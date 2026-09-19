"""G1-only scope, native proof and safety regressions; synthetic offline I/O."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from tests import test_benchmark_q1_scope as q1
from tests import test_benchmark_allocation as alloc
from tests import test_benchmark_client as wire
from benchmark import allocation, client, warmup

runner, profiles, fixtures = q1.runner, q1.profiles, q1.fixtures
CASES = [name.replace('Q1-', 'G1-') for name in q1.CASES]


class G1Scope(unittest.TestCase):
    def setup_case(self, path):
        runner.save(path / 'execution.json', q1.EXECUTION)
        runner.save(path / 'private/fixtures.json', q1.saved_fixtures())
        sha = runner.arm(path, 'benchrun-20260919', 'g1-only')
        armed = runner.load_arm(path, sha)
        c, host, requests = q1.integrated.IntegratedRunner().setup_case(path, armed['manifests'])
        c.armed = armed
        transport = c.transport_factory
        c.transport_factory = lambda url, key, **options: transport(url, key)
        host.budget.clock = lambda: q1.EPOCH
        host.budget.start('maintenance')
        host.budget.clock = lambda: q1.EPOCH + 600
        return c, host, requests, sha

    def test_exact_ladder_three_warmups_five_cases_and_preserved_qwen_fixtures(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            c, host, requests, _ = self.setup_case(path)
            before = copy.deepcopy(c.fixture_cache)
            with patch.object(c, 'mixed', side_effect=AssertionError('mixed forbidden')):
                c.run(resume=True)
            self.assertEqual(list(c.progress['completed']), CASES)
            self.assertTrue(all(row['status'] == 'PASS' for row in c.progress['completed'].values()))
            loads = [host.manifests[a['manifest_sha256']] for op, a in host.events if op == 'load']
            self.assertEqual([(m['placement'], m['configured_capacity']) for m in loads],
                             [('G1', 4096), ('G1', 16384), ('G1', 65536)])
            original = [profiles.command_manifest('G1', n, log_verbosity=4) for n in (4096, 16384, 65536)]
            self.assertEqual(loads, original)
            for m in loads:
                self.assertEqual(m['gpu_uuids'], [profiles.read_config()['gpu_uuids'][0]])
                self.assertEqual((m['guest_cpuset'], m['guest_cpu_count']), ('0-95', 96))
                for flag, value in [('--n-cpu-moe','76'),('--cache-type-k','f16'),('--cache-type-v','f16'),('--fit','off')]:
                    self.assertEqual(m['native_argv'][m['native_argv'].index(flag)+1], value)
            self.assertEqual(len(requests), 8)
            self.assertEqual(sum('warmup-prefix-' in r['messages'][0]['content'] for r in requests), 3)
            self.assertEqual(sum(r['max_tokens'] == 512 for r in requests), 1)
            self.assertTrue(all(r['model'] == 'bench-glm-5.3' and not r.get('tools') and r['reasoning_effort'] == 'low' for r in requests))
            self.assertNotIn('admit_mixed', [op for op, _ in host.events])
            after = json.loads((path / 'private/fixtures.json').read_bytes())
            self.assertEqual({k: after[k] for k in before}, before)
            self.assertEqual(len(after) - len(before), 4)
            self.assertTrue(all(k.startswith('bench-glm-5.3-') for k in after.keys() - before.keys()))
            self.assertEqual(json.loads((path / 'execution.json').read_bytes()), q1.EXECUTION)
            self.assertEqual(host.budget.data['started_at'] + 21600, q1.DEADLINE)
            anchor = c.progress['completed'][CASES[2]]
            self.assertEqual(anchor['fixture_sha256'], c.progress['completed'][CASES[1]]['fixture_sha256'])

    def test_logging_only_manifest_delta_and_historical_defaults_unchanged(self):
        import shlex
        for capacity in (4096,16384,65536):
            base=profiles.command_manifest('G1',capacity)
            logged=profiles.command_manifest('G1',capacity,log_verbosity=4)
            self.assertEqual(logged['native_argv'],base['native_argv']+['--log-verbosity','4'])
            self.assertEqual(logged['create_argv'],base['create_argv']+['--log-verbosity','4'])
            normalized={**logged,'native_argv':logged['native_argv'][:-2],
                        'create_argv':logged['create_argv'][:-2],
                        'create_shell':shlex.join(logged['create_argv'][:-2])}
            self.assertEqual(normalized,base)
            self.assertNotIn('--log-verbosity',base['native_argv'])
        for placement,verbosity in [('G2',4),('Q1',4),('G1',3),('G1',5),('G1',True)]:
            with self.assertRaisesRegex(ValueError,'unreviewed_observational_logging'):
                profiles.command_manifest(placement,4096,log_verbosity=verbosity)

    def test_scope_manifest_plan_and_resume_gates_before_host(self):
        with tempfile.TemporaryDirectory() as directory:
            c, host, _, _ = self.setup_case(Path(directory))
            with self.assertRaisesRegex(RuntimeError, 'explicit_resume'): c.run()
            original = copy.deepcopy(c.armed)
            bad = []
            for p,n in [('Q1',4096),('Q2',16384),('G2',65536)]:
                bad.append({**original,'manifests':original['manifests']+[profiles.command_manifest(p,n)]})
            bad.extend([{**original,'trial_plan':profiles.trial_order()},
                        {**original,'manifests':list(reversed(original['manifests']))}])
            for value in bad:
                c.armed = value
                with self.assertRaises(ValueError): c.run(resume=True)
            self.assertEqual(host.events, [])
            host = q1.host_tests.HostTests().bare(); host.scope = 'g1-only'
            with self.assertRaisesRegex(ValueError, 'mixed_excluded'): host.dispatch({'op':'admit_mixed'})
            with patch.object(profiles, 'read_config', return_value={}):
                with self.assertRaisesRegex(RuntimeError, 'BLOCKED_GLM_OFFLOAD'): runner.run_preflight('g1-only')
                runner.run_preflight('q1-only'); runner.run_preflight('q1-256k')
            runner.run_preflight('g1-only')

    def test_failure_stops_restores_without_retry_or_reclassification(self):
        for verdict in ('MODEL_INCORRECT','HARNESS_FAILURE','STOP_OOM'):
            with self.subTest(verdict=verdict), tempfile.TemporaryDirectory() as directory:
                c, host, _, _ = self.setup_case(Path(directory))
                with patch.object(c, 'trial', return_value={'status':verdict}):
                    with self.assertRaisesRegex(RuntimeError, 'stopped_for_review'): c.run(resume=True)
                self.assertEqual(sum(op == 'load' for op, _ in host.events), 1)
                self.assertEqual(host.events[-1][0], 'restore')
                self.assertEqual(c.progress['skipped_after_stop'], CASES)
                c.progress['completed'][CASES[0]] = {'status':verdict}
                host.events.clear()
                with self.assertRaisesRegex(RuntimeError, 'failed_measurement'): c.run(resume=True)
                self.assertEqual(host.events, [])

    def test_exact_cache_and_graph_proof_at_each_g1_capacity(self):
        f = alloc.Allocation()
        for n in (4096,16384,65536):
            m = profiles.command_manifest('G1',n)
            log = f.glm_log().replace('4096',str(n)).replace('lid_nodes=78','lid_nodes=21').replace('bytes=195035136',f'bytes={95232*n}')
            parsed = allocation.parse_glm_log(log)
            self.assertEqual(allocation.allocation_gate(m,parsed,f.observed(m),strict_g1=True)['status'], 'ALLOCATION_PROOF_ACCEPTED')
            for field,value,reason in [('cache_bytes',{'CUDA0':95232*n//2},'g1_f16_cache_bytes_mismatch'),
                                       ('lid_nodes',78,'g1_main_indexer_graph_mismatch'),
                                       ('fa_nodes',77,'g1_main_indexer_graph_mismatch')]:
                bad = copy.deepcopy(parsed);bad['native'][field] = value
                self.assertIn(reason,allocation.allocation_gate(m,bad,f.observed(m),strict_g1=True)['reasons'])
        # Historical default acceptance remains unchanged; strict scope adds checks.
        m=f.glm_manifest(); parsed=allocation.parse_glm_log(f.glm_log())
        self.assertEqual(allocation.allocation_gate(m,parsed,f.observed(m))['status'],'ALLOCATION_PROOF_ACCEPTED')

    def test_glm_native_timing_proof_and_missing_counter_refusal(self):
        # Native GLM response shape retained in d3cap4 smoke-result.json.
        saved=json.loads((profiles.ROOT/'reports/d3cap4-evidence/smoke-result.json').read_bytes())
        raw=wire.stream([wire.event({'content':'ok'}),wire.event(finish='stop'),
                         {'model':'bench-glm-5.3','choices':[], 'usage':saved['usage'],'timings':saved['timings']}])
        counters=client.parse_response(raw,'bench-glm-5.3')['counters']
        self.assertEqual(counters['evaluated_prompt_tokens'],saved['timings']['prompt_n'])
        self.assertEqual(counters['cached_tokens'],saved['timings']['cache_n'])
        self.assertEqual(counters['prompt_ms'],saved['timings']['prompt_ms'])
        m=profiles.command_manifest('G1',4096)
        self.assertEqual(saved['identity']['image'],m['image'])
        with self.assertRaisesRegex(RuntimeError,'PREFILL_UNPROVED'): warmup.prefill_proof(counters,m,{})
        synthetic={**counters,'evaluated_prompt_tokens':2340,'prompt_tokens':2340}
        self.assertEqual(warmup.prefill_proof(synthetic,m,{})['source'],'native_evaluated_prompt_tokens')
        synthetic.update(evaluated_prompt_tokens=None,cached_tokens=None)
        with self.assertRaisesRegex(RuntimeError,'PREFILL_UNPROVED'):
            warmup.prefill_proof(synthetic,m,{'server_facts':{'disable_radix_cache':True}})

    def test_resource_latch_cancels_but_reporting_failure_does_not(self):
        for violation in ('oom','swap','gpu','host','missing','reporting'):
            with self.subTest(violation=violation), tempfile.TemporaryDirectory() as directory:
                c, host, _, _=self.setup_case(Path(directory));host.call('begin')
                cid=c.loaded(c.armed['manifests'][0]);original=host.call
                def call(op, **args):
                    row=original(op,**args)
                    if op=='telemetry':
                        if violation=='oom': row['cgroups'][cid]['events']['oom']=1
                        if violation=='swap': row['cgroups'][cid]['swap_bytes']=4096
                        if violation=='gpu': row['gpus'][0]['free_bytes']=0
                        if violation=='host': row['host']['available_bytes']=0
                        if violation=='missing': row['host']['available_bytes']=None
                        if violation=='reporting': raise ValueError('synthetic observer failure')
                    return row
                host.call=call
                for _ in range(3): c.collect()
                self.assertEqual(c.active[cid]['cancel_event'].is_set(),violation not in ('missing','reporting'))
                if violation in ('missing','reporting'): continue
                # Replay a violation arriving after admission; raw partial remains
                # saved before request_end and the outer restoration path.
                c.safety.clear()
                def transport(url,key,**options):
                    self.assertTrue(options['cancel_event'].is_set())
                    def send(raw,timeout):
                        yield b'data: {"partial":true}\n\n'
                        raise OSError('synthetic cancelled socket')
                    return send
                c.transport_factory=transport
                raw=fixtures.serialize_validate(fixtures.build_sample('bench-glm-5.3',20,'safe-seed','safe-nonce'))
                with self.assertRaisesRegex(RuntimeError,'STOP_|SKIP_'): c.request(cid,raw,'safety-stop')
                self.assertEqual(host.events[-1][0],'request_end')
                self.assertEqual((Path(directory)/'private/safety-stop.response.sse').read_bytes(),b'data: {"partial":true}\n\n')

    def test_already_set_event_refuses_http_dispatch(self):
        cancel=threading.Event();cancel.set()
        with patch('http.client.HTTPConnection') as factory:
            send=client.http_transport('http://127.0.0.1:31002','synthetic',cancel_event=cancel)
            with self.assertRaisesRegex(fixtures.HarnessError,'resource safety cancellation'): list(send(b'{}',10))
            factory.return_value.request.assert_not_called()
            factory.return_value.close.assert_called_once()

    def test_waiting_http_headers_are_closed_on_resource_event(self):
        cancel=threading.Event();closed=threading.Event()
        with patch('http.client.HTTPConnection') as factory:
            connection=factory.return_value
            connection.sock.shutdown.side_effect=lambda *_:closed.set()
            def headers():
                cancel.set()
                self.assertTrue(closed.wait(2),'resource event must close a waiting header socket')
                raise OSError('cancelled')
            connection.getresponse.side_effect=headers
            send=client.http_transport('http://127.0.0.1:31002','synthetic',cancel_event=cancel)
            with self.assertRaises(OSError): list(send(b'{}',10))
            connection.close.assert_called_once()

    def test_blocked_http_read_is_closed_on_resource_event(self):
        cancel=threading.Event();closed=threading.Event()
        with patch('http.client.HTTPConnection') as factory:
            connection=factory.return_value;response=connection.getresponse.return_value
            response.status=200;response.getheader.return_value='text/event-stream'
            connection.sock.shutdown.side_effect=lambda *_:closed.set()
            def read(*_):
                cancel.set()
                self.assertTrue(closed.wait(2),'resource event must close a blocked read')
                raise OSError('cancelled')
            response.read1.side_effect=read
            send=client.http_transport('http://127.0.0.1:31002','synthetic',cancel_event=cancel)
            with self.assertRaises(OSError): list(send(b'{}',10))
            connection.close.assert_called_once();response.close.assert_called_once()


if __name__ == '__main__': unittest.main()
