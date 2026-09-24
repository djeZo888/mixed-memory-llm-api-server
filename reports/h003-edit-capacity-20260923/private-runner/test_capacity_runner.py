"""Offline settlement/telemetry failure checks. No Docker, SSH or GPU execution."""
import copy
import base64
import hashlib
import io
import json
from pathlib import Path
import unittest
import tempfile
from capacity_runner import approved_c03_reserve_settlement, KNOWN_C03_RESERVE_SHA, settled_case_continuation, admission_proved, AUTHORITY_SHA, FAILED_WINDOW_SHA, INSTALLED_SOURCES, RECONCILIATION_TYPE, identity, probe_command, settle_private_case, violations, admission_closed, memory_pass, require_previous_settlement
from candidate_codec import process
from reconcile_capacity_window import process_identity


class CapacitySettlement(unittest.TestCase):
    def test_ambiguous_previous_dispatch_blocks_even_independent_c04(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stage = root / 'work/evidence/run/H003-CAPACITY-C01'
            stage.mkdir(parents=True)
            with self.assertRaises(RuntimeError):
                require_previous_settlement(root, 'run', 'C04')
            (root / 'receipts').mkdir()
            receipt = root / 'receipts/H003-CAPACITY-C01-receipt.json'
            receipt.write_text(json.dumps({'dispatches': 1, 'native_operation_settled': False}))
            with self.assertRaises(RuntimeError):
                require_previous_settlement(root, 'run', 'C04')
            receipt.write_text(json.dumps({'dispatches': 1, 'native_operation_settled': True, 'qualification_memory_pass': True}))
            require_previous_settlement(root, 'run', 'C04')
            with self.assertRaises(RuntimeError):
                require_previous_settlement(root, 'run', 'C01')

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

    def test_task_specific_reconciliation_never_accepts_generic_killed_exit(self):
        unit = {'ActiveState': 'inactive', 'SubState': 'dead', 'MainPID': '0',
                'Result': 'success', 'ExecMainCode': '2', 'ExecMainStatus': '15'}
        proof = {'evidence_type': RECONCILIATION_TYPE, 'clean_stop_proved': False,
                 'asgi_cleanup': 'UNPROVEN', 'original_failed_receipt_sha256': FAILED_WINDOW_SHA,
                 'authority_sha256': AUTHORITY_SHA, 'installed_source_sha256': INSTALLED_SOURCES,
                 'no_inflight_native_operation_proved': True, 'coordinated_no_call_interval': True,
                 'old_api_process_absent': True, 'loopback_api_listener_absent': True,
                 'canonical_lease': True, 'private_requests': 0, 'api_after': unit.copy()}
        self.assertFalse(admission_closed(unit))  # Existing strict check preserved.
        self.assertTrue(admission_proved(unit, proof, 'C01'))
        self.assertFalse(admission_proved(unit, proof, 'C02'))
        for key in proof:
            missing = dict(proof); missing.pop(key)
            self.assertFalse(admission_proved(unit, missing, 'C01'), key)
        for field, value in [('MainPID', '22'), ('Result', 'signal'), ('ExecMainCode', '3'),
                             ('ExecMainStatus', '9'), ('SubState', 'failed')]:
            changed = {**unit, field: value}
            self.assertFalse(admission_proved(changed, {**proof, 'api_after': changed}, 'C01'), field)
        for key, value in [('authority_sha256', 'unknown'), ('original_failed_receipt_sha256', 'unknown'),
                           ('installed_source_sha256', {}), ('coordinated_no_call_interval', False),
                           ('asgi_cleanup', 'PROVED'), ('private_requests', 1)]:
            self.assertFalse(admission_proved(unit, {**proof, key: value}, 'C01'), key)
        clean = {**unit, 'ExecMainCode': '1', 'ExecMainStatus': '0'}
        self.assertTrue(admission_proved(clean, {'clean_stop_proved': True}, 'C01'))

    def test_c02_continuation_requires_successful_settled_c01_same_window(self):
        unit = {'MainPID': '0'}
        good = {'case': 'C01', 'accepted_model_executions': 1, 'dispatches': 1,
                'qualification_memory_pass': True, 'native_operation_settled': True,
                'violations': [], 'checkpoint_api_stopped_backend_healthy': True,
                'telemetry_durable_settled': True, 'admission_receipt_sha256': 'bound', 'api_after': unit}
        self.assertTrue(settled_case_continuation(good, 'C02', 'bound', unit))
        for key in good:
            broken = dict(good); broken.pop(key)
            if key == 'violations': broken[key] = ['reserve']
            self.assertFalse(settled_case_continuation(broken, 'C02', 'bound', unit), key)
        self.assertFalse(settled_case_continuation(good, 'C03', 'bound', unit))
        self.assertTrue(settled_case_continuation({**good, 'case': 'C02'}, 'C03', 'bound', unit))
        self.assertFalse(settled_case_continuation({**good, 'case': 'C02'}, 'C04', 'bound', unit))
        self.assertTrue(settled_case_continuation({**good, 'case': 'C03'}, 'C04', 'bound', unit))
        self.assertFalse(settled_case_continuation(good, 'C02', 'wrong', unit))
        self.assertFalse(settled_case_continuation({**good, 'runner_error_type': 'late'}, 'C02', 'bound', unit))

    def test_only_exact_approved_settled_c03_reserve_miss_can_continue_c04(self):
        good = {'case': 'C03', 'exit_code': 0, 'dispatches': 1, 'accepted_model_executions': 1,
                'qualification_memory_pass': False, 'violations': ['device_reserve'],
                'native_operation_settled': True, 'checkpoint_api_stopped_backend_healthy': True,
                'telemetry_durable_settled': True, 'admission_receipt_sha256': 'window', 'api_after': {}}
        self.assertTrue(approved_c03_reserve_settlement(good, KNOWN_C03_RESERVE_SHA))
        self.assertFalse(memory_pass(good))  # C03 remains failed.
        self.assertFalse(approved_c03_reserve_settlement(good, None))
        self.assertFalse(approved_c03_reserve_settlement(good, 'other'))
        self.assertFalse(settled_case_continuation(good, 'C04', 'window', {}))
        self.assertTrue(settled_case_continuation(good, 'C04', 'window', {}, KNOWN_C03_RESERVE_SHA))
        for key,value in [('native_operation_settled',False),('telemetry_durable_settled',False),
                          ('runner_error_type','late'),('violations',['device_reserve','new_global_swap_activity']),
                          ('exit_code',124),('case','C02')]:
            self.assertFalse(approved_c03_reserve_settlement({**good,key:value}, KNOWN_C03_RESERVE_SHA),key)

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
        live = [('gpu', '123', '100')]
        persisted = json.loads(json.dumps(live))
        self.assertEqual(process_identity(live), process_identity(persisted))
        self.assertNotEqual(process_identity(live), process_identity([['gpu', '124', '100']]))
        self.assertEqual(identity(live), identity([['gpu', '123', '200']]))
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
