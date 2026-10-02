#!/usr/bin/env python3
"""Fixed H046 CAS executor. Source-only until root seals and stages an exact GO.

No service start/stop/remove or inference commands are admitted. Original
actual-child receipts remain independently durable even on a later refusal.
"""
from __future__ import annotations
import datetime
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

LEAVES = ('image_executor.py','image_owner_successor.py','image_owner_reconcile.py',
          'image_process_recorder.py','image_command_gate.py')

RELEASE = '/data/services/releases/h037-image-placement-20260930'
REGISTRATION = '/etc/local-ai-server/storage.json'
CANONICAL_SHA256 = {
    '/data/services/image21-runtime-20260923/source/service.py':
        '610397909e66e6242bace7f96f7c179ff9451c14699ed3555dfdbc5e06669438',
    RELEASE+'/scripts/install/storage.py':
        '4f834e92d149ea1955e79d34c53c18bf8c5846a4121d779e135a50d31a615505',
    RELEASE+'/scripts/install/storage_io.py':
        '5ba1b1356519bbb4922b563662a605459862a84b81ce4f521dfbce293d97302a',
    RELEASE+'/scripts/lifecycle/manager.py':
        'e75057f1d5a9e9cf4c09591cb7811a3b028aaad8371964a1d33993ccf13f0249',
    RELEASE+'/scripts/lifecycle/storage_binding.py':
        '69e61ce6685c310ce83449de75d45b209e63c6454c175f03d42bdad3daea7fbf',
    RELEASE+'/scripts/lifecycle/runtime_io.py':
        '07a8275f07109eb4e3543fb7aafc86d8f9367de5e04c2277894e1c98a7562783',
    RELEASE+'/scripts/common/registered-storage.py':
        '21cf082a841aeab9470bd6704b77104961b9d4afcaec696d90aa22b65f5b6f3d',
}
ALIASES = {'docker':'/usr/bin/docker','nvidia-smi':'/usr/bin/nvidia-smi','ss':'/usr/bin/ss',
           'systemctl':'/usr/bin/systemctl','/usr/bin/python3':'/usr/bin/python3.12',
           'findmnt':'/usr/bin/findmnt','lsblk':'/usr/bin/lsblk','df':'/usr/bin/df'}


def normalize_argv(argv):
    if type(argv) is not list or not argv or any(type(x) is not str or '\0' in x for x in argv):
        raise ValueError('exact string argv required')
    return [ALIASES.get(argv[0],argv[0]),*argv[1:]]


def _directory_identity(value):
    if (type(value) is not list or len(value) != 5 or any(type(x) is not int for x in value)
            or not stat.S_ISDIR(value[2]) or value[3] != 0 or value[2]&0o022):
        raise ValueError('protected bound directory identity required')
    return value


def _file_identity(value, *, private=False):
    if (type(value) is not list or len(value) != 9 or any(type(x) is not int for x in value)
            or not stat.S_ISREG(value[2]) or value[3] != 0 or value[5] != 1
            or value[2]&(0o077 if private else 0o022)):
        raise ValueError('protected bound file identity required')
    return value


