"""Offline migration gates; synthetic proofs establish no live acceptance."""
import copy
import unittest
from tests.lifecycle.test_concurrent_profiles import bound, receipt, pair, LifecycleError

class QwenMigration(unittest.TestCase):
    def setUp(self):
        self.d = bound(pair.QWEN_PROFILE)
        self.value, self.instance = receipt(self.d)
        self.binding = self.d['_storage_binding']
        self.path = self.binding.path('data', 'services/llm-manager/evidence/h008-qwen1-proof.json')

    def check(self):
        self.instance['concurrent_pair_acceptance']['sha256'] = pair.receipt_sha256(self.value)
        return pair.check_acceptance(self.d, self.instance)

    def test_old_receipt_is_not_activation_authority(self):
        del self.value['h008_transition']
        with self.assertRaisesRegex(LifecycleError, 'h008_fresh_migration_proof_required'):
            self.check()

    def test_fresh_proof_binds_source_uuid_native_capacity_and_auth(self):
        original = copy.deepcopy(self.binding.documents[self.path])
        for field, invalid in [('gpu_uuid', 'GPU-69acfa26-8b60-61b5-702d-aee252c163cc'),
                ('native_pool_tokens', 65536), ('native_input_limit', 65530),
                ('source_sha256', {}), ('auth', 'NOT_TESTED'), ('short_output', 'FAIL')]:
            bad = copy.deepcopy(original); bad[field] = invalid
            self.binding.documents[self.path] = bad
            self.value['h008_transition']['proof_sha256'] = pair.receipt_sha256(bad)
            with self.subTest(field=field), self.assertRaisesRegex(LifecycleError, 'h008_fresh_migration_proof_invalid'):
                self.check()

    def test_occupied_context_cannot_be_copied_from_old_slot(self):
        self.value['modes']['dual-qwen']['slots']['qwen']['largest_occupied_context'] = 480000
        with self.assertRaisesRegex(LifecycleError, 'h008_slot_measurement_mismatch'):
            self.check()

    def test_top_receipt_rehash_cannot_rewrite_unchanged_binding_or_slot(self):
        original = copy.deepcopy(self.value)
        cases = [
            (lambda p: p.pop('h005_transition'), 'h008_unchanged_binding_modified'),
            (lambda p: p.update(host_usable_bytes=900 * 1024**3), 'h008_unchanged_binding_modified'),
            (lambda p: p['modes']['dual-qwen']['slots']['glm'].update(
                minimum_free_gpu_bytes=24 * 1024**3), 'h008_slot_measurement_mismatch'),
            (lambda p: p['modes']['dual-qwen']['slots']['qwen'].update(
                gpu_total_bytes=80 * 1024**3), 'h008_slot_measurement_mismatch')]
        for change, code in cases:
            self.value = copy.deepcopy(original)
            self.binding.documents[self.instance['concurrent_pair_acceptance']['path']] = self.value
            change(self.value)
            with self.subTest(code=code), self.assertRaisesRegex(LifecycleError, code):
                self.check()

    def test_logical_launcher_slot_does_not_follow_physical_index(self):
        from lifecycle import qwen38
        self.assertEqual(self.d['concurrent_pair']['guest_gpu_index'], 3)
        self.assertEqual(qwen38.command(self.d)[-1], 'gpu1')
        self.assertEqual(self.d['launch']['gpus'], [pair.GPU_UUIDS[1]])

if __name__ == '__main__':
    unittest.main()
