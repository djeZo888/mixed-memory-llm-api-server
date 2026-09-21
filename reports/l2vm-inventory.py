"""Fixed ai-vm read-only evidence; run via SSH sudo python3 -I -B -.

Verification: --help; syntax compile on worker; actual read-only execution.
No key bytes, Docker environment, API requests, writes or stateful Manager calls.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

if '--help' in sys.argv:
    print(__doc__)
    raise SystemExit(0)

def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL)

def meta(path, content=False):
    p = Path(path)
    try:
        s = p.lstat()
    except FileNotFoundError:
        return {'absent': True}
    v = {k: getattr(s, 'st_' + k) for k in ('uid','gid','ino','dev','nlink','size','mtime_ns','ctime_ns')}
    v['mode'] = format(stat.S_IMODE(s.st_mode), '04o')
    v['type'] = 'dir' if stat.S_ISDIR(s.st_mode) else 'file' if stat.S_ISREG(s.st_mode) else 'OTHER'
    assert v['type'] != 'OTHER', path
    if content:
        assert 'key' not in p.name.lower(), 'secret path forbidden'
        v['sha256'] = hashlib.sha256(p.read_bytes()).hexdigest()
    return v

files = [
    '/data/services/llm-manager/deployment-instance.json',
    '/data/services/llm-manager/active/active.json', '/run/llmctl/recovery.json',
    '/data/services/llm-manager/acquisition/glm-5.3-ud-q4-k-xl.complete.json',
    '/data/services/llm-manager/acquisition/qwen38-27b-fp8.complete.json',
    '/etc/fstab', '/etc/local-ai-server/storage.json', '/etc/llm-server/control.json',
    '/etc/llm-server/network.json', '/usr/local/lib/llm-server/private-network/private_network.py',
    '/etc/systemd/system/llm-control.service', '/etc/systemd/system/m6b-post-reboot-verify.service',
    '/etc/systemd/system/llmctl-boot.service', '/etc/tmpfiles.d/llmctl.conf',
    '/data/services/llm-control/operations.json',
]
dirs = ['/', '/data', '/data/models-large', '/data/build', '/data/hf-cache', '/data/backups', '/data/logs',
        '/data/services', '/data/services/llm-manager', '/data/services/installer', '/data/services/llm-control',
        '/data/services/llm-manager/acquisition', '/data/services/llm-manager/adoption',
        '/etc/llm-server', '/etc/local-ai-server', '/usr/local/lib/llm-server',
        '/usr/local/lib/llm-server/control-api', '/data/build/d3p-d3b-20260915', '/run/llmctl']
metadata_only = ['/data/services/secrets/llm-api-key','/etc/llm-server/control-api-key','/run/llmctl/lifecycle.lock']
out = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
       'files': {p: meta(p, True) for p in files}, 'directories': {p: meta(p) for p in dirs},
       'private_metadata_only': {p: meta(p) for p in metadata_only}}
mounts = json.loads(run('findmnt','--json','--list','--output','TARGET,SOURCE,UUID,FSTYPE,FSROOT,OPTIONS,MAJ:MIN'))['filesystems']
expected = {'/data': ('8daf56f1-5649-4163-9d87-919c2d271875','8:17'),
            '/data/models-large': ('a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a','8:33')}
for p,(uuid,dev) in expected.items():
    rows = [m for m in mounts if m['target']==p]
    assert len(rows)==1 and rows[0]['uuid']==uuid and rows[0]['maj:min']==dev, 'mount identity'
    assert rows[0]['fsroot']=='/' and rows[0]['fstype']=='ext4' and 'rw' in rows[0]['options'].split(','), 'whole mount'
    assert [m['target'] for m in mounts if m['maj:min']==dev and m['fsroot']=='/']==[p], 'mount alias'
out['mounts'] = [m for m in mounts if m['target'] in ('/','/boot','/boot/efi',*expected)]
out['blocks'] = json.loads(run('lsblk','--json','--bytes','--paths','--output','NAME,PATH,TYPE,PKNAME,MOUNTPOINTS,FSTYPE,UUID,RO,MAJ:MIN'))
flat=[]
def walk(rows):
    for r in rows:
        flat.append(r); walk(r.get('children',[]))
walk(out['blocks']['blockdevices'])
for uuid,dev in expected.values():
    assert len([r for r in flat if r.get('uuid')==uuid])==1, 'duplicate UUID'
v=os.statvfs('/');out['root_available_bytes']=v.f_bavail*v.f_frsize
assert out['root_available_bytes']>=4*1024**3, 'root below 4GiB'
c=json.loads(run('docker','inspect','llmctl-glm-5.3-32k'))[0]
assert c['Id']=='bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55', 'container changed'
assert '--api-key' not in c['Config']['Cmd'], 'inline key forbidden'
out['container']={k:c[k] for k in ('Id','Image','Name','RestartCount','Path','Args','Mounts')}
out['container']['State']={k:c['State'][k] for k in ('Status','Running','Pid','StartedAt','FinishedAt','Restarting')}
out['container']['Config']={k:c['Config'][k] for k in ('Image','Entrypoint','Cmd','Labels')}
out['container']['HostConfig']={k:c['HostConfig'][k] for k in ('NetworkMode','PortBindings','RestartPolicy','LogConfig','DeviceRequests','Binds')}
env=dict(x.split('=',1) for x in c['Config']['Env'] if '=' in x)
out['container']['reviewed_environment']={k:env.get(k) for k in ('CUDA_VISIBLE_DEVICES','GGML_CUDA_ENABLE_UNIFIED_MEMORY','NVIDIA_VISIBLE_DEVICES')}
units=['llm-control.service','llmctl-boot.service','m6b-post-reboot-verify.service',
       'llm-private-control.socket','llm-private-glm.socket','llm-private-qwen38.socket']
out['units']={u:run('systemctl','show',u,'--property=LoadState,ActiveState,SubState,UnitFileState,MainPID,DropInPaths') for u in units}
out['listeners']= '\n'.join(l for l in run('ss','-ltnH').splitlines() if any(':'+str(p) in l for p in (30000,30002,30004)))
out['active_jobs']=run('systemctl','list-units','--all','--plain','--no-legend','d3*','q38*','n1*')
out['data_root_children']={p:{x.name:meta(x) for x in Path(p).iterdir()} for p in ('/data/build','/data/hf-cache','/data/backups','/data/logs')}
print(json.dumps(out,indent=2,sort_keys=True))
