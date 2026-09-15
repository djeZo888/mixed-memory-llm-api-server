"""Synthetic command-boundary tests; no host package, driver or service changes."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("installer_prerequisites", ROOT / "scripts/install/prerequisites.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeRunner:
    def __init__(self, lock):
        self.lock = lock
        self.calls = []
        self.installed = {}
        self.simulation = "Inst base-tool (1.0 Ubuntu [amd64])\n"
        self.boot = "00000000-0000-0000-0000-000000000001"
        self.gpu = False
        self.module = "595.71.05"
        self.modinfo = "595.71.05"
        self.secure_boot = "SecureBoot disabled"
        self.root_free = 20 * module.GIB
        self.data_free = 100 * module.GIB
        self.uid = "0"
        self.missing = False
        self.fail_install = False
        self.skip_postcondition = False
        self.downloaded = False
        self.package_status = {"state": "quiescent", "successful": True}

    # Synthetic ownership adapter only. Real process behavior is covered in
    # test_package_processes; systemd semantics in test_package_systemd.
    def package_identity(self):
        return {"kind": "synthetic", "token": "owned-fixture"}

    def prepare_package(self, identity, *, gate_path, timeout):
        return identity

    def hold_package_lease(self, identity):
        pass

    def inspect_package(self, identity):
        if identity != self.package_identity():
            raise RuntimeError("unknown fixture transaction")
        return self.package_status

    def run_package(self, identity, argv, *, gate_path, timeout=120, env=None):
        return self.run(argv, timeout=timeout, env=env)

    def run(self, argv, timeout=60, env=None):
        self.calls.append((argv, env))
        command = argv[0]
        if command == "id":
            return self.uid
        if command == "df":
            return "Avail\n" + str(self.root_free if argv[-1] == "/" else self.data_free)
        if command == "dpkg" and argv[1:] == ["--audit"]:
            return ""
        if command == "dpkg-query":
            if "${binary:Package}" in argv[3]:
                return "nvidia-utils-580\t580.1.0\n"
            version = self.installed.get(argv[-1])
            if version is None:
                raise RuntimeError("not installed")
            return "install ok installed\t" + version
        if command == "apt-cache":
            if self.missing:
                raise RuntimeError("secret-sensitive-command-output")
            name, version = argv[-1].split("=")
            item = self.lock["packages"][name]
            return "Version: " + version + "\nSHA256: " + item["sha256"] + "\nSize: " + str(item["size_bytes"])
        if command == "apt-get":
            if "-s" in argv:
                return self.simulation
            if "--download-only" in argv:
                self.downloaded = True
            elif "--no-download" in argv:
                if self.fail_install:
                    raise RuntimeError("secret-sensitive-command-output")
                if not self.skip_postcondition:
                    for arg in argv[argv.index("install") + 1:]:
                        name, version = arg.split("=")
                        self.installed[name] = version
            return ""
        if command == "cat":
            return self.boot if argv[-1].endswith("boot_id") else self.module if self.gpu else ""
        if command == "modinfo":
            return self.modinfo if self.gpu else ""
        if command == "nvidia-smi":
            return self.module + ", 00000000:01:00.0\n" + self.module + ", 00000000:02:00.0\n" if self.gpu else ""
        if command == "mokutil":
            return self.secure_boot
        if command == "uname":
            return "6.8.0-100-generic"
        raise AssertionError("unexpected command " + repr(argv))


class PrerequisitesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name).resolve() / "data"
        self.data.mkdir()
        self.policy = Path(self.tmp.name).resolve() / "policy-rc.d"
        self.lock = {"schema_version": 1, "ubuntu_snapshot": "20260707T140000Z",
                     "requested": {"base": {"base-tool": "1.0"}, "driver": {"driver-tool": "2.0"}},
                     "groups": {"base": ["base-tool", "base-library"], "driver": ["driver-tool"]},
                     "compatibility": {"compatible_driver_minimum": "595.71.05", "driver_kernel": "6.8.0-134-generic"},
                     "packages": {n: {"version": v, "size_bytes": 100, "installed_bytes": 1000, "sha256": "a" * 64}
                                  for n, v in [("base-tool", "1.0"), ("base-library", "3.0"), ("driver-tool", "2.0")]}}
        lock_path = Path(self.tmp.name) / "lock.json"
        lock_path.write_text(json.dumps(self.lock))
        self.runner = FakeRunner(self.lock)
        self.guard_calls = 0
        self.mount_present = True
        self.after_download_mount_loss = False

        def guard():
            self.guard_calls += 1
            if not self.mount_present or self.after_download_mount_loss and self.runner.downloaded:
                raise module.PrerequisiteError("Verified mount disappeared")
        self.subject = module.Prerequisites({"data_dir": str(self.data)}, self.runner, guard,
                                           lock_path, policy_path=self.policy)

    def mutations(self):
        return [a for a, _ in self.runner.calls if a[0] == "apt-get" and "--no-download" in a]

    def test_exact_dependency_install_then_verified_noop(self):
        self.runner.simulation += "Inst base-library (3.0 Ubuntu [amd64])\n"
        first = self.subject.apply_base()
        self.assertEqual(first["changed_packages"], {"base-tool": "1.0", "base-library": "3.0"})
        self.assertEqual(self.runner.installed["base-library"], "3.0")
        self.assertEqual(self.subject.apply_base(), {"changed": False})
        self.assertEqual(len(self.mutations()), 1)
        self.assertGreater(self.guard_calls, 8)
        args = self.mutations()[0]
        self.assertIn("base-library=3.0", args)
        self.assertIn("--no-remove", args)
        apt_calls = [(a, e) for a, e in self.runner.calls if a[0] == "apt-get"]
        self.assertTrue(all(e["TMPDIR"].startswith(str(self.data)) for _, e in apt_calls))
        self.assertTrue(all(any(str(self.data / "logs/installer/dpkg.log") in v for v in a) for a, _ in apt_calls))
        self.assertFalse(self.policy.exists())

    def test_missing_pin_has_no_package_mutation_and_redacts_output(self):
        self.runner.missing = True
        with self.assertRaises(module.PrerequisiteError) as error:
            self.subject.apply_base()
        self.assertNotIn("secret-sensitive", str(error.exception))
        self.assertEqual(error.exception.code, "locked_package_unavailable")
        self.assertEqual(error.exception.public_details, {"package": "base-tool", "version": "1.0"})
        self.assertFalse(self.mutations())

    def test_unpinned_transitive_dependency_refused(self):
        self.runner.simulation += "Inst base-library (99.0 Ubuntu [amd64])\n"
        with self.assertRaisesRegex(module.PrerequisiteError, "Unpinned"):
            self.subject.apply_base()
        self.assertFalse(self.mutations())

    def test_removal_or_downgrade_refused(self):
        for value in ("Remv important-system-lib [3.0]\n", "The following packages will be DOWNGRADED:\n"):
            with self.subTest(value=value):
                self.runner.simulation = value
                with self.assertRaisesRegex(module.PrerequisiteError, "removes or downgrades"):
                    self.subject.apply_base()
        self.assertFalse(self.mutations())

    def test_root_space_cannot_be_replaced_by_data_space(self):
        self.runner.root_free = 4 * module.GIB + 999
        with self.assertRaisesRegex(module.PrerequisiteError, "Root package"):
            self.subject.apply_base()
        self.assertFalse(self.mutations())

    def test_data_archive_budget(self):
        self.runner.data_free = module.GIB
        with self.assertRaisesRegex(module.PrerequisiteError, "data capacity"):
            self.subject.apply_base()
        self.assertFalse(self.mutations())

    def test_mount_loss_after_download_prevents_dpkg(self):
        self.after_download_mount_loss = True
        with self.assertRaisesRegex(module.PrerequisiteError, "mount disappeared"):
            self.subject.apply_base()
        self.assertTrue(self.runner.downloaded)
        self.assertFalse(self.mutations())

    def test_unprivileged_invocation_cannot_install(self):
        self.runner.uid = "1000"
        with self.assertRaisesRegex(module.PrerequisiteError, "root or sudo"):
            self.subject.apply_base()
        self.assertFalse(self.mutations())

    def test_prior_service_policy_preserved_on_install_failure(self):
        original = b"#!/bin/sh\n# pre-existing local policy\nexit 101\n"
        self.policy.write_bytes(original)
        self.policy.chmod(0o750)
        self.runner.fail_install = True
        with self.assertRaises(module.PrerequisiteError):
            self.subject.apply_base()
        self.assertEqual(self.policy.read_bytes(), original)
        self.assertEqual(self.policy.stat().st_mode & 0o777, 0o750)
        self.assertFalse(self.subject.check_base())

    def test_failed_dpkg_postcondition_is_failure(self):
        self.runner.skip_postcondition = True
        with self.assertRaisesRegex(module.PrerequisiteError, "postcondition"):
            self.subject.apply_base()

    def test_existing_compatible_loaded_driver_is_preserved(self):
        self.runner.gpu = True
        result = self.subject.apply_driver()
        self.assertFalse(result["changed"])
        self.assertEqual(result["driver"]["gpu_count"], 2)
        self.assertFalse(self.mutations())
        self.assertEqual(result["gpu_container_gate"], "PENDING runtime stage")

    def test_driver_module_userspace_disagreement_is_not_ready(self):
        self.runner.gpu = True
        self.runner.modinfo = "580.1.0"
        self.assertFalse(self.subject.check_driver())

    def test_wrong_gpu_count_is_not_ready(self):
        self.runner.gpu = True
        self.subject.config["expected_gpu_count"] = 1
        self.assertFalse(self.subject.check_driver())

    def test_driver_reboot_checkpoint_requires_changed_boot_and_driver(self):
        self.runner.simulation = "Inst driver-tool (2.0 Ubuntu [amd64])\n"
        self.runner.secure_boot = "SecureBoot enabled"
        with self.assertRaises(module.RebootRequired) as error:
            self.subject.apply_driver()
        self.assertEqual(error.exception.exit_code, 75)
        self.assertTrue(error.exception.checkpoint["secure_boot_enabled"])
        self.assertEqual(self.subject.checkpoint_path.stat().st_mode & 0o777, 0o600)
        self.runner.gpu = True
        self.assertFalse(self.subject.check_driver())
        with self.assertRaises(module.RebootRequired):
            self.subject.apply_driver()
        self.assertEqual(len(self.mutations()), 1)
        self.runner.boot = "00000000-0000-0000-0000-000000000002"
        self.assertTrue(self.subject.check_driver())
        self.assertFalse(self.subject.apply_driver()["changed"])

    def test_post_reboot_missing_driver_is_failure(self):
        self.runner.simulation = "Inst driver-tool (2.0 Ubuntu [amd64])\n"
        with self.assertRaises(module.RebootRequired):
            self.subject.apply_driver()
        self.runner.boot = "00000000-0000-0000-0000-000000000002"
        with self.assertRaisesRegex(module.PrerequisiteError, "invalid after reboot"):
            self.subject.apply_driver()
        self.assertEqual(len(self.mutations()), 1)

    def test_unknown_secureboot_state_refuses_driver_mutation(self):
        self.runner.secure_boot = "unrecognized"
        with self.assertRaisesRegex(module.PrerequisiteError, "Secure Boot"):
            self.subject.apply_driver()
        self.assertFalse(self.mutations())

    def test_cache_symlink_rejected_before_creating_payload(self):
        outside = Path(self.tmp.name).resolve() / "outside"
        outside.mkdir()
        (self.data / "cache").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(module.PrerequisiteError):
            self.subject.apply_base()
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse(any(a[0] == "apt-get" for a, _ in self.runner.calls))

    def test_existing_additional_sources_refused(self):
        self.subject._paths()
        (self.subject.apt_root / "sourceparts/custom.sources").write_text("untrusted sources")
        with self.assertRaisesRegex(module.PrerequisiteError, "sourceparts must be empty"):
            self.subject.apply_base()
        self.assertFalse(any(a[0] == "apt-get" for a, _ in self.runner.calls))

    def test_group_writable_cache_refused(self):
        (self.data / "cache").mkdir(mode=0o777)
        (self.data / "cache").chmod(0o777)
        with self.assertRaisesRegex(module.PrerequisiteError, "ownership/type/mode"):
            self.subject.apply_base()
        self.assertEqual(list((self.data / "cache").iterdir()), [])

    def test_atomic_state_rejects_hardlinks_and_fixed_tmp_is_untouched(self):
        target = self.data / "state.json"
        unrelated = self.data / "unrelated"
        unrelated.write_bytes(b"preserve me")
        fixed_tmp = self.data / "state.json.tmp"
        fixed_tmp.hardlink_to(unrelated)
        self.subject._write_json(target, {"value": 1})
        self.assertEqual(unrelated.read_bytes(), b"preserve me")
        target.unlink()
        target.hardlink_to(unrelated)
        with self.assertRaisesRegex(module.PrerequisiteError, "ownership/type/mode"):
            self.subject._write_json(target, {"value": 2})
        self.assertEqual(unrelated.read_bytes(), b"preserve me")

    def test_interrupted_service_policy_is_restored(self):
        self.subject._paths()
        original = b"#!/bin/sh\nexit 42\n"
        self.subject._write_json(self.subject.state / "package-service-policy.json",
                                 {"schema_version": 2, "existed": True, "original_hex": original.hex(), "mode": 0o750,
                                  "phase": "owned", "transaction": self.runner.package_identity()})
        self.policy.write_bytes(b"#!/bin/sh\n# local-ai installer temporary package service inhibitor\nexit 101\n")
        self.subject.apply_base()
        self.assertEqual(self.policy.read_bytes(), original)
        self.assertEqual(self.policy.stat().st_mode & 0o777, 0o750)

    def test_completed_packages_do_not_skip_interrupted_policy_recovery(self):
        self.subject._paths()
        original = b"#!/bin/sh\nexit 42\n"
        self.subject._write_json(self.subject.state / "package-service-policy.json",
                                 {"schema_version": 2, "existed": True, "original_hex": original.hex(), "mode": 0o750,
                                  "phase": "owned", "transaction": self.runner.package_identity()})
        self.policy.write_bytes(b"#!/bin/sh\n# local-ai installer temporary package service inhibitor\nexit 101\n")
        self.runner.installed["base-tool"] = "1.0"
        self.runner.gpu = True
        self.assertFalse(self.subject.check_base())
        self.assertFalse(self.subject.check_driver())
        self.assertTrue(self.subject.recover_policy()["changed"])
        self.assertEqual(self.policy.read_bytes(), original)
        self.assertTrue(self.subject.check_base())
        self.assertTrue(self.subject.check_driver())
        self.assertFalse(self.subject.apply_base()["changed"])
        self.assertFalse(self.mutations())

    def test_driver_readiness_rejects_mount_loss_even_with_live_driver(self):
        self.runner.gpu = True
        self.mount_present = False
        with self.assertRaisesRegex(module.PrerequisiteError, "mount disappeared"):
            self.subject.check_driver()

    def test_checked_in_lock_has_real_complete_artifact_metadata(self):
        lock = json.loads((ROOT / "scripts/install/versions.lock.json").read_text())
        for group, names in lock["groups"].items():
            self.assertTrue(names)
            for name in names:
                item = lock["packages"][name]
                self.assertEqual(item["http_head_status"], 200, name)
                self.assertEqual(item["http_content_length"], item["size_bytes"], name)
                self.assertRegex(item["sha256"], r"^[a-f0-9]{64}$")
                self.assertTrue(item["url"].startswith("https://"))
        self.assertNotIn("cuda-toolkit", lock["requested"]["driver"])


if __name__ == "__main__":
    unittest.main()
