"""Saved REAL72 loading accounting gap; real gates with offline I/O only."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import cpu_budget_profiles as profiles, postrestart72_run, runner
from benchmark.host import LinuxHost

FIXTURE = Path(__file__).parent / 'fixtures/postrestart72-loading-gap.json'
GIB = 1024**3


class LoadingAccountingGapTests(unittest.TestCase):
    def setup_case(self, scope=profiles.POSTRESTART_SCOPE):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        state = Path(directory.name)
        runner.save(state / 'progress.json', {'phase': 'OFFLINE', 'completed': {}, 'inflight': {}, 'errors': []})
        saved = json.loads(FIXTURE.read_bytes())
        gap = saved['sample']
        host = LinuxHost.__new__(LinuxHost)
        host.scope = profiles.POSTRESTART_SCOPE
        host.config = {'gpu_uuids': ['GPU-offline-0', 'GPU-offline-1']}
        host.load_manifests = {cid: profiles.postrestart_manifest(placement)
                               for cid, placement in (('g', 'G1'), ('q', 'Q1'))}
        for index, manifest in enumerate(host.load_manifests.values()):
            manifest['gpu_uuids'] = ['GPU-offline-' + str(index)]
        host.allocation_proofs, host.requests = {'g': {}}, {}
        host.owner = SimpleNamespace(phase='ACTIVE', warm_hold_resumed=False)
        host.followup_request = None
        host.budget = Mock(); host.budget.request_timeout.return_value = 7200
        host.concurrent_limits = Mock(return_value=({}, {}))
        host.assert_idle, host.write_json, host.write_bytes = Mock(), Mock(), Mock()
        host.manager, host.binding, host.auth_probe = Mock(), Mock(), Mock()
        host.log_root = '/offline-not-read'
        host.readiness_failure = Mock(return_value=None)
        host.cuda_mapping = Mock(return_value=['GPU-offline-1'])
        qmanifest = host.load_manifests['q']
        model_path = next(arg.split('source=', 1)[1].split(',', 1)[0]
                          for arg in qmanifest['create_argv'] if 'target=/models' in arg)
        container = {'Config': {'Image': 'offline', 'Cmd': []},
                     'HostConfig': {'DeviceRequests': [{'DeviceIDs': ['GPU-offline-1']}]},
                     'Mounts': [{'Source': model_path, 'Destination': '/models', 'RW': False}]}
        host.identity = Mock(return_value=(container, Path('/offline-not-read'), []))
        good = copy.deepcopy(gap)
        good['errors'] = []
        good['processes']['q'].update(rss_bytes=15000000000, swap_bytes=0)
        rows = {'current': gap, 'gap': gap, 'good': good, 'recover': True, 'calls': []}

        def telemetry(cid):
            row = copy.deepcopy(rows['current'])
            row['concurrent_resource_gate'] = host.concurrent_pressure(row)
            row['required_host_demand'] = copy.deepcopy(row['concurrent_resource_gate']['charges'][cid])
            row['required_host_demand']['sample_phase'] = (
                'pre_readiness_load' if cid not in host.allocation_proofs else 'post_readiness')
            return row
        host.telemetry = telemetry

        def native(port, route, **kwargs):
            if route == '/v1/models': return {'data': [{'id': 'bench-qwen3.8-27b'}]}
            return {'context_length': 480000, 'tp_size': 1,
                    'max_total_num_tokens': 480000, 'max_req_input_len': 479994}

        def call(op, **args):
            rows['calls'].append(op)
            if op == 'budget': return {'remaining_s': 100}
            if op == 'load': return {'id': 'q'}
            if op == 'telemetry': return host.telemetry(args['id'])
            if op == 'readiness':
                if rows['recover']: rows['current'] = rows['good']
                # Actual allocation pressure and readiness propagation; only native
                # I/O and unrelated parsers/topology are synthetic.
                with patch('benchmark.host.command', return_value=SimpleNamespace(stdout=b'', stderr=b'')), \
                     patch('benchmark.host.http_json', side_effect=native), \
                     patch('benchmark.host.parse_qwen_log', return_value={'ranks': {'0': {'k_gb_log_label': 1, 'v_gb_log_label': 1}}}), \
                     patch('benchmark.host.allocation_gate', return_value={'status': 'ALLOCATION_PROOF_ACCEPTED', 'reasons': []}), \
                     patch('benchmark.cpu_budget_host.postrestart_cpu_anchor', return_value=None), \
                     patch('benchmark.cpu_budget_host.coherent_postrestart_cpu_proof', return_value={}), \
                     patch.object(Path, 'read_bytes', return_value=b'{"chat_template":"offline"}'):
                    return host._readiness(args['id'])
            if op == 'quiescent': return {'telemetry': host.telemetry(args['id'])}
            with patch('benchmark.cpu_budget_host.resident_obligations', return_value={}):
                return host.dispatch({'op': op, **args})

        remote = Mock(); remote.call.side_effect = call
        job = runner.Campaign(state, {'scope': scope}, remote, 'synthetic-nonsecret', sleep=Mock())
        for cid, manifest in host.load_manifests.items():
            job.active[cid] = {'manifest': manifest, 'phase': 'ready' if cid == 'g' else 'loading',
                'baseline': copy.deepcopy(gap['cgroups'][cid]), 'cancel_event': threading.Event()}
        return job, host, rows, saved

    def test_saved_fixture_keeps_exact_gap_and_cross_charge_evidence(self):
        job, host, rows, saved = self.setup_case()
        self.assertEqual(saved['_provenance']['source_line_sha256'],
                         '0e877aba410d3711b3bd2f58cfe7ecbeeff4959aab6c2e0fe8cfe9ec15230cbb')
        gap = rows['gap']; gate = gap['concurrent_resource_gate']
        self.assertEqual(gap['errors'], ['read_FileNotFoundError'] * 5)
        self.assertIsNone(gate['charges']['q']['required_bytes'])
        self.assertIsNone(gap['processes']['q']['rss_bytes'])
        self.assertEqual(gate['charges']['q']['component_bracket_bytes'], 5297053696)
        self.assertEqual(gate['charges']['q']['sampled_peak_required_bytes'], 15050743808)
        # Use the saved gate verbatim here. Subsequent tests recompute real pressure.
        job.host.call.side_effect = lambda op, **args: copy.deepcopy(gap)
        job.collect()
        self.assertEqual(job.safety, {})
        emitted = [json.loads(line) for line in (job.state / 'results.jsonl').read_text().splitlines()]
        self.assertEqual([row['container'] for row in emitted], ['g', 'q'])
        for row in emitted:
            self.assertEqual(row['sample']['concurrent_resource_gate'], gate)
            self.assertEqual(row['sample']['errors'], gap['errors'])
        self.assertFalse(any(v['cancel_event'].is_set() for v in job.active.values()))

    def test_transient_gap_then_real_readiness_and_admission_reaches_warmup_boundary(self):
        job, host, rows, _ = self.setup_case()
        def warm(cid, *_):
            self.assertEqual(job.admission(cid), 7200)
            host.dispatch({'op': 'request_end', 'id': cid})
        job.warm = Mock(side_effect=warm)
        self.assertEqual(job.loaded(host.load_manifests['q']), 'q')
        job.warm.assert_called_once()
        self.assertEqual(job.samples['g'][0]['concurrent_resource_gate']['status'], 'UNAVAILABLE')
        self.assertIn('q', host.allocation_proofs)
        self.assertEqual(job.active['q']['phase'], 'ready')
        job.interrupted = threading.Event(); job.root_paused = Mock(return_value=False)
        job.in_hold, job.hold_ready = False, False
        job.require_no_faults = lambda: postrestart72_run.PostrestartRun.require_no_faults(job)
        job.ensure_current_proof = lambda: postrestart72_run.PostrestartRun.ensure_current_proof(job)
        postrestart72_run.PostrestartRun.boundary(job)
        self.assertEqual(job.safety, {})
        self.assertEqual(job.samples['q'][-1]['concurrent_resource_gate']['status'], 'PASS')
        self.assertEqual(host.requests, {})
        self.assertEqual(rows['calls'].count('request_begin'), 1)

    def test_persistent_gap_denies_actual_allocation_readiness_and_fresh_admission(self):
        job, host, rows, _ = self.setup_case(); rows['recover'] = False
        job.warm = Mock()
        with self.assertRaisesRegex(RuntimeError, 'STOP_ALLOCATION_FAILURE'):
            job.loaded(host.load_manifests['q'])
        job.warm.assert_not_called()
        self.assertNotIn('q', host.allocation_proofs)
        self.assertEqual(job.safety, {})  # unavailable stays recorded, not sticky
        with self.assertRaisesRegex(ValueError, 'concurrent_current_allocation_required'):
            job.admission('q')
        # G already has native allocation; healthy numeric quiescence alone still
        # cannot admit it while the current pair accounting gate is unavailable.
        self.assertGreater(rows['gap']['host']['available_bytes'], 16 * GIB)
        refusal = job.host.call('request_begin', id='g', timeout_s=7200)
        self.assertIs(refusal['proof_pending'], True)
        self.assertIs(refusal['admitted'], False)
        self.assertEqual(host.requests, {})

    def test_all_nonnumeric_gaps_are_current_but_explicit_faults_remain_sticky(self):
        for variant in ('ready', 'unknown_peer', 'allocation', 'different_error', 'extra_error',
                        'no_errors', 'components', 'known_rss', 'known_required', 'peer_rss',
                        'vmstat', 'latched', 'reason', 'other_reason'):
            with self.subTest(variant=variant):
                job, host, rows, _ = self.setup_case()
                gap = rows['gap']; charge = gap['concurrent_resource_gate']['charges']['q']
                if variant == 'ready': job.active['q']['phase'] = 'ready'
                if variant == 'unknown_peer': del job.active['q']
                if variant == 'allocation': charge['allocation_proof_available'] = True
                if variant == 'different_error': gap['errors'] = ['read_PermissionError']
                if variant == 'extra_error': gap['errors'].append('gpu_TimeoutExpired')
                if variant == 'no_errors': gap['errors'] = []
                if variant == 'components': gap['cgroups']['q']['kernel_bytes'] = None
                if variant == 'known_rss': gap['processes']['q']['rss_bytes'] = 15000000000
                if variant == 'known_required': charge['required_bytes'] = 15000000000
                if variant == 'peer_rss': gap['processes']['g']['rss_bytes'] = None
                if variant == 'vmstat': gap['vmstat']['pswpout'] = None
                if variant == 'latched': gap['concurrent_resource_gate']['latched_violations'] = {'q': {}}
                if variant == 'reason': gap['concurrent_resource_gate']['reasons'] = ['numeric_failure']
                if variant == 'other_reason': gap['concurrent_resource_gate']['unavailable_reasons'].append('other_missing')
                job.host.call.side_effect = lambda op, **args: copy.deepcopy(gap)
                job.collect()
                if variant in ('latched', 'reason'):
                    self.assertTrue(job.safety)
                    with self.assertRaisesRegex(RuntimeError, 'STOP_RESOURCE_GATE'):
                        job.admission('g')
                else:
                    self.assertEqual(job.safety, {})
                    self.assertTrue(job.proof_pending)
                    self.assertFalse(any(v['cancel_event'].is_set() for v in job.active.values()))

    def test_unavailable_ready_peer_charge_also_requires_fresh_proof(self):
        job, host, rows, _ = self.setup_case()
        rows['gap']['processes']['g']['rss_bytes'] = None
        job.collect()
        self.assertEqual(job.samples['g'][-1]['concurrent_resource_gate']['charges']['g']['required_bytes'], None)
        self.assertEqual(job.safety, {})
        self.assertTrue(job.proof_pending)

    def test_numeric_oom_swap_stops_survive_following_complete_sample(self):
        for violation in ('cap', 'host', 'gpu', 'oom', 'swap'):
            with self.subTest(violation=violation):
                job, host, rows, _ = self.setup_case()
                group = rows['gap']['cgroups']['q']
                if violation == 'cap': group['anon_bytes'] = 32 * GIB
                if violation == 'host': rows['gap']['host']['available_bytes'] = 0
                if violation == 'gpu': rows['gap']['gpus'][1]['free_bytes'] = 0
                if violation == 'oom': group['events']['oom'] = 1
                if violation == 'swap': group['swap_bytes'] = 4096
                for _ in range(3 if violation == 'swap' else 1): job.collect()
                self.assertTrue(job.safety)
                self.assertTrue(job.active['q']['cancel_event'].is_set())
                rows['current'] = rows['good']; job.active['q']['phase'] = 'ready'
                job.collect()
                self.assertTrue(job.safety)
                self.assertTrue(job.active['q']['cancel_event'].is_set())
                with self.assertRaises(RuntimeError): job.admission('q')
                self.assertEqual(host.requests, {})

    def test_existing_safety_never_cleared_and_legacy_scopes_unchanged(self):
        job, _, _, _ = self.setup_case()
        job.safety['g'] = 'STOP_PRIOR_RESOURCE'
        job.collect()
        self.assertEqual(job.safety, {'g': 'STOP_PRIOR_RESOURCE'})
        for scope in ('concurrent-480k-cpu', 'concurrent-g1q1', 'candidate-pair-validation'):
            with self.subTest(scope=scope):
                job, _, _, _ = self.setup_case(scope)
                job.collect()
                self.assertEqual(job.safety, {'g': 'SKIP_UNSAFE_PLACEMENT', 'q': 'SKIP_UNSAFE_PLACEMENT'})


if __name__ == '__main__':
    unittest.main()
