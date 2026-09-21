"""Focused frozen G1 acceptance; offline synthetic proof only."""
import copy
from pathlib import Path
import shlex
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import allocation, profiles
from tests import test_benchmark_allocation as allocation_fixtures
from tests import test_glmrepair_host as host_fixtures


class G1Profile(unittest.TestCase):
    def test_frozen_g1_plan_and_native_arguments(self):
        m = profiles.glmrepair_manifest(profiles.GLMREPAIR_G1_CAMPAIGN)
        arm = {'scope': 'glmrepair', 'campaign': profiles.GLMREPAIR_G1_CAMPAIGN,
               'manifests': [m], 'trial_plan': profiles.trial_order('glmrepair', campaign=profiles.GLMREPAIR_G1_CAMPAIGN)}
        self.assertEqual(profiles.validate_arm_scope(arm), 'glmrepair')
        self.assertEqual(m['placement'], 'G1')
        self.assertEqual(m['gpu_uuids'], ['GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237'])
        self.assertEqual((m['guest_cpu_count'], m['guest_cpuset'], m['ram_cap_bytes']), (96, '0-95', 640 * 1024**3))
        self.assertEqual(m['create_shell'], shlex.join(m['create_argv']))
        for flag, value in (('--threads', '96'), ('--threads-batch', '96'), ('--n-cpu-moe', '76'),
                            ('--log-verbosity', '4'), ('--ctx-size', '4096'), ('--cache-type-k', 'f16'),
                            ('--cache-type-v', 'f16'), ('--batch-size', '2048'), ('--ubatch-size', '512'),
                            ('--split-mode', 'none'), ('--tensor-split', '1'), ('--device', 'CUDA0')):
            self.assertEqual(m['native_argv'][m['native_argv'].index(flag) + 1], value)
        self.assertEqual([t['output_cap'] for t in arm['trial_plan']['trials']], [32, 256, 256])
        self.assertEqual(arm['trial_plan']['trials'][-1]['conditional'], 'duplicate_json_or_literal_think')
        bad = copy.deepcopy(arm); bad['manifests'][0]['guest_cpuset'] = '0-111'
        with self.assertRaisesRegex(ValueError, 'glmrepair_exact_arm_scope_mismatch'):
            profiles.validate_arm_scope(bad)
        bad = copy.deepcopy(arm); bad['trial_plan']['trials'][-1]['output_cap'] = 512
        with self.assertRaisesRegex(ValueError, 'glmrepair_exact_arm_scope_mismatch'):
            profiles.validate_arm_scope(bad)

    def test_g1_strict_proof_and_cpu_memory_reserve_gates(self):
        fixture, limits = allocation_fixtures.Allocation(), host_fixtures.GlmrepairHost()
        manifest = profiles.glmrepair_manifest(profiles.GLMREPAIR_G1_CAMPAIGN)
        parsed = allocation.parse_glm_log(fixture.glm_log(1).replace('lid_nodes=78', 'lid_nodes=21').replace('195035136', '390070272'))
        observed = fixture.observed(manifest)
        observed.update(container_memory_limits=limits.limits(), container_cpu_limits=limits.cpu_limits())
        gate = lambda p, o: allocation.allocation_gate(manifest, p, o, strict_glmrepair=True)
        self.assertEqual(gate(parsed, observed)['status'], 'ALLOCATION_PROOF_ACCEPTED')
        for field, value in (('cache_bytes', {'CUDA0': 1}), ('lid_nodes', 78), ('fa_nodes', 77)):
            bad = copy.deepcopy(parsed); bad['native'][field] = value
            self.assertEqual(gate(bad, observed)['status'], 'STOP_ALLOCATION_PROOF')
        for section, field, value in (('container_memory_limits', 'cgroup_memory_swap_max', '1'),
                                       ('container_cpu_limits', 'docker_cpuset_cpus', '0-111'),
                                       ('container_cpu_limits', 'cgroup_cpu_max', '9600000 100000')):
            bad = copy.deepcopy(observed); bad[section][field] = value
            self.assertEqual(gate(parsed, bad)['status'], 'STOP_ALLOCATION_PROOF')
        bad = copy.deepcopy(observed); bad['gpu_free_bytes'][manifest['gpu_uuids'][0]] = 16 * allocation.GIB - 1
        self.assertEqual(gate(parsed, bad)['status'], 'STOP_ALLOCATION_PROOF')


if __name__ == '__main__':
    unittest.main()
