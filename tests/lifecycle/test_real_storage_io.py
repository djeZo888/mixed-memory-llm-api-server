"""L1 calls real I1b guard/writer on protected worker directories.

MountedStorageGuard, AnchoredRoot, GuardedFile, Manager.persistent_json and the
historical import helper execute their actual implementations. Only Linux
storage discovery/mountinfo and ordinary-user uid are explicit fixture seams.
Historical /data names additionally project into the fixture at writer entry;
no real /data, device, key, model, Docker or service is accessed.

Rename/exchange at the actual mkdir/replace syscall is a deterministic detach
surrogate, not a claim that a Linux mount was unmounted on this worker. Synthetic
single/split mount entries reside on the worker's one real fixture filesystem.
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
from common.lifecycle_lease import acquire_lease
from install.storage import Storage, StorageError
from install import storage_io as real_io
from lifecycle.instance_binding import import_historical_instance
from lifecycle.manager import LABEL, OWNER, Manager, empty_state
from lifecycle.runtime_io import LifecycleError
from lifecycle.storage_binding import BindingError, RegisteredStorageBinding
from test_manager import FakeDocker


class LocalStorageFixture:
    def __init__(self, *, layout='single', historical=False):
        self.temp = tempfile.TemporaryDirectory(prefix='.l1-real-storage-', dir=ROOT)
        self.base = Path(self.temp.name).resolve()
        self.historical = historical
        self.data = '/data' if historical else str(self.base / 'srv/ai-server')
        if historical:
            self.models = '/data/models-large'
        elif layout == 'nested':
            self.models = self.data + '/models-large'
        elif layout == 'sibling':
            self.models = str(self.base / 'mnt/model-volume')
        elif layout == 'equal':
            self.models = self.data
        else:
            self.models = self.data + '/models'
        self.split = historical or layout in {'nested', 'sibling'}
        self.lost = False
        self.full_checks = 0
        self.guards, self.anchors = [], []
        fixture = self

        class StorageProbe(Storage):
            """Retain real registry/identity/ownership checks; inject discovery."""
            def _local(self, path):
                return fixture.local(path)

            def _snapshot(self):
                fixture.full_checks += 1
                if fixture.lost:
                    raise StorageError('synthetic_registered_mount_lost')
                return copy.deepcopy(fixture.snapshot)

            def _capacity(self, snapshot):
                return {'root_available_bytes': 100 * 1024 ** 3,
                        'data_available_bytes': 100 * 1024 ** 3,
                        'model_available_bytes': 100 * 1024 ** 3}

            def _mount(self, path):
                # Binding's system_root seam emits a path in the virtual root.
                logical = path if historical else str(fixture.base / path.lstrip('/'))
                if not historical and str(path).startswith(str(fixture.base) + '/'):
                    logical = path
                rows = [fixture.snapshot[role] for role in ('data', 'models')
                        if logical == fixture.snapshot[role]['mount']
                        or logical.startswith(fixture.snapshot[role]['mount'] + '/')]
                if fixture.lost or not rows:
                    return {'target': '/', 'uuid': 'fixture-root-uuid', 'fstype': 'ext4'}
                value = max(rows, key=lambda row: len(row['mount']))
                return {'target': value['mount'], 'uuid': value['uuid'], 'fstype': value['fstype']}

        self.storage = StorageProbe({'data_dir': self.data, 'model_dir': self.models,
                                     'data_uuid': 'fixture-data-uuid',
                                     'model_uuid': 'fixture-model-uuid' if self.split else 'fixture-data-uuid'},
                                    runner=None, system_root=self.base)
        roots = self.storage._roots()
        for role, path in roots.items():
            local = self.local(path)
            local.mkdir(parents=True, exist_ok=True)
            local.chmod(0o700 if role in {'state', 'secrets'} else 0o755)
        info = self.local(self.data).stat()
        device = f'{os.major(info.st_dev)}:{os.minor(info.st_dev)}'
        data = {'path': self.data, 'mount': self.data, 'uuid': 'fixture-data-uuid',
                'fstype': 'ext4', 'device': device, 'source': '/dev/fixture-data', 'parents': ['/dev/fixture-data']}
        models = dict(data, path=self.models)
        if self.split:
            models.update(mount=self.models, uuid='fixture-model-uuid', source='/dev/fixture-model', parents=['/dev/fixture-model'])
        self.snapshot = {'schema_version': 1, 'storage_mode': 'existing', 'data': data,
                         'models': models, 'roots': roots}
        self.jsonfile('/etc/local-ai-server/storage.json', self.snapshot)
        self.local('/etc/local-ai-server').chmod(0o700)
        self.mountinfo = '1 0 0:1 / / rw - ext4 /dev/fixture-root rw\n'
        self.mountinfo += f'2 1 {device} / {self.data} rw - ext4 /dev/fixture-data rw\n'
        if self.split:
            self.mountinfo += f'3 2 {device} / {self.models} rw - ext4 /dev/fixture-model rw\n'
        self.binding = RegisteredStorageBinding(self.storage, self.snapshot)
        self.binding.verify()
        self.api = SimpleNamespace(MountedStorageGuard=self.mounted_guard, AnchoredRoot=self.anchored_root)
        self.instance = {'schema_version': 1, 'id': 'real-io-fixture',
                         'storage_identity': self.binding.identity,
                         'paths': {'state': {'role': 'data', 'suffix': 'services/llm-manager/active'}}}
        self.docker = FakeDocker()
        self.manager = Manager(ROOT / 'configs', self.instance, binding=self.binding, storage_io=self.api,
                               test_paths=True, lease_system_root=self.base, docker=self.docker)

    def close(self):
        for guard in self.guards:
            guard.close()
        for anchor in self.anchors:
            anchor.close()
        self.temp.cleanup()

    def local(self, path):
        path = Path(path)
        if path == self.base or self.base in path.parents:
            return path
        return self.base / str(path).lstrip('/')

    def jsonfile(self, path, value):
        local = self.local(path)
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(json.dumps(value))
        local.chmod(0o600)
        return local

    def mounted_guard(self, storage):
        value = real_io.MountedStorageGuard(storage, mountinfo_reader=lambda: self.mountinfo)
        self.guards.append(value)
        return value

    def physical_snapshot(self, snapshot):
        if not self.historical:
            return snapshot
        value = copy.deepcopy(snapshot)
        for role in ('data', 'models'):
            for key in ('path', 'mount'):
                value[role][key] = str(self.local(value[role][key]))
        value['roots'] = {name: str(self.local(path)) for name, path in value['roots'].items()}
        return value

    def anchored_root(self, path, guard):
        # No writer substitute: return the actual class, with the documented
        # uid seam. /data projection is limited to the historical fixture.
        checked = (lambda: self.physical_snapshot(guard())) if self.historical else guard
        value = real_io.AnchoredRoot(str(self.local(path)), checked, uid=os.geteuid())
        self.anchors.append(value)
        return value

    def lease(self):
        return acquire_lease(system_root=self.base, trusted_uid=os.geteuid())

    def detach_surrogate(self):
        """Expose a preexisting fallback tree after the writer holds old FDs."""
        mount = self.local(self.data)
        detached = self.base / 'detached-data'
        fallback = self.base / 'fallback-root'
        fallback.mkdir(mode=0o700)
        (fallback / 'underlying-marker').write_bytes(b'underlying-root-unchanged')
        os.rename(mount, detached)
        os.rename(fallback, mount)
        self.lost = True
        self.mountinfo = self.mountinfo.splitlines()[0] + '\n'
        return detached


class RealStorageIntegrationTests(unittest.TestCase):
    def fixture(self, **kwargs):
        value = LocalStorageFixture(**kwargs)
        self.addCleanup(value.close)
        return value

    def assert_closed(self, fixture):
        self.assertTrue(fixture.guards)
        self.assertTrue(fixture.anchors)
        for handle in fixture.guards + fixture.anchors:
            self.assertTrue(handle._closed)
            self.assertEqual(handle._lineage, [])

    def test_manager_real_writer_single_equal_nested_sibling_nondefault_paths(self):
        for layout in ('single', 'equal', 'nested', 'sibling'):
            with self.subTest(layout=layout):
                fixture = self.fixture(layout=layout)
                for deployment in ('glm-5.3-ud-q4-k-xl-8k', 'qwen3-coder-next'):
                    path = fixture.binding.path('data', f'logs/llmctl/{deployment}/result.json')
                    with fixture.lease() as lease:
                        fixture.manager.persistent_json(path, {'deployment': deployment, 'complete': False})
                        lease.validate()
                    self.assertEqual(json.loads(Path(path).read_text())['deployment'], deployment)
                    self.assertEqual(Path(path).stat().st_mode & 0o777, 0o600)
                    self.assertEqual([p.name for p in Path(path).parent.iterdir()], ['result.json'])
                self.assert_closed(fixture)

    def test_mkdir_race_writes_only_to_detached_held_directory(self):
        fixture = self.fixture()
        target = fixture.binding.path('data', 'services/llm-manager/race-child/state.json')
        original = os.mkdir
        detached = []

        def exchange_then_mkdir(path, mode=0o777, *, dir_fd=None):
            if str(path) == 'race-child' and dir_fd is not None and not detached:
                detached.append(fixture.detach_surrogate())
            return original(path, mode, dir_fd=dir_fd)

        with fixture.lease(), patch.object(real_io.os, 'mkdir', side_effect=exchange_then_mkdir):
            with self.assertRaisesRegex(LifecycleError, 'persistent_storage_io_failed'):
                fixture.manager.persistent_json(target, {'complete': True})
        self.assertEqual(len(detached), 1)
        self.assertTrue((detached[0] / 'services/llm-manager/race-child').is_dir())
        self.assertEqual(sorted(p.name for p in fixture.local(fixture.data).iterdir()), ['underlying-marker'])
        self.assertFalse(Path(target).exists())
        self.assert_closed(fixture)

    def test_atomic_commit_race_stays_on_old_fd_and_never_reports_success(self):
        fixture = self.fixture(layout='sibling')
        target = fixture.binding.path('data', 'services/llm-manager/active/active.json')
        with fixture.lease():
            fixture.manager.persistent_json(target, {'generation': 1})
        original = os.replace
        detached = []

        def exchange_then_replace(source, destination, *, src_dir_fd=None, dst_dir_fd=None):
            if destination == 'active.json' and src_dir_fd is not None and not detached:
                detached.append(fixture.detach_surrogate())
            return original(source, destination, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)

        with fixture.lease(), patch.object(real_io.os, 'replace', side_effect=exchange_then_replace):
            with self.assertRaisesRegex(LifecycleError, 'persistent_storage_io_failed'):
                fixture.manager.persistent_json(target, {'generation': 2})
        self.assertEqual(len(detached), 1)
        retained = detached[0] / 'services/llm-manager/active/active.json'
        self.assertEqual(json.loads(retained.read_text()), {'generation': 2})
        self.assertEqual(sorted(p.name for p in fixture.local(fixture.data).iterdir()), ['underlying-marker'])
        self.assertFalse(Path(target).exists())
        self.assert_closed(fixture)

    def test_actual_mounted_guard_rejects_mount_id_replacement_during_write(self):
        fixture = self.fixture()
        target = fixture.binding.path('data', 'services/llm-manager/active/active.json')
        with fixture.lease():
            fixture.manager.persistent_json(target, {'generation': 1})
        original = os.write
        changed = []

        def replace_mount_id(fd, data):
            count = original(fd, data)
            if not changed:
                changed.append(True)
                fixture.mountinfo = fixture.mountinfo.replace('2 1 ', '9 1 ')
            return count

        with fixture.lease(), patch.object(real_io.os, 'write', side_effect=replace_mount_id):
            with self.assertRaisesRegex(LifecycleError, 'persistent_storage_io_failed'):
                fixture.manager.persistent_json(target, {'generation': 2})
        self.assertEqual(json.loads(Path(target).read_text()), {'generation': 1})
        self.assert_closed(fixture)

    def test_real_mounted_guard_enter_failure_closes_its_registry_descriptors(self):
        fixture = self.fixture()
        original_factory = fixture.api.MountedStorageGuard

        def lose_mount_after_constructor(storage):
            guard = original_factory(storage)
            fixture.mountinfo = fixture.mountinfo.splitlines()[0] + '\n'
            return guard

        fixture.api.MountedStorageGuard = lose_mount_after_constructor
        target = fixture.binding.path('data', 'services/llm-manager/active/active.json')
        with fixture.lease(), self.assertRaisesRegex(LifecycleError, 'persistent_storage_io_failed'):
            fixture.manager.persistent_json(target, {'generation': 1})
        self.assertEqual(len(fixture.guards), 1)
        self.assertTrue(fixture.guards[0]._closed)
        self.assertEqual(fixture.guards[0]._lineage, [])
        self.assertFalse(Path(target).exists())

    def test_real_anchor_enter_failure_closes_its_directory_descriptors(self):
        fixture = self.fixture()
        original_factory = fixture.api.AnchoredRoot

        def lose_mount_after_constructor(path, guard):
            anchor = original_factory(path, guard)
            fixture.mountinfo = fixture.mountinfo.splitlines()[0] + '\n'
            return anchor

        fixture.api.AnchoredRoot = lose_mount_after_constructor
        target = fixture.binding.path('data', 'services/llm-manager/active/active.json')
        with fixture.lease(), self.assertRaisesRegex(LifecycleError, 'persistent_storage_io_failed'):
            fixture.manager.persistent_json(target, {'generation': 1})
        self.assert_closed(fixture)
        self.assertFalse(Path(target).exists())

    def test_new_same_device_descendant_mount_after_preflight_is_rejected(self):
        """Required shared gap: actual guard currently checks only named roots.

        This injects the kernel mountinfo observation, not a real Linux bind.
        The guard must reject the newly observed bind before persistent success.
        """
        fixture = self.fixture()
        parent = fixture.binding.path('data', 'services/llm-manager')
        Path(parent).mkdir(mode=0o700)
        original_factory = fixture.api.AnchoredRoot

        def insert_descendant_mount_after_anchor(path, guard):
            anchor = original_factory(path, guard)
            device = fixture.snapshot['data']['device']
            fixture.mountinfo += f'9 2 {device} /elsewhere {parent} rw - ext4 /dev/fixture-data rw\n'
            return anchor

        fixture.api.AnchoredRoot = insert_descendant_mount_after_anchor
        target = parent + '/active/active.json'
        with fixture.lease(), self.assertRaisesRegex(LifecycleError, 'persistent_storage_io_failed'):
            fixture.manager.persistent_json(target, {'generation': 1})
        self.assertFalse(Path(target).exists())

    def test_trusted_stop_after_real_persistence_race_retains_volatile_truth(self):
        fixture = self.fixture()
        identity = {'id': 'a' * 64, 'image_id': 'sha256:' + 'b' * 64,
                    'name': 'llmctl-trusted-fixture', 'owner': OWNER,
                    'instance': fixture.instance['id'], 'deployment': 'qwen3-coder-next', 'legacy': False}
        fixture.docker.records = [{'Id': identity['id'], 'Image': identity['image_id'], 'Name': '/' + identity['name'],
                                   'Config': {'Labels': {LABEL + key: identity[key] for key in ('owner', 'instance', 'deployment')}},
                                   'State': {'Running': True, 'Status': 'running'},
                                   'NetworkSettings': {'Ports': {}}}]
        fixture.manager.state = {**empty_state(), 'selected': identity['deployment'], 'desired': 'running',
                                 'observed': 'ready', 'container_running': True, 'container': identity}
        with fixture.lease():
            fixture.manager.save()
        original = os.replace
        detached = []

        def detach_commit(source, destination, *, src_dir_fd=None, dst_dir_fd=None):
            if destination == 'active.json' and src_dir_fd is not None and not detached:
                detached.append(fixture.detach_surrogate())
            return original(source, destination, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)

        with fixture.lease() as lease, patch.object(real_io.os, 'replace', side_effect=detach_commit):
            result = fixture.manager.dispatch('stop', lease=lease)
            lease.validate()
        self.assertEqual(result['observed'], 'stopped')
        self.assertEqual(result['desired'], 'stopped')
        self.assertFalse(result['state_persisted'])
        self.assertIn(('stop', identity['id']), fixture.docker.calls)
        journal = json.loads(fixture.manager.recovery_file.read_text())
        self.assertFalse(journal['state_persisted'])
        self.assertEqual(journal['container']['id'], identity['id'])
        self.assertEqual(sorted(p.name for p in fixture.local(fixture.data).iterdir()), ['underlying-marker'])
        self.assert_closed(fixture)

    def test_historical_import_uses_actual_writer_and_preserves_all_prior_evidence(self):
        fixture = self.fixture(historical=True)
        path = '/data/services/llm-manager/deployment-instance.json'
        old = {'schema_version': 1, 'id': 'historical-kept',
               'paths': {'state': '/data/services/llm-manager/active', 'lock': '/run/llmctl/lifecycle.lock',
                         'recovery': '/run/llmctl/recovery.json'},
               'required_mounts': [{'target': fixture.snapshot[role]['mount'], 'uuid': fixture.snapshot[role]['uuid'],
                                    'filesystem': fixture.snapshot[role]['fstype']} for role in ('data', 'models')],
               'selected': 'qwen3-coder-next', 'desired': 'running', 'boot_policy': 'resume',
               'runtime_evidence': {'sglang-qwen-next-0.5.14': {'auth_gate_passed': True,
                    'launcher_sha256': 'c' * 64, 'auth_gate_evidence': 'retained-synthetic-evidence'}},
               'model_integrity': {'qwen3-coder-next-fp8': {'verified': True,
                    'completion_manifest': '/data/services/llm-manager/acquisition/qwen.complete.json'}}}
        fixture.jsonfile(path, old)
        state = fixture.jsonfile('/data/services/llm-manager/active/active.json',
                                 {'schema_version': 2, 'desired': 'running', 'container': {'id': 'retained-container'}})
        completion = fixture.jsonfile('/data/services/llm-manager/acquisition/qwen.complete.json',
                                      {'model_root': '/data/models-large/qwen3-coder-next-fp8', 'proof': 'retained'})
        before = {state: state.read_bytes(), completion: completion.read_bytes()}
        with fixture.lease() as lease:
            value = import_historical_instance(fixture.binding, lease=lease, storage_io=fixture.api)
            lease.validate()
        expected = {**old, 'storage_identity': fixture.binding.identity, 'historical_import': True}
        self.assertEqual(value, expected)
        self.assertEqual(json.loads(fixture.local(path).read_text()), expected)
        self.assertEqual(before, {item: item.read_bytes() for item in before})
        self.assert_closed(fixture)
        previous_inode = fixture.local(path).stat().st_ino
        with fixture.lease() as lease:
            self.assertEqual(import_historical_instance(fixture.binding, lease=lease, storage_io=fixture.api), expected)
        self.assertEqual(fixture.local(path).stat().st_ino, previous_inode)


if __name__ == '__main__':
    unittest.main()
