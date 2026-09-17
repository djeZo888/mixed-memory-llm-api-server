"""Production adapter over actual L1 Manager and actual localhost HTTP.

Synthetic resources: temporary one-byte artifact, inert disposable key, profile
and acquisition evidence, Linux storage discovery, Docker inspect inventory and
API probe results. Real behavior: Python adapter/Manager, canonical OS flock,
I1R package admission, fsynced temporary fixture files, TCP sockets and HTTP server.
HTTP tests use the actual MountedStorageGuard/AnchoredRoot writer with explicit
worker discovery, mountinfo and uid seams. No lifecycle forwarding is replaced.
This is worker-only evidence, not installed systemd, real image execution,
mount detach, GPU/inference, two-model acceptance or whole-install acceptance.
"""
from __future__ import annotations

import copy
from functools import partial
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import select
import shutil
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import call, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'tests/lifecycle'))
sys.path.insert(0, str(ROOT / 'scripts'))
from common.lifecycle_lease import acquire_lease, transition_in_progress, LeaseBusy, LeaseError
from control.adapter import ProductionBackend, ManagerJournalStore
from control.core import Application
from control.http import make_server
from control.journal import Journal
from control.protocol import ControlError, Deadline, StorageUnavailable
from install import prerequisites
from lifecycle.manager import Manager
from lifecycle.runtime_io import LifecycleError
from test_manager import FakeDocker, IMAGE
from test_real_storage_io import LocalStorageFixture
from test_control_journal import FixtureAtomicJSONStore

REAL_ADMISSION = prerequisites.assert_package_admission
OLD = 'fixture-old'
TARGET = 'fixture-target'
MODEL = 'fixture-model'


class ControlledDocker(FakeDocker):
    def __init__(self, fixture):
        super().__init__()
        self.fixture = fixture
        self.target_fault = None
        self.start_serial = 0
        self.max_running = 0
        self.entered = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.on_mutation = None
        self.lock_events = []

    def _event(self, event):
        held = transition_in_progress(system_root=self.fixture.base, trusted_uid=os.geteuid())
        self.lock_events.append((event, held, threading.current_thread().name))
        if event[0] in {'stop', 'remove', 'create', 'start_enter'} and self.on_mutation:
            self.on_mutation(event)
        super()._event(event)

    def run(self, args, timeout=30):
        if args[0] == 'info':
            self._event(('run', tuple(args)))
            return self.fixture.binding.path('data', 'docker') + '\n'
        if args[:2] == ['image', 'inspect']:
            self._event(('run', tuple(args)))
            target = args[-1] == 'local/fixture:target'
            if target and self.target_fault == 'missing':
                raise LifecycleError('command_failed')
            ident = 'sha256:' + 'c' * 64 if target and self.target_fault == 'mismatch' else IMAGE
            entrypoint = ['/wrong/entrypoint'] if target and self.target_fault == 'entrypoint' else ['/opt/llama/llama-server']
            return json.dumps([{'Id': ident, 'Config': {'Entrypoint': entrypoint}}])
        return super().run(args, timeout=timeout)

    def start(self, identity):
        super().start(identity)
        self.start_serial += 1
        records = self._read()
        record = next(item for item in records if item['Id'] == identity)
        record['State']['StartedAt'] = f'2026-09-15T00:00:{self.start_serial:02d}.000000000Z'
        self._write(records)
        self.max_running = max(self.max_running, sum(item['State']['Running'] for item in records))

    def stop(self, identity, timeout=120):
        started = next(item for item in self._read() if item['Id'] == identity)['State'].get('StartedAt')
        super().stop(identity, timeout=timeout)
        records = self._read()
        next(item for item in records if item['Id'] == identity)['State']['StartedAt'] = started
        self._write(records)


class ControlledWriter:
    """Worker-only writer; does not establish I1W mount-loss/race safety."""
    def __init__(self, fixture):
        self.MountedStorageGuard = fixture.mounted_guard

    class AnchoredRoot:
        def __init__(self, path, guard):
            self.path, self.guard = Path(path), guard

        def __enter__(self):
            self.guard()
            return self

        def __exit__(self, *args):
            return False

        def mkdir(self, relative, mode=0o700, parents=True):
            self.guard()
            target = self.path / relative
            target.mkdir(mode=mode, parents=parents, exist_ok=True)
            # FixtureAtomicJSONStore requires a private fixture directory.
            target.chmod(0o700)

        def atomic_json(self, relative, value):
            self.guard()
            FixtureAtomicJSONStore(self.path / relative, expected_uid=os.geteuid()).write(value)
            self.guard()

        def check(self):
            self.guard()


