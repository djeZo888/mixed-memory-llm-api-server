"""One bounded sequence, exact local Ada endpoint; all streams drain before parsing."""
import datetime,hashlib,http.client,json,os,subprocess,time
from pathlib import Path
BASE=Path('/data/services/qwen-ada200k-h028-20260929');LOG=Path('/data/logs/qwen-ada200k-h028-20260929');MODEL='qwen3.8-27b-ada200k'
os.umask(0o077)
key=Path('/data/services/secrets/llm-api-key').read_text();identity=json.loads((BASE/'state.json').read_text())['container']['id']
native_start=json.loads(subprocess.check_output(['docker','inspect',identity],text=True))[0]['State']['StartedAt']
boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
results=[]
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def get(path):
 c=http.client.HTTPConnection('127.0.0.1',30014,timeout=5);c.request('GET',path,headers={'Authorization':'Bearer '+key});r=c.getresponse();assert r.status==200;v=json.loads(r.read());c.close();return v
def save():
 (LOG/'qualification-results.json').write_text(json.dumps({'container_id':identity,'utc':now(),'results':results},indent=2)+'\n')
def request(name,body):
 assert now()<'2026-09-29T00:00:00+00:00'
 assert get('/v1/readiness')['ready']
 status=json.loads((BASE/'status.json').read_text());assert status['container_id']==identity and status['free_mib']>=status['total_mib']*.07
 raw=json.dumps(body).encode();(LOG/(name+'.request.json')).write_bytes(raw)
 c=http.client.HTTPConnection('127.0.0.1',30014,timeout=120);start=time.monotonic();deadline=start+120
 row={'name':name,'dispatch_utc':now(),'body_sha256':hashlib.sha256(raw).hexdigest(),'deadline_seconds':120,'http':None,'eof':False};results.append(row);save()
 try:
  c.request('POST','/v1/chat/completions',raw,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'});r=c.getresponse();row['http']=r.status
  lines=[]
  while True:
   if time.monotonic()>=deadline:raise TimeoutError('request_deadline')
   if c.sock:c.sock.settimeout(max(.1,deadline-time.monotonic()))
   line=r.readline()
   if not line:row['eof']=True;break
   lines.append([time.monotonic()-start,line.decode()])
  row['elapsed_seconds']=time.monotonic()-start;row['drain_utc']=now()
  (LOG/(name+'.stream.json')).write_text(json.dumps(lines))
  assert r.status==200
 finally:c.close();save()
 content='';calls={};first=None;last=None;done=False;usage=None;finish=None;ids=set()
 for elapsed,line in lines:
  if not line.startswith('data:'):continue
  data=line[5:].strip()
  if data=='[DONE]':done=True;continue
  event=json.loads(data);assert not event.get('error');ids.add(event.get('id'))
  if event.get('usage'):usage=event['usage']
  for choice in event.get('choices',[]):
   delta=choice.get('delta',{});text=delta.get('content') or '';content+=text
   if text or delta.get('tool_calls'):
    first=elapsed if first is None else first;last=elapsed
   if choice.get('finish_reason'):finish=choice['finish_reason']
   for call in delta.get('tool_calls') or []:
    x=calls.setdefault(call['index'],{'id':'','type':'function','function':{'name':'','arguments':''}})
    if call.get('id'):x['id']+=call['id']
    for k,v in (call.get('function') or {}).items():x['function'][k]+=v or ''
 row.update(done=done,usage=usage,finish_reason=finish,native_ids=sorted(i for i in ids if i),ttft_seconds=first,last_output_seconds=last,content=content,tool_calls=list(calls.values()))
 assert done and usage and row['eof'] and finish in ['stop','length','tool_calls']
 if first is not None and last>first:row['output_tokens_per_second']=(usage['completion_tokens']-1)/(last-first)
 row['native_after']={k:v for k,v in get('/get_server_info').items() if k in ['status','max_total_num_tokens','max_req_input_len','internal_states']}
 save();return row
try:
 info=get('/get_server_info');assert info['context_length']==info['max_total_tokens']==info['max_total_num_tokens']==200000
 assert info['kv_cache_dtype']=='bfloat16' and info['quantization']=='fp8' and info['port']==30014
 for case in json.loads((LOG/'requests.json').read_text()):
  row=request(case['name'],case['body']);row['retrieval_values_present']=all(v in row['content'] for v in case['scorer']['retrieval'].values());assert row['retrieval_values_present'];save()
 tool={'type':'function','function':{'name':'add','description':'Add two integers.','parameters':{'type':'object','properties':{'a':{'type':'integer'},'b':{'type':'integer'}},'required':['a','b'],'additionalProperties':False}}}
 messages=[{'role':'user','content':'Call add with a=2 and b=3. After the tool result, return only the number.'}]
 body={'model':MODEL,'messages':messages,'tools':[tool],'tool_choice':'auto','temperature':0,'max_tokens':128,'stream':True,'stream_options':{'include_usage':True},'reasoning_effort':'none'}
 first=request('tool_call',body);assert len(first['tool_calls'])==1
 call=first['tool_calls'][0];assert call['function']['name']=='add' and json.loads(call['function']['arguments'])=={'a':2,'b':3}
 messages+=[{'role':'assistant','content':first['content'] or None,'tool_calls':first['tool_calls']},{'role':'tool','tool_call_id':call['id'],'content':'5'}]
 body['tool_choice']='none';last=request('tool_continuation',body);assert last['content'].strip()=='5'
 q={'status':'PASS','container_id':identity,'boot_id':boot_id,'docker_started_at':native_start,'context_tokens':200000,'utc':now(),'occupied_input_tokens_max':max(x['usage']['prompt_tokens'] for x in results),'results_sha256':hashlib.sha256((LOG/'qualification-results.json').read_bytes()).hexdigest()}
 (BASE/'qualification.json').write_text(json.dumps(q)+'\n');print(json.dumps(q))
except BaseException as e:
 (LOG/'qualification-error.json').write_text(json.dumps({'utc':now(),'type':type(e).__name__,'error':str(e),'container_id':identity})+'\n')
 # Accepted but undrained transport is uncertain: stop only the exact current owner.
 if results and not results[-1].get('eof'):
  subprocess.run(['python3','-I','-B',str(BASE/'source/ada_owner.py'),'stop'],timeout=45,check=True)
 raise
