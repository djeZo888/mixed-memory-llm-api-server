"""Actual I1b preparation boundary with explicitly injected protected fixtures.

Only run() executes commands; it first requires the outer guardian's exact
read-only fake apt/dpkg bindings on the authorized ephemeral hosted VM. This is
synthetic package execution, not package installation or storage-lifetime proof.
The local tests use the real generator/parser with no package command execution.
"""
from __future__ import annotations

from contextlib import contextmanager
import inspect
import json
import os
from pathlib import Path
import re
import sys

SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from common.lifecycle_lease import (  # noqa: E402
    LifecycleLease, LeaseError, acquire_lease,
    _export_package_watcher_fd, _validate_borrowed_lease,
)
from install.container import ContainerPackages  # noqa: E402
from install.core import InstallError, Runner  # noqa: E402
from install.storage_io import AnchoredRoot  # noqa: E402
from lifecycle.manager import Manager  # noqa: E402


PREPARATION_MODES = {
    "update": ["update"],
    "simulate": ["-s", "--no-install-recommends", "--no-remove", "install", "i2r-fixture=1.0"],
    "download": ["--download-only", "--yes", "--no-install-recommends", "--no-remove", "install", "i2r-fixture=1.0"],
}
FAKE_RESPONSE = "I2R_FAKE_APT_PREPARATION_OK"


def _safe_code(exc):
    value = getattr(exc, "code", "")
    return value if isinstance(value, str) and re.fullmatch(r"[a-z0-9_]{1,100}", value) else "preparation_check_failed"


@contextmanager
def fixture_packages(workdir, *, runner=None):
    """Actual AnchoredRoot; guard data explicitly describes fixture directories.

    The supplied guard is not production mount verification. No _paths() call
    or repository-key fetch occurs. These fixtures deliberately make no claim
    about I1c scope-owned anchors, detached mounts, or anchored marker writes.
    """
    workdir = Path(workdir)
    if not workdir.is_absolute() or workdir.resolve() != workdir:
        raise RuntimeError("preparation_fixture_path_not_canonical")
    base = workdir / "preparation-fixture"
    base.mkdir(mode=0o700)
    data, system = base / "data", base / "system"
    data.mkdir(mode=0o700)
    system.mkdir(mode=0o700)
    (system / "usr").mkdir(mode=0o700)
    (system / "usr/sbin").mkdir(mode=0o700)
    device = data.stat().st_dev
    role = {"path": str(data), "mount": str(data), "uuid": "i2r-explicit-fixture",
            "fstype": "fixture", "device": f"{os.major(device)}:{os.minor(device)}"}
    snapshot = {"schema_version": 1, "data": role,
                "models": dict(role, path=str(data / "models")),
                "roots": {"state": str(data / "services/installer"),
                          "logs": str(data / "logs"), "build": str(data / "build")}}

    def guard():
        # Stable fixture registration; AnchoredRoot independently checks every
        # real descriptor, directory ancestry, owner/mode and device identity.
        return snapshot

    runner = runner if runner is not None else Runner(writable=True)
    lock = json.loads((SCRIPTS / "install/versions.lock.json").read_text())
    packages = ContainerPackages({"data_dir": str(data)}, runner, guard,
                                 lock=lock, system_root=system, uid=os.geteuid())
    with AnchoredRoot(str(data), guard, uid=os.geteuid()) as anchor:
        for relative in ("cache/installer-apt/archives/partial", "cache/installer-apt/lists/partial",
                         "cache/installer-apt/sourceparts", "cache/installer-apt/tmp",
                         "logs/installer", "services/installer"):
            anchor.mkdir(relative)
        with anchor.open("cache/installer-apt/ubuntu.sources", os.O_WRONLY | os.O_CREAT | os.O_EXCL) as stream:
            stream.write(b"# I2R explicit synthetic fixture; no package repositories\n")
            stream.fsync()
        packages._anchor = anchor  # explicit fixture lifetime; no production override
        try:
            yield packages
        finally:
            packages._anchor = None


def negative_commands(options):
    """Unsupported sandbox values, overriding options/modes and plain mutation."""
    result = {}
    for index, value in enumerate(("_apt", "nobody", "", "Root", "root\n")):
        altered = ["APT::Sandbox::User=" + value if item == "APT::Sandbox::User=root" else item
                   for item in options]
        result[f"sandbox_value_{index}"] = ["apt-get", *altered, "update"]
    for name, tail in {
        "sandbox_override": ["-o", "APT::Sandbox::User=_apt", "update"],
        "download_override": ["-o", "APT::Get::Download-Only=false", "update"],
        "late_option": ["update", "-o", "APT::Sandbox::User=root"],
        "late_mutating_mode": [*PREPARATION_MODES["download"], "--no-download"],
        "simulate_override": [*PREPARATION_MODES["simulate"], "--no-simulate"],
        "direct_mutation": ["--yes", "--no-download", "--no-install-recommends", "--no-remove", "install", "i2r-fixture=1.0"],
    }.items():
        result[name] = ["apt-get", *options, *tail]
    result["dpkg_mutation"] = ["dpkg", "--install", "i2r-fixture.deb"]
    return result


def check_source_only_negatives():
    """Inspect unbound apt's parser decisions without invoking Runner.run.

    Only apt-get/dpkg have approved fake bindings. Even a parser regression
    must never reach an executable for this apt fixture. Actual Runner refusal
    for unbound apt is deliberately NOT_TESTED in the hosted harness.
    """
    argv = ["apt", "install", "i2r-fixture"]
    preparation = Runner._package_preparation(argv)
    readonly = Runner._readonly(argv)
    return {"apt_mutation": {
        "status": "PASS" if not preparation and not readonly else "FAIL",
        "verification": "actual_parser_source_only",
        "preparation_parser_rejected": not preparation,
        "readonly_parser_rejected": not readonly,
        "runner_execution": {"status": "NOT_TESTED", "code": "unbound_apt_execution_omitted"},
    }}


