"""A single brief, new-UUID-only transfer using the installed CUDA runtime."""
import datetime,json,subprocess,time
import torch
GPU='GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf'
assert torch.cuda.device_count()==1
props=torch.cuda.get_device_properties(0)
assert str(props.uuid)==GPU.removeprefix('GPU-') or str(props.uuid)==GPU
assert (props.major,props.minor)==(8,9)
print(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'name':props.name,'uuid':str(props.uuid),'capability':[props.major,props.minor],'torch':torch.__version__,'cuda':torch.version.cuda}),flush=True)
host=torch.empty(64*1024*1024,dtype=torch.uint8,pin_memory=True)
gpu=torch.empty_like(host,device='cuda')
start=time.monotonic();rows=[];loops=0
while time.monotonic()-start<3:
    for _ in range(4):
        gpu.copy_(host,non_blocking=True);host.copy_(gpu,non_blocking=True)
    torch.cuda.synchronize();loops+=4
    r=subprocess.check_output(['nvidia-smi','--id='+GPU,'--query-gpu=uuid,pci.bus_id,pcie.link.gen.current,pcie.link.width.current,temperature.gpu,power.draw,memory.used,memory.free','--format=csv,noheader,nounits'],text=True,timeout=3).strip()
    assert int(r.split(',')[4])<85
    rows.append(r)
print(json.dumps({'seconds':time.monotonic()-start,'copies_each_direction':loops,'bytes_per_copy':host.numel(),'samples':rows}),flush=True)
del gpu,host
torch.cuda.synchronize()
