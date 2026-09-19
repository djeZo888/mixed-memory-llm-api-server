"""Concrete host adapter protocol/commands with mocked Linux I/O; no host contact."""
from __future__ import annotations

import copy
from contextlib import contextmanager
import os
import tempfile
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark.host import LinuxHost, HostBudget, serve, command, _COMMAND_DEADLINE
from benchmark.lifecycle import CONTROL_UNIT, BOOT_UNIT, PlanError, validate_snapshot
from install.storage_io import AnchoredRoot, GuardedFile
from benchmark.owner import WorkerVerificationPending
from tests.test_benchmark_owner import Fixture
from tests.test_benchmark_lifecycle import snapshot
from common.lifecycle_lease import acquire_lease, transition_in_progress


class HostTests(unittest.TestCase):
    def bare(self):
        host = LinuxHost.__new__(LinuxHost)
        host.scope = 'full'
        host.campaign = 'benchrun-offline'
        host.log_root = '/data/logs/benchrun-offline'
        host.owner = SimpleNamespace(phase='ACTIVE', lease=Mock(), resources=[], original={})
        host.requests, host.manifests, host.samples = {}, {}, {}
        host.load_manifests, host.allocation_proofs, host.measured = {}, {}, {}
        host.write_json = Mock()
        host.identity = Mock()
        host.budget = Mock()
        host.budget.request_timeout.return_value = 43
        host.budget.checkpoint.return_value = 43
        host.budget.data = {'phase': 'MEASURING'}
        return host

    def test_shell_never_used_and_environment_sanitized(self):
        with patch('benchmark.host.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=b'yes', stderr=b'')) as run:
            command(['/usr/bin/docker', 'inspect', '1' * 64])
        args, kwargs = run.call_args
        self.assertEqual(args[0], ['/usr/bin/docker', 'inspect', '1' * 64])
        self.assertNotIn('shell', kwargs)
        self.assertEqual(set(kwargs['env']), {'PATH', 'LC_ALL'})
        self.assertEqual(kwargs['stdin'], __import__('subprocess').DEVNULL)

    def test_command_failure_never_exposes_stderr(self):
        with patch('benchmark.host.subprocess.run', return_value=SimpleNamespace(returncode=1, stdout=b'', stderr=b'synthetic-sensitive-diagnostic')):
            with self.assertRaisesRegex(ValueError, '^host_command_failed$'):
                command(['/usr/bin/docker', 'inspect', '1' * 64])

    def test_control_only_target_fixed_unit(self):
        host = self.bare()
        with patch('benchmark.host.command') as run:
            host.control('stop')
            host.control('start')
            with self.assertRaises(ValueError):
                host.control('restart llmctl-boot.service')
        self.assertEqual([call.args[0] for call in run.call_args_list],
                         [['/usr/bin/systemctl', 'stop', 'llm-control.service'],
                          ['/usr/bin/systemctl', 'start', 'llm-control.service']])

    def test_units_accepts_omitted_control_execstop_and_keeps_boot_contract(self):
        # Actual systemctl show shape: an empty ExecStop array is omitted,
        # including with --all; required state/path properties are present.
        control = (b'ActiveState=active\nSubState=running\n'
                   b'FragmentPath=/etc/systemd/system/llm-control.service\n'
                   b'DropInPaths=\nUnitFileState=enabled\n')
        boot = (b'ExecStop={ path=/usr/bin/python3 ; argv[]=/usr/bin/python3 '
                b'-I -B /usr/local/lib/local-ai-server/scripts/llmctl boot-stop '
                b'--yes --instance /data/services/llm-manager/deployment-instance.json ; }\n'
                b'ActiveState=active\nSubState=exited\n'
                b'FragmentPath=/etc/systemd/system/llmctl-boot.service\n'
                b'DropInPaths=\nUnitFileState=enabled\n')
        with patch('benchmark.host.command', side_effect=[
                SimpleNamespace(stdout=control), SimpleNamespace(stdout=boot)]), \
                patch('benchmark.host.protected', return_value=(b'unit bytes', {})):
            services = self.bare().units()
        self.assertFalse(services[CONTROL_UNIT]['exec_stop_uses_lifecycle'])
        self.assertTrue(services[BOOT_UNIT]['exec_stop_uses_lifecycle'])
        original = snapshot()
        original['services'] = services
        validate_snapshot(original)
        original['services'][BOOT_UNIT]['exec_stop_uses_lifecycle'] = False
        with self.assertRaisesRegex(ValueError, 'service_stop_contract_changed'):
            validate_snapshot(original)

    def test_request_admission_top_level_rpc_and_timeout(self):
        host = self.bare()
        result = host.dispatch({'op': 'request_begin', 'id': '1' * 64, 'timeout_s': 99})
        self.assertEqual(result['timeout_s'], 43)
        host.budget.request_timeout.assert_called_once_with(99)
        host.identity.assert_called_once_with('1' * 64)
        self.assertIn('1' * 64, host.requests)
        with self.assertRaises(ValueError):
            host.dispatch({'op': 'request_begin', 'id': '1' * 64, 'timeout_s': 99})
        host.dispatch({'op': 'request_end', 'id': '1' * 64})
        self.assertEqual(host.requests, {})

    def test_invalid_owner_cannot_admit_request(self):
        host = self.bare()
        host.owner.phase = 'RESTORING'
        with self.assertRaises(ValueError):
            host.dispatch({'op': 'request_begin', 'id': '1' * 64})
        host.identity.assert_not_called()

    def test_pss_never_accepted_outside_two_checkpoints(self):
        host = self.bare()
        host.assert_idle = Mock()
        for point in ('timed_decode', 'sample', 'warmup'):
            with self.assertRaises(ValueError):
                host.quiescent('1' * 64, point)
        host.identity.assert_not_called()
        host.assert_idle.assert_not_called()

    def test_active_request_prevents_idle_gate_before_ss(self):
        host = self.bare()
        host.requests['1' * 64] = {'started_at': 1}
        with patch('benchmark.host.command') as run:
            with self.assertRaises(ValueError):
                host.assert_idle()
        run.assert_not_called()

    def test_private_durable_json_calls_installed_anchored_manager(self):
        host = self.bare()
        # Use real method, with explicit mocked installed binding/Manager only.
        del host.write_json
        host.guards = Mock()
        host.binding = Mock()
        host.binding.path.return_value = '/data/logs/benchrun-offline/owner.json'
        host.manager = Mock()
        host.write_json('owner.json', {'phase': 'ACTIVE'})
        host.manager.persistent_json.assert_called_once_with('/data/logs/benchrun-offline/owner.json', {'phase': 'ACTIVE'})
        self.assertEqual(host.guards.call_count, 2)
        with self.assertRaises(ValueError):
            host.write_json('../root.json', {})

    def test_resource_observation_does_not_export_environment(self):
        container = {'Id': '1' * 64, 'Name': '/benchrun-offline-g1-4096', 'Image': 'sha256:' + '2' * 64,
                     'Config': {'Env': ['SYNTHETIC_SECRET=value'], 'Labels': {'benchmark.campaign': 'benchrun-offline', 'benchmark.owner': 'llm-benchmark'}},
                     'HostConfig': {'RestartPolicy': {'Name': 'no'}}, 'State': {'Running': True}}
        result = LinuxHost.resource(container)
        self.assertEqual(result['name'], 'benchrun-offline-g1-4096')
        self.assertNotIn('Env', result)
        self.assertNotIn('SYNTHETIC_SECRET', json.dumps(result))

    def test_remove_refuses_running_and_uses_only_full_id(self):
        host = self.bare()
        resource = {'id': '1' * 64}
        host._exact = Mock(return_value={'State': {'Running': True}})
        with patch('benchmark.host.command') as run:
            with self.assertRaises(ValueError):
                host.remove(resource)
            run.assert_not_called()
            host._exact.return_value['State']['Running'] = False
            host.remove(resource)
            run.assert_called_once_with(['/usr/bin/docker', 'rm', '1' * 64], 60)

    def test_failed_inspect_requires_separate_absence_not_command_error(self):
        host = self.bare()
        cid = '1' * 64
        with patch('benchmark.host.command', side_effect=[SimpleNamespace(returncode=1, stdout=b''), SimpleNamespace(stdout=cid.encode())]):
            with self.assertRaises(ValueError):
                host.docker_inspect(cid)
        with patch('benchmark.host.command', side_effect=[SimpleNamespace(returncode=1, stdout=b''), SimpleNamespace(stdout=b'')]):
            self.assertIsNone(host.docker_inspect(cid))

    def test_pending_worker_proof_is_not_fabricated(self):
        host = self.bare()
        with self.assertRaises(WorkerVerificationPending):
            host.checks({'manager': {'selected': 'glm-original'}}, {'status': 'ready'})
        self.assertEqual(host.write_json.call_args.args[0], 'restoration-challenge.json')
        self.assertTrue(host.worker_nonce)
        self.assertGreater(host.restored_at, 0)

    def test_protocol_errors_bounded_without_auto_restoration(self):
        host = Mock()
        host.owner.phase = 'ACTIVE'
        host.dispatch.side_effect = [ValueError('sensitive diagnostic'), {'phase': 'ACTIVE'}]
        sink = io.StringIO()
        serve(host, io.StringIO('{"op":"bad"}\n{"op":"status"}\n'), sink)
        replies = [json.loads(line) for line in sink.getvalue().splitlines()]
        self.assertEqual(replies[0], {'ok': False, 'error': 'host_rpc_failed', 'phase': 'ACTIVE'})
        self.assertEqual(replies[1], {'ok': True, 'result': {'phase': 'ACTIVE'}})
        self.assertNotIn('sensitive', sink.getvalue())
        host.restore.assert_not_called()

    def test_rpc_diagnostic_nonleak_defers_until_drain_and_writer_failure_is_nonfatal(self):
        host = self.bare()
        secret = 'SYNTHETIC_PRIVATE_HEADER_BODY_EXCEPTION_VALUE'
        host.requests = {'healthy-inference': {'body': secret}}
        sink, receipts = io.StringIO(), []

        def collect_receipt(path, value):
            self.assertFalse(host.requests)
            self.assertTrue(path.startswith('rpc-errors/'))
            self.assertTrue(path.endswith('.json'))
            # The client already received its reply before guarded evidence I/O.
            self.assertGreaterEqual(len(sink.getvalue().splitlines()), 2)
            receipts.append(copy.deepcopy(value))
            if len(receipts) == 1:
                raise OSError(secret)

        def dispatch(message):
            if message['op'] == 'readiness':
                credentials_in_locals = {'Authorization': secret}
                return {}[credentials_in_locals['Authorization']]
            if message['op'] == 'request_end':
                host.write_json.assert_not_called()
                host.requests.clear()
                return {'drained': True}
            if message['op'] == 'allocation':
                raise PlanError('native_server_args_unavailable')
            if message['op'] == 'restore':
                return {'restored': True}
            raise PlanError(secret)

        host.dispatch = Mock(side_effect=dispatch)
        host.write_json = Mock(side_effect=collect_receipt)
        host.restore = Mock()
        messages = [{'op': 'readiness', 'headers': secret, 'body': secret},
                    {'op': 'request_end'}, {'op': 'allocation'},
                    {'op': secret}, {'op': 'restore'}]
        serve(host, io.StringIO(''.join(json.dumps(m) + '\n' for m in messages)), sink)
        self.assertEqual([r['operation'] for r in receipts], ['readiness', 'allocation', 'unknown'])
        self.assertEqual([r['exception_class'] for r in receipts], ['KeyError', 'PlanError', 'PlanError'])
        self.assertEqual([r['require_code'] for r in receipts], [None, 'native_server_args_unavailable', None])
        for receipt in receipts:
            self.assertEqual(set(receipt), {'operation', 'exception_class', 'require_code', 'frames'})
            self.assertTrue(receipt['frames'])
            for frame in receipt['frames']:
                self.assertEqual(set(frame), {'source', 'function', 'line'})
                self.assertEqual(Path(frame['source']).name, frame['source'])
                self.assertIsInstance(frame['line'], int)
        self.assertNotIn(secret, json.dumps(receipts) + sink.getvalue())
        replies = [json.loads(line) for line in sink.getvalue().splitlines()]
        self.assertEqual(replies[0], {'ok': False, 'error': 'host_rpc_failed', 'phase': 'ACTIVE'})
        self.assertEqual(replies[-1], {'ok': True, 'result': {'restored': True}})
        host.restore.assert_not_called()
        self.assertEqual(host.owner.phase, 'ACTIVE')

    def test_postrelease_recovery_reissues_nonce_without_control_or_model_mutation(self):
        for prior_phase in ('POST_RELEASE_LAN_VERIFICATION_PENDING', 'RESTORED'):
            with self.subTest(prior_phase=prior_phase), tempfile.TemporaryDirectory(prefix='host-recovery-') as directory:
                root = Path(directory).resolve()
                host = self.bare()
                original = snapshot()
                host.read_json = Mock(return_value={'campaign': host.campaign, 'evidence_kind': 'live',
                    'phase': prior_phase, 'original': original, 'resources': [], 'pending_create': None})
                host.owner.phase = 'NEW'
                host.owner._save = Mock()
                host.owner._release = lambda: release(host.owner)
                host.capture = Mock(side_effect=lambda lease: copy.deepcopy(original))
                host.campaign_containers = Mock(return_value=[])
                host.assert_idle = Mock()
                host.manager = Mock()
                host.control = Mock()
                host.budget.data = {'phase': 'RESTORING'}

                @contextmanager
                def lease_factory(*, blocking):
                    self.assertFalse(blocking)
                    with acquire_lease(blocking=False, system_root=root, trusted_uid=os.geteuid()) as lease:
                        yield lease

                def release(owner):
                    owner.lease_context.__exit__(None, None, None)
                    owner.lease_context = owner.lease = None

                with patch('common.lifecycle_lease.acquire_lease', lease_factory), patch('benchmark.host.command') as command_mock:
                    result = host.recover()
                self.assertFalse(result['restored'])
                self.assertEqual(result['worker_lan_verification'], 'PENDING')
                self.assertEqual(host.owner.phase, 'POST_RELEASE_LAN_VERIFICATION_PENDING')
                self.assertTrue(host.worker_nonce)
                self.assertEqual(original['services']['llm-control.service']['active'], 'active')
                self.assertFalse(transition_in_progress(system_root=root, trusted_uid=os.geteuid()))
                host.manager.dispatch.assert_not_called()
                host.control.assert_not_called()
                command_mock.assert_not_called()

    def test_budget_preserves_earlier_stage_epoch(self):
        host = self.bare()
        host.start_epoch = 1000
        host.read_json = Mock(return_value=None)
        budget = HostBudget(host)
        with patch('benchmark.host.time.time', return_value=1020):
            budget.start('maintenance')
        self.assertEqual(budget.data['started_at'], 1000)
        self.assertEqual(budget.data['last_seen_at'], 1020)
        host.write_json.assert_called_once_with('budget.json', budget.data)

    def test_actual_budget_constructor_reload_and_inherited_mutex_methods(self):
        host = self.bare()
        host.start_epoch = None
        host.read_json = Mock(return_value=None)
        budget = HostBudget(host)
        with patch('benchmark.host.time.time', return_value=1000):
            budget.start('maintenance')
        original = budget.data
        original['phase'] = 'invalid_detached_edit'
        self.assertEqual(budget.data['phase'], 'MEASURING')
        host.read_json.return_value = budget.data
        reloaded = HostBudget(host)
        reloaded.clock = lambda: 1007
        self.assertEqual(reloaded.checkpoint(), 21593)
        self.assertEqual(reloaded.request_timeout(7200), 7200)
        reloaded.begin_restoration()
        reloaded.finish_restoration(True)
        self.assertEqual(reloaded.data['phase'], 'RESTORED')
        host.read_json.return_value = {'schema': 0}
        with self.assertRaisesRegex(ValueError, 'invalid_budget_ledger'):
            HostBudget(host)

    def test_actual_anchored_writer_chunking_and_fsync_contract(self):
        host = self.bare()
        host.guards = Mock()
        with tempfile.TemporaryDirectory(prefix='host-writer-', dir=ROOT) as directory:
            root = Path(directory).resolve()
            root.chmod(0o700)
            device = str(os.major(root.stat().st_dev)) + ':' + str(os.minor(root.stat().st_dev))
            registration = {'schema_version': 1, 'roots': {'logs': str(root)},
                'data': {'path': str(root), 'mount': str(root), 'uuid': 'synthetic-data', 'fstype': 'synthetic', 'device': device},
                'models': {'path': str(root), 'mount': str(root), 'uuid': 'synthetic-models', 'fstype': 'synthetic', 'device': device}}
            @contextmanager
            def mounted_guard(*args, **kwargs):
                yield lambda: registration
            host.binding = SimpleNamespace(path=lambda role: str(root), mounted_guard=mounted_guard)
            host.storage_io = SimpleNamespace(AnchoredRoot=lambda path, guard: AnchoredRoot(path, guard, uid=os.geteuid()))
            raw = b'synthetic-private-evidence\n' * 50000
            actual_fsync = GuardedFile.fsync
            calls = []
            def fsync(handle):
                calls.append(handle.name)
                return actual_fsync(handle)
            with patch.object(GuardedFile, 'fsync', fsync):
                host.write_bytes('loads/synthetic.log', raw)
            target = root / host.campaign / 'loads/synthetic.log'
            self.assertEqual(target.read_bytes(), raw)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual(calls, ['synthetic.log'])
            self.assertFalse(hasattr(GuardedFile, 'flush'))
            self.assertEqual(host.guards.call_count, 2)

    def test_glm_mapping_native_only_explicit_uuid_order(self):
        host = self.bare()
        manifest = {'placement': 'G2', 'gpu_uuids': ['GPU-B', 'GPU-A']}
        container = {'Config': {'Env': ['CUDA_VISIBLE_DEVICES=GPU-B,GPU-A']}}
        replies = [SimpleNamespace(stdout=b'Available devices:\n  CUDA0: GPU\n  CUDA1: GPU\n'),
                   SimpleNamespace(stdout=b'GPU-A\nGPU-B\n')]
        with patch('benchmark.host.command', side_effect=replies) as run:
            self.assertEqual(host.cuda_mapping('1'*64, manifest, container), ['GPU-B', 'GPU-A'])
        self.assertEqual(run.call_args_list[0].args[0][-2:], ['/opt/llama/llama-server', '--list-devices'])
        self.assertNotIn('python', str(run.call_args_list))
        container['Config']['Env'] = ['CUDA_VISIBLE_DEVICES=0,1']
        with patch('benchmark.host.command') as run, self.assertRaisesRegex(ValueError, 'uuid_visibility'):
            host.cuda_mapping('1'*64, manifest, container)
        run.assert_not_called()

    def test_helper_gate_precedes_production_stop_and_restore_clears_deadline(self):
        host = self.bare()
        host.pin_sources, host.jobs, host.assert_idle = Mock(), Mock(), Mock()
        units = {BOOT_UNIT: {'active': 'active'}, CONTROL_UNIT: {'active': 'inactive'}}
        host.units = Mock(return_value=units)
        host.verify_mapping_helpers = Mock()
        original = {'services': units}
        host.gate('control_frozen', host.owner.lease, original, [])
        host.verify_mapping_helpers.assert_called_once_with(host.owner.lease)
        token = _COMMAND_DEADLINE.set(0)
        try:
            host.gate('restore', host.owner.lease, original, [])
            self.assertIsNone(_COMMAND_DEADLINE.get())
        finally:
            _COMMAND_DEADLINE.reset(token)

    def test_load_timeout_clamps_commands_and_clears_before_auto_restore(self):
        host = self.bare()
        host.budget.checkpoint.return_value = 2
        host.manifests = {'reviewed': {'placement': 'G1'}}
        host.pin_sources, host.jobs, host.assert_idle = Mock(), Mock(), Mock()
        units = {BOOT_UNIT: {'active': 'active'}, CONTROL_UNIT: {'active': 'inactive'}}
        host.units = Mock(return_value=units)
        def launch(manifest):
            command(['/synthetic/docker', 'create'], 120)
            host.gate('restore', host.owner.lease, {'services': units}, [])
            command(['/synthetic/systemctl', 'start'], 120)
            return {'synthetic': True}
        host.owner.launch = launch
        with patch('benchmark.host.subprocess.run', return_value=SimpleNamespace(returncode=0)) as run:
            host.dispatch({'op': 'load', 'manifest_sha256': 'reviewed'})
        self.assertGreater(run.call_args_list[0].kwargs['timeout'], 0)
        self.assertLessEqual(run.call_args_list[0].kwargs['timeout'], 2)
        self.assertEqual(run.call_args_list[1].kwargs['timeout'], 120)
        self.assertIsNone(_COMMAND_DEADLINE.get())

    def test_exited_dead_and_oom_fail_before_http_sanitized(self):
        for state in ({'Running': False, 'Status': 'exited', 'ExitCode': 1},
                      {'Running': True, 'Status': 'dead', 'Dead': True},
                      {'Running': False, 'Status': 'exited', 'OOMKilled': True}):
            with self.subTest(state=state):
                host = self.bare()
                cid = '1'*64
                container = {'Id': cid, 'Name': '/benchrun-offline-g1', 'Image': 'sha256:'+'2'*64,
                    'Config': {'Labels': {'benchmark.campaign': host.campaign, 'benchmark.owner': 'llm-benchmark'}},
                    'HostConfig': {'RestartPolicy': {'Name': 'no'}}, 'State': {**state, 'Error': 'synthetic-sensitive'}}
                resource = {k: v for k, v in host.resource(container).items() if k != 'running'}
                host.owner.resources = [{'resource': resource, 'state': 'RUNNING'}]
                host.docker_inspect = Mock(return_value=container)
                host.write_bytes = Mock()
                with patch('benchmark.host.http_json') as http, patch('benchmark.host.command',
                          return_value=SimpleNamespace(returncode=0, stdout=b'synthetic-private-log', stderr=b'')):
                    result = host.readiness(cid, 5)
                self.assertTrue(result['failed'])
                self.assertFalse(result['ready'])
                self.assertEqual(result['state'], 'STOP_OOM' if state.get('OOMKilled') else 'STOP_BACKEND_EXITED')
                self.assertNotIn('sensitive', json.dumps(result))
                self.assertNotIn('synthetic-private-log', json.dumps(result))
                http.assert_not_called()
                host.write_bytes.assert_called_once()

    def test_load_demand_precedes_allocation_proof_and_retains_transient_peak(self):
        host = self.bare()
        cid = '1'*64
        host.identity.return_value = ({}, Path('/synthetic/cgroup'), [123])
        host.load_manifests[cid] = {'placement': 'Q1'}
        group = {'current_bytes': 10000, 'anon_bytes': 1000, 'kernel_bytes': 100,
                 'file_bytes': 8900, 'file_mapped_bytes': 200, 'shmem_bytes': 50}
        with patch('benchmark.host.collect_sample', side_effect=lambda *a, **k: {'cgroups': {cid: dict(group)}}):
            first = host.telemetry(cid)
            group['anon_bytes'] = 500
            host.allocation_proofs[cid] = {}  # synthetic accepted Qwen readiness proof
            second = host.telemetry(cid)
        self.assertEqual(first['required_host_demand']['required_bytes'], 1350)
        self.assertEqual(first['required_host_demand']['reclaimable_file_bytes'], 8650)
        self.assertEqual(second['required_host_demand']['required_bytes'], 850)
        self.assertEqual(host.measured['Q1']['required_bytes'], 1350)
        self.assertEqual(host.measured['Q1']['sample_phase'], 'pre_readiness_load')
        self.assertEqual(host.measured['Q1']['load_phase_sample_count'], 1)
        self.assertEqual(host.measured['Q1']['load_phase_peak_required_bytes'], 1350)
        self.assertTrue(host.measured['Q1']['sampled_peak_not_absolute'])
        host.write_json.assert_not_called()

        # Real owner persistence callback preserves the transient loader peak.
        host.write({'phase': 'ACTIVE'})
        persisted = json.loads(json.dumps(host.write_json.call_args.args[1]))
        resumed = self.bare()
        resumed.measured = {**persisted, 'G1': copy.deepcopy(persisted['Q1'])}
        resumed.campaign_containers, resumed.assert_idle = Mock(return_value=[]), Mock()
        with patch('benchmark.host.collect_sample', return_value={'host': {'available_bytes': 32 * 1024**3}}):
            admitted = resumed.dispatch({'op': 'admit_mixed', 'measured_glm': 1350, 'measured_qwen': 850})
        self.assertEqual(admitted['caps'], {'G1': 1688, 'Q1': 1688})
        self.assertEqual(admitted['measured_required_demand']['Q1']['required_bytes'], 1350)
        self.assertEqual(admitted['usable_host_bytes_after_retirement'], 32 * 1024**3)
        self.assertTrue(admitted['private_receipt'].endswith('/mixed-manifests.json'))
        self.assertEqual([m['ram_cap_bytes'] for m in admitted['manifests']], [1688, 1688])
        self.assertEqual(resumed.write_json.call_args.args[1]['measured']['Q1']['load_phase_sample_count'], 1)

    def test_start_and_readiness_sample_before_return_and_http(self):
        host, events = self.bare(), []
        cid = '1' * 64
        host._exact = Mock()
        host.readiness_failure = Mock(return_value=None)
        host.telemetry = Mock(side_effect=lambda actual: events.append(('sample', actual)))
        with patch('benchmark.host.command', side_effect=lambda argv, *a: events.append(('start', argv[-1]))):
            host.start({'id': cid})
        self.assertEqual(events, [('start', cid), ('sample', cid)])
        events.clear()
        host.readiness_failure = Mock(return_value=None)
        host._readiness = Mock(side_effect=lambda actual: events.append(('http', actual)) or {'ready': False})
        self.assertEqual(host.readiness(cid, 5), {'ready': False})
        self.assertEqual(events, [('sample', cid), ('http', cid)])

    def test_terminal_immediately_after_start_persists_diagnosis_before_sampling(self):
        for oom in (False, True):
            with self.subTest(oom=oom):
                host = self.bare()
                cid = '1' * 64
                container = {'Id': cid, 'Name': '/benchrun-offline-g1', 'Image': 'sha256:'+'2'*64,
                    'Config': {'Labels': {'benchmark.campaign': host.campaign, 'benchmark.owner': 'llm-benchmark'}},
                    'HostConfig': {'RestartPolicy': {'Name': 'no'}},
                    'State': {'Running': False, 'Status': 'exited', 'OOMKilled': oom, 'ExitCode': 137 if oom else 1}}
                resource = {k: v for k, v in host.resource(container).items() if k != 'running'}
                host.owner.resources = [{'resource': resource, 'state': 'CREATED'}]
                host.docker_inspect = Mock(return_value=container)
                host._exact, host.telemetry, host.write_bytes = Mock(), Mock(), Mock()
                with patch('benchmark.host.command', return_value=SimpleNamespace(returncode=0, stdout=b'synthetic', stderr=b'')):
                    with self.assertRaisesRegex(ValueError, 'STOP_OOM' if oom else 'STOP_BACKEND_EXITED'):
                        host.start(resource)
                host.telemetry.assert_not_called()
                host.write_bytes.assert_called_once()
                saved = host.write_json.call_args
                self.assertEqual(saved.args[0], 'loads/' + cid + '-failure.json')
                self.assertEqual(saved.args[1]['state'], 'STOP_OOM' if oom else 'STOP_BACKEND_EXITED')

    def test_mixed_refuses_warm_only_evidence_even_with_required_components(self):
        host = self.bare()
        host.campaign_containers, host.assert_idle = Mock(return_value=[]), Mock()
        host.measured = {p: {'evidence_status': 'MEASURED_COMPONENTS', 'required_bytes': 100}
                         for p in ('G1', 'Q1')}
        with patch('benchmark.host.collect_sample') as collect:
            with self.assertRaisesRegex(ValueError, 'mixed_load_demand_evidence_unavailable'):
                host.dispatch({'op': 'admit_mixed', 'measured_glm': 100, 'measured_qwen': 100})
        collect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
