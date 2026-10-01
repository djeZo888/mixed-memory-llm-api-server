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
import time
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


def publish_cleanup_evidence(config,receipts,trace,producer,container,native_id,raw_exit,requested_stop,cli_reaped,rm_exit,exists_exit,pipes_joined):
    trace_ok=True
    if trace is not None:
        try:trace.publish(receipts,producer,native_id,raw_exit,requested_stop,cli_reaped and rm_exit==0 and exists_exit==1 and pipes_joined)
        except Exception:trace_ok=False
    settlement_ok=True
    try:receipts['publish_settlement'](config,producer,container,native_id,raw_exit,requested_stop,cli_reaped,rm_exit,exists_exit,pipes_joined)
    except Exception:settlement_ok=False
    return trace_ok and settlement_ok

def cleanup_command(argv, timeout, env, config, receipts, producer, container, name):
    """Own/reap this exact fresh cleanup CLI; seal raw terminal before later checks."""
    process = None; identity = None; error = None; raw_exit = None
    started = time.monotonic()
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, env=env, start_new_session=True)
        if config is not None:
            try: identity = receipts['process_identity'](process.pid)
            except Exception: pass  # Missing birth remains an explicit unknown fact.
        try: raw_exit = process.wait(timeout=max(0.01, timeout - min(2, timeout/4)))
        except subprocess.TimeoutExpired as failure:
            error = failure
            # Exact Popen PID/group remains unreaped/owned; no PID-name lookup.
            os.killpg(process.pid, signal.SIGKILL)
            raw_exit = process.wait(timeout=max(0.01, timeout - (time.monotonic()-started)))
    except Exception as failure:
        error = failure
    finally:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
                raw_exit = process.wait(timeout=max(0.01, timeout - (time.monotonic()-started)))
            except Exception as failure:
                if error is None: error = failure
        if process is not None and type(process.returncode) is int: raw_exit=process.returncode
        if config is not None:
            receipts['publish_cleanup_terminal'](config, producer, container, name,
                process.pid if process is not None else None, identity, raw_exit, error)
    if error is not None: raise error
    return subprocess.CompletedProcess(argv, raw_exit)


