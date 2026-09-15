"""Installer safety tests. All writable effects are confined to a repo fixture."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
from install.core import InstallError, Runner, State, atomic_json, exclusive, private_path, read_private_json


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".install-test-", dir=REPO)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.uid = os.geteuid()
        self.path = self.root / "state.json"
        self.guard = mock.Mock()

    def state(self, config=None, lock="lock", source="source"):
        return State(self.path, config or {"profile": "fixture"}, lock, source, self.guard, uid=self.uid)

    def read(self):
        return read_private_json(self.path, uid=self.uid)


class StateTests(Fixture):
    def test_constructor_and_verify_only_do_not_write(self):
        state = self.state()
        action = mock.Mock()
        self.assertEqual(state.run([("service", lambda: False, action)], verify_only=True),
                         [{"stage": "service", "status": "pending"}])
        action.assert_not_called()
        self.assertFalse(self.path.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_stages_are_ordered_and_postconditions_required(self):
        events, done = [], set()
        def stage(name):
            def check():
                events.append("check:" + name)
                return name in done
            def action():
                events.append("apply:" + name)
                done.add(name)
            return name, check, action
        result = self.state().run([stage("storage"), stage("base"), stage("driver")])
        self.assertEqual(events, ["check:storage", "apply:storage", "check:storage", "check:base",
                                  "apply:base", "check:base", "check:driver", "apply:driver", "check:driver"])
        self.assertTrue(all(row["status"] == "complete" for row in result))
        with self.assertRaisesRegex(InstallError, "stage_postcondition_failed"):
            self.state().run([("service", lambda: False, lambda: None)])
        self.assertEqual(self.read()["stages"]["service"]["status"], "failed")

    def test_second_run_rechecks_without_any_state_write(self):
        done = set()
        self.state().run([("base", lambda: "base" in done, lambda: done.add("base"))])
        before, mtime = self.path.read_bytes(), self.path.stat().st_mtime_ns
        check, action = mock.Mock(return_value=True), mock.Mock()
        result = self.state().run([("base", check, action)])
        self.assertEqual(result, [{"stage": "base", "status": "verified_noop"}])
        check.assert_called_once_with()
        action.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.path.stat().st_mtime_ns, mtime)

    def test_completed_marker_does_not_override_failed_postcondition(self):
        self.state().run([("base", lambda: True, lambda: None)])
        checks = mock.Mock(side_effect=[False, True])
        action = mock.Mock()
        self.state().run([("base", checks, action)])
        action.assert_called_once_with()
        self.assertEqual(checks.call_count, 2)

    def test_process_interruption_preserves_partial_then_resumes(self):
        partial = self.root / "artifact.partial"
        def interrupted():
            partial.write_bytes(b"first half")
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.state().run([("models", lambda: False, interrupted)])
        self.assertEqual(self.read()["stages"]["models"]["status"], "running")
        def finish():
            self.assertEqual(partial.read_bytes(), b"first half")
            partial.write_bytes(partial.read_bytes() + b" second half")
        self.state().run([("models", lambda: partial.read_bytes() == b"first half second half", finish)])
        self.assertEqual(self.read()["stages"]["models"]["attempt"], 2)

    def test_failure_redacts_credential_and_preserves_existing_secret(self):
        credential = self.root / "api-key"
        credential.write_bytes(b"fixture_private_sentinel")
        credential.chmod(0o600)
        def fail():
            raise RuntimeError("failed command with fixture_private_sentinel")
        with self.assertRaises(RuntimeError):
            self.state().run([("service", lambda: False, fail)])
        self.assertNotIn(b"fixture_private_sentinel", self.path.read_bytes())
        self.assertEqual(self.read()["stages"]["service"]["failure"], "stage_failed")
        self.assertEqual(credential.read_bytes(), b"fixture_private_sentinel")

    def test_mount_loss_does_not_write_failure_or_later_stage(self):
        present = True
        def guard():
            if not present:
                raise InstallError("data_mount_missing")
        self.guard = guard
        captured = {}
        def lose_mount():
            nonlocal present
            captured["bytes"] = self.path.read_bytes()
            present = False
        later = mock.Mock()
        with self.assertRaisesRegex(InstallError, "data_mount_missing"):
            self.state().run([("base", lambda: False, lose_mount), ("driver", lambda: False, later)])
        later.assert_not_called()
        self.assertEqual(self.path.read_bytes(), captured["bytes"])
        self.assertEqual(json.loads(self.path.read_bytes())["stages"]["base"]["status"], "running")

    def test_changed_config_lock_or_source_rejected(self):
        self.state().run([("base", lambda: True, lambda: None)])
        for kwargs in ({"config": {"profile": "other"}}, {"lock": "changed"}, {"source": "changed"}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(InstallError, "state_config_lock_or_source_changed"):
                self.state(**kwargs)

    def test_malformed_stage_records_and_installation_id_rejected(self):
        self.state().run([("base", lambda: True, lambda: None)])
        valid = self.read()
        changes = [lambda x: x.update(installation_id="not-a-uuid"),
                   lambda x: x.update(stages=[]),
                   lambda x: x["stages"].update(base="complete"),
                   lambda x: x["stages"]["base"].update(status="whatever"),
                   lambda x: x["stages"]["base"].update(attempt=True),
                   lambda x: x["stages"]["base"].update(config_hash="different"),
                   lambda x: x["stages"]["base"].update(installation_id="different"),
                   lambda x: x["stages"]["base"].update(finished="bad timestamp")]
        for change in changes:
            broken = copy.deepcopy(valid)
            change(broken)
            atomic_json(self.path, broken, uid=self.uid)
            with self.assertRaisesRegex(InstallError, "invalid_stage_state"):
                self.state()

    def test_reboot_exception_records_checkpoint_and_resume_rechecks(self):
        class Reboot(InstallError):
            exit_code = 75
            checkpoint = {"boot_id": "10000000-0000-4000-8000-000000000001", "secret": "fixture_private_sentinel",
                          "reason": "raw credential: fixture_private_sentinel", "required_driver": "fixture_private_sentinel",
                          "secure_boot": "fixture_private_sentinel"}
        def action():
            raise Reboot("reboot_required")
        with self.assertRaises(Reboot):
            self.state().run([("driver", lambda: False, action)])
        row = self.read()["stages"]["driver"]
        self.assertEqual(row["status"], "reboot_required")
        self.assertEqual(row["checkpoint"], {"boot_id": Reboot.checkpoint["boot_id"]})
        self.assertNotIn(b"fixture_private_sentinel", self.path.read_bytes())
        check, repeated = mock.Mock(return_value=True), mock.Mock()
        self.state().run([("driver", check, repeated)])
        check.assert_called_once_with()
        repeated.assert_not_called()
        self.assertEqual(self.read()["stages"]["driver"]["status"], "complete")


class ProtectedFilesTests(Fixture):
    def test_root_ancestors_allowed_and_leaf_owner_exact(self):
        atomic_json(self.path, {"value": 1}, uid=self.uid)
        self.assertEqual(self.read(), {"value": 1})
        with self.assertRaises(InstallError):
            private_path(self.path, uid=self.uid + 1)

    def test_symlink_hardlink_and_public_state_rejected(self):
        atomic_json(self.path, {"value": 1}, uid=self.uid)
        alias = self.root / "alias.json"
        alias.symlink_to(self.path)
        with self.assertRaises(InstallError):
            read_private_json(alias, uid=self.uid)
        alias.unlink()
        os.link(self.path, alias)
        with self.assertRaises(InstallError):
            self.read()
        alias.unlink()
        self.path.chmod(0o644)
        with self.assertRaises(InstallError):
            self.read()

    def test_atomic_failure_preserves_previous_state_and_cleans_temporary(self):
        atomic_json(self.path, {"version": 1}, uid=self.uid)
        with mock.patch("install.core.os.replace", side_effect=OSError("fixture")):
            with self.assertRaises(OSError):
                atomic_json(self.path, {"version": 2}, uid=self.uid)
        self.assertEqual(self.read(), {"version": 1})
        self.assertEqual(list(self.root.iterdir()), [self.path])

    def test_lock_rejects_symlink_ancestry_before_creating_directories(self):
        destination = self.root / "destination"
        destination.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(destination, target_is_directory=True)
        with self.assertRaises(InstallError):
            with exclusive(alias / "new" / "lock", uid=self.uid):
                self.fail("unsafe lock was acquired")
        self.assertEqual(list(destination.iterdir()), [])

    def test_concurrent_process_owner_rejected_then_lock_released(self):
        lock = self.root / "lifecycle.lock"
        script = '''import os, sys
sys.path.insert(0, sys.argv[1])
from install.core import exclusive, InstallError
try:
    with exclusive(sys.argv[2], uid=os.geteuid()):
        print("acquired")
except InstallError as exc:
    print(exc.code)
    sys.exit(23)
'''
        def child():
            return subprocess.run([sys.executable, "-B", "-c", script, str(REPO / "scripts"), str(lock)],
                                  text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        with exclusive(lock, uid=self.uid):
            result = child()
            self.assertEqual(result.returncode, 23, result.stderr)
            self.assertEqual(result.stdout.strip(), "installer_or_lifecycle_owner_active")
        result = child()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "acquired")


class CommandBoundaryTests(unittest.TestCase):
    def test_mutating_and_disguised_readonly_commands_never_spawn(self):
        rejected = [[], "systemctl restart docker", ["systemctl", "restart", "docker"],
                    ["systemctl", "show", "--root=/tmp/other", "docker"], ["mount", "/dev/test", "/data"],
                    ["fuser", "-k", "/data"], ["ss", "-K"], ["mokutil", "--reset"],
                    ["apt-cache", "gencaches"], ["blkid", "-w", "/tmp/cache"],
                    ["wipefs", "--all", "/dev/test"], ["wipefs", "--no-act", "--all", "/dev/test"],
                    ["dpkg", "--print-architecture", "--install", "payload.deb"],
                    ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader", "-pm", "1"],
                    ["/tmp/ss", "-H", "-ltn"], ["cat", "/etc/shadow"], ["dpkg-query", "-W", "--control-list", "pkg"]]
        with mock.patch("install.core.subprocess.run") as spawn:
            for argv in rejected:
                with self.subTest(argv=argv), self.assertRaises(InstallError):
                    Runner().run(argv)
            spawn.assert_not_called()

    def test_reviewed_queries_are_allowed_without_inherited_credentials(self):
        commands = [["dpkg", "--print-architecture"], ["uname", "-r"], ["id", "-u"],
                    ["cat", "/proc/sys/kernel/random/boot_id"], ["cat", "/sys/module/nvidia/version"],
                    ["mokutil", "--sb-state"], ["modinfo", "-F", "version", "nvidia"],
                    ["getent", "ahosts", "snapshot.ubuntu.com"], ["ss", "-H", "-ltn"],
                    ["df", "-B1", "--output=avail", "/data"], ["df", "--output=avail", "--block-size=1", "/"],
                    ["dpkg-query", "-W", "-f=${Status}\t${Version}", "python3-venv"],
                    ["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\n", "*nvidia*", "linux-image-*"],
                    ["nvidia-smi", "--query-gpu=driver_version,pci.bus_id", "--format=csv,noheader,nounits"],
                    ["findmnt", "--json", "--output", "TARGET,SOURCE,UUID,FSTYPE,OPTIONS,MAJ:MIN", "--target", "/data"],
                    ["wipefs", "--no-act", "--json", "--output", "DEVICE,OFFSET,TYPE,UUID,LABEL", "/dev/nvme1n1"]]
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "fixture_private_sentinel", "LD_PRELOAD": "bad"}), \
             mock.patch("install.core.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "observed")) as spawn:
            for argv in commands:
                self.assertEqual(Runner().run(argv), "observed")
                kwargs = spawn.call_args.kwargs
                self.assertNotIn("OPENAI_API_KEY", kwargs["env"])
                self.assertNotIn("LD_PRELOAD", kwargs["env"])
                self.assertNotIn("shell", kwargs)
                self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)

    def test_readonly_environment_cannot_replace_executable_search_or_loader(self):
        with mock.patch("install.core.subprocess.run") as spawn:
            for env in ({"PATH": "/tmp"}, {"LD_PRELOAD": "fixture"}, {"PYTHONPATH": "/tmp"}):
                with self.assertRaisesRegex(InstallError, "read_only_command_boundary"):
                    Runner().run(["id", "-u"], env=env)
            spawn.assert_not_called()

    def test_failed_command_or_timeout_never_exposes_argv_output(self):
        for effect in [subprocess.CompletedProcess([], 1, "fixture_private_sentinel"),
                       subprocess.TimeoutExpired(["fixture_private_sentinel"], 1, output="fixture_private_sentinel")]:
            with mock.patch("install.core.subprocess.run") as spawn:
                if isinstance(effect, Exception):
                    spawn.side_effect = effect
                else:
                    spawn.return_value = effect
                with self.assertRaises(InstallError) as caught:
                    Runner(writable=True).run(["fake", "fixture_private_sentinel"])
                self.assertNotIn("fixture_private_sentinel", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
