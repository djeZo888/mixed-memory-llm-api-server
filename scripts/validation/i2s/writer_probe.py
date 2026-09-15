#!/usr/bin/env python3
"""Actual mount-path writer checks, only in a guarded disposable Linux namespace.

The Storage discovery snapshot and registry path are explicit fixture seams.
MountedStorageGuard itself reads real kernel mountinfo with no injected reader.
No disk, installed registration, model path, Docker mount, or package is used.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[3]
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}
CONTEXT_KEYS = ("GITHUB_ACTIONS", "RUNNER_ENVIRONMENT", "GITHUB_REPOSITORY",
                "GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT",
                "I2P_DISPOSABLE_ACK", "RUNNER_TEMP", "ImageOS", "ImageVersion")
MAX_TMPFS_BYTES = 16 * 1024 * 1024


class ProbeError(RuntimeError):
    """Fixed, sanitized fixture error."""


def _require(condition, code):
    if not condition:
        raise ProbeError(code)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def plan():
    return {"mode": "DRY_RUN", "scope": "owned_tmpfs_and_bind_mounts_only",
            "namespace": "new private Linux mount namespace; no shared mounts",
            "fixture_parent": "/run", "max_concurrent_tmpfs_bytes": MAX_TMPFS_BYTES,
            "disk_backing_bytes": 0, "external_path_or_device_arguments": False,
            "cases": ["valid_preflight_and_anchor", "same_device_nested_bind",
                      "unrelated_docker_style_sibling", "unknown_mount_ownership",
                      "detach_before_write", "detach_after_precheck_before_os_write"],
            "cleanup": "exact mount entry, mountpoint device/inode; no broad unmount",
            "not_tested": ["production_Storage_discovery", "production_root_exclusion",
                           "Docker", "model_mounts", "I1c_role_aware_writer_conversion"]}


def _command(argv):
    # Guest tools have fixed, small output. Do not capture or relay their output.
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, env=ENV, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeError("command_incomplete:" + Path(argv[0]).name + ":" + type(exc).__name__) from None
    _require(result.returncode == 0,
             "command_failed:" + Path(argv[0]).name + ":" + str(result.returncode))
    return result.returncode


def _mounts():
    with open("/proc/self/mountinfo", "rb") as stream:
        raw = stream.read(8 * 1024 * 1024 + 1)
    _require(len(raw) <= 8 * 1024 * 1024, "mountinfo_too_large")
    result = []
    try:
        for line in raw.decode("utf-8", errors="strict").splitlines():
            fields = line.split()
            split = fields.index("-", 6)
            _require(len(fields) == split + 4 and fields[0].isdigit(), "invalid_mountinfo")
            decode = lambda value: re.sub(r"\\(040|011|012|134)",
                                           lambda match: chr(int(match[1], 8)), value)
            result.append({"id": int(fields[0]), "device": fields[2],
                           "root": decode(fields[3]), "target": decode(fields[4]),
                           "fstype": fields[split + 1], "entry": fields,
                           "propagation": fields[6:split]})
    except (ValueError, UnicodeError, IndexError):
        raise ProbeError("invalid_mountinfo") from None
    _require(bool(result), "empty_mountinfo")
    return result


def _identity(path):
    info = os.lstat(path)
    _require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
             "unprotected_fixture_directory")
    return [info.st_dev, info.st_ino]


def _environment():
    i2p = _load("i2s_writer_i2p_context", REPO / "scripts/validation/i2p/run.py")
    i2p.validate_context({key: os.environ.get(key, "") for key in CONTEXT_KEYS})
    _require(platform.system() == "Linux" and os.geteuid() == 0,
             "requires_disposable_linux_root")
    release = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines()
                   if "=" in line)
    _require(release.get("ID", "").strip('"') == "ubuntu"
             and release.get("VERSION_ID", "").strip('"') == "24.04",
             "requires_ubuntu_24_04")
    _require(platform.machine() == "x86_64", "requires_amd64")
    _require(os.readlink("/proc/self/ns/mnt") != os.readlink("/proc/1/ns/mnt"),
             "refuse_initial_mount_namespace")
    _require(all(not any(flag.startswith(("shared:", "master:", "propagate_from:"))
                         for flag in row["propagation"]) for row in _mounts()),
             "requires_private_mount_propagation")
    for tool in ("mount", "umount"):
        _require(shutil.which(tool) is not None, "missing_prerequisite:" + tool)
    _identity(Path("/run"))
    i2p.capability(Path(os.environ.get("RUNNER_TEMP", "")))


def _capture_mount(target, source_identity=None):
    rows = [row for row in _mounts() if row["target"] == str(target)]
    _require(len(rows) == 1, "mount_target_missing_or_ambiguous")
    row = rows[0]
    identity = _identity(target)
    device = f"{os.major(identity[0])}:{os.minor(identity[0])}"
    _require(row["device"] == device and row["fstype"] == "tmpfs", "fixture_mount_device_changed")
    if source_identity is not None:
        _require(identity == source_identity, "bind_source_identity_changed")
    return {"target": str(target), "identity": identity, "entry": row["entry"],
            "mount_id": row["id"], "device": row["device"], "fstype": row["fstype"]}


def _assert_owned(record):
    actual = _capture_mount(Path(record["target"]))
    _require(actual == record, "mount_ownership_changed_preserve_state")
    return actual


def _unmount_owned(record, *, lazy=False):
    _assert_owned(record)  # no command may precede exact identity validation
    _command(["umount", "--internal-only", *(["--lazy"] if lazy else []), "--", record["target"]])
    _require(not any(row["id"] == record["mount_id"] for row in _mounts()),
             "owned_mount_id_still_present")
    return {"mount_id": record["mount_id"], "verified_identity": record["identity"],
            "verified_device": record["device"], "lazy": lazy,
            "independently_observed_mount_id_absent": True}


def _snapshot(directory):
    """Small exact manifest; refuses symlinks, hardlinks and foreign file types."""
    result = {}
    paths = [directory, *sorted(directory.rglob("*"))]
    _require(len(paths) <= 100, "fixture_manifest_entry_bound")
    for path in paths:
        info = os.lstat(path)
        _require(info.st_uid == 0 and not info.st_mode & 0o022, "fixture_manifest_owner_mode")
        row = {"device": info.st_dev, "inode": info.st_ino, "mode": stat.S_IMODE(info.st_mode)}
        if stat.S_ISDIR(info.st_mode):
            row["type"] = "directory"
        else:
            _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 65536,
                     "fixture_manifest_file_bound")
            row.update(type="file", size=info.st_size,
                       sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        result[str(path.relative_to(directory))] = row
    return result


class Fixture:
    """One exact scratch tree and at most one 16 MiB tmpfs at a time."""

    def __init__(self):
        self.path = Path(tempfile.mkdtemp(prefix="i2s-writer-", dir="/run"))
        self.identity = _identity(self.path)
        self.mount = self.path / "data"
        self.mount.mkdir(mode=0o700)
        self.marker = self.mount / "underlay-marker"
        self.marker.write_bytes(b"i2s-owned-underlay-unchanged\n")
        self.marker.chmod(0o600)
        self.underlay_identity = _identity(self.mount)
        self.registry = self.path / "etc/local-ai-server/storage.json"
        self.registry.parent.mkdir(parents=True, mode=0o700)
        self.registry.write_bytes(b"{}\n")
        self.registry.chmod(0o600)
        self.records = []
        self.removed = []
        self.clean_tree = _snapshot(self.path)

    def start(self):
        _require(_identity(self.path) == self.identity, "fixture_root_replaced")
        _require(_identity(self.mount) == self.underlay_identity, "fixture_underlay_replaced")
        _require(not any(row["target"] == str(self.mount) for row in _mounts()),
                 "fixture_target_already_mounted")
        _command(["mount", "--internal-only", "-t", "tmpfs", "-o", "size=16m,mode=0700,nosuid,nodev,noexec",
                  "i2s-writer-owned", str(self.mount)])
        record = _capture_mount(self.mount)
        self.records.append(record)
        return record

    def bind(self, source, target):
        _require(source.is_relative_to(self.mount) and target.is_relative_to(self.mount)
                 and source != target, "bind_outside_owned_fixture")
        _assert_owned(self.records[0])
        _identity(target)
        source_id = _identity(source)
        _require(not any(row["target"] == str(target) for row in _mounts()),
                 "bind_target_already_mounted")
        _command(["mount", "--internal-only", "--bind", "--", str(source), str(target)])
        record = _capture_mount(target, source_id)
        self.records.append(record)
        return record

    def detach(self, record, *, lazy=False):
        self.removed.append(_unmount_owned(record, lazy=lazy))
        self.records.remove(record)

    def storage(self, record):
        data = str(self.mount)
        self.value = {"schema_version": 1,
                      "roots": {"build": data + "/build", "models": data + "/models"},
                      "data": {"path": data, "mount": data, "device": record["device"],
                               "fstype": "tmpfs", "uuid": "i2s-fixture-no-block-uuid"},
                      "models": {"path": data + "/models", "mount": data,
                                 "device": record["device"], "fstype": "tmpfs",
                                 "uuid": "i2s-fixture-no-block-uuid"}}
        for relative in ("build", "models", "alias-source", "build/target", "build/docker-style-sibling"):
            (self.mount / relative).mkdir(mode=0o700)
        self.registry.write_text(json.dumps(self.value, sort_keys=True) + "\n")
        self.registry.chmod(0o600)
        registry_row = self.clean_tree["etc/local-ai-server/storage.json"]
        registry_row["sha256"] = hashlib.sha256(self.registry.read_bytes()).hexdigest()
        registry_row["size"] = self.registry.stat().st_size
        fixture = self

        class StorageFixture:
            owner = 0
            system_root = fixture.path

            def guard(self):
                _assert_owned(record)
                return copy.deepcopy(fixture.value)

        return StorageFixture()

    def cleanup(self):
        evidence = {"status": "INCOMPLETE", "mounts_removed": self.removed, "scratch_removed": False}
        try:
            _require(_identity(self.path) == self.identity, "fixture_root_replaced")
            for record in list(reversed(self.records)):
                self.detach(record)
            _require(not any(row["target"] == str(self.path)
                             or row["target"].startswith(str(self.path) + "/") for row in _mounts()),
                     "unknown_descendant_mount_preserve_scratch")
            actual = _snapshot(self.path)
            _require(actual == self.clean_tree,
                     "scratch_identity_or_bytes_changed_preserve_state")
            # Exact snapshot and parent ownership were checked. No recursive deletion.
            for relative, row in sorted(actual.items(), key=lambda item: item[0].count("/"), reverse=True):
                if relative == ".":
                    continue
                path = self.path / relative
                info = os.lstat(path)
                _require([info.st_dev, info.st_ino] == [row["device"], row["inode"]],
                         "scratch_identity_changed_during_cleanup")
                path.rmdir() if row["type"] == "directory" else path.unlink()
            self.path.rmdir()
            evidence.update(status="PASS", scratch_removed=True,
                            observed_remaining_mount_ids=[])
        except (OSError, ProbeError) as exc:
            evidence["error_code"] = str(exc) if isinstance(exc, ProbeError) else type(exc).__name__
            evidence["scratch_preserved"] = True
        return evidence


def _attempt(io, operation):
    try:
        operation()
        return {"rejected": False, "error_code": None}
    except io.StorageIOError as exc:
        return {"rejected": True, "error_code": exc.code}


def _write(root, relative, payload=b"i2s-owned-payload"):
    with root.open(relative, os.O_CREAT | os.O_EXCL | os.O_RDWR) as stream:
        stream.write(payload)
        stream.fsync()


def _alias_cases(io, fixture, record, guard, root):
    results = {}
    root.check()
    _write(root, "ordinary")
    results["valid_preflight_and_anchor"] = {"status": "PASS", "mount_id": record["mount_id"],
        "device": record["device"], "anchor_identity": _identity(root.path)}
    source, target = fixture.mount / "alias-source", fixture.mount / "build/target"
    before = _snapshot(source)
    bind = fixture.bind(source, target)
    _require(bind["device"] == record["device"] and bind["mount_id"] != record["mount_id"],
             "same_device_distinct_mount_id_fixture_not_established")
    observed = _attempt(io, lambda: _write(root, "target/forbidden"))
    after = _snapshot(source)
    results["same_device_nested_bind"] = {**observed,
        "status": "PASS" if observed["rejected"] and before == after else "FAIL",
        "same_underlying_device": bind["device"] == record["device"],
        "registered_mount_id": record["mount_id"], "alias_mount_id": bind["mount_id"],
        "source_identity": _identity(source), "target_identity": _identity(target),
        "before": before, "after": after, "source_unchanged": before == after}
    # Deliberately present a wrong ownership claim; no unmount command may run.
    false_claim = copy.deepcopy(bind)
    false_claim["mount_id"] = record["mount_id"]
    initial = _capture_mount(target)
    refusal_code = None
    try:
        _unmount_owned(false_claim)
        refused = False
    except ProbeError as exc:
        refusal_code = str(exc)
        refused = str(exc) == "mount_ownership_changed_preserve_state"
    final = _capture_mount(target)
    results["unknown_mount_ownership"] = {"status": "PASS" if refused and initial == final else "FAIL",
        "refused_before_unmount": refused, "exact_mount_state_preserved": initial == final,
        "observed_mount_id": final["mount_id"], "claimed_mount_id": false_claim["mount_id"],
        "error_code": refusal_code, "before": initial, "after": final}
    fixture.detach(bind)
    sibling = fixture.bind(source, fixture.mount / "build/docker-style-sibling")
    observed = _attempt(io, lambda: _write(root, "safe-sibling-operation"))
    results["unrelated_docker_style_sibling"] = {**observed,
        "status": "PASS" if not observed["rejected"] else "FAIL",
        "sibling_mount_id": sibling["mount_id"], "real_Docker_used": False}
    fixture.detach(sibling)
    return results


def _detach_case(io, fixture, record, root, *, race):
    underlay_identity = _identity(fixture.mount)
    with root.open("partial", os.O_CREAT | os.O_EXCL | os.O_RDWR) as stream:
        stream.write(b"preserved")
        fd = stream.fileno()
        before = os.pread(fd, 128, 0)
        actual_write = os.write
        injected = []

        def detach_then_write(target_fd, payload):
            _require(target_fd == fd and not injected, "unexpected_race_write_target")
            fixture.detach(record, lazy=True)
            injected.append(True)
            return actual_write(target_fd, payload)

        if race:
            with patch.object(io.os, "write", side_effect=detach_then_write):
                outcome = _attempt(io, lambda: stream.write(b"anchored-after-detach"))
        else:
            fixture.detach(record, lazy=True)
            outcome = _attempt(io, lambda: stream.write(b"must-not-write"))
        after = os.pread(fd, 128, 0)
        late_create = _attempt(io, lambda: _write(root, "fallthrough-forbidden"))
        underlay = sorted(path.name for path in fixture.mount.iterdir())
        preserved = (underlay == ["underlay-marker"]
                     and fixture.marker.read_bytes() == b"i2s-owned-underlay-unchanged\n")
        expected_bytes = before + b"anchored-after-detach" if race else before
        return {"status": "PASS" if outcome["rejected"] and late_create["rejected"]
                and preserved and after == expected_bytes and bool(injected) == race else "FAIL",
                "write": outcome, "late_create": late_create,
                "detach_after_valid_precheck": race and bool(injected),
                "injection": "actual_lazy_umount_immediately_before_actual_os_write" if race
                             else "actual_lazy_umount_before_guarded_write",
                "detached_mount_identity": underlay_identity,
                "fallthrough_identity": _identity(fixture.mount),
                "held_file_before_sha256": hashlib.sha256(before).hexdigest(),
                "held_file_after_sha256": hashlib.sha256(after).hexdigest(),
                "held_file_size_after": len(after), "root_underlay_unchanged": preserved,
                "root_underlay_entries": underlay, "actual_parent_SIGKILL": False}


def run_probe():
    """Return JSON-safe evidence; caller must have created a private namespace."""
    _environment()  # must precede every fixture creation or Linux mutation
    started = time.monotonic()
    io = _load("i2s_actual_writer", REPO / "scripts/install/storage_io.py")
    evidence = {"status": "FAIL", "plan": plan(), "cases": {}, "cleanup": [],
                "kernel": platform.release(), "namespace": os.readlink("/proc/self/ns/mnt"),
                "source_sha256": hashlib.sha256(Path(io.__file__).read_bytes()).hexdigest(),
                "path_aware_writer_api_present": hasattr(io.MountedStorageGuard, "check_path"),
                "discovery": "explicit_fixture_snapshot_and_registry_path; real_kernel_mountinfo",
                "role_aware_Storage_conversion": {"status": "NOT_TESTED"}}
    for name in ("aliases", "detach_before_write", "detach_during_write"):
        fixture = None
        try:
            fixture = Fixture()
            record = fixture.start()
            storage = fixture.storage(record)
            with io.MountedStorageGuard(storage) as guard:
                with io.AnchoredRoot(str(fixture.mount / "build"), guard, uid=0) as root:
                    if name == "aliases":
                        evidence["cases"].update(_alias_cases(io, fixture, record, guard, root))
                    else:
                        evidence["cases"][name] = _detach_case(io, fixture, record, root,
                                                             race=name == "detach_during_write")
            if fixture.records:
                fixture.detach(record)
            # The original pre-mount manifest remains the cleanup authority.
            _require(sorted(p.name for p in fixture.mount.iterdir()) == ["underlay-marker"]
                     and fixture.marker.read_bytes() == b"i2s-owned-underlay-unchanged\n",
                     "root_underlay_changed_preserve_state")
        except Exception as exc:
            evidence["cases"][name] = {"status": "FAIL", "failure_type": type(exc).__name__,
                "error_code": getattr(exc, "code", str(exc) if isinstance(exc, ProbeError) else type(exc).__name__)}
        finally:
            if fixture is not None:
                evidence["cleanup"].append(fixture.cleanup())
            else:
                evidence["cleanup"].append({"status": "INCOMPLETE",
                                            "error_code": "fixture_allocation_identity_unavailable"})
        if evidence["cleanup"][-1]["status"] != "PASS":
            evidence["stop_reason"] = "cleanup_uncertain_no_further_fixture_allocation"
            break
    evidence["elapsed_seconds"] = round(time.monotonic() - started, 3)
    fixtures = evidence["cleanup"]
    evidence["cleanup"] = {"status": "PASS" if len(fixtures) == 3
                           and all(row["status"] == "PASS" for row in fixtures)
                           else "INCOMPLETE", "fixtures": fixtures}
    if (all(row["status"] == "PASS" for row in evidence["cases"].values())
            and evidence["cleanup"]["status"] == "PASS"):
        evidence["status"] = "PASS"
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--namespace-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps(plan(), indent=2, sort_keys=True))
        return 0
    if not args.namespace_child:
        i2p = _load("i2s_writer_i2p_context", REPO / "scripts/validation/i2p/run.py")
        i2p.validate_context({key: os.environ.get(key, "") for key in CONTEXT_KEYS})
        _require(platform.system() == "Linux" and os.geteuid() == 0,
                 "requires_disposable_linux_root")
        i2p.capability(Path(os.environ.get("RUNNER_TEMP", "")))
        result = subprocess.run(["unshare", "--mount", "--propagation", "private", sys.executable,
                                 "-B", str(Path(__file__).resolve()), "--apply", "--namespace-child"],
                                env={**ENV, **{key: os.environ.get(key, "") for key in CONTEXT_KEYS}},
                                timeout=180, check=False)
        return result.returncode
    evidence = run_probe()
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
