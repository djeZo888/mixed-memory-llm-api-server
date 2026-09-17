"""C1 dry-run/non-use adaptation only. No apply or retirement in this runner."""
import types

OBSOLETE = {
 '/data/models/minimax-m3-mxfp8': {'inode':12320800,'revision':'ca165902e868fd015fab5acaff776643be00dc6e','files':159,'dirs':7,'bytes':443776023939,
  'container':'634daeb70a3ae9aa7403ec8d2256984de9cfe8b5521b839de16a1707164f7522','image':'sha256:362917ee2a4188bdb827c5b97d0f9a8a5c5dd1663b2ea43ad1ef6daa55a0a768','name':'minimax-m3-mxfp8-poc','service':'minimax-m3-mxfp8-poc','compose':'minimax-m3-poc.compose.yml'},
 '/data/models/qwen3-30b-a3b-instruct-2507': {'inode':12320782,'revision':'0d7cf23991f47feeb3a57ecb4c9cee8ea4a17bfe','files':56,'dirs':4,'bytes':61084266282,
  'container':'321ee2110e2e0130739ca51fe192b23d746ecefca76e746c9e2df3fd8a799153','image':'sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3','name':'sglang-qwen3-30b-a3b-instruct-2507','service':'sglang-qwen3-30b','compose':'sglang-qwen3-30b.compose.yml'},
 '/data/models/qwen3-0.6b-smoke': {'inode':12320770,'revision':'c1899de289a04d12100db370d81485cdf75e47ca','files':22,'dirs':4,'bytes':1519210490,
  'container':'6cfa91273417ad7f5ae23a471aaf7b2f5be47bfab74550df93b71587fb3fb71f','image':'sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3','name':'sglang-smoke-qwen3-0.6b','service':'sglang-smoke','compose':'sglang-smoke.compose.yml'},
 '/data/models-large/qwen3-coder-next-fp8': {'inode':119275521,'revision':'da6e2ed27304dd39abadd9c82ef50e8de67bdd4c','payload_files':48,'payload_bytes':80407722953},
}


def inspect_tree(root, helper):
    snapshot=helper.dry_run(root); plan=OBSOLETE[root]
    reasons=[]
    if snapshot['root_identity']['ino']!=plan['inode']: reasons.append('historical_root_inode_drift')
    if 'files' in plan and (snapshot['files'],snapshot['directories'],snapshot['apparent_file_bytes'])!=(plan['files'],plan['dirs'],plan['bytes']):
        reasons.append('historical_file_count_or_size_drift')
    entries={}; revisions=[]; metadata_files={}
    for current, dirs, files in os.walk(root,followlinks=False):
        for entry in [Path(current),*[Path(current)/name for name in files]]:
            info=entry.lstat(); entries[str(entry)]=snap(info)
            if entry.suffix=='.metadata' and info.st_size<16384:
                # HF acquisition metadata is small; no weight reads or copies.
                data,record=read_untrusted_reference(str(entry),model_metadata=True)
                value=data.decode().splitlines()
                assert value and re.fullmatch('[a-f0-9]{40}',value[0]), 'invalid_hf_revision_metadata'
                revisions.append(value[0])
                metadata_files[str(entry)]={'sha256':record['sha256'],'metadata':snap(info),'authority':'UNTRUSTED_ACQUISITION_METADATA_CHECKED_AGAINST_REVIEWED_REVISION'}
    if 'files' in plan:
        if not revisions or set(revisions)!={plan['revision']}: reasons.append('acquisition_revision_mismatch_or_unavailable')
    else:
        receipt='/data/services/llm-manager/acquisition/qwen3-coder-next-fp8.complete.json'
        value=json.loads(raw(receipt))
        if not (value.get('complete') is True and value.get('model_root')==root and value.get('repo_id')=='Qwen/Qwen3-Coder-Next-FP8' and value.get('revision')==plan['revision'] and value.get('artifact_count')==48 and value.get('total_bytes')==plan['payload_bytes']):
            reasons.append('coder_completion_identity_mismatch')
        payload=[v for p,v in entries.items() if stat.S_ISREG(v['mode']) and not p.endswith('.lock')]
        if len(payload)!=48 or sum(v['size'] for v in payload)!=plan['payload_bytes']:
            reasons.append('coder_payload_count_or_size_drift')
        expected_payload={str(Path(root)/a['path']):a['size_bytes'] for a in value['artifacts']}
        actual_payload={p:v['size'] for p,v in entries.items() if stat.S_ISREG(v['mode']) and not p.endswith('.lock')}
        if actual_payload!=expected_payload: reasons.append('coder_payload_manifest_names_or_sizes_drift')
        seal_path='/data/services/llm-manager/acquisition/f1d-qwen-seal-evidence.json'
        if value.get('evidence')!=seal_path or value.get('evidence_sha256')!=digest(seal_path):
            reasons.append('coder_seal_receipt_binding_mismatch')
        seal=json.loads(raw(seal_path)); sealed={r['path']:r['identity'] for r in seal['after'] if r['path']==root or r['path'].startswith(root+'/')}
        if set(sealed)!=set(entries): reasons.append('coder_sealed_entry_set_drift')
        for path,expected in sealed.items():
            actual=entries.get(path,{})
            pairs={'ino':'inode','uid':'uid','gid':'gid','nlink':'nlink','size':'size_bytes','mtime_ns':'mtime_ns','ctime_ns':'ctime_ns'}
            if any(actual.get(k)!=expected[v] for k,v in pairs.items()) or actual.get('mode',0)&0o7777!=int(expected['mode'],8):
                reasons.append('coder_sealed_metadata_drift'); break
    assert helper.dry_run(root)==snapshot, 'tree_changed_during_metadata_scan'
    return {'snapshot':snapshot,'entries':entries,'metadata_files':metadata_files,
            'revision_counts':{v:revisions.count(v) for v in set(revisions)},'blockers':reasons}


