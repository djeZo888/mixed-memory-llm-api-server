"""Focused R9 authority, predecessor and unchanged safety contracts; local only."""
import ast
import datetime
import hashlib
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import candidate_owner as owner


ROOT = pathlib.Path(__file__).resolve().parent


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


class FinalOwnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temp.name)
        self.cfg = json.loads((ROOT / 'LAUNCH.json').read_text())
        self.winner = {'authorized': True, 'threads': 16, 'context': 1000000,
                       'expected_physical_cache_pool_tokens': 1000192,
                       'physical_padding_multiple': 256,
                       'logging_decision': {'keep_existing_default_verbosity': 3,
                           'add_log_verbosity4_authorized': False,
                           'missing_safe_component_log_is_not_failure': True}}
        self.hashes = {name: hashlib.sha256(name.encode()).hexdigest()
                       for name in owner.SOURCE_NAMES}
        self.hashes['mimo-production-fixture-65536.json'] = owner.FIXTURE_SHA
        self.go = {'authorized': True, 'expires_utc': '2026-09-27T16:50:00+00:00',
                   'source_sha256': {name: self.hashes[name] for name in owner.SOURCE_NAMES},
                   'fixture_sha256': owner.FIXTURE_SHA}

    def tearDown(self):
        self.temp.cleanup()

    def validate(self, *, rebind=True, now=None):
        raw = json.dumps(self.winner).encode()
        (self.base / 'ROOT-WINNER.json').write_bytes(raw)
        if rebind:
            self.go['winner_sha256'] = hashlib.sha256(raw).hexdigest()
        (self.base / 'ROOT-R9-GO.json').write_text(json.dumps(self.go))
        with mock.patch.object(owner, 'BASE', str(self.base)), \
                mock.patch.object(owner.time, 'time', return_value=now or owner.ADMIT_END - 3600):
            owner.validate_authority(self.cfg, self.hashes)

    def test_missing_component_logs_allowed_but_conflict_refused(self):
        from allocation import parse_native_allocation
        harness = type('Harness', (), {'require': staticmethod(require)})()
        proof = parse_native_allocation('', 1000000, expected_pool_context=1000192)
        owner.require_consistent_components(harness, proof, 1000000, 1000192)
        proof['native_context_records'] = [1048576]
        with self.assertRaisesRegex(RuntimeError, 'observed_native_context_mismatch'):
            owner.require_consistent_components(harness, proof, 1000000, 1000192)
        proof['native_context_records'] = []
        proof['slot_records'] = [{'slots': 1, 'context': 131072}]
        with self.assertRaisesRegex(RuntimeError, 'observed_slot_log_mismatch'):
            owner.require_consistent_components(harness, proof, 1000000, 1000192)

    def test_exact_scoped_authority_accepts(self):
        self.validate()

    def test_missing_or_drifted_executable_closure_refused(self):
        for name in sorted(owner.SOURCE_NAMES):
            with self.subTest(name=name):
                digest = self.go['source_sha256'].pop(name)
                with self.assertRaisesRegex(RuntimeError, 'source_closure'):
                    self.validate()
                self.go['source_sha256'][name] = digest
        self.hashes['benchmark.py'] = '0' * 64
        with self.assertRaisesRegex(RuntimeError, 'source_closure'):
            self.validate()

    def test_missing_or_changed_fixture_refused(self):
        self.hashes['mimo-production-fixture-65536.json'] = '0' * 64
        with self.assertRaisesRegex(RuntimeError, 'production_fixture_not_bound'):
            self.validate()
        del self.hashes['mimo-production-fixture-65536.json']
        with self.assertRaisesRegex(RuntimeError, 'production_fixture_not_bound'):
            self.validate()

    def test_winner_authorization_digest_threads_and_padding_refused(self):
        self.validate()
        self.winner['threads'] = 64
        with self.assertRaisesRegex(RuntimeError, 'root_winner_not_bound'):
            self.validate(rebind=False)
        for threads in [True, 32, '16']:
            with self.subTest(threads=threads):
                self.winner['threads'] = threads
                with self.assertRaisesRegex(RuntimeError, 'root_threads_invalid'):
                    self.validate()
        self.winner['threads'] = 16
        self.winner['physical_padding_multiple'] = 512
        with self.assertRaisesRegex(RuntimeError, 'physical_padding_not_reviewed'):
            self.validate()
        self.winner['physical_padding_multiple'] = 256
        self.winner['authorized'] = False
        with self.assertRaisesRegex(RuntimeError, 'root_authority_missing'):
            self.validate()

    def test_no_implicit_capacity_fallback(self):
        self.winner['context'] = self.cfg['capacity'] = 917504
        with self.assertRaisesRegex(RuntimeError, 'r9_context_requires_exact_review'):
            self.validate()

    def test_expiry_and_admission_are_absolute(self):
        self.validate()
        self.go['expires_utc'] = '2026-09-27T17:00:01+00:00'
        with self.assertRaisesRegex(RuntimeError, 'root_go_expired_or_outside_admission'):
            self.validate()
        self.go['expires_utc'] = '2026-09-27T16:00:00+00:00'
        with self.assertRaisesRegex(RuntimeError, 'root_go_expired_or_outside_admission'):
            self.validate()
        self.go['expires_utc'] = '2026-09-27T16:50:00+00:00'
        self.cfg['request_end_utc'] = '2026-09-27T17:26:00Z'
        with self.assertRaisesRegex(RuntimeError, 'deadline_changed'):
            self.validate()

    def test_current_logging_decision_keeps_verbosity_three(self):
        # Scoped ROOT-WINNER explicitly declines verbosity 4 and its extra traces.
        self.assertNotIn('--log-verbosity', self.cfg['native_argv'])
        self.assertEqual(self.cfg['capacity'], 1000000)
        self.assertEqual(self.cfg['physical_cache_pool_tokens'], 1000192)

    def test_logging_delta_or_changed_missing_log_policy_refused(self):
        self.cfg['native_argv'].extend(['--log-verbosity', '4'])
        with self.assertRaisesRegex(RuntimeError, 'unapproved_logging_delta'):
            self.validate()
        del self.cfg['native_argv'][-2:]
        self.winner['logging_decision']['missing_safe_component_log_is_not_failure'] = False
        with self.assertRaisesRegex(RuntimeError, 'allocation_logging_decision_changed'):
            self.validate()

    def predecessor(self, change_old=None, change_container=None, change_props=None,
                    exists=()):
        cid = '45c1a8e97199fc6876b6e9add26cfc956e03a1304d695ecf961ab940293d3aff'
        started = '2026-09-27T15:15:50.592314598Z'
        old = {'candidate_id': cid, 'native_pid': 942451, 'pid': 939758,
               'native_started_at': started, 'status': 'SETTLED_GLM_RESTORED',
               'glm_suppressed': False, 'glm_restored_utc': '2026-09-27T15:34:00Z',
               'native_cgroup': '/sys/fs/cgroup/exact-r8', 'proxy_pid': 944000,
               'native_settled': {key: True for key in
                   ['pid_zero', 'cgroup_empty', 'gpu_compute_empty']}}
        container = {'Id': cid, 'Image': owner.IMAGE, 'Name': '/llm-h016-mimo-pro-r8',
                     'State': {'Running': False, 'Pid': 0, 'StartedAt': started}}
        props = {'MainPID': '0', 'ControlPID': '0', 'ActiveState': 'failed',
                 'InvocationID': 'f7eedd254a734907996d310a4feb7349'}
        if change_old:
            change_old(old)
        if change_container:
            change_container(container)
        if change_props:
            change_props(props)
        h = mock.Mock()
        h.require.side_effect = require
        with mock.patch.object(pathlib.Path, 'read_text', return_value=json.dumps(old)), \
                mock.patch.object(pathlib.Path, 'exists', autospec=True,
                                  side_effect=lambda p: str(p) in exists), \
                mock.patch.object(owner, 'inspect', return_value=container), \
                mock.patch.object(owner, 'run_cmd', return_value='\n'.join(k + '=' + v for k, v in props.items())):
            owner.require_r8_settled(h)

    def test_exact_r8_failed_unit_with_real_settlement_accepted(self):
        self.predecessor()
        self.predecessor(change_props=lambda p: p.update(ActiveState='inactive'))

    def test_wrong_predecessor_or_unreleased_owner_refused(self):
        cases = [
            ({'change_old': lambda o: o.update(native_pid=942452)}, 'r8_identity_changed'),
            ({'change_old': lambda o: o.update(status='FAILED_SETTLING')}, 'r8_not_normally_settled'),
            ({'change_old': lambda o: o['native_settled'].update(gpu_compute_empty=False)}, 'r8_not_normally_settled'),
            ({'change_container': lambda c: c['State'].update(Pid=942451)}, 'r8_native_not_settled'),
            ({'change_props': lambda p: p.update(InvocationID='different')}, 'r8_invocation_changed'),
            ({'change_props': lambda p: p.update(MainPID='939758')}, 'r8_owner_active'),
            ({'exists': ['/sys/fs/cgroup/exact-r8']}, 'r8_process_or_cgroup_present'),
            ({'exists': ['/proc/942451']}, 'r8_process_or_cgroup_present'),
            ({'exists': ['/proc/939758']}, 'r8_process_or_cgroup_present'),
            ({'exists': ['/proc/944000']}, 'r8_proxy_present'),
            ({'exists': ['/sys/fs/cgroup/system.slice/h016-mimo-profile-20260927-r8.service']}, 'r8_unit_cgroup_present')]
        for kwargs, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(RuntimeError, reason):
                    self.predecessor(**kwargs)

    def test_safety_cleanup_functions_unchanged_from_reviewed_r8(self):
        def functions(path):
            return {node.name: ast.dump(node, include_attributes=False)
                    for node in ast.parse(path.read_text()).body if isinstance(node, ast.FunctionDef)}
        old = functions(ROOT.parent / 'r8/candidate_owner.py')
        new = functions(ROOT / 'candidate_owner.py')
        for name in ['suppress', 'settle', 'cleanup_proxy_and_settle', 'interrupted']:
            self.assertEqual(old[name], new[name], name)
        old = functions(ROOT.parent / 'r8/telemetry.py')
        new = functions(ROOT / 'telemetry.py')
        self.assertEqual(old['monitor'], new['monitor'])

    def test_proxy_deadlines_and_capacity_match_owner(self):
        source = (ROOT / 'private_proxy.py').read_text()
        dates = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == 'datetime':
                dates.append(tuple(arg.value for arg in node.args if isinstance(arg, ast.Constant)))
        self.assertEqual(sorted(dates), [(2026, 9, 27, 17, 0), (2026, 9, 27, 17, 25)])
        self.assertIn("['capacity']", source)
        self.assertNotIn('131072', source)
        self.assertEqual(owner.ADMIT_END, datetime.datetime(2026, 9, 27, 17, 0,
                         tzinfo=datetime.timezone.utc).timestamp())
        self.assertEqual(owner.HARD_END, datetime.datetime(2026, 9, 27, 17, 25,
                         tzinfo=datetime.timezone.utc).timestamp())


if __name__ == '__main__':
    unittest.main()
