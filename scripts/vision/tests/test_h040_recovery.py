"""Synthetic H040 transactions on Mac storage; no VM writes or HTTP requests.

Actual repository guard implementations match the read-only installed hashes.
Only UID, mount discovery, registration, time and network are fixture seams.
These tests do not qualify actual Linux mounts or a durable download.
"""
import base64
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from test_artifact_job import ROOT, Response, job, launcher, load

sys.path.insert(0, str(ROOT / "scripts"))
from common.lifecycle_lease import acquire_lease, LeaseBusy
from install import storage_io as real_io

stage = load("stage_job")
NOW = job.H040_START + 600
JOB = "h039-vision-original"
ATTEMPT = JOB + "-h040-recovery-01"


def sha(body):
    return hashlib.sha256(body).hexdigest()


class GuardFixture:
    """Real descriptor writer and mounted guard with synthetic mountinfo."""
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".h040-guard-", dir=ROOT)
        self.base = Path(self.temp.name).resolve()
        self.data = self.base / "data"
        self.paths = {role: self.data / role for role in ("models", "build", "logs")}
        for path in self.paths.values():
            path.mkdir(parents=True, mode=0o700)
        (self.base / "run/llmctl").mkdir(parents=True, mode=0o700)
        info = self.data.stat()
        identity = {"path": str(self.data), "mount": str(self.data), "uuid": "synthetic-uuid",
                    "fstype": "ext4", "device": f"{os.major(info.st_dev)}:{os.minor(info.st_dev)}"}
        self.snapshot = {"schema_version": 1, "data": identity,
                         "models": {**identity, "path": str(self.paths["models"])},
                         "roots": {key: str(value) for key, value in self.paths.items()}}
        registry = self.base / "etc/local-ai-server/storage.json"
        registry.parent.mkdir(parents=True, mode=0o700)
        self.write(registry, json.dumps(self.snapshot).encode())
        self.mountinfo = ("1 0 0:1 / / rw - ext4 /dev/synthetic-root rw\n"
                          f"2 1 {identity['device']} / {self.data} rw - ext4 /dev/synthetic-data rw\n")
        self.body = b"official-small-config-fixture"
        self.manifest = {"models": []}
        for repo in sorted(job.APPROVED):
            revision = "a" * 40
            self.manifest["models"].append({"repo": repo, "revision": revision,
                "directory": repo.split("/")[1].lower() + "-" + revision,
                "files": [{"path": "config.json", "size": len(self.body), "sha256": sha(self.body)}]})
        self.manifest_bytes = json.dumps(self.manifest).encode()
        self.failed_bytes = b'{"status":"FAILED","failureCode":"TimeoutError","verifiedFiles":13}'
        self.original = self.paths["logs"] / JOB
        self.original.mkdir(mode=0o700)
        self.write(self.original / "manifest.json", self.manifest_bytes)
        self.write(self.original / "status.json", self.failed_bytes)
        self.model_root = self.paths["models"] / JOB
        self.model_root.mkdir(mode=0o700)
        self.write(self.model_root / "retained.partial", b"previous-partial")
        self.worker_bytes = (ROOT / "scripts/vision/artifact_job.py").read_bytes()
        self.payload = {"artifact_job.py": base64.b64encode(self.worker_bytes).decode(),
                        "artifacts.lock.json": base64.b64encode(self.manifest_bytes).decode()}
        fixture = self

        class Storage:
            owner = os.geteuid()
            system_root = fixture.base
            def guard(self, roles=("data", "models")):
                return {**copy.deepcopy(fixture.snapshot), "verified_roles": list(roles)}

        self.storage = Storage()
        self.binding = types.SimpleNamespace(path=lambda role: str(self.paths[role]),
            verify=lambda: {"capacity": {"model_available_bytes": 10**15}},
            mounted_guard=lambda api: real_io.MountedStorageGuard(self.storage, mountinfo_reader=lambda: self.mountinfo))
        lease_module = types.ModuleType("common.lifecycle_lease")
        lease_module.acquire_lease = lambda **kwargs: acquire_lease(system_root=self.base, trusted_uid=os.geteuid(), **kwargs)
        binding_module = types.ModuleType("lifecycle.storage_binding")
        binding_module.RegisteredStorageBinding = types.SimpleNamespace(load=lambda runner: self.binding)
        install_module = types.ModuleType("install")
        install_module.storage_io = types.SimpleNamespace(AnchoredRoot=lambda path, guard:
            real_io.AnchoredRoot(path, guard, uid=os.geteuid()))
        self.modules = {"common.lifecycle_lease": lease_module, "lifecycle.storage_binding": binding_module,
                        "install": install_module}

    def close(self):
        self.temp.cleanup()

    @staticmethod
    def write(path, body):
        path.write_bytes(body)
        path.chmod(0o600)

    def hashes(self):
        return {str(p.relative_to(self.base)): sha(p.read_bytes()) for p in self.original.iterdir()} | {
            "retained.partial": sha((self.model_root / "retained.partial").read_bytes())}

    def common_args(self):
        info = self.model_root.stat()
        return ["--reviewed-window", job.H040_WINDOW, "--expected-root-device", str(info.st_dev),
                "--expected-root-inode", str(info.st_ino), "--expected-original-status-sha256", sha(self.failed_bytes),
                "--expected-original-manifest-sha256", sha(self.manifest_bytes)]

    def stage_args(self):
        return ["stage_job.py", "--guard-scripts", str(ROOT / "scripts"), "--job", ATTEMPT,
                "--artifact-job", JOB, "--deadline-epoch", str(job.H040_CUTOFF), *self.common_args(),
                "--expected-worker-sha256", sha(self.worker_bytes), "--expected-manifest-sha256", sha(self.manifest_bytes)]

    @contextlib.contextmanager
    def staged(self, argv=None):
        stream = io.TextIOWrapper(io.BytesIO(json.dumps(self.payload).encode()))
        with patch.dict(sys.modules, self.modules), patch.object(sys, "argv", argv or self.stage_args()), \
             patch.object(sys, "stdin", stream), patch.object(stage.time, "time", return_value=NOW), \
             patch("builtins.print"):
            yield

    def worker_args(self):
        return ["artifact_job.py", "--guard-scripts", str(ROOT / "scripts"), "--job", JOB, "--attempt", ATTEMPT,
                "--manifest", str(self.paths["build"] / ATTEMPT / "artifacts.lock.json"),
                "--deadline-epoch", str(job.H040_CUTOFF), *self.common_args()]

    @contextlib.contextmanager
    def working(self, argv=None, now=NOW):
        with patch.dict(sys.modules, self.modules), patch.object(sys, "argv", argv or self.worker_args()), \
             patch.object(job.time, "time", return_value=now), patch.object(job.signal, "signal"), \
             patch.object(job.signal, "setitimer"), patch.object(job.os, "fstatvfs",
                 return_value=types.SimpleNamespace(f_bavail=10**15, f_frsize=1)), \
             patch.object(job.urllib.request, "urlopen", side_effect=lambda *a, **k: Response(self.body)) as network:
            yield network


