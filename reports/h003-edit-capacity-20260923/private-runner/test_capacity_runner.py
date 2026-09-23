"""Offline settlement/telemetry failure checks. No Docker, SSH or GPU execution."""
import copy
import base64
import hashlib
import io
import json
from pathlib import Path
import unittest
from capacity_runner import identity, probe_command, settle_private_case, violations, admission_closed, memory_pass
from candidate_codec import process


class CapacitySettlement(unittest.TestCase):
    def test_actual_candidate_codec_prepare_deliver_without_native_request(self):
        from PIL import Image
        from candidate_codec import process
        def png(size):
            stream = io.BytesIO()
            Image.new('RGB', size, 'red').save(stream, format='PNG')
            return stream.getvalue()
        source = Path('repo/scripts/image_api/protocol.py').read_bytes()
        raw = png((1024, 1024))
        digest = hashlib.sha256(raw).hexdigest()
        payload = {'action': 'prepare', 'protocol': {'data': base64.b64encode(source).decode(), 'sha256': hashlib.sha256(source).hexdigest()},
                   'originals': [{'data': base64.b64encode(raw).decode()}],
                   'case': {'prompt': 'x', 'size': '1024x1024', 'native_size': '1024x1024', 'crop_bottom': 0,
                            'seed': 46, 'references': [{'sha256': digest, 'working_sha256': digest}]}}
        prepared = process(payload)
        self.assertEqual(prepared['native']['seed'], 46)
        self.assertEqual(base64.b64decode(prepared['working'][0]['data']), raw)
        response = json.dumps({'data': [{'b64_json': base64.b64encode(raw).decode()}]}).encode()
        delivered = process({**payload, 'action': 'deliver', 'response': base64.b64encode(response).decode()})
        self.assertEqual(delivered['seed'], 46)
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(delivered['delivered']))).size, (1024, 1024))
        payload['case']['references'][0]['working_sha256'] = '0' * 64
        with self.assertRaises(AssertionError):
            process(payload)  # Preparation refusal happens before any dispatch.

    def test_success_requires_all_settlement_checks(self):
        events = []
        receipt = {'exit_code': 0}
        def check():
            events.extend(['decoded', 'probe_absent', 'same_pids', 'same_cgroup', 'guards', 'reserve'])
            return {item: True for item in events}
        self.assertTrue(settle_private_case(receipt, check))
        self.assertEqual(events[-1], 'reserve')
        self.assertTrue(receipt['native_operation_settled'])

    def test_timeout_kill_or_unknown_exit_never_passes(self):
        for code in (None, 1, 124, 137, -9):
            receipt = {'exit_code': code}
            self.assertFalse(settle_private_case(receipt, lambda: {'all_checks': True}))
            self.assertFalse(receipt['native_operation_settled'])

    def test_missing_probe_or_changed_identity_or_failed_guard_never_passes(self):
        for failed in ('decoded_success', 'owned_probe_absent', 'same_models', 'api_remains_stopped', 'fresh_guards_and_reserve'):
            receipt = {'exit_code': 0}
            self.assertFalse(settle_private_case(receipt, lambda: {failed: False}))
            self.assertIn(failed, receipt['settlement_checks'])

    def test_check_exception_retained_for_final_receipt(self):
        def check():
            raise RuntimeError('guard failed')
        receipt = {'exit_code': 0}
        self.assertFalse(settle_private_case(receipt, check))
        self.assertEqual(receipt['settlement_error_type'], 'RuntimeError')

    def test_running_wrapper_refused_even_if_ready_get_preceded_racing_admission(self):
        self.assertFalse(admission_closed({'ActiveState': 'active', 'MainPID': '100', 'Result': 'success', 'ExecMainStatus': '0'}))
        self.assertFalse(admission_closed({'ActiveState': 'deactivating', 'MainPID': '100', 'Result': 'success', 'ExecMainStatus': '0'}))
        self.assertTrue(admission_closed({'ActiveState': 'inactive', 'MainPID': '0', 'Result': 'success', 'ExecMainStatus': '0'}))

    def test_late_error_or_unsettled_telemetry_cannot_pass(self):
        good = {'native_operation_settled': True, 'violations': [], 'checkpoint_api_stopped_backend_healthy': True, 'telemetry_durable_settled': True}
        self.assertTrue(memory_pass(good))
        for key in ('runner_error_type', 'settlement_error_type', 'telemetry_error_type', 'final_observation_error_type', 'evidence_error_type'):
            self.assertFalse(memory_pass({**good, key: 'InjectedFailure'}))
        self.assertFalse(memory_pass({**good, 'telemetry_durable_settled': False}))
        self.assertFalse(memory_pass({**good, 'checkpoint_api_stopped_backend_healthy': False}))

    def test_in_container_term_kill_and_fixed_request_path(self):
        command = probe_command('exact-container', '/work/evidence/run/H003-CAPACITY-C01/probe.py')
        self.assertEqual(command[:7], ['docker', 'exec', 'exact-container', '/usr/bin/timeout', '--signal=TERM', '--kill-after=5s', '840s'])
        self.assertEqual(command[-3:-1], ['-I', '-B'])

    def test_context_comparison_ignores_memory_bytes(self):
        self.assertEqual(identity([['gpu', '123', '100']]), identity([['gpu', '123', '200']]))
        self.assertNotEqual(identity([['gpu', '123', '100']]), identity([['gpu', '124', '100']]))

    def test_fresh_swap_events_and_reserve_failures_detected(self):
        first = {'devices': [['a', '100', '20'], ['b', '100', '20'], ['ada', '100', '20']],
                 'host_available': 20, 'host_total': 100, 'swap': {'pswpin': 308, 'pswpout': 5323},
                 'processes': [['ada', '123', '80']],
                 'cgroups': {'q1': {'memory.swap.current': 155086848, 'memory.events': {'max': 441}, 'memory.swap.events': {'fail': 0}}}}
        self.assertEqual(violations(first, first), [])
        current = copy.deepcopy(first)
        current['devices'][2][2] = '4'
        current['host_available'] = 14
        current['swap']['pswpout'] += 1
        current['cgroups']['q1']['memory.swap.current'] += 4096
        current['cgroups']['q1']['memory.events']['max'] += 1
        self.assertEqual(set(violations(current, first)), {'device_reserve', 'host_reserve', 'new_global_swap_activity', 'q1:swap_changed', 'q1:memory_events_changed'})


if __name__ == '__main__':
    unittest.main()
