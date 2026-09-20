"""Focused offline sealed warm-only sequence, authority and package contracts."""
import ast
import copy
from dataclasses import replace
import json
from pathlib import Path
import stat
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import cpu_budget_profiles as profile, fixtures, postrestart72_run as run72, runner
from tests.test_benchmark_client import event, stream
from tests.test_postrestart72_run import ARCHIVES, SOURCES, armed


def warm_arm():
    value = armed()
    value.update(mode=profile.POSTRESTART_WARM_ONLY_MODE, campaign=profile.POSTRESTART_WARM_CAMPAIGN,
        manifests=profile.postrestart_manifests(profile.POSTRESTART_WARM_CAMPAIGN),
        trial_plan=profile.postrestart_trial_order(profile.POSTRESTART_WARM_ONLY_MODE))
    return value


class WarmOnlyContractTests(unittest.TestCase):
    def test_actual_retained_host_owner_followup_from_never_measured_clock(self):
        from benchmark.host import LinuxHost, _COMMAND_DEADLINE
        from benchmark import cpu_budget_host as cpu_proof
        from benchmark import postrestart72_followup as followup
        from tests.test_postrestart72_clocks import HoldTests
        from tests.test_postrestart72_proc_snapshot import CoherentProcSnapshotTests
        proc = CoherentProcSnapshotTests(); proc.setUp(); self.addCleanup(proc.doCleanups)
        with tempfile.TemporaryDirectory() as directory:
            fixture, owner, budget, now = HoldTests().owned_pair(directory, measured=False)
            lease = owner.lease
            original_gate = owner.host.gate
            def gate(*args):
                original_gate(*args)
                return {'status': 'HELD', 'jobs': []}
            owner.host = replace(owner.host, gate=gate)
            try:
                host = LinuxHost.__new__(LinuxHost)
                host.scope, host.campaign, host.owner = profile.POSTRESTART_SCOPE, profile.POSTRESTART_WARM_CAMPAIGN, owner
                host.run_source_commit, host.run_session_id = 'a' * 40, 'warm-run-session'
                host.budget, host.followup_request = budget, None
                host.concurrent_resource_violations = {}; host.requests = {}
                host.config = {'lease': '/run/llmctl/lifecycle.lock'}
                ids = list(fixture.containers)
                host.load_manifests = dict(zip(ids, profile.postrestart_manifests(host.campaign)))
                host.allocation_proofs = dict.fromkeys(ids, {})
                host.assert_idle = Mock(); host.guards = fixture.guards
                cpu_observations = []
                def readiness(cid):
                    manifest = host.load_manifests[cid]
                    proc.cid = cid
                    proc.container['Id'] = cid
                    proc.container['HostConfig']['CpusetCpus'] = manifest['guest_cpuset']
                    (proc.group / 'cpuset.cpus.effective').write_text(manifest['guest_cpuset'])
                    for pid in (44, 45):
                        (proc.proc / str(pid) / 'status').write_text(
                            'Cpus_allowed_list:\t' + manifest['guest_cpuset'] + '\nMems_allowed_list:\t0-7\n')
                    observed = cpu_proof.coherent_postrestart_cpu_proof(host, cid, manifest,
                        proc_root=proc.proc, sys_root=proc.system)
                    cpu_observations.append((owner.phase, budget.data['phase'], observed['status']))
                    return {'ready': True, 'allocation': {'status': 'ALLOCATION_PROOF_ACCEPTED'},
                            'observed': {'actual_cpu_scope': observed}}
                host.identity = proc.host.identity
                host._readiness = readiness
                saved = {}
                host.read_json = lambda name: copy.deepcopy(saved[name])
                host.write_json = lambda name, value: saved.update({name: copy.deepcopy(value)})
                with self.assertRaisesRegex(ValueError, 'warm_only_initial_measurement_forbidden'):
                    host.dispatch({'op': 'request_begin', 'id': ids[0], 'measured': True})
                self.assertIsNone(budget.data['started_at'])
                receipt = host.dispatch({'op': 'warm_hold', 'reason': 'complete'})
                self.assertEqual(receipt['status'], 'HELD')
                self.assertIsNone(receipt['budget']['started_at'])
                self.assertEqual(owner.phase, 'WARM_HOLD')
                now[0] += 9000  # idle hold outlives the original preparation bound
                budget.checkpoint(); original = budget.data
                # Missing RPC bound cannot borrow idle retention as unbounded proof.
                with self.assertRaisesRegex(ValueError, 'postrestart_held_cpu_bounded_rpc_required'):
                    readiness(ids[0])
                owner.lease = None
                with self.assertRaisesRegex(ValueError, 'postrestart_held_cpu_owner_required'):
                    readiness(ids[0])
                owner.lease = lease
                owner.phase = 'ACTIVE'
                with self.assertRaisesRegex(ValueError, '^STOP_BUDGET$'):
                    readiness(ids[0])
                owner.phase = 'WARM_HOLD'
                manifest = host.load_manifests[ids[0]]
                go = {'decision': 'GO', 'source_commit': host.run_source_commit,
                    'owner_run_session_id': host.run_session_id, 'followup_session_id': 'fresh-warm-followup',
                    'campaign': host.campaign, 'preset': 'P-G4K', 'placement': 'G1',
                    'warm_hold_receipt_sha256': fixtures.digest(fixtures.canonical(receipt) + b'\n'),
                    'manifest_sha256': fixtures.digest(fixtures.canonical(manifest)),
                    'request_sha256': 'b' * 64, 'fixture_sha256': 'c' * 64,
                    'request_id': 'F-warm-future-g4k', 'policy': copy.deepcopy(followup.POLICY)}
                arm = warm_arm(); arm.update(source_commit=host.run_source_commit, session_id=host.run_session_id)
                followup.validate_go(go, arm, go['warm_hold_receipt_sha256'])
                admitted = host.dispatch({'op': 'admit_followup', 'go': go})
                self.assertEqual(cpu_observations[-2:], [('WARM_HOLD', 'PREPARING', 'PASS')] * 2)
                self.assertIsNone(_COMMAND_DEADLINE.get())
                self.assertEqual(admitted['phase'], 'ACTIVE')
                self.assertEqual(budget.data['prior_segment'], original)
                self.assertIsNone(budget.data['prior_segment']['started_at'])
                self.assertIsNone(budget.data['prior_segment']['deadline_epoch'])
                self.assertIsNone(budget.data['started_at'])
                self.assertIs(owner.lease, lease); owner.lease.validate()
                self.assertEqual(len(fixture.containers), 2)
                host.identity = Mock(return_value=({}, Path('/synthetic'), [])); host.concurrent_limits = Mock()
                host.telemetry = Mock(return_value={'concurrent_resource_gate': {'status': 'PASS'}})
                identity = {k: go[k] for k in ('request_id', 'request_sha256', 'manifest_sha256')}
                now[0] += 5
                with patch('benchmark.cpu_budget_host.resident_obligations', return_value={}):
                    grant = host.dispatch({'op': 'request_begin', 'id': ids[0], 'measured': True,
                        'request_identity': identity})
                self.assertEqual(grant['timeout_s'], 7200)
                self.assertEqual(budget.data['started_at'], now[0])
                self.assertEqual(budget.data['deadline_epoch'], now[0] + 21600)
                self.assertEqual(budget.data['prior_segment'], original)
                host.dispatch({'op': 'request_end', 'id': ids[0]})
                owner.warm_hold('complete')
                self.assertIs(owner.lease, lease)
                owner.restore()
            finally:
                if owner.lease_context:
                    owner.lease_context.__exit__(None, None, None)

    def test_exact_mode_campaign_plan_and_actual_shared_staging_literal(self):
        value = warm_arm()
        profile.validate_postrestart_arm_scope(value)
        self.assertEqual(value['trial_plan']['trials'], [])
        self.assertEqual(value['trial_plan']['initial_measured_requests'], 0)
        self.assertEqual(value['trial_plan']['loads'], 2)
        self.assertEqual(value['trial_plan']['maximum_request_seconds'], 7200)
        contract = [node for node in ast.walk(ast.parse(runner.STAGE)) if isinstance(node, ast.Assert)
            and any(isinstance(part, ast.Name) and part.id == 'campaign' for part in ast.walk(node))]
        self.assertEqual(len(contract), 1)
        exec(compile(ast.Module(body=contract, type_ignores=[]), 'actual-STAGE', 'exec'),
             {'campaign': value['campaign']})
        for actual, previous in zip(value['manifests'], profile.postrestart_manifests()):
            for name in ('image', 'model', 'gpu_uuids', 'native_argv', 'configured_capacity',
                         'ram_cap_bytes', 'resource_policy', 'guest_cpuset', 'guest_mems_allowed'):
                self.assertEqual(actual[name], previous[name], name)
        for update in ({'mode': 'measured'}, {'mode': None}, {'campaign': profile.POSTRESTART_CAMPAIGN},
                       {'trial_plan': profile.postrestart_trial_order()}, {'manifests': profile.postrestart_manifests()}):
            bad = copy.deepcopy(value); bad.update(update)
            with self.assertRaises(ValueError): profile.validate_postrestart_arm_scope(bad)
        bad = copy.deepcopy(value); del bad['mode']
        with self.assertRaises(ValueError): profile.validate_postrestart_arm_scope(bad)
        profile.validate_postrestart_arm_scope(armed())  # Historical measured arm remains measured.

    def test_warm_GO_cannot_transpose_or_omit_mode_and_campaign(self):
        value = warm_arm(); value['session_id'] = 'prep-session'
        go = {'runtime': copy.deepcopy(run72.POLICY), 'run_session_id': 'fresh-run-session',
              'mode': value['mode'], 'campaign': value['campaign']}
        self.assertEqual(run72.bind_runtime(value, go, 'fresh-run-session'), run72.POLICY)
        for name, other in (('mode', 'measured'), ('campaign', profile.POSTRESTART_CAMPAIGN)):
            bad = copy.deepcopy(go); bad[name] = other
            with self.assertRaisesRegex(ValueError, 'exact_arm_GO'):
                run72.bind_runtime(value, bad, 'fresh-run-session')
            del bad[name]
            with self.assertRaisesRegex(ValueError, 'exact_arm_GO'):
                run72.bind_runtime(value, bad, 'fresh-run-session')
        normal = armed(); normal['session_id'] = 'prep-session'
        with self.assertRaisesRegex(ValueError, 'exact_arm_GO_mode'):
            run72.bind_runtime(normal, go, 'fresh-run-session')


