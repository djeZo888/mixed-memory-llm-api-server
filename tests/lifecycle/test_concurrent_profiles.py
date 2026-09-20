"""Synthetic fixed-pair contracts only; never write an acceptance receipt."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.lifecycle.test_qwen38 import (BindingFixture, LifecycleError, bound as qbound, q,
                                       auth_receipt, container as qcontainer, image as qimage)
from tests.lifecycle.test_sglang38_file_auth import args_fixture
from lifecycle import concurrent_profiles as pair
from lifecycle.manager import Manager
from runtime import sglang38_pair_file_auth as launcher


def bound(identifier, binding=None):
    binding = binding or BindingFixture()
    binding.identity = {'synthetic': 'registered-storage-fixture'}
    d = pair.declared_profile(identifier)
    d, _ = q._bound_expected(d, binding)
    d['_storage_binding'] = binding
    return d


def receipt(d):
    """In-memory schema fixture; this is not a live measurement or authority."""
    binding = d['_storage_binding']
    value = {'schema_version': 1, 'kind': 'root-reviewed-concurrent-g1q1',
        'status': 'ACCEPTED_FOR_ACTIVATION', 'instance_id': 'synthetic-instance',
        'storage_identity': binding.identity, 'reviewed_source_commit': 'a' * 40,
        'source_sha256': pair.source_identity(), 'concurrency_performance_review': 'ACCEPTED',
        'evidence': ['SYNTHETIC in-memory unit fixture, not live evidence'],
        'gpu_inventory': list(enumerate(pair.GPU_UUIDS)), 'slots': {}, 'host_usable_bytes': 800 * 1024**3}
    for slot, identifier in pair.SLOTS.items():
        expected = pair.declared_profile(identifier)
        resource = expected['concurrent_pair']
        value['slots'][slot] = {
            'deployment': identifier, 'configured_context': expected['launch']['context_size'],
            'profile_sha256': pair.PINS['configs/deployments/' + identifier + '.json'],
            'runtime_image_id': expected['_runtime']['validation']['image_id'] if slot == 'glm' else expected['_runtime']['image_id'],
            'model_revision': expected['_model']['revision'],
            'visible_cuda_devices': {'CUDA0': expected['launch']['gpus'][0]},
            'guest_cpu_count': resource['guest_cpu_count'], 'guest_cpuset': resource['guest_cpuset'],
            'memory_bytes': resource['memory_bytes'], 'memory_swap_bytes': resource['memory_swap_bytes'],
            'allocation': 'PASS', 'short_inference': 'PASS', 'correctness': 'PASS',
            'largest_occupied_context': 65008 if slot == 'glm' else 699000,
            'host_peak_bytes': resource['memory_bytes'] // 2, 'minimum_free_gpu_bytes': 20 * 1024**3,
            'gpu_total_bytes': 96 * 1024**3}
        if slot == 'qwen':
            value['slots'][slot].update(pair_launcher_sha256=pair.PINS['scripts/runtime/sglang38_pair_file_auth.py'],
                native_auth_checks={name: 'PASS' for name in q.AUTH_CHECKS})
    path = binding.path('data', pair.ACCEPTANCE_SUFFIX)
    binding.documents[path] = value
    instance = {'id': 'synthetic-instance', 'concurrent_pair_acceptance': {
        'path': path, 'sha256': pair.receipt_sha256(value), 'reviewed_source_commit': 'a' * 40}}
    return value, instance


def inspect_fixture(d):
    resource = d['concurrent_pair']
    return {'Config': {'Env': ['CUDA_VISIBLE_DEVICES=' + d['launch']['gpus'][0]]}, 'HostConfig': {
        'CpusetCpus': resource['guest_cpuset'], 'Memory': resource['memory_bytes'],
        'MemorySwap': resource['memory_swap_bytes'], 'RestartPolicy': {'Name': 'no', 'MaximumRetryCount': 0},
        'DeviceRequests': [{'Driver': 'nvidia', 'Count': 0, 'DeviceIDs': d['launch']['gpus'],
                            'Capabilities': [['gpu']]}]}}


class Profiles(unittest.TestCase):
    def test_fixed_pair_retains_model_runtime_and_endpoints(self):
        for slot, identifier in pair.SLOTS.items():
            d = bound(identifier)
            pair.validate(d)
            self.assertEqual(pair.slot_for_deployment(identifier), slot)
            self.assertEqual(d['capability_status'], 'UNVALIDATED')
            self.assertEqual(d['endpoint']['port'], 30002 if slot == 'glm' else 30004)
            self.assertEqual(d['docker_restart_policy'], 'no')
            self.assertEqual(len(d['launch']['gpus']), 1)
            self.assertIn('--memory-swap', pair.resource_args(d))
            self.assertEqual(d['concurrent_pair']['memory_bytes'], d['concurrent_pair']['memory_swap_bytes'])
        self.assertIsNone(pair.slot_for_deployment('arbitrary'))
        self.assertIsNone(pair.slot_for_deployment([]))

    def test_compatible_pair_and_preserved_tp2_conflicts(self):
        glm, qwen = bound(pair.GLM_PROFILE), bound(pair.QWEN_PROFILE)
        pair.validate_pair(glm, qwen)
        pair.validate_pair(qwen, glm)
        for peer in (glm, {}, qbound(q.EXTENSION_PROFILE), qbound()):
            with self.subTest(peer=peer.get('id')), self.assertRaises(LifecycleError):
                pair.validate_pair(glm, peer)

    def test_closed_fields_and_binding_cannot_be_overridden(self):
        changes = [lambda d: d['launch'].update(context_size=500000),
            lambda d: d['launch'].update(gpus=['0']), lambda d: d['launch'].update(gpus=[pair.GPU_UUIDS[1]]),
            lambda d: d['launch'].update(threads=112), lambda d: d['launch'].update(cache_type_k='q8_0'),
            lambda d: d['concurrent_pair'].update(guest_cpuset='0-111'),
            lambda d: d['concurrent_pair'].update(memory_bytes=800 * 1024**3),
            lambda d: d['launch_environment'].update(CUDA_VISIBLE_DEVICES='0'),
            lambda d: d['_runtime'].update(source_revision='unreviewed'),
            lambda d: d['_model'].update(revision='unreviewed'),
            lambda d: d['endpoint'].update(host='0.0.0.0'), lambda d: d.update(user_arguments=[])]
        for change in changes:
            d = bound(pair.GLM_PROFILE); change(d)
            with self.assertRaisesRegex(LifecycleError, 'concurrent_profile_contract_mismatch'):
                pair.validate(d)
        d = bound(pair.QWEN_PROFILE); d.pop('_storage_binding')
        with self.assertRaises(LifecycleError):
            pair.validate(d)

    def test_source_byte_drift_is_rejected(self):
        relative = 'configs/deployments/' + pair.GLM_PROFILE + '.json'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); target = root / relative
            target.parent.mkdir(parents=True); target.write_bytes((pair.ROOT / relative).read_bytes() + b'\n')
            with patch.object(pair, 'ROOT', root), self.assertRaisesRegex(LifecycleError, 'concurrent_source_pin_mismatch'):
                pair.declared_profile(pair.GLM_PROFILE)

    def test_gpu_inventory_rejects_indices_duplicates_unknown_and_remapping(self):
        pair.validate_gpu_inventory('0, ' + pair.GPU_UUIDS[0] + '\n1, ' + pair.GPU_UUIDS[1] + '\n')
        for rows in ([(0, pair.GPU_UUIDS[1]), (1, pair.GPU_UUIDS[0])], [(0, pair.GPU_UUIDS[0])],
                     [(0, pair.GPU_UUIDS[0]), (0, pair.GPU_UUIDS[1])], [], None, '0, unknown\n1, unknown'):
            with self.subTest(rows=rows), self.assertRaisesRegex(LifecycleError, 'concurrent_gpu_inventory_mismatch'):
                pair.validate_gpu_inventory(rows)

    def test_glm_full_command_pins_allocation_and_native_defaults(self):
        d = bound(pair.GLM_PROFILE)
        e = {'image_id': d['_runtime']['validation']['image_id'], 'load_mode': 'none'}
        argv = pair.glm_command(d, e)
        for flag, value in [('--ctx-size', '480000'), ('--threads', '96'), ('--threads-batch', '96'),
            ('--device', 'CUDA0'), ('--cache-type-k', 'f16'), ('--cache-type-v', 'f16'),
            ('--fit', 'off'), ('--batch-size', '2048'), ('--ubatch-size', '512'), ('--main-gpu', '0')]:
            self.assertEqual(argv[argv.index(flag) + 1], value)
        self.assertEqual(json.loads(argv[-1]), {'clear_thinking': True, 'reasoning_effort': 'low'})
        with self.assertRaisesRegex(LifecycleError, 'concurrent_glm_runtime_mismatch'):
            pair.glm_command(d, dict(e, load_mode='auto'))

    def test_exact_reuse_resource_and_cuda_contract(self):
        for identifier in pair.SLOTS.values():
            d = bound(identifier); c = inspect_fixture(d)
            pair.validate_reuse(c, d)
            changes = [lambda c: c['HostConfig'].update(MemorySwap=-1),
                lambda c: c['HostConfig'].update(Memory=True),
                lambda c: c['HostConfig'].update(CpuQuota=100000),
                lambda c: c['HostConfig'].update(CpusetMems='0'),
                lambda c: c['HostConfig'].update(CpusetCpus='0-111'),
                lambda c: c['HostConfig'].update(RestartPolicy={'Name': 'always', 'MaximumRetryCount': 0}),
                lambda c: c['HostConfig']['DeviceRequests'][0].update(DeviceIDs=['1']),
                lambda c: c['HostConfig']['DeviceRequests'][0].update(Count=True),
                lambda c: c['Config'].update(Env=['CUDA_VISIBLE_DEVICES=0']),
                lambda c: c['Config']['Env'].append(c['Config']['Env'][0])]
            for change in changes:
                bad = copy.deepcopy(c); change(bad)
                with self.subTest(identifier=identifier), self.assertRaises(LifecycleError):
                    pair.validate_reuse(bad, d)


class Acceptance(unittest.TestCase):
    def test_source_profile_never_implies_live_acceptance(self):
        for identifier in pair.SLOTS.values():
            with self.assertRaisesRegex(LifecycleError, 'concurrent_reviewed_acceptance_required'):
                pair.check_acceptance(bound(identifier), {})

    def test_protected_receipt_binds_both_slots_and_occupied_context_separately(self):
        d = bound(pair.GLM_PROFILE); proof, instance = receipt(d)
        accepted = pair.check_acceptance(d, instance)
        self.assertEqual(accepted['slots']['glm']['configured_context'], 480000)
        self.assertEqual(accepted['slots']['glm']['largest_occupied_context'], 65008)
        pair.check_acceptance(bound(pair.QWEN_PROFILE, d['_storage_binding']), instance)

    def test_actual_capacity_source_and_margin_evidence_fail_closed(self):
        d = bound(pair.QWEN_PROFILE); original, instance = receipt(d)
        path = instance['concurrent_pair_acceptance']['path']
        changes = [lambda p: p.update(status='UNVALIDATED'), lambda p: p.update(schema_version=True),
            lambda p: p.update(instance_id='another-host'), lambda p: p.update(source_sha256={}),
            lambda p: p.update(storage_identity={}), lambda p: p.update(host_usable_bytes=100),
            lambda p: p.update(concurrency_performance_review='PENDING'), lambda p: p['slots'].pop('glm'),
            lambda p: p['slots']['glm'].update(configured_context=500000),
            lambda p: p['slots']['glm'].update(allocation='NOT_TESTED'),
            lambda p: p['slots']['glm'].update(host_peak_bytes=640 * 1024**3),
            lambda p: p['slots']['qwen'].update(minimum_free_gpu_bytes=15 * 1024**3),
            lambda p: p['slots']['qwen'].update(gpu_total_bytes=300 * 1024**3),
            lambda p: p['slots']['qwen'].update(visible_cuda_devices={'CUDA0': pair.GPU_UUIDS[0]}),
            lambda p: p['slots']['qwen'].update(native_auth_checks={}),
            lambda p: p['slots']['qwen'].update(pair_launcher_sha256='0' * 64),
            lambda p: p['slots']['qwen'].update(largest_occupied_context=True)]
        for change in changes:
            proof = copy.deepcopy(original); change(proof)
            d['_storage_binding'].documents[path] = proof
            instance['concurrent_pair_acceptance']['sha256'] = pair.receipt_sha256(proof)
            with self.assertRaises(LifecycleError):
                pair.check_acceptance(d, instance)

    def test_receipt_digest_and_canonical_path_are_mandatory(self):
        d = bound(pair.GLM_PROFILE); _, instance = receipt(d)
        instance['concurrent_pair_acceptance']['sha256'] = '0' * 64
        with self.assertRaisesRegex(LifecycleError, 'concurrent_acceptance_digest_mismatch'):
            pair.check_acceptance(d, instance)
        instance['concurrent_pair_acceptance']['path'] = '/tmp/arbitrary.json'
        with self.assertRaisesRegex(LifecycleError, 'concurrent_reviewed_acceptance_required'):
            pair.check_acceptance(d, instance)


class QwenPairLauncher(unittest.TestCase):
    def setUp(self):
        self.base = launcher.pinned_base(pair.ROOT / 'scripts/runtime/sglang38_file_auth.py')

    def test_closed_argv_retains_yarn4_tp1_defaults_and_container_cuda0(self):
        d = bound(pair.QWEN_PROFILE)
        self.assertEqual(q.command(d), [q.PAIR_LAUNCHER_TARGET])
        self.assertEqual(q.launcher_targets(d), {q.LAUNCHER_TARGET, q.PAIR_LAUNCHER_TARGET})
        self.assertEqual(q.launch_environment(d)['CUDA_VISIBLE_DEVICES'], pair.GPU_UUIDS[1])
        argv = launcher.bind_variant(self.base)
        self.assertEqual(self.base.parse_options(argv)[0].context_length, '700160')
        for flag, value in [('--tp-size', '1'), ('--base-gpu-id', '0'), ('--max-total-tokens', '700160'),
                            ('--json-model-override-args', self.base.EXTENSION_OVERRIDE_JSON)]:
            self.assertEqual(argv[argv.index(flag) + 1], value)
        for invalid in (argv[::-1], argv + ['--context-length', '700160'], argv[:-1]):
            with self.assertRaises(self.base.LaunchError):
                self.base.parse_options(invalid)

    def test_raw_and_resolved_tuple_and_unchanged_auth_guards(self):
        launcher.bind_variant(self.base)
        for resolved in (False, True):
            args = args_fixture(1000000, resolved=resolved)
            args.context_length = args.max_total_tokens = 700160; args.tp_size = 1
            self.base.validate_server_args(args, resolved=resolved)
            for field, value in [('context_length', 700161), ('max_total_tokens', True), ('tp_size', 2),
                ('base_gpu_id', 1), ('api_key', 'synthetic-prohibited'), ('kv_cache_dtype', 'fp8'),
                ('json_model_override_args', '{}'), ('served_model_name', 'bench-qwen3.8-27b')]:
                bad = copy.deepcopy(args); setattr(bad, field, value)
                with self.subTest(field=field, resolved=resolved), self.assertRaises(self.base.LaunchError):
                    self.base.validate_server_args(bad, resolved=resolved)

    def test_original_launcher_bytes_and_context_set_are_unchanged(self):
        with self.assertRaises(self.base.LaunchError):
            self.base.backend_argv(700160)
        self.assertEqual(self.base.ACCEPTED_CONTEXTS, (131072, 262144, 1000000))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'base.py'; path.write_text('raise AssertionError("must not import")')
            with self.assertRaisesRegex(ValueError, 'pair_auth_source_mismatch'):
                launcher.pinned_base(path)


class ManagerPairIntegration(unittest.TestCase):
    """Real Manager create/reuse validation; synthetic image, storage and receipts."""
    def setUp(self):
        self.binding = BindingFixture()
        self.binding.identity = {'synthetic': 'registered-storage-fixture'}
        self.manager = Manager(pair.ROOT / 'configs', {'schema_version': 1, 'id': 'synthetic-instance',
            'storage_identity': self.binding.identity,
            'paths': {'state': {'role': 'data', 'suffix': 'services/llm-manager/active'}}},
            binding=self.binding, test_paths=True,
            run_fn=lambda *a, **k: self.fail('unexpected external process'))
        self.inspects = []
        self.images = {}
        def capture(*args, **kwargs):
            self.inspects.append(args)
            self.assertEqual(args[:2], ('image', 'inspect'))
            return json.dumps([self.images[args[2]]])
        self.manager.docker.capture = capture
        self.launcher_patch = patch.object(q, '_protected_bytes',
            side_effect=lambda path: (pair.ROOT / 'scripts/runtime' / Path(path).name).read_bytes())
        self.launcher_patch.start()
        self.addCleanup(self.launcher_patch.stop)

    def prepare(self, identifier):
        d = self.manager.deployment(identifier)
        _, instance = receipt(d)
        self.manager.instance.update(instance)
        if identifier == pair.QWEN_PROFILE:
            _, runtime = auth_receipt(d)
            self.manager.instance.update(runtime)
            self.images[q.IMAGE_REFERENCE] = qimage(d)
            c = qcontainer(d)
        else:
            e = dict(d['_runtime']['validation'], flags_verified=True, load_mode='none',
                     evidence=['SYNTHETIC runtime evidence'])
            self.manager.instance['runtime_evidence'] = {d['runtime']: e}
            self.images[d['_runtime']['image_tag']] = {'Id': e['image_id'],
                'Config': {'Entrypoint': d['_runtime']['entrypoint']}}
            c = {'Image': e['image_id'], 'Config': {'Entrypoint': d['_runtime']['entrypoint'],
                'Cmd': self.manager.launch_command(d, e),
                'Env': [key + '=' + value for key, value in
                        {**d['_runtime']['environment'], **pair.launch_environment(d)}.items()]},
                'Mounts': [{'Source': m['source'], 'Destination': m['target'], 'RW': not m['read_only']}
                           for m in d['mounts']], 'HostConfig': {
                    'LogConfig': {'Type': 'json-file', 'Config': {'max-size': '20m', 'max-file': '3'}}}}
        c['HostConfig'].update(inspect_fixture(d)['HostConfig'])
        return d, c

    def test_real_manager_create_and_reuse_both_exact_candidates(self):
        for identifier in pair.SLOTS.values():
            d, c = self.prepare(identifier)
            args = self.manager.create_args(d)
            self.assertEqual(args[args.index('--gpus') + 1], '"device=' + d['launch']['gpus'][0] + '"')
            self.assertEqual(args[args.index('--cpuset-cpus') + 1], d['concurrent_pair']['guest_cpuset'])
            self.assertEqual(args[args.index('--memory-swap') + 1], str(d['concurrent_pair']['memory_bytes']))
            self.assertEqual(args.count('--mount'), 7 if identifier == pair.QWEN_PROFILE else 5)
            self.assertIn('CUDA_VISIBLE_DEVICES=' + d['launch']['gpus'][0], args)
            self.assertEqual(args[args.index('--publish') + 1],
                '127.0.0.1:' + str(d['endpoint']['port']) + ':' + str(d['container_port']) + '/tcp')
            self.manager.validate_reused_contract(c, d)
            for change in (lambda c: c['HostConfig'].update(CpusetCpus='0-111'),
                lambda c: c['HostConfig'].update(MemorySwap=-1),
                lambda c: c['HostConfig']['DeviceRequests'][0].update(DeviceIDs=['0']),
                lambda c: c['Config'].update(Cmd=['arbitrary'])):
                bad = copy.deepcopy(c); change(bad)
                with self.assertRaises(LifecycleError):
                    self.manager.validate_reused_contract(bad, d)

    def test_create_and_reuse_need_acceptance_even_with_prior_native_runtime_proof(self):
        for identifier in pair.SLOTS.values():
            d, c = self.prepare(identifier)
            self.manager.instance.pop('concurrent_pair_acceptance')
            self.inspects.clear()
            with self.assertRaisesRegex(LifecycleError, 'concurrent_reviewed_acceptance_required'):
                self.manager.create_args(d)
            self.assertEqual(self.inspects, [])
            with self.assertRaisesRegex(LifecycleError, 'concurrent_reviewed_acceptance_required'):
                self.manager.validate_reused_contract(c, d)

    def test_current_gpu_inventory_blocks_before_artifacts_or_container_creation(self):
        d, _ = self.prepare(pair.GLM_PROFILE)
        wrong = '0, ' + pair.GPU_UUIDS[1] + '\n1, ' + pair.GPU_UUIDS[0]
        with patch.object(self.manager, 'check_sources'), patch.object(self.manager, 'host_guards'), \
                patch.object(self.manager, 'run', return_value=wrong) as run, \
                patch.object(self.manager, 'check_artifacts') as artifacts:
            with self.assertRaisesRegex(LifecycleError, 'concurrent_gpu_inventory_mismatch'):
                self.manager.prepare_start(d)
            run.assert_called_once_with(['nvidia-smi', '--query-gpu=index,uuid', '--format=csv,noheader'], timeout=30)
            artifacts.assert_not_called()
            self.assertEqual(self.inspects, [])


if __name__ == '__main__':
    unittest.main()
