"""D06 exact D04 follow-up reference at seed44; original42 regression remains failed."""
import base64,hashlib,http.client,importlib.util,io,json,pathlib,time
from PIL import Image
out=pathlib.Path(__file__).parent
spec=importlib.util.spec_from_file_location('native','/runtime/native_request.py');n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n)
raw=(out/'input.png').read_bytes();assert hashlib.sha256(raw).hexdigest()=='c718b9feb9c7825cb66b69b69be5e87829b811fb536fcc109346c73533a281bb'
fields={'model':'qwen-image-2.1','prompt':'Change the blue teapot to green, keeping its shape, table, window, and lighting unchanged.','n':1,'size':'1024x1024','num_inference_steps':40,'guidance_scale':1.0,'true_cfg_scale':1.0,'seed':44,'generator_device':'cpu','output_format':'png','response_format':'b64_json','background':'opaque','enable_teacache':False,'perf_dump_path':str(out/'perf.json')}
(out/'request.json').write_text(json.dumps(fields,indent=2)+'\n')
body,ctype=n.multipart(fields,raw,'h003seed44')
m={'id':'D06','http_calls':0,'completed_outputs':0,'steps_completed':None,'status':'prepared'}
def save():(out/'metrics.json').write_text(json.dumps(m,indent=2)+'\n')
save();start=time.monotonic();conn=http.client.HTTPConnection('127.0.0.1',30007,timeout=820)
try:
 m.update(http_calls=1,status='submitted');save()
 conn.request('POST','/v1/images/edits',body=body,headers={'Content-Type':ctype,'Content-Length':str(len(body))})
 response=conn.getresponse();result=response.read(32*1024*1024+1);m['http_status']=response.status;m['latency_seconds']=time.monotonic()-start
 assert response.status==200 and len(result)<=32*1024*1024
 data=json.loads(result);assert len(data['data'])==1
 png=base64.b64decode(data['data'][0]['b64_json'],validate=True);im=Image.open(io.BytesIO(png));im.load();assert im.size==(1024,1024) and im.format=='PNG'
 (out/'raw-output.png').write_bytes(png)
 clean=Image.frombytes('RGB',im.size,im.convert('RGB').tobytes());clean.save(out/'delivered-rgb.png')
 m['outputs']=[{'name':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (out/'raw-output.png',out/'delivered-rgb.png')]
 m.update(status='completed_visual_pending',completed_outputs=1,raw_mode=im.mode,raw_extrema=im.getextrema(),size=list(im.size))
 if (out/'perf.json').exists():m['perf']=json.loads((out/'perf.json').read_text())
except BaseException as e:m.update(status='failed',error_type=type(e).__name__);raise
finally:conn.close();save()
