#!/usr/bin/env python3
"""H046 archive-adopting stopped-owner successor; no historical GO is accepted.

Reuse the canonical H044 FD/CAS/storage/lease engine. This module never starts,
stops, removes, downloads or signals a model. Live entry requires a current
root GO and the exact closed helper graph, plus current stopped proof collected
again while the guards and exclusive locks are held.
"""
from __future__ import annotations

import contextlib
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import uuid

import image_owner_reconcile as core

MANIFEST_SHA = '58607a3e51d3e0b8b565a0c5c14d7f588b8f17af4da76be812861527e15fc7cf'
UNITS = ('llm-image-api.service', 'llm-image-backend.service')
API_UNIT = '/etc/systemd/system/llm-image-api.service'
BACKEND_UNIT = '/etc/systemd/system/llm-image-backend.service'
LATCH_PATH = '/data/services/llm-manager/hardware-latch.json'
ACTIONS = ['adopt_exact_existing_seven_file_archive', 'fresh_stopped_owner_reconcile_CAS',
           'conditional_own_inode_whole_byte_rollback']
require, sha, strict = core.require, core.sha, core.strict


def validate_go(go, source_sha, now):
    require(type(go) is dict and go.get('status') == 'GO' and go.get('issuedBy') == 'root'
        and go.get('phase') == 'H046-image-stopped-CAS' and go.get('bootId') == core.BOOT
        and go.get('sourceSha256') == source_sha and go.get('expectedFileSha256') == core.EXPECTED
        and go.get('archiveDestination') == core.ARCHIVE and go.get('archiveManifestSha256') == MANIFEST_SHA
        and go.get('ownerSourceSha256') == core.OWNER_SOURCE_SHA
        and type(go.get('maximumInvocations')) is int and go['maximumInvocations'] == 1
        and go.get('maximumSeconds') == 180 and go.get('actions') == ACTIONS
        and go.get('nativeImageStartPermitted') is False and go.get('generationPermitted') is False,
        'h046_exact_finite_root_go_required')
    try:
        begin = datetime.datetime.fromisoformat(go['notBeforeUtc'])
        end = datetime.datetime.fromisoformat(go['expiresUtc'])
    except (KeyError, ValueError, TypeError):
        raise core.RequirementsMissing('h046_go_time_required') from None
    require(begin.tzinfo is not None and end.tzinfo is not None and begin <= now < end
        and 0 < (end - begin).total_seconds() <= 180, 'h046_go_expired')
    for field in ('helperSha256', 'apiCanonicalSourceSha256', 'peerFileSha256', 'residentBindings',
                  'expectedFileIdentity', 'archiveFileIdentity', 'stoppedUnits', 'cachedPublicOCIPaths'):
        require(type(go.get(field)) is dict and bool(go[field]), 'h046_current_graph_required')
    require(set(go['expectedFileIdentity']) == set(core.PATHS)
        and set(go['archiveFileIdentity']) == {k+'.original.json' for k in core.PATHS} | {'manifest.json'}
        and set(go['apiCanonicalSourceSha256']) == set(core.API_FILES)
        and set(go['stoppedUnits']) == set(UNITS)
        and set(go['residentBindings']) == {'Qwen0', 'Qwen1', 'MiMo', 'VisionQwen', 'VisionOCR'},
        'h046_exact_source_owner_sets_required')
    for field in ('apiUnitRawSha256', 'backendUnitRawSha256', 'dockerBinarySha256', 'daemonId',
                  'pythonSha256', 'rootStage', 'hardwareLatchSha256'):
        require(type(go.get(field)) is str and bool(go[field]), 'h046_source_inputs_required')
    require(type(go.get('archiveDirectoryIdentity')) is list and len(go['archiveDirectoryIdentity']) == 5,
            'h046_archive_directory_identity_required')
    for identities in (go['expectedFileIdentity'],go['archiveFileIdentity']):
        require(all(type(v) is list and len(v) == 9 and all(type(n) is int for n in v)
                    for v in identities.values()),'h046_exact_nine_field_inode_pins_required')
    require(type(go.get('hardwareLatchIdentity')) is list and len(go['hardwareLatchIdentity']) == 9,
            'h046_current_hardware_latch_identity_required')


def identity(file):
    return list(core.signature(file.before))


