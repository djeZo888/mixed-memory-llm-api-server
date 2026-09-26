"""H006 local-only privacy, admission and installed-needrestart policy fixtures."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
SPEC = importlib.util.spec_from_file_location('h006_image_service', ROOT / 'scripts/image_runtime/service.py')
service = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(service)
from common.lifecycle_lease import LeaseBusy, LeaseError
from install import storage_io
from lifecycle.runtime_io import LifecycleError


class Attempts(unittest.TestCase):
    def tearDown(self):
        service.ATTEMPT = None
        service.OPERATION_DEADLINE = None
        service.SETTLEMENT_DEADLINE = None

    def invoke(self, action, runtime=None, construction_error=None, lease_factory=None):
        runtime = runtime or Mock()
        persisted, journal = [], []
        stderr = io.StringIO()
        with patch.object(service.sys, 'argv', ['service.py', action]), \
                patch.object(service, 'Runtime', return_value=runtime, side_effect=construction_error), \
                patch.object(service, 'acquire_lease', side_effect=lease_factory or (lambda **kw: contextlib.nullcontext('lease'))), \
                patch.object(service, 'persist_attempt', side_effect=lambda value: persisted.append(value)), \
                patch.object(service.syslog, 'openlog'), \
                patch.object(service.syslog, 'syslog', side_effect=lambda _, value: journal.append(json.loads(value))), \
                contextlib.redirect_stderr(stderr):
            code = service.entrypoint()
        return code, persisted, journal, stderr.getvalue()

    def test_constructor_failure_captured_for_all_actions_before_container(self):
        for action in ('start', 'stop', 'recover'):
            with self.subTest(action=action):
                runtime = Mock()
                code, records, journal, stderr = self.invoke(action, runtime, RuntimeError('runtime_source_changed'))
                self.assertEqual(code, 1)
                self.assertEqual(len(records), 1)
                record = records[0]
                self.assertEqual((record['action'], record['phase'], record['code']),
                                 (action, 'construct', 'runtime_source_changed'))
                self.assertEqual(record['status'], 'failed')
                self.assertRegex(record['attempt_id'], r'^[0-9a-f]{32}$')
                self.assertIn('started_utc', record)
                self.assertIn('finished_utc', record)
                self.assertEqual([item['storage_status'] for item in journal], ['pending', 'verified'])
                runtime.start.assert_not_called()
                runtime.reset_owned.assert_not_called()

    def test_precontainer_lease_failure_current_attempt_not_historical_state(self):
        runtime = Mock()
        runtime.state.return_value = {'phase': 'warm', 'native_failure': 'native_exited_during_load',
                                      'recovery_failure': 'reset_warm_failed_no_retry'}
        records = []
        with patch.object(service.sys, 'argv', ['service.py', 'start']), \
                patch.object(service, 'Runtime', return_value=runtime), \
                patch.object(service, 'start_admission', side_effect=LeaseBusy()), \
                patch.object(service, 'persist_attempt', side_effect=records.append), \
                patch.object(service.Attempt, 'emit'):
            self.assertEqual(service.entrypoint(), 1)
        self.assertEqual(records[0]['code'], 'lifecycle_busy')
        self.assertEqual(records[0]['phase'], 'start_admission')
        self.assertNotIn('native_exited_during_load', json.dumps(records))
        runtime.state.assert_not_called()
        runtime.start.assert_not_called()

    def test_known_hardware_guard_timeout_and_unknown_errors_are_bounded(self):
        errors = [(LifecycleError('hardware_inventory_unknown'), 'hardware_inventory_unknown'),
                  (RuntimeError('root_disk_guard_failed'), 'root_disk_guard_failed'),
                  (LeaseError('untrusted_lock_file'), 'canonical_lease_refused'),
                  (storage_io.StorageIOError('private/path SECRET'), 'registered_storage_refused'),
                  (subprocess.TimeoutExpired(['SECRET'], 1, output='PROMPT', stderr='TOKEN'), 'owned_command_timeout'),
                  (RuntimeError('SECRET' * 10000), 'owned_backend_failed'),
                  (RuntimeError('syntactically_valid_but_private'), 'owned_backend_failed'),
                  (ValueError({'prompt': 'SECRET'}), 'owned_backend_failed')]
        for error, expected in errors:
            with self.subTest(expected=expected):
                _, records, journal, stderr = self.invoke('start', construction_error=error)
                self.assertEqual(records[0]['code'], expected)
                data = json.dumps(records) + json.dumps(journal) + stderr
                for secret in ('SECRET', 'PROMPT', 'TOKEN', 'private/path', 'syntactically_valid_but_private'):
                    self.assertNotIn(secret, data)
                self.assertLess(len(json.dumps(records[0])), 2048)

    def test_untrusted_invocation_and_boot_are_not_copied(self):
        with patch.dict(os.environ, {'INVOCATION_ID': 'SECRET' * 1000}), \
                patch.object(service.Path, 'read_text', return_value='SECRET' * 1000):
            attempt = service.Attempt('start')
        self.assertIsNone(attempt.boot)
        self.assertIsNone(attempt.invocation)

    def test_boot_and_systemd_invocation_remain_correlatable(self):
        boot = '12345678-1234-1234-1234-123456789012'
        with patch.dict(os.environ, {'INVOCATION_ID': 'c' * 32}), \
                patch.object(service.Path, 'read_text', return_value=boot + '\n'):
            attempt = service.Attempt('stop')
        self.assertEqual(attempt.boot, boot)
        self.assertEqual(attempt.invocation, 'c' * 32)
        self.assertNotEqual(attempt.identity, service.Attempt('stop').identity)

    def test_original_failure_not_replaced_by_settlement(self):
        attempt = service.Attempt('recover')
        with patch.object(service, 'ATTEMPT', attempt), patch.object(service, 'persist_attempt') as persist, \
                patch.object(service.Attempt, 'emit'):
            service.attempt_phase('systemd_restart')
            service.attempt_failure(RuntimeError('owned_systemd_restart_warm_failed'))
            service.attempt_phase('reset_state')
            service.attempt_failure(RuntimeError('root_disk_guard_failed'))
            attempt.finish(RuntimeError('root_disk_guard_failed'))
        record = persist.call_args.args[0]
        self.assertEqual(record['phase'], 'systemd_restart')
        self.assertEqual(record['code'], 'owned_systemd_restart_warm_failed')
        self.assertEqual(record['settlement_code'], 'root_disk_guard_failed')

    def test_guard_refusal_still_emits_safe_journal_first_no_fallback(self):
        events = []
        attempt = service.Attempt('start')
        def persist(_):
            events.append('write')
            raise RuntimeError('SECRET')
        with patch.object(service, 'persist_attempt', side_effect=persist) as write, \
                patch.object(service.Attempt, 'emit', side_effect=lambda _, status, error: events.append(status)):
            attempt.finish(RuntimeError('runtime_source_changed'))
        self.assertEqual(events, ['pending', 'write', 'unavailable'])
        write.assert_called_once()

    def test_success_pending_journal_is_informational_failure_is_error(self):
        with contextlib.redirect_stderr(io.StringIO()), \
                patch.object(service.syslog, 'openlog'), \
                patch.object(service.syslog, 'syslog') as log:
            for status, error, level in (
                    ('pending', None, service.syslog.LOG_INFO),
                    ('verified', None, service.syslog.LOG_INFO),
                    ('unavailable', None, service.syslog.LOG_ERR),
                    ('pending', RuntimeError('owned_command_failed'), service.syslog.LOG_ERR)):
                service.Attempt.emit({'code': 'ok' if error is None else 'owned_command_failed'}, status, error)
                self.assertEqual(log.call_args.args[0], level)

    def test_success_is_fresh_and_does_not_reuse_failure(self):
        code, records, _, _ = self.invoke('start')
        self.assertEqual(code, 0)
        self.assertEqual(records[0]['code'], 'ok')
        self.assertEqual(records[0]['status'], 'succeeded')
        self.assertIsNone(records[0]['settlement_code'])
        self.assertIsNone(service.ATTEMPT)

    def test_new_start_and_success_keep_legacy_failure_only_as_history(self):
        state = {'run_id': 'b' * 32, 'phase': 'warm', 'warm': True,
                 'failure_type': 'RuntimeError', 'failure_code': 'native_exited_during_load',
                 'native_failure': 'native_exited_during_load',
                 'recovery_failure': 'reset_warm_failed_no_retry'}
        expected = {key: value for key, value in state.items() if key not in {'phase', 'warm'}}
        service.archive_failure_fields(state)
        self.assertEqual(state['historical_failure'], expected)
        self.assertFalse({'failure_code', 'failure_type', 'native_failure', 'recovery_failure'} & state.keys())
        state.update(run_id='c' * 32, phase='warm')
        service.archive_failure_fields(state)
        self.assertEqual(state['historical_failure'], expected)
        # New failures have their own immutable attempt receipts; a later new
        # start archives only known current fields without restoring stale ones.
        state['failure_code'] = 'native_readiness_timeout'
        service.archive_failure_fields(state)
        self.assertEqual(state['historical_failure']['native_failure'], 'native_exited_during_load')
        self.assertEqual(state['historical_failure'], expected)
        self.assertEqual(state['historical_failure']['run_id'], 'b' * 32)
        self.assertNotIn('failure_code', state)

    def test_real_start_precontainer_gates_capture_without_docker_or_state_write(self):
        for gate, expected_phase, expected_code in (
                ('guards', 'start_preflight', 'registered_storage_guard_failed'),
                ('require_hardware', 'hardware_preflight', 'hardware_inventory_unknown'),
                ('check_ports', 'backend_preflight', 'native_port_already_owned'),
                ('require_ada_idle', 'backend_preflight', 'ada_compute_process_already_present')):
            runtime = object.__new__(service.Runtime)
            runtime.config = {}
            for method in ('guards', 'require_hardware', 'check_network', 'check_ports',
                           'require_ada_idle', 'host_headroom', 'make_work', 'save'):
                setattr(runtime, method, Mock())
            runtime.state = Mock(return_value={'phase': 'warm', 'native_failure': 'native_exited_during_load'})
            runtime.inspect_owned = Mock(return_value=None)
            getattr(runtime, gate).side_effect = RuntimeError(expected_code)
            attempt = service.Attempt('start')
            with self.subTest(gate=gate), patch.object(service, 'ATTEMPT', attempt), \
                    patch.dict(os.environ, {'INVOCATION_ID': 'c' * 32}), \
                    patch.object(service, 'OPERATION_DEADLINE', service.time.monotonic() + 775), \
                    patch.object(service, 'run') as run, \
                    patch.object(service, 'persist_attempt') as persist, \
                    patch.object(service.Attempt, 'emit'):
                try:
                    runtime.start()
                except RuntimeError as error:
                    attempt.finish(error)
                else:
                    self.fail('gate must refuse')
            record = persist.call_args.args[0]
            self.assertEqual((record['phase'], record['code']), (expected_phase, expected_code))
            run.assert_not_called()
            runtime.save.assert_not_called()
            runtime.make_work.assert_not_called()

    def test_refreshed_guards_precede_start_under_admitted_lease(self):
        runtime = Mock()
        events, held = [], [False]
        @contextlib.contextmanager
        def lease_factory(**kwargs):
            self.assertFalse(kwargs['blocking'])
            events.append('admitted')
            held[0] = True
            try:
                yield 'lease'
            finally:
                held[0] = False
                events.append('released')
        def guarded(event):
            self.assertTrue(held[0])
            events.append(event)
        runtime.guards.side_effect = lambda: guarded('guards')
        runtime.start.side_effect = lambda: guarded('start')
        self.invoke('start', runtime, lease_factory=lease_factory)
        self.assertEqual(events, ['admitted', 'guards', 'start', 'released'])
        self.assertEqual(runtime.lease, 'lease')
        runtime.reset_owned.assert_not_called()
        events.clear()
        runtime.start.reset_mock()
        def failed_guard():
            guarded('guards')
            raise RuntimeError('root_disk_guard_failed')
        runtime.guards.side_effect = failed_guard
        code, records, _, _ = self.invoke('start', runtime, lease_factory=lease_factory)
        self.assertEqual(code, 1)
        self.assertEqual(records[0]['phase'], 'admitted_guards')
        self.assertEqual(events, ['admitted', 'guards', 'released'])
        runtime.start.assert_not_called()


class ProtectedWriting(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='.h006-receipts-', dir=ROOT)
        self.root = Path(self.tmp.name)
        info = self.root.stat()
        identity = {'path': str(self.root), 'mount': str(self.root), 'uuid': 'fixture',
                    'fstype': 'ext4', 'device': f'{os.major(info.st_dev)}:{os.minor(info.st_dev)}'}
        self.snapshot = {'schema_version': 1, 'data': identity.copy(), 'models': identity.copy(),
                         'roots': {'logs': str(self.root)}}
        self.lost = False
        self.binding = Mock()
        self.binding.path.return_value = str(self.root)
        self.binding.mounted_guard.side_effect = lambda _io: contextlib.nullcontext(self.guard)
        self.anchor = storage_io.AnchoredRoot
        self.record = {'attempt_id': 'a' * 32, 'action': 'start', 'phase': 'construct',
                       'code': 'runtime_source_changed'}

    def tearDown(self):
        self.tmp.cleanup()

    def guard(self):
        if self.lost:
            raise storage_io.StorageIOError('fixture_mount_lost')
        return self.snapshot

    def write(self):
        with patch.object(service.RegisteredStorageBinding, 'load', return_value=self.binding), \
                patch.object(storage_io, 'AnchoredRoot',
                             side_effect=lambda path, guard: self.anchor(path, guard, uid=os.geteuid())):
            service.persist_attempt(self.record)

    def test_real_anchored_private_exclusive_write_with_pre_post_guards(self):
        self.write()
        path = self.root / 'image-runtime-attempts' / ('a' * 32 + '.json')
        self.assertEqual(json.loads(path.read_text()), self.record)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.binding.storage.root_payload_guard.call_count, 2)
        with self.assertRaises(FileExistsError):
            self.write()
        self.assertEqual(json.loads(path.read_text()), self.record)

    def test_symlink_parent_and_file_refused(self):
        outside = self.root / 'outside'
        outside.mkdir()
        target = self.root / 'image-runtime-attempts'
        target.symlink_to(outside, target_is_directory=True)
        with self.assertRaises((OSError, storage_io.StorageIOError)):
            self.write()
        self.assertEqual(list(outside.iterdir()), [])
        target.unlink()
        target.mkdir(mode=0o700)
        (target / ('a' * 32 + '.json')).symlink_to(outside / 'secret')
        with self.assertRaises((OSError, storage_io.StorageIOError)):
            self.write()
        self.assertFalse((outside / 'secret').exists())

    def test_unprotected_parent_refused(self):
        path = self.root / 'image-runtime-attempts'
        path.mkdir(mode=0o777)
        path.chmod(0o777)
        with self.assertRaises(storage_io.StorageIOError):
            self.write()
        self.assertEqual(list(path.iterdir()), [])

    def test_registration_root_guard_and_mount_loss_refuse_without_file(self):
        for stage in ('registration', 'root', 'mount'):
            with self.subTest(stage=stage):
                if stage == 'registration':
                    with patch.object(service.RegisteredStorageBinding, 'load', side_effect=RuntimeError('refused')):
                        with self.assertRaises(RuntimeError):
                            service.persist_attempt(self.record)
                elif stage == 'root':
                    self.binding.storage.root_payload_guard.side_effect = RuntimeError('refused')
                    with self.assertRaises(RuntimeError):
                        self.write()
                    self.binding.storage.root_payload_guard.side_effect = None
                else:
                    self.lost = True
                    with self.assertRaises(storage_io.StorageIOError):
                        self.write()
                self.assertEqual(list(self.root.iterdir()), [])

    def test_guard_loss_during_write_reports_unavailable(self):
        original = storage_io.GuardedFile.write
        def lose(stream, data):
            self.lost = True
            return original(stream, data)
        with patch.object(storage_io.GuardedFile, 'write', lose):
            with self.assertRaises(storage_io.StorageIOError):
                self.write()
        self.assertEqual(self.binding.storage.root_payload_guard.call_count, 2)
        # Partial exclusive file is not a complete receipt; no root fallback.
        self.assertEqual((self.root / 'image-runtime-attempts' / ('a' * 32 + '.json')).read_bytes(), b'')


class Admission(unittest.TestCase):
    def test_entry_busy_then_release_runs_body_once(self):
        events = []
        clock = [0.0]
        def sleep(seconds):
            clock[0] += seconds
            events.append('wait')
        def acquire(**kwargs):
            self.assertFalse(kwargs['blocking'])
            events.append('acquire')
            if clock[0] < 0.4:
                raise LeaseBusy()
            return contextlib.nullcontext('canonical')
        with patch.object(service, 'acquire_lease', side_effect=acquire), \
                patch.object(service.time, 'monotonic', side_effect=lambda: clock[0]), \
                patch.object(service.time, 'sleep', side_effect=sleep):
            with service.start_admission() as lease:
                self.assertEqual(lease, 'canonical')
                events.append('mutation')
        self.assertEqual(events, ['acquire', 'wait', 'acquire', 'wait', 'acquire', 'mutation'])

    def test_persistent_busy_exhausts_two_seconds_without_body(self):
        clock = [0.0]
        def sleep(seconds):
            clock[0] += seconds
        with patch.object(service, 'acquire_lease', side_effect=LeaseBusy()), \
                patch.object(service.time, 'monotonic', side_effect=lambda: clock[0]), \
                patch.object(service.time, 'sleep', side_effect=sleep):
            with self.assertRaises(LeaseBusy):
                with service.start_admission():
                    self.fail('mutation must not be admitted')
        self.assertEqual(clock[0], 2.0)

    def test_acquired_body_busy_is_never_replayed(self):
        with patch.object(service, 'acquire_lease', return_value=contextlib.nullcontext('canonical')) as acquire, \
                patch.object(service.time, 'sleep') as sleep:
            with self.assertRaises(LeaseBusy):
                with service.start_admission():
                    raise LeaseBusy()
        acquire.assert_called_once_with(blocking=False)
        sleep.assert_not_called()

    def test_nonbusy_lease_refusal_never_waits(self):
        with patch.object(service, 'acquire_lease', side_effect=LeaseError('lock_path_changed')) as acquire, \
                patch.object(service.time, 'sleep') as sleep:
            with self.assertRaises(LeaseError):
                with service.start_admission():
                    self.fail('unsafe lease')
        acquire.assert_called_once()
        sleep.assert_not_called()

    def test_real_canonical_lease_contention_no_bypass(self):
        from common.lifecycle_lease import acquire_lease
        with tempfile.TemporaryDirectory(prefix='.h006-lease-', dir=ROOT) as temporary:
            def acquire(**kwargs):
                return acquire_lease(**kwargs, system_root=Path(temporary), trusted_uid=os.geteuid())
            with acquire(blocking=False) as parent:
                with patch.object(service, 'acquire_lease', side_effect=acquire), \
                        patch.object(service, 'START_ADMISSION_SECONDS', 0.01), \
                        self.assertRaises(LeaseBusy):
                    with service.start_admission():
                        self.fail('must not bypass parent')
                parent.validate()
            with patch.object(service, 'acquire_lease', side_effect=acquire):
                with service.start_admission() as child:
                    child.validate()


class NeedrestartPolicy(unittest.TestCase):
    def test_exact_unit_exclusions_preserve_ubuntu_automatic_policy(self):
        config = ROOT / 'configs/needrestart/90-llm-managed-units.conf'
        # Selection loop copied from installed Ubuntu needrestart 3.6-7ubuntu4.5,
        # /usr/sbin/needrestart:1088-1103. No daemon or package commands execute.
        perl = r'''
use strict; use warnings; use JSON::PP;
our %nrconf = (restart => 'a', defno => 0, override_rc => { qr(\Adbus\.service\z) => 0 });
do $ARGV[0]; die $@ if $@;
my @units = ('llm-control.service', 'llm-node.service', 'llm-image-api.service', 'llm-image-backend.service',
             'llm-control.service.evil', 'xllm-node.service', 'llm-image-apiXservice', 'llm-image-backend@x.service',
             'llm-control.socket', 'llmctl-boot.service', 'llm-private-image.service', 'polkit.service',
             'unattended-upgrades.service', "llm-control.service\n", 'dbus.service');
my %results;
foreach my $rc (@units) {
    my $restart = !$nrconf{defno};
    foreach my $re (keys %{$nrconf{override_rc}}) {
        next unless($rc =~ /$re/);
        $restart = $nrconf{override_rc}->{$re};
        last;
    }
    $results{$rc} = $restart ? 1 : 0;
}
print encode_json({ results => \%results, restart => $nrconf{restart}, count => scalar keys %{$nrconf{override_rc}} });
'''
        result = subprocess.run(['perl', '-e', perl, str(config)], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        deferred = {name for name, enabled in value['results'].items() if not enabled}
        self.assertEqual(deferred, {'llm-control.service', 'llm-node.service', 'llm-image-api.service',
                                    'llm-image-backend.service', 'dbus.service'})
        self.assertEqual(value['count'], 5)
        self.assertEqual(value['restart'], 'a')
        self.assertEqual(set(line.split('->')[0] for line in config.read_text().splitlines() if line.startswith('$')),
                         {'$nrconf{override_rc}'})

    def test_unit_retains_restart_no_and_emits_safe_stderr(self):
        unit = (ROOT / 'scripts/image_runtime/llm-image-backend.service').read_text()
        self.assertIn('StandardError=journal\n', unit)
        self.assertIn('StandardOutput=null\n', unit)
        self.assertIn('Restart=no\n', unit)
        self.assertNotIn('StandardError=null', unit)


if __name__ == '__main__':
    unittest.main()
