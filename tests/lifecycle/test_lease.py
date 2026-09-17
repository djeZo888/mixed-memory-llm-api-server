"""Canonical lease worker fixtures: real flock, no services or host changes."""

from __future__ import annotations

import errno
import fcntl
import multiprocessing
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from common import lifecycle_lease as lease_module  # noqa: E402
from common.lifecycle_lease import (  # noqa: E402
    LifecycleLease, LeaseError, LeaseBusy, acquire_lease, transition_in_progress,
    _validate_borrowed_lease, _export_package_watcher_fd,
)


def _compete(root, uid, attempted, acquired, results):
    original = fcntl.flock

    def marked_flock(fd, flags):
        if flags == fcntl.LOCK_EX:
            attempted.set()
        return original(fd, flags)

    try:
        with patch.object(lease_module.fcntl, "flock", side_effect=marked_flock):
            with acquire_lease(system_root=Path(root), trusted_uid=uid) as lease:
                lease.validate()
                acquired.set()
        results.put("ok")
    except Exception as exc:
        results.put(type(exc).__name__)


def _inherited_lease(lease, results):
    try:
        lease.validate()
        results.put("incorrectly_accepted")
    except LeaseError as exc:
        results.put(exc.code)


def _try_nonblocking(root, uid, results):
    try:
        with acquire_lease(blocking=False, system_root=Path(root), trusted_uid=uid) as lease:
            lease.validate()
        results.put("ok")
    except LeaseBusy as exc:
        results.put(exc.code)


