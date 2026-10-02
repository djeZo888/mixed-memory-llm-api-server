#!/usr/bin/env python3
"""Synthetic host producer/transport fixtures. No Podman, systemd, nft or native acceptance."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
DEPLOY = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


receipts = load('receipt_fixture', DEPLOY / 'engine/codex_receipts.py')
guard = load('scope_fixture', DEPLOY / 'engine/task-egress.py')


class FileTransport(unittest.TestCase):
    def test_one_shot_ready_and_immutable_first_receipt(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root).resolve(); path.chmod(0o700)
            receipts.write_once(path, 'launch', {'nonce': 'fixture', 'value': 1})
            self.assertEqual(receipts.read_private(path / 'launch.json')['value'], 1)
            self.assertEqual((path / 'launch.ready').stat().st_size, 0)
            self.assertEqual((path / 'launch.json').stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                receipts.write_once(path, 'launch', {'value': 2})
            self.assertEqual(receipts.read_private(path / 'launch.json')['value'], 1)

    def test_symlink_hardlink_mode_and_size_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root).resolve(); path.chmod(0o700)
            receipts.write_once(path, 'safe', {'ok': True})
            target = path / 'safe.json'; link = path / 'link.json'
            link.symlink_to(target)
            with self.assertRaises(ValueError): receipts.read_private(link)
            link.unlink(); os.link(target, link)
            with self.assertRaises(ValueError): receipts.read_private(target)
            link.unlink(); target.chmod(0o644)
            with self.assertRaises(ValueError): receipts.read_private(target)
            target.chmod(0o600); target.write_text('x' * 32769)
            with self.assertRaises(ValueError): receipts.read_private(target)

    def test_oversize_and_nonfinite_never_publish_ready(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root).resolve(); path.chmod(0o700)
            for value in ({'text': 'x' * 32768}, {'bad': float('nan')}):
                with self.assertRaises(ValueError): receipts.write_once(path, 'bad', value)
                self.assertFalse((path / 'bad.ready').exists())

    def test_inspection_capture_has_real_byte_and_time_bounds(self):
        with tempfile.TemporaryDirectory() as root:
            command = Path(root) / 'fake-inspect.py'
            command.write_text('#!' + sys.executable + '\nimport os,time\nos.write(1,b"x"*2097152)\n')
            command.chmod(0o700)
            with self.assertRaises(ValueError): receipts.capture(str(command), ['inspect'])
            command.write_text('#!' + sys.executable + '\nimport time\ntime.sleep(4)\n')
            start = time.monotonic()
            with self.assertRaises(ValueError): receipts.capture(str(command), ['inspect'], timeout=0.05)
            self.assertLess(time.monotonic() - start, 1.5)

    def test_atomic_publication_failure_never_exposes_json_or_ready(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root).resolve();path.chmod(0o700)
            with patch.object(receipts.os,'write',side_effect=OSError('original disk failure')):
                with self.assertRaises(OSError):receipts.write_once(path,'scope-intent',{'original':True})
            self.assertFalse((path/'scope-intent.json').exists());self.assertFalse((path/'scope-intent.ready').exists())
            with patch.object(receipts.os,'link',side_effect=OSError('atomic link failure')):
                with self.assertRaises(OSError):receipts.write_once(path,'producer',{'original':True})
            self.assertFalse((path/'producer.json').exists());self.assertFalse((path/'producer.ready').exists())

    def test_inspect_setup_error_reaps_actual_spawned_child(self):
        with tempfile.TemporaryDirectory() as root:
            command=Path(root)/'capture-child.py';command.write_text('#!'+sys.executable+'\nimport time\ntime.sleep(4)\n');command.chmod(0o700)
            created=[];actual=subprocess.Popen
            def spawn(*args,**kwargs):
                p=actual(*args,**kwargs);created.append(p);return p
            with patch.object(receipts.subprocess,'Popen',spawn),patch.object(receipts.selectors,'DefaultSelector',side_effect=OSError('selector setup failed')):
                with self.assertRaises(OSError):receipts.capture(str(command),['inspect'])
            self.assertEqual(len(created),1);self.assertIsInstance(created[0].returncode,int)
            with self.assertRaises(ProcessLookupError):os.kill(created[0].pid,0)


class InspectedLaunch(unittest.TestCase):
    def fixture(self, path):
        binding = {'nonce': 'a' * 64, 'runId': 'probe-run', 'sessionId': 'session-1',
                   'workspace': '/fixture/workspace', 'profileDir': '/fixture/profile',
                   'deploymentDir':'/fixture/deploy','imageJobsQualified':False,'sources': {'synthetic': 'b' * 64}}
        ro=lambda src,dst:dict(source=src,destination=dst,rw=False,type='bind')
        mounts=[dict(source='/fixture/profile',destination='/fixture/profile',rw=True,type='bind'),dict(source='/fixture/workspace',destination='/fixture/workspace',rw=True,type='bind'),ro('/fixture/tools/image/image-mcp.mjs','/opt/ai-harness/tools/image/image-mcp.mjs'),ro('/fixture/tools/image/image.mjs','/opt/ai-harness/tools/image/image.mjs'),ro('/fixture/deploy/codex/config.toml','/fixture/profile/codex-home/config.toml'),ro('/fixture/deploy/codex/models.json','/opt/sova/codex/models.json'),ro('/fixture/deploy/codex/skills/sova-local-tools','/fixture/profile/codex-home/skills/sova-local-tools')]
        args = []
        for mount in mounts:
            args += ['--volume', mount['source'] + ':' + mount['destination'] + (':rw,rprivate' if mount['rw'] else ':ro,rprivate')]
        identity = {'pid': 123, 'startTicks': '456', 'uid': os.getuid(), 'bootId': 'fixture', 'cgroupPath': '/fixture'}
        native = {'Id': 'c' * 64, 'Name': '/ai-harness-' + 'f' * 32, 'Image': 'sha256:' + 'd8841743002e16de1f9269a850a2f06a73055688befec4c309778ca8a4c11aad',
                  'State': {'Running': True, 'Pid': 123}, 'EffectiveCaps': [],
                  'HostConfig': {'CapDrop': ['ALL'], 'SecurityOpt': ['no-new-privileges', 'seccomp=/fixture/profile'],
                                 'Privileged': False, 'ReadonlyRootfs': True, 'NetworkMode': 'slirp4netns:allow_host_loopback=true', 'UsernsMode': 'keep-id'},
                  'Config': {'User': str(os.getuid()) + ':' + str(os.getgid()), 'WorkingDir': binding['workspace'],
                             'Env': ['UNTRUSTED_LOG_BODY=must-never-enter-receipt']},
                  'Mounts': [{'Source': m['source'], 'Destination': m['destination'], 'RW': m['rw'], 'Type': m['type']} for m in mounts]}
        image = {'Id': native['Image'], 'Config': {'Labels': {
            'org.opencontainers.image.revision': '064c6b8c737f5b41d171fdda80bd9ef10ad06eb3',
            'org.opencontainers.image.ai-harness.patchset': 'dd0ff12a651db4cc8521cddb8e5094c5a197ca87cef6b7ec797343da67d9f1ec'}}}
        def capture(_, command):
            if command[0] == 'inspect': return json.dumps([native]).encode()
            if command[0] == 'info': return b'true\n'
            return json.dumps([image]).encode()
        receipts.write_once(path, 'producer', receipts.causal((path,binding),'codex-producer-original-v1',producer=identity,containerName='ai-harness-'+'f'*32))
        receipts.write_once(path, 'egress', {'synthetic': True})
        return binding, args, identity, native, image, capture

    def test_observed_fields_only_no_environment_payload(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root).resolve(); path.chmod(0o700)
            binding, args, identity, _, _, capture = self.fixture(path)
            with patch.object(receipts, 'capture', capture), patch.object(receipts, 'process_identity', return_value=identity):
                value = receipts.inspect_launch('/fixture/podman', 'ai-harness-' + 'f' * 32, args, (path, binding))
            self.assertEqual(value['container']['pidStartTicks'], '456')
            self.assertEqual(len(value['container']['mounts']), 7)
            self.assertNotIn('UNTRUSTED_LOG_BODY', json.dumps(value))
            self.assertEqual(receipts.read_private(path / 'launch.json'), value)

    def test_generation_only_and_independent_technical_exact_mounts(self):
        for technical in (False,True):
            with self.subTest(technical=technical), tempfile.TemporaryDirectory() as root:
                path=Path(root).resolve();path.chmod(0o700)
                binding,args,identity,native,image,capture=self.fixture(path)
                binding['imageGenerationQualified']=True
                args=[value.replace('codex/config.toml:','codex/config-generation-only.toml:') for value in args]
                native['Mounts'][4]['Source']='/fixture/deploy/codex/config-generation-only.toml'
                if technical:
                    binding['technicalVisionQualified']=True
                    for name in ('technical-vision-mcp','technical-vision'):
                        source=f'/fixture/tools/technical-vision/{name}.mjs';destination=f'/opt/ai-harness/tools/technical-vision/{name}.mjs'
                        args+=['--volume',source+':'+destination+':ro,rprivate'];native['Mounts'].append(dict(Source=source,Destination=destination,RW=False,Type='bind'))
                with patch.object(receipts,'capture',capture),patch.object(receipts,'process_identity',return_value=identity):
                    result=receipts.inspect_launch('/fixture/podman','ai-harness-'+'f'*32,args,(path,binding))
                self.assertEqual(len(result['container']['mounts']),9 if technical else 7)
                self.assertIn('codex/config-generation-only.toml',receipts.source_profile(binding))
                binding['imageJobsQualified']=True
                with self.assertRaisesRegex(ValueError,'ambiguous'):
                    receipts.inspect_launch('/fixture/podman','ai-harness-'+'f'*32,args,(path,binding))

    def test_v1_v2_environment_is_independently_inspected_and_wrong_pair_fails(self):
        for mode,log in [('post-sampling-token-usage-v1','off,codex_core::session::turn=trace'),('post-sampling-token-usage-v2','off,codex_core::session::turn=trace,codex_core::tasks=info')]:
            with tempfile.TemporaryDirectory() as root:
                path=Path(root).resolve();path.chmod(0o700);binding,args,identity,native,image,capture=self.fixture(path);binding['nativeTraceMode']=mode;native['Config']['Env']+=['RUST_LOG='+log,'LOG_FORMAT=json']
                with patch.object(receipts,'capture',capture),patch.object(receipts,'process_identity',return_value=identity):
                    receipts.inspect_launch('/fixture/podman','ai-harness-'+'f'*32,args,(path,binding))
                self.assertEqual(receipts.read_private(path/'trace-env.json')['environment'],{'RUST_LOG':log,'LOG_FORMAT':'json'})
            with tempfile.TemporaryDirectory() as root:
                path=Path(root).resolve();path.chmod(0o700);binding,args,identity,native,image,capture=self.fixture(path);binding['nativeTraceMode']=mode;native['Config']['Env']+=['RUST_LOG=wrong','LOG_FORMAT=json']
                with patch.object(receipts,'capture',capture),patch.object(receipts,'process_identity',return_value=identity),self.assertRaises(ValueError):
                    receipts.inspect_launch('/fixture/podman','ai-harness-'+'f'*32,args,(path,binding))
                self.assertFalse((path/'launch.ready').exists())

    def test_mount_caps_network_privilege_user_and_image_tamper_refused(self):
        mutations = [lambda c, i: c['Mounts'].pop(), lambda c, i: c.update(EffectiveCaps=['CAP_SYS_ADMIN']),
                     lambda c, i: c['HostConfig'].update(NetworkMode='host'),
                     lambda c, i: c['HostConfig'].update(Privileged=True),
                     lambda c, i: c['Config'].update(User='0:0'), lambda c, i: i.update(Id='sha256:' + '0' * 64),
                     lambda c, i: c['Mounts'].append({'Type':'volume','Source':'/private/oracle','Destination':'/oracle','RW':False}),
                     lambda c, i: c.update(Name='/shared-container')]
        for mutate in mutations:
            with self.subTest(mutation=mutations.index(mutate)), tempfile.TemporaryDirectory() as root:
                path = Path(root).resolve(); path.chmod(0o700)
                binding, args, identity, native, image, capture = self.fixture(path); mutate(native, image)
                with patch.object(receipts, 'capture', capture), patch.object(receipts, 'process_identity', return_value=identity):
                    with self.assertRaises(ValueError): receipts.inspect_launch('/fixture/podman', 'ai-harness-' + 'f' * 32, args, (path, binding))
                self.assertFalse((path / 'launch.ready').exists())

    def test_receipt_root_mount_exposure_refused_before_inspect(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root).resolve(); path.chmod(0o700)
            binding, args, identity, _, _, _ = self.fixture(path)
            args[1] = str(path.parent) + ':/exposed:ro,rprivate'
            with patch.object(receipts, 'capture') as capture, patch.object(receipts,'process_identity',return_value=identity):
                with self.assertRaises(ValueError): receipts.inspect_launch('/fixture/podman', 'ai-harness-'+'f'*32, args, (path, binding))
                capture.assert_not_called()


class ScopeForwarding(unittest.TestCase):
    def test_exact_scope_exec_preserves_private_host_environment_across_process_hop(self):
        # Execute the actual guard's argv/environment seam with a fake Linux policy
        # verifier and fake systemd boundary. This cannot qualify installed systemd.
        class ExecCaptured(Exception): pass
        captured = {}
        def exec_capture(path, argv):
            captured.update(path=path, argv=argv, env=dict(os.environ)); raise ExecCaptured()
        supervisor = DEPLOY / 'engine/redact-acp.py'
        with patch.object(sys, 'argv', ['guard', '--', str(supervisor), 'fixture']), \
             patch.object(guard, 'verify', return_value='fixture/slice'), \
             patch.dict(os.environ, {'AI_HARNESS_CODEX_RECEIPT_DIR': '/private/fixture', 'AI_HARNESS_CODEX_RECEIPT_NONCE': 'a' * 64}), \
             patch.object(guard, 'receipt_module', return_value={'channel':lambda:None}), \
             patch.object(guard.os, 'execv', exec_capture):
            with self.assertRaises(ExecCaptured): guard.main()
        self.assertEqual(captured['path'], '/usr/bin/systemd-run')
        self.assertEqual(captured['argv'][1:7], ['--user','--scope','--quiet','--collect','--expand-environment=no','--slice=aiharnesstasks.slice'])
        self.assertEqual(captured['argv'][-5:], ['--inside-scope','-','--',str(supervisor),'fixture'])
        result = subprocess.run([sys.executable, '-c', 'import os,sys;sys.exit(0 if os.environ.get("AI_HARNESS_CODEX_RECEIPT_DIR")=="/private/fixture" and os.environ.get("AI_HARNESS_CODEX_RECEIPT_NONCE")=="a"*64 else 1)'],
                                env=captured['env'], capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 0); self.assertEqual(result.stdout + result.stderr, b'')

    def test_inside_scope_publishes_before_existing_supervisor_exec_and_wrong_scope_refuses(self):
        class ExecCaptured(Exception): pass
        calls = []
        prefix = 'fixture/slice'; supervisor = DEPLOY / 'engine/redact-acp.py'
        read_text = Path.read_text
        def read(path, *args, **kwargs):
            return '0::/' + prefix + '/test.scope\n' if str(path) == '/proc/self/cgroup' else read_text(path, *args, **kwargs)
        def execute(path, argv): calls.append(('exec', path, argv)); raise ExecCaptured()
        with patch.object(sys, 'argv', ['guard','--inside-scope','-','--',str(supervisor),'fixture']), \
             patch.object(guard, 'verify', return_value=prefix), patch.object(Path, 'read_text', read), \
             patch('runpy.run_path', return_value={'channel':lambda:None,'publish_egress': lambda p: calls.append(('egress', p))}), \
             patch.object(guard.os, 'execv', execute):
            with self.assertRaises(ExecCaptured): guard.main()
        self.assertEqual(calls[0], ('egress', prefix)); self.assertEqual(calls[1][2], [sys.executable,str(supervisor),'fixture'])
        with patch.object(sys, 'argv', ['guard','--inside-scope','-','--',str(supervisor),'fixture']), \
             patch.object(guard, 'verify', return_value=prefix), patch.object(Path, 'read_text', return_value='0::/wrong/scope\n'), \
             patch.object(guard.os, 'execv') as execute:
            with self.assertRaises(ValueError): guard.main()
            execute.assert_not_called()


class RealSupervisorFixture(unittest.TestCase):
    def run_supervisor(self, root, raw_exit=7, rm_exit=0, exists_exit=1, stop=False, fail_phase=None):
        path = Path(root).resolve(); path.chmod(0o700)
        podman = path / 'fake-podman.py'
        podman.write_text('#!' + sys.executable + '\n' + '''import json,os,sys,time
from pathlib import Path
args=sys.argv[1:]
assert Path(__file__).with_name('producer.ready').exists()
with open(Path(__file__).with_name('calls.jsonl'),'a') as f: f.write(json.dumps({'args':args,'host_receipt_env':any(k.startswith('AI_HARNESS_CODEX_RECEIPT') for k in os.environ)})+'\\n')
if 'run' in args:
 time.sleep(0.15)
 print('synthetic engine bytes',flush=True); print(os.environ['AI_HARNESS_GATEWAY_TOKEN'],file=sys.stderr,flush=True)
 if ''' + repr(stop) + ''': time.sleep(4)
 Path(__file__).with_name('run-exiting.ready').write_text(str(os.getpid()))
 sys.exit(''' + str(raw_exit) + ''')
if 'rm' in args: sys.exit(''' + str(rm_exit) + ''')
sys.exit(''' + str(exists_exit) + ')\n')
        podman.chmod(0o700)
        wrapper = path / 'wrapper.py'
        wrapper.write_text('''import importlib.util,os,runpy,sys,subprocess,time
from pathlib import Path
def load(p):
 s=importlib.util.spec_from_file_location('fixture'+Path(p).stem,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
r=load(sys.argv[1]); supervisor=load(sys.argv[2]); root=Path(sys.argv[3]); podman=sys.argv[4]
binding={'nonce':'a'*64,'runId':'probe-run','sessionId':'session-1','sources':{'synthetic':'b'*64}}
def identity(pid=None):
 pid=os.getpid() if pid is None else pid
 q=subprocess.run(['/bin/ps','-p',str(pid),'-o','lstart='],capture_output=True,check=True)
 birth=str(int(time.mktime(time.strptime(q.stdout.decode().strip(),'%a %b %d %H:%M:%S %Y'))))
 return {'pid':pid,'startTicks':birth,'uid':os.getuid(),'bootId':'synthetic-mac-fixture','cgroupPath':'/fixture/scope'}
producer=identity();r.process_identity=identity
r.write_once(root,'scope',r.causal((root,binding),'codex-scope-original-v1',producer=producer,unit='ai-harness-codex-'+'e'*32+'.scope',scope={'inode':root.stat().st_ino,'dev':root.stat().st_dev,'invocationId':'e'*32},parent=producer,creator=producer))
phase=sys.argv[5]
def gate(config,producer,container):
 if phase=='producer':raise OSError('original receipt write failed')
 return r.publish_producer(config,producer,container)
def inspect(*args):
 if phase=='inspect':
  deadline=time.monotonic()+2
  while not (root/'run-exiting.ready').exists() and time.monotonic()<deadline:time.sleep(0.01)
  if not (root/'run-exiting.ready').exists():raise TimeoutError('fixture child did not reach original exit')
  time.sleep(0.05);raise ValueError('original inspection failed after child exit')
 if phase=='inspect-signal':
  os.kill(os.getpid(),15);time.sleep(0.35);raise ValueError('inspection failed during stop')
 return {'container':{'id':'c'*64}}
def cli(config,producer,container,pid):
 # Actual child PID and observed birth; fixture only, no Linux qualification.
 if phase=='cli':raise OSError('original postfork CLI publication failed')
 r.write_once(root,'cli',r.causal(config,'codex-cli-original-v1',producer=producer,containerName=container,child=identity(pid),pgid=os.getpgid(pid)))
runpy.run_path=lambda _: {'channel':lambda:(_ for _ in ()).throw(OSError('bootstrap failed')) if phase=='bootstrap' else (root,binding),'process_identity':identity,'publish_producer':gate,'verify_child_gate':lambda *a:None,'publish_cli':cli,'inspect_launch':inspect,'publish_failure':r.publish_failure,'publish_cli_terminal':r.publish_cli_terminal,'publish_cleanup':r.publish_cleanup,'publish_cleanup_terminal':r.publish_cleanup_terminal,'publish_settlement':r.publish_settlement}
sys.argv=['supervisor',podman,'--remote=false','--cgroup-manager=systemd','run']
os._exit(supervisor.main())
''')
        env = dict(os.environ, AI_HARNESS_GATEWAY_TOKEN='synthetic-token-not-a-secret', AI_HARNESS_CODEX_RECEIPT_DIR=str(path), AI_HARNESS_CODEX_RECEIPT_NONCE='a' * 64)
        command = [sys.executable,str(wrapper),str(DEPLOY/'engine/codex_receipts.py'),str(DEPLOY/'engine/redact-acp.py'),str(path),str(podman),fail_phase or '-']
        if stop:
            process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            deadline = time.monotonic() + 2
            while not (path / 'calls.jsonl').exists() and time.monotonic() < deadline: time.sleep(0.01)
            process.terminate(); stdout, stderr = process.communicate(timeout=8)
            result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        else:
            process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            stdout,stderr=process.communicate(timeout=8)
            result=subprocess.CompletedProcess(command,process.returncode,stdout,stderr)
        value = receipts.read_private(path / 'settlement.json') if (path/'settlement.ready').exists() else None
        calls = [json.loads(line) for line in (path / 'calls.jsonl').read_text().splitlines()] if (path / 'calls.jsonl').exists() else []
        self.last_failure = receipts.read_private(path/'failure.json') if (path/'failure.ready').exists() else None
        self.last_cleanup = receipts.read_private(path/'cleanup.json') if (path/'cleanup.ready').exists() else None
        self.last_producer = receipts.read_private(path/'producer.json') if (path/'producer.ready').exists() else None
        evidence=os.environ.get('H043_FIXTURE_EVIDENCE_DIR')
        if evidence:
            target=Path(tempfile.mkdtemp(prefix='redactor-',dir=evidence));shutil.copytree(path,target,dirs_exist_ok=True)
            (target/'stdout.private').write_bytes(result.stdout);(target/'stderr.private').write_bytes(result.stderr)
            (target/'fixture-result.json').write_text(json.dumps({'argv':command,'cwd':str(Path.cwd()),'pid':process.pid,'actualExit':result.returncode,'reaped':True,'injectedFailurePhase':fail_phase,'qualification':'MAC_SOURCE_FIXTURE_ONLY'}))
        return result, value, calls

    def test_raw_engine_failure_distinct_from_successful_exact_cleanup(self):
        with tempfile.TemporaryDirectory() as root:
            result, value, calls = self.run_supervisor(root)
        self.assertEqual(result.returncode, 7); self.assertEqual(value['engineExitStatus'], 7)
        self.assertTrue(value['cleanupOk']); self.assertEqual(value['rmExit'], 0); self.assertEqual(value['existsExit'], 1)
        self.assertTrue(value['cliReaped'] and value['pipesJoined'])
        name = calls[0]['args'][calls[0]['args'].index('--name')+1]
        self.assertRegex(name, r'^ai-harness-[0-9a-f]{32}$')
        self.assertEqual(calls[1]['args'][-1], name); self.assertEqual(calls[2]['args'][-1], name)
        self.assertTrue(calls[0]['host_receipt_env']); self.assertFalse(calls[1]['host_receipt_env'] or calls[2]['host_receipt_env'])
        self.assertNotIn(b'synthetic-token-not-a-secret', result.stdout + result.stderr)
        self.assertIn(b'[REDACTED]', result.stderr)

    def test_rm_failure_and_exists_present_or_error_never_attest_cleanup(self):
        for rm_exit, exists_exit in ((2,1),(0,0),(0,2)):
            with self.subTest(rm=rm_exit, exists=exists_exit), tempfile.TemporaryDirectory() as root:
                result, value, _ = self.run_supervisor(root, raw_exit=0, rm_exit=rm_exit, exists_exit=exists_exit)
                self.assertEqual(result.returncode, 125); self.assertFalse(value['cleanupOk'])
                self.assertEqual(value['engineExitStatus'], 0)

    def test_stop_ack_does_not_rewrite_raw_engine_exit(self):
        with tempfile.TemporaryDirectory() as root:
            result, value, _ = self.run_supervisor(root, raw_exit=0, stop=True)
        self.assertEqual(result.returncode, 0); self.assertTrue(value['requestedStop'])
        self.assertEqual(value['engineExitStatus'], -15); self.assertTrue(value['cleanupOk'])


    def test_producer_publication_failure_prevents_every_podman_child(self):
        with tempfile.TemporaryDirectory() as root:
            result,value,calls=self.run_supervisor(root,fail_phase='producer')
        self.assertEqual(result.returncode,125);self.assertEqual(calls,[])
        self.assertIsNone(self.last_producer);self.assertEqual(self.last_failure['phase'],'bootstrap')
        self.assertFalse(value['cleanupOk']);self.assertFalse(self.last_cleanup['childCreated'])
        self.assertIsNone(value['rmExit']);self.assertIsNone(value['existsExit'])

    def test_postfork_inspection_failure_never_becomes_success_from_child_exit_zero(self):
        for phase in ('inspect','inspect-signal'):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as root:
                result,value,calls=self.run_supervisor(root,raw_exit=0,fail_phase=phase)
            self.assertEqual(result.returncode,125)
            self.assertEqual(self.last_failure['phase'],'inspect-launch')
            self.assertTrue(value['cleanupOk']);self.assertFalse(value['requestedStop'])
            self.assertTrue(self.last_cleanup['observedError'])
            self.assertEqual(self.last_producer['producer']['pid'],self.last_cleanup['producer']['pid'])
            self.assertTrue(all(c['args'][-1]==self.last_producer['containerName'] for c in calls if 'rm' in c['args'] or 'exists' in c['args']))
            if phase=='inspect':self.assertEqual(value['engineExitStatus'],0)
            else:self.assertIn(value['engineExitStatus'],(0,-15))


    def test_bootstrap_failure_cannot_spawn_or_claim_absence(self):
        with tempfile.TemporaryDirectory() as root:
            result,value,calls=self.run_supervisor(root,fail_phase='bootstrap')
        self.assertEqual(result.returncode,125);self.assertIsNone(value);self.assertEqual(calls,[])
        self.assertIsNone(self.last_cleanup);self.assertIsNone(self.last_producer)

    def test_postfork_cli_receipt_failure_retains_failure_and_reaps_exact_child(self):
        with tempfile.TemporaryDirectory() as root:
            result,value,calls=self.run_supervisor(root,fail_phase='cli')
            self.assertTrue((Path(root)/'cli-terminal.ready').exists())
            self.assertTrue((Path(root)/'rm-terminal.ready').exists())
            self.assertTrue((Path(root)/'exists-terminal.ready').exists())
        self.assertEqual(result.returncode,125);self.assertEqual(self.last_failure['phase'],'spawn')
        self.assertTrue(value['cliReaped']);self.assertTrue(value['cleanupOk'])
        self.assertTrue(self.last_cleanup['observedError']);self.assertFalse(value['requestedStop'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
