#!/usr/bin/env python3
"""Current image-only migration proposal. No runtime write/lifecycle CLI exists.

Raw configs/owner records remain in memory or protected exact-byte archives.
Selected historical JSON is insufficient to reconstruct any original. These
checks cannot mint native settlement, storage, lease or runtime authority.
"""
from __future__ import annotations

import copy
import datetime
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import stat

BOOT = '424b2823-b27c-4b3c-88b3-0ae9f4e7106d'
OLD_BOOT = 'a64e7b47-ed94-4ed2-a26c-01c030423148'
OWNER = 'IMAGE21-RUNTIME-20260923'
CID = '7978d53e33a5502ba7a3b6cf5e6d10a63cfec60829950e565b9a2c4a111579cc'
INVOCATION = 'ba8d3f2e0172482194d2b4b8743aecae'
NETWORK_ID = '4d21a85d6dc326cc90d68e0f017d2e58fb96f5664e55384c1f3f337661d7ef80'
API_OWNER = {'pid':11783,'pgid':11783,'startTicks':2769,'invocation':'add9855d26bf4eab96b7574c7f0c8af8'}
EXTERNAL_GPU = 'GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23'
READING_GPU = 'GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf'
PLATFORM = 'sha256:50a3bfd20fc931f05fc5fc919b0445abbce30d5c7716424d697a7ab6708c08ef'
CONFIG = 'sha256:3f6178faa74c4a9bcb95ed4304dbee57473efa8913a793e067014af4a98281ad'
PARENT = 'sha256:dafbccb763cff6a6aa3777c7c0a8cc185d838bd4b9f61bec8007f57f2c7233f8'
REVISION = '790c92633540aa0cb11d9abf19eb46d861714758'
SOURCE = '0cd8be351d0825488f4b81c8931167bbab618eca'
BASE = '/data/services/image21-runtime-20260923'
MODEL = '/data/models-large/qwen-image-2.1-'+REVISION
ARCHIVE = '/data/services/h044-evidence/I-image03-current-owner-424b2823-f7c7a4d8'
API = '/etc/llm-server/image-api.json'
PATHS = {'config':BASE+'/config.json','state':BASE+'/state.json',
         'operation':BASE+'/operation.json','recovery':BASE+'/recovery.json',
         'api':API,'checkpoint':MODEL+'/CHECKPOINT-RECEIPT.json'}
EXPECTED = {
    'config':'1800f1eeecb5cc20b08545e46b17811e36b412a97bcadf0ba50e00c5df07534a',
    'state':'64410770122b0bfd1e0a73043e35f08dce83c789ee3d56027a4ca386dc129e6b',
    'operation':'74583bebf9e3eeaaca2af50a603a1fd9b69b8512817c06746a1996a3c89689ef',
    'recovery':'627033bd0ab6b260c9d92e59fa3712b8097b28372b140a59272aeef14a2b413c',
    'api':'9c001640638833950fca3a60363f64e93c71b6b5f0113da792eec0256d99e8b3',
    'checkpoint':'b662d87e521153a396639e574267f1cc0ffa709009392d482a0fcb00ad040b73'}


class Refused(ValueError): pass
def require(ok,code):
    if not ok: raise Refused(code)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def strict(raw):
    require(type(raw) is bytes and len(raw)<=262144,'raw_size')
    def pairs(items):
        d={}
        for k,v in items:
            require(k not in d,'duplicate_key'); d[k]=v
        return d
    def bad(_): raise Refused('nonfinite')
    try: value=json.loads(raw,object_pairs_hook=pairs,parse_constant=bad)
    except (UnicodeError,ValueError,RecursionError): raise Refused('raw_json') from None
    def bound(v,depth=0):
        require(depth<=20,'raw_depth')
        if type(v) in (dict,list):
            require(len(v)<=1024,'raw_count')
            for child in (v.values() if type(v) is dict else v): bound(child,depth+1)
        elif type(v) is str: require(len(v)<=65536,'raw_string')
    bound(value); require(type(value) is dict,'raw_object'); return value
