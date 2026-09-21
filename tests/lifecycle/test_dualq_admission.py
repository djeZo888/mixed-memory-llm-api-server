"""Closed physical modes and real admission seams; synthetic I/O only."""
import copy
import unittest
from unittest.mock import patch

from tests.lifecycle.test_concurrent_profiles import bound, receipt, pair, LifecycleError
from tests.lifecycle.test_concurrent_capacity import MemoryFixture, GIB, resident
from lifecycle import runtime_io


class DualQAdmission(unittest.TestCase):
    def setUp(self):
        self.d = bound(pair.QWEN0_PROFILE)
        self.proof, self.instance = receipt(self.d)

    def check(self):
        self.instance['concurrent_pair_acceptance']['sha256'] = pair.receipt_sha256(self.proof)
        return pair.check_acceptance(self.d, self.instance)

    def test_only_two_exact_physical_pairs(self):
        q1 = bound(pair.QWEN_PROFILE)
        pair.validate_pair(self.d, q1)
        pair.validate_pair(bound(pair.GLM_PROFILE), q1)
        for other in (self.d, bound(pair.GLM_PROFILE)):
            with self.assertRaisesRegex(LifecycleError, 'concurrent_peer_conflict'):
                pair.validate_pair(self.d, other)

    def test_dualq_never_reuses_mixed_receipt_or_qwen1_proof(self):
        self.assertEqual(self.check()['slots']['glm']['deployment'], pair.QWEN0_PROFILE)
        self.proof['modes'].pop('dual-qwen')
        with self.assertRaisesRegex(LifecycleError, 'concurrent_acceptance_modes_mismatch'):
            self.check()
        self.proof, self.instance = receipt(self.d)
        self.proof['modes']['dual-qwen']['slots']['glm'] = copy.deepcopy(
            self.proof['modes']['dual-qwen']['slots']['qwen'])
        with self.assertRaisesRegex(LifecycleError, 'concurrent_capacity_evidence_mismatch'):
            self.check()

    def test_gpu0_qwen_requires_native_auth_and_qwen_gpu_reserve(self):
        slot = self.proof['modes']['dual-qwen']['slots']['glm']
        for key, invalid, code in (
            ('native_auth_checks', {}, 'concurrent_qwen_actual_auth_evidence_required'),
            ('gpu_total_bytes', 300 * GIB, 'concurrent_resource_margin_unaccepted'),
            ('guest_cpu_sharing', 'exclusive', 'concurrent_capacity_evidence_mismatch'),
        ):
            saved = slot[key]
            slot[key] = invalid
            with self.subTest(key=key), self.assertRaisesRegex(LifecycleError, code):
                self.check()
            slot[key] = saved

    def test_shared_masks_do_not_turn_into_exclusive_cpu_claims(self):
        profiles = [pair.declared_profile(name) for name in pair.PROFILES]
        self.assertEqual([p['concurrent_pair']['guest_cpuset'] for p in profiles], ['0-71', '0-7', '0-7'])
        self.assertTrue(all(p['concurrent_pair']['guest_cpu_sharing'] == 'shared' for p in profiles))
        fixture = MemoryFixture()
        fixture.overrides[('/usr/bin/cat', '/sys/devices/system/cpu/online')] = '0-95\n'
        with self.assertRaisesRegex(LifecycleError, 'concurrent_current_cpu_inventory_mismatch'):
            pair.preflight_current(self.d, self.instance, fixture.run)

    def test_current_memory_uses_resident_qwen0_cap_not_glm_cap(self):
        q1 = bound(pair.QWEN_PROFILE, self.d['_storage_binding'])
        q0 = resident('glm')
        q0['Config']['Labels']['io.llmctl.deployment'] = pair.QWEN0_PROFILE
        fixture = MemoryFixture(available=80, free=(20, 95), residents={'glm': 10})
        result = pair.preflight_current(q1, self.instance, fixture.run, residents={'glm': q0})
        self.assertEqual(result['required_host_available_bytes'], 70 * GIB)
        self.assertEqual(result['gpu_required_free_bytes']['glm'], 16 * GIB)
        fixture.available = 69
        with self.assertRaisesRegex(LifecycleError, 'concurrent_current_host_memory_insufficient'):
            pair.preflight_current(q1, self.instance, fixture.run, residents={'glm': q0})

    def test_qwen0_native_capacity_uses_qwen_backend_on_glm_historical_port(self):
        info = {'context_length': 480000, 'tp_size': 1,
                'max_total_num_tokens': 480000, 'max_req_input_len': 479994}
        with patch.object(runtime_io, 'native_capacity_metadata', return_value=info) as read:
            self.assertEqual(pair.native_capacity(self.d)['native_input_limit'], 479994)
            read.assert_called_once_with('http://127.0.0.1:30002/v1',
                self.d['auth']['key_file'], timeout=3, backend='qwen')


if __name__ == '__main__':
    unittest.main()
