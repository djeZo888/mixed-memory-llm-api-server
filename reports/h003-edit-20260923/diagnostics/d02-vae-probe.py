"""D02: one native VAE encode/decode, never a pipeline/warm/edit retry."""
import hashlib,io,json,pathlib,time,sys,traceback
import numpy as np
import torch
from PIL import Image
from safetensors.torch import load_file
from sglang.multimodal_gen.configs.models.vaes.qwenimage21 import QwenImage21VAEConfig
from sglang.multimodal_gen.configs.pipeline_configs.qwen_image21 import QwenImage21PipelineConfig
from sglang.multimodal_gen.runtime.models.vaes.autoencoder_kl_qwenimage21 import AutoencoderKLQwenImage21
from sglang.multimodal_gen.runtime.loader.component_loaders.vae_loader import _consume_vae_checkpoint_arch_metadata
from sglang.multimodal_gen.runtime.loader.utils import load_model_state_dict
from sglang.multimodal_gen.runtime.pipelines_core.stages.decoding import scale_and_shift_latents
from types import SimpleNamespace
out=pathlib.Path(__file__).parent
m={'id':'D02','attempts':1,'encode_completed':0,'decode_completed':0,'denoising_steps_completed':0,'outputs':[]}
def save(): (out/'metrics.json').write_text(json.dumps(m,indent=2)+'\n')
def stats(x):
 f=x.float();return {'shape':list(x.shape),'dtype':str(x.dtype),'min':f.min().item(),'max':f.max().item(),'mean':f.mean().item(),'std':f.std().item(),'finite':bool(f.isfinite().all())}
def png(name,im):
 p=out/name;im.save(p);raw=p.read_bytes();m['outputs'].append({'name':name,'sha256':hashlib.sha256(raw).hexdigest(),'mode':im.mode,'size':list(im.size)})
start=time.monotonic();save()
try:
 raw=(out/'input.png').read_bytes();assert hashlib.sha256(raw).hexdigest()=='9756c58b989a7656162e8777bb98fcd20671c58a9c79ae4c2d1744a63fb0d575'
 im=Image.open(io.BytesIO(raw));im.load();assert im.mode=='RGB' and im.size==(1024,1024) and not im.getexif()
 rgba=im.convert('RGBA').resize((1024,1024),Image.Resampling.LANCZOS);assert rgba.convert('RGB').tobytes()==im.tobytes();png('conditioning.png',rgba)
 cfg=QwenImage21VAEConfig();cfg.use_tiling=False
 checkpoint=json.loads(pathlib.Path('/models/vae/config.json').read_text())
 for k,v in checkpoint.items():
  if not k.startswith('_') and hasattr(cfg.arch_config,k):assert json.loads(json.dumps(getattr(cfg.arch_config,k)))==v,(k,'config mismatch')
 # Create the same native class/dtype, strict-load exact local checkpoint.
 old=torch.get_default_dtype();torch.set_default_dtype(torch.bfloat16)
 try:vae=AutoencoderKLQwenImage21(cfg).eval()
 finally:torch.set_default_dtype(old)
 files=sorted(pathlib.Path('/models/vae').glob('*.safetensors'));assert len(files)==1
 state=load_file(str(files[0]),device='cpu');m['checkpoint_file']=str(files[0]);m['metadata_consumed']=list(_consume_vae_checkpoint_arch_metadata(state,cfg,vae.state_dict()))
 load_model_state_dict(vae,state,strict=True,assign=False);del state
 free,total=torch.cuda.mem_get_info();cap=min(10*1024**3,free-int(total*.05)-1024**3);assert cap>4*1024**3
 torch.cuda.set_per_process_memory_fraction(cap/total);m['diagnostic_allocator_cap_bytes']=cap
 vae=vae.to('cuda');torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize();m['load_seconds']=time.monotonic()-start
 with torch.inference_mode():
  pixels=torch.frombuffer(bytearray(rgba.tobytes()),dtype=torch.uint8).reshape(1024,1024,4)
  pixels=pixels[None].permute(0,3,1,2).unsqueeze(2).float()/255.0
  pixels=(2*pixels-1).to(device='cuda',dtype=torch.bfloat16);m['pixels']=stats(pixels)
  t=time.monotonic();latent=vae.encode(pixels).mode();torch.cuda.synchronize();m['encode_seconds']=time.monotonic()-t;m['encode_completed']=1;m['latent']=stats(latent);save()
  ac=cfg.arch_config;mean=latent.new_tensor(ac.latents_mean).view(1,64,1,1,1);std=latent.new_tensor(ac.latents_std).view(1,64,1,1,1)
  condition=((latent-mean)/std).flatten(2).transpose(1,2);m['condition']=stats(condition)
  target=condition.transpose(1,2).reshape(1,64,1,64,64)
  pipeline=QwenImage21PipelineConfig();pipeline.vae_config=cfg
  decoded_latent=scale_and_shift_latents(target,SimpleNamespace(pipeline_config=pipeline),vae)
  m['inverse_normalization_max_abs_error']=(decoded_latent-latent).abs().max().item()
  t=time.monotonic();decoded=vae.decode(decoded_latent);torch.cuda.synchronize();m['decode_seconds']=time.monotonic()-t;m['decode_completed']=1;m['decoded']=stats(decoded)
  # Native decoder range mapping; PNG quantization is CPU codec work only.
  mapped=(decoded/2+.5).clamp(0,1)
  array=(mapped[0,:,0].permute(1,2,0).float().cpu().numpy()*255).round().astype(np.uint8)
  result=Image.fromarray(array,'RGBA');png('raw-reconstruction.png',result);png('delivered-rgb.png',result.convert('RGB'))
  delta=np.asarray(result.convert('RGB')).astype(float)-np.asarray(im).astype(float)
  m['rgb_mae']=float(np.abs(delta).mean());m['rgb_rmse']=float(np.sqrt((delta*delta).mean()))
 m['allocator']={'max_allocated':torch.cuda.max_memory_allocated(),'max_reserved':torch.cuda.max_memory_reserved()};m['status']='completed_visual_pending'
except BaseException as e:
 m.update(status='failed',error_type=type(e).__name__,error=str(e),traceback=traceback.format_exc());raise
finally:m['total_seconds']=time.monotonic()-start;save()