def storage_targets(registration, boot_paths):
    """The frozen Storage/RegisteredStorageBinding layout, not caller paths."""
    if (type(registration) is not dict or set(registration) !=
            {'schema_version','storage_mode','roots','data','models'}
            or type(registration['schema_version']) is not int or registration['schema_version'] != 1
            or registration['storage_mode'] != 'existing'):
        raise ValueError('current existing storage registration required')
    from pathlib import PurePosixPath
    def path(value):
        import re
        if (type(value) is not str or not re.fullmatch(r'/[A-Za-z0-9_./-]+',value)
                or str(PurePosixPath(value)) != value or any(x in {'.','..'} for x in value.split('/'))
                or value == '/' or any(value == x or value.startswith(x+'/')
                    for x in ('/boot','/etc','/dev','/proc','/sys','/run'))):
            raise ValueError('canonical normalized registered storage path required')
        return value
    for role in ('data','models'):
        item = registration[role]
        if type(item) is not dict or not {'path','mount','uuid','fstype'} <= set(item):
            raise ValueError('registered mount metadata required')
        path(item['path']); path(item['mount'])
        import re
        if (type(item['uuid']) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{3,127}',item['uuid'])
                or item['fstype'] not in ('ext4','xfs')):raise ValueError('registered mount identity required')
        if item['path'] != item['mount'] and not item['path'].startswith(item['mount']+'/'):
            raise ValueError('registered namespace outside mount')
    data,models = registration['data'],registration['models']
    if (data['path'] != data['mount'] or (data['mount'] == models['mount']) != (data['uuid'] == models['uuid'])
            or data['mount'] == models['mount'] and data['fstype'] != models['fstype']):
        raise ValueError('ambiguous registered mount alias')
    # Exact _roots from the pinned 4f834e source; checked against actual source in tests.
    roots = {name:data['path']+'/'+suffix for name,suffix in {
        'hf_cache':'hf-cache','docker':'docker','containerd':'containerd','build':'build','logs':'logs',
        'backups':'backups','services':'services','secrets':'services/secrets','state':'services/installer'}.items()}
    roots['models'] = models['path']
    if registration['roots'] != roots:raise ValueError('canonical registered roots changed')
    if type(boot_paths) is not dict or set(boot_paths) != {'/boot','/boot/efi'}:
        raise ValueError('exact boot existence proof required')
    targets = {'/',*roots.values(),data['path'],data['mount'],models['path'],models['mount']}
    for p,meta in boot_paths.items():
        if type(meta) is not dict or set(meta) != {'exists','identity'} or type(meta['exists']) is not bool:
            raise ValueError('exact boot path proof required')
        if meta['exists']:_directory_identity(meta['identity']);targets.add(p)
        elif meta['identity'] is not None:raise ValueError('absent boot identity required')
    return sorted(targets),sorted({'/',data['mount'],models['mount']})


def validate_storage_binding(binding, source_raws=None):
    required = {'schema','sourceSha256','sourceIdentity','registrationSha256','registrationIdentity',
                'registration','bootPaths','findmntTargets','dfTargets','targetDirectoryIdentity'}
    if (type(binding) is not dict or set(binding) != required
            or binding['schema'] != 'h046-canonical-storage-command-binding-v1'
            or binding['sourceSha256'] != CANONICAL_SHA256
            or set(binding['sourceIdentity']) != set(CANONICAL_SHA256)):
        raise ValueError('exact frozen canonical source binding required')
    for value in binding['sourceIdentity'].values():_file_identity(value)
    _file_identity(binding['registrationIdentity'],private=True)
    import re
    if not re.fullmatch('[0-9a-f]{64}',binding['registrationSha256']):
        raise ValueError('bound registration hash required')
    findmnt,df = storage_targets(binding['registration'],binding['bootPaths'])
    if binding['findmntTargets'] != findmnt or binding['dfTargets'] != df:
        raise ValueError('canonical target set changed')
    if set(binding['targetDirectoryIdentity']) != set(findmnt):
        raise ValueError('exact target directory identities required')
    for value in binding['targetDirectoryIdentity'].values():_directory_identity(value)
    for p,meta in binding['bootPaths'].items():
        if meta['exists'] and meta['identity'] != binding['targetDirectoryIdentity'][p]:
            raise ValueError('boot target inode join required')
    if source_raws is not None:
        if set(source_raws) != set(CANONICAL_SHA256):raise ValueError('exact canonical bytes required')
        for p,raw in source_raws.items():
            if hashlib.sha256(raw).hexdigest() != CANONICAL_SHA256[p]:raise ValueError('canonical source changed')
    return binding


def canonical_storage_binding(packet):
    if packet.get('schema') != 'h046-canonical-readonly-argv-source-packet-v1':
        raise ValueError('actual canonical read packet required')
    sources = packet['sources'];reg = packet['storageRegistration']
    binding = {'schema':'h046-canonical-storage-command-binding-v1',
        'sourceSha256':{p:e['sha256'] for p,e in sources.items()},
        'sourceIdentity':{p:e['identity'] for p,e in sources.items()},
        'registrationSha256':reg['sha256'],'registrationIdentity':reg['identity'],
        'registration':reg['registration'],'bootPaths':packet['bootPaths'],
        'findmntTargets':packet['findmntTargets'],'dfTargets':packet['dfTargets'],
        'targetDirectoryIdentity':packet['targetDirectoryIdentity']}
    if reg['path'] != REGISTRATION or any(p != e['path'] for p,e in sources.items()):
        raise ValueError('exact canonical paths required')
    validate_storage_binding(binding,{p:e['text'].encode() for p,e in sources.items()})
    return binding


