"""Diagnostic request/counter/clock seams only; no model or network acceptance."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import decode_diag as diag, fixtures, profiles, telemetry, g1_ladder
from benchmark.host import HostBudget, LinuxHost, RPC_OPERATIONS
from benchmark.runner import Campaign


def counter(capacity):
    def count(raw):
        body=json.loads(raw)
        records=body['messages'][0]['content'].count('record=')
        return {'source':'synthetic_offline','input_tokens':records*31+140,
                'body_sha256':fixtures.digest(raw),'configured_context':capacity,
                'template_sha256':'a'*64,'token_ids_sha256':'b'*64}
    return count


class DecodeProtocol(unittest.TestCase):
    def test_short_matching_final_count_and_no_eos_forcing(self):
        sample,raw,count=diag.fit_short(1024,'short-fresh-0001',counter(1024),synthetic=True)
        self.assertTrue(600<=count['input_tokens']<=750)
        body=json.loads(raw)
        self.assertEqual((body['max_tokens'],body['seed'],body['temperature']), (128,1729,1))
        self.assertTrue(body['timings_per_token'])
        self.assertNotIn('ignore_eos',body);self.assertNotIn('response_format',body)
        self.assertEqual(count['body_sha256'],fixtures.digest(raw))
        for capacity in (32768,65536):
            later,_,proof=diag.fit_short(capacity,'short-fresh-0002',counter(capacity),matched=sample,synthetic=True)
            self.assertEqual(later['fixture_sha256'],sample['fixture_sha256'])
            self.assertEqual(proof['input_tokens'],count['input_tokens'])
        with self.assertRaises(ValueError):
            diag.fit_short(32768,'short-fresh-0002',counter(32768),synthetic=True)
        with self.assertRaises(ValueError):
            diag.fit_short(32768,sample['nonce'],counter(32768),matched=sample,synthetic=True)

    def test_warmup_provenance_uses_actual_capacity(self):
        for capacity in diag.CAPACITIES:
            _,raw,proof=diag.fit_warmup(capacity,'warmup-fresh-001',counter(capacity),synthetic=True)
            minimum=512 if capacity==1024 else 2048
            self.assertEqual(proof['minimum_warmup_prefill_tokens'],minimum)
            self.assertEqual(proof['configured_context'],capacity)
            self.assertEqual(proof['body_sha256'],fixtures.digest(raw))
            self.assertLess(proof['input_tokens']+32,capacity)

    def test_replay_and_long_contract_separate(self):
        prior,_,_=g1_ladder.fit(65536,'prior-saved-0001',counter(65536),synthetic=True)
        counted=Mock(side_effect=counter(65536))
        sample,raw,proof=diag.fit_replay('trial-fresh-0001',counted,prior,synthetic=True)
        counted.assert_called_once();self.assertEqual(sample['fixture_sha256'],prior['fixture_sha256'])
        body=json.loads(raw)
        self.assertEqual(body['response_format']['json_schema']['schema']['required'],list(fixtures.MARKERS))
        self.assertTrue(64896<=proof['input_tokens']<=65024)
        self.assertEqual(proof['body_sha256'],fixtures.digest(raw))
        natural=json.loads(diag.long_body())
        self.assertEqual(natural['messages'],[{'role':'user','content':diag.QUESTION}])
        self.assertEqual(natural['max_tokens'],4096)
        self.assertNotIn('response_format',natural);self.assertNotIn('ignore_eos',natural)
        self.assertIn('finite-element method solves Poisson’s equation',natural['messages'][0]['content'])

    def test_existing_ladder_caller_keeps_native_counter_default_scope(self):
        manifest=profiles.g1_ladder_manifest(16384)
        native={'/props':{'model_alias':'bench-glm-5.3','is_sleeping':False,'total_slots':1,
                         'default_generation_settings':{'n_ctx':16384},'chat_template':'template'},
                '/apply-template':{'prompt':'rendered'},'/tokenize':{'tokens':[1,2,3]}}
        job=SimpleNamespace(active={'c':{'manifest':manifest,'template_sha256':None}},armed={'scope':'g1-ladder'},
            key='offline-not-a-key',admission=Mock(return_value=10),host=Mock(),
            json_factory=lambda *a,**kw:lambda route,body:native[route])
        count=Campaign.counter(job,'c')
        result=count(diag.long_body())
        self.assertEqual(result['input_tokens'],3)
        self.assertEqual(job.host.call.call_count,3)

    def test_sparse_events_use_native_count_intervals_and_final_reconcile(self):
        rows=[{'arrived_monotonic_s':i,'native_timings':{'predicted_n':n,'predicted_ms':ms}}
              for i,(n,ms) in enumerate(((1,0),(5,400),(9,800),(13,1200),(13,1200)))]
        result=diag.decode_windows(rows,{'decode_tokens':13,'decode_ms':1200})
        self.assertEqual([w['native_tokens_per_second'] for w in result['windows']],[10,10,10])
        self.assertEqual(diag.decode_windows(rows[:2])['status'],'UNAVAILABLE')
        self.assertEqual(diag.decode_windows(rows,{'decode_tokens':14,'decode_ms':1200})['status'],'UNAVAILABLE')
        rows[-1]['native_timings']['predicted_n']=3
        self.assertEqual(diag.decode_windows(rows)['reason'],'native_counter_regression')
        repeated=copy.deepcopy(rows[:2]);repeated.append({'native_timings':{'predicted_n':5,'predicted_ms':900}})
        repeated += rows[2:4]
        self.assertEqual(diag.decode_windows(repeated)['reason'],'same_count_native_time_changed')

    def test_natural_answer_length_does_not_imply_quality_or_completion(self):
        for status,finish,n,complete,cap in [('COMPLETE','stop',300,True,False),
                ('OUTPUT_LIMIT','length',4096,False,True),('TRANSPORT_ERROR',None,None,False,False)]:
            result={'summary':{'status':status,'counters':{'completion_tokens':n}},
                    'parsed':{'finish_reason':finish,'message':{'content':'private final text'}}}
            row=diag.natural_outcome(result)
            self.assertEqual(row['completed_natural_answer'],complete)
            self.assertEqual(row['is_4096_token_throughput_sample'],cap)
            self.assertNotIn('private final text',json.dumps(row))
            self.assertEqual(row['coherence_and_topic_coverage'],'REQUIRES_PRIVATE_FINAL_CONTENT_REVIEW')

    def test_capture_requires_complete_same_task_decode_bracket(self):
        before={'slot_id':0,'task_id':42,'is_processing':True,'n_decoded':3,'host_finished_monotonic_s':10}
        after={'slot_id':0,'task_id':42,'is_processing':True,'n_decoded':14,'host_started_monotonic_s':16}
        self.assertTrue(diag.capture_is_decode(before,after,10.1,15.9))
        for key,value in [('task_id',43),('n_decoded',3),('is_processing',False),('host_started_monotonic_s',15)]:
            changed={**after,key:value};self.assertFalse(diag.capture_is_decode(before,changed,10.1,15.9))
        self.assertFalse(diag.capture_is_decode({},after,10.1,15.9))

    def test_host_slot_snapshot_sanitizes_debug_payload(self):
        host=object.__new__(LinuxHost);host.scope='glm-decode-diag';host.owner=SimpleNamespace(phase='ACTIVE')
        host.requests={'a':{}};host.identity=Mock()
        slot={'id':0,'id_task':42,'is_processing':True,'next_token':[{'n_decoded':3}],
              'prompt':'PRIVATE_PROMPT','generated':'PRIVATE_OUTPUT','params':{'seed':1729}}
        with patch('benchmark.host.http_json',return_value=[slot]) as call:
            receipt=host.dispatch({'op':'decode_progress','args':{'id':'a'}})
        self.assertNotIn('PRIVATE',json.dumps(receipt));self.assertEqual(receipt['n_decoded'],3)
        self.assertIn('decode_progress',RPC_OPERATIONS);call.assert_called_once_with(31002,'/slots',timeout_s=5)

    def test_clock_timeout_and_host_budget_never_reset(self):
        clock={'start_epoch':1000,'deadline_epoch':15400,'budget_seconds':14400,
               'request_max_seconds':7200,'clock_includes_preparation':True,'restoration_outside_budget':True}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'stage-clock.json';path.write_text(json.dumps(clock))
            self.assertEqual(diag.stage_clock(directory),clock)
            clock['budget_seconds']=10800;path.write_text(json.dumps(clock))
            with self.assertRaises(ValueError):diag.stage_clock(directory)
            clock['budget_seconds']=14400
        self.assertEqual(LinuxHost.decode_clock({'runtime':clock}),(1000,15400))
        self.assertEqual(diag.request_timeout(clock,2000),7200)
        self.assertEqual(diag.request_timeout(clock,15399),1)
        with self.assertRaises(RuntimeError):diag.request_timeout(clock,15400)
        host=SimpleNamespace(scope='glm-decode-diag',log_root='/data/logs/test',start_epoch=1000,
             deadline_epoch=15400,read_json=Mock(return_value=None),write_json=Mock())
        with patch('benchmark.host.time.time',return_value=1100):
            budget=HostBudget(host);budget.start('maintenance')
        budget.clock=lambda:15400
        with self.assertRaises(ValueError):budget.request_timeout()
        budget.begin_restoration();budget.finish_restoration(True)
        self.assertEqual(budget.data['deadline_epoch'],15400)

    def test_gpu_optional_fields_never_replace_missing_or_change_defaults(self):
        base='GPU-abc, 100, 40, 60, 2, 100'
        self.assertNotIn('decode_fields',telemetry.parse_gpu_csv(base)[0])
        row=telemetry.parse_gpu_csv(base+', N/A, 1500, 1400, 5, 16, 600',decode_diagnostic=True)[0]
        self.assertIsNone(row['decode_fields']['memory_utilization_percent'])
        self.assertEqual(row['decode_fields']['sm_clock_mhz'],1500)
        self.assertIsNone(row['pcie_throughput'])

    def test_host_cpu_cadence_uses_existing_monitor_without_slot_polling(self):
        host=object.__new__(LinuxHost);host.scope='glm-decode-diag';host.identity=Mock(return_value=({},Path('/unused'),[1]))
        host.samples={};host.load_manifests={};host.allocation_proofs={};host.measured={}
        with patch('benchmark.host.collect_sample',return_value={'cgroups':{},'gpus':[]}) as base, \
             patch('benchmark.decode_telemetry.collect_decode_sample',return_value={'sample_kind':'decode_cpu'}) as cpu, \
             patch('benchmark.host.time.monotonic',return_value=10) as clock, \
             patch('benchmark.host.http_json') as http:
            host.telemetry('c');host.telemetry('c');self.assertEqual(cpu.call_count,1)
            clock.return_value=15;host.telemetry('c');self.assertEqual(cpu.call_count,2)
            self.assertTrue(base.call_args.kwargs['decode_diagnostic']);http.assert_not_called()


if __name__=='__main__':unittest.main()
