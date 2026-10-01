#!/usr/bin/env python3
"""Synthetic host producer/transport fixtures. No Podman, systemd, nft or native acceptance."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
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


class InspectedLaunch(unittest.TestCase):
    def fixture(self, path):
        binding = {'nonce': 'a' * 64, 'runId': 'probe-run', 'sessionId': 'session-1',
                   'workspace': '/fixture/workspace', 'profileDir': '/fixture/profile',
                   'sources': {'synthetic': 'b' * 64}}
        mounts = [{'source': '/fixture/mount-' + str(n), 'destination': '/native/mount-' + str(n),
                   'rw': n < 2, 'type': 'bind'} for n in range(7)]
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
            binding, args, _, _, _, _ = self.fixture(path)
            args[1] = str(path.parent) + ':/exposed:ro,rprivate'
            with patch.object(receipts, 'capture') as capture:
                with self.assertRaises(ValueError): receipts.inspect_launch('/fixture/podman', 'fixture', args, (path, binding))
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
             patch.object(guard.os, 'execv', exec_capture):
            with self.assertRaises(ExecCaptured): guard.main()
        self.assertEqual(captured['path'], '/usr/bin/systemd-run')
        self.assertEqual(captured['argv'][1:7], ['--user','--scope','--quiet','--collect','--expand-environment=no','--slice=aiharnesstasks.slice'])
        self.assertEqual(captured['argv'][-4:], ['--inside-scope','--',str(supervisor),'fixture'])
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
        with patch.object(sys, 'argv', ['guard','--inside-scope','--',str(supervisor),'fixture']), \
             patch.object(guard, 'verify', return_value=prefix), patch.object(Path, 'read_text', read), \
             patch('runpy.run_path', return_value={'publish_egress': lambda p: calls.append(('egress', p))}), \
             patch.object(guard.os, 'execv', execute):
            with self.assertRaises(ExecCaptured): guard.main()
        self.assertEqual(calls[0], ('egress', prefix)); self.assertEqual(calls[1][2], [sys.executable,str(supervisor),'fixture'])
        with patch.object(sys, 'argv', ['guard','--inside-scope','--',str(supervisor),'fixture']), \
             patch.object(guard, 'verify', return_value=prefix), patch.object(Path, 'read_text', return_value='0::/wrong/scope\n'), \
             patch.object(guard.os, 'execv') as execute:
            with self.assertRaises(ValueError): guard.main()
            execute.assert_not_called()


class RealSupervisorFixture(unittest.TestCase):
    def run_supervisor(self, root, raw_exit=7, rm_exit=0, exists_exit=1, stop=False):
        path = Path(root).resolve(); path.chmod(0o700)
        podman = path / 'fake-podman.py'
        podman.write_text('#!' + sys.executable + '\n' + '''import json,os,sys,time
from pathlib import Path
args=sys.argv[1:]
with open(Path(__file__).with_name('calls.jsonl'),'a') as f: f.write(json.dumps({'args':args,'host_receipt_env':any(k.startswith('AI_HARNESS_CODEX_RECEIPT') for k in os.environ)})+'\\n')
if 'run' in args:
 print('synthetic engine bytes',flush=True); print(os.environ['AI_HARNESS_GATEWAY_TOKEN'],file=sys.stderr,flush=True)
 if ''' + repr(stop) + ''': time.sleep(4)
 sys.exit(''' + str(raw_exit) + ''')
if 'rm' in args: sys.exit(''' + str(rm_exit) + ''')
sys.exit(''' + str(exists_exit) + ')\n')
        podman.chmod(0o700)
        wrapper = path / 'wrapper.py'
        wrapper.write_text('''import importlib.util,os,runpy,sys
from pathlib import Path
def load(p):
 s=importlib.util.spec_from_file_location('fixture'+Path(p).stem,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
r=load(sys.argv[1]); supervisor=load(sys.argv[2]); root=Path(sys.argv[3]); podman=sys.argv[4]
binding={'nonce':'a'*64,'runId':'probe-run','sessionId':'session-1'}
producer={'pid':123,'startTicks':'456','uid':os.getuid(),'bootId':'synthetic','cgroupPath':'synthetic'}
runpy.run_path=lambda _: {'channel':lambda:(root,binding),'process_identity':lambda:producer,'inspect_launch':lambda *args:{'container':{'id':'c'*64}},'publish_settlement':r.publish_settlement}
sys.argv=['supervisor',podman,'--remote=false','--cgroup-manager=systemd','run']
os._exit(supervisor.main())
''')
        env = dict(os.environ, AI_HARNESS_GATEWAY_TOKEN='synthetic-token-not-a-secret', AI_HARNESS_CODEX_RECEIPT_DIR=str(path), AI_HARNESS_CODEX_RECEIPT_NONCE='a' * 64)
        command = [sys.executable,str(wrapper),str(DEPLOY/'engine/codex_receipts.py'),str(DEPLOY/'engine/redact-acp.py'),str(path),str(podman)]
        if stop:
            process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            deadline = time.monotonic() + 2
            while not (path / 'calls.jsonl').exists() and time.monotonic() < deadline: time.sleep(0.01)
            process.terminate(); stdout, stderr = process.communicate(timeout=8)
            result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        else:
            result = subprocess.run(command, env=env, capture_output=True, timeout=8)
        value = receipts.read_private(path / 'settlement.json')
        calls = [json.loads(line) for line in (path / 'calls.jsonl').read_text().splitlines()]
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


if __name__ == '__main__':
    unittest.main(verbosity=2)