class CanonicalStorageGuard:
    """Hold the reviewed sources/registry; reject every later identity change."""
    def __init__(self,binding,core):
        self.binding = validate_storage_binding(binding)
        self.stack = contextlib.ExitStack()
        try:
            self.sources = {p:self.stack.enter_context(core.ProtectedFile(p)) for p in CANONICAL_SHA256}
            self.registration = self.stack.enter_context(core.ProtectedFile(REGISTRATION))
            self.check()
        except BaseException:self.close();raise

    def close(self):self.stack.close()

    def check(self):
        b = validate_storage_binding(self.binding)
        def signature(s):return [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,
                                s.st_size,s.st_mtime_ns,s.st_ctime_ns]
        for p,held in self.sources.items():
            held.check()
            if (signature(held.before) != b['sourceIdentity'][p]
                    or os.pread(held.fd,len(held.raw)+1,0) != held.raw
                    or hashlib.sha256(held.raw).hexdigest() != b['sourceSha256'][p]):
                raise ValueError('current canonical source/inode changed')
        held = self.registration;held.check()
        if (signature(held.before) != b['registrationIdentity']
                or os.pread(held.fd,len(held.raw)+1,0) != held.raw
                or hashlib.sha256(held.raw).hexdigest() != b['registrationSha256']):
            raise ValueError('current registration config/inode changed')
        if json.loads(held.raw) != b['registration']:raise ValueError('current registered metadata changed')
        for p,meta in b['bootPaths'].items():
            if os.path.lexists(p) != meta['exists']:raise ValueError('current boot target set changed')
        for p,expected in b['targetDirectoryIdentity'].items():
            for parent in (Path(p),*Path(p).parents):
                _directory_identity(signature(parent.lstat())[:5])
            if signature(Path(p).lstat())[:5] != expected:raise ValueError('current target directory inode changed')


def storage_guard_argv(argv,core,go):
    """Keep the normal CLI/Runner; bind its isolated child's cache lookup."""
    argv = normalize_argv(argv)
    stage = Path(go['rootStage'])
    if (str(stage) != go['rootStage'] or '..' in stage.parts
            or str(stage.parent) != '/run/llmctl' or not stage.name.startswith('h046-image-stopped-cas-')):
        raise ValueError('exact protected CAS stage required for child cache')
    for extra in ([],['--root-guard']):
        raw = ['/usr/bin/python3.12','-I','-B',core.RELEASE+'/scripts/common/registered-storage.py','--json',*extra]
        if argv == raw:
            return [*raw[:3],'-X','pycache_prefix='+str(stage/'NO-PYC-CACHE'),*raw[3:]]
    return argv


def read_argv_allowed(argv, core, go):
    """Positive closed-source command shapes only; no flag/subcommand fallback."""
    try:argv = normalize_argv(argv)
    except ValueError:return False
    fixed = [
        ['/usr/bin/docker','info','--format','{{.ID}}'],
        ['/usr/bin/docker','container','ls','--all','--no-trunc','--format','{{json .}}'],
        ['/usr/bin/docker','image','inspect','--format',
         '{"id":{{json .Id}},"descriptor":{{json .Descriptor}},"os":{{json .Os}},"architecture":{{json .Architecture}}}',core.PLATFORM],
        ['/usr/bin/ss','-H','-ltn'],
        ['/usr/bin/lsblk','--json','--bytes','--paths','--output',
         'NAME,PATH,TYPE,PKNAME,MOUNTPOINTS,FSTYPE,UUID,SIZE,WWN,SERIAL,RO,MAJ:MIN'],
    ]
    for query in ('--query-gpu=uuid','--query-gpu=uuid,memory.total,memory.free','--query-compute-apps=gpu_uuid,pid'):
        fixed.append(['/usr/bin/nvidia-smi','--id='+core.EXTERNAL_GPU,query,'--format=csv,noheader,nounits'])
    for unit in ('llm-image-api.service','llm-image-backend.service'):
        fixed.append(['/usr/bin/systemctl','show',unit,
            '--property=Id,MainPID,ControlPID,ActiveState,ControlGroup,InvocationID,Job,NeedDaemonReload'])
    try:
        binding = validate_storage_binding(go.get('canonicalStorageBinding'))
    except (ValueError,KeyError,TypeError):binding = None
    if binding is not None:
        for path in binding['findmntTargets']:
            fixed.append(['/usr/bin/findmnt','--json','--output','TARGET,SOURCE,UUID,FSTYPE,OPTIONS,MAJ:MIN','--target',path])
        for path in binding['dfTargets']:
            fixed.append(['/usr/bin/df','--output=avail','--block-size=1',path])
        for extra in ([],['--root-guard']):
            raw = ['/usr/bin/python3.12','-I','-B',core.RELEASE+'/scripts/common/registered-storage.py','--json',*extra]
            try:bound = storage_guard_argv(raw,core,go)
            except (ValueError,KeyError,TypeError):continue
            fixed.extend((raw,bound))
    template = '{"id":{{json .Id}},"image":{{json .Image}},"devices":{{json .HostConfig.DeviceRequests}},"running":{{json .State.Running}},"pid":{{json .State.Pid}}}'
    for peer in go.get('residentBindings',{}).values():
        fixed.append(['/usr/bin/docker','container','inspect','--format',template,peer['container']['id']])
    return argv in fixed


