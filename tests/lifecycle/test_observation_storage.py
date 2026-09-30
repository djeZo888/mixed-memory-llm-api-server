"""Actual mounted guard in an adapter-local read; synthetic Linux discovery only."""
from contextlib import contextmanager
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
from install.storage import StorageError
from lifecycle.storage_binding import BindingError
from control.adapter import ManagerSession, _ObservationStorageBinding
from control.protocol import Deadline, StorageUnavailable


class ObservationStorageTests(unittest.TestCase):
    def setUp(self):
        self.f = LocalStorageFixture()
        self.addCleanup(self.f.close)
        self.b = self.f.binding

    @contextmanager
    def scope(self, fixture=None):
        fixture = fixture or self.f
        wrapper = _ObservationStorageBinding(fixture.binding)
        with wrapper.observation(fixture.api):
            yield wrapper

    def profile(self, binding=None):
        binding = binding or self.b
        d, _ = qwen38._bound_expected(pair.declared_profile(
            'qwen38-27b-q1-server-480000-yarn4-bf16kv'), binding)
        d['_storage_binding'] = binding
        return d

    def state(self):
        return {'schema_version': 3, 'slots': {name: {
            'selected': None, 'container': None, 'desired': 'stopped', 'generation': 1}
            for name in ('glm', 'qwen')}}

    def test_repeated_real_profile_validation_keeps_path_checks_without_full_discovery_per_path(self):
        d = self.profile()
        before = self.f.full_checks
        for _ in range(32):
            pair.validate(d)
        self.assertEqual(self.f.full_checks - before, 448)
        before = self.f.full_checks
        with self.scope() as b:
            d = self.profile(b)
            guard = self.f.guards[-1]
            with patch.object(guard, 'check_path', wraps=guard.check_path) as paths:
                for _ in range(32):
                    pair.validate(d)
                self.assertEqual(paths.call_count, 32 * 13 * 2)
        self.assertEqual(self.f.full_checks - before, 3)
        self.assertTrue(guard._closed)
        with self.scope() as b, self.assertRaises(Exception):
            d = self.profile(b)
            pair.validate(dict(d, launch={**d['launch'], 'context_size': 123}))

    def test_hidden_mount_and_registry_replacement_fail_during_observation(self):
        for mutation in ('hidden_mount', 'registry', 'registry_bytes', 'mount_identity'):
            with self.subTest(mutation=mutation):
                old_mounts = self.f.mountinfo
                file = self.f.local('/etc/local-ai-server/storage.json')
                original = file.read_bytes()
                try:
                    with self.assertRaises(BindingError), self.scope() as b:
                        path = b.path('services', 'llm-manager/absent/new.json')
                        b.validate_path('services', path)
                        if mutation == 'hidden_mount':
                            self.f.mountinfo += ('9 2 8:9 / ' + b.path('services', 'llm-manager')
                                                 + ' rw - ext4 /dev/other rw\n')
                        elif mutation == 'mount_identity':
                            self.f.mountinfo = self.f.mountinfo.replace('2 1 ', '8 1 ')
                        elif mutation == 'registry_bytes':
                            file.write_bytes(original + b' ')
                        else:
                            replacement = file.with_suffix('.new')
                            replacement.write_bytes(original)
                            replacement.chmod(0o600)
                            replacement.replace(file)
                        b.validate_path('services', path)
                finally:
                    self.f.mountinfo = old_mounts
                    file.write_bytes(original)
                self.assertIsNone(b._active_guard())
                self.assertTrue(self.f.guards[-1]._closed)
                self.assertIs(self.f.manager.binding, self.b)

    def test_symlink_and_role_escape_are_still_rejected(self):
        alias = self.f.local(self.b.path('services', 'alias'))
        alias.symlink_to(self.f.local(self.b.path('logs')))
        with self.scope() as b:
            for path in (str(alias / 'new.json'), b.path('logs', 'outside.json')):
                with self.subTest(path=path), self.assertRaises(BindingError):
                    b.validate_path('services', path)

    def test_requested_role_cannot_cross_nested_registered_mount_but_aliases_work(self):
        for layout in ('nested', 'equal', 'single', 'sibling'):
            with self.subTest(layout=layout):
                fixture = LocalStorageFixture(layout=layout)
                try:
                    with self.scope(fixture) as b:
                        path = b.path('models', 'absent/new.json')
                        b.validate_path('models', path)
                        b.validate_path('data', b.path('data', 'absent/new.json'))
                        if layout in ('nested', 'sibling'):
                            with self.assertRaises(BindingError):
                                b.validate_path('data', path)
                        else:
                            b.validate_path('data', path)
                        if layout != 'equal':
                            with self.assertRaises(BindingError):
                                b.validate_path('models', b.path('data', 'absent/new.json'))
                finally:
                    fixture.close()

    def test_full_exit_failure_cannot_return_observation(self):
        session = ManagerSession(self.f.manager, lambda *_: [])
        original = session._observe_slot
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            self.f.lost = True
            return result
        with patch.object(self.f.manager, 'read_state', return_value=self.state()), \
                patch.object(session, '_observe_slot', side_effect=changed), \
                self.assertRaises(StorageUnavailable):
            session.observe(Deadline.after(5))
        self.assertIs(session.manager, self.f.manager)
        self.assertIs(self.f.manager.binding, self.b)
        self.assertTrue(self.f.guards[-1]._closed)

    def test_successive_observations_and_other_threads_do_not_reuse_guard(self):
        barrier = Barrier(2)
        wrappers, guards, failures = [], [], []
        def read():
            try:
                with self.scope() as b:
                    wrappers.append(b)
                    guard = b._active_guard()
                    guards.append(guard)
                    barrier.wait(2)
                    b.validate_path('models', b.path('models', 'missing'))
                    barrier.wait(2)
                    self.assertIs(b._active_guard(), guard)
            except BaseException as exc:
                failures.append(exc)
        threads = [Thread(target=read) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(5)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(failures, [])
        self.assertIsNot(wrappers[0], wrappers[1])
        self.assertIsNot(guards[0], guards[1])
        self.assertTrue(all(b._guard is None for b in wrappers))
        before = self.f.full_checks
        self.b.verify()
        self.assertEqual(self.f.full_checks, before + 1)
        with self.scope() as b:
            self.assertNotIn(b._active_guard(), guards)

    def test_exception_and_nested_rejection_restore_full_verification(self):
        with self.assertRaisesRegex(RuntimeError, 'fixture'), self.scope() as b:
            with self.assertRaises(BindingError), b.observation(self.f.api):
                self.fail('nested scope admitted')
            raise RuntimeError('fixture')
        self.assertIsNone(b._active_guard())
        before = self.f.full_checks
        b.verify()
        self.b.verify()
        self.assertEqual(self.f.full_checks, before + 2)
        with self.scope() as successor:
            self.assertIsNot(successor, b)
            successor.verify()
            successor.validate_path('models', successor.path('models', 'missing'))
        self.assertTrue(all(g._closed for g in self.f.guards))

    def test_another_thread_sees_original_binding_and_wrapper_falls_back_to_full(self):
        failures = []
        with self.scope() as b:
            before = self.f.full_checks
            def read():
                try:
                    self.assertIs(self.f.manager.binding, self.b)
                    self.assertIsNone(b._active_guard())
                    self.b.verify()
                    b.verify()
                except BaseException as exc:
                    failures.append(exc)
            thread = Thread(target=read)
            thread.start()
            thread.join(3)
            self.assertFalse(thread.is_alive())
            self.assertEqual(failures, [])
            self.assertEqual(self.f.full_checks, before + 2)

    def test_session_wrapper_never_replaces_shared_manager_binding_on_exception(self):
        session = ManagerSession(self.f.manager, lambda *_: [])
        before = dict(self.b.__dict__)
        original_run = self.f.manager.run
        with self.assertRaisesRegex(RuntimeError, 'fixture'):
            with session._observation_storage(Deadline.after(5)) as observed:
                self.assertIsNot(observed, self.f.manager)
                self.assertIsNot(observed.binding, self.b)
                self.assertIsNot(observed.binding.storage, self.b.storage)
                self.assertIs(self.f.manager.binding, self.b)
                self.assertIs(self.f.manager.run, original_run)
                raise RuntimeError('fixture')
        self.assertEqual(self.b.__dict__, before)
        self.assertIsNone(observed.binding._guard)
        self.assertTrue(self.f.guards[-1]._closed)

    def test_two_sessions_sharing_manager_observe_independently(self):
        sessions = [ManagerSession(self.f.manager, lambda *_: []) for _ in range(2)]
        with sessions[0]._observation_storage(Deadline.after(5)) as first:
            with sessions[1]._observation_storage(Deadline.after(5)) as second:
                self.assertIsNot(first.binding, second.binding)
                self.assertIsNot(first.binding._active_guard(), second.binding._active_guard())
                self.assertIs(self.f.manager.binding, self.b)
                first.binding.verify()
                second.binding.verify()
            first.binding.verify()
        self.assertTrue(all(g._closed for g in self.f.guards))

    def test_guard_entry_failure_leaves_original_binding_and_closes_descriptors(self):
        original = self.f.mounted_guard
        def failing(storage):
            guard = original(storage)
            self.f.mountinfo = self.f.mountinfo.replace('2 1 ', '8 1 ')
            return guard
        session = ManagerSession(self.f.manager, lambda *_: [])
        with patch.object(self.f.api, 'MountedStorageGuard', side_effect=failing), \
                self.assertRaises(StorageUnavailable):
            session.observe(Deadline.after(5))
        self.assertTrue(self.f.guards[-1]._closed)
        self.assertIs(self.f.manager.binding, self.b)

    def test_source_identity_hash_is_recomputed_inside_observation(self):
        # source_identity hashes every listed source on every call; a read scope
        # must not memoize it or any resulting readiness/acceptance decision.
        for name in pair.source_identity():
            target = self.f.base / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((pair.ROOT / name).read_bytes())
        source = self.f.base / 'scripts/control/adapter.py'
        with patch.object(pair, 'ROOT', self.f.base), self.scope():
            first = pair.source_identity()
            source.write_bytes(source.read_bytes() + b'\n# changed source\n')
            second = pair.source_identity()
            self.assertNotEqual(first, second)
            self.assertNotEqual(first['scripts/control/adapter.py'], second['scripts/control/adapter.py'])

    def test_bounded_runner_is_private_and_restored_after_failure(self):
        class Runner:
            def run(self, *, timeout=30):
                return timeout
        runner = self.b.storage.runner = Runner()
        original = runner.run
        session = ManagerSession(self.f.manager, lambda *_: [])
        with self.assertRaisesRegex(RuntimeError, 'fixture'):
            with session._observation_storage(Deadline.after(5)) as observed:
                scoped = observed.binding.storage.runner
                self.assertIsNot(scoped, runner)
                self.assertEqual(runner.run, original)
                self.assertEqual(runner.run(), 30)
                self.assertLessEqual(scoped.run(), 5)
                raise RuntimeError('fixture')
        self.assertEqual(runner.run, original)
        self.assertEqual(scoped.run(), 30)

    def test_full_guard_entry_and_exit_use_deadline_and_cleanup_on_failure(self):
        class Runner:
            def run(self, *, timeout=30):
                return timeout
        for fail_at in (None, 1, 3):
            with self.subTest(fail_at=fail_at):
                fixture = LocalStorageFixture()
                try:
                    runner = fixture.storage.runner = Runner()
                    session = ManagerSession(fixture.manager, lambda *_: [])
                    original = type(fixture.storage)._snapshot
                    budgets = []
                    def snapshot(storage):
                        budgets.append(storage.runner.run(timeout=30))
                        if len(budgets) == fail_at:
                            raise StorageError('synthetic_full_boundary_failure')
                        return original(storage)
                    with patch.object(type(fixture.storage), '_snapshot', snapshot):
                        if fail_at is None:
                            with session._observation_storage(Deadline.after(5)):
                                pass
                        else:
                            with self.assertRaises(StorageUnavailable):
                                with session._observation_storage(Deadline.after(5)):
                                    pass
                    self.assertEqual(len(budgets), fail_at or 3)
                    self.assertTrue(all(0 < budget <= 5 for budget in budgets))
                    self.assertEqual(runner.run(), 30)
                    self.assertIs(fixture.manager.binding, fixture.binding)
                    self.assertTrue(all(g._closed for g in fixture.guards))
                    with session._observation_storage(Deadline.after(5)) as successor:
                        successor.binding.verify()
                finally:
                    fixture.close()

    def test_observe_routes_both_slots_through_private_wrapper(self):
        session = ManagerSession(self.f.manager, lambda *_: [])
        original = session._observe_slot
        bindings = []
        def inspect_scope(*args, **kwargs):
            b = kwargs['manager'].binding
            self.assertIsNot(b, self.b)
            self.assertIs(self.f.manager.binding, self.b)
            bindings.append(b)
            pair.validate(self.profile(b))
            return original(*args, **kwargs)
        before = self.f.full_checks
        with patch.object(self.f.manager, 'read_state', return_value=self.state()), \
                patch.object(session, '_observe_slot', side_effect=inspect_scope):
            result = session.observe(Deadline.after(5))
        self.assertEqual(set(result['slots']), {'glm', 'qwen'})
        self.assertIs(bindings[0], bindings[1])
        self.assertIsNone(bindings[0]._active_guard())
        self.assertEqual(self.f.full_checks - before, 3)
        self.assertIs(session.manager, self.f.manager)



if __name__ == '__main__':
    unittest.main()
