"""Exactly one authorized reference edit; no warmup, fallback, or retry."""
import collections,datetime,hashlib,inspect,io,json,os,pathlib,time,traceback
import torch,transformers,diffusers
from PIL import Image
from diffusers import QwenImage21Pipeline
from diffusers.models.attention_dispatch import attention_backend
OUT=pathlib.Path('/work');start=time.monotonic()
PROMPT='Change the red teapot to blue, keeping its shape, table, window, and lighting unchanged.'
metrics={'session_id':'01a0cc4b-c378-7880-b15f-0ca5886bc4a9','status':'starting','inference_calls':0,'torch':torch.__version__,'transformers':transformers.__version__,'diffusers':diffusers.__version__,'diffusers_revision':'8b3c707ebd3ec4881f4190cf42931da07eaf3b65','checkpoint_revision':'790c92633540aa0cb11d9abf19eb46d861714758','prompt':PROMPT,'prompt_sha256':hashlib.sha256(PROMPT.encode()).hexdigest(),'diffusers_attention':'native','generator':'CPU seed42'}
def save():
 metrics['updated_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 (OUT/'metrics.json').write_text(json.dumps(metrics,indent=2,default=str)+'\n')
 print(json.dumps({'status':metrics['status'],'inference_calls':metrics['inference_calls']}),flush=True)
def peak():
 return {'max_memory_allocated_bytes':torch.cuda.max_memory_allocated(),'max_memory_reserved_bytes':torch.cuda.max_memory_reserved(),'current_allocated_bytes':torch.cuda.memory_allocated(),'current_reserved_bytes':torch.cuda.memory_reserved()}
def component_stats(module):
 result=collections.Counter()
 for x in list(module.parameters())+list(module.buffers()):
  result[str(x.device)+'/'+str(x.dtype)]+=x.numel()*x.element_size()
  assert x.device.type=='cuda','component not resident on CUDA'
 return dict(result)
def attention_configs(config):
 result={}
 for name in ('','text_config','vision_config'):
  c=config if not name else getattr(config,name,None)
  if c is not None:result[name or 'root']={k:getattr(c,k,None) for k in ('_attn_implementation','_attn_implementation_internal')}
 return result
try:
 assert torch.__version__=='2.13.0+cu130' and transformers.__version__=='5.17.0'
 raw=pathlib.Path('/reference/normalized-reference.png').read_bytes()
 metrics['input_sha256']=hashlib.sha256(raw).hexdigest()
 assert metrics['input_sha256']=='9756c58b989a7656162e8777bb98fcd20671c58a9c79ae4c2d1744a63fb0d575'
 reference=Image.open(io.BytesIO(raw));reference.load()
 assert reference.mode=='RGB' and reference.size==(1024,1024)
 metrics['call_signature']=str(inspect.signature(QwenImage21Pipeline.__call__))
 metrics['call_defaults']={k:repr(v.default) for k,v in inspect.signature(QwenImage21Pipeline.__call__).parameters.items() if v.default is not inspect.Parameter.empty}
 assert 'guidance_scale' not in inspect.signature(QwenImage21Pipeline.__call__).parameters
 metrics['cuda_device_name']=torch.cuda.get_device_name(0)
 metrics['cuda_device_properties']=str(torch.cuda.get_device_properties(0))
 metrics['torch_sdpa_defaults']={'flash_sdp_enabled':torch.backends.cuda.flash_sdp_enabled(),'mem_efficient_sdp_enabled':torch.backends.cuda.mem_efficient_sdp_enabled(),'math_sdp_enabled':torch.backends.cuda.math_sdp_enabled(),'cudnn_sdp_enabled':torch.backends.cuda.cudnn_sdp_enabled(),'float32_matmul_precision':torch.get_float32_matmul_precision(),'cuda_matmul_allow_tf32':torch.backends.cuda.matmul.allow_tf32,'cudnn_allow_tf32':torch.backends.cudnn.allow_tf32}
 torch.cuda.synchronize();torch.cuda.reset_peak_memory_stats();load_start=time.monotonic()
 metrics['status']='loading';save()
 pipe=QwenImage21Pipeline.from_pretrained('/models',local_files_only=True,torch_dtype=torch.bfloat16).to('cuda')
 torch.cuda.synchronize();metrics['load_seconds']=time.monotonic()-load_start;metrics['load_allocator']=peak()
 metrics['components']={n:component_stats(getattr(pipe,n)) for n in ('text_encoder','transformer','vae')}
 metrics['transformers_attention']=attention_configs(pipe.text_encoder.config)
 metrics['attention_processors']=dict(collections.Counter(type(p).__name__ for p in pipe.transformer.attn_processors.values()))
 assert set(metrics['attention_processors'])=={'QwenImage21AttnProcessor'}
 assert all(v['_attn_implementation'] in ('sdpa','eager') for v in metrics['transformers_attention'].values())
 metrics['vae_use_tiling']=getattr(pipe.vae,'use_tiling',None)
 assert not metrics['vae_use_tiling']
 metrics['scheduler_config']=dict(pipe.scheduler.config)
 metrics['recipe']={'height':1024,'width':1024,'output_resolution':1024,'num_inference_steps':40,'true_cfg_scale':1.0,'negative_prompt':None,'sigmas':None,'latents':None,'num_images_per_prompt':1,'use_kv_cache':True,'output_type':'pil','return_dict':True,'generator_device':'cpu','seed':42}
 metrics['status']='inference';metrics['inference_calls']=1;save()
 torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize();infer_start=time.monotonic()
 with torch.inference_mode(),attention_backend('native'):
  comparison=pipe(image=reference,prompt=PROMPT,negative_prompt=None,true_cfg_scale=1.0,width=1024,height=1024,output_resolution=1024,num_inference_steps=40,num_images_per_prompt=1,generator=torch.Generator('cpu').manual_seed(42),sigmas=None,latents=None,use_kv_cache=True,output_type='pil',return_dict=True).images[0]
 torch.cuda.synchronize();metrics['inference_seconds']=time.monotonic()-infer_start;metrics['inference_allocator']=peak()
 metrics['scheduler_timesteps']=pipe.scheduler.timesteps.detach().cpu().tolist();metrics['scheduler_sigmas']=pipe.scheduler.sigmas.detach().cpu().tolist()
 comparison.save(OUT/'output.png');decoded=Image.open(OUT/'output.png');decoded.load()
 assert decoded.size==(1024,1024)
 metrics['output']={'sha256':hashlib.sha256((OUT/'output.png').read_bytes()).hexdigest(),'bytes':(OUT/'output.png').stat().st_size,'mode':decoded.mode,'size':list(decoded.size),'extrema':decoded.getextrema()}
 metrics['status']='COMPLETE_DECODED_VISUAL_REVIEW_PENDING';metrics['total_process_seconds']=time.monotonic()-start;save()
except BaseException as error:
 metrics['status']='FAILED';metrics['error_type']=type(error).__name__;metrics['error']=str(error);metrics['traceback']=traceback.format_exc()
 if torch.cuda.is_initialized():metrics['failure_allocator']=peak()
 save();raise
