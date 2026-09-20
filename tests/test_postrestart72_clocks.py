"""Focused offline admission/HTTP-clock/canonical-stopped-restore checks."""
import copy
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import client, concurrent_run, runner, worker_verify
from benchmark.campaign import CampaignBudget
from benchmark.cpu_budget_profiles import POSTRESTART_SCOPE
from benchmark.lifecycle import digest
from benchmark.owner import CampaignOwner, HostCallbacks
from benchmark.postrestart72_budget import PostrestartBudget
from tests.test_benchmark_lifecycle import snapshot
from tests.test_benchmark_owner import Fixture


class MemoryHost:
    log_root = '/data/logs/benchrun-p72-offline'

    def __init__(self):
        self.saved = {}

    def read_json(self, name, missing=False):
        return copy.deepcopy(self.saved.get(name))

    def write_json(self, name, value):
        self.saved[name] = copy.deepcopy(value)


class ClockTests(unittest.TestCase):
    def setUp(self):
        self.host, self.now = MemoryHost(), [1000.]
        self.budget = PostrestartBudget(self.host, clock=lambda: self.now[0])
        self.budget.start('maintenance')

    def test_preparation_warmup_and_count_excluded_then_first_measurement_starts_six_hours(self):
        self.now[0] += 7100
        self.assertEqual(self.budget.request_timeout(measured=False), 7200)
        self.assertEqual(self.budget.request_timeout(120, measured=False), 120)
        self.assertIsNone(self.budget.data['started_at'])
        self.assertEqual(self.budget.data['phase'], 'PREPARING')
        self.assertEqual(self.budget.request_timeout(measured=True), 7200)
        self.assertEqual(self.budget.data['started_at'], 8100)
        self.assertEqual(self.budget.data['deadline_epoch'], 8100 + 21600)
        self.assertEqual(self.budget.checkpoint(), 21600)

    def test_last_second_admission_grants_full_request_and_later_expiry_only_refuses_new(self):
        self.budget.request_timeout(measured=True)
        self.now[0] += 21599
        admitted_timeout = self.budget.request_timeout(measured=True)
        self.assertEqual(admitted_timeout, 7200)
        self.now[0] += 100
        self.assertEqual(self.budget.checkpoint(), 0)
        with self.assertRaisesRegex(ValueError, 'STOP_BUDGET'):
            self.budget.request_timeout(measured=True)
        self.assertEqual(admitted_timeout, 7200)
        self.budget.begin_restoration()
        self.now[0] += 8000
        self.budget.finish_restoration(True)
        self.assertEqual(self.budget.data['phase'], 'RESTORED')

    def test_preparation_bound_and_restoration_before_first_measurement(self):
        self.now[0] += 7200
        with self.assertRaisesRegex(ValueError, 'STOP_BUDGET'):
            self.budget.request_timeout(measured=True)
        self.budget.begin_restoration()
        self.now[0] += 50000
        self.budget.finish_restoration(True)
        self.assertIsNone(self.budget.data['started_at'])
        self.assertEqual(self.budget.data['phase'], 'RESTORED')

    def test_durable_resume_preserves_clock_and_refuses_backward_time_or_tamper(self):
        self.budget.request_timeout(measured=True)
        self.now[0] += 21590
        resumed = PostrestartBudget(self.host, clock=lambda: self.now[0])
        self.assertEqual(resumed.request_timeout(measured=True), 7200)
        self.assertEqual(resumed.data['started_at'], 1000)
        self.now[0] -= 1
        with self.assertRaisesRegex(ValueError, 'wall_clock_regressed'):
            resumed.checkpoint()
        self.host.saved['budget.json']['deadline_epoch'] += 1
        with self.assertRaisesRegex(ValueError, 'invalid_postrestart_measurement_clock'):
            PostrestartBudget(self.host)

    def test_historical_request_budget_still_clamps(self):
        with tempfile.TemporaryDirectory() as directory:
            old = CampaignBudget(Path(directory) / 'budget.json', clock=lambda: self.now[0],
                                 before_write=lambda: None, after_write=lambda: None)
            old.start('maintenance')
            self.now[0] += 21599
            self.assertEqual(old.request_timeout(), 1)