class ProtectedExecutable(core.ProtectedFile):
    """Dedicated finite streaming binary pin; config/raw JSON cap stays262144.

    Synthetic fixture boundary follows the existing ordinary-user seam. Live
    binary paths are fixed and root-owned; retained descriptors recheck named
    inode/metadata and all held ancestor identities without exporting ELF bytes.
    """
    def __init__(self,path,*,trusted_uid=0,fixture_root=None):
        p = Path(path)
        require(p.is_absolute() and '..' not in p.parts,'executable_path')
        if fixture_root is None:
            require(str(p) in ('/usr/bin/docker','/usr/bin/python3.12'),'fixed_executable_path')
            root = Path('/'); parts = p.parts[1:-1]
        else:
            root = Path(fixture_root)
            require(trusted_uid != 0 and trusted_uid == os.getuid() and root.is_absolute()
                    and root in p.parents,'fixture_boundary')
            parts = p.relative_to(root).parts[:-1]
        self.directory = os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        self.fd = None; self.chain = []; self.directories = [self.directory]
        self.name = p.name; self.path = str(p); self.uid = trusted_uid
        try:
            s = os.fstat(self.directory)
            require(stat.S_ISDIR(s.st_mode) and s.st_uid in (0,trusted_uid) and not s.st_mode&0o022,'executable_root')
            for part in parts:
                child = os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=self.directory)
                s = os.fstat(child); self.directories.append(child)
                require(s.st_uid in (0,trusted_uid) and not s.st_mode&0o022,'executable_ancestry')
                require(core.signature(s) == core.signature(os.stat(part,dir_fd=self.directory,follow_symlinks=False)),
                        'executable_directory_cas')
                self.chain.append((self.directory,part,child,(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid)))
                self.directory = child
            self.before = os.stat(self.name,dir_fd=self.directory,follow_symlinks=False)
            s = self.before
            require(stat.S_ISREG(s.st_mode) and s.st_uid == trusted_uid and s.st_nlink == 1
                    and not s.st_mode&0o022 and 0 < s.st_size <= 128*1024**2,'executable_bound_owner')
            self.fd = os.open(self.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.directory)
            self.check(); digest = hashlib.sha256(); count = 0
            while True:
                block = os.read(self.fd,1048576)
                if not block: break
                count += len(block); require(count <= s.st_size,'executable_size'); digest.update(block)
            require(count == s.st_size,'executable_size'); self.check()
            self.whole_sha256 = digest.hexdigest()
        except BaseException: self.close(); raise


def validate_peers(go, module):
    import image_process_recorder as recorder
    template = '{"id":{{json .Id}},"image":{{json .Image}},"devices":{{json .HostConfig.DeviceRequests}},"running":{{json .State.Running}},"pid":{{json .State.Pid}}}'
    for name,expected in go['residentBindings'].items():
        require(type(expected) is dict and set(expected) == {'container','birth'},'exact_current_peer_tuple_required')
        container = expected['container']
        require(container.get('running') is True and type(container.get('pid')) is int
            and container['pid'] > 0,'current_peer_not_running')
        actual = strict(module.run(['/usr/bin/docker','container','inspect','--format',template,
                                   container['id']],timeout=3).stdout.encode())
        require(actual == container,'current_peer_container_changed')
        actual_birth = recorder.process_identity(container['pid'])
        require(actual_birth == expected['birth'] and actual_birth['bootId'] == core.BOOT,
                'current_peer_birth_changed')


class ArchiveTransaction(core.RawTransaction):
    """Adopt seven held original FDs; never clear/create/write the archive."""
    def __init__(self, *args, archive_files, manifest_sha=MANIFEST_SHA, **kwargs):
        super().__init__(*args, **kwargs)
        self.archive_files = archive_files
        self.manifest_sha = manifest_sha

    def archive_all(self):
        require(set(self.files) == set(core.PATHS), 'transaction_six_files_required')
        self.join()
        expected_names = {k+'.original.json' for k in core.PATHS} | {'manifest.json'}
        require(set(os.listdir(self.archive.fileno())) == set(self.archive_files) == expected_names,
                'existing_archive_exact_seven_required')
        manifest = self.archive_files['manifest.json']
        require(sha(manifest.raw) == self.manifest_sha, 'existing_archive_manifest_hash')
        require(strict(manifest.raw) == {'schema': 'h044-six-raw-archive-v1',
            'files': {k:sha(v) for k,v in self.original.items()}}, 'existing_archive_manifest_join')
        self.archived = True
        self.join()
        self.journal.append('ADOPTED_ALL_SEVEN_IMMUTABLE_ORIGINALS')

    def join(self):
        result = super().join()
        for name, held in self.archive_files.items():
            held.check()
            require(stat.S_IMODE(held.before.st_mode) == 0o400
                and os.pread(held.fd,262145,0) == held.raw, 'existing_archive_fd_bytes_changed')
            expected = self.manifest_sha if name == 'manifest.json' else sha(self.original[name[:-14]])
            require(sha(held.raw) == expected, 'existing_archive_original_hash')
        return result


