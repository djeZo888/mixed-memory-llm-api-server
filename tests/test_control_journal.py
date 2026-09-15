"""Disposable local file-store contracts; no production storage or VM access.

FixtureAtomicJSONStore is intentionally confined to tests. Production must use
the reviewed registered-storage owner; it cannot opt into this path-based seam.
"""

import copy
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from control.journal import (  # noqa: E402
    Journal, JournalCorrupt, JournalInvalid, JournalUnavailable, MAX_BYTES,
    empty_state,
)


class FixtureAtomicJSONStore:
    """Atomic, private fixture storage anchored to a disposable directory FD."""

    def __init__(self, path, *, expected_uid):
        self.path = Path(path)
        self.expected_uid = expected_uid

    def _directory(self):
        fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            self._check_directory(fd)
        except BaseException:
            os.close(fd)
            raise
        return fd

    def _check_directory(self, fd):
        actual = os.fstat(fd)
        named = os.stat(self.path.parent, follow_symlinks=False)
        if (not stat.S_ISDIR(actual.st_mode) or actual.st_uid != self.expected_uid
                or actual.st_mode & 0o077 or actual.st_nlink < 1
                or (actual.st_dev, actual.st_ino) != (named.st_dev, named.st_ino)):
            raise OSError("fixture_storage_unprotected")

    def _check_file(self, info):
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != self.expected_uid
                or info.st_mode & 0o077 or info.st_nlink != 1):
            raise OSError("fixture_storage_unprotected")

    def _existing(self, directory):
        try:
            info = os.stat(self.path.name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            return
        self._check_file(info)

    def read(self):
        directory = self._directory()
        try:
            try:
                fd = os.open(self.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            except FileNotFoundError:
                self._check_directory(directory)
                return None
            try:
                info = os.fstat(fd)
                self._check_file(info)
                if info.st_size > MAX_BYTES:
                    raise JournalCorrupt()
                raw = bytearray()
                while len(raw) <= MAX_BYTES:
                    part = os.read(fd, min(65536, MAX_BYTES + 1 - len(raw)))
                    if not part:
                        break
                    raw.extend(part)
                if len(raw) > MAX_BYTES:
                    raise JournalCorrupt()
                self._check_directory(directory)
                named = os.stat(self.path.name, dir_fd=directory, follow_symlinks=False)
                if (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino):
                    raise OSError("fixture_storage_changed")
            finally:
                os.close(fd)
            try:
                def unique(pairs):
                    result = {}
                    for key, value in pairs:
                        if key in result:
                            raise ValueError()
                        result[key] = value
                    return result
                return json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
            except (ValueError, UnicodeDecodeError, RecursionError):
                raise JournalCorrupt() from None
        finally:
            os.close(directory)

    def write(self, value):
        encoded = json.dumps(value, allow_nan=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_BYTES:
            raise OSError("fixture_storage_too_large")
        directory = self._directory()
        temporary = ".fixture-journal-" + uuid.uuid4().hex
        created = False
        try:
            self._existing(directory)
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
            created = True
            try:
                os.fchmod(fd, 0o600)
                remaining = memoryview(encoded)
                while remaining:
                    count = os.write(fd, remaining)
                    if count <= 0:
                        raise OSError("fixture_storage_short_write")
                    remaining = remaining[count:]
                os.fsync(fd)
            finally:
                os.close(fd)
            self._check_directory(directory)
            self._existing(directory)
            os.replace(temporary, self.path.name, src_dir_fd=directory, dst_dir_fd=directory)
            created = False
            os.fsync(directory)
            self._check_directory(directory)
        finally:
            if created:
                os.unlink(temporary, dir_fd=directory)
            os.close(directory)


class MemoryStore:
    def __init__(self, value=None):
        self.value = copy.deepcopy(value)

    def read(self):
        return self.value

    def write(self, value):
        self.value = copy.deepcopy(value)


def operation(number=1, *, status="succeeded", completed_at=100):
    identifier = f"{number:032x}"
    return {
        "id": identifier, "kind": "switch", "target": "future-model",
        "status": status, "created_at": 10, "updated_at": 100,
        "deadline": 300, "completed_at": completed_at,
        "request_digest": f"{number:064x}", "idempotency_digest": f"{number+128:064x}",
        "generation": number, "active_identity": "a" * 64, "failure_code": None,
        "observed": {
            "selected": "future-model", "desired": "running", "observed": "ready",
            "container_running": True, "active_identity": "a" * 64,
            "generation": number, "state_persisted": True, "observed_at": 100,
        },
        "state_persisted": True, "poll_url": "/control/v1/operations/" + identifier,
    }


def state_with(*entries):
    return {"schema": 1, "generation": 2, "fingerprint": "f" * 64,
            "entries": {entry["id"]: copy.deepcopy(entry) for entry in entries}}


class JournalTests(unittest.TestCase):
    def test_absence_is_empty_and_copies_are_independent(self):
        journal = Journal(MemoryStore())
        value = journal.read()
        self.assertEqual(value, empty_state())
        value["generation"] = 99
        self.assertEqual(journal.read()["generation"], 0)
        store = MemoryStore(state_with(operation()))
        value = Journal(store).read()
        value["entries"].clear()
        self.assertEqual(len(store.value["entries"]), 1)

    def test_durable_snapshot_is_not_mutated_by_caller(self):
        store = MemoryStore()
        journal = Journal(store)
        value = state_with(operation())
        self.assertTrue(journal.save(value))
        value["entries"].clear()
        self.assertEqual(len(journal.read()["entries"]), 1)

    def test_corruption_and_unavailable_are_distinct_safe_errors(self):
        with self.assertRaisesRegex(JournalCorrupt, "^journal_corrupt$"):
            Journal(MemoryStore({"secret": "sensitive-fixture"})).read()
        store = MemoryStore()
        with mock.patch.object(store, "read", side_effect=OSError("sensitive-fixture")):
            with self.assertRaisesRegex(JournalUnavailable, "^journal_unavailable$") as raised:
                Journal(store).read()
        self.assertTrue(raised.exception.__suppress_context__)

    def test_write_failure_does_not_report_persistence(self):
        store = MemoryStore(empty_state())
        with mock.patch.object(store, "write", side_effect=OSError("sensitive-fixture")):
            self.assertFalse(Journal(store).save(state_with(operation())))
        self.assertEqual(store.value, empty_state())

    def test_unknown_fields_and_raw_objects_are_rejected_before_store(self):
        variants = []
        for key in ("authorization", "body", "env", "command", "path", "config"):
            value = state_with(operation())
            value["entries"][operation()["id"]][key] = "sensitive-fixture"
            variants.append(value)
        value = state_with(operation())
        value["entries"][operation()["id"]]["observed"]["container"] = {"Env": ["sensitive-fixture"]}
        variants.append(value)
        for value in variants:
            with self.subTest(value=next(iter(value["entries"].values())).keys()):
                store = MemoryStore()
                with self.assertRaises(JournalInvalid):
                    Journal(store).save(value)
                self.assertIsNone(store.value)

    def test_invalid_scalars_ids_and_nonfinite_time_rejected(self):
        for field, value in (
            ("generation", True), ("created_at", float("nan")), ("deadline", float("inf")),
            ("created_at", 10**1000),
            ("request_digest", "raw-request"), ("idempotency_digest", "raw-key"),
            ("target", "../../file"), ("failure_code", "private /path: detail"),
            ("poll_url", "https://example.invalid/operation"), ("state_persisted", 1),
            ("status", ["running"]), ("completed_at", None),
        ):
            with self.subTest(field=field):
                entry = operation()
                entry[field] = value
                with self.assertRaises(JournalInvalid):
                    Journal(MemoryStore()).save(state_with(entry))

    def test_capacity_never_evicts_unexpired_idempotency_records(self):
        journal = Journal(MemoryStore(), max_entries=2, retention_seconds=100, clock=lambda: 199)
        value = state_with(operation(1), operation(2))
        self.assertEqual(journal.prune(value), value)
        too_many = state_with(operation(1), operation(2), operation(3))
        with self.assertRaises(JournalInvalid):
            journal.save(too_many)

    def test_retention_expires_terminal_only_at_exact_boundary(self):
        pending = operation(2, status="running", completed_at=None)
        value = state_with(operation(1), pending)
        before = Journal(MemoryStore(), retention_seconds=100, clock=lambda: 199).prune(value)
        self.assertEqual(len(before["entries"]), 2)
        after = Journal(MemoryStore(), retention_seconds=100, clock=lambda: 200).prune(value)
        self.assertEqual(list(after["entries"]), [pending["id"]])
        self.assertEqual(len(value["entries"]), 2)

    def test_duplicate_idempotency_and_multiple_active_entries_refused(self):
        one, two = operation(1), operation(2)
        two["idempotency_digest"] = one["idempotency_digest"]
        with self.assertRaises(JournalInvalid):
            Journal(MemoryStore()).save(state_with(one, two))
        with self.assertRaises(JournalInvalid):
            Journal(MemoryStore()).save(state_with(
                operation(1, status="pending", completed_at=None),
                operation(2, status="running", completed_at=None),
            ))

    def test_restart_preserves_interrupted_work_without_replaying(self):
        store = MemoryStore()
        saved = state_with(operation(status="running", completed_at=None))
        self.assertTrue(Journal(store).save(saved))
        self.assertEqual(Journal(store).read(), saved)
        # Owner reconciliation is mandatory; persistence has no backend methods.
        self.assertEqual(Journal(store).read()["entries"][operation()["id"]]["status"], "running")


class FileStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="u1-journal-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.directory.chmod(0o700)
        self.path = self.directory / "journal.json"
        self.store = FixtureAtomicJSONStore(self.path, expected_uid=os.getuid())
        self.journal = Journal(self.store)

    def test_file_durability_restart_and_private_mode(self):
        state = state_with(operation())
        with mock.patch("os.fsync", wraps=os.fsync) as sync:
            self.assertTrue(self.journal.save(state))
        self.assertEqual(sync.call_count, 2)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        reopened = Journal(FixtureAtomicJSONStore(self.path, expected_uid=os.getuid()))
        self.assertEqual(reopened.read(), state)

    def test_failed_atomic_replace_preserves_old_and_removes_temporary(self):
        self.assertTrue(self.journal.save(empty_state()))
        with mock.patch("os.replace", side_effect=OSError("fixture-disk-full")):
            self.assertFalse(self.journal.save(state_with(operation())))
        self.assertEqual(self.journal.read(), empty_state())
        self.assertEqual(sorted(p.name for p in self.directory.iterdir()), ["journal.json"])

    def test_directory_fsync_failure_reports_uncertain_persistence(self):
        real_sync = os.fsync
        def sync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("fixture-directory-fsync-failed")
            real_sync(fd)
        with mock.patch("os.fsync", side_effect=sync):
            self.assertFalse(self.journal.save(state_with(operation())))
        # Rename can precede an uncertain durability result. Work must never be
        # replayed automatically merely because save returned False.
        self.assertEqual(self.journal.read(), state_with(operation()))

    def test_directory_replacement_cannot_redirect_commit(self):
        real_sync = os.fsync
        original = self.directory / "original"
        replacement = self.directory / "replacement"
        original.mkdir(mode=0o700)
        replacement.mkdir(mode=0o700)
        store = FixtureAtomicJSONStore(original / "journal.json", expected_uid=os.getuid())
        detached = self.directory / "detached"
        def sync(fd):
            real_sync(fd)
            if stat.S_ISREG(os.fstat(fd).st_mode):
                original.rename(detached)
                replacement.rename(original)
        with mock.patch("os.fsync", side_effect=sync):
            self.assertFalse(Journal(store).save(empty_state()))
        self.assertEqual(list(original.iterdir()), [])
        self.assertEqual(list(detached.iterdir()), [])

    def test_symlink_and_hardlink_file_rejected_for_read_and_write(self):
        target = self.directory / "untouched.json"
        target.write_text("untouched")
        target.chmod(0o600)
        self.path.symlink_to(target)
        with self.assertRaises(JournalUnavailable):
            self.journal.read()
        self.assertFalse(self.journal.save(empty_state()))
        self.assertEqual(target.read_text(), "untouched")
        self.path.unlink()
        os.link(target, self.path)
        with self.assertRaises(JournalUnavailable):
            self.journal.read()
        self.assertFalse(self.journal.save(empty_state()))

    def test_unprotected_or_wrong_owner_directory_refused(self):
        self.directory.chmod(0o750)
        with self.assertRaises(JournalUnavailable):
            self.journal.read()
        self.assertFalse(self.journal.save(empty_state()))
        self.directory.chmod(0o700)
        other = Journal(FixtureAtomicJSONStore(self.path, expected_uid=os.getuid() + 1))
        with self.assertRaises(JournalUnavailable):
            other.read()
        self.assertFalse(other.save(empty_state()))

    def test_symlink_directory_refused(self):
        link = self.directory / "link"
        link.symlink_to(self.directory, target_is_directory=True)
        journal = Journal(FixtureAtomicJSONStore(link / "journal.json", expected_uid=os.getuid()))
        with self.assertRaises(JournalUnavailable):
            journal.read()
        self.assertFalse(journal.save(empty_state()))

    def test_bounded_malformed_duplicate_and_invalid_utf8_file(self):
        for contents in (b"{" + b"x" * MAX_BYTES, b"{invalid", b'{"schema":1,"schema":1}', b"\xff"):
            with self.subTest(length=len(contents)):
                self.path.write_bytes(contents)
                self.path.chmod(0o600)
                with self.assertRaises(JournalCorrupt):
                    self.journal.read()

    def test_missing_directory_is_unavailable_not_empty_journal(self):
        journal = Journal(FixtureAtomicJSONStore(self.directory / "missing" / "journal.json", expected_uid=os.getuid()))
        with self.assertRaises(JournalUnavailable):
            journal.read()
        self.assertFalse(journal.save(empty_state()))


if __name__ == "__main__":
    unittest.main()
