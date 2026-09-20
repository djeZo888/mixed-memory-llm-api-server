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
ORIGINAL_START = 1789890954.308154
EXTENDED_DEADLINE = 1789898154.308154


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
        return {'host': {'available_bytes': available}, 'cgroups': {}, 'processes': {},
                'gpus': [{'uuid': m['gpu_uuids'][0], 'free_bytes': 90 * GIB} for m in manifests[:2]]}

    def clock(self):
        return {'campaign': profiles.CONCURRENT_CAMPAIGN, 'runtime': {
            'start_epoch': ORIGINAL_START, 'deadline_epoch': EXTENDED_DEADLINE, 'budget_seconds': 7200,
            'request_max_seconds': 7200, 'clock_includes_preparation': True,
            'includes_load_warmup_fitting': True, 'excludes_source_prep': True,
            'clock_starts': 'RUN_DISPATCH', 'restoration_outside_budget': True}}

    def test_long_identity_isolates_manifests_host_paths_and_preserves_original_clock(self):
        from benchmark import concurrent_run, runner
        previous = 'benchrun-concurrent-g1q1-cont1-20260920'
        campaign = 'benchrun-concurrent-g1q1-long2-20260920'
        self.assertEqual(profiles.CONCURRENT_CAMPAIGN, campaign)
        current = profiles.concurrent_manifests()
        self.assertEqual([(m['placement'], m['configured_capacity']) for m in current],
                         [('G1', 65536), ('Q1', 700160)])
        with patch.object(profiles, 'CONCURRENT_CAMPAIGN', previous):
            original = profiles.concurrent_manifests()
        self.assertEqual(json.loads(json.dumps(current).replace(campaign, previous)), original)
        armed = {'scope': profiles.CONCURRENT_SCOPE, 'campaign': campaign, 'manifests': current,
                 'trial_plan': profiles.trial_order(profiles.CONCURRENT_SCOPE),
                 'runtime_policy': concurrent_run.POLICY, 'session_id': 'prep'}
        self.assertEqual(profiles.validate_arm_scope(armed), profiles.CONCURRENT_SCOPE)
        ssh = runner.SSHHost(armed, popen=Mock())  # No process or connection.
        self.assertIn('/data/services/' + campaign + '/source/scripts/bench/benchmark-host.py', ssh.command)
        self.assertIn('/data/services/' + campaign + '/manifests.json', ssh.command)
        runtime = {**concurrent_run.POLICY, 'start_epoch': 1789890954.308154,
                   'deadline_epoch': EXTENDED_DEADLINE}
        go = {'run_session_id': 'fresh-run', 'runtime': runtime}
        self.assertEqual(concurrent_run.bind_runtime(armed, go, 'fresh-run', runtime['start_epoch'] + 600), runtime)
        self.assertEqual(LinuxHost.concurrent_clock({**armed, 'runtime': runtime}),
                         (runtime['start_epoch'], runtime['deadline_epoch']))
        host = self.bare()
        host.log_root = '/data/logs/' + campaign
        host.start_epoch, host.deadline_epoch = runtime['start_epoch'], runtime['deadline_epoch']
        host.binding = Mock(); host.binding.path.side_effect = lambda role, suffix: '/data/' + role + '/' + suffix
        host.manager, host.read_json = Mock(), Mock(return_value=None)
        host.measured = {}
        host.write_json = lambda suffix, value: LinuxHost.write_json(host, suffix, value)
        host.write({'phase': 'NEW'})
        budget = HostBudget(host)
        self.assertEqual(str(budget.path), host.log_root + '/budget.json')
        with patch('benchmark.host.time.time', return_value=runtime['start_epoch'] + 600):
            budget.start('maintenance')
        self.assertEqual(budget.data['started_at'], runtime['start_epoch'])
        self.assertEqual(budget.data['deadline_epoch'], runtime['deadline_epoch'])
        self.assertEqual([c.args[0] for c in host.manager.persistent_json.call_args_list],
                         [host.log_root + '/' + name for name in ('owner.json', 'measured-demand.json', 'budget.json')])

    def test_clock_bound_only_to_fresh_run_not_prep_or_old_campaign(self):
        self.assertEqual(LinuxHost.concurrent_clock(self.clock()), (ORIGINAL_START, EXTENDED_DEADLINE))
        for key, value in [('start_epoch', True), ('start_epoch', float('nan')),
                           ('start_epoch', ORIGINAL_START + 1), ('deadline_epoch', EXTENDED_DEADLINE + 1),
                           ('deadline_epoch', 1789896354.308154), ('budget_seconds', 5400),
                           ('budget_seconds', 21600),
                           ('request_max_seconds', 7201), ('clock_includes_preparation', False),
                           ('includes_load_warmup_fitting', False), ('excludes_source_prep', False),
                           ('clock_starts', 'PREP'), ('restoration_outside_budget', False)]:
            bad = self.clock(); bad['runtime'][key] = value
            with self.assertRaisesRegex(ValueError, 'concurrent_fresh_dispatch_clock_required'):
                LinuxHost.concurrent_clock(bad)
        bad = self.clock(); bad['continuation_execution'] = {}
        with self.assertRaises(ValueError): LinuxHost.concurrent_clock(bad)
        bad = self.clock(); bad['runtime'].update(start_epoch=1000, deadline_epoch=6400)
        with self.assertRaises(ValueError): LinuxHost.concurrent_clock(bad)
        bad = self.clock(); bad['campaign'] = 'benchrun-concurrent-g1q1-cont1-20260920'
        with self.assertRaises(ValueError): LinuxHost.concurrent_clock(bad)

    def test_budget_deadline_and_restore_outside_clock(self):
        host = SimpleNamespace(scope=profiles.CONCURRENT_SCOPE, log_root='/data/logs/offline',
                               start_epoch=ORIGINAL_START, deadline_epoch=EXTENDED_DEADLINE,
                               read_json=Mock(return_value=None), write_json=Mock())
        with patch('benchmark.host.time.time', return_value=ORIGINAL_START + 10):
            budget = HostBudget(host); budget.start('maintenance')
        budget.clock = lambda: EXTENDED_DEADLINE - 1
        self.assertEqual(budget.request_timeout(7200), 1)
        budget.clock = lambda: EXTENDED_DEADLINE + 1
        with self.assertRaises(ValueError): budget.request_timeout(7200)
        budget.begin_restoration(); budget.finish_restoration(True)
        self.assertEqual(budget.data['deadline_epoch'], EXTENDED_DEADLINE)

    def test_admission_long_only_and_no_replay(self):
        host = self.bare()
        with patch('benchmark.host.collect_sample', return_value=self.sample()):
            with self.assertRaises(ValueError): host.admit_concurrent('short')
            long = host.dispatch({'op': 'admit_concurrent', 'round': 'long'})
            self.assertEqual([(m['placement'], m['configured_capacity']) for m in long['manifests']],
                             [('G1', 65536), ('Q1', 700160)])
            with self.assertRaises(ValueError): host.admit_concurrent('long')
        self.assertNotEqual(long['capacity_policy']['evidence_status'], 'MEASURED_COMPONENTS')
        self.assertEqual(long['capacity_policy']['caps_bytes'], {'G1': 640 * GIB, 'Q1': 32 * GIB})
        self.assertEqual(len(host.concurrent_admitted), 2)

    def test_scope_order_retirement_and_request_refusals(self):
        for alteration in ('wrong_scope', 'wrong_owner', 'live_container', 'unretired'):
            host = self.bare()
            if alteration == 'wrong_scope': host.scope = 'full'
            if alteration == 'wrong_owner': host.owner.phase = 'NEW'
            if alteration == 'live_container': host.campaign_containers.return_value = ['a' * 64]
            if alteration == 'unretired': host.owner.resources = [{'state': 'RUNNING'}]
            with self.assertRaises(ValueError), patch('benchmark.host.collect_sample') as collector:
                host.admit_concurrent('long')
            collector.assert_not_called()
        with self.assertRaises(ValueError): self.bare().admit_concurrent('short')

    def test_available_and_per_device_reserve_gates(self):
        for sample in (self.sample(688 * GIB - 1), self.sample(None), self.sample()):
            if sample['host']['available_bytes'] == 1000 * GIB:
                sample['gpus'][1]['free_bytes'] = 16 * GIB - 1
            with patch('benchmark.host.collect_sample', return_value=sample), self.assertRaises(ValueError):
                self.bare().admit_concurrent('long')
        with patch('benchmark.host.collect_sample', return_value=self.sample(688 * GIB)):
            self.bare().admit_concurrent('long')

    def test_no_load_without_matching_round_admission(self):
        host = self.bare(); host.owner.launch = Mock()
        manifest = profiles.concurrent_manifest('G1', 65536)
        with self.assertRaisesRegex(ValueError, 'concurrent_round_not_admitted'):
            host.dispatch({'op': 'load', 'manifest_sha256': digest(manifest)})
        host.owner.launch.assert_not_called()
        with patch('benchmark.host.collect_sample', return_value=self.sample()): host.admit_concurrent('long')
        host.dispatch({'op': 'load', 'manifest_sha256': digest(manifest)})
        host.owner.launch.assert_called_once_with(manifest)
        for placement, capacity in [('G1', 16384), ('Q1', 262144)]:
            with self.assertRaises(ValueError): profiles.concurrent_manifest(placement, capacity)

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
        host.load_manifests = {'a': profiles.concurrent_manifest('G1', 65536),
                               'b': profiles.concurrent_manifest('Q1', 700160)}
        # Saved predecessor line 952: mapped and shmem overlap by about399GiB;
        # raw file includes another110GiB whose instant reclaimability is unknown.
        row['cgroups']['a'] = {'anon_bytes': 222023680, 'kernel_bytes': 2100539392,
            'file_bytes': 547576070144, 'file_mapped_bytes': 428890877952, 'shmem_bytes': 428888788992,
            'current_bytes': 549898883072, 'peak_since_cgroup_creation_bytes': 549898883072}
        row['processes']['a'] = {'rss_bytes': 429220401152, 'known_process_count': 1}
        row['cgroups']['b'] = {'anon_bytes': 12 * GIB, 'kernel_bytes': GIB,
            'file_bytes': GIB, 'file_mapped_bytes': GIB, 'shmem_bytes': GIB,
            'current_bytes': 14 * GIB, 'peak_since_cgroup_creation_bytes': 15 * GIB}
        row['processes']['b'] = {'rss_bytes': 13 * GIB, 'known_process_count': 3}
        return host, row

    def test_pressure_realistic_overlap_is_estimate_and_raw_charge_stays_separate(self):
        host, row = self.pressure_sample()
        pressure = host.concurrent_pressure(row)
        charge = pressure['charges']['a']
        self.assertEqual(pressure['status'], 'PASS')
        self.assertEqual(charge['component_bracket_bytes'], 431213441024)
        self.assertEqual(charge['headroom_comparison_bytes'], 431320940544)
        self.assertEqual(charge['evidence_status'], 'ESTIMATE')
        self.assertEqual(charge['current_bytes'], 549898883072)
        self.assertEqual(charge['lifetime_peak_bytes'], 549898883072)
        self.assertEqual(charge['extra_charged_file_bytes'], 118685192192)
        self.assertIsNone(charge['reclaimable_file_bytes'])
        self.assertIn('UNPROVEN', charge['reclaimable_status'])
        self.assertNotIn('required_host_demand', row)
        self.assertLess(charge['headroom_comparison_bytes'], 512 * GIB)
        self.assertGreater(charge['lifetime_peak_bytes'], 512 * GIB)

    def test_pressure_retains_host_and_per_gpu_reserve_guards(self):
        for variant in ('host', 'gpu', 'unknown_host', 'unknown_gpu'):
            with self.subTest(variant=variant):
                host, row = self.pressure_sample()
                if variant == 'host': row['host']['available_bytes'] = 16 * GIB - 1
                if variant == 'gpu': row['gpus'][1]['free_bytes'] = 16 * GIB - 1
                if variant == 'unknown_host': row['host']['available_bytes'] = None
                if variant == 'unknown_gpu': row['gpus'][1]['free_bytes'] = None
                self.assertEqual(host.concurrent_pressure(row)['status'],
                                 'UNAVAILABLE' if variant.startswith('unknown') else 'STOP_RESOURCE_GATE')

    def test_missing_rss_or_cgroup_components_never_invent_fit(self):
        for field in ('rss_bytes', 'anon_bytes', 'kernel_bytes', 'file_bytes',
                      'file_mapped_bytes', 'shmem_bytes', 'current_bytes', 'peak_since_cgroup_creation_bytes'):
            with self.subTest(field=field):
                host, row = self.pressure_sample()
                target = row['processes']['b'] if field == 'rss_bytes' else row['cgroups']['b']
                target[field] = None
                result = host.concurrent_pressure(row)
                self.assertEqual(result['status'], 'UNAVAILABLE')
                self.assertEqual(result['charges']['b']['evidence_status'], 'UNAVAILABLE')
                self.assertIsNone(result['charges']['b']['required_bytes'])
                self.assertEqual(result['latched_violations'], {})
        host, row = self.pressure_sample(); row.pop('processes')
        self.assertEqual(host.concurrent_pressure(row)['status'], 'UNAVAILABLE')

    def test_numeric_required_pressure_sampled_peak_latches_through_pass_or_missing(self):
        for branch in ('rss', 'component'):
            with self.subTest(branch=branch):
                host, good = self.pressure_sample(); bad = copy.deepcopy(good)
                if branch == 'rss': bad['processes']['b']['rss_bytes'] = 26 * GIB
                else: bad['cgroups']['b']['anon_bytes'] = 25 * GIB
                first = host.concurrent_pressure(bad)
                self.assertEqual(first['status'], 'STOP_RESOURCE_GATE')
                self.assertEqual(first['charges']['b']['headroom_comparison_bytes'], 27 * GIB)
                after = host.concurrent_pressure(good)
                self.assertEqual(after['charges']['b']['required_bytes'], 14 * GIB)
                self.assertEqual(after['charges']['b']['sampled_peak_required_bytes'], 27 * GIB)
                self.assertFalse(after['charges']['b']['cap_headroom_25_percent'])
                self.assertEqual(after['status'], 'STOP_RESOURCE_GATE')
                self.assertEqual(after['latched_violations']['b'], first['latched_violations']['b'])
                missing = copy.deepcopy(good)
                for key in missing['cgroups']['b']: missing['cgroups']['b'][key] = None
                after = host.concurrent_pressure(missing)
                self.assertEqual(after['status'], 'STOP_RESOURCE_GATE')
                self.assertIsNone(after['charges']['b']['required_bytes'])
                self.assertEqual(after['charges']['b']['headroom_comparison_bytes'], 27 * GIB)
                self.assertEqual(after['latched_violations']['b'], first['latched_violations']['b'])

    def test_raw_current_and_lifetime_peak_keep_exact_640_and_32_gib_hardcaps(self):
        for cid, cap in [('a', 640 * GIB), ('b', 32 * GIB)]:
            for field in ('current_bytes', 'peak_since_cgroup_creation_bytes'):
                with self.subTest(cid=cid, field=field):
                    host, row = self.pressure_sample(); row['cgroups'][cid][field] = cap
                    self.assertEqual(host.concurrent_pressure(row)['status'], 'PASS')
                    row['cgroups'][cid][field] = cap + 1
                    first = host.concurrent_pressure(row)
                    self.assertEqual(first['status'], 'STOP_RESOURCE_GATE')
                    self.assertIn('concurrent_raw_hard_cap_exceeded', first['reasons'])
                    row['cgroups'][cid][field] = cap
                    after = host.concurrent_pressure(row)
                    self.assertEqual(after['status'], 'STOP_RESOURCE_GATE')
                    self.assertEqual(after['latched_violations'][cid], first['latched_violations'][cid])
        host, row = self.pressure_sample(); row['cgroups']['b']['peak_since_cgroup_creation_bytes'] = 26 * GIB
        self.assertEqual(host.concurrent_pressure(row)['status'], 'PASS')

    def test_native_floor_historical_and_current_provenance_remain_distinct(self):
        host, row = self.pressure_sample()
        historical = host.concurrent_pressure(row)['charges']['a']
        self.assertEqual(historical['native_floor_bytes'], 429039864250)
        self.assertIn('historical', historical['native_floor_basis'])
        self.assertIn('not current allocation proof', historical['native_floor_basis'])
        self.assertFalse(historical['allocation_proof_available'])
        host.allocation_proofs['a'] = {'host_weights_mib_log_label': {'CUDA_Host': 409012.22},
                                       'host_workspace_bytes': 159461408}
        accepted = host.concurrent_pressure(row)['charges']['a']
        self.assertTrue(accepted['allocation_proof_available'])
        self.assertIn('current accepted native', accepted['native_floor_basis'])
        self.assertEqual(accepted['native_floor_bytes'], historical['native_floor_bytes'])
        self.assertEqual(accepted['headroom_comparison_bytes'], historical['headroom_comparison_bytes'])
        # A larger accepted native floor is pressure even if other observed branches are small.
        host.allocation_proofs['a']['host_weights_mib_log_label'] = {'CUDA_Host': 530 * 1024}
        result = host.concurrent_pressure(row)
        self.assertEqual(result['status'], 'STOP_RESOURCE_GATE')
        self.assertGreater(result['charges']['a']['native_floor_bytes'], 530 * GIB)
        self.assertEqual(result['charges']['b']['native_floor_basis'], 'UNAVAILABLE_no_native_host_weight_measurement')
        self.assertIsNone(result['charges']['b']['native_floor_bytes'])

    def test_latched_resource_failure_prevents_long_admission(self):
        host, row = self.pressure_sample()
        row['processes']['b']['rss_bytes'] = 26 * GIB
        host.concurrent_pressure(row)
        with self.assertRaisesRegex(ValueError, 'concurrent_latched_resource_failure'), \
                patch('benchmark.host.collect_sample') as collect:
            host.admit_concurrent('long')
        collect.assert_not_called()

    def test_missing_components_with_known_numeric_required_excess_still_stop(self):
        host, row = self.pressure_sample()
        row['cgroups']['b']['file_mapped_bytes'] = None
        result = host.concurrent_pressure(row)
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertIsNone(result['charges']['b']['component_charge_bytes'])
        self.assertEqual(result['latched_violations'], {})
        row['processes']['b']['rss_bytes'] = 26 * GIB
        result = host.concurrent_pressure(row)
        self.assertEqual(result['status'], 'STOP_RESOURCE_GATE')
        self.assertIn('concurrent_required_demand_estimate_unavailable', result['unavailable_reasons'])
        self.assertIsNone(result['charges']['b']['required_bytes'])
        self.assertEqual(result['charges']['b']['known_numeric_floor_bytes'], 27 * GIB)

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
