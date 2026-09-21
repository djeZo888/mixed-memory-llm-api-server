"""Q38MAX source contracts only: synthetic receipts/host I/O, no live acceptance."""
import copy
import hashlib
import json
import unittest

from tests.lifecycle.test_qwen38 import ROOT, bound, auth_receipt, container, q, launcher, LifecycleError
from tests.lifecycle.test_qwen38_image_fixture import host, native_result, lifetime
from tests.lifecycle import test_qwen38_manager as manager_tests


def extension_receipt(d):
    """In-memory negative/positive schema collaborator; never publish a receipt."""
    native, instance = auth_receipt(d)
    provenance = json.loads((ROOT / 'tests/lifecycle/sglang38_fixture/provenance.json').read_text())
    extra = {'extension_identity': host.extension_identity(ROOT, provenance),
             'model_config_resolution': host.expected_extension_resolution(provenance)}
    extension = copy.deepcopy(native)
    extension.update(kind='q38max_actual_image_auth', contexts=[1000000], **extra,
        native_results=[dict(native_result(provenance, 1000000), **extra)],
        container_lifetimes=[lifetime(1000000)])
    binding = d['_storage_binding']
    path = binding.path('data', q.EXTENSION_PROOF_SUFFIX)
    binding.documents[path] = extension
    instance['runtime_evidence'][q.RUNTIME]['extension_auth_gate_evidence'] = path
    return native, extension, instance


