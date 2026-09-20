"""Closed concurrent host admission and recovery evidence; all Linux I/O mocked."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from benchmark import profiles
from benchmark.host import LinuxHost, HostBudget, concurrent_capacity_policy, _COMMAND_DEADLINE
from benchmark.lifecycle import digest

GIB = 1024**3


class ConcurrentHostTests(unittest.TestCase):
    def bare(self):
        host = LinuxHost.__new__(LinuxHost)
        host.scope, host.campaign = profiles.CONCURRENT_SCOPE, profiles.CONCURRENT_CAMPAIGN
        host.owner = SimpleNamespace(phase='ACTIVE', lease=Mock(), resources=[])
        host.requests, host.load_manifests, host.allocation_proofs = {}, {}, {}
        host.manifests = {digest(m): m for m in profiles.concurrent_manifests()}
        host.concurrent_round, host.concurrent_admitted = None, set()
        host.assert_idle, host.guards, host.write_json = Mock(), Mock(), Mock()
        host.campaign_containers = Mock(return_value=[])
        host.budget = Mock(); host.budget.checkpoint.return_value = 100
        host.budget.request_timeout.return_value = 100
        return host

    def sample(self, available=1000 * GIB):
        manifests = profiles.concurrent_manifests()
        return {'host': {'available_bytes': available}, 'cgroups': {},
                'gpus': [{'uuid': m['gpu_uuids'][0], 'free_bytes': 90 * GIB} for m in manifests[:2]]}

    def clock(self):
        return {'campaign': profiles.CONCURRENT_CAMPAIGN, 'runtime': {
            'start_epoch': 1000, 'deadline_epoch': 6400, 'budget_seconds': 5400,
            'request_max_seconds': 7200, 'clock_includes_preparation': True,
            'includes_load_warmup_fitting': True, 'excludes_source_prep': True,
            'clock_starts': 'RUN_DISPATCH', 'restoration_outside_budget': True}}

    def test_clock_bound_only_to_fresh_run_not_prep_or_old_campaign(self):
        self.assertEqual(LinuxHost.concurrent_clock(self.clock()), (1000, 6400))
        for key, value in [('start_epoch', True), ('start_epoch', float('nan')),
                           ('deadline_epoch', 6401), ('budget_seconds', 21600),
                           ('request_max_seconds', 7201), ('clock_includes_preparation', False),
                           ('includes_load_warmup_fitting', False), ('excludes_source_prep', False),
                           ('clock_starts', 'PREP'), ('restoration_outside_budget', False)]:
            bad = self.clock(); bad['runtime'][key] = value
            with self.assertRaisesRegex(ValueError, 'concurrent_fresh_dispatch_clock_required'):
                LinuxHost.concurrent_clock(bad)
        bad = self.clock(); bad['continuation_execution'] = {}
        with self.assertRaises(ValueError): LinuxHost.concurrent_clock(bad)

    def test_budget_deadline_and_restore_outside_clock(self):
        host = SimpleNamespace(scope=profiles.CONCURRENT_SCOPE, log_root='/data/logs/offline',
                               start_epoch=1000, deadline_epoch=6400,
                               read_json=Mock(return_value=None), write_json=Mock())
        with patch('benchmark.host.time.time', return_value=1010):
            budget = HostBudget(host); budget.start('maintenance')
        budget.clock = lambda: 6399
        self.assertEqual(budget.request_timeout(7200), 1)
        budget.clock = lambda: 6401
        with self.assertRaises(ValueError): budget.request_timeout(7200)
        budget.begin_restoration(); budget.finish_restoration(True)
        self.assertEqual(budget.data['deadline_epoch'], 6400)

    def test_admission_closed_short_then_long_and_no_replay(self):
        host = self.bare()
        with patch('benchmark.host.collect_sample', return_value=self.sample()):
            short = host.dispatch({'op': 'admit_concurrent', 'round': 'short'})
            self.assertEqual([(m['placement'], m['configured_capacity']) for m in short['manifests']],
                             [('G1', 16384), ('Q1', 262144)])
            with self.assertRaises(ValueError): host.admit_concurrent('short')
            long = host.admit_concurrent('long')
            self.assertEqual([(m['placement'], m['configured_capacity']) for m in long['manifests']],
                             [('G1', 65536), ('Q1', 700160)])
            with self.assertRaises(ValueError): host.admit_concurrent('long')
        self.assertNotEqual(short['capacity_policy']['evidence_status'], 'MEASURED_COMPONENTS')
        self.assertEqual(short['capacity_policy']['caps_bytes'], {'G1': 640 * GIB, 'Q1': 32 * GIB})
        self.assertEqual(len(host.concurrent_admitted), 2)

    def test_scope_order_retirement_and_request_refusals(self):
        for alteration in ('wrong_scope', 'wrong_owner', 'live_container', 'unretired'):
            host = self.bare()
            if alteration == 'wrong_scope': host.scope = 'full'
            if alteration == 'wrong_owner': host.owner.phase = 'NEW'
            if alteration == 'live_container': host.campaign_containers.return_value = ['a' * 64]
            if alteration == 'unretired': host.owner.resources = [{'state': 'RUNNING'}]
            with self.assertRaises(ValueError), patch('benchmark.host.collect_sample') as collector:
                host.admit_concurrent('short')
            collector.assert_not_called()
        with self.assertRaises(ValueError): self.bare().admit_concurrent('long')

    def test_available_and_per_device_reserve_gates(self):
        for sample in (self.sample(688 * GIB - 1), self.sample(None), self.sample()):
            if sample['host']['available_bytes'] == 1000 * GIB:
                sample['gpus'][1]['free_bytes'] = 16 * GIB - 1
            with patch('benchmark.host.collect_sample', return_value=sample), self.assertRaises(ValueError):
                self.bare().admit_concurrent('short')
        with patch('benchmark.host.collect_sample', return_value=self.sample(688 * GIB)):
            self.bare().admit_concurrent('short')

    def test_no_load_without_matching_round_admission(self):
        host = self.bare(); host.owner.launch = Mock()
        manifest = profiles.concurrent_manifest('G1', 65536)
        with self.assertRaisesRegex(ValueError, 'concurrent_round_not_admitted'):
            host.dispatch({'op': 'load', 'manifest_sha256': digest(manifest)})
        host.owner.launch.assert_not_called()
        with patch('benchmark.host.collect_sample', return_value=self.sample()): host.admit_concurrent('short')
        with self.assertRaises(ValueError): host.dispatch({'op': 'load', 'manifest_sha256': digest(manifest)})
        initial = profiles.concurrent_manifest('G1', 16384)
        host.dispatch({'op': 'load', 'manifest_sha256': digest(initial)})
        host.owner.launch.assert_called_once_with(initial)

    def limits(self, root, placement):
        cap = 640 * GIB if placement == 'G1' else 32 * GIB
        cpus = '0-95' if placement == 'G1' else '96-111'
        for name, text in {'memory.max': str(cap), 'memory.swap.max': '0',
                           'cpuset.cpus.effective': cpus, 'cpu.max': 'max 100000'}.items():
            (root / name).write_text(text)
        return {'HostConfig': {'Memory': cap, 'MemorySwap': cap, 'CpusetCpus': cpus,
                               'NanoCpus': 0, 'CpuQuota': 0, 'CpuPeriod': 0}}

    def test_current_limits_exact_both_models_no_swap_or_cpu_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            for placement, capacity in [('G1', 65536), ('Q1', 700160)]:
                manifest = profiles.concurrent_manifest(placement, capacity)
                container = self.limits(path, placement)
                memory, cpu = LinuxHost.concurrent_limits(manifest, container, path)
                self.assertEqual(memory['cgroup_memory_swap_max'], '0')
                (path / 'memory.swap.max').write_text('1')
                with self.assertRaisesRegex(ValueError, 'no_swap'): LinuxHost.concurrent_limits(manifest, container, path)
                container = self.limits(path, placement); container['HostConfig']['CpusetCpus'] = '0-111'
                with self.assertRaisesRegex(ValueError, 'cpu_limits'): LinuxHost.concurrent_limits(manifest, container, path)

    def pressure_sample(self):
        host = self.bare(); row = self.sample(300 * GIB)
        for cid, placement, cap, anon, file in [('a', 'G1', 65536, 400, 70), ('b', 'Q1', 700160, 12, 1)]:
            host.load_manifests[cid] = profiles.concurrent_manifest(placement, cap)
            row['cgroups'][cid] = {'anon_bytes': anon * GIB, 'kernel_bytes': GIB,
                'file_bytes': file * GIB, 'file_mapped_bytes': file * GIB + 1, 'shmem_bytes': file * GIB,
                'current_bytes': (anon + file + 1) * GIB, 'peak_since_cgroup_creation_bytes': (anon + file + 2) * GIB}
        return host, row

    def test_pressure_inclusive_peak_avoids_component_double_count(self):
        host, row = self.pressure_sample()
        pressure = host.concurrent_pressure(row)
        self.assertEqual(pressure['status'], 'PASS')
        self.assertEqual(pressure['charges']['a']['headroom_comparison_bytes'], 472 * GIB)
        self.assertEqual(pressure['charges']['a']['evidence_status'], 'OBSERVED_TOTALS_AND_CONSERVATIVE_COMPONENT_BRACKET')
        self.assertNotIn('required_host_demand', row)

    def test_pressure_refuses_headroom_reserve_and_unknown_components(self):
        for variant in ('cap', 'host', 'gpu', 'unknown'):
            host, row = self.pressure_sample()
            if variant == 'cap': row['cgroups']['b']['peak_since_cgroup_creation_bytes'] = 26 * GIB
            if variant == 'host': row['host']['available_bytes'] = 16 * GIB - 1
            if variant == 'gpu': row['gpus'][1]['free_bytes'] = 16 * GIB - 1
            if variant == 'unknown': row['cgroups']['a']['current_bytes'] = None
            self.assertEqual(host.concurrent_pressure(row)['status'], 'UNAVAILABLE' if variant == 'unknown' else 'STOP_RESOURCE_GATE')

    def test_headroom_uses_max_component_bracket_without_adding_totals(self):
        host, row = self.pressure_sample()
        row['cgroups']['a'].update(current_bytes=400 * GIB, peak_since_cgroup_creation_bytes=401 * GIB,
                                  anon_bytes=430 * GIB, kernel_bytes=GIB, file_bytes=70 * GIB,
                                  file_mapped_bytes=71 * GIB, shmem_bytes=72 * GIB)
        result = host.concurrent_pressure(row)
        self.assertEqual(result['charges']['a']['headroom_comparison_bytes'], 503 * GIB)
        self.assertEqual(result['status'], 'PASS')
        row['cgroups']['a']['anon_bytes'] = 440 * GIB
        result = host.concurrent_pressure(row)
        self.assertEqual(result['charges']['a']['headroom_comparison_bytes'], 513 * GIB)
        self.assertEqual(result['status'], 'STOP_RESOURCE_GATE')

    def test_transient_current_and_peak_violations_latch_through_pass_or_missing(self):
        for field in ('current_bytes', 'peak_since_cgroup_creation_bytes'):
            host, good = self.pressure_sample()
            bad = copy.deepcopy(good); bad['cgroups']['b'][field] = 26 * GIB
            first = host.concurrent_pressure(bad)
            self.assertEqual(first['status'], 'STOP_RESOURCE_GATE')
            after = host.concurrent_pressure(good)
            self.assertTrue(after['charges']['b']['cap_headroom_25_percent'])
            self.assertEqual(after['status'], 'STOP_RESOURCE_GATE')
            self.assertEqual(after['latched_violations']['b'], first['latched_violations']['b'])
            missing = copy.deepcopy(good)
            for key in missing['cgroups']['b']: missing['cgroups']['b'][key] = None
            after = host.concurrent_pressure(missing)
            self.assertEqual(after['status'], 'STOP_RESOURCE_GATE')
            self.assertIsNone(after['charges']['b']['headroom_comparison_bytes'])
            self.assertEqual(after['latched_violations']['b'], first['latched_violations']['b'])

    def test_latched_resource_failure_prevents_next_round_admission(self):
        host, row = self.pressure_sample()
        row['cgroups']['b']['current_bytes'] = 26 * GIB
        host.concurrent_pressure(row)
        with self.assertRaisesRegex(ValueError, 'concurrent_latched_resource_failure'), \
                patch('benchmark.host.collect_sample') as collect:
            host.admit_concurrent('short')
        collect.assert_not_called()

    def test_missing_components_not_zero_and_known_numeric_excess_still_stops(self):
        host, row = self.pressure_sample()
        row['cgroups']['b']['file_mapped_bytes'] = None
        result = host.concurrent_pressure(row)
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertIsNone(result['charges']['b']['component_charge_bytes'])
        self.assertEqual(result['latched_violations'], {})
        row['cgroups']['b']['current_bytes'] = 26 * GIB
        result = host.concurrent_pressure(row)
        self.assertEqual(result['status'], 'STOP_RESOURCE_GATE')
        self.assertIn('concurrent_component_charge_unavailable', result['unavailable_reasons'])

    def test_quiescent_uses_cheap_counters_not_pss(self):
        host = self.bare(); host.identity = Mock(return_value=({}, Path('/not-read'), [123]))
        host.telemetry = Mock(return_value={'sample_kind': 'cheap'})
        with patch('pathlib.Path.read_text', side_effect=AssertionError('no smaps read')):
            result = host.quiescent('a', 'warm_idle')
        self.assertIsNone(result['pss_bytes'])
        self.assertEqual(result['scope'], 'cheap_quiescent_counters')

    def test_cpu_pressure_is_small_numeric_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / 'cpu.stat').write_text('usage_usec 10\nuser_usec 5\nsystem_usec 5\nother_sensitive_text 11\n')
            (path / 'memory.pressure').write_text('some avg10=0.00 avg60=1.00 avg300=2.00 total=123\n')
            result = LinuxHost.concurrent_cpu_pressure({'a': path})
            self.assertEqual(result['cgroups']['a']['cpu_stat'], {'usage_usec': 10, 'user_usec': 5, 'system_usec': 5})
            self.assertEqual(result['cgroups']['a']['memory_pressure']['some']['total'], 123)
            self.assertIsNone(result['cgroups']['a']['cpu_pressure'])

    def test_safe_rpc_receipt_excludes_unstructured_message_and_locals(self):
        host = self.bare(); host.log_root = '/data/logs/offline'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp); (path / '123-1234567890abcdef.json').write_text('{}')
            host.binding = SimpleNamespace(validate_path=Mock(return_value=path))
            host.read_json = Mock(return_value={'operation': 'restore', 'exception_class': 'OwnerError',
                'require_code': None, 'frames': [{'source': 'owner.py', 'function': 'restore', 'line': 329,
                                                'locals': 'PRIVATE'}], 'message': 'PRIVATE'})
            receipt = host.dispatch({'op': 'rpc_diagnostics'})
            self.assertNotIn('PRIVATE', json.dumps(receipt))
            self.assertEqual(receipt['diagnostics'][0]['frames'], [{'source': 'owner.py', 'function': 'restore', 'line': 329}])

    def test_restore_clears_deadline_and_never_loads(self):
        host = self.bare(); host.worker_nonce = 'not-a-secret-test-nonce'; host.restored_at = 1
        def restore():
            self.assertIsNone(_COMMAND_DEADLINE.get())
            host.owner.phase = 'POST_RELEASE_LAN_VERIFICATION_PENDING'
            return {'local_restoration': 'VERIFIED'}
        host.owner.restore = Mock(side_effect=restore)
        token = _COMMAND_DEADLINE.set(1)
        try:
            result = host.dispatch({'op': 'restore'})
            self.assertEqual(result['local_restoration'], 'VERIFIED')
            self.assertEqual(_COMMAND_DEADLINE.get(), 1)
        finally: _COMMAND_DEADLINE.reset(token)
        self.assertEqual(host.concurrent_round, None)


if __name__ == '__main__':
    unittest.main()
