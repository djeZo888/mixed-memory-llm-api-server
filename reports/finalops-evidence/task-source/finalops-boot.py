"""Narrow FINALOPS adaptation of HOSTRECOVER/APIDEPLOY verification; stdin runner."""
import http.client, re
from common.lifecycle_lease import acquire_lease
from lifecycle.manager import Manager, StorageRunner
from lifecycle.storage_binding import RegisteredStorageBinding
RECOVERY_FILES = ('scripts/llmctl','scripts/lifecycle/__init__.py','scripts/lifecycle/manager.py',
                  'scripts/lifecycle/runtime_io.py','scripts/lifecycle/qwen_next.py',
                  'scripts/lifecycle/storage_binding.py','scripts/common/lifecycle_lease.py',
                  'scripts/install/__init__.py','scripts/install/storage.py',
                  'scripts/install/storage_io.py','scripts/install/prerequisites.py')

UUIDS = {'data': '8daf56f1-5649-4163-9d87-919c2d271875',
         'models': 'a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a'}


def raw(path, limit=8*1024*1024):
    p=protected(path); fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NOATIME)
    try:
        before=os.fstat(fd)
        assert stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=limit, 'unsafe_small_file'
        value=os.read(fd,limit+1)
        assert len(value)==before.st_size and snap(before)==snap(os.fstat(fd))==snap(p.lstat()), 'small_file_drift'
        return value
    finally: os.close(fd)


def digest(path): return hashlib.sha256(raw(path)).hexdigest()


def guard():
    guard_identity()
    reg=protected('/etc/local-ai-server/storage.json')
    assert stat.S_IMODE(reg.stat().st_mode)==0o600 and reg.stat().st_gid==0, 'registry_mode'
    assert digest(reg)=='626db7130b644199f5f632b2ac3c04f86cdd382121573aa6f3825bbca8de9c27', 'registry_identity'
    values=[]
    for flags in ([],['--root-guard']):
        value=json.loads(run(['/usr/bin/python3','-I','-B',CFG['registered_host']['guard']['path'],*flags,'--json'],90))
        assert value['capacity']['root_available_bytes']>=4*1024**3, 'root_floor'
        for role,mount in [('data','/data'),('models','/data/models-large')]:
            assert value[role]['path']==value[role]['mount']==mount and value[role]['uuid']==UUIDS[role] and value[role]['fstype']=='ext4', 'registered_mount_identity'
            actual=json.loads(run(['findmnt','--json','--mountpoint',mount,'--output','TARGET,FSTYPE,FSROOT,UUID']))['filesystems']
            assert actual==[{'target':mount,'fstype':'ext4','fsroot':'/','uuid':UUIDS[role]}], 'mount_identity'
        values.append(value)
    return values[-1]


def idle():
    quiet()
    journal=json.loads(raw('/data/services/llm-control/operations.json'))
    assert all(x['status'] not in ('pending','running') for x in journal['entries'].values()), 'control_operation_inflight'


def request(path, port=30000, native=False):
    key='/data/services/secrets/llm-api-key' if native else '/etc/llm-server/control-api-key'
    conn=http.client.HTTPConnection('127.0.0.1',port,timeout=35)
    headers={'Authorization':'Bearer '+raw(key).decode().strip(),'Connection':'close'}
    try:
        conn.request('GET',path,headers=headers); response=conn.getresponse(); body=response.read(4*1024*1024)
        assert response.status==200, 'authenticated_readiness_http'
        return json.loads(body)
    finally: conn.close(); headers.clear()


def control_ready(initial=False):
    status=request('/control/v1/status'); catalog=request('/control/v1/catalog')
    for value in (status,catalog):
        assert value['selected']==TARGET and value['desired']=='running' and value['observed']=='ready', 'qwen_not_ready'
        assert value['state_persisted'] is True and value['generation_current'] is True and value['current_operation'] is None, 'control_state_not_final'
        assert value['endpoint']['ready'] is True and value['endpoint']['served_model']=='qwen3.8-27b', 'endpoint_identity'
        assert value['endpoint']['base_url']=='http://10.156.100.60:30004/v1', 'endpoint_changed'
    assert {e['deployment_id'] for e in catalog['entries']}=={'glm-5.3-ud-q4-k-xl-n76-native1m',TARGET}, 'catalog_roster'
    if initial:
        assert status['generation']==F['generation'] and status['active_identity']==F['active_identity'], 'accepted_control_identity_changed'
    native=request('/v1/models',30004,True)
    assert 'qwen3.8-27b' in [x['id'] for x in native['data']], 'native_alias'
    return {'status':status,'catalog':catalog,'native_models':native}