def process_nonuse(trees):
    identities={root:{(v['dev'],v['ino']) for v in tree['entries'].values()} for root,tree in trees.items()}
    hits={root:[] for root in trees}; unknown=[]; inspected=0
    locks=Path('/proc/locks').read_text().splitlines()
    for line in locks:
        parts=line.split()
        for word in parts:
            if re.fullmatch(r'[0-9a-fA-F]+:[0-9a-fA-F]+:[0-9]+',word):
                major,minor,inode=word.split(':'); identity=(os.makedev(int(major,16),int(minor,16)),int(inode))
                for root,ids in identities.items():
                    if identity in ids: hits[root].append({'kind':'acquisition_or_file_lock','identity':list(identity)})
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name)==os.getpid(): continue
        try:
            start=(proc/'stat').read_text().rsplit(')',1)[1].split()[19]
            inspected+=1
            for link in [proc/'cwd',proc/'root',*list((proc/'fd').iterdir())]:
                try: info=link.stat()
                except FileNotFoundError: continue
                for root,ids in identities.items():
                    if (info.st_dev,info.st_ino) in ids: hits[root].append({'pid':int(proc.name),'kind':'fd_cwd_root','entry':link.name})
            for line in (proc/'maps').read_text().splitlines():
                fields=line.split(None,5)
                if len(fields)<5: continue
                major,minor=fields[3].split(':'); identity=(os.makedev(int(major,16),int(minor,16)),int(fields[4]))
                for root,ids in identities.items():
                    if identity in ids: hits[root].append({'pid':int(proc.name),'kind':'mmap'})
            # Inspect privately, emit only the matching target/PID, never argv.
            command=(proc/'cmdline').read_bytes()
            for root in trees:
                if root.encode() in command or Path(root).name.encode() in command:
                    hits[root].append({'pid':int(proc.name),'kind':'job_command_reference'})
            after=(proc/'stat').read_text().rsplit(')',1)[1].split()[19]
            if start!=after: unknown.append({'pid':int(proc.name),'reason':'pid_reused'})
        except (FileNotFoundError,ProcessLookupError): continue
        except (OSError,ValueError) as exc: unknown.append({'pid':int(proc.name),'reason':type(exc).__name__})
    return {'inspected_processes':inspected,'hits':hits,'visibility_unknown':unknown,'lock_table_read':True}