def replace_fields(raw, changes):
    """Edit only selected top-level value tokens; retain history/profile bytes."""
    strict(raw)
    text = raw.decode('utf-8'); decoder = json.JSONDecoder(); p = text.index('{')+1
    spans = {}; close = None
    while True:
        while text[p].isspace(): p += 1
        if text[p] == '}': close = p; break
        key, p = decoder.raw_decode(text,p)
        while text[p].isspace(): p += 1
        require(text[p] == ':', 'state_field_colon'); p += 1
        while text[p].isspace(): p += 1
        start = p; _, p = decoder.raw_decode(text,p); spans[key] = (start,p)
        while text[p].isspace(): p += 1
        if text[p] == '}': close = p; break
        require(text[p] == ',', 'state_field_comma'); p += 1
    edits = [(spans[k][0],spans[k][1],json.dumps(v,ensure_ascii=False,allow_nan=False))
             for k,v in changes.items() if k in spans]
    added = {k:v for k,v in changes.items() if k not in spans}
    if added:
        insertion = (',' if spans else '') + '\n' + ',\n'.join(
            json.dumps(k)+': '+json.dumps(v,ensure_ascii=False,allow_nan=False) for k,v in added.items())+'\n'
        edits.append((close,close,insertion))
    for start,end,value in sorted(edits,reverse=True): text = text[:start]+value+text[end:]
    result = text.encode(); require(strict(result) == dict(strict(raw),**changes), 'state_field_join')
    return result


def stopped_successors(raw, runtime_config, stamp, *, expected=core.EXPECTED):
    config,state,op,recovery,api,checkpoint = core.validate_current_raw(raw,runtime_config,expected=expected)
    require(type(stamp) is dict and type(stamp.get('pid')) is int and stamp['pid'] > 0
        and type(stamp.get('start_ticks')) is int and stamp['start_ticks'] > 0, 'fresh_writer_birth_required')
    updated_config = dict(config,gpu_uuid=core.EXTERNAL_GPU)
    digest = sha(json.dumps(updated_config,sort_keys=True,separators=(',',':')).encode())
    history = {'archivePath':core.ARCHIVE,'originalWholeFileSha256':dict(expected),'oldBoot':core.OLD_BOOT}
    updated_op = {'token':uuid.uuid4().hex,'boot':core.BOOT,'pid':stamp['pid'],'action':'stop',
        'status':'complete','recovery':None,'config_sha256':digest,'gpu_uuid':core.EXTERNAL_GPU,
        'invocation_id':None,'prior_state_sha256':sha(raw['state']),'h046_reconciliation':history}
    updated_recovery = {'token':uuid.uuid4().hex,'boot':core.BOOT,'pid':stamp['pid'],'status':'complete',
        'phase':'complete','process':stamp,'config_sha256':digest,'gpu_uuid':core.EXTERNAL_GPU,
        'prior_invocation':core.INVOCATION,'child_start':None,'h046_reconciliation':history}
    return {'config':core.replace_scalar(raw['config'],'gpu_uuid',core.READING_GPU,core.EXTERNAL_GPU),
        'api':core.replace_scalar(raw['api'],'runtime_image_digest',core.PARENT,core.PLATFORM),
        'state':replace_fields(raw['state'],{'phase':'stopped','container':None,'warm':False,
            'native_actions':{},'native_generation':None,'h046_reconciliation':history}),
        'operation':core.encode(updated_op),'recovery':core.encode(updated_recovery)}