def signature(s):
    return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)


class ProtectedFile:
    """Held raw-file descriptor, exact protected ancestry and named-FD CAS.

    trusted_uid is a synthetic Mac-test seam only; production always uses0.
    No command-line path, uid or expected-hash override is provided.
    """
    def __init__(self,path,*,trusted_uid=0,fixture_root=None):
        p=Path(path); require(p.is_absolute() and '..' not in p.parts,'protected_path')
        if fixture_root is None:
            root=Path('/'); parts=p.parts[1:-1]
        else:
            # Explicit in-process synthetic fixture trust boundary only.
            root=Path(fixture_root)
            require(trusted_uid!=0 and trusted_uid==os.getuid() and root.is_absolute()
                    and '..' not in root.parts and root in p.parents,'fixture_boundary')
            parts=p.relative_to(root).parts[:-1]
        self.directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW); self.fd=None
        initial=os.fstat(self.directory)
        require(stat.S_ISDIR(initial.st_mode) and initial.st_uid in (0,trusted_uid)
                and not initial.st_mode&0o022,'protected_root')
        self.chain=[]; self.directories=[self.directory]
        self.name=p.name; self.path=str(p); self.uid=trusted_uid
        try:
            for part in parts:
                child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=self.directory)
                s=os.fstat(child)
                if s.st_uid not in (0,trusted_uid) or s.st_mode&0o022:
                    os.close(child); raise Refused('protected_ancestry')
                named=os.stat(part,dir_fd=self.directory,follow_symlinks=False)
                require(signature(s)==signature(named),'directory_cas')
                self.chain.append((self.directory,part,child,(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid)))
                self.directories.append(child); self.directory=child
            self.before=os.stat(self.name,dir_fd=self.directory,follow_symlinks=False)
            s=self.before
            require(stat.S_ISREG(s.st_mode) and s.st_uid==trusted_uid and s.st_nlink==1
                    and not s.st_mode&0o022 and s.st_size<=262144,'protected_file')
            self.fd=os.open(self.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.directory)
            self.check(); self.raw=os.read(self.fd,262145)
            require(len(self.raw)==s.st_size,'protected_size'); self.check()
        except BaseException:
            self.close(); raise
    def check(self):
        for parent,name,child,identity in self.chain:
            held=os.fstat(child); named=os.stat(name,dir_fd=parent,follow_symlinks=False)
            sig=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid)
            require(sig(held)==sig(named)==identity,'protected_ancestor_cas')
        require(self.fd is not None and signature(self.before)==signature(os.fstat(self.fd))
            and signature(self.before)==signature(os.stat(self.name,dir_fd=self.directory,follow_symlinks=False)),
            'protected_fd_cas')
    def close(self):
        if self.fd is not None: os.close(self.fd); self.fd=None
        for directory in reversed(self.directories): os.close(directory)
        self.directories=[]; self.directory=None
    def __enter__(self): return self
    def __exit__(self,*_): self.close()


@dataclass(repr=False)
class Snapshot:
    files: dict = field(repr=False)
    boot: str = BOOT
    def raw(self):
        self.check(); return {k:v.raw for k,v in self.files.items()}
    def check(self):
        require(self.boot==BOOT and set(self.files)==set(PATHS),'snapshot_identity')
        for name,value in self.files.items():
            require(value.path==PATHS[name],'snapshot_path'); value.check()
            require(sha(value.raw)==EXPECTED[name],'current_file_hash_changed')
    def close(self):
        for value in self.files.values(): value.close()