def container_review(trees):
    values=[container(cid) for cid in run(['docker','ps','-a','--quiet','--no-trunc']).split()]
    byid={value['Id']:value for value in values}; result={}
    for root in trees:
        plan=OBSOLETE[root]; result[root]={'approved_stopped_container':None,'other_references':[],'blockers':[]}
        approved=plan.get('container')
        if approved:
            value=byid.get(approved)
            if value is None:
                result[root]['approved_stopped_container']={'id':approved,'state':'ALREADY_ABSENT'}
                if any(v['Name'].lstrip('/')==plan['name'] for v in values): result[root]['blockers'].append('name_reused_new_unapproved_id')
            else:
                labels=value['Labels'] or {}; mounts=sorted((m['Source'],m['Destination'],m['RW']) for m in value['Mounts'])
                expected_file='/data/services/llm-manager/compose/'+plan['compose']
                expected_mounts={('/data/models','/data/models',False),('/data/hf-cache','/data/hf-cache',True),('/data/logs','/data/logs',True)}
                ok=(value['Name']=='/'+plan['name'] and value['Image']==plan['image'] and value['State']['Status']=='exited' and value['State']['Pid']==0 and not value['State']['Running'] and value['RestartPolicy']['Name']=='no' and labels.get('com.docker.compose.project')=='compose' and labels.get('com.docker.compose.service')==plan['service'] and labels.get('com.docker.compose.project.config_files')==expected_file and set(mounts)==expected_mounts and all(m['Type']=='bind' and m['Propagation']=='rprivate' for m in value['Mounts']))
                result[root]['approved_stopped_container']={'id':approved,'image':value['Image'],'state':value['State']['Status'],'pid':value['State']['Pid'],'restart':value['RestartPolicy'],'mounts':mounts,'identity_match':ok,'compose':expected_file}
                if not ok: result[root]['blockers'].append('approved_container_identity_drift')
        for value in values:
            if value['Id']==approved: continue
            for mount in value['Mounts']:
                source=mount['Source'].rstrip('/')
                if source==root or root.startswith(source+'/') or source.startswith(root+'/'):
                    result[root]['other_references'].append({'id':value['Id'],'source':source,'running':value['State']['Running']})
    checked={v['approved_stopped_container']['id'] for v in result.values()
             if v['approved_stopped_container'] and v['approved_stopped_container'].get('identity_match') is True}
    for root,row in result.items():
        row['planned_retirement_dependencies']=[r for r in row['other_references'] if r['id'] in checked]
        row['other_references']=[r for r in row['other_references'] if r['id'] not in checked]
        if row['other_references']: row['blockers'].append('other_container_reference_requires_reconciliation')
    return result


def parse_systemd_jobs(text):
    text=text.strip()
    if text in ('','No jobs running.'): return []
    jobs=[]
    for line in text.splitlines():
        fields=line.split()
        assert len(fields)==4 and fields[0].isdigit(), 'systemd_job_metadata_format_unknown'
        jobs.append(dict(zip(('id','unit','type','state'),fields)))
    return jobs


def acquisition_targets(unit_name):
    # Exact project acquisition ownership, not Ubuntu's generic download units.
    return {'f1a-qwen-fast-acquire-20260915.service':
            ['/data/models-large/qwen3-coder-next-fp8']}.get(unit_name,[])


