"""Focused baseline contract, not a reproduction of the live H018 cause.

Run: python3 -B reports/h018-latch-review03-20260928/test_latch_contract.py
Only in-memory storage and synthetic timestamps; no VM, GPU or service I/O.
"""
import copy
import datetime
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from common.lifecycle_lease import LeaseBusy
from control.hardware_latch import HardwareLatch
from control.node_collectors import HardwareEvidenceCollector
from lifecycle import hardware_policy as policy
from lifecycle.storage_binding import RegisteredStorageBinding

spec = importlib.util.spec_from_file_location('review_owner', ROOT / 'scripts/runtime/mimo/owner.py')
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)
GPU = owner.GPU
BOOT = '11111111-1111-1111-1111-111111111111'
OTHER_BOOT = '22222222-2222-2222-2222-222222222222'
EPOCH = 1790554500.0


def stamp(seconds=0):
    return datetime.datetime.fromtimestamp(EPOCH + seconds, datetime.timezone.utc).isoformat()


def healthy():
    return {'schema_version': 1, 'targets': {}, 'validated': {
        GPU: {'boot_id': BOOT, 'observed_at': stamp(), 'observation_id': 'synthetic-proof'}}}


class Binding:
    def __init__(self, state):
        self.state = state

    def path(self, role, suffix):
        assert (role, suffix) == ('services', policy.STATE_SUFFIX)
        return '/synthetic/' + suffix

    def read_json(self, role, path, *, maximum):
        assert maximum == 65536
        if isinstance(self.state, Exception):
            raise self.state
        return copy.deepcopy(self.state)


class Contract(unittest.TestCase):
    def query(self, state, age=0, boot=BOOT, gpu=GPU):
        return policy.read_latch_status(Binding(state), [gpu], current_boot_id=boot,
                                        wall=lambda: EPOCH + age)

    def owner_query(self, state, age=0, boot=BOOT):
        read = policy.read_latch_status
        with patch.object(RegisteredStorageBinding, 'read_registered', return_value=Binding(state)), \
             patch.object(policy, 'read_latch_status', side_effect=lambda *a, **k:
                          read(*a, **k, wall=lambda: EPOCH + age)):
            return owner.latch(None, boot)

    def positive(self):
        latch = HardwareLatch(healthy())
        latch.observe(GPU, {'state': 'ok', 'freshness': 'fresh', 'age_ms': 0,
            'complete': True, 'boot_id': BOOT, 'observed_at': stamp(1),
            'observation_id': 'synthetic-fault', 'gpu_uuids': [GPU],
            'hardware_faults': {GPU: 'gpu_fallen_off_bus'}},
            current_boot_id=BOOT, boot_age_seconds=200)
        return latch

    def test_expiry_changes_availability_not_identity_or_persistent_state(self):
        state = healthy()
        before = copy.deepcopy(state)
        fresh = self.owner_query(state, 15)
        stale = self.query(state, 15.001)
        self.assertIs(fresh['hardware_latched'], False)
        self.assertIsNone(stale['hardware_latched'])
        self.assertEqual(fresh['identity'], stale['identity'])
        with self.assertRaisesRegex(owner.OwnerRefusal, '^owned_gpu_latch_unproven$'):
            self.owner_query(state, 15.001)
        self.assertEqual(state, before)

    def test_unknown_cases_all_remain_closed(self):
        missing = {'schema_version': 1, 'targets': {}}
        for state, age, boot in [(healthy(), -1, BOOT), (healthy(), 0, OTHER_BOOT),
                                 (missing, 0, BOOT), ({'corrupt': True}, 0, BOOT),
                                 (OSError('synthetic-unreadable'), 0, BOOT)]:
            with self.subTest(state=type(state).__name__, age=age, boot=boot):
                self.assertIsNone(self.query(state, age, boot)['hardware_latched'])
                with self.assertRaisesRegex(owner.OwnerRefusal, '^owned_gpu_latch_unproven$'):
                    self.owner_query(state, age, boot)
        self.assertIsNone(self.query(healthy(), gpu=policy.GPU_UUIDS[0])['hardware_latched'])

    def test_positive_wins_over_expired_proof_and_inherited_boot(self):
        state = self.positive().export_state()
        for boot in (BOOT, OTHER_BOOT):
            result = self.query(state, 1000, boot)
            self.assertIs(result['hardware_latched'], True)
            self.assertEqual(result['reason'], 'hardware_fault')
            self.assertEqual(result['hardware_latched_boot_id'], BOOT)
            with self.assertRaisesRegex(owner.OwnerRefusal, '^owned_gpu_latch_unproven$'):
                self.owner_query(state, 1000, boot)

    def test_same_boot_exact_healthy_receipt_cannot_clear_positive(self):
        latch = self.positive()
        before = latch.export_state()
        result = latch.validate_required(GPU, current_boot_id=BOOT,
            receipt={'observed_at': stamp(2), 'observation_id': 'synthetic-exact'})
        self.assertIs(result['hardware_latched'], True)
        self.assertEqual(latch.export_state(), before)

    def test_contention_can_leave_persisted_proof_stale_despite_fresh_collector(self):
        # A conditional source mechanism, not evidence that H018 held this lease.
        persisted = healthy()
        gpu = types.SimpleNamespace(gpu_uuid=GPU, last_proof=({
            'gpu_uuid': GPU, 'boot_id': BOOT, 'observed_at': stamp(16),
            'observation_id': 'synthetic-fresh-but-unpublished'}, 116))
        collector = HardwareEvidenceCollector(types.SimpleNamespace(last_proof=None), [gpu])
        with patch('common.lifecycle_lease.acquire_lease', side_effect=LeaseBusy()) as lease, \
             patch('control.node_observation.production_binding') as binding:
            with self.assertRaises(LeaseBusy):
                collector(2)
            lease.assert_called_once_with(blocking=False)
            binding.assert_not_called()
        self.assertEqual(persisted, healthy())
        with self.assertRaisesRegex(owner.OwnerRefusal, '^owned_gpu_latch_unproven$'):
            self.owner_query(persisted, 16)


if __name__ == '__main__':
    unittest.main(verbosity=2)
