#!/usr/bin/env python3
"""H019 post-PASS qualifier adapted from the reviewed H018 mapping, with fresh identity and
actual full17 read/result/continuation verification. Never emits a PASS from count.
Usage: python3 build_qualification.py TASK_DIRECTORY COLLECTION_JSON
"""
from pathlib import Path
import base64,copy,datetime,hashlib,json,subprocess,sys
T=Path(sys.argv[1]).resolve();P=T/'private';R=T/'repo';collection=Path(sys.argv[2]).resolve()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(raw):return hashlib.sha256(raw).hexdigest()
def load(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n');p.chmod(0o600)
col=load(collection);start=load(T/'READINESS.json')['production_identity'];st=col['ordinary_state'];receipts=col['receipts'];rows={n:json.loads(v['raw']) for n,v in receipts.items() if n.endswith('.json')}
assert col['status']=='TERMINAL_COLLECTED' and col['unit']['MainPID']=='0' and col['unit']['Result']=='success' and col['unit']['ExecMainStatus']=='0'
client=rows['CLIENT.json'];native=rows['FINAL17-QUALIFICATION.json'];alloc=rows['ALLOCATION.json']
assert client['status']=='PASS_KEEP_WARM' and client['request_may_be_active'] is False
identity={k:st[k] for k in ('boot_id','manifest_sha256','supervisor','launch_id','native')}
assert st['status']=='RUNNING' and st['launch_id']==start['launch_id'] and st['native']==start['native']
assert client['production_identity']==identity==alloc['production_identity']
assert alloc['status']=='PASS' and st['selection']['generation']==12 and st['request_hold'] is False
assert col['proxy']['active_requests']==0 and col['proxy']['quarantined'] is False and col['proxy']['launch_id']==st['launch_id'] and col['proxy']['native']==st['native']
assert rows['AUTHORITY.json']['production_identity']==identity and rows['DISPATCH-ATTEMPT.json']['production_identity']==identity
assert native['status']=='PASS' and native['tools']==17 and native['native_tool_qualification'] is True
assert native['configured_context']==native['allocated_context']==alloc['actual_usable_context']==950000
for name,item in receipts.items():
 assert Path(name).name==name and digest(item['raw'].encode())==item['sha256']
 (P/name).write_text(item['raw']);(P/name).chmod(0o600)
labels=['SHORT-TEXT','FINAL17-TURN1','FINAL17-TURN2'];summaries={}
for label in labels:
 row=rows[label+'.json'];assert row['correctness']=='PASS' and row['done'] is True and row['full_http_drain'] is True
 assert row['owned_stream_disposition']['status']=='OWN_STREAM_TERMINAL_FULL_DRAIN'
 assert row['native_settlement']['status']=='AUTHENTICATED_SLOT_IDLE_AFTER_FULL_DRAIN'
 assert row['usage']['prompt_tokens']==row['expected_input_tokens']
 assert sha(P/(label+'-REQUEST.json'))==row['request_sha256']
 chunks=[json.loads(line) for line in (P/(label+'-RAW.jsonl')).read_text().splitlines()]
 wire=b''.join(base64.b64decode(x['base64'],validate=True) for x in chunks)
 events=[line[6:].strip() for line in wire.splitlines() if line.startswith(b'data: ')]
 assert events.count(b'[DONE]')==1
 parsed=[json.loads(x) for x in events if x!=b'[DONE]']
 assert any(x.get('usage')==row['usage'] for x in parsed)
 assert all(x['model']=='mimo-v2.6-pro-rl' and x['id']==row['response_id'] and x['system_fingerprint']==alloc['props']['build_info'] for x in parsed)
 assert ''.join(x.get('choices',[{}])[0].get('delta',{}).get('content') or '' for x in parsed if x.get('choices'))==row['content']
 assert ''.join(x.get('choices',[{}])[0].get('delta',{}).get('reasoning_content') or '' for x in parsed if x.get('choices'))==row['reasoning_content']
 actual_calls={}
 for event in parsed:
  for choice in event.get('choices',[]):
   for tool in choice.get('delta',{}).get('tool_calls',[]):
    call=actual_calls.setdefault(tool['index'],{'id':'','type':'','function':{'name':'','arguments':''}})
    for key in ('id','type'):
     if key in tool: call[key]=tool[key]
    for key in ('name','arguments'):
     if key in tool.get('function',{}):call['function'][key]+=tool['function'][key]
 assert [actual_calls[k] for k in sorted(actual_calls)]==row['tool_calls']
 assert [ch['finish_reason'] for event in parsed for ch in event.get('choices',[]) if ch.get('finish_reason') is not None]==[row['finish_reason']]
 assert row['native_settlement']['is_processing'] is False
 assert rows[label+'-BODY-SENT.json']['request_sha256']==row['request_sha256']
 assert row['usage']['total_tokens']==row['usage']['prompt_tokens']+row['usage']['completion_tokens']
 assert row['native_settlement']['monotonic_seconds']>=row['drained_monotonic_seconds']>=row['done_monotonic_seconds']>=row['last_output_monotonic_seconds']>=row['first_output_monotonic_seconds']
 summaries[label]={k:row[k] for k in ('usage','expected_input_tokens','output_budget','finish_reason','correctness','done','full_http_drain','owned_stream_disposition','native_settlement','request_sha256','request_sent_utc','drained_utc','native_timings','ttft_seconds','total_seconds','first_output_utc','last_output_utc')}
 summaries[label]['input_processing_seconds']=row['native_timings']['prompt_ms']/1000
 summaries[label]['output_generation_seconds']=row['native_timings']['predicted_ms']/1000
assert rows['SHORT-TEXT.json']['content'].strip()=='READY' and not rows['SHORT-TEXT.json']['tool_calls']
first,second=[rows[x+'.json'] for x in labels[1:]];req1,req2=[load(P/(x+'-REQUEST.json')) for x in labels[1:]]
assert req1['tools']==req2['tools'] and len(req1['tools'])==17
assert digest(json.dumps(req1['tools'],separators=(',',':'),ensure_ascii=False).encode())==native['tools_sha256']=='80e7a1e12e073ac57638e86638cf571158711ff821c96605135627777ce44e8c'
assert native['fixture_sha256']=='2fb03cef2e700b304f8eea538a5ef8df300afc53bb0a94241bc754c17679ef78'
assert req1['max_tokens']==req2['max_tokens']==65536 and first['finish_reason']=='tool_calls' and len(first['tool_calls'])==1
call=first['tool_calls'][0];assert call['type']=='function' and call['function']['name']=='read' and call['id']==native['actual_tool_call_id']
read_path='/data/logs/H019-20260928/worker1-short/FINAL17-READ.txt'
assert json.loads(call['function']['arguments'])=={'path':read_path}
read_text=receipts['FINAL17-READ.txt']['raw'];assert read_text=='A=2\nB=3\nMARKER=H016_R9_REAL_READ_20260927\n' and digest(read_text.encode())==native['actual_read_sha256']
expected=copy.deepcopy(req1);expected['messages'].extend([{'role':'assistant','content':first['content'] or None,'reasoning_content':first['reasoning_content'],'tool_calls':first['tool_calls']},{'role':'tool','tool_call_id':call['id'],'content':read_text}]);assert req2==expected
assert second['finish_reason']=='stop' and not second['tool_calls'] and second['content'].strip()=='5 H016_R9_REAL_READ_20260927'
strict=[t['function'].get('strict') for t in req1['tools']];assert all(x is None or type(x) is bool for x in strict)
final=col['final_read'];assert final['state']['status']=='RUNNING' and final['state']['native']==st['native'] and final['state']['launch_id']==st['launch_id']
assert native['actual_input_tokens']==[first['usage']['prompt_tokens'],second['usage']['prompt_tokens']]
assert native['actual_completion_tokens']==[first['usage']['completion_tokens'],second['usage']['completion_tokens']]
assert native['request_sha256']==[first['request_sha256'],second['request_sha256']]
assert native['output_ceiling_each_turn']==65536
assert final['actual_usable_context']==final['private_usable_context']==950000 and final['native_ready_predicate'] is True
r9=R/'reports/h016-production-prep16-20260927/QUALIFICATION-R9.json';assert sha(r9)=='f03120cf00356e0d1992129aac81ae37959677519f9cc2c463ab6f98a0867455'
occupied=max(v['usage']['prompt_tokens'] for v in summaries.values());output=max(v['usage']['completion_tokens'] for v in summaries.values())
mapping={'status':'PASS_CURRENT_950K_NATIVE_ORDINARY','utc':col['utc'],'historical_static_lineage':{'path':str(r9.relative_to(R)),'sha256':sha(r9),'scope':'Immutable artifact/runtime/image/tensor/tokenizer/admission arithmetic lineage. R9 usable1000000 and4K/16K are historical; no current ladder claim.'},'production_identity':identity,'manifest_sha256':st['manifest_sha256'],'capacity':{'published':1048576,'configured':950000,'allocated':950000,'occupiedTested':occupied},'requests':summaries,'full17':native,'real_read_continuation':{'verified':True,'path':read_path,'sha256':native['actual_read_sha256'],'actual_call_id':call['id'],'actual_result_in_second_body':True,'actual_sum_marker_correct':True},'strict_nested_scope':{'status':'ACCEPTANCE_AND_PRESERVATION','strict_values':strict,'strict_true_enforcement':'NOT_TESTED','proof':'Pinned unchanged full17 fixture, historical strict:false/nested preservation lineage, current actual read/result continuation.'},'digest_scopes':{'runtimeBuildSha256':'Immutable Docker image digest; no fresh binary or in-memory hash.','loadedTensorMetadataSha256':'Archived verified GGUF-INVENTORY.json; no fresh native tensor attestation.','loadedTokenizerSha256':'Whole verified5948832-byte tokenizer/template carrier shard00001,tensor_count0; not extracted tokenizer digest.','loadedTemplateSha256':'Effective chat_template string observed in current props.','artifactBytes':'Historical all13 verified shards; no new rehash.'},'current_receipts':{n:{'sha256':v['sha256'],'remote_path':v['remote_path']} for n,v in receipts.items()},'collection_sha256':sha(collection),'application_sova':'NOT_TESTED_BY_THIS_TASK','LAST':'NOT_DISPATCHED_IN_QUALIFY03','occupied950K':'NOT_TESTED','current4K16K64K':'NOT_TESTED','settlement':'Own terminal SSE/usage/DONE/full HTTP drain then authenticated idle for each request; no later caller used as settlement.'}
binding={'selection':st['selection'],'production_identity':identity,'source_baseline':'f855f408a203a055cf23cf10d2c7c2ddd73f53a4','owner_sha256':rows['AUTHORITY.json']['source_sha256']['/data/services/mimo-h016-20260927/source/owner.py'],'manifest_raw_sha256':'743edc0f8fa343f8c05efe7a307cf5a6eb4396b09ba9ed378230fe9d62e1e0a0','manifest_semantic_sha256':st['manifest_sha256'],'policy_sha256':'cf5581289148f419f7056165e244ade8d696542cbb24c045b7d3533f873c46d1','authority_sha256':receipts['AUTHORITY.json']['sha256'],'client_closure_sha256':sha(R/'scripts/h019/client-closure.json')}
assert binding['owner_sha256']=='e5fda2057168c29b1fe6e53da727b337beaf5634ddbc7dbb3d4f2c46602bcd53'
assert binding['manifest_semantic_sha256']=='d8bd9326118458774ac2b585e6029faa2a607d195001d85e14c5d238f6c05be4'
assert rows['AUTHORITY.json']['source_sha256']==load(R/'scripts/h019/client-closure.json')
mapping['deployment_binding']=binding
mapping['source_sha256']=rows['AUTHORITY.json']['source_sha256']
mapping['checks_scope']={'artifactBytes_nativePrecision_textArrayRendering_arithmeticFixtures':'Retained unchanged H016 R9 static lineage; artifact stat/source/image identity verified by current owner preflight, no new shard hashing or build.','allocation_reserves_templateAndTokenizer_shortNativeCountUsageMatch_generationCeiling_reasoningAndTools_singleOwner':'Current H019 readiness, authentic three completed requests, full17 continuation, and idle settlement.'}
write(T/'EVIDENCE-MAPPING.json',mapping)
q=load(r9);q['kind']='H019_CURRENT_950K_NATIVE_ORDINARY_QUALIFIED_WITH_ARCHIVED_STATIC_LINEAGE';q['capacity']=mapping['capacity'];q['qualification']['identity'].update(serverInstance=st['native']['container_id'],serverGeneration=st['launch_id'],actualSlotContext=950000);q['qualification']['evidenceSha256']=sha(T/'EVIDENCE-MAPPING.json');q['qualification']['checks']['generationCeiling']['largestCompletedOutputTokens']=output
q['deploymentBinding']=binding
q['scope']={'sova':'NOT_TESTED_BY_THIS_TASK','near950KInput':'NOT_TESTED','maximumOutputCeiling':65536,'largestCompletedOutputTokens':output,'lineageAndDigestScopes':'See evidenceSha256 mapping; no fresh tensor attestation or shard rehash.'}
assert q['qualification']['identity']['runtimeBuildSha256']==st['native']['image_id'].split(':',1)[1]
assert q['nativePins']['buildInfo']==alloc['props']['build_info'] and q['nativePins']['modelPath']==alloc['props']['model_path']
assert q['nativePins']['chatTemplateSha256']==digest(alloc['props']['chat_template'].encode())
assert 0<occupied<950000 and len(json.dumps(q).encode())<=65536
# Candidate file precedes schema validation; only successful validation publishes qualifier.
write(T/'QUALIFICATION-950K.CANDIDATE.json',q)
run=subprocess.run(['node','--experimental-transform-types',str(P/'schema/validate.mjs'),str(T/'QUALIFICATION-950K.CANDIDATE.json'),str(P/'ALLOCATION.json')],text=True,capture_output=True)
(P/'VALIDATOR.stdout').write_text(run.stdout);(P/'VALIDATOR.stderr').write_text(run.stderr);assert run.returncode==0,(run.returncode,run.stderr)
validation=json.loads(run.stdout);write(T/'SCHEMA-VALIDATION.json',validation);(T/'QUALIFICATION-950K.CANDIDATE.json').rename(T/'QUALIFICATION-950K.json')
for name in ('ALLOCATION.json','FINAL17-QUALIFICATION.json'):
 (T/name).write_bytes((P/name).read_bytes());(T/name).chmod(0o600)
root={'status':'READY_RECEIPT','qualified_json':str(T/'QUALIFICATION-950K.json'),'qualified_json_sha256':sha(T/'QUALIFICATION-950K.json'),'evidence_mapping':str(T/'EVIDENCE-MAPPING.json'),'evidence_mapping_sha256':sha(T/'EVIDENCE-MAPPING.json'),'allocation_remote_path':receipts['ALLOCATION.json']['remote_path'],'allocation_sha256':receipts['ALLOCATION.json']['sha256'],'deployment_binding':binding,'native_qualification_remote_path':receipts['FINAL17-QUALIFICATION.json']['remote_path'],'native_qualification_sha256':receipts['FINAL17-QUALIFICATION.json']['sha256'],'raw_collection_path':str(collection),'raw_collection_sha256':sha(collection),'capacity':q['capacity'],'production_identity':identity,'validator':validation,'client_status':client['status'],'finished_utc':client['finished_utc'],'own_request_settled':True,'Sova':'NOT_TESTED_BY_THIS_TASK','LAST':'NOT_DISPATCHED_IN_QUALIFY03'}
write(T/'ROOT-QUALIFICATION.json',root);(T/'QUALIFICATION-950K.sha256').write_text(sha(T/'QUALIFICATION-950K.json')+'  QUALIFICATION-950K.json\n');print(json.dumps(root),flush=True)