class H040TransactionTests(unittest.TestCase):
    def setUp(self):
        self.f = GuardFixture()
        self.addCleanup(self.f.close)
        self.old = self.f.hashes()

    def assert_preserved(self):
        self.assertEqual(self.f.hashes(), self.old)

    def test_real_guard_stage_and_worker_preserve_failed_original_and_partial(self):
        with self.f.staged():
            self.assertEqual(stage.main(), 0)
        self.assertEqual(list(self.f.paths["models"].iterdir()), [self.f.model_root])
        with self.f.working() as network:
            self.assertEqual(job.main(), 0)
        status = json.loads((self.f.paths["logs"] / ATTEMPT / "status.json").read_text())
        self.assertEqual(status["status"], "VERIFIED")
        self.assertEqual(status["reviewedWindow"]["id"], job.H040_WINDOW)
        self.assertEqual(network.call_count, 2)
        for name in ("stage.claim.json", "attempt.claim.json"):
            self.assertTrue((self.f.paths["logs"] / ATTEMPT / name).is_file())
        with self.f.working() as duplicate_network:
            with self.assertRaises(FileExistsError):
                job.main()
            duplicate_network.assert_not_called()
        self.assert_preserved()

    def test_existing_stage_namespace_is_not_overwritten(self):
        with self.f.staged():
            stage.main()
        hashes = {str(p): sha(p.read_bytes()) for p in self.f.paths["logs"].rglob("*") if p.is_file()}
        with self.f.staged():
            with self.assertRaisesRegex(stage.StageFailure, "attempt_namespace_already_exists"):
                stage.main()
        self.assertEqual({str(p): sha(p.read_bytes()) for p in self.f.paths["logs"].rglob("*") if p.is_file()}, hashes)
        self.assert_preserved()

    def test_stager_rejects_changed_root_and_receipt_before_new_namespace(self):
        for flag, value, expected in (("--expected-root-inode", "1", "original_artifact_root_identity_changed"),
                                     ("--expected-original-status-sha256", "0" * 64, "original_receipt_hash_changed")):
            with self.subTest(flag=flag):
                argv = self.f.stage_args(); argv[argv.index(flag) + 1] = value
                with self.f.staged(argv):
                    with self.assertRaisesRegex(stage.StageFailure, expected):
                        stage.main()
                self.assertFalse((self.f.paths["logs"] / ATTEMPT).exists())
                self.assert_preserved()

    def test_stager_rejects_mismatched_payload_hash_before_storage(self):
        argv = self.f.stage_args(); argv[argv.index("--expected-worker-sha256") + 1] = "0" * 64
        with self.f.staged(argv):
            with self.assertRaisesRegex(stage.StageFailure, "reviewed_payload_hash_mismatch"):
                stage.main()
        self.assertFalse((self.f.paths["logs"] / ATTEMPT).exists())

    def test_real_canonical_lease_contention_makes_no_namespace(self):
        with acquire_lease(system_root=self.f.base, trusted_uid=os.geteuid()):
            with self.f.staged():
                with self.assertRaises(LeaseBusy):
                    stage.main()
        self.assertFalse((self.f.paths["logs"] / ATTEMPT).exists())
        self.assert_preserved()

    def test_mounted_guard_rejects_injected_descendant_before_stage_claim(self):
        device = self.f.snapshot["data"]["device"]
        self.f.mountinfo += f"3 2 {device} /elsewhere {self.f.paths['logs']} rw - ext4 /dev/synthetic-data rw\n"
        with self.f.staged():
            with self.assertRaises(real_io.StorageIOError):
                stage.main()
        self.assertFalse((self.f.paths["logs"] / ATTEMPT).exists())
        self.assert_preserved()

    def test_worker_rejects_changed_preserved_status_before_network_or_claim(self):
        with self.f.staged():
            stage.main()
        argv = self.f.worker_args(); argv[argv.index("--expected-original-status-sha256") + 1] = "0" * 64
        with self.f.working(argv) as network:
            with self.assertRaisesRegex(job.JobFailure, "original_receipt_hash_changed"):
                job.main()
            network.assert_not_called()
        self.assertFalse((self.f.paths["logs"] / ATTEMPT / "attempt.claim.json").exists())
        self.assert_preserved()

    def test_finalizer_can_settle_own_h040_attempt_after_cutoff_without_network(self):
        with self.f.staged():
            stage.main()
        with self.f.working(self.f.worker_args() + ["--finalize"], now=job.H040_CUTOFF + 20) as network:
            self.assertEqual(job.main(), 0)
            network.assert_not_called()
        status = json.loads((self.f.paths["logs"] / ATTEMPT / "status.json").read_text())
        self.assertEqual(status["status"], "FAILED")
        self.assertEqual(status["failureCode"], "failed_before_running_receipt")
        self.assert_preserved()

    def test_finalizer_rejects_mismatched_stored_authority_without_rewriting_status(self):
        with self.f.staged():
            stage.main()
        path = self.f.paths["logs"] / ATTEMPT / "status.json"
        state = json.loads(path.read_text()); state["reviewedWindow"] = {"id": "different-window"}
        self.f.write(path, json.dumps(state).encode()); before = path.read_bytes()
        with self.f.working(self.f.worker_args() + ["--finalize"], now=job.H040_CUTOFF + 20) as network:
            with self.assertRaisesRegex(job.JobFailure, "finalizer_reviewed_window_mismatch"):
                job.main()
            network.assert_not_called()
        self.assertEqual(path.read_bytes(), before)
        self.assert_preserved()

    def test_stage_window_expiring_during_readiness_creates_no_namespace(self):
        binding_class = self.f.modules["lifecycle.storage_binding"].RegisteredStorageBinding
        with self.f.staged(), patch.object(stage.time, "time", return_value=NOW) as clock:
            def late_load(runner):
                clock.return_value = job.H040_CUTOFF
                return self.f.binding
            with patch.object(binding_class, "load", side_effect=late_load):
                with self.assertRaisesRegex(stage.StageFailure, "deadline_outside_reviewed_recovery_window"):
                    stage.main()
        self.assertFalse((self.f.paths["logs"] / ATTEMPT).exists())
        self.assert_preserved()


