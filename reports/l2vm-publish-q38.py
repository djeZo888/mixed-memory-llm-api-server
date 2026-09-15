"""One-use Q38 protected receipt publication; root stage already complete.

Worker supplies Q38_CHECK_SOURCE exact reviewed task probe bytes in memory.
No payload reads, model/runtime/auth activity, downloader or installer entrypoint.
--help, worker syntax, live held-proof/lease/anchored-write and check_completion QA.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import types
if '--help' in sys.argv:print(__doc__);raise SystemExit(0)
SRC=Path('/usr/local/lib/llm-server/control-api');sys.path.insert(0,str(SRC/'scripts'))
from common.lifecycle_lease import acquire_lease
from lifecycle.storage_binding import RegisteredStorageBinding
from lifecycle.manager import StorageRunner,Manager
from lifecycle import qwen38
from control import installation
from install import storage_io
probe=types.ModuleType('l2vm_q38_proof');exec(compile(Q38_CHECK_SOURCE,'l2vm-q38-check.py','exec'),probe.__dict__)
def command(args):return subprocess.check_output(args,text=True,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin'},stderr=subprocess.DEVNULL)
def guards():
    for name,digest in probe.GUARDS.items():
        p=probe.GUARD_ROOT+name
        assert hashlib.sha256(installation.protected_file(p)).hexdigest()==digest
        if name=='require-data-mounted.sh':command(['/bin/bash',p])
        else:report=command(['/bin/bash','-c','exec 3>&1; /bin/bash "$1" --report /proc/self/fd/3','l2vm',p])
    assert '## Conclusion\n\nPASS' in report
    return report.encode()
def encode(v):return (json.dumps(v,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def signature(s):return tuple(getattr(s,'st_'+k) for k in ('dev','ino','uid','gid','mode','nlink','size','mtime_ns','ctime_ns'))
pre=guards();b=RegisteredStorageBinding.load(StorageRunner(),roles=('data','models'))
assert command(['systemctl','show','llm-control.service','--property=ActiveState','--value']).strip()=='inactive'
state_paths=['/data/services/llm-manager/active/active.json','/run/llmctl/recovery.json','/data/services/llm-manager/acquisition/glm-5.3-ud-q4-k-xl.complete.json']
unchanged={p:(installation.protected_file(p),signature(Path(p).lstat())) for p in state_paths}
key=Path('/data/services/secrets/llm-api-key');native=installation.protected_file(key,modes={0o600});native_stat=signature(key.lstat())
c=json.loads(command(['docker','inspect','llmctl-glm-5.3-32k']))[0]
c['Mounts']=sorted(c['Mounts'],key=lambda x:x['Destination'])
with acquire_lease(blocking=False) as lease:
    with probe.validate() as proof:
        with b.mounted_guard(storage_io,roles=('data','models')) as guard:
            with storage_io.AnchoredRoot('/data',guard) as a:
                prefix='services/llm-manager/adoption/l2vm-existing-host-20260915/'
                def put(name,raw):
                    lease.validate();assert a.stat(prefix+name,missing_ok=True) is None
                    with a.open(prefix+name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600) as f:f.write(raw);f.fsync()
                    a.check()
                inst_path='services/llm-manager/deployment-instance.json'
                receipt_path='services/llm-manager/acquisition/qwen38-27b-fp8.complete.json'
                old=a.read_json(inst_path)
                assert old.get('historical_import') is True and old.get('storage_identity')==b.identity
                assert 'qwen38-27b-fp8' not in old['model_integrity'] and a.stat(receipt_path,missing_ok=True) is None
                with a.open(inst_path) as f:raw=f.read()
                assert json.loads(raw)==old
                put('q38-immediate-preinstance.raw',raw)
                put('q38-sealed-evidence.raw.json',proof.seal_raw);put('q38-acquisition-complete.raw.json',proof.complete_raw)
                put('q38-pre-root-guard.md',pre)
                proof.check();lease.validate()
                a.atomic_json(receipt_path,proof.receipt)
                assert hashlib.sha256(installation.protected_file('/data/'+receipt_path)).hexdigest()==probe.RECEIPT_SHA
                value=json.loads(json.dumps(old));value['model_integrity'].update(proof.instance_addition)
                assert a.read_json(inst_path)==old
                proof.check();lease.validate();a.atomic_json(inst_path,value)
                assert a.read_json(inst_path)==value
                m=Manager(SRC/'configs',value,binding=b)
                d=m.deployment('qwen38-27b-128k');qwen38.check_completion(d,value)
                assert value['runtime_evidence']==old['runtime_evidence']
                for p,(raw,s) in unchanged.items():assert installation.protected_file(p)==raw and signature(Path(p).lstat())==s
                assert installation.protected_file(key,modes={0o600})==native and signature(key.lstat())==native_stat
                after=json.loads(command(['docker','inspect','llmctl-glm-5.3-32k']))[0]
                after['Mounts']=sorted(after['Mounts'],key=lambda x:x['Destination'])
                assert all(after[k]==c[k] for k in ('Id','Image','Name','RestartCount','State','Path','Args','Mounts','Config','HostConfig'))
                assert command(['systemctl','show','llm-control.service','--property=ActiveState','--value']).strip()=='inactive'
                result=proof.check();result.update(receipt_publication='PUBLISHED_PROTECTED_COMPLETE_RECEIPT_AND_INSTANCE_LINK',
                    actual_reviewed_check_completion='PASS',runtime_evidence='UNCHANGED_NO_Q38_RUNTIME_ENTRY_ADDED',
                    active_recovery_bytes_timestamps='UNCHANGED',native_key_exactbytes='UNCHANGED_PRIVATE_COMPARISON',
                    glm_container_contract='UNCHANGED',control='STOPPED_DISABLED',
                    instance_sha256=hashlib.sha256(installation.protected_file('/data/'+inst_path)).hexdigest())
                put('q38-post-root-guard.md',guards())
                put('q38-publication.json',encode(result))
print(json.dumps(result,sort_keys=True,indent=2))
