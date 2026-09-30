"""Actual mounted guard in a bounded read; synthetic Linux discovery only."""
import copy
from pathlib import Path
import sys
from threading import Barrier, Thread
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_real_storage_io import LocalStorageFixture
from lifecycle import concurrent_profiles as pair, qwen38
from lifecycle.storage_binding import BindingError
from control.adapter import ManagerSession
from control.protocol import Deadline, StorageUnavailable


class ObservationStorageTests(unittest.TestCase):
    def setUp(self):
        self.f = LocalStorageFixture()
        self.addCleanup(self.f.close)
        self.b = self.f.binding

    def profile(self):
        d, _ = qwen38._bound_expected(pair.declared_profile(
            'qwen38-27b-q1-server-480000-yarn4-bf16kv'), self.b)
        d['_storage_binding'] = self.b
        return d

    def test_repeated_real_profile_validation_keeps_path_checks_without_full_discovery_per_path(self):
        d = self.profile()
        before = self.f.full_checks
        for _ in range(32):
            pair.validate(d)
        self.assertEqual(self.f.full_checks - before, 448)
        before = self.f.full_checks
        with self.b.read_observation(self.f.api):
            guard = self.f.guards[-1]
            with patch.object(guard, 'check_path', wraps=guard.check_path) as paths:
                for _ in range(32):
                    pair.validate(d)
                self.assertEqual(paths.call_count, 32 * 13 * 2)
        self.assertEqual(self.f.full_checks - before, 3)
        self.assertTrue(guard._closed)
        # No readiness or profile result is cached by the scope.
        bad = dict(d, launch={**d['launch'], 'context_size': 123})
        with self.b.read_observation(self.f.api), self.assertRaises(Exception):
            pair.validate(bad)

    def test_hidden_mount_and_registry_replacement_fail_during_observation(self):
        for mutation in ('hidden_mount', 'registry'):
            with self.subTest(mutation=mutation):
                old_mounts = self.f.mountinfo
                original = self.f.local('/etc/local-ai-server/storage.json').read_bytes()
                try:
                    with self.assertRaises(BindingError), self.b.read_observation(self.f.api):
                        path = self.b.path('services', 'llm-manager/absent/new.json')
                        self.b.validate_path('services', path)
                        if mutation == 'hidden_mount':
                            self.f.mountinfo += ('9 2 8:9 / ' + self.b.path('services', 'llm-manager')
                                                 + ' rw - ext4 /dev/other rw\n')
                        else:
                            file = self.f.local('/etc/local-ai-server/storage.json')
                            replacement = file.with_suffix('.new')
                            replacement.write_bytes(original)
                            replacement.chmod(0o600)
                            replacement.replace(file)
                        self.b.validate_path('services', path)
                finally:
                    self.f.mountinfo = old_mounts
                self.assertIsNone(self.b._observation_guard())
                self.assertTrue(self.f.guards[-1]._closed)

    def test_symlink_and_role_escape_are_still_rejected(self):
        alias = self.f.local(self.b.path('services', 'alias'))
        alias.symlink_to(self.f.local(self.b.path('logs')))
        with self.b.read_observation(self.f.api):
            for path in (str(alias / 'new.json'), self.b.path('logs', 'outside.json')):
                with self.subTest(path=path), self.assertRaises(BindingError):
                    self.b.validate_path('services', path)

    def test_requested_role_cannot_cross_nested_registered_mount_but_aliases_work(self):
        for layout in ('nested', 'equal', 'single'):
            with self.subTest(layout=layout):
                fixture = LocalStorageFixture(layout=layout)
                try:
                    binding = fixture.binding
                    path = binding.path('models', 'absent/new.json')
                    with binding.read_observation(fixture.api):
                        binding.validate_path('models', path)
                        if layout == 'nested':
                            with self.assertRaisesRegex(BindingError, 'path_crosses_unregistered_mount'):
                                binding.validate_path('data', path)
                        else:
                            binding.validate_path('data', path)
                finally:
                    fixture.close()

    def test_full_exit_failure_cannot_return_observation(self):
        state = {'schema_version': 3, 'slots': {name: {
            'selected': None, 'container': None, 'desired': 'stopped', 'generation': 1}
            for name in ('glm', 'qwen')}}
        session = ManagerSession(self.f.manager, lambda *_: [])
        original = session._observe_slot
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            self.f.lost = True  # topology/capacity stage boundary, unchanged mountinfo
            return result
        with patch.object(self.f.manager, 'read_state', return_value=state), \
                patch.object(session, '_observe_slot', side_effect=changed), \
                self.assertRaises(StorageUnavailable):
            session.observe(Deadline.after(5))
        self.assertIsNone(self.b._observation_guard())
        self.assertTrue(self.f.guards[-1]._closed)

    def test_successive_observations_and_other_threads_do_not_reuse_guard(self):
        barrier = Barrier(2)
        guards, failures = [], []
        def read():
            try:
                with self.b.read_observation(self.f.api):
                    guard = self.b._observation_guard()
                    guards.append(guard)
                    barrier.wait(2)
                    self.b.validate_path('models', self.b.path('models', 'missing'))
                    barrier.wait(2)
                    self.assertIs(self.b._observation_guard(), guard)
            except BaseException as exc:
                failures.append(exc)
        threads = [Thread(target=read) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(5)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(failures, [])
        self.assertIsNot(guards[0], guards[1])
        self.assertIsNone(self.b._observation_guard())
        before = self.f.full_checks
        self.b.verify()
        self.assertEqual(self.f.full_checks, before + 1)
        with self.b.read_observation(self.f.api):
            self.assertNotIn(self.b._observation_guard(), guards)

    def test_exception_and_nested_rejection_restore_full_verification(self):
        with self.assertRaisesRegex(RuntimeError, 'fixture'), self.b.read_observation(self.f.api):
            with self.assertRaises(BindingError), self.b.read_observation(self.f.api):
                self.fail('nested scope admitted')
            raise RuntimeError('fixture')
        self.assertIsNone(self.b._observation_guard())
        before = self.f.full_checks
        self.b.verify()
        self.assertEqual(self.f.full_checks, before + 1)


if __name__ == '__main__':
    unittest.main()