class RequestCompositionTests(unittest.TestCase):
    def test_timed_flag_native_counter_and_transport_do_not_inherit_campaign_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            runner.save(state / 'progress.json', {'phase': 'OFFLINE', 'completed': {}, 'inflight': {}, 'errors': []})
            host, transport = Mock(), Mock()
            host.call.return_value = {'timeout_s': 7200}
            armed = {'scope': POSTRESTART_SCOPE, 'runtime': {'deadline_epoch': 1},
                     'session_id': 'offline', 'source_commit': 'a' * 40}
            run = concurrent_run.ConcurrentRun(state, armed, host, 'synthetic-offline', transport_factory=transport)
            event = threading.Event()
            run.active['g'] = {'manifest': {'transport': {'port': 31002}}, 'cancel_event': event}
            with patch.object(client, '_capture_request', return_value={'summary': {}}) as capture:
                for measured in (False, True):
                    run.request('g', b'{"max_tokens":256,"stream":true}', 'offline', timed=measured)
                    self.assertEqual(host.call.call_args_list[-2].kwargs['measured'], measured)
                    self.assertEqual(capture.call_args.kwargs['timeout'], 7200)
                    self.assertIsNone(transport.call_args.kwargs['deadline_epoch'])
                    self.assertIs(transport.call_args.kwargs['cancel_event'], event)
            # The inherited native counter calls admission(maximum=120) without
            # marking a measurement; it must not start the measurement clock.
            run.admission('g', 120)
            self.assertEqual(host.call.call_args.kwargs, {'id': 'g', 'timeout_s': 120, 'measured': False})

    def test_transport_own_timer_starts_at_dispatch_and_survives_admission_expiry(self):
        now, received = [100.], []
        sock = Mock()
        response = SimpleNamespace(status=200, getheader=lambda *a: 'text/event-stream', close=lambda: None)
        chunks = iter([b'data: [DONE]\n\n', b''])
        def read(size):
            now[0] += 1000
            return next(chunks)
        response.read1 = read
        conn = SimpleNamespace(sock=sock, request=lambda *a, **k: received.append(now[0]),
                               getresponse=lambda: response, close=lambda: None)
        with patch('http.client.HTTPConnection', return_value=conn) as connection, \
             patch('threading.Timer') as timer, patch.object(client.time, 'time', return_value=999999):
            transport = client.http_transport('http://127.0.0.1:31002', 'synthetic', clock=lambda: now[0], deadline_epoch=None)
            self.assertEqual(list(transport(b'{}', 7200)), [b'data: [DONE]\n\n'])
        self.assertEqual(received, [100.])
        self.assertEqual(connection.call_args.kwargs['timeout'], 7200)
        self.assertEqual(timer.call_args.args[0], 7200)
        self.assertEqual(sock.settimeout.call_args_list[0].args[0], 7200)
        self.assertEqual(sock.settimeout.call_args_list[1].args[0], 6200)


class StoppedRestoreTests(unittest.TestCase):
    def test_original_deactivated_stopped_manual_restores_canonically_without_model_start(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory).resolve(), snapshot(None, False))
            clockhost, now = MemoryHost(), [1000.]
            budget = PostrestartBudget(clockhost, clock=lambda: now[0])
            callbacks = HostCallbacks(**{name: getattr(fixture, name) for name in HostCallbacks.__dataclass_fields__})
            owner = CampaignOwner('benchrun-offline', fixture, callbacks, budget,
                reviewed_manifest_hashes=[digest(fixture.manifest)], lease_factory=fixture.lease_factory,
                synthetic_offline=True, scope=POSTRESTART_SCOPE)
            fixture.owner = owner
            try:
                owner.begin()
                self.assertEqual(budget.data['phase'], 'PREPARING')
                result = owner.restore()
                self.assertTrue(result['restored'])
                self.assertEqual(fixture.state['manager']['desired'], 'stopped')
                self.assertEqual(fixture.state['manager']['boot_policy'], 'manual')
                self.assertIsNone(fixture.state['manager']['selected'])
                self.assertFalse(any(event[:2] == ('manager', 'start') for event in fixture.events))
                self.assertIn(('manager', 'deactivate', {}), fixture.events)
                self.assertEqual(budget.data['phase'], 'RESTORED')
                self.assertEqual(fixture.writes[-1]['validation_scope'], POSTRESTART_SCOPE)
            finally:
                if owner.lease_context:
                    owner.lease_context.__exit__(None, None, None)

    def test_stopped_active_control_verification_uses_only_read_only_status(self):
        state = snapshot(None, False)
        calls = []
        def call(port, path, key, payload=None):
            calls.append((port, path, payload))
            return {**state['manager'], 'current_operation': None}
        receipt = worker_verify.verify({'original': state, 'nonce': 'a' * 32}, 'synthetic-i', 'synthetic-c', call=call)
        self.assertEqual(calls, [(30000, '/control/v1/status', None)])
        self.assertEqual(receipt['checks']['worker_lan_inference_authenticated'], 'NOT_APPLICABLE_STOPPED_INTENT')