class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="lifecycle-lease-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.uid = os.getuid()
        self.arguments = {"system_root": self.root, "trusted_uid": self.uid}
        self.lock = self.root / "run/llmctl/lifecycle.lock"

    def acquire(self):
        return acquire_lease(**self.arguments)

    def observe(self):
        return transition_in_progress(**self.arguments)

    def make_lock(self):
        with self.acquire():
            pass

    def test_canonical_path_and_private_mode(self):
        with self.acquire() as lease:
            self.assertIs(type(lease), LifecycleLease)
            self.assertIsNone(lease.validate())
            self.assertEqual(self.lock.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.lock.parent.stat().st_mode & 0o777, 0o700)
            self.assertTrue(self.observe())
        self.assertFalse(self.observe())

    def test_status_does_not_create_missing_directories_or_lock(self):
        self.assertFalse(self.observe())
        self.assertFalse((self.root / "run").exists())
        (self.root / "run/llmctl").mkdir(parents=True, mode=0o700)
        before = tuple(self.lock.parent.iterdir())
        self.assertFalse(self.observe())
        self.assertEqual(tuple(self.lock.parent.iterdir()), before)

    def test_missing_lock_observation_never_uses_create_flag(self):
        (self.root / "run/llmctl").mkdir(parents=True, mode=0o700)
        original = os.open

        def checking_open(path, flags, *args, **kwargs):
            self.assertFalse(flags & os.O_CREAT)
            return original(path, flags, *args, **kwargs)

        with patch.object(lease_module.os, "open", side_effect=checking_open):
            self.assertFalse(self.observe())

    def test_environment_never_changes_lock_root_or_uid(self):
        with patch.dict(os.environ, {"LLMCTL_LOCK": str(self.root / "wrong.lock"),
                                     "SYSTEM_ROOT": "/different", "TRUSTED_UID": "98765"}):
            with self.acquire() as lease:
                lease.validate()
            self.assertTrue(self.lock.exists())
            self.assertFalse((self.root / "wrong.lock").exists())

    def test_borrow_validation_never_opens_lock_or_flocks(self):
        with self.acquire() as lease:
            original = os.open

            def directory_open(path, flags, *args, **kwargs):
                self.assertTrue(flags & os.O_DIRECTORY)
                return original(path, flags, *args, **kwargs)

            with patch.object(lease_module.fcntl, "flock", side_effect=AssertionError("borrow reacquired")), \
                    patch.object(lease_module.os, "open", side_effect=directory_open):
                lease.validate()
                lease.validate()
            os.fstat(lease_module._active[lease].fd)
            self.assertTrue(self.observe())

    def test_constructor_and_arbitrary_fd_do_not_mint_lease(self):
        with self.assertRaisesRegex(LeaseError, "lease_must_be_acquired"):
            LifecycleLease()
        with self.lock_parent_fd() as fd:
            with self.assertRaisesRegex(LeaseError, "lease_must_be_acquired"):
                LifecycleLease(fd)
        fabricated = object.__new__(LifecycleLease)
        with self.assertRaisesRegex(LeaseError, "lease_not_active"):
            fabricated.validate()

    def lock_parent_fd(self):
        # A legitimate ordinary FD still conveys no lease capability.
        from contextlib import contextmanager

        @contextmanager
        def opened():
            fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                yield fd
            finally:
                os.close(fd)

        return opened()

    def test_stale_lease_rejected_after_owner_exit(self):
        with self.acquire() as lease:
            pass
        with self.assertRaisesRegex(LeaseError, "lease_not_active"):
            lease.validate()

    def test_closed_descriptor_rejected_without_cleanup_double_close(self):
        with self.acquire() as lease:
            descriptor = lease_module._active[lease].fd
            os.close(descriptor)
            with self.assertRaisesRegex(LeaseError, "lease_descriptor_closed"):
                lease.validate()
        self.assertFalse(self.observe())

    def test_reused_descriptor_rejected_and_not_closed_on_exit(self):
        replacement = self.root / "unrelated"
        replacement.write_text("fixture")
        replacement.chmod(0o600)
        replacement_fd = None
        try:
            with self.acquire() as lease:
                descriptor = lease_module._active[lease].fd
                os.close(descriptor)
                replacement_fd = os.open(replacement, os.O_RDWR)
                if replacement_fd != descriptor:
                    os.dup2(replacement_fd, descriptor)
                    os.close(replacement_fd)
                    replacement_fd = descriptor
                self.assertEqual(descriptor, replacement_fd)
                with self.assertRaisesRegex(LeaseError, "lease_descriptor_changed"):
                    lease.validate()
            os.fstat(replacement_fd)
        finally:
            if replacement_fd is not None:
                os.close(replacement_fd)

    def test_same_pid_is_required(self):
        with self.acquire() as lease:
            with patch.object(lease_module.os, "getpid", return_value=os.getpid() + 1):
                with self.assertRaisesRegex(LeaseError, "lease_wrong_process"):
                    lease.validate()

    def test_replaced_inode_rejected_and_old_descriptor_released(self):
        with self.acquire() as lease:
            original_identity = self.lock.stat().st_ino
            self.lock.rename(self.lock.with_suffix(".old"))
            self.lock.touch(mode=0o600)
            self.assertNotEqual(original_identity, self.lock.stat().st_ino)
            with self.assertRaisesRegex(LeaseError, "lock_path_changed"):
                lease.validate()
        self.assertFalse(self.observe())
        with self.lock.with_suffix(".old").open() as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_replacement_during_acquisition_cannot_mint_a_lease(self):
        original = fcntl.flock

        def replacing_flock(fd, flags):
            result = original(fd, flags)
            if flags == fcntl.LOCK_EX:
                self.lock.rename(self.lock.with_suffix(".old"))
                self.lock.touch(mode=0o600)
            return result

        with patch.object(lease_module.fcntl, "flock", side_effect=replacing_flock):
            with self.assertRaisesRegex(LeaseError, "lock_path_changed"):
                with self.acquire():
                    self.fail("changed canonical inode minted a lease")
        self.assertFalse(self.observe())
        with self.lock.with_suffix(".old").open() as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_removed_canonical_lock_rejected(self):
        with self.acquire() as lease:
            self.lock.unlink()
            with self.assertRaises(LeaseError):
                lease.validate()

    def test_replaced_lock_directory_rejected(self):
        with self.acquire() as lease:
            self.lock.parent.rename(self.root / "run/previous")
            self.lock.parent.mkdir(mode=0o700)
            self.lock.touch(mode=0o600)
            with self.assertRaisesRegex(LeaseError, "lock_path_changed"):
                lease.validate()

    def test_symlink_lock_rejected_without_following_target(self):
        self.make_lock()
        self.lock.unlink()
        target = self.root / "target"
        target.write_text("fixture")
        target.chmod(0o600)
        self.lock.symlink_to(target)
        for operation in (self.observe, self.acquire_and_validate):
            with self.assertRaises(LeaseError):
                operation()
        self.assertEqual(target.read_text(), "fixture")

    def acquire_and_validate(self):
        with self.acquire() as lease:
            lease.validate()

    def test_symlink_ancestor_rejected_without_lock_creation(self):
        target = self.root / "outside"
        target.mkdir()
        (self.root / "run").symlink_to(target, target_is_directory=True)
        for operation in (self.observe, self.acquire_and_validate):
            with self.assertRaises(LeaseError):
                operation()
        self.assertEqual(tuple(target.iterdir()), ())

    def test_unsafe_directory_modes_rejected(self):
        for relative in (".", "run", "run/llmctl"):
            with self.subTest(relative=relative):
                self.make_lock()
                path = self.root / relative
                mode = path.stat().st_mode & 0o777
                path.chmod(0o777)
                try:
                    for operation in (self.observe, self.acquire_and_validate):
                        with self.assertRaisesRegex(LeaseError, "untrusted_lock_directory"):
                            operation()
                finally:
                    path.chmod(mode)

    def test_wrong_file_owner_rejected(self):
        self.make_lock()
        for operation in (transition_in_progress, acquire_lease):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(LeaseError, "untrusted_lock_"):
                    if operation is acquire_lease:
                        with operation(system_root=self.root, trusted_uid=self.uid + 1):
                            pass
                    else:
                        operation(system_root=self.root, trusted_uid=self.uid + 1)

    def test_group_readable_lock_and_hardlink_rejected(self):
        self.make_lock()
        self.lock.chmod(0o640)
        with self.assertRaisesRegex(LeaseError, "untrusted_lock_file"):
            self.observe()
        self.lock.chmod(0o600)
        os.link(self.lock, self.root / "alias.lock")
        with self.assertRaisesRegex(LeaseError, "untrusted_lock_file"):
            self.acquire_and_validate()

    def test_exact_lock_file_and_directory_modes_required(self):
        self.make_lock()
        for mode in (0o000, 0o400, 0o200, 0o640, 0o660):
            with self.subTest(mode=mode):
                self.lock.chmod(mode)
                with self.assertRaises(LeaseError):
                    with acquire_lease(blocking=False, **self.arguments):
                        pass
        self.lock.chmod(0o600)
        self.lock.parent.chmod(0o755)
        with self.assertRaisesRegex(LeaseError, "untrusted_lock_directory"):
            self.observe()

    def test_nonblocking_creates_same_canonical_path_and_reacquires(self):
        for _ in range(2):
            with acquire_lease(blocking=False, **self.arguments) as lease:
                lease.validate()
                self.assertTrue(self.lock.exists())
        self.assertFalse(self.observe())

    def test_nonblocking_errno_mapping_and_no_blocking_retry(self):
        self.make_lock()
        for code in (errno.EAGAIN, errno.EACCES):
            with self.subTest(code=code):
                with patch.object(lease_module.fcntl, "flock", side_effect=OSError(code, "private")) as operation:
                    with self.assertRaises(LeaseBusy) as caught:
                        with acquire_lease(blocking=False, **self.arguments):
                            pass
                self.assertEqual(str(caught.exception), "lifecycle_busy")
                self.assertEqual(caught.exception.code, "lifecycle_busy")
                self.assertEqual(operation.call_count, 1)
                self.assertEqual(operation.call_args.args[1], fcntl.LOCK_EX | fcntl.LOCK_NB)
        with self.assertRaisesRegex(LeaseError, "invalid_lease_blocking_mode"):
            with acquire_lease(blocking="false", **self.arguments):
                pass

    def test_nonblocking_rejects_unsafe_file_before_flock(self):
        self.make_lock()
        self.lock.chmod(0o666)
        with patch.object(lease_module.fcntl, "flock", side_effect=AssertionError("unsafe flock")):
            with self.assertRaisesRegex(LeaseError, "untrusted_lock_file"):
                with acquire_lease(blocking=False, **self.arguments):
                    pass

    def test_multiprocess_nonblocking_busy_then_success_after_release(self):
        context = multiprocessing.get_context("spawn")
        results = context.Queue()
        processes = []
        try:
            with self.acquire():
                process = context.Process(target=_try_nonblocking, args=(str(self.root), self.uid, results))
                processes.append(process)
                process.start()
                process.join(10)
                self.assertEqual(process.exitcode, 0)
                self.assertEqual(results.get(timeout=2), "lifecycle_busy")
            process = context.Process(target=_try_nonblocking, args=(str(self.root), self.uid, results))
            processes.append(process)
            process.start()
            process.join(10)
            self.assertEqual(process.exitcode, 0)
            self.assertEqual(results.get(timeout=2), "ok")
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(5)
            results.close()
            results.join_thread()

    def test_expected_scope_rejects_other_root_uid_and_subclass(self):
        class PretendLease(LifecycleLease):
            def validate(self):
                return None

        with self.acquire() as lease:
            _validate_borrowed_lease(lease, **self.arguments)
            with self.assertRaisesRegex(LeaseError, "borrowed_lease_scope_mismatch"):
                _validate_borrowed_lease(lease)
            with self.assertRaisesRegex(LeaseError, "borrowed_lease_scope_mismatch"):
                _validate_borrowed_lease(lease, system_root=self.root, trusted_uid=self.uid + 1)
            for invalid in (object.__new__(PretendLease), object(), lease_module._active[lease].fd):
                with self.assertRaisesRegex(LeaseError, "invalid_borrowed_lease"):
                    _validate_borrowed_lease(invalid, **self.arguments)

    def test_package_export_is_duplicate_and_close_reopen_cannot_counterfeit_lease(self):
        with self.acquire() as lease:
            exported = _export_package_watcher_fd(lease)
            private = lease_module._active[lease].fd
            self.assertNotEqual(exported, private)
            os.close(exported)
            # Reopen the same trusted inode without a lock, reusing the exported
            # number. The module's unexported owner still holds the real flock.
            replacement = os.open(self.lock, os.O_RDWR)
            try:
                if replacement != exported:
                    os.dup2(replacement, exported)
                    os.close(replacement)
                    replacement = exported
                lease.validate()
                with self.assertRaises(LeaseBusy):
                    with acquire_lease(blocking=False, **self.arguments):
                        pass
            finally:
                os.close(replacement)
        self.assertFalse(self.observe())

    def test_package_export_rejects_stale_fabricated_raw_and_failed_handoff_leaks_no_lock(self):
        with self.acquire() as lease:
            for invalid in (object(), object.__new__(LifecycleLease), lease_module._active[lease].fd):
                with self.assertRaises(LeaseError):
                    _export_package_watcher_fd(invalid)
            exported = _export_package_watcher_fd(lease)
            try:
                with self.assertRaises(FileNotFoundError):
                    subprocess.Popen([str(self.root / "absent-executable")], pass_fds=(exported,))
            finally:
                os.close(exported)
            with self.assertRaises(OSError):
                os.fstat(exported)
        with self.assertRaisesRegex(LeaseError, "lease_not_active"):
            _export_package_watcher_fd(lease)
        with acquire_lease(blocking=False, **self.arguments):
            pass

    def test_package_watcher_retains_same_lock_after_context_exit(self):
        watcher = None
        try:
            with self.acquire() as lease:
                exported = _export_package_watcher_fd(lease)
                try:
                    watcher = subprocess.Popen(
                        [sys.executable, "-c", "import sys; print('ready', flush=True); sys.stdin.buffer.read(1)"],
                        pass_fds=(exported,), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                finally:
                    os.close(exported)
                self.assertTrue(select.select([watcher.stdout], [], [], 10)[0])
                self.assertEqual(watcher.stdout.readline(), b"ready\n")
            self.assertTrue(self.observe())
            with self.assertRaises(LeaseBusy):
                with acquire_lease(blocking=False, **self.arguments):
                    pass
            watcher.stdin.close()
            watcher.wait(timeout=10)
            self.assertEqual(watcher.returncode, 0)
            with acquire_lease(blocking=False, **self.arguments):
                pass
        finally:
            if watcher is not None:
                if watcher.poll() is None:
                    watcher.kill()
                    watcher.wait(timeout=5)
                watcher.stdout.close()
                if not watcher.stdin.closed:
                    watcher.stdin.close()

    def test_package_watcher_retains_lock_after_owner_sigkill(self):
        read_end, write_end = os.pipe()
        watcher_pid = None
        owner = None
        script = """
import os, pathlib, subprocess, sys, time
sys.path.insert(0, sys.argv[1])
from common.lifecycle_lease import acquire_lease, _export_package_watcher_fd
with acquire_lease(system_root=pathlib.Path(sys.argv[2]), trusted_uid=int(sys.argv[3])) as lease:
    exported = _export_package_watcher_fd(lease)
    try:
        child = subprocess.Popen([sys.executable, '-c',
            'import os,sys; print(\"ready\",flush=True); os.read(int(sys.argv[1]),1)', sys.argv[4]],
            pass_fds=(exported, int(sys.argv[4])), stdout=subprocess.PIPE, start_new_session=True)
    finally:
        os.close(exported)
    if child.stdout.readline() != b'ready\\n':
        raise RuntimeError('watcher_not_ready')
    print(child.pid, flush=True)
    time.sleep(120)
"""
        try:
            owner = subprocess.Popen([sys.executable, "-c", script, str(ROOT / "scripts"),
                                      str(self.root), str(self.uid), str(read_end)],
                                     pass_fds=(read_end,), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            os.close(read_end)
            read_end = None
            self.assertTrue(select.select([owner.stdout], [], [], 10)[0])
            watcher_pid = int(owner.stdout.readline().strip())
            owner.kill()
            owner.wait(timeout=10)
            self.assertEqual(owner.returncode, -signal.SIGKILL)
            self.assertTrue(self.observe())
            with self.assertRaises(LeaseBusy):
                with acquire_lease(blocking=False, **self.arguments):
                    pass
            os.write(write_end, b"x")
            deadline = time.monotonic() + 10
            while True:
                try:
                    with acquire_lease(blocking=False, **self.arguments):
                        break
                except LeaseBusy:
                    if time.monotonic() >= deadline:
                        self.fail("watcher did not release the inherited lock")
                    time.sleep(0.01)
            watcher_pid = None
        finally:
            if read_end is not None:
                os.close(read_end)
            os.close(write_end)
            if owner is not None:
                if owner.poll() is None:
                    owner.kill()
                    owner.wait(timeout=5)
                owner.stdout.close()
            if watcher_pid is not None:
                try:
                    os.kill(watcher_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

    def test_context_and_observer_never_explicitly_unlock(self):
        original = fcntl.flock

        def forbid_unlock(fd, flags):
            self.assertNotEqual(flags, fcntl.LOCK_UN)
            return original(fd, flags)

        with patch.object(lease_module.fcntl, "flock", side_effect=forbid_unlock):
            with self.acquire():
                self.assertTrue(self.observe())
            self.assertFalse(self.observe())

    def test_fifo_does_not_block_or_qualify_as_lock(self):
        (self.root / "run/llmctl").mkdir(parents=True, mode=0o700)
        os.mkfifo(self.lock, mode=0o600)
        for operation in (self.observe, self.acquire_and_validate):
            with self.assertRaisesRegex(LeaseError, "untrusted_lock_file"):
                operation()

    def test_permission_change_invalidates_active_lease(self):
        with self.acquire() as lease:
            self.lock.chmod(0o666)
            with self.assertRaisesRegex(LeaseError, "untrusted_lock_file"):
                lease.validate()
            self.lock.chmod(0o600)

    def test_invalid_fixture_arguments_fail_closed(self):
        for root, uid in ((Path("relative"), self.uid), (self.root / "..", self.uid),
                          (self.root, -1), (self.root, True), (self.root, "0")):
            with self.subTest(root=root, uid=uid):
                with self.assertRaisesRegex(LeaseError, "unsafe_lease_root"):
                    with acquire_lease(system_root=root, trusted_uid=uid):
                        pass
        self.assertFalse((self.root / "run").exists())

    def test_safe_errors_do_not_include_arbitrary_diagnostics(self):
        self.assertEqual(str(LeaseError("secret: not a diagnostic code")), "lease_failed")
        with patch.object(lease_module.os, "open", side_effect=PermissionError(errno.EACCES, "private payload")):
            with self.assertRaises(LeaseError) as result:
                self.acquire_and_validate()
        self.assertEqual(str(result.exception), "lease_acquisition_failed")

    def test_exception_releases_once_and_preserves_body_error(self):
        original_flock, original_close = fcntl.flock, os.close
        unlocks, owner_closes = [], []
        owner_fd = None

        def recording_flock(fd, flags):
            if flags == fcntl.LOCK_UN:
                unlocks.append(fd)
            return original_flock(fd, flags)

        def recording_close(fd):
            if fd == owner_fd:
                owner_closes.append(fd)
            return original_close(fd)

        with patch.object(lease_module.fcntl, "flock", side_effect=recording_flock), \
                patch.object(lease_module.os, "close", side_effect=recording_close):
            with self.assertRaisesRegex(RuntimeError, "body_failed"):
                with self.acquire() as lease:
                    owner_fd = lease_module._active[lease].fd
                    raise RuntimeError("body_failed")
        self.assertEqual(unlocks, [])
        self.assertEqual(owner_closes, [owner_fd])
        self.assertFalse(self.observe())

    def test_multiprocess_competitor_blocked_across_borrow(self):
        context = multiprocessing.get_context("spawn")
        attempted, acquired, results = context.Event(), context.Event(), context.Queue()
        process = context.Process(target=_compete,
                                  args=(str(self.root), self.uid, attempted, acquired, results))
        try:
            with self.acquire() as lease:
                process.start()
                self.assertTrue(attempted.wait(10), "competitor did not attempt flock")
                self.assertFalse(acquired.wait(0.15), "competitor crossed owner lock")
                with patch.object(lease_module.fcntl, "flock", side_effect=AssertionError("borrow reacquired")):
                    lease.validate()
                self.assertFalse(acquired.is_set())
                self.assertTrue(self.observe())
            self.assertTrue(acquired.wait(10), "owner failed to release")
            process.join(10)
            self.assertEqual(process.exitcode, 0)
            self.assertEqual(results.get(timeout=2), "ok")
        finally:
            if process.is_alive():
                process.terminate()
                process.join(5)
            results.close()
            results.join_thread()

    @unittest.skipUnless("fork" in multiprocessing.get_all_start_methods(), "requires fork")
    def test_fork_inherited_lease_cannot_borrow_or_release_parent_lock(self):
        context = multiprocessing.get_context("fork")
        results = context.Queue()
        process = None
        try:
            with self.acquire() as lease:
                process = context.Process(target=_inherited_lease, args=(lease, results))
                process.start()
                process.join(10)
                self.assertEqual(process.exitcode, 0)
                self.assertEqual(results.get(timeout=2), "lease_not_active")
                lease.validate()
                self.assertTrue(self.observe(), "child unlocked the parent's lease")
            self.assertFalse(self.observe())
        finally:
            if process is not None and process.is_alive():
                process.terminate()
                process.join(5)
            results.close()
            results.join_thread()


if __name__ == "__main__":
    unittest.main()