def protected(path, maximum=262144):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts: raise ValueError('absolute protected path required')
    for parent in (path.parent,*path.parent.parents):
        s = parent.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != 0 or s.st_mode&0o022:
            raise ValueError('protected root ancestry required')
    before = path.lstat()
    signature = lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    if not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or before.st_nlink != 1 or before.st_mode&0o022 or before.st_size > maximum:
        raise ValueError('protected source file required')
    fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        if signature(before) != signature(os.fstat(fd)): raise ValueError('protected fd changed')
        raw = os.read(fd,maximum+1)
        if len(raw) != before.st_size or signature(before) != signature(os.fstat(fd)) or signature(before) != signature(path.lstat()):
            raise ValueError('protected source changed')
        return raw
    finally: os.close(fd)


def main(go_path):
    if os.geteuid() != 0: raise ValueError('root required')
    os.umask(0o077)
    if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode) or sys.flags.optimize:
        raise ValueError('isolated no-site no-bytecode unoptimized interpreter required')
    go_raw = protected(go_path)
    # Strict parsing rejects duplicate fields/nonfinite values before any claim.
    def pairs(items):
        result = {}
        for k,v in items:
            if k in result: raise ValueError('duplicate control key')
            result[k] = v
        return result
    go = json.loads(go_raw,object_pairs_hook=pairs,
                    parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite control')))
    stage = Path(go['rootStage'])
    if stage != Path(go_path).parent or stage != Path(__file__).absolute().parent:
        raise ValueError('exact stage join required')
    if stat.S_IMODE(stage.stat().st_mode) != 0o700: raise ValueError('protected stage0700 required')
    hashes = go.get('helperSha256',{})
    if set(hashes) != {str(stage/name) for name in LEAVES}: raise ValueError('exact five helper source graph required')
    raw_sources = {name:protected(stage/name) for name in LEAVES}
    for name,raw in raw_sources.items():
        if hashlib.sha256(raw).hexdigest() != hashes[str(stage/name)]: raise ValueError('reviewed helper hash changed')
    def load(name):
        if name in sys.modules: raise ValueError('helper import collision')
        spec = importlib.util.spec_from_file_location(name,stage/(name+'.py'))
        module = importlib.util.module_from_spec(spec); sys.modules[name] = module
        exec(compile(raw_sources[name+'.py'],str(stage/(name+'.py')),'exec'),module.__dict__)
        return module
    core = load('image_owner_reconcile')
    recorder = load('image_process_recorder')
    successor = load('image_owner_successor')
    now = datetime.datetime.now(datetime.timezone.utc)
    successor.validate_go(go,hashes[str(stage/'image_owner_successor.py')],now)
    expires = datetime.datetime.fromisoformat(go['expiresUtc']).timestamp()
    end = time.monotonic()+min(180,expires-time.time())
    class Deadline:
        def remaining(self): return min(expires-time.time(),end-time.monotonic())
        def check(self,reserve=0):
            if self.remaining() <= reserve: raise TimeoutError('finite CAS deadline')
            if Path('/proc/sys/kernel/random/boot_id').read_text().strip() != core.BOOT:
                raise ValueError('current boot changed')
    deadline = Deadline()
    # -B prohibits writes but Python can still read an existing stale .pyc.
    # Redirect lookup to a protected absent prefix before canonical imports.
    sys.pycache_prefix = str(stage/'NO-PYC-CACHE')
    if os.path.lexists(sys.pycache_prefix): raise ValueError('absent source-only pycache prefix required')
    storage_guard = CanonicalStorageGuard(go.get('canonicalStorageBinding'),core)
    def put(path,raw):
        if Path(path).parent != stage: raise ValueError('fixed evidence stage only')
        # Terminal/failure receipts are durable even after the admission expires.
        recorder.put(path,raw)
    def write(name,value):
        raw = (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
        put(stage/name,raw)
    try:
        write('INVOCATION-CLAIM.json',{'goWholeFileSha256':hashlib.sha256(go_raw).hexdigest(),
            'pid':os.getpid(),'birth':recorder.process_identity(os.getpid()),'startedUtc':now.isoformat(),
            'maximumInvocations':1,'nativeImageStartPermitted':False,'generationPermitted':False})
    except BaseException:storage_guard.close();raise
    # Exclusive claim O_EXCL admits one invocation; replay refuses before CAS.
    sequence = 0
    def command(argv, *, timeout=60, check=True):
        nonlocal sequence
        deadline.check(5)
        if sys.pycache_prefix != str(stage/'NO-PYC-CACHE') or os.path.lexists(sys.pycache_prefix):
            raise ValueError('exact absent child source cache prefix required')
        argv = normalize_argv(argv)
        storage_guard.check()
        if not read_argv_allowed(argv,core,go): raise ValueError('fixed read guard command only')
        argv = storage_guard_argv(argv,core,go)
        if not read_argv_allowed(argv,core,go):raise ValueError('exact emitted read guard command required')
        sequence += 1; stem = 'command-'+str(sequence).zfill(4)
        result = recorder.run_gated(argv,str(stage),{'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LC_ALL':'C',
            'TMPDIR':core.BASE+'/tmp'},stage/(stem+'.stdout'),stage/(stem+'.stderr'),
            stage/(stem+'.launch.json'),stage/(stem+'.terminal.json'),min(float(timeout),deadline.remaining()-5),
            deadline,writer=put,allowed={0},gate=stage/'image_command_gate.py',
            python='/usr/bin/python3.12',python_sha=go['pythonSha256'])
        stdout = (stage/(stem+'.stdout')).read_bytes(); stderr = (stage/(stem+'.stderr')).read_bytes()
        deadline.check(5)
        if os.path.lexists(sys.pycache_prefix):raise ValueError('source-only child cache prefix populated')
        if len(stdout)>16*1024**2 or len(stderr)>1024**2: raise ValueError('guard output bound')
        write(stem+'.stream-join.json',{'stdoutSha256':hashlib.sha256(stdout).hexdigest(),
            'stderrSha256':hashlib.sha256(stderr).hexdigest(),'actualExitCode':result['actualExitCode'],
            'directReaped':result['reaped'],'closure':result['closure']})
        if result['failure'] is not None or result['reaped'] is not True or result['closure']['independentBirthGroupAbsence'] is not True:
            raise ValueError('actual owned command closure required')
        if check and result['actualExitCode'] != 0: raise ValueError('guard command actual nonzero')
        storage_guard.check()
        return subprocess.CompletedProcess(argv,result['actualExitCode'],stdout.decode(),stderr.decode())
    old_loader = core._load_owner
    def load_owner():
        module = old_loader(); module.run = command
        # Keep the real canonical StorageRunner class and guard object graph.
        # Only its existing command transport port gains the same finite recorder.
        from lifecycle import manager
        manager.run = lambda argv,timeout=30:command(argv,timeout=timeout).stdout
        return module
    core._load_owner = load_owner
    try:
        deadline.check(60)
        descriptor_sequence = 0
        def descriptor_audit(snapshot):
            nonlocal descriptor_sequence
            descriptor_sequence += 1
            if descriptor_sequence > 4096:raise ValueError('finite mutable readback audit bound')
            write('mutable-read-'+str(descriptor_sequence).zfill(4)+'.json',snapshot)
        with successor.open_stopped_session(go,audit=descriptor_audit) as session:
            result = successor.reconcile_stopped(session)
        write('CAS-RESULT.json',dict(result,qualification='SOURCE_WRITER_COMPLETED; native NOT_TESTED'))
    except BaseException as error:
        write('CAS-FAILURE.json',{'failureClass':type(error).__name__,
            'nativeImageStartPermitted':False,'generationPermitted':False,
            'originalCommandFailuresPreserved':True,'settlement':'REQUIRES_CURRENT_READBACK'})
        raise
    finally:storage_guard.close()


if __name__ == '__main__':
    if len(sys.argv) != 2: raise SystemExit('usage: image_executor.py EXACT_PROTECTED_GO_PATH')
    main(sys.argv[1])