def reference_review(trees):
    candidates=[Path('/etc/llm-server/control.json'),Path('/data/services/llm-manager/deployment-instance.json'),
                Path('/data/services/llm-manager/active/active.json'),Path('/run/llmctl/recovery.json')]
    for folder in ['/data/services/llm-manager/compose','/data/services/llm-manager/acquisition',
                   '/data/build/f1a-qwen-20260915/evidence']:
        directory=Path(folder)
        if directory.exists():
            candidates.extend(p for p in directory.iterdir() if p.suffix in ('.json','.yml','.yaml') and not p.is_symlink())
    seal=Path('/data/services/llm-manager/acquisition/f1d-qwen-seal-evidence.json')
    if seal.exists() and seal not in candidates: candidates.append(seal)
    result={root:[] for root in trees};unknown=[]
    for path in sorted(set(candidates)):
        try:
            if str(path) in READ_ONLY_REFERENCE_PATHS:
                content,_=read_untrusted_reference(str(path))
            else: content=raw(path)
        except Exception as exc:
            unknown.append({'path':str(path),'reason':type(exc).__name__}); continue
        for root in trees:
            if root.encode() in content or Path(root).name.encode() in content:
                classification='BLOCKED_CURRENT_OPERATIONAL_REFERENCE'
                if '/compose/' in str(path): classification='PROPOSED_OBSOLETE_OPERATIONAL_COMPOSE_RETIREMENT'
                elif '/data/build/f1a-qwen-20260915/evidence/' in str(path) or path.name=='f1d-qwen-seal-evidence.json': classification='PRESERVE_HISTORICAL_PROVENANCE'
                elif path.name=='qwen3-coder-next-fp8.complete.json': classification='PROPOSED_OBSOLETE_COMPLETION_RECEIPT_RETIREMENT'
                result[root].append({'path':str(path),'sha256':hashlib.sha256(content).hexdigest(),'metadata':snap(path.stat()),'bytes':len(content),'classification':classification})
    units=json.loads(run(['systemctl','list-units','--all','--output=json','--no-pager']))
    jobs=parse_systemd_jobs(run(['systemctl','list-jobs','--no-legend','--no-pager']))
    relevant=[]
    for unit in units:
        name=unit.get('unit','')
        targets=acquisition_targets(name)
        if targets:
            relevant.append({**{k:unit.get(k) for k in ('unit','load','active','sub')},'targets':targets,'classification':'EXACT_PROJECT_ACQUISITION_OWNER'})
    return {'references':result,'visibility_unknown':unknown,'relevant_units':relevant,'jobs':jobs,
            'coder_seal_at_expected_acquisition_path':seal.exists()}


