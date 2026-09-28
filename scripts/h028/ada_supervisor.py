"""Exact H028 owner with a bounded load/acceptance window and persistent guards."""
import datetime,hashlib,json,os,signal,subprocess,sys,time,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import ada_owner as owner
stopping=False
def stop_signal(*_):
    global stopping
    stopping=True
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(path,value):
    tmp=path.with_suffix('.new');data=(json.dumps(value,sort_keys=True)+'\n').encode()
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
def qualification_matches(q, identity, boot_id, started_at):
    return (q.get("status")=="PASS" and q.get("container_id")==identity
            and q.get("context_tokens")==200000 and q.get("boot_id")==boot_id
            and q.get("docker_started_at")==started_at)

def immutable_profile(config):
    return {"image_id":owner.IMAGE,"gpu_uuid":owner.GPU,"context_tokens":200000,
            "kv_cache_dtype":"bfloat16","fp8_gemm_backend":"triton",
            "launcher_sha256":config["source_sha256"]["ada_launcher.py"],
            "model_metadata_sha256":config["model_metadata_sha256"]}

def profile_qualified(config):
    proof=config.get("profile_qualification",{})
    return proof.get("status")=="PASS" and proof.get("profile")==immutable_profile(config)

def main():
    signal.signal(signal.SIGTERM,stop_signal);signal.signal(signal.SIGINT,stop_signal)
    base=Path(owner.BASE);log=Path(owner.LOG);config=json.loads((base/'config.json').read_text())
    started=False;qualified=profile_qualified(config);ready_once=False;reason=None
    startup_deadline=time.monotonic()+600
    if not qualified:raise RuntimeError('immutable_profile_not_qualified')
    try:
        owner.operate('start');started=True
        state=json.loads((base/'state.json').read_text());identity=state['container']['id']
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        key=Path('/data/services/secrets/llm-api-key').read_text()
        with (log/'telemetry.jsonl').open('a') as records:
            while not stopping:
                c=json.loads(subprocess.check_output(['docker','inspect',identity],text=True,timeout=5))[0]
                owner.validate_container(c,config,state)
                if not c['State']['Running']:raise RuntimeError('native_container_exited')
                row=subprocess.check_output(['nvidia-smi','--id='+owner.GPU,'--query-gpu=uuid,memory.total,memory.used,memory.free,temperature.gpu,power.draw,pcie.link.gen.current,pcie.link.width.current','--format=csv,noheader,nounits'],text=True,timeout=5).strip().split(',')
                uuid,total,used,free,temp,power,gen,width=[x.strip() for x in row]
                if uuid!=owner.GPU or float(temp)>=85:raise RuntimeError('gpu_identity_or_thermal_guard')
                if float(free)<float(total)*.07:raise RuntimeError('gpu_seven_percent_reserve_guard')
                if subprocess.check_output(['systemctl','is-active','local-ai-fan-boost.service'],text=True,timeout=3).strip()!='active':raise RuntimeError('fan_service_guard')
                ready=False
                try:
                    req=urllib.request.Request('http://127.0.0.1:30014/v1/readiness',headers={'Authorization':'Bearer '+key})
                    with urllib.request.urlopen(req,timeout=2) as r:ready=json.load(r).get('ready') is True
                except Exception:pass
                ready_once=ready_once or ready
                receipt={'utc':now(),'gpu_uuid':uuid,'total_mib':int(total),'used_mib':int(used),'free_mib':int(free),'temperature_c':int(temp),'power_w':float(power),'link_gen':int(gen),'link_width':int(width),'ready':ready,'qualified':qualified,'profile_qualified':qualified,'boot_id':boot_id,'docker_started_at':c['State']['StartedAt'],'container_id':identity}
                records.write(json.dumps(receipt)+'\n');records.flush();write(base/'status.json',receipt)
                accepted=base/'qualification.json'
                if accepted.exists():
                    q=json.loads(accepted.read_text())
                    current_instance_qualified=qualification_matches(q,identity,boot_id,c['State']['StartedAt'])
                if not ready_once and time.monotonic()>startup_deadline:raise RuntimeError('relative_warmup_deadline')
                time.sleep(2)
    except BaseException as e:
        reason=type(e).__name__+':'+str(e)
        raise
    finally:
        saved=json.loads((base/'state.json').read_text())
        owned=saved.get('owner')==owner.OWNER and saved.get('container') is not None
        if started or owned:
            try:owner.operate('stop')
            except BaseException as e:reason=(reason or '')+';cleanup:'+type(e).__name__+':'+str(e)
        write(base/'terminal.json',{'utc':now(),'reason':reason,'stop_requested':stopping,'started':started,'qualified':qualified})
if __name__=='__main__':main()
