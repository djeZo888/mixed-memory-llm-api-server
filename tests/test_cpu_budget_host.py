"""Closed 480K CPU host checks with synthetic counters and all host I/O mocked."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from benchmark import cpu_budget_host as proofs, cpu_budget_profiles as cpu, profiles
from benchmark.host import LinuxHost, HostBudget, concurrent_capacity_policy
from benchmark.lifecycle import digest
from tests import test_concurrent_host as legacy

GIB = 1024**3


class CPUHost(unittest.TestCase):
    def bare(self):
        host = legacy.ConcurrentHostTests().bare()
        host.scope, host.campaign = cpu.SCOPE, cpu.CAMPAIGN
        host.manifests = {digest(m): m for m in cpu.manifests()}
        return host

    def sample(self, available=688 * GIB):
        row = legacy.ConcurrentHostTests().sample(available)
        for gpu in row['gpus']:
            gpu['total_bytes'] = 96 * GIB
        return row

    def pressure(self, scope=cpu.SCOPE):
        host, row = legacy.ConcurrentHostTests().pressure_sample()
        host.scope = scope
        if scope == cpu.SCOPE:
            host.load_manifests = {'a': cpu.manifest('A', 'G1'), 'b': cpu.manifest('A', 'Q1')}
        for gpu in row['gpus']:
            gpu['total_bytes'] = 96 * GIB
        return host, row

    def test_exact_A_B_effective_limits_and_no_swap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for layout in ('A', 'B'):
                for placement in ('G1', 'Q1'):
                    manifest = cpu.manifest(layout, placement)
                    cap, cpus = manifest['ram_cap_bytes'], manifest['guest_cpuset']
                    def reset():
                        for name, value in {'memory.max': str(cap), 'memory.swap.max': '0',
                                'cpuset.cpus.effective': cpus, 'cpu.max': 'max 100000'}.items():
                            (root / name).write_text(value)
                        return {'HostConfig': {'Memory': cap, 'MemorySwap': cap, 'CpusetCpus': cpus,
                            'NanoCpus': 0, 'CpuQuota': 0, 'CpuPeriod': 0}}
                    memory, limits = LinuxHost.concurrent_limits(manifest, reset(), root)
                    self.assertEqual(memory['cgroup_memory_swap_max'], '0')
                    self.assertEqual(limits['cgroup_cpuset_cpus_effective'], cpus)
                    for name, bad in [('memory.swap.max', '1'), ('memory.max', str(cap - 1)),
                                      ('cpuset.cpus.effective', '0-111'), ('cpu.max', '50000 100000')]:
                        container = reset(); (root / name).write_text(bad)
                        with self.subTest(layout=layout, placement=placement, file=name), self.assertRaises(ValueError):
                            LinuxHost.concurrent_limits(manifest, container, root)
                    for name, bad in [('MemorySwap', cap + 1), ('CpusetCpus', '0-111'), ('CpuQuota', 1)]:
                        container = reset(); container['HostConfig'][name] = bad
                        with self.subTest(layout=layout, placement=placement, field=name), self.assertRaises(ValueError):
                            LinuxHost.concurrent_limits(manifest, container, root)

    def test_new_15_percent_estimate_and_historical_25_percent_are_isolated(self):
        for scope, expected in ((cpu.SCOPE, 'PASS'), (profiles.CONCURRENT_SCOPE, 'STOP_RESOURCE_GATE')):
            host, row = self.pressure(scope)
            row['processes']['b']['rss_bytes'] = 26 * GIB  # +1GiB kernel =27GiB estimate.
            result = host.concurrent_pressure(row)
            self.assertEqual(result['status'], expected)
            charge = result['charges']['b']
            self.assertEqual(charge['headroom_comparison_bytes'], 27 * GIB)
            self.assertEqual(charge['headroom_numerator'], 23 if scope == cpu.SCOPE else 5)
            self.assertEqual(charge['headroom_denominator'], 20 if scope == cpu.SCOPE else 4)
            if scope == cpu.SCOPE:
                self.assertEqual(charge['sampled_required_working_set_estimate_bytes'], 27 * GIB)
                self.assertEqual(charge['required_with_headroom_bytes'], (27 * GIB * 23 + 19) // 20)
                self.assertEqual(charge['host_headroom_policy'], cpu.resource_policy()['host_headroom_policy'])
            else:
                self.assertNotIn('sampled_required_working_set_estimate_bytes', charge)
        self.assertNotIn('host_headroom_policy', concurrent_capacity_policy())
        self.assertEqual(concurrent_capacity_policy(cpu.SCOPE)['host_headroom_policy'],
                         cpu.resource_policy()['host_headroom_policy'])

    def test_15_percent_numeric_failure_latches_through_missing_or_later_good(self):
        host, good = self.pressure(); bad = copy.deepcopy(good)
        bad['processes']['b']['rss_bytes'] = 28 * GIB
        first = host.concurrent_pressure(bad)
        self.assertEqual(first['status'], 'STOP_RESOURCE_GATE')
        self.assertIn('concurrent_cap_15_percent_headroom_failed', first['reasons'])
        for after in (good, copy.deepcopy(good)):
            if after is not good:
                after['cgroups']['b']['file_mapped_bytes'] = None
            result = host.concurrent_pressure(after)
            self.assertEqual(result['status'], 'STOP_RESOURCE_GATE')
            self.assertEqual(result['charges']['b']['sampled_peak_required_bytes'], 29 * GIB)
            self.assertEqual(result['latched_violations']['b'], first['latched_violations']['b'])

    def test_unavailable_is_not_numeric_latch_and_raw_peak_is_not_estimate(self):
        host, row = self.pressure()
        row['cgroups']['b']['current_bytes'] = 32 * GIB
        row['cgroups']['b']['peak_since_cgroup_creation_bytes'] = 32 * GIB
        result = host.concurrent_pressure(row)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['charges']['b']['headroom_comparison_bytes'], 14 * GIB)
        self.assertEqual(result['charges']['b']['lifetime_peak_bytes'], 32 * GIB)
        row['cgroups']['b']['file_mapped_bytes'] = None
        result = host.concurrent_pressure(row)
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertEqual(result['latched_violations'], {})
        row['cgroups']['b']['peak_since_cgroup_creation_bytes'] += 1
        result = host.concurrent_pressure(row)
        self.assertEqual(result['status'], 'STOP_RESOURCE_GATE')
        self.assertIn('concurrent_raw_hard_cap_exceeded', result['reasons'])

    def test_host_GPU_floor_and_Qwen_ten_percent_guards_remain_numeric(self):
        for kind in ('host', 'gpu', 'qwen10', 'unavailable'):
            host, row = self.pressure()
            if kind == 'host': row['host']['available_bytes'] = 16 * GIB - 1
            if kind == 'gpu': row['gpus'][0]['free_bytes'] = 16 * GIB - 1
            if kind == 'qwen10': row['gpus'][1].update(free_bytes=16 * GIB, total_bytes=200 * GIB)
            if kind == 'unavailable': row['gpus'][1]['total_bytes'] = None
            result = host.concurrent_pressure(row)
            self.assertEqual(result['status'], 'UNAVAILABLE' if kind == 'unavailable' else 'STOP_RESOURCE_GATE')
            if kind == 'unavailable': self.assertEqual(result['latched_violations'], {})

    def test_native_Qwen_pool_and_input_require_actual_values_and_agreement(self):
        actual = {'max_total_num_tokens': 480000, 'max_req_input_len': 479994, 'max_req_len': 479999}
        args = {'context_length': 480000, 'tp_size': 1, **actual}
        for info in ({'server_args': args, **actual}, {'server_args': args, 'internal_states': [actual]},
                     {'server_args': args, **actual, 'internal_states': [actual]}):
            result = proofs.qwen_native_proof(info)
            self.assertEqual((result['native_pool_tokens'], result['native_input_limit']), (480000, 479994))
        for bad in ({'server_args': args}, {'server_args': args, **actual, 'max_total_num_tokens': 479744},
                {'server_args': args, **actual, 'max_req_input_len': 480000},
                {'server_args': args, **actual, 'internal_states': [{**actual, 'max_total_num_tokens': 700160}]},
                {'server_args': args, **actual, 'internal_states': [actual, actual]},
                {'server_args': {**args, 'tp_size': 2}, **actual},
                {'server_args': args, **actual, 'max_total_num_tokens': True}):
            with self.subTest(info=list(bad)), self.assertRaises(ValueError):
                proofs.qwen_native_proof(bad)

    def test_closed_operations_reject_profiler_extra_cases_and_resume(self):
        host = self.bare()
        with patch('benchmark.host.command', side_effect=AssertionError('no command')):
            for op in ('profile', 'decode_cpu_capture_start', 'decode_cpu_capture_status',
                       'candidate_evidence', 'candidate_denials', 'unknown'):
                with self.subTest(op=op), self.assertRaisesRegex(ValueError, 'cpu_operation_outside_scope'):
                    host.dispatch({'op': op})
            with self.assertRaisesRegex(ValueError, 'resume_forbidden'):
                host.dispatch({'op': 'begin', 'resume': True})

    def test_closed_A_then_B_requires_retirement_fresh_688_and_forbids_replay(self):
        host = self.bare()
        with patch('benchmark.host.collect_sample', return_value=self.sample()) as sample:
            with self.assertRaises(ValueError): host.admit_concurrent('B')
            sample.assert_not_called()
            self.assertEqual(host.admit_concurrent('A')['round'], 'A')
            with self.assertRaises(ValueError): host.admit_concurrent('A')
            host.owner.resources = [{'state': 'RUNNING'}]
            with self.assertRaises(ValueError): host.admit_concurrent('B')
            host.owner.resources = [{'state': 'REMOVED'}]
            sample.return_value = self.sample(688 * GIB - 1)
            with self.assertRaisesRegex(ValueError, 'host_available_reserve'): host.admit_concurrent('B')
            sample.return_value = self.sample()
            self.assertEqual(host.admit_concurrent('B')['round'], 'B')
            self.assertEqual(host.concurrent_admitted, {digest(cpu.manifest('B', p)) for p in ('G1', 'Q1')})
            with self.assertRaises(ValueError): host.admit_concurrent('A')
            with self.assertRaises(ValueError): host.admit_concurrent('B')

    def test_fresh_688_before_production_retirement_and_no_other_singleton(self):
        host = self.bare()
        original = {'manager': {'selected': 'qwen38-27b-1000000-yarn4-tp2-bf16kv', 'desired': 'running'}}
        with patch('benchmark.host.collect_sample', return_value=self.sample()) as sample:
            self.assertEqual(proofs.pre_retirement_admission(host, original)['minimum_bytes'], 688 * GIB)
            sample.return_value = self.sample(688 * GIB - 1)
            with self.assertRaisesRegex(ValueError, 'cpu_fresh_host_admission_failed'):
                proofs.pre_retirement_admission(host, original)
            for field, value in [('selected', 'other'), ('desired', 'stopped')]:
                bad = copy.deepcopy(original); bad['manager'][field] = value
                with self.assertRaisesRegex(ValueError, 'cpu_original_singleton_required'):
                    proofs.pre_retirement_admission(host, bad)

    def test_resident_obligation_sample_rechecks_identity_and_exact_inventory(self):
        host = self.bare()
        host.load_manifests = {'a': cpu.manifest('A', 'G1')}
        host.owner.resources = [{'state': 'RUNNING', 'resource': {'id': 'a'}}]
        host.identity = Mock(return_value=({}, Path('/synthetic'), [123]))
        sample = self.sample(268 * GIB)
        sample['cgroups'] = {'a': {'anon_bytes': 400 * GIB, 'shmem_bytes': 20 * GIB,
                                  'file_bytes': 500 * GIB, 'swap_bytes': 0}}
        with patch('benchmark.host.collect_sample', return_value=sample), \
                patch('benchmark.concurrent_validate.identity_stamp', return_value={'pid': 123}) as stamp:
            result = proofs.resident_obligations(host)
        self.assertEqual(stamp.call_count, 2)
        self.assertEqual(result['required_host_available_bytes'], 268 * GIB)
        self.assertEqual(result['resident_nonreclaimable_bytes'], {'G1': 420 * GIB})
        with patch('benchmark.host.collect_sample', return_value=sample), \
                patch('benchmark.concurrent_validate.identity_stamp', side_effect=[{'pid': 123}, {'pid': 124}]), \
                self.assertRaisesRegex(ValueError, 'cpu_resident_identity_changed'):
            proofs.resident_obligations(host)
        sample['cgroups'] = {}
        with patch('benchmark.host.collect_sample', return_value=sample), \
                patch('benchmark.concurrent_validate.identity_stamp', return_value={'pid': 123}), \
                self.assertRaisesRegex(ValueError, 'cpu_resident_inventory_changed'):
            proofs.resident_obligations(host)

    def test_CPU_owner_reuses_durable_uncertain_create_and_cleanup_barrier(self):
        from benchmark.owner import CampaignOwner
        manifest = cpu.manifest('A', 'G1')
        owner = CampaignOwner(cpu.CAMPAIGN, Mock(), Mock(), Mock(),
                              reviewed_manifest_hashes=[digest(manifest)], synthetic_offline=True, scope=cpu.SCOPE)
        owner.pending_create = {'dispatch': 'not_dispatched', 'kind': 'model',
                                'manifest_sha256': digest(manifest), 'name': manifest['container_name']}
        writes = []
        owner._save = Mock(side_effect=lambda: writes.append(copy.deepcopy(owner._ledger())))
        owner.mark_create_dispatched()
        self.assertEqual(owner.pending_create['dispatch'], 'uncertain')
        self.assertEqual(writes[-1]['pending_create']['dispatch'], 'uncertain')
        self.assertEqual(writes[-1]['validation_scope'], cpu.SCOPE)
        mutation = Mock()
        with self.assertRaisesRegex(ValueError, 'unresolved_create_blocks_mutation'):
            owner._mutate('start', mutation)
        with self.assertRaisesRegex(ValueError, 'unresolved_create_blocks_cleanup'):
            owner._retire_row({})
        owner._settle_undispatched()
        self.assertEqual(owner.pending_create['dispatch'], 'uncertain')
        mutation.assert_not_called()
        owner.pending_create['dispatch'] = 'not_dispatched'
        owner._settle_undispatched()
        self.assertIsNone(owner.pending_create)
        self.assertIsNone(writes[-1]['pending_create'])

    def loading_case(self, phase='loading'):
        from benchmark import runner
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        state = Path(directory.name)
        runner.save(state / 'progress.json', {'phase': 'OFFLINE', 'completed': {}, 'inflight': {}, 'errors': []})
        host, good = self.pressure()
        for group in good['cgroups'].values():
            group.update(swap_bytes=0, events={'oom': 0, 'oom_kill': 0, 'oom_group_kill': 0})
        good.update(errors=[], timestamp_monotonic_s=1)
        gap = {**copy.deepcopy(good), 'errors': ['gpu_TimeoutExpired'], 'gpus': []}
        rows = {'current': gap, 'good': good}
        def call(op, **kwargs):
            if op == 'telemetry':
                row = copy.deepcopy(rows['current'])
                row['concurrent_resource_gate'] = host.concurrent_pressure(row)
                return row
            if op == 'request_begin': return {'timeout_s': 17}
            raise AssertionError('unexpected offline host call')
        remote = Mock(); remote.call.side_effect = call
        job = runner.Campaign(state, {'scope': cpu.SCOPE}, remote, 'synthetic-nonsecret')
        job.active['b'] = {'manifest': host.load_manifests['b'], 'phase': phase,
            'baseline': copy.deepcopy(good['cgroups']['b']), 'cancel_event': threading.Event()}
        return job, host, rows

    def test_CPU_loading_exact_GPU_timeout_pair_is_saved_without_safety_latch(self):
        job, host, rows = self.loading_case()
        job.collect()
        gap = job.samples['b'][-1]
        self.assertEqual(gap['concurrent_resource_gate']['unavailable_reasons'],
                         ['concurrent_gpu_free_unavailable', 'cpu_qwen_ten_percent_unavailable'])
        self.assertEqual(gap['concurrent_resource_gate']['status'], 'UNAVAILABLE')
        self.assertEqual(gap['concurrent_resource_gate']['latched_violations'], {})
        self.assertEqual(job.safety, {})
        self.assertFalse(job.active['b']['cancel_event'].is_set())
        rows['current'] = rows['good']; job.active['b']['phase'] = 'ready'
        job.collect()
        self.assertEqual(job.samples['b'][-1]['concurrent_resource_gate']['status'], 'PASS')
        self.assertEqual(job.admission('b', 120), 17)
        self.assertEqual(host.concurrent_resource_violations, {})

    def test_CPU_initial_G_only_loading_retains_exact_single_GPU_gap(self):
        job, host, rows = self.loading_case()
        host.load_manifests.pop('b')
        for row in rows.values():
            row['cgroups'].pop('b'); row['processes'].pop('b')
        job.active = {'a': {'manifest': host.load_manifests['a'], 'phase': 'loading',
            'baseline': copy.deepcopy(rows['good']['cgroups']['a']), 'cancel_event': threading.Event()}}
        job.collect()
        self.assertEqual(job.samples['a'][-1]['concurrent_resource_gate']['unavailable_reasons'],
                         ['concurrent_gpu_free_unavailable'])
        self.assertEqual(job.safety, {})
        self.assertFalse(job.active['a']['cancel_event'].is_set())

    def test_CPU_running_GPU_gap_blocks_later_admission_without_cancelling_peer(self):
        job, host, rows = self.loading_case('ready')
        job.collect()
        rows['current'] = rows['good']; job.collect()
        self.assertEqual(job.safety, {'b': 'SKIP_UNSAFE_PLACEMENT'})
        self.assertFalse(job.active['b']['cancel_event'].is_set())
        with self.assertRaisesRegex(RuntimeError, 'SKIP_UNSAFE_PLACEMENT'):
            job.admission('b')
        self.assertEqual(host.concurrent_resource_violations, {})

    def test_CPU_loading_numeric_violation_latches_and_other_omissions_are_not_forgiven(self):
        job, host, rows = self.loading_case()
        rows['current']['processes']['b']['rss_bytes'] = 28 * GIB
        job.collect()
        self.assertEqual(job.safety, {'b': 'STOP_RESOURCE_GATE'})
        self.assertTrue(job.active['b']['cancel_event'].is_set())
        rows['current'] = rows['good']; job.collect()
        self.assertEqual(job.samples['b'][-1]['concurrent_resource_gate']['status'], 'STOP_RESOURCE_GATE')
        self.assertTrue(host.concurrent_resource_violations)
        for variant in ('error', 'extra_error', 'accounting', 'host'):
            job, _, rows = self.loading_case()
            if variant == 'error': rows['current']['errors'] = ['gpu_ValueError']
            if variant == 'extra_error': rows['current']['errors'].append('other_TimeoutExpired')
            if variant == 'accounting': rows['current']['cgroups']['b']['file_mapped_bytes'] = None
            if variant == 'host': rows['current']['host']['available_bytes'] = None
            job.collect()
            with self.subTest(variant=variant):
                self.assertEqual(job.safety, {'b': 'SKIP_UNSAFE_PLACEMENT'})
                self.assertFalse(job.active['b']['cancel_event'].is_set())

    def test_actual_LinuxHost_constructor_with_nonnetwork_install_stubs(self):
        from benchmark import concurrent_cpu_run
        from benchmark import host as module
        root = profiles.ROOT
        relative = 'scripts/benchmark/cpu_budget_host.py'
        source = (root / relative).read_bytes()
        arm = {'scope': cpu.SCOPE, 'campaign': cpu.CAMPAIGN, 'manifests': cpu.manifests(),
            'trial_plan': cpu.trial_order(), 'runtime_policy': concurrent_cpu_run.POLICY,
            'runtime': {**concurrent_cpu_run.POLICY, 'start_epoch': 1000, 'deadline_epoch': 5500},
            'concurrent_capacity_policy': concurrent_capacity_policy(cpu.SCOPE),
            'source_files': {relative: hashlib.sha256(source).hexdigest()}}
        binding = Mock()
        binding.path.side_effect = lambda role, suffix='': '/data/' + role + '/' + suffix
        manager = SimpleNamespace(binding=binding)
        manifest_path = '/data/services/synthetic/manifests.json'
        def protected(path, **kwargs):
            if str(path) == manifest_path: return json.dumps(arm).encode(), {}
            if Path(path) == root / relative: return source, {}
            raise AssertionError('unexpected protected read')
        with patch.object(module, 'INSTALL', root), patch.object(module.os, 'geteuid', return_value=0), \
                patch.object(LinuxHost, 'pin_sources'), patch.object(LinuxHost, 'read_json', return_value=None), \
                patch.object(module, 'protected', side_effect=protected), \
                patch('lifecycle.manager.load_manager', return_value=manager), \
                patch.object(module, 'command', side_effect=AssertionError('no host command')) as command:
            host = LinuxHost(cpu.CAMPAIGN, manifest_path)
        self.assertEqual(host.scope, cpu.SCOPE)
        self.assertEqual(len(host.manifests), 4)
        self.assertEqual((host.start_epoch, host.deadline_epoch), (1000, 5500))
        self.assertIsInstance(host.budget, HostBudget)
        self.assertEqual(host.budget.budget_seconds, 4500)
        self.assertEqual(host.owner.phase, 'NEW')
        self.assertEqual(host.owner.scope, cpu.SCOPE)
        self.assertIsNone(host.owner.lease)
        command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
