"""Actual Manager/registered-file discovery with synthetic worker storage.

Uses the actual Storage ownership/identity and protected receipt reader through
LocalStorageFixture. Mount discovery and uid are fixture seams. No model bytes,
Docker process, real credentials, service, installation, or live inference.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests/lifecycle'))

from control.catalog import Catalog, MAX_ENTRIES
from control.discovery import discover_catalog, discover_records
from control.protocol import ControlError, Deadline
from test_real_storage_io import LocalStorageFixture


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = LocalStorageFixture()
        self.addCleanup(self.fixture.close)
        self.manager = self.fixture.manager
        self.config = self.fixture.base / 'configs'
        for name in ('deployments', 'models', 'runtimes'):
            (self.config / name).mkdir(parents=True)
        self.manager.config_root = self.config
        runtime = json.loads((ROOT / 'configs/runtimes/llama-cpp-v0.4.1-d1.json').read_text())
        self.runtime = runtime
        self.write(self.config / 'runtimes' / (runtime['id'] + '.json'), runtime)
        self.manager.instance['model_integrity'] = {}
        self.manager.instance['runtime_evidence'] = {runtime['id']: {
            'image_id': 'sha256:' + 'b' * 64, 'flags_verified': True,
            'supported_flags': runtime['required_cli_flags'], 'load_mode': 'none',
            'evidence': 'synthetic-runtime-proof',
        }}
        self.receipts = {}
        self.add_model('first-8k', 'first-model', 'Fixture/First')

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        path.chmod(0o600)
        return path

    def add_model(self, identifier, model_id, repo_id):
        source = ROOT / 'configs/deployments/glm-5.3-ud-q4-k-xl-8k.json'
        text = source.read_text().replace('glm-5.3-ud-q4-k-xl-8k', identifier)
        text = text.replace('glm-5.3-ud-q4-k-xl', model_id)
        deployment = json.loads(text)
        deployment['endpoint']['served_model'] = model_id
        deployment['container_name'] = 'llmctl-' + identifier
        self.write(self.config / 'deployments' / (identifier + '.json'), deployment)
        # Expected metadata only. No corresponding model payload exists.
        artifacts = [{'path': 'synthetic.gguf', 'size_bytes': 1, 'sha256': 'a' * 64}]
        model = {'schema_version': 1, 'id': model_id, 'repo_id': repo_id,
                 'revision': 'c' * 40, 'quantization': 'synthetic',
                 'model_root': {'role': 'models', 'suffix': model_id},
                 'load_entry': artifacts[0]['path'], 'artifact_count': 1,
                 'total_bytes': 1, 'artifacts': artifacts,
                 'capability_status': 'Live behavior NOT_TESTED',
                 'private_fixture': '/secret/path must never be echoed'}
        self.write(self.config / 'models' / (model_id + '.json'), model)
        receipt = {
            'schema_version': 1, 'complete': True, 'repo_id': repo_id,
            'revision': model['revision'],
            'model_root': self.fixture.binding.path('models', model_id),
            'artifact_count': 1, 'total_bytes': 1,
            'artifacts': [dict(artifacts[0], verified=True)],
        }
        location = self.fixture.binding.path('data', f'services/llm-manager/acquisition/{model_id}.complete.json')
        self.fixture.jsonfile(location, receipt)
        self.receipts[model_id] = (Path(location), receipt)
        self.manager.instance['model_integrity'][model_id] = {
            'verified': True, 'revision': model['revision'], 'evidence': 'synthetic-completion-proof',
            'completion_manifest': location,
        }
        return deployment, model

    def snapshot(self, **changes):
        result = {'storage_available': True, 'observation_available': True,
                  'observed_at': 1789434000.0, 'selected': None, 'desired': 'stopped',
                  'observed': 'stopped', 'container_running': False, 'active_identity': None}
        result.update(changes)
        return result

    def public(self):
        return discover_catalog(self.manager).public(self.snapshot())

    def test_actual_manager_discovers_third_future_model_and_variant_generically(self):
        self.add_model('second-8k', 'second-model', 'Fixture/Second')
        self.add_model('third-future-8k', 'future-model', 'Future/Third')
        self.add_model('third-future-32k', 'future-model', 'Future/Third')
        entries = self.public()
        self.assertEqual([e['deployment_id'] for e in entries],
                         ['first-8k', 'second-8k', 'third-future-32k', 'third-future-8k'])
        self.assertEqual(entries[-1]['model_id'], 'Future/Third')
        self.assertTrue(all(e['state'] == 'available' for e in entries))
        self.assertTrue(all(e['installed_bytes'] == 1 for e in entries))
        self.assertTrue(all(e['start_revalidation_required'] for e in entries))
        self.assertTrue(all(e['context']['configured_tokens'] == e['context_limit'] for e in entries))
        self.assertTrue(all(e['context']['configured_provenance'] == 'declared' for e in entries))
        self.assertTrue(all(e['context']['verified_occupied_tokens'] is None for e in entries))
        self.assertTrue(all(e['context']['verified_occupied_provenance'] == 'unknown' for e in entries))
        self.assertFalse(Path(self.fixture.binding.path('models', 'first-model')).exists())

    def test_reads_no_model_key_state_docker_or_preflight(self):
        with patch.object(self.manager, 'check_artifacts', side_effect=AssertionError('artifact read')), \
                patch.object(self.manager, 'prepare_start', side_effect=AssertionError('preflight')), \
                patch.object(self.manager, 'read_state', side_effect=AssertionError('state read')), \
                patch.object(self.manager, 'status', side_effect=AssertionError('state probe')), \
                patch('lifecycle.manager.validate_key_metadata', side_effect=AssertionError('key read')):
            entries = self.public()
        self.assertEqual(len(entries), 1)
        self.assertEqual(self.fixture.docker.calls, [])

    def test_missing_and_false_installed_evidence_remain_known_unavailable(self):
        self.add_model('second-8k', 'second-model', 'Fixture/Second')
        del self.manager.instance['model_integrity']['first-model']['completion_manifest']
        self.manager.instance['model_integrity']['second-model']['verified'] = False
        catalog = discover_catalog(self.manager)
        self.assertEqual(catalog.public(self.snapshot()), [])
        for ident in ('first-8k', 'second-8k'):
            with self.assertRaisesRegex(ValueError, '^target_unavailable$'):
                catalog.target(ident)
        with self.assertRaisesRegex(ValueError, '^unknown_deployment$'):
            catalog.target('never-registered')

    def test_legacy_and_research_profile_presence_do_not_install(self):
        self.write(self.config / 'deployments/qwen3-0.6b-smoke.json', {'legacy': True})
        source = ROOT / 'configs'
        for kind, name in (('deployments', 'qwen38-27b-128k'), ('models', 'qwen38-27b-fp8'),
                           ('runtimes', 'sglang-qwen38-0.5.19')):
            shutil.copyfile(source / kind / (name + '.json'), self.config / kind / (name + '.json'))
        entries = self.public()
        self.assertEqual([e['deployment_id'] for e in entries], ['first-8k'])

    def test_receipt_identity_and_artifact_tampering_fail_closed(self):
        path, original = self.receipts['first-model']
        changes = [lambda d: d.update(revision='d' * 40), lambda d: d.update(complete=False),
                   lambda d: d.update(model_root='/elsewhere'), lambda d: d.update(total_bytes=2),
                   lambda d: d.update(artifact_count=True),
                   lambda d: d['artifacts'][0].update(sha256='e' * 64),
                   lambda d: d['artifacts'][0].update(verified=False),
                   lambda d: d['artifacts'].append(copy.deepcopy(d['artifacts'][0]))]
        for mutate in changes:
            candidate = copy.deepcopy(original)
            mutate(candidate)
            self.write(path, candidate)
            self.assertEqual(self.public(), [])

    def test_manifest_hash_is_bound_to_model_instance_and_receipt(self):
        model_path = self.config / 'models/first-model.json'
        model = json.loads(model_path.read_text())
        model['manifest_sha256'] = 'f' * 64
        self.write(model_path, model)
        path, receipt = self.receipts['first-model']
        self.assertEqual(self.public(), [])
        self.manager.instance['model_integrity']['first-model']['manifest_sha256'] = 'f' * 64
        self.assertEqual(self.public(), [])
        self.write(path, dict(receipt, manifest_sha256='f' * 64))
        self.assertEqual(len(self.public()), 1)
        self.manager.instance['model_integrity']['first-model']['manifest_sha256'] = 'e' * 64
        self.assertEqual(self.public(), [])

    def test_actual_protected_reader_rejects_receipt_mode_and_symlink(self):
        path, receipt = self.receipts['first-model']
        path.chmod(0o644)
        self.assertEqual(self.public(), [])
        path.unlink()
        other = self.write(path.with_name('other.json'), receipt)
        path.symlink_to(other)
        self.assertEqual(self.public(), [])

    def test_lost_storage_cannot_advertise_installed_or_ready(self):
        self.fixture.lost = True
        self.assertEqual(self.public(), [])

    def test_missing_runtime_attestation_leaves_installed_unavailable(self):
        self.manager.instance['runtime_evidence'] = {}
        entry = self.public()[0]
        self.assertEqual(entry['state'], 'unavailable')
        self.assertFalse(entry['endpoint']['ready'])
        with self.assertRaisesRegex(ValueError, '^target_unavailable$'):
            discover_catalog(self.manager).target('first-8k')

    def test_reserved_control_port_keeps_installed_target_unavailable(self):
        path = self.config / 'deployments/first-8k.json'
        deployment = json.loads(path.read_text())
        deployment['endpoint']['port'] = 30000
        self.write(path, deployment)
        catalog = discover_catalog(self.manager)
        entry = catalog.public(self.snapshot())[0]
        self.assertEqual(entry['state'], 'unavailable')
        self.assertEqual(entry['endpoint']['base_url'], 'http://127.0.0.1:30000/v1')
        self.assertFalse(entry['endpoint']['ready'])
        with self.assertRaisesRegex(ValueError, '^target_unavailable$'):
            catalog.target('first-8k')

    def test_metadata_and_capabilities_are_allowlisted_and_saved_ready_is_not_proof(self):
        catalog = discover_catalog(self.manager)
        entry = catalog.public(self.snapshot(selected='first-8k', desired='running',
                                            observed='ready', container_running=True))[0]
        self.assertEqual(entry['state'], 'unknown')
        self.assertFalse(entry['endpoint']['ready'])
        self.assertEqual(entry['endpoint']['base_url'], 'http://127.0.0.1:30002/v1')
        self.assertTrue(entry['endpoint']['authentication_required'])
        self.assertTrue(entry['endpoint']['server_relative'])
        self.assertTrue(all(v == {'status': 'unknown', 'evidence': []} for v in entry['capabilities'].values()))
        self.assertTrue(all(v == {'bytes': None, 'provenance': 'unknown', 'evidence': []}
                            for v in entry['requirements'].values()))
        rendered = json.dumps(entry)
        for forbidden in ('/secret/', self.fixture.data, 'private_fixture', 'completion_manifest',
                          'image_id', 'evidence_owner', 'key_file', 'environment', 'artifacts'):
            self.assertNotIn(forbidden, rendered)

    def test_deadline_and_catalog_cardinality_are_bounded(self):
        with self.assertRaisesRegex(ControlError, '^deadline_exceeded$'):
            discover_records(self.manager, Deadline.after(-1))
        for i in range(MAX_ENTRIES):
            self.write(self.config / 'deployments' / f'additional-{i}.json', {})
        with self.assertRaisesRegex(ControlError, '^catalog_unavailable$'):
            discover_records(self.manager)

    def test_production_source_trust_rejects_user_owned_checkout(self):
        if os.geteuid() == 0:
            self.skipTest('worker ownership negative requires ordinary uid')
        self.manager.test_paths = False
        with self.assertRaisesRegex(ControlError, '^catalog_unavailable$'):
            discover_records(self.manager)


if __name__ == '__main__':
    unittest.main()