def fresh_stopped(record):
    """Current units/inventory/cgroups/commands; historical PID11783 is irrelevant."""
    record.check()
    before = {unit:core._unit(record.module,unit) for unit in UNITS}
    require(before == record.go['stoppedUnits'], 'current_stopped_unit_generation_changed')
    record.runtime.prove_absent(core.CID)
    for path in ('/sys/fs/cgroup/system.slice/llm-image-api.service',
                 '/sys/fs/cgroup/system.slice/llm-image-backend.service',
                 '/sys/fs/cgroup/system.slice/docker-'+core.CID+'.scope'):
        core._absent(path,'current_image_cgroup_present_or_unknown')
    # All UIDs participate; select only exact image source commands/cgroups.
    rows = 0
    for proc in Path('/proc').iterdir():
        if not proc.name.isdecimal(): continue
        rows += 1; require(rows <= 20000, 'finite_stopped_inventory')
        try:
            first = (proc/'stat').read_bytes()
            cmd = (proc/'cmdline').read_bytes(); cg = (proc/'cgroup').read_text()
            second = (proc/'stat').read_bytes()
        except (FileNotFoundError,ProcessLookupError):
            core._absent(str(proc),'stopped_process_race_ambiguous'); continue
        except OSError: raise core.RequirementsMissing('stopped_process_inventory_unreadable') from None
        birth = lambda raw:raw.rsplit(b')',1)[1].split()[19]
        require(birth(first) == birth(second), 'stopped_process_birth_race')
        argv = cmd.split(b'\0')
        targets = [*core.API_FILES,core.BASE+'/source/native_server.py',core.BASE+'/source/service.py']
        require(not any(t.encode() in argv for t in targets)
            and not any('/'+unit in cg for unit in UNITS)
            and core.CID not in cg, 'foreign_or_active_image_owner')
    after = {unit:core._unit(record.module,unit) for unit in UNITS}
    require(before == after, 'stopped_unit_readback_race')
    record.check()
    return {'schema':'h046-current-stopped-image-proof-v1','boot':core.BOOT,
        'observedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'stoppedUnits':after,
        'sourceSha256':record.go['apiCanonicalSourceSha256'],'originalApiConfigSha256':core.EXPECTED['api'],
        'historicalPidUsed':False,'currentImageOwner':'ABSENT','oldCID':core.CID,'procRowsChecked':rows}


class StoppedRecord(core._SessionRecord):
    def check(self):
        validate_go(self.go,self.source_sha,datetime.datetime.now(datetime.timezone.utc))
        require(sys.pycache_prefix == str(Path(self.go['rootStage'])/'NO-PYC-CACHE'),
                'closed_source_pycache_prefix_required')
        core._absent(sys.pycache_prefix,'source_only_pycache_prefix_populated')
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == core.BOOT,'writer_boot_changed')
        require(type(self.runtime) is self.module.Runtime,'closed_runtime_class_required')
        core._canonical_guards(self.lease,self.anchor,self.mounted,self.runtime.binding,
                              self.model_lock,self.operation_lock)
        self.oci.check(); self.module.verify_source_closure(self.runtime.config); self.archive.check()
        for held in self.executables.values(): held.check()
        for held in (*self.peers.values(),*self.protected_sources.values(),*self.archive_files.values()):
            held.check(); require(os.pread(held.fd,len(held.raw)+1,0) == held.raw,'closed_graph_bytes_changed')
        self.peer_check()

    def hardware_readonly(self):
        """Strict CAS-only guard; never publish, clear or reset latch evidence.

        Native starts still use unchanged Runtime.require_hardware persistence.
        This transition requires the protected canonical latch to contain NO
        target record for the external GPU, including inherited/pending records.
        It checks the canonical pure policy with a fresh exact probe but never
        publishes its prospective validation annotation as native admission.
        """
        from lifecycle.hardware_policy import HardwarePolicy, MAX_AGE_MS, _timestamp
        from control.hardware_latch import HardwareLatch
        held = self.protected_sources[LATCH_PATH]
        held.check(); require(os.pread(held.fd,262145,0) == held.raw,'hardware_latch_changed')
        require(identity(held) == self.go['hardwareLatchIdentity'] and sha(held.raw) == self.go['hardwareLatchSha256'],
                'source_bound_hardware_latch_changed')
        record = self
        class ReadOnlyStore:
            def read(self):
                record.services_check()
                return strict(held.raw)
            def write(self,value): raise core.Refused('hardware_latch_write_out_of_scope')
        policy = HardwarePolicy(ReadOnlyStore(),lease=self.lease)
        saved = policy._owner().export_state()
        require(core.EXTERNAL_GPU not in saved['targets'],'hardware_target_protection_must_not_clear')
        proof = self.runtime.hardware_observation
        observed = _timestamp(proof['observed_at'])
        require(policy.boot()['boot_id'] == proof['boot'] == core.BOOT and observed is not None
                and 0 <= (policy.wall()-observed)*1000 <= MAX_AGE_MS,'hardware_validation_stale')
        result = HardwareLatch(saved).validate_required(core.EXTERNAL_GPU,current_boot_id=core.BOOT,
            receipt={'observed_at':proof['observed_at'],'observation_id':proof['observation_id']})
        require(result['hardware_latched'] is False and result.get('reason') is None,'hardware_fault')
        held.check()

    def services_check(self):
        self.runtime.services_anchor.check()
        self.mounted()

    def physical(self):
        self.proof = fresh_stopped(self)
        old = self.runtime.config
        try:
            self.runtime.config = dict(old,gpu_uuid=core.EXTERNAL_GPU)
            self.runtime.hardware_observation = self.runtime.probe_hardware()
            self.hardware_readonly(); self.runtime.require_ada_idle()
            device = self.runtime.current_device()
            require(device['free_bytes']*20 >= device['total_bytes'],'ada_initial_margin_below_5_percent')
            self.runtime.host_headroom(); self.runtime.check_ports()
        finally: self.runtime.config = old
        self.check()


