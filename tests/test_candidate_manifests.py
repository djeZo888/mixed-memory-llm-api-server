"""Closed candidate source checks; no VM, model, mounted storage or auth proof."""
import copy
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.lifecycle.test_qwen38 import BindingFixture
from benchmark import profiles


def flag(argv, name):
    return argv[argv.index(name) + 1]


class CandidateManifests(unittest.TestCase):
    def setUp(self):
        self.binding = BindingFixture(data='/data', models='/data/models-large')
        self.pair, self.qwen = profiles.candidate_modules()

    def test_exact_pair_preserves_production_commands_resources_defaults_and_aliases(self):
        manifests = profiles.candidate_manifests(self.binding)
        self.assertEqual(manifests, profiles.candidate_manifests())
        self.assertEqual([(m['placement'], m['configured_capacity']) for m in manifests],
                         [('G1', 480000), ('Q1', 700160)])
        for m, cpus, cap, port, alias in zip(manifests, ('0-95', '96-111'), (640, 32),
                                            (30002, 30004), ('glm-5.3', 'qwen3.8-27b')):
            d = profiles.candidate_profile(m['placement'], self.binding)
            args = m['create_argv']
            self.assertEqual(flag(args, '--cpuset-cpus'), cpus)
            self.assertEqual(flag(args, '--memory'), str(cap * 1024**3))
            self.assertEqual(flag(args, '--memory-swap'), str(cap * 1024**3))
            self.assertEqual(flag(args, '--publish'), f'127.0.0.1:{port}:{port}/tcp')
            self.assertEqual(m['served_model'], alias)
            self.assertEqual(m['registered_paths']['cache'], d['paths']['cache'])
            self.assertEqual(flag(args, '--restart'), 'no')
            self.assertNotIn('--log-verbosity', args)
            if m['placement'] == 'G1':
                native = self.pair.glm_command(d, {'image_id': m['image'], 'load_mode': 'none'})
                self.assertEqual(m['native_argv'], native)
                self.assertEqual(args[-len(native):], native)
                self.assertEqual(flag(native, '--chat-template-kwargs'),
                                 '{"clear_thinking":true,"reasoning_effort":"low"}')
            else:
                self.assertEqual(args[-1:], self.qwen.command(d))
                self.assertEqual(flag(m['native_argv'], '--context-length'), '700160')
                self.assertEqual(flag(m['native_argv'], '--max-total-tokens'), '700160')
                self.assertEqual(flag(m['native_argv'], '--tp-size'), '1')
                self.assertEqual(flag(m['native_argv'], '--port'), '30004')
                self.assertEqual(flag(m['native_argv'], '--served-model-name'), 'qwen3.8-27b')
                self.assertEqual(flag(m['native_argv'], '--mem-fraction-static'), '0.80')
                self.assertEqual(m['expected_image_ids'], [self.qwen.IMAGE_ID])

    def test_only_owned_identity_evidence_paths_and_identical_staged_pair_wrapper_differ(self):
        for m in profiles.candidate_manifests():
            differences = m['production_differences']
            self.assertEqual(set(differences), {'container_name', 'labels', 'paths'})
            expected = {'/logs', '/service'} | ({self.qwen.PAIR_LAUNCHER_TARGET} if m['placement'] == 'Q1' else set())
            self.assertEqual(set(differences['paths']), expected)
            self.assertEqual(m['status'], 'CANDIDATE_UNVALIDATED')
            self.assertEqual(m['live_allocation'], 'NOT_TESTED')
            self.assertEqual(m['storage_binding'], 'REQUIRES_REGISTERED_LIVE_REGENERATION')
            if m['placement'] == 'Q1':
                mount = next(row for row in m['mounts'] if row['target'] == self.qwen.PAIR_LAUNCHER_TARGET)
                self.assertTrue(mount['read_only'])
                self.assertEqual(mount['source'], m['registered_paths']['source'] + '/scripts/runtime/sglang38_pair_file_auth.py')
                for name, sha in m['wrapper_sha256'].items():
                    self.assertEqual(hashlib.sha256((profiles.ROOT / name).read_bytes()).hexdigest(), sha)

    def test_registered_binding_failure_is_not_source_render_success(self):
        self.binding.fail = True
        with self.assertRaises(self.pair.LifecycleError):
            profiles.candidate_manifests(self.binding)
        with self.assertRaises(ValueError):
            profiles.candidate_profile('G1', None)
        self.assertEqual(profiles.candidate_manifests()[0]['storage_binding'],
                         'REQUIRES_REGISTERED_LIVE_REGENERATION')

    def test_live_binding_paths_and_production_contract_are_rechecked(self):
        other = BindingFixture(data='/srv/ai', models='/mnt/models')
        manifests = profiles.candidate_manifests(other)
        self.assertNotEqual(manifests, profiles.candidate_manifests())
        self.assertTrue(all(m['registered_paths']['service'].startswith('/srv/ai/services/') for m in manifests))
        self.assertTrue(other.checked)
        with patch.object(self.pair, 'glm_command', return_value=['unreviewed']), self.assertRaisesRegex(
                ValueError, 'candidate_production_launch_render_mismatch'):
            profiles.candidate_manifests(self.binding)

    def test_validation_does_not_call_or_bypass_production_acceptance(self):
        with patch.object(self.pair, 'check_acceptance', side_effect=AssertionError('no candidate receipt')):
            profiles.candidate_manifests(self.binding)
        for placement in ('G1', 'Q1'):
            d = profiles.candidate_profile(placement, self.binding)
            with self.assertRaisesRegex(self.pair.LifecycleError, 'concurrent_reviewed_acceptance_required'):
                self.pair.check_acceptance(d, {})
        self.assertEqual(self.binding.documents, {})
        self.assertEqual(self.binding.reads, [])

    def test_staged_candidate_package_does_not_replace_canonical_lifecycle(self):
        import lifecycle.concurrent_profiles as installed
        self.assertNotEqual(self.pair.__name__, installed.__name__)
        self.assertEqual(Path(self.pair.__file__).resolve(), profiles.ROOT / 'scripts/lifecycle/concurrent_profiles.py')
        self.assertIs(profiles.candidate_modules()[0], self.pair)

    def test_closed_arm_and_plan_reject_all_manifest_mutations(self):
        arm = {'scope': profiles.CANDIDATE_SCOPE, 'campaign': profiles.CANDIDATE_CAMPAIGN,
               'manifests': profiles.candidate_manifests(), 'trial_plan': profiles.trial_order(profiles.CANDIDATE_SCOPE)}
        self.assertEqual(profiles.validate_arm_scope(arm), profiles.CANDIDATE_SCOPE)
        changes = [lambda a: a.update(campaign='benchrun-arbitrary'),
            lambda a: a['manifests'][0].update(configured_capacity=500000),
            lambda a: a['manifests'][1].update(ram_cap_bytes=64 * 1024**3),
            lambda a: a['manifests'][0]['create_argv'].extend(['--log-verbosity', '4']),
            lambda a: a['manifests'][1].update(served_model='bench-qwen3.8-27b'),
            lambda a: a['trial_plan'].update(no_near_capacity_fit=False),
            lambda a: a['trial_plan'].update(output_cap=2048)]
        for change in changes:
            bad = copy.deepcopy(arm); change(bad)
            with self.assertRaisesRegex(ValueError, 'candidate_exact_arm_scope_mismatch'):
                profiles.validate_arm_scope(bad)
        for placement in ('G2', 'Q2', 'G480000', '', None):
            with self.assertRaises(ValueError):
                profiles.candidate_manifest(placement)
        with self.assertRaises(TypeError):
            profiles.candidate_manifest('G1', capacity=500000)
        with self.assertRaises(ValueError):
            profiles.command_manifest('G1', 480000, scope=profiles.CANDIDATE_SCOPE)

    def test_short_plan_has_no_ladder_measurement_clock_or_occupied_capacity_claim(self):
        plan = profiles.trial_order(profiles.CANDIDATE_SCOPE)
        self.assertEqual(plan, {'trials': [], 'mixed_jobs': [], 'kind': 'short_candidate_checks',
            'placements': ['G1', 'Q1'], 'warmup_records': 12, 'smoke_records': 12,
            'tool_records': 12, 'output_cap': 256, 'no_near_capacity_fit': True})
        self.assertEqual(profiles.scope_placements(profiles.CANDIDATE_SCOPE), ('G1', 'Q1'))
        self.assertEqual(profiles.scope_capacities(profiles.CANDIDATE_SCOPE), (480000, 700160))


if __name__ == '__main__':
    unittest.main()