def check_negatives(options):
    """Actual Runner refusals only for the two guardian-bound executables."""
    cases = {}
    runner = Runner(writable=True)
    for name, argv in negative_commands(options).items():
        if argv[0] not in {"apt-get", "dpkg"}:
            cases[name] = {"status": "FAIL", "code": "unbound_negative_executable_refused"}
            continue
        # Never execute a shape already known to have regressed at the parser.
        if Runner._package_preparation(argv):
            cases[name] = {"status": "FAIL", "code": "unsafe_preparation_shape_accepted"}
            continue
        try:
            runner.run(argv, timeout=5)
        except InstallError as exc:
            cases[name] = {"status": "PASS" if exc.code == "owned_package_transaction_required" else "FAIL",
                           "code": exc.code}
        else:
            cases[name] = {"status": "FAIL", "code": "unsafe_plain_runner_command_accepted"}
    return cases


def capability_refusals(lease, *, system_root, trusted_uid, wrong_root):
    """Canonical helper proof only; this does not claim Manager integration."""
    cases = {}
    exported = _export_package_watcher_fd(lease)
    try:
        attempts = {
            "wrong_root": (lease, Path(wrong_root), trusted_uid),
            "wrong_uid": (lease, Path(system_root), trusted_uid + 1),
            "fabricated": (object.__new__(LifecycleLease), Path(system_root), trusted_uid),
            "raw_export_fd": (exported, Path(system_root), trusted_uid),
            "plain_object": (object(), Path(system_root), trusted_uid),
        }
        for name, (borrowed, expected_root, expected_uid) in attempts.items():
            try:
                _validate_borrowed_lease(borrowed, system_root=expected_root, trusted_uid=expected_uid)
            except LeaseError as exc:
                expected = {"wrong_root": "borrowed_lease_scope_mismatch",
                            "wrong_uid": "borrowed_lease_scope_mismatch",
                            "fabricated": "lease_not_active"}.get(name, "invalid_borrowed_lease")
                cases[name] = {"status": "PASS" if exc.code == expected else "FAIL", "code": exc.code}
            else:
                cases[name] = {"status": "FAIL", "code": "invalid_capability_accepted"}
        lease.validate()
    finally:
        os.close(exported)  # caller duplicate closes before outer lease; no LOCK_UN
    return cases


def manager_contract():
    if "lease" not in inspect.signature(Manager.dispatch).parameters:
        return {"status": "NOT_TESTED", "code": "shipped_manager_borrow_api_missing",
                "evidence": "Manager.dispatch has no lease parameter; no canonical borrowing proof"}
    return {"status": "NOT_TESTED", "code": "manager_borrow_integration_requires_separate_review"}


def run(workdir: Path) -> dict:
    """Called only by the guarded hosted outer process with fake bindings active."""
    import guardian
    guardian.assert_active_bindings(workdir)
    report = {"status": "FAIL", "execution": "actual_runner_synthetic_packages",
              "fixture_injection": "protected_data_and_system_dirs_with_explicit_AnchoredRoot_guard",
              "manager_borrowing": manager_contract(),
              "storage_lifetime": {"status": "NOT_TESTED", "code": "i1c_scope_owned_anchors_pending"},
              "cases": {}}
    try:
        # Actual canonical module and fixed installed root, never a fixture
        # lock. Keep its minted duplicate for the ENTIRE Runner-use scope.
        with acquire_lease(blocking=False) as lease:
            exported = _export_package_watcher_fd(lease)
            try:
                runner = Runner(writable=True, package_lease_fd=exported)
                with fixture_packages(workdir, runner=runner) as packages:
                    options = packages._apt_options()
                    report["option_keys"] = [item.split("=", 1)[0] for item in options if item != "-o"]
                    report["sandbox_exact_root"] = options[-2:] == ["-o", "APT::Sandbox::User=root"]
                    for name, args in PREPARATION_MODES.items():
                        argv = ["apt-get", *options, *args]
                        accepted = Runner._package_preparation(argv)
                        result = {"status": "FAIL", "parser_accepted": accepted}
                        if accepted:
                            try:
                                response = packages._apt(args, timeout=10)
                                result.update(status="PASS" if response == FAKE_RESPONSE else "FAIL",
                                              fake_response_matched=response == FAKE_RESPONSE)
                            except Exception as exc:
                                result["code"] = _safe_code(exc)
                        else:
                            result["code"] = "actual_container_options_rejected"
                        report["cases"][name] = result
                    report["negative_cases"] = check_negatives(options)
                    report["source_only_negative_cases"] = check_source_only_negatives()
                report["canonical_helper_refusals"] = capability_refusals(
                    lease, system_root=Path("/"), trusted_uid=0, wrong_root=Path(workdir))
            finally:
                os.close(exported)  # before outer lease exit; never LOCK_UN
        report["actual_runner_negative_count"] = len(report["negative_cases"])
        required = [*report["cases"].values(), *report["negative_cases"].values(),
                    *report["source_only_negative_cases"].values(),
                    *report["canonical_helper_refusals"].values()]
        if (report["sandbox_exact_root"] and report["actual_runner_negative_count"] == 12
                and all(item["status"] == "PASS" for item in required)):
            report["status"] = "PASS"
    except Exception as exc:
        report["failure_code"] = _safe_code(exc)
    return report
