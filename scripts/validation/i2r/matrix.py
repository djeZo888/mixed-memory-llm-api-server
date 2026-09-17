#!/usr/bin/env python3
"""Actual systemd + synthetic-package acceptance on the guarded disposable VM.

The outer guardian MUST keep both approved fake executable mounts present until
``cleanup_owned`` succeeds. This module is not a standalone guest admission
guard. It uses production classes unchanged. ``sys.settrace`` observes shipped
Python return boundaries and pauses selected installer children for crash
injection; it never replaces an adapter, lease, command, or production method.
Private fixture data/policy paths are intentionally NOT storage acceptance.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time


SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from common.lifecycle_lease import (  # noqa: E402
    LeaseBusy, LeaseError, acquire_lease, _export_package_watcher_fd,
)
from install.core import InstallError, Runner, SystemdPackageScope  # noqa: E402
from install.prerequisites import (  # noqa: E402
    POLICY_SENTINEL, PrerequisiteError, Prerequisites, assert_package_admission,
)
from validation.i2r.guardian import assert_active_bindings, CONTEXT_KEYS  # noqa: E402


CLEAN_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
MAX_CASE_SECONDS = 45
ORIGINAL = b"\x00I2R opaque original policy\xff\n"
ORIGINAL_MODE = 0o4750


def child_env():
    """Pass only nonsecret hosted identity metadata through the sudo boundary."""
    return {**CLEAN_ENV, **{key: os.environ.get(key, "") for key in CONTEXT_KEYS}}


def safe_code(exc):
    value = getattr(exc, "code", None)
    return value if isinstance(value, str) and re.fullmatch(r"[a-z0-9_]{1,100}", value) else "i2r_assertion_failed" if isinstance(exc, AssertionError) else "i2r_unexpected_error"


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name("." + path.name + "." + str(os.getpid()))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def read_json(path, default=None):
    try:
        if Path(path).stat().st_size > 1024 * 1024:
            raise InstallError("i2r_evidence_too_large")
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def process_record(pid, kind, parent_pid=None):
    """Read kernel start time and ancestry; names never establish ownership."""
    raw = Path(f"/proc/{pid}/stat").read_text()
    fields = raw[raw.rfind(")") + 2:].split()
    return {"kind": kind, "pid": int(pid), "start_ticks": int(fields[19]),
            "parent_pid": int(fields[1]) if parent_pid is None else parent_pid,
            "observed_parent_pid": int(fields[1])}


def alive(record):
    try:
        actual = process_record(record["pid"], record["kind"])
        raw = Path(f"/proc/{record['pid']}/stat").read_text()
        return actual["start_ticks"] == record["start_ticks"] and raw[raw.rfind(")") + 2:].split()[0] != "Z"
    except FileNotFoundError:
        return False


def signal_owned(record, sig):
    """A pinned pidfd plus recorded kernel start time prevents PID reuse kills."""
    if not alive(record):
        return False
    fd = os.pidfd_open(record["pid"], 0)
    try:
        if not alive(record):
            return False
        signal.pidfd_send_signal(fd, sig)
        return True
    finally:
        os.close(fd)


def fixture_guard(directory):
    directory = Path(directory)
    if directory.resolve() != directory or not directory.is_relative_to(Path("/run")):
        raise InstallError("i2r_fixture_path_invalid")
    for path in (directory, *directory.parents):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise InstallError("i2r_fixture_path_unprotected")
    return {"fixture_only": True}


def package_objects(case, runner):
    data = case / "data"
    return Prerequisites({"data_dir": str(data)}, runner,
                         lambda: fixture_guard(data), policy_path=case / "policy-rc.d")


def append_event(case, value):
    fd = os.open(case / "trace.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, (json.dumps(value, sort_keys=True) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)


def trace_events(case):
    try:
        content = (case / "trace.jsonl").read_bytes()
    except FileNotFoundError:
        return []
    if len(content) > 256 * 1024:
        raise InstallError("i2r_trace_too_large")
    return [json.loads(row) for row in content.splitlines() if row.endswith(b"}")]


def tracing_fixture(case, runner, options):
    initial_pid = os.getpid()
    seen = set()
    marker = case / "data/services/installer/package-service-policy.json"
    gate = marker.with_name("package-execution-gate.json")
    production = {str(SCRIPTS / "install/core.py"), str(SCRIPTS / "install/prerequisites.py")}

    def trace(frame, event, arg):
        if os.getpid() != initial_pid:
            sys.settrace(None)
            return None
        if event != "return" or frame.f_code.co_filename not in production:
            return trace
        name = frame.f_code.co_name
        stage = None
        identity = None
        saved = read_json(marker)
        if name == "prepare" and isinstance(arg, dict) and "invocation_id" in arg:
            stage, identity = "prepared", arg
        elif name == "_write_json" and saved:
            stage, identity = saved["phase"], saved["transaction"]
        elif name == "hold_package_lease" and saved:
            stage, identity = "ready", saved["transaction"]
        elif name == "execute" and saved and gate.exists():
            stage, identity = "gate", saved["transaction"]
        elif name == "atomic_bytes" and saved and saved.get("phase") == "owned":
            policy = case / "policy-rc.d"
            if policy.exists() and policy.read_bytes() == ORIGINAL:
                stage, identity = "retirement", saved["transaction"]
        if stage is None:
            return trace
        key = (stage, identity.get("token"))
        if key in seen:
            return trace
        seen.add(key)
        watchers = []
        for pid in runner._package_watchers:
            try:
                watchers.append(process_record(pid, "watcher", initial_pid))
            except FileNotFoundError:
                pass
        policy = case / "policy-rc.d"
        value = {"stage": stage, "identity": identity, "gate_exists": gate.exists(),
                 "marker_phase": saved.get("phase") if saved else None,
                 "policy_inhibited": policy.exists() and policy.read_bytes() == POLICY_SENTINEL,
                 "watchers": watchers}
        append_event(case, value)
        if options.get("pause") == stage:
            write_json(case / "paused.json", {"stage": stage, "identity": identity})
            deadline = time.monotonic() + 25
            while not (case / "resume").exists():
                if time.monotonic() >= deadline:
                    raise InstallError("i2r_checkpoint_pause_deadline")
                time.sleep(0.025)
        return trace
    return trace


def child(case):
    """Only started by guarded parent with fully scrubbed environment."""
    fixture_guard(case)
    assert_active_bindings(case.parent)
    deadline = time.monotonic() + 10
    while not (case / "parent-ready.json").exists():
        if time.monotonic() >= deadline:
            return 2
        time.sleep(.025)
    registration = read_json(case / "parent-ready.json")
    actual = process_record(os.getpid(), "installer")
    if (registration["pid"], registration["start_ticks"], registration["parent_pid"]) != (actual["pid"], actual["start_ticks"], actual["observed_parent_pid"]):
        raise InstallError("i2r_child_registration_mismatch")
    options = read_json(case / "options.json")
    result = {"status": "FAIL", "code": "i2r_child_did_not_complete"}
    try:
        with acquire_lease(blocking=False) as lease:
            exported = _export_package_watcher_fd(lease)
            try:
                runner = Runner(writable=True, package_lease_fd=exported)
                packages = package_objects(case, runner)
                sys.settrace(tracing_fixture(case, runner, options))
                for index in range(options.get("transactions", 1)):
                    os.fstat(exported)
                    lease.validate()
                    pin = {"sleep": "wait"}.get(options["mode"], options["mode"])
                    packages.package_transaction(
                        ["apt-get", "--no-download", "--yes", "--no-install-recommends",
                         "--no-remove", "install", "i2r-" + pin + "=1"],
                        timeout=options.get("timeout", 9), env={"TMPDIR": str(case / "fake")})
                    append_event(case, {"stage": "transaction_complete", "index": index,
                                        "export_valid": bool(os.fstat(exported).st_ino)})
                result = {"status": "PASS", "code": "i2r_child_complete"}
            finally:
                sys.settrace(None)
                os.close(exported)  # closes before outer canonical lease; never LOCK_UN
    except BaseException as exc:
        result = {"status": "FAIL", "code": "i2r_keyboard_interrupt" if isinstance(exc, KeyboardInterrupt) else safe_code(exc)}
    write_json(case / "child-result.json", result)
    return 0 if result["status"] == "PASS" else 1


def contender(workdir):
    """Independent process acquisition, never inherited fixture flock."""
    assert_active_bindings(workdir)
    try:
        with acquire_lease(blocking=False):
            return 0
    except LeaseBusy:
        return 3
    except LeaseError:
        return 4


def compete(workdir):
    assert_active_bindings(workdir)
    result = subprocess.run([sys.executable, "-I", str(Path(__file__).resolve()), "--contender", str(workdir)],
                            env=child_env(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=5, close_fds=True)
    if result.returncode not in {0, 3}:
        raise InstallError("i2r_contender_failed")
    return "acquired" if result.returncode == 0 else "busy"


def observe(identity):
    scope = SystemdPackageScope()
    values = scope._show(identity)
    fd = scope._cgroup(identity)
    inventory = []
    try:
        populated = scope._populated(fd) if fd is not None else False
        if fd is not None:
            base = Path("/sys/fs/cgroup") / identity["cgroup"].lstrip("/")
            # Read-only recursive inventory; cgroup.events supplies kernel-wide
            # descendant population and exact cgroup inode supplies ownership.
            for root, dirs, files in os.walk(base, followlinks=False):
                if "cgroup.procs" not in files:
                    continue
                for value in (Path(root) / "cgroup.procs").read_text().split():
                    try:
                        record = process_record(int(value), "scope_descendant")
                        record["cgroup"] = "/" + str(Path(root).relative_to("/sys/fs/cgroup"))
                        inventory.append(record)
                    except FileNotFoundError:
                        pass
        return {"identity": identity, "properties": values, "cgroup_present": fd is not None,
                "recursive_populated": populated, "descendants": inventory}
    finally:
        if fd is not None:
            os.close(fd)


def inspect_stable(identity, limit=3):
    deadline = time.monotonic() + limit
    while True:
        try:
            return SystemdPackageScope().inspect(identity)
        except InstallError as exc:
            if exc.code != "package_scope_state_changing_retry" or time.monotonic() >= deadline:
                raise
            time.sleep(.05)


def allocated_observation(identity):
    """Read-only missing-unit evidence; never mints prepared ownership."""
    SystemdPackageScope()._validate(identity, prepared=False)
    process = subprocess.run(["/usr/bin/systemctl", "show", "--no-pager", "--all",
                              "--property=Id,LoadState,InvocationID", "--", identity["unit"]],
                             env=CLEAN_ENV, text=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
    if len(process.stdout) > 4096:
        raise InstallError("i2r_allocated_observation_invalid")
    rows = [line.split("=", 1) for line in process.stdout.splitlines()]
    values = dict(rows)
    if (len(rows) != 3 or set(values) != {"Id", "LoadState", "InvocationID"}
            or values["Id"] != identity["unit"]
            or not re.fullmatch(r"[a-z-]{1,30}", values["LoadState"])
            or not re.fullmatch(r"(?:[0-9a-f]{32})?", values["InvocationID"])):
        raise InstallError("i2r_allocated_observation_invalid")
    return values


class Harness:
    def __init__(self, workdir):
        self.workdir = workdir
        self.journal = {"schema_version": 1, "units": [], "allocated_units": [], "processes": [], "cases": []}
        self.cases = []
        self.save()

    def save(self):
        write_json(self.workdir / "ownership.json", self.journal)

    def collect(self, case, evidence):
        events = trace_events(case)
        evidence["trace"] = events
        fake_events = case / "fake/events.jsonl"
        if fake_events.exists():
            raw = fake_events.read_bytes()
            if len(raw) > 128 * 1024:
                raise InstallError("i2r_fake_events_too_large")
            values = [json.loads(row) for row in raw.splitlines() if row.endswith(b"}")]
            for value in values:
                if (set(value) != {"stage", "pid", "start_ticks", "ppid", "cgroup"}
                        or value["stage"] not in {"main_started", "main_exit", "descendant_started", "descendant_exit"}
                        or not re.fullmatch(r"0::/system.slice/local-ai-package-[0-9a-f]{32}\.service", value["cgroup"])
                        or any(type(value[key]) is not int or value[key] <= 0 for key in ("pid", "start_ticks", "ppid"))):
                    raise InstallError("i2r_fake_event_invalid")
            evidence["fake_events"] = values
        for event in events:
            identity = event.get("identity", {})
            if identity.get("token") and identity["token"] not in {i["token"] for i in self.journal["allocated_units"]}:
                self.journal["allocated_units"].append({key: identity[key] for key in ("kind", "token", "unit", "boot_id")})
            if "invocation_id" in identity and identity not in self.journal["units"]:
                self.journal["units"].append(identity)
            for process in event.get("watchers", []):
                if process not in self.journal["processes"]:
                    self.journal["processes"].append(process)
        self.save()
        units = {event["identity"]["token"]: event["identity"] for event in events
                 if "invocation_id" in event.get("identity", {})}
        for identity in units.values():
            try:
                observation = observe(identity)
            except InstallError as exc:
                observation = {"identity": identity, "inspection_code": safe_code(exc)}
            samples = evidence.setdefault("observations", [])
            # Bounded but retain changes in population/MainPID and identities.
            signature = (identity["token"], observation.get("recursive_populated"),
                         observation.get("properties", {}).get("MainPID"), observation.get("inspection_code"))
            previous = {(s["identity"]["token"], s.get("recursive_populated"),
                         s.get("properties", {}).get("MainPID"), s.get("inspection_code")) for s in samples}
            if signature not in previous and len(samples) < 24:
                samples.append(observation)
            policy = case / "policy-rc.d"
            if observation.get("recursive_populated") and (not policy.exists() or policy.read_bytes() != POLICY_SENTINEL):
                # Exclude a sampling race where quiescence/restoration happened
                # after the prior population observation.
                try:
                    if inspect_stable(identity)["state"] == "live":
                        evidence["policy_restored_while_populated"] = True
                except InstallError:
                    pass
        return events

    def wait(self, case, evidence, predicate, timeout=MAX_CASE_SECONDS):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            events = self.collect(case, evidence)
            if predicate(events):
                return events
            time.sleep(.06)
        raise InstallError("i2r_case_deadline")

    def start(self, name, **options):
        case = self.workdir / name
        case.mkdir(mode=0o700)
        (case / "data").mkdir(mode=0o700)
        (case / "fake").mkdir(mode=0o700)
        if not options.get("absent"):
            fd = os.open(case / "policy-rc.d", os.O_WRONLY | os.O_CREAT | os.O_EXCL, ORIGINAL_MODE)
            with os.fdopen(fd, "wb") as stream:
                stream.write(ORIGINAL)
            os.chmod(case / "policy-rc.d", ORIGINAL_MODE)
        write_json(case / "options.json", options)
        write_json(case / "fake/control.json", {"mode": options["mode"], "duration": options.get("duration", .6)})
        self.journal["cases"].append(case.name)
        self.save()
        process = subprocess.Popen([sys.executable, "-I", str(Path(__file__).resolve()), "--child", str(case)],
                                   env=child_env(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, close_fds=True)
        try:
            record = process_record(process.pid, "installer", os.getpid())
            self.journal["processes"].append(record)
            self.save()
            write_json(case / "parent-ready.json", record)
        except BaseException:
            # The direct, unreaped Popen child cannot have a reused PID; it has
            # not received permission to acquire a lease or prepare a service.
            process.kill()
            process.wait(timeout=3)
            raise
        evidence = {"case": name, "status": "FAIL", "fixture": "actual_systemd_synthetic_package",
                    "child": record, "storage_acceptance": "NOT_TESTED", "observations": []}
        self.cases.append(evidence)
        return case, process, record, evidence

    def finish_child(self, case, process, evidence):
        self.wait(case, evidence, lambda events: process.poll() is not None)
        process.wait(timeout=1)
        evidence["child_result"] = read_json(case / "child-result.json", {"code": "i2r_child_sigkill"})
        evidence["child_returncode"] = process.returncode
        evidence["policy_restored_while_populated"] = evidence.get("policy_restored_while_populated", False)

    def reacquire(self, case, evidence):
        outcomes = []
        def available(_):
            outcome = compete(self.workdir)
            if not outcomes or outcomes[-1] != outcome:
                outcomes.append(outcome)
            return outcome == "acquired"
        self.wait(case, evidence, available, timeout=20)
        evidence["final_contender"] = outcomes

    def recovery(self, case, *, expected=None):
        with acquire_lease(blocking=False) as lease:
            exported = _export_package_watcher_fd(lease)
            try:
                runner = Runner(writable=True, package_lease_fd=exported)
                packages = package_objects(case, runner)
                try:
                    result = packages.recover_policy()
                except (InstallError, PrerequisiteError) as exc:
                    if expected is None:
                        raise
                    assert safe_code(exc) == expected
                    return {"code": safe_code(exc)}
                if expected is not None:
                    raise AssertionError("expected recovery refusal")
                assert_package_admission(packages.data, packages.guard, policy_path=packages.policy_path)
                return result
            finally:
                os.close(exported)

    def admission(self, case):
        with acquire_lease(blocking=False):
            packages = package_objects(case, Runner())
            try:
                assert_package_admission(packages.data, packages.guard, policy_path=packages.policy_path)
            except PrerequisiteError as exc:
                assert exc.code == "package_transaction_recovery_required"
                return exc.code
        raise AssertionError("pending marker admitted")

    def restored(self, case, absent=False):
        policy = case / "policy-rc.d"
        if absent:
            assert not policy.exists()
        else:
            assert policy.read_bytes() == ORIGINAL
            assert stat.S_IMODE(policy.stat().st_mode) == ORIGINAL_MODE
        assert not (case / "data/services/installer/package-service-policy.json").exists()
        assert not (case / "data/services/installer/package-execution-gate.json").exists()


def _last_identity(evidence):
    return next(event["identity"] for event in reversed(evidence["trace"]) if "invocation_id" in event.get("identity", {}))


def _resume(case):
    (case / "resume").touch(mode=0o600)


def completion(h, name, *, absent=False, fail=False, transactions=1):
    case, process, record, evidence = h.start(name, mode="fail" if fail else "success", absent=absent, transactions=transactions)
    h.finish_child(case, process, evidence)
    assert evidence["child_result"]["code"] == ("package_command_failed_or_timeout" if fail else "i2r_child_complete")
    h.reacquire(case, evidence)
    h.restored(case, absent)
    assert not evidence["policy_restored_while_populated"]
    identities = {e["identity"]["token"] for e in evidence["trace"] if e["stage"] == "ready"}
    assert len(identities) == transactions
    for token in identities:
        stages = [e for e in evidence["trace"] if e.get("identity", {}).get("token") == token]
        for stage in ("preparing", "owned", "ready"):
            assert any(e["stage"] == stage and not e["gate_exists"] for e in stages)
        assert any(e["stage"] == "ready" and e["watchers"] for e in stages)
        assert any(e["stage"] == "gate" and e["gate_exists"] and e["marker_phase"] == "owned" for e in stages)
    terminal = observe(_last_identity(evidence))
    evidence["terminal"] = terminal
    assert not terminal["recursive_populated"]
    assert inspect_stable(_last_identity(evidence))["successful"] is not fail
    evidence["policy_original_sha256"] = hashlib.sha256(ORIGINAL).hexdigest() if not absent else None
    evidence["policy_original_mode"] = ORIGINAL_MODE if not absent else None
    evidence["status"] = "PASS"


def descendants(h, *, interrupt=False, timeout=False):
    name = "ctrl_c_exact_scope_abort" if interrupt else "manager_timeout" if timeout else "main_exit_live_descendant"
    case, process, record, evidence = h.start(name, mode="sleep" if timeout else "descendant", duration=12 if timeout else 4, timeout=2 if timeout else 9)
    h.wait(case, evidence, lambda events: any(e["stage"] == "gate" for e in events))
    identity = _last_identity(evidence)
    # Wait for fake executable's own event so the pre-exec worker is excluded.
    h.wait(case, evidence, lambda events: (case / "fake/events.jsonl").exists())
    time.sleep(.2)
    evidence["live"] = observe(identity)
    evidence["contender_while_live"] = compete(h.workdir)
    assert evidence["live"]["recursive_populated"] and evidence["contender_while_live"] == "busy"
    if not timeout:
        h.wait(case, evidence, lambda events: observe(identity)["properties"]["MainPID"] == "0", timeout=3)
        evidence["main_exited_descendants_live"] = observe(identity)
        assert evidence["main_exited_descendants_live"]["recursive_populated"]
    if interrupt:
        signal_owned(record, signal.SIGINT)
    h.finish_child(case, process, evidence)
    expected = "i2r_keyboard_interrupt" if interrupt else "package_command_failed_or_timeout" if timeout else "i2r_child_complete"
    assert evidence["child_result"]["code"] == expected
    h.reacquire(case, evidence)
    h.restored(case)
    assert not evidence["policy_restored_while_populated"]
    evidence["terminal"] = observe(identity)
    assert not evidence["terminal"]["recursive_populated"]
    evidence["status"] = "PASS"


def crash(h, checkpoint, *, kill_watcher=False):
    name = "watcher_then_installer_killed" if kill_watcher else "sigkill_" + checkpoint
    case, process, record, evidence = h.start(name, mode="sleep", duration=12, timeout=4, pause=checkpoint)
    h.wait(case, evidence, lambda events: read_json(case / "paused.json") is not None)
    paused = read_json(case / "paused.json")
    assert paused["stage"] == checkpoint
    evidence["paused"] = paused
    if kill_watcher:
        watchers = next(e["watchers"] for e in reversed(evidence["trace"]) if e["stage"] == "ready")
        assert len(watchers) == 1 and watchers[0]["observed_parent_pid"] == process.pid
        signal_owned(watchers[0], signal.SIGKILL)
        evidence["killed_watcher"] = watchers[0]
    signal_owned(record, signal.SIGKILL)
    process.wait(timeout=3)
    h.collect(case, evidence)
    evidence["child_returncode"] = process.returncode
    evidence["contender_after_installer_death"] = compete(h.workdir)
    has_watcher = checkpoint in {"ready", "gate", "retirement"} and not kill_watcher
    if has_watcher and checkpoint != "retirement":
        assert evidence["contender_after_installer_death"] == "busy"
    else:
        assert evidence["contender_after_installer_death"] == "acquired"
        evidence["admission_after_lock_available"] = h.admission(case)
    if checkpoint != "preparing":
        identity = _last_identity(evidence)
        evidence["after_crash"] = observe(identity)
        if kill_watcher:
            assert evidence["after_crash"]["recursive_populated"]
        h.wait(case, evidence, lambda events: inspect_stable(identity)["state"] == "quiescent", timeout=20)
        h.reacquire(case, evidence)
        evidence["admission_before_recovery"] = h.admission(case)
        evidence["recovery"] = h.recovery(case)
        h.restored(case)
        evidence["terminal"] = observe(identity)
        evidence["terminal_status"] = inspect_stable(identity)
        if checkpoint in {"owned", "ready"}:
            assert evidence["terminal_status"]["successful"] is False
            assert not (case / "fake/events.jsonl").exists()
            evidence["fake_package_never_executed"] = True
    else:
        evidence["recovery"] = h.recovery(case, expected="package_ownership_incomplete")
        assert not (case / "data/services/installer/package-execution-gate.json").exists()
        evidence["explicit_reconciliation"] = "NOT_TESTED_preparing_marker_requires_operator"
    assert not evidence.get("policy_restored_while_populated")
    evidence["status"] = "PASS"


def unknown_identity(h):
    case, process, record, evidence = h.start("unknown_identity", mode="sleep", duration=12, timeout=5, pause="gate")
    h.wait(case, evidence, lambda events: read_json(case / "paused.json") is not None)
    identity = _last_identity(evidence)
    scope = SystemdPackageScope()
    checks = []
    for field, value, expected in (("invocation_id", "0" * 32, "package_scope_identity_missing_or_stale"),
                                   ("cgroup_inode", identity["cgroup_inode"] + 1, "package_cgroup_identity_changed")):
        changed = {**identity, field: value}
        for operation in ("inspect", "abort"):
            try:
                getattr(scope, operation)(changed)
            except InstallError as exc:
                assert exc.code == expected
                checks.append({"field": field, "operation": operation, "code": exc.code})
            else:
                raise AssertionError("changed identity accepted")
        assert inspect_stable(identity)["state"] == "live"
    missing = {**scope.new_identity(), "invocation_id": "0" * 32, "cgroup_inode": identity["cgroup_inode"]}
    missing["cgroup"] = "/system.slice/" + missing["unit"]
    try:
        scope.inspect(missing)
    except InstallError as exc:
        assert exc.code == "package_scope_identity_missing_or_stale"
        checks.append({"field": "missing_unit", "operation": "inspect", "code": exc.code})
    else:
        raise AssertionError("missing unit accepted")
    # A real persisted marker with deliberately mismatched expected identity is
    # an explicit fixture corruption. The original retained service is unchanged.
    marker = case / "data/services/installer/package-service-policy.json"
    saved = read_json(marker)
    write_json(marker, {**saved, "transaction": {**identity, "invocation_id": "0" * 32}})
    signal_owned(record, signal.SIGKILL)
    process.wait(timeout=3)
    h.wait(case, evidence, lambda events: inspect_stable(identity)["state"] == "quiescent", timeout=20)
    h.reacquire(case, evidence)
    evidence["corrupt_marker_recovery"] = h.recovery(case, expected="package_ownership_unknown")
    assert (case / "policy-rc.d").read_bytes() == POLICY_SENTINEL and marker.exists()
    write_json(marker, saved)
    evidence["restored_observation_recovery"] = h.recovery(case)
    h.restored(case)
    evidence["checks"] = checks
    evidence["manager_unavailable"] = "NOT_TESTED_no_manager_namespace_mutation_authorized"
    evidence["actual_cgroup_inode_replacement"] = "NOT_TESTED_expected_identity_mismatch_only"
    evidence["status"] = "PASS"


def audit_policy(h, *, external=False):
    name = "external_policy_change" if external else "dirty_audit"
    write_json(h.workdir / "audit-state.json", {"dirty": True})
    case, process, record, evidence = h.start(name, mode="success")
    h.finish_child(case, process, evidence)
    assert evidence["child_result"]["code"] == "package_database_repair_required"
    h.reacquire(case, evidence)
    assert (case / "policy-rc.d").read_bytes() == POLICY_SENTINEL
    evidence["admission_dirty"] = h.admission(case)
    evidence["dirty_recovery"] = h.recovery(case, expected="package_database_repair_required")
    write_json(h.workdir / "audit-state.json", {"dirty": False})
    if external:
        (case / "policy-rc.d").write_bytes(b"I2R externally changed policy\n")
        evidence["external_recovery"] = h.recovery(case, expected="existing_policy_changed")
        assert (case / "policy-rc.d").read_bytes() == b"I2R externally changed policy\n"
        # Explicit test reconciliation restores the known fixture inhibitor only.
        (case / "policy-rc.d").write_bytes(POLICY_SENTINEL)
    evidence["recovery"] = h.recovery(case)
    h.restored(case)
    evidence["status"] = "PASS"


def retirement(h):
    case, process, record, evidence = h.start("retirement_crash_retry", mode="success", pause="retirement")
    h.wait(case, evidence, lambda events: read_json(case / "paused.json") is not None)
    assert read_json(case / "paused.json")["stage"] == "retirement"
    assert (case / "policy-rc.d").read_bytes() == ORIGINAL
    assert not observe(_last_identity(evidence))["recursive_populated"]
    signal_owned(record, signal.SIGKILL)
    process.wait(timeout=3)
    h.reacquire(case, evidence)
    evidence["admission"] = h.admission(case)
    evidence["recovery"] = h.recovery(case)
    h.restored(case)
    evidence["status"] = "PASS"


def cleanup_owned(workdir):
    """Guardian finalizer: retain bind mounts unless no owned execution remains.

    Exact service identity is verified before pinned cgroup kill. Watcher/child
    signals use pidfds plus recorded kernel start ticks and original ancestry.
    Missing/reused service identity remains a cleanup failure, never a guess.
    """
    workdir = Path(workdir)
    journal = read_json(workdir / "ownership.json")
    result = {"status": "PASS", "units": [], "processes": [],
              "terminal_units": "retained_intentionally_until_disposable_vm_teardown"}
    if journal is None:
        # Preparation runs before Harness creation and creates no package units.
        if any(p.is_file() for p in workdir.glob("*/options.json")):
            return {"status": "FAIL", "code": "i2r_ownership_journal_missing"}
        return result
    # Stop producers FIRST: no child may create a later transaction while its
    # previously recorded cgroup is being cleaned up.
    for process in journal["processes"]:
        if process["kind"] != "installer":
            continue
        try:
            if process.get("observed_parent_pid") != process.get("parent_pid"):
                raise InstallError("i2r_process_ancestry_unverified")
            signal_owned(process, signal.SIGKILL)
            deadline = time.monotonic() + 3
            while alive(process) and time.monotonic() < deadline:
                time.sleep(.025)
            if alive(process):
                raise InstallError("i2r_installer_cleanup_incomplete")
        except BaseException as exc:
            result["status"] = "FAIL"
            result["processes"].append({**process, "status": "FAIL", "code": safe_code(exc)})
    if result["status"] != "PASS":
        write_json(workdir / "cleanup.json", result)
        return result  # No quiescent inventory possible while producers survive.
    # Absorb observations emitted after the parent's last poll, including the
    # exact prepared identity before owned-marker persistence.
    for name in journal.get("cases", []):
        if not re.fullmatch(r"[a-z0-9_]{1,80}", name):
            return {"status": "FAIL", "code": "i2r_case_journal_invalid"}
        case = workdir / name
        registration = read_json(case / "parent-ready.json")
        if registration and registration not in journal["processes"]:
            return {"status": "FAIL", "code": "i2r_unjournaled_installer"}
        for event in trace_events(case):
            identity = event.get("identity", {})
            if identity.get("token") and identity["token"] not in {i["token"] for i in journal.setdefault("allocated_units", [])}:
                journal["allocated_units"].append({key: identity[key] for key in ("kind", "token", "unit", "boot_id")})
            if "invocation_id" in identity and identity not in journal["units"]:
                journal["units"].append(identity)
            for process in event.get("watchers", []):
                if process not in journal["processes"]:
                    journal["processes"].append(process)
        marker = read_json(case / "data/services/installer/package-service-policy.json")
        if marker:
            identity = marker["transaction"]
            if identity.get("token") not in {i["token"] for i in journal.setdefault("allocated_units", [])}:
                journal["allocated_units"].append({key: identity[key] for key in ("kind", "token", "unit", "boot_id")})
            # An owned marker alone supplies exact immutable source identity.
            if (marker.get("phase") == "owned" and "invocation_id" in identity
                    and identity["token"] not in {i["token"] for i in journal["units"]}):
                journal["units"].append(identity)
    write_json(workdir / "ownership.json", journal)
    scope = SystemdPackageScope()
    prepared = {i["token"] for i in journal["units"]}
    for identity in journal.get("allocated_units", []):
        if identity["token"] in prepared:
            continue
        item = {"identity": identity}
        try:
            values = allocated_observation(identity)
            item["observed_properties"] = values
            if values != {"Id": identity["unit"], "LoadState": "not-found", "InvocationID": ""}:
                raise InstallError("i2r_prepared_identity_unrecorded")
            item.update(status="PASS", state="never_started")
        except BaseException as exc:
            result["status"] = "FAIL"
            item.update(status="FAIL", code=safe_code(exc))
        result["units"].append(item)
    for identity in journal["units"]:
        item = {"identity": identity}
        try:
            status = inspect_stable(identity)
            if status["state"] == "live":
                scope.abort(identity)
            item["final"] = observe(identity)
            assert not item["final"]["recursive_populated"]
            item["status"] = "PASS"
        except BaseException as exc:
            item.update(status="FAIL", code=safe_code(exc))
            result["status"] = "FAIL"
        result["units"].append(item)
    # Always stop exact installer children before watcher cleanup. No process is
    # owned merely because its PID/name resembles one of the fixtures.
    for process in sorted(journal["processes"], key=lambda p: p["kind"] == "watcher"):
        item = dict(process)
        try:
            if process.get("observed_parent_pid") != process.get("parent_pid"):
                raise InstallError("i2r_process_ancestry_unverified")
            if alive(process):
                signal_owned(process, signal.SIGKILL)
                deadline = time.monotonic() + 3
                while alive(process) and time.monotonic() < deadline:
                    time.sleep(.025)
            item["alive_after"] = alive(process)
            if item["alive_after"]:
                raise InstallError("i2r_owned_process_cleanup_incomplete")
            item["status"] = "PASS"
        except BaseException as exc:
            item.update(status="FAIL", code=safe_code(exc))
            result["status"] = "FAIL"
        result["processes"].append(item)
    try:
        # Also detects an inherited keeper that died between fork and its READY
        # evidence. Unknown extra holders prevent exposing real package commands.
        result["canonical_contender"] = compete(workdir)
        if result["canonical_contender"] != "acquired":
            result["status"] = "FAIL"
    except BaseException as exc:
        result.update(status="FAIL", contender_code=safe_code(exc))
    write_json(workdir / "cleanup.json", result)
    return result


def run(workdir):
    """Called only after outer I2P guard and approved readonly fake bindings."""
    workdir = Path(workdir)
    fixture_guard(workdir)
    if os.geteuid() != 0 or Path("/proc/1/comm").read_text().strip() != "systemd":
        raise InstallError("i2r_actual_systemd_root_required")
    # A guardian attestation protects against accidental direct invocation. It
    # is private fixture orchestration, never a production execution override.
    assert_active_bindings(workdir)
    h = Harness(workdir)
    sentinel_path = workdir / "owned-sentinel.py"
    sentinel_path.write_text("import time\ntime.sleep(600)\n")
    sentinel_path.chmod(0o600)
    sentinel = subprocess.Popen(["/usr/bin/python3", "-I", str(sentinel_path)],
                                env=CLEAN_ENV, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, close_fds=True)
    sentinel_record = process_record(sentinel.pid, "sentinel", os.getpid())
    h.journal["processes"].append(sentinel_record)
    h.save()
    checks = [
        ("canonical_export_two_transactions", lambda: completion(h, "canonical_export_two_transactions", transactions=2)),
        ("initially_absent_policy", lambda: completion(h, "initially_absent_policy", absent=True)),
        ("failed_transient_retention", lambda: completion(h, "failed_transient_retention", fail=True)),
        ("main_exit_live_descendant", lambda: descendants(h)),
        ("ctrl_c_exact_scope_abort", lambda: descendants(h, interrupt=True)),
        ("manager_timeout", lambda: descendants(h, timeout=True)),
        ("sigkill_preparing", lambda: crash(h, "preparing")),
        ("sigkill_owned", lambda: crash(h, "owned")),
        ("sigkill_ready", lambda: crash(h, "ready")),
        ("sigkill_gate", lambda: crash(h, "gate")),
        ("watcher_then_installer_killed", lambda: crash(h, "gate", kill_watcher=True)),
        ("unknown_identity", lambda: unknown_identity(h)),
        ("dirty_audit", lambda: audit_policy(h)),
        ("external_policy_change", lambda: audit_policy(h, external=True)),
        ("retirement_crash_retry", lambda: retirement(h)),
    ]
    try:
        for name, check in checks:
            write_json(workdir / "audit-state.json", {"dirty": False})
            before = len(h.cases)
            try:
                check()
                assert alive(sentinel_record)
                h.cases[-1]["unrelated_sentinel_alive"] = True
            except BaseException as exc:
                if len(h.cases) == before:
                    h.cases.append({"case": name, "status": "FAIL"})
                h.cases[-1].update(status="FAIL", code=safe_code(exc))
                h.cases[-1]["unrelated_sentinel_alive"] = alive(sentinel_record)
                # Keep evidence before cleanup. A source failure is never fixed
                # or relabelled an expected success in this verification task.
                write_json(workdir / "matrix-progress.json", h.cases)
                cleanup = cleanup_owned(workdir)
                # cleanup includes sentinel, restart only after exact success.
                if cleanup["status"] != "PASS":
                    break
                sentinel.wait(timeout=3)
                sentinel = subprocess.Popen(["/usr/bin/python3", "-I", str(sentinel_path)],
                                            env=CLEAN_ENV, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL, close_fds=True)
                sentinel_record = process_record(sentinel.pid, "sentinel", os.getpid())
                h.journal["processes"].append(sentinel_record)
                h.save()
            write_json(workdir / "matrix-progress.json", h.cases)
    finally:
        cleanup = cleanup_owned(workdir)
        try:
            sentinel.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
    gaps = [
        {"case": "scope_owned_storage_after_installer_death", "status": "NOT_TESTED", "code": "i1c_scope_owned_anchors_unfinished"},
        {"case": "mount_loss_gate_marker_writes", "status": "NOT_TESTED", "code": "i1c_anchored_gate_marker_unfinished"},
        {"case": "actual_reboot", "status": "NOT_TESTED", "code": "no_reboot_authorized"},
        {"case": "actual_package_gpu_docker_agent_acceptance", "status": "NOT_TESTED", "code": "synthetic_package_scope_only"},
    ]
    reached = {case["case"] for case in h.cases}
    h.cases.extend({"case": name, "status": "NOT_TESTED", "code": "earlier_cleanup_blocked_execution"}
                   for name, check in checks if name not in reached)
    result = {"schema_version": 1, "evidence_class": "actual_systemd_synthetic_package",
              "cases": h.cases + gaps, "cleanup": cleanup,
              "actual_cases_status": "PASS" if len(h.cases) == len(checks) and all(c["status"] == "PASS" for c in h.cases) else "FAIL",
              "full_source_acceptance": "NOT_TESTED", "fixture_storage": "private_protected_run_data_no_mount_proof"}
    result["status"] = "PASS" if result["actual_cases_status"] == "PASS" and cleanup["status"] == "PASS" else "FAIL"
    write_json(workdir / "matrix-result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--child", type=Path, help="internal bounded installer child")
    group.add_argument("--contender", type=Path, help="internal canonical nonblocking contender; guarded fixture root")
    group.add_argument("--dry-run", action="store_true", help="print bounded synthetic package plan without effects")
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps({"mode": "dry_run", "effects": "none", "canonical_lock": "/run/llmctl/lifecycle.lock",
                          "requires": ["approved_disposable_github_ubuntu", "guardian_fake_apt_dpkg_bindings"],
                          "test_count": 15, "storage_acceptance": "NOT_TESTED"}, sort_keys=True))
        return 0
    return child(args.child) if args.child else contender(args.contender)


if __name__ == "__main__":
    raise SystemExit(main())
