# Explicit protected import bootstrap for genuine Python -I entrypoints.
if __name__ == '__main__':
 import hashlib as _h, importlib.util as _iu, json as _j, os as _o, stat as _s
 from pathlib import Path as _P
 _root = _P(__file__).absolute().parents[3]
 _loader = _root/'scripts/h044/vision_runtime/trusted_imports.py'
 _manifest = (_root/'SOURCE-MANIFEST.json') if str(_root).startswith('/opt/') else (_root.parent/'output/SOURCE-MANIFEST.json')
 _uid = 0 if str(_root).startswith('/opt/') else _o.geteuid()
 def _protected(p):
  if str(p)!=_o.path.realpath(p):raise ValueError('bootstrap_symlink')
  for a in [p,*p.parents]:
   z=a.lstat()
   if z.st_uid not in (0,_uid) or z.st_mode&0o022:raise ValueError('bootstrap_owner_mode')
  fd=_o.open(p,_o.O_RDONLY|_o.O_NOFOLLOW)
  try:
   z=_o.fstat(fd)
   if not _s.S_ISREG(z.st_mode) or z.st_uid!=_uid or z.st_nlink!=1 or z.st_size>1048576:raise ValueError('bootstrap_source')
   raw=_o.read(fd,1048577);q=_o.fstat(fd)
   if (z.st_dev,z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns)!=(q.st_dev,q.st_ino,q.st_size,q.st_mtime_ns,q.st_ctime_ns):raise ValueError('bootstrap_changed')
   return raw
  finally:_o.close(fd)
 _m=_j.loads(_protected(_manifest));_b=_protected(_loader);_record=_m['modules']['trusted_imports']
 if _record['path']!='scripts/h044/vision_runtime/trusted_imports.py' or _h.sha256(_b).hexdigest()!=_record['sha256'] or len(_b)!=_record['bytes']:raise ValueError('bootstrap_hash')
 _spec=_iu.spec_from_file_location('trusted_imports',_loader);_module=_iu.module_from_spec(_spec)
 import sys as _sys
 _sys.modules['trusted_imports']=_module;exec(compile(_b,str(_loader),'exec'),_module.__dict__)
 _module.install(_root,_m,_uid)

#!/usr/bin/env python3
"""Generated independently labelled small corpus; genuine outputs only after GO."""
import hashlib,http.client,json,os,re,struct,time,zlib
from pathlib import Path
import control
# Original deterministic 5x7 raster labels; no external/font/model dependency.
GLYPHS={'R':['11110','10001','10001','11110','10100','10010','10001'],'1':['00100','01100','00100','00100','00100','00100','01110'],'0':['01110','10001','10011','10101','11001','10001','01110'],'K':['10001','10010','10100','11000','10100','10010','10001'],'V':['10001','10001','10001','10001','10001','01010','00100'],'5':['11111','10000','10000','11110','00001','00001','11110'],' ':['00000']*7}
def fixture():
 literal='R1 10K 5V';scale=6;w=len(literal)*6*scale+24;h=7*scale+24;rows=[bytearray(b'\xff\xff\xff'*w) for _ in range(h)]
 for n,c in enumerate(literal):
  for y,row in enumerate(GLYPHS[c]):
   for x,p in enumerate(row):
    if p=='1':
     for yy in range(scale):
      for xx in range(scale):
       i=(12+n*6*scale+x*scale+xx)*3;rows[12+y*scale+yy][i:i+3]=b'\0\0\0'
 def chunk(k,b):return struct.pack('>I',len(b))+k+b+struct.pack('>I',zlib.crc32(k+b)&0xffffffff)
 png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(b'\0'+r for r in rows)))+chunk(b'IEND',b'')
 return png,{'schema':'h043-original-labelled-corpus-v1','fixtureId':'original-raster-literal01','width':w,'height':h,'pixelSha256':control.sha(b''.join(rows)),'pngSha256':control.sha(png),'expectedLiteral':literal,'interpretationExpectedFacts':['visible label R1','visible value 10K','visible value 5V'],'predictionStatus':'NOT_RUN','fixtureKind':'ORIGINAL_GENERATED_INPUT_NOT_MODEL_OUTPUT','crop':{'id':'literal-row','page':1,'x':0,'y':0,'width':w,'height':h}}
