"""Fresh/import contracts with real lease and injected AnchoredRoot interface.

No model/key/state/container is read or written. The anchor below is an event
recorder, NOT the I1b implementation and NOT proof of mount-loss race safety.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common.lifecycle_lease import LifecycleLease, LeaseError, acquire_lease, transition_in_progress
from lifecycle.instance_binding import render_fresh_instance, import_historical_instance
from lifecycle.runtime_io import LifecycleError
from fixture_storage import HistoricalBinding

INSTANCE_SUFFIX = 'services/llm-manager/deployment-instance.json'
INSTANCE_PATH = '/data/' + INSTANCE_SUFFIX


def profile(name):
    return json.loads((ROOT / 'configs/deployments/instances' / (name + '.json')).read_text())


class InstanceBinding(HistoricalBinding):
    """Only the protected instance path can be read through this fixture."""
    def __init__(self, instance=None, data='/data', models='/data/models-large', system_root=Path('/')):
        super().__init__()
        self.registry['data'].update(path=data, mount=data)
        self.registry['models'].update(path=models, mount=models)
        self.registry['roots'] = {name: data + value[len('/data'):] for name, value in self.registry['roots'].items()}
        self.registry['roots']['models'] = models
        self.identity = copy.deepcopy(self.registry)
        self.instance = copy.deepcopy(instance)
        self.storage = SimpleNamespace(system_root=Path(system_root), owner=os.geteuid())
        self.reads, self.verifications = [], []

    def verify(self, roles=('data', 'models')):
        self.verifications.append(tuple(roles))
        return copy.deepcopy(self.registry)

    def read_json(self, role, path):
        if (role, path) != ('data', INSTANCE_PATH):
            raise AssertionError('instance import touched a non-instance file')
        self.reads.append((role, path))
        return copy.deepcopy(self.instance)


class AnchorRecorder:
    """Expected I1b AnchoredRoot call contract, without filesystem operations."""
    def __init__(self, binding):
        self.binding = binding
        self.events = []
        self.writes = []
        self.current = copy.deepcopy(binding.instance)
        self.fail_write = False
        outer = self

        class AnchoredRoot:
            def __init__(self, path, verify):
                if path != '/data':
                    raise AssertionError('import anchor is not historical data root')
                self.verify = verify
                outer.events.append(('open', path))

            def __enter__(self):
                self.verify()
                return self

            def __exit__(self, exc_type, value, tb):
                outer.events.append(('close', exc_type))

            def read_json(self, relative):
                if relative != INSTANCE_SUFFIX:
                    raise AssertionError('anchor read a non-instance file')
                outer.events.append(('read', relative))
                return copy.deepcopy(outer.current)

            def atomic_json(self, relative, value):
                if relative != INSTANCE_SUFFIX:
                    raise AssertionError('anchor wrote a non-instance file')
                if outer.fail_write:
                    raise OSError('synthetic anchor write failure')
                outer.events.append(('write', relative))
                outer.writes.append((relative, copy.deepcopy(value)))
                outer.current = copy.deepcopy(value)

            def check(self):
                outer.events.append(('check',))
                self.verify()

        self.api = SimpleNamespace(AnchoredRoot=AnchoredRoot)


class FreshInstanceTests(unittest.TestCase):
    def test_both_fresh_templates_bind_nondefault_paths_without_io_or_claims(self):
        for name in ('instance.template', 'f1s.template'):
            for data, models in [('/srv/ai', '/srv/ai/models'), ('/srv/ai', '/srv/ai'),
                                 ('/srv/ai', '/srv/ai/models-large'), ('/srv/ai', '/mnt/weights')]:
                with self.subTest(template=name, data=data, models=models):
                    binding = InstanceBinding(data=data, models=models)
                    template = profile(name)
                    before = copy.deepcopy(template)
                    with patch.object(Path, 'write_text', side_effect=AssertionError('fresh write')), \
                            patch.object(Path, 'read_text', side_effect=AssertionError('fresh read')):
                        result = render_fresh_instance(template, binding, 'fresh-instance')
                    self.assertEqual(template, before)
                    self.assertEqual(result['id'], 'fresh-instance')
                    self.assertEqual(result['storage_identity'], binding.identity)
                    self.assertEqual(result['paths']['state'], {'role': 'data', 'suffix': 'services/llm-manager/active'})
                    self.assertEqual(result['runtime_evidence'], template['runtime_evidence'])
                    self.assertFalse(result['obsolete_boot_owner_disabled'])
                    self.assertEqual(binding.reads, [])
                    self.assertEqual(binding.verifications, [('data', 'models')])
                    for model_id, evidence in result['model_integrity'].items():
                        self.assertFalse(evidence['verified'])
                        if 'completion_manifest' in evidence:
                            self.assertEqual(evidence['completion_manifest'],
                                             data + '/services/llm-manager/acquisition/' + model_id + '.complete.json')

    def test_rejects_prebound_historical_activated_and_unsafe_fresh_templates(self):
        base = profile('f1s.template')
        cases = []
        for mutation in [lambda d: d.update(storage_identity={'preexisting': True}),
                         lambda d: d.update(required_mounts=[]),
                         lambda d: d['model_integrity']['qwen3-coder-next-fp8'].update(verified=True),
                         lambda d: d['runtime_evidence']['sglang-qwen-next-0.5.14'].update(auth_gate_passed=True),
                         lambda d: d['paths'].update(state='/data/services/llm-manager/active'),
                         lambda d: d['model_integrity']['qwen3-coder-next-fp8'].update(completion_manifest='/models/completion.json'),
                         lambda d: d['model_integrity']['qwen3-coder-next-fp8'].update(completion_manifest={'role': 'models', 'suffix': 'services/llm-manager/acquisition/result.json'}),
                         lambda d: d['model_integrity']['qwen3-coder-next-fp8'].update(completion_manifest={'role': 'data', 'suffix': 'services/llm-manager/acquisition/../result.json'})]:
            d = copy.deepcopy(base)
            mutation(d)
            cases.append(d)
        for index, template in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(LifecycleError):
                render_fresh_instance(template, InstanceBinding(), 'fresh-instance')
        with self.assertRaises(LifecycleError):
            render_fresh_instance(base, InstanceBinding(), '../instance')


class HistoricalImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.old = profile('ai-vm-d0b')
        self.old.update(
            selected='qwen3-coder-next', desired='running', boot_policy='resume',
            state_schema_version=2,
            container={'id': 'fixture-container', 'image_id': 'fixture-image', 'owner': 'llmctl'},
            key_evidence={'path': '/data/services/secrets/llm-api-key', 'mode': '0600', 'preserved': True},
        )
        self.old['model_integrity']['glm-5.3-ud-q4-k-xl'].update(verified=True, evidence=['retained-artifact-proof'])
        f1s = profile('f1s.template')
        self.old['runtime_evidence'].update(f1s['runtime_evidence'])
        self.old['runtime_evidence']['sglang-qwen-next-0.5.14'].update(
            flags_verified=True, auth_gate_passed=True, launcher_sha256='retained-launcher-hash',
            evidence=['retained-runtime-proof'], auth_gate_evidence=['retained-image-auth-proof'])
        self.old['model_integrity']['qwen3-coder-next-fp8'] = {
            'verified': True, 'revision': 'da6e2ed27304dd39abadd9c82ef50e8de67bdd4c',
            'manifest_sha256': '022674d4daf63fa57c2798a30fea80c6dde7b1b2e73630ae3c3aa94e45debb9e',
            'completion_manifest': '/data/services/llm-manager/acquisition/qwen3-coder-next-fp8.complete.json',
            'evidence': ['retained-acquisition-proof'],
        }
        self.binding = InstanceBinding(self.old, system_root=self.root)
        for role, mount in zip(('data', 'models'), self.old['required_mounts']):
            self.binding.registry[role]['uuid'] = mount['uuid']
        self.binding.identity = copy.deepcopy(self.binding.registry)
        self.anchor = AnchorRecorder(self.binding)

    def lease(self):
        return acquire_lease(system_root=self.root, trusted_uid=os.geteuid())

    def imported(self, lease):
        return import_historical_instance(self.binding, lease=lease, storage_io=self.anchor.api)

    def test_explicit_import_changes_only_binding_markers_and_keeps_borrowed_lease(self):
        before = copy.deepcopy(self.old)
        with self.lease() as lease:
            self.assertTrue(transition_in_progress(system_root=self.root, trusted_uid=os.geteuid()))
            result = self.imported(lease)
            lease.validate()
            self.assertTrue(transition_in_progress(system_root=self.root, trusted_uid=os.geteuid()))
        self.assertFalse(transition_in_progress(system_root=self.root, trusted_uid=os.geteuid()))
        expected = {**before, 'storage_identity': self.binding.identity, 'historical_import': True}
        self.assertEqual(result, expected)
        self.assertEqual(self.binding.instance, before)
        self.assertEqual(self.binding.reads, [('data', INSTANCE_PATH)])
        self.assertEqual(self.anchor.writes, [(INSTANCE_SUFFIX, expected)])
        self.assertEqual([e[0] for e in self.anchor.events], ['open', 'read', 'write', 'check', 'close'])
        self.assertEqual(self.binding.verifications, [('data', 'models'), ('data',), ('data',)])

    def test_idempotent_explicit_import_does_not_rewrite_evidence(self):
        self.binding.instance.update(storage_identity=self.binding.identity, historical_import=True)
        with self.lease() as lease:
            result = self.imported(lease)
            lease.validate()
        self.assertEqual(result, self.binding.instance)
        self.assertEqual(self.anchor.events, [])
        self.assertEqual(self.anchor.writes, [])

    def test_changed_registry_instance_paths_mounts_and_completion_refuse_before_write(self):
        mutations = [lambda d: d.update(storage_identity={'mismatch': True}),
                     lambda d: d.update(schema_version=2),
                     lambda d: d['paths'].update(state='/new/state'),
                     lambda d: d['required_mounts'][1].update(uuid='replaced'),
                     lambda d: d['required_mounts'][0].update(target='/elsewhere'),
                     lambda d: d['model_integrity']['qwen3-coder-next-fp8'].update(completion_manifest='/elsewhere/result.json'),
                     lambda d: d['model_integrity']['qwen3-coder-next-fp8'].update(completion_manifest={'role': 'data', 'suffix': 'receipt.json'})]
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index):
                self.binding.instance = copy.deepcopy(self.old)
                mutate(self.binding.instance)
                with self.lease() as lease, self.assertRaises(LifecycleError):
                    self.imported(lease)
                self.assertEqual(self.anchor.writes, [])

    def test_different_actual_mount_or_root_cannot_reinterpret_historical_paths(self):
        for role, field, path in [('data', 'path', '/srv/ai'), ('models', 'path', '/mnt/weights'),
                                  ('models', 'mount', '/data'), ('data', 'mount', '/')]:
            with self.subTest(role=role, field=field):
                saved = self.binding.registry[role][field]
                self.binding.registry[role][field] = path
                try:
                    with self.lease() as lease, self.assertRaises(LifecycleError):
                        self.imported(lease)
                    self.assertEqual(self.binding.reads, [])
                    self.assertEqual(self.anchor.writes, [])
                finally:
                    self.binding.registry[role][field] = saved

    def test_instance_replacement_after_preflight_refuses_commit(self):
        self.anchor.current['id'] = 'replacement-instance'
        with self.lease() as lease:
            with self.assertRaisesRegex(LifecycleError, 'historical_instance_changed'):
                self.imported(lease)
            lease.validate()
        self.assertEqual(self.anchor.writes, [])
        self.assertEqual([e[0] for e in self.anchor.events], ['open', 'read', 'close'])

    def test_write_error_does_not_close_or_release_owners_lease(self):
        self.anchor.fail_write = True
        with self.lease() as lease:
            with self.assertRaises(OSError):
                self.imported(lease)
            lease.validate()
            self.assertTrue(transition_in_progress(system_root=self.root, trusted_uid=os.geteuid()))
        self.assertFalse(transition_in_progress(system_root=self.root, trusted_uid=os.geteuid()))
        self.assertEqual(self.anchor.writes, [])

    def test_raw_forged_stale_and_replaced_inode_leases_refuse_before_instance_reads(self):
        for lease in (object(), 5, object.__new__(LifecycleLease)):
            with self.subTest(kind=type(lease).__name__), self.assertRaises((LeaseError, LifecycleError)):
                self.imported(lease)
        with self.lease() as stale:
            pass
        with self.assertRaises(LeaseError):
            self.imported(stale)
        with self.lease() as lease:
            lock = self.root / 'run/llmctl/lifecycle.lock'
            lock.rename(lock.with_name('old.lock'))
            lock.touch(mode=0o600)
            with self.assertRaises(LeaseError):
                self.imported(lease)
        self.assertEqual(self.binding.reads, [])
        self.assertEqual(self.anchor.events, [])

    def test_active_lease_for_another_fixture_scope_refuses_before_instance_read(self):
        with tempfile.TemporaryDirectory() as other:
            other_root = Path(other).resolve()
            with acquire_lease(system_root=other_root, trusted_uid=os.geteuid()) as lease:
                with self.assertRaises(LeaseError):
                    self.imported(lease)
                lease.validate()
                self.assertTrue(transition_in_progress(system_root=other_root, trusted_uid=os.geteuid()))
        self.assertEqual(self.binding.reads, [])
        self.assertEqual(self.binding.verifications, [])
        self.assertEqual(self.anchor.events, [])


if __name__ == '__main__':
    unittest.main()