class FollowupClockTests(unittest.TestCase):
    def test_one_fresh_retained_segment_preserves_expired_original_and_full_dispatch_budget(self):
        host, now = MemoryHost(), [1000.]
        budget = PostrestartBudget(host, clock=lambda: now[0])
        budget.start('maintenance'); budget.request_timeout(measured=True)
        now[0] += 25000
        original = budget.data
        identity = {'session_id': 'fresh-followup', 'source_commit': 'a' * 40, 'preliminary_result_sha256': 'b' * 64}
        budget.begin_followup(identity)
        self.assertEqual(budget.data['phase'], 'PREPARING')
        self.assertEqual(budget.data['prior_segment']['started_at'], original['started_at'])
        self.assertEqual(budget.data['prior_segment']['deadline_epoch'], original['deadline_epoch'])
        self.assertIsNone(budget.data['started_at'])
        now[0] += 500
        budget.request_timeout(measured=True)
        self.assertEqual(budget.data['started_at'], now[0])
        now[0] += 21599
        self.assertEqual(budget.request_timeout(measured=True), 7200)
        resumed = PostrestartBudget(host, clock=lambda: now[0])
        self.assertEqual(resumed.data, budget.data)
        with self.assertRaisesRegex(ValueError, 'postrestart_followup_budget_forbidden'):
            resumed.begin_followup(identity)


