"""Verify approved writable cache paths as native UID; execute unchanged recipe once."""
import json,os,pathlib,runpy,time
assert os.getuid()==1000 and os.getgid()==1001
keys=['HOME','XDG_CACHE_HOME','HF_HOME','HF_HUB_CACHE','FLASHINFER_WORKSPACE_BASE','TMPDIR','TORCH_HOME','TORCH_EXTENSIONS_DIR','TORCHINDUCTOR_CACHE_DIR','TRITON_CACHE_DIR','CUDA_CACHE_PATH','SGLANG_DIFFUSION_CACHE_ROOT','SGLANG_DIFFUSION_CONFIG_ROOT']
checks={}
for key in keys:
 p=pathlib.Path(os.environ[key]);assert p.is_relative_to('/work')
 p.mkdir(parents=True,exist_ok=True)
 probe=p/('.reference-write-check-'+str(os.getpid()))
 fd=os.open(probe,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 try:os.write(fd,b'owned writable cache check');os.fsync(fd)
 finally:os.close(fd)
 probe.unlink();checks[key]={'path':str(p),'writable':True}
pathlib.Path('/work/cache-writeability.json').write_text(json.dumps({'uid':os.getuid(),'gid':os.getgid(),'checks':checks},indent=2)+'\n')
print(json.dumps({'cache_writeability':'PASS','uid':os.getuid()}),flush=True)
runpy.run_path('/reference/reference_edit.py',run_name='__main__')
