#!/usr/bin/env python3
"""Fixed H046 CAS executor. Source-only until root seals and stages an exact GO.

No service start/stop/remove or inference commands are admitted. Original
actual-child receipts remain independently durable even on a later refusal.
"""
from __future__ import annotations
import datetime
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


def read_argv_allowed(argv, core, go):
    """Positive closed-source command shapes only; no flag/subcommand fallback."""
    if type(argv) is not list or not argv or any(type(x) is not str or '\0' in x for x in argv):return False
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
    for path in ('/','/data','/data/models-large'):
        fixed.append(['/usr/bin/findmnt','--json','--output','TARGET,SOURCE,UUID,FSTYPE,OPTIONS,MAJ:MIN','--target',path])
        fixed.append(['/usr/bin/df','--output=avail','--block-size=1',path])
    for extra in ([],['--root-guard']):
        fixed.append(['/usr/bin/python3.12','-I','-B',core.RELEASE+'/scripts/common/registered-storage.py','--json',*extra])
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
    def put(path,raw):
        if Path(path).parent != stage: raise ValueError('fixed evidence stage only')
        # Terminal/failure receipts are durable even after the admission expires.
        recorder.put(path,raw)
    def write(name,value):
        raw = (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
        put(stage/name,raw)
    write('INVOCATION-CLAIM.json',{'goWholeFileSha256':hashlib.sha256(go_raw).hexdigest(),
        'pid':os.getpid(),'birth':recorder.process_identity(os.getpid()),'startedUtc':now.isoformat(),
        'maximumInvocations':1,'nativeImageStartPermitted':False,'generationPermitted':False})
    # Exclusive claim O_EXCL admits one invocation; replay refuses before CAS.
    sequence = 0
    aliases = {'docker':'/usr/bin/docker','nvidia-smi':'/usr/bin/nvidia-smi','ss':'/usr/bin/ss',
               'systemctl':'/usr/bin/systemctl','/usr/bin/python3':'/usr/bin/python3.12',
               'findmnt':'/usr/bin/findmnt','lsblk':'/usr/bin/lsblk','df':'/usr/bin/df'}
    def command(argv, *, timeout=60, check=True):
        nonlocal sequence
        deadline.check(5)
        argv = [aliases.get(argv[0],argv[0]),*argv[1:]]
        if not read_argv_allowed(argv,core,go): raise ValueError('fixed read guard command only')
        sequence += 1; stem = 'command-'+str(sequence).zfill(4)
        result = recorder.run_gated(argv,str(stage),{'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LC_ALL':'C',
            'TMPDIR':core.BASE+'/tmp'},stage/(stem+'.stdout'),stage/(stem+'.stderr'),
            stage/(stem+'.launch.json'),stage/(stem+'.terminal.json'),min(float(timeout),deadline.remaining()-5),
            deadline,writer=put,allowed={0},gate=stage/'image_command_gate.py',
            python='/usr/bin/python3.12',python_sha=go['pythonSha256'])
        stdout = (stage/(stem+'.stdout')).read_bytes(); stderr = (stage/(stem+'.stderr')).read_bytes()
        if len(stdout)>16*1024**2 or len(stderr)>1024**2: raise ValueError('guard output bound')
        write(stem+'.stream-join.json',{'stdoutSha256':hashlib.sha256(stdout).hexdigest(),
            'stderrSha256':hashlib.sha256(stderr).hexdigest(),'actualExitCode':result['actualExitCode'],
            'directReaped':result['reaped'],'closure':result['closure']})
        if result['failure'] is not None or result['reaped'] is not True or result['closure']['independentBirthGroupAbsence'] is not True:
            raise ValueError('actual owned command closure required')
        if check and result['actualExitCode'] != 0: raise ValueError('guard command actual nonzero')
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
        with successor.open_stopped_session(go) as session:
            result = successor.reconcile_stopped(session)
        write('CAS-RESULT.json',dict(result,qualification='SOURCE_WRITER_COMPLETED; native NOT_TESTED'))
    except BaseException as error:
        write('CAS-FAILURE.json',{'failureClass':type(error).__name__,
            'nativeImageStartPermitted':False,'generationPermitted':False,
            'originalCommandFailuresPreserved':True,'settlement':'REQUIRES_CURRENT_READBACK'})
        raise


if __name__ == '__main__':
    if len(sys.argv) != 2: raise SystemExit('usage: image_executor.py EXACT_PROTECTED_GO_PATH')
    main(sys.argv[1])
