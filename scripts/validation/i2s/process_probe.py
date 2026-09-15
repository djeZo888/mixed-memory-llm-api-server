#!/usr/bin/env python3
"""Actual Linux disk-lock process adapters; never opens a device or installs anything.

The child deadline belongs to this harmless adapter, not the production helper.
The production DiskIO.command and transaction_lock are imported unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid

REPO = Path(__file__).resolve().parents[3]
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1"}
ROOT_PATTERN = re.compile(r"i2s-process-[a-f0-9]{32}-[A-Za-z0-9_]+\Z")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def plan():
    return {
        "proof": "real_DiskIO_and_disk_local_lock_with_harmless_process_adapters",
        "fixture_devices": 0,
        "maximum_adapter_seconds": 30,
        "cases": ["parent_SIGKILL_live_child_disk_lock", "caught_timeout_live_descendant", "unrelated_sentinel_preserved"],
        "not_tested": ["real_disk_tool_hard_parent_death", "canonical_global_admission", "production_autonomous_child_deadline"],
    }


def _guard():
    require(platform.system() == "Linux" and os.geteuid() == 0, "requires_disposable_linux_root")
    spec = importlib.util.spec_from_file_location("i2s_process_i2p_guard", REPO / "scripts/validation/i2p/run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate_context(os.environ)
    release = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line)
    require(release.get("ID", "").strip('"') == "ubuntu" and release.get("VERSION_ID", "").strip('"') == "24.04", "requires_ubuntu_24_04")
    require(platform.machine() == "x86_64", "requires_amd64")
    parent_ns = os.environ.get("I2S_PARENT_NAMESPACE")
    require(parent_ns and os.readlink("/proc/self/ns/mnt") != parent_ns, "requires_private_i2s_mount_namespace")
    require(hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal"), "missing_python_pidfd_prerequisite")


def _disk_module():
    path = str(REPO / "scripts")
    if path not in sys.path:
        sys.path.insert(0, path)
    from install import disk_init
    return disk_init


def _parse_proc_stat(raw):
    prefix, tail = raw.rsplit(") ", 1)
    fields = tail.split()
    require(len(fields) >= 20, "invalid_process_stat")
    return {"pid": int(prefix.split(" ", 1)[0]), "state": fields[0], "ppid": int(fields[1]),
            "pgrp": int(fields[2]), "session": int(fields[3]), "starttime": int(fields[19])}


def _identity(pid):
    require(type(pid) is int and pid > 1, "unsafe_process_pid")
    try:
        result = _parse_proc_stat(Path(f"/proc/{pid}/stat").read_text())
    except FileNotFoundError:
        return None
    require(result["pid"] == pid, "process_pid_changed")
    return result


def _same_process(expected, observed):
    return observed is not None and (expected["pid"], expected["starttime"]) == (observed["pid"], observed["starttime"])


def _live(expected):
    observed = _identity(expected["pid"])
    if observed is None:
        return False
    require(_same_process(expected, observed), "process_ownership_changed_preserve_state")
    return observed["state"] != "Z"


def _signal_exact(expected, signum):
    """Use a pidfd after checking starttime; never signal a numeric PID/group."""
    observed = _identity(expected["pid"])
    if observed is None:
        return False
    require(_same_process(expected, observed), "process_ownership_changed_refuse_signal")
    if observed["state"] == "Z":
        return False
    try:
        fd = os.pidfd_open(expected["pid"], 0)
    except ProcessLookupError:
        return False
    try:
        observed = _identity(expected["pid"])
        if observed is None:
            return False
        require(_same_process(expected, observed), "process_ownership_changed_refuse_signal")
        signal.pidfd_send_signal(fd, signum, None, 0)
        return True
    except ProcessLookupError:
        return False
    finally:
        os.close(fd)


def _write(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and
                stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1 and info.st_size < 8192,
                "unsafe_process_record")
        value = json.load(stream)
    require(isinstance(value, dict), "invalid_process_record")
    return value


def _wait_record(path, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            # The writer creates exclusively, then emits one bounded record.
            try:
                return _read(path)
            except json.JSONDecodeError:
                pass
        time.sleep(0.025)
    raise RuntimeError("adapter_ready_deadline_exceeded")


def _wait_gone(expected, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        observed = _identity(expected["pid"])
        if observed is None:
            return True
        require(_same_process(expected, observed), "process_ownership_changed_preserve_state")
        time.sleep(0.025)
    return False


def _protected_root(root):
    require(root.parent == Path("/run") and ROOT_PATTERN.fullmatch(root.name), "unsafe_process_root")
    info = root.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700,
            "unsafe_process_root")
    require(root.resolve() == root, "symlink_process_root")
    return info


def _worker(root, role, token):
    """Internal adapters require a live exact coordinator and private namespace."""
    require(platform.system() == "Linux" and os.geteuid() == 0, "requires_disposable_linux_root")
    os.umask(0o077)
    _protected_root(root)
    intent = _read(root / "intent.json")
    require(intent["token"] == token and intent["namespace"] == os.readlink("/proc/self/ns/mnt") and
            intent["namespace"] != intent["parent_namespace"], "invalid_adapter_intent")
    require(_same_process(intent["coordinator"], _identity(intent["coordinator"]["pid"])), "adapter_coordinator_changed")
    disk = _disk_module()
    location = root / ("timeout" if role in {"timeout-leader", "timeout-child"} else "hard")
    storage = disk.Storage({}, None, location)
    own = _identity(os.getpid())
    if role in {"sentinel", "hard-child", "timeout-child"}:
        duration = {"sentinel": 30, "hard-child": 6, "timeout-child": 8}[role]
        if role != "sentinel":
            owner_record = _read(root / ("hard-parent.json" if role == "hard-child" else "timeout-owner.json"))
            fd = owner_record["lock_fd"]
            info = os.fstat(fd)
            require((info.st_dev, info.st_ino) == tuple(owner_record["lock_identity"]), "adapter_inherited_lock_changed")
            own.update(lock_fd=fd, lock_identity=[info.st_dev, info.st_ino])
        own["adapter_deadline_seconds"] = duration
        _write(root / (role + ".json"), own)
        time.sleep(duration)
        return 0
    if role == "hard-parent":
        io = disk.DiskIO(storage)
        with disk.transaction_lock(storage, io):
            info = os.fstat(io.lock_fd)
            own.update(lock_fd=io.lock_fd, lock_identity=[info.st_dev, info.st_ino])
            _write(root / "hard-parent.json", own)
            io.command([sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--worker", str(root), "hard-child", token], timeout=12)
        return 0
    if role == "timeout-leader":
        owner_record = _read(root / "timeout-owner.json")
        child = subprocess.Popen([sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--worker", str(root), "timeout-child", token],
                                 stdin=subprocess.DEVNULL, pass_fds=(owner_record["lock_fd"],), env=ENV)
        record = _wait_record(root / "timeout-child.json", timeout=1)
        require(record["pid"] == child.pid, "timeout_child_identity_changed")
        _write(root / "timeout-leader.json", own)
        return 0
    raise RuntimeError("unknown_adapter_role")


def _lock_descriptor(record):
    require(_live(record), "expected_adapter_child_not_live")
    info = Path(f'/proc/{record["pid"]}/fd/{record["lock_fd"]}').stat()
    require([info.st_dev, info.st_ino] == record["lock_identity"], "child_lock_descriptor_changed")
    return {"device": info.st_dev, "inode": info.st_ino, "fd": record["lock_fd"]}


def _remove_owned(root, original):
    current = _protected_root(root)
    require((current.st_dev, current.st_ino) == (original.st_dev, original.st_ino), "process_root_ownership_changed")
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        target = line.split()[4]
        require(target != str(root) and not target.startswith(str(root) + "/"), "unexpected_process_scratch_mount_preserved")
    require(shutil.rmtree.avoids_symlink_attacks, "unsafe_recursive_cleanup_platform")
    shutil.rmtree(root)


def run_probe():
    _guard()
    disk = _disk_module()
    token = uuid.uuid4().hex
    root = Path(tempfile.mkdtemp(prefix="i2s-process-" + token + "-", dir="/run"))
    root.chmod(0o700)
    original = _protected_root(root)
    result = {"status": "FAIL", "plan": plan(), "cases": {}, "cleanup": {"status": "NOT_TESTED"},
              "source_sha256": {"process_probe.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                "disk_init.py": hashlib.sha256((REPO / "scripts/install/disk_init.py").read_bytes()).hexdigest()}}
    direct = []
    owned = []
    sentinel_record = None
    try:
        coordinator = _identity(os.getpid())
        _write(root / "intent.json", {"token": token, "coordinator": coordinator,
            "namespace": os.readlink("/proc/self/ns/mnt"), "parent_namespace": os.environ["I2S_PARENT_NAMESPACE"]})
        for name in ("hard", "timeout"):
            (root / name / "etc").mkdir(mode=0o700, parents=True)
        def launch(role):
            process = subprocess.Popen([sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--worker", str(root), role, token],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=ENV, start_new_session=True)
            direct.append(process)
            identity = _identity(process.pid)
            require(identity is not None, "adapter_exited_before_identity")
            owned.append(identity)
            return process
        sentinel = launch("sentinel")
        sentinel_record = _wait_record(root / "sentinel.json")
        require(sentinel_record["pid"] == sentinel.pid, "sentinel_identity_changed")
        parent = launch("hard-parent")
        parent_record = _wait_record(root / "hard-parent.json")
        require(parent_record["pid"] == parent.pid, "initializer_identity_changed")
        child = _wait_record(root / "hard-child.json")
        owned.append(child)
        require(child["ppid"] == parent.pid, "hard_child_parent_changed")
        descriptor_before = _lock_descriptor(child)
        require(_signal_exact(parent_record, signal.SIGKILL), "initializer_not_live_before_SIGKILL")
        require(parent.wait(timeout=3) == -signal.SIGKILL, "initializer_did_not_die_by_SIGKILL")
        descriptor_after = _lock_descriptor(child)
        require(descriptor_before == descriptor_after, "child_lock_changed_after_parent_death")
        storage = disk.Storage({}, None, root / "hard")
        blocked = None
        try:
            with disk.transaction_lock(storage, disk.DiskIO(storage)):
                raise RuntimeError("disk_contender_admitted_while_child_live")
        except disk.StorageError as error:
            blocked = str(error)
        require(blocked == "disk transaction or surviving child is active", "unexpected_disk_contender_error")
        require(_live(child), "child_not_live_during_contender_proof")
        natural_exit = _wait_gone(child, timeout=10)
        require(natural_exit, "adapter_child_did_not_exit_by_its_own_deadline")
        with disk.transaction_lock(storage, disk.DiskIO(storage)):
            pass
        result["cases"]["parent_SIGKILL_live_child"] = {"status": "PASS", "initializer_returncode": parent.returncode,
            "initializer": parent_record, "child": child, "child_lock_after_parent_death": descriptor_after,
            "contender_error": blocked, "contender_admitted_after_child_exit": True,
            "child_exit": "adapter_self_deadline_proc_absent", "scope": "disk_local_lock_harmless_process_adapter"}
        storage = disk.Storage({}, None, root / "timeout")
        io = disk.DiskIO(storage)
        caught = None
        with disk.transaction_lock(storage, io):
            info = os.fstat(io.lock_fd)
            _write(root / "timeout-owner.json", {"lock_fd": io.lock_fd, "lock_identity": [info.st_dev, info.st_ino]})
            try:
                io.command([sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--worker", str(root), "timeout-leader", token], timeout=1.5)
            except disk.StorageError as error:
                caught = str(error)
        descendant = _wait_record(root / "timeout-child.json", timeout=1)
        owned.append(descendant)
        leader = _wait_record(root / "timeout-leader.json", timeout=1)
        require(descendant["pgrp"] == leader["pid"] and descendant["session"] == leader["pid"], "timeout_descendant_left_owned_session")
        require(caught == "disk command unavailable or timed out; intent retained", "unexpected_timeout_result")
        require(_wait_gone(descendant, timeout=4), "timeout_descendant_not_reaped")
        with disk.transaction_lock(storage, disk.DiskIO(storage)):
            pass
        result["cases"]["caught_timeout_live_descendant"] = {"status": "PASS", "error": caught,
            "leader": leader, "child": descendant, "descendant_absent_after_caught_timeout": True,
            "disk_lock_reacquired": True, "scope": "real_DiskIO_command_with_harmless_process_adapter"}
        require(_live(sentinel_record) and sentinel.poll() is None, "unrelated_sentinel_was_killed")
        result["cases"]["unrelated_sentinel"] = {"status": "PASS", "identity": sentinel_record,
            "survived_parent_SIGKILL_and_caught_timeout": True}
        result["status"] = "PASS"
    except Exception as error:
        # Messages are fixed harness/Storage errors, never raw child output/env.
        result["error"] = {"type": type(error).__name__, "message": str(error)[:256]}
    finally:
        cleanup_errors = []
        # Discover only this fixture's explicitly named records after an early failure.
        for name in ("hard-child", "timeout-child"):
            path = root / (name + ".json")
            if path.exists():
                try:
                    record = _read(path)
                    if not any(_same_process(record, old) for old in owned):
                        owned.append(record)
                except Exception:
                    cleanup_errors.append("unreadable_owned_child_record")
        for record in reversed(owned):
            try:
                _signal_exact(record, signal.SIGTERM)
            except Exception:
                cleanup_errors.append("unknown_process_ownership_no_signal")
        for process in direct:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                cleanup_errors.append("direct_adapter_did_not_exit")
        for record in owned:
            try:
                if not _wait_gone(record, timeout=2):
                    cleanup_errors.append("owned_process_still_present")
            except Exception:
                cleanup_errors.append("process_identity_changed_preserve_state")
        if not cleanup_errors:
            try:
                _remove_owned(root, original)
            except Exception:
                cleanup_errors.append("scratch_ownership_or_mount_unknown_preserved")
        result["cleanup"] = {"status": "PASS" if not cleanup_errors else "FAIL",
            "exact_process_identities": [{"pid": item["pid"], "starttime": item["starttime"]} for item in owned],
            "scratch_removed": not root.exists(), "errors": cleanup_errors}
        if cleanup_errors:
            result["status"] = "FAIL"
            result["cleanup"]["preserved_scratch"] = str(root)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--dry-run", action="store_true", help="print the pure bounded adapter plan")
    actions.add_argument("--apply", action="store_true", help="run only inside the approved guarded Linux namespace")
    actions.add_argument("--worker", nargs=3, metavar=("ROOT", "ROLE", "TOKEN"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps(plan(), sort_keys=True))
        return 0
    if args.worker:
        return _worker(Path(args.worker[0]), args.worker[1], args.worker[2])
    result = run_probe()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