@unittest.skipUnless(all((ARCHIVES / rel).is_file() for rel, _ in run72.SAVED.values()),
                     'operator private archives unavailable')
class WarmOnlyReadChainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.state = self.root / 'task'; self.state.mkdir(mode=0o700)
        for name, (relative, expected) in run72.SAVED.items():
            raw = (ARCHIVES / relative).read_bytes(); self.assertEqual(fixtures.digest(raw), expected)
            destination = self.root / relative; destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            destination.write_bytes(raw); destination.chmod(0o600)
        runner.save(self.state / 'evidence-index.json', {'refs': {}, 'protected_key_metadata': {'synthetic': True}})
        (self.state / 'incoming-latest.md').write_text('Offline warm-only test authority.\n')
        with patch.object(run72.glmrepair, 'git', side_effect=lambda *args: '' if args[0] == 'status' else run72.WARM_ONLY_BASE), \
             patch.object(runner, 'source_files', return_value=SOURCES):
            self.arm = run72.prepare(self.state, 'prep-warm-session', mode=profile.POSTRESTART_WARM_ONLY_MODE)
        self.executed = {**self.arm, 'runtime': copy.deepcopy(run72.POLICY), 'session_id': 'run-warm-session'}

    def test_package_raw_arm_mode_and_private_read_chain_fail_before_host(self):
        receipt = json.loads((self.state / 'arm-receipt.json').read_bytes())
        self.assertEqual(receipt['arm_sha256'], fixtures.digest((self.state / 'arm.json').read_bytes()))
        self.assertTrue((self.state / 'arm.json').read_bytes().endswith(b'\n'))
        self.assertEqual(self.arm['base_commit'], run72.WARM_ONLY_BASE)
        self.assertEqual(receipt['mode'], profile.POSTRESTART_WARM_ONLY_MODE)
        self.assertEqual(json.loads((self.state / 'GO.template.json').read_bytes())['mode'], receipt['mode'])
        run72.prior.verify_initial_package(self.state, self.arm)
        host = Mock()
        job = run72.PostrestartRun(self.state, self.executed, host, 'synthetic-offline-key')
        host.call.assert_not_called()
        self.assertEqual(stat.S_IMODE((self.state / 'private').stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE((self.state / name).stat().st_mode) == 0o600 for name in self.arm['frozen_inputs']))
        with self.assertRaisesRegex(ValueError, 'warm_only_initial_measurement_forbidden'):
            job.prepare_job('g', 'P-G4K')
        with self.assertRaisesRegex(ValueError, 'warm_only_initial_measurement_forbidden'):
            job.admission('g', measured=True, request_identity={'request_id': 'P-G4K'})
        host.call.assert_not_called()
        (self.state / 'private').chmod(0o755)
        with self.assertRaisesRegex(run72.client.HarnessError, '0700'):
            run72.PostrestartRun(self.state, self.executed, host, 'synthetic-offline-key')
        host.call.assert_not_called()

    def test_actual_sequence_dispatches_only_two_discarded_warmups_then_same_hold(self):
        host = Mock(); operations = []
        def host_call(method, **kwargs):
            operations.append((method, kwargs))
            if method == 'admit_concurrent': return {'manifests': self.arm['manifests']}
            if method == 'request_begin': return {'timeout_s': 7200}
            if method in ('begin', 'request_end', 'quiescent', 'budget'): return {}
            raise AssertionError(method)
        host.call.side_effect = host_call
        dispatched = []
        def transport(raw, timeout):
            body = json.loads(raw); dispatched.append((body, timeout))
            model = body['model']; tokens = 3546 if model == 'bench-glm-5.3' else 3251
            return iter([stream([event({'content': 'discarded offline warmup'}, 'length', model=model),
                {'model': model, 'choices': [], 'usage': {'prompt_tokens': tokens, 'completion_tokens': 32,
                    'prompt_tokens_details': {'cached_tokens': 0}},
                 'timings': {'prompt_n': tokens, 'predicted_n': 32, 'prompt_ms': 1000, 'predicted_ms': 1000}}])])
        job = run72.PostrestartRun(self.state, self.executed, host, 'synthetic-offline-key',
            transport_factory=Mock(return_value=transport))
        job.boundary = Mock(); job.ensure_current_proof = Mock(); job.collect = Mock()
        def loaded(manifest):
            cid = manifest['placement']; job.active[cid] = {'manifest': manifest, 'cancel_event': threading.Event()}
            job.warm(cid, manifest, {}); return cid
        job.loaded = Mock(side_effect=loaded)
        def counter(cid):
            return lambda raw: {'source': 'native_apply_template_tokenize', 'body_sha256': fixtures.digest(raw),
                'configured_context': 480000, 'input_tokens': 3546 if cid == 'G1' else 3251,
                'template_sha256': run72.TEMPLATES[cid], 'token_ids_sha256': 'b' * 64}
        job.counter = counter; job.hold = Mock(); job.measure = Mock(); job.prepare_job = Mock()
        with patch.object(run72, 'prefill_proof', return_value={'synthetic': True}), \
             patch.object(run72.cpu, 'warmup_gate', return_value={'status': 'PASS'}), \
             patch.object(run72.cpu_run, 'execute_pair') as pair:
            job.sequence()
        self.assertEqual(job.loaded.call_count, 2)
        self.assertEqual([body['max_tokens'] for body, _ in dispatched], [32, 32])
        self.assertEqual([timeout for _, timeout in dispatched], [7200, 7200])
        admissions = [args for op, args in operations if op == 'request_begin']
        self.assertEqual([args['measured'] for args in admissions], [False, False])
        self.assertEqual([args['request_identity']['request_id'] for args in admissions], ['P-G1-warmup', 'P-Q1-warmup'])
        job.measure.assert_not_called(); job.prepare_job.assert_not_called(); pair.assert_not_called()
        job.hold.assert_called_once_with('complete'); self.assertTrue(job.hold_ready)
        self.assertIs(job.host, host); self.assertEqual(job.progress['completed'], {})
        self.assertFalse((self.state / 'samples.jsonl').exists())


if __name__ == '__main__':
    unittest.main()
