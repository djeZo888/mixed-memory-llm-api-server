"""Offline selected-byte producer fixtures, not native TRACE availability."""
import importlib.util,json,tempfile,unittest,os,hashlib
from pathlib import Path
from unittest.mock import patch
p=Path(__file__).resolve().parents[1]/'engine/codex_native_trace.py';spec=importlib.util.spec_from_file_location('trace_fixture',p);trace=importlib.util.module_from_spec(spec);spec.loader.exec_module(trace)
class Fixtures(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.capture=trace.TraceCapture((self.root,{'nonce':'n','runId':'r','sessionId':'s','sources':{},'nativeTraceMode':trace.MODE}))
 def tearDown(self):self.temp.cleanup()
 def line(self,**fields):return (json.dumps({'target':'codex_core::session::turn','level':'TRACE','timestamp':'2026-10-01T14:00:00Z','fields':{'message':'post sampling token usage','turn_id':'actual-fixture-turn',**fields}})+'\n').encode()
 def test_split_exact_original_offset_sequence_before_redaction(self):
  line=self.line(total_usage_tokens=7);original=b'unselected secret must not be retained\n'+line;self.capture.feed(original[:11]);self.capture.feed(original[11:]);self.capture.feed(b'',final=True);e=self.capture.events[0];self.assertEqual(e['stderrSequence'],2);self.assertEqual(e['stderrOffset'],39);self.assertEqual((self.root/e['file']).read_bytes(),line);self.assertEqual(e['sha256'],hashlib.sha256(line).hexdigest());self.assertEqual(len(list(self.root.iterdir())),1)
 def test_all_matching_events_survive_not_just_final_low_usage(self):
  self.capture.feed(self.line(total_usage_tokens=400000)+self.line(total_usage_tokens=10),final=True);self.assertEqual(len(self.capture.events),2)
 def test_estimate_and_other_target_are_not_usage(self):
  self.capture.feed(b'{"target":"codex_core::post_sampling_token_estimate","level":"TRACE","fields":{"message":"post sampling token estimate"}}\n',final=True);self.assertEqual(self.capture.events,[])
 def test_truncated_matching_json_fails_no_completion(self):
  with self.assertRaises(ValueError):self.capture.feed(self.line()[:-1],final=True)
  self.assertFalse(self.capture.complete)
 def test_invalid_utf8_and_selected_json_fail(self):
  for raw in [b'\xff\n',b'post sampling token usage not valid JSON\n']:
   with self.assertRaises((ValueError,UnicodeError)):trace.TraceCapture((self.root,{'nativeTraceMode':trace.MODE})).feed(raw)
 def test_missing_turn_and_duplicate_artifact_fail(self):
  with self.assertRaises(ValueError):self.capture.feed(self.line(turn_id=''))
  (self.root/'trace-event-0000.raw').write_text('old evidence')
  with self.assertRaises(FileExistsError):trace.TraceCapture((self.root,{'nativeTraceMode':trace.MODE})).feed(self.line())
 def test_event_overflow_fails_without_readiness(self):
  with self.assertRaises(ValueError):self.capture.feed(self.line()*65)
 def test_publish_requires_complete_same_observed_environment_and_cleanup_fields(self):
  self.capture.feed(self.line(),final=True);published=[];producer={'pid':1};receipts={'read_private':lambda p:{'containerId':'c','producer':producer,'nonce':'n','environment':trace.PAIR},'write_once':lambda p,n,v:published.append(v)}
  self.capture.publish(receipts,producer,'c',143,True,True);v=published[0];self.assertEqual(v['environment'],trace.PAIR);self.assertEqual(v['engineExitStatus'],143);self.assertTrue(v['requestedStop']);self.assertTrue(v['complete'])
  with self.assertRaises(ValueError):self.capture.publish(receipts,producer,'foreign',0,False,True)
class SettlementPublication(unittest.TestCase):
 def test_trace_failure_does_not_erase_actual_raw_engine_and_cleanup_receipt(self):
  p=Path(__file__).resolve().parents[1]/'engine/redact-acp.py';spec=importlib.util.spec_from_file_location('redact_fixture',p);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);calls=[]
  class Broken:
   def publish(self,*a):raise ValueError('synthetic capture failure')
  result=module.publish_cleanup_evidence('channel',{'publish_settlement':lambda *a:calls.append(a)},Broken(),'producer','container','id',143,True,True,0,1,True)
  self.assertFalse(result);self.assertEqual(len(calls),1);self.assertEqual(calls[0][4:],(143,True,True,0,1,True))
