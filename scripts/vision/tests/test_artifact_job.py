import copy
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import time
import types
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
    def __init__(self, path, guard=None): self.path = Path(path)
    def __enter__(self): return self
    def __exit__(self, *args):
        if hasattr(self,"fd"): os.close(self.fd)
    def stat(self, name, missing_ok=False):
        try: return (self.path/name).stat()
        except FileNotFoundError:
            if missing_ok: return None
            raise
    def mkdir(self, name): (self.path/name).mkdir(parents=True, exist_ok=True)
    def open(self, name, flags=os.O_RDONLY): return File(self.path/name, flags)
    def replace(self, a, b): (self.path/a).rename(self.path/b)
    def fileno(self):
        if not hasattr(self,"fd"): self.fd=os.open(self.path,os.O_RDONLY)
        return self.fd
    def directory(self,name): return FixtureRoot(self.path/name)
    def read_json(self,name): return json.loads((self.path/name).read_text())
    def atomic_json(self,name,value): (self.path/name).write_text(json.dumps(value))


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
    def test_configurable_timeout_is_clamped_to_absolute_deadline(self):
        with patch.object(job.time,"time",return_value=100):
            self.assertEqual(job.bounded_network_timeout(180,400),180)
            self.assertEqual(job.bounded_network_timeout(180,115),15)
            with self.assertRaises(job.JobFailure): job.bounded_network_timeout(180,100)
            with self.assertRaises(job.JobFailure): job.bounded_network_timeout(601,400)
    def test_open_timeout_is_one_attempt_and_keeps_partial(self):
        path=self.root.path/"model/model.safetensors.partial"
        path.write_bytes(self.data[:5])
        with patch.object(job.urllib.request,"urlopen",side_effect=TimeoutError) as request:
            with self.assertRaises(TimeoutError): self.run_transfer()
        self.assertEqual(request.call_count,1)
        self.assertEqual(path.read_bytes(),self.data[:5])
        self.assertLessEqual(request.call_args.kwargs['timeout'],60)
    def test_read_timeout_retains_incremental_block_for_next_resume(self):
        response=Response(self.data)
        response.read1=lambda size: self.data[:7]
        with patch.object(job.urllib.request,"urlopen",return_value=response), patch.object(response,"read1",side_effect=[self.data[:7],TimeoutError]):
            with self.assertRaises(TimeoutError): self.run_transfer()
        path=self.root.path/"model/model.safetensors.partial"
        self.assertEqual(path.read_bytes(),self.data[:7])
        response=Response(self.data[7:],206,{'Content-Range':f'bytes 7-{len(self.data)-1}/{len(self.data)}'})
        with patch.object(job.urllib.request,"urlopen",return_value=response): self.run_transfer()
        self.assertEqual((self.root.path/"model/model.safetensors").read_bytes(),self.data)