def container(cid):
    fmt='{"Id":{{json .Id}},"Name":{{json .Name}},"Image":{{json .Image}},"State":{{json .State}},"RestartPolicy":{{json .HostConfig.RestartPolicy}},"Mounts":{{json .Mounts}},"Labels":{{json .Config.Labels}}}'
    return json.loads(run(['docker','inspect','--format',fmt,cid],15))


def tree_meta(root):
    p=Path(root); rows={}
    for current,dirs,files in os.walk(p,followlinks=False):
        for entry in [Path(current),*[Path(current)/n for n in files]]:
            info=entry.lstat(); assert not stat.S_ISLNK(info.st_mode), 'retained_model_link'
            rows[str(entry.relative_to(p))]=snap(info)
        assert all(not (Path(current)/n).is_symlink() for n in dirs), 'retained_model_link'
    return rows


def preservation():
    mp='/usr/local/lib/llm-server/control-api.manifest.json'
    assert digest(mp)==P['source_manifest_sha256'], 'source_manifest_changed'
    manifest=json.loads(raw(mp)); assert manifest['source_commit']==P['source_commit'], 'source_commit_changed'
    for name, row in manifest['files'].items():
        path=SRC/name
        assert digest(path)==row['sha256'] and stat.S_IMODE(path.stat().st_mode)==int(row['mode'],8), 'source_closure_changed'
        assert raw(path)==raw(Path(P['normal_release'])/name), 'release_source_changed'
    for name in RECOVERY_FILES:
        assert raw(Path('/usr/local/lib/local-ai-server')/name)==raw(SRC/name), 'recovery_source_changed'
    instance=Path('/data/services/llm-manager/deployment-instance.json')
    assert digest(instance)==P['instance_sha256'], 'instance_changed'
    assert digest('/etc/systemd/system/llmctl-boot.service')==P['boot_unit_sha256'], 'boot_unit_changed'
    installed=json.loads(raw(instance))
    names=['/etc/local-ai-server/storage.json','/etc/llm-server/control.json','/etc/llm-server/network.json',
           '/etc/llm-server/private-network-state.json','/usr/local/lib/llm-server/private-network/private_network.py',
           '/etc/llm-server/control-api-key','/data/services/secrets/llm-api-key',mp,str(instance),
           '/etc/systemd/system/llmctl-boot.service','/etc/systemd/system/llm-control.service',
           '/data/services/llm-manager/adapters/sglang38_file_auth.py']
    names.extend(P['receipts'])
    for evidence in installed['model_integrity'].values():
        if evidence.get('completion_manifest'): names.append(evidence['completion_manifest'])
    for name,row in P['receipts'].items():
        assert digest(name)==row['sha256'] and stat.S_IMODE(Path(name).stat().st_mode)==0o600, 'receipt_binding'
    assert digest('/usr/local/lib/llm-server/private-network/private_network.py')=='9ca8ca4b86dbf04988bfe2f8f0a7b3748bbe5d1922c0543f081616f37ec1a6af', 'netpatch_changed'
    return {'files':{n:{'sha256':digest(n),'metadata':snap(Path(n).stat())} for n in sorted(set(names))},
            'weights':{n:tree_meta('/data/models-large/'+n) for n in ('glm-5.3-ud-q4-k-xl','qwen38-27b-fp8')},
            'images':sorted(set(run(['docker','image','ls','-a','--no-trunc','--quiet']).split()))}


def current(initial=False):
    m=manager(); state=m.read_state()
    assert state['selected']==TARGET and state['desired']=='running' and state['boot_policy']=='resume', 'accepted_qwen_resume_state_required'
    assert state.get('state_persisted') is not False, 'state_not_persisted'
    c=container(state['container']['id']); d=m.deployment(TARGET)
    m.trusted_container(state['container'])
    # The existing lifecycle validator binds runtime/proof/launcher/mounts/keys.
    full=json.loads(run(['docker','inspect',c['Id']],30))[0]
    m.validate_reused_contract(full,d)
    assert c['State']['Running'] and not c['State']['Restarting'] and c['State']['Pid']>0 and c['RestartPolicy']['Name']=='no', 'qwen_runtime_state'
    assert run(['docker','ps','--no-trunc','--quiet']).split()==[c['Id']], 'unexpected_running_container'
    if initial:
        for key,actual in [('container_id',c['Id']),('image_id',c['Image']),('pid',c['State']['Pid']),('started_at',c['State']['StartedAt'])]:
            if key in F: assert F[key]==actual, 'accepted_runtime_identity_changed'
    return {'state':state,'container':c}


