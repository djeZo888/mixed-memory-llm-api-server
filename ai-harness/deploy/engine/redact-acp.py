#!/usr/bin/env python3
"""Byte-preserving ACP token filter and bounded lifecycle for one local container.

The token is read only from the environment. No command, payload or exception is
logged. Container cleanup addresses a fresh random name, never a shared label.
"""
import json
import os
import re
import signal
import subprocess
import sys
import threading
import uuid


class Redactor:
    def __init__(self, token):
        self.patterns = tuple(sorted({token.encode(), json.dumps(token, ensure_ascii=False)[1:-1].encode(),
                                      json.dumps(token, ensure_ascii=True)[1:-1].encode()}, key=len, reverse=True))
        self.expression = re.compile(b"|".join(re.escape(pattern) for pattern in self.patterns))
        self.pending = b""

    def feed(self, data, final=False):
        data = self.expression.sub(b"[REDACTED]", self.pending + data)
        keep = 0
        if not final:
            for size in range(min(len(data), max(map(len, self.patterns)) - 1), 0, -1):
                if any(pattern.startswith(data[-size:]) for pattern in self.patterns):
                    keep = size
                    break
        self.pending = data[-keep:] if keep else b""
        return data[:-keep] if keep else data


def write_all(fd, data):
    while data:
        data = data[os.write(fd, data):]


def main():
    if sys.argv[1:] in (["--help"], ["-h"]):
        os.write(1, b"Private ACP supervisor: invoked by run-engine.sh with local Podman run arguments.\n"
                    b"Filters the environment-provided ephemeral token and cleans up its exact container.\n")
        return 0
    token = os.environ.get("AI_HARNESS_GATEWAY_TOKEN", "")
    if not token or len(sys.argv) < 3 or sys.argv[2:4] != ["--remote=false", "run"]:
        os.write(2, b"run-engine: invalid private ACP supervisor invocation\n")
        return 64
    podman = sys.argv[1]
    container = "ai-harness-" + uuid.uuid4().hex
    args = [podman, *sys.argv[2:4], "--name", container, *sys.argv[4:]]
    stopped = threading.Event()
    pipe_failed = threading.Event()
    received_signal = [0]

    def on_signal(number, _frame):
        received_signal[0] = number
        stopped.set()

    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(number, on_signal)

    def copy_stream(source, destination):
        redactor = Redactor(token)
        try:
            while True:
                chunk = os.read(source.fileno(), 65536)
                if not chunk:
                    write_all(destination, redactor.feed(b"", final=True))
                    return
                write_all(destination, redactor.feed(chunk))
        except (OSError, ValueError):
            # No raw-stream fallback and no exception text containing payloads.
            pipe_failed.set()
            stopped.set()

    process = None
    filters = []
    code = 125
    cleanup_ok = True
    try:
        process = subprocess.Popen(args, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        for source, destination in ((process.stdout, 1), (process.stderr, 2)):
            worker = threading.Thread(target=copy_stream, args=(source, destination), daemon=True)
            worker.start()
            filters.append(worker)
        while not stopped.is_set():
            try:
                code = process.wait(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                pass
        if received_signal[0]:
            code = 128 + received_signal[0]
        elif pipe_failed.is_set():
            code = 125
    except (OSError, ValueError):
        os.write(2, b"run-engine: ACP process start failed\n")
    finally:
        # A second TERM must not interrupt cleanup and strand the container.
        for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(number, signal.SIG_IGN)
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    cleanup_ok = False
            except ProcessLookupError:
                pass
            except OSError:
                cleanup_ok = False
        # Stop CLI creation first, then remove this exact container. Podman's
        # forced removal terminates its container process tree after 20 seconds.
        # Never report successful settlement if local cleanup cannot complete.
        cleanup_env = {key: value for key, value in os.environ.items() if not key.startswith("AI_HARNESS_")}
        try:
            result = subprocess.run([podman, "--remote=false", "rm", "--force", "--time", "20", "--ignore", container],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=30, env=cleanup_env, check=False)
            cleanup_ok = cleanup_ok and result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            cleanup_ok = False
        for worker in filters:
            worker.join(timeout=2)
        if any(worker.is_alive() for worker in filters) or pipe_failed.is_set():
            cleanup_ok = False
        if not cleanup_ok:
            # Fixed text only; stderr may be closed after the server cancels.
            try:
                os.set_blocking(2, False)
                os.write(2, b"run-engine: container settlement unconfirmed; workspace requires operator review\n")
            except OSError:
                pass
            code = 125
    return code if code >= 0 else 128 - code


if __name__ == "__main__":
    # Daemon pipe workers must not keep the launcher alive if the peer stops
    # reading. All container stop/reap work happens above before bounded exit.
    os._exit(main())