@contextlib.contextmanager
def open_stopped_session(go):
    """Only reviewed executor supplies the mandatory exact current peer join."""
    require(os.geteuid() == 0, 'writer_root_required')
    with core.ProtectedFile(str(Path(__file__).absolute())) as source:
        digest = sha(source.raw); validate_go(go,digest,datetime.datetime.now(datetime.timezone.utc))
        # Validate the closed helper before importing canonical owner classes.
        sources = contextlib.ExitStack()
        with sources:
            protected_sources = {}
            graph = dict(go['helperSha256']) | dict(go['apiCanonicalSourceSha256']) | {
                API_UNIT:go['apiUnitRawSha256'],BACKEND_UNIT:go['backendUnitRawSha256'],
                LATCH_PATH:go['hardwareLatchSha256']}
            for path,expected in graph.items():
                held = sources.enter_context(core.ProtectedFile(path))
                require(sha(held.raw) == expected,'h046_closed_helper_source_changed')
                protected_sources[path] = held
            executables = {}
            for path,expected in {'/usr/bin/docker':go['dockerBinarySha256'],
                                  '/usr/bin/python3.12':go['pythonSha256']}.items():
                held = sources.enter_context(ProtectedExecutable(path))
                require(held.whole_sha256 == expected,'h046_binary_changed'); executables[path] = held
            module = core._load_owner(); runtime = module.Runtime(); runtime.boot = core.BOOT
            runtime.guards()
            from install.storage import Storage
            from install.storage_io import AnchoredRoot
            Storage.root_payload_guard(runtime.binding.storage,runtime.binding.registry)
            require(runtime.binding.storage.system_root == Path('/') and runtime.binding.storage.owner == 0,
                    'production_storage_scope_required')
            with contextlib.ExitStack() as stack:
                oci = stack.enter_context(core.read_cached_oci(go))
                require(module.run(['/usr/bin/docker','info','--format','{{.ID}}'],timeout=3).stdout.strip()
                        == go['daemonId'],'docker_daemon_changed')
                cached = strict(module.run(['/usr/bin/docker','image','inspect','--format',
                    '{"id":{{json .Id}},"descriptor":{{json .Descriptor}},"os":{{json .Os}},"architecture":{{json .Architecture}}}',
                    core.PLATFORM],timeout=3).stdout.encode())
                require(cached.get('id') == core.PLATFORM and cached.get('descriptor',{}).get('digest') == core.PLATFORM
                    and cached.get('os') == 'linux' and cached.get('architecture') == 'amd64','cached_daemon_platform_changed')
                mounted = stack.enter_context(runtime.binding.mounted_guard(module.storage_io))
                anchor = stack.enter_context(AnchoredRoot(core.BASE,mounted))
                services = stack.enter_context(AnchoredRoot(runtime.binding.path('services'),mounted))
                runtime.storage_anchor = anchor; runtime.services_anchor = services
                model = stack.enter_context(runtime.singleton('recovery.lock'))
                operation = stack.enter_context(runtime.singleton('operation.lock'))
                archive = stack.enter_context(AnchoredRoot(core.ARCHIVE,mounted))
                a = os.fstat(archive.fileno())
                require([a.st_dev,a.st_ino,a.st_mode,a.st_uid,a.st_gid] == go['archiveDirectoryIdentity']
                    and stat.S_IMODE(a.st_mode) == 0o700,'existing_archive_directory_changed')
                archived = {name:stack.enter_context(core.ProtectedFile(core.ARCHIVE+'/'+name))
                            for name in go['archiveFileIdentity']}
                files = {name:stack.enter_context(core.ProtectedFile(path)) for name,path in core.PATHS.items()}
                for names,identities in ((archived,go['archiveFileIdentity']),(files,go['expectedFileIdentity'])):
                    require(all(identity(held) == identities[name] for name,held in names.items()),'h046_bound_inode_changed')
                snapshot = core.Snapshot(files); snapshot.check()
                peers = {path:stack.enter_context(core.ProtectedFile(path)) for path in go['peerFileSha256']}
                require(all(sha(f.raw) == go['peerFileSha256'][p] for p,f in peers.items()),'peer_file_changed')
                lease = stack.enter_context(module.acquire_lease(blocking=False)); runtime.lease = lease
                session = object.__new__(core.ProductionSession)
                record = StoppedRecord(module,runtime,anchor,mounted,lease,model,operation,
                    snapshot,archive,go,digest,oci,peers)
                record.archive_files = archived; record.protected_sources = protected_sources
                record.executables = executables
                record.peer_check = lambda: validate_peers(go,module)
                core._ACTIVE[session] = record
                try:
                    record.check(); record.physical(); yield session
                finally:
                    core._ACTIVE.pop(session,None); runtime.lease = None
            runtime.guards(); Storage.root_payload_guard(runtime.binding.storage,runtime.binding.registry)


