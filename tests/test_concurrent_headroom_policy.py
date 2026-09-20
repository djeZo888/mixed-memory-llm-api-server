"""In-memory receipt-policy checks; no live evidence or acceptance is written."""
import copy
import unittest

from tests.lifecycle.test_concurrent_profiles import bound, receipt
from lifecycle import concurrent_profiles as pair
from lifecycle.runtime_io import LifecycleError


class HeadroomPolicy(unittest.TestCase):
    def setUp(self):
        self.deployment = bound(pair.GLM_PROFILE)
        self.proof, self.instance = receipt(self.deployment)

    def check(self):
        reference = self.instance['concurrent_pair_acceptance']
        reference['sha256'] = pair.receipt_sha256(self.proof)
        return pair.check_acceptance(self.deployment, self.instance)

    def use_estimate_policy(self):
        self.proof['host_headroom_policy'] = copy.deepcopy(pair.HOST_HEADROOM_POLICY_15)
        for slot in self.proof['slots'].values():
            slot['sampled_required_working_set_estimate_bytes'] = slot['memory_bytes'] * 20 // 23
            slot['host_peak_bytes'] = slot['memory_bytes']

    def test_historical_absent_policy_keeps_exact_25_percent_boundary(self):
        for slot in self.proof['slots'].values():
            slot['host_peak_bytes'] = slot['memory_bytes'] * 4 // 5
            # A stray estimate never opts a historical receipt into 15%.
            slot['sampled_required_working_set_estimate_bytes'] = 1
        self.check()
        self.proof['slots']['glm']['host_peak_bytes'] += 1
        with self.assertRaisesRegex(LifecycleError, 'concurrent_resource_margin_unaccepted'):
            self.check()

    def test_explicit_estimate_15_percent_boundary_is_separate_from_raw_peak(self):
        self.use_estimate_policy()
        self.check()
        self.proof['slots']['glm']['sampled_required_working_set_estimate_bytes'] += 1
        with self.assertRaisesRegex(LifecycleError, 'concurrent_resource_margin_unaccepted'):
            self.check()

    def test_each_slot_requires_positive_integer_estimate(self):
        self.use_estimate_policy()
        for slot in ('glm', 'qwen'):
            saved = self.proof['slots'][slot]['sampled_required_working_set_estimate_bytes']
            for invalid in (None, False, 0, -1, float(saved)):
                self.proof['slots'][slot]['sampled_required_working_set_estimate_bytes'] = invalid
                with self.subTest(slot=slot, invalid=invalid), self.assertRaisesRegex(
                        LifecycleError, 'concurrent_resource_margin_unaccepted'):
                    self.check()
            self.proof['slots'][slot].pop('sampled_required_working_set_estimate_bytes')
            with self.assertRaisesRegex(LifecycleError, 'concurrent_resource_margin_unaccepted'):
                self.check()
            self.proof['slots'][slot]['sampled_required_working_set_estimate_bytes'] = saved

    def test_policy_is_exact_versioned_metadata_not_global_weakening(self):
        self.use_estimate_policy()
        for invalid in (None, {}, {'version': 'historical'},
                dict(pair.HOST_HEADROOM_POLICY_15, numerator=15),
                dict(pair.HOST_HEADROOM_POLICY_15, denominator=100),
                dict(pair.HOST_HEADROOM_POLICY_15, basis='host_peak_bytes'),
                dict(pair.HOST_HEADROOM_POLICY_15, extra=True)):
            self.proof['host_headroom_policy'] = invalid
            with self.subTest(policy=invalid), self.assertRaisesRegex(
                    LifecycleError, 'concurrent_host_headroom_policy_unaccepted'):
                self.check()

    def test_raw_hard_cap_and_gpu_reserves_remain_required(self):
        self.use_estimate_policy()
        for slot, key, value in (('glm', 'host_peak_bytes', 640 * 1024**3 + 1),
                ('qwen', 'host_peak_bytes', 32 * 1024**3 + 1),
                ('glm', 'host_peak_bytes', None),
                ('glm', 'minimum_free_gpu_bytes', 16 * 1024**3 - 1),
                ('qwen', 'gpu_total_bytes', 300 * 1024**3)):
            saved = self.proof['slots'][slot][key]
            self.proof['slots'][slot][key] = value
            with self.subTest(slot=slot, key=key), self.assertRaisesRegex(
                    LifecycleError, 'concurrent_resource_margin_unaccepted'):
                self.check()
            self.proof['slots'][slot][key] = saved


if __name__ == '__main__':
    unittest.main()
