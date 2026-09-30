"""Offline intentional-stop source transition fixtures; no host/model operations."""
import contextlib
import copy
import datetime
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

spec = importlib.util.spec_from_file_location(
    'same_boot_source_fixture', Path(__file__).with_name('test_mimo_new_boot_recovery.py'))
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
o, sha, BOOT = f.o, f.sha, f.NEW


class SameBootSourceTests(unittest.TestCase):
    def setUp(self):
        f.RecoveryTests.setUp(self)
        self.state.update(status='RUNNING', request_hold=False, boot_id=BOOT,
                          proxy_started=True,
                          supervisor={'unit': o.UNIT, 'pid': 605245,
                                      'invocation_id': 'prior-invocation'},
                          proxy={'pid': 777446, 'pid_start_ticks': '12345',
                                 'parent_pid': 605245})
        self.state['native']['pid_start_ticks'] = '23456'
        self.proxy = {k: copy.deepcopy(self.state[k]) for k in ('boot_id', 'launch_id', 'native')}
        self.proxy.update(schema_version=2, **self.state['proxy'], active_requests=0, quarantined=False)
        self.guard = dict(schema_version=2, status='ok', boot_id=BOOT,
                          manifest_sha256=o.digest(self.old), selection=self.selected,
                          supervisor=self.state['supervisor'], native=self.state['native'],
                          proxy=self.state['proxy'], proxy_disposition=self.proxy,
                          hardware_latched=False,
                          hardware_proof={'hardware_latched': False,
                                          'identity': [[o.GPU, BOOT, 'validated']]},
                          observed_monotonic_s=time.monotonic(),
                          observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        self.running = copy.deepcopy(self.state)
        self.delta = {str(self.base / 'source/owner.py'): {
            'old': self.old['source_sha256'][str(self.base / 'source/owner.py')],
            'new': self.new['source_sha256'][str(self.base / 'source/owner.py')]}}
        self.save('manifest.json', self.old)
        self.save('state.json', self.state)
        self.save('proxy-state.json', self.proxy)
        self.save('guard.json', self.guard)
        self.save('source-successor-delta.json', self.delta)
        (self.base / 'source/owner.py').write_bytes(b'old-source')
        self.delta_sha = sha((self.base / 'source-successor-delta.json').read_bytes())
        self.hardware = self.stack.enter_context(patch.object(o, 'latch', return_value={
            'hardware_latched': False, 'identity': [[o.GPU, BOOT, 'validated']]}))
        self.native = {'Id': self.state['native']['container_id'],
                       'State': {'Running': True, 'Pid': self.state['native']['pid'], 'Status': 'running'}}
        self.stack.enter_context(patch.object(o, 'inspect', return_value=self.native))
        self.stack.enter_context(patch.object(o, 'exact_container', side_effect=lambda c, *a: c))
        self.os_run = self.stack.enter_context(patch.object(o, 'run', return_value=
            'MainPID=605245\nInvocationID=prior-invocation\nActiveState=active\nJob=\n'
            'ControlGroup=/system.slice/' + o.UNIT + '\n'))
        real_exists = Path.exists
        self.stack.enter_context(patch.object(Path, 'exists', lambda p:
            True if str(p) in ('/proc/605646', '/proc/777446') else real_exists(p)))
        real_read_text = Path.read_text
        self.stack.enter_context(patch.object(Path, 'read_text', lambda p, *a, **kw:
            '0::/system.slice/' + o.UNIT if str(p) == '/proc/605245/cgroup' else real_read_text(p, *a, **kw)))
        self.stack.enter_context(patch.object(o, 'ticks', side_effect=lambda pid:
            '23456' if pid == self.state['native']['pid'] else '12345'))
        self.physical = self.stack.enter_context(patch.object(o, 'settled_source_absence',
            return_value={'old_boot_id': BOOT, 'current_boot_id': BOOT,
                          'physical_release': 'NORMAL_OWNER_STOP',
                          'prior_request_outcome': 'IDLE_INTENTIONAL_STOP'}))

    def save(self, name, value):
        (self.base / name).write_text(json.dumps(value))

    def prepare(self):
        return o.prepare_source_stop(sha((self.base / 'state.json').read_bytes()), BOOT,
                                     o.digest(self.old), self.delta_sha)

    def finish_stop(self):
        self.state = copy.deepcopy(self.running)
        self.state.update(status='SETTLED', request_hold=False,
                          settlement={'pid_released': True, 'cgroup_empty': True,
                                      'gpu_compute_empty': True},
                          primary_failure={'code': 'owner_interrupted', 'phase': 'RUNNING',
                                           'operation': 'cycle_sleep',
                                           'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
        self.save('state.json', self.state)
        self.save('source-successor-prior-manifest.json', self.old)
        (self.base / 'source-successor-prior-owner.py').write_bytes(b'old-source')
        self.save('manifest.json', self.new)
        (self.base / 'source/owner.py').write_bytes(b'new-reviewed-source')

    def reconcile(self, *, same_boot=True):
        return o.reconcile_settled_source(sha((self.base / 'state.json').read_bytes()), BOOT,
            o.digest(self.new), self.delta_sha, same_boot=same_boot)

    def test_prepare_archives_exact_running_evidence_without_stopping_or_rewriting_owner(self):
        before = {n: (self.base / n).read_bytes() for n in
                  ('state.json', 'proxy-state.json', 'guard.json', 'selection.json', 'manifest.json')}
        self.prepare()
        self.assertTrue(self.os_run.call_args_list)
        self.assertTrue(all(call.args[0][:2] == ['systemctl', 'show']
                            for call in self.os_run.call_args_list))
        self.assertNotIn('evidence', self.hardware.call_args.kwargs)
        for name, raw in before.items():
            self.assertEqual((self.base / name).read_bytes(), raw)
        intent = self.base / o.source_stop_name(self.state)
        self.assertTrue(intent.exists())
        self.assertEqual(intent.stat().st_mode & 0o777, 0o400)
        self.assertIn('RUNNING', intent.read_text())
        with self.assertRaises((o.OwnerRefusal, FileExistsError)):
            self.prepare()

    def test_prepare_requires_running_idle_clean_launch_and_exact_guard(self):
        cases = [('held', 'state', {'status': 'HELD'}),
                 ('stopped', 'state', {'status': 'SETTLED'}),
                 ('request_hold', 'state', {'request_hold': True}),
                 ('old_failure', 'state', {'primary_failure': {'code': 'mandatory_guard_timeout'}}),
                 ('active', 'proxy', {'active_requests': 1}),
                 ('unknown', 'proxy', {'active_requests': None}),
                 ('boolean', 'proxy', {'active_requests': False}),
                 ('quarantined', 'proxy', {'quarantined': True}),
                 ('unknown_quarantine', 'proxy', {'quarantined': None}),
                 ('wrong_proxy', 'proxy', {'pid_start_ticks': 'other'}),
                 ('guard_owner', 'guard', {'supervisor': {'pid': 1}}),
                 ('guard_manifest', 'guard', {'manifest_sha256': 'e' * 64}),
                 ('guard_latch', 'guard', {'hardware_latched': None}),
                 ('stale_guard', 'guard', {'observed_monotonic_s': time.monotonic() - 60,
                     'observed_at': (datetime.datetime.now(datetime.timezone.utc) -
                                     datetime.timedelta(seconds=60)).isoformat()})]
        originals = {'state': self.state, 'proxy': self.proxy, 'guard': self.guard}
        names = {'state': 'state.json', 'proxy': 'proxy-state.json', 'guard': 'guard.json'}
        for label, target, change in cases:
            with self.subTest(case=label):
                self.save(names[target], {**originals[target], **change})
                try:
                    with self.assertRaises(o.OwnerRefusal):
                        self.prepare()
                    self.assertFalse((self.base / o.source_stop_name(self.state)).exists())
                finally:
                    self.save(names[target], originals[target])

    def test_prepare_positive_or_unknown_hardware_never_creates_intent(self):
        for value in (True, None):
            with self.subTest(latched=value):
                self.hardware.return_value = {'hardware_latched': value,
                    'identity': [[o.GPU, BOOT, 'validated']]}
                with self.assertRaises(o.OwnerRefusal):
                    self.prepare()
                self.assertFalse((self.base / o.source_stop_name(self.state)).exists())

    def test_prepare_requires_exact_reviewed_input_hashes(self):
        arguments = [sha((self.base / 'state.json').read_bytes()), BOOT,
                     o.digest(self.old), self.delta_sha]
        for index in (0, 2, 3):
            with self.subTest(argument=index):
                changed = list(arguments)
                changed[index] = 'e' * 64
                with self.assertRaises(o.OwnerRefusal):
                    o.prepare_source_stop(*changed)
                self.assertFalse((self.base / o.source_stop_name(self.state)).exists())

    def test_prepared_intent_cannot_be_rebound_to_other_launch_manifest_boot_or_delta(self):
        intent = self.prepare()
        self.finish_stop()
        name = o.source_stop_name(self.state)
        (self.base / name).chmod(0o600)
        for change in ({'launch_id': 'e' * 32}, {'current_boot_id': f.OLD},
                       {'prior_manifest_sha256': 'e' * 64}, {'prior_state_digest': 'e' * 64},
                       {'reviewed_delta_sha256': 'e' * 64}):
            with self.subTest(change=change):
                self.save(name, {**intent, **change})
                with self.assertRaises(o.OwnerRefusal):
                    self.reconcile()
                self.assertEqual(o.read(self.base / 'selection.json'), self.selected)
        self.save(name, intent)

    def test_source_config_selection_and_reviewed_delta_drift_refuse_before_archive(self):
        self.prepare()
        self.finish_stop()
        cases = ('source_bytes', 'context', 'runtime', 'config', 'selection', 'delta')
        for case in cases:
            with self.subTest(case=case):
                original_new, original_delta_sha = self.new, self.delta_sha
                self.new = copy.deepcopy(self.new)
                try:
                    if case == 'source_bytes':
                        (self.base / 'source/owner.py').write_bytes(b'unreviewed-bytes')
                    elif case in ('context', 'runtime', 'config'):
                        self.new[{'context': 'context', 'runtime': 'runtime_revision',
                                  'config': 'native_argv'}[case]] = 'unreviewed-change'
                        self.save('manifest.json', self.new)
                    elif case == 'selection':
                        self.save('selection.json', {**self.selected, 'generation': 13})
                    else:
                        # Same semantic delta with different reviewed raw bytes must
                        # still fail the pre-stop exact digest binding.
                        path = self.base / 'source-successor-delta.json'
                        path.write_text(json.dumps(self.delta, indent=2))
                        self.delta_sha = sha(path.read_bytes())
                    with self.assertRaises(o.OwnerRefusal):
                        self.reconcile()
                    archive, receipt, _ = o.settled_source_names(BOOT, o.digest(self.new))
                    self.assertFalse((self.base / archive).exists())
                    self.assertFalse((self.base / receipt).exists())
                    self.assertEqual(o.read(self.base / 'state.json'), self.state)
                finally:
                    self.new, self.delta_sha = original_new, original_delta_sha
                    self.save('manifest.json', self.new)
                    self.save('selection.json', self.selected)
                    self.save('source-successor-delta.json', self.delta)
                    (self.base / 'source/owner.py').write_bytes(b'new-reviewed-source')

    def test_clean_normal_stop_reconciles_without_erasing_predecessor_outcome(self):
        self.prepare()
        self.finish_stop()
        prior = (self.base / 'state.json').read_bytes()
        receipt = self.reconcile()
        self.assertEqual(receipt['transition'], 'SAME_BOOT_INTENTIONAL_STOP')
        self.assertEqual(receipt['physical_absence']['physical_release'], 'NORMAL_OWNER_STOP')
        self.assertEqual(receipt['prior_request_outcome'], 'IDLE_INTENTIONAL_STOP')
        self.assertEqual((self.base / 'state.json').read_bytes(), prior)
        archive = o.read(self.base / receipt['archive_name'])
        self.assertEqual(archive['files']['state.json'].encode(), prior)
        self.assertEqual(json.loads(archive['files']['state.json'])['primary_failure'],
                         self.state['primary_failure'])
        self.assertEqual(receipt['selection']['generation'], self.selected['generation'])
        actual, old = o.settled_source_for_start(self.new, receipt['selection'], self.state)
        self.assertEqual(old, self.old)
        o.assert_launch_admission(self.new, receipt['selection'], self.state, actual)
        self.physical.assert_called_once()
        self.assertIs(self.physical.call_args.kwargs['same_boot'], True)
        with self.assertRaises((o.OwnerRefusal, FileExistsError)):
            self.reconcile()

    def test_stopped_state_without_prepared_intent_cannot_be_promoted(self):
        self.finish_stop()
        with self.assertRaises((o.OwnerRefusal, FileNotFoundError)):
            self.reconcile()
        self.assertEqual(o.read(self.base / 'selection.json'), self.selected)

    def test_failed_or_uncertain_stops_refuse_and_preserve_history(self):
        self.prepare()
        self.finish_stop()
        original = copy.deepcopy(self.state)
        changes = [{'request_hold': True},
                   {'primary_failure': None},
                   {'primary_failure': {'code': 'mandatory_guard_timeout', 'phase': 'RUNNING'}},
                   {'primary_failure': {'code': 'owner_interrupted', 'phase': 'LOADING'}},
                   {'settlement_failure': {'code': 'command_timeout'}},
                   {'settlement_recheck_failure': {'code': 'settlement_lease_deadline'}},
                   {'receipt_failure': {'code': 'os_error'}}]
        for change in changes:
            with self.subTest(change=change):
                candidate = {**copy.deepcopy(original), **change}
                self.save('state.json', candidate)
                before = (self.base / 'state.json').read_bytes()
                with self.assertRaises(o.OwnerRefusal):
                    self.reconcile()
                self.assertEqual((self.base / 'state.json').read_bytes(), before)
                self.assertEqual(o.read(self.base / 'selection.json'), self.selected)
        self.save('state.json', original)

    def test_final_proxy_requires_exact_terminal_identity_and_known_zero_work(self):
        self.prepare()
        self.finish_stop()
        changes = [{'schema_version': 1}, {'active_requests': 1}, {'active_requests': None},
                   {'active_requests': False}, {'quarantined': True}, {'quarantined': None},
                   {'pid_start_ticks': 'other'}, {'parent_pid': 1}, {'pid': 1},
                   {'launch_id': 'b' * 32}, {'boot_id': f.OLD}, {'native': {}}]
        for change in changes:
            with self.subTest(change=change):
                self.save('proxy-state.json', {**self.proxy, **change})
                with self.assertRaises(o.OwnerRefusal):
                    self.reconcile()
                self.assertEqual(o.read(self.base / 'selection.json'), self.selected)
        self.save('proxy-state.json', self.proxy)

    def test_current_hardware_positive_or_unknown_refuses_reconcile_before_archive(self):
        self.prepare()
        self.finish_stop()
        for value in (True, None):
            with self.subTest(latched=value):
                self.hardware.return_value = {'hardware_latched': value,
                    'identity': [[o.GPU, BOOT, 'validated']]}
                with self.assertRaises(o.OwnerRefusal):
                    self.reconcile()
                archive, receipt, _ = o.settled_source_names(BOOT, o.digest(self.new))
                self.assertFalse((self.base / archive).exists())
                self.assertFalse((self.base / receipt).exists())
                self.assertEqual(o.read(self.base / 'selection.json'), self.selected)

    def test_receipt_and_archive_drift_cannot_authorize_successor(self):
        self.prepare()
        self.finish_stop()
        receipt = self.reconcile()
        _, receipt_name, _ = o.settled_source_names(BOOT, o.digest(self.new))
        (self.base / receipt_name).chmod(0o600)  # Deliberate fixture corruption only.
        changes = [{'transition': 'NEW_BOOT'}, {'prior_request_outcome': 'FAILED_OR_UNKNOWN'},
                   {'current_boot_id': f.OLD}, {'prior_state_digest': 'e' * 64},
                   {'reviewed_delta_sha256': 'e' * 64}, {'consumed_name': 'other.json'},
                   {'manifest_sha256': 'e' * 64},
                   {'physical_absence': {**receipt['physical_absence'], 'physical_release': 'REBOOT'}}]
        for change in changes:
            with self.subTest(change=change):
                self.save(receipt_name, {**receipt, **change})
                with self.assertRaises(o.OwnerRefusal):
                    o.settled_source_for_start(self.new, receipt['selection'], self.state)
        self.save(receipt_name, receipt)
        for change in ({'launch_id': 'd' * 32}, {'boot_id': f.OLD}, {'request_hold': True}):
            with self.subTest(previous=change), self.assertRaises(o.OwnerRefusal):
                o.settled_source_for_start(self.new, receipt['selection'], {**self.state, **change})
        (self.base / receipt['consumed_name']).write_text('{}')
        with self.assertRaises(o.OwnerRefusal):
            o.settled_source_for_start(self.new, receipt['selection'], self.state)

    def test_start_preflight_failure_preserves_predecessor_then_consumes_and_renames_once(self):
        self.prepare()
        self.finish_stop()
        receipt = self.reconcile()
        before = (self.base / 'state.json').read_bytes()
        consumed = self.base / receipt['consumed_name']

        class EndFixture(RuntimeError):
            pass

        old_container = {'Id': 'c' * 64, 'State': {'Running': False, 'Pid': 0}}
        new_container = {'Id': 'd' * 64, 'State': {'Running': True, 'Pid': 44}}

        def run(argv, *args):
            if argv[:2] == ['systemctl', 'show']:
                return 'MainPID=0\nActiveState=inactive\n'
            if argv[:2] == ['docker', 'ps']:
                return 'c' * 64
            if argv == ['fixture-create']:
                return 'd' * 64
            return ''

        with contextlib.ExitStack() as stack:
            values = dict(unit_identity=Mock(return_value={'pid': os.getpid(), 'invocation_id': 'new'}),
                run=Mock(side_effect=run), memory=Mock(return_value={'MemAvailable': 1000, 'MemTotal': 1000}),
                temperature_limit=Mock(return_value=85),
                sample_guard=Mock(return_value={'hardware_validation': {'fixture': 'fresh-sample'}}),
                memory_policy=Mock(), latch=Mock(side_effect=[o.OwnerRefusal('owned_gpu_latch_unproven'),
                    {'hardware_latched': False}, {'hardware_latched': False}]),
                inspect=Mock(side_effect=lambda name: old_container if name == 'c' * 64 else new_container),
                create_argv=Mock(return_value=['fixture-create']),
                native_identity=Mock(return_value={'container_id': 'd' * 64, 'pid': 44}),
                cgpath=Mock(return_value=Path('/fixture')), read_key=Mock(return_value=b'fixture'),
                native_ready=Mock(side_effect=EndFixture('fixture complete')),
                record_failure=Mock(), settle_state=Mock())
            for name, value in values.items():
                stack.enter_context(patch.object(o, name, value))
            with self.assertRaisesRegex(o.OwnerRefusal, 'owned_gpu_latch_unproven'):
                o.supervise()
            # The same-boot receipt cannot refresh an unknown latch, even when
            # the ordinary sampler supplied evidence suitable for normal starts.
            self.assertIsNone(values['latch'].call_args.kwargs['evidence'])
            self.assertFalse(consumed.exists())
            self.assertEqual((self.base / 'state.json').read_bytes(), before)
            self.assertFalse(any(c.args[0][:2] in (['docker', 'rename'], ['docker', 'rm'])
                                 for c in values['run'].call_args_list))
            with self.assertRaises(EndFixture):
                o.supervise()
            successor = o.read(self.base / 'state.json')
            self.assertNotEqual(successor['launch_id'], self.state['launch_id'])
            self.assertEqual(o.read(consumed)['successor_launch_id'], successor['launch_id'])
            self.assertEqual(o.read(consumed)['recovery_sha256'], o.digest(receipt))
            self.assertEqual(sum(c.args[0][:2] == ['docker', 'rename']
                                 for c in values['run'].call_args_list), 1)
            self.assertFalse(any(c.args[0][:2] == ['docker', 'rm'] for c in values['run'].call_args_list))
            values['settle_state'].assert_called_once()
            with self.assertRaisesRegex(o.OwnerRefusal, 'new_boot_recovery_consumed'):
                o.settled_source_for_start(self.new, receipt['selection'], self.state)

    def test_post_receipt_live_proxy_or_guard_or_intent_drift_refuses(self):
        self.prepare()
        self.finish_stop()
        receipt = self.reconcile()
        intent_name = o.source_stop_name(self.state)
        for name, changed in [('proxy-state.json', {**self.proxy, 'active_requests': 1}),
                              ('guard.json', {**self.guard, 'hardware_latched': True}),
                              (intent_name, {})]:
            with self.subTest(name=name):
                raw = (self.base / name).read_bytes()
                (self.base / name).chmod(0o600)
                self.save(name, changed)
                try:
                    with self.assertRaises(o.OwnerRefusal):
                        o.settled_source_for_start(self.new, receipt['selection'], self.state)
                finally:
                    (self.base / name).write_bytes(raw)


class SameBootPhysicalTests(unittest.TestCase):
    def fixture(self):
        cid = 'c' * 64
        old = {'container_name': 'llm-frontier-mimo-production'}
        state = dict(schema_version=2, status='SETTLED', request_hold=False, boot_id=BOOT,
            settlement={'pid_released': True, 'cgroup_empty': True, 'gpu_compute_empty': True},
            manifest_sha256=o.digest(old), native={'pid': 10, 'container_id': cid},
            supervisor={'pid': 11}, proxy={'pid': 12},
            native_cgroup='/sys/fs/cgroup/llmmimo.slice/docker-' + cid + '.scope')
        container = {'Id': cid, 'State': {'Running': False, 'Pid': 0, 'Status': 'exited'}}
        return old, state, container

    @contextlib.contextmanager
    def host(self, state, container, *, case='ok', successor=None):
        service = Path('/sys/fs/cgroup/system.slice') / o.UNIT
        unit = 'MainPID=0\nActiveState=inactive\nSubState=dead\nInvocationID=\nJob=\n'
        if successor:
            unit = ('MainPID=' + str(successor['pid']) + '\nActiveState=activating\n'
                    'SubState=start\nInvocationID=' + successor['invocation_id'] + '\nJob=\n')
        if case == 'unit':
            unit = unit.replace('MainPID=0', 'MainPID=55')
        if case == 'job':
            unit = unit.replace('Job=\n', 'Job=32/start\n')
        if case == 'invocation':
            unit = unit.replace('InvocationID=successor', 'InvocationID=other')

        def run(argv, *args):
            if argv[0] == 'systemctl':
                return '/system.slice/' + o.UNIT if '--value' in argv else unit
            if argv[0] == 'nvidia-smi':
                return '99' if case == 'gpu' else ''
            if argv[0] == 'ss':
                return 'LISTEN 127.0.0.1:30012' if case == 'listener' else ''
            raise AssertionError(argv)

        def exists(path):
            path = str(path)
            if path.startswith('/proc/'):
                return path == '/proc/' + {'native': '10', 'supervisor': '11', 'proxy': '12'}.get(case, '')
            if path == str(service):
                return True
            return path == state['native_cgroup'] and case in ('native_cgroup', 'native_child_cgroup')

        def contents(path):
            if path == service / 'cgroup.procs':
                return str(successor['pid']) if successor else ('99' if case == 'owner_cgroup' else '')
            if path == service / 'child/cgroup.procs':
                return '99' if case == 'child_cgroup' else ''
            if str(path) == state['native_cgroup'] + '/cgroup.procs':
                return '99' if case == 'native_cgroup' else ''
            if str(path) == state['native_cgroup'] + '/child/cgroup.procs':
                return '99' if case == 'native_child_cgroup' else ''
            raise AssertionError(path)

        with patch.object(o, 'BOOT', SimpleNamespace(read_text=lambda: f.OLD if case == 'boot' else BOOT)), \
             patch.object(o, 'run', side_effect=run), patch.object(o, 'inspect', return_value=container), \
             patch.object(o, 'exact_container', side_effect=lambda c, *a: c), \
             patch.object(Path, 'exists', exists), patch.object(Path, 'read_text', contents), \
             patch.object(Path, 'rglob', lambda p, pattern: iter([p / 'child/cgroup.procs'])):
            yield

    def test_clean_same_boot_absence_is_normal_stop_and_requires_explicit_mode(self):
        old, state, container = self.fixture()
        with self.host(state, container):
            physical = o.settled_source_absence(old, state, BOOT, same_boot=True)
            self.assertEqual(physical['physical_release'], 'NORMAL_OWNER_STOP')
            self.assertEqual(physical['prior_request_outcome'], 'IDLE_INTENTIONAL_STOP')
            with self.assertRaises(o.OwnerRefusal):
                o.settled_source_absence(old, state, BOOT)

    def test_remaining_process_cgroup_gpu_socket_work_and_unsettled_states_refuse(self):
        cases = ('native', 'supervisor', 'proxy', 'unit', 'job', 'running', 'container_pid',
                 'native_cgroup', 'native_child_cgroup', 'owner_cgroup', 'child_cgroup', 'gpu', 'listener', 'boot',
                 'held', 'request_hold', 'physical_unknown')
        for case in cases:
            with self.subTest(case=case):
                old, state, container = self.fixture()
                if case == 'running':
                    container['State']['Running'] = True
                if case == 'container_pid':
                    container['State']['Pid'] = 10
                if case == 'held':
                    state['status'] = 'HELD'
                if case == 'request_hold':
                    state['request_hold'] = True
                if case == 'physical_unknown':
                    state['settlement']['gpu_compute_empty'] = None
                with self.host(state, container, case=case), self.assertRaises(o.OwnerRefusal):
                    o.settled_source_absence(old, state, BOOT, same_boot=True)

    def test_start_allows_exact_successor_only_and_refuses_descendants_or_wrong_invocation(self):
        successor = {'pid': os.getpid(), 'invocation_id': 'successor'}
        for case in ('ok', 'child_cgroup', 'invocation'):
            with self.subTest(case=case):
                old, state, container = self.fixture()
                with self.host(state, container, case=case, successor=successor):
                    if case == 'ok':
                        result = o.settled_source_absence(old, state, BOOT, same_boot=True, successor=successor)
                        self.assertEqual(result['physical_release'], 'NORMAL_OWNER_STOP')
                    else:
                        with self.assertRaises(o.OwnerRefusal):
                            o.settled_source_absence(old, state, BOOT, same_boot=True, successor=successor)


if __name__ == '__main__':
    unittest.main()