def validate_archive_go(go,source_sha,now):
    require(type(go) is dict and go.get('status')=='GO' and go.get('issuedBy')=='root'
        and go.get('phase')=='I-image03' and go.get('bootId')==BOOT
        and go.get('sourceSha256')==source_sha and go.get('expectedFileSha256')==EXPECTED
        and go.get('archiveDestination')==ARCHIVE and type(go.get('maximumInvocations')) is int
        and go['maximumInvocations']==1 and go.get('runtimeCASPermitted') is False
        and go.get('actions')==['read_current_six_raw','archive_exact_originals_only'],'archive_root_go')
    before=datetime.datetime.fromisoformat(go['notBeforeUtc']); end=datetime.datetime.fromisoformat(go['expiresUtc'])
    require(before.tzinfo is not None and end.tzinfo is not None and before<=now<end
            and (end-before).total_seconds()<=120,'archive_go_time')


def _archive_go(go):
    with ProtectedFile(str(Path(__file__).absolute())) as source:
        validate_archive_go(go,sha(source.raw),datetime.datetime.now(datetime.timezone.utc))
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT,'archive_boot')


def read_current_files(go):
    """Future root helper entry only; no export of raw content/credentials."""
    require(os.geteuid()==0,'root_required'); _archive_go(go)
    boot=lambda:Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    require(boot()==BOOT,'current_boot'); files={}
    try:
        for name,path in PATHS.items(): files[name]=ProtectedFile(path)
        snap=Snapshot(files); snap.check(); require(boot()==BOOT,'boot_changed'); return snap
    except BaseException:
        for value in files.values(): value.close()
        raise


def _capabilities(lease,storage):
    # Native guard objects, never booleans or a JSON assertion. This helper
    # does not import/mint them. A reviewed future adapter must supply them.
    require(type(lease).__module__=='common.lifecycle_lease'
            and type(lease).__name__=='LifecycleLease','canonical_lease_required')
    lease.validate()
    require(type(storage).__module__=='install.storage_io'
            and type(storage).__name__=='AnchoredRoot','registered_storage_anchor_required')
    storage.check()


def archive_originals(snapshot,lease,storage,go):
    """Future exact archive mutation only; runtime files cannot be written here.

    Caller must obtain NEW source-bound read/archive GO, registered topology,
    root-disk guards and canonical lease through the reviewed original graph.
    The destination must already be created by that reviewed storage owner.
    """
    require(os.geteuid()==0,'root_required'); _archive_go(go); _capabilities(lease,storage); snapshot.check()
    require(str(storage.path)==ARCHIVE,'archive_registered_path')
    fd=os.dup(storage.fileno())
    try:
        s=os.fstat(fd)
        require(s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700,'archive_directory')
        require(os.listdir(fd)==[],'archive_exclusive_empty')
        names={k:k+'.original.json' for k in PATHS}
        for key,name in names.items():
            _archive_go(go); _capabilities(lease,storage); storage.check(name); snapshot.check()
            out=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
            try:
                info=os.fstat(out)
                require(info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1,'archive_file')
                view=memoryview(snapshot.files[key].raw)
                while view:
                    count=os.write(out,view); require(count>0,'archive_write'); view=view[count:]
                os.fsync(out)
                named=os.stat(name,dir_fd=fd,follow_symlinks=False)
                require(signature(os.fstat(out))==signature(named) and named.st_size==len(snapshot.files[key].raw),'archive_fd_cas')
            finally: os.close(out)
        os.fsync(fd); snapshot.check(); _archive_go(go); _capabilities(lease,storage)
        for key,name in names.items():
            with ProtectedFile(ARCHIVE+'/'+name) as file:
                require(file.raw==snapshot.files[key].raw and sha(file.raw)==EXPECTED[key],'archive_bytes')
        return {'archivePath':ARCHIVE,'fileSha256':{names[k]:EXPECTED[k] for k in PATHS},
                'runtimeCASPermitted':False,'runtimeMutation':'NOT_IMPLEMENTED'}
    finally: os.close(fd)


