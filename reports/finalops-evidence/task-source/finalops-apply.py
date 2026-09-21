"""Exact root-approved C1 apply using the unchanged scoped helper and guards."""
import base64


def cleanup_apply_diagnose():
    guard();idle()
    old=json.loads(raw(REPORT/'cleanup-corrected-dry-run.json'))['running']
    new=current();differences=[]
    def compare(a,b,path):
        if a==b:return
        if isinstance(a,dict) and isinstance(b,dict):
            for key in sorted(set(a)|set(b)):compare(a.get(key),b.get(key),path+'/'+key)
        elif isinstance(a,list) and isinstance(b,list):
            for i in range(max(len(a),len(b))):compare(a[i] if i<len(a) else None,b[i] if i<len(b) else None,path+'/'+str(i))
        else: differences.append({'field':path,'old_type':type(a).__name__,'new_type':type(b).__name__})
    compare(old,new,'running')
    emit('C1_PREAPPLY_STATE_DIAGNOSIS',differences=differences,pid=new['container']['State']['Pid'],container_id=new['container']['Id'],generation=control_ready()['status']['generation'],mutation=False)


def exact_running(value=None):
    value=json.loads(json.dumps(current() if value is None else value))
    value['container']['Mounts']=sorted(value['container']['Mounts'],key=lambda row:json.dumps(row,sort_keys=True))
    return value


def available_bytes():
    return {p:os.statvfs(p).f_bavail*os.statvfs(p).f_frsize for p in ('/','/data','/data/models-large')}


def apply_nonuse(trees, expected_refs, containers_absent=False):
    idle(); use=process_nonuse(trees); containers=container_review(trees); refs=reference_review(trees)
    assert not use['visibility_unknown'], 'preapply_process_visibility_unknown:'+json.dumps(use['visibility_unknown'])
    assert not refs['visibility_unknown'], 'preapply_reference_visibility_unknown:'+json.dumps(refs['visibility_unknown'])
    for root in trees:
        assert not use['hits'][root], 'preapply_process_use:'+root+':'+json.dumps(use['hits'][root])
        assert not containers[root]['blockers'], 'preapply_container_reference:'+root+':'+json.dumps(containers[root]['blockers'])
        if containers_absent:
            assert not containers[root]['other_references'] and not containers[root]['planned_retirement_dependencies'], 'container_reference_after_retirement:'+root
            approved=containers[root]['approved_stopped_container']
            assert approved is None or approved['state']=='ALREADY_ABSENT', 'approved_container_still_present:'+root
        assert refs['references'][root]==expected_refs[root], 'operational_reference_drift:'+root
        assert not any(root in u['targets'] and u['active'] not in ('inactive','failed') for u in refs['relevant_units']), 'target_acquisition_active:'+root
        assert not any(root in acquisition_targets(j['unit']) for j in refs['jobs']), 'target_acquisition_job:'+root
    return containers


def retire_metadata(row, lease):
    path=row['path']; descriptors=[]; edges=[]
    try:
        parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC);descriptors.append(parent)
        for name in Path(path).parts[1:-1]:
            child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
            descriptors.append(child);edges.append((parent,name,child,snap(os.fstat(child))));parent=child
        name=Path(path).name
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NOATIME|os.O_CLOEXEC,dir_fd=parent);descriptors.append(fd)
        info=os.fstat(fd)
        assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_size<65536, 'retirement_file_type:'+path
        data=os.read(fd,65537)
        assert snap(info)==row['metadata'] and hashlib.sha256(data).hexdigest()==row['sha256'] and len(data)==row['bytes'], 'retirement_identity_drift:'+path
        backup_name='retired-metadata-'+name+'.json'
        save(backup_name,{'original':row,'content_base64':base64.b64encode(data).decode(),'scope':'metadata_only_no_weights'},exclusive=True)
        assert json.loads(raw(REPORT/backup_name))['content_base64']==base64.b64encode(data).decode(), 'metadata_backup_verification:'+path
        lease.validate();guard();idle()
        for directory,component,opened,expected in edges:
            assert snap(os.fstat(opened))==expected==snap(os.stat(component,dir_fd=directory,follow_symlinks=False)), 'retirement_ancestor_drift:'+path
        assert snap(os.fstat(fd))==row['metadata']==snap(os.stat(name,dir_fd=parent,follow_symlinks=False)), 'retirement_preunlink_drift:'+path
        os.lseek(fd,0,os.SEEK_SET)
        assert hashlib.sha256(os.read(fd,65537)).hexdigest()==row['sha256'], 'retirement_preunlink_hash:'+path
        os.unlink(name,dir_fd=parent);os.fsync(parent)
        try: os.stat(name,dir_fd=parent,follow_symlinks=False)
        except FileNotFoundError: pass
        else: raise AssertionError('retirement_absence_failed:'+path)
        backup=Path(REPORT/backup_name).stat()
        emit('C1_METADATA_RETIRED',path=path,absence_verified=True,backup_bytes=backup.st_size,backup_allocated_bytes=backup.st_blocks*512,weights_backed_up=False)
        return {'path':path,'backup':str(REPORT/backup_name),'backup_bytes':backup.st_size,'backup_allocated_bytes':backup.st_blocks*512,'retired_allocated_bytes':info.st_blocks*512}
    finally:
        for fd in reversed(descriptors):os.close(fd)


