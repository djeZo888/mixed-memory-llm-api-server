"""Bounded GLMREPAIR host/source contracts; synthetic offline I/O only."""
import copy
import json
from pathlib import Path
import shlex
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import allocation, profiles
from benchmark.host import HostBudget, LinuxHost
from benchmark.lifecycle import digest
from tests import test_benchmark_allocation as allocation_fixtures
from tests import test_benchmark_host as host_fixtures


class GlmrepairHost(unittest.TestCase):
    def arm(self):
        return {'scope': 'glmrepair', 'campaign': profiles.GLMREPAIR_CAMPAIGN,
                'manifests': [profiles.glmrepair_manifest()], 'trial_plan': profiles.trial_order('glmrepair'),
                'runtime': {'start_epoch': 1000, 'deadline_epoch': 4600, 'budget_seconds': 3600}}

    def limits(self):
        return {'docker_memory_bytes': profiles.G1_RAM_CAP_BYTES,
                'docker_memory_swap_bytes': profiles.G1_RAM_CAP_BYTES,
                'cgroup_memory_max': str(profiles.G1_RAM_CAP_BYTES), 'cgroup_memory_swap_max': '0'}

    def cpu_limits(self):
        return {'docker_cpuset_cpus': '0-95', 'docker_nano_cpus': 0,
                'docker_cpu_quota': 0, 'docker_cpu_period': 0,
                'cgroup_cpuset_cpus_effective': '0-95', 'cgroup_cpu_max': 'max 100000'}

    def container(self):
        return {'HostConfig': {'Memory': profiles.G1_RAM_CAP_BYTES, 'MemorySwap': profiles.G1_RAM_CAP_BYTES,
                              'CpusetCpus': '0-95', 'NanoCpus': 0, 'CpuQuota': 0, 'CpuPeriod': 0},
                'State': {'StartedAt': '2026-09-19T21:00:00Z'}}

    def test_exact_accepted_manifest_and_historical_cpu_contract(self):
        arm = self.arm(); m = arm['manifests'][0]
        self.assertEqual(profiles.validate_arm_scope(arm), 'glmrepair')
        self.assertEqual((m['guest_cpu_count'], m['guest_cpuset'], m['ram_cap_bytes']),
                         (96, '0-95', 640 * 1024**3))
        self.assertEqual(m['create_shell'], shlex.join(m['create_argv']))
        for flag, value in (('--threads', '96'), ('--threads-batch', '96'), ('--n-cpu-moe', '76'),
                            ('--log-verbosity', '4'), ('--ctx-size', '4096'), ('--cache-type-k', 'f16'),
                            ('--cache-type-v', 'f16'), ('--batch-size', '2048'), ('--ubatch-size', '512'),
                            ('--split-mode', 'layer'), ('--tensor-split', '1,1'), ('--device', 'CUDA0,CUDA1')):
            self.assertEqual(m['native_argv'][m['native_argv'].index(flag) + 1], value)
        self.assertEqual(profiles.command_manifest('G2', 4096)['guest_cpu_count'], 112)
        self.assertEqual(profiles.trial_order('full')['measurement_budget_seconds'], 21600)

    def test_scope_rejects_profile_or_trial_expansion(self):
        original = self.arm()
        variants = []
        for field, value in (('campaign', 'benchrun-old'), ('manifests', original['manifests'] * 2)):
            bad = copy.deepcopy(original); bad[field] = value; variants.append(bad)
        for field, value in (('guest_cpu_count', 112), ('guest_cpuset', '0-111'), ('configured_capacity', 16384)):
            bad = copy.deepcopy(original); bad['manifests'][0][field] = value; variants.append(bad)
        bad = copy.deepcopy(original); bad['trial_plan']['trials'][0]['output_cap'] = 256; variants.append(bad)
        for arm in variants:
            with self.assertRaisesRegex(ValueError, 'glmrepair_exact_arm_scope_mismatch'):
                profiles.validate_arm_scope(arm)
        plan = original['trial_plan']
        self.assertEqual([row['output_cap'] for row in plan['trials']], [32, 128, 128, 256])
        self.assertEqual(plan['mixed_jobs'], [])

    def test_clock_requires_new_epoch_exact_deadline_without_continuation(self):
        self.assertEqual(LinuxHost.glmrepair_clock(self.arm()), (1000, 4600))
        for field, value in (('start_epoch', True), ('deadline_epoch', 4601), ('budget_seconds', 21600),
                             ('start_epoch', float('nan')), ('deadline_epoch', float('inf'))):
            bad = self.arm(); bad['runtime'][field] = value
            with self.assertRaisesRegex(ValueError, 'glmrepair_new_immutable_clock_required'):
                LinuxHost.glmrepair_clock(bad)
        bad = self.arm(); bad['continuation_execution'] = bad['runtime']
        with self.assertRaises(ValueError): LinuxHost.glmrepair_clock(bad)

    def test_one_hour_budget_persists_once_caps_requests_and_excludes_restore(self):
        host = SimpleNamespace(scope='glmrepair', log_root='/data/logs/benchrun-glmrepair-20260919',
                               start_epoch=1000, deadline_epoch=4600, read_json=Mock(return_value=None), write_json=Mock())
        with patch('benchmark.host.time.time', return_value=1001):
            budget = HostBudget(host); budget.start('maintenance')
        budget.clock = lambda: 1100
        self.assertEqual(budget.request_timeout(7200), 3500)
        self.assertEqual(budget.data['deadline_epoch'], 4600)
        with self.assertRaises(ValueError): budget.start('maintenance')
        budget.clock = lambda: 4600
        with self.assertRaisesRegex(ValueError, 'STOP_BUDGET'): budget.request_timeout()
        budget.begin_restoration()
        budget.clock = lambda: 5600
        budget.finish_restoration(True)
        self.assertEqual(budget.data['phase'], 'RESTORED')
        self.assertEqual(budget.data['deadline_epoch'], 4600)
        host.read_json.return_value = budget.data
        self.assertEqual(HostBudget(host).data['phase'], 'RESTORED')
        host.deadline_epoch += 1
        with self.assertRaisesRegex(ValueError, 'glmrepair_immutable_clock_changed'): HostBudget(host)

    def test_scope_forbids_resume_and_mixed_before_actions(self):
        host = host_fixtures.HostTests().bare(); host.scope = 'glmrepair'; host.read_json = Mock()
        for message in ({'op': 'begin', 'args': {'resume': True}}, {'op': 'admit_mixed'}):
            with self.assertRaises(ValueError): host.dispatch(message)
        host.read_json.assert_not_called()

    def test_strict_dual_cache_graph_cpu_and_memory_admission(self):
        fixture = allocation_fixtures.Allocation(); manifest = profiles.glmrepair_manifest()
        parsed = allocation.parse_glm_log(fixture.glm_log(2).replace('lid_nodes=78', 'lid_nodes=21'))
        observed = fixture.observed(manifest)
        observed.update(container_memory_limits=self.limits(), container_cpu_limits=self.cpu_limits())
        gate = lambda p, o: allocation.allocation_gate(manifest, p, o, strict_glmrepair=True)
        self.assertEqual(gate(parsed, observed)['status'], 'ALLOCATION_PROOF_ACCEPTED')
        for key, value in (('cache_bytes', {'CUDA0': 390070272}), ('cache_bytes', {'CUDA0': 1, 'CUDA1': 1}),
                           ('compute_bytes', {'CUDA0': 1}), ('lid_nodes', 78), ('fa_nodes', 77)):
            bad = copy.deepcopy(parsed); bad['native'][key] = value
            self.assertEqual(gate(bad, observed)['status'], 'STOP_ALLOCATION_PROOF')
        for section, key, value in (('container_memory_limits', 'cgroup_memory_swap_max', '1'),
                                    ('container_cpu_limits', 'cgroup_cpu_max', '9600000 100000'),
                                    ('container_cpu_limits', 'docker_cpuset_cpus', '0-111')):
            bad = copy.deepcopy(observed); bad[section][key] = value
            self.assertEqual(gate(parsed, bad)['status'], 'STOP_ALLOCATION_PROOF')
        for uuid in manifest['gpu_uuids']:
            bad = copy.deepcopy(observed); bad['gpu_free_bytes'][uuid] = 16 * allocation.GIB - 1
            self.assertEqual(gate(parsed, bad)['status'], 'STOP_ALLOCATION_PROOF')

    def test_effective_cpu_and_no_swap_limits_read_actual_files(self):
        with tempfile.TemporaryDirectory() as directory:
            group = Path(directory)
            for name, value in (('memory.max', str(profiles.G1_RAM_CAP_BYTES)), ('memory.swap.max', '0'),
                                ('cpuset.cpus.effective', '0-95'), ('cpu.max', 'max 100000')):
                (group/name).write_text(value)
            self.assertEqual(LinuxHost.glmrepair_cpu_limits(self.container(), group), self.cpu_limits())
            self.assertEqual(LinuxHost.g1_memory_limits(self.container(), group), self.limits())
            for name, value in (('cpuset.cpus.effective', '0-111'), ('cpu.max', '9600000 100000')):
                old = (group/name).read_text(); (group/name).write_text(value)
                with self.assertRaises(ValueError): LinuxHost.glmrepair_cpu_limits(self.container(), group)
                (group/name).write_text(old)

    def test_glmrepair_precreate_cap_reserve_failure_precedes_writes(self):
        host = host_fixtures.HostTests().bare(); host.scope = 'glmrepair'; host.manager = Mock(); host.mkdir_paths = Mock()
        manifest = profiles.glmrepair_manifest(); host.manifests = {digest(manifest): manifest}
        with patch('benchmark.host.command', return_value=SimpleNamespace(stdout=json.dumps([{'Id': manifest['image']}]).encode())):
            with patch('benchmark.host.collect_sample', return_value={'host': {'available_bytes': profiles.G1_RAM_CAP_BYTES}}):
                with self.assertRaisesRegex(ValueError, 'g1_container_cap_host_reserve_unproved'): host.create(manifest)
        host.mkdir_paths.assert_not_called()

    def test_diagnostic_counters_are_structured_and_raw_logs_private(self):
        host = host_fixtures.HostTests().bare(); host.scope = 'glmrepair'; host.assert_idle = Mock(); host.write_bytes = Mock()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); group_root = base/'cgroup'; group = group_root/'leaf'; group.mkdir(parents=True)
            for name, value in (('memory.max', str(profiles.G1_RAM_CAP_BYTES)), ('memory.swap.max', '0'),
                                ('cpuset.cpus.effective', '0-95'), ('cpu.max', 'max 100000'),
                                ('cpu.stat', 'usage_usec 1000\nnr_throttled 3\nthrottled_usec 45\n')):
                (group/name).write_text(value)
            proc = base/'proc'/'12'; proc.mkdir(parents=True)
            fields = ['0'] * 40
            for offset, value in ((7, '15'), (9, '2'), (11, '100'), (12, '20'), (17, '196'), (19, '700')):
                fields[offset] = value
            (proc/'stat').write_text('12 (llama-server) ' + ' '.join(fields))
            (proc/'status').write_text('Cpus_allowed_list:\t0-95\nMems_allowed_list:\t0-6\n')
            (proc/'numa_maps').write_text('abc default anon=10 N0=3 N1=7\n')
            real_path = Path
            def mapped(value):
                return base/'proc' if str(value) == '/proc' else group_root if str(value) == '/sys/fs/cgroup' else real_path(value)
            host.identity.return_value = (self.container(), group, [12])
            private_raw = b'private model output process_token\n'
            with patch('benchmark.host.Path', side_effect=mapped), patch('benchmark.host.command', return_value=SimpleNamespace(stdout=private_raw, stderr=b'')) as command:
                result = host.dispatch({'op': 'diagnostic_snapshot', 'args': {'id': 'a'*64, 'point': 'before_baseline'}})
            self.assertEqual(result['cpu_stat']['nr_throttled'], 3)
            self.assertEqual(result['processes'][0]['thread_count'], 196)
            self.assertEqual(result['processes'][0]['minor_faults'], 15)
            self.assertEqual(result['processes'][0]['numa_pages_by_node'], {'0': 3, '1': 7})
            self.assertEqual(result['log']['marker_line_counts']['process_token'], 1)
            self.assertNotIn('private model output', json.dumps(result))
            self.assertEqual(host.write_bytes.call_args.args[1], private_raw)
            self.assertEqual(command.call_args.args[0][1:3], ['logs', '--timestamps'])
        host.scope = 'full'
        with self.assertRaises(ValueError): host.diagnostic_snapshot('a'*64, 'before_baseline')


if __name__ == '__main__':
    unittest.main()
