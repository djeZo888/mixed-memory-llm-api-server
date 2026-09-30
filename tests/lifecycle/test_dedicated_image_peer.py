"""Offline dedicated-image coexistence proofs; no VM, Docker or native requests."""
import copy
import hashlib
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from tests.lifecycle.test_concurrent_profiles import bound
from tests.lifecycle.test_qwen38 import BindingFixture
from lifecycle import concurrent_profiles as pair
from lifecycle.manager import Manager, OWNER
from lifecycle.runtime_io import LifecycleError
from runtime.h005_runtime_binding import load


ROOT = Path(__file__).resolve().parents[2]
ADA = 'GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23'
IMAGE_OWNER = 'IMAGE21-RUNTIME-20260923'
IMAGE_RUNTIME = '0cd8be351d0825488f4b81c8931167bbab618eca'
IMAGE_REVISION = '790c92633540aa0cb11d9abf19eb46d861714758'
CID, RUN_ID, NETWORK_ID = 'a' * 64, 'b' * 32, 'c' * 64
NETWORK = 'llm-image-backend-private'
CAP = 96 * 1024**3
START = '2026-09-25T19:39:28.867729650Z'
PORTS = {'30007/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '30007'}]}


def change(value, path, replacement):
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = replacement


class DedicatedImagePeerTests(unittest.TestCase):
    def setUp(self):
        self.image_id = load()['image']['image_id']
        self.binding = BindingFixture()
        self.binding.roots = {**self.binding.roots, 'services': self.binding.path('data', 'services')}
        self.binding.identity = {'synthetic': 'registered-storage-fixture'}
        self.manager = Manager(ROOT / 'configs', {
            'schema_version': 1, 'id': 'synthetic-instance',
            'storage_identity': self.binding.identity,
            'paths': {'state': {'role': 'data', 'suffix': 'services/llm-manager/active'}},
        }, binding=self.binding, test_paths=True,
            run_fn=lambda *a, **k: self.fail('external command forbidden'),
            probe_fn=lambda *a, **k: self.fail('native probe forbidden'))
        self.manager.persistent_json = Mock(side_effect=AssertionError('persistent write forbidden'))
        self.manager.sglang_probe = Mock(side_effect=AssertionError('native probe forbidden'))
        self.state = {'schema_version': 1, 'owner': IMAGE_OWNER, 'phase': 'warm', 'warm': True,
            'run_id': RUN_ID, 'container': {'id': CID, 'image_id': self.image_id}}
        self.config = {'schema_version': 1, 'owner': IMAGE_OWNER, 'image_id': self.image_id,
            'network_id': NETWORK_ID, 'source_commit': IMAGE_RUNTIME,
            'checkpoint_revision': IMAGE_REVISION,
            'checkpoint_path': self.binding.path('models', 'qwen-image-2.1-' + IMAGE_REVISION)}
        base = self.binding.path('services', 'image21-runtime-20260923')
        self.source_bytes = {base + '/source/' + name: ('# synthetic ' + name + '\n').encode()
            for name in ('service.py', 'native_server.py', 'native_request.py', 'telemetry.py')}
        self.config['source_sha256'] = {Path(path).name: hashlib.sha256(value).hexdigest()
            for path, value in self.source_bytes.items()}
        self.source_patch = patch('control.installation.protected_file',
            side_effect=lambda path, **kw: self.source_bytes[str(path)])
        self.source_read = self.source_patch.start()
        self.addCleanup(self.source_patch.stop)
        self.docs = {}
        for suffix, value in (('state.json', self.state), ('config.json', self.config)):
            self.docs[self.binding.path('services', 'image21-runtime-20260923/' + suffix)] = value
        self.binding.read_json = Mock(side_effect=lambda role, path, **kw: copy.deepcopy(self.docs[path]))
        self.candidate = {
            'Id': CID, 'Name': '/llm-image-backend', 'Image': self.image_id,
            'Config': {'User': '1000:1001', 'Image': self.image_id,
                'Entrypoint': ['/opt/image-venv/bin/python'],
                'Cmd': ['-I', '-B', '/runtime/native_server.py', RUN_ID], 'Labels': {
                'io.llm-image.owner': IMAGE_OWNER, 'io.llm-image.invocation': RUN_ID,
                'io.llm-image.gpu': ADA},
                'Env': ['CUDA_VISIBLE_DEVICES=' + ADA, 'NVIDIA_VISIBLE_DEVICES=' + ADA]},
            'State': {'Running': True, 'Status': 'running', 'Pid': 592783, 'StartedAt': START,
                'Paused': False, 'Restarting': False, 'Dead': False, 'OOMKilled': False},
            'HostConfig': {
                'DeviceRequests': [{'DeviceIDs': [ADA], 'Count': 0, 'Driver': 'nvidia',
                    'Capabilities': [['gpu']], 'Options': {}}],
                'Devices': [], 'DeviceCgroupRules': [], 'Privileged': False, 'ReadonlyRootfs': True,
                'CapAdd': [], 'CapDrop': ['ALL'], 'SecurityOpt': ['no-new-privileges'],
                'PidMode': '', 'IpcMode': 'private', 'UTSMode': '', 'UsernsMode': '',
                'CgroupnsMode': 'private', 'Binds': [], 'VolumesFrom': [],
                'CpusetCpus': '8-15', 'Memory': CAP, 'MemorySwap': CAP,
                'RestartPolicy': {'Name': 'no', 'MaximumRetryCount': 0},
                'NetworkMode': NETWORK, 'PublishAllPorts': False,
                'PortBindings': copy.deepcopy(PORTS)},
            'NetworkSettings': {'Ports': copy.deepcopy(PORTS),
                'Networks': {NETWORK: {'NetworkID': NETWORK_ID}}},
            'Mounts': [{'Type': 'bind', 'Source': source,
                'Destination': destination, 'RW': writable, 'Propagation': 'rprivate'}
                for destination, source, writable in (
                    ('/models', self.config['checkpoint_path'], False),
                    ('/runtime', base + '/source', False),
                    ('/work', base + '/work', True),
                    ('/tmp', base + '/work/tmp/' + RUN_ID, True))],
        }
        self.fresh = copy.deepcopy(self.candidate)
        self.manager.docker = Mock(spec=['inspect', 'inventory'])
        self.manager.docker.inspect.side_effect = lambda name: copy.deepcopy(self.fresh) if name == CID else None
        forbidden_reader = patch('control.node_observation.CanonicalIdentityReader',
            side_effect=AssertionError('image API/unit/latch ownership reader forbidden'))
        self.forbidden_reader = forbidden_reader.start()
        self.addCleanup(forbidden_reader.stop)
        self.deployments = {key: bound(key, self.binding) for key in (pair.QWEN0_PROFILE, pair.QWEN_PROFILE)}
        self.deployment = self.deployments[pair.QWEN0_PROFILE]

    def validate(self, candidate=None):
        return self.manager.validate_dedicated_image_peer(
            self.candidate if candidate is None else candidate, self.deployment)

    def test_exact_current_registered_image_is_accepted_without_mutation(self):
        before = copy.deepcopy((self.candidate, self.docs))
        self.validate()
        self.assertEqual((self.candidate, self.docs), before)
        self.manager.docker.inspect.assert_called_once_with(CID)
        self.forbidden_reader.assert_not_called()
        self.manager.persistent_json.assert_not_called()
        self.manager.sglang_probe.assert_not_called()

    def test_fresh_mount_order_is_irrelevant_but_full_entries_must_match(self):
        self.fresh['Mounts'].reverse()
        before = copy.deepcopy((self.candidate, self.fresh))
        self.validate()
        self.assertEqual((self.candidate, self.fresh), before)
        cases = (
            ('changed source', lambda mounts: mounts[0].update(Source='/data/services/foreign')),
            ('changed writable flag', lambda mounts: mounts[0].update(RW=not mounts[0]['RW'])),
            ('changed propagation', lambda mounts: mounts[0].update(Propagation='rshared')),
            ('changed destination', lambda mounts: mounts[0].update(Destination='/different')),
            ('duplicate destination', lambda mounts: mounts[0].update(Destination=mounts[1]['Destination'])),
            ('duplicate entry', lambda mounts: mounts.append(copy.deepcopy(mounts[0]))),
            ('missing entry', lambda mounts: mounts.pop()),
        )
        original = copy.deepcopy(self.fresh)
        for name, mutate in cases:
            with self.subTest(name=name):
                self.fresh = copy.deepcopy(original)
                mutate(self.fresh['Mounts'])
                with self.assertRaisesRegex(LifecycleError, '^untrusted_concurrent_peer$'):
                    self.validate()

    def test_backend_ownership_does_not_require_image_api_or_warm_readiness(self):
        for phase in ('loading', 'failed'):
            with self.subTest(image_phase=phase):
                self.state.update(phase=phase, warm=False)
                # The API may be failed, absent, or unconfigured. Any attempt to
                # consult its identity reader or files fails this positive case.
                before = copy.deepcopy((self.candidate, self.docs, self.fresh))
                self.validate()
                self.assertEqual((self.candidate, self.docs, self.fresh), before)
        self.forbidden_reader.assert_not_called()
        self.assertTrue(all(call[0] == 'inspect' for call in self.manager.docker.mock_calls))
        self.manager.persistent_json.assert_not_called()
        self.manager.sglang_probe.assert_not_called()

    def test_unproven_owner_or_changed_invocation_is_rejected(self):
        cases = (
            ('backend stopped', ('State', 'Running'), False),
            ('container id', ('Id',), 'd' * 64),
            ('pid', ('State', 'Pid'), 592784),
            ('started at', ('State', 'StartedAt'), '2026-09-25T20:22:21Z'),
            ('invocation', ('Config', 'Labels', 'io.llm-image.invocation'), 'd' * 32),
            ('device containment', ('HostConfig', 'DeviceRequests', 0, 'DeviceIDs'), [pair.GPU_UUIDS[0]]),
            ('new environment', ('Config', 'Env'), self.candidate['Config']['Env'] + ['NEW_SETTING=yes']),
            ('changed mounted source', ('Mounts', 1, 'Source'), '/data/services/unreviewed-source'),
            ('changed network', ('NetworkSettings', 'Networks', NETWORK, 'NetworkID'), 'd' * 64),
            ('paused', ('State', 'Paused'), True),
        )
        original = copy.deepcopy(self.fresh)
        for name, path, value in cases:
            with self.subTest(name=name):
                self.fresh = copy.deepcopy(original)
                change(self.fresh, path, value)
                with self.assertRaisesRegex(LifecycleError, '^untrusted_concurrent_peer$'):
                    self.validate()

    def test_protected_state_or_config_mismatch_is_rejected(self):
        cases = (
            ('state', ('owner',), 'foreign'), ('state', ('schema_version',), 2),
            ('state', ('run_id',), 'd' * 32),
            ('state', ('container', 'id'), 'd' * 64),
            ('state', ('container', 'image_id'), 'sha256:' + 'd' * 64),
            ('config', ('owner',), 'foreign'), ('config', ('schema_version',), 2),
            ('config', ('image_id',), 'sha256:' + 'd' * 64),
            ('config', ('network_id',), 'd' * 64),
            ('config', ('source_commit',), 'd' * 40),
            ('config', ('checkpoint_revision',), 'd' * 40),
            ('config', ('checkpoint_path',), '/unregistered/model'),
            ('config', ('source_sha256', 'service.py'), 'd' * 64),
        )
        original = copy.deepcopy(self.docs)
        for document, path, value in cases:
            with self.subTest(document=document, path=path):
                self.docs = copy.deepcopy(original)
                key = self.binding.path('services', 'image21-runtime-20260923/' + document + '.json')
                change(self.docs[key], path, value)
                with self.assertRaisesRegex(LifecycleError, '^untrusted_concurrent_peer$'):
                    self.validate()

    def test_missing_or_unavailable_proof_fails_closed(self):
        for target in (self.binding.read_json, self.manager.docker.inspect):
            old = target.side_effect
            try:
                target.side_effect = OSError('synthetic unavailable proof')
                with self.assertRaisesRegex(LifecycleError, '^untrusted_concurrent_peer$'):
                    self.validate()
            finally:
                target.side_effect = old
        self.manager.docker.inspect.side_effect = None
        self.manager.docker.inspect.return_value = None
        with self.assertRaisesRegex(LifecycleError, '^untrusted_concurrent_peer$'):
            self.validate()

    def test_protected_owner_or_config_changed_during_inspection_is_rejected(self):
        for suffix in ('state.json', 'config.json'):
            with self.subTest(changed=suffix):
                reads = {}
                def read(role, path, **kwargs):
                    reads[path] = reads.get(path, 0) + 1
                    value = copy.deepcopy(self.docs[path])
                    if path.endswith('/' + suffix) and reads[path] == 2:
                        value['concurrent_change'] = True
                    return value
                self.binding.read_json.side_effect = read
                with self.assertRaisesRegex(LifecycleError, '^untrusted_concurrent_peer$'):
                    self.validate()

    def test_source_bytes_or_closure_change_is_rejected(self):
        path = next(iter(self.source_bytes))
        original = self.source_bytes[path]
        self.source_bytes[path] = original + b'# tampered\n'
        with self.assertRaisesRegex(LifecycleError, '^untrusted_concurrent_peer$'):
            self.validate()
        self.source_bytes[path] = original
        self.config['source_sha256']['unreviewed.py'] = 'd' * 64
        with self.assertRaisesRegex(LifecycleError, '^untrusted_concurrent_peer$'):
            self.validate()

    def test_image_gpu_must_not_overlap_target(self):
        self.deployment['launch']['gpus'].append(ADA)
        with self.assertRaisesRegex(LifecycleError, '^untrusted_concurrent_peer$'):
            self.validate()
        self.manager.docker.inspect.assert_not_called()

    def test_adversarial_container_and_containment_fields_are_rejected(self):
        cases = (
            ('Id', ('Id',), 'd' * 64), ('name', ('Name',), '/forged-image'),
            ('image', ('Image',), 'sha256:' + 'd' * 64),
            ('owner label', ('Config', 'Labels', 'io.llm-image.owner'), 'foreign'),
            ('run label', ('Config', 'Labels', 'io.llm-image.invocation'), 'd' * 32),
            ('gpu label', ('Config', 'Labels', 'io.llm-image.gpu'), pair.GPU_UUIDS[0]),
            ('stopped', ('State', 'Running'), False), ('pid zero', ('State', 'Pid'), 0),
            ('paused', ('State', 'Paused'), True), ('restarting', ('State', 'Restarting'), True),
            ('dead', ('State', 'Dead'), True),
            ('wrong GPU', ('HostConfig', 'DeviceRequests', 0, 'DeviceIDs'), [pair.GPU_UUIDS[0]]),
            ('extra GPU', ('HostConfig', 'DeviceRequests', 0, 'DeviceIDs'), [ADA, pair.GPU_UUIDS[0]]),
            ('all GPUs', ('HostConfig', 'DeviceRequests', 0, 'Count'), -1),
            ('device options', ('HostConfig', 'DeviceRequests', 0, 'Options'), {'arbitrary': 'yes'}),
            ('devices', ('HostConfig', 'Devices'), [{'PathOnHost': '/dev/nvidia0'}]),
            ('device rules', ('HostConfig', 'DeviceCgroupRules'), ['c 195:* rwm']),
            ('privileged', ('HostConfig', 'Privileged'), True),
            ('writable root', ('HostConfig', 'ReadonlyRootfs'), False),
            ('cap add', ('HostConfig', 'CapAdd'), ['SYS_ADMIN']),
            ('cap drop', ('HostConfig', 'CapDrop'), []),
            ('security', ('HostConfig', 'SecurityOpt'), []),
            ('pid namespace', ('HostConfig', 'PidMode'), 'host'),
            ('ipc namespace', ('HostConfig', 'IpcMode'), 'host'),
            ('uts namespace', ('HostConfig', 'UTSMode'), 'host'),
            ('cpuset', ('HostConfig', 'CpusetCpus'), '0-71'),
            ('memory', ('HostConfig', 'Memory'), CAP + 1),
            ('swap', ('HostConfig', 'MemorySwap'), -1),
            ('restart', ('HostConfig', 'RestartPolicy'), {'Name': 'always', 'MaximumRetryCount': 0}),
            ('host network', ('HostConfig', 'NetworkMode'), 'host'),
            ('wildcard port', ('HostConfig', 'PortBindings', '30007/tcp', 0, 'HostIp'), '0.0.0.0'),
            ('text port', ('HostConfig', 'PortBindings', '30007/tcp', 0, 'HostPort'), '30002'),
            ('effective port', ('NetworkSettings', 'Ports', '30007/tcp', 0, 'HostPort'), '30004'),
            ('network id', ('NetworkSettings', 'Networks', NETWORK, 'NetworkID'), 'd' * 64),
            ('extra network', ('NetworkSettings', 'Networks'), {NETWORK: {'NetworkID': NETWORK_ID}, 'bridge': {}}),
            ('root user', ('Config', 'User'), '0'),
            ('entrypoint', ('Config', 'Entrypoint'), ['/bin/sh']),
            ('native command', ('Config', 'Cmd'), ['-I', '-B', '/runtime/native_server.py', 'd' * 32]),
            ('CUDA mismatch', ('Config', 'Env'), ['CUDA_VISIBLE_DEVICES=' + pair.GPU_UUIDS[0], 'NVIDIA_VISIBLE_DEVICES=' + ADA]),
            ('CUDA duplicate', ('Config', 'Env'), ['CUDA_VISIBLE_DEVICES=' + ADA, 'CUDA_VISIBLE_DEVICES=' + ADA, 'NVIDIA_VISIBLE_DEVICES=' + ADA]),
            ('root bind', ('Mounts', 0, 'Source'), '/'),
            ('device bind', ('Mounts', 0, 'Source'), '/dev/nvidia0'),
            ('proc target', ('Mounts', 0, 'Destination'), '/proc'),
            ('sys bind', ('Mounts', 0, 'Source'), '/sys'),
            ('wrong runtime source', ('Mounts', 1, 'Source'), '/data/services/unreviewed-source'),
            ('writable runtime source', ('Mounts', 1, 'RW'), True),
            ('wrong invocation tmp', ('Mounts', 3, 'Source'), '/data/services/unreviewed-tmp'),
        )
        for name, path, value in cases:
            with self.subTest(name=name):
                candidate = copy.deepcopy(self.candidate)
                change(candidate, path, value)
                with self.assertRaisesRegex(LifecycleError, '^untrusted_concurrent_peer$'):
                    self.validate(candidate)

    def integration(self, target):
        peer = 'qwen' if target == 'glm' else 'glm'
        profiles = {'glm': pair.QWEN0_PROFILE, 'qwen': pair.QWEN_PROFILE}
        peer_d = self.deployments[profiles[peer]]
        identity = {'id': 'e' * 64, 'name': peer_d['container_name'], 'image_id': 'sha256:' + 'f' * 64,
            'owner': OWNER, 'instance': self.manager.instance['id'], 'deployment': peer_d['id'], 'legacy': False}
        text_peer = {'Id': identity['id'], 'Name': '/' + identity['name'], 'Image': identity['image_id'],
            'Config': {'Labels': {'io.llmctl.owner': OWNER, 'io.llmctl.instance': identity['instance'],
                'io.llmctl.deployment': identity['deployment']}}, 'State': {'Running': True}}
        self.manager._slots_envelope = {'slots': {
            target: {'selected': profiles[target], 'container': None},
            peer: {'selected': profiles[peer], 'container': identity}}}
        self.manager._slot_target = target
        self.manager.deployment = Mock(side_effect=lambda name: self.deployments[name])
        self.manager.network_check = Mock()
        self.manager.validate_reused_contract = Mock()
        self.manager.docker = Mock(spec=['inspect', 'inventory'])
        self.manager.docker.inventory.return_value = [copy.deepcopy(text_peer), copy.deepcopy(self.candidate)]
        self.manager.docker.inspect.side_effect = lambda name: copy.deepcopy(
            text_peer if name == identity['id'] else self.fresh if name == CID else None)
        return self.deployments[profiles[target]], text_peer

    def test_conflict_check_admits_registered_image_for_both_qwen_slots(self):
        for target in ('glm', 'qwen'):
            with self.subTest(target=target):
                deployment, text_peer = self.integration(target)
                before = copy.deepcopy(self.manager._slots_envelope)
                self.manager.conflict_check(deployment=deployment)
                self.assertEqual(self.manager._slots_envelope, before)
                self.manager.network_check.assert_called_once_with(text_peer, self.deployments[
                    pair.QWEN_PROFILE if target == 'glm' else pair.QWEN0_PROFILE])
                self.manager.validate_reused_contract.assert_called_once()
                self.assertTrue(all(call[0] in ('inventory', 'inspect') for call in self.manager.docker.mock_calls))
                self.manager.persistent_json.assert_not_called()
                self.manager.sglang_probe.assert_not_called()

    def test_valid_image_does_not_admit_another_unknown_gpu_peer(self):
        deployment, _ = self.integration('glm')
        foreign = copy.deepcopy(self.candidate)
        foreign.update(Id='d' * 64, Name='/foreign-gpu-owner')
        self.manager.docker.inventory.return_value.append(foreign)
        with self.assertRaisesRegex(LifecycleError, '^untrusted_concurrent_peer$'):
            self.manager.conflict_check(deployment=deployment)

    def test_no_image_and_singleton_do_not_require_image_proof(self):
        deployment, _ = self.integration('glm')
        self.manager.docker.inventory.return_value.pop()
        self.manager.conflict_check(deployment=deployment)
        self.assertNotIn(((CID,), {}), self.manager.docker.inspect.call_args_list)
        self.manager._slots_envelope = None
        self.manager.docker.inventory.return_value = [copy.deepcopy(self.candidate)]
        self.manager.conflict_check(deployment=deployment)
        self.assertNotIn(((CID,), {}), self.manager.docker.inspect.call_args_list)
        self.forbidden_reader.assert_not_called()


if __name__ == '__main__':
    unittest.main()