class HoldTests(unittest.TestCase):
    def owned_pair(self, root):
        fixture = Fixture(Path(root).resolve(), snapshot(None, False))
        budget_host, now = MemoryHost(), [1000.]
        budget = PostrestartBudget(budget_host, clock=lambda: now[0])
        original_create, original_gate = fixture.create, fixture.gate
        def create(manifest):
            fixture.owner.mark_create_dispatched()
            return original_create(manifest)
        def gate(stage, *args):
            if stage == 'warm_hold' and fixture.requests_active:
                raise ValueError('healthy_request_still_registered')
            return original_gate(stage, *args)
        fixture.create, fixture.gate = create, gate
        second = {**fixture.manifest, 'container_name': 'benchrun-offline-q1-4096'}
        callbacks = HostCallbacks(**{name: getattr(fixture, name) for name in HostCallbacks.__dataclass_fields__})
        owner = CampaignOwner('benchrun-offline', fixture, callbacks, budget,
            reviewed_manifest_hashes=[digest(fixture.manifest), digest(second)], lease_factory=fixture.lease_factory,
            synthetic_offline=True, scope=POSTRESTART_SCOPE)
        fixture.owner = owner
        owner.begin(); owner.launch(fixture.manifest); owner.launch(second)
        budget.request_timeout(measured=True)
        return fixture, owner, budget, now

    def test_idle_owned_pair_hold_keeps_real_lease_and_explicit_release_restores_stopped(self):
        from benchmark.host import LinuxHost
        with tempfile.TemporaryDirectory() as directory:
            fixture, owner, budget, now = self.owned_pair(directory)
            owner.warm_hold('complete')
            self.assertEqual(owner.phase, 'WARM_HOLD')
            owner.lease.validate()
            self.assertEqual(fixture.writes[-1]['phase'], 'WARM_HOLD')
            self.assertEqual(len(fixture.containers), 2)
            host = LinuxHost.__new__(LinuxHost); host.scope, host.owner = POSTRESTART_SCOPE, owner
            with self.assertRaisesRegex(ValueError, 'owner_not_active'):
                host.dispatch({'op': 'request_begin', 'id': '1' * 64})
            now[0] += 99999
            self.assertEqual(budget.checkpoint(), 0)
            self.assertEqual(owner.phase, 'WARM_HOLD')
            with self.assertRaisesRegex(ValueError, 'postrestart_hold_resume_forbidden'):
                owner.resume_measurements({})
            restored = owner.restore()
            self.assertTrue(restored['restored'])
            self.assertEqual(fixture.containers, {})
            self.assertFalse(any(event[:2] == ('manager', 'start') for event in fixture.events))

    def test_active_request_prevents_hold_then_preliminary_one_time_followup(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture, owner, budget, now = self.owned_pair(directory)
            try:
                fixture.requests_active = True
                with self.assertRaisesRegex(ValueError, 'healthy_request_still_registered'):
                    owner.warm_hold('preliminary_review')
                self.assertEqual(owner.phase, 'ACTIVE')
                fixture.requests_active = False
                owner.warm_hold('preliminary_review')
                now[0] += 25000
                identity = {'session_id': 'fresh-followup', 'source_commit': 'a' * 40, 'preliminary_result_sha256': 'b' * 64}
                owner.resume_measurements(identity)
                self.assertEqual(owner.phase, 'ACTIVE')
                self.assertTrue(owner.warm_hold_resumed)
                self.assertEqual(budget.data['phase'], 'PREPARING')
                owner.warm_hold('preliminary_review')
                with self.assertRaisesRegex(ValueError, 'postrestart_hold_resume_forbidden'):
                    owner.resume_measurements(identity)
                owner.restore()
            finally:
                if owner.lease_context:
                    owner.lease_context.__exit__(None, None, None)

    def test_hold_proof_resource_failure_never_enters_hold(self):
        from benchmark.host import LinuxHost
        host = LinuxHost.__new__(LinuxHost)
        host.owner = Mock()
        host.postrestart_hold_proof = Mock(side_effect=ValueError('postrestart_unsafe_hold_forbidden'))
        with self.assertRaisesRegex(ValueError, 'postrestart_unsafe_hold_forbidden'):
            host.warm_hold('complete')
        host.owner.warm_hold.assert_not_called()

    def test_eof_only_new_idle_hold_attempts_canonical_restore(self):
        import io
        from benchmark.host import serve
        for scope, phase, requests, expected in ((POSTRESTART_SCOPE, 'WARM_HOLD', {}, 1),
                ('concurrent-480k-cpu', 'WARM_HOLD', {}, 0), (POSTRESTART_SCOPE, 'ACTIVE', {}, 0),
                (POSTRESTART_SCOPE, 'WARM_HOLD', {'g': {}}, 0)):
            owner = SimpleNamespace(phase=phase, restore=Mock())
            host = SimpleNamespace(scope=scope, owner=owner, requests=requests)
            serve(host, io.StringIO(), io.StringIO())
            self.assertEqual(owner.restore.call_count, expected)

    def test_lost_hold_reply_restores_but_never_claims_remote_verification(self):
        import io
        from benchmark.host import serve
        owner = SimpleNamespace(phase='WARM_HOLD', restore=Mock(return_value={'restored': False,
                                'worker_lan_verification': 'PENDING'}))
        host = SimpleNamespace(scope=POSTRESTART_SCOPE, owner=owner, requests={},
                               dispatch=Mock(return_value={'phase': 'WARM_HOLD'}))
        sink = Mock(); sink.write.side_effect = BrokenPipeError()
        with self.assertRaises(BrokenPipeError):
            serve(host, io.StringIO('{"op":"status"}\n'), sink)
        owner.restore.assert_called_once_with()
        sink.flush.assert_not_called()

    def test_fresh_host_cannot_resume_or_adopt_hold(self):
        from benchmark.host import LinuxHost
        host = LinuxHost.__new__(LinuxHost)
        host.scope, host.owner = POSTRESTART_SCOPE, SimpleNamespace(phase='NEW')
        with self.assertRaisesRegex(ValueError, 'postrestart_hold_resume_forbidden'):
            host.resume_measurements('fresh', 'a' * 40, 'b' * 64)

class HostIntegrationTests(unittest.TestCase):
    def test_actual_allocation_rejects_conflicting_flat_nested_Q_context_before_acceptance(self):
        from benchmark import cpu_budget_profiles as profile
        from benchmark.host import LinuxHost
        from tests.test_cpu_budget_host import CPUHost
        host = CPUHost().bare(); host.scope = POSTRESTART_SCOPE
        cid = 'synthetic-postrestart-q'
        host.load_manifests[cid] = profile.postrestart_manifest('Q1')
        host.identity = Mock(return_value=({}, Path('/synthetic-no-io'), []))
        host.write_bytes, host.write_json = Mock(), Mock()
        conflict = {'context_length': 700160, 'tp_size': 1,
            'server_args': {'context_length': 480000, 'tp_size': 1},
            'max_total_num_tokens': 480000, 'max_req_input_len': 479994}
        with patch('benchmark.host.command', return_value=SimpleNamespace(stdout=b'', stderr=b'')), \
             patch('benchmark.host.http_json', return_value=conflict), \
             patch('benchmark.host.allocation_gate') as gate:
            with self.assertRaisesRegex(ValueError, 'cpu_native_context_mismatch'):
                LinuxHost.allocation(host, cid)
        gate.assert_not_called()
        self.assertTrue(any('native-numeric-diagnostic' in call.args[0] for call in host.write_json.call_args_list))

    def held_host(self):
        from benchmark import cpu_budget_profiles as profile
        from benchmark.host import LinuxHost
        host = LinuxHost.__new__(LinuxHost)
        host.scope, host.campaign = POSTRESTART_SCOPE, profile.POSTRESTART_CAMPAIGN
        host.owner = SimpleNamespace(phase='WARM_HOLD', _gate=Mock(), lease=SimpleNamespace(validate=Mock()),
                                     pending_create=None, resources=[{'resource': {'id': 'g'}, 'state': 'RUNNING'},
                                                                    {'resource': {'id': 'q'}, 'state': 'RUNNING'}])
        host.load_manifests = {'g': profile.postrestart_manifest('G1'), 'q': profile.postrestart_manifest('Q1')}
        host.allocation_proofs = {'g': {}, 'q': {}}
        host.concurrent_resource_violations = {}
        host.identity = Mock(return_value=({}, Path('/synthetic'), [123]))
        host.concurrent_limits, host.guards, host.credentials = Mock(), Mock(), Mock()
        host.requests = {}
        host.budget = SimpleNamespace(data={'phase': 'MEASURING', 'started_at': 1000, 'deadline_epoch': 22600})
        host.allocation = Mock(side_effect=AssertionError('no allocation/log rewriting on heartbeat'))
        host.telemetry = Mock(side_effect=AssertionError('no accumulating timed arrays on heartbeat'))
        return host

    def test_actual_RPC_hold_checkpoint_is_bounded_cheap_and_missing_proof_stays_review(self):
        from benchmark.host import _COMMAND_DEADLINE
        for pressure, expected in (('PASS', 'HELD'), ('UNAVAILABLE', 'REVIEW_REQUIRED')):
            host = self.held_host()
            host.concurrent_pressure = Mock(return_value={'status': pressure, 'unavailable_reasons': [] if pressure == 'PASS' else ['synthetic_missing']})
            sample = {'cgroups': {'g': {'events': {'oom': 0}, 'swap_bytes': 0}, 'q': {'events': {'oom': 0}, 'swap_bytes': 0}}}
            def native(port, route, timeout_s):
                self.assertIsNotNone(_COMMAND_DEADLINE.get())
                if route == '/v1/models':
                    return {'data': [{'id': 'bench-glm-5.3' if port == 31002 else 'bench-qwen3.8-27b'}]}
                return {'context_length': 480000, 'tp_size': 1, 'max_total_num_tokens': 480000, 'max_req_input_len': 479994}
            with patch('benchmark.host.collect_sample', return_value=sample), patch('benchmark.host.http_json', side_effect=native):
                result = host.dispatch({'op': 'hold_checkpoint'})
            self.assertEqual(result['phase'], 'WARM_HOLD'); self.assertEqual(result['status'], expected)
            self.assertEqual(host.owner.phase, 'WARM_HOLD')
            host.owner._gate.assert_called_once_with('warm_hold')
            host.allocation.assert_not_called(); host.telemetry.assert_not_called()
            self.assertIsNone(_COMMAND_DEADLINE.get())

    def test_actual_hold_checkpoint_resource_failure_is_not_proof_unavailable(self):
        host = self.held_host()
        host.concurrent_pressure = Mock(return_value={'status': 'STOP_RESOURCE_GATE', 'unavailable_reasons': []})
        sample = {'cgroups': {'g': {'events': {'oom': 0}, 'swap_bytes': 0}, 'q': {'events': {'oom': 0}, 'swap_bytes': 0}}}
        with patch('benchmark.host.collect_sample', return_value=sample), \
             patch('benchmark.host.http_json', side_effect=TimeoutError()):
            with self.assertRaisesRegex(ValueError, 'postrestart_unsafe_hold_forbidden'):
                host.dispatch({'op': 'hold_checkpoint'})
        self.assertEqual(host.owner.phase, 'WARM_HOLD')  # owner cleanup is explicit supervisor responsibility

    def test_body_bound_followup_reuses_owner_once_and_host_admission_rejects_other_body(self):
        from benchmark import cpu_budget_profiles as profile, fixtures
        from benchmark.host import LinuxHost
        with tempfile.TemporaryDirectory() as directory:
            fixture, owner, budget, now = HoldTests().owned_pair(directory)
            try:
                owner.warm_hold('complete')
                host = LinuxHost.__new__(LinuxHost)
                host.scope, host.campaign, host.owner = POSTRESTART_SCOPE, profile.POSTRESTART_CAMPAIGN, owner
                host.run_source_commit, host.run_session_id = 'a' * 40, 'original-run'
                host.budget = budget
                saved = {'phase': 'WARM_HOLD', 'reason': 'complete', 'pair': 'synthetic-exact-pair'}
                host.read_json = Mock(return_value=saved); host.write_json = Mock()
                host.postrestart_hold_proof = Mock(return_value={'status': 'HELD'})
                manifest = profile.postrestart_manifest('G1')
                go = {'decision': 'GO', 'source_commit': host.run_source_commit, 'owner_run_session_id': host.run_session_id,
                    'followup_session_id': 'fresh-extra', 'campaign': host.campaign,
                    'warm_hold_receipt_sha256': fixtures.digest(fixtures.canonical(saved) + b'\n'),
                    'placement': 'G1', 'preset': 'P-G4K', 'manifest_sha256': digest(manifest),
                    'request_sha256': 'b' * 64, 'fixture_sha256': 'c' * 64, 'request_id': 'extra-G4K',
                    'policy': {'measurement_admission_seconds': 21600, 'request_timeout_seconds': 7200,
                               'request_clock_starts': 'HTTP_DISPATCH', 'admission_deadline_refuses_new_only': True}}
                result = host.dispatch({'op': 'admit_followup', 'go': go})
                self.assertEqual(result['phase'], 'ACTIVE'); self.assertTrue(owner.additional_followup_used)
                self.assertEqual(budget.data['phase'], 'PREPARING')
                self.assertIsNotNone(owner.lease); owner.lease.validate()
                cid = '1' * 64
                host.load_manifests, host.allocation_proofs, host.requests = {cid: manifest}, {cid: {}}, {}
                host.identity = Mock(return_value=({}, Path('/synthetic'), [])); host.concurrent_limits = Mock()
                host.telemetry = Mock(return_value={'concurrent_resource_gate': {'status': 'PASS'}})
                identity = {k: go[k] for k in ('request_id', 'request_sha256', 'manifest_sha256')}
                with patch('benchmark.cpu_budget_host.resident_obligations', return_value={}):
                    bad = {**identity, 'request_sha256': 'd' * 64}
                    with self.assertRaisesRegex(ValueError, 'postrestart_only_bound_additional_request'):
                        host.dispatch({'op': 'request_begin', 'id': cid, 'measured': True, 'request_identity': bad})
                    admitted = host.dispatch({'op': 'request_begin', 'id': cid, 'measured': True, 'request_identity': identity})
                    self.assertEqual(admitted['timeout_s'], 7200)
                    host.dispatch({'op': 'request_end', 'id': cid})
                    with self.assertRaisesRegex(ValueError, 'postrestart_only_bound_additional_request'):
                        host.dispatch({'op': 'request_begin', 'id': cid, 'measured': True, 'request_identity': identity})
                owner.warm_hold('complete')
                with self.assertRaisesRegex(ValueError, 'postrestart_additional_followup_forbidden'):
                    host.dispatch({'op': 'admit_followup', 'go': {**go, 'followup_session_id': 'another-extra'}})
                owner.restore()
            finally:
                if owner.lease_context:
                    owner.lease_context.__exit__(None, None, None)

class HoldUnavailableEntryTests(unittest.TestCase):
    def test_real_readiness_stop_for_unavailable_resource_proof_enters_review_hold_only(self):
        from benchmark import host as module
        host = HostIntegrationTests().held_host()
        host.owner.phase = 'ACTIVE'
        host.owner.original = {'manager': {'selected': None, 'desired': 'stopped', 'boot_policy': 'manual'}}
        host.owner.warm_hold = Mock(side_effect=lambda reason: setattr(host.owner, 'phase', 'WARM_HOLD'))
        host.run_session_id, host.config = 'synthetic-run', {'lease': '/run/llmctl/lifecycle.lock'}
        host.assert_idle, host.auth_probe, host.write_json = Mock(), Mock(), Mock()
        host.readiness_failure = Mock(return_value=None)
        host.concurrent_limits = Mock(return_value=({'no_swap': True}, {'cpus': 'reviewed'}))
        host.hold_checkpoint = Mock(return_value={'status': 'REVIEW_REQUIRED', 'unavailable_reasons': ['concurrent_gpu_free_unavailable']})
        # This is allocation()'s actual shape and _readiness()'s real propagation:
        # admission still fails; the unavailable-only hold disposition is scoped.
        unavailable = {'allocation': {'status': 'STOP_ALLOCATION_PROOF',
            'reasons': ['concurrent_gpu_free_unavailable']}, 'parsed': {}, 'observed': {}, 'server_facts': {},
            'raw_log_path': '/data/logs/synthetic-allocation.log', 'resource_proof_unavailable_only': True}
        host.allocation = Mock(return_value=unavailable)
        original = module.LinuxHost._readiness.__get__(host)
        def readiness(cid):
            if cid == 'g':
                return original(cid)
            return {'ready': True, 'failed': False, 'allocation': {'status': 'ALLOCATION_PROOF_ACCEPTED'}, 'observed': {}}
        host._readiness = readiness
        with patch('benchmark.host.http_json', return_value={'data': [{'id': 'bench-glm-5.3'}]}):
            receipt = host.warm_hold('quality_review')
        self.assertEqual(receipt['status'], 'REVIEW_REQUIRED')
        self.assertEqual(receipt['phase'], 'WARM_HOLD')
        self.assertEqual(host.owner.phase, 'WARM_HOLD')
        self.assertIn('G1_fresh_allocation_proof_unavailable', receipt['unavailable_reasons'])
        host.readiness_failure.assert_called_once_with('g')
        self.assertEqual(host.allocation_proofs, {'g': {}, 'q': {}})
        self.assertEqual(host.requests, {})
        with self.assertRaisesRegex(ValueError, 'owner_not_active'):
            host.dispatch({'op': 'request_begin', 'id': 'g'})

    def test_resource_or_terminal_failure_never_uses_unavailable_entry_fallback(self):
        for marker, state, terminal in ((False, 'STOP_ALLOCATION_PROOF', None),
                (True, 'STOP_OOM', None), (True, 'STOP_ALLOCATION_PROOF', {'failed': True, 'state': 'STOP_BACKEND_EXITED'})):
            host = HostIntegrationTests().held_host()
            host.owner.phase = 'ACTIVE'; host.assert_idle = Mock()
            host._readiness = Mock(return_value={'ready': False, 'failed': True, 'state': state,
                                                'resource_proof_unavailable_only': marker})
            host.readiness_failure = Mock(return_value=terminal)
            host.hold_checkpoint = Mock()
            with self.assertRaisesRegex(ValueError, 'postrestart_hold_native_ready_failed'):
                host.postrestart_hold_proof()
            host.hold_checkpoint.assert_not_called()
            self.assertEqual(host.owner.phase, 'ACTIVE')
