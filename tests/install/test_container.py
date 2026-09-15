"""Synthetic staged container tests: no packages/services/GPU on the worker."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from install.container import ContainerPackages, ContainerStage, InstallError, NVIDIA_RUNTIME, UNITS
from install.prerequisites import PrerequisiteError


class Response(io.BytesIO):
    status = 200
    url = "https://fixture.invalid/key"


class FixtureRunner:
    def __init__(self, owner):
        self.owner = owner
        self.calls = []
        self.installed = {}
        self.active = False
        self.image = False
        self.boot = "fixture-boot-one"
        self.fail_install = False
        self.skip_install = False
        self.root_override = None
        self.exec_override = None
        self.private_mounts = "yes"
        self.unpinned = False
        self.gpu_rows = "595.71.05, 00000000:01:00.0\n595.71.05, 00000000:02:00.0"
        self.container_rows = self.gpu_rows
        self.image_digest_override = None
        self.image_id = "sha256:" + "c" * 64
        self.after_download = None

    # Explicit synthetic transaction capability seam; the reviewed I1R backend
    # is absent in this checkout. These fixtures do not prove cgroup ownership.
    def package_identity(self): pass
    def prepare_package(self, *a, **k): pass
    def hold_package_lease(self, *a, **k): pass
    def run_package(self, *a, **k): pass
    def inspect_package(self, *a, **k): pass

    def run(self, argv, timeout=60, env=None):
        self.calls.append((argv, env))
        if argv[0] == "id":
            return "0"
        if argv[0] == "df":
            return "Avail\n" + str(100 * 1024 ** 3)
        if argv[0] == "dpkg-query":
            version = self.installed.get(argv[-1])
            if not version:
                raise RuntimeError("not installed")
            return "install ok installed\t" + version
        if argv[0] == "apt-cache":
            name, version = argv[-1].split("=", 1)
            item = self.owner.lock["packages"][name]
            return "Version: " + version + "\nSHA256: " + item["sha256"] + "\nSize: " + str(item["size_bytes"])
        if argv[0] == "apt-get":
            if "-s" in argv:
                name = argv[-1].split("=")[0]
                text = "Inst " + name + " (1.0 fixture [amd64])\n"
                return text + ("Inst surprise (9.0 fixture [amd64])\n" if self.unpinned else "")
            if "--download-only" in argv and self.after_download:
                self.after_download()
            if "--no-download" in argv:
                o = self.owner
                o.assertTrue(all((o.system / "run/systemd/system" / unit).is_symlink() for unit in UNITS))
                o.assertIn(b"exit 101", (o.system / "usr/sbin/policy-rc.d").read_bytes())
                o.assertEqual(json.loads((o.system / "etc/docker/daemon.json").read_text())["data-root"], str(o.data / "docker"))
                o.assertIn(str(o.data / "containerd"), (o.system / "etc/containerd/config.toml").read_text())
                if self.fail_install:
                    raise RuntimeError("fixture sensitive output")
                if not self.skip_install:
                    self.installed.update(item.split("=", 1) for item in argv[argv.index("install") + 1:])
            return ""
        if argv[:2] == ["systemctl", "is-active"]:
            return "active" if self.active else "inactive"
        if argv[:2] == ["systemctl", "show"]:
            if "--property=Environment" in argv:
                return "DOCKER_TMPDIR=" + str(self.owner.data / "cache/docker-tmp") + " TMPDIR=" + str(self.owner.data / "cache/container-tmp")
            if "--property=PrivateMounts" in argv: return self.private_mounts
            if "--property=BindPaths" in argv: return str(self.owner.data) + ":" + str(self.owner.data) + ":rbind"
            return self.exec_override if self.exec_override is not None else "/usr/bin/" + argv[2].split(".")[0]
        if argv[:2] == ["systemctl", "daemon-reload"]:
            return ""
        if argv[:2] == ["systemctl", "start"]:
            self.owner.assertTrue(all(not (self.owner.system / "run/systemd/system" / u).is_symlink() for u in UNITS))
            self.active = True
            return ""
        if argv[:2] == ["docker", "info"]:
            if not self.active:
                raise RuntimeError("inactive")
            return json.dumps({"DockerRootDir": self.root_override or str(self.owner.data / "docker"), "Runtimes": {"nvidia": {}}})
        if argv[:3] == ["docker", "image", "inspect"]:
            if not self.image:
                raise RuntimeError("image absent")
            image = self.owner.lock["gpu_container_gate"]["image"]
            return json.dumps({"Architecture": "amd64", "Os": "linux", "Id": self.image_id,
                               "RepoDigests": [self.image_digest_override or image.split(":", 1)[0] + "@" + image.split("@", 1)[1]]})
        if argv[:2] == ["docker", "pull"]:
            self.image = True
            return ""
        if argv[:2] == ["docker", "run"]:
            return self.container_rows
        if argv[0] == "containerd":
            return (self.owner.system / "etc/containerd/config.toml").read_text()
        if argv[0] == "dockerd":
            return "configuration OK"
        if argv[0] == "nvidia-smi":
            return self.gpu_rows
        if argv[0] == "cat":
            return self.boot
        raise AssertionError(argv)


class ContainerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix=".container-test-", dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        self.system, self.data = base / "system", base / "data"
        self.system.mkdir(); self.data.mkdir()
        (self.system / "usr/sbin").mkdir(parents=True)
        self.key = b"fixture armored key bytes"
        self.lock = {"schema_version": 1, "ubuntu_snapshot": "20260707T140000Z",
                     "requested": {"docker": {"engine": "1.0"}, "toolkit": {"toolkit": "1.0"}},
                     "groups": {"docker": ["engine"], "toolkit": ["toolkit"]},
                     "packages": {n: {"version": "1.0", "size_bytes": 100, "installed_bytes": 1000, "sha256": "a" * 64} for n in ("engine", "toolkit")},
                     "container_repositories": {n: {"key_url": "https://fixture.invalid/key", "key_sha256": hashlib.sha256(self.key).hexdigest(), "key_size_bytes": len(self.key)} for n in ("docker", "nvidia")},
                     "gpu_container_gate": {"image": "nvidia/cuda:locked@sha256:" + "b" * 64, "capacity_reserve_bytes": 8 * 1024 ** 3, "registry_artifact": {"config_digest": "sha256:" + "c" * 64, "platform_manifest_digest": "sha256:" + "b" * 64, "compressed_artifact_bytes": 1000}}}
        self.config = {"data_dir": str(self.data), "expected_gpu_count": 2}
        self.present = True
        self.runner = FixtureRunner(self)
        self.stage = ContainerStage(self.config, self.runner, self.guard, system_root=self.system, uid=os.geteuid(), lock=self.lock)
        self.patcher = patch("install.container.urllib.request.urlopen", side_effect=lambda *a, **kw: Response(self.key))
        self.patcher.start(); self.addCleanup(self.patcher.stop)

    def guard(self):
        if not self.present:
            raise InstallError("fixture_mount_lost")
        device = self.data.stat().st_dev
        mount = {"path": str(self.data), "mount": str(self.data), "uuid": "fixture-uuid", "fstype": "ext4", "device": str(os.major(device)) + ":" + str(os.minor(device))}
        return {"schema_version": 1, "data": mount, "models": dict(mount, path=str(self.data / "models")), "roots": {"docker": str(self.data / "docker"), "containerd": str(self.data / "containerd"),
                          "state": str(self.data / "services/installer"), "logs": str(self.data / "logs"), "build": str(self.data / "build")}}

    def write(self, relative, content):
        target = self.system / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def mutations(self):
        return [a for a, _ in self.runner.calls if a[0] == "apt-get" and "--no-download" in a]

    def test_real_stage_entrypoint_order_and_second_verified_noop(self):
        result = self.stage.apply()
        self.assertTrue(result["changed"])
        self.assertEqual(result["gpu_gate"], "NOT_RUN")
        self.assertTrue(self.stage.check())
        self.assertFalse(self.stage.apply()["changed"])
        self.assertEqual(len(self.mutations()), 2)
        for a, env in self.runner.calls:
            if a[0] == "apt-get":
                self.assertRegex(env["TMPDIR"], r"^/proc/[0-9]+/fd/[0-9]+/cache/")
        self.assertFalse(self.stage.check_gpu())

    def test_existing_config_preserved_with_narrow_merge_and_backup(self):
        original = {"data-root": str(self.data / "docker"), "dns": ["1.1.1.1"], "live-restore": True,
                    "runtimes": {"runc-custom": {"path": "/usr/bin/runc"}}}
        target = self.write("etc/docker/daemon.json", json.dumps(original).encode())
        cdata = ("# existing tuning\nversion = 2\nroot = " + json.dumps(str(self.data / "containerd")) + "\n[grpc]\nmax_recv_message_size = 12345\n").encode()
        ctarget = self.write("etc/containerd/config.toml", cdata)
        self.stage.apply()
        actual = json.loads(target.read_text())
        self.assertEqual(actual["dns"], original["dns"])
        self.assertEqual(actual["runtimes"]["runc-custom"], original["runtimes"]["runc-custom"])
        self.assertEqual(ctarget.read_bytes(), cdata)
        backups = list((self.data / "services/installer").glob("container-config-before-*.json"))
        self.assertEqual(len(backups), 2)
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in backups))

    def test_semantically_complete_json_bytes_preserved(self):
        self.stage.apply()
        target = self.system / "etc/docker/daemon.json"
        original = json.dumps(json.loads(target.read_text()), separators=(",", ":")).encode()
        target.write_bytes(original)
        self.assertFalse(self.stage.apply()["changed"])
        self.assertEqual(target.read_bytes(), original)

    def test_policy_and_runtime_masks_restore_after_failed_package(self):
        prior = b"#!/bin/sh\n# local policy\nexit 0\n"
        target = self.write("usr/sbin/policy-rc.d", prior); target.chmod(0o750)
        self.runner.fail_install = True
        with self.assertRaises(PrerequisiteError): self.stage.apply()
        self.assertEqual(target.read_bytes(), prior)
        self.assertEqual(target.stat().st_mode & 0o777, 0o750)
        self.assertFalse(any((self.system / "run/systemd/system" / unit).is_symlink() for unit in UNITS))
        self.runner.fail_install = False
        self.assertTrue(self.stage.apply()["changed"])

    def test_interrupted_runtime_mask_checkpoint_recovers(self):
        self.stage.prereqs._ensure_directory(self.stage.state)
        unit = self.system / "run/systemd/system/docker.service"; unit.parent.mkdir(parents=True)
        unit.symlink_to("/dev/null")
        self.stage._state_write(self.stage.mask_marker, {"schema_version": 1, "created": ["docker.service"]})
        self.assertFalse(self.stage.check())
        self.stage.apply()
        self.assertFalse(unit.is_symlink()); self.assertFalse(self.stage.mask_marker.exists())

    def test_existing_runtime_mask_preserved(self):
        unit = self.system / "run/systemd/system/docker.socket"; unit.parent.mkdir(parents=True)
        unit.symlink_to("/dev/null")
        # The fixture start ignores systemd mask; preservation is the assertion.
        self.runner.fail_install = True
        with self.assertRaises(PrerequisiteError): self.stage.apply()
        self.assertEqual(os.readlink(unit), "/dev/null")

    def test_configured_root_mismatch_refuses_before_packages(self):
        self.write("etc/docker/daemon.json", b'{"data-root":"/some/other/root"}')
        with self.assertRaisesRegex(InstallError, "root_mismatch"): self.stage.apply()
        self.assertFalse(self.mutations())

    def test_running_root_mismatch_and_active_reconfigure_refuse(self):
        self.runner.active = True; self.runner.root_override = "/var/lib/docker"
        with self.assertRaisesRegex(InstallError, "root_mismatch"): self.stage.apply()
        self.runner.root_override = None
        with self.assertRaisesRegex(InstallError, "coordinated_change"): self.stage.apply()
        self.assertFalse(self.mutations())

    def test_populated_old_root_not_hidden(self):
        payload = self.write("var/lib/containerd/old.snapshot", b"preserve")
        with self.assertRaisesRegex(InstallError, "requires_migration"): self.stage.apply()
        self.assertEqual(payload.read_bytes(), b"preserve")
        self.assertFalse(self.mutations())

    def test_service_flag_and_containerd_imports_rejected(self):
        self.runner.exec_override = "/usr/bin/dockerd --data-root=/unreviewed"
        with self.assertRaisesRegex(InstallError, "override_requires_review"): self.stage.apply()
        self.runner.exec_override = ""
        self.write("etc/containerd/config.toml", b'imports = ["/another/config.toml"]\n')
        with self.assertRaisesRegex(InstallError, "imports_require_review"): self.stage.apply()

    def test_unpinned_dependency_and_failed_postcondition_refuse(self):
        self.runner.unpinned = True
        with self.assertRaisesRegex(PrerequisiteError, "Unpinned"): self.stage.apply()
        self.assertFalse(self.mutations())
        self.runner.unpinned = False; self.runner.skip_install = True
        with self.assertRaisesRegex(PrerequisiteError, "postcondition"): self.stage.apply()

    def test_key_identity_drift_refuses_package_mutation(self):
        self.lock["container_repositories"]["docker"]["key_sha256"] = "e" * 64
        with self.assertRaisesRegex(PrerequisiteError, "key identity changed"): self.stage.apply()
        self.assertFalse(self.mutations())

    def test_mount_loss_after_package_download_keeps_masks_until_recovery(self):
        self.runner.after_download = lambda: setattr(self, "present", False)
        with self.assertRaisesRegex(InstallError, "mount_lost"): self.stage.apply()
        self.assertFalse(self.mutations())
        self.assertTrue(all((self.system / "run/systemd/system" / unit).is_symlink() for unit in UNITS))
        self.present = True; self.runner.after_download = None
        self.assertTrue(self.stage.apply()["changed"])

    def test_gpu_command_requires_exact_host_image_and_boot_identity(self):
        self.stage.apply()
        result = self.stage.apply_gpu()
        # These are explicit command fixtures, not actual GPU evidence.
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["evidence_class"], "SYNTHETIC_FIXTURE")
        self.assertTrue(self.stage.check_gpu())
        runs = [a for a, _ in self.runner.calls if a[:2] == ["docker", "run"]]
        self.assertEqual(len(runs), 1); self.assertIn("never", runs[0]); self.assertIn("none", runs[0])
        self.assertFalse(self.stage.apply_gpu()["changed"])
        self.runner.boot = "different-boot"
        self.assertFalse(self.stage.check_gpu())
        self.runner.container_rows = "595.71.05, 00000000:99:00.0"
        with self.assertRaisesRegex(InstallError, "execution_failed"): self.stage.apply_gpu()

    def test_verified_manifest_id_is_accepted_for_containerd_image_store(self):
        self.stage.apply(); self.runner.image_id = "sha256:" + "b" * 64
        self.assertEqual(self.stage.apply_gpu()["evidence_class"], "SYNTHETIC_FIXTURE")
        self.assertTrue(self.stage.check_gpu())

    def test_matching_tag_different_digest_is_not_accepted(self):
        self.stage.apply(); self.runner.image = True
        self.runner.image_digest_override = "nvidia/cuda@sha256:" + "d" * 64
        with self.assertRaisesRegex(InstallError, "image_identity_mismatch"): self.stage.apply_gpu()
        self.assertFalse(self.stage.gpu_record.exists())

    def test_package_and_evidence_drift_force_revalidation(self):
        self.stage.apply(); self.stage.apply_gpu()
        self.runner.installed["engine"] = "2.0"
        self.assertFalse(self.stage.check()); self.assertFalse(self.stage.check_gpu())

    def test_effective_service_namespace_drift_cannot_reuse_completion(self):
        self.stage.apply()
        self.runner.private_mounts = "no"
        self.assertFalse(self.stage.check())
        with self.assertRaisesRegex(InstallError, "coordinated_change"):
            self.stage.apply()

    def test_unbounded_logging_and_containerd_tcp_listener_rejected(self):
        self.write("etc/docker/daemon.json", b'{"log-driver":"json-file","log-opts":{"max-size":"-1","max-file":"3"}}')
        with self.assertRaisesRegex(InstallError, "unbounded_docker_logging"):
            self.stage.apply()
        (self.system / "etc/docker/daemon.json").unlink()
        self.write("etc/containerd/config.toml", b'[grpc]\ntcp_address="0.0.0.0:1234"\n')
        with self.assertRaisesRegex(InstallError, "api_exposure_requires_review"):
            self.stage.apply()
        self.assertFalse(self.mutations())

    def test_compact_service_root_override_and_unknown_command_fail_closed(self):
        for override in ("/usr/bin/containerd -r=/other", "/usr/bin/containerd -r/other", "/usr/bin/dockerd -g=/other", "/usr/bin/containerd -c=/other"):
            self.runner.exec_override = override
            with self.assertRaisesRegex(InstallError, "override_requires_review"):
                self.stage.apply()
        self.runner.active = True; self.runner.exec_override = ""
        with self.assertRaisesRegex(InstallError, "command_unverified"):
            self.stage.check()
        self.assertFalse(self.mutations())

    def test_original_backup_survives_interrupted_install_resume(self):
        original = b'{"dns":["1.1.1.1"]}'
        self.write("etc/docker/daemon.json", original)
        self.runner.fail_install = True
        with self.assertRaises(PrerequisiteError): self.stage.apply()
        backup = next(self.stage.state.glob("container-config-before-*.json"))
        before = backup.read_bytes()
        self.runner.fail_install = False
        self.stage.apply()
        self.assertEqual(backup.read_bytes(), before)
        self.assertEqual(bytes.fromhex(json.loads(before)["content_hex"]), original)

    def test_unreviewed_runner_refuses_before_config_or_package_mutation(self):
        self.runner.package_identity = None
        with self.assertRaisesRegex(InstallError, "i1r_package_lease_integration_required"):
            self.stage.apply()
        self.assertFalse((self.system / "etc/docker/daemon.json").exists())
        self.assertFalse(self.mutations())

    def test_lock_contains_exact_selected_inputs_and_all_closure_records(self):
        lock = json.loads((ROOT / "scripts/install/versions.lock.json").read_text())
        for group in ("docker", "toolkit"):
            for name in lock["groups"][group]:
                p = lock["packages"][name]
                self.assertRegex(p["sha256"], r"^[0-9a-f]{64}$")
                self.assertTrue(p["url"].startswith("https://"))
                self.assertGreater(p["size_bytes"], 0)
        for item in lock["selected_models"].values():
            self.assertEqual(hashlib.sha256((ROOT / item["manifest"]).read_bytes()).hexdigest(), item["sha256"])
        self.assertEqual(lock["container_repositories"]["docker"]["primary_fingerprint"], "9DC858229FC7DD38854AE2D88D81803C0EBFCD88")
        self.assertIn("@sha256:", lock["gpu_container_gate"]["image"])


if __name__ == "__main__": unittest.main()
