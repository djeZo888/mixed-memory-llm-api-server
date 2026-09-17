"""Bounded Q38 adapter contracts, synthetic L1/receipt/inspect inputs only.

These tests do not prove mounted Linux storage, real acquired weights, image
execution, readiness or inference. No Docker/VM/key/model operation occurs.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from lifecycle import qwen38 as q
from lifecycle.runtime_io import LifecycleError
from runtime import sglang38_file_auth as launcher


class BindingFixture:
    """An explicitly synthetic dependency, not a minted or verified L1 binding."""
    def __init__(self, data='/srv/ai', models='/mnt/models'):
        self.roots = {'data': data, 'models': models}
        self.checked = []
        self.reads = []
        self.documents = {}
        self.fail = False

    def path(self, role, suffix=''):
        assert role in self.roots
        assert not suffix.startswith('/') and all(p not in ('.', '..') for p in suffix.split('/'))
        return self.roots[role] + ('/' + suffix if suffix else '')

    def verify(self, roles=('data', 'models')):
        if self.fail:
            raise ValueError('synthetic unmounted storage with PRIVATE diagnostic')
        self.checked.append(tuple(roles))

    def validate_path(self, role, path):
        self.verify((role,))
        if not path.startswith(self.roots[role] + '/'):
            raise ValueError('synthetic unregistered path')
        self.checked.append((role, path))
        return Path(path)

    def read_json(self, role, path, *, maximum):
        self.validate_path(role, path)
        self.reads.append(path)
        return copy.deepcopy(self.documents[path])


def bound(identifier='qwen38-27b-128k', binding=None):
    binding = binding or BindingFixture()
    d = q.declared_profile(identifier)
    # Reproduce only the published L1 bind_deployment field transformation.
    resolve = lambda r: binding.path(r['role'], r['suffix'])
    d['paths'] = {k: resolve(v) for k, v in d['paths'].items()}
    d['auth']['key_file'] = resolve(d['auth']['key_file'])
    d['_model']['model_root'] = resolve(d['_model']['model_root'])
    for m in d['mounts']:
        m['source'] = resolve(m['source'])
    d['_storage_binding'] = binding
    return d


def receipt(d):
    manifest = q.expected_manifest()
    result = {'schema_version': 1, 'complete': True, 'repo_id': manifest['repo_id'],
              'revision': q.REVISION, 'model_root': d['_model']['model_root'],
              'manifest_sha256': q.PROFILE_HASHES['reports/q38s-acquisition-manifest.json'],
              'artifact_count': 81, 'total_bytes': 30890049597,
              'artifacts': [{k: a[k] for k in ('path', 'size_bytes', 'sha256')} | {'verified': True}
                            for a in manifest['artifacts']]}
    binding = d['_storage_binding']
    path = binding.path('data', q.COMPLETION_SUFFIX)
    binding.documents[path] = result
    instance = {'model_integrity': {q.MODEL: {'verified': True, 'revision': q.REVISION,
                'manifest_sha256': result['manifest_sha256'], 'completion_manifest': path,
                'evidence': 'SYNTHETIC unit receipt, not actual acquisition'}}}
    return result, instance


def image(d):
    return {'Id': q.IMAGE_ID, 'RepoDigests': [q.IMAGE_REFERENCE], 'Os': 'linux', 'Architecture': 'amd64', 'Config': {
            'Env': [k + '=' + v for k, v in d['_runtime']['image_environment'].items()],
            'Entrypoint': list(q.oci.IMAGE_ENTRYPOINT), 'WorkingDir': q.oci.IMAGE_WORKDIR,
            'Cmd': None, 'Labels': {'org.opencontainers.image.revision': q.SOURCE_REVISION,
            'org.opencontainers.image.source': q.oci.SOURCE_REPOSITORY}}}


def container(d):
    env = q.image_environment(image(d), d)
    return {'Image': q.IMAGE_ID, 'State': {'Running': False}, 'Config': {
        'Image': q.IMAGE_REFERENCE, 'Entrypoint': ['python3'], 'Cmd': q.command(d),
        'Env': [k + '=' + v for k, v in env.items()], 'WorkingDir': '/service',
        'User': '0', 'Healthcheck': {'Test': ['NONE']}}, 'Mounts': [
        {'Type': 'bind', 'Source': m['source'], 'Destination': m['target'],
         'RW': not m['read_only'], 'Propagation': 'rprivate'} for m in d['mounts']],
        'HostConfig': {'ReadonlyRootfs': True, 'ShmSize': 8 * 1024**3,
            'Tmpfs': {'/tmp': 'rw,nosuid,nodev,size=1g'}, 'CapDrop': ['ALL'],
            'SecurityOpt': ['no-new-privileges:true'],
            'Ulimits': [{'Name': 'core', 'Soft': 1, 'Hard': 1}],
            'LogConfig': {'Type': 'json-file', 'Config': {'max-size': '20m', 'max-file': '3'}},
            'DeviceRequests': [{'Driver': 'nvidia', 'Count': 0, 'DeviceIDs': ['0'], 'Capabilities': [['gpu']]}],
            'RestartPolicy': {'Name': 'no', 'MaximumRetryCount': 0}, 'NetworkMode': 'bridge',
            'PortBindings': {'30004/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '30004'}]}},
        'NetworkSettings': {'Ports': {}, 'Networks': {'bridge': {}}}}


def auth_receipt(d):
    """Entirely synthetic in-memory attestation; never write it to an instance."""
    from tests.lifecycle.test_qwen38_image_fixture import native_result, lifetime
    p = json.loads((ROOT / 'tests/lifecycle/sglang38_fixture/provenance.json').read_text())
    identity = {'image_id': q.IMAGE_ID, 'image_reference': q.IMAGE_REFERENCE,
                'source_revision': q.SOURCE_REVISION, 'launcher_sha256': q.launcher_hash()}
    proof = dict(identity, schema_version=2, kind='q38b_actual_image_auth', status='PASS',
        fixture_sha256=p['fixture_sha256'], support_sha256=p['support_sha256'], source_hashes={k: v['sha256'] for k, v in p['sources'].items()},
        checks={k: 'PASS' for k in q.AUTH_CHECKS}, contexts=[131072, 262144],
        image_identity_verification='HOST_DOCKER_INSPECT_AND_PINNED_RUN',
        docker_inspect=q.oci.verify_image(image(d)),
        native_results=[native_result(p, context) for context in (131072, 262144)],
        container_lifetimes=[lifetime(context) for context in (131072, 262144)],
        model_execution='NOT_TESTED', native_lifespan='NOT_TESTED', live_inference_and_agent_acceptance='NOT_TESTED')
    binding = d['_storage_binding']; path = binding.path('data', q.PROOF_SUFFIX)
    binding.documents[path] = proof
    evidence = dict(identity, flags_verified=True, auth_gate_passed=True,
        supported_flags=d['_runtime']['required_cli_flags'], evidence='SYNTHETIC unit receipt only',
        auth_gate_evidence=path, docker_inspect=proof['docker_inspect'])
    return proof, {'runtime_evidence': {q.RUNTIME: evidence}}


class Profiles(unittest.TestCase):
    def test_two_native_variants_have_distinct_deployment_identity(self):
        a, b = [bound(k) for k in q.NATIVE_VARIANTS]
        self.assertNotEqual(a['container_name'], b['container_name'])
        for d in (a, b):
            q.validate(d)
            self.assertEqual(d['launch']['context_size'], q.NATIVE_VARIANTS[d['id']])
            self.assertEqual(d['launch']['max_total_tokens'], q.NATIVE_VARIANTS[d['id']])
            self.assertEqual(d['launch']['gpus'], ['0'])
        self.assertEqual(a['_model'], b['_model'])
        self.assertEqual(a['_runtime'], b['_runtime'])

    def test_manifest_normalization_retains_every_original_record(self):
        old = json.loads((ROOT / 'reports/q38r-source-weight-manifest.json').read_text())
        new = q.expected_manifest()
        self.assertEqual(len(new['artifacts']), 81)
        self.assertEqual(sum(a['size_bytes'] for a in new['artifacts']), 30890049597)
        weights = [a for a in new['artifacts'] if a['path'].endswith('.safetensors')]
        self.assertEqual(len(weights), 66)
        self.assertEqual(sum(a['size_bytes'] for a in weights), 30866866928)
        by_path = {a['path']: a for a in new['artifacts']}
        for row in old['artifacts']:
            a = by_path[row[0]]
            self.assertEqual((a['size_bytes'], a['sha256']), tuple(row[1:3]))
            self.assertIn(row[3], json.dumps(a))
            self.assertIn(row[4], json.dumps(a))
            self.assertIn(row[5], json.dumps(a))
            self.assertRegex(a['sha256'], r'^[a-f0-9]{64}$')
            self.assertEqual(a['revision'], q.REVISION)

    def test_profile_byte_change_fails_closed(self):
        path = 'configs/models/' + q.MODEL + '.json'
        with patch.dict(q.PROFILE_HASHES, {path: 'f' * 64}):
            with self.assertRaises(LifecycleError):
                q.declared_profile(next(iter(q.NATIVE_VARIANTS)))

    def test_model_and_runtime_immutable_pins(self):
        d = bound()
        self.assertEqual(d['_runtime']['image_ref'], q.IMAGE_REFERENCE)
        self.assertEqual(d['_runtime']['image_id'], q.IMAGE_ID)
        self.assertNotEqual(q.MANIFEST_DIGEST, q.IMAGE_ID)
        self.assertEqual(d['_model']['revision'], q.REVISION)
        self.assertEqual(d['_runtime']['source_commit'], q.SOURCE_REVISION)

    def test_unknown_profiles_and_extension_refused(self):
        for ident in ('qwen3.8-27b', '../bad', 'qwen3.8-27b-1m'):
            with self.assertRaises(LifecycleError):
                q.declared_profile(ident)
        for field in ('args', 'plugins', 'command', 'env', 'legacy'):
            d = bound(); d[field] = []
            with self.assertRaises(LifecycleError):
                q.validate(d)

    def test_context_gpu_parser_backend_and_boolean_impostors_refused(self):
        for field, value in [('context_size', 262144), ('max_total_tokens', 1000000),
                             ('gpus', ['1']), ('tp_size', True), ('tool_call_parser', 'json'),
                             ('reasoning_parser', None), ('kv_cache_dtype', 'fp8'),
                             ('max_mamba_cache_size', 128), ('cuda_graph_backend_decode', 'cuda_graph'),
                             ('disable_radix_cache', False), ('default_chat_template_kwargs', {})]:
            with self.subTest(field=field):
                d = bound(); d['launch'][field] = value
                with self.assertRaises(LifecycleError):
                    q.command(d)

    def test_model_hash_revision_and_source_evidence_changes_refused(self):
        for field in ('revision', 'manifest_sha256', 'artifacts'):
            d = bound(); d['_model'][field] = None
            with self.assertRaises(LifecycleError):
                q.validate(d)
        for field in ('image_id', 'image_ref', 'source_commit', 'environment', 'backend'):
            d = bound(); d['_runtime'][field] = None
            with self.assertRaises(LifecycleError):
                q.validate(d)

    def test_launcher_and_runtime_flag_cache_contracts_match(self):
        d = bound()
        self.assertEqual(d['_runtime']['required_cli_flags'],
                         [*launcher.FIXED_FLAGS, '--context-length', '--max-total-tokens', *launcher.BOOLEAN_FLAGS])
        self.assertEqual(d['_runtime']['environment'], launcher.CACHE_ENVIRONMENT)
        for context in q.NATIVE_VARIANTS.values():
            argv = launcher.backend_argv(context)
            options, rendered = launcher.parse_options(['--key-file', '/run/secrets/llm-api-key', '--warmup-timeout', '600', *argv])
            self.assertEqual(rendered, argv)
            self.assertEqual(int(options.context_length), context)

    def test_fast_preset_is_explicit_and_no_thinking_is_default_only(self):
        d = bound()
        self.assertEqual(d['client_preset']['reasoning_effort'], 'none')
        self.assertEqual(d['client_preset']['chat_template_kwargs'], {'enable_thinking': False})
        self.assertGreaterEqual(d['client_preset']['minimum_reserved_tokens'], 8192)
        self.assertIn('NOT_TESTED', d['client_preset']['continuation_contract'])

    def test_handoff_contains_no_runtime_activation_capability(self):
        d = q.declared_profile(next(iter(q.NATIVE_VARIANTS)))
        self.assertEqual(d['_runtime']['validation']['actual_image'], 'NOT_TESTED')
        with self.assertRaises(LifecycleError):
            q.validate(d)
        self.assertFalse(hasattr(q, 'start'))
        self.assertFalse(hasattr(q, 'switch'))


class PathsAndReceipts(unittest.TestCase):
    def test_registered_shared_and_separate_roots(self):
        for binding in (BindingFixture(), BindingFixture('/srv/ai', '/srv/ai/models')):
            d = bound(binding=binding)
            q.validate(d)
            self.assertTrue(binding.checked)
            self.assertNotIn('/data/', json.dumps({k: v for k, v in d.items() if k != '_storage_binding'}))

    def test_unmounted_failure_precedes_any_receipt_read(self):
        d = bound(); b = d['_storage_binding']; b.fail = True
        with self.assertRaises(LifecycleError) as error:
            q.check_completion(d, {})
        self.assertNotIn('PRIVATE', str(error.exception))
        self.assertFalse(b.reads)

    def test_root_escape_and_bound_path_alias_refused(self):
        for value in ('/tmp/model', '/srv/ai/../escape', '/data/models-large/qwen38-27b-fp8'):
            d = bound(); d['paths']['model'] = value
            with self.assertRaises(LifecycleError):
                q.validate(d)

    def test_binding_validation_refusal_is_not_swallowed(self):
        d = bound()
        with patch.object(d['_storage_binding'], 'validate_path', side_effect=ValueError('symlink or mount lost')):
            with self.assertRaises(LifecycleError):
                q.command(d)

    def test_exact_generic_complete_receipt(self):
        d = bound(); _, instance = receipt(d)
        q.check_completion(d, instance)

    def test_unknown_missing_duplicate_or_unverified_artifact_refused(self):
        for mutation in ('missing', 'duplicate', 'unknown_hash', 'unverified', 'boolean_size', 'unknown_metadata'):
            d = bound(); r, instance = receipt(d)
            if mutation == 'missing': r['artifacts'].pop()
            if mutation == 'duplicate': r['artifacts'][-1] = r['artifacts'][0]
            if mutation == 'unknown_hash': r['artifacts'][0]['sha256'] = None
            if mutation == 'unverified': r['artifacts'][0]['verified'] = False
            if mutation == 'boolean_size': r['artifacts'][0]['size_bytes'] = True
            if mutation == 'unknown_metadata': r['artifacts'][0]['download_url'] = 'bad'
            with self.subTest(mutation=mutation), self.assertRaises(LifecycleError):
                q.check_completion(d, instance)

    def test_receipt_revision_root_and_manifest_must_match(self):
        for field in ('model_root', 'revision', 'manifest_sha256', 'repo_id', 'artifact_count', 'complete'):
            d = bound(); r, instance = receipt(d); r[field] = None
            with self.subTest(field=field), self.assertRaises(LifecycleError):
                q.check_completion(d, instance)

    def test_receipt_outside_fixed_registered_location_refused(self):
        d = bound(); _, instance = receipt(d)
        instance['model_integrity'][q.MODEL]['completion_manifest'] = '/tmp/complete.json'
        with self.assertRaises(LifecycleError):
            q.check_completion(d, instance)
        self.assertFalse(d['_storage_binding'].reads)

    def test_research_manifest_is_not_complete_acquisition(self):
        d = bound(); _, instance = receipt(d)
        d['_storage_binding'].documents[d['_storage_binding'].path('data', q.COMPLETION_SUFFIX)] = q.expected_manifest()
        with self.assertRaises(LifecycleError):
            q.check_completion(d, instance)

    def test_source_only_success_never_satisfies_image_gate(self):
        d = bound()
        for e in ({}, {'flags_verified': True, 'auth_gate_passed': True, 'evidence': 'mock passed'}, d['_runtime']['validation']):
            with self.assertRaises(LifecycleError):
                q.evidence(d, {'runtime_evidence': {q.RUNTIME: e}})


class Reuse(unittest.TestCase):
    def check(self, c, d):
        # Isolate inspect-contract checks; installed protected-source I/O is a
        # separate production gate and not claimed by this synthetic fixture.
        with patch.object(q, 'validate_launcher'):
            q.validate_reused(c, d, {'docker_inspect': q.oci.verify_image(image(d))}, image(d))

    def test_exact_inspect_fixture(self):
        d = bound(); self.check(container(d), d)

    def test_same_alias_different_context_cannot_be_reused(self):
        a, b = [bound(k) for k in q.NATIVE_VARIANTS]
        with self.assertRaises(LifecycleError):
            self.check(container(a), b)

    def test_wrong_digest_or_image_id_refused(self):
        d = bound()
        for field in ('Id', 'RepoDigests'):
            value = image(d); value[field] = q.MANIFEST_DIGEST
            with self.assertRaises(LifecycleError):
                q.image_environment(value, d)
        c = container(d); c['Config']['Image'] = d['_runtime']['image_tag']
        with self.assertRaises(LifecycleError): self.check(c, d)

    def test_unknown_or_duplicate_inherited_env_refused(self):
        d = bound()
        for extra in ('HF_TOKEN=synthetic-not-a-real-key', 'HOME=/cache', 'SGLANG_BUILD_URL=unknown'):
            im = image(d); im['Config']['Env'].append(extra)
            with self.assertRaises(LifecycleError): q.image_environment(im, d)
        im = image(d); im['Config']['Env'].append(im['Config']['Env'][0])
        with self.assertRaises(LifecycleError): q.image_environment(im, d)

    def test_inspect_string_or_mapping_cannot_masquerade_as_lists(self):
        d = bound(); im = image(d); im['RepoDigests'] = q.IMAGE_REFERENCE
        with self.assertRaises(LifecycleError): q.image_environment(im, d)
        c = container(d); c['Config']['Env'] = dict.fromkeys(c['Config']['Env'])
        with self.assertRaises(LifecycleError): self.check(c, d)

    def test_lfs_pointer_hash_is_not_used_as_payload_git_hash(self):
        artifacts = q.expected_manifest()['artifacts']
        lfs = [a for a in artifacts if 'lfs_sha256' in a]
        self.assertEqual(len(lfs), 67)
        self.assertTrue(all('lfs_pointer_git_blob_sha1' in a and 'git_blob_sha1' not in a for a in lfs))

    def test_reused_gpu_mount_cache_key_and_command_mutations_refused(self):
        d = bound()
        for field in ('gpu', 'mount', 'env', 'command', 'port', 'privileged', 'readonly'):
            c = container(d)
            if field == 'gpu': c['HostConfig']['DeviceRequests'][0]['DeviceIDs'] = ['1']
            if field == 'mount': c['Mounts'][-1]['RW'] = True
            if field == 'env': c['Config']['Env'].append('SGLANG_API_KEY=synthetic-private')
            if field == 'command': c['Config']['Cmd'].extend(['--api-key', 'synthetic-private'])
            if field == 'port': c['HostConfig']['PortBindings']['30004/tcp'][0]['HostIp'] = '0.0.0.0'
            if field == 'privileged': c['HostConfig']['Privileged'] = True
            if field == 'readonly': c['HostConfig']['ReadonlyRootfs'] = False
            with self.subTest(field=field), self.assertRaises(LifecycleError) as error:
                self.check(c, d)
            self.assertNotIn('synthetic-private', str(error.exception))

    def test_starting_health_is_not_overridden_by_model_listing(self):
        with patch.object(q, 'probe_sglang', return_value='not_ready') as check:
            self.assertEqual(q.probe('http://127.0.0.1:30004/v1', 'qwen3.8-27b', '/synthetic/key'), 'not_ready')
            check.assert_called_once_with('http://127.0.0.1:30004/v1', 'qwen3.8-27b', '/synthetic/key', require_auth=True, timeout=3)


class AuthEvidence(unittest.TestCase):
    def test_cache_lifetime_and_observed_domain_proofs_are_required(self):
        mutations = (
            lambda p: p.pop('container_lifetimes'),
            lambda p: p['container_lifetimes'][0].update(cleanup='FAILED_UNVERIFIED'),
            lambda p: p['container_lifetimes'][1].update(container_id=p['container_lifetimes'][0]['container_id']),
            lambda p: p['container_lifetimes'][0]['runtime_inspect'].update(runtime='runc'),
            lambda p: p['container_lifetimes'][0]['runtime_inspect'].update(visible_devices='all'),
            lambda p: p['native_results'][0]['cache_probe'].update(native_torch_device_count=1),
            lambda p: p['native_results'][0]['cache_probe']['resolved_paths'].update(sglang='/root/.cache/sglang'),
            lambda p: p['native_results'][0]['cache_probe']['driver_library_loading'].update({'libcuda.so.1': 'NOT_TESTED'}),
            lambda p: p['docker_inspect'].update(image_id_domain='oci_platform_manifest'),
            lambda p: p.update(support_sha256={}),
        )
        for mutation in mutations:
            d = bound(); proof, instance = auth_receipt(d); mutation(proof)
            with self.subTest(mutation=mutation), self.assertRaises(LifecycleError):
                q.evidence(d, instance)

    def test_installer_observed_domain_cannot_be_rewritten_from_auth_proof(self):
        d = bound(); _, instance = auth_receipt(d)
        instance['runtime_evidence'][q.RUNTIME]['docker_inspect'] = q.oci.expected_evidence(q.MANIFEST_DIGEST)
        with self.assertRaisesRegex(LifecycleError, 'qwen38_installer_observed_identity_mismatch'):
            q.evidence(d, instance)

    def test_receipt_schema_and_source_fixture_checks_agree(self):
        from tests.lifecycle.test_qwen38_image_fixture import host
        self.assertEqual(q.AUTH_CHECKS, host.CHECKS)
        d = bound(); _, instance = auth_receipt(d)
        self.assertTrue(q.evidence(d, instance)['auth_gate_passed'])

    def test_image_source_launcher_and_fixture_proof_are_all_required(self):
        for field in ('image_id', 'image_reference', 'source_revision', 'launcher_sha256',
                      'source_hashes', 'fixture_sha256', 'checks', 'docker_inspect', 'contexts'):
            d = bound(); proof, instance = auth_receipt(d); proof[field] = None
            with self.subTest(field=field), self.assertRaises(LifecycleError):
                q.evidence(d, instance)

    def test_missing_context_or_native_failure_refuses(self):
        for mutate in (lambda p: p['native_results'].pop(),
                       lambda p: p['native_results'][1].update(configured_context=131072),
                       lambda p: p['native_results'][0].update(ordinary_http_auth='FAIL'),
                       lambda p: p.update(model_execution='PASS')):
            d = bound(); proof, instance = auth_receipt(d); mutate(proof)
            with self.assertRaises(LifecycleError): q.evidence(d, instance)

    def test_auth_receipt_path_is_fixed_under_registered_data(self):
        d = bound(); _, instance = auth_receipt(d)
        instance['runtime_evidence'][q.RUNTIME]['auth_gate_evidence'] = '/tmp/proof.json'
        with self.assertRaises(LifecycleError): q.evidence(d, instance)
        self.assertFalse(d['_storage_binding'].reads)

    def test_changed_installed_launcher_refuses(self):
        d = bound(); e = {'launcher_sha256': q.launcher_hash()}
        with patch.object(q, '_protected_bytes', return_value=b'unreviewed source'):
            with self.assertRaises(LifecycleError): q.validate_launcher(d, e)

    def test_changed_fixture_source_requires_reexecution(self):
        d = bound(); _, instance = auth_receipt(d)
        with patch.object(q, 'launcher_hash', return_value='0' * 64):
            with self.assertRaises(LifecycleError): q.evidence(d, instance)


if __name__ == '__main__':
    unittest.main()
