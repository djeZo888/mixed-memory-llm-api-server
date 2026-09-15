#!/usr/bin/env python3
"""Local standard-library tests; no Docker, SSH or actual /data accesses."""
import importlib.util
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('pull_image', Path(__file__).with_name('pull_image.py'))
pull = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pull)


class ImagePullTests(unittest.TestCase):
    def image(self):
        return {'Id': pull.CONFIG_ID, 'RepoDigests': [pull.IMAGE], 'Os': 'linux',
                'Architecture': 'amd64', 'Size': 1000, 'source_revision': pull.SOURCE}

    def test_narrow_metadata_and_config_manifest_distinction(self):
        proof = pull.expected_content_proof()
        self.assertEqual(pull.narrow_image(json.dumps(self.image()), proof)['Id_kind'], 'config_digest')
        item = self.image()
        item['Id'] = pull.MANIFEST_ID
        self.assertEqual(pull.narrow_image(json.dumps(item), proof)['Id_kind'], 'platform_manifest_digest')
        with self.assertRaises(pull.ImageStop):
            pull.narrow_image(json.dumps(item), {})
        for field, wrong in [('Id', 'sha256:unknown'), ('Architecture', 'arm64'),
                             ('RepoDigests', []), ('source_revision', 'unknown'), ('Size', True)]:
            item = self.image()
            item[field] = wrong
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                pull.narrow_image(json.dumps(item), proof)

    def test_rejects_environment_and_only_emits_approved_digest(self):
        item = self.image()
        item['Env'] = ['SECRET=sentinel']
        with self.assertRaises(RuntimeError):
            pull.narrow_image(json.dumps(item), pull.expected_content_proof())
        item = self.image()
        item['RepoDigests'].append('unrelated@sha256:unused')
        self.assertEqual(pull.narrow_image(json.dumps(item), pull.expected_content_proof())['RepoDigests'], [pull.IMAGE])

    def test_command_scope_is_pinned_and_local(self):
        command = pull.docker_command(77, 'pull', '--platform', 'linux/amd64', pull.IMAGE)
        self.assertEqual(command, ['/usr/bin/docker', '--config', '/proc/self/fd/77/docker-config',
                                   '--host', 'unix:///run/docker.sock', 'pull', '--platform',
                                   'linux/amd64', pull.IMAGE])
        self.assertNotIn('.Config.Env', pull.INSPECT_TEMPLATE)
        self.assertNotIn('json .Config', pull.INSPECT_TEMPLATE)
        self.assertEqual(pull.content_command(pull.CONFIG_ID), ['/usr/bin/ctr', '--address',
                         '/run/containerd/containerd.sock', '--namespace', 'moby', 'content', 'get', pull.CONFIG_ID])
        with self.assertRaises(pull.ImageStop):
            pull.content_command('sha256:foreign')

    def test_stored_metadata_hashes_descriptors_and_public_output(self):
        for architecture in ('amd64', 'arm64'):
            config = json.dumps({'os': 'linux', 'architecture': architecture, 'config': {
                'Labels': {'org.opencontainers.image.revision': pull.SOURCE},
                'Env': ['PRIVATE_SENTINEL=never_emitted']}}).encode()
            config_id = 'sha256:' + hashlib.sha256(config).hexdigest()
            manifest = json.dumps({'schemaVersion': 2, 'config': {'digest': config_id, 'size': len(config)}}).encode()
            with patch.multiple(pull, CONFIG_ID=config_id, CONFIG_BYTES=len(config),
                                MANIFEST_ID='sha256:' + hashlib.sha256(manifest).hexdigest(),
                                MANIFEST_BYTES=len(manifest)):
                if architecture == 'arm64':
                    with self.assertRaisesRegex(pull.ImageStop, 'descriptor/platform/source'):
                        pull.verify_stored_metadata(manifest, config)
                    continue
                proof = pull.verify_stored_metadata(manifest, config)
                self.assertEqual(proof, pull.expected_content_proof())
                self.assertNotIn('PRIVATE_SENTINEL', json.dumps(proof))
                with self.assertRaisesRegex(pull.ImageStop, 'computed SHA256'):
                    pull.verify_stored_metadata(manifest, config[:-1] + b'x')
                with self.assertRaisesRegex(pull.ImageStop, 'length'):
                    pull.verify_stored_metadata(manifest + b'x', config)

    def test_verify_only_never_pulls_and_preserves_successful_pull_lineage(self):
        proof = pull.expected_content_proof()
        socket = SimpleNamespace(st_uid=0, st_mode=pull.stat.S_IFSOCK, st_dev=1, st_ino=2)
        bindings = {
            'verify_provenance': Mock(), 'storage_module': Mock(return_value=Mock()),
            'mount_ids': Mock(return_value=['1', '2']), 'open_directory': Mock(return_value=(55, {})),
            'protected_subdir': Mock(return_value=56), 'safe_regular': Mock(),
            'previous_status': Mock(return_value={'pull_exit_code': 0, 'pull_pid': 123, 'state': 'STOP'}),
            'atomic_status': Mock(), 'identities_unchanged': Mock(),
            'read_content': Mock(return_value=b'metadata'), 'verify_stored_metadata': Mock(return_value=proof),
        }
        with ExitStack() as stack:
            for name, value in bindings.items():
                stack.enter_context(patch.object(pull, name, value))
            for name, value in {'geteuid': 0, 'umask': 0, 'fstat': socket, 'stat': socket,
                                'lstat': socket, 'open': 57, 'listdir': [], 'write': 0,
                                'fsync': None, 'close': None, 'statvfs': SimpleNamespace(
                                    f_bavail=10 * 1024**3, f_frsize=1)}.items():
                stack.enter_context(patch.object(pull.os, name, return_value=value))
            stack.enter_context(patch.object(pull.fcntl, 'flock'))
            stack.enter_context(patch.object(pull.subprocess, 'run'))
            stack.enter_context(patch.object(pull.subprocess, 'check_output', side_effect=[
                '/data/docker', json.dumps(self.image())]))
            popen = stack.enter_context(patch.object(pull.subprocess, 'Popen'))
            result = pull.run(verify_only=True)
        popen.assert_not_called()
        self.assertEqual(result['state'], 'COMPLETE')
        self.assertEqual(result['verification_mode'], 'read_only')
        self.assertEqual(result['prior_attempt']['pull_pid'], 123)
        self.assertEqual(result['prior_attempt']['pull_exit_code'], 0)
        self.assertEqual(bindings['read_content'].call_count, 2)
        bindings['verify_stored_metadata'].assert_called_once_with(b'metadata', b'metadata')

    def test_environment_does_not_inherit_docker_or_tokens_or_repurpose_home(self):
        with patch.dict(os.environ, {'DOCKER_HOST': 'tcp://foreign', 'TOKEN': 'sentinel',
                                     'HOME': '/unchanged'}, clear=True):
            env = pull.command_environment(77)
        self.assertEqual(env['HOME'], '/unchanged')
        self.assertNotIn('TOKEN', env)
        self.assertNotIn('DOCKER_HOST', env)
        for key in ('DOCKER_CONFIG', 'TMPDIR', 'XDG_CACHE_HOME'):
            self.assertTrue(env[key].startswith('/proc/self/fd/77/'))

    def test_directory_walk_rejects_symlink_and_detects_replacement(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw).resolve()
            target = base / 'target'
            target.mkdir()
            (base / 'link').symlink_to(target)
            with self.assertRaises(OSError):
                pull.open_directory(base / 'link')
            fd, identities = pull.open_directory(target)
            try:
                pull.identities_unchanged(identities)
                target.rename(base / 'old')
                target.mkdir()
                with self.assertRaises(RuntimeError):
                    pull.identities_unchanged(identities)
            finally:
                os.close(fd)

    def test_status_is_atomic_and_cannot_follow_destination_link(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            outside = base / 'outside'
            outside.write_text('unchanged')
            (base / 'status.json').symlink_to(outside)
            fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with self.assertRaises(OSError):
                    pull.atomic_status(fd, {'state': 'PULLING'})
                (base / 'status.json').unlink()
                pull.atomic_status(fd, {'task': 'Q38A', 'image_reference': pull.IMAGE, 'state': 'PULLING'})
            finally:
                os.close(fd)
            self.assertEqual(outside.read_text(), 'unchanged')
            self.assertFalse((base / 'status.json').is_symlink())
            self.assertEqual(json.loads((base / 'status.json').read_text())['state'], 'PULLING')
            self.assertEqual(list(base.glob('.image-status-*')), [])

    def test_child_stop_terminates_only_own_process(self):
        child = Mock()
        child.poll.return_value = None
        pull.stop_child(child)
        child.terminate.assert_called_once_with()
        child.kill.assert_not_called()
        child.wait.assert_called_once_with(timeout=10)

    def test_inherited_setgid_directory_keeps_root_only_access(self):
        for uid, mode, accepted in ((0, 0o700, True), (0, 0o2700, True),
                                    (0, 0o2770, False), (1000, 0o2700, False)):
            with self.subTest(uid=uid, mode=oct(mode)), \
                    patch.object(pull.os, 'mkdir', side_effect=FileExistsError), \
                    patch.object(pull.os, 'open', return_value=77), \
                    patch.object(pull.os, 'close'), \
                    patch.object(pull.os, 'fstat', return_value=SimpleNamespace(
                        st_uid=uid, st_mode=pull.stat.S_IFDIR | mode)):
                if accepted:
                    self.assertEqual(pull.protected_subdir(22, 'image'), 77)
                else:
                    with self.assertRaises(pull.ImageStop):
                        pull.protected_subdir(22, 'image')

    def test_guard_failure_cancels_the_pull(self):
        child = Mock()
        child.poll.return_value = None
        guard = Mock(side_effect=pull.ImageStop('mount identity changed'))
        with self.assertRaisesRegex(pull.ImageStop, 'mount identity changed'):
            pull.monitor_pull(child, guard, Mock())
        child.terminate.assert_called_once_with()
        child.wait.assert_called_once_with(timeout=10)

    def test_timeout_cancels_the_pull_without_waiting(self):
        child = Mock()
        child.poll.return_value = None
        with patch.object(pull.time, 'monotonic', side_effect=[0, 11]):
            with self.assertRaisesRegex(pull.ImageStop, 'bounded pull timeout'):
                pull.monitor_pull(child, Mock(), Mock(), timeout=10)
        child.terminate.assert_called_once_with()

    def test_reviewed_provenance(self):
        pull.verify_provenance()


if __name__ == '__main__':
    unittest.main()
