"""Focused sealed-batch runner/transport composition; synthetic offline only."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import client, concurrent_run, cpu_budget_profiles as profile
from benchmark import decode_diag, fixtures, g1_ladder, postrestart72_batch as batch, postrestart72_followup as followup, postrestart72_run as run72, runner


def arm():
    return {'scope': profile.POSTRESTART_SCOPE, 'campaign': profile.POSTRESTART_BATCH_CAMPAIGN,
        'mode': profile.POSTRESTART_BATCH_MODE, 'source_commit': 'a'*40, 'session_id': 'fresh-batch-session',
        'manifests': profile.postrestart_manifests(profile.POSTRESTART_BATCH_CAMPAIGN),
        'trial_plan': profile.postrestart_trial_order(profile.POSTRESTART_BATCH_MODE),
        'frozen_inputs': {}, 'runtime': copy.deepcopy(run72.POLICY), 'runtime_policy': copy.deepcopy(run72.POLICY)}


class BatchRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        (self.state/'private').mkdir(mode=0o700)
        runner.save(self.state/'progress.json', {'phase':'INITIAL','completed':{},'inflight':{},'errors':[]})
        self.host = Mock()
        self.run = run72.PostrestartRun(self.state, arm(), self.host, 'synthetic-test-key')
        self.run.boundary = Mock(); self.run.record = Mock(); self.run.emit = Mock(); self.run.hold = Mock()
        self.run.require_no_faults = Mock()
        self.run.prepare_job = lambda cid, identifier: {'id':identifier,'cid':cid}
        self.host.call.side_effect = lambda op, **kw: {'sealed':True} if op == 'seal_batch' else {'admitted':True}

    def test_exact_B3_pair_quality_outcome_holds_with_display_B3_and_host_ordinal_one(self):
        seen=[]; barrier=threading.Barrier(2)
        def measure(job):
            seen.append(job['id']); barrier.wait(timeout=2)
            return {'id':job['id'], 'status':'FAIL_FORMAT',
                'sample':{'status':'COMPLETE', 'owner_drain':{'drained':True}}}
        self.run.measure = measure
        with patch.object(batch, 'bind_jobs', return_value={'sealed':'synthetic'}):
            self.run.batch_sequence({'G1':'g','Q1':'q'})
        self.assertEqual(set(seen), set(batch.CASES[0]))
        self.assertEqual(len(seen),2)
        self.run.hold.assert_called_once_with('quality_review')
        self.assertEqual([x.kwargs['case'] for x in self.host.call.call_args_list if x.args[0]=='batch_case_begin'],[1])
        self.run.record.assert_any_call('DISPATCHING_B3')
        saved=json.loads((self.state/'B3-case.json').read_bytes())
        self.assertEqual(saved['case'],'B3')
        self.assertEqual(saved['requested_ids'],list(batch.REQUEST_IDS))
        self.assertFalse(saved['automatic_retry'])
        self.assertFalse((self.state/'B1-case.json').exists())
        self.assertFalse((self.state/'B2-case.json').exists())
        self.assertEqual([row.args[0]['case'] for row in self.run.emit.call_args_list
                          if row.args[0].get('type')=='sealed_batch_case'],['B3'])

    def test_existing_sequence_two_loads_two_discarded_warmups_two_measures_then_hold(self):
        loaded=[]; warmed=[]; measured=[]; barrier=threading.Barrier(2)
        def load(manifest):
            cid=manifest['placement']; loaded.append(cid)
            self.run.pending_warmups.append((cid,))
            return cid
        def measure(job):
            self.assertEqual(warmed,['G1','Q1'])
            measured.append(job['id']); barrier.wait(timeout=2)
            return {'id':job['id'],'status':'PASS',
                    'sample':{'status':'COMPLETE','owner_drain':{'drained':True}}}
        self.run.loaded=load
        self.run.discarded_warmup=lambda cid: warmed.append(cid)
        self.run.measure=measure
        self.host.call.side_effect=lambda op, **kw: (
            {'manifests':arm()['manifests']} if op=='admit_concurrent' else
            {'sealed':True} if op=='seal_batch' else {'admitted':True})
        with patch.object(batch,'bind_jobs',return_value={}):
            self.run.sequence()
        self.assertEqual(loaded,['G1','Q1']);self.assertEqual(warmed,loaded)
        self.assertEqual(sorted(measured),sorted(batch.REQUEST_IDS));self.assertEqual(len(measured),2)
        self.assertTrue(self.run.hold_ready)
        self.run.hold.assert_called_once_with('complete')

    def test_ambiguous_drain_or_numeric_fault_stops_later_case_and_preserves_entered_case(self):
        seen=[]
        def measure(job):
            seen.append(job['id'])
            return {'id':job['id'],'status':'PASS','sample':{'status':'COMPLETE','owner_drain':{'drained':False}}}
        self.run.measure=measure
        with patch.object(batch,'bind_jobs',return_value={}):
            with self.assertRaisesRegex(RuntimeError,'UNRESOLVED'):
                self.run.batch_sequence({'G1':'g','Q1':'q'})
        self.assertEqual(set(seen),set(batch.CASES[0]));self.run.hold.assert_not_called()
        self.assertTrue((self.state/'B3-case.json').exists())
        self.run.require_no_faults.side_effect=RuntimeError('STOP_RESOURCE_GATE')
        with patch.object(batch,'bind_jobs',return_value={}):
            with self.assertRaisesRegex(RuntimeError,'STOP_RESOURCE_GATE'):
                self.run.batch_sequence({'G1':'g','Q1':'q'})

    def test_batch_GO_mode_campaign_must_match_and_legacy_4096_remains_forbidden(self):
        armed=arm();armed['session_id']='prep-session'
        go={'mode':profile.POSTRESTART_BATCH_MODE,'campaign':profile.POSTRESTART_BATCH_CAMPAIGN,
            'run_session_id':'fresh-run-session','runtime':copy.deepcopy(run72.POLICY)}
        self.assertEqual(run72.BATCH_BASE,'ad76a6435dd6af2c95f7c47bd3d4453f58b43c69')
        self.assertEqual(run72.bind_runtime(armed,go,'fresh-run-session'),run72.POLICY)
        for key in ('mode','campaign'):
            bad=copy.deepcopy(go);bad.pop(key)
            with self.assertRaises(ValueError):run72.bind_runtime(armed,bad,'fresh-run-session')
        self.run.mode=profile.POSTRESTART_MEASURED_MODE
        with self.assertRaisesRegex(ValueError,'closed_output'):
            self.run.request('g',decode_diag.long_body(),batch.SCIENCE_ID)

    def test_B3_dispatch_keeps_full_timeout_and_science_is_not_admitted(self):
        self.run.active['g']={'manifest':arm()['manifests'][0],'cancel_event':threading.Event()}
        self.run.admission=Mock(return_value=7200)
        clock={'dispatch_monotonic_s':1,'deadline_monotonic_s':7201,'terminal_monotonic_s':7201,
               'timeout_seconds':7200,'basis':'HTTP_transport_dispatch','terminal_reason':'DRAINED',
               'deadline_expired':False}
        transport=Mock();transport.request_clock=clock
        self.run.transport_factory=Mock(return_value=transport)
        with self.assertRaisesRegex(ValueError,'batch_exact_request_required'):
            self.run.request('g',decode_diag.long_body(),batch.SCIENCE_ID)
        self.run.admission.assert_not_called();self.run.transport_factory.assert_not_called()
        preset=followup.PRESETS['P-G65008']
        raw=g1_ladder.body_bytes(fixtures.build_sample('bench-glm-5.3',preset['records'],preset['seed'],'fresh-dispatch-B3'))
        self.host.call.side_effect=None;self.host.call.return_value={'drained':True}
        for terminal, status in [('DRAINED','COMPLETE'),('REQUEST_DEADLINE','TRANSPORT_FAILURE')]:
            clock.update(terminal_reason=terminal,deadline_expired=terminal=='REQUEST_DEADLINE')
            captured={'summary':{'status':status,'counters':{}},'parsed':None}
            with patch.object(client,'_capture_request',return_value=captured) as capture:
                result=self.run.request('g',raw,'B3-G65008')
            self.assertEqual(result['summary']['status'],status)
            self.assertTrue(capture.call_args.kwargs['capture_events'])
            self.assertEqual(capture.call_args.kwargs['timeout'],7200)
            self.assertIsNone(self.run.transport_factory.call_args.kwargs['deadline_epoch'])
        self.assertFalse(result['summary']['owner_drain']['drained'])
        self.assertFalse(any(c.args[0]=='batch_timeout_drain' for c in self.host.call.call_args_list))


class TransportDeadlineTests(unittest.TestCase):
    def test_admission_expiry_refuses_new_HTTP_without_clipping_an_admitted_request(self):
        with patch.object(client.time, 'time', return_value=101), patch('http.client.HTTPConnection') as connect:
            send=client.http_transport('http://127.0.0.1:31002','synthetic',admission_deadline_epoch=101)
            with self.assertRaises(Exception): list(send(b'{}',7200))
            connect.assert_not_called()
            self.assertEqual(send.request_clock['terminal_reason'],'NOT_DISPATCHED_ADMISSION_EXPIRED')
            self.assertFalse(send.request_clock['http_dispatched'])
        now=[100.]; sock=Mock()
        def read(size): now[0]=102.; return b''
        response=SimpleNamespace(status=200,getheader=lambda *a:'text/event-stream',read1=read,close=lambda:None)
        conn=SimpleNamespace(sock=sock,request=lambda *a,**k:None,getresponse=lambda:response,close=lambda:None)
        with patch.object(client.time,'time',side_effect=lambda:now[0]),patch('http.client.HTTPConnection',return_value=conn),patch('threading.Timer'):
            send=client.http_transport('http://127.0.0.1:31002','synthetic',clock=lambda:now[0],admission_deadline_epoch=101)
            self.assertEqual(list(send(b'{}',7200)),[])
        self.assertEqual(send.request_clock['terminal_reason'],'DRAINED')
        self.assertEqual(send.request_clock['deadline_monotonic_s'],7300)

    def transport(self, outcome):
        now=[1.]; callback=[]; sock=Mock()
        class Timer:
            daemon=False
            def __init__(self,timeout,fn):self.fn=fn;callback.append(fn)
            def start(self):pass
            def cancel(self):pass
        def read(size):
            if outcome=='deadline':
                now[0]=7201.;callback[0]();return b''
            now[0]=2.;raise ConnectionResetError('synthetic')
        response=SimpleNamespace(status=200,getheader=lambda *a:'text/event-stream',read1=read,close=lambda:None)
        conn=SimpleNamespace(sock=sock,request=lambda *a,**k:None,getresponse=lambda:response,close=lambda:None)
        with patch('http.client.HTTPConnection',return_value=conn),patch('threading.Timer',Timer):
            send=client.http_transport('http://127.0.0.1:31002','synthetic',clock=lambda:now[0])
            with self.assertRaises(Exception):list(send(b'{}',7200))
        return send.request_clock

    def test_timer_closed_EOF_is_TIMEOUT_evidence_but_connection_reset_is_not(self):
        deadline=self.transport('deadline'); reset=self.transport('reset')
        self.assertEqual(deadline['terminal_reason'],'REQUEST_DEADLINE')
        self.assertTrue(deadline['deadline_expired'])
        self.assertEqual(deadline['deadline_monotonic_s']-deadline['dispatch_monotonic_s'],7200)
        self.assertEqual(reset['terminal_reason'],'TRANSPORT_FAILURE')
        self.assertFalse(reset['deadline_expired'])

if __name__=='__main__':unittest.main()