def cleanup_apply():
    assert CLEANUP_IDLE_RELEASE is True and ROOT_APPLY_APPROVED is True, 'root_apply_approval_required'
    helper=types.ModuleType('c1_scoped_cleanup');exec(compile(C1_CODE,'c1_scoped_cleanup.py','exec'),helper.__dict__)
    reviewed=json.loads(raw(REPORT/'cleanup-corrected-dry-run.json'))
    assert set(reviewed['trees'])==set(OBSOLETE) and not reviewed['failed'], 'reviewed_target_set'
    for root,tree in reviewed['trees'].items():
        assert tree['snapshot']==APPROVED_SNAPSHOTS[root] and not tree['blockers'], 'root_reviewed_snapshot_mismatch:'+root
    refs=reviewed['operational_references']['references']
    retire=[row for rows in refs.values() for row in rows if row['classification'].startswith('PROPOSED_OBSOLETE_')]
    assert {r['path'] for r in retire}=={
        '/data/services/llm-manager/compose/minimax-m3-poc.compose.yml',
        '/data/services/llm-manager/compose/sglang-qwen3-30b.compose.yml',
        '/data/services/llm-manager/compose/sglang-smoke.compose.yml',
        '/data/services/llm-manager/acquisition/qwen3-coder-next-fp8.complete.json'}, 'retirement_allowlist'
    assert len(retire)==4 and sum(t['snapshot']['allocated_bytes'] for t in reviewed['trees'].values())==586788376576, 'reviewed_union'
    guard();idle();control_ready()
    completed=[]; retired=[]; removed_containers=[]; before=available_bytes()
    with acquire_lease(blocking=False) as lease, temporary_models_parent(lease):
        running=exact_running();retained=preservation()
        assert running==exact_running(reviewed['running']), 'accepted_running_state_drift'
        assert running['container']['State']['Pid']==11259 and running['container']['Id']==F['container_id'], 'accepted_qwen_identity'
        assert control_ready()['status']['generation']==6, 'accepted_generation'
        assert retained==json.loads(raw(REPORT/'pre-reboot.json'))['preservation'], 'accepted_preservation_drift'
        trees={root:inspect_tree(root,helper) for root in OBSOLETE}
        for root,tree in trees.items():
            assert tree['snapshot']==APPROVED_SNAPSHOTS[root] and not tree['blockers'], 'preapply_tree_drift:'+root
        apply_nonuse(trees,refs)
        emit('C1_PREAPPLY_VERIFIED',targets=4,allocated_bytes=586788376576,qwen_pid=11259,generation=6,guards='PASS',non_use='PASS')
        for root,plan in OBSOLETE.items():
            if 'container' not in plan: continue
            lease.validate();guard();idle()
            checked=apply_nonuse(trees,refs)[root]['approved_stopped_container']
            if checked['state']!='ALREADY_ABSENT':
                assert checked['identity_match'] is True, 'container_identity_drift:'+plan['container']
                assert run(['docker','rm',plan['container']],60).strip()==plan['container'], 'container_retirement_output'
            assert plan['container'] not in run(['docker','ps','-a','--quiet','--no-trunc']).split(), 'container_absence_failed'
            removed_containers.append(plan['container']);guard()
            emit('C1_CONTAINER_RETIRED',id=plan['container'],absence_verified=True,force=False,volumes=False)
        apply_nonuse(trees,refs,containers_absent=True)
        for row in retire:
            retired.append(retire_metadata(row,lease))
        preserved_refs={root:[row for row in rows if row['classification']=='PRESERVE_HISTORICAL_PROVENANCE'] for root,rows in refs.items()}
        for root in OBSOLETE:
            def gate(snapshot):
                lease.validate();guard();idle()
                assert exact_running()==running and preservation()==retained, 'pretarget_retained_drift:'+root
                assert control_ready()['status']['generation']==6, 'pretarget_control_generation'
                apply_nonuse({root:trees[root]},preserved_refs,containers_absent=True)
                return True
            emit('C1_TARGET_APPLY_BEGIN',root=root)
            result=helper.apply_reviewed(root,APPROVED_SNAPSHOTS[root],gate)
            completed.append(result)
            emit('C1_TARGET_ABSENCE',**result)
            lease.validate();guard();idle()
            assert exact_running()==running and preservation()==retained, 'posttarget_retained_drift:'+root
            assert control_ready()['status']['generation']==6, 'posttarget_catalog_generation'
            apply_nonuse({root:trees[root]},preserved_refs,containers_absent=True)
            emit('C1_TARGET_VERIFIED',root=root,absence_verified=True,retained_metadata='UNCHANGED',mounts_guards='PASS',qwen_pid=11259,generation=6,catalog='TWO_RETAINED_MODELS_READY')
        after=available_bytes();drivers=gpu()
    guard();assert exact_running()==running and preservation()==retained, 'final_retained_drift'
    assert control_ready()['status']['generation']==6, 'final_control_generation'
    report={'completed':completed,'retired_metadata':retired,'retired_containers':removed_containers,'allocated_weight_bytes_removed':sum(r['removed_inventory_allocated_bytes'] for r in completed),'free_before':before,'free_after':after,'free_delta':{p:after[p]-before[p] for p in before},'metadata_backup_allocated_bytes':sum(r['backup_allocated_bytes'] for r in retired),'retired_metadata_allocated_bytes':sum(r['retired_allocated_bytes'] for r in retired),'parent_restored':True,'canonical_lease':'RELEASED','qwen_pid':11259,'generation':6,'preservation':'PASS','guards':'PASS','gpu':drivers,'concurrent_write_limitation':'Filesystem deltas include concurrent service/log writes and filesystem accounting; allocation removed is measured separately. Metadata backups do not restore weights.'}
    emit('C1_APPLY_RELEASED',**report)
    save('cleanup-applied.json',report,exclusive=True)