@dataclass(repr=False)
class Proposal:
    runtime_successor: bytes = field(repr=False)
    api_successor: bytes = field(repr=False)
    before: dict
    def public(self):
        return {'schema':'h044-current-image-owner-migration-proposal-v1','executable':False,
            'runtimeWriteAuthority':False,'originalFileSha256':self.before,
            'successorWholeFileSha256':{'config':sha(self.runtime_successor),'api':sha(self.api_successor)},
            'deltas':{'runtime':{'gpu_uuid':EXTERNAL_GPU},'api':{'runtime_image_digest':PLATFORM}},
            'archiveRequiredBeforeAnyCAS':ARCHIVE,'oldBoot':OLD_BOOT,
            'priorPid':{'pid':13527,'startTicks':2853,'authority':'NONE; never signal or adopt on current boot'},
            'unchanged':['state','operation','recovery','checkpoint','credentials','profiles','peers','weights'],
            'blockers':['actual protected raw recovery/state/operation schema and owner qualification',
                'fresh current image API owner and peer invariance','native owned descendant absence',
                'registered topology/root disk/held anchors/canonical lease/mandatory hardware/resource guards',
                'actual cached platform/config relationship and in-container overlay verification',
                'root-reviewed explicit settlement transition and successor CAS/rollback writer',
                'separate R normal-generation-only protected qualification'],
            'qualification':'SOURCE_ONLY; Linux/native/lifecycle/model/generation NOT_TESTED'}


def validate_evidence(e):
    require(type(e) is dict and e.get('origin')=='CURRENT_ROOT_PROTECTED_READ'
            and e.get('bootBefore')==e.get('bootAfter')==BOOT,'evidence_boot')
    c=e.get('container',{})
    require(c.get('id')==CID and c.get('owner')==OWNER and c.get('invocation')==INVOCATION
            and c.get('image')==c.get('configImage')==PLATFORM and c.get('gpu')==READING_GPU
            and c.get('status')=='exited' and c.get('running') is False
            and type(c.get('pid')) is int and c['pid']==0
            and type(c.get('exitCode')) is int and c['exitCode']==255,'current_container_tuple')
    a=e.get('apiOwner',{})
    require(a.get('boot')==BOOT and a.get('unit')=='llm-image-api.service'
            and a.get('cgroup')=='0::/system.slice/llm-image-api.service'
            and a.get('exe')=='/usr/bin/python3.12' and a.get('stable') is True
            and all(type(a.get(k)) is int and a[k]==API_OWNER[k] for k in ('pid','pgid','startTicks'))
            and a.get('invocation')==API_OWNER['invocation'],'current_api_owner')
    require(e.get('peerBeforeFileSha256')==e.get('peerAfterFileSha256')
            and type(e.get('peerBeforeFileSha256')) is dict and bool(e['peerBeforeFileSha256'])
            and all(type(v) is str and len(v)==64 and all(ch in '0123456789abcdef' for ch in v)
                    for v in e['peerBeforeFileSha256'].values()),'peer_invariance')
    hardware=e.get('hardware',{})
    require(hardware.get('gpuUuid')==EXTERNAL_GPU and hardware.get('boot')==BOOT
            and hardware.get('stableReadingGpu')==READING_GPU,'external_gpu_evidence')
    require(e.get('apiHealthOrReadyInvoked') is False,'admission_closed')


