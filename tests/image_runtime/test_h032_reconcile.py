"""Finite H032 incident fixtures; no VM, inference, Docker or systemd calls.

Real anchored files, exclusive descriptors, short common leases, dispatch markers,
reset/settlement and install CAS are exercised. Only external native/system proof
producers are substituted. Retained record fields omit request/user payloads.
"""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import types
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_operation_protocol as protocol

SPEC = importlib.util.spec_from_file_location('h032_reconcile_fixture',
    protocol.REPO / 'scripts/h032/image_reconcile.py')
reconcile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reconcile)
service = protocol.service


class Harness:
    def __enter__(self):
        self.base = protocol.OperationProtocol()
        self.base.setUp()
        self.stack = self.base.stack
        self.root, self.anchor, self.runtime = self.base.root, self.base.anchor, self.base.runtime
        self.stack.enter_context(patch.object(reconcile, 'BASE', self.root))
        self.stack.enter_context(patch.object(reconcile, 'NATIVE_UID', os.geteuid()))
        self.stack.enter_context(patch.object(reconcile, 'NATIVE_GID', os.getegid()))
        self.base.boot = reconcile.BOOT
        self.stack.enter_context(patch.object(reconcile, 'time', types.SimpleNamespace(
            time=lambda: reconcile.END - 300, monotonic=protocol.time.monotonic)))
        self.runtime.boot = reconcile.BOOT
        self.commands, self.evidence_commands, self.events = [], [], []
        self.owner_present, self.native = False, {
            'Id': reconcile.CID, 'HostConfig': {'LogConfig': {'Type': 'none', 'Config': {}}},
            'Mounts': [{'Type': 'bind', 'Source': str(self.root / 'work'), 'Destination': '/work'}],
            'State': {'Running': True, 'OOMKilled': False,
            'Pid': reconcile.NATIVE['pid'], 'StartedAt': '2026-09-29T09:55:35.757660444Z'}}
        self.runtime.inspect_owned.side_effect = lambda *_a, **_k: copy.deepcopy(self.native)
        self.runtime.process_stamp.side_effect = lambda pid: {
            'pid': pid, 'start_ticks': 3992209 if pid == reconcile.NATIVE['pid'] else 123}
        self.runtime.cleanup_tmp = Mock(return_value={'removed_exact_owned_invocation': True})
        self.old_source = b'# exact old source fixture\n'
        self.new_source = b'# exact corrected source fixture\n'
        self.runtime.config['source_sha256'] = {'service.py': reconcile.sha(self.old_source)}
        self.anchor.atomic_json('config.json', self.runtime.config)
        self.anchor.mkdir('source')
        self.write('source/service.py', self.old_source)
        self.anchor.mkdir(reconcile.PREFIX.rstrip('/'))
        self.anchor.mkdir('receipts')
        self.native_files()
        self.write('receipts/' + reconcile.RUN + '-telemetry.jsonl', b'{"fixture":"telemetry"}\n')
        self.anchor.mkdir('logs/image-runtime-attempts')
        for attempt, action, code in (
                ('03b0c9d00efd493fa1ec9f065ce4de5e', 'start', 'image_operation_changed'),
                ('1518f23193164d529609b02871873b12', 'recover', 'owned_systemd_restart_warm_failed')):
            self.anchor.atomic_json('logs/image-runtime-attempts/' + attempt + '.json',
                {'attempt_id': attempt, 'action': action, 'code': code, 'status': 'failed'})
        self.state = {'schema_version': 1, 'owner': service.OWNER, 'phase': 'warm', 'warm': True,
            'run_id': reconcile.RUN, 'container': {'id': reconcile.CID, 'image_id': protocol.IMAGE},
            'native_generation': {'Pid': reconcile.NATIVE['pid'], 'pid': reconcile.NATIVE['pid'],
                'start_ticks': 3992209, 'StartedAt': self.native['State']['StartedAt']},
            'native_actions': {'create': 'received', 'start': 'received', 'warm': 'dispatched'},
            'residency': {'container_id': reconcile.CID,
                'started_at': '2026-09-29T09:55:35.757660444Z',
                'gpu_processes': [[reconcile.GPU, '1664791', '32224']],
                'device_current': {'free_bytes': 17064525824, 'total_bytes': 51527024640,
                                   'uuid': reconcile.GPU}},
            'historical_failure': {'failure_code': 'native_exited_during_load',
                'failure_type': 'RuntimeError', 'recovery_failure': 'reset_warm_failed_no_retry',
                'run_id': '98cba57d44a14bd79a0f24c8b9519706'},
            'generation': copy.deepcopy(self.generation),
            'telemetry_path': str(reconcile.BASE / 'receipts' / (reconcile.RUN + '-telemetry.jsonl'))}
        digest = self.runtime.config_digest()
        self.op = {'action': 'start', 'boot': reconcile.BOOT, 'config_sha256': digest,
            'gpu_uuid': reconcile.GPU, 'invocation_id': reconcile.RUN, 'pid': 1656742,
            'prior_state_sha256': '926e69dd6d5b465735f7629dd749218d5ccaab9d2633c56b38d79165b39b7032',
            'recovery': '83be8882e6374f3fbc3918de6bc5107c', 'status': 'active',
            'token': '868d9b48784b44f4b702b52c05655a65'}
        self.recovery = {'boot': reconcile.BOOT, 'child_start': reconcile.RUN,
            'config_sha256': digest, 'gpu_uuid': reconcile.GPU, 'phase': 'settle', 'pid': 1655508,
            'prior_invocation': '', 'process': {'pid': 1655508, 'start_ticks': 3990457},
            'status': 'active', 'token': self.op['recovery']}
        for name, value in [('state.json', self.state), ('operation.json', self.op),
                            ('recovery.json', self.recovery)]:
            self.anchor.atomic_json(name, value)
        self.originals = {name: self.read(name) for name in
                         ('state.json', 'operation.json', 'recovery.json', 'config.json', 'source/service.py')}
        self.stack.enter_context(patch.object(reconcile, 'OLD_RECORDS', {
            name: reconcile.sha(self.originals[name]) for name in ('state.json', 'operation.json', 'recovery.json')}))
        self.stack.enter_context(patch.object(reconcile, 'OLD_SERVICE', reconcile.sha(self.old_source)))
        self.stack.enter_context(patch.object(reconcile, 'OLD_CONFIG', reconcile.sha(self.originals['config.json'])))
        self.new_config = copy.deepcopy(self.runtime.config)
        self.new_config['source_sha256']['service.py'] = reconcile.sha(self.new_source)
        self.write(reconcile.PREFIX + 'candidate-service.py', self.new_source)
        self.write(reconcile.PREFIX + 'candidate-config.json', reconcile.js(self.new_config))
        self.plan = {'activation_deadline_unix': reconcile.END, 'case': reconcile.CASE, 'boot': reconcile.BOOT, 'gpu_uuid': reconcile.GPU,
            'native': copy.deepcopy(reconcile.NATIVE), 'old_service_sha256': reconcile.OLD_SERVICE,
            'old_config_sha256': reconcile.OLD_CONFIG, 'new_service_sha256': reconcile.sha(self.new_source),
            'new_config_sha256': reconcile.sha(reconcile.js(self.new_config))}
        self.plan['old_raw_sha256'] = {('service.py' if n == 'source/service.py' else n):
            reconcile.sha(raw) for n, raw in self.originals.items()}
        self.plan_raw = reconcile.js(self.plan)
        self.write(reconcile.PREFIX + 'plan.json', self.plan_raw)
        binding = types.SimpleNamespace(path=lambda _name: str(self.root / 'logs'),
            mounted_guard=lambda _io: contextlib.nullcontext(self.base.storage_guard))
        self.runtime.binding = binding
        module = types.SimpleNamespace(now=service.now, storage_io=types.SimpleNamespace(
            AnchoredRoot=lambda path, guard: protocol.storage_io.AnchoredRoot(path, guard, uid=os.geteuid())))
        self.stack.enter_context(patch.object(reconcile, 'runtime_module', module, create=True))
        original_read_text, original_iterdir = Path.read_text, Path.iterdir
        def read_text(path, *args, **kwargs):
            if str(path) == '/proc/' + str(reconcile.NATIVE['pid']) + '/cgroup':
                return '0::' + reconcile.NATIVE['cgroup'] + '\n'
            return original_read_text(path, *args, **kwargs)
        def iterdir(path):
            return iter(()) if str(path) == '/proc' else original_iterdir(path)
        self.stack.enter_context(patch.object(Path, 'read_text', read_text))
        self.stack.enter_context(patch.object(Path, 'iterdir', iterdir))
        self.stack.enter_context(patch.object(reconcile, 'absent', side_effect=self.absent))
        self.stack.enter_context(patch.object(reconcile, 'unit', side_effect=self.unit))
        self.stack.enter_context(patch.object(reconcile, 'command', side_effect=self.evidence_command))
        self.stack.enter_context(patch.object(service, 'run', side_effect=self.native_command))
        self.stack.enter_context(patch.object(reconcile, 'load_owner', side_effect=self.load_owner))
        return self

    def __exit__(self, *_args):
        self.base.doCleanups()

    def read(self, name):
        return reconcile.raw(self.anchor, name)

    def write(self, name, content):
        with self.anchor.open(name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC) as stream:
            stream.write(content)
            stream.fsync()

    def native_files(self):
        self.anchor.mkdir('work/evidence/' + reconcile.RUN)
        self.native_directory = self.root / 'work/evidence' / reconcile.RUN
        files = {'backend.log': b'fixture native backend log\n',
                 'generation-request.json': b'{"fixture":"request"}\n',
                 'generation-response.json': b'{"fixture":"response"}\n',
                 'generation-perf.json': b'{"fixture":"perf"}\n',
                 'generation.png': b'fixture output bytes'}
        summary = {'run_id': reconcile.RUN, 'status': 'pass',
            'output': {'sha256': reconcile.sha(files['generation.png'])},
            'response_bytes': len(files['generation-response.json']),
            'request_body_sha256': reconcile.sha(files['generation-request.json']),
            'native_perf': {'sha256': reconcile.sha(files['generation-perf.json'])}}
        self.generation = summary
        files['generation-summary.json'] = reconcile.js(summary)
        for name, content in files.items():
            self.write('work/evidence/' + reconcile.RUN + '/' + name, content)

    def unit(self, name):
        return {'MainPID': '0', 'ControlPID': '0', 'ActiveState': 'failed', 'SubState': 'failed',
                'InvocationID': reconcile.RUN if name == 'llm-image-backend.service' else '0' * 32,
                'Job': '', 'ControlGroup': ''}

    def absent(self, path):
        if str(path) in ('/proc/1656742', '/proc/1655508'):
            return not self.owner_present
        return self.native is None

    def evidence_command(self, argv, **_kwargs):
        self.base.assert_common_available()
        self.evidence_commands.append(argv)
        if argv[:2] == ['systemctl', 'list-jobs']:
            return b'', b''
        if argv[0] == 'journalctl':
            return b'{"fixture":"journal"}\n', b''
        raise AssertionError('unexpected external evidence boundary: ' + repr(argv))

    def native_command(self, argv, **_kwargs):
        self.base.assert_common_available()
        self.commands.append(argv)
        if argv[:2] in (['docker', 'stop'], ['docker', 'rm']):
            assert self.anchor.stat(reconcile.PREFIX + 'consumed.json')
            assert self.anchor.stat(reconcile.PREFIX + 'archive-manifest.json')
            self.events.append(argv[1])
        if argv[:2] == ['docker', 'stop']:
            assert argv == ['docker', 'stop', '--time', '30', reconcile.CID]
            self.native['State'].update(Running=False, Pid=0)
            return subprocess.CompletedProcess(argv, 0, '', '')
        if argv[:2] == ['docker', 'rm']:
            assert argv == ['docker', 'rm', reconcile.CID]
            self.native = None
            return subprocess.CompletedProcess(argv, 0, '', '')
        if argv[:3] == ['docker', 'container', 'ls']:
            assert self.native is None
            # Other retained model container remains present and is ignored.
            out = json.dumps({'ID': 'e' * 64, 'Names': 'retained-qwen'}) + '\n'
        elif argv[:3] == ['systemctl', 'show', service.UNIT]:
            out = '\n'.join(key + '=' + value for key, value in self.unit(service.UNIT).items())
        elif argv[0] == 'nvidia-smi':
            assert '--id=' + reconcile.GPU in argv
            out = ''
        elif argv == ['ss', '-H', '-ltn']:
            out = 'LISTEN 0 4096 127.0.0.1:30008 0.0.0.0:*\n'
        else:
            raise AssertionError('unexpected external native boundary: ' + repr(argv))
        return subprocess.CompletedProcess(argv, 0, out, '')

    def load_owner(self, expected):
        assert expected == self.plan['new_service_sha256']
        self.events.append('load-corrected-owner')
        updated = self.base.make_runtime()
        updated.config = copy.deepcopy(self.new_config)
        updated.boot = reconcile.BOOT
        return types.SimpleNamespace(Runtime=lambda: updated)

    def run(self, **kwargs):
        return reconcile.reconcile(self.runtime, self.plan_raw, **kwargs)