def reconcile_stopped(session):
    require(type(session) is core.ProductionSession,'registered_production_session_required')
    record = core.ProductionSession.check(session)
    require(type(record) is StoppedRecord,'h046_stopped_session_required')
    record.snapshot.check(); record.physical(); raw = record.snapshot.raw()
    config = record.runtime.config
    successors = stopped_successors(raw,config,record.runtime.process_stamp(os.getpid()))
    transaction = ArchiveTransaction(record.snapshot.files,record.archive,record.physical,
        anchors={k:record.anchor for k in ('config','state','operation','recovery')},session=session,
        archive_files=record.archive_files)
    updated = strict(successors['config'])
    def verify():
        candidate = record.module.Runtime()
        require(type(candidate) is record.module.Runtime and candidate.config == updated,
                'normal_runtime_registration_failed')
        record.runtime.config = updated
        record.runtime.hardware_observation = record.runtime.probe_hardware(); record.hardware_readonly()
    try:
        result = transaction.apply(successors,verify)
        return dict(result,stoppedProof=record.proof,archiveMutation='NONE',liveGeneration='NOT_TESTED',
                    hardwareProof='READ_ONLY_NO_PUBLISHED_HARDWARE_RECEIPT')
    finally: record.runtime.config = config


def request():
    return {'schema':'h046-image-stopped-CAS-request-v1','authorization':'SOURCE_ONLY_NO_GO',
        'phase':'H046-image-stopped-CAS','expectedBoot':core.BOOT,'maximumSeconds':180,'maximumInvocations':1,
        'actions':ACTIONS,'expectedFileSha256':core.EXPECTED,'archiveDestination':core.ARCHIVE,
        'archiveManifestSha256':MANIFEST_SHA,'archiveMutation':'NONE','nativeImageStartPermitted':False,
        'generationPermitted':False,'historicalPID11783Authority':'NONE',
        'entry':'image_executor.py EXACT_PROTECTED_GO_PATH','qualification':'SOURCE_ONLY; native NOT_TESTED'}


if __name__ == '__main__': print(json.dumps(request(),indent=2,sort_keys=True))