class ActualManagerFixture:
    """Only constructor-owned host I/O is injected; no Manager method override."""
    def __init__(self, *, actual_writer=True):
        self.storage = LocalStorageFixture()
        self.writer = self.storage.api if actual_writer else ControlledWriter(self.storage)
        self.base = self.storage.base
        self.configs = self.base / 'reviewed-source/configs'
        self.instance = copy.deepcopy(self.storage.instance)
        self.instance.update(obsolete_boot_owner_disabled=True,
                             obsolete_boot_owner_evidence='synthetic-reviewed-removal')
        self.instance['runtime_evidence'] = {}
        self.instance['model_integrity'] = {}
        self.profile_reads = []
        self.probe_result = 'ready'
        self.probes = []
        self.managers = []
        self.host_commands = []
        self.docker = ControlledDocker(self.storage)
        self.policy = self.base / 'policy-rc.d'
        self._profiles()

    def write_json(self, path, value):
        return self.storage.jsonfile(path, value)

    def _profiles(self):
        model = {'schema_version': 1, 'id': MODEL, 'repo_id': 'Fixture/GenericModel',
                 'display_name': 'Synthetic generic model', 'revision': 'a' * 40,
                 'quantization': 'synthetic', 'model_root': {'role': 'models', 'suffix': MODEL},
                 'load_entry': 'fixture.bin', 'artifact_count': 1, 'total_bytes': 1,
                 'artifacts': [{'path': 'fixture.bin', 'size_bytes': 1,
                                'sha256': hashlib.sha256(b'x').hexdigest()}]}
        self.write_json(self.configs / 'models' / (MODEL + '.json'), model)
        completion = self.storage.binding.path('data', 'services/llm-manager/acquisition/' + MODEL + '.complete.json')
        receipt = {'schema_version': 1, 'complete': True, 'repo_id': model['repo_id'],
                   'revision': model['revision'], 'model_root': self.storage.binding.path('models', MODEL),
                   'artifact_count': 1, 'total_bytes': 1,
                   'artifacts': [dict(model['artifacts'][0], verified=True)]}
        self.write_json(completion, receipt)
        self.completion_path = Path(completion)
        self.instance['model_integrity'][MODEL] = {
            'verified': True, 'revision': model['revision'],
            'evidence': ['synthetic-acquisition'], 'completion_manifest': completion}
        template = json.loads((ROOT / 'configs/deployments/glm-5.3-ud-q4-k-xl-8k.json').read_text())
        runtime = json.loads((ROOT / 'configs/runtimes/llama-cpp-v0.4.1-d1.json').read_text())
        for deployment_id, tag, port in [(OLD, 'old', 30101), (TARGET, 'target', 30109)]:
            runtime_id = 'fixture-runtime-' + tag
            rt = copy.deepcopy(runtime)
            rt.update(id=runtime_id, image_tag='local/fixture:' + tag)
            self.write_json(self.configs / 'runtimes' / (runtime_id + '.json'), rt)
            self.instance['runtime_evidence'][runtime_id] = {
                'image_id': IMAGE, 'flags_verified': True, 'evidence': ['synthetic-image'],
                'supported_flags': rt['required_cli_flags'], 'load_mode': 'mmap'}
            profile = copy.deepcopy(template)
            profile.update(id=deployment_id, model=MODEL, runtime=runtime_id,
                           container_name='llmctl-' + deployment_id)
            profile['endpoint'].update(port=port, served_model=deployment_id + '-alias')
            profile['container_port'] = port
            profile['launch'].update(timeout_seconds=2, poll_seconds=1, request_timeout_seconds=1)
            suffixes = {'model': ('models', MODEL), 'cache': ('models', 'runtime-cache/' + runtime_id),
                        'logs': ('data', 'logs/llmctl/' + deployment_id),
                        'service': ('data', 'services/llm-manager/' + deployment_id)}
            for role, (storage_role, suffix) in suffixes.items():
                profile['paths'][role] = {'role': storage_role, 'suffix': suffix}
            for mount in profile['mounts']:
                role = {'/models': 'model', '/cache': 'cache', '/logs': 'logs', '/service': 'service'}.get(mount['target'])
                if role:
                    mount['source'] = copy.deepcopy(profile['paths'][role])
                    Path(self.storage.binding.path(mount['source']['role'], mount['source']['suffix'])).mkdir(parents=True, exist_ok=True)
            self.write_json(self.configs / 'deployments' / (deployment_id + '.json'), profile)
        artifact = Path(self.storage.binding.path('models', MODEL + '/fixture.bin'))
        artifact.write_bytes(b'x')
        artifact.chmod(0o600)
        self.artifact_path = artifact
        key = Path(self.storage.binding.path('data', 'services/secrets/llm-api-key'))
        key.write_bytes(b'inert-disposable-inference-fixture-credential')
        key.chmod(0o600)

    def host_run(self, args, **kwargs):
        self.host_commands.append((tuple(args), kwargs))
        if args[-1] == '--root-guard':
            return '{"status":"synthetic-pass"}'
        if args[0].endswith('/require-data-mounted.sh'):
            return ''
        raise AssertionError('uncontrolled external command')

    def probe(self, endpoint, model, key_file, **kwargs):
        self.probes.append((endpoint, model, kwargs))
        return self.probe_result

    def load(self, args=None, config=None):
        self.storage.binding.verify()
        manager = Manager(self.configs, self.instance, binding=self.storage.binding,
                          storage_io=self.writer, test_paths=True,
                          lease_system_root=self.base, docker=self.docker,
                          run_fn=self.host_run, probe_fn=self.probe)
        self.managers.append(manager)
        return manager

    def recovery(self, *, config=None):
        # The fixture reader protects the synthetic /run directory and file.
        # Root-owned ancestry is installed-host evidence, not available on this
        # ordinary-user worker. Actual Manager validates recovery state/identity.
        state = FixtureAtomicJSONStore(self.base / 'run/llmctl/recovery.json', expected_uid=os.geteuid()).read()
        manager = Manager(self.base / 'absent-config',
                          {'schema_version': 1, 'id': state['container']['instance']},
                          docker=self.docker, recovery_only=True, test_paths=True,
                          lease_system_root=self.base)
        self.managers.append(manager)
        return manager

    def lease(self, **kwargs):
        return acquire_lease(system_root=self.base, trusted_uid=os.geteuid(), **kwargs)

    def close(self):
        self.docker.release.set()
        self.storage.close()


