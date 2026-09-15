"""D2 source contracts and hostile profile fixtures; no host/container/model I/O."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lifecycle.manager import Manager
from lifecycle.runtime_io import LifecycleError
from lifecycle.storage_binding import BindingError
import test_manager as retained
from fixture_storage import HistoricalBinding

MODEL = 'glm-5.3-ud-q4-k-xl'
RUNTIME = 'llama-cpp-v0.4.1-d1'
PROOF = MODEL + '-8k'
IMAGE = 'sha256:' + 'b' * 64
D1_IMAGE = 'sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62'
MODEL_REVISION = '346b3591c7f28d1a23716f97a065ecf12ec14771'
RUNTIME_REVISION = 'b29c606e28a01b1bc8c1351026a0fa6e616bf6c4'
SHARD_SIZES = [9428677, 49433942336, *([48566415136] * 8), 29314424736]


def read(relative):
    return json.loads((ROOT / relative).read_text())


class SourceContractTests(unittest.TestCase):
    def test_exact_artifact_inventory_and_preserved_relative_directory(self):
        model = read(f'configs/models/{MODEL}.json')
        original = read('reports/r2-flagship-artifact.json')
        self.assertEqual(model['artifacts'], original['artifacts'])
        self.assertEqual(model['revision'], MODEL_REVISION)
        self.assertEqual(model['repo_id'], 'unsloth/GLM-5.3-GGUF')
        self.assertEqual(model['quantization'], 'UD-Q4_K_XL')
        self.assertEqual(model['artifact_count'], 11)
        self.assertEqual(model['total_bytes'], 467289116837)
        self.assertEqual([a['size_bytes'] for a in model['artifacts']], SHARD_SIZES)
        self.assertEqual(sum(SHARD_SIZES), model['total_bytes'])
        for index, artifact in enumerate(model['artifacts'], 1):
            self.assertEqual(artifact['path'], f'UD-Q4_K_XL/GLM-5.3-UD-Q4_K_XL-{index:05d}-of-00011.gguf')
            self.assertRegex(artifact['sha256'], r'^[0-9a-f]{64}$')
        self.assertEqual(model['load_entry'], model['artifacts'][0]['path'])
        self.assertEqual(model['model_root'], {'role': 'models', 'suffix': MODEL})

    def test_runtime_pin_and_final_build_scope_remain_explicit(self):
        runtime = read(f'configs/runtimes/{RUNTIME}.json')
        self.assertEqual(runtime['source_release'], 'v0.4.1')
        self.assertEqual(runtime['source_revision'], RUNTIME_REVISION)
        self.assertEqual(runtime['image_tag'], 'local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d1')
        self.assertEqual(runtime['entrypoint'], ['/opt/llama/llama-server'])
        self.assertEqual(runtime['validation']['status'], 'PASS_BUILD_CUDA_CLI_ONLY')
        self.assertEqual(runtime['validation']['image_id'], D1_IMAGE)
        self.assertEqual(runtime['validation']['glm_inference'], 'NOT_TESTED')
        self.assertEqual(runtime['validation']['tool_calls'], 'NOT_TESTED')
        self.assertEqual(runtime['validation']['service_activation'], 'NOT_PERFORMED')
        self.assertEqual(runtime['validation']['supported_flags'], runtime['required_cli_flags'])
        self.assertEqual(len(runtime['required_cli_flags']), 16)
        self.assertIn('--device', runtime['required_cli_flags'])
        self.assertIn('--chat-template-kwargs', runtime['required_cli_flags'])
        self.assertIn('none', runtime['validation']['supported_load_modes'])
        self.assertIn('--api-key-file', runtime['required_cli_flags'])
        self.assertIn('--load-mode', runtime['required_cli_flags'])
        self.assertNotIn('--mmap', runtime['required_cli_flags'])
        self.assertNotIn('--no-mmap', runtime['required_cli_flags'])

    def test_copied_d1_cli_evidence_matches_supplied_proof_hash(self):
        proof = read('reports/d2-contract-evidence/d1-runtime-proof.json')
        cli = read('reports/d2-contract-evidence/d1-cli-verbatim.json')['text'].encode('utf-8')
        normalized = '\n'.join(line.rstrip() for line in cli.decode().splitlines()) + '\n'
        self.assertEqual((ROOT / 'reports/d2-contract-evidence/d1-cli-selected.txt').read_text(), normalized)
        self.assertEqual(hashlib.sha256(cli).hexdigest(), proof['evidence_sha256']['cli-selected.txt'])
        self.assertEqual(proof['image_id'], D1_IMAGE)
        self.assertEqual(proof['source_commit'], RUNTIME_REVISION)
        self.assertEqual(proof['build_status'], 'PASS_BUILD_CUDA_CLI_ONLY')
        self.assertEqual(proof['glm_inference'], 'NOT_TESTED')
        self.assertEqual(proof['tool_calls'], 'NOT_TESTED')
        for flag in ('--api-key-file', '--device', '--load-mode', '--chat-template-kwargs'):
            self.assertIn(flag.encode(), cli)

    def test_host_uuids_only_in_explicit_instance_and_not_generic_template(self):
        host = read('configs/deployments/instances/ai-vm-d0b.json')
        template = read('configs/deployments/instances/instance.template.json')
        expected = {'/data': '8daf56f1-5649-4163-9d87-919c2d271875',
                    '/data/models-large': 'a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a'}
        self.assertEqual({m['target']: m['uuid'] for m in host['required_mounts']}, expected)
        self.assertIsNone(template['storage_identity'])
        self.assertNotIn('required_mounts', template)
        self.assertEqual(template['paths']['state'], {'role': 'data', 'suffix': 'services/llm-manager/active'})
        for path in [ROOT / f'configs/models/{MODEL}.json', ROOT / f'configs/runtimes/{RUNTIME}.json',
                     *list((ROOT / 'configs/deployments').glob('*.json')),
                     *list((ROOT / 'scripts/lifecycle').glob('*.py'))]:
            text = path.read_text()
            for uuid in expected.values():
                self.assertNotIn(uuid, text, str(path))
        self.assertFalse(host['obsolete_boot_owner_disabled'])
        self.assertFalse(host['model_integrity'][MODEL]['verified'])
        self.assertEqual(host['model_integrity'][MODEL]['revision'], MODEL_REVISION)
        self.assertTrue(host['runtime_evidence'][RUNTIME]['flags_verified'])
        self.assertEqual(host['runtime_evidence'][RUNTIME]['image_id'], D1_IMAGE)
        self.assertEqual(host['runtime_evidence'][RUNTIME]['load_mode'], 'none')
        self.assertIsNone(template['runtime_evidence'][RUNTIME]['image_id'])
        self.assertFalse(template['runtime_evidence'][RUNTIME]['flags_verified'])
        self.assertIsNone(template['runtime_evidence'][RUNTIME]['load_mode'])

    def test_context_presets_require_explicit_selection_with_bounded_limits(self):
        for suffix, context in [('8k', 8192), ('32k', 32768)]:
            deployment = read(f'configs/deployments/{MODEL}-{suffix}.json')
            with self.subTest(preset=suffix):
                self.assertEqual(deployment['model'], MODEL)
                self.assertEqual(deployment['runtime'], RUNTIME)
                self.assertEqual(deployment['endpoint'], {'host': '127.0.0.1', 'port': 30002,
                                 'api_prefix': '/v1', 'served_model': 'glm-5.3'})
                launch = deployment['launch']
                self.assertEqual(launch['context_size'], context)
                self.assertEqual(launch['parallel'], 1)
                self.assertEqual(launch['gpus'], ['0', '1'])
                self.assertEqual(launch['devices'], ['CUDA0', 'CUDA1'])
                self.assertEqual(launch['chat_template_kwargs'], {'clear_thinking': True})
                self.assertTrue(launch['cpu_moe'] and launch['jinja'] and launch['no_webui'])
                self.assertEqual(launch['timeout_seconds'], 7200)
                self.assertEqual(deployment['docker_restart_policy'], 'no')
                self.assertEqual(deployment['boot_policy'], 'manual')
                self.assertEqual(deployment['paths']['cache'], {'role': 'models',
                    'suffix': 'runtime-cache/' + RUNTIME, 'historical_suffix': 'runtime-cache/llama-cpp'})
                self.assertEqual(deployment['paths']['logs']['suffix'], 'logs/llmctl/' + deployment['id'])
                self.assertEqual(deployment['paths']['service']['suffix'], 'services/llm-manager/' + deployment['id'])
                self.assertEqual(deployment['auth']['mode'], '0600')
                self.assertTrue(next(m for m in deployment['mounts'] if m['source'] ==
                                     deployment['auth']['key_file'])['read_only'])


class ImageMetadataOnlyDocker:
    def capture(self, *args, **kwargs):
        if args[:2] == ('image', 'inspect'):
            return json.dumps([{'Id': IMAGE, 'Config': {'Entrypoint': ['/opt/llama/llama-server']}}])
        raise AssertionError('Unexpected Docker I/O in source profile fixture')


class BoundProfileManager(retained.FixtureManager):
    """Inject only storage/lease fixture I/O; preserve production profile checks."""
    host_guards = Manager.host_guards
    check_mounts = Manager.check_mounts
    check_artifacts = Manager.check_artifacts
    image_evidence = Manager.image_evidence
    prepare_start = Manager.prepare_start


class ProfileValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.configs = self.root / 'configs'
        shutil.copytree(ROOT / 'configs', self.configs)
        self.instance = read('configs/deployments/instances/ai-vm-d0b.json')
        self.instance['paths'] = {'state': str(self.root / 'state'), 'lock': str(self.root / 'run/llmctl/lifecycle.lock'),
                                  'recovery': str(self.root / 'run/llmctl/recovery.json')}
        runtime = read(f'configs/runtimes/{RUNTIME}.json')
        self.instance['runtime_evidence'][RUNTIME] = {
            'image_id': IMAGE, 'flags_verified': True, 'supported_flags': runtime['required_cli_flags'],
            'load_mode': 'none', 'evidence': 'Synthetic worker fixture using D1 supported no-special-mode selection'}
        self.manager = BoundProfileManager(self.configs, self.instance, docker=ImageMetadataOnlyDocker(), test_paths=True)
        self.original = self.manager.deployment(PROOF)

    def assertRejected(self, deployment):
        with self.assertRaises(LifecycleError):
            self.manager.validate_deployment(deployment)
            self.manager.create_args(deployment)

    def test_fresh_registered_profiles_use_runtime_and_deployment_ids(self):
        for data, models in [('/srv/ai', '/srv/ai/models'), ('/srv/ai', '/srv/ai'),
                             ('/srv/ai', '/srv/ai/models-large'), ('/srv/ai', '/mnt/weights')]:
            with self.subTest(data=data, models=models):
                binding = HistoricalBinding()
                binding.registry['data'].update(path=data, mount=data)
                binding.registry['models'].update(path=models, mount=models)
                binding.registry['roots'] = {name: data + value[len('/data'):] for name, value in binding.registry['roots'].items()}
                binding.registry['roots']['models'] = models
                binding.identity = copy.deepcopy(binding.registry)
                instance = copy.deepcopy(self.instance)
                instance['paths']['state'] = {'role': 'data', 'suffix': 'services/llm-manager/active'}
                instance['storage_identity'] = binding.identity
                instance.pop('historical_import', None)
                manager = Manager(self.configs, instance, docker=ImageMetadataOnlyDocker(),
                                  binding=binding, test_paths=True)
                d = manager.deployment(PROOF)
                self.assertEqual(d['paths'], {
                    'model': models + '/' + MODEL,
                    'cache': models + '/runtime-cache/' + RUNTIME,
                    'logs': data + '/logs/llmctl/' + PROOF,
                    'service': data + '/services/llm-manager/' + PROOF,
                })
                self.assertEqual(d['auth']['key_file'], data + '/services/secrets/llm-api-key')
                by_target = {m['target']: m['source'] for m in d['mounts']}
                self.assertEqual(by_target['/models'], d['paths']['model'])
                self.assertEqual(by_target['/cache'], d['paths']['cache'])
                self.assertEqual(by_target['/logs'], d['paths']['logs'])
                self.assertEqual(by_target['/service'], d['paths']['service'])
                self.assertIn('/models/UD-Q4_K_XL/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf', manager.create_args(d))

    def test_render_is_local_pinned_key_file_only_and_has_no_download_or_restart_owner(self):
        args = self.manager.create_args(self.original)
        self.assertEqual(args[args.index('--publish') + 1], '127.0.0.1:30002:30002/tcp')
        self.assertEqual(args[args.index('--restart') + 1], 'no')
        self.assertEqual(args[args.index('--network') + 1], 'bridge')
        self.assertIn(IMAGE, args)
        self.assertEqual(args[args.index('--api-key-file') + 1], '/run/secrets/llm-api-key')
        self.assertNotIn('--api-key', args)
        self.assertNotIn('--hf-repo', args)
        self.assertNotIn('--model-url', args)
        self.assertNotIn('--mmap', args)
        self.assertNotIn('--no-mmap', args)
        self.assertEqual(args[args.index('--ctx-size') + 1], '8192')
        self.assertEqual(args[args.index('--load-mode') + 1], 'none')
        self.assertEqual(args[args.index('--device') + 1], 'CUDA0,CUDA1')
        self.assertEqual(json.loads(args[args.index('--chat-template-kwargs') + 1]), {'clear_thinking': True})
        self.assertIn('/models/UD-Q4_K_XL/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf', args)

    def test_missing_d1_evidence_refuses_render(self):
        cases = [{'image_id': None}, {'flags_verified': False}, {'supported_flags': []},
                 {'load_mode': None}, {'evidence': None}]
        for change in cases:
            with self.subTest(change=list(change)):
                altered = copy.deepcopy(self.instance)
                altered['runtime_evidence'][RUNTIME].update(change)
                manager = BoundProfileManager(self.configs, altered, docker=ImageMetadataOnlyDocker(), test_paths=True)
                with self.assertRaises(LifecycleError):
                    manager.create_args(self.original)

    def test_wildcard_lan_host_network_and_extra_supervisor_are_rejected(self):
        for host in ['0.0.0.0', '::', '::1', '10.0.0.2', 'localhost']:
            bad = copy.deepcopy(self.original)
            bad['endpoint']['host'] = host
            self.assertRejected(bad)
        for mode in ['host', 'container:other', 'macvlan']:
            bad = copy.deepcopy(self.original)
            bad['_runtime']['network_mode'] = mode
            self.assertRejected(bad)
        bad = copy.deepcopy(self.original)
        bad['docker_restart_policy'] = 'unless-stopped'
        self.assertRejected(bad)

    def test_mount_escape_writable_model_key_duplicate_and_missing_mount_are_rejected(self):
        cases = []
        for source in ['/etc', '/data/../etc', '/data/models-large']:
            bad = copy.deepcopy(self.original)
            bad['mounts'][0]['source'] = source
            cases.append(bad)
        for index in [0, 4]:
            bad = copy.deepcopy(self.original)
            bad['mounts'][index]['read_only'] = False
            cases.append(bad)
        bad = copy.deepcopy(self.original)
        bad['mounts'][1]['target'] = '/models'
        cases.append(bad)
        bad = copy.deepcopy(self.original)
        bad['mounts'].pop()
        cases.append(bad)
        for index, bad in enumerate(cases):
            with self.subTest(case=index):
                self.assertRejected(bad)

    def test_secret_directory_cannot_be_exported_as_cache_logs_or_service(self):
        for role, target in [('cache', '/cache'), ('logs', '/logs'), ('service', '/service')]:
            bad = copy.deepcopy(self.original)
            bad['paths'][role] = '/data/services/secrets'
            mount = next(m for m in bad['mounts'] if m['target'] == target)
            mount.update(source='/data/services/secrets', required_role='data')
            with self.subTest(role=role):
                self.assertRejected(bad)

    def test_unreviewed_environment_keys_and_values_cannot_enter_argv(self):
        cases = [('API_KEY', 'synthetic-fixture-not-a-real-key'),
                 ('LLAMA_ARG_HOST', '0.0.0.0 --api-key synthetic-fixture'),
                 ('LD_LIBRARY_PATH', '/data/services/secrets'),
                 ('XDG_CACHE_HOME', '/data/services/secrets')]
        for key, value in cases:
            bad = copy.deepcopy(self.original)
            bad['_runtime']['environment'][key] = value
            with self.subTest(key=key):
                self.assertRejected(bad)

    def test_launch_limits_and_key_destination_are_fail_closed(self):
        for key, value in [('parallel', 2), ('context_size', 0), ('timeout_seconds', 0),
                           ('timeout_seconds', 999999), ('no_webui', False),
                           ('cpu_moe', False), ('gpus', ['0', '0']), ('devices', ['CUDA0', 'CUDA0']),
                           ('chat_template_kwargs', {'clear_thinking': False})]:
            bad = copy.deepcopy(self.original)
            bad['launch'][key] = value
            with self.subTest(key=key, value=value):
                self.assertRejected(bad)
        bad = copy.deepcopy(self.original)
        bad['auth']['container_key_file'] = '/opt/llama/llama-server'
        bad['mounts'][-1]['target'] = '/opt/llama/llama-server'
        self.assertRejected(bad)


class GlmCompletionTests(unittest.TestCase):
    """Receipt metadata validation only; protected storage reads are injected."""
    def setUp(self):
        binding = HistoricalBinding()
        binding.registry['data'].update(path='/srv/ai', mount='/srv/ai')
        binding.registry['models'].update(path='/mnt/weights', mount='/mnt/weights')
        binding.identity = copy.deepcopy(binding.registry)
        instance = read('configs/deployments/instances/instance.template.json')
        instance.update(id='fresh-glm-fixture', storage_identity=binding.identity)
        self.path = '/srv/ai/services/llm-manager/acquisition/' + MODEL + '.complete.json'
        instance['model_integrity'][MODEL].update(
            verified=True, evidence=['synthetic-completed-acquisition'], completion_manifest=self.path)
        self.manager = Manager(ROOT / 'configs', instance, binding=binding, test_paths=True)
        self.d = self.manager.deployment(PROOF)
        self.model = self.d['_model']
        self.receipt = {
            'schema_version': 1, 'complete': True, 'repo_id': self.model['repo_id'],
            'revision': self.model['revision'], 'model_root': '/mnt/weights/' + MODEL,
            'artifact_count': self.model['artifact_count'], 'total_bytes': self.model['total_bytes'],
            'artifacts': [{**a, 'verified': True} for a in self.model['artifacts']],
        }
        self.reader = Mock(side_effect=lambda *a, **kw: copy.deepcopy(self.receipt))
        binding.read_json = self.reader

    def test_fresh_receipt_reads_only_protected_data_acquisition_and_exact_model_root(self):
        before = copy.deepcopy(self.manager.instance)
        self.manager.check_completion(self.d)
        self.reader.assert_called_once_with('data', self.path)
        self.assertEqual(self.manager.instance, before)
        self.assertEqual(self.receipt['model_root'], self.manager.binding.path('models', MODEL))
        self.receipt['artifacts'].reverse()
        self.manager.check_completion(self.d)

    def test_missing_or_unsafe_completion_never_falls_back_to_attestation(self):
        item = self.manager.instance['model_integrity'][MODEL]
        for path in [None, '/data/services/llm-manager/acquisition/' + MODEL + '.complete.json',
                     '/srv/ai/services/llm-manager/acquisition/../receipt.json',
                     {'role': 'data', 'suffix': 'services/llm-manager/acquisition/' + MODEL + '.complete.json'}]:
            with self.subTest(path=path):
                item['completion_manifest'] = path
                with self.assertRaisesRegex(LifecycleError, 'acquisition_completion_required'):
                    self.manager.check_completion(self.d)
        self.reader.assert_not_called()
        item['completion_manifest'] = self.path
        self.reader.side_effect = BindingError('missing_or_unprotected_receipt')
        with self.assertRaises(BindingError):
            self.manager.check_completion(self.d)

    def test_receipt_identity_fields_and_actual_root_must_match_exactly(self):
        mutations = [('schema_version', True), ('complete', False), ('repo_id', 'other/model'),
                     ('revision', '0' * 40), ('model_root', '/data/models-large/' + MODEL),
                     ('model_root', '/mnt/weights/other-model'), ('model_root', '/models'),
                     ('artifact_count', 10), ('total_bytes', self.receipt['total_bytes'] + 1)]
        for field, value in mutations:
            saved = self.receipt[field]
            with self.subTest(field=field, value=value):
                self.receipt[field] = value
                with self.assertRaisesRegex(LifecycleError, 'acquisition_completion_identity_mismatch'):
                    self.manager.check_completion(self.d)
            self.receipt[field] = saved

    def test_partial_unverified_duplicate_or_wrong_artifact_metadata_refuses(self):
        original = copy.deepcopy(self.receipt['artifacts'])
        for mutation in [lambda files: files.pop(),
                         lambda files: files[0].update(verified=False),
                         lambda files: files[0].update(sha256='0' * 64),
                         lambda files: files[0].update(size_bytes=files[0]['size_bytes'] + 1),
                         lambda files: files[0].update(path='unexpected.gguf'),
                         lambda files: files.__setitem__(1, copy.deepcopy(files[0]))]:
            self.receipt['artifacts'] = copy.deepcopy(original)
            mutation(self.receipt['artifacts'])
            with self.assertRaises(LifecycleError):
                self.manager.check_completion(self.d)

    def test_explicit_historical_d1_attestation_without_receipt_is_preserved(self):
        binding = HistoricalBinding()
        instance = copy.deepcopy(self.manager.instance)
        instance.update(storage_identity=binding.identity, historical_import=True)
        manager = Manager(ROOT / 'configs', instance, binding=binding, test_paths=True)
        d = manager.deployment(PROOF)
        binding.read_json = self.reader
        self.assertEqual(d['paths']['model'], '/data/models-large/' + MODEL)
        item = manager.instance['model_integrity'][MODEL]
        item.pop('completion_manifest')
        before = copy.deepcopy(manager.instance)
        manager.check_completion(d)
        self.reader.assert_not_called()
        self.assertEqual(manager.instance, before)
        item['verified'] = False
        with self.assertRaisesRegex(LifecycleError, 'd1_integrity_evidence_required'):
            manager.check_completion(d)
        item['verified'] = True
        item['completion_manifest'] = '/data/services/llm-manager/acquisition/' + MODEL + '.complete.json'
        self.receipt['model_root'] = '/mnt/weights/another-model'
        with self.assertRaisesRegex(LifecycleError, 'acquisition_completion_identity_mismatch'):
            manager.check_completion(d)


if __name__ == '__main__':
    unittest.main()
