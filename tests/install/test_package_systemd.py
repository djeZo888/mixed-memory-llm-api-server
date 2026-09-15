"""Mocked systemd adapter checks; temporary files are NOT Linux cgroup evidence.

No systemctl, systemd-run, apt, host policy, or kernel cgroup operation runs here.
The independent POSIX package-process fixtures live in test_package_processes.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
from install.core import InstallError, Runner, SystemdPackageScope, _package_worker, digest


class SystemdAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".package-systemd-", dir=REPO)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cgroup = self.root / "cgroup"
        self.cgroup.mkdir()
        (self.cgroup / "cgroup.events").write_text("populated 1\nfrozen 0\n")
        (self.cgroup / "cgroup.kill").write_bytes(b"")
        self.gate = self.root / "execute.json"
        self.boot = "10000000-0000-4000-8000-000000000001"
        self.boot_patch = mock.patch.object(SystemdPackageScope, "_boot_id", return_value=self.boot)
        self.boot_patch.start()
        self.addCleanup(self.boot_patch.stop)
        # Any unmocked command is a test bug, never a host operation.
        self.spawn = mock.patch("install.core.subprocess.run", side_effect=AssertionError("unmocked host command"))
        self.spawn.start()
        self.addCleanup(self.spawn.stop)
        self.scope = SystemdPackageScope()
        self.identity = self.scope.new_identity()
        self.identity.update(invocation_id="1" * 32,
                             cgroup="/system.slice/" + self.identity["unit"],
                             cgroup_inode=self.cgroup.stat().st_ino)
        self.rows = {
            "Id": self.identity["unit"],
            "Description": "local-ai package " + self.identity["token"],
            "LoadState": "loaded", "ActiveState": "active", "SubState": "running",
            "InvocationID": self.identity["invocation_id"], "ControlGroup": self.identity["cgroup"],
            "MainPID": "4242", "ExecMainPID": "4242", "ExecMainCode": "0",
            "ExecMainStatus": "0", "Result": "success", "Type": "exec",
            "ExitType": "cgroup", "RemainAfterExit": "yes", "KillMode": "control-group",
            "SendSIGKILL": "yes", "Restart": "no", "CollectMode": "inactive",
        }

    def raw(self, rows=None):
        return "".join(key + "=" + value + "\n" for key, value in (rows or self.rows).items())

    def cgroup_fd(self, _identity):
        return os.open(self.cgroup, os.O_RDONLY | os.O_DIRECTORY)

    def terminal(self, *, success=True):
        self.rows.update(ActiveState="active" if success else "failed",
                         SubState="exited" if success else "failed", MainPID="0",
                         ExecMainCode="1" if success else "2", ExecMainStatus="0" if success else "9",
                         Result="success" if success else "timeout")
        (self.cgroup / "cgroup.events").write_text("populated 0\nfrozen 0\n")

    def observe(self):
        with mock.patch.object(self.scope, "_command", return_value=self.raw()), \
             mock.patch.object(self.scope, "_cgroup", side_effect=self.cgroup_fd):
            return self.scope.inspect(self.identity)

    def test_identity_is_unique_and_never_a_shared_service(self):
        next_identity = self.scope.new_identity()
        self.assertNotEqual(self.identity["token"], next_identity["token"])
        self.assertRegex(next_identity["token"], r"^[0-9a-f]{32}$")
        self.assertEqual(next_identity["unit"], "local-ai-package-" + next_identity["token"] + ".service")
        self.assertEqual(next_identity["boot_id"], self.boot)

    def test_missing_stale_or_reused_persisted_identity_refuses_before_manager(self):
        changed = [None, {}, {**self.identity, "unit": "docker.service"},
                   {**self.identity, "token": "../unrelated"},
                   {**self.identity, "boot_id": "20000000-0000-4000-8000-000000000002"},
                   {**self.identity, "invocation_id": ""},
                   {**self.identity, "cgroup": "/system.slice/docker.service"},
                   {**self.identity, "cgroup_inode": True},
                   {**self.identity, "cgroup_inode": 0}]
        with mock.patch.object(self.scope, "_command") as command:
            for identity in changed:
                with self.subTest(identity=identity), self.assertRaises(InstallError):
                    self.scope.inspect(identity)
            command.assert_not_called()

    def test_manager_identity_and_ownership_properties_are_required(self):
        wrong = {"Id": "docker.service", "Description": "another transaction",
                 "LoadState": "not-found", "InvocationID": "2" * 32,
                 "Type": "oneshot", "ExitType": "main", "RemainAfterExit": "no",
                 "KillMode": "process", "SendSIGKILL": "no", "Restart": "always",
                 "CollectMode": "inactive-or-failed"}
        for key, value in wrong.items():
            changed = {**self.rows, key: value}
            with self.subTest(key=key), mock.patch.object(self.scope, "_command", return_value=self.raw(changed)), \
                 self.assertRaises(InstallError):
                self.scope._show(self.identity)

    def test_incomplete_duplicate_and_malformed_manager_output_is_unknown(self):
        missing = {key: value for key, value in self.rows.items() if key != "InvocationID"}
        for raw in ("", self.raw(missing), self.raw() + "Id=other.service\n", "invalid line\n"):
            with self.subTest(raw=raw), mock.patch.object(self.scope, "_command", return_value=raw), \
                 self.assertRaises(InstallError):
                self.scope._show(self.identity)

    def test_manager_error_timeout_and_output_are_sanitized(self):
        effects = [OSError("fixture_private_sentinel"),
                   subprocess.TimeoutExpired(["fixture_private_sentinel"], 1),
                   subprocess.CompletedProcess([], 1, "fixture_private_sentinel")]
        for effect in effects:
            with self.subTest(effect=type(effect).__name__), mock.patch("install.core.subprocess.run") as command:
                if isinstance(effect, BaseException):
                    command.side_effect = effect
                else:
                    command.return_value = effect
                with self.assertRaises(InstallError) as caught:
                    self.scope._show(self.identity)
                self.assertNotIn("fixture_private_sentinel", str(caught.exception))
                argv = command.call_args.args[0]
                self.assertEqual(argv[0:3], ["/usr/bin/systemctl", "show", "--no-pager"])
                self.assertIn("--all", argv)  # ControlGroup can legitimately become empty.
                self.assertEqual(argv[-2:], ["--", self.identity["unit"]])
                self.assertNotIn("shell", command.call_args.kwargs)
                self.assertEqual(command.call_args.kwargs["stderr"], subprocess.DEVNULL)

    def test_live_descendants_override_main_exit_and_failed_unit(self):
        self.terminal(success=False)
        (self.cgroup / "cgroup.events").write_text("populated 1\nfrozen 0\n")
        self.assertEqual(self.observe(), {"state": "live", "successful": False})

    def test_exact_empty_success_uses_current_main_pid_not_historical_exec_pid(self):
        self.terminal()
        self.assertEqual(self.rows["ExecMainPID"], "4242")
        self.assertEqual(self.observe(), {"state": "quiescent", "successful": True})

    def test_exact_empty_failed_unit_is_quiescent_but_never_successful(self):
        self.terminal(success=False)
        self.assertEqual(self.observe(), {"state": "quiescent", "successful": False})

    def test_missing_cgroup_requires_exact_retained_terminal_identity(self):
        with mock.patch.object(self.scope, "_command", side_effect=lambda _argv: self.raw()), \
             mock.patch.object(self.scope, "_cgroup", return_value=None):
            with self.assertRaises(InstallError):
                self.scope.inspect(self.identity)
            self.terminal()
            self.rows["ControlGroup"] = ""
            self.assertEqual(self.scope.inspect(self.identity), {"state": "quiescent", "successful": True})
            self.rows["InvocationID"] = "3" * 32
            with self.assertRaises(InstallError):
                self.scope.inspect(self.identity)

    def test_empty_cgroup_running_or_terminating_unit_remains_unknown(self):
        (self.cgroup / "cgroup.events").write_text("populated 0\n")
        for active, sub in (("active", "running"), ("activating", "start"), ("deactivating", "stop-sigkill")):
            self.rows.update(ActiveState=active, SubState=sub)
            with self.subTest(active=active), self.assertRaises(InstallError):
                self.observe()

    def test_changing_manager_state_retries_instead_of_approving_quiescence(self):
        before = self.raw()
        self.terminal()
        with mock.patch.object(self.scope, "_command", side_effect=[before, self.raw()]), \
             mock.patch.object(self.scope, "_cgroup", side_effect=self.cgroup_fd), \
             self.assertRaisesRegex(InstallError, "state_changing"):
            self.scope.inspect(self.identity)

    def test_missing_malformed_or_unreadable_cgroup_population_fails_closed(self):
        for content in ("", "frozen 0\n", "populated unknown\n", "not a valid row\n",
                        "populated 1\npopulated 0\nfrozen 0\n"):
            (self.cgroup / "cgroup.events").write_text(content)
            with self.subTest(content=content), self.assertRaises(InstallError):
                self.observe()
        (self.cgroup / "cgroup.events").unlink()
        with self.assertRaises(InstallError):
            self.observe()

    def test_reused_cgroup_inode_is_refused_and_open_descriptor_closed(self):
        real_open = os.open
        descriptor = real_open(self.cgroup, os.O_RDONLY | os.O_DIRECTORY)
        stale = {**self.identity, "cgroup_inode": self.identity["cgroup_inode"] + 1}
        with mock.patch("install.core.os.open", return_value=descriptor), \
             self.assertRaisesRegex(InstallError, "cgroup_identity_changed"):
            self.scope._cgroup(stale)
        with self.assertRaises(OSError):
            os.fstat(descriptor)

    def test_prepare_starts_only_gate_worker_in_retained_bounded_service(self):
        commands = []
        real_open = os.open

        def command(argv):
            commands.append(argv)
            return "" if argv[0].endswith("systemd-run") else self.raw()

        def redirect(path, flags, *args, **kwargs):
            if str(path) == "/sys/fs/cgroup" + self.identity["cgroup"]:
                return real_open(self.cgroup, flags, *args, **kwargs)
            return real_open(path, flags, *args, **kwargs)

        identity = {key: value for key, value in self.identity.items()
                    if key not in {"invocation_id", "cgroup", "cgroup_inode"}}
        with mock.patch.object(self.scope, "_command", side_effect=command), \
             mock.patch("install.core.private_path"), mock.patch("install.core.Path.is_file", return_value=True), \
             mock.patch("install.core.os.open", side_effect=redirect):
            prepared = self.scope.prepare(identity, gate_path=self.gate, timeout=42)
        self.assertEqual(prepared, self.identity)
        launch = commands[0]
        for property_value in ("Type=exec", "ExitType=cgroup", "RemainAfterExit=yes",
                               "KillMode=control-group", "SendSIGKILL=yes", "Restart=no",
                               "CollectMode=inactive", "RuntimeMaxSec=42", "TimeoutStopSec=5", "Delegate=no"):
            self.assertIn("--property=" + property_value, launch)
        self.assertIn("--unit=" + self.identity["unit"], launch)
        self.assertNotIn("--collect", launch)
        self.assertNotIn("apt-get", launch)
        self.assertEqual(launch[-2:], ["--package-worker", str(self.gate)])
        self.assertFalse(self.gate.exists())
        self.assertEqual((self.cgroup / "cgroup.kill").read_bytes(), b"")

    def test_prepare_requires_cgroup_v2_and_valid_deadline_before_manager(self):
        with mock.patch.object(self.scope, "_command") as command, mock.patch("install.core.private_path"), \
             mock.patch("install.core.Path.is_file", return_value=False):
            for timeout in (0, -1, True, float("nan"), float("inf"), 86401):
                with self.subTest(timeout=timeout), self.assertRaises(InstallError):
                    self.scope.prepare(self.identity, gate_path=self.gate, timeout=timeout)
            with self.assertRaisesRegex(InstallError, "unified_cgroup_v2"):
                self.scope.prepare(self.identity, gate_path=self.gate, timeout=5)
            command.assert_not_called()

    def test_execute_preserves_exact_identity_and_rejects_loader_environment(self):
        with mock.patch.object(self.scope, "inspect", return_value={"state": "live"}), \
             mock.patch("install.core.atomic_json") as save:
            for env in ({"PATH": "/untrusted"}, {"LD_PRELOAD": "bad"}, {"PYTHONPATH": "bad"}, {"TMP": "bad\0value"}):
                with self.subTest(env=env), self.assertRaisesRegex(InstallError, "invalid_package_environment"):
                    self.scope.execute(self.identity, ["apt-get", "install", "fixture=1"], gate_path=self.gate, env=env)
            save.assert_not_called()
            self.scope.execute(self.identity, ["apt-get", "install", "fixture=1"], gate_path=self.gate,
                               env={"DEBIAN_FRONTEND": "noninteractive"})
            payload = save.call_args.args[1]
            self.assertEqual(payload["identity"], self.identity)
            self.assertEqual(payload["argv"], ["apt-get", "install", "fixture=1"])
            self.assertEqual(payload["env"]["PATH"], "/usr/sbin:/usr/bin:/sbin:/bin")

    def test_execute_never_reuses_a_gate_or_launches_nonpackage_command(self):
        with mock.patch.object(self.scope, "inspect", return_value={"state": "live"}), \
             mock.patch("install.core.atomic_json") as save:
            for argv in ([], "apt-get install", ["/usr/bin/apt-get"], ["sh", "-c", "apt-get install"],
                         ["apt-get", 5], ["apt-get", "bad\0value"]):
                with self.subTest(argv=argv), self.assertRaises(InstallError):
                    self.scope.execute(self.identity, argv, gate_path=self.gate)
            self.gate.write_text("already armed")
            with self.assertRaisesRegex(InstallError, "gate_already_exists"):
                self.scope.execute(self.identity, ["apt-get", "install", "fixture=1"], gate_path=self.gate)
            save.assert_not_called()

    def test_worker_refuses_stale_invocation_before_exec(self):
        self.gate.write_text("protected gate fixture is mocked below")
        gate = {"identity": self.identity, "argv": ["apt-get", "install", "fixture=1"], "env": {}}
        with mock.patch("install.core.read_private_json", return_value=gate), \
             mock.patch.dict(os.environ, {"INVOCATION_ID": "f" * 32}), \
             mock.patch("install.core.os.execve") as execute, self.assertRaises(InstallError):
            _package_worker(self.gate)
        execute.assert_not_called()

    def test_runner_never_treats_benign_package_tokens_as_mutation_authority(self):
        commands = [["apt-get", "install", "update"],
                    ["apt-get", "-s", "-o", "APT::Get::Simulate=false", "install", "fixture"],
                    ["apt-get", "--download-only", "-o", "APT::Get::Download-Only=false", "install", "fixture"],
                    ["apt-get", "install", "fixture"], ["/usr/bin/apt-get", "install", "fixture"],
                    ["dpkg", "--configure", "--pending"], ["dpkg", "--audit", "--configure", "--pending"]]
        with mock.patch("install.core.subprocess.run") as command:
            for argv in commands:
                with self.subTest(argv=argv), self.assertRaises(InstallError):
                    Runner(writable=True).run(argv)
            command.assert_not_called()

    def test_runner_retries_normal_manager_transition_without_aborting_package(self):
        runner = Runner(writable=True, package_lease_fd=17, package_scope=self.scope)
        # Isolate the monitor decision here; real lease ownership uses the POSIX fixtures.
        runner._package_lease_identities.add(digest(self.identity))
        with mock.patch.object(runner, "_validate_package_lease"), \
             mock.patch.object(self.scope, "execute"), \
             mock.patch.object(self.scope, "inspect", side_effect=[InstallError("package_scope_state_changing_retry"),
                                                               {"state": "quiescent", "successful": True}]), \
             mock.patch.object(self.scope, "abort") as abort, mock.patch("install.core.time.sleep"):
            self.assertEqual(runner.run_package(self.identity, ["apt-get", "install", "fixture=1"],
                                               gate_path=self.gate, timeout=5), "")
        abort.assert_not_called()

    def test_runner_preparation_requires_writable_borrowed_lease_before_scope_start(self):
        for runner in (Runner(package_scope=self.scope), Runner(writable=True, package_scope=self.scope)):
            with self.subTest(writable=runner.writable), mock.patch.object(self.scope, "prepare") as prepare, \
                 self.assertRaisesRegex(InstallError, "borrowed_lifecycle_lease_required"):
                runner.prepare_package(self.identity, gate_path=self.gate, timeout=5)
            prepare.assert_not_called()

    def test_runner_gate_requires_ready_keeper_for_this_exact_identity(self):
        runner = Runner(writable=True, package_lease_fd=17, package_scope=self.scope)
        runner._package_lease_identities.add(digest({**self.identity, "invocation_id": "2" * 32}))
        with mock.patch.object(runner, "_validate_package_lease"), \
             mock.patch.object(self.scope, "execute") as execute, \
             self.assertRaisesRegex(InstallError, "keeper_required"):
            runner.run_package(self.identity, ["apt-get", "install", "fixture=1"], gate_path=self.gate)
        execute.assert_not_called()

    def test_abort_unknown_or_reused_identity_never_opens_kill_target(self):
        with mock.patch.object(self.scope, "inspect", side_effect=InstallError("package_scope_identity_missing_or_stale")), \
             mock.patch.object(self.scope, "_cgroup") as cgroup, self.assertRaises(InstallError):
            self.scope.abort(self.identity)
        cgroup.assert_not_called()
        self.assertEqual((self.cgroup / "cgroup.kill").read_bytes(), b"")

    def test_abort_revalidates_invocation_before_any_kill_write(self):
        changed = {**self.rows, "InvocationID": "2" * 32}
        with mock.patch.object(self.scope, "inspect", return_value={"state": "live"}), \
             mock.patch.object(self.scope, "_cgroup", side_effect=self.cgroup_fd), \
             mock.patch.object(self.scope, "_command", return_value=self.raw(changed)), \
             self.assertRaises(InstallError):
            self.scope.abort(self.identity)
        self.assertEqual((self.cgroup / "cgroup.kill").read_bytes(), b"")

    def test_abort_pinned_directory_cannot_retarget_replacement_path(self):
        moved = self.root / "owned-old-cgroup"

        def pin_then_replace(_identity):
            descriptor = os.open(self.cgroup, os.O_RDONLY | os.O_DIRECTORY)
            self.cgroup.rename(moved)
            self.cgroup.mkdir()
            (self.cgroup / "cgroup.kill").write_bytes(b"unrelated")
            return descriptor

        with mock.patch.object(self.scope, "inspect", side_effect=[{"state": "live"}, {"state": "quiescent"}]), \
             mock.patch.object(self.scope, "_cgroup", side_effect=pin_then_replace), \
             mock.patch.object(self.scope, "_command", return_value=self.raw()):
            self.scope.abort(self.identity)
        self.assertEqual((moved / "cgroup.kill").read_bytes(), b"1")
        self.assertEqual((self.cgroup / "cgroup.kill").read_bytes(), b"unrelated")

    def test_abort_quiescent_scope_never_signals(self):
        with mock.patch.object(self.scope, "inspect", return_value={"state": "quiescent"}), \
             mock.patch.object(self.scope, "_cgroup") as cgroup:
            self.scope.abort(self.identity)
        cgroup.assert_not_called()

    def test_abort_retains_live_state_when_kill_does_not_establish_quiescence(self):
        with mock.patch.object(self.scope, "inspect", return_value={"state": "live"}), \
             mock.patch.object(self.scope, "_cgroup", side_effect=self.cgroup_fd), \
             mock.patch.object(self.scope, "_command", return_value=self.raw()), \
             mock.patch("install.core.time.monotonic", side_effect=[0, 1, 11]), \
             mock.patch("install.core.time.sleep"), \
             self.assertRaisesRegex(InstallError, "still_live_recovery_required"):
            self.scope.abort(self.identity)
        self.assertEqual((self.cgroup / "cgroup.kill").read_bytes(), b"1")


if __name__ == "__main__":
    unittest.main()
