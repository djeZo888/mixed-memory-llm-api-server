#!/usr/bin/env python3
"""Authorized serial two-turn native qualification; real allowlisted read on Mac."""
import argparse,base64,copy,datetime,hashlib,json,pathlib,subprocess,sys
P=pathlib.Path(__file__).resolve().parents[3].parent/'private/profile9'
T=P.parent.parent
ROSTER_SHA='80e7a1e12e073ac57638e86638cf571158711ff821c96605135627777ce44e8c'
def canonical(x):return json.dumps(x,separators=(',',':'),ensure_ascii=False).encode()
def write(n,v):(P/n).write_text(json.dumps(v,indent=2)+'\n')
def run(payload,label):
 src=pathlib.Path(__file__).with_name('umc512_client.py').read_text()
 old='payload=body(TEXT,thinking=False,output=512);payload[\'seed\']=270927'
 assert old in src
 src=src.replace(old,'payload=json.loads(base64.b64decode('+repr(base64.b64encode(canonical(payload)).decode())+'))')
 src=src.replace("time.time()+240","time.time()+300").replace("deadline-time.time()>=180 and expected+512<=131071","deadline-time.time()>=120 and expected+65536<=131071")
 src=src.replace("fixture=TEXT,payload=payload,","payload=payload,").replace("'label':'HOST-UMC512'","'label':"+repr(label))
 src=src.replace("output_ceiling=512","output_ceiling=65536").replace("usage['completion_tokens']<=512","usage['completion_tokens']<=65536").replace("correctness='UNSCORED_LENGTH_THROUGHPUT'","correctness='PENDING_TWO_TURN_CHECK'")
 compile(src,label,'exec');(P/(label+'-client.py')).write_text(src)
 proc=subprocess.Popen(['ssh','ai-vm','sudo -n python3 -B - --run-authorized'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(P/(label+'.stderr')).open('wb'))
 proc.stdin.write(src.encode());proc.stdin.close();receipt=None
 with (P/'TOOL17-PROGRESS.jsonl').open('a',buffering=1) as f:
  for line in proc.stdout:
   e=json.loads(line);e['label']=label
   if e['event']=='RECEIPT':
    receipt=e['receipt'];write(label+'.json',receipt);(P/(label+'.sse')).write_bytes(b''.join(base64.b64decode(c['base64']) for c in receipt['raw_chunks']));continue
   f.write(json.dumps(e)+'\n')
   public={k:v for k,v in e.items() if k not in ['payload','fixture']}
   with (T/'ROOT-NOTICE.md').open('a') as n:n.write('\n## '+label+' '+e['event']+'\n\n```json\n'+json.dumps(public,indent=2)+'\n```\n')
   st=json.loads((T/'STATUS.json').read_text());st['tool17_progress']=public;write_status=T/'STATUS.json';write_status.write_text(json.dumps(st,indent=2)+'\n')
   print(json.dumps(public),flush=True)
 rc=proc.wait();assert rc==0 and receipt and receipt['status']=='TRANSPORT_COMPLETE' and receipt['full_http_drain'] and receipt['done'] and receipt['slot_idle_after'], 'Native request did not settle normally; no continuation'
 return receipt

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run-authorized',action='store_true');ap.add_argument('--fixture',required=True);args=ap.parse_args()
 f=json.loads(pathlib.Path(args.fixture).read_text());base=copy.deepcopy(f['canonicalBody']);assert hashlib.sha256(canonical(base['tools'])).hexdigest()==ROSTER_SHA and len(base['tools'])==17
 assert base['max_tokens']==65536 and base['chat_template_kwargs']=={'enable_thinking':True} and base['tool_choice']=='auto' and base['parallel_tool_calls'] is False
 path=P/'tool-read-A2B3.txt';assert not path.exists() or path.read_text()=='A=2\nB=3\nMARKER=R7-HOST-270927-A2B3\n'
 path.write_text('A=2\nB=3\nMARKER=R7-HOST-270927-A2B3\n')
 base['messages']=[{'role':'developer','content':'Use the read tool exactly once for the user-specified file. Use only that read result to calculate A+B and report MARKER. Do not call other tools. After receiving the real tool result, give only a compact JSON object with sum and marker.'},{'role':'user','content':[{'type':'text','text':'Read '+str(path)+' using read with path, then return A+B and the exact MARKER. Keep the final answer brief.'}]}]
 write('TOOL17-TURN1-PAYLOAD.json',base)
 plan={'tools_sha256':ROSTER_SHA,'tools_count':17,'turn1_payload_sha256':hashlib.sha256(canonical(base)).hexdigest(),'fixture_source':str(pathlib.Path(args.fixture).resolve()),'allowlisted_file':str(path),'max_tokens_both':65536,'thinking_both':True,'deadline':'each min(start+300s,14:57 UTC); owner15:35 unchanged','no_concurrent_inference':True,'scope':'Native backend tool protocol only, not actual app or MiniMax delegation'};write('TOOL17-PLAN.json',plan);print(json.dumps(plan),flush=True)
 if not args.run_authorized:return
 u=json.loads((P/'HOST-UMC512.json').read_text());assert u['status']=='TRANSPORT_COMPLETE' and u['done'] and u['full_http_drain'] and u['slot_idle_after']
 r1=run(base,'TOOL17-TURN1');calls=r1['tool_calls'];assert r1['finish_reason']=='tool_calls' and len(calls)==1
 call=calls[0];assert call['id'] and call['type']=='function' and call['function']['name']=='read'
 arguments=json.loads(call['function']['arguments']);assert arguments=={'path':str(path)}
 assert path.resolve()==path and path.is_file() and not path.is_symlink();raw=path.read_bytes();assert len(raw)<=256
 result='\n'.join(f'{i}: {s}' for i,s in enumerate(raw.decode().splitlines(),1))
 write('TOOL17-ACTUAL-READ.json',{'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'call':call,'arguments':arguments,'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'result':result,'actual_file_read':True})
 b2=copy.deepcopy(base);b2['messages'] += [{'role':'assistant','content':r1['content'],'reasoning_content':r1['reasoning_content'],'tool_calls':calls},{'role':'tool','content':result,'tool_call_id':call['id']}]
 assert canonical(b2['tools'])==canonical(base['tools']);write('TOOL17-TURN2-PAYLOAD.json',b2);r2=run(b2,'TOOL17-TURN2')
 answer=r2['content'].strip();answer=answer.removeprefix('```json').removeprefix('```').removesuffix('```').strip();j=json.loads(answer);assert r2['finish_reason']=='stop' and not r2['tool_calls'] and j=={'sum':5,'marker':'R7-HOST-270927-A2B3'}
 summary={'status':'PASS_NATIVE_TWO_TURN_TOOL_PROTOCOL','tools_sha256':ROSTER_SHA,'tools_count':17,'max_tokens_both':65536,'thinking_both':True,'actual_read':True,'tool_call_id':call['id'],'turn1_usage':r1['usage'],'turn2_usage':r2['usage'],'turn1_payload_sha256':r1['request_sha256'],'turn2_payload_sha256':r2['request_sha256'],'final':j,'count_usage_parity_both':True,'done_full_drain_idle_both':True,'application_qualified':False,'minimax_delegation_qualified':False};write('TOOL17-RESULT.json',summary)
 with (T/'ROOT-NOTICE.md').open('a') as f:f.write('\n## TOOL17 RESULT\n\n```json\n'+json.dumps(summary,indent=2)+'\n```\n')
 st=json.loads((T/'STATUS.json').read_text());st['tool17_result']=summary;(T/'STATUS.json').write_text(json.dumps(st,indent=2)+'\n');print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
