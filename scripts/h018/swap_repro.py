#!/usr/bin/env python3
"""H018 finite no-GPU swap-limit experiment; installed ordinary guards only."""
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import time

BASE = Path('/data/build/H018-20260928/swap-repair')
LOG = Path('/data/logs/H018-20260928/swap-repair704')
OWNER = Path('/data/services/mimo-h016-20260927/source/owner.py')
OWNER_SHA = 'dd9c10c75214fbbf8f1d5566618ac35bafa17f709ffc12ec3f84003dc9e30786'
# Exact installed CUDA base, used only for /bin/sleep; no NVIDIA runtime/devices.
IMAGE = 'sha256:7be56e69d8ae7c3648b8fca009fa35980ecd9c6eefaafbff3ee8c224e0043eb5'
SLICE = 'llmmimo.slice'
POLICY = Path('/etc/systemd/system') / SLICE
POLICY_BYTES = b'[Unit]\nDescription=MiMo dedicated zero-swap boundary\n[Slice]\nMemoryAccounting=yes\nMemoryMax=755914244096\nMemorySwapMax=0\n'
CAP = datetime.datetime.fromisoformat('2026-09-28T00:02:00+00:00').timestamp()
LIMIT_FILES = ('memory.min', 'memory.low', 'memory.high', 'memory.max', 'memory.swap.max')


