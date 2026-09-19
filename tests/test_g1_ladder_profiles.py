"""Two-load G1 ladder source/host admission; synthetic offline proof only."""
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
from tests import test_glmrepair_host as limit_fixtures


class LadderProfiles(unittest.TestCase):
    def arm(self):
        return {'scope': 'g1-ladder', 'campaign': profiles.G1_LADDER_CAMPAIGN,
                'manifests': [profiles.g1_ladder_manifest(n) for n in (16384, 65536)],
                'trial_plan': profiles.trial_order('g1-ladder'),
                'runtime': {'start_epoch': 1000, 'deadline_epoch': 11800, 'budget_seconds': 10800,
                            'clock_includes_preparation': True, 'restoration_outside_budget': True}}

    def test_two_profiles_native_context_only_delta(self):
        frozen = profiles.glmrepair_manifest(profiles.GLMREPAIR_G1_CAMPAIGN)
        for capacity, cache_bytes in ((16384, 1560281088), (65536, 6241124352)):
            manifest = profiles.g1_ladder_manifest(capacity)
            native = list(manifest['native_argv'])
            native[native.index('--ctx-size') + 1] = '4096'
            self.assertEqual(native, frozen['native_argv'])
            self.assertNotIn('--poll', native)  # Preserve pinned original default50.
            self.assertEqual(manifest['create_shell'], shlex.join(manifest['create_argv']))
            self.assertEqual(manifest['gpu_uuids'], ['GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237'])
            self.assertEqual((manifest['guest_cpu_count'], manifest['guest_cpuset'], manifest['ram_cap_bytes']),
                             (96, '0-95', 640 * 1024**3))
            self.assertEqual(95232 * capacity, cache_bytes)
            for flag in ('--memory', '--memory-swap'):
                self.assertEqual(manifest['create_argv'][manifest['create_argv'].index(flag) + 1], str(640 * 1024**3))
            restored = json.loads(json.dumps(manifest).replace(manifest['container_name'], frozen['container_name'])
                                  .replace(profiles.G1_LADDER_CAMPAIGN, profiles.GLMREPAIR_G1_CAMPAIGN))
            restored['configured_capacity'] = 4096
            for key in ('native_argv', 'create_argv'):
                restored[key][restored[key].index('--ctx-size') + 1] = '4096'
            restored['create_shell'] = shlex.join(restored['create_argv'])
            self.assertEqual(restored, frozen)
        for capacity in (4096, 131072, 262144, 1000000, True):
            with self.assertRaisesRegex(ValueError, 'outside_scope'):
                profiles.g1_ladder_manifest(capacity)

    def test_exact_plan_and_scope_expansion_refusal(self):
        arm = self.arm()
        self.assertEqual(profiles.validate_arm_scope(arm), 'g1-ladder')
        trials = arm['trial_plan']['trials']
        self.assertEqual([(t['capacity'], t['case'], t['output_cap']) for t in trials],
                         [(16384, 'load_warmup', 32), (16384, 'primary', 256),
                          (16384, 'repeat_anchor', 256), (65536, 'load_warmup', 32), (65536, 'primary', 256)])
        self.assertEqual(arm['trial_plan']['mixed_jobs'], [])
        variants = []
        for field, value in (('campaign', profiles.GLMREPAIR_G1_CAMPAIGN),
                             ('manifests', list(reversed(arm['manifests']))), ('manifests', arm['manifests'] * 2)):
            bad = copy.deepcopy(arm); bad[field] = value; variants.append(bad)
        bad = copy.deepcopy(arm); bad['trial_plan']['trials'][1]['output_cap'] = 512; variants.append(bad)
        bad = copy.deepcopy(arm); bad['manifests'][0]['native_argv'] += ['--poll', '0']; variants.append(bad)
        for bad in variants:
            with self.assertRaisesRegex(ValueError, 'g1_ladder_exact_arm_scope_mismatch'):
                profiles.validate_arm_scope(bad)

    def test_fresh_absolute_clock_and_restoration_outside_budget(self):
        self.assertEqual(LinuxHost.ladder_clock(self.arm()), (1000, 11800))
        for field, value in (('start_epoch', True), ('deadline_epoch', 11801), ('budget_seconds', 21600),
                             ('clock_includes_preparation', False), ('restoration_outside_budget', False),
                             ('start_epoch', float('nan')), ('deadline_epoch', float('inf'))):
            bad = self.arm(); bad['runtime'][field] = value
            with self.assertRaisesRegex(ValueError, 'g1_ladder_fresh_immutable_clock_required'):
                LinuxHost.ladder_clock(bad)
        bad = self.arm(); bad['continuation_execution'] = bad['runtime']
        with self.assertRaises(ValueError): LinuxHost.ladder_clock(bad)
        host = SimpleNamespace(scope='g1-ladder', log_root='/data/logs/ladder', start_epoch=1000,
                               deadline_epoch=11800, read_json=Mock(return_value=None), write_json=Mock())
        with patch('benchmark.host.time.time', return_value=1300):
            budget = HostBudget(host); budget.start('maintenance')
        budget.clock = lambda: 1300
        self.assertEqual(budget.request_timeout(7200), 7200)
        budget.clock = lambda: 11790
        self.assertEqual(budget.request_timeout(7200), 10)
        budget.clock = lambda: 11800
        with self.assertRaisesRegex(ValueError, 'STOP_BUDGET'): budget.request_timeout()
        budget.begin_restoration(); budget.clock = lambda: 13000; budget.finish_restoration(True)
        self.assertEqual((budget.data['phase'], budget.data['start_epoch'], budget.data['deadline_epoch']),
                         ('RESTORED', 1000, 11800))
        host.read_json.return_value = budget.data
        self.assertEqual(HostBudget(host).data['phase'], 'RESTORED')
        host.deadline_epoch += 1
        with self.assertRaisesRegex(ValueError, 'immutable_clock_changed'): HostBudget(host)

    def test_no_resume_or_mixed_and_precreate_reserve_before_writes(self):
        host = host_fixtures.HostTests().bare(); host.scope = 'g1-ladder'; host.read_json = Mock()
        for message in ({'op': 'begin', 'args': {'resume': True}}, {'op': 'admit_mixed'}):
            with self.assertRaises(ValueError): host.dispatch(message)
        host.read_json.assert_not_called()
        host.manager = Mock(); host.mkdir_paths = Mock()
        manifest = profiles.g1_ladder_manifest(16384); host.manifests = {digest(manifest): manifest}
        with patch('benchmark.host.command', return_value=SimpleNamespace(stdout=json.dumps([{'Id': manifest['image']}]).encode())), \
             patch('benchmark.host.collect_sample', return_value={'host': {'available_bytes': profiles.G1_RAM_CAP_BYTES}}):
            with self.assertRaisesRegex(ValueError, 'g1_container_cap_host_reserve_unproved'): host.create(manifest)
        host.mkdir_paths.assert_not_called()

    def test_native_cache_graph_and_actual_host_limits_required(self):
        fixture, limits = allocation_fixtures.Allocation(), limit_fixtures.GlmrepairHost()
        with tempfile.TemporaryDirectory() as directory:
            group = Path(directory)
            for filename, value in (('memory.max', str(profiles.G1_RAM_CAP_BYTES)), ('memory.swap.max', '0'),
                                    ('cpuset.cpus.effective', '0-95'), ('cpu.max', 'max 100000')):
                (group / filename).write_text(value)
            for capacity in (16384, 65536):
                manifest = profiles.g1_ladder_manifest(capacity)
                raw = fixture.glm_log(1).replace('4096', str(capacity)).replace('lid_nodes=78', 'lid_nodes=21')
                raw = raw.replace('195035136', str(95232 * capacity)).encode()
                container = limits.container()
                container['Config'] = {'Image': manifest['image'], 'Cmd': manifest['native_argv']}
                container['HostConfig']['DeviceRequests'] = [{'DeviceIDs': manifest['gpu_uuids']}]
                container['Mounts'] = [{'Source': '/data/models-large/glm-5.3-ud-q4-k-xl', 'Destination': '/models', 'RW': False}]
                host = host_fixtures.HostTests().bare(); host.scope = 'g1-ladder'; host.manager = Mock()
                host.assert_idle = Mock(); host.write_bytes = Mock()
                host.identity.return_value = (container, group, [1])
                host.load_manifests['a' * 64] = manifest
                host.cuda_mapping = Mock(return_value=manifest['gpu_uuids'])
                host.telemetry = Mock(return_value={'gpus': [{'uuid': manifest['gpu_uuids'][0], 'free_bytes': 20 * allocation.GIB}]})
                with patch('benchmark.host.command', return_value=SimpleNamespace(stdout=raw, stderr=b'')):
                    result = host.allocation('a' * 64)
                    self.assertEqual(result['allocation']['status'], 'ALLOCATION_PROOF_ACCEPTED')
                    self.assertEqual(result['observed']['container_cpu_limits'], limits.cpu_limits())
                    self.assertEqual(result['observed']['container_memory_limits'], limits.limits())
                    for filename, value in (('memory.swap.max', '1'), ('memory.max', '1'),
                                            ('cpuset.cpus.effective', '0-111'), ('cpu.max', '9600000 100000')):
                        previous = (group / filename).read_text(); (group / filename).write_text(value)
                        with self.assertRaises(ValueError): host.allocation('a' * 64)
                        (group / filename).write_text(previous)
                for field, value in (('cache_bytes', {'CUDA0': 95232 * capacity - 1}), ('lid_nodes', 78), ('fa_nodes', 77)):
                    bad = copy.deepcopy(result['parsed']); bad['native'][field] = value
                    self.assertEqual(allocation.allocation_gate(manifest, bad, result['observed'], strict_g1=True)['status'],
                                     'STOP_ALLOCATION_PROOF')


if __name__ == '__main__':
    unittest.main()
