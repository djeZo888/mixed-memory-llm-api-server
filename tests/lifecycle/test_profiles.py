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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from lifecycle.manager import Manager
from lifecycle.runtime_io import LifecycleError

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
        self.assertEqual(model['model_root'], '/data/models-large/glm-5.3-ud-q4-k-xl')

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
        self.assertTrue(all(m['uuid'] is None for m in template['required_mounts']))
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
                self.assertTrue(deployment['paths']['cache'].startswith('/data/models-large/'))
                self.assertEqual(deployment['auth']['mode'], '0600')
                self.assertTrue(next(m for m in deployment['mounts'] if m['source'] ==
                                     deployment['auth']['key_file'])['read_only'])


class ImageMetadataOnlyDocker:
    def capture(self, *args, **kwargs):
        if args[:2] == ('image', 'inspect'):
            return json.dumps([{'Id': IMAGE, 'Config': {'Entrypoint': ['/opt/llama/llama-server']}}])
        raise AssertionError('Unexpected Docker I/O in source profile fixture')


class ProfileValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.configs = self.root / 'configs'
        shutil.copytree(ROOT / 'configs', self.configs)
        self.instance = read('configs/deployments/instances/ai-vm-d0b.json')
        self.instance['paths'] = {'state': str(self.root / 'state'), 'lock': str(self.root / 'lock'),
                                  'recovery': str(self.root / 'recovery.json')}
        runtime = read(f'configs/runtimes/{RUNTIME}.json')
        self.instance['runtime_evidence'][RUNTIME] = {
            'image_id': IMAGE, 'flags_verified': True, 'supported_flags': runtime['required_cli_flags'],
            'load_mode': 'none', 'evidence': 'Synthetic worker fixture using D1 supported no-special-mode selection'}
        self.manager = Manager(self.configs, self.instance, docker=ImageMetadataOnlyDocker(), test_paths=True)
        self.original = self.manager.deployment(PROOF)

    def assertRejected(self, deployment):
        with self.assertRaises(LifecycleError):
            self.manager.validate_deployment(deployment)
            self.manager.create_args(deployment)

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
                manager = Manager(self.configs, altered, docker=ImageMetadataOnlyDocker(), test_paths=True)
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
            mount.update(source='/data/services/secrets', required_mount='/data')
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


if __name__ == '__main__':
    unittest.main()
