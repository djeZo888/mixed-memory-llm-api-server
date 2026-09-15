#!/usr/bin/env python3
"""Real, bounded systemd/cgroup/flock primitives for the disposable I2P runner.

Imported by the capability harness after its disposable-host gates. This module
does not execute or import the installer and does not install any packages.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time


_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}
_PROPERTIES = (
    "LoadState", "ActiveState", "SubState", "InvocationID", "ControlGroup", "MainPID"
)
_HELPER = r'''#!/usr/bin/python3
import fcntl
import json
import os
from pathlib import Path
import signal
import sys
import time

work = Path(sys.argv[1])
mode = sys.argv[2]
deadline = time.monotonic() + 50

def identity():
    raw = Path('/proc/self/stat').read_text()
    return {'pid': os.getpid(), 'starttime': int(raw[raw.rfind(')') + 2:].split()[19]),
            'cgroup': Path('/proc/self/cgroup').read_text().strip()}

def record(name, value):
    target = work / name
    temp = work / (name + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, sort_keys=True)
    os.replace(temp, target)

launcher = os.fork()
if launcher == 0:
    holder = os.fork()
    if holder == 0:
        fd = os.open(work / 'package.lock', os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        record('holder.json', identity())
        while time.monotonic() < deadline:
            time.sleep(0.05)
        os._exit(0)
    while not (work / 'holder.json').exists():
        if time.monotonic() >= deadline:
            os._exit(71)
        time.sleep(0.05)
    record('launcher.json', identity())
    while not (work / 'release-launcher').exists():
        if time.monotonic() >= deadline:
            os._exit(72)
        time.sleep(0.05)
    if mode == 'sigkill':
        os.kill(os.getpid(), signal.SIGKILL)
    os._exit(0)

_, status = os.waitpid(launcher, 0)
record('launcher-outcome.json', {'exitcode': os.waitstatus_to_exitcode(status)})
while time.monotonic() < deadline:
    time.sleep(0.05)
'''


class ProbeError(RuntimeError):
    """A sanitized, bounded probe failure."""


def _command(argv: list[str], *, timeout: int = 10, allow_missing_unit: bool = False) -> str:
    try:
        result = subprocess.run(
            argv, check=False, capture_output=True, text=True,
            timeout=timeout, env=_ENV,
        )
    except subprocess.TimeoutExpired as exc:
        raise ProbeError("bounded_command_timeout") from exc
    except OSError as exc:
        raise ProbeError("required_command_unavailable") from exc
    if result.returncode and not (
        allow_missing_unit and "LoadState=not-found" in result.stdout.splitlines()
    ):
        # Never expose arbitrary subprocess output, environment, or journal data.
        raise ProbeError("bounded_command_failed")
    return result.stdout


def _show(unit: str) -> dict[str, str]:
    text = _command([
        "/usr/bin/systemctl", "show", "--all", unit,
        "--property=" + ",".join(_PROPERTIES),
    ], allow_missing_unit=True)
    values = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    if set(values) != set(_PROPERTIES):
        raise ProbeError("incomplete_unit_identity")
    return values


def _proc_identity(pid: int) -> dict[str, int | str] | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
        starttime = int(raw[raw.rfind(")") + 2:].split()[19])
        cgroup = Path(f"/proc/{pid}/cgroup").read_text().strip()
    except FileNotFoundError:
        return None
    return {"pid": pid, "starttime": starttime, "cgroup": cgroup}


def _assert_process(expected: dict, cgroup: str) -> None:
    if (
        set(expected) != {"pid", "starttime", "cgroup"}
        or type(expected["pid"]) is not int
        or type(expected["starttime"]) is not int
        or expected["pid"] <= 1
        or expected["starttime"] <= 0
        or expected["cgroup"] != "0::" + cgroup
        or _proc_identity(expected["pid"]) != expected
    ):
        raise ProbeError("process_identity_mismatch")


def _assert_unit(current: dict[str, str], owned: dict) -> None:
    if (
        current["LoadState"] != "loaded"
        or current["InvocationID"] != owned["invocation_id"]
        or current["ControlGroup"] != owned["control_group"]
        or current["MainPID"] != str(owned["main_process"]["pid"])
    ):
        raise ProbeError("unit_identity_mismatch_refusing_stop")
    _assert_process(owned["main_process"], owned["control_group"])


def _locked(path: Path) -> bool:
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def _wait_file(path: Path, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return json.loads(path.read_text())
        time.sleep(0.05)
    raise ProbeError("bounded_evidence_wait_timeout")


def _stop_owned(unit: str, owned: dict, lock: Path) -> dict:
    # The UUID-style InvocationID prevents acting on a same-name replacement;
    # PID starttime and cgroup membership prevent trusting a recycled PID.
    current = _show(unit)
    group = Path("/sys/fs/cgroup" + owned["control_group"])
    if current["LoadState"] == "not-found":
        if group.exists() or _proc_identity(owned["main_process"]["pid"]) == owned["main_process"]:
            raise ProbeError("unit_disappeared_with_live_owned_process")
    else:
        _assert_unit(current, owned)
        _command(["/usr/bin/systemctl", "stop", unit], timeout=10)
    deadline = time.monotonic() + 8
    while group.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    if group.exists():
        raise ProbeError("owned_cgroup_persisted_after_stop")
    if lock.exists() and _locked(lock):
        raise ProbeError("owned_lock_remained_after_stop")
    return {"status": "PASS", "cgroup_removed": True, "lock_reacquirable": lock.exists()}


def _case(workdir: Path, run_id: str, mode: str) -> dict:
    unit = f"{run_id}-package-{mode}.service"
    expected_cgroup = "/system.slice/" + unit
    case_dir = workdir / ("package-" + mode)
    case_dir.mkdir(mode=0o700)
    helper = case_dir / "fake_package.py"
    fd = os.open(helper, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(_HELPER)
    lock = case_dir / "package.lock"
    result: dict = {"case": mode, "unit": unit, "status": "FAIL"}
    owned = None
    started = False
    try:
        if _show(unit)["LoadState"] != "not-found":
            raise ProbeError("unit_name_already_exists")
        started = True  # A timed-out launch can still have created the bounded unit.
        _command([
            "/usr/bin/systemd-run", "--quiet", "--collect", "--unit=" + unit,
            "--service-type=exec", "--property=RuntimeMaxSec=60s",
            "--property=TimeoutStopSec=5s", "--property=KillMode=control-group",
            "--property=UMask=0077", "--property=StandardOutput=null",
            "--property=StandardError=null", "--property=NoNewPrivileges=yes",
            "--property=PrivateDevices=yes", "--property=PrivateNetwork=yes",
            "--property=TasksMax=8", "--property=MemoryMax=64M",
            "--property=ProtectSystem=strict",
            "--property=ReadWritePaths=" + str(case_dir),
            "/usr/bin/env", "-i", "PATH=/usr/sbin:/usr/bin:/sbin:/bin",
            "/usr/bin/python3", str(helper), str(case_dir), mode,
        ])
        state = _show(unit)
        if (
            state["LoadState"] != "loaded"
            or state["ActiveState"] != "active"
            or not re.fullmatch(r"[0-9a-f]{32}", state["InvocationID"])
            or state["ControlGroup"] != expected_cgroup
            or not state["MainPID"].isdigit()
            or int(state["MainPID"]) <= 1
        ):
            raise ProbeError("initial_unit_identity_unverified")
        main = _proc_identity(int(state["MainPID"]))
        if main is None:
            raise ProbeError("main_process_disappeared")
        _assert_process(main, expected_cgroup)
        owned = {
            "invocation_id": state["InvocationID"],
            "control_group": expected_cgroup, "main_process": main,
        }
        # Preserve only non-secret ownership evidence in private job temporary storage.
        ownership = case_dir / "ownership.json"
        fd = os.open(ownership, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(owned, stream, sort_keys=True)
        holder = _wait_file(case_dir / "holder.json")
        launcher = _wait_file(case_dir / "launcher.json")
        _assert_process(holder, expected_cgroup)
        _assert_process(launcher, expected_cgroup)
        if len({main["pid"], launcher["pid"], holder["pid"]}) != 3:
            raise ProbeError("process_tree_not_distinct")
        if not _locked(lock):
            raise ProbeError("descendant_did_not_hold_lock")
        fd = os.open(case_dir / "release-launcher", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        outcome = _wait_file(case_dir / "launcher-outcome.json")
        if outcome != {"exitcode": -9 if mode == "sigkill" else 0}:
            raise ProbeError("unexpected_launcher_exit")
        if _proc_identity(launcher["pid"]) == launcher:
            raise ProbeError("launcher_not_reaped")
        _assert_unit(_show(unit), owned)
        _assert_process(holder, expected_cgroup)
        if not _locked(lock):
            raise ProbeError("lock_did_not_survive_launcher_exit")
        result.update({
            "status": "PASS", "invocation_id": owned["invocation_id"],
            "control_group": expected_cgroup,
            "main_process": main, "launcher_process": launcher,
            "holder_process": holder, "launcher_exitcode": outcome["exitcode"],
            "launcher_reaped": True, "descendant_survived": True,
            "same_service_cgroup": True, "lock_held_after_launcher_exit": True,
        })
    except (ProbeError, OSError, ValueError, KeyError, TypeError) as exc:
        result["failure"] = str(exc) if isinstance(exc, ProbeError) else "probe_evidence_or_io_error"
    finally:
        if owned is not None:
            try:
                result["cleanup"] = _stop_owned(unit, owned, lock)
            except (ProbeError, OSError, ValueError, KeyError, TypeError) as exc:
                result["status"] = "FAIL"
                result["cleanup"] = {
                    "status": "FAIL",
                    "failure": str(exc) if isinstance(exc, ProbeError) else "cleanup_evidence_or_io_error",
                    "automatic_runtime_bound_seconds": 60,
                }
        else:
            result["cleanup"] = {
                "status": "NOT_OWNED" if not started else "IDENTITY_UNVERIFIED",
                "stop_attempted": False,
                "automatic_runtime_bound_seconds": 60 if started else None,
            }
    return result


def run(workdir: Path, run_id: str) -> dict:
    """Run two harmless transient-service cases in a prevalidated disposable VM.

    The caller must first verify explicit disposable-workflow opt-in, Ubuntu
    24.04 amd64, systemd PID 1, cgroup v2 and root. The workdir must be a fresh,
    root-owned private directory. The unit helper receives an empty environment
    except PATH, never repository credentials or workflow secrets.
    """
    if not re.fullmatch(r"i2p-[0-9a-f]{8,32}", run_id):
        raise ProbeError("invalid_run_id")
    if os.geteuid() != 0:
        raise ProbeError("root_required_inside_disposable_runner")
    if not workdir.is_absolute() or workdir.is_symlink():
        raise ProbeError("private_absolute_workdir_required")
    info = workdir.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        raise ProbeError("private_root_owned_workdir_required")
    if workdir.resolve() != workdir:
        raise ProbeError("symlinked_workdir_refused")
    cases = []
    for mode in ("exit", "sigkill"):
        result = _case(workdir, run_id, mode)
        cases.append(result)
        if result["status"] != "PASS":
            break
    return {
        "status": "PASS" if len(cases) == 2 and all(case["status"] == "PASS" for case in cases) else "FAIL",
        "proof_scope": "real_systemd_cgroup_flock_primitives_only",
        "runtime_bound_seconds_per_unit": 60,
        "cases": cases,
        "installer_integration": "NOT_TESTED",
        "real_package_manager": "NOT_TESTED",
        "limitation": "A harmless supervisor remains MainPID; a child launcher exits or self-SIGKILLs while its descendant holds flock.",
    }
