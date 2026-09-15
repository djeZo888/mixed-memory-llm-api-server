"""Canonical L1 export lifetime through the real package Runner API.

Uses the existing disposable POSIX supervisor and fake package executables.
Actual Linux systemd/cgroup behavior and host package mutation are NOT_TESTED.
Run: python3 -m unittest discover -s tests/install -p test_package_lease_retention.py -v
"""
import errno
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from package_process_fixture import (FakePackageScope, SENTINEL, fake_argv,
                                     make_subject, pid_is_live, wait_until)
from common.lifecycle_lease import (
    LeaseBusy, acquire_lease, _export_package_watcher_fd, _validate_borrowed_lease,
)
from install.core import InstallError
from install.prerequisites import PrerequisiteError, assert_package_admission


def canonical_installer(root):
    """Disposable child caller; SIGKILL bypasses both normal close-only exits."""
    scope = FakePackageScope(root, attach=True)
    arguments = {"system_root": root, "trusted_uid": os.getuid()}
    with acquire_lease(**arguments) as lease:
        _validate_borrowed_lease(lease, **arguments)
        exported = _export_package_watcher_fd(lease)
        try:
            subject = make_subject(root, exported, scope)
            subject.package_transaction(fake_argv(root, "stubborn"), timeout=3)
        finally:
            os.close(exported)  # before acquire_lease exits; never LOCK_UN


