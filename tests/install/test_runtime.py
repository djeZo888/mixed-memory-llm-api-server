"""Runtime source fixtures. No real Docker daemon, GPU or model is contacted."""
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from install.core import InstallError, Runner
from install.runtime import RuntimeStage, monitored_process, runtime_inputs, runtime_plan
from install.storage_io import AnchoredRoot


class RuntimeRunner:
    def __init__(self, config):
        self.config, self.calls, self.images = config, [], {}
        self.stage = None
        self.fail_label = None
        self.missing_flag = False
        self.bad_source = False
        self.bad_static = False
        self.git_dirty = False
        self.git_head = ""
        self.root_mismatch = False
        self.skip_build_image = False
        self.probes = 0

    def image(self, name):
        pin = self.stage.pins[name]
        if name == "glm":
            return {"Id": pin['observed_reference_image_id'], "Architecture": "amd64", "Os": "linux",
                    "Config": {"Entrypoint": ["/opt/llama/llama-server"], "Labels": {
                        "org.opencontainers.image.source": pin['source_repository'],
                        "org.opencontainers.image.revision": pin['source_revision'],
                        "org.opencontainers.image.version": pin['source_release'],
                        "local.d1.cuda.architectures": pin['cuda_architectures']}}}
        return {"Id": pin['image_id'], "Architecture": "amd64", "Os": "linux",
                "RepoDigests": [pin['repo_digest']], "Config": {}}

    def install(self, name):
        image = self.image(name)
        pin = self.stage.pins[name]
        self.images[pin['repo_digest'] if name == "qwen" else pin['image_tag']] = image
        self.images[image['Id']] = image

    def run(self, argv, timeout=120, env=None):
        self.calls.append((argv, env))
        if argv[:2] == ["docker", "info"]:
            return "/var/lib/docker" if self.root_mismatch else self.config['data_dir'] + "/docker"
        if argv[:3] == ["docker", "image", "inspect"]:
            if argv[3] not in self.images:
                raise InstallError("command_failed")
            return json.dumps([self.images[argv[3]]])
        if argv[:2] == ["docker", "pull"]:
            self.install("qwen")
            return "fixture pull\n"
        if argv[0] == "git":
            if argv[1] == "rev-parse":
                if not self.git_head:
                    raise InstallError("runtime_command_failed")
                return self.git_head
            if argv[1] == "checkout":
                self.git_head = self.stage.pins['glm']['source_revision']
            if argv[1] == "status":
                return " M README.md" if self.git_dirty else ""
            return ""
        if argv[:2] == ["docker", "build"]:
            if self.fail_label == "build":
                raise InstallError("runtime_command_failed")
            if not self.skip_build_image:
                self.install("glm")
            return "fixture build\n"
        if argv[:2] == ["docker", "run"]:
            self.probes += 1
            if self.fail_label == "probe":
                raise InstallError("runtime_command_failed")
            if argv[-1] == "--version":
                return "version: 0.4.1-dev (build 62, commit b29c606)"
            if argv[-1] == "--help":
                flags = json.loads((ROOT/'configs/runtimes/llama-cpp-v0.4.1-d1.json').read_text())['required_cli_flags']
                return " ".join(flags[:-1] + [flags[-1]+"-unsupported"] if self.missing_flag else flags)
            if argv[-1] == "--list-devices":
                return "Available devices:\n  CUDA0: fixture\n  CUDA1: fixture\n"
            if argv[-1].endswith("source-commit.txt"):
                return "f"*40 if self.bad_source else self.stage.pins['glm']['source_revision']
            if argv[-1].endswith("CMakeCache.txt"):
                values = {"CMAKE_CUDA_ARCHITECTURES":"120a-real", "GGML_CUDA":"ON", "GGML_NATIVE":"OFF",
                          "GGML_BACKEND_DL":"ON", "GGML_CPU_ALL_VARIANTS":"ON", "LLAMA_BUILD_UI":"OFF", "LLAMA_USE_PREBUILT_UI":"OFF"}
                return "\n".join(k+":STRING="+v for k,v in values.items())
            if argv[-1].endswith("build-packages.tsv"):
                return "fixture-package\t1.0"
            if argv[-1].endswith("nvcc-version.txt"):
                return "Cuda compilation tools, release 13.2, V13.2.78"
            if argv[-2] == "-c":
                proof = self.stage._proof("qwen")
                value = {k:copy.deepcopy(proof['static'][k]) for k in ('packages','source_files')}
                value['option_contract'] = proof['fixtures']['option_contract']
                if self.bad_static:
                    value['source_files']['launch_server.py']['sha256'] = 'a'*64
                return "fixture import diagnostic\nI1B_RUNTIME_STATIC=" + json.dumps(value)
        raise AssertionError(repr(argv))


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        # macOS /tmp is a symlink; resolve once before trusted descriptor walk.
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name).resolve() / 'volume'
        self.data.mkdir(mode=0o700)
        self.config = {'data_dir':str(self.data), 'model_set':'glm,qwen', 'expected_gpu_count':2}
        device = self.data.stat().st_dev
        block = {'path':str(self.data),'mount':str(self.data),'uuid':'11111111-2222-4333-8444-555555555555',
                 'fstype':'ext4','device':f'{os.major(device)}:{os.minor(device)}'}
        self.snapshot = {'schema_version':1,'data':dict(block),'models':dict(block),
                         'roots':{'build':str(self.data/'build'),'logs':str(self.data/'logs'),
                                  'state':str(self.data/'services/installer')}}
        self.present = True
        def guard():
            if not self.present:
                raise InstallError('fixture_mount_lost')
            return copy.deepcopy(self.snapshot)
        self.guard = guard
        self.runner = RuntimeRunner(self.config)
        self.stage = RuntimeStage(self.config,self.runner,self.guard,uid=os.getuid())
        self.runner.stage = self.stage

    def test_pins_match_reviewed_source_and_plan_is_readonly(self):
        rows = runtime_plan(self.config)
        self.assertEqual([r['selection'] for r in rows], ['glm','qwen'])
        self.assertEqual(list(self.data.iterdir()), [])
        self.assertEqual(rows[0]['artifact_download_bytes'], 3653618310)
        self.assertEqual(rows[1]['artifact_download_bytes'], 13197815873)

    def test_reuse_real_inspection_and_probes_then_verified_noop(self):
        self.runner.install('glm'); self.runner.install('qwen')
        self.assertFalse(self.stage.check())
        result = self.stage.apply()
        self.assertFalse(result['ready'])
        self.assertTrue(self.stage.check())
        self.assertFalse(any(a[:2] in [['docker','build'],['docker','pull']] for a,_ in self.runner.calls))
        count = self.runner.probes
        self.assertEqual(self.stage.apply(), {'changed':False})
        self.assertEqual(count,self.runner.probes)
        self.assertEqual(result['runtimes'][0]['evidence_class'],'SYNTHETIC_FIXTURE')

    def test_false_marker_is_not_completion(self):
        state = self.data/'services/installer/runtime'
        state.mkdir(parents=True)
        (state/'glm.json').write_text('{"status":"RUNTIME_ARTIFACT_VERIFIED"}')
        (state/'glm.json').chmod(0o600)
        self.assertFalse(self.stage.check())

    def test_mutable_tag_conflict_preserved_not_overwritten(self):
        self.runner.install('glm')
        self.runner.images[self.stage.pins['glm']['image_tag']]['Id']='sha256:'+'a'*64
        with self.assertRaisesRegex(InstallError,'runtime_existing_image_identity_conflict'):
            self.stage.apply()
        self.assertFalse(any(a[:2]==['docker','build'] for a,_ in self.runner.calls))

    def test_pinned_sglang_digest_not_matching_mutable_tag(self):
        self.config['model_set']='qwen'; self.stage.selected=['qwen']
        self.runner.images[self.stage.pins['qwen']['image']] = self.runner.image('qwen')
        with mock.patch('install.runtime.os.fstatvfs') as capacity:
            capacity.return_value = type('V',(),{'f_bavail':1000*1024**3,'f_frsize':1})()
            self.stage.apply()
        pulls=[a for a,_ in self.runner.calls if a[:2]==['docker','pull']]
        self.assertEqual(pulls[0][-1],self.stage.pins['qwen']['repo_digest'])

    def test_image_platform_and_repo_digest_drift_rejected(self):
        self.runner.install('glm'); self.runner.install('qwen'); self.stage.apply()
        self.runner.images[self.stage.pins['qwen']['image_id']]['RepoDigests']=[]
        self.assertFalse(self.stage.check())

    def test_identity_and_evidence_drift_invalidates_record(self):
        self.runner.install('glm'); self.runner.install('qwen'); self.stage.apply()
        record=json.loads((self.data/self.stage._record('glm')).read_text())
        (self.data/record['evidence_files']['version']['path']).write_text('modified')
        self.assertFalse(self.stage.check())

    def test_installed_source_hash_drift_blocks_completion(self):
        self.runner.install('glm'); self.runner.install('qwen'); self.runner.bad_static=True
        with self.assertRaisesRegex(InstallError,'runtime_sglang_source_or_capability_drift'):
            self.stage.apply()
        self.assertFalse((self.data/self.stage._record('qwen')).exists())

    def test_llama_required_flag_boundary_not_substring(self):
        self.runner.install('glm'); self.runner.missing_flag=True
        with self.assertRaisesRegex(InstallError,'runtime_cli_capability_missing'):
            self.stage.apply()

    def test_llama_image_source_must_match_exact_commit(self):
        self.runner.install('glm'); self.runner.bad_source=True
        with self.assertRaisesRegex(InstallError,'runtime_image_source_drift'):
            self.stage.apply()

    def test_daemon_storage_root_mismatch_refused(self):
        self.runner.root_mismatch=True
        with self.assertRaisesRegex(InstallError,'runtime_docker_storage_root_mismatch'):
            self.stage.apply()
        self.assertEqual(list(self.data.iterdir()),[])

    def test_interrupted_probe_preserves_logs_resume_rechecks_image(self):
        self.runner.install('glm');self.runner.install('qwen');self.runner.fail_label='probe'
        with self.assertRaises(InstallError):self.stage.apply()
        before=set((self.data/'logs/installer/runtime').iterdir())
        self.assertFalse((self.data/self.stage._record('glm')).exists())
        self.runner.fail_label=None
        self.stage.apply()
        self.assertTrue(before <= set((self.data/'logs/installer/runtime').iterdir()))
        self.assertTrue(self.stage.check())

    def test_source_build_exact_recipe_identity_and_probes(self):
        self.stage.selected=['glm']
        with mock.patch('install.runtime.os.fstatvfs') as capacity:
            capacity.return_value=type('V',(),{'f_bavail':1000*1024**3,'f_frsize':1})()
            self.stage.apply()
        command=next(a for a,_ in self.runner.calls if a[:2]==['docker','build'])
        self.assertIn('LLAMA_COMMIT='+self.stage.pins['glm']['source_revision'],command)
        self.assertIn('CUDA_DEVEL='+self.stage.pins['glm']['cuda_devel'],command)
        self.assertIn('local.installer.runtime-input='+self.stage._identity('glm'),command)
        self.assertIn('../recipe/Dockerfile',command)
        self.assertTrue(all(e is None or '/proc/self/fd/' in e['TMPDIR'] for _,e in self.runner.calls))

    def test_existing_dirty_source_refused_without_build(self):
        self.stage.selected=['glm'];self.runner.git_head=self.stage.pins['glm']['source_revision'];self.runner.git_dirty=True
        with mock.patch('install.runtime.os.fstatvfs') as capacity:
            capacity.return_value=type('V',(),{'f_bavail':1000*1024**3,'f_frsize':1})()
            with self.assertRaisesRegex(InstallError,'runtime_source_not_clean'):self.stage.apply()
        self.assertFalse(any(a[:2]==['docker','build'] for a,_ in self.runner.calls))

    def test_build_without_result_cannot_complete(self):
        self.stage.selected=['glm'];self.runner.skip_build_image=True
        with mock.patch('install.runtime.os.fstatvfs') as capacity:
            capacity.return_value=type('V',(),{'f_bavail':1000*1024**3,'f_frsize':1})()
            with self.assertRaisesRegex(InstallError,'runtime_result_image_identity_invalid'):self.stage.apply()

    def test_release_recipe_hash_drift_fails_before_any_command(self):
        pins=copy.deepcopy(self.stage.pins);pins['glm']['build_recipe_sha256']['containers/llama-cpp/Dockerfile']='a'*64
        with self.assertRaisesRegex(InstallError,'runtime_release_input_drift'):
            RuntimeStage(self.config,self.runner,self.guard,lock={'runtimes':pins},uid=os.getuid())
        self.assertEqual(self.runner.calls,[])

    def test_mount_loss_refuses_even_error_contract_write(self):
        self.present=False
        with self.assertRaisesRegex(InstallError,'fixture_mount_lost'):self.stage.apply()
        self.assertEqual(list(self.data.iterdir()),[])

    def test_fixture_contract_cannot_verify_with_actual_runner(self):
        self.runner.install('glm');self.runner.install('qwen');self.stage.apply()
        actual_runner=Runner(writable=False)
        actual_runner.run=self.runner.run
        actual_stage=RuntimeStage(self.config,actual_runner,self.guard,uid=os.getuid())
        self.assertFalse(actual_stage.check())


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux /proc FD subprocess integration only')
class MonitoredProcessTest(unittest.TestCase):
    setUp = RuntimeTest.setUp
    def test_real_child_timeout_kills_descendant_and_keeps_anchored_log(self):
        self.data.joinpath('logs').mkdir()
        with AnchoredRoot(self.data,self.guard,uid=os.getuid()) as root:
            with root.open('logs/child.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL) as log:
                script='import os,time; pid=os.fork(); time.sleep(2); open("late-write","w").write("bad"); time.sleep(10)'
                with self.assertRaisesRegex(InstallError,'runtime_command_timeout'):
                    monitored_process([sys.executable,'-c',script],cwd=root,log=log,anchors=[root],env={},timeout=.2,poll=.02)
            time.sleep(2.2)
            self.assertFalse((self.data/'late-write').exists())

    def test_real_child_guard_loss_stops_future_writes(self):
        self.data.joinpath('logs').mkdir()
        def monitored_guard():
            if (self.data/'started').exists():
                raise InstallError('fixture_mount_lost')
            return self.guard()
        with AnchoredRoot(self.data,monitored_guard,uid=os.getuid()) as root:
            with root.open('logs/child.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL) as log:
                script='import time; open("started","w").write("started"); time.sleep(2); open("late-write","w").write("bad")'
                with self.assertRaisesRegex(InstallError,'fixture_mount_lost'):
                    monitored_process([sys.executable,'-c',script],cwd=root,log=log,anchors=[root],env={},timeout=10,poll=.02)
            time.sleep(2.2)
            self.assertFalse((self.data/'late-write').exists())

    def test_successful_parent_cannot_leave_background_writer(self):
        self.data.joinpath('logs').mkdir()
        with AnchoredRoot(self.data,self.guard,uid=os.getuid()) as root:
            with root.open('logs/child.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL) as log:
                script='import os,time; pid=os.fork(); os._exit(0) if pid else None; time.sleep(2); open("late-write","w").write("bad")'
                with self.assertRaisesRegex(InstallError,'runtime_command_descendants_survived'):
                    monitored_process([sys.executable,'-c',script],cwd=root,log=log,anchors=[root],env={},timeout=10,poll=.02)
            time.sleep(2.2)
            self.assertFalse((self.data/'late-write').exists())


if __name__ == '__main__':unittest.main()