def cleanup_dry_run():
    assert CLEANUP_IDLE_RELEASE is True, 'postboot_worker2_release_required'
    guard(); controls=control_ready(); idle()
    helper=types.ModuleType('c1_scoped_cleanup');exec(compile(C1_CODE,'c1_scoped_cleanup.py','exec'),helper.__dict__)
    with acquire_lease(blocking=False) as lease, temporary_models_parent(lease):
        idle(); running=current(); retained=preservation(); before={p:os.statvfs(p).f_bavail*os.statvfs(p).f_frsize for p in ('/','/data','/data/models-large')}
        trees={}; failed={}
        for root in OBSOLETE:
            try: trees[root]=inspect_tree(root,helper)
            except FileNotFoundError: failed[root]={'status':'ABSENCE_OR_MISSING_REQUIRED_METADATA_REQUIRES_REVIEW'}
            except Exception as exc: failed[root]={'status':'BLOCKED','reason':str(exc) if isinstance(exc,(AssertionError,helper.Refused)) else type(exc).__name__}
            if root in trees:
                emit('C1_TREE_IDENTITY_FIRST',root=root,snapshot=trees[root]['snapshot'],blockers=trees[root]['blockers'],non_use='PENDING',apply_authorized=False)
            else: emit('C1_TREE_IDENTITY_FIRST',root=root,**failed[root],apply_authorized=False)
        use=process_nonuse(trees); containers=container_review(trees); references=reference_review(trees)
        report={'utc':time.time(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'trees':trees,'failed':failed,'non_use':use,'containers':containers,'operational_references':references,'running':running,'control':controls,'free_before':before,'apply_authorized':False}
        for root,tree in trees.items():
            if use['hits'][root]: tree['blockers'].append('process_or_lock_reference')
            if use['visibility_unknown']: tree['blockers'].append('process_visibility_unknown')
            tree['blockers'].extend(containers[root]['blockers'])
            if references['visibility_unknown']: tree['blockers'].append('reference_visibility_unknown')
            if any(root in u['targets'] and u['active'] not in ('inactive','failed') for u in references['relevant_units']): tree['blockers'].append('target_acquisition_unit_active')
            if any(root in acquisition_targets(job['unit']) for job in references['jobs']): tree['blockers'].append('target_acquisition_job_pending')
            if any(r['classification']=='BLOCKED_CURRENT_OPERATIONAL_REFERENCE' for r in references['references'][root]): tree['blockers'].append('current_operational_reference_requires_review')
            if not root.startswith('/data/models/') and not references['coder_seal_at_expected_acquisition_path']: tree['blockers'].append('coder_seal_path_requires_reconciliation')
            assert helper.dry_run(root)==tree['snapshot'], 'dry_run_identity_drift'
        lease.validate(); assert preservation()==retained, 'retained_identity_changed_during_dry_run'; guard(); idle()
        save('cleanup-corrected-dry-run.json',report,exclusive=True)
        for root,tree in trees.items():
            emit('C1_TARGET_DRY_RUN',root=root,snapshot=tree['snapshot'],blockers=tree['blockers'],process_hits=use['hits'][root],process_visibility_unknown=len(use['visibility_unknown']),containers=containers[root],references=references['references'][root],status='BLOCKED' if tree['blockers'] else 'READY_FOR_ROOT_REFERENCE_AND_APPLY_REVIEW',apply_authorized=False)
        for root,result in failed.items(): emit('C1_TARGET_DRY_RUN',root=root,**result,apply_authorized=False)
    emit('C1_DRY_RUN_RELEASED',canonical_lease='RELEASED',model_running=True,awaiting='ROOT_FRESH_REPORT_REVIEW_NO_DELETION')


def cleanup_reconcile():
    guard(); idle()
    with acquire_lease(blocking=False) as lease:
        report=json.loads(raw(REPORT/'cleanup-dry-run.json'))
        ancestors={}
        for root in OBSOLETE:
            for path in [*reversed(Path(root).parents),Path(root)]:
                ancestors[str(path)]=snap(path.lstat())
        references=report['operational_references']
        units=[]
        for value in references['relevant_units']:
            detail=run(['systemctl','show',value['unit'],'--property=Id,ActiveState,SubState,MainPID,ControlPID,ControlGroup,Result,RemainAfterExit,FragmentPath'])
            units.append(dict(line.split('=',1) for line in detail.splitlines() if '=' in line))
        value={'ancestors':ancestors,'containers':container_review(OBSOLETE),
               'reference_visibility_unknown':references['visibility_unknown'],
               'related_units':units,'jobs':references['jobs'],
               'processes_inspected':report['non_use']['inspected_processes'],
               'process_visibility_unknown':report['non_use']['visibility_unknown']}
        lease.validate(); guard(); save('cleanup-blocker-details.json',value)
    emit('C1_BLOCKER_DETAILS',**value,canonical_lease='RELEASED',deletion_attempted=False)


READ_ONLY_REFERENCE_PATHS = {
    '/data/build/f1a-qwen-20260915/evidence/'+name for name in
    ('acquisition-status.json','capacity-plan.json','handoff-snapshot.json',
     'helper-sha256.json','hf-pinned-metadata.json','metadata-proof.json','startup.json')
} | {'/data/services/llm-manager/compose/'+OBSOLETE[root]['compose']
     for root in OBSOLETE if 'compose' in OBSOLETE[root]}


def read_untrusted_reference(path, model_metadata=False):
    """Read exact historical operands via checked FDs; never deletion authority."""
    if model_metadata:
        assert any(path.startswith(root+'/.cache/huggingface/download/') and path.endswith('.metadata') for root in OBSOLETE if root.startswith('/data/models/')), 'metadata_not_in_allowlisted_tree'
        assert '..' not in Path(path).parts, 'metadata_traversal'
    else: assert path in READ_ONLY_REFERENCE_PATHS, 'reference_not_allowlisted'
    descriptors=[]; edges=[]
    try:
        parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        descriptors.append(parent)
        for name in Path(path).parts[1:-1]:
            child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
            descriptors.append(child); edges.append((parent,name,child,snap(os.fstat(child)))); parent=child
        fd=os.open(Path(path).name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC|os.O_NOATIME,dir_fd=parent)
        descriptors.append(fd); before=os.fstat(fd)
        assert stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=8*1024*1024, 'unsafe_reference_type_or_size'
        data=os.read(fd,8*1024*1024+1)
        assert len(data)==before.st_size and snap(before)==snap(os.fstat(fd))==snap(os.stat(Path(path).name,dir_fd=parent,follow_symlinks=False)), 'reference_read_drift'
        for directory,name,opened,expected in edges:
            assert snap(os.fstat(opened))==expected==snap(os.stat(name,dir_fd=directory,follow_symlinks=False)), 'reference_ancestor_drift'
        return data,{'metadata':snap(before),'sha256':hashlib.sha256(data).hexdigest(),
                     'trust':'READ_ONLY_HISTORICAL_INPUT_NOT_DELETION_AUTHORITY'}
    finally:
        for fd in reversed(descriptors): os.close(fd)


def cleanup_reference_review():
    guard(); idle()
    with acquire_lease(blocking=False) as lease:
        records={}; seal=json.loads(raw('/data/services/llm-manager/acquisition/f1d-qwen-seal-evidence.json'))
        for path in sorted(READ_ONLY_REFERENCE_PATHS):
            data,record=read_untrusted_reference(path)
            record['target_references']=[root for root in OBSOLETE if root.encode() in data or Path(root).name.encode() in data]
            if path.endswith('/acquisition-status.json'):
                value=json.loads(data)
                record['safe_fields']={k:value[k] for k in ('repo_id','revision','model_root','complete','state','total_bytes','artifact_count') if k in value and isinstance(value[k],(str,int,bool,type(None)))}
                record['matches_original_f1d_status_hash']=record['sha256']==seal['status']['sha256']
            records[path]=record
        lease.validate(); guard(); save('cleanup-reference-details.json',records)
    emit('C1_REFERENCE_DETAILS',records=records,canonical_lease='RELEASED',deletion_attempted=False)


@contextmanager
def temporary_models_parent(lease):
    """Root-reviewed temporary fence of one literal inode; restore on every exit."""
    lease.validate(); guard()
    descriptors=[]; changed=False
    try:
        top=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC);descriptors.append(top)
        data=os.open('data',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=top);descriptors.append(data)
        parent=os.open('models',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=data);descriptors.append(parent)
        info=os.fstat(parent); before=snap(info)
        assert (info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(2065,12320769,1000,1001,0o2775), 'reviewed_models_parent_identity_drift'
        assert snap(os.stat('models',dir_fd=data,follow_symlinks=False))==before, 'models_parent_named_identity'
        xattrs={name:os.getxattr(parent,name) for name in os.listxattr(parent)}
        changed=True
        os.fchown(parent,0,1001);os.fchmod(parent,0o2755);os.fsync(parent)
        info=os.fstat(parent)
        assert (info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(2065,12320769,0,1001,0o2755), 'temporary_parent_protection_failed'
        lease.validate();guard()
        emit('C1_TEMPORARY_PARENT_PROTECTED',path='/data/models',dev=2065,inode=12320769,uid=0,gid=1001,mode='02755',recursive=False,restore_on_exit=True)
        yield before
    finally:
        try:
            if changed:
                # Restore the exact held inode even if the operation failed.
                info=os.fstat(parent);assert (info.st_dev,info.st_ino)==(2065,12320769), 'restoration_fd_identity'
                os.fchown(parent,1000,1001);os.fchmod(parent,0o2775);os.fsync(parent)
                info=os.fstat(parent)
                assert (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(1000,1001,0o2775), 'models_parent_restore_failed'
                named=os.stat('models',dir_fd=data,follow_symlinks=False)
                assert (named.st_dev,named.st_ino)==(2065,12320769), 'models_parent_path_changed'
                assert {name:os.getxattr(parent,name) for name in os.listxattr(parent)}==xattrs, 'models_parent_xattrs_changed'
                emit('C1_TEMPORARY_PARENT_RESTORED',path='/data/models',dev=2065,inode=12320769,uid=1000,gid=1001,mode='02775',recursive=False)
        finally:
            for fd in reversed(descriptors):os.close(fd)
            if changed: guard()