def module(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def setup():
    assert hashlib.sha256(OWNER.read_bytes()).hexdigest() == OWNER_SHA
    o = module('installed_ordinary_owner', OWNER)
    return o, o.setup()


def save(o, h, name, value):
    with h.MountedStorageGuard(h.s) as g, h.AnchoredRoot(str(LOG), g) as a:
        h.s.root_payload_guard()
        a.atomic_json(name, value)
        h.s.root_payload_guard()


def snapshot(o):
    rows = []
    for cid in o.run(['docker', 'ps', '-q', '--no-trunc'], 3).split():
        c = o.inspect(cid)
        cg = o.cgpath(c['State']['Pid'])
        rows.append({'id': cid, 'name': c['Name'], 'image': c['Image'], 'pid': c['State']['Pid'],
                     'started': c['State']['StartedAt'], 'cgroup': str(cg),
                     'limits': {n: (cg/n).read_text().strip() for n in LIMIT_FILES},
                     'swap_current': (cg/'memory.swap.current').read_text().strip(),
                     'events': (cg/'memory.events').read_text().strip(),
                     'hostconfig': {k:c['HostConfig'].get(k) for k in ('Memory','MemorySwap','CgroupParent','Runtime')}})
    return rows


def identities(rows):
    return [{k:r[k] for k in ('id','name','image','pid','started','cgroup')} for r in rows]


def restore_residents(o, before):
    """Undo only observed reload changes to exact resident cgroups; not the fix."""
    changed = []
    for r in before:
        c = o.inspect(r['id'])
        assert c['State']['Running'] and c['State']['Pid'] == r['pid'] and c['State']['StartedAt'] == r['started']
        assert str(o.cgpath(r['pid'])) == r['cgroup']
        for n, old in r['limits'].items():
            p = Path(r['cgroup'])/n
            new = p.read_text().strip()
            if new != old:
                assert old == 'max' or old.isascii() and old.isdecimal()
                changed.append({'id':r['id'],'file':n,'before':old,'after_reload':new})
                p.write_text(old)
                assert p.read_text().strip() == old
    return changed


def check_quiet(o):
    q = json.loads((BASE/'QUIET.json').read_text())
    assert q['status'] == 'QUIET_ORIGINAL_APP_PAUSED' and q['app']['MainPID'] == '0'
    assert all(q[k] == 0 for k in ('activeOwnedRuns','activeFrontierRequests','activeImageJobs','uncertainImageJobs'))
    assert 0 <= time.time() - datetime.datetime.fromisoformat(q['utc']).timestamp() < 1800
    assert time.time() < CAP
    st = o.read(o.BASE/'state.json')
    assert st['status'] == 'SETTLED' and st['request_hold'] is False
    assert not Path('/proc',str(st['native']['pid'])).exists() and not Path(st['native_cgroup']).exists()
    assert not o.inspect(st['native']['container_id'])['State']['Running']
    assert not Path('/proc',str(st['proxy']['pid'])).exists()
    assert o.selection() == {'schema_version':1,'generation':8,'selected_frontier':o.GLM}
    return q


def baseline_stop():
    o,h = setup()
    with o.settlement_lease(h) as lease, h.MountedStorageGuard(h.s) as g:
        h.s.root_payload_guard();o.storage_paths(h,g);q=check_quiet(o)
        m=o.read(o.BASE/'manifest.json');o.source_preflight(h,m)
        assert o.digest(m) == 'e5fa5be2a05c037ac8bac892f73c484f7bbf18e510008d1f4c00729ffd2a77fb'
        rows=snapshot(o);assert len(rows)==4
        idle=[]
        for row in rows:
            sched=[]
            for pid in (Path(row['cgroup'])/'cgroup.procs').read_text().split():
                if Path('/proc',pid,'comm').read_text().startswith(('sglang::schedul','sgl_diffusion::')):
                    w=Path('/proc',pid,'wchan').read_text().strip();assert 'poll' in w
                    st=Path('/proc',pid,'stat').read_text().rsplit(')',1)[1].split()
                    sched.append({'pid':pid,'ticks':st[11:13],'start':st[19],'wchan':w})
            assert len(sched)==1
            idle.append(sched[0])
        time.sleep(1)
        for r in idle:
            st=Path('/proc',r['pid'],'stat').read_text().rsplit(')',1)[1].split()
            assert r['start']==st[19]
            r['cpu_ticks_before_after']=[r['ticks'],st[11:13]]
            # Match retained native scheduler idle proof: polling at both boundaries;
            # passive observer/status work can increment CPU ticks without inference.
            assert 'poll' in Path('/proc',r['pid'],'wchan').read_text()
        gpu=o.run(['nvidia-smi','--query-gpu=uuid,utilization.gpu,temperature.gpu,memory.free,memory.total','--format=csv,noheader,nounits'],3)
        for line in gpu.splitlines():
            f=[x.strip() for x in line.split(',')];assert int(f[1])==0 and int(f[2])<85
        glm=[r for r in rows if r['name']=='/llm-frontier-flash'][0]
        assert glm['id']=='2b5e5e386f70678cefebbfcb66cfdab568e9b3744abfb366f03a66ea7fdb03ab'
        out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'BASELINE_IDLE','source_sha256':OWNER_SHA,
             'selection':o.selection(),'quiet_sha256':hashlib.sha256((BASE/'QUIET.json').read_bytes()).hexdigest(),
             'storage':h.s.read_registration(),'lease_inode':list((lambda s:(s.st_dev,s.st_ino))(o.LEASE_PATH.stat())),
             'containers':rows,'native_idle':idle,'gpu':gpu,'memory':o.memory(),
             'versions':o.run(['docker','version','--format','{{json .Server.Components}}'],3),
             'docker_info':o.run(['docker','info','--format','{{.ServerVersion}} {{.CgroupDriver}} {{.CgroupVersion}} {{.DockerRootDir}}'],3),
             'systemd':o.run(['systemctl','--version'],3).splitlines()[0]}
        save(o,h,'BASELINE.json',out);lease.validate();h.s.root_payload_guard()
    # Existing unit invokes its exact original owner and takes the canonical lease.
    o.run(['systemctl','stop',o.GLM_UNIT],50)
    with o.settlement_lease(h), h.MountedStorageGuard(h.s) as g:
        h.s.root_payload_guard();c=o.inspect(glm['id'])
        assert not c['State']['Running'] and c['State']['Pid']==0
        assert not Path('/proc',str(glm['pid'])).exists() and not Path(glm['cgroup']).exists()
        assert not o.run(['nvidia-smi','--id='+o.GPU,'--query-compute-apps=pid','--format=csv,noheader,nounits'],3).strip()
        after=snapshot(o);assert identities(after)==identities([r for r in rows if r!=glm])
        save(o,h,'GLM-STOP.json',{'status':'EXACT_ORIGINAL_GLM_SETTLED','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                'container':glm,'pid_released':True,'cgroup_released':True,'gpu_released':True,'preserved':after})
        h.s.root_payload_guard()
    print('EXACT_ORIGINAL_GLM_SETTLED',flush=True)


def experiment():
    o,h=setup();owned=[];installed=False;before=[];out={'status':'RUNNING','stages':[],'collateral_restorations':[]}
    def stop(*_):raise TimeoutError('finite_job_deadline')
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGALRM,stop);signal.alarm(150)
    with o.settlement_lease(h) as lease,h.MountedStorageGuard(h.s) as g:
        h.s.root_payload_guard();o.storage_paths(h,g);check_quiet(o)
        assert not o.inspect('llm-frontier-flash')['State']['Running']
        before=snapshot(o);assert len(before)==3
        assert not POLICY.exists() and not POLICY.is_symlink()
        assert o.inspect(IMAGE)['Id']==IMAGE
        def sample(cid,label):
            c=o.inspect(cid);cg=o.cgpath(c['State']['Pid'])
            r={'stage':label,'id':cid,'pid':c['State']['Pid'],'cgroup':str(cg),
               'leaf':{n:(cg/n).read_text().strip() for n in (*LIMIT_FILES,'memory.swap.current','memory.events')},
               'parent':{n:(cg.parent/n).read_text().strip() for n in ('memory.max','memory.swap.max','memory.swap.current')}}
            assert r['leaf']['memory.max']=='67108864' and r['leaf']['memory.swap.current']=='0'
            assert all(v=='0' for k,v in dict(x.split() for x in r['leaf']['memory.events'].splitlines()).items() if k.startswith('oom'))
            if label.startswith('policy_'):
                candidate=module('candidate_memory_policy',BASE/'owner_candidate.py')
                r['production_policy_validation']=candidate.memory_policy({'memory':{'limit_bytes':755914244096}}, {'container_id':cid})
            out['stages'].append(r);save(o,h,'REPRO.json',out);return r
        def reload():
            out['resident_before_reload']=snapshot(o)
            o.run(['systemctl','daemon-reload'],10)
            out['resident_after_reload']=snapshot(o)
            out['collateral_restorations']+=restore_residents(o,before)
        def create(sliced):
            name='h018-swap-prototype-'+('policy' if sliced else 'plain')
            argv=['docker','create','--pull=never','--name',name,'--runtime=runc','--network=none','--read-only','--cap-drop=ALL',
                  '--security-opt=no-new-privileges','--memory=64m','--memory-swap=64m','--pids-limit=16','--restart=no',
                  '--label=io.h018.owner=H018-SWAP-REPAIR-01-20260928','--log-driver=none','--entrypoint=/bin/sleep']
            if sliced:argv+=['--cgroup-parent='+SLICE]
            cid=o.run(argv+[IMAGE,'120'],10).strip();assert o.HEX.fullmatch(cid);owned.append(cid)
            c=o.inspect(cid);assert not c['HostConfig'].get('DeviceRequests') and not c['Mounts'] and c['HostConfig']['NetworkMode']=='none'
            save(o,h,'OWNED.json',{'ids':owned,'policy_path':str(POLICY),'policy_sha256':hashlib.sha256(POLICY_BYTES).hexdigest()})
            o.run(['docker','start',cid],5);return cid
        try:
            cid=create(False);a=sample(cid,'plain_before_reload');reload();b=sample(cid,'plain_after_reload')
            out['local_zero_to_max_reproduced']=a['leaf']['memory.swap.max']=='0' and b['leaf']['memory.swap.max']=='max'
            fd=os.open(POLICY,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
            with os.fdopen(fd,'wb') as f:f.write(POLICY_BYTES)
            installed=True;reload();o.run(['systemctl','start',SLICE],5)
            fixed=create(True);sample(fixed,'policy_before_reload');reload();r=sample(fixed,'policy_after_reload')
            assert r['parent']['memory.swap.max']=='0' and r['parent']['memory.max']=='755914244096' and r['parent']['memory.swap.current']=='0'
            o.run(['docker','stop','--time','2',fixed],5);o.run(['docker','start',fixed],5)
            sample(fixed,'policy_after_container_restart');reload();r=sample(fixed,'policy_after_restart_and_reload')
            assert r['parent']['memory.swap.max']=='0' and r['parent']['memory.max']=='755914244096'
            out['status']='PASS'
        except BaseException as exc:
            out['status']='FAILED';out['failure_class']=type(exc).__name__;raise
        finally:
            signal.alarm(0)
            for cid in owned:
                c=o.inspect(cid);assert c['Config']['Labels'].get('io.h018.owner')=='H018-SWAP-REPAIR-01-20260928' and c['Image']==IMAGE
                pid=c['State']['Pid'];cg=o.cgpath(pid) if pid else None
                o.run(['docker','rm','-f',cid],8)
                assert not pid or not Path('/proc',str(pid)).exists()
                assert cg is None or not cg.exists()
            if installed:
                o.run(['systemctl','stop',SLICE],5);assert POLICY.read_bytes()==POLICY_BYTES;POLICY.unlink();reload()
            out['collateral_restorations']+=restore_residents(o,before)
            after=snapshot(o);assert identities(after)==identities(before)
            assert all(r['limits']==next(x['limits'] for x in before if x['id']==r['id']) for r in after)
            out.update(final_residents=after,owned_removed=True,prototype_policy_removed=not POLICY.exists(),
                       end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
            lease.validate();h.s.root_payload_guard();save(o,h,'REPRO.json',out)
    print(json.dumps({'status':out['status'],'local_zero_to_max_reproduced':out.get('local_zero_to_max_reproduced'),'owned_removed':True}),flush=True)


if __name__=='__main__':
    import sys
    {'baseline-stop':baseline_stop,'experiment':experiment}[sys.argv[1]]()