class AttemptTests(unittest.TestCase):
    def run_attempt(self, response_error=False, wrong_inode=False, legacy_noattempt=False):
        import sys
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            job_name="h039-vision-original"
            attempt="h039-vision-recovery-01"
            for path in ['logs/'+job_name,'models/'+job_name]: (root/path).mkdir(parents=True)
            body=b'official fixture'
            manifest={'models':[]}
            for repo in job.APPROVED:
                revision='a'*40
                manifest['models'].append({'repo':repo,'revision':revision,'directory':repo.split('/')[1].lower()+'-'+revision,
                    'files':[{'path':'config.json','size':len(body),'sha256':hashlib.sha256(body).hexdigest()}]})
            manifest_path=root/'manifest.json'; manifest_path.write_text(json.dumps(manifest))
            original=root/'logs'/job_name
            (original/'manifest.json').write_text(json.dumps(manifest))
            failed=json.dumps({'status':'FAILED','failureCode':'TimeoutError','verifiedFiles':13,'verifiedWeightFiles':1})
            (original/'status.json').write_text(failed)
            old_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in original.iterdir()}
            info=(root/'models'/job_name).stat()
            binding=types.SimpleNamespace(path=lambda role:str(root/role), verify=lambda:{'capacity':{'model_available_bytes':10**15}}, mounted_guard=lambda io:contextlib.nullcontext(lambda:{}))
            lease_module=types.ModuleType('common.lifecycle_lease')
            lease_module.acquire_lease=lambda **k:contextlib.nullcontext(types.SimpleNamespace(validate=lambda:None))
            binding_module=types.ModuleType('lifecycle.storage_binding')
            binding_module.RegisteredStorageBinding=types.SimpleNamespace(load=lambda runner:binding)
            install_module=types.ModuleType('install'); install_module.storage_io=types.SimpleNamespace(AnchoredRoot=FixtureRoot)
            modules={'common.lifecycle_lease':lease_module,'lifecycle.storage_binding':binding_module,'install':install_module}
            argv=['artifact_job.py','--job',job_name,'--attempt',attempt,'--manifest',str(manifest_path),'--guard-scripts','/fixture',
                  '--deadline-epoch',str(job.RECOVERY_CUTOFF),'--expected-root-device',str(info.st_dev),'--expected-root-inode',str(info.st_ino+(1 if wrong_inode else 0))]
            if legacy_noattempt:
                index=argv.index('--attempt'); del argv[index:index+2]
            with patch.dict(sys.modules,modules), patch.object(sys,'argv',argv), patch.object(job.time,'time',return_value=job.RECOVERY_CUTOFF-3600), patch.object(job.signal,'signal'), patch.object(job.signal,'setitimer'), patch.object(job.os,'fstatvfs',return_value=types.SimpleNamespace(f_bavail=10**15,f_frsize=1)), patch.object(job.urllib.request,'urlopen',side_effect=TimeoutError if response_error else lambda *a,**k:Response(body)) as network:
                if legacy_noattempt:
                    with self.assertRaisesRegex(job.JobFailure,'settled_original_requires_distinct_attempt'): job.main()
                    network.assert_not_called()
                elif wrong_inode:
                    with self.assertRaisesRegex(job.JobFailure,'original_artifact_root_identity_changed'): job.main()
                    network.assert_not_called()
                else:
                    self.assertEqual(job.main(),1 if response_error else 0)
                    retry=json.loads((root/'logs'/attempt/'status.json').read_text())
                    self.assertEqual(retry['status'],'FAILED' if response_error else 'VERIFIED')
                    if response_error:
                        self.assertEqual(retry['failureCode'],'TimeoutError')
                        self.assertEqual(retry['artifacts'][0]['networkPhase'],'OPENING_PUBLIC_REVISION_URL')
                        self.assertEqual(network.call_count,1)
                    with self.assertRaises(FileExistsError): job.main()
                self.assertEqual({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in original.iterdir()},old_hashes)
    def test_successful_attempt_has_distinct_receipts_and_leaves_failure_unchanged(self): self.run_attempt()
    def test_failed_attempt_stays_failed_without_overwriting_original(self): self.run_attempt(response_error=True)
    def test_changed_original_root_identity_rejected_before_network(self): self.run_attempt(wrong_inode=True)
    def test_legacy_failed_original_cannot_be_rerun_in_place(self): self.run_attempt(legacy_noattempt=True)
    def test_normal_success_exit_not_caught_as_failure(self):
        with patch.object(job,'main',return_value=0): self.assertEqual(job.cli(),0)
        with patch.object(job,'main',return_value=1): self.assertEqual(job.cli(),1)


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
    def recovery_args(self,path):
        return ['launch_job.py','--job','h039-vision-original','--attempt','h039-vision-recovery-01','--deadline-utc','2026-10-01T02:25:00Z',
                '--expected-root-device','2081','--expected-root-inode','140247041','--receipt',str(path)]
    def test_recovery_proposal_separates_receipts_and_keeps_original_root(self):
        import sys,subprocess
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'proposal.json'
            with patch.object(sys,'argv',self.recovery_args(path)+['--prepare-only']), patch.object(launcher,'remote',return_value=subprocess.CompletedProcess([],0,str(int(launcher.RECOVERY_CUTOFF)-3600)+'\n','')) as remote, patch('builtins.print'):
                self.assertEqual(launcher.main(),0)
            self.assertEqual(remote.call_count,1) # Clock only; never systemd-run.
            proposal=json.loads(path.read_text())
            self.assertEqual(proposal['status'],'READY_FOR_ROOT_REVIEW')
            self.assertEqual(proposal['unit'],'h039-vision-recovery-01.service')
            self.assertEqual(proposal['artifactRoot'],'/data/models-large/h039-vision-original')
            self.assertEqual(proposal['statusPath'],'/data/logs/h039-vision-recovery-01/status.json')
            self.assertEqual(proposal['deadlineEpoch'],launcher.RECOVERY_CUTOFF)
            self.assertEqual(proposal['networkTimeoutSeconds'],180)
    def test_recovery_launch_requires_explicit_root_review_gate(self):
        import sys
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(sys,'argv',self.recovery_args(Path(directory)/'attempt.json')), patch.object(launcher,'remote') as remote:
                with self.assertRaisesRegex(ValueError,'root_review_required'): launcher.main()
            remote.assert_not_called()
    def test_recovery_deadline_after_0225_rejected(self):
        import sys,subprocess
        with tempfile.TemporaryDirectory() as directory:
            argv=self.recovery_args(Path(directory)/'attempt.json')+['--prepare-only']
            argv[argv.index('--deadline-utc')+1]='2026-10-01T02:26:00Z'
            with patch.object(sys,'argv',argv), patch.object(launcher,'remote',return_value=subprocess.CompletedProcess([],0,str(int(launcher.RECOVERY_CUTOFF)-3600)+'\n','')) as remote:
                with self.assertRaisesRegex(ValueError,'deadline_outside_reviewed_recovery_window'): launcher.main()
            self.assertEqual(remote.call_count,1)
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