def propose(raw,evidence,source_maps,*,expected=EXPECTED):
    """Pure proposal using full raw bytes; expected override is tests ONLY."""
    require(set(raw)==set(PATHS) and set(expected)==set(PATHS),'six_originals_required')
    require(all(type(raw[k]) is bytes and sha(raw[k])==expected[k] for k in PATHS),'six_file_cas')
    validate_evidence(evidence); values={k:strict(v) for k,v in raw.items()}
    c,s,o,r,a,q=(values[k] for k in ('config','state','operation','recovery','api','checkpoint'))
    require(type(c.get('schema_version')) is int and c['schema_version']==1 and c.get('owner')==OWNER
        and c.get('gpu_uuid')==READING_GPU and c.get('image_id')==PLATFORM
        and c.get('checkpoint_revision')==REVISION and c.get('source_commit')==SOURCE
        and c.get('network_id')==NETWORK_ID
        and c.get('checkpoint_path')==MODEL and c.get('checkpoint_receipt_sha256')==expected['checkpoint'], 'config_schema_owner_pins')
    require(type(source_maps) is tuple and len(source_maps)==2
        and c.get('source_sha256')==source_maps[0] and c.get('release_source_sha256')==source_maps[1]
        and len(source_maps[0])+len(source_maps[1])==37,'source_closure37')
    require(type(s.get('schema_version')) is int and s['schema_version']==1 and s.get('owner')==OWNER
        and s.get('run_id')==INVOCATION and s.get('container',{}).get('id')==CID
        and s['container'].get('image_id')==PLATFORM and s.get('phase')=='loading' and s.get('warm') is False,
        'raw_state_schema_owner')
    n=s.get('native_generation',{})
    require(type(n.get('pid')) is int and n['pid']==13527 and type(n.get('Pid')) is int and n['Pid']==13527
        and type(n.get('start_ticks')) is int and n['start_ticks']==2853
        and n.get('StartedAt')=='2026-10-01T02:07:48.872235338Z','raw_prior_native_tuple')
    for record in (o,r):
        require(record.get('boot')==OLD_BOOT and record.get('status')=='active'
                and record.get('gpu_uuid')==READING_GPU and type(record.get('pid')) is int and record['pid']>0
                and type(record.get('token')) is str and len(record['token'])==32
                and all(ch in '0123456789abcdef' for ch in record['token']),'raw_prior_owner_capability')
    # The original operation schema has no process-stamp field. Recovery does.
    process=r.get('process',{})
    require(type(process) is dict and process.get('pid')==r['pid']
            and type(process.get('start_ticks')) is int and process['start_ticks']>0,'raw_prior_recovery_process_schema')
    require(o.get('invocation_id')==INVOCATION and o.get('action')=='start'
            and o.get('recovery')==r.get('token')
            and r.get('phase') in ('reset','restart') and r.get('child_start') in (None,INVOCATION),
            'raw_operation_recovery_schema')
    require(type(a.get('schema_version')) is int and a['schema_version']==1
        and a.get('model_id')=='Qwen/Qwen-Image-2.1' and a.get('runtime_revision')==SOURCE
        and a.get('model_revision')==REVISION and a.get('runtime_image_digest')==PARENT
        and type(a.get('profiles')) is list,'api_schema_identity')
    require(q.get('status')=='COMPLETE_VERIFIED' and q.get('revision')==REVISION
        and type(q.get('file_count')) is int and q['file_count']==26
        and type(q.get('total_bytes')) is int and q['total_bytes']==33131614782,'checkpoint_receipt')
    rc,ac=copy.deepcopy(c),copy.deepcopy(a); rc['gpu_uuid']=EXTERNAL_GPU; ac['runtime_image_digest']=PLATFORM
    encode=lambda v:(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode()
    return Proposal(encode(rc),encode(ac),{PATHS[k]:expected[k] for k in PATHS})


def request():
    return {'schema':'h044-current-image-reconcile-source-request-v1','authorization':'SOURCE_ONLY_NO_GO',
        'expectedBoot':BOOT,'originalFileSha256':{PATHS[k]:EXPECTED[k] for k in PATHS},
        'archiveDestination':ARCHIVE,'runtimeWriter':'NOT_IMPLEMENTED; schema/guard/settlement review required',
        'priorStateAuthority':'Old boot/PID13527/start2853 is archival only; no signal, reuse, reset or latch clear',
        'readMode':'future exact protected raw FD reads in memory; no values, individual credential hashes or reconstructed state export',
        'currentApiHealthReady':'CLOSED; can mutate admission',
        'sourceOnly':True,'normalGenerationOnly':True,'rawPreCropArtifact':'NOT_CAPTURED',
        'globalAllThreeGate':'CLOSED; distinct protected R normal-generation-only contract needed'}


if __name__=='__main__':
    # Deliberately no Linux import, read/archive/CAS, credentials, or lifecycle.
    print(json.dumps(request(),indent=2,sort_keys=True))