class H032ReconcileTests(unittest.TestCase):
    def assert_unchanged(self, h):
        self.assertEqual(h.commands, [])
        self.assertIsNone(h.anchor.stat(reconcile.PREFIX + 'consumed.json', missing_ok=True))
        self.assertEqual(h.read('operation.json'), h.originals['operation.json'])
        self.assertEqual(h.read('recovery.json'), h.originals['recovery.json'])

    def test_exact_pair_archives_before_intent_and_only_stops_removes_once(self):
        with Harness() as h:
            h.run()
            self.assertEqual(h.events, ['stop', 'rm', 'load-corrected-owner'])
            archived = h.anchor.read_json(reconcile.PREFIX + 'archive-manifest.json')
            for name, original in h.originals.items():
                archive_name = 'service.py' if name == 'source/service.py' else name
                self.assertEqual(h.read(reconcile.PREFIX + 'archive/' + archive_name), original)
                self.assertEqual(archived['files'][archive_name], reconcile.sha(original))
                self.assertEqual(h.anchor.stat(reconcile.PREFIX + 'archive/' + archive_name).st_mode & 0o777, 0o400)
            state = h.runtime.state()
            self.assertEqual(state['last_native_actions']['warm'], 'dispatched')
            self.assertEqual(state['historical_failure'], h.state['historical_failure'])
            self.assertFalse(state['warm'])
            self.assertIsNone(state['container'])
            recovery = h.runtime.record('recovery.json')
            self.assertEqual((recovery['status'], recovery['phase']),
                             ('active', 'settled_awaiting_reviewed_activation'))
            self.assertNotEqual(recovery['token'], h.recovery['token'])
            self.assertEqual(h.read('source/service.py'), h.new_source)
            self.assertEqual(h.anchor.read_json('config.json'), h.new_config)
            self.assertTrue(h.anchor.read_json(reconcile.PREFIX + 'settlement.json')['physically_absent'])
            self.assertIsNotNone(h.anchor.stat('h032-image-handoff.json'))
            with self.assertRaisesRegex(RuntimeError, 'plan_already_consumed'):
                h.run()
            self.assertEqual([a[1] for a in h.commands if a[0] == 'docker' and a[1] in ('stop', 'rm')],
                             ['stop', 'rm'])

    def test_exact_no_log_driver_archives_bind_files_without_docker_log_query(self):
        with Harness() as h:
            h.run()
            self.assertFalse(any(argv[0] == 'docker' for argv in h.evidence_commands))
            receipt = h.anchor.read_json(reconcile.PREFIX + 'archive/native-log-bound.json')
            self.assertEqual(receipt['docker_log_stream'], 'ABSENT_BY_EXACT_LOG_DRIVER_NONE')
            self.assertEqual(set(receipt['files']), {
                'backend.log', 'generation-request.json', 'generation-response.json',
                'generation-summary.json', 'generation-perf.json', 'generation.png'})
            for name, meta in receipt['files'].items():
                raw = h.read(reconcile.PREFIX + 'archive/native-' + name)
                self.assertEqual(raw, (h.native_directory / name).read_bytes())
                self.assertEqual(reconcile.sha(raw), meta['sha256'])
                self.assertFalse(meta['truncated'])

    def test_native_bound_files_missing_unknown_policy_or_symlink_refuse_before_cleanup(self):
        for case in ('missing-log', 'missing-output', 'log-policy', 'symlink', 'output-digest', 'foreign-bind'):
            with self.subTest(case=case), Harness() as h:
                if case == 'missing-log': (h.native_directory / 'backend.log').unlink()
                elif case == 'missing-output': (h.native_directory / 'generation.png').unlink()
                elif case == 'log-policy': h.native['HostConfig']['LogConfig']['Type'] = 'json-file'
                elif case == 'foreign-bind': h.native['Mounts'][0]['Source'] = '/unrelated/work'
                elif case == 'output-digest': (h.native_directory / 'generation.png').write_bytes(b'changed')
                else:
                    path = h.native_directory / 'backend.log'
                    path.unlink()
                    path.symlink_to(h.native_directory / 'generation-request.json')
                with self.assertRaises((RuntimeError, OSError)): h.run()
                self.assert_unchanged(h)

    def test_sglang_perf_read_bits_allowed_but_group_write_refuses_archive(self):
        with Harness() as h:
            (h.native_directory / 'generation-perf.json').chmod(0o644)
            h.run()
            self.assertIsNotNone(h.anchor.stat(reconcile.PREFIX + 'archive/native-generation-perf.json'))
        with Harness() as h:
            (h.native_directory / 'generation-perf.json').chmod(0o664)
            with self.assertRaisesRegex(RuntimeError, 'native_evidence_unsafe'): h.run()
            self.assert_unchanged(h)

    def test_main_stop_timeout_finishes_one_immutable_failed_attempt(self):
        with Harness() as h:
            helper = b'fixture reviewed helper source'
            h.plan['helper_sha256'] = reconcile.sha(helper)
            h.write(reconcile.PREFIX + 'plan.json', reconcile.js(h.plan))
            original_native = h.native_command
            original_anchor = protocol.storage_io.AnchoredRoot
            receipts = []
            def lost_ack(argv, **kwargs):
                result = original_native(argv, **kwargs)
                if argv[:2] == ['docker', 'stop']:
                    raise subprocess.TimeoutExpired(argv, 45)
                return result
            def persist(record):
                name = reconcile.PREFIX + 'attempt-' + record['attempt_id'] + '.json'
                reconcile.immutable(h.anchor, name, reconcile.js(record))
                receipts.append((name, copy.deepcopy(record)))
            fake_os = types.SimpleNamespace(**{name: getattr(os, name) for name in dir(os)})
            fake_os.geteuid = lambda: 0
            with patch.object(reconcile, 'load_owner', return_value=service), \
                 patch.object(reconcile, 'protected', return_value=helper), \
                 patch.object(reconcile, 'os', fake_os), \
                 patch.object(reconcile, 'sys', types.SimpleNamespace(argv=['reviewed-helper'])), \
                 patch.object(service, 'Runtime', return_value=h.runtime), \
                 patch.object(service, 'run', side_effect=lost_ack), \
                 patch.object(service, 'persist_attempt', side_effect=persist), \
                 patch.object(service.Attempt, 'emit'), \
                 patch.object(protocol.storage_io, 'AnchoredRoot', side_effect=lambda path, guard:
                     original_anchor(path, guard, uid=os.geteuid())):
                with self.assertRaises(subprocess.TimeoutExpired): reconcile.main()
            self.assertEqual(len(receipts), 1)
            name, record = receipts[0]
            self.assertEqual((record['action'], record['status'], record['code']),
                             ('h032_reconcile', 'failed', 'owned_command_timeout'))
            self.assertEqual(h.anchor.stat(name).st_mode & 0o777, 0o400)
            self.assertEqual(h.anchor.read_json(name), record)
            self.assertEqual(h.runtime.record('recovery.json')['status'], 'active')
            self.assertEqual(h.runtime.state()['native_actions']['stop'], 'dispatched')
            self.assertIsNone(service.ATTEMPT)
            self.assertIsNone(service.OPERATION_DEADLINE)
            self.assertEqual(h.events, ['stop'])

    def test_native_backend_log_tail_has_explicit_bound_and_truncation_receipt(self):
        with Harness() as h:
            lines = [('%04d fixture line\n' % n).encode() for n in range(1200)]
            (h.native_directory / 'backend.log').write_bytes(b''.join(lines))
            evidence = reconcile.native_evidence(h.runtime, h.anchor, h.native)
            self.assertEqual(evidence['native-backend.log'], b''.join(lines[-1000:]))
            bound = json.loads(evidence['native-log-bound.json'])['files']['backend.log']
            self.assertTrue(bound['truncated'])
            self.assertEqual(bound['offset'], len(b''.join(lines[:200])))
            self.assertEqual(h.commands, [])

    def test_helper_handoff_is_accepted_by_actual_corrected_service(self):
        with Harness() as h:
            h.run()
            updated = h.load_owner(h.plan['new_service_sha256']).Runtime()
            prior = updated.record('recovery.json')
            original_stat = Path.stat
            def settled_processes(path, *args, **kwargs):
                if str(path).startswith(('/proc/', '/sys/fs/cgroup/')):
                    raise FileNotFoundError(str(path))
                return original_stat(path, *args, **kwargs)
            clock = types.SimpleNamespace(time=lambda: reconcile.END - 300,
                                          monotonic=protocol.time.monotonic)
            with patch.object(service, 'H032_OLD_SERVICE', reconcile.sha(h.old_source)), \
                 patch.object(service, 'time', clock), \
                 patch.object(Path, 'stat', settled_processes), \
                 updated.singleton('recovery.lock'), updated.singleton('operation.lock'):
                proof = service._h032_handoff(updated, prior)
            self.assertEqual(proof['prior'], prior)
            self.assertEqual(proof['handoff']['native'], reconcile.NATIVE)
            self.assertIsNone(updated.record('h032-image-handoff-consumed.json'))

    def test_deployed_publish_cleanup_uses_loaded_json_lists_without_tuple_regression(self):
        # This is the exact old 26f7 publish body. reset_owned, settle_native,
        # critical and operation are AST-identical in the retained old source;
        # cleanup uses JSON-loaded state and does not call verify_resident().
        def deployed_publish(self, state, *, hardware=False):
            with self.critical(hardware=hardware):
                self.save(state)
                self.expected_state = copy.deepcopy(state)
        with Harness() as h:
            h.runtime.publish = types.MethodType(deployed_publish, h.runtime)
            h.runtime.verify_resident = Mock(side_effect=AssertionError('cleanup cannot create residency tuples'))
            before = h.runtime.state()['residency']
            self.assertIsInstance(before['gpu_processes'][0], list)
            h.run()
            self.assertEqual(h.runtime.state()['residency'], before)
            self.assertIsInstance(h.runtime.state()['residency']['gpu_processes'][0], list)
            self.assertEqual(h.runtime.state()['last_native_actions']['warm'], 'dispatched')
            self.assertEqual(h.events, ['stop', 'rm', 'load-corrected-owner'])
            h.runtime.verify_resident.assert_not_called()

    def test_wrong_raw_leaf_refuses_without_consumption_or_native_cleanup(self):
        for name in ('state.json', 'operation.json', 'recovery.json', 'config.json', 'source/service.py'):
            with self.subTest(name=name), Harness() as h:
                h.write(name, h.read(name) + b' ')
                with self.assertRaisesRegex(RuntimeError, 'predecessor_bytes_changed'):
                    h.run()
                self.assertEqual(h.commands, [])
                self.assertIsNone(h.anchor.stat(reconcile.PREFIX + 'consumed.json', missing_ok=True))

    def test_wrong_boot_native_generation_or_retained_owner_refuses(self):
        for case, code in [('boot', 'image_boot_changed'), ('native-id', 'native_identity_changed'),
                           ('native-generation', 'image_native_generation_changed'),
                           ('pid-owner', 'recorded_owner_not_absent'), ('source', 'runtime_source_changed'),
                           ('hardware', 'hardware_validation_stale')]:
            with self.subTest(case=case), Harness() as h:
                if case == 'boot': h.base.boot = 'changed-boot'
                elif case == 'native-id': h.native['Id'] = 'f' * 64
                elif case == 'native-generation': h.native['State']['Pid'] += 1
                elif case == 'pid-owner': h.owner_present = True
                elif case == 'source': h.base.source_valid = False
                else: h.base.hardware_valid = False
                with self.assertRaisesRegex(RuntimeError, code): h.run()
                self.assert_unchanged(h)

    def test_preexisting_uncertain_stop_or_remove_cannot_enter_cleanup(self):
        for action in ('stop', 'remove'):
            with self.subTest(action=action), Harness() as h:
                state = h.runtime.state()
                state['native_actions'][action] = 'dispatched'
                h.anchor.atomic_json('state.json', state)
                # An independently reviewed fixture hash cannot make an already
                # dispatched destructive action a safe first entry.
                with patch.dict(reconcile.OLD_RECORDS, {'state.json': reconcile.sha(h.read('state.json'))}):
                    with self.assertRaisesRegex(RuntimeError, 'uncertain_cleanup_action'): h.run()
                self.assert_unchanged(h)

    def test_missing_physical_absence_proof_cannot_install_or_release_reservation(self):
        with Harness() as h:
            original = h.native_command
            def inventory(argv, **kwargs):
                result = original(argv, **kwargs)
                if argv[:3] == ['docker', 'container', 'ls']:
                    result.stdout = json.dumps({'ID': 'f' * 64, 'Names': service.NAME}) + '\n'
                return result
            with patch.object(service, 'run', side_effect=inventory):
                with self.assertRaisesRegex(RuntimeError, 'image_native_absence_unproven'): h.run()
            self.assertEqual(h.read('source/service.py'), h.old_source)
            self.assertEqual(h.runtime.record('recovery.json')['status'], 'active')
            self.assertIsNone(h.anchor.stat('h032-image-handoff.json', missing_ok=True))
            self.assertIsNone(h.anchor.stat(reconcile.PREFIX + 'settlement.json', missing_ok=True))
            with self.assertRaisesRegex(RuntimeError, 'plan_already_consumed'): h.run()

    def test_expired_activation_refuses_before_archive_or_intent(self):
        with Harness() as h, patch.object(reconcile.time, 'time', return_value=reconcile.END):
            with self.assertRaisesRegex(RuntimeError, 'wrong_reviewed_case'): h.run()
            self.assert_unchanged(h)
            self.assertIsNone(h.anchor.stat(reconcile.PREFIX + 'archive', missing_ok=True))

    def test_archive_failure_never_consumes_or_changes_retained_records(self):
        with Harness() as h:
            real = reconcile.immutable
            def fail_archive(anchor, name, content):
                if name.endswith('/native-backend.log'):
                    raise OSError('fake archive fsync failure')
                return real(anchor, name, content)
            with patch.object(reconcile, 'immutable', side_effect=fail_archive):
                with self.assertRaisesRegex(OSError, 'fake archive fsync failure'): h.run()
            self.assert_unchanged(h)
            self.assertIsNotNone(h.anchor.stat(reconcile.PREFIX + 'archive/state.json'))

    def test_later_successor_during_slow_archive_is_not_cleaned(self):
        with Harness() as h:
            def collect(*args):
                digest = reconcile.archive(*args)
                changed = copy.deepcopy(h.op)
                changed['token'] = 'f' * 32
                h.anchor.atomic_json('operation.json', changed)
                return digest
            with self.assertRaisesRegex(RuntimeError, 'predecessor_bytes_changed'):
                h.run(collect=collect)
            self.assertEqual(h.runtime.record('operation.json')['token'], 'f' * 32)
            self.assertEqual(h.commands, [])
            self.assertIsNone(h.anchor.stat(reconcile.PREFIX + 'consumed.json', missing_ok=True))

    def test_lost_stop_ack_remains_unresolved_and_consumed_no_replay(self):
        with Harness() as h:
            real = h.native_command
            def lost_ack(argv, **kwargs):
                if argv[:2] == ['docker', 'stop']:
                    real(argv, **kwargs)
                    raise subprocess.TimeoutExpired(argv, 45)
                return real(argv, **kwargs)
            with patch.object(service, 'run', side_effect=lost_ack):
                with self.assertRaises(subprocess.TimeoutExpired): h.run()
            self.assertEqual(h.runtime.state()['native_actions']['stop'], 'dispatched')
            self.assertEqual(h.runtime.state()['native_actions']['warm'], 'dispatched')
            self.assertEqual(h.runtime.record('recovery.json')['status'], 'active')
            self.assertIsNone(h.anchor.stat('h032-image-handoff.json', missing_ok=True))
            self.assertEqual(h.read('source/service.py'), h.old_source)
            with self.assertRaisesRegex(RuntimeError, 'plan_already_consumed'): h.run()
            self.assertEqual(h.events, ['stop'])

    def test_descriptors_exclude_concurrent_recovery_through_cleanup_and_install(self):
        for phase in ('stop', 'load-corrected-owner'):
            with self.subTest(phase=phase), Harness() as h:
                entered, release = threading.Event(), threading.Event()
                errors = []
                def block():
                    entered.set()
                    if not release.wait(3): raise AssertionError('finite fake boundary deadline')
                native, load = h.native_command, h.load_owner
                def native_boundary(argv, **kwargs):
                    if phase == 'stop' and argv[:2] == ['docker', 'stop']: block()
                    return native(argv, **kwargs)
                def install_boundary(expected):
                    if phase == 'load-corrected-owner': block()
                    return load(expected)
                def worker():
                    try: h.run()
                    except BaseException as error: errors.append(error)
                with patch.object(service, 'run', side_effect=native_boundary), \
                     patch.object(reconcile, 'load_owner', side_effect=install_boundary):
                    thread = threading.Thread(target=worker)
                    thread.start()
                    try:
                        self.assertTrue(entered.wait(2), errors)
                        h.base.assert_common_available()
                        contender = h.base.make_runtime()
                        for name in ('recovery.lock', 'operation.lock'):
                            with self.assertRaisesRegex(RuntimeError, 'image_operation_busy'):
                                with contender.singleton(name): self.fail('concurrent owner admitted')
                    finally:
                        release.set()
                        thread.join(3)
                self.assertFalse(thread.is_alive())
                self.assertEqual(errors, [])

    def test_consumed_intent_follows_verified_archive_and_precedes_record_changes(self):
        with Harness() as h:
            original = reconcile.immutable
            intents = []
            def inspect_order(anchor, name, content):
                if name == reconcile.PREFIX + 'consumed.json':
                    manifest = anchor.read_json(reconcile.PREFIX + 'archive-manifest.json')
                    self.assertGreater(len(manifest['files']), 10)
                    for item, digest in manifest['files'].items():
                        self.assertEqual(reconcile.sha(h.read(reconcile.PREFIX + 'archive/' + item)), digest)
                    self.assertEqual(h.read('operation.json'), h.originals['operation.json'])
                    self.assertEqual(h.read('recovery.json'), h.originals['recovery.json'])
                    self.assertEqual(h.commands, [])
                    intents.append(name)
                return original(anchor, name, content)
            with patch.object(reconcile, 'immutable', side_effect=inspect_order): h.run()
            self.assertEqual(len(intents), 1)

    def test_busy_or_replaced_descriptor_cannot_authorize_cleanup(self):
        for name in ('recovery.lock', 'operation.lock'):
            with self.subTest(lock=name), Harness() as h:
                with h.runtime.singleton(name):
                    with self.assertRaisesRegex(RuntimeError, 'image_operation_busy'): h.run()
                self.assert_unchanged(h)
            with self.subTest(replaced=name), Harness() as h:
                def collect(*args):
                    digest = reconcile.archive(*args)
                    (h.root / name).unlink()
                    (h.root / name).touch(mode=0o600)
                    return digest
                with self.assertRaises(protocol.storage_io.StorageIOError): h.run(collect=collect)
                self.assert_unchanged(h)

    def test_install_cas_refuses_later_source_after_exact_cleanup(self):
        with Harness() as h:
            original = h.native_command
            def successor(argv, **kwargs):
                result = original(argv, **kwargs)
                if argv[:2] == ['docker', 'rm']:
                    h.write('source/service.py', b'# later unrelated source owner\n')
                return result
            with patch.object(service, 'run', side_effect=successor):
                with self.assertRaisesRegex(RuntimeError, 'install_cas_changed'): h.run()
            self.assertEqual(h.read('source/service.py'), b'# later unrelated source owner\n')
            self.assertEqual(h.read('config.json'), h.originals['config.json'])
            self.assertEqual(h.runtime.record('recovery.json')['status'], 'active')
            self.assertIsNone(h.anchor.stat('h032-image-handoff.json', missing_ok=True))
            with self.assertRaisesRegex(RuntimeError, 'plan_already_consumed'): h.run()
            self.assertEqual(h.events, ['stop', 'rm'])

    def test_partial_install_crash_preserves_active_reservation_and_no_handoff(self):
        with Harness() as h:
            original = h.anchor.replace
            def crash(source, destination):
                if destination == 'config.json': raise OSError('fake crash before config rename')
                return original(source, destination)
            with patch.object(h.anchor, 'replace', side_effect=crash):
                with self.assertRaisesRegex(OSError, 'fake crash before config rename'): h.run()
            self.assertEqual(h.read('source/service.py'), h.new_source)
            self.assertEqual(h.read('config.json'), h.originals['config.json'])
            self.assertEqual(h.runtime.record('recovery.json')['status'], 'active')
            self.assertEqual(h.read(reconcile.PREFIX + 'archive/state.json'), h.originals['state.json'])
            self.assertIsNone(h.anchor.stat('h032-image-handoff.json', missing_ok=True))
            with self.assertRaisesRegex(RuntimeError, 'plan_already_consumed'): h.run()
            self.assertEqual(h.events, ['stop', 'rm'])

    def test_real_common_policy_keeps_peer_latch_and_validates_only_image_gpu(self):
        from lifecycle.hardware_policy import HardwarePolicy, STATE_SUFFIX, GPU_UUIDS
        with Harness() as h:
            peer = next(gpu for gpu in GPU_UUIDS if gpu != reconcile.GPU)
            peer_record = {'boot_id': reconcile.BOOT, 'hardware_latched': True,
                'reason': 'hardware_fault', 'hardware_fault_code': 'gpu_fallen_off_bus',
                'evidence': [{'observed_at': service.now(), 'observation_id': 'peer-proof'}]}
            h.anchor.mkdir('llm-manager')
            h.anchor.atomic_json(STATE_SUFFIX, {'schema_version': 1, 'targets': {peer: peer_record}})
            h.runtime.require_hardware = service.Runtime.require_hardware.__get__(h.runtime)
            def policy(store, **kwargs):
                return HardwarePolicy(store, system_root=h.root, trusted_uid=os.geteuid(),
                    boot=lambda: {'boot_id': reconcile.BOOT, 'uptime_seconds': 300}, **kwargs)
            with patch.object(service, 'HardwarePolicy', side_effect=policy): h.run()
            latch = h.anchor.read_json(STATE_SUFFIX)
            self.assertEqual(latch['targets'][peer], peer_record)
            self.assertEqual(set(latch['validated']), {reconcile.GPU})

    def test_target_gpu_probes_and_idle_proof_never_require_peer_negatives(self):
        with Harness() as h:
            h.runtime.boot = reconcile.BOOT
            def target_probe(argv, **_kwargs):
                self.assertEqual(argv, ['/usr/bin/nvidia-smi', '--id=' + reconcile.GPU,
                    '--query-gpu=uuid', '--format=csv,noheader,nounits'])
                return subprocess.CompletedProcess(argv, 0, reconcile.GPU + '\n', '')
            with patch.object(service, 'run', side_effect=target_probe):
                proof = service.Runtime.probe_hardware(h.runtime)
            self.assertEqual(proof['boot'], reconcile.BOOT)
            h.run()
            gpu_commands = [a for a in h.commands if a[0] == 'nvidia-smi']
            self.assertTrue(gpu_commands)
            self.assertTrue(all('--id=' + reconcile.GPU in a for a in gpu_commands))
            self.assertTrue(all('warm' not in a and 'start' not in a and 'create' not in a for a in h.commands))


if __name__ == '__main__':
    unittest.main()