def gpu():
    kernel=run(['uname','-r']).strip(); loaded=Path('/sys/module/nvidia/version').read_text().strip()
    installed=run(['modinfo','-F','version','nvidia']).strip()
    rows=run(['nvidia-smi','--query-gpu=index,name,driver_version,memory.total,memory.free','--format=csv,noheader,nounits'],15).strip().splitlines()
    assert loaded==installed and len(rows)==2 and all(loaded in row for row in rows), 'gpu_driver_alignment'
    assert run(['docker','info','--format','{{.DockerRootDir}}']).strip()=='/data/docker', 'docker_storage'
    return {'kernel':kernel,'loaded':loaded,'installed':installed,'gpus':rows}


def save(name, value, exclusive=False):
    guard()
    binding=bind()
    with writer(binding) as anchor:
        anchor.mkdir(REPORT.name,mode=0o700)
        with anchor.directory(REPORT.name) as directory:
            os.fchown(directory.fileno(),0,0)
            os.fchmod(directory.fileno(),0o700)
        assert stat.S_IMODE(anchor.stat(REPORT.name).st_mode)==0o700, 'report_parent_mode'
        if exclusive: assert anchor.stat(REPORT.name+'/'+name,missing_ok=True) is None, 'phase_already_recorded'
        anchor.atomic_json(REPORT.name+'/'+name,value)
    guard()


def reboot():
    assert F.get('idle_release') is True and F.get('models_accepted') is True, 'final_handoff_required'
    g=guard()
    emit('PREBOOT_GUARDS_PASS',root_available_bytes=g['capacity']['root_available_bytes'])
    controls=control_ready(initial=True); idle(); no_package_writer()
    with acquire_lease(blocking=False) as lease:
        idle(); accepted=current(initial=True); retained=preservation(); drivers=gpu()
        lock=Path('/run/llmctl/lifecycle.lock').stat()
        assert lock.st_ino==P['canonical_lease_inode'], 'preboot_canonical_lock_changed'
        baseline={'utc':time.time(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  'accepted':accepted,'preservation':retained,'gpu':drivers,'control':controls,
                  'guard':g,'lease_identity':{'dev':lock.st_dev,'ino':lock.st_ino}}
        guard(); lease.validate(); idle()
        save('pre-reboot.json',baseline,exclusive=True)
        emit('PRE_REBOOT_PASS',boot_id=baseline['boot_id'],container_id=accepted['container']['Id'],pid=accepted['container']['State']['Pid'],boot_policy='resume',root_available_bytes=g['capacity']['root_available_bytes'])
    # Canonical lease is closed here, before systemd stop/start paths acquire it.
    idle(); no_package_writer(); guard()
    emit('NORMAL_REBOOT_DISPATCH',canonical_lease='RELEASED',container_id=accepted['container']['Id'])
    subprocess.run(['/usr/bin/systemctl','reboot'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=15)


def postboot():
    g=guard(); before=json.loads(raw(REPORT/'pre-reboot.json'))
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert boot!=before['boot_id'], 'actual_reboot_not_observed'
    emit('SSH_RETURN_NEW_BOOT_ID',boot_id=boot,prior_boot_id=before['boot_id'],guards='PASS')
    drivers=gpu(); assert drivers['loaded']==before['gpu']['loaded'] and drivers['kernel']==before['gpu']['kernel'], 'driver_or_kernel_drift'
    unit=run(['systemctl','show','llmctl-boot.service','--property=ActiveState,SubState,Result'])
    if 'ActiveState=activating' in unit:
        emit('POSTBOOT_LOADING',boot_id=boot,guard='PASS',gpu='PASS',canonical_lease='NOT_ACQUIRED'); return
    assert 'ActiveState=active' in unit and 'Result=success' in unit, 'boot_owner_not_successful'
    controls=control_ready(); idle()
    with acquire_lease(blocking=False) as lease:
        observed=current(); assert observed['container']['Id']==before['accepted']['container']['Id'] and observed['container']['Image']==before['accepted']['container']['Image'], 'resumed_container_or_image_changed'
        assert observed['container']['State']['StartedAt']!=before['accepted']['container']['State']['StartedAt'], 'new_runtime_lifetime_missing'
        assert preservation()==before['preservation'], 'retained_identity_changed'
        lease.validate(); guard()
        value={'boot_id':boot,'prior_boot_id':before['boot_id'],'current':observed,'control':controls,'gpu':drivers,'guard':g,'retained_preservation':'PASS'}
        save('postboot.json',value)
    emit('POSTBOOT_READY',boot_id=boot,container_id=observed['container']['Id'],image_id=observed['container']['Image'],pid=observed['container']['State']['Pid'],started_at=observed['container']['State']['StartedAt'],selected=TARGET,generation=controls['status']['generation'],active_identity=controls['status']['active_identity'],canonical_lease='RELEASED',worker2_lan='READY_FOR_INDEPENDENT_CHECK')