class V2Fixtures(Fixtures):
 def setUp(self):
  super().setUp();self.capture=trace.TraceCapture((self.root,{'nonce':'n','runId':'r','sessionId':'s','sources':{},'nativeTraceMode':trace.MODE_V2}))
 def line(self,**fields):
  raw=json.loads(super().line(**fields));raw.update(spans=[{'name':'turn','thread.id':'native-thread','turn.id':'actual-fixture-turn'}],span={'name':'turn','thread.id':'native-thread','turn.id':'actual-fixture-turn'});return (json.dumps(raw)+'\n').encode()
 def auto(self,thread='native-thread',turn='actual-fixture-turn',timestamp='2026-10-01T14:00:00.000123456Z'):
  return (json.dumps({'target':'codex_core::session::turn','level':'TRACE','timestamp':timestamp,'fields':{'message':'new'},'spans':[{'name':'turn','thread.id':thread,'turn.id':turn}],'span':{'name':'run_auto_compact','reason':'ContextLimit','phase':'MidTurn'}})+'\n').encode()
 def published(self):
  values=[];producer={'pid':1};self.capture.publish({'read_private':lambda p:{'containerId':'c','producer':producer,'nonce':'n','environment':trace.PAIR_V2},'write_once':lambda p,n,v:values.append(v)},producer,'c',125,False,True);return values[0]
 def test_v2_exact_array_even_empty_never_v1_downgrade(self):
  self.capture.feed(self.line(total_usage_tokens=400001),final=True);v=self.published();self.assertEqual(v['schema'],'codex-native-trace-v2');self.assertEqual(v['mode'],trace.MODE_V2);self.assertEqual(v['autoCalls'],[]);self.assertEqual(v['engineExitStatus'],125)
 def test_v2_all_original_numeric_and_auto_ancestry_sequences_hashes(self):
  original=self.line(total_usage_tokens=400001)+self.auto()+self.line(total_usage_tokens=10)+self.auto(thread='foreign',turn='foreign-turn');self.capture.feed(original[:17]);self.capture.feed(original[17:],final=True);v=self.published();self.assertEqual([e['kind'] for e in v['events']],['postSampling','autoCompactNew','postSampling','autoCompactNew']);self.assertEqual(len(v['autoCalls']),2);self.assertEqual(v['autoCalls'][-1]['threadId'],'foreign');self.assertEqual(v['autoCalls'][0]['nativeTimestamp'],'2026-10-01T14:00:00.000123456Z');self.assertEqual(b''.join((self.root/e['file']).read_bytes() for e in v['events']),original)
 def test_v2_duplicate_auto_retained_for_failclosed_consumer(self):
  self.capture.feed(self.line()+self.auto()+self.auto(),final=True);self.assertEqual(len(self.published()['autoCalls']),2)
 def test_v2_missing_foreign_conflicting_ancestry_fails_without_completion(self):
  for change in [lambda v:v.pop('spans'),lambda v:v['spans'][0].update({'thread.id':'foreign'}),lambda v:v['fields'].update(turn_id='foreign')]:
   raw=json.loads(self.line());change(raw)
   if 'spans' not in raw:raw.pop('span')
   with self.assertRaises(ValueError):trace.TraceCapture((self.root,{'nativeTraceMode':trace.MODE_V2})).feed((json.dumps(raw)+'\n').encode(),final=True)
 def test_publish_requires_complete_same_observed_environment_and_cleanup_fields(self):
  self.capture.feed(self.line(),final=True);v=self.published();self.assertEqual(v['environment'],trace.PAIR_V2)
  with self.assertRaises(ValueError):self.capture.publish({'read_private':lambda p:{'containerId':'c','producer':{'pid':1},'nonce':'n','environment':trace.PAIR},'write_once':lambda *a:None},{'pid':1},'c',0,False,True)
 def test_explicit_unknown_off_and_schema_mode_fail(self):
  for mode in ['off','unknown',None]:
   with self.assertRaises(ValueError):trace.TraceCapture((self.root,{'nativeTraceMode':mode}))
if __name__=='__main__':unittest.main()
