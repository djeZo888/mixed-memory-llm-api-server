"""Offline actual held RPC + canonical PID lease; never runs systemctl or contacts a host."""
from contextlib import contextmanager
from dataclasses import replace
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tests import test_postrestart72_clocks as clocks
from benchmark import cpu_budget_profiles as profile, fixtures
from benchmark.lifecycle import CONTROL_UNIT, digest


class HeldJobsTests(unittest.TestCase):
    @contextmanager
    def held(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture, owner, budget, _ = clocks.HoldTests().owned_pair(directory)
            owner.warm_hold('complete')
            host = clocks.HostIntegrationTests().held_host()
            host.owner, host.budget = owner, budget
            host.config = json.loads((Path(__file__).resolve().parents[1] /
                                      'configs/benchmarks/gpu-split-20260919.json').read_text())
            host.run_session_id, host.run_source_commit = 'original-run', 'a' * 40
            host.pin_sources, host.write_json = Mock(), Mock()
            host.guards = fixture.guards
            host.units = lambda: copy.deepcopy(fixture.state['services'])
            host.load_manifests = dict(zip(fixture.containers, (profile.postrestart_manifest(p) for p in ('G1', 'Q1'))))
            host.allocation_proofs = {cid: {} for cid in fixture.containers}
            host.concurrent_pressure = Mock(return_value={'status': 'PASS', 'unavailable_reasons': []})
            host._readiness = Mock(return_value={'ready': True,
                'allocation': {'status': 'ALLOCATION_PROOF_ACCEPTED'}, 'observed': {}})
            host.followup_request, host.followup_admitted = None, set()
            owner.host = replace(owner.host, gate=host.gate)
            sample = {'cgroups': {cid: {'events': {'oom': 0}, 'swap_bytes': 0} for cid in fixture.containers}}
            def native(port, route, **kwargs):
                if route == '/v1/models':
                    return {'data': [{'id': 'bench-glm-5.3' if port == 31002 else 'bench-qwen3.8-27b'}]}
                return {'context_length': 480000, 'tp_size': 1,
                        'max_total_num_tokens': 480000, 'max_req_input_len': 479994}
            try:
                with patch('benchmark.host.collect_sample', return_value=sample), \
                     patch('benchmark.host.http_json', side_effect=native):
                    yield host, fixture, owner
            finally:
                if owner.lease_context:
                    owner.lease_context.__exit__(None, None, None)

    def commands(self, raw, *, props=None, after=None, missing=False, timeout_units=()):
        calls = []
        def command(argv, *args, **kwargs):
            calls.append(argv)
            result = SimpleNamespace(returncode=0, stdout=b'', stderr=b'')
            if argv[0] == '/usr/bin/ss':
                return result
            if argv[1] == 'list-jobs':
                if missing:
                    raise TimeoutError('synthetic read gap')
                result.stdout = (after if after is not None and sum(a[1] == 'list-jobs' for a in calls) > 1 else raw).encode()
                return result
            self.assertEqual(argv[1], 'show')
            if argv[2] in timeout_units:
                raise TimeoutError('synthetic unit evidence gap')
            keys = argv[-1].split('=', 1)[1].split(',')
            fields = dict.fromkeys(keys, '')
            fields.update(Id=argv[2], Names=argv[2], LoadState='loaded')
            fields.update((props or {}).get(argv[2], {}))
            result.stdout = '\n'.join(k + '=' + v for k, v in fields.items()).encode()
            return result
        return command

    def test_unrelated_passive_job_actual_dispatch_keeps_same_PID_lease_pair_and_evidence(self):
        with self.held() as (host, fixture, owner):
            lease, resources = owner.lease, copy.deepcopy(owner.resources)
            with patch('benchmark.host.command', side_effect=self.commands('91 isolated.target start waiting\n')):
                result = host.dispatch({'op': 'hold_checkpoint'})
            self.assertEqual(result['status'], 'HELD')
            self.assertEqual(result['systemd_jobs']['jobs'][0]['classification'], 'UNRELATED_PASSIVE')
            self.assertIs(owner.lease, lease); lease.validate()
            self.assertEqual(owner.phase, 'WARM_HOLD'); self.assertEqual(owner.resources, resources)
            self.assertEqual(len(fixture.containers), 2)
            saved = host.write_json.call_args.args[1]
            self.assertEqual(len(saved['snapshots']), 2)
            self.assertIn('isolated.target', saved['unit_evidence'])

    def test_unknown_missing_changed_and_foreign_scope_remain_guarded_review(self):
        for raw, options in [('15 background.service start running\n', {}),
                             ('15 docker-client-refresh.service start running\n', {}),
                             ('malformed\n', {}), ('', {'missing': True}),
                             ('15 session-9.scope stop waiting\n', {}),
                             ('15 mnt-external.mount stop waiting\n', {}),
                             ('15 passive.target start waiting\n', {'after': ''}),
                             ('15 passive.timer start waiting\n', {'props': {'passive.timer': {'LoadState': ''}}}),
                             ('15 passive.target start waiting\n', {'props': {
                                 'passive.target': {'WantedBy': 'other.target'}, 'other.target': {'Requires': 'docker.service'}}}),
                             ('15 passive.timer start waiting\n', {'props': {'passive.timer': {'Conflicts': 'shutdown.target'}}})]:
            with self.subTest(raw=raw, options=options), self.held() as (host, fixture, owner):
                with patch('benchmark.host.command', side_effect=self.commands(raw, **options)):
                    result = host.dispatch({'op': 'hold_checkpoint'})
                self.assertEqual(result['status'], 'REVIEW_REQUIRED')
                self.assertTrue(result['guarded']); owner.lease.validate()
                self.assertEqual(owner.phase, 'WARM_HOLD'); self.assertEqual(len(fixture.containers), 2)

    def test_direct_runtime_registered_storage_shutdown_and_causal_alias_hazards(self):
        rows = [('42 docker.service restart waiting\n', {}),
                ('42 data.mount stop waiting\n', {}),
                ('42 data-models\\x2dlarge.mount stop waiting\n', {}),
                ('42 systemd-reboot.service start running\n', {}),
                ('42 shutdown.target start waiting\n', {}),
                ('malformed\n42 reboot.target start waiting\n', {}),
                ('42 reboot.target start waiting\nmalformed\n', {}),
                ('42 alias.service stop waiting\n', {'props': {'alias.service': {'Names': 'alias.service docker.service'}}}),
                ('42 dev-sdb.device stop waiting\n', {'props': {'dev-sdb.device': {'Names':
                    'dev-sdb.device dev-disk-by\\x2duuid-a6d4ab58\\x2d84e1\\x2d4e48\\x2d9a67\\x2d13ad1c6f6e0a.device'}}}),
                ('42 passive.target start waiting\n', {'props': {'passive.target': {'Requires': 'docker.service'}}}),
                ('42 passive.target start waiting\n', {'props': {'passive.target': {'Conflicts': 'docker.service'}}}),
                ('42 passive.target start waiting\n', {'props': {
                    'passive.target': {'Requires': 'docker.service unavailable.target'}}, 'timeout_units': ('unavailable.target',)}),
                ('42 passive.target start waiting\n', {'after': '43 reboot.target start running\n'})]
        for raw, options in rows:
            with self.subTest(raw=raw), self.held() as (host, fixture, owner):
                with patch('benchmark.host.command', side_effect=self.commands(raw, **options)):
                    with self.assertRaisesRegex(ValueError, 'postrestart_held_systemd_job_hazard'):
                        host.dispatch({'op': 'hold_checkpoint'})
                self.assertEqual(host.write_json.call_args.args[1]['status'], 'HAZARD')
                owner.lease.validate()  # failure disposition remains existing supervisor responsibility

    def test_resource_control_and_ordinary_jobs_gates_are_preserved(self):
        with self.held() as (host, fixture, owner):
            with patch('benchmark.host.command', side_effect=self.commands('42 isolated.target start waiting\n')):
                with self.assertRaisesRegex(ValueError, 'pending_systemd_jobs'):
                    host.gate('restore', owner.lease, owner.original, owner.resources)
                fixture.state['services'][CONTROL_UNIT]['active'] = 'active'
                with self.assertRaisesRegex(ValueError, 'control_not_frozen'):
                    host.dispatch({'op': 'hold_checkpoint'})
                fixture.state['services'][CONTROL_UNIT]['active'] = 'inactive'
                host.concurrent_pressure.return_value = {'status': 'STOP_RESOURCE_GATE', 'unavailable_reasons': []}
                with self.assertRaisesRegex(ValueError, 'postrestart_unsafe_hold_forbidden'):
                    host.dispatch({'op': 'hold_checkpoint'})

    def followup(self, host):
        saved = {'phase': 'WARM_HOLD', 'reason': 'complete'}
        host.read_json = Mock(return_value=saved)
        return {'decision': 'GO', 'source_commit': host.run_source_commit,
            'owner_run_session_id': host.run_session_id, 'followup_session_id': 'fresh-review',
            'campaign': host.campaign, 'warm_hold_receipt_sha256': fixtures.digest(fixtures.canonical(saved) + b'\n'),
            'placement': 'G1', 'preset': 'P-G4K', 'manifest_sha256': digest(profile.postrestart_manifest('G1')),
            'request_sha256': 'b' * 64, 'fixture_sha256': 'c' * 64, 'request_id': 'reviewed-extra',
            'policy': {'measurement_admission_seconds': 21600, 'request_timeout_seconds': 7200,
                       'request_clock_starts': 'HTTP_DISPATCH', 'admission_deadline_refuses_new_only': True}}

    def test_full_proof_and_second_owner_gate_block_admission_without_transition(self):
        for race in (False, True):
            with self.subTest(race=race), self.held() as (host, fixture, owner):
                go = self.followup(host)
                if race:
                    host.postrestart_hold_proof = Mock(return_value={'status': 'HELD'})
                with patch('benchmark.host.command', side_effect=self.commands('3 background.service start waiting\n')):
                    result = host.dispatch({'op': 'admit_followup', 'go': go})
                self.assertIs(result['admitted'], False); self.assertTrue(result['proof_pending'])
                self.assertEqual(owner.phase, 'WARM_HOLD'); self.assertFalse(owner.additional_followup_used)
                self.assertIsNone(host.followup_request); owner.lease.validate()

    def test_hold_entry_second_gate_downgrades_current_missing_proof(self):
        with self.held() as (host, fixture, owner):
            owner.phase = 'ACTIVE'
            host.postrestart_hold_proof = Mock(return_value={'status': 'HELD', 'unavailable_reasons': []})
            with patch('benchmark.host.command', side_effect=self.commands('3 background.service start waiting\n')):
                result = host.warm_hold('complete')
            self.assertEqual(result['status'], 'REVIEW_REQUIRED')
            self.assertEqual(result['entry_systemd_jobs']['status'], 'REVIEW_REQUIRED')
            self.assertEqual(owner.phase, 'WARM_HOLD'); owner.lease.validate()

    def test_missing_or_malformed_second_owner_proof_refuses_both_followup_paths(self):
        for proof in (None, {}, {'status': 'UNKNOWN'}):
            for resume in (False, True):
                with self.subTest(proof=proof, resume=resume), self.held() as (host, fixture, owner):
                    owner.host = replace(owner.host, gate=Mock(return_value=proof))
                    identity = {'session_id': 'fresh-review', 'source_commit': 'a' * 40}
                    if resume:
                        owner.warm_hold_reason = 'preliminary_review'
                        result = owner.resume_measurements(identity)
                    else:
                        result = owner.admit_followup(identity)
                    self.assertIs(result['admitted'], False)
                    self.assertEqual(owner.phase, 'WARM_HOLD')
                    self.assertFalse(owner.warm_hold_resumed or owner.additional_followup_used)
                    owner.lease.validate()


if __name__ == '__main__':
    unittest.main()
