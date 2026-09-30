"""Offline admission and exact failure settlement checks; no host contacts."""
import importlib.util
import io
import contextlib
import json
from pathlib import Path
import types
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('short_test_client', Path(__file__).with_name('client.py'))
c = importlib.util.module_from_spec(spec);spec.loader.exec_module(c)


class ShortTests(unittest.TestCase):
    def test_expired_authority_refuses_before_owner_or_network(self):
        transport = Mock()
        with patch.object(c, 'setup', return_value=(Mock(), Mock(), transport, {'admit_before_epoch': 0})), self.assertRaisesRegex(RuntimeError, 'short_admission_closed'):
            c.run()
        transport.check_identity.assert_not_called()
        transport.adapter.assert_not_called()

    def test_unready_owner_refuses_before_reader_or_inference(self):
        transport = Mock();transport.check_identity.side_effect = RuntimeError('production_owner_changed_or_held')
        cfg = {'admit_before_epoch': 10**12, 'active_cap_seconds': 900, 'hard_end_epoch': 10**12}
        with patch.object(c, 'setup', return_value=(Mock(), Mock(), transport, cfg)), patch.object(c, 'module') as loader, self.assertRaisesRegex(RuntimeError, 'production_owner_changed_or_held'):
            c.run()
        loader.assert_not_called();transport.adapter.assert_not_called()

    def settlement(self, result, state=None, actual=None):
        identity = {'launch_id': 'our-launch', 'supervisor': {'pid': 123, 'invocation_id': 'our-invocation'}}
        state = state or {**identity, 'status': 'RUNNING'}
        final = {'status': 'SETTLED', 'settlement': {'pid_released': True, 'cgroup_empty': True, 'gpu_compute_empty': True}}
        owner = types.SimpleNamespace(BASE=Path('/fixture'), UNIT='fixture.service', read=Mock(side_effect=[result, state, final]), run=Mock(return_value=actual or 'MainPID=123\nInvocationID=our-invocation\n'))
        return owner, (owner, Mock(), Mock(), {'production_identity': identity})

    def test_local_busy_or_own_complete_does_not_stop_model(self):
        for status in ('BUSY_NOT_SUBMITTED', 'PASS_KEEP_WARM', 'FAILED_NO_RETRY'):
            owner, values = self.settlement({'status': status, 'request_may_be_active': False})
            with patch.object(c, 'setup', return_value=values):c.settle()
            owner.run.assert_not_called()
            self.assertEqual(owner.read.call_count, 1)

    def test_ambiguous_request_uses_exact_existing_owner_stop(self):
        owner, values = self.settlement({'request_may_be_active': True})
        with patch.object(c, 'setup', return_value=values):c.settle()
        self.assertEqual(owner.run.call_args.args, (['systemctl', 'stop', 'fixture.service'], 55))

    def test_replacement_launch_is_untouched(self):
        owner, values = self.settlement({'request_may_be_active': True}, state={'launch_id': 'replacement'})
        with patch.object(c, 'setup', return_value=values), self.assertRaisesRegex(RuntimeError, 'settlement_owner_changed'):c.settle()
        owner.run.assert_not_called()

    def test_replacement_unit_is_untouched(self):
        owner, values = self.settlement({'request_may_be_active': True}, actual='MainPID=456\nInvocationID=replacement\n')
        with patch.object(c, 'setup', return_value=values), self.assertRaisesRegex(RuntimeError, 'settlement_supervisor_changed'):c.settle()
        self.assertEqual(owner.run.call_count, 1)

    def test_cli_omits_exception_payload(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(c.sys, 'argv', ['client.py', 'run']), patch.object(c, 'run', side_effect=RuntimeError('PRIVATE-SENTINEL')), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(c.main(), 1)
        self.assertEqual(json.loads(out.getvalue()), {'status': 'REFUSED_OR_FAILED', 'error_type': 'RuntimeError'})
        self.assertEqual(err.getvalue(), '')


if __name__ == '__main__':unittest.main()
