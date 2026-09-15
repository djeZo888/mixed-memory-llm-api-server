"""Real disposable POSIX descendants and borrowed flock ownership tests.

These exercise production Runner/recovery with a disposable supervisor adapter.
They do NOT test systemd, cgroup containment, Linux daemon escapes, or host apt.
Run: python3 -m unittest discover -s tests/install -p test_package_processes.py -v
"""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from package_process_fixture import (FakePackageScope, HERE, SENTINEL, fake_argv,
                                     make_subject, pid_is_live, wait_until)
from install.core import InstallError
from install.prerequisites import PrerequisiteError, assert_package_admission


@unittest.skipUnless(os.name == "posix" and hasattr(os, "fork"), "requires POSIX fork/flock fixture")
class PackageProcessOwnershipTests(unittest.TestCase):
    def setUp(self):
        # Keep Unix socket names under Darwin's length limit. All effects remain
        # inside this disposable tree; no system policy/services/packages change.
        self.tmp = tempfile.TemporaryDirectory(prefix="i1r-", dir="/tmp")
        self.root = Path(self.tmp.name).resolve()
        self.root.chmod(0o700)
        self.scope = FakePackageScope(self.root)
        self.fd = os.open(self.root / "lifecycle.lock", os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.subject = make_subject(self.root, self.fd, self.scope)
        self.policy = self.root / "policy-rc.d"
        self.marker = self.subject.state / "package-service-policy.json"
        self.original = b"#!/bin/sh\n# pre-existing fixture policy\n# opaque bytes: \xff\x00\nexit 42\n"
        self.policy.write_bytes(self.original)
        self.policy.chmod(0o751)
        self.installers = []

    def tearDown(self):
        # Kill only owned live Popen installer fixtures. The independent
        # supervisor remains authoritative for its own package-group cleanup.
        for process in self.installers:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        (self.root / "inspect-failure").unlink(missing_ok=True)
        (self.root / "keeper-release-ready").touch()
        self.scope.close()
        self.wait_keepers()
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        # Supervisor shutdown retains terminal evidence for keepers to observe.
        # Ensure no live fake package descendants escaped cleanup.
        for filename in ("apt.pid", "child.pid"):
            if (self.root / filename).exists():
                pid = int((self.root / filename).read_text())
                wait_until(lambda pid=pid: not pid_is_live(pid), timeout=5)
        self.tmp.cleanup()

    def assert_restored(self):
        self.assertEqual(self.policy.read_bytes(), self.original)
        self.assertEqual(self.policy.stat().st_mode & 0o777, 0o751)
        self.assertFalse(self.marker.exists())
        self.assertFalse((self.root / "child-saw-restored").exists(),
                         "descendant observed restored policy before exiting")
        for filename in ("apt.pid", "child.pid"):
            if (self.root / filename).exists():
                self.assertFalse(pid_is_live(int((self.root / filename).read_text())))
        self.wait_keepers()

    def wait_keepers(self):
        runner = self.subject.runner
        for pid in runner._package_watchers[:]:
            def reaped():
                try:
                    return os.waitpid(pid, os.WNOHANG)[0]
                except ChildProcessError:
                    return True
            wait_until(reaped, timeout=5)
            runner._package_watchers.remove(pid)

    def run_package(self, mode, timeout=3):
        return self.subject._package_install(fake_argv(self.root, mode), timeout=timeout, env=None)

    def lock_available(self):
        probe = os.open(self.root / "lifecycle.lock", os.O_RDWR)
        try:
            try:
                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
            return True
        finally:
            os.close(probe)

    def start_crashing_installer(self, timeout=3):
        os.close(self.fd)
        self.fd = None
        process = subprocess.Popen([sys.executable, HERE, "installer", str(self.root), "stubborn", str(timeout)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True)
        self.installers.append(process)
        wait_until(lambda: (self.root / "child.pid").exists(), timeout=5)
        self.assertIsNone(process.poll())
        self.assertEqual(self.policy.read_bytes(), SENTINEL)
        self.assertTrue(self.marker.exists())
        return process

    def recover(self):
        # Real admission cannot obtain this flock while the keeper owns it.
        # Calling recovery read/inspect directly here checks its additional
        # liveness gate independently of admission; fixture paths only.
        return self.subject.recover_policy()

    def assert_admission(self, *, blocked):
        """The caller really holds a newly acquired canonical fixture flock."""
        descriptor = os.open(self.root / "lifecycle.lock", os.O_RDWR)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            before = self.marker.read_bytes() if self.marker.exists() else None
            policy_before = self.policy.read_bytes() if self.policy.exists() else None
            if blocked:
                with self.assertRaises(PrerequisiteError) as raised:
                    assert_package_admission(self.subject.data, lambda: None, policy_path=self.policy)
                self.assertEqual(raised.exception.code, "package_transaction_recovery_required")
            else:
                assert_package_admission(self.subject.data, lambda: None, policy_path=self.policy)
            self.assertEqual(self.marker.read_bytes() if self.marker.exists() else None, before)
            self.assertEqual(self.policy.read_bytes() if self.policy.exists() else None, policy_before)
        finally:
            os.close(descriptor)

    def start_window_installer(self, mode, checkpoint, timeout=2):
        os.close(self.fd)
        self.fd = None
        process = subprocess.Popen([sys.executable, HERE, "installer", str(self.root), mode, str(timeout)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True)
        self.installers.append(process)
        wait_until(lambda: (self.root / checkpoint).exists(), timeout=5)
        self.assertIsNone(process.poll())
        saved = json.loads(self.marker.read_text())
        self.assertEqual(saved["phase"], "owned")
        self.assertEqual(self.policy.read_bytes(), SENTINEL)
        return process, saved["transaction"]

    def assert_admission_blocked_until_recovered(self, identity):
        self.assertTrue(self.lock_available())
        self.assertEqual(self.scope.inspect(identity)["state"], "live")
        self.assert_admission(blocked=True)
        with self.assertRaises((PrerequisiteError, InstallError)):
            self.recover()
        self.assertEqual(self.policy.read_bytes(), SENTINEL)
        wait_until(lambda: self.scope.inspect(identity)["state"] == "quiescent", timeout=6)
        # A released lock and quiescent scope still do not retire a transaction.
        self.assert_admission(blocked=True)
        self.recover()
        self.assert_restored()
        self.assert_admission(blocked=False)

    def test_crash_after_prepared_marker_before_watcher_requires_admission_recovery(self):
        process, identity = self.start_window_installer("before-watcher", "before-watcher")
        process.kill()
        self.assertEqual(process.wait(timeout=3), -signal.SIGKILL)
        self.assertFalse((self.root / "apt.pid").exists())
        self.assert_admission_blocked_until_recovered(identity)
        self.assertFalse((self.root / "apt.pid").exists())

    def test_crash_after_ready_before_gate_releases_lease_only_on_bounded_quiescence(self):
        process, identity = self.start_window_installer("after-ready", "after-ready-before-gate")
        process.kill()
        self.assertEqual(process.wait(timeout=3), -signal.SIGKILL)
        self.assertFalse(self.lock_available())
        self.assertEqual(self.scope.inspect(identity)["state"], "live")
        self.assertFalse((self.root / "apt.pid").exists())
        with self.assertRaises((PrerequisiteError, InstallError)):
            self.recover()
        self.assertEqual(self.policy.read_bytes(), SENTINEL)
        wait_until(self.lock_available, timeout=6)
        self.assertEqual(self.scope.inspect(identity)["state"], "quiescent")
        self.assert_admission(blocked=True)
        self.recover()
        self.assert_restored()
        self.assert_admission(blocked=False)
        self.assertFalse((self.root / "apt.pid").exists())

    def test_watcher_then_cli_crash_cannot_admit_live_descendant_from_available_lease(self):
        process, identity = self.start_window_installer("watcher-dies", "watcher-reaped", timeout=2.5)
        child_pid = int((self.root / "child.pid").read_text())
        self.assertTrue(pid_is_live(child_pid))
        heartbeat = (self.root / "heartbeat").read_text()
        process.kill()
        self.assertEqual(process.wait(timeout=3), -signal.SIGKILL)
        wait_until(lambda: (self.root / "heartbeat").read_text() != heartbeat)
        self.assertTrue(pid_is_live(child_pid))
        self.assert_admission_blocked_until_recovered(identity)
        self.assertFalse(pid_is_live(child_pid))

    def test_missing_borrowed_lease_refuses_before_policy_marker_or_package_start(self):
        self.subject.runner.package_lease_fd = None
        with self.assertRaises(PrerequisiteError) as raised:
            self.run_package("normal")
        self.assertEqual(raised.exception.code, "package_borrowed_lifecycle_lease_required")
        self.assert_restored()
        self.assertFalse((self.root / "apt.pid").exists())

    def test_prepared_scope_cannot_execute_before_keeper_ready_authorization(self):
        runner = self.subject.runner
        identity = runner.package_identity()
        gate = self.root / "unarmed-gate.json"
        prepared = runner.prepare_package(identity, gate_path=gate, timeout=3)
        try:
            with self.assertRaisesRegex(InstallError, "package_lease_keeper_required"):
                runner.run_package(prepared, fake_argv(self.root, "normal"), gate_path=gate, timeout=3)
            self.assertFalse(gate.exists())
            self.assertFalse((self.root / "apt.pid").exists())
            self.assertEqual(self.scope.inspect(prepared)["state"], "live")
        finally:
            self.scope.abort(prepared)
            wait_until(lambda: self.scope.inspect(prepared)["state"] == "quiescent")
        self.assert_restored()

    def test_sigkill_during_ready_handshake_retains_borrowed_lease_without_opening_gate(self):
        os.close(self.fd)
        self.fd = None
        process = subprocess.Popen([sys.executable, HERE, "installer", str(self.root), "handshake", "1.5"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True)
        self.installers.append(process)
        wait_until(lambda: (self.root / "keeper-before-ready").exists(), timeout=5)
        self.assertEqual(self.policy.read_bytes(), SENTINEL)
        process.kill()
        self.assertEqual(process.wait(timeout=3), -signal.SIGKILL)
        (self.root / "keeper-release-ready").touch()
        time.sleep(.2)
        self.assertFalse(self.lock_available(), "BrokenPipe discarded the borrowed lifecycle lease")
        self.assertFalse((self.root / "apt.pid").exists(), "gate opened without READY acknowledgment")
        with self.assertRaises((PrerequisiteError, InstallError)):
            self.recover()
        self.assertEqual(self.policy.read_bytes(), SENTINEL)
        wait_until(self.lock_available, timeout=6)
        self.recover()
        self.assert_restored()
        self.assertFalse((self.root / "apt.pid").exists())

    def test_normal_completion_restores_exact_existing_policy_after_child_exit(self):
        self.run_package("normal")
        self.assertTrue((self.root / "child-exited").exists())
        self.assert_restored()

    def test_nonzero_parent_exit_restores_only_after_child_quiescence(self):
        with self.assertRaises((PrerequisiteError, InstallError)):
            self.run_package("nonzero")
        self.assertTrue((self.root / "child-exited").exists())
        self.assert_restored()

    def test_timeout_direct_parent_dies_stubborn_descendant_remains_inhibited_until_killed(self):
        start = time.monotonic()
        with self.assertRaises((PrerequisiteError, InstallError)):
            self.run_package("stubborn", timeout=.6)
        self.assertLess(time.monotonic() - start, 6)
        self.assertTrue((self.root / "stubborn-after-term").exists())
        self.assertEqual((self.root / "apt-parent-exited").read_text(), str(-signal.SIGTERM))
        self.assert_restored()

    def test_sigkill_installer_retains_same_lease_and_live_recovery_refuses_then_restores(self):
        process = self.start_crashing_installer(timeout=2)
        heartbeat = (self.root / "heartbeat").read_text()
        process.kill()
        self.assertEqual(process.wait(timeout=3), -signal.SIGKILL)
        wait_until(lambda: (self.root / "heartbeat").read_text() != heartbeat)
        self.assertFalse(self.lock_available(), "borrowed flock escaped on installer SIGKILL")
        before = self.marker.read_bytes()
        with self.assertRaises((PrerequisiteError, InstallError)):
            self.recover()
        self.assertEqual(self.policy.read_bytes(), SENTINEL)
        self.assertEqual(self.marker.read_bytes(), before)
        wait_until(self.lock_available, timeout=7)
        self.assertEqual(self.recover(), {"changed": True, "package_database_audited": True})
        self.assert_restored()
        self.assertEqual(self.recover(), {"changed": False})
        self.fd = os.open(self.root / "lifecycle.lock", os.O_RDWR)
        fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.subject = make_subject(self.root, self.fd, self.scope)
        self.run_package("normal")
        self.assert_restored()

    def test_graceful_interrupt_aborts_owned_group_before_recovery(self):
        process = self.start_crashing_installer(timeout=8)
        process.send_signal(signal.SIGINT)
        self.assertNotEqual(process.wait(timeout=4), 0)
        self.assertEqual(self.policy.read_bytes(), SENTINEL)
        self.assertTrue(self.marker.exists())
        wait_until(self.lock_available, timeout=6)
        self.recover()
        self.assert_restored()

    def test_no_previous_policy_removed_only_after_descendant_exit(self):
        self.policy.unlink()
        self.run_package("normal")
        self.assertTrue((self.root / "child-exited").exists())
        self.assertFalse(self.policy.exists())
        self.assertFalse(self.marker.exists())
        self.assertFalse((self.root / "child-saw-restored").exists())
        self.assertFalse(pid_is_live(int((self.root / "child.pid").read_text())))
        self.wait_keepers()

    def test_failed_inspection_keeps_policy_marker_and_lease_until_known_quiescence(self):
        process = self.start_crashing_installer(timeout=1.5)
        process.kill()
        process.wait(timeout=3)
        (self.root / "inspect-failure").touch()
        before = self.marker.read_bytes()
        with self.assertRaises((PrerequisiteError, InstallError)):
            self.recover()
        self.assertEqual(self.marker.read_bytes(), before)
        self.assertEqual(self.policy.read_bytes(), SENTINEL)
        child_pid = int((self.root / "child.pid").read_text())
        wait_until(lambda: not pid_is_live(child_pid), timeout=6)
        self.assertFalse(self.lock_available(), "unknown scope inspection released borrowed lease")
        with self.assertRaises((PrerequisiteError, InstallError)):
            self.recover()
        (self.root / "inspect-failure").unlink()
        wait_until(self.lock_available, timeout=5)
        self.recover()
        self.assert_restored()

    def test_stale_reused_identity_refuses_recovery_and_never_signals_other_process(self):
        process = self.start_crashing_installer(timeout=1.3)
        process.kill()
        process.wait(timeout=3)
        saved = json.loads(self.marker.read_text())
        wait_until(self.lock_available, timeout=6)
        unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            # Simulate an exact UUID with a different invocation plus recycled
            # persisted PID. Neither field authorizes signalling that process.
            altered = json.loads(json.dumps(saved))
            altered["transaction"]["invocation_id"] = "f" * 32
            altered["transaction"]["fixture_group"] = unrelated.pid
            self.marker.write_text(json.dumps(altered))
            before = self.marker.read_bytes()
            for _ in range(2):
                with self.assertRaises((PrerequisiteError, InstallError)):
                    self.recover()
                self.assertIsNone(unrelated.poll())
                self.assertEqual(self.marker.read_bytes(), before)
                self.assertEqual(self.policy.read_bytes(), SENTINEL)
            with self.assertRaises(InstallError):
                self.scope.abort(altered["transaction"])
            self.assertIsNone(unrelated.poll())
            self.marker.write_text(json.dumps(saved))
            self.recover()
            self.assert_restored()
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=3)

    def test_quiescent_transaction_with_incomplete_dpkg_audit_retains_inhibitor(self):
        process = self.start_crashing_installer(timeout=1.2)
        process.kill()
        process.wait(timeout=3)
        wait_until(self.lock_available, timeout=6)
        (self.root / "audit-incomplete").touch()
        before = self.marker.read_bytes()
        with self.assertRaises(PrerequisiteError) as raised:
            self.recover()
        self.assertEqual(raised.exception.code, "package_database_repair_required")
        self.assertEqual(self.marker.read_bytes(), before)
        self.assertEqual(self.policy.read_bytes(), SENTINEL)
        (self.root / "audit-incomplete").unlink()
        self.recover()
        self.assert_restored()

    def test_missing_marker_with_inhibitor_and_incomplete_identity_are_fail_closed(self):
        self.subject._ensure_directory(self.subject.state)
        self.policy.write_bytes(SENTINEL)
        with self.assertRaises(PrerequisiteError) as raised:
            self.recover()
        self.assertEqual(raised.exception.code, "package_ownership_marker_missing")
        self.assertEqual(self.policy.read_bytes(), SENTINEL)
        for phase in ("preparing", "owned"):
            with self.subTest(phase=phase):
                self.marker.write_text(json.dumps({"schema_version": 2, "existed": True,
                    "original_hex": self.original.hex(), "mode": 0o751,
                    "phase": phase, "transaction": {}}))
                self.marker.chmod(0o600)
                before = self.marker.read_bytes()
                with self.assertRaises((PrerequisiteError, InstallError)):
                    self.recover()
                self.assertEqual(self.marker.read_bytes(), before)
                self.assertEqual(self.policy.read_bytes(), SENTINEL)

    def test_missing_legacy_ownership_is_repeatably_fail_closed(self):
        self.subject._ensure_directory(self.subject.state)
        self.policy.write_bytes(SENTINEL)
        self.marker.write_text(json.dumps({"schema_version": 1, "existed": True,
            "original_hex": self.original.hex(), "mode": 0o751}))
        self.marker.chmod(0o600)
        before = self.marker.read_bytes()
        for _ in range(2):
            with self.assertRaises((PrerequisiteError, InstallError)):
                self.recover()
            self.assertEqual(self.marker.read_bytes(), before)
            self.assertEqual(self.policy.read_bytes(), SENTINEL)


if __name__ == "__main__":
    unittest.main()
