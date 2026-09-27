#!/usr/bin/env python3
"""Synthetic pinned-log-shape tests; these are not a live allocation receipt."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from allocation import compose_phase, parse_native_allocation


def log_fixture(context=1000000, pool=None, dtype='f16'):
    pool = context if pool is None else pool
    global_mib = 51200 * pool / 1048576
    return f'''2026-09-27T15:40:00Z llama_context: n_ctx = {pool}
load_tensors: CUDA0 model buffer size = 38300.25 MiB
load_tensors: CPU model buffer size = 507321.19 MiB
llama_kv_cache_iswa: creating non-SWA KV cache, size = {pool} cells
llama_kv_cache: CUDA0 KV buffer size = {global_mib:.2f} MiB
llama_kv_cache: size = {global_mib:.2f} MiB ({pool} cells, 10 layers, 1/1 seqs), K ({dtype}): {global_mib * .6:.2f} MiB, V ({dtype}): {global_mib * .4:.2f} MiB
llama_kv_cache_iswa: creating     SWA KV cache, size = 768 cells
llama_kv_cache: CUDA0 KV buffer size = 225.00 MiB
llama_kv_cache: size = 225.00 MiB (768 cells, 60 layers, 1/1 seqs), K (f16): 135.00 MiB, V (f16): 90.00 MiB
llama_context: CPU output buffer size = 1.12 MiB
sched_reserve: CUDA0 compute buffer size = 750.25 MiB
sched_reserve: CPU compute buffer size = 125.75 MiB
srv    load_model: initializing, n_slots = 1, n_ctx_slot = {context}, kv_unified = 'true'
srv  llama_server: model loaded
'''


class AllocationTests(unittest.TestCase):
    def test_complete_f16_allocation(self):
        proof = parse_native_allocation(log_fixture(), 1000000)
        self.assertEqual(proof['status'], 'PROVEN', proof['reasons'])
        self.assertEqual(proof['actual_global_pool_cells'], 1000000)
        self.assertEqual(proof['global_kv_bytes_calculated'], 51200000000)
        self.assertIsNone(proof['occupied_input_tokens'])
        self.assertEqual(proof['pools']['swa']['summary']['mib_log_label'], 225)

    def test_native_padding_is_preserved_and_refused(self):
        proof = parse_native_allocation(log_fixture(pool=1000192), 1000000)
        self.assertEqual(proof['status'], 'UNPROVEN')
        self.assertEqual(proof['actual_global_pool_cells'], 1000192)
        self.assertEqual(proof['pool_padding_cells'], 192)
        self.assertEqual(proof['slot_records'][0]['context'], 1000000)
        self.assertIn('global_actual_cells_mismatch', proof['reasons'])

    def test_explicit_reviewed_physical_pool_distinct_from_slot(self):
        proof = parse_native_allocation(log_fixture(pool=1000192), 1000000,
                                        expected_pool_context=1000192)
        self.assertEqual(proof['status'], 'PROVEN', proof['reasons'])
        self.assertEqual(proof['usable_context_tokens'], 1000000)
        self.assertEqual(proof['actual_global_pool_cells'], 1000192)
        self.assertEqual(proof['pool_padding_cells'], 192)
        self.assertEqual(proof['global_kv_bytes_calculated'], 51209830400)

    def test_reviewed_usable_rounding_is_separate_from_config_and_physical_pool(self):
        proof = parse_native_allocation(log_fixture(1000192), 1000000,
                                        expected_pool_context=1000192,
                                        expected_usable_context=1000192)
        self.assertEqual(proof['status'], 'PROVEN', proof['reasons'])
        self.assertEqual(proof['configured_context'], 1000000)
        self.assertEqual(proof['usable_context_tokens'], 1000192)
        self.assertEqual(proof['actual_global_pool_cells'], 1000192)
        self.assertEqual(proof['pool_padding_cells'], 0)
        self.assertEqual(parse_native_allocation(log_fixture(1000192), 1000000,
                         expected_pool_context=1000192)['status'], 'UNPROVEN')
        with self.assertRaises(ValueError):
            parse_native_allocation(log_fixture(1000192), 1000000,
                                    expected_pool_context=1000000,
                                    expected_usable_context=1000192)
        with self.assertRaises(ValueError):
            parse_native_allocation(log_fixture(1000448), 1000000,
                                    expected_pool_context=1000448,
                                    expected_usable_context=1000448)

    def test_fallback_requires_its_own_actual_pool(self):
        self.assertEqual(parse_native_allocation(log_fixture(917504), 917504)['status'], 'PROVEN')
        self.assertEqual(parse_native_allocation(log_fixture(), 917504)['status'], 'UNPROVEN')

    def test_slot_limit_is_not_pool_proof(self):
        proof = parse_native_allocation("srv load_model: initializing, n_slots = 1, n_ctx_slot = 1000000, kv_unified = 'true'", 1000000)
        self.assertEqual(proof['status'], 'UNPROVEN')
        self.assertIsNone(proof['actual_global_pool_cells'])
        self.assertIn('global_pool_missing', proof['reasons'])

    def test_create_line_without_allocated_summary_is_not_proof(self):
        text = '\n'.join(x for x in log_fixture().splitlines() if 'layers,' not in x)
        proof = parse_native_allocation(text, 1000000)
        self.assertEqual(proof['status'], 'UNPROVEN')
        self.assertIsNone(proof['actual_global_pool_cells'])

    def test_non_f16_and_wrong_layers_refused(self):
        for text in (log_fixture(dtype='q8_0'), log_fixture().replace('10 layers', '9 layers')):
            self.assertEqual(parse_native_allocation(text, 1000000)['status'], 'UNPROVEN')

    def test_wrong_kv_size_or_host_placement_refused(self):
        for text in (log_fixture().replace('135.00', '133.00'),
                     log_fixture().replace('CUDA0 KV buffer', 'CPU KV buffer')):
            self.assertEqual(parse_native_allocation(text, 1000000)['status'], 'UNPROVEN')

    def test_concatenated_loads_refused(self):
        proof = parse_native_allocation(log_fixture() * 2, 1000000)
        self.assertEqual(proof['status'], 'UNPROVEN')
        self.assertIn('duplicate_global_pool', proof['reasons'])

    def test_workspace_missing_refused_and_growth_recorded(self):
        text = '\n'.join(x for x in log_fixture().splitlines() if 'CUDA0 compute' not in x)
        self.assertEqual(parse_native_allocation(text, 1000000)['status'], 'UNPROVEN')
        proof = parse_native_allocation(log_fixture() + 'sched_reserve: CUDA0 compute buffer size = 900.25 MiB\n', 1000000)
        self.assertEqual(proof['status'], 'PROVEN')
        self.assertEqual(proof['workspace_buffers_mib_log_label']['CUDA0'], 900.25)
        self.assertEqual(len(proof['workspace_buffer_records']), 3)


class PhaseTests(unittest.TestCase):
    def phase(self, **kwargs):
        return compose_phase(parse_native_allocation(log_fixture(), 1000000), 'POST-LOAD',
            [{'uuid': 'GPU-test', 'total_mib': 97887, 'used_mib': 88910, 'free_mib': 8341,
              'temp_c': 58, 'util_pct': 17}],
            {'MemTotal': 1024 ** 4, 'MemAvailable': 200 * 1024 ** 3}, 'GPU-test',
            {'candidate_id': 'current', 'native_pid': 1, 'not_an_identity_field': 'omitted'}, **kwargs)

    def test_reserved_and_unaccounted_differ(self):
        result = self.phase(reserved_mib=638)
        self.assertEqual(result['frontier']['arithmetic_unaccounted_mib'], 636)
        self.assertEqual(result['frontier']['reserved_mib_readback'], 638)
        self.assertEqual(result['frontier']['residual_minus_reserved_mib'], -2)
        self.assertTrue(result['frontier']['reserve_pass'])
        self.assertTrue(result['host_reserve_pass'])
        self.assertNotIn('util_pct', result['gpu_readback'][0])
        self.assertNotIn('not_an_identity_field', result['native_identity'])
        self.assertIsNone(result['occupied_input_tokens'])

    def test_missing_reserved_is_not_synthesized(self):
        self.assertIsNone(self.phase()['frontier']['reserved_mib_readback'])

    def test_separate_occupied_count(self):
        result = self.phase(occupied_input_tokens=4096)
        self.assertEqual(result['occupied_input_tokens'], 4096)
        self.assertEqual(result['allocation']['actual_global_pool_cells'], 1000000)
        self.assertIsNone(result['allocation']['occupied_input_tokens'])

    def test_missing_counters_fail_closed(self):
        result = compose_phase(None, 'BASELINE', [], {}, 'GPU-test', {})
        self.assertEqual(result['capture_status'], 'INVALID')
        self.assertEqual(result['frontier'], {})
        self.assertIsNone(result['host_reserve_pass'])

    def test_nonfinite_reserved_refused(self):
        with self.assertRaises(ValueError):
            self.phase(reserved_mib=float('nan'))


if __name__ == '__main__':
    unittest.main()
