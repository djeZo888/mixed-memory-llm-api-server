"""Serialized actual SSH/host path with mocked processes: synthetic/offline."""
import io
import json
from pathlib import Path
import shlex
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import runner

class Transport(unittest.TestCase):
    def test_arm_binds_source_and_transport_serializes_actual_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            digest = runner.arm(path, 'benchrun-offline-review')
            armed = runner.load_arm(path, digest)
            calls = []
            process = SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO('{"ok":true,"result":{"phase":"ACTIVE"}}\n'), wait=lambda timeout: 0)
            def run(argv, **kwargs):
                calls.append(('stage', argv, kwargs))
                return SimpleNamespace(returncode=0, stdout=b'{"staged":true}')
            def popen(argv, **kwargs):
                calls.append(('serve', argv, kwargs)); return process
            host = runner.SSHHost(armed, stage=True, popen=popen, run=run)
            payload = json.loads(calls[0][2]['input'])
            self.assertEqual(payload['arm']['source_files'], armed['source_files'])
            self.assertIn('scripts/benchmark/host.py', payload['files'])
            self.assertEqual(shlex.split(calls[0][1][-1])[-1], runner.STAGE)
            remote = shlex.split(calls[1][1][-1])
            self.assertEqual(remote, host.command)
            self.assertIn('/data/services/benchrun-offline-review/source/scripts/bench/benchmark-host.py', remote)
            self.assertIn('127.0.0.1:31002:127.0.0.1:31002', calls[1][1])
            self.assertEqual(host.call('begin', resume=False), {'phase': 'ACTIVE'})
            self.assertEqual(json.loads(process.stdin.getvalue()), {'op': 'begin', 'resume': False})
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                runner.load_arm(path, '0' * 64)
            with self.assertRaisesRegex(ValueError, 'arm_exists'):
                runner.arm(path, 'benchrun-offline-review')

    def test_failed_campaign_still_finishes_worker_verification(self):
        host = SimpleNamespace(call=lambda op, **kwargs: {'phase': 'POST_RELEASE_LAN_VERIFICATION_PENDING'}, close=lambda: None)
        campaign = SimpleNamespace(run=lambda **kwargs: (_ for _ in ()).throw(RuntimeError('synthetic stop')), emit=lambda x: None, record=lambda x: None)
        with tempfile.TemporaryDirectory() as directory, patch.object(runner, 'load_arm', return_value={}), patch.object(runner, 'run_preflight'), patch.object(runner.os, 'geteuid', return_value=501), patch('runtime.sglang38_file_auth.read_key', return_value='synthetic'), patch.object(runner, 'SSHHost', return_value=host), patch.object(runner, 'Campaign', return_value=campaign), patch('benchmark.worker_verify.verify', return_value={'checks': {}}) as verify:
            result = runner.main(['run', '--state', directory, '--reviewed-arm-sha256', 'synthetic', '--inference-key-file', 'synthetic', '--control-key-file', 'synthetic'])
            self.assertEqual(result, 1)
            verify.assert_called_once()

    def test_handled_stop_reports_independent_restoration_verification_failure(self):
        emitted, phases = [], []
        host = SimpleNamespace(call=lambda op, **kwargs: {'phase': 'POST_RELEASE_LAN_VERIFICATION_PENDING'}, close=lambda: None)
        campaign = SimpleNamespace(run=lambda **kwargs: (_ for _ in ()).throw(RuntimeError('synthetic stop')),
                                   emit=emitted.append, record=phases.append)
        with tempfile.TemporaryDirectory() as directory, patch.object(runner, 'load_arm', return_value={}), patch.object(runner, 'run_preflight'), patch.object(runner.os, 'geteuid', return_value=501), patch('runtime.sglang38_file_auth.read_key', return_value='synthetic'), patch.object(runner, 'SSHHost', return_value=host), patch.object(runner, 'Campaign', return_value=campaign), patch('benchmark.worker_verify.verify', side_effect=ValueError('synthetic verification refusal')):
            with self.assertRaises(ValueError):
                runner.main(['run', '--state', directory, '--reviewed-arm-sha256', 'synthetic', '--inference-key-file', 'synthetic', '--control-key-file', 'synthetic'])
        self.assertEqual(phases, ['RESTORATION_VERIFICATION_FAILED'])
        self.assertEqual(emitted[-1]['type'], 'worker_restoration_verification_failure')
        self.assertEqual(emitted[-1]['measurement_error_class'], 'RuntimeError')
        self.assertEqual(emitted[-1]['error_class'], 'ValueError')

    def test_missing_reviewed_offload_counts_stops_before_keys_or_ssh(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runner, 'load_arm', return_value={}), patch.object(runner.profiles, 'read_config', return_value={"glm_offload_expectation": {"evidence_status": "HOLD_LOG_COUNT_SEMANTICS"}}), patch('runtime.sglang38_file_auth.read_key') as read, patch.object(runner, 'SSHHost') as ssh:
            with self.assertRaisesRegex(RuntimeError, 'BLOCKED_GLM_OFFLOAD'):
                runner.main(['run', '--state', directory, '--reviewed-arm-sha256', 'synthetic', '--inference-key-file', 'synthetic', '--control-key-file', 'synthetic'])
            read.assert_not_called();ssh.assert_not_called()
            self.assertFalse((Path(directory) / 'execution.json').exists())

if __name__ == '__main__': unittest.main()
