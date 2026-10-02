#!/usr/bin/env python3
"""Protected image reconciliation writer; live entry requires a new finite root GO.

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
ARCHIVE = '/data/services/h044-evidence/I-image04-current-owner-424b2823'
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
    # Compare canonical objects, not Python module/name strings. validate()
    # checks the lifecycle module's private active-capability registry.
    from common.lifecycle_lease import LifecycleLease, _validate_borrowed_lease
    from install.storage_io import AnchoredRoot
    require(type(lease) is LifecycleLease,'canonical_registered_lease_required')
    _validate_borrowed_lease(lease)
    require(type(storage) is AnchoredRoot,'canonical_storage_anchor_required')
    AnchoredRoot.check(storage)


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
                'runtimeCASPermitted':False,'runtimeMutation':'ARCHIVE_ONLY_LEGACY_INTERFACE; use guarded reconcile_current for writer'}
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
            and ((r.get('phase')=='reset' and r.get('child_start') is None
                  and r.get('prior_invocation') in (None,INVOCATION))
                 or (r.get('phase')=='restart' and o.get('recovery')==r.get('token')
                     and r.get('child_start') in (None,INVOCATION))),
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

# These capabilities are minted by this helper while the exact production
# contexts remain open. None can be constructed from a dictionary/readiness bit.
import contextlib
import importlib
import sys
import time
import uuid
import weakref

RELEASE = '/data/services/releases/h037-image-placement-20260930'
OWNER_SOURCE_SHA = '610397909e66e6242bace7f96f7c179ff9451c14699ed3555dfdbc5e06669438'
OVERLAY = 'dda84e200adcc6a1ee8915e0e993627695477a346c5848fc27f9251c34d04b3b'
_ACTIVE = weakref.WeakKeyDictionary()
_OCI = weakref.WeakKeyDictionary()

class RequirementsMissing(Refused):
    """Safe enumerated requirement; never includes external output or values."""

class RollbackFailed(Refused): pass

class ProductionSession:
    def __new__(cls): raise RequirementsMissing('production_session_must_be_opened')
    def check(self):
        record = _ACTIVE.get(self) if type(self) is ProductionSession else None
        require(record is not None,'registered_production_session_required')
        record.check()
        return record

class CachedOCI:
    def __new__(cls): raise RequirementsMissing('cached_oci_must_be_read_from_protected_fds')
    def check(self):
        pair = _OCI.get(self) if type(self) is CachedOCI else None
        require(pair is not None,'registered_cached_oci_required')
        for file in pair:
            file.check()
            require(os.pread(file.fd,262145,0)==file.raw,'cached_oci_bytes_changed')
        return self


def verify_image_registry_bytes(manifest_raw, config_raw):
    """Image pins only; same small-byte authentication as qwen38_oci.py.

    Platform and config digests authenticate these public metadata bytes. The
    manifest descriptor must point to the actual config FD bytes. No layer,
    weight, parent, daemon display name or descriptor name establishes this join.
    """
    require(type(manifest_raw) is bytes and len(manifest_raw)==7832
            and 'sha256:'+sha(manifest_raw)==PLATFORM,'image_manifest_raw_pin')
    require(type(config_raw) is bytes and 0<len(config_raw)<=262144
            and 'sha256:'+sha(config_raw)==CONFIG,'image_config_raw_pin')
    manifest,config = strict(manifest_raw),strict(config_raw)
    require(type(manifest.get('schemaVersion')) is int and manifest['schemaVersion']==2
            and manifest.get('mediaType')=='application/vnd.oci.image.manifest.v1+json'
            and manifest.get('config')=={'mediaType':'application/vnd.oci.image.config.v1+json',
                'digest':CONFIG,'size':len(config_raw)},'image_manifest_config_join')
    require(config.get('os')=='linux' and config.get('architecture')=='amd64', 'image_config_platform')
    labels=config.get('config',{}).get('Labels',{})
    require(labels.get('org.opencontainers.image.revision')==SOURCE
            and labels.get('io.llmctl.adaptive-idle.overlay-sha256')==OVERLAY,'image_config_source_overlay')
    return {'platformManifest':PLATFORM,'configDigest':CONFIG,'platform':'linux/amd64',
            'qualification':'PUBLIC_METADATA_ONLY'}


@contextlib.contextmanager
def read_cached_oci(go):
    """Root must bind exact cache filenames; no discovery, network or export."""
    paths=go.get('cachedPublicOCIPaths')
    require(type(paths) is dict and set(paths)=={'manifest','config'},'exact_cached_oci_paths_required')
    with ProtectedFile(paths['manifest']) as manifest, ProtectedFile(paths['config']) as config:
        verify_image_registry_bytes(manifest.raw,config.raw)
        capability=object.__new__(CachedOCI); _OCI[capability]=(manifest,config)
        try: yield capability
        finally: _OCI.pop(capability,None)


def replace_scalar(raw,key,old,new):
    """Replace one top-level JSON scalar token; all other bytes are retained."""
    value=strict(raw); require(value.get(key)==old,'field_specific_old_value_changed')
    text=raw.decode('utf-8'); decoder=json.JSONDecoder(); position=text.index('{')+1
    while True:
        while position<len(text) and text[position].isspace(): position+=1
        if text[position]=='}': break
        name,end=decoder.raw_decode(text,position); position=end
        while text[position].isspace(): position+=1
        require(text[position]==':','field_specific_json_colon'); position+=1
        while text[position].isspace(): position+=1
        start=position; current,end=decoder.raw_decode(text,position)
        if name==key:
            require(current==old and type(current) is str,'field_specific_scalar_required')
            return (text[:start]+json.dumps(new,ensure_ascii=False)+text[end:]).encode('utf-8')
        position=end
        while text[position].isspace(): position+=1
        if text[position]=='}': break
        require(text[position]==',','field_specific_json_comma'); position+=1
    raise Refused('field_specific_key_missing')


def encode(value):
    return (json.dumps(value,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode()


def validate_writer_go(go, source_sha, now):
    require(type(go) is dict and go.get('status')=='GO' and go.get('issuedBy')=='root'
            and go.get('phase')=='I-image04' and go.get('bootId')==BOOT
            and go.get('sourceSha256')==source_sha and go.get('expectedFileSha256')==EXPECTED
            and go.get('archiveDestination')==ARCHIVE and type(go.get('maximumInvocations')) is int
            and go['maximumInvocations']==1 and go.get('actions')==[
                'protected_six_raw_archive','stopped_owner_reconcile_CAS','conditional_exact_byte_rollback']
            and go.get('ownerSourceSha256')==OWNER_SOURCE_SHA,'writer_exact_root_go_required')
    try:
        begin=datetime.datetime.fromisoformat(go['notBeforeUtc']); end=datetime.datetime.fromisoformat(go['expiresUtc'])
    except (KeyError,ValueError,TypeError): raise RequirementsMissing('writer_finite_root_go_required') from None
    require(begin.tzinfo is not None and end.tzinfo is not None and begin<=now<end
            and 0<(end-begin).total_seconds()<=180,'writer_root_go_expired')
    for key in ('dockerBinarySha256','daemonId','apiStoppedProofPath','apiStoppedProofSha256',
                'apiBeforeObservationPath','apiBeforeObservationWholeFileSha256'):
        require(type(go.get(key)) is str and bool(go[key]),'writer_source_bound_owner_inputs_required')
    require(type(go.get('peerFileSha256')) is dict and bool(go['peerFileSha256']),
            'exact_peer_file_inputs_required')


def _load_owner():
    """Import closed actual source, then compare class identities directly."""
    with ProtectedFile(BASE+'/source/service.py') as source:
        require(sha(source.raw)==OWNER_SOURCE_SHA,'closed_owner_source_changed')
        with ProtectedFile(PATHS['config']) as config_file:
            require(sha(config_file.raw)==EXPECTED['config'],'closed_config_before_import_changed')
            config=strict(config_file.raw)
        for field,root in (('source_sha256',BASE+'/source'),('release_source_sha256',RELEASE)):
            require(type(config.get(field)) is dict,'source_closure_required_before_import')
            for leaf,digest in config[field].items():
                require(type(leaf) is str and '..' not in Path(leaf).parts and not leaf.startswith('/'),
                    'source_closure_path')
                with ProtectedFile(root+'/'+leaf) as dependency:
                    require(sha(dependency.raw)==digest,'closed_import_source_changed')
        # Owner's ordinary imports use this exact protected closed release.
        if RELEASE+'/scripts' not in sys.path: sys.path.insert(0,RELEASE+'/scripts')
        name='_h044_closed_image_owner'
        require(name not in sys.modules,'closed_owner_import_collision')
        import importlib.util
        spec=importlib.util.spec_from_file_location(name,source.path)
        module=importlib.util.module_from_spec(spec); sys.modules[name]=module
        try: exec(compile(source.raw,source.path,'exec'),module.__dict__)
        except BaseException:
            sys.modules.pop(name,None); raise
        source.check()
        for leaf in config['release_source_sha256']:
            if leaf.startswith('scripts/') and leaf.endswith('.py'):
                name=leaf[len('scripts/'):-3].replace('/','.')
                if name.endswith('.__init__'): name=name[:-9]
                imported=sys.modules.get(name)
                if imported is not None:
                    require(Path(imported.__file__).absolute()==Path(RELEASE+'/'+leaf),
                        'canonical_import_path_changed')
        return module


def _canonical_guards(lease, anchor, mounted, binding, model_lock, operation_lock):
    """Use actual closed guard classes, their registered capabilities and FDs."""
    from common.lifecycle_lease import LifecycleLease, _validate_borrowed_lease
    from install.storage import Storage
    from install.storage_io import AnchoredRoot, MountedStorageGuard, GuardedFile
    from lifecycle.storage_binding import RegisteredStorageBinding, _BoundMountedGuard
    require(type(lease) is LifecycleLease,'canonical_registered_lease_required')
    require(type(binding) is RegisteredStorageBinding and type(binding.storage) is Storage,
            'canonical_registered_storage_binding_required')
    _validate_borrowed_lease(lease,system_root=binding.storage.system_root,trusted_uid=binding.storage.owner)
    require(type(mounted) is _BoundMountedGuard and type(mounted._mounted) is MountedStorageGuard
            and mounted._mounted.storage is binding.storage,'actual_mounted_storage_guard_required')
    require(type(anchor) is AnchoredRoot and anchor._verifier is mounted,
            'actual_registered_anchor_required')
    MountedStorageGuard.__call__(mounted._mounted)
    AnchoredRoot.check(anchor)
    for stream,name in ((model_lock,'recovery.lock'),(operation_lock,'operation.lock')):
        require(type(stream) is GuardedFile and stream.root is anchor and stream.name==name,
                'canonical_image_model_operation_lease_required')
        GuardedFile.check(stream)


def _absent(path, code):
    try: os.stat(path,follow_symlinks=False)
    except FileNotFoundError: return
    except OSError: raise RequirementsMissing(code) from None
    raise RequirementsMissing(code)


def _unit(module, name):
    value=module.run(['/usr/bin/systemctl','show',name,'--property=Id,MainPID,ControlPID,ActiveState,ControlGroup,InvocationID,Job,NeedDaemonReload'],timeout=2).stdout
    require(type(value) is str and len(value)<=8192,'unit_identity_unavailable')
    result=dict(line.split('=',1) for line in value.splitlines() if '=' in line)
    require(result.get('Id')==name and result.get('MainPID')==result.get('ControlPID')=='0'
            and result.get('ActiveState') in ('inactive','failed') and result.get('ControlGroup')==''
            and result.get('Job')=='' and result.get('NeedDaemonReload')=='no','current_unit_owner_not_absent')
    return result


@dataclass(repr=False)
class _SessionRecord:
    module: object
    runtime: object
    anchor: object
    mounted: object
    lease: object
    model_lock: object
    operation_lock: object
    snapshot: Snapshot
    archive: object
    go: dict = field(repr=False)
    source_sha: str
    oci: CachedOCI
    peers: dict = field(repr=False)
    def check(self):
        validate_writer_go(self.go,self.source_sha,datetime.datetime.now(datetime.timezone.utc))
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT,'writer_boot_changed')
        require(type(self.runtime) is self.module.Runtime,'closed_runtime_class_required')
        _canonical_guards(self.lease,self.anchor,self.mounted,self.runtime.binding,self.model_lock,self.operation_lock)
        self.oci.check()
        self.module.verify_source_closure(self.runtime.config)
        self.archive.check()
        for file in self.peers.values():
            file.check(); require(os.pread(file.fd,262145,0)==file.raw,'peer_bytes_changed')

    def physical(self):
        self.check()
        self.runtime.prove_absent(CID) # successful complete Docker inventory
        for pid in (13527,10956): _absent('/proc/'+str(pid),'native_or_prior_owner_pid_present')
        recovery=strict(self.snapshot.files['recovery'].raw)
        _absent('/proc/'+str(recovery['pid']),'prior_recovery_owner_pid_present')
        _absent('/sys/fs/cgroup/system.slice/docker-'+CID+'.scope','native_cgroup_present')
        _unit(self.module,'llm-image-backend.service')
        api=_unit(self.module,'llm-image-api.service')
        require(api==self.go.get('apiStoppedUnit'),'api_generation_changed')
        _absent('/proc/'+str(API_OWNER['pid']),'current_api_owner_present')
        _absent('/sys/fs/cgroup/system.slice/llm-image-api.service','api_cgroup_present')
        # Genuine fresh reading of the dedicated external target, with normal
        # unchanged mandatory policy and resource guards. No fan action.
        old=self.runtime.config
        try:
            self.runtime.config=dict(old,gpu_uuid=EXTERNAL_GPU)
            self.runtime.hardware_observation=self.runtime.probe_hardware()
            self.runtime.require_hardware()
            self.runtime.require_ada_idle()
            device=self.runtime.current_device()
            require(device['free_bytes']*20>=device['total_bytes'],'ada_initial_margin_below_5_percent')
            self.runtime.host_headroom()
            self.runtime.check_ports()
        finally: self.runtime.config=old
        self.check()


@contextlib.contextmanager
def open_production_session(go):
    """Source-only worker never calls this. Privileged finite-GO entry only.

    API pause and exact stopped native removal are separate root-reviewed
    lifecycle actions. Historical observations do not satisfy their absence.
    """
    require(os.geteuid()==0,'writer_root_required')
    with ProtectedFile(str(Path(__file__).absolute())) as source:
        source_sha=sha(source.raw)
        validate_writer_go(go,source_sha,datetime.datetime.now(datetime.timezone.utc))
        module=_load_owner(); runtime=module.Runtime(); runtime.boot=BOOT
        runtime.guards()
        require(runtime.binding.storage.system_root==Path('/') and runtime.binding.storage.owner==0,
                'production_storage_scope_required')
        from install.storage import Storage
        from install.storage_io import AnchoredRoot
        require(type(runtime.binding.storage) is Storage,'canonical_storage_required')
        # Actual production RootPayloadGuard is Storage.root_payload_guard,
        # not a fabricated class or caller assertion. It runs normally.
        Storage.root_payload_guard(runtime.binding.storage,runtime.binding.registry)
        with contextlib.ExitStack() as stack:
            oci=stack.enter_context(read_cached_oci(go))
            proof=stack.enter_context(ProtectedFile(go['apiStoppedProofPath']))
            require(sha(proof.raw)==go['apiStoppedProofSha256'],'source_bound_api_stop_proof_required')
            permit=strict(proof.raw)
            observation=stack.enter_context(ProtectedFile(go['apiBeforeObservationPath']))
            require(sha(observation.raw)==go['apiBeforeObservationWholeFileSha256'],'genuine_api_before_observation_required')
            original=strict(observation.raw)
            require(original.get('schema')=='h044-current-image-api-owner-v1'
                and original.get('boot')==BOOT and original.get('priorOwner')==API_OWNER
                and original.get('sourceSha256')==go.get('apiCanonicalSourceSha256')
                and original.get('unitRawSha256')==go.get('apiUnitRawSha256')
                and original.get('apiConfigWholeFileSha256')==EXPECTED['api'], 'api_before_source_join_required')
            observed=datetime.datetime.fromisoformat(original['observedUtc'])
            require(observed.tzinfo is not None and 0<=(datetime.datetime.now(datetime.timezone.utc)-observed).total_seconds()<=300,
                'api_before_observation_stale')
            require(permit.get('schema')=='h044-current-image-api-stopped-v1'
                and permit.get('boot')==BOOT and permit.get('priorOwner')==API_OWNER
                and permit.get('sourceSha256')==go.get('apiCanonicalSourceSha256')
                and permit.get('unitRawSha256')==go.get('apiUnitRawSha256')
                and permit.get('beforeKernelIdentity')=={'pid':11783,'pgid':11783,'start_ticks':2769,
                    'exe':'/usr/bin/python3.12','cgroup':'0::/system.slice/llm-image-api.service'}
                and permit.get('afterUnit')==go.get('apiStoppedUnit')
                and permit.get('beforeObservationWholeFileSha256')==go.get('apiBeforeObservationWholeFileSha256')
                and type(permit.get('stopExit')) is int and permit['stopExit']==0,
                'genuine_current_api_source_identity_proof_required')
            require(type(go.get('apiCanonicalSourceSha256')) is dict and set(go['apiCanonicalSourceSha256'])==set(API_FILES),
                    'exact_api_source_map_required')
            for path,digest in go['apiCanonicalSourceSha256'].items():
                file=stack.enter_context(ProtectedFile(path)); require(sha(file.raw)==digest,'api_source_changed')
            with ProtectedFile('/etc/systemd/system/llm-image-api.service') as unit:
                require(sha(unit.raw)==go['apiUnitRawSha256'],'api_unit_source_changed')
            with ProtectedFile('/usr/bin/docker') as docker:
                require(sha(docker.raw)==go['dockerBinarySha256'],'docker_source_changed')
            observed=module.run(['/usr/bin/docker','info','--format','{{.ID}}'],timeout=3).stdout.strip()
            require(observed==go['daemonId'],'docker_daemon_changed')
            value=strict(module.run(['/usr/bin/docker','image','inspect','--format',
                '{"id":{{json .Id}},"descriptor":{{json .Descriptor}},"os":{{json .Os}},"architecture":{{json .Architecture}}}',
                PLATFORM],timeout=3).stdout.encode())
            require(value.get('id')==PLATFORM and value.get('descriptor',{}).get('digest')==PLATFORM
                and value.get('os')=='linux' and value.get('architecture')=='amd64','cached_daemon_platform_changed')
            mounted=stack.enter_context(runtime.binding.mounted_guard(module.storage_io))
            anchor=stack.enter_context(AnchoredRoot(BASE,mounted))
            services=stack.enter_context(AnchoredRoot(runtime.binding.path('services'),mounted))
            runtime.storage_anchor=anchor; runtime.services_anchor=services
            model_lock=stack.enter_context(runtime.singleton('recovery.lock'))
            operation_lock=stack.enter_context(runtime.singleton('operation.lock'))
            archive=stack.enter_context(AnchoredRoot(ARCHIVE,mounted))
            files={name:stack.enter_context(ProtectedFile(path)) for name,path in PATHS.items()}
            snapshot=Snapshot(files); snapshot.check()
            peers={path:stack.enter_context(ProtectedFile(path)) for path in go['peerFileSha256']}
            require(all(sha(f.raw)==go['peerFileSha256'][p] for p,f in peers.items()),'peer_source_bound_hash_changed')
            lease=stack.enter_context(module.acquire_lease(blocking=False)); runtime.lease=lease
            session=object.__new__(ProductionSession)
            record=_SessionRecord(module,runtime,anchor,mounted,lease,model_lock,operation_lock,
                snapshot,archive,go,source_sha,oci,peers)
            _ACTIVE[session]=record
            try:
                record.check(); record.physical(); yield session
            finally:
                _ACTIVE.pop(session,None); runtime.lease=None
        runtime.guards()
        Storage.root_payload_guard(runtime.binding.storage,runtime.binding.registry)


def exchange(directory, source, destination):
    """Linux renameat2 EXCHANGE; Darwin RENAME_SWAP is offline fixture QA only.

    No fallback to overwrite-rename. Unsupported ABI/filesystem fails closed.
    Paths are exact leaf names in an already-held protected parent descriptor.
    """
    import ctypes
    require('/' not in source and '/' not in destination,'exchange_leaf_required')
    libc=ctypes.CDLL(None,use_errno=True)
    if sys.platform=='linux': function=getattr(libc,'renameat2',None)
    elif sys.platform=='darwin': function=getattr(libc,'renameatx_np',None)
    else: function=None
    require(function is not None,'atomic_exchange_abi_required')
    function.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
    function.restype=ctypes.c_int
    if function(directory,os.fsencode(source),directory,os.fsencode(destination),2):
        raise OSError(ctypes.get_errno(),'atomic_exchange_failed')


class RawTransaction:
    """Real six-file archive/stage/whole-byte CAS/conditional rollback engine.

    Private core is shared with offline filesystem fault tests. Only
    reconcile_current() admits a production registered session. No CLI paths,
    boolean readiness, alternate owners or generic reset are accepted there.
    """
    def __init__(self, files, archive, check, *, anchors=None):
        self.files=files; self.archive=archive; self.guard=check; self.anchors=anchors or {}
        self.original={k:v.raw for k,v in files.items()}; self.current=dict(self.original)
        self.identities={k:signature(v.before) for k,v in files.items()}
        self.staged={}; self.committed=[]; self.journal=[]; self.archived=False

    def join(self):
        self.guard()
        for key,file in self.files.items():
            for parent,name,child,identity in file.chain:
                sig=lambda v:(v.st_dev,v.st_ino,v.st_mode,v.st_uid,v.st_gid)
                require(sig(os.fstat(child))==sig(os.stat(name,dir_fd=parent,follow_symlinks=False))==identity,
                    'transaction_ancestry_changed')
            # Current named inode, not the old still-open FD after promotion.
            fd=os.open(file.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=file.directory)
            try:
                before=os.fstat(fd); raw=os.read(fd,262145); after=os.fstat(fd)
                named=os.stat(file.name,dir_fd=file.directory,follow_symlinks=False)
                require(signature(before)==signature(after)==signature(named)==self.identities[key]
                    and raw==self.current[key],'transaction_whole_byte_cas_changed')
            finally: os.close(fd)
        if self.archived:
            for key in PATHS:
                require(self.read_archive(key+'.original.json')==self.original[key], 'durable_archive_changed')
        return True

    def immutable(self,name,raw):
        self.guard(); self.archive.check(name)
        with self.archive.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o400) as out:
            view=memoryview(raw)
            while view:
                count=out.write(view); require(type(count) is int and count>0,'archive_partial_write')
                view=view[count:]
            out.fsync(); os.fsync(out.parent); out.check()
        require(self.read_archive(name)==raw,'archive_exact_bytes_failed')

    def read_archive(self,name):
        with self.archive.open(name) as stream:
            require(stat.S_IMODE(stream.stat().st_mode)==0o400,'archive_immutable_mode')
            raw=stream.read(262145); stream.check(); return raw

    def archive_all(self):
        require(set(self.files)==set(PATHS),'transaction_six_files_required')
        self.join(); require(os.listdir(self.archive.fileno())==[],'archive_must_be_exclusive_empty')
        for key in PATHS: self.immutable(key+'.original.json',self.original[key])
        self.immutable('manifest.json',encode({'schema':'h044-six-raw-archive-v1',
            'files':{k:sha(v) for k,v in self.original.items()}}))
        os.fsync(self.archive.fileno())
        for key in PATHS:
            require(self.read_archive(key+'.original.json')==self.original[key], 'archive_all_six_readback_required')
        self.archived=True; self.join()
        self.journal.append('ALL_SIX_DURABLE_BEFORE_MUTATION')

    def stage(self,key,raw,tag):
        file=self.files[key]; name='.h044-'+tag+'-'+uuid.uuid4().hex
        self.guard()
        anchor=self.anchors.get(key)
        if anchor is not None:
            anchor.check(name)
            with anchor.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600) as stream:
                os.fchown(stream.fileno(),file.before.st_uid,file.before.st_gid)
                os.fchmod(stream.fileno(),stat.S_IMODE(file.before.st_mode))
                stream.write(raw); stream.fsync(); os.fsync(stream.parent); stream.check()
        else:
            # /etc is deliberately not a registered payload root. Hold its
            # already-protected parent FD; production RootPayloadGuard ran.
            out=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=file.directory)
            try:
                os.fchown(out,file.before.st_uid,file.before.st_gid)
                os.fchmod(out,stat.S_IMODE(file.before.st_mode))
                view=memoryview(raw)
                while view:
                    count=os.write(out,view); require(count>0,'stage_partial_write'); view=view[count:]
                os.fsync(out)
            finally: os.close(out)
            os.fsync(file.directory)
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=file.directory)
        try:
            info=os.fstat(fd); data=os.read(fd,262145)
            require(data==raw and stat.S_ISREG(info.st_mode) and info.st_nlink==1
                    and info.st_uid==file.before.st_uid,'stage_byte_readback_failed')
            identity=signature(info)
        finally: os.close(fd)
        return name,identity

    def promote(self,key,stage,raw):
        self.join()
        self._swap_cas(key,stage,raw)
        self.join()

    def _swap_cas(self,key,stage,raw):
        # Atomic exchange retains the displaced inode for a real CAS check.
        # A concurrent replacement cannot be silently destroyed by rename.
        file=self.files[key]; name,identity=stage
        anchor=self.anchors.get(key)
        if anchor is not None: anchor.check(file.name); anchor.check(name)
        self.guard()
        expected=self.identities[key]
        require(signature(os.stat(name,dir_fd=file.directory,follow_symlinks=False))==identity,
                'stage_identity_changed')
        require(signature(os.stat(file.name,dir_fd=file.directory,follow_symlinks=False))==expected,
                'cas_immediate_inode_changed')
        exchange(file.directory,name,file.name)
        os.fsync(file.directory)
        promoted=os.stat(file.name,dir_fd=file.directory,follow_symlinks=False)
        displaced=os.stat(name,dir_fd=file.directory,follow_symlinks=False)
        # Rename changes ctime on some filesystems; identity/size/mtime/mode are
        # checked separately and full original/successor bytes are reread.
        stable=lambda v:signature(v)[:-1]
        def read(leaf):
            fd=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=file.directory)
            try:
                before=os.fstat(fd); content=os.read(fd,262145)
                require(signature(before)==signature(os.fstat(fd))==signature(
                    os.stat(leaf,dir_fd=file.directory,follow_symlinks=False)),'exchange_fd_changed')
                return content
            finally: os.close(fd)
        displaced_raw=read(name); promoted_raw=read(file.name)
        if stable(displaced)!=expected[:-1] or displaced_raw!=self.current[key]:
            # Restore the foreign raced leaf only while both swapped identities
            # are still exact. No stale owner or unconditional rollback write.
            require(stable(promoted)==identity[:-1] and promoted_raw==raw,
                    'exchange_race_reversal_not_safe')
            require(signature(os.stat(name,dir_fd=file.directory,follow_symlinks=False))==signature(displaced)
                and signature(os.stat(file.name,dir_fd=file.directory,follow_symlinks=False))==signature(promoted),
                'exchange_race_reversal_not_safe')
            exchange(file.directory,name,file.name); os.fsync(file.directory)
            raise Refused('cas_exchange_race_rejected_foreign_leaf_restored')
        require(stable(promoted)==identity[:-1] and promoted_raw==raw,'promotion_inode_changed')
        self.current[key]=raw; self.identities[key]=signature(promoted)
        if anchor is not None: anchor.check(file.name)

    def apply(self, successors, verify):
        require(set(successors)=={'config','state','operation','recovery','api'},'transaction_exact_successor_set')
        self.archive_all()
        # A current active recovery reservation closes normal admission across
        # a crash/partial transaction. Every original remains in immutable raw
        # archive. Complete recovery is promoted last after owner validation.
        reservation=strict(successors['recovery'])
        reservation.update(status='active',phase='settle')
        ordered=[('recovery',encode(reservation)),('operation',successors['operation']),
            ('state',successors['state']),('config',successors['config']),
            ('api',successors['api'])]
        all_stages=[(key,raw,self.stage(key,raw,'candidate')) for key,raw in ordered]
        final=self.stage('recovery',successors['recovery'],'complete')
        try:
            for key,raw,stage in all_stages:
                # Track intent first: an exception after rename/fsync may have
                # promoted. Rollback must examine actual named bytes, never
                # assume a throwing replace did nothing.
                self.committed.append((key,raw))
                self.promote(key,stage,raw)
            verify() # actual normal Runtime constructor/source/owner validation
            self.committed.append(('recovery',successors['recovery']))
            self.promote('recovery',final,successors['recovery'])
            self.join(); self.journal.append('COMMITTED_NORMAL_REGISTRATION')
        except BaseException:
            failed=False
            for key,raw in reversed(self.committed):
                try:
                    file=self.files[key]
                    fd=os.open(file.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=file.directory)
                    try:
                        info=os.fstat(fd); actual=os.read(fd,262145)
                        named=os.stat(file.name,dir_fd=file.directory,follow_symlinks=False)
                        require(signature(info)==signature(named),'rollback_named_fd_changed')
                    finally: os.close(fd)
                    if actual==self.original[key]:
                        self.current[key]=actual; self.identities[key]=signature(named); continue
                    require(actual in (raw,self.current[key]),'rollback_foreign_bytes_refused')
                    self.current[key]=actual; self.identities[key]=signature(named)
                    self.guard()
                    # Do not join other not-yet-reconciled post-error leaves.
                    stage=self.stage(key,self.original[key],'rollback')
                    name,identity=stage
                    require(signature(os.stat(file.name,dir_fd=file.directory,follow_symlinks=False))==self.identities[key],
                        'rollback_cas_race')
                    self._swap_cas(key,stage,self.original[key])
                except BaseException: failed=True
            if failed:
                self.journal.append('ROLLBACK_FAILED_ADMISSION_MUST_REMAIN_CLOSED')
                raise RollbackFailed('rollback_failed_current_owner_review_required') from None
            self.join(); self.journal.append('ROLLED_BACK_EXACT_ORIGINAL_BYTES')
            raise
        return {'status':'COMMITTED_SOURCE_WRITER','archivePath':str(self.archive.path),
            'originalWholeFileSha256':{k:sha(v) for k,v in self.original.items()},
            'successorWholeFileSha256':{k:sha(v) for k,v in self.current.items()},
            'journal':list(self.journal),'nativeGeneration':'NOT_TESTED'}


def validate_current_raw(raw,runtime_config,*,expected=EXPECTED):
    """Actual full schema; expected override is private offline fixture use only."""
    require(type(raw) is dict and set(raw)==set(PATHS) and set(expected)==set(PATHS)
        and all(type(raw[k]) is bytes and sha(raw[k])==expected[k] for k in PATHS), 'current_six_raw_hash_join')
    values={k:strict(v) for k,v in raw.items()}
    config,state,op,recovery,api,checkpoint=(values[k] for k in ('config','state','operation','recovery','api','checkpoint'))
    require(config==runtime_config and config.get('gpu_uuid')==READING_GPU
        and config.get('image_id')==PLATFORM and config.get('checkpoint_receipt_sha256')==sha(raw['checkpoint']),
        'raw_current_config_join')
    require(state.get('owner')==OWNER and type(state.get('schema_version')) is int and state['schema_version']==1 and state.get('run_id')==INVOCATION
        and state.get('container')=={'id':CID,'image_id':PLATFORM} and state.get('warm') is False,
        'raw_native_owner_join')
    require(op.get('boot')==recovery.get('boot')==OLD_BOOT and op.get('status')==recovery.get('status')=='active'
        and op.get('gpu_uuid')==recovery.get('gpu_uuid')==READING_GPU
        and op.get('action')=='start' and op.get('invocation_id')==INVOCATION
        and type(op.get('pid')) is int and op['pid']==10956
        and type(recovery.get('pid')) is int and recovery['pid']>0
        and type(recovery.get('process')) is dict and recovery['process'].get('pid')==recovery['pid']
        and type(recovery['process'].get('start_ticks')) is int and recovery['process']['start_ticks']>0
        and recovery.get('phase')=='reset' and recovery.get('child_start') is None,
        'actual_oldboot_reset_phase_schema_required')
    for owner_record in (op,recovery):
        require(type(owner_record.get('token')) is str and len(owner_record['token'])==32
            and all(c in '0123456789abcdef' for c in owner_record['token']), 'actual_owner_token_schema_required')
    digest=sha(json.dumps(config,sort_keys=True,separators=(',',':')).encode())
    require(op.get('config_sha256')==recovery.get('config_sha256')==digest,'raw_owner_config_digest_join')
    require(api.get('runtime_image_digest')==PARENT and api.get('runtime_revision')==SOURCE
        and api.get('model_revision')==REVISION and api.get('model_id')=='Qwen/Qwen-Image-2.1', 'raw_api_identity_join')
    require(checkpoint.get('status')=='COMPLETE_VERIFIED' and checkpoint.get('revision')==REVISION
        and type(checkpoint.get('file_count')) is int and checkpoint['file_count']==26
        and checkpoint.get('total_bytes')==33131614782,'raw_checkpoint_join')
    return config,state,op,recovery,api,checkpoint


def reconcile_current(session):
    """Actual writer; only a genuine open registered production session enters."""
    require(type(session) is ProductionSession,'registered_production_session_required')
    record=ProductionSession.check(session); record.snapshot.check(); record.physical()
    raw=record.snapshot.raw()
    # Full raw schema checks do not reconstruct selected observations. Old
    # reset phase is parsed according to actual Runtime.recover() schema.
    config,state,op,recovery,api,checkpoint=validate_current_raw(raw,record.runtime.config)
    updated_config=copy.deepcopy(config); updated_config['gpu_uuid']=EXTERNAL_GPU
    updated_api=copy.deepcopy(api); updated_api['runtime_image_digest']=PLATFORM
    token=uuid.uuid4().hex
    history={'archivePath':ARCHIVE,'originalWholeFileSha256':dict(EXPECTED),'oldBoot':OLD_BOOT}
    updated_state=copy.deepcopy(state)
    updated_state.update(phase='stopped',container=None,warm=False,h044_reconciliation=history)
    updated_state['last_native_actions']=updated_state.pop('native_actions',{})
    updated_state.pop('native_generation',None)
    new_digest=sha(json.dumps(updated_config,sort_keys=True,separators=(',',':')).encode())
    updated_op={'token':uuid.uuid4().hex,'boot':BOOT,'pid':os.getpid(),'action':'stop','status':'complete',
        'recovery':None,'config_sha256':new_digest,'gpu_uuid':EXTERNAL_GPU,'invocation_id':None,
        'prior_state_sha256':sha(raw['state']),'h044_reconciliation':history}
    updated_recovery={'token':token,'boot':BOOT,'pid':os.getpid(),'status':'complete','phase':'complete',
        'process':record.runtime.process_stamp(os.getpid()),'config_sha256':new_digest,'gpu_uuid':EXTERNAL_GPU,
        'prior_invocation':INVOCATION,'child_start':None,'h044_reconciliation':history}
    successors={k:encode(v) for k,v in zip(('config','state','operation','recovery','api'),
        (updated_config,updated_state,updated_op,updated_recovery,updated_api))}
    successors['config']=replace_scalar(raw['config'],'gpu_uuid',READING_GPU,EXTERNAL_GPU)
    successors['api']=replace_scalar(raw['api'],'runtime_image_digest',PARENT,PLATFORM)
    tx=RawTransaction(record.snapshot.files,record.archive,record.physical,
        anchors={k:record.anchor for k in ('config','state','operation','recovery')})
    def verify():
        candidate=record.module.Runtime() # unchanged normal constructor guards
        require(type(candidate) is record.module.Runtime and candidate.config==updated_config,
            'normal_runtime_registration_failed')
        record.runtime.config=updated_config
        record.runtime.hardware_observation=record.runtime.probe_hardware()
        record.runtime.require_hardware()
    try: return tx.apply(successors,verify)
    finally: record.runtime.config=config


API_FILES=tuple('/usr/local/lib/llm-server/image-api/scripts/image_api/'+name
    for name in ('__init__.py','serve.py','protection.py','protocol.py','uploads.py','backend.py','app.py'))
API_ARGV=['/data/services/image-api/venv/bin/python','-I','-B',API_FILES[1]]


def current_api_owner_proof(go):
    """Finite read-only proof before a separately authorized exact API stop.

    No signal/systemctl stop, no health/ready/auth/key read, and no argv output.
    The current kernel owner, unit invocation, source/ExecStart and raw config
    file are joined twice. Root archives these nonsecret proof bytes and binds
    their whole-file hash in its distinct stop and writer GO.
    """
    require(os.geteuid()==0,'api_proof_root_required')
    with ProtectedFile(str(Path(__file__).absolute())) as helper:
        require(go.get('status')=='GO' and go.get('issuedBy')=='root'
            and go.get('actions')==['current_source_bound_api_owner_read']
            and go.get('bootId')==BOOT and go.get('sourceSha256')==sha(helper.raw)
            and type(go.get('maximumInvocations')) is int and go['maximumInvocations']==1,
            'api_owner_read_exact_go_required')
        begin=datetime.datetime.fromisoformat(go['notBeforeUtc']);end=datetime.datetime.fromisoformat(go['expiresUtc'])
        now=datetime.datetime.now(datetime.timezone.utc)
        require(begin.tzinfo is not None and end.tzinfo is not None and begin<=now<end
            and (end-begin).total_seconds()<=30,'api_owner_read_finite_go_required')
        require(set(go.get('apiCanonicalSourceSha256',{}))==set(API_FILES),'api_exact_canonical_source_set')
        module=_load_owner()
        with contextlib.ExitStack() as stack:
            sources={path:stack.enter_context(ProtectedFile(path)) for path in API_FILES}
            require(all(sha(file.raw)==go['apiCanonicalSourceSha256'][path] for path,file in sources.items()),
                    'api_canonical_source_changed')
            unit=stack.enter_context(ProtectedFile('/etc/systemd/system/llm-image-api.service'))
            require(sha(unit.raw)==go.get('apiUnitRawSha256') and
                ('ExecStart='+' '.join(API_ARGV)).encode() in unit.raw.splitlines(), 'api_execstart_source_changed')
            config=stack.enter_context(ProtectedFile(API));require(sha(config.raw)==EXPECTED['api'],'api_config_changed')
            def read():
                require(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT,'api_owner_boot_changed')
                text=module.run(['/usr/bin/systemctl','show','llm-image-api.service',
                    '--property=Id,MainPID,ControlPID,ActiveState,SubState,ControlGroup,InvocationID,NeedDaemonReload'],timeout=2).stdout
                properties=dict(line.split('=',1) for line in text.splitlines() if '=' in line)
                require(properties.get('Id')=='llm-image-api.service' and properties.get('MainPID')=='11783'
                    and properties.get('ControlPID')=='0' and properties.get('ActiveState')=='active'
                    and properties.get('SubState')=='running' and properties.get('InvocationID')==API_OWNER['invocation']
                    and properties.get('ControlGroup')=='/system.slice/llm-image-api.service'
                    and properties.get('NeedDaemonReload')=='no','api_current_manager_owner_changed')
                root=Path('/proc/11783'); stat_raw=(root/'stat').read_text()
                tail=stat_raw[stat_raw.rfind(')')+2:].split()
                require(tail[0] not in ('Z','X') and int(tail[2])==11783 and int(tail[19])==2769,
                        'api_current_kernel_generation_changed')
                require(os.readlink(root/'exe')=='/usr/bin/python3.12'
                    and (root/'cgroup').read_text().splitlines()==['0::/system.slice/llm-image-api.service']
                    and (root/'cmdline').read_bytes().split(b'\0')[:-1]==[x.encode() for x in API_ARGV],
                    'api_canonical_kernel_command_changed')
                return properties
            before=read()
            for file in (*sources.values(),unit,config):
                file.check();require(os.pread(file.fd,262145,0)==file.raw,'api_source_fd_bytes_changed')
            require(read()==before and datetime.datetime.now(datetime.timezone.utc)<end,'api_owner_read_race')
            return {'schema':'h044-current-image-api-owner-v1','boot':BOOT,'priorOwner':dict(API_OWNER),
                'beforeKernelIdentity':{'pid':11783,'pgid':11783,'start_ticks':2769,'exe':'/usr/bin/python3.12',
                    'cgroup':'0::/system.slice/llm-image-api.service'},
                'sourceSha256':dict(go['apiCanonicalSourceSha256']),'unitRawSha256':sha(unit.raw),
                'apiConfigWholeFileSha256':sha(config.raw),'observedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'action':'READ_ONLY; distinct finite root GO required to stop current exact owner'}

def request():
    return {'schema':'h044-image04-protected-writer-request-v1','authorization':'SOURCE_ONLY_NO_GO',
        'runtimeWriter':'IMPLEMENTED_GUARDED_ARCHIVE_CAS_ROLLBACK','expectedBoot':BOOT,
        'expectedFileSha256':dict(EXPECTED),'archiveDestination':ARCHIVE,
        'ownerSourceSha256':OWNER_SOURCE_SHA,'maximumInvocations':1,'maximumSeconds':180,
        'actions':['protected_six_raw_archive','stopped_owner_reconcile_CAS','conditional_exact_byte_rollback'],
        'apiOwnerReadEntry':'current_api_owner_proof(exact_distinct_read_go); read-only before separate exact stop GO',
        'entry':'with open_production_session(exact_root_go) as session: reconcile_current(session)',
        'requiredInputs':['exact protected public cached OCI manifest/config FD paths',
            'protected current source-bound API stop proof and API source/unit hashes',
            'exact docker executable whole-file hash and current daemon ID',
            'current physically absent exact CID/name/kernel/cgroup/API and old-owner refusals',
            'protected exclusive empty registered0700 archive directory',
            'exact peer whole-file hash map'],
        'canonicalGraph':['closed Runtime from protected service.py610397',
            'LifecycleLease private active registry/_validate_borrowed_lease',
            'RegisteredStorageBinding + actual MountedStorageGuard + AnchoredRoot',
            'Storage.root_payload_guard before/after; actual image recovery/operation singleton GuardedFiles',
            'unchanged source/model/checkpoint/hardware/resource/owner guards'],
        'lifecyclePrerequisite':'Separate exact source-bound root API-stop and stopped native removal GO; writer never signals old PIDs or calls generic reset/latch clear',
        'normalGenerationOnly':True,'rawPreCropArtifact':'NOT_CAPTURED','globalAllThreeGate':'CLOSED',
        'qualification':'SOURCE_ONLY; Linux/lifecycle/native/normalgeneration NOT_TESTED'}


if __name__=='__main__': print(json.dumps(request(),indent=2,sort_keys=True))
