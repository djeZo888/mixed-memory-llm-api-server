"""Protected placement/retirement regressions; synthetic offline I/O only."""
import copy
import ctypes
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import Mock, patch

from tests.image_runtime.test_service import service, owned_container, owned_state, completed, IMAGE, RUN_ID
from tests.image_runtime import test_operation_protocol as operation
from tests.lifecycle import test_dedicated_image_peer as peer
from tests.test_node_projection import BOOT, Cached, sample
from tests import test_ada_passive as ada_fixture
from tests.test_mimo_same_boot_source import o
from control import node_observation as n
from control.node import NodeStatus, SERVICES
from lifecycle.runtime_io import image_gpu_uuid, validate_image_container

ROOT = Path(__file__).resolve().parents[1]
INTERNAL = n.ADA_GPU
EXTERNAL = service.H032_GPU_UUID

def module(name):
    spec = importlib.util.spec_from_file_location('h037_' + name, ROOT / 'scripts/image_runtime' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def selected(gpu=INTERNAL):
    return dict(uuid=gpu, selectionConfigSha256='a' * 64, bootId=BOOT)


class PlacementTests(unittest.TestCase):
    def test_explicit_reviewed_config_selection_no_default_or_ordinal(self):
        for gpu in (INTERNAL, EXTERNAL):
            self.assertEqual(image_gpu_uuid({'gpu_uuid': gpu}), gpu)
        for config in ({}, None, {'gpu_uuid': None}, {'gpu_uuid': 0}, {'gpu_uuid': '0'},
                       {'gpu_uuid': 'all'}, {'gpu_uuid': INTERNAL + ',' + EXTERNAL},
                       {'gpu_uuid': SERVICES['qwen-gpu0'][0]}, {'gpu_uuid': INTERNAL.upper()}):
            with self.subTest(config=config), self.assertRaisesRegex(RuntimeError, 'image_gpu_selection_invalid'):
                image_gpu_uuid(config)

    def test_owner_launch_and_exact_target_query_follow_config(self):
        runtime = object.__new__(service.Runtime)
        runtime.model = '/data/models-large/synthetic'
        for gpu in (INTERNAL, EXTERNAL):
            runtime.config = {'image_id': IMAGE, 'gpu_uuid': gpu}
            argv = runtime.create_argv(RUN_ID)
            self.assertEqual(argv[argv.index('--gpus') + 1], 'device=' + gpu)
            self.assertIn('io.llm-image.gpu=' + gpu, argv)
            self.assertIn('CUDA_VISIBLE_DEVICES=' + gpu, argv)
            self.assertIn('NVIDIA_VISIBLE_DEVICES=' + gpu, argv)
            self.assertEqual(argv[-2:], [RUN_ID, gpu])
            with patch.object(service, 'run', return_value=completed([], gpu + ', 49140, 48000')) as command:
                self.assertEqual(runtime.current_device()['uuid'], gpu)
                self.assertEqual(command.call_args.args[0][1], '--id=' + gpu)
            with patch.object(service, 'run', side_effect=RuntimeError('owned_command_failed')) as command:
                with self.assertRaisesRegex(RuntimeError, 'owned_command_failed'):
                    runtime.current_device()
                self.assertEqual(command.call_count, 1)

    def test_containment_requires_all_selected_identities_and_keeps_device_guards(self):
        state, value = owned_state(), owned_container()
        for gpu in (INTERNAL, EXTERNAL):
            value['Config']['Labels']['io.llm-image.gpu'] = gpu
            value['Config']['Env'] = ['CUDA_VISIBLE_DEVICES=' + gpu, 'NVIDIA_VISIBLE_DEVICES=' + gpu]
            value['HostConfig']['DeviceRequests'][0]['DeviceIDs'] = [gpu]
            config = {'gpu_uuid': gpu, 'image_id': IMAGE}
            validate_image_container(value, state, config)
            for mutation in (
                lambda c: c['Config']['Labels'].update({'io.llm-image.gpu': '0'}),
                lambda c: c['Config']['Env'].append('CUDA_VISIBLE_DEVICES=0'),
                lambda c: c['Config']['Env'].append('NVIDIA_VISIBLE_DEVICES=all'),
                lambda c: c['HostConfig']['DeviceRequests'][0].update(DeviceIDs=['0']),
                lambda c: c['HostConfig'].update(Privileged=True),
                lambda c: c['HostConfig'].update(Devices=[{'PathOnHost': '/dev/nvidia0'}]),
            ):
                bad = copy.deepcopy(value); mutation(bad)
                with self.assertRaises(RuntimeError):
                    validate_image_container(bad, state, config)

    def test_native_visibility_uses_forwarded_full_uuid_and_refuses_fallback(self):
        native = module('native_server')
        for gpu in (INTERNAL, EXTERNAL):
            env = dict(CUDA_VISIBLE_DEVICES=gpu, NVIDIA_VISIBLE_DEVICES=gpu)
            self.assertEqual(native.selected_gpu(['native', RUN_ID, gpu], env), gpu)
            for argv, bad in ((['native', RUN_ID], env), (['native', RUN_ID, '0'], env),
                              (['native', RUN_ID, gpu], {**env, 'NVIDIA_VISIBLE_DEVICES': 'all'}),
                              (['native', RUN_ID, gpu], {**env, 'CUDA_VISIBLE_DEVICES': EXTERNAL if gpu == INTERNAL else INTERNAL})):
                with self.assertRaisesRegex(RuntimeError, 'unexpected_gpu_visibility'):
                    native.selected_gpu(argv, bad)

    def test_nvml_uuid_lookup_is_exact_and_mismatch_never_samples(self):
        telemetry = module('telemetry')
        for gpu in (INTERNAL, EXTERNAL):
            nvml = telemetry.NVML(gpu, Mock())
            calls = []
            def call(name, *args):
                calls.append((name, args))
                if name == 'nvmlDeviceGetUUID':
                    ctypes.memmove(args[1], (gpu + '\0').encode(), len(gpu) + 1)
                return {'function': name, 'code': 0}
            nvml.call = call
            self.assertTrue(nvml.start()['identity']['matches_required_uuid'])
            self.assertEqual(calls[1][0], 'nvmlDeviceGetHandleByUUID')
            self.assertEqual(calls[1][1][0], gpu.encode())
        with self.assertRaises(ValueError):
            telemetry.NVML('0', Mock())
        fake = Mock(); fake.close.return_value = {'code': 0}; fake.start.return_value = {'identity': {'matches_required_uuid': False}}
        with patch.object(telemetry, 'NVML', return_value=fake) as factory:
            self.assertEqual(telemetry.run(io.StringIO(), None, threading.Event(), gpu_uuid=INTERNAL), 2)
        factory.assert_called_once_with(INTERNAL, None)
        fake.memory.assert_not_called()

    def test_critical_config_cas_refuses_selection_swap_before_dispatch(self):
        fixture = operation.OperationProtocol(methodName='runTest'); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.runtime.boot = fixture.boot
        fixture.anchor.atomic_json('config.json', {**fixture.runtime.config, 'gpu_uuid': INTERNAL})
        with self.assertRaisesRegex(RuntimeError, 'image_config_changed'):
            with fixture.runtime.critical():
                self.fail('CAS mismatch admitted')
        fixture.runtime.config.pop('gpu_uuid')
        with self.assertRaisesRegex(RuntimeError, 'image_gpu_selection_invalid'):
            with fixture.runtime.critical():
                self.fail('missing selection admitted')

    def test_text_coexistence_accepts_internal_placement_without_readiness_dependency(self):
        fixture = peer.DedicatedImagePeerTests(methodName='runTest'); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.config['gpu_uuid'] = INTERNAL
        fixture.candidate['Config']['Labels']['io.llm-image.gpu'] = INTERNAL
        fixture.candidate['Config']['Env'] = ['CUDA_VISIBLE_DEVICES=' + INTERNAL, 'NVIDIA_VISIBLE_DEVICES=' + INTERNAL]
        fixture.candidate['Config']['Cmd'][-1] = INTERNAL
        fixture.candidate['HostConfig']['DeviceRequests'][0]['DeviceIDs'] = [INTERNAL]
        fixture.manager.docker.inspect = Mock(return_value=copy.deepcopy(fixture.candidate))
        fixture.manager.validate_dedicated_image_peer(fixture.candidate, fixture.manager.deployment('qwen38-27b-q0-480000-yarn4-bf16kv'))
        fixture.manager.sglang_probe.assert_not_called()

    def test_missing_image_only_and_durable_selection_visible_when_native_unknown(self):
        text_gpu = SERVICES['qwen-gpu0'][0]
        text = dict(boot_id=BOOT, generation=7, ready=True, admitting=True, hardware_latched=False,
                    hardware_validation_age_ms=0, hardware_validated_boot_id=BOOT,
                    hardware_validated_gpu_uuids=[text_gpu], installed_capabilities=['chat.completions'])
        image = dict(boot_id=BOOT, imageGPU=selected(), ready=False, admitting=False,
                     hardware_latched=True, reason='hardware_missing', generation=None,
                     installed_capabilities=['images.generations', 'images.edits'])
        snapshot = NodeStatus(Cached({'boot': sample({'boot_id': BOOT}),
            'qwen-gpu0': sample(text), 'image': sample(image)})).snapshot()
        self.assertEqual(snapshot['imageGPU'], selected())
        self.assertFalse(snapshot['image']['ready'])
        self.assertEqual(snapshot['image']['capabilities'], ['images.edits', 'images.generations'])
        row = next(x for x in snapshot['services'] if x['service_id'] == 'qwen-gpu0')
        self.assertEqual(row['availability'], 'available'); self.assertTrue(row['admitting'])
        image.pop('imageGPU'); image.update(ready=True, admitting=True, hardware_latched=False)
        snapshot = NodeStatus(Cached({'boot': sample({'boot_id': BOOT}), 'image': sample(image)})).snapshot()
        self.assertIsNone(snapshot['imageGPU']['uuid']); self.assertFalse(snapshot['image']['admitting'])

    def test_selected_internal_resident_keeps_exact_five_percent_reserve(self):
        runtime = object.__new__(service.Runtime)
        runtime.config = {'gpu_uuid': INTERNAL, 'image_id': IMAGE, 'network_id': 'a' * 64}
        value = owned_container(); value['State'].update(OOMKilled=False, StartedAt='synthetic-start')
        value['NetworkSettings']['Networks'] = {service.NETWORK: {'NetworkID': 'a' * 64}}
        runtime.inspect_owned = Mock(return_value=value)
        runtime.check_network = Mock(); runtime.native_health = Mock(return_value=True)
        runtime.host_headroom = Mock(return_value={})
        def command(argv, **kwargs):
            if argv[:2] == ['docker', 'top']:
                return completed(argv, 'PID\n1234\n')
            self.assertEqual(argv[1], '--id=' + INTERNAL)
            return completed(argv, INTERNAL + ', 1234, 1\n')
        with patch.object(service, 'run', side_effect=command):
            runtime.current_device = Mock(return_value={'uuid': INTERNAL, 'total_bytes': 100, 'free_bytes': 4})
            with self.assertRaisesRegex(RuntimeError, 'ada_current_margin_below_5_percent'):
                runtime.verify_resident(owned_state())
            runtime.current_device.return_value['free_bytes'] = 5
            self.assertEqual(runtime.verify_resident(owned_state())['device_current']['free_bytes'], 5)

    def test_selected_internal_metrics_and_affected_services_follow_same_uuid(self):
        image = dict(boot_id=BOOT, imageGPU=selected(), ready=False, admitting=False,
            hardware_latched=True, reason='hardware_missing')
        metrics = dict(boot_id=BOOT, gpus=[dict(uuid=INTERNAL, temperature_c=42,
            pcie_generation=4, pcie_width=16, memory_total_mib=49140, memory_used_mib=0)])
        snapshot = NodeStatus(Cached({'boot': sample({'boot_id': BOOT}),
            'image': sample(image), 'image_gpu': sample(metrics)})).snapshot()
        gpu = next(row for row in snapshot['gpus'] if row['uuid'] == INTERNAL)
        self.assertEqual(gpu['affected_services'], ['image'])
        self.assertEqual((gpu['pcie_generation'], gpu['pcie_width']), (4, 16))
        self.assertEqual(gpu['temperature_c'], 42)
        self.assertEqual(next(row for row in snapshot['services'] if row['service_id'] == 'image')['required_gpu_uuids'], [INTERNAL])

    def test_reader_publishes_raw_config_hash_before_unavailable_native_state(self):
        config = {'schema_version': 1, 'owner': n.IMAGE_OWNER, 'gpu_uuid': INTERNAL}
        raw = json.dumps(config).encode()
        binding = SimpleNamespace(path=lambda role, suffix: '/data/services/' + suffix,
            validate_path=lambda *_: None,
            read_json=lambda role, path: config if path.endswith('config.json') else {})
        reader = n.CanonicalIdentityReader(binding=lambda _: binding, boot=lambda: {'boot_id': BOOT},
            read=lambda *a, **k: raw, latch=lambda b, ids: {'hardware_latched': True, 'reason': 'hardware_missing'},
            run=lambda *a: self.fail('no native query when owner state is unknown'))
        row = reader.service('image')
        self.assertEqual(row['imageGPU'], {**selected(), 'selectionConfigSha256': hashlib.sha256(raw).hexdigest()})
        self.assertFalse(row['ready']); self.assertIsNone(row['generation'])

    def test_selected_physical_collector_keeps_twenty_slot_bound_and_no_fallback(self):
        from control.node_collectors import ImageGpuCollector, production_callbacks
        from control.passive import BoundedObservers
        config = dict(schema_version=1, owner=n.IMAGE_OWNER, gpu_uuid=INTERNAL)
        binding = SimpleNamespace(path=lambda *args: '/registered/config.json',
            read_json=lambda *args: copy.deepcopy(config))
        calls = []
        def command(argv, seconds):
            calls.append(argv)
            return '<nvidia_smi_log><gpu><uuid>' + config['gpu_uuid'] + '</uuid></gpu></nvidia_smi_log>'
        collector = ImageGpuCollector(binding=lambda _: binding, run=command, boot=lambda: {'boot_id': BOOT})
        self.assertEqual(collector(2)['gpus'][0]['uuid'], INTERNAL)
        config['gpu_uuid'] = EXTERNAL
        self.assertEqual(collector(2)['gpus'][0]['uuid'], EXTERNAL)
        self.assertEqual([c[1] for c in calls], ['--id=' + INTERNAL, '--id=' + EXTERNAL])
        config.pop('gpu_uuid')
        with self.assertRaisesRegex(RuntimeError, 'image_gpu_selection_invalid'):
            collector(2)
        self.assertIsNone(collector.last_proof); self.assertEqual(len(calls), 2)
        callbacks = production_callbacks()
        self.assertLessEqual(len(callbacks), 20)
        BoundedObservers(callbacks)  # Construction only, never start production I/O.

    def test_source_successor_accepts_exact_seam_refuses_profile_and_unrelated_path(self):
        paths = o.source_amendment_paths()
        required = {f'/usr/local/lib/llm-server/{root}/scripts/lifecycle/{leaf}'
                    for root in ('control-api', 'node-api') for leaf in ('manager.py', 'runtime_io.py')}
        required |= {f'/usr/local/lib/llm-server/node-api/scripts/control/{leaf}'
                     for leaf in ('node.py', 'node_actions.py', 'node_observation.py')}
        self.assertTrue(required <= paths)
        old = {'context': 480000, 'max_output_tokens': 65536, 'decode_threads': 8,
               'source_sha256': {p: 'a' * 64 for p in required}}
        new = copy.deepcopy(old); new['source_sha256'] = {p: 'b' * 64 for p in required}
        delta = {p: {'old': 'a' * 64, 'new': 'b' * 64} for p in required}
        with patch.object(o, 'protected', return_value=b'new'), patch.object(o.hashlib, 'sha256', return_value=SimpleNamespace(hexdigest=lambda: 'b' * 64)):
            o.reviewed_source_amendment(old, new, delta)
            for field, value in (('context', 420000), ('max_output_tokens', 8192), ('decode_threads', 4)):
                bad = copy.deepcopy(new); bad[field] = value
                with self.assertRaisesRegex(RuntimeError, 'source_successor_invalid'):
                    o.reviewed_source_amendment(old, bad, delta)
            path = '/usr/local/lib/llm-server/node-api/scripts/install/storage.py'
            bad_old = copy.deepcopy(old); bad_new = copy.deepcopy(new)
            bad_old['source_sha256'][path] = 'a' * 64; bad_new['source_sha256'][path] = 'b' * 64
            with self.assertRaisesRegex(RuntimeError, 'source_successor_invalid'):
                o.reviewed_source_amendment(bad_old, bad_new, {**delta, path: {'old': 'a' * 64, 'new': 'b' * 64}})


class RetirementTests(unittest.TestCase):
    def setUp(self):
        self.receipt = dict(schema_version=1, kind='h037-ada200k-retirement', service_id=n.ADA_SERVICE,
            unit='qwen-ada200k.service', gpu_uuid=INTERNAL, native_id=n.ADA_RETIRED_NATIVE, boot_id=BOOT,
            container_retained=True, history_retained=True, listener_absent=True,
            gpu_processes=[], gpu_used_memory_mib=0, observed_at_utc='2026-09-30T11:00:00Z')
        self.container = {'Id': n.ADA_RETIRED_NATIVE, 'State': {'Running': False, 'Pid': 0}}
        self.unit = dict(Id='qwen-ada200k.service', ActiveState='inactive', UnitFileState='disabled',
                         MainPID='0', ControlPID='0', Job='')

    def test_retirement_needs_exact_protected_receipt_stop_disable_and_listener_absence(self):
        self.assertTrue(n.ada_retirement(self.receipt, self.container, self.unit, '', BOOT))
        for field, value in (('native_id', 'a' * 64), ('boot_id', 'old'), ('gpu_used_memory_mib', -1),
                             ('gpu_processes', [123]), ('history_retained', False), ('schema_version', True)):
            receipt = {**self.receipt, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                n.ada_retirement(receipt, self.container, self.unit, '', BOOT)
        for unit in ({**self.unit, 'UnitFileState': 'enabled'}, {**self.unit, 'MainPID': '123'}):
            with self.assertRaises(ValueError):
                n.ada_retirement(self.receipt, self.container, unit, '', BOOT)
        with self.assertRaises(ValueError):
            n.ada_retirement(self.receipt, self.container, self.unit, 'LISTEN 0 10 127.0.0.1:30014 0.0.0.0:*', BOOT)

    def test_actual_collector_needs_receipt_and_current_stop_disable_proof(self):
        fixture = ada_fixture.AdaPassiveTests(methodName='runTest'); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.cid = n.ADA_RETIRED_NATIVE
        fixture.files[n.ADA_BASE + '/state.json'] = json.dumps({'container': {'id': fixture.cid}}).encode()
        def read(path, **kwargs):
            if str(path) not in fixture.files:
                raise FileNotFoundError()
            return fixture.files[str(path)]
        fixture.reader.read = read
        def command(argv, seconds):
            if argv[0] == '/usr/bin/docker':
                return json.dumps([self.container])
            if argv[0] == '/usr/bin/systemctl':
                return '\n'.join(k + '=' + v for k, v in self.unit.items())
            if argv[0] == '/usr/bin/ss':
                return ''
            self.fail('unregistered retirement command')
        fixture.reader.run = command
        collector = n.AdaPassiveCollector(fixture.reader, get=lambda *_: self.fail('stopped native probe'))
        self.assertFalse(collector(2)['retired'])
        fixture.files[n.ADA_BASE + '/retirement.json'] = json.dumps(self.receipt).encode()
        result = collector(2)
        self.assertTrue(result['retired']); self.assertTrue(result['present']); self.assertFalse(result['ready'])
        self.unit['UnitFileState'] = 'enabled'
        with self.assertRaisesRegex(ValueError, 'ada_retirement_unproven'):
            collector(2)

    def test_only_current_proven_retirement_removes_active_row_and_keeps_presence(self):
        for retired in (False, None, True):
            row = dict(boot_id=BOOT, present=True, ready=False, retired=retired, reason='service_stopped')
            snapshot = NodeStatus(Cached({'boot': sample({'boot_id': BOOT}), n.ADA_SERVICE: sample(row)})).snapshot()
            self.assertEqual(n.ADA_SERVICE in [r['service_id'] for r in snapshot['services']], retired is not True)
            self.assertEqual(snapshot['retired200K'], dict(present=True, ready=False, retired=retired))
        stale = NodeStatus(Cached({'boot': sample({'boot_id': BOOT}), n.ADA_SERVICE: sample(row, age_ms=16000, freshness='stale')})).snapshot()
        self.assertIsNone(stale['retired200K']['retired'])


if __name__ == '__main__':
    unittest.main()