class ExtensionAdapter(unittest.TestCase):
    def test_closed_pinned_profiles_same_identity_and_native_bytes(self):
        self.assertEqual(set(q.VARIANTS), set(q.NATIVE_VARIANTS) | {q.EXTENSION_PROFILE} | set(q.PAIR_PROFILES))
        d = bound(q.EXTENSION_PROFILE)
        q.validate(d)
        self.assertEqual(d['_model'], bound()['_model'])
        self.assertEqual(d['_runtime'], bound()['_runtime'])
        self.assertEqual(d['launch']['gpus'], ['0', '1'])
        self.assertEqual(d['launch']['tp_size'], 2)
        self.assertEqual(d['launch']['context_size'], 1000000)
        self.assertEqual(d['launch']['max_total_tokens'], 1000000)
        self.assertEqual(d['launch']['dtype'], 'bfloat16')
        self.assertEqual(d['launch']['kv_cache_dtype'], 'bfloat16')
        self.assertEqual(d['launch']['json_model_override_args'], launcher.EXTENSION_OVERRIDE_JSON)
        self.assertEqual(q.launch_environment(d),
                         bound()['_runtime']['environment'] | launcher.EXTENSION_ENVIRONMENT)
        for name, digest in {
            'qwen38-27b-128k': 'cee5253c28bd8ff36f33630f27642cc9cdd3857eaa108bd177488efd6a0d133f',
            'qwen38-27b-256k': '462ed5792940890eaa410c3c6dd4996c6723157eee5fb7021ee210ed2f78523a',
        }.items():
            self.assertEqual(hashlib.sha256((ROOT / 'configs/deployments' / (name + '.json')).read_bytes()).hexdigest(), digest)
            self.assertEqual(q.launch_environment(bound(name)), d['_runtime']['environment'])

    def test_partial_tuple_and_external_overrides_refuse(self):
        for field, value in [('gpus', ['0']), ('gpus', ['1', '0']), ('tp_size', 1),
                             ('kv_cache_dtype', 'fp8_e4m3'), ('dtype', 'float16'),
                             ('context_size', 1048576), ('max_total_tokens', 262144),
                             ('json_model_override_args', '{}')]:
            d = bound(q.EXTENSION_PROFILE)
            d['launch'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(LifecycleError):
                q.command(d)
        for identifier in q.VARIANTS:
            for env in ({'SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN': '0'},
                        {'PYTHONPATH': '/arbitrary'}, {}):
                d = bound(identifier)
                d['launch_environment'] = env
                with self.subTest(identifier=identifier, env=env), self.assertRaises(LifecycleError):
                    q.launch_environment(d)

    def test_native_receipt_alone_cannot_accept_extension(self):
        d = bound(q.EXTENSION_PROFILE)
        _, instance = auth_receipt(d)
        with self.assertRaisesRegex(LifecycleError, 'qwen38_extension_auth_evidence_required'):
            q.evidence(d, instance)

    def test_extension_requires_both_receipts_and_exact_source_bound_identity(self):
        d = bound(q.EXTENSION_PROFILE)
        native, extension, instance = extension_receipt(d)
        self.assertTrue(q.evidence(d, instance)['auth_gate_passed'])
        binding = d['_storage_binding']
        native_path = binding.path('data', q.PROOF_SUFFIX)
        extension_path = binding.path('data', q.EXTENSION_PROOF_SUFFIX)
        changes = [('kind', native['kind']), ('contexts', [262144]),
                   ('launcher_sha256', '0' * 64), ('native_results', native['native_results']),
                   ('container_lifetimes', native['container_lifetimes']),
                   ('model_execution', 'PASS')]
        for field, value in changes:
            changed = copy.deepcopy(extension); changed[field] = value
            binding.documents[extension_path] = changed
            with self.subTest(field=field), self.assertRaises(LifecycleError):
                q.evidence(d, instance)
        for block in ('extension_identity', 'model_config_resolution'):
            for key in extension[block]:
                changed = copy.deepcopy(extension); changed[block][key] = 'drift'
                binding.documents[extension_path] = changed
                with self.subTest(block=block, key=key), self.assertRaises(LifecycleError):
                    q.evidence(d, instance)
                changed = copy.deepcopy(extension)
                changed['native_results'][0][block][key] = 'drift'
                binding.documents[extension_path] = changed
                with self.subTest(result_block=block, key=key), self.assertRaises(LifecycleError):
                    q.evidence(d, instance)
        binding.documents[extension_path] = extension
        binding.documents[native_path] = extension
        with self.assertRaises(LifecycleError):
            q.evidence(d, instance)


class ExtensionManager(unittest.TestCase):
    setUp = manager_tests.ManagerDispatch.setUp

    def use_extension(self):
        d = self.manager.deployment(q.EXTENSION_PROFILE)
        _, _, instance = extension_receipt(d)
        self.manager.instance.update(instance)
        return d

    def test_create_reuse_exact_gpu_environment_core_and_command(self):
        d = self.use_extension()
        argv = self.manager.create_args(d)
        self.assertEqual(argv[argv.index('--gpus') + 1], '"device=0,1"')
        self.assertEqual(argv.count('core=1:1'), 1)
        self.assertLess(argv.index('core=1:1'), argv.index(q.IMAGE_REFERENCE))
        self.assertEqual(argv[argv.index('--publish') + 1], '127.0.0.1:30004:30004/tcp')
        self.assertEqual(argv[argv.index(q.IMAGE_REFERENCE) + 1:], q.command(d))
        env = [argv[i + 1] for i, item in enumerate(argv) if item == '--env']
        self.assertEqual(env, [k + '=' + v for k, v in q.launch_environment(d).items()])
        c = container(d); c['HostConfig']['DeviceRequests'][0]['DeviceIDs'] = ['0', '1']
        self.manager.validate_reused_contract(c, d)
        changes = [lambda v: v['HostConfig']['DeviceRequests'][0].update(DeviceIDs=['0']),
                   lambda v: v['HostConfig']['DeviceRequests'][0].update(DeviceIDs=['1', '0']),
                   lambda v: v['HostConfig'].update(Ulimits=[]),
                   lambda v: v['Config']['Env'].remove('SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=1'),
                   lambda v: v['Config']['Env'].append('PYTHONPATH=/arbitrary'),
                   lambda v: v['Config'].update(Cmd=q.command(bound()))]
        for change in changes:
            bad = copy.deepcopy(c); change(bad)
            with self.assertRaises(LifecycleError):
                self.manager.validate_reused_contract(bad, d)

    def test_missing_extension_proof_refuses_before_image_inspection(self):
        d = self.manager.deployment(q.EXTENSION_PROFILE)
        with self.assertRaisesRegex(LifecycleError, 'qwen38_extension_auth_evidence_required'):
            self.manager.create_args(d)
        self.assertEqual(self.docker.calls, [])


if __name__ == '__main__':
    unittest.main()