def main():
    if sys.argv[1:] in (["--help"], ["-h"]):
        os.write(1, b"Private ACP supervisor: invoked by run-engine.sh with local Podman run arguments.\n"
                    b"Filters the environment-provided ephemeral token and cleans up its exact container.\n")
        return 0
    token = os.environ.get("AI_HARNESS_GATEWAY_TOKEN", "")
    if not token or len(sys.argv) < 3 or sys.argv[2:5] != ["--remote=false", "--cgroup-manager=systemd", "run"]:
        os.write(2, b"run-engine: invalid private ACP supervisor invocation\n")
        return 64
    podman = sys.argv[1]
    container = "ai-harness-" + uuid.uuid4().hex
    args = [podman, *sys.argv[2:5], "--name", container, *sys.argv[5:]]
    stopped = threading.Event()
    pipe_failed = threading.Event()
    received_signal = [0]

    def on_signal(number, _frame):
        received_signal[0] = number
        stopped.set()

    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(number, on_signal)

    trace = None

    def copy_stream(source, destination):
        redactor = Redactor(token)
        try:
            while True:
                chunk = os.read(source.fileno(), 65536)
                if not chunk:
                    if destination == 2 and trace is not None: trace.feed(b"",final=True)
                    write_all(destination, redactor.feed(b"", final=True))
                    return
                if destination == 2 and trace is not None: trace.feed(chunk)
                write_all(destination, redactor.feed(chunk))
        except Exception:
            # No raw-stream fallback and no exception text containing payloads.
            pipe_failed.set()
            stopped.set()

    process = None
    filters = []
    code = 125
    cleanup_ok = True
    engine_exited = False
    failure_observed = False
    failure_published = False
    requested_stop = False
    receipt_config = receipts = producer = native_id = None
    rm_exit = exists_exit = None
    failure_phase = "bootstrap"
    try:
        if os.environ.get('AI_HARNESS_CODEX_RECEIPT_DIR') or os.environ.get('AI_HARNESS_CODEX_RECEIPT_NONCE'):
            import runpy
            from pathlib import Path
            receipts = runpy.run_path(str(Path(__file__).resolve().with_name('codex_receipts.py')))
            receipt_config = receipts['channel']()
            producer = receipts['process_identity']()
            receipts['publish_producer'](receipt_config, producer, container)
            if receipt_config and receipt_config[1].get('nativeTraceMode'):
                module=runpy.run_path(str(Path(__file__).resolve().with_name('codex_native_trace.py')))
                trace=module['TraceCapture'](receipt_config)
        if stopped.is_set():
            requested_stop = bool(received_signal[0])
            raise InterruptedError('stop before Podman child creation')
        if receipt_config is not None:
            receipts['verify_child_gate'](receipt_config, producer, container)
        failure_phase = "spawn"
        process = subprocess.Popen(args, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        if receipt_config is not None:
            receipts['publish_cli'](receipt_config, producer, container, process.pid)
        for source, destination in ((process.stdout, 1), (process.stderr, 2)):
            worker = threading.Thread(target=copy_stream, args=(source, destination), daemon=True)
            worker.start()
            filters.append(worker)
        if receipt_config is not None:
            failure_phase = 'inspect-launch'
            launch = receipts['inspect_launch'](podman, container, args, receipt_config)
            native_id = launch['container']['id']
        failure_phase = 'run'
        while not stopped.is_set():
            try:
                code = process.wait(timeout=0.1)
                engine_exited = True
                break
            except subprocess.TimeoutExpired:
                pass
        if pipe_failed.is_set():
            raise OSError('ACP pipe forwarding failed')
        if engine_exited and code != 0:
            raise RuntimeError('original engine exited unsuccessfully')
        # A requested stop is acknowledged only after verified settlement below.
        # An already observed engine failure is never normalized by a signal.
        requested_stop = bool(received_signal[0]) and not engine_exited
    except Exception as error:
        failure_observed = True
        code = 125 if not engine_exited else code
        if receipt_config is not None and producer is not None:
            try:
                receipts['publish_failure'](receipt_config,producer,failure_phase,error)
                failure_published = True
            except Exception: pass
        try: os.write(2, b"run-engine: ACP process failed\n")
        except OSError: pass
    finally:
        # A second TERM must not interrupt cleanup and strand the container.
        for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(number, signal.SIG_IGN)
        if process is not None and process.poll() is not None and not engine_exited:
            if not failure_observed: code = process.returncode
            engine_exited = True
            requested_stop = False
        if engine_exited and code != 0 and not failure_observed:
            failure_observed = True
            if receipt_config is not None and producer is not None:
                try:
                    receipts['publish_failure'](receipt_config, producer, 'run', RuntimeError('original engine exit observed before stop'))
                    failure_published = True
                except Exception: pass
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
        if receipt_config is not None and producer is not None:
            try: receipts['publish_cli_terminal'](receipt_config, producer, container, process)
            except Exception: cleanup_ok = False
        # Stop CLI creation first, then remove this exact container. Podman's
        # forced removal terminates its container process tree after 20 seconds.
        # Never report successful settlement if local cleanup cannot complete.
        if process is not None:
            cleanup_env = {key: value for key, value in os.environ.items() if not key.startswith("AI_HARNESS_")}
            try:
                result = cleanup_command([podman, "--remote=false", "rm", "--force", "--time", "20", "--ignore", container],
                                         28, cleanup_env, receipt_config, receipts, producer, container, 'rm-terminal')
                rm_exit = result.returncode
                cleanup_ok = cleanup_ok and result.returncode == 0
            except Exception:
                cleanup_ok = False
            # rm success alone is insufficient: Podman must explicitly report this
            # exact random container absent (exists exit1). Exit0 or errors are not
            # a settlement receipt. Cleanup budget: CLI4 + rm28 + exists2 + pipes4.
            try:
                result = cleanup_command([podman, "--remote=false", "container", "exists", container],
                                         2, cleanup_env, receipt_config, receipts, producer, container, 'exists-terminal')
                exists_exit = result.returncode
                cleanup_ok = cleanup_ok and result.returncode == 1
            except Exception:
                cleanup_ok = False
        for worker in filters:
            worker.join(timeout=2)
        # If a postfork gate failed before filters started, close the actual
        # owned read pipes after reap; no vacuous joined-empty-list claim.
        pipes_closed = True
        if process is not None and len(filters) != 2:
            for source in (process.stdout, process.stderr):
                try: source.close()
                except Exception: pipes_closed = False
        if not pipes_closed or any(worker.is_alive() for worker in filters) or pipe_failed.is_set():
            cleanup_ok = False
        if receipt_config is not None and producer is not None:
            if not cleanup_ok and not failure_published:
                try:
                    receipts['publish_failure'](receipt_config, producer, 'cleanup', RuntimeError('original cleanup unconfirmed'))
                    failure_published = True
                except Exception: pass
            try:
                receipts['publish_cleanup'](receipt_config, producer, container, process,
                    rm_exit, exists_exit, pipes_closed and not any(worker.is_alive() for worker in filters),
                    pipe_failed.is_set(), received_signal[0], failure_observed)
            except Exception: cleanup_ok = False
            published=publish_cleanup_evidence(receipt_config,receipts,trace,producer,container,native_id,
                process.returncode if process is not None else None,requested_stop,
                process is not None and process.poll() is not None,rm_exit,exists_exit,
                pipes_closed and not any(worker.is_alive() for worker in filters) and not pipe_failed.is_set())
            cleanup_ok=cleanup_ok and published
        if not cleanup_ok:
            # Fixed text only; stderr may be closed after the server cancels.
            try:
                os.set_blocking(2, False)
                os.write(2, b"run-engine: container settlement unconfirmed; workspace requires operator review\n")
            except OSError:
                pass
            code = 125
        elif requested_stop and process is not None and not failure_observed:
            # SERVER treats exit0 as the clean cancellation acknowledgment.
            # ACP stdout remains exclusively the engine's byte stream.
            code = 0
    return code if code >= 0 else 128 - code


if __name__ == "__main__":
    # Daemon pipe workers must not keep the launcher alive if the peer stops
    # reading. All container stop/reap work happens above before bounded exit.
    os._exit(main())
