"""Finite internal canonical-lease carrier, no HTTP/CLI/env activation or shell.

Production construction requires the actual helper Operations object and a
source-reviewed host implementation of the exact task/admission/closure gates.
This module never infers quiescence, clears holds or restores old SQLite bytes.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import hashlib
import json
import os
import stat
import time


class CarrierError(Exception):
    pass


@dataclass(frozen=True)
class CarrierPlan:
    transaction_id: str
    boot_id: str
    stop_request: dict
    start_request: dict
    issued_at: float
    expires_at: float
    dispatch_cutoff: float
    settlement_reserve: float
    source_roots: tuple[Path, ...]
    backup_root: Path
    journal: Path


class CarrierHost(Protocol):
    # Methods are trusted host producers, never results supplied by a task/model.
    def assert_current(self, plan: CarrierPlan, lease, stage: str) -> None: ...
    def assert_stopped_writers(self, plan: CarrierPlan, lease) -> None: ...
    def run_owned_task(self, plan: CarrierPlan, lease) -> object: ...
    def settle_owned_task(self, plan: CarrierPlan, lease) -> None: ...
    def assert_task_closed(self, plan: CarrierPlan, lease) -> None: ...
    def assert_restored(self, plan: CarrierPlan, lease, before: dict) -> object: ...
    def retain_restore_needed(self, plan: CarrierPlan, reason: str) -> None: ...


def _identity(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid,
            s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def _file_bytes(path: Path):
    before = path.lstat()
    if before.st_size > 128 * 1024 * 1024:
        raise CarrierError("preservation_file_bound")
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise CarrierError("preservation_file_alias")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        if _identity(before) != _identity(os.fstat(fd)):
            raise CarrierError("preservation_identity_changed")
        digest = hashlib.sha256()
        chunks = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            chunks.append(chunk)
        if _identity(before) != _identity(os.fstat(fd)) or _identity(before) != _identity(path.lstat()):
            raise CarrierError("preservation_identity_changed")
        return b"".join(chunks), digest.hexdigest(), before
    finally:
        os.close(fd)


def tree_manifest(root: Path):
    """Whole stopped tree, including ALL present DB/WAL/SHM/journal/native files.

    Symlinks/special files/foreign hardlinks reject rather than following into
    credentials, another owner's data or silently dropping preservation inputs.
    """
    if root.resolve() != root or not root.is_dir():
        raise CarrierError("preservation_root_alias")
    result = {}
    for path in sorted([root, *root.rglob("*")]):
        s = path.lstat()
        key = str(path.relative_to(root))
        if stat.S_ISDIR(s.st_mode):
            result[key] = {"kind": "directory", "mode": stat.S_IMODE(s.st_mode), "uid": s.st_uid, "gid": s.st_gid}
        elif stat.S_ISREG(s.st_mode):
            _, digest, s = _file_bytes(path)
            result[key] = {"kind": "file", "mode": stat.S_IMODE(s.st_mode), "uid": s.st_uid, "gid": s.st_gid,
                           "bytes": s.st_size, "sha256": digest}
        else:
            raise CarrierError("preservation_unsupported_member")
    return result


def preserve_stopped_roots(roots: tuple[Path, ...], destination: Path):
    if destination.exists() or destination.resolve() != destination:
        raise CarrierError("fresh_preservation_root_required")
    for root in roots:
        if root == destination or root in destination.parents or destination in root.parents:
            raise CarrierError("preservation_overlap")
    destination.mkdir(mode=0o700)
    receipts = []
    for index, root in enumerate(roots):
        before = tree_manifest(root)
        target = destination / str(index)
        target.mkdir(mode=0o700)
        for name, metadata in before.items():
            if name == ".":
                continue
            path = target / name
            if metadata["kind"] == "directory":
                path.mkdir(mode=metadata["mode"])
                os.chmod(path, metadata["mode"])
                if os.geteuid() == 0:
                    os.chown(path, metadata["uid"], metadata["gid"])
            else:
                raw, digest, info = _file_bytes(root / name)
                if digest != metadata["sha256"]:
                    raise CarrierError("preservation_source_changed")
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, metadata["mode"])
                try:
                    view = memoryview(raw)
                    while view:
                        view = view[os.write(fd, view):]
                    os.fsync(fd)
                    os.fchmod(fd, metadata["mode"])
                    if os.geteuid() == 0:
                        os.fchown(fd, info.st_uid, info.st_gid)
                finally:
                    os.close(fd)
        # Exact file content/modes/owner and complete member set, then recheck source.
        copied = tree_manifest(target)
        if set(copied) != set(before) or any(copied[k] != v for k, v in before.items() if k != "."):
            raise CarrierError("preservation_copy_mismatch")
        if tree_manifest(root) != before:
            raise CarrierError("preservation_source_changed")
        receipts.append({"source": str(root), "copy": str(target), "manifest": before})
    return receipts


_retained_carriers = {}  # Same-process strong owner retention; NOT a process-death watcher.


class QualificationCarrier:
    def __init__(self, operations, host: CarrierHost, *, clock=time.time):
        self.operations, self.host, self.clock = operations, host, clock
        self._pending = {}  # Strongly retains the SAME same-process minted lease/context.

    def pending(self, transaction_id):
        return transaction_id in self._pending

    def settle_pending(self, transaction_id):
        """Trusted same-process cleanup/restore only. Never re-executes task work."""
        retained = self._pending[transaction_id]
        plan, context, lease, stop, preservation = retained
        lease.validate()
        self.host.settle_owned_task(plan, lease)
        self.host.assert_task_closed(plan, lease)
        self.host.assert_stopped_writers(plan, lease)
        if preservation is None:
            raise CarrierError("preservation_baseline_unavailable")
        for receipt in preservation:
            if tree_manifest(Path(receipt["source"])) != receipt["manifest"]:
                raise CarrierError("preserved_original_changed_before_restore")
        self.host.assert_current(plan, lease, "before-restore")
        start = self.operations.submit_under_lease(plan.start_request, lease)
        if start["status"] != "succeeded":
            raise CarrierError("normal_restore_unproved")
        delta = self.host.assert_restored(plan, lease, {"stop": stop, "start": start, "preservation": preservation})
        lease.validate()
        del self._pending[transaction_id]
        _retained_carriers.pop(transaction_id, None)
        context.__exit__(None, None, None)
        return {"status": "restored_no_replay", "start": start, "recoveryDelta": delta}

    def run(self, plan: CarrierPlan):
        if plan.transaction_id in _retained_carriers:
            raise CarrierError("carrier_unsettled_owner_retained")
        # Explicit plan supplied by a reviewed protected entry, no window override.
        if (not plan.transaction_id or plan.issued_at > self.clock() or
                not plan.issued_at < plan.dispatch_cutoff < plan.expires_at or
                plan.settlement_reserve != 120 or plan.dispatch_cutoff > plan.expires_at - 120):
            raise CarrierError("carrier_authorization_invalid")
        for request, action in [(plan.stop_request, "service.stop"), (plan.start_request, "service.start")]:
            if (request.get("action") != action or request.get("node_id") != "ai-harness" or
                    request.get("service_id") != "harness" or request.get("expected_boot_id") != plan.boot_id):
                raise CarrierError("carrier_fixed_action_required")
        if plan.stop_request["idempotency_key"] == plan.start_request["idempotency_key"]:
            raise CarrierError("carrier_action_key_reuse")
        # O_EXCL durable once-only journal. A crashed carrier is UNKNOWN; never replay.
        fd = os.open(plan.journal, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        def event(stage, **values):
            raw = (json.dumps({"transaction": plan.transaction_id, "stage": stage, **values}, sort_keys=True)+"\n").encode()
            os.write(fd, raw); os.fsync(fd)
        stop_attempted = False
        stopped = False
        task_started = False
        restored = False
        preservation = None
        stop = None
        context = self.operations.lease()
        lease = None
        keep_owned = False
        started_wall, started_mono = self.clock(), time.monotonic()
        def remaining():
            return min(plan.expires_at-self.clock(), plan.expires_at-started_wall-(time.monotonic()-started_mono))
        def dispatch():
            if self.clock() >= plan.dispatch_cutoff or remaining() <= plan.settlement_reserve:
                raise CarrierError("carrier_dispatch_expired")
        try:
            lease = context.__enter__()
            lease.validate()
            self.host.assert_current(plan, lease, "before-stop")
            dispatch()
            stop_attempted = True
            stop = self.operations.submit_under_lease(plan.stop_request, lease)
            event("normal-stop", receipt=stop)
            if stop["status"] != "succeeded":
                raise CarrierError("normal_stop_unproved")
            stopped = True
            self.host.assert_stopped_writers(plan, lease)
            preservation = preserve_stopped_roots(plan.source_roots, plan.backup_root)
            event("stopped-preservation", roots=preservation)
            task_error = None
            task = None
            try:
                self.host.assert_current(plan, lease, "before-task")
                dispatch()
                task_started = True
                task = self.host.run_owned_task(plan, lease)
                event("task-returned", result=task)
            except Exception as error:
                task_error = error
                event("task-failed", noReplay=True)
            finally:
                if task_started:
                    self.host.settle_owned_task(plan, lease)
                self.host.assert_task_closed(plan, lease)
                lease.validate()
            for receipt in preservation:
                if tree_manifest(Path(receipt["source"])) != receipt["manifest"]:
                    raise CarrierError("preserved_original_changed_before_restore")
            self.host.assert_current(plan, lease, "before-restore")
            start = self.operations.submit_under_lease(plan.start_request, lease)
            event("normal-start", receipt=start)
            if start["status"] != "succeeded":
                raise CarrierError("normal_restore_unproved")
            delta = self.host.assert_restored(plan, lease, {"stop": stop, "start": start, "preservation": preservation})
            lease.validate(); restored = True
            event("restored", recoveryDelta=delta)
            if task_error is not None:
                raise task_error
            if remaining() <= 0:
                raise CarrierError("carrier_expired_after_restore")
            return {"status": "settled", "stop": stop, "start": start, "task": task, "preservation": preservation, "recoveryDelta": delta}
        except Exception:
            if stop_attempted and not restored:
                # Store owner/context BEFORE calling any fallible journal/quarantine producer.
                # Do not let a failed cleanup release the lock and race normal restoration.
                keep_owned = True
                self._pending[plan.transaction_id] = (plan, context, lease, stop, preservation)
                _retained_carriers[plan.transaction_id] = self
                self.host.retain_restore_needed(plan, "owned_settlement_or_restore_unproved")
            event("failed", stopAttempted=stop_attempted, stopped=stopped, taskStarted=task_started, restored=restored, noReplay=True)
            raise
        finally:
            if lease is not None and not keep_owned:
                context.__exit__(None, None, None)
            os.close(fd)
