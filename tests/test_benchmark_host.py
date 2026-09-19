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
from benchmark.host import LinuxHost, HostBudget, serve, command
from benchmark.owner import WorkerVerificationPending
from tests.test_benchmark_owner import Fixture
from tests.test_benchmark_lifecycle import snapshot
from common.lifecycle_lease import acquire_lease, transition_in_progress


class HostTests(unittest.TestCase):
    def bare(self):
        host = LinuxHost.__new__(LinuxHost)
        host.campaign = 'benchrun-offline'
        host.log_root = '/data/logs/benchrun-offline'
        host.owner = SimpleNamespace(phase='ACTIVE', lease=Mock(), resources=[], original={})
        host.requests, host.manifests, host.samples = {}, {}, {}
        host.write_json = Mock()
        host.identity = Mock()
        host.budget = Mock()
        host.budget.request_timeout.return_value = 43
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


if __name__ == '__main__':
    unittest.main()