def request(method,path,body,key,deadline):
 control.current_authority('inference')
 if not re.fullmatch(r'/v1/(?:models|technical-vision/(?:capabilities|jobs|requests/[A-Za-z0-9_-]+/status|jobs/[A-Za-z0-9_-]+/(?:status|cancel)))',path):raise control.Refused('fixed_route')
 c=http.client.HTTPConnection('127.0.0.1',18193,timeout=min(10,max(.01,deadline-time.monotonic())))
 try:
  c.request(method,path,body=body,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','Content-Length':str(len(body)),'Connection':'close'});r=c.getresponse();raw=r.read(1048577)
  if len(raw)>1048576:raise control.Refused('unknown_response_cap')
  return {'httpStatus':r.status,'rawBytes':raw,'rawSHA256':control.sha(raw),'completeObserved':r.isclosed(),'nativeDrainProven':False}
 finally:c.close()
def exact_raw_checkpoint(path,result,source,crop,model,residency_proof):
 control.current_authority('inference')
 if not residency_proof or residency_proof.get('configuredIdentityOnly') is not False:raise control.Refused('actual_residency_required')
 control.exclusive(path,{'rawResponseHex':result['rawBytes'].hex(),'rawSHA256':result['rawSHA256'],'source':source,'crop':crop,'modelAlias':model,'residencyProof':residency_proof,'fixtureNotPrediction':'original pixels + genuine returned bytes','settlement':'COMPLETE_RESPONSE_ONLY_NOT_ENGINE_SHUTDOWN'})
if __name__=='__main__':
 png,corpus=fixture();print(json.dumps(corpus,indent=2))

def bounded_call(method,host,port,path,payload,typ,key,deadline,rid=None):
 """One entire monotonic wall timer covers connect, write, headers and full body."""
 import socket,threading
 if time.monotonic()>=deadline:raise TimeoutError('entire_wall_deadline')
 c=http.client.HTTPConnection(host,port,timeout=min(10,deadline-time.monotonic()));expired=threading.Event();sock=None
 def expire():
  expired.set()
  if sock is not None:
   try:sock.shutdown(socket.SHUT_RDWR)
   except OSError:pass
  c.close()
 timer=threading.Timer(deadline-time.monotonic(),expire);timer.daemon=True;timer.start()
 try:
  c.connect();sock=c.sock
  if expired.is_set():raise TimeoutError('entire_wall_deadline')
  headers={'Authorization':'Bearer '+key,'Content-Type':typ,'Content-Length':str(len(payload)),'Connection':'close','Accept':'application/json'}
  if rid:headers['Idempotency-Key']=rid
  c.request(method,path,payload,headers);r=c.getresponse();chunks=[];size=0
  while True:
   if expired.is_set() or time.monotonic()>=deadline:raise TimeoutError('entire_wall_deadline')
   b=r.read(8192)
   if not b:break
   size+=len(b)
   if size>1048576:raise control.Refused('response_cap')
   chunks.append(b)
  raw=b''.join(chunks)
  if expired.is_set() or time.monotonic()>=deadline or not r.isclosed():raise TimeoutError('entire_wall_deadline')
  return r.status,raw,control.parse_proof(raw)
 finally:timer.cancel();c.close()


def health(graph,proof,deadline,credential):
 if proof.get('component')!='health' or proof.get('actualUid')!=1000:raise control.Refused('signed_uid_health_required')
 control.validate_graph(graph)
 # This validates both exact role addresses and their dedicated internal network
 # before reading a bearer key or making any request. No URL or DNS selection.
 origins=control.model_origins(graph)
 observations=[]
 while time.monotonic()<deadline:
  try:
   for role,model in (('interpretation','Qwen/Qwen3.5-9B'),('ocr','PaddlePaddle/PaddleOCR-VL-1.6')):
    host,port=origins[role][len('http://'):].split(':')
    status,raw,v=bounded_call('GET',host,int(port),'/v1/models',b'','application/json',credential(role),deadline)
    if status!=200 or model not in [x.get('id') for x in v.get('data',[])]:raise control.Refused('exact_model_health')
    observations.append({'role':role,'origin':origins[role],'rawHex':raw.hex(),'sha256':control.sha(raw),'model':model})
   for host in ('127.0.0.1','10.156.100.60'):
    status,raw,v=bounded_call('GET',host,18193,'/v1/technical-vision/capabilities',b'','application/json',credential('service'),deadline)
    if status!=200 or v.get('service')!={k:graph_service(graph)[k] for k in ('serviceId','generation','mode','interpreter','parser')} or not v.get('ready') or not v.get('admitting'):raise control.Refused('service_ingress_health')
    observations.append({'host':host,'rawHex':raw.hex(),'sha256':control.sha(raw)})
   return {'status':'HEALTHY','observations':observations,'proofSHA256':proof['proofSHA256'],'actualUid':os.geteuid()}
  except (OSError,TimeoutError,ValueError,http.client.HTTPException):
   if time.monotonic()>=deadline:break
   time.sleep(min(.2,deadline-time.monotonic()))
 return {'status':'HEALTH_TIMEOUT','observations':observations,'settled':False}


def graph_service(graph):
 from trusted_imports import protected_bytes
 return json.loads(protected_bytes(Path(graph['sourceRoot'])/'configs/vision/h043-candidate.json',0))['service']


def assess_response(current,corpus,identity,source,record,elapsed,wall_limit):
 failures=[]
 if elapsed>wall_limit:failures.append('TIMING_OVERRUN')
 if current.get('state')!='completed' or current.get('settled') is not True:failures.append('MODEL_RESPONSE_FAILED_OR_UNSETTLED')
 result=current.get('result',{})
 if result.get('service')!=identity or result.get('source')!=source:failures.append('SERVICE_INPUT_IDENTITY')
 texts=result.get('extraction',{}).get('text',[])
 if len(texts)!=1 or texts[0].get('exactText')!=corpus['expectedLiteral']:failures.append('EXPECTED_OCR_LITERAL_MISMATCH')
 description=result.get('description','')
 if not all(x in description for x in ('R1','10K','5V')):failures.append('INTERPRETATION_ATTRIBUTES_MISSING')
 if not any(x.get('id','').startswith('qwen-uncertainty-') and x.get('description') for x in result.get('uncertainties',[])) or result.get('electricalNetReconstruction')!='not_qualified':failures.append('INTERPRETATION_UNCERTAINTY_MISSING')
 evidence=record.get('backendEvidence',[]);responses=[x for x in evidence if x.get('kind')=='model_response']
 if len(responses)!=2 or {x.get('role') for x in responses}!={'interpretation','ocr'}:failures.append('RAW_MODEL_PROVENANCE_MISSING')
 for x in responses:
  try:
   raw=bytes.fromhex(x.get('rawResponseHex',''))
   if not raw or control.sha(raw)!=x.get('responseSha256') or control.parse_proof(raw)!=x.get('response'):failures.append('RAW_BYTE_HASH_PROVENANCE')
  except (ValueError,TypeError):failures.append('RAW_BYTE_HASH_PROVENANCE')
  role=x['role'];model=identity['interpreter' if role=='interpretation' else 'parser']
  if x.get('inputPngSHA256')!=x.get('viewSha256') or x.get('model')!=model['model'] or x.get('revision')!=model['revision'] or x.get('sourceSha256')!=source['sha256'] or not isinstance(x.get('response'),dict) or not re.fullmatch('[a-f0-9]{64}',x.get('responseSha256','')):failures.append('MODEL_REVISION_RAW_INPUT_PROVENANCE')
 return {'status':'RESPONSE_ASSERTIONS_FAILED' if failures else 'RESPONSE_ASSERTIONS_PASS','failures':failures,'fixtureQualification':'SOURCE_ONLY_NEVER_GPU_ACCURACY_PASS','rawModelEvidence':responses,'expectedLiteral':corpus['expectedLiteral'],'elapsedSeconds':elapsed,'nativeEngineDrained':False}


def poll_job(call,owner,request_id,deadline,record,clock=time.monotonic,pause=time.sleep):
 observations=0
 while clock()<deadline:
  status,raw,current=call('/v1/technical-vision/requests/'+request_id+'/status',control.canonical({'schemaVersion':1,'owner':owner}));observations+=1;record(observations,status,raw)
  if status!=200:raise control.Refused('status_failure_no_retry')
  if current.get('state') in ('completed','failed','cancelled','interrupted'):return current,observations
  pause(min(.2,max(0,deadline-clock())))
 raise TimeoutError('entire_wall_deadline')


def service_job(graph,proof,deadline,key):
 # Executed ONLY by actual service UID, never root reading a UID1000 bearer leaf.
 if os.geteuid()!=1000 or proof.get('component')!='workload' or proof.get('actualUid')!=1000 or proof.get('identityOrigin')!='REVIEWED_SIGNED_ROOT_PROOF':raise control.Refused('authentic_uid_workload_boundary')
 start=time.monotonic();wall_limit=deadline-start
 png,corpus=fixture();s=graph_service(graph);identity={k:s[k] for k in ('serviceId','generation','mode','interpreter','parser')}
 request_id='private-'+__import__('secrets').token_hex(16);owner={'sessionId':'h044-private-vision','workspaceId':'h044-private-corpus','runId':'h044-v03-'+request_id}
 source={'reference':{'fileId':corpus['fixtureId']},'sha256':corpus['pngSha256'],'mediaType':'image/png','coordinateSpace':'oriented_page_pixels','pages':[{'page':1,'width':corpus['width'],'height':corpus['height'],'originalWidth':corpus['width'],'originalHeight':corpus['height'],'orientation':1}],'crops':[corpus['crop']]}
 metadata={'schemaVersion':1,'owner':owner,'requestId':request_id,'service':identity,'source':source,'question':'Describe visible labels conservatively, distinguishing uncertain interpretation from literal extraction.','pageImages':[{'page':1,'sha256':corpus['pngSha256'],'part':'page-1'}]}
 # Auxiliary evidence uses the existing UID1000 control storage; the job ledger
 # remains reserved for PrivateLedger records.
 ledger=Path(graph['runtime']['service']['ledger']);control_ledger=Path(graph['runtime']['service']['controlLedger'])
 control.exclusive(control_ledger/('request-'+request_id+'.evidence'),{'metadata':metadata,'corpus':corpus,'inputPngHex':png.hex(),'status':'PRE_DISPATCH','proofSHA256':proof['proofSHA256']})
 boundary='h044-private-'+request_id;meta=control.canonical(metadata);body=(('--'+boundary+'\r\nContent-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n').encode()+meta+('\r\n--'+boundary+'\r\nContent-Disposition: form-data; name="page-1"; filename="page-1.png"\r\nContent-Type: image/png\r\n\r\n').encode()+png+('\r\n--'+boundary+'--\r\n').encode())
 def call(path,payload,typ='application/json',rid=None):return bounded_call('POST','127.0.0.1',18193,path,payload,typ,key,deadline,rid)
 status,raw,job=call('/v1/technical-vision/jobs',body,'multipart/form-data; boundary='+boundary,request_id)
 control.exclusive(control_ledger/('admission-'+request_id+'.evidence'),{'status':status,'rawHex':raw.hex(),'rawSHA256':control.sha(raw),'requestId':request_id})
 if status not in (200,202):raise control.Refused('admission_failed_no_retry')
 status,dup,duplicate=call('/v1/technical-vision/jobs',body,'multipart/form-data; boundary='+boundary,request_id)
 if status!=200 or duplicate.get('jobId')!=job.get('jobId'):raise control.Refused('duplicate_identity_unknown')
 last_status_raw=[None]
 def record(n,status,raw):
  last_status_raw[0]=raw
  control.exclusive(control_ledger/('status-'+request_id+'-'+str(n)+'.evidence'),{'status':status,'rawHex':raw.hex(),'rawSHA256':control.sha(raw)})
 try:current,polls=poll_job(call,owner,request_id,deadline,record)
 except TimeoutError:return {'status':'TIMING_OVERRUN','settled':False,'requestId':request_id,'admission':'CLOSED_QUARANTINE','noRetry':True,'nativeEngineDrained':False}
 from vision_service_entrypoint import protected_read
 scope=control.sha(control.canonical([owner['workspaceId'],owner['sessionId'],owner['runId'],request_id]))
 record_raw=protected_read(ledger/(scope+'.json'),limit=51*1024*1024,secret=False)
 record_value=control.parse_proof(record_raw)
 if record_value.get('metadata')!=metadata or record_value.get('job')!=current or current.get('jobId')!=job.get('jobId'):raise control.Refused('original_service_ledger_identity_mismatch')
 assessment=assess_response(current,corpus,identity,source,record_value,time.monotonic()-start,wall_limit)
 return dict(assessment,requestId=request_id,jobId=current.get('jobId'),polls=polls,rawServiceResponseHex=last_status_raw[0].hex(),rawServiceResponseSHA256=control.sha(last_status_raw[0]),inputSHA256=corpus['pngSha256'],serviceIdentity=identity,rawRecordSHA256=control.sha(record_raw),rawRecordHex=record_raw.hex(),proofSHA256=proof['proofSHA256'])
