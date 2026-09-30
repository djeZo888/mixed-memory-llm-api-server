"""Focused H019 borrowed-path review. Run with isolated candidate on PYTHONPATH."""
import contextlib
import copy
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests.test_mimo_owner import LatchRefreshTests, o


class IndependentNestedLeaseTests(unittest.TestCase):
    def setUp(self):
        self.fixture = LatchRefreshTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_borrowed_positive_fault_retained(self):
        from control.hardware_latch import HardwareLatch
        from tests.test_hardware_latch import inventory
        f = self.fixture
        f.store.state['validated'] = {}
        latch = HardwareLatch(f.store.state)
        for second in (0, 5):
            latch.observe(o.GPU, inventory(second, uuids=[]), current_boot_id=f.boot, boot_age_seconds=150)
        f.store.state = latch.export_state()
        self.assertTrue(f.store.state['targets'][o.GPU]['hardware_latched'])
        before = copy.deepcopy(f.store.state)
        with f.h.acquire_lease(blocking=False) as lease, f.borrowed_scope():
            with self.assertRaises(o.OwnerRefusal):
                o.latch(f.h, f.boot, evidence=f.evidence, lease=lease)
            lease.validate()
        self.assertEqual(f.store.state, before)
        self.assertEqual(f.store.writes, 0)

    def test_borrowed_swallowed_alarm_still_refuses_refresh(self):
        f = self.fixture
        def delayed_read():
            time.sleep(.04)
            return copy.deepcopy(f.store.state)
        with f.h.acquire_lease(blocking=False) as lease, f.borrowed_scope():
            with patch.object(f.store, 'read', side_effect=delayed_read), o.bounded(.01):
                with self.assertRaises(o.MandatoryGuardTimeout):
                    o.latch(f.h, f.boot, evidence=f.evidence, lease=lease, deadline=time.monotonic() + .01)
            lease.validate()
        self.assertEqual(f.store.writes, 0)

    def test_actual_startup_refresh_borrows_one_parent_and_reuses_sample(self):
        f = self.fixture
        class CreateReached(Exception):
            pass
        memory = dict(MemTotal=1000, MemAvailable=1000, SwapTotal=100, SwapFree=100)
        manifest = {'memory': {'limit_bytes': 800}, 'container_name': 'fixture'}
        selected = dict(selected_frontier=o.MODEL, manifest_sha256=o.digest(manifest), generation=1)
        acquire = Mock(side_effect=f.h.acquire_lease)
        helper = SimpleNamespace(acquire_lease=acquire,
            MountedStorageGuard=lambda _: contextlib.nullcontext(),
            s=SimpleNamespace(root_payload_guard=lambda: None))
        commands = []
        def read(path):
            if path == o.BASE / 'manifest.json':
                return manifest
            raise FileNotFoundError
        def run(argv, *args):
            commands.append(argv)
            if argv[:2] == ['systemctl', 'show']:
                return 'MainPID=0\nActiveState=inactive\n'
            if any(arg.startswith('--query-gpu=') for arg in argv):
                return o.GPU + ', 100, 8, 40'
            if argv == ['fixture-create']:
                raise CreateReached
            return ''
        with contextlib.ExitStack() as stack:
            for name, value in dict(setup=Mock(return_value=helper), source_preflight=Mock(),
                read=Mock(side_effect=read), require_selected=Mock(return_value=selected),
                unit_identity=Mock(return_value={'pid': 1, 'invocation_id': 'fixture'}),
                storage_paths=Mock(), memory=Mock(return_value=memory),
                temperature_limit=Mock(return_value=85), run=Mock(side_effect=run),
                memory_policy=Mock(return_value={}), write=Mock(),
                create_argv=Mock(return_value=['fixture-create']), settle_state=Mock()).items():
                stack.enter_context(patch.object(o, name, value))
            stack.enter_context(f.borrowed_scope())
            with self.assertRaises(CreateReached):
                o.supervise()
        self.assertEqual(acquire.call_count, 1)
        self.assertEqual(f.store.writes, 1)
        self.assertEqual(f.store.state['validated'][o.GPU]['boot_id'], f.boot)
        self.assertNotEqual(f.store.state['validated'][o.GPU]['observation_id'], 'a' * 32)
        self.assertEqual(sum(any(arg.startswith('--query-gpu=') for arg in argv) for argv in commands), 1)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(IndependentNestedLeaseTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