class H040WindowTests(unittest.TestCase):
    def launcher_args(self, receipt):
        return ["launch_job.py", "--job", JOB, "--attempt", ATTEMPT, "--prepare-only", "--receipt", str(receipt),
                "--deadline-utc", "2026-10-01T04:26:10Z", "--reviewed-window", job.H040_WINDOW,
                "--expected-root-device", "2081", "--expected-root-inode", "140247041",
                "--expected-original-status-sha256", "a" * 64, "--expected-original-manifest-sha256", "b" * 64]

    def test_exact_h040_proposal_propagates_authority_to_worker_and_finalizer(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "proposal.json"
            with patch.object(sys, "argv", self.launcher_args(p)), patch.object(launcher, "remote",
                return_value=subprocess.CompletedProcess([], 0, str(int(NOW)), "")) as remote, patch("builtins.print"):
                self.assertEqual(launcher.main(), 0)
            remote.assert_called_once_with(["/usr/bin/date", "+%s"])
            saved = json.loads(p.read_text())
            self.assertEqual(saved["deadlineEpoch"], job.H040_CUTOFF)
            self.assertEqual(saved["maximumWorkSeconds"], job.H040_CUTOFF - NOW)
            self.assertIn("Restart=no", saved["properties"])
            self.assertEqual(saved["automaticRetries"], 0)
            self.assertEqual(saved["artifactRoot"], "/data/models-large/" + JOB)
            self.assertIn("--reviewed-window", saved["command"])
            finalizer = next(v for v in saved["properties"] if v.startswith("ExecStopPost="))
            self.assertIn(job.H040_WINDOW, finalizer)
            self.assertIn("--finalize", finalizer)
            self.assertNotIn("launchExit", saved)

    def test_old_default_is_expired_in_launcher_worker_and_stager(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.launcher_args(Path(directory) / "receipt.json")
            i = args.index("--reviewed-window"); del args[i:i+2]
            with patch.object(sys, "argv", args), patch.object(launcher, "remote",
                return_value=subprocess.CompletedProcess([], 0, str(int(NOW)), "")):
                with self.assertRaisesRegex(ValueError, "deadline_outside_reviewed_recovery_window"):
                    launcher.main()
            worker_args = ["artifact_job.py", "--job", JOB, "--attempt", ATTEMPT, "--manifest", "/not/read",
                "--guard-scripts", "/not/imported", "--deadline-epoch", str(job.H040_CUTOFF),
                "--expected-root-device", "2081", "--expected-root-inode", "140247041"]
            with patch.object(sys, "argv", worker_args), patch.object(job.urllib.request, "urlopen") as network:
                with self.assertRaisesRegex(job.JobFailure, "deadline_outside_reviewed_recovery_window"):
                    job.main()
                network.assert_not_called()
            with patch.object(sys, "argv", ["stage_job.py", "--job", ATTEMPT, "--guard-scripts", "/not/imported"]), \
                 patch.object(stage.time, "time", return_value=NOW):
                with self.assertRaisesRegex(stage.StageFailure, "old_review_window_expired"):
                    stage.main()

    def test_launcher_rejects_unknown_untied_and_excessive_idle_authority(self):
        for flag, value, code in (("--reviewed-window", "h041", "unknown_reviewed_window"),
                                 ("--attempt", "h039-vision-unrelated", "h040_requires_distinct_tied_attempt"),
                                 ("--network-timeout-seconds", "181", "h040_network_timeout_must_be_1_to_180_seconds")):
            with tempfile.TemporaryDirectory() as directory, self.subTest(flag=flag):
                args = self.launcher_args(Path(directory) / "receipt.json")
                if flag in args: args[args.index(flag)+1] = value
                else: args += [flag, value]
                with patch.object(sys, "argv", args), patch.object(launcher, "remote") as remote:
                    with self.assertRaisesRegex(ValueError, code): launcher.main()
                    remote.assert_not_called()

    def test_h040_deadline_and_opening_boundaries_fail_before_receipt(self):
        for deadline, clock, code in (("2026-10-01T04:26:11Z", NOW, "deadline_outside_reviewed_recovery_window"),
                                     ("2026-10-01T04:26:10Z", job.H040_START-1, "reviewed_window_not_open"),
                                     ("2026-10-01T04:26:10Z", job.H040_CUTOFF, "deadline_outside_reviewed_recovery_window")):
            with tempfile.TemporaryDirectory() as directory, self.subTest(clock=clock):
                p = Path(directory) / "receipt.json"; args = self.launcher_args(p)
                args[args.index("--deadline-utc")+1] = deadline
                with patch.object(sys, "argv", args), patch.object(launcher, "remote",
                    return_value=subprocess.CompletedProcess([], 0, str(int(clock)), "")):
                    with self.assertRaisesRegex(ValueError, code): launcher.main()
                self.assertFalse(p.exists())

    def test_live_launcher_still_requires_reviewed_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.launcher_args(Path(directory) / "receipt.json"); args.remove("--prepare-only")
            with patch.object(sys, "argv", args), patch.object(launcher, "remote") as remote:
                with self.assertRaisesRegex(ValueError, "root_review_required"): launcher.main()
                remote.assert_not_called()

    def test_worker_rejects_unreviewed_or_expired_h040_before_manifest_or_network(self):
        base = ["artifact_job.py", "--job", JOB, "--attempt", ATTEMPT, "--manifest", "/not/read",
                "--guard-scripts", "/not/imported", "--reviewed-window", job.H040_WINDOW,
                "--deadline-epoch", str(job.H040_CUTOFF), "--expected-root-device", "2081",
                "--expected-root-inode", "140247041", "--expected-original-status-sha256", "a" * 64,
                "--expected-original-manifest-sha256", "b" * 64]
        cases = [("--reviewed-window", "h041", NOW, "unknown_reviewed_window"),
                 ("--attempt", "h039-vision-unrelated", NOW, "h040_requires_distinct_tied_attempt"),
                 ("--deadline-epoch", str(job.H040_CUTOFF + 1), NOW, "deadline_outside_reviewed_recovery_window"),
                 ("--network-timeout-seconds", "181", NOW, "h040_network_timeout_must_be_1_to_180_seconds"),
                 ("--expected-original-status-sha256", "invalid", NOW, "reviewed_original_receipt_hashes_required"),
                 ("--reviewed-window", job.H040_WINDOW, job.H040_START - 1, "reviewed_window_not_open"),
                 ("--reviewed-window", job.H040_WINDOW, job.H040_CUTOFF, "deadline_must_be_within_two_hours")]
        for flag, value, clock, code in cases:
            with self.subTest(flag=flag, clock=clock):
                args = list(base)
                if flag in args: args[args.index(flag)+1] = value
                else: args += [flag, value]
                with patch.object(sys, "argv", args), patch.object(job.time, "time", return_value=clock), \
                     patch.object(job.Path, "read_text") as read, patch.object(job.urllib.request, "urlopen") as network:
                    with self.assertRaisesRegex(job.JobFailure, code): job.main()
                    read.assert_not_called(); network.assert_not_called()


class StageDiagnosticTests(unittest.TestCase):
    def test_subprocess_failure_retains_exit_and_stderr_digest_without_raw_secret(self):
        secret = "signed URL https://private.invalid/?token=SYNTHETIC_SECRET"
        result = subprocess.CompletedProcess([], 7, "protected output", secret)
        with patch.object(stage.subprocess, "run", return_value=result):
            with self.assertRaises(stage.StageFailure) as caught:
                stage.Runner().run(["synthetic-guard-command"])
        err = io.StringIO()
        with patch.object(stage, "main", side_effect=caught.exception), contextlib.redirect_stderr(err):
            self.assertEqual(stage.cli(), 1)
        saved = json.loads(err.getvalue())
        self.assertEqual(saved["failureType"], "StageFailure")
        self.assertEqual(saved["failureCode"], "stage_guard_command_failed")
        self.assertEqual(saved["privateCommandReceipt"], {"exitCode": 7, "stderrSha256": sha(secret.encode()),
                                                         "stderrBytes": len(secret.encode())})
        self.assertNotIn(secret, err.getvalue())
        self.assertNotIn("protected output", err.getvalue())

    def test_timed_out_guard_keeps_unknown_exit_and_private_stderr_digest(self):
        failure = subprocess.TimeoutExpired(["synthetic-guard"], 30, stderr=b"SYNTHETIC_SECRET")
        with patch.object(stage.subprocess, "run", side_effect=failure):
            with self.assertRaises(stage.StageFailure) as caught:
                stage.Runner().run(["synthetic-guard"])
        self.assertEqual(caught.exception.code, "stage_guard_command_timeout")
        self.assertIsNone(caught.exception.command_receipt["exitCode"])
        self.assertTrue(caught.exception.command_receipt["timedOut"])
        self.assertEqual(caught.exception.command_receipt["stderrSha256"], sha(b"SYNTHETIC_SECRET"))

    def test_unexpected_error_prints_only_type_and_success_exit_is_truthful(self):
        err = io.StringIO()
        with patch.object(stage, "main", side_effect=OSError("SYNTHETIC_SECRET")), contextlib.redirect_stderr(err):
            self.assertEqual(stage.cli(), 1)
        self.assertNotIn("SYNTHETIC_SECRET", err.getvalue())
        with patch.object(stage, "main", return_value=0):
            self.assertEqual(stage.cli(), 0)


if __name__ == "__main__":
    unittest.main()