def recovery_http_child(root):
    """Test-only subprocess entrypoint; never exposed by control/serve.py.

    It executes production adapter/core/HTTP and actual recovery-only Manager.
    Only Docker resources, /run file ownership root and unavailable normal
    loader are controlled. This does not test the installed service entrypoint.
    """
    root = Path(root).resolve()
    events = root / 'run/llmctl/docker-events.json'
    inventory = root / 'run/llmctl/docker-inventory.json'

    class RecoveryDocker(FakeDocker):
        def _event(self, event):
            if event[0] in {'stop', 'create', 'start_enter', 'remove'}:
                if event[0] != 'stop':
                    raise AssertionError('recovery attempted forbidden Docker mutation')
                prior = FixtureAtomicJSONStore(events, expected_uid=os.geteuid()).read() or []
                prior.append({'event': event[0], 'id': event[1],
                              'lease_held': transition_in_progress(system_root=root, trusted_uid=os.geteuid())})
                FixtureAtomicJSONStore(events, expected_uid=os.geteuid()).write(prior)
            super()._event(event)

        def run(self, args, timeout=30):
            raise AssertionError('recovery attempted image or runtime access')

    def normal_unavailable(*args, **kwargs):
        raise StorageUnavailable()

    def load_recovery(*, config=None):
        saved = FixtureAtomicJSONStore(root / 'run/llmctl/recovery.json', expected_uid=os.geteuid()).read()
        return Manager(root / 'absent-config',
                       {'schema_version': 1, 'id': saved['container']['instance']},
                       docker=RecoveryDocker(path=inventory), recovery_only=True,
                       test_paths=True, lease_system_root=root)

    key = (root / 'etc/llm-server/control-api-key').read_bytes()
    backend = ProductionBackend(root / 'absent-config', manager_loader=normal_unavailable,
                                recovery_loader=load_recovery, control_key=key)
    application = Application(backend, Journal(ManagerJournalStore(normal_unavailable)),
                              lease_factory=partial(acquire_lease, system_root=root, trusted_uid=os.geteuid()),
                              transition_seconds=10, admission_seconds=2, read_seconds=2)
    server = make_server(application, key, port=0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    thread.start()
    try:
        print(json.dumps({'port': server.server_address[1], 'pid': os.getpid(), 'cwd': os.getcwd()}), flush=True)
        if sys.stdin.readline() != 'shutdown\n':
            return 3
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
        if not application.close():
            raise RuntimeError('recovery fixture executor did not close')
    return 0


class ActualWriterIntegrationTests(unittest.TestCase):
    def test_reviewed_l1_i1w_path_verifier_forwarding(self):
        """Execute the received L1 forwarding over the actual anchored writer."""
        fixture = ActualManagerFixture(actual_writer=True)
        self.addCleanup(fixture.close)
        manager = fixture.load()
        with fixture.lease() as lease:
            manager.persistent_json(fixture.storage.binding.path('data', 'logs/control-l1b-seam.json'),
                                    {'schema_version': 1, 'synthetic': True})
            lease.validate()
        self.assertTrue((Path(fixture.storage.data) / 'logs/control-l1b-seam.json').is_file())


class ManagerObservationReuseTests(unittest.TestCase):
    """Read-only observations over the existing synthetic Manager resources."""
    def setUp(self):
        self.fixture = ActualManagerFixture()
        self.addCleanup(self.fixture.close)
        with patch.object(prerequisites, 'assert_package_admission',
                          side_effect=partial(REAL_ADMISSION, policy_path=self.fixture.policy)):
            manager = self.fixture.load()
            with self.fixture.lease() as lease:
                manager.dispatch('select', OLD, boot_policy='resume', lease=lease)
                manager.dispatch('start', lease=lease)
        self.session = ProductionBackend(
            self.fixture.configs, manager_loader=self.fixture.load,
            control_key=b'inert-disposable-control-fixture-credential').open()
        self.fixture.docker.calls.clear()

    def test_equal_id_reuses_success_only_within_each_observation(self):
        manager = self.session.manager
        with (patch.object(manager, 'deployment', wraps=manager.deployment) as resolve,
              patch.object(manager, 'validate_deployment', wraps=manager.validate_deployment) as validate,
              patch.object(manager, 'check_mounts', wraps=manager.check_mounts) as mounts,
              patch.object(manager, 'trusted_container', wraps=manager.trusted_container) as identity,
              patch.object(self.session, '_separate_key', wraps=self.session._separate_key) as keys,
              patch.object(manager, 'network_check', wraps=manager.network_check) as network,
              patch.object(manager, 'validate_reused_contract', wraps=manager.validate_reused_contract) as contract,
              patch.object(manager, 'probe_deployment', wraps=manager.probe_deployment) as probe):
            ready = self.session.observe(Deadline.after(5))
            self.assertEqual(ready['observed'], 'ready')
            self.assertEqual(ready['ready_proof'], dict.fromkeys((
                'trusted_identity', 'safe_network', 'authenticated_model', 'runtime_health'), True))
            self.fixture.probe_result = 'not_ready'
            current = self.session.observe(Deadline.after(5))
            self.assertEqual(current['observed'], 'unhealthy')
            self.assertFalse(any(current['ready_proof'].values()))
        self.assertEqual(resolve.call_args_list, [call(OLD), call(OLD)])
        # Contract validation is still separate and repeated on every read.
        self.assertEqual(validate.call_count, 4)
        self.assertEqual((mounts.call_count, identity.call_count), (6, 4))
        self.assertEqual((keys.call_count, network.call_count, contract.call_count, probe.call_count), (2, 2, 2, 2))
        for index in range(2):
            deployment = keys.call_args_list[index].args[0]
            self.assertIs(network.call_args_list[index].args[1], deployment)
            self.assertIs(contract.call_args_list[index].args[1], deployment)
            self.assertIs(probe.call_args_list[index].args[0], deployment)
        self.assertIsNot(keys.call_args_list[0].args[0], keys.call_args_list[1].args[0])
        self.assertTrue(all(probe[2]['require_auth'] for probe in self.fixture.probes))
        self.assertFalse(any(event[0] in {'stop', 'remove', 'create', 'start_enter'}
                             for event in self.fixture.docker.calls))

    def test_different_selected_id_resolves_active_deployment_separately(self):
        manager = self.session.manager
        state = manager.read_state()
        # L1 rejects mismatched persisted state; exercise this adapter branch
        # through an explicit in-process observation seam only.
        with (patch.object(manager, 'read_state', return_value=dict(state, selected=TARGET)),
              patch.object(manager, 'deployment', wraps=manager.deployment) as resolve,
              patch.object(manager, 'probe_deployment', wraps=manager.probe_deployment) as probe):
            observation = self.session.observe(Deadline.after(5))
        self.assertEqual(resolve.call_args_list, [call(TARGET), call(OLD)])
        self.assertEqual(observation['observed'], 'ready')
        self.assertEqual(observation['endpoint']['served_model'], TARGET + '-alias')
        self.assertEqual(probe.call_args.args[0]['id'], OLD)

    def test_failed_selected_resolution_preserves_active_retry_and_error(self):
        manager = self.session.manager
        original = manager.deployment
        for retry_succeeds in (True, False):
            with self.subTest(retry_succeeds=retry_succeeds):
                attempts = []
                def resolve(identifier):
                    attempts.append(identifier)
                    if len(attempts) == 1 or not retry_succeeds:
                        raise LifecycleError('synthetic_selected_unavailable')
                    return original(identifier)
                with patch.object(manager, 'deployment', side_effect=resolve):
                    observation = self.session.observe(Deadline.after(5))
                self.assertEqual(attempts, [OLD, OLD])
                self.assertEqual(observation['observed'], 'ready' if retry_succeeds else 'unhealthy')
                self.assertIsNone(observation['endpoint'])
                self.assertIsNone(observation['model_id'])
                self.assertEqual(bool(observation['ready_proof']), retry_succeeds)

    def test_equal_id_still_rechecks_storage_identity_and_health_after_probe(self):
        baseline = copy.deepcopy(self.fixture.docker.records)
        original = self.session.manager.probe_deployment
        for change in ('storage', 'generation', 'health'):
            with self.subTest(change=change):
                self.fixture.docker.records = copy.deepcopy(baseline)
                self.fixture.storage.lost = False
                def probe(deployment, timeout):
                    result = original(deployment, timeout)
                    if change == 'storage':
                        self.fixture.storage.lost = True
                    elif change == 'generation':
                        self.fixture.docker.records[0]['State']['StartedAt'] = '2026-09-17T00:00:00Z'
                    else:
                        self.fixture.docker.records[0]['State']['Health'] = {'Status': 'unhealthy'}
                    return result
                with patch.object(self.session.manager, 'probe_deployment', side_effect=probe):
                    if change == 'storage':
                        with self.assertRaises(StorageUnavailable):
                            self.session.observe(Deadline.after(5))
                    else:
                        observation = self.session.observe(Deadline.after(5))
                        self.assertEqual(observation['observed'], 'unhealthy')
                        self.assertFalse(any(observation['ready_proof'].values()))


class ProductionHTTPTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ActualManagerFixture()
        self.addCleanup(self.fixture.close)
        self.admission_patch = patch.object(prerequisites, 'assert_package_admission',
                                          side_effect=partial(REAL_ADMISSION, policy_path=self.fixture.policy))
        self.actual_admission = self.admission_patch.start()
        self.addCleanup(self.admission_patch.stop)
        self.key = secrets.token_urlsafe(36).encode('ascii')
        self.app = None
        self.server = None
        self.thread = None
        self.addCleanup(self.close_service)
        manager = self.fixture.load()
        with self.fixture.lease() as lease:
            manager.dispatch('select', OLD, boot_policy='resume', lease=lease)
            manager.dispatch('start', lease=lease)
        self.old_identity = manager.state['container']['id']
        self.fixture.docker.calls.clear()
        self.fixture.docker.lock_events.clear()
        self.fixture.docker.entered.clear()
        self.start_service()

    def start_service(self):
        backend = ProductionBackend(self.fixture.configs, manager_loader=self.fixture.load,
                                    recovery_loader=self.fixture.recovery, control_key=self.key)
        self.store = ManagerJournalStore(self.fixture.load)
        self.app = Application(backend, Journal(self.store), lease_factory=self.fixture.lease,
                               transition_seconds=10, admission_seconds=2, read_seconds=2)
        self.server = make_server(self.app, self.key, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.01}, daemon=True)
        self.thread.start()
        self.address = self.server.server_address

    def close_service(self):
        self.fixture.docker.release.set()
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(2)
            self.server = None
        if self.app:
            deadline = time.monotonic() + 5
            while not self.app.close() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertFalse(self.app._worker.is_alive(), 'lifecycle executor did not terminate')
            self.app = None

    def request(self, method='GET', path='/control/v1/status', payload=None, key=None, auth=True):
        headers = {'Content-Type': 'application/json'}
        if auth:
            headers['Authorization'] = 'Bearer ' + self.key.decode('ascii')
        if key:
            headers['Idempotency-Key'] = key
        body = None if payload is None else json.dumps(payload)
        connection = http.client.HTTPConnection(*self.address, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            data = response.read()
            self.assertNotIn(self.key, data)
            self.assertNotIn(str(self.fixture.base).encode(), data)
            return response.status, json.loads(data)
        finally:
            connection.close()

    def snapshot(self):
        status, data = self.request()
        self.assertEqual(status, 200, data)
        return data

    def body(self, snapshot=None, *, switch=False):
        snapshot = snapshot or self.snapshot()
        result = {'expected_active': snapshot['active_identity'],
                  'expected_generation': snapshot['generation']}
        if switch:
            result.update(deployment_id=TARGET, allow_interrupt=True)
        return result

    def finish(self, receipt):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            code, operation = self.request(path=receipt['operation']['poll_url'])
            self.assertEqual(code, 200, operation)
            if operation['status'] in {'succeeded', 'failed', 'interrupted'}:
                return operation
            time.sleep(0.01)
        self.fail('operation deadline exceeded')

    def mutations(self):
        return [item for item in self.fixture.docker.calls if item[0] in {'stop', 'remove', 'create', 'start_enter'}]

    def assert_intent(self, selected, desired, boot_policy):
        state = self.fixture.load().read_state()
        self.assertEqual((state['selected'], state['desired'], state['boot_policy']),
                         (selected, desired, boot_policy))
        self.assertTrue(state['state_persisted'])
        return state

    def test_every_route_authenticates_before_actual_owner_io(self):
        before = len(self.fixture.managers)
        for method, path in [('GET', '/control/v1/status'), ('GET', '/control/v1/catalog'),
                             ('GET', '/control/v1/operations/' + 'a' * 32),
                             ('POST', '/control/v1/switch'), ('POST', '/control/v1/stop'),
                             ('GET', '/unknown')]:
            with self.subTest(method=method, path=path):
                status, result = self.request(method, path, {} if method == 'POST' else None, auth=False)
                self.assertEqual((status, result), (401, {'error': {'code': 'unauthorized'}}))
        self.assertEqual(len(self.fixture.managers), before)
        self.assertEqual(self.mutations(), [])

    def test_real_observed_readiness_and_server_relative_discovery_no_weight_read(self):
        original = Path.open
        def bounded_open(path, *args, **kwargs):
            if path == self.fixture.artifact_path:
                raise AssertionError('catalog or status read model artifact')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', bounded_open):
            status, catalog = self.request(path='/control/v1/catalog')
        self.assertEqual(status, 200, catalog)
        self.assertEqual({entry['deployment_id'] for entry in catalog['entries']}, {OLD, TARGET})
        self.assertEqual(catalog['observed'], 'ready')
        entry = next(item for item in catalog['entries'] if item['deployment_id'] == OLD)
        self.assertTrue(entry['endpoint']['server_relative'])
        self.assertEqual(entry['endpoint']['base_url'], 'http://127.0.0.1:30101/v1')
        self.assertTrue(entry['endpoint']['ready'])
        self.assertEqual(entry['capabilities']['tool_calling']['status'], 'unknown')
        self.fixture.probe_result = 'not_ready'
        self.assertNotEqual(self.snapshot()['observed'], 'ready')
        self.assertEqual(self.mutations(), [])

    def test_actual_missing_mismatched_image_or_entrypoint_never_stops_old(self):
        for fault in ('missing', 'mismatch', 'entrypoint'):
            with self.subTest(fault=fault):
                self.fixture.docker.target_fault = fault
                status, receipt = self.request('POST', '/control/v1/switch', self.body(switch=True), 'preflight-' + fault)
                self.assertEqual(status, 202, receipt)
                operation = self.finish(receipt)
                self.assertEqual(operation['status'], 'failed', operation)
                self.assertEqual(self.mutations(), [], 'target preflight stopped or replaced the old container')
                self.assertTrue(next(item for item in self.fixture.docker.records if item['Id'] == self.old_identity)['State']['Running'])
                self.assert_intent(OLD, 'running', 'resume')
                inspections = [event for event, held, thread in self.fixture.docker.lock_events
                               if event == ('run', ('image', 'inspect', 'local/fixture:target')) and held
                               and thread == 'control-transition']
                self.assertTrue(inspections, 'actual target image preflight was not reached under canonical lease')

    def test_cas_and_interrupt_ack_reject_before_destructive_work(self):
        body = self.body(switch=True)
        for change, expected in [({'expected_generation': body['expected_generation'] + 1}, 'stale_state'),
                                 ({'expected_active': '0' * 64}, 'stale_state'),
                                 ({'allow_interrupt': False}, 'interruption_ack_required')]:
            with self.subTest(expected=expected):
                status, result = self.request('POST', '/control/v1/switch', dict(body, **change), 'reject-' + expected + str(len(change)))
                self.assertEqual(status, 409, result)
                self.assertEqual(result['error']['code'], expected)
                self.assert_intent(OLD, 'running', 'resume')
        self.assertEqual(self.mutations(), [])

    def test_switch_borrows_one_lease_and_admits_durably_before_first_stop(self):
        body = self.body(switch=True)
        receipts_at_stop = []
        def durable_before_mutation(event):
            self.assertTrue(transition_in_progress(system_root=self.fixture.base, trusted_uid=os.geteuid()))
            state = self.store.read()
            receipts_at_stop.append(copy.deepcopy(state))
            self.assertEqual(len(state['entries']), 1)
            self.assertIn(next(iter(state['entries'].values()))['status'], {'pending', 'running'})
        self.fixture.docker.on_mutation = durable_before_mutation
        status, receipt = self.request('POST', '/control/v1/switch', body, 'switch-success')
        self.assertEqual(status, 202, receipt)
        self.assertTrue(receipt['state_persisted'])
        operation = self.finish(receipt)
        self.assertEqual(operation['status'], 'succeeded', operation)
        selected = self.assert_intent(TARGET, 'running', 'resume')
        self.assertTrue(receipts_at_stop)
        self.assertEqual(self.fixture.docker.max_running, 1)
        self.assertEqual([item for item in self.mutations() if item[0] == 'stop'], [('stop', self.old_identity)])
        self.assertTrue(all(held and thread == 'control-transition' for event, held, thread in self.fixture.docker.lock_events
                            if event[0] in {'stop', 'remove', 'create', 'start_enter'}))
        status, discovery = self.request(path='/control/v1/catalog')
        target = next(item for item in discovery['entries'] if item['deployment_id'] == TARGET)
        self.assertTrue(target['endpoint']['ready'])
        self.assertEqual(target['endpoint']['base_url'], 'http://127.0.0.1:30109/v1')
        self.assertGreater(discovery['generation'], body['expected_generation'])

        # Exercise real boot intent, not just the saved preference field.
        self.fixture.docker.on_mutation = None
        self.fixture.docker.calls.clear()
        self.fixture.docker.lock_events.clear()
        with self.fixture.lease() as lease:
            self.fixture.load().dispatch('boot-stop', lease=lease)
            stopped = self.assert_intent(TARGET, 'running', 'resume')
            self.assertFalse(stopped['container_running'])
            self.fixture.load().dispatch('boot-start', lease=lease)
            self.fixture.load().dispatch('boot-start', lease=lease)
            lease.validate()
        resumed = self.assert_intent(TARGET, 'running', 'resume')
        self.assertTrue(resumed['container_running'])
        self.assertEqual(resumed['container']['id'], selected['container']['id'])
        self.assertEqual([item for item in self.mutations() if item[0] == 'start_enter'],
                         [('start_enter', selected['container']['id'])])
        self.assertTrue(all(held for event, held, _ in self.fixture.docker.lock_events
                            if event[0] in {'stop', 'remove', 'create', 'start_enter'}))
        self.assertEqual(self.fixture.docker.max_running, 1)

    def test_manual_switch_preserves_manual_and_boot_start_does_not_start(self):
        manager = self.fixture.load()
        with self.fixture.lease() as lease:
            manager.dispatch('stop', lease=lease)
            manager.dispatch('select', OLD, boot_policy='manual', lease=lease)
            manager.dispatch('start', lease=lease)
        self.fixture.docker.calls.clear()
        self.assert_intent(OLD, 'running', 'manual')
        status, receipt = self.request('POST', '/control/v1/switch', self.body(switch=True), 'manual-switch')
        self.assertEqual(status, 202, receipt)
        self.assertEqual(self.finish(receipt)['status'], 'succeeded')
        selected = self.assert_intent(TARGET, 'running', 'manual')
        self.assertTrue(selected['container_running'])
        self.assertEqual([item for item in self.mutations() if item[0] == 'start_enter'],
                         [('start_enter', selected['container']['id'])])
        self.fixture.docker.calls.clear()
        with self.fixture.lease() as lease:
            self.fixture.load().dispatch('boot-stop', lease=lease)
            self.fixture.load().dispatch('boot-start', lease=lease)
            self.fixture.load().dispatch('boot-start', lease=lease)
        stopped = self.assert_intent(TARGET, 'running', 'manual')
        self.assertFalse(stopped['container_running'])
        self.assertFalse(any(item[0] == 'start_enter' for item in self.mutations()))
        self.assertEqual(self.fixture.docker.max_running, 1)

    def test_switch_replay_and_idempotency_conflict_preserve_boot_intent(self):
        body = self.body(switch=True)
        status, receipt = self.request('POST', '/control/v1/switch', body, 'switch-replay')
        self.assertEqual(status, 202, receipt)
        self.assertEqual(self.finish(receipt)['status'], 'succeeded')
        selected = self.assert_intent(TARGET, 'running', 'resume')
        mutations = self.mutations()
        status, replay = self.request('POST', '/control/v1/switch', body, 'switch-replay')
        self.assertEqual(status, 202, replay)
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['operation']['id'], receipt['operation']['id'])
        status, refused = self.request('POST', '/control/v1/switch',
                                       dict(body, deployment_id=OLD), 'switch-replay')
        self.assertEqual((status, refused['error']['code']), (409, 'idempotency_conflict'))
        self.assertEqual(self.assert_intent(TARGET, 'running', 'resume'), selected)
        self.assertEqual(self.mutations(), mutations)

    def test_select_reads_current_policy_over_stale_manager_and_observation(self):
        backend = ProductionBackend(self.fixture.configs, manager_loader=self.fixture.load)
        for prior, current in [('manual', 'resume'), ('resume', 'manual')]:
            with self.subTest(prior=prior, current=current):
                session = backend.open()
                with self.fixture.lease() as lease:
                    session.manager.dispatch('stop', lease=lease)
                    session.manager.dispatch('select', OLD, boot_policy=prior, lease=lease)
                    observation = session.observe(Deadline.after(5))
                    self.fixture.load().dispatch('select', OLD, boot_policy=current, lease=lease)
                    self.assertEqual(session.manager.state['boot_policy'], prior)
                    self.assertEqual(observation['boot_policy'], prior)
                    session.select(TARGET, lease, Deadline.after(5))
                    lease.validate()
                self.assert_intent(TARGET, 'stopped', current)

    def test_select_refuses_invalid_or_unreadable_current_state_without_mutation(self):
        session = ProductionBackend(self.fixture.configs, manager_loader=self.fixture.load).open()
        path = session.manager.state_file
        original = path.read_bytes()
        state = json.loads(original)
        with self.fixture.lease() as lease:
            for value in (None, True, 1, [], {}, 'automatic'):
                with self.subTest(boot_policy=value):
                    self.fixture.write_json(path, dict(state, boot_policy=value))
                    invalid = path.read_bytes()
                    with self.assertRaisesRegex(LifecycleError, '^invalid_state$'):
                        session.select(TARGET, lease, Deadline.after(5))
                    self.assertEqual(path.read_bytes(), invalid)
                    self.assertEqual(self.mutations(), [])
            missing = dict(state)
            missing.pop('boot_policy')
            self.fixture.write_json(path, missing)
            with self.assertRaisesRegex(LifecycleError, '^invalid_state$'):
                session.select(TARGET, lease, Deadline.after(5))
            path.unlink()
            path.mkdir(mode=0o700)
            try:
                with self.assertRaisesRegex(LifecycleError, '^invalid_or_missing_json$'):
                    session.select(TARGET, lease, Deadline.after(5))
                self.assertTrue(path.is_dir())
                self.assertEqual(self.mutations(), [])
                lease.validate()
            finally:
                path.rmdir()
                path.write_bytes(original)
                path.chmod(0o600)
        self.assert_intent(OLD, 'running', 'resume')

    def test_select_refuses_wrong_or_stale_lease_before_storage_or_docker_io(self):
        session = ProductionBackend(self.fixture.configs, manager_loader=self.fixture.load).open()
        with self.fixture.lease() as stale:
            pass
        foreign = self.fixture.base / 'foreign-owner'
        foreign.mkdir(mode=0o700)
        with acquire_lease(system_root=foreign, trusted_uid=os.geteuid()) as wrong:
            for lease, expected in [(wrong, 'borrowed_lease_scope_mismatch'),
                                    (stale, 'lease_not_active'), (None, 'invalid_borrowed_lease')]:
                with self.subTest(expected=expected):
                    checks = self.fixture.storage.full_checks
                    calls = list(self.fixture.docker.calls)
                    with self.assertRaisesRegex(LeaseError, '^' + expected + '$'):
                        session.select(TARGET, lease, Deadline.after(5))
                    self.assertEqual(self.fixture.storage.full_checks, checks)
                    self.assertEqual(self.fixture.docker.calls, calls)
        self.assert_intent(OLD, 'running', 'resume')

    def test_select_expired_deadline_refuses_before_storage_or_docker_io(self):
        session = ProductionBackend(self.fixture.configs, manager_loader=self.fixture.load).open()
        with self.fixture.lease() as lease:
            checks = self.fixture.storage.full_checks
            calls = list(self.fixture.docker.calls)
            with self.assertRaisesRegex(ControlError, '^deadline_exceeded$'):
                session.select(TARGET, lease, Deadline.after(-1))
            lease.validate()
            self.assertEqual(self.fixture.storage.full_checks, checks)
            self.assertEqual(self.fixture.docker.calls, calls)
        self.assert_intent(OLD, 'running', 'resume')

    def test_external_canonical_lease_conflicts_without_queue(self):
        body = self.body(switch=True)
        program = '''import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from common.lifecycle_lease import acquire_lease
with acquire_lease(system_root=Path(sys.argv[2]),trusted_uid=os.geteuid()):
 print('held',flush=True)
 sys.stdin.readline()
'''
        owner = subprocess.Popen([sys.executable, '-I', '-B', '-c', program,
                                  str(ROOT / 'scripts'), str(self.fixture.base)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(owner.stdout.readline().strip(), 'held')
            start = time.monotonic()
            status, result = self.request('POST', '/control/v1/switch', body, 'external-owner')
            self.assertLess(time.monotonic() - start, 1)
            self.assertEqual((status, result['error']['code']), (409, 'lifecycle_busy'))
        finally:
            owner.communicate('release\n', timeout=5)
            self.assertEqual(owner.returncode, 0)
        self.assertEqual(self.mutations(), [])

    def test_loading_status_responsive_second_mutation_conflicts(self):
        self.fixture.docker.release.clear()
        status, receipt = self.request('POST', '/control/v1/switch', self.body(switch=True), 'loading-one')
        self.assertEqual(status, 202, receipt)
        self.assertTrue(self.fixture.docker.entered.wait(3))
        start = time.monotonic()
        loading = self.snapshot()
        self.assertLess(time.monotonic() - start, 2)
        self.assertEqual(loading['observed'], 'loading')
        status, result = self.request('POST', '/control/v1/stop', self.body(loading), 'loading-conflict')
        self.assertEqual((status, result['error']['code']), (409, 'lifecycle_busy'))
        self.fixture.docker.release.set()
        self.assertEqual(self.finish(receipt)['status'], 'succeeded')
        self.assertEqual(self.fixture.docker.max_running, 1)

    def test_actual_package_pending_marker_blocks_switch_before_stop(self):
        body = self.body(switch=True)
        marker = self.fixture.storage.binding.path('data', 'services/installer/package-service-policy.json')
        self.fixture.write_json(marker, {'schema_version': 1, 'terminal': False})
        status, result = self.request('POST', '/control/v1/switch', body, 'package-blocked')
        self.assertEqual(status, 503, result)
        self.assertEqual(result['error']['code'], 'package_admission_unavailable')
        self.assertTrue(self.actual_admission.called)
        self.assertEqual(self.mutations(), [])

    def test_success_receipt_replays_after_fresh_application_without_second_stop(self):
        """Stopped/resume survives reopen and boot until an explicit new switch."""
        body = self.body()
        status, receipt = self.request('POST', '/control/v1/stop', body, 'durable-stop')
        self.assertEqual(status, 202, receipt)
        self.assertEqual(self.finish(receipt)['status'], 'succeeded')
        self.assert_intent(OLD, 'stopped', 'resume')
        directory = self.fixture.base / 'run/llmctl'
        lock = directory / 'lifecycle.lock'
        recovery = directory / 'recovery.json'
        identity = lambda path: (path.stat().st_dev, path.stat().st_ino)
        before = (identity(directory), identity(lock), identity(recovery), recovery.read_bytes())
        durable = self.store.read()
        self.close_service()
        with self.fixture.lease() as lease:
            for _ in range(2):
                # Existing lease acquisition provisions fixed directories via
                # mkdir/FileExistsError. Real worker flock/paths, NOT tmpfiles.
                with self.assertRaises(LeaseBusy):
                    with acquire_lease(blocking=False, system_root=self.fixture.base,
                                       trusted_uid=os.geteuid()):
                        self.fail('provisioning bypassed the existing locked inode')
                lease.validate()
            self.start_service()
            lease.validate()
            self.assertEqual((identity(directory), identity(lock), identity(recovery),
                              recovery.read_bytes()), before)
            self.assertEqual(self.store.read(), durable)
        status, replay = self.request('POST', '/control/v1/stop', body, 'durable-stop')
        self.assertEqual(status, 202, replay)
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['operation']['id'], receipt['operation']['id'])
        self.assertEqual(self.finish(replay)['status'], 'succeeded')
        self.assertEqual([item for item in self.mutations() if item[0] == 'stop'], [('stop', self.old_identity)])
        self.assert_intent(OLD, 'stopped', 'resume')
        with self.fixture.lease() as lease:
            self.fixture.load().dispatch('boot-start', lease=lease)
            self.fixture.load().dispatch('boot-start', lease=lease)
        stopped = self.assert_intent(OLD, 'stopped', 'resume')
        self.assertFalse(stopped['container_running'])
        self.assertFalse(any(item[0] == 'start_enter' for item in self.mutations()))
        status, switched = self.request('POST', '/control/v1/switch', self.body(switch=True), 'switch-after-stop')
        self.assertEqual(status, 202, switched)
        self.assertEqual(self.finish(switched)['status'], 'succeeded')
        selected = self.assert_intent(TARGET, 'running', 'resume')
        self.assertTrue(selected['container_running'])
        self.assertEqual([item for item in self.mutations() if item[0] == 'start_enter'],
                         [('start_enter', selected['container']['id'])])
        self.assertEqual([item for item in self.mutations() if item[0] == 'stop'], [('stop', self.old_identity)])
        self.assertEqual(self.fixture.docker.max_running, 1)

    def test_equal_control_inference_key_blocks_switch_but_allows_explicit_stop(self):
        inference = Path(self.fixture.storage.binding.path('data', 'services/secrets/llm-api-key'))
        inference.write_bytes(self.key)
        before = self.snapshot()
        self.assertIsNotNone(before['active_identity'])
        self.assertNotEqual(before['observed'], 'ready')
        status, receipt = self.request('POST', '/control/v1/switch', self.body(before, switch=True), 'equal-key-start')
        self.assertEqual(status, 202, receipt)
        self.assertEqual(self.finish(receipt)['status'], 'failed')
        self.assertEqual(self.mutations(), [])
        status, receipt = self.request('POST', '/control/v1/stop', self.body(), 'equal-key-stop')
        self.assertEqual(status, 202, receipt)
        self.assertEqual(self.finish(receipt)['status'], 'succeeded')
        self.assertEqual([item for item in self.mutations() if item[0] == 'stop'], [('stop', self.old_identity)])

    def test_missing_inference_key_keeps_observed_identity_for_explicit_stop(self):
        inference = Path(self.fixture.storage.binding.path('data', 'services/secrets/llm-api-key'))
        inference.unlink()
        before = self.snapshot()
        self.assertIsNotNone(before['active_identity'])
        self.assertNotEqual(before['observed'], 'ready')
        status, receipt = self.request('POST', '/control/v1/stop', self.body(before), 'missing-key-stop')
        self.assertEqual(status, 202, receipt)
        self.assertEqual(self.finish(receipt)['status'], 'succeeded')
        self.assertEqual([item for item in self.mutations() if item[0] == 'stop'], [('stop', self.old_identity)])

    def test_recovery_never_adopts_reused_name_or_stops_unrelated_container(self):
        before = self.snapshot()
        self.close_service()
        self.fixture.storage.lost = True
        original = self.fixture.docker.records[0]
        replacement = copy.deepcopy(original)
        replacement['Id'] = 'f' * 64
        replacement['Config']['Labels'] = {'external.owner': 'unrelated'}
        self.fixture.docker.records = [replacement]
        self.start_service()
        status, result = self.request('POST', '/control/v1/stop', self.body(before), 'reused-name-stop')
        self.assertEqual(status, 503, result)
        self.assertEqual(result['error']['code'], 'recovery_identity_unavailable')
        self.assertEqual(self.mutations(), [])
        self.assertTrue(self.fixture.docker.records[0]['State']['Running'])

    def test_storage_loss_stop_targets_only_trusted_id_among_unrelated_containers(self):
        self.close_service()
        unrelated = copy.deepcopy(self.fixture.docker.records[0])
        unrelated['Id'] = 'e' * 64
        unrelated['Name'] = '/unrelated-fixture'
        unrelated['Config']['Labels'] = {'external.owner': 'unrelated'}
        self.fixture.docker.records.append(unrelated)
        self.fixture.storage.lost = True
        self.start_service()
        snapshot = self.snapshot()
        status, receipt = self.request('POST', '/control/v1/stop', self.body(snapshot), 'narrow-recovery-stop')
        self.assertEqual(status, 202, receipt)
        self.assertEqual(self.finish(receipt)['status'], 'succeeded')
        self.assertEqual([item for item in self.mutations() if item[0] == 'stop'], [('stop', self.old_identity)])
        self.assertTrue(next(item for item in self.fixture.docker.records if item['Id'] == 'e' * 64)['State']['Running'])

    def test_fresh_subprocess_recovers_over_real_http_without_data_config_or_inference_key(self):
        self.close_service()
        root = self.fixture.base
        inventory = root / 'run/llmctl/docker-inventory.json'
        unrelated = copy.deepcopy(self.fixture.docker.records[0])
        unrelated.update(Id='d' * 64, Name='/external-process-fixture')
        unrelated['Config']['Labels'] = {'external.owner': 'unrelated'}
        FixtureAtomicJSONStore(inventory, expected_uid=os.geteuid()).write(self.fixture.docker.records + [unrelated])
        credential = root / 'etc/llm-server/control-api-key'
        credential.parent.mkdir(mode=0o700, parents=True)
        credential.write_bytes(self.key)
        credential.chmod(0o600)
        # Only disposable synthetic files are removed. A new interpreter has no
        # Manager instance, saved process state, profiles or inference key.
        shutil.rmtree(self.fixture.configs)
        shutil.rmtree(self.fixture.storage.data)
        child = subprocess.Popen([sys.executable, '-I', '-B', str(Path(__file__).resolve()),
                                  '--fixture-recovery-worker', str(root)], cwd='/',
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        try:
            readable, _, _ = select.select([child.stdout], [], [], 5)
            self.assertTrue(readable, 'fresh recovery process did not expose HTTP within bounded startup')
            line = child.stdout.readline()
            self.assertTrue(line, 'fresh recovery process failed before listener startup')
            metadata = json.loads(line)
            self.assertEqual(metadata['cwd'], '/')
            self.assertNotEqual(metadata['pid'], os.getpid())
            self.address = ('127.0.0.1', metadata['port'])
            status, unauthenticated = self.request(auth=False)
            self.assertEqual(status, 401, unauthenticated)
            snapshot = self.snapshot()
            self.assertFalse(snapshot['storage_available'])
            self.assertFalse(snapshot['state_persisted'])
            self.assertTrue(snapshot['generation_current'])
            self.assertIsNotNone(snapshot['active_identity'])
            status, refused = self.request('POST', '/control/v1/switch', self.body(snapshot, switch=True), 'subprocess-no-start')
            self.assertEqual(status, 503, refused)
            stale = dict(self.body(snapshot), expected_generation=snapshot['generation'] + 1)
            status, refused = self.request('POST', '/control/v1/stop', stale, 'subprocess-stale-stop')
            self.assertEqual((status, refused['error']['code']), (409, 'stale_state'))
            status, receipt = self.request('POST', '/control/v1/stop', self.body(snapshot), 'subprocess-trusted-stop')
            self.assertEqual(status, 202, receipt)
            self.assertFalse(receipt['state_persisted'])
            outcome = self.finish(receipt)
            self.assertEqual(outcome['status'], 'succeeded', outcome)
            self.assertFalse(outcome['state_persisted'])
            self.assertEqual(outcome['observed']['desired'], 'stopped')
            saved = FixtureAtomicJSONStore(root / 'run/llmctl/recovery.json', expected_uid=os.geteuid()).read()
            self.assertEqual(saved['desired'], 'stopped')
            self.assertEqual(saved['boot_policy'], 'resume')
            self.assertFalse(saved['state_persisted'])
            events = FixtureAtomicJSONStore(root / 'run/llmctl/docker-events.json', expected_uid=os.geteuid()).read()
            self.assertEqual(events, [{'event': 'stop', 'id': self.old_identity, 'lease_held': True}])
            records = json.loads(inventory.read_text())
            self.assertFalse(next(item for item in records if item['Id'] == self.old_identity)['State']['Running'])
            self.assertTrue(next(item for item in records if item['Id'] == unrelated['Id'])['State']['Running'])
            self.assertFalse(self.fixture.configs.exists())
            self.assertFalse(Path(self.fixture.storage.data).exists())
        finally:
            if child.poll() is None:
                try:
                    output, errors = child.communicate('shutdown\n', timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.communicate(timeout=2)
                    self.fail('fresh recovery fixture did not exit within bounded shutdown')
            else:
                output, errors = child.communicate(timeout=2)
            self.assertNotIn(self.key.decode('ascii'), output + errors)
            self.assertEqual(child.returncode, 0, 'fresh recovery fixture exited unsuccessfully')

    def test_fresh_storage_loss_uses_exact_run_identity_and_preserves_stop_on_restore(self):
        self.close_service()
        inference_key = Path(self.fixture.storage.binding.path('data', 'services/secrets/llm-api-key'))
        inference_key.unlink()
        self.fixture.storage.lost = True
        self.start_service()
        with patch.object(Manager, 'deployment', side_effect=AssertionError('recovery read configuration')), \
                patch.object(Manager, 'check_artifacts', side_effect=AssertionError('recovery read artifacts')), \
                patch.object(Manager, 'status', side_effect=AssertionError('recovery used normal status')):
            snapshot = self.snapshot()
            self.assertFalse(snapshot['storage_available'])
            self.assertFalse(snapshot['state_persisted'])
            self.assertIsNotNone(snapshot['active_identity'])
            self.assertTrue(snapshot['generation_current'])
            status, refused = self.request('POST', '/control/v1/switch', self.body(snapshot, switch=True), 'lost-start')
            self.assertEqual(status, 503, refused)
            status, receipt = self.request('POST', '/control/v1/stop', self.body(snapshot), 'lost-stop')
            self.assertEqual(status, 202, receipt)
            self.assertFalse(receipt['state_persisted'])
            stopped = self.finish(receipt)
            self.assertEqual(stopped['status'], 'succeeded', stopped)
            self.assertFalse(stopped['state_persisted'])
        self.assertEqual([item for item in self.mutations() if item[0] == 'stop'], [('stop', self.old_identity)])
        recovery = FixtureAtomicJSONStore(self.fixture.base / 'run/llmctl/recovery.json', expected_uid=os.geteuid()).read()
        self.assertEqual(recovery['desired'], 'stopped')
        self.assertEqual(recovery['boot_policy'], 'resume')
        self.close_service()
        self.fixture.storage.lost = False
        self.start_service()
        restored = self.snapshot()
        self.assertEqual(restored['desired'], 'stopped')
        manager = self.fixture.load()
        with self.fixture.lease() as lease:
            manager.dispatch('boot-start', lease=lease)
        self.assertFalse(any(item[0] == 'start_enter' for item in self.mutations()))


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--fixture-recovery-worker':
        raise SystemExit(recovery_http_child(sys.argv[2]))
    unittest.main()
