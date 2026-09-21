"""Disposable POSIX process fixture, NEVER a production package scope.

A token-authenticated supervisor owns a process group created by its own Popen.
The group contains a leader, fake apt parent and child. It cannot prove Linux
cgroup containment or systemd behavior. No host package command is executed.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
from install.core import InstallError, Runner
from install.prerequisites import Prerequisites

SENTINEL = b"#!/bin/sh\n# local-ai installer temporary package service inhibitor\nexit 101\n"
HERE = str(Path(__file__).resolve())


def wait_until(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.02)
    raise AssertionError("disposable process fixture deadline exceeded")


def group_members(pgid):
    result = subprocess.run(["ps", "-axo", "pid=,pgid=,stat="],
                            capture_output=True, text=True, check=True)
    return [(int(row[0]), row[2]) for line in result.stdout.splitlines()
            if len(row := line.split()) == 3 and int(row[1]) == pgid]


def pid_is_live(pid):
    result = subprocess.run(["ps", "-p", str(pid), "-o", "stat="],
                            capture_output=True, text=True, check=False)
    return bool(result.stdout.strip()) and not result.stdout.strip().startswith("Z")


class FakePackageScope:
    """Adapter to a real independent disposable supervisor, with durable token.

    Signal targets never come from persisted PID fields. Only supervisor-owned,
    unreaped Popen groups can be signalled, after exact token identity checks.
    This is deliberately less capable than production Linux cgroups.
    """
    def __init__(self, root, *, attach=False):
        self.root = Path(root)
        self.socket_path = str(self.root / "manager.sock")
        self.manager = None
        if not attach:
            self.manager = subprocess.Popen([sys.executable, HERE, "supervisor", str(root)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True, close_fds=True)
            wait_until(lambda: (self.root / "manager-ready").exists())

    def request(self, action, **values):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
                channel.settimeout(3)
                channel.connect(self.socket_path)
                channel.sendall((json.dumps({"action": action, **values}) + "\n").encode())
                stream = channel.makefile("rb")
                response = json.loads(stream.readline())
        except (OSError, ValueError):
            raise InstallError("package_fixture_inspection_unavailable") from None
        if "error" in response:
            raise InstallError(response["error"])
        return response

    def new_identity(self):
        return self.request("allocate")["identity"]

    def prepare(self, identity, *, gate_path, timeout):
        return self.request("prepare", identity=identity, gate_path=str(gate_path),
                            timeout=timeout)["identity"]

    def inspect(self, identity):
        if (self.root / "inspect-failure").exists():
            raise InstallError("package_fixture_inspection_unavailable")
        return self.request("inspect", identity=identity)

    def execute(self, identity, argv, *, gate_path, env=None):
        self.request("execute", identity=identity, argv=list(argv),
                     gate_path=str(gate_path), env=env)
        return ""

    def _terminal(self, identity):
        result = self.inspect(identity)
        return result if result["state"] == "quiescent" else None

    def abort(self, identity):
        return self.request("abort", identity=identity)

    def close(self):
        if self.manager is None:
            return
        try:
            self.request("shutdown")
        finally:
            try:
                self.manager.wait(timeout=8)
            except subprocess.TimeoutExpired:
                # The supervisor owns children; kill is deliberately not a
                # fallback, since losing it would discard cleanup authority.
                raise AssertionError("fixture supervisor failed to clean up")
            if self.manager.returncode != 0:
                raise AssertionError("fixture supervisor exited unsuccessfully")


class FixtureRunner(Runner):
    """Only discovery is synthetic; production package Runner stays real."""
    def run(self, argv, *, timeout=120, env=None):
        if argv == ["id", "-u"]:
            return "0\n"
        if argv == ["dpkg", "--audit"]:
            return "fixture package incomplete\n" if (self.package_scope.root / "audit-incomplete").exists() else ""
        if argv[:3] == ["df", "-B1", "--output=avail"]:
            return "Avail\n107374182400\n"
        raise AssertionError("unexpected command in package fixture: " + repr(argv))


def make_subject(root, lease_fd, scope):
    root = Path(root)
    data = root / "data"
    data.mkdir(mode=0o700, exist_ok=True)
    runner = FixtureRunner(True, package_lease_fd=lease_fd, package_scope=scope)
    return Prerequisites({"data_dir": str(data)}, runner, lambda: None,
                         policy_path=root / "policy-rc.d")


def fake_argv(root, mode):
    return [sys.executable, HERE, "apt", str(root), mode]


def supervisor(root):
    socket_path = root / "manager.sock"
    records = {}
    stopping = False
    terminal_since = None

    def update(record):
        process = record.get("process")
        if process is None or record["state"] == "quiescent":
            return
        live = [pid for pid, state in group_members(process.pid) if not state.startswith("Z")]
        if not live:
            process.wait(timeout=1)
            record["state"] = "quiescent"
            result_path = record["directory"] / "result.json"
            result = json.loads(result_path.read_text()) if result_path.exists() else {}
            record["successful"] = result.get("returncode") == 0 and not record.get("terminated")
            return
        elapsed = time.monotonic()
        if elapsed >= record["deadline"] and not record.get("terminated"):
            # Exact authenticated record owns this still-unreaped group leader.
            os.killpg(process.pid, signal.SIGTERM)
            (root / "term-sent").touch()
            record["terminated"] = elapsed
        if record.get("terminated") and elapsed >= record["terminated"] + .3 and not record.get("killed"):
            os.killpg(process.pid, signal.SIGKILL)
            record["killed"] = True

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(socket_path))
        server.listen(8)
        server.settimeout(.025)
        (root / "manager-ready").touch()
        while True:
            for record in records.values():
                update(record)
            if stopping and all(record["state"] == "quiescent" for record in records.values()):
                if terminal_since is None:
                    terminal_since = time.monotonic()
                if time.monotonic() - terminal_since > .5:
                    return
            try:
                channel, _ = server.accept()
            except socket.timeout:
                continue
            with channel:
                request = json.loads(channel.makefile("rb").readline())
                action = request["action"]
                response = {}
                if action == "allocate":
                    nonce = uuid.uuid4().hex
                    identity = {"transaction_id": nonce, "unit": "fixture-" + nonce + ".service",
                                "boot_id": str(uuid.uuid4()), "fixture_token": uuid.uuid4().hex}
                    records[nonce] = {"identity": identity, "state": "quiescent", "successful": False}
                    response = {"identity": identity}
                elif action == "shutdown":
                    stopping = True
                    for record in records.values():
                        record["deadline"] = 0
                else:
                    identity = request.get("identity", {})
                    record = records.get(identity.get("transaction_id"))
                    if record is None or record["identity"] != identity:
                        response = {"error": "package_fixture_identity_mismatch"}
                    elif action == "prepare":
                        if "process" in record:
                            response = {"error": "package_fixture_identity_reused"}
                        else:
                            directory = root / identity["transaction_id"]
                            directory.mkdir(mode=0o700)
                            process = subprocess.Popen([sys.executable, HERE, "group", str(directory)],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True, close_fds=True)
                            identity = {**identity, "invocation_id": uuid.uuid4().hex,
                                        "fixture_group": process.pid}
                            record.update(identity=identity, directory=directory, process=process,
                                state="live", successful=False, deadline=time.monotonic() + request["timeout"],
                                gate_path=request["gate_path"])
                            response = {"identity": identity}
                    elif action == "inspect":
                        response = {"state": record["state"], "successful": record["successful"]}
                    elif action == "execute":
                        if request["gate_path"] != record["gate_path"] or record.get("executed"):
                            response = {"error": "package_fixture_gate_mismatch"}
                        else:
                            record["executed"] = True
                            pending = record["directory"] / "request.tmp"
                            pending.write_text(json.dumps(request))
                            pending.replace(record["directory"] / "request.json")
                    elif action == "abort":
                        record["deadline"] = 0
                    else:
                        response = {"error": "package_fixture_unknown_action"}
                channel.sendall((json.dumps(response) + "\n").encode())


def group(directory):
    # Keep a live, unreaped process group leader through timeout escalation.
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    request_path = directory / "request.json"
    wait_until(request_path.exists, timeout=12)
    request = json.loads(request_path.read_text())
    process = subprocess.Popen(request["argv"], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               env=request.get("env") or None)
    returncode = process.wait()
    (directory / "result.json").write_text(json.dumps({"returncode": returncode}))
    (directory.parent / "apt-parent-exited").write_text(str(returncode))
    if returncode < 0:
        while True:
            time.sleep(.05)


def apt(root, mode):
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    (root / "apt.pid").write_text(str(os.getpid()))
    process = subprocess.Popen([sys.executable, HERE, "child", str(root), mode],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    process.wait()
    return 7 if mode == "nonzero" else 0


def child(root, mode):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    (root / "child.pid").write_text(str(os.getpid()))
    deadline = time.monotonic() + (.18 if mode in {"normal", "nonzero"} else 20)
    while time.monotonic() < deadline:
        path = root / "policy-rc.d"
        if not path.exists() or path.read_bytes() != SENTINEL:
            (root / "child-saw-restored").touch()
        if (root / "term-sent").exists():
            (root / "stubborn-after-term").touch()
        (root / "heartbeat").write_text(str(time.monotonic()))
        time.sleep(.01)
    (root / "child-exited").touch()


def installer(root, mode, timeout):
    if mode == "handshake":
        # Deterministically pause only the fixture keeper immediately before
        # READY; killing the CLI closes the pipe reader and forces BrokenPipe.
        original_write = os.write
        def pause_ready(fd, value):
            if value == b"R":
                (root / "keeper-before-ready").touch()
                wait_until(lambda: (root / "keeper-release-ready").exists(), timeout=6)
            return original_write(fd, value)
        os.write = pause_ready
    descriptor = os.open(root / "lifecycle.lock", os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    scope = FakePackageScope(root, attach=True)
    subject = make_subject(root, descriptor, scope)
    if mode == "before-watcher":
        def pause_before_watcher(identity):
            (root / "before-watcher").touch()
            wait_until(lambda: (root / "release-fixture-pause").exists(), timeout=10)
        subject.runner.hold_package_lease = pause_before_watcher
    elif mode == "after-ready":
        def pause_before_gate(identity, argv, **kwargs):
            (root / "after-ready-before-gate").touch()
            wait_until(lambda: (root / "release-fixture-pause").exists(), timeout=10)
        subject.runner.run_package = pause_before_gate
    elif mode == "watcher-dies":
        original_execute = scope.execute
        def execute_then_lose_watcher(identity, argv, **kwargs):
            result = original_execute(identity, argv, **kwargs)
            wait_until(lambda: (root / "child.pid").exists(), timeout=5)
            # Only this actual owning CLI knows its unreaped fork child. No
            # saved marker PID or externally supplied PID authorizes this kill.
            keeper = subject.runner._package_watchers[-1]
            if os.waitpid(keeper, os.WNOHANG)[0]:
                raise AssertionError("fixture keeper exited before deliberate crash")
            os.kill(keeper, signal.SIGKILL)
            if os.waitpid(keeper, 0) != (keeper, signal.SIGKILL):
                raise AssertionError("fixture keeper SIGKILL was not reaped")
            subject.runner._package_watchers.remove(keeper)
            (root / "watcher-reaped").touch()
            wait_until(lambda: (root / "release-fixture-pause").exists(), timeout=10)
            return result
        scope.execute = execute_then_lose_watcher
    try:
        subject._package_install(fake_argv(root, mode), timeout=float(timeout), env=None)
    finally:
        os.close(descriptor)


if __name__ == "__main__":
    action, root = sys.argv[1], Path(sys.argv[2])
    if action == "supervisor":
        supervisor(root)
    elif action == "group":
        group(root)
    elif action == "apt":
        sys.exit(apt(root, sys.argv[3]))
    elif action == "child":
        child(root, sys.argv[3])
    elif action == "installer":
        installer(root, sys.argv[3], sys.argv[4])
    else:
        raise SystemExit("unsupported disposable fixture action")
