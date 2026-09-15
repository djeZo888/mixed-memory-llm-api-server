"""L2VM fixed post-stage verification after unordered Docker Mounts comparison.

Frozen PAYLOAD supplied in memory. Only writes exclusive evidence under existing
protected transaction via actual registered AnchoredRoot. No installation/actions.
Verification: --help, worker syntax, exact VM execution and output evidence.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
if '--help' in sys.argv:print(__doc__);raise SystemExit(0)
P=PAYLOAD;SRC=Path('/usr/local/lib/llm-server/control-api')
sys.path.insert(0,str(SRC/'scripts'))
from common.lifecycle_lease import acquire_lease
from lifecycle.storage_binding import RegisteredStorageBinding
from lifecycle.manager import StorageRunner,Manager
from control import installation
from install import storage_io
def sha(b):return hashlib.sha256(b).hexdigest()
def command(args):return subprocess.check_output(args,text=True,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin'},stderr=subprocess.DEVNULL)
def canonical():
    for n,e in P['guards']['guards'].items():
        assert sha(installation.protected_file(e['path']))==e['sha256']
        if n=='require-data-mounted.sh':command(['/bin/bash',e['path']])
        else:r=command(['/bin/bash','-c','exec 3>&1; /bin/bash "$1" --report /proc/self/fd/3','l2vm',e['path']])
    assert '## Conclusion\n\nPASS' in r
    return r
def encode(v):return (json.dumps(v,sort_keys=True,indent=2)+'\n').encode()
pre=canonical()
b=RegisteredStorageBinding.load(StorageRunner(),roles=('data','models'))
assert b.identity==json.loads(base64.b64decode(P['proposals']['storage-identity.proposed.json']))
result={'status':'PASS_STAGED_ONLY','control':'STOPPED_DISABLED','mounts_comparison':'exact tuples sorted by Destination; Docker inspect array order is not stable','native_key_exactbytes':'initial apply private comparison passed before unrelated mount-order assertion; final metadata unchanged','runtime_auth':'NOT_PUBLISHED','q38_receipt':'NOT_YET_PUBLISHED'}
with acquire_lease(blocking=False) as lease:
    with b.mounted_guard(storage_io,roles=('data','models')) as guard:
        with storage_io.AnchoredRoot('/data',guard) as a:
            def put(name,raw):
                lease.validate();rel='services/llm-manager/adoption/l2vm-existing-host-20260915/'+name
                assert a.stat(rel,missing_ok=True) is None
                with a.open(rel,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600) as f:f.write(raw);f.fsync()
                a.check()
            unchanged=['/data/services/llm-manager/active/active.json','/run/llmctl/recovery.json','/data/services/llm-manager/acquisition/glm-5.3-ud-q4-k-xl.complete.json','/etc/fstab','/etc/llm-server/network.json','/usr/local/lib/llm-server/private-network/private_network.py','/etc/systemd/system/m6b-post-reboot-verify.service']
            for p in unchanged:
                e=P['before']['files'][p];s=Path(p).lstat()
                assert sha(installation.protected_file(p))==e['sha256']
                assert all(getattr(s,'st_'+k)==e[k] for k in ('uid','gid','ino','dev','nlink','size','mtime_ns','ctime_ns'))
            for p in P['before']['private_metadata_only']:
                if p.endswith('control-api-key'):continue
                s=Path(p).lstat();e=P['before']['private_metadata_only'][p]
                assert all(getattr(s,'st_'+k)==e[k] for k in ('uid','gid','ino','dev','nlink','size','mtime_ns','ctime_ns'))
            original=a.read_json('services/llm-manager/adoption/l2vm-existing-host-20260915/instance-immediate-preimport.raw')
            adopted=b.read_json('data','/data/services/llm-manager/deployment-instance.json')
            assert adopted==dict(original,storage_identity=b.identity,historical_import=True)
            m=Manager(SRC/'configs',adopted,binding=b);state=m.read_state();c=m.trusted_container(state['container'])
            e=P['before']['container']
            for k in ('Id','Image','Name','RestartCount','Path','Args'):assert c[k]==e[k]
            assert sorted(c['Mounts'],key=lambda x:x['Destination'])==sorted(e['Mounts'],key=lambda x:x['Destination'])
            for k,v in e['State'].items():assert c['State'][k]==v
            for k,v in e['Config'].items():assert c['Config'][k]==v
            for k,v in e['HostConfig'].items():assert c['HostConfig'][k]==v
            d=json.loads(base64.b64decode(P['historical_readonly']['configs/deployments/glm-5.3-ud-q4-k-xl-32k.json']))
            d['_runtime']=json.loads(base64.b64decode(P['historical_readonly']['configs/runtimes/llama-cpp-v0.4.1-d1.json']))
            d['_model']=json.loads(installation.protected_file(SRC/'configs/models/glm-5.3-ud-q4-k-xl.json'))
            m.bind_deployment(d);m.validate_reused_contract(c,d)
            installed={str(p.relative_to(SRC)) for p in SRC.rglob('*') if p.is_file()}
            assert installed==set(P['manifest']['files'])
            for p,e in P['manifest']['files'].items():
                f=SRC/p;s=f.lstat();assert sha(installation.protected_file(f,root_device=Path('/').stat().st_dev))==e['sha256']
                assert stat.S_IMODE(s.st_mode)==int(e['mode'],8) and s.st_gid==0
            for p in ('/data/build','/data/hf-cache','/data/backups','/data/logs'):
                s=Path(p).lstat();e=P['before']['directories'][p]
                assert (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode),s.st_ino,s.st_dev)==(0,e['gid'],0o2755,e['ino'],e['dev'])
            for p in ('/data/services/installer','/data/services/llm-control'):
                s=Path(p).lstat();assert (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))==(0,0,0o700) and not list(Path(p).iterdir())
            assert command(['systemctl','show','llm-control.service','--property=UnitFileState','--value']).strip()=='disabled'
            assert command(['systemctl','show','llm-control.service','--property=ActiveState','--value']).strip()=='inactive'
            assert command(['systemctl','show','m6b-post-reboot-verify.service','--property=UnitFileState','--value']).strip()=='disabled'
            assert not any(':'+str(p) in l for l in command(['ss','-ltnH']).splitlines() for p in (30000,30004))
            assert not Path('/etc/systemd/system/llmctl-boot.service').exists() and not Path('/etc/tmpfiles.d/llmctl.conf').exists()
            installation._control_config(Path('/').stat().st_dev)
            installation._key(installation.protected_file('/etc/llm-server/control-api-key',modes={0o600},maximum=257,root_device=Path('/').stat().st_dev))
            assert Path('/etc/systemd/system/llm-control.service').read_bytes()==base64.b64decode(P['proposals']['llm-control.service.proposed'])
            assert a.read_json('services/llm-manager/adoption/l2vm-existing-host-20260915/control-key-action.json')['action']=='created'
            registered=command(['/usr/bin/python3','-I','-B',str(SRC/'scripts/common/registered-storage.py'),'--root-guard','--json'])
            json.loads(registered)
            put('finalize-pre-root-guard.md',pre.encode());put('registered-root-guard.json',registered.encode())
            put('finalize-post-root-guard.md',canonical().encode());put('stage-result.json',encode(result))
print(json.dumps(result,sort_keys=True))
