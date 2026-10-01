import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/vision" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


job = load("artifact_job")
runtime = load("runtime_plan")
launcher = load("launch_job")


class File:
    def __init__(self, path, flags):
        self.fd = os.open(path, flags, 0o600)
    def __enter__(self): return self
    def __exit__(self, *args): os.close(self.fd)
    def stat(self): return os.fstat(self.fd)
    def seek(self, offset): return os.lseek(self.fd, offset, os.SEEK_SET)
    def read(self, size): return os.read(self.fd, size)
    def write(self, value): return os.write(self.fd, value)
    def fsync(self): os.fsync(self.fd)


class FixtureRoot:
    """Transfer-only seam. Production uses existing descriptor-anchored guards."""
    def __init__(self, path): self.path = Path(path)
    def stat(self, name, missing_ok=False):
        try: return (self.path/name).stat()
        except FileNotFoundError:
            if missing_ok: return None
            raise
    def mkdir(self, name): (self.path/name).mkdir(parents=True, exist_ok=True)
    def open(self, name, flags=os.O_RDONLY): return File(self.path/name, flags)
    def replace(self, a, b): (self.path/a).rename(self.path/b)
    def fileno(self): raise AssertionError("use mocked disk capacity")


class Response(io.BytesIO):
    def __init__(self, body, status=200, headers=None):
        super().__init__(body)
        self.status, self.headers = status, headers or {}


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = FixtureRoot(self.temp.name)
        self.root.mkdir("model")
        self.data = b"official-weight-fixture"
        self.item = {"path": "model.safetensors", "size": len(self.data), "sha256": hashlib.sha256(self.data).hexdigest()}
        self.model = {"repo": "Qwen/Qwen3.5-9B", "revision": "a"*40}
        self.events = []
    def run_transfer(self):
        with patch.object(FixtureRoot, "fileno", return_value=0), patch.object(job.os, "fstatvfs") as capacity:
            capacity.return_value.f_bavail = 10**15
            capacity.return_value.f_frsize = 1
            return job.transfer(self.root, "model/model.safetensors", self.model, self.item,
                                time.time()+60, lambda s, n: self.events.append((s, n)))
    def test_manifest_rejects_third_model_and_path_escape(self):
        manifest = json.loads((ROOT/"configs/vision/h039-artifacts.lock.json").read_text())
        job.validate_manifest(manifest)
        third = copy.deepcopy(manifest)
        third["models"].append(third["models"][0])
        with self.assertRaises(job.JobFailure): job.validate_manifest(third)
        manifest["models"][0]["files"][0]["path"] = "../escape"
        with self.assertRaises(job.JobFailure): job.validate_manifest(manifest)
    def test_valid_download_requires_hash_before_final(self):
        with patch.object(job.urllib.request, "urlopen", return_value=Response(self.data)):
            self.run_transfer()
        self.assertEqual((self.root.path/"model/model.safetensors").read_bytes(), self.data)
        self.assertEqual(self.events[-1][0], "HASH_VERIFIED")
    def test_existing_valid_artifact_reused_without_network(self):
        (self.root.path/"model/model.safetensors").write_bytes(self.data)
        with patch.object(job.urllib.request, "urlopen", side_effect=AssertionError("redownload")):
            self.run_transfer()
        self.assertEqual(self.events[-1][0], "HASH_VERIFIED_REUSED")
    def test_hash_failure_preserves_partial_and_no_final(self):
        with patch.object(job.urllib.request, "urlopen", return_value=Response(b"x"*len(self.data))):
            with self.assertRaisesRegex(job.JobFailure, "download_hash_mismatch"): self.run_transfer()
        self.assertTrue((self.root.path/"model/model.safetensors.partial").exists())
        self.assertFalse((self.root.path/"model/model.safetensors").exists())
    def test_resume_appends_only_matching_exact_range(self):
        (self.root.path/"model/model.safetensors.partial").write_bytes(self.data[:5])
        response = Response(self.data[5:], 206, {"Content-Range": f"bytes 5-{len(self.data)-1}/{len(self.data)}"})
        with patch.object(job.urllib.request, "urlopen", return_value=response) as request:
            self.run_transfer()
        self.assertEqual(request.call_args.args[0].get_header("Range"), "bytes=5-")
        self.assertEqual((self.root.path/"model/model.safetensors").read_bytes(), self.data)
    def test_range_rejection_retains_original_partial(self):
        path = self.root.path/"model/model.safetensors.partial"
        path.write_bytes(self.data[:5])
        with patch.object(job.urllib.request, "urlopen", return_value=Response(self.data)):
            with self.assertRaisesRegex(job.JobFailure, "resume_range_not_honored"): self.run_transfer()
        self.assertEqual(path.read_bytes(), self.data[:5])
    def test_deadline_retains_partial(self):
        path = self.root.path/"model/model.safetensors.partial"
        path.write_bytes(self.data)
        with self.assertRaisesRegex(job.JobFailure, "deadline_exceeded"):
            job.transfer(self.root,"model/model.safetensors",self.model,self.item,time.time()-1,lambda *a:None)
        self.assertEqual(path.read_bytes(),self.data)
    def test_storage_guard_error_does_not_start_network(self):
        with patch.object(self.root, "stat", side_effect=RuntimeError("storage_detached")), patch.object(job.urllib.request, "urlopen") as request:
            with self.assertRaises(RuntimeError): self.run_transfer()
        request.assert_not_called()


class RuntimeTests(unittest.TestCase):
    def test_candidate_does_not_execute_and_enforces_shared_reserve(self):
        config=json.loads((ROOT/"configs/vision/h039-candidate.json").read_text())
        for profile in ("16k","32k"):
            plan=runtime.plan(config,profile)
            self.assertFalse(plan["execute"])
            self.assertEqual(len(plan["servers"]),2)
        config["models"][1]["gpuMemoryUtilization"] = .3
        with self.assertRaisesRegex(ValueError,"combined_vram_reserve_required"): runtime.plan(config)
    def test_activation_gate_rejected(self):
        config=json.loads((ROOT/"configs/vision/h039-candidate.json").read_text())
        config["activation"]="ACTIVE"
        with self.assertRaises(ValueError): runtime.plan(config)


class LauncherTests(unittest.TestCase):
    def test_launch_failure_is_bounded_and_is_not_retried(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory)/"launch.json"
            responses = [subprocess.CompletedProcess([],0,"100000\n",""), subprocess.CompletedProcess([],1,"","private signed URL must never enter receipt")]
            with patch.object(sys,"argv",["launch_job.py","--job","h039-vision-test","--receipt",str(receipt)]), patch.object(launcher,"remote",side_effect=responses) as remote:
                with patch("builtins.print"):
                    self.assertEqual(launcher.main(),1)
            self.assertEqual(remote.call_count,2)
            saved=json.loads(receipt.read_text())
            self.assertEqual(saved["deadlineEpoch"]-saved["launchEpoch"],7200)
            self.assertEqual(saved["automaticRetries"],0)
            self.assertEqual(saved["status"],"LAUNCH_FAILED")
            self.assertIn("RuntimeMaxSec=7200s",saved["properties"])
            self.assertIn("Restart=no",saved["properties"])
            self.assertNotIn("private signed URL",receipt.read_text())


if __name__ == "__main__":
    unittest.main()
