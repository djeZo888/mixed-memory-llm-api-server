#!/usr/bin/env python3
"""Unit-ordered SearXNG startup with fake Podman; no containers or network."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
IMAGE = 'a' * 64
CONTAINER = 'b' * 64
SECRET = 'c' * 64


@unittest.skipIf(os.geteuid() == 0, 'launcher deliberately refuses root')
class SearxngStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='searxng-unit-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.release = self.root / 'release'
        self.bin = self.root / 'bin'
        self.release.mkdir(mode=0o700)
        self.bin.mkdir(mode=0o700)
        (self.release / 'run.sh').write_bytes((SOURCE / 'run.sh').read_bytes())
        (self.release / 'image.id').write_text('sha256:' + IMAGE)
        (self.release / 'run.sh').chmod(0o500)
        (self.release / 'image.id').chmod(0o400)
        sums = ''.join(hashlib.sha256((self.release / name).read_bytes()).hexdigest()
                       + '  ' + name + '\n' for name in ('run.sh', 'image.id'))
        (self.release / 'SHA256SUMS').write_text(sums)
        (self.release / 'SHA256SUMS').chmod(0o400)
        self.secret = self.root / 'service.env'
        self.secret.write_text('SEARXNG_SECRET=' + SECRET + '\n')
        self.secret.chmod(0o600)
        self.settings = {'exists': True, 'id': CONTAINER, 'label': 'searxng',
                         'image': IMAGE, 'status': 'created', 'stop_exit': 0, 'rm_exit': 0}
        self.state = self.bin / 'state.json'
        self.log = self.bin / 'calls.jsonl'
        self.executable('podman', r'''
import json, pathlib, sys
base = pathlib.Path(__file__).resolve().parent
state = json.loads((base / 'state.json').read_text())
a = sys.argv[1:]
with (base / 'calls.jsonl').open('a') as f: f.write(json.dumps(a) + '\n')
if a == ['info', '--format', '{{.Host.Security.Rootless}}']: print('true')
elif a == ['image', 'inspect', 'sha256:' + 'a' * 64, '--format', '{{index .Labels "io.ai-harness.service"}}']: print('searxng')
elif a == ['container', 'exists', 'ai-harness-searxng']: sys.exit(0 if state['exists'] else 1)
elif a == ['inspect', 'ai-harness-searxng', '--format', '{{.Id}}']: print(state['id'])
elif a == ['inspect', state['id'], '--format', '{{index .Config.Labels "io.ai-harness.service"}}']: print(state['label'])
elif a == ['inspect', state['id'], '--format', '{{.Image}}']: print(state['image'])
elif a == ['stop', '--time', '15', state['id']]:
    assert state['status'] == 'created', 'retained post-reboot fixture shape'
    sys.exit(state['stop_exit'])
elif a == ['rm', '--ignore', state['id']]:
    if state['rm_exit']: sys.exit(state['rm_exit'])
    state['exists'] = False
    (base / 'state.json').write_text(json.dumps(state))
elif a and a[0] == 'run':
    assert not state['exists'], 'must remove old container before start'
    assert '--pull=never' in a and '--rm' in a
    assert a[a.index('--name') + 1] == 'ai-harness-searxng'
    assert a[-1] == 'sha256:' + 'a' * 64
else: raise AssertionError(a)
''')
        # Narrow Linux metadata-command equivalents allow the unchanged shell
        # helper to run on macOS too. They check real fixture bytes/permissions.
        self.executable('stat', r'''
import pathlib, sys
assert sys.argv[1:3] == ['-c', '%u'], sys.argv
print(pathlib.Path(sys.argv[3]).stat().st_uid)
''')
        self.executable('find', r'''
import os, pathlib, sys
root = pathlib.Path(sys.argv[1])
for path in (root, *root.rglob('*')):
    st = path.lstat()
    if path.is_symlink() or st.st_mode & 0o022 or st.st_uid != os.getuid():
        print(path)
        break
''')
        self.executable('sha256sum', r'''
import hashlib, pathlib, sys
assert sys.argv[1:] == ['--check', '--status', 'SHA256SUMS'], sys.argv
for line in pathlib.Path('SHA256SUMS').read_text().splitlines():
    digest, name = line.split('  ', 1)
    if hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest() != digest: sys.exit(1)
''')
        self.executable('ss', r'''
import sys
assert sys.argv[1:] == ['-H', '-lnt', '( sport = :8082 )'], sys.argv
''')
        self.env = dict(os.environ, PATH=str(self.bin) + ':/usr/bin:/bin', SEARXNG_SECRET=SECRET)

    def executable(self, name, text):
        path = self.bin / name
        path.write_text('#!' + sys.executable + '\n' + text)
        path.chmod(0o700)

    def startup(self):
        """Execute actual unit pre/start directives, stopping on first failure."""
        self.state.write_text(json.dumps(self.settings))
        results = []
        for line in (SOURCE / 'ai-harness-searxng.service.in').read_text().splitlines():
            if line.startswith(('ExecStartPre=', 'ExecStart=')):
                args = shlex.split(line.split('=', 1)[1])
                self.assertEqual(args[0], '%h/.ai-harness-searxng/current/run.sh')
                result = subprocess.run(['/bin/bash', str(self.release / 'run.sh'), *args[1:]],
                                        env=self.env, capture_output=True, text=True, timeout=10)
                results.append(result)
                if result.returncode: break
        return results

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def lifecycle(self):
        return [a for a in self.calls() if a[0] in ('stop', 'rm', 'run')]

    def test_unit_requires_guarded_cleanup_before_start(self):
        lines = (SOURCE / 'ai-harness-searxng.service.in').read_text().splitlines()
        pre = 'ExecStartPre=%h/.ai-harness-searxng/current/run.sh stop'
        start = 'ExecStart=%h/.ai-harness-searxng/current/run.sh run'
        self.assertEqual([v for v in lines if v.startswith('ExecStartPre=')], [pre])
        self.assertLess(lines.index(pre), lines.index(start))
        self.assertIn('EnvironmentFile=%h/.config/ai-harness-searxng/service.env', lines)
        self.assertIn('ExecStop=%h/.ai-harness-searxng/current/run.sh stop', lines)

    def test_owned_created_leftover_removed_by_exact_id_before_start_and_files_preserved(self):
        before = {p.name: p.read_bytes() for p in self.release.iterdir()}
        secret_before = self.secret.read_bytes()
        results = self.startup()
        self.assertEqual([r.returncode for r in results], [0, 0], [r.stderr for r in results])
        lifecycle = self.lifecycle()
        self.assertEqual(lifecycle[:2], [['stop', '--time', '15', CONTAINER], ['rm', '--ignore', CONTAINER]])
        self.assertEqual([a[0] for a in lifecycle], ['stop', 'rm', 'run'])
        self.assertFalse(any('--force' in a or '-f' in a for a in lifecycle))
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.release.iterdir()})
        self.assertEqual(self.secret.read_bytes(), secret_before)
        self.assertFalse(any(SECRET in ' '.join(a) for a in self.calls()))

    def test_cleanup_needs_no_secret_but_start_still_requires_it(self):
        self.env.pop('SEARXNG_SECRET')
        results = self.startup()
        self.assertEqual([r.returncode for r in results], [0, 1])
        self.assertIn('Missing/invalid protected SEARXNG_SECRET.', results[1].stderr)
        self.assertEqual(self.lifecycle(), [['stop', '--time', '15', CONTAINER],
                                           ['rm', '--ignore', CONTAINER]])

    def test_foreign_container_refuses_before_any_lifecycle_action(self):
        self.settings['label'] = 'foreign'
        results = self.startup()
        self.assertEqual(len(results), 1)
        self.assertNotEqual(results[0].returncode, 0)
        self.assertIn('Unowned container name conflict.', results[0].stderr)
        self.assertEqual(self.lifecycle(), [])
        self.assertTrue(json.loads(self.state.read_text())['exists'])

    def test_wrong_image_refuses_before_any_lifecycle_action(self):
        self.settings['image'] = 'd' * 64
        results = self.startup()
        self.assertEqual(len(results), 1)
        self.assertNotEqual(results[0].returncode, 0)
        self.assertIn('Container image differs from release; refusing mutation.', results[0].stderr)
        self.assertEqual(self.lifecycle(), [])
        self.assertTrue(json.loads(self.state.read_text())['exists'])

    def test_invalid_identity_refuses_without_cleanup_or_start(self):
        self.settings['id'] = 'not-an-exact-container-id'
        results = self.startup()
        self.assertEqual(len(results), 1)
        self.assertNotEqual(results[0].returncode, 0)
        self.assertIn('Invalid container identity.', results[0].stderr)
        self.assertEqual(self.lifecycle(), [])

    def test_failed_stop_blocks_remove_and_start(self):
        self.settings['stop_exit'] = 125
        results = self.startup()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].returncode, 125)
        self.assertEqual(self.lifecycle(), [['stop', '--time', '15', CONTAINER]])
        self.assertTrue(json.loads(self.state.read_text())['exists'])

    def test_failed_remove_blocks_start(self):
        self.settings['rm_exit'] = 125
        results = self.startup()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].returncode, 125)
        self.assertEqual(self.lifecycle(), [['stop', '--time', '15', CONTAINER],
                                           ['rm', '--ignore', CONTAINER]])
        self.assertTrue(json.loads(self.state.read_text())['exists'])

    def test_no_leftover_starts_without_stop_or_remove(self):
        self.settings['exists'] = False
        results = self.startup()
        self.assertEqual([r.returncode for r in results], [0, 0], [r.stderr for r in results])
        self.assertEqual([a[0] for a in self.lifecycle()], ['run'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