@unittest.skipUnless(os.name == "posix" and hasattr(os, "fork"), "requires POSIX fork/flock fixture")
class CanonicalPackageLeaseRetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="i1r2-", dir="/tmp")
        self.root = Path(self.tmp.name).resolve()
        self.root.chmod(0o700)
        self.arguments = {"system_root": self.root, "trusted_uid": os.getuid()}
        self.scope = FakePackageScope(self.root)
        flock_patch = patch("common.lifecycle_lease.fcntl.flock", wraps=fcntl.flock)
        self.flock_calls = flock_patch.start()
        self.addCleanup(flock_patch.stop)
        self.runners = []
        self.installers = []
        self.policy = self.root / "policy-rc.d"
        self.original = b"#!/bin/sh\n# original fixture policy\nexit 42\n"
        self.policy.write_bytes(self.original)
        self.policy.chmod(0o751)

    def tearDown(self):
        for process in self.installers:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        self.scope.close()
        self.wait_watchers()
        for name in ("apt.pid", "child.pid"):
            if (self.root / name).exists():
                pid = int((self.root / name).read_text())
                wait_until(lambda: not pid_is_live(pid), timeout=5)
        self.tmp.cleanup()
        self.assertFalse(any(call.args[1] & fcntl.LOCK_UN
                             for call in self.flock_calls.call_args_list),
                         "caller release must close descriptors, never LOCK_UN")

    def subject(self, exported):
        subject = make_subject(self.root, exported, self.scope)
        self.runners.append(subject.runner)
        return subject

    def export(self, lease):
        # Expected root/UID validation and mint provenance come from the one
        # actual canonical module, not Runner's raw-descriptor file checks.
        _validate_borrowed_lease(lease, **self.arguments)
        return _export_package_watcher_fd(lease)

    def wait_watchers(self):
        for runner in self.runners:
            for pid in runner._package_watchers[:]:
                wait_until(lambda: os.waitpid(pid, os.WNOHANG)[0], timeout=5)
                runner._package_watchers.remove(pid)

    def available(self):
        try:
            with acquire_lease(blocking=False, **self.arguments) as lease:
                lease.validate()
            return True
        except LeaseBusy:
            return False

    def assert_busy(self):
        with self.assertRaises(LeaseBusy):
            with acquire_lease(blocking=False, **self.arguments):
                self.fail("canonical lease was released while still owned")

    def close_before_lease_exit(self, exported, lease):
        os.close(exported)
        with self.assertRaises(OSError) as closed:
            os.fstat(exported)
        self.assertEqual(closed.exception.errno, errno.EBADF)
        lease.validate()  # canonical owner remains valid after export close
        self.assert_busy()

    def assert_restored(self, subject):
        self.assertEqual(self.policy.read_bytes(), self.original)
        self.assertEqual(self.policy.stat().st_mode & 0o777, 0o751)
        self.assertFalse((subject.state / "package-service-policy.json").exists())
        self.assertFalse((self.root / "child-saw-restored").exists())

    def test_same_export_retained_through_two_transactions_and_closed_before_lease_exit(self):
        with acquire_lease(**self.arguments) as lease:
            exported = self.export(lease)
            try:
                subject = self.subject(exported)
                for _ in range(2):
                    subject.package_transaction(fake_argv(self.root, "normal"), timeout=3)
                    self.assertEqual(subject.runner.package_lease_fd, exported)
                    os.fstat(exported)
                    lease.validate()
                    self.assert_restored(subject)
            finally:
                self.close_before_lease_exit(exported, lease)
        self.wait_watchers()
        self.assertTrue(self.available())

    def test_package_failure_closes_export_in_finally_before_lease_exit(self):
        with self.assertRaises(PrerequisiteError) as failure:
            with acquire_lease(**self.arguments) as lease:
                exported = self.export(lease)
                try:
                    subject = self.subject(exported)
                    subject.package_transaction(fake_argv(self.root, "nonzero"), timeout=3)
                finally:
                    self.close_before_lease_exit(exported, lease)
        self.assertEqual(failure.exception.code, "package_command_failed_or_timeout")
        self.assert_restored(subject)
        self.wait_watchers()
        self.assertTrue(self.available())

    def test_premature_close_after_ready_refuses_before_gate_but_watcher_retains_lease(self):
        with acquire_lease(**self.arguments) as lease:
            exported = self.export(lease)
            runner = self.subject(exported).runner
            gate = self.root / "unopened-gate.json"
            identity = runner.prepare_package(runner.package_identity(), gate_path=gate, timeout=3)
            runner.hold_package_lease(identity)  # returns only after watcher READY
            self.close_before_lease_exit(exported, lease)  # deliberately wrong timing
            with patch.object(self.scope, "execute", wraps=self.scope.execute) as execute:
                with self.assertRaises(InstallError) as refused:
                    runner.run_package(identity, fake_argv(self.root, "normal"), gate_path=gate)
                self.assertEqual(refused.exception.code, "package_borrowed_lifecycle_lease_invalid")
                execute.assert_not_called()
            self.assertFalse(gate.exists())
            self.assertFalse((self.root / "apt.pid").exists())
        # Both caller references are now closed. Only the watcher's inherited
        # export can retain the same flock while the prepared scope is live.
        self.assertEqual(self.scope.inspect(identity)["state"], "live")
        self.assert_busy()
        self.scope.abort(identity)
        wait_until(lambda: self.scope.inspect(identity)["state"] == "quiescent")
        self.wait_watchers()
        self.assertTrue(self.available())

    def test_parent_sigkill_keeps_canonical_lease_until_quiescence_then_recovers(self):
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
            "--canonical-installer", str(self.root)], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        self.installers.append(process)
        wait_until(lambda: (self.root / "child.pid").exists(), timeout=5)
        self.assertIsNone(process.poll())
        marker = self.root / "data/services/installer/package-service-policy.json"
        identity = json.loads(marker.read_text())["transaction"]
        child = int((self.root / "child.pid").read_text())
        process.kill()
        self.assertEqual(process.wait(timeout=3), -signal.SIGKILL)
        self.assertTrue(pid_is_live(child))
        self.assertEqual(self.scope.inspect(identity)["state"], "live")
        self.assert_busy()
        self.assertEqual(self.policy.read_bytes(), SENTINEL)
        wait_until(self.available, timeout=6)
        self.assertEqual(self.scope.inspect(identity)["state"], "quiescent")
        self.assertFalse(pid_is_live(child))
        with acquire_lease(**self.arguments) as lease:
            exported = self.export(lease)
            try:
                subject = self.subject(exported)
                with self.assertRaises(PrerequisiteError) as blocked:
                    assert_package_admission(subject.data, lambda: None, policy_path=self.policy)
                self.assertEqual(blocked.exception.code, "package_transaction_recovery_required")
                subject.recover_policy()
                assert_package_admission(subject.data, lambda: None, policy_path=self.policy)
                self.assert_restored(subject)
            finally:
                self.close_before_lease_exit(exported, lease)
        self.assertTrue(self.available())


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--canonical-installer":
        canonical_installer(Path(sys.argv[2]))
    else:
        unittest.main()
