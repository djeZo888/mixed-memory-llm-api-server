#!/usr/bin/env python3
"""H046 finite root deployment control; preparation is not live qualification.

STAGE_COMPILED_ONLY and RESTART_STAGED_NORMAL_NO_INFERENCE require distinct
fresh GO envelopes/journals. Publish the current source sidecar as a separate
root operation BETWEEN staging and restart. STAGE configFiles must not require
the not-yet-published current sidecar; RESTART configFiles must include it.
Default mode is read-only preflight. --execute is a separate root operation and
requires a fresh HMAC envelope {body, seal} using an EXISTING protected key.
No signing, inference, Linux builds/installs, credential rotation, broad kills,
or database restoration exist here. A consumed GO stays consumed on failure.

GO body (all fields required): schema, operation, approvedBy, goId, issuedUtc,
expiresUtc, invocations, retries, counts, hostBootId, sourceCommit, helper,
release, archives, dependencies, configFiles, owner, unit, data, proofs, journal.
References are {path,sha256,uid}; paths and hashes are observed/approved by root,
not copied from historical authority. release.files is an exhaustive relative
file SHA map; each archive carries an exact subset of that map. Dependencies
are separate immutable verified trees, copied rather than installed/built.
proofs.visionNormal binds original receipt bytes, JSON pointers to its NORMAL
state/time/owner fields, and a freshly observed Linux producer owner. The helper
checks that supplied evidence; it never writes or manufactures that receipt.
proofs.ordinaryApproval and ordinaryKey are original protected files; the real
compiled ordinary loader validates original native launch/settlement/binary and
current source sidecar after staging, before any unit replacement.

Unit changes are limited to the reviewed ExecStart/WorkingDirectory/Restart
lines; restart is disabled in the candidate. Only one candidate restart is
permitted. Rollback has no default authority: [] or the exact three operations
in ROLLBACK must be enumerated by the signed GO (at most one original restart).
All live commands get original stdout/stderr bytes, actual integer waits,
owned birth identities and process/group-absence receipts in a private journal.
This source has only local negative/fixture tests; Linux operation is NOT_TESTED.
"""
import argparse
import base64
import datetime as dt
import hashlib
import hmac
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import tarfile
import time
import uuid
import urllib.request

SCHEMA = 'h046-normal-deployment-go-v1'
STAGE = 'STAGE_COMPILED_ONLY'
RESTART = 'RESTART_STAGED_NORMAL_NO_INFERENCE'
ROLLBACK = ['restore-original-unit', 'daemon-reload', 'restart-original-owned-unit']
ROOT_FIELDS = {'schema','operation','approvedBy','goId','issuedUtc','expiresUtc',
               'invocations','retries','counts','hostBootId','sourceCommit','helper',
               'release','archives','dependencies','configFiles','owner','unit',
               'data','proofs','journal'}
PATH_OPTIONS = {'--node-prefix','--app-dir','--data-dir','--inference-key-file',
 '--frontier-key-file','--browser-approval-key-file','--node-control-key-file',
 '--engine-launcher','--codex-preview-receipt','--codex-owned-acceptance-policy',
 '--codex-specialist-qualification','--codex-ordinary-entry','--codex-ordinary-entry-key',
 '--codex-generation-acceptance','--codex-global-generation-proof',
 '--codex-current-frontier-proof'}
MAX_FILE = 128 * 1024 * 1024
MAX_ARCHIVE = 1024 * 1024 * 1024

class Denied(RuntimeError): pass

def need(condition, reason):
    if not condition: raise Denied(reason)

def sha(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
def utc(): return dt.datetime.now(dt.timezone.utc).isoformat()
def timestamp(value):
    need(isinstance(value,str), 'timestamp is not text')
    result = dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    need(result.tzinfo is not None, 'timestamp has no UTC offset')
    return result.timestamp()
def is_digest(value): return isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value) is not None

def strict_json(raw):
    def pairs(items):
        out = {}
        for key,value in items:
            need(key not in out, 'duplicate JSON key'); out[key]=value
        return out
    return json.loads(raw.decode('utf-8',errors='strict'), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(Denied('nonfinite JSON')))

def relative(value):
    need(isinstance(value,str) and value and '\\' not in value and '\x00' not in value,
         'unsafe relative path')
    p=PurePosixPath(value)
    need(not p.is_absolute() and str(p)==value and all(x not in ('.','..') for x in p.parts),
         'noncanonical relative path')
    need(all(ord(x)>=32 for x in value), 'control character path')
    return value

def absolute(value):
    need(isinstance(value,str) and value.startswith('/') and all(ord(x)>=32 for x in value),
         'path is not absolute single-line text')
    path=Path(value)
    need(str(path)==value and '..' not in path.parts and path.resolve()==path,
         'path contains aliases/symlinks')
    return path

def ancestry(path, owners=(0,), writable_mask=0o022):
    for parent in (path, *path.parents):
        st=parent.lstat()
        need(stat.S_ISDIR(st.st_mode) and st.st_uid in owners and not st.st_mode&writable_mask,
             'unsafe path ancestry: '+str(parent))

def identity(path):
    st=path.lstat()
    return {'dev':st.st_dev,'ino':st.st_ino,'mode':stat.S_IMODE(st.st_mode),'uid':st.st_uid,
            'gid':st.st_gid,'nlink':st.st_nlink,'size':st.st_size,
            'mtimeNs':st.st_mtime_ns,'ctimeNs':st.st_ctime_ns}

def protected(path, uid, cap=MAX_FILE, private=False):
    path=absolute(str(path)); ancestry(path.parent, (0,uid))
    before=identity(path)
    need(stat.S_ISREG(path.lstat().st_mode) and before['uid']==uid and before['nlink']==1,
         'unsafe file type/owner/link count')
    need(not before['mode'] & (0o077 if private else 0o022) and (not private or before['size']>0) and 0<=before['size']<=cap,
         'unsafe file permissions/size')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd)
        need((st.st_dev,st.st_ino)==(before['dev'],before['ino']), 'opened file identity changed')
        with os.fdopen(os.dup(fd),'rb') as stream: raw=stream.read(cap+1)
        need(len(raw)==before['size'] and identity(path)==before, 'file changed while reading')
        return raw
    finally: os.close(fd)

def reference(ref, cap=MAX_FILE, private=False):
    need(isinstance(ref,dict) and set(ref)=={'path','sha256','uid'} and is_digest(ref['sha256'])
         and type(ref['uid']) is int and ref['uid']>=0, 'invalid exact file reference')
    raw=protected(ref['path'],ref['uid'],cap,private)
    need(sha(raw)==ref['sha256'], 'file SHA mismatch: '+ref['path'])
    return raw

def pointer(value, path):
    need(isinstance(path,str) and (path=='' or path.startswith('/')), 'invalid JSON pointer')
    for component in path.split('/')[1:]:
        key=component.replace('~1','/').replace('~0','~')
        if isinstance(value,list): value=value[int(key)]
        else: value=value[key]
    return value

def validate_go(envelope, key, now, helper_path, helper_sha):
    need(isinstance(envelope,dict) and set(envelope)=={'body','seal'} and is_digest(envelope['seal']),
         'invalid signed GO envelope')
    need(32<=len(key)<=4096 and hmac.compare_digest(envelope['seal'],hmac.new(key,canonical(envelope['body']),hashlib.sha256).hexdigest()),
         'GO HMAC mismatch')
    b=envelope['body']; need(isinstance(b,dict) and set(b)==ROOT_FIELDS, 'GO exact fields mismatch')
    need(b['schema']==SCHEMA and b['operation'] in (STAGE,RESTART) and b['approvedBy']=='root', 'GO authority mismatch')
    need(str(uuid.UUID(b['goId']))==b['goId'], 'GO ID is not canonical UUID')
    issued,expires=timestamp(b['issuedUtc']),timestamp(b['expiresUtc'])
    need(issued<=now<expires and 60<=expires-issued<=600 and now<expires-45, 'GO expired/not yet issued/unsafe reserve')
    need(type(b['invocations']) is int and type(b['retries']) is int and b['invocations']==1 and b['retries']==0, 'retry or multi-invocation GO forbidden')
    allowed = ([{'stage':1,'restart':0,'rollback':[]}] if b['operation']==STAGE else
               [{'stage':0,'restart':1,'rollback':[]},{'stage':0,'restart':1,'rollback':ROLLBACK}])
    need(type(b['counts'].get('stage')) is int and type(b['counts'].get('restart')) is int and
         b['counts'] in allowed, 'finite operation counts mismatch')
    need(re.fullmatch('[a-f0-9]{40}',b['sourceCommit'] or '') is not None, 'sealed final source commit missing')
    need(b['helper']=={'path':str(helper_path),'sha256':helper_sha,'uid':0}, 'executed helper mismatch')
    need(b['owner']['uid']==1000 and b['owner']['gid']==1000 and b['owner']['bootId']==b['hostBootId'],
         'normal service owner/boot mismatch')
    need(b['unit']['path']=='/home/user/.config/systemd/user/ai-harness.service', 'unknown service unit path')
    need(b['release']['path'].startswith('/opt/ai-harness/releases/'+b['sourceCommit']+'-'),
         'release path does not bind final commit')
    return b

def process(pid, proc_root=Path('/proc')):
    need(type(pid) is int and pid>0, 'invalid process PID')
    p=proc_root/str(pid); first=(p/'stat').read_bytes()
    fields=first.decode().rsplit(')',1)[1].split()
    need(fields[0] not in ('Z','X') and len(fields)>19, 'owner process is exited/zombie')
    ids=[int(x) for x in (p/'status').read_text().split('Uid:',1)[1].splitlines()[0].split()]
    gids=[int(x) for x in (p/'status').read_text().split('Gid:',1)[1].splitlines()[0].split()]
    need(len(set(ids))==1 and len(set(gids))==1, 'process has changing IDs')
    env=dict(item.split(b'=',1) for item in (p/'environ').read_bytes().split(b'\0') if b'=' in item)
    selected={k:env[k.encode()].decode() for k in ('AI_HARNESS_DATA_DIR','AI_HARNESS_WEB_DIST','AI_HARNESS_ENGINE_LAUNCHER') if k.encode() in env}
    result={'pid':pid,'startTicks':fields[19],'bootId':(proc_root/'sys/kernel/random/boot_id').read_text().strip(),
            'uid':ids[0],'gid':gids[0],'pgid':int(fields[2]),'cgroup':(p/'cgroup').read_text().strip(),
            'exe':os.readlink(p/'exe'),'cmdlineSha256':sha((p/'cmdline').read_bytes()),'selectedEnvironment':selected}
    need((p/'stat').read_bytes().decode().rsplit(')',1)[1].split()[19]==fields[19], 'process birth changed during observation')
    return result

def exact_owner(expected, invocation_id, proc_root=Path('/proc')):
    observed=process(expected['pid'],proc_root)
    need(set(expected)==set(observed)|{'invocationId'}, 'owner tuple fields mismatch')
    need(observed=={k:v for k,v in expected.items() if k!='invocationId'} and expected['invocationId']==invocation_id,
         'current owner tuple mismatch')
    return observed

def owner_absent(owner, proc_root=Path('/proc')):
    p=proc_root/str(owner['pid'])/'stat'
    if not p.exists(): return True
    return p.read_text().rsplit(')',1)[1].split()[19]!=owner['startTicks']

def group_absent(pgid, proc_root=Path('/proc')):
    for p in proc_root.iterdir():
        if not p.name.isdigit(): continue
        try:
            fields=(p/'stat').read_text().rsplit(')',1)[1].split()
            if int(fields[2])==pgid: return False
        except FileNotFoundError: continue
    return True

def dependency_digest(root, uid=0):
    root=absolute(str(root)); ancestry(root,(0,)); graph={}
    for parent,dirs,files in os.walk(root,followlinks=False):
        dirs.sort()
        for name in sorted(dirs+files):
            path=Path(parent)/name; st=path.lstat(); rel=str(path.relative_to(root))
            need(st.st_uid==uid and (stat.S_ISLNK(st.st_mode) or not st.st_mode&0o022), 'mutable dependency bytes')
            if stat.S_ISLNK(st.st_mode):
                target=os.readlink(path)
                need(not os.path.isabs(target) and path.resolve().is_relative_to(root) and path.resolve().exists(), 'dependency symlink escapes/missing tree')
                graph[rel]={'symlink':target}
            elif stat.S_ISDIR(st.st_mode): continue
            else:
                need(stat.S_ISREG(st.st_mode) and st.st_nlink==1, 'dependency special/hardlinked file')
                graph[rel]={'sha256':sha(protected(path,uid,MAX_FILE)),'mode':stat.S_IMODE(st.st_mode),'uid':st.st_uid}
    need(bool(graph),'empty dependency graph')
    return sha(canonical(graph))


def spawned_birth(pid, proc_root=Path('/proc')):
    fields=(proc_root/str(pid)/'stat').read_text().rsplit(')',1)[1].split()
    need(int(fields[2])==pid and int(fields[3])==pid,'command process did not create owned session/group')
    return {'pid':pid,'pgid':pid,'startTicks':fields[19],
            'bootId':(proc_root/'sys/kernel/random/boot_id').read_text().strip(),
            'procStatUtf8':(proc_root/str(pid)/'stat').read_text(),
            'bootIdUtf8':(proc_root/'sys/kernel/random/boot_id').read_text()}

def archive_members(raw, expected):
    need(isinstance(expected,dict) and expected and all(is_digest(v) for v in expected.values()), 'archive expected graph invalid')
    contents={}
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:*') as archive:
        names=set(); total=0
        for member in archive.getmembers():
            name=relative(member.name.rstrip('/') if member.isdir() else member.name)
            need(name not in names, 'duplicate archive path'); names.add(name)
            need(member.isdir() or member.isfile(), 'archive links/special files forbidden')
            if member.isdir(): continue
            need(name in expected and 0<=member.size<=MAX_FILE, 'archive extra/oversized member')
            total+=member.size; need(total<=MAX_ARCHIVE, 'expanded archive exceeds bound')
            stream=archive.extractfile(member); body=stream.read(MAX_FILE+1)
            need(len(body)==member.size and sha(body)==expected[name], 'archive content mismatch')
            contents[name]=body
    need(set(contents)==set(expected), 'archive omits exact file graph')
    return contents

def database_state(spec):
    root=absolute(spec['path']); ancestry(root.parent,(0,1000),0o022)
    need(root.lstat().st_uid==1000 and not root.lstat().st_mode&0o077,'data directory is not service-private')
    db=root/'harness.sqlite'; current=identity(db)
    need(all(current.get(k)==v for k,v in spec['databaseIdentity'].items()) and
         set(spec['databaseIdentity'])=={'dev','ino','uid','gid','mode','nlink'} and current['uid']==1000 and current['nlink']==1,
         'database identity mismatch')
    connection=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=3)
    try:
        connection.execute('PRAGMA query_only=ON'); connection.execute('BEGIN')
        active=connection.execute("SELECT COUNT(*) FROM runs WHERE status IN ('queued','running','cancelling')").fetchone()[0]
        owners=connection.execute("SELECT e.session_id,e.ownership,e.active_turn_id,s.status FROM h021_session_engines e JOIN sessions s ON s.id=e.session_id WHERE e.active_turn_id IS NOT NULL OR e.ownership!='idle' ORDER BY e.session_id").fetchall()
        need(active==0 and [list(v) for v in owners]==spec['retainedOwners'], 'work non-idle or retained owner changed')
        images=connection.execute('SELECT data FROM h003_image_jobs ORDER BY id').fetchall()
        need(all(strict_json(v[0].encode())['job']['state'] in ('completed','failed','cancelled','interrupted') for v in images),
             'image work non-idle or unknown')
        sid=spec['preservedSessionId']; projection={}
        for table,column in [('sessions','id'),('messages','session_id'),('runs','session_id'),('events','session_id'),('h021_session_engines','session_id')]:
            cursor=connection.execute('SELECT * FROM '+table+' WHERE '+column+'=? ORDER BY rowid',(sid,))
            rows=cursor.fetchall(); projection[table]={'columns':[v[0] for v in cursor.description],'rows':rows}
        need(len(projection['sessions']['rows'])==1 and sha(canonical(projection))==spec['preservedSessionSha256'],
             'original user session changed')
        return {'activeRuns':active,'retainedOwners':[list(v) for v in owners],
                'preservedSessionSha256':sha(canonical(projection)),'databaseIdentity':current}
    finally: connection.close()

def unit_candidate(original,candidate,spec,b):
    before=original.decode('utf-8',errors='strict').splitlines()
    after=candidate.decode('utf-8',errors='strict').splitlines()
    mutable={'ExecStart','WorkingDirectory','Restart'}
    def fixed(lines): return [line for line in lines if not any(line.startswith(k+'=') for k in mutable)]
    need(fixed(before)==fixed(after), 'unit changes outside reviewed deployment options')
    directives={}
    for line in after:
        if line.startswith(tuple(k+'=' for k in mutable)):
            k,v=line.split('=',1); need(k not in directives,'duplicate unit execution directive'); directives[k]=v
    need(directives.get('Restart')=='no','automatic service retries forbidden')
    need(directives.get('WorkingDirectory')==b['release']['path']+'/ai-harness/server','working directory not final release')
    argv=shlex.split(directives.get('ExecStart',''),posix=True)
    need(argv==spec['argv'],'unit command differs from root reviewed argv')
    launcher=b['release']['path']+'/ai-harness/deploy/run-server.sh'
    if argv and argv[0] in ('/bin/bash','/usr/bin/bash'): argv=argv[1:]
    need(argv and argv[0]==launcher and '%' not in directives['ExecStart'] and '\\' not in directives['ExecStart'],
         'unknown launcher/unit expansion')
    options={}; items=argv[1:]
    need(len(items)%2==0,'unpaired or boolean launcher flag')
    for option,value in zip(items[::2],items[1::2]):
        need(option not in options and option in PATH_OPTIONS|{'--codex-preview-output-limit'},'unknown/duplicate launcher option')
        if option=='--codex-preview-output-limit': need(value=='65536','output pin changed')
        else: absolute(value)
        options[option]=value
    required={'--node-prefix','--app-dir','--data-dir','--inference-key-file','--engine-launcher',
              '--codex-preview-receipt','--codex-ordinary-entry','--codex-ordinary-entry-key'}
    need(required<=set(options),'normal ordinary source admission options omitted')
    need(options['--app-dir']==b['release']['path']+'/ai-harness' and options['--data-dir']==b['data']['path'] and
         options['--engine-launcher']==b['release']['path']+'/ai-harness/deploy/run-engine.sh' and
         options['--codex-ordinary-entry']==b['proofs']['ordinaryApproval']['path'] and
         options['--codex-ordinary-entry-key']==b['proofs']['ordinaryKey']['path'] and
         options['--node-prefix']+'/bin/node'==b['owner']['exe'],'startup release/data/credential tuple mismatch')
    return options

class Control:
    def __init__(self,body): self.b=body; self.expires=timestamp(body['expiresUtc']); self.journal=None; self.command_sequence=0; self.readonly_receipts=[]
    def budget(self,reserve=10):
        value=self.expires-time.time()-reserve; need(value>1,'finite GO deadline/reserve exhausted'); return min(60,value)
    def record(self,name,value=None,raw=None):
        need(self.journal is not None,'journal not claimed')
        destination=self.journal/name
        fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(raw if raw is not None else canonical(value)+b'\n'); stream.flush(); os.fsync(stream.fileno())
    def claim(self):
        root=absolute(self.b['journal']); ancestry(root.parent,(0,)); need(not root.exists(),'GO spent/retry journal already exists')
        root.mkdir(mode=0o700); self.journal=root
        self.record('spent.json',{'goId':self.b['goId'],'bodySha256':sha(canonical(self.b)),'consumedUtc':utc(),'retryPermitted':False})
    def command(self,label,argv,cwd=None):
        timeout=self.budget(); self.command_sequence+=1; prefix='%03d-%s'%(self.command_sequence,label)
        child=subprocess.Popen(argv,cwd=cwd,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        birth=spawned_birth(child.pid); timed=False
        try: stdout,stderr=child.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed=True
            # Kill only the group created here if its exact birth still exists.
            if not owner_absent(birth): os.killpg(child.pid,signal.SIGKILL)
            stdout,stderr=child.communicate(timeout=5)
        absent=owner_absent(birth); group=group_absent(child.pid)
        self.record(prefix+'.stdout',raw=stdout); self.record(prefix+'.stderr',raw=stderr)
        receipt={'argv':argv,'cwd':cwd,'birth':birth,'pgid':child.pid,'actualExitCode':child.returncode,
                 'integerWait':type(child.returncode) is int,'timedOut':timed,'processAbsent':absent,'processGroupAbsent':group,
                 'stdoutSha256':sha(stdout),'stderrSha256':sha(stderr),'finishedUtc':utc()}
        self.record(prefix+'.json',receipt)
        need(type(child.returncode) is int and child.returncode==0 and not timed and absent and group,'command failed/partial: '+label)
        return stdout
    def manager(self,action):
        return self.command('manager-'+action[0],['/usr/sbin/runuser','-u','user','--','/usr/bin/env','-i',
         'HOME=/home/user','USER=user','LOGNAME=user','XDG_RUNTIME_DIR=/run/user/1000',
         'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus','PATH=/usr/bin:/bin',
         '/usr/bin/systemctl','--user',*action])
    def state(self):
        action=['show','ai-harness.service','--property=MainPID,ActiveState,SubState,NRestarts,InvocationID,ControlGroup']
        if self.journal: raw=self.manager(action)
        else:
            argv=['/usr/sbin/runuser','-u','user','--','/usr/bin/env','-i','HOME=/home/user',
                  'XDG_RUNTIME_DIR=/run/user/1000','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus',
                  'PATH=/usr/bin:/bin','/usr/bin/systemctl','--user',*action]
            p=subprocess.run(argv,stdin=subprocess.DEVNULL,capture_output=True,timeout=min(10,self.budget()))
            self.readonly_receipts.append({'argv':argv,'actualExitCode':p.returncode,'integerWait':type(p.returncode) is int,
              'stdoutBase64':base64.b64encode(p.stdout).decode(),'stderrBase64':base64.b64encode(p.stderr).decode()})
            need(type(p.returncode) is int and p.returncode==0,'read-only systemd observation failed; stderr='+p.stderr.decode(errors='replace'))
            raw=p.stdout
        return dict(line.split('=',1) for line in raw.decode().splitlines())
    def vision(self):
        v=self.b['proofs']['visionNormal']; value=strict_json(reference(v['receipt']))
        need(timestamp(v['reviewedAt'])<=time.time() and time.time()-timestamp(v['reviewedAt'])<=120,
             'vision root review is stale/not current')
        need(pointer(value,v['statePointer'])=='NORMAL','vision producer is not genuinely NORMAL')
        observed_at=timestamp(pointer(value,v['observedAtPointer']))
        need(0<=time.time()-observed_at<=120,'vision producer observation stale')
        expected=v['owner']; actual=process(expected['pid'])
        need(actual==expected,'vision current producer identity mismatch')
        need(set(v['ownerPointers'])==set(expected),'vision original receipt lacks exact owner pointers')
        for field,p in v['ownerPointers'].items(): need(pointer(value,p)==expected[field],'vision original owner bytes mismatch')
        return {'originalReceiptSha256':v['receipt']['sha256'],'owner':actual,'observedAt':observed_at,
                'newQualificationClaimed':False}
    def preflight(self):
        b=self.b; need(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==b['hostBootId'],'host boot changed')
        need(not absolute(b['journal']).exists(),'GO spent/retry journal already exists')
        root=absolute(b['release']['path']); ancestry(root.parent,(0,)); need(root.exists() if b['operation']==RESTART else not root.exists(),'release absent/already exists for operation')
        need(set(b['release'])=={'path','files','executableFiles'} and b['release']['files'],'release graph omitted')
        need(set(b['release']['executableFiles'])<=set(b['release']['files']),'unknown executable file')
        for name,digest in b['release']['files'].items(): relative(name); need(is_digest(digest),'invalid source graph SHA')
        contents={}
        for item in b['archives']:
            need(set(item)=={'archive','files'},'archive spec fields mismatch')
            raw=reference(item['archive'],MAX_ARCHIVE); members=archive_members(raw,item['files'])
            need(not set(contents)&set(members),'archive overlap'); contents.update(members)
        need({k:sha(v) for k,v in contents.items()}==b['release']['files'],'archive/final source graph mismatch')
        need(contents.get('ai-harness/source-commit.txt',b'').decode().strip()==b['sourceCommit'],'archive source commit does not bind final head')
        for dependency in b['dependencies']:
            need(set(dependency)=={'source','sha256','target'},'dependency fields mismatch')
            relative(dependency['target']); need(dependency['target'].endswith('/node_modules'),'dependency target is not node_modules')
            need(not any(name==dependency['target'] or name.startswith(dependency['target']+'/') for name in contents),'archive contains dependency mutation')
            need(dependency_digest(Path(dependency['source']))==dependency['sha256'],'immutable dependency source graph changed')
        for ref in b['configFiles']: reference(ref)
        approval=reference(b['proofs']['ordinaryApproval'],262144,True)
        key_spec=b['proofs']['ordinaryKey']; key=protected(key_spec['path'],1000,32,True)
        need(len(key)==32 and identity(Path(key_spec['path']))==key_spec['identity'],'original ordinary key identity mismatch')
        envelope=strict_json(approval); need(set(envelope)=={'body','seal'} and is_digest(envelope['seal']) and
            hmac.compare_digest(envelope['seal'],hmac.new(key,canonical(envelope['body']),hashlib.sha256).hexdigest()),'original ordinary approval HMAC mismatch')
        q=envelope['body'].get('qualification',{})
        need(q.get('binaryVersion')=='0.158.0' and q.get('upstream')=='064c6b8c737f5b41d171fdda80bd9ef10ad06eb3','original ordinary native pins missing')
        for name in ('launch','settlement','protocolAck','binary'):
            reference({'path':q[name+'Path'],'sha256':q[name+'Sha256'],'uid':1000},512*1024*1024 if name=='binary' else MAX_FILE,True)
        original=protected(b['unit']['path'],1000)
        need(sha(original)==b['unit']['sha256'],'current unit bytes mismatch')
        candidate=reference(b['unit']['candidate']); options=unit_candidate(original,candidate,b['unit'],b)
        state=self.state(); need(state['ActiveState']=='active' and state['SubState']=='running' and state['NRestarts']=='0' and
            int(state['MainPID'])==b['owner']['pid'],'normal service not current single active owner')
        owner=exact_owner(b['owner'],state['InvocationID']); idle=database_state(b['data']); vision=self.vision()
        need(owner['selectedEnvironment']['AI_HARNESS_DATA_DIR']==b['data']['path'],'current data path differs')
        if b['operation']==RESTART: self.verify_staged()
        return {'contents':contents,'original':original,'candidate':candidate,'options':options,'owner':owner,'idle':idle,'vision':vision}
    def stage(self,prepared):
        root=Path(self.b['release']['path']); self.budget(90); root.mkdir(mode=0o700)
        for name,body in prepared['contents'].items():
            target=root/name; target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as stream: stream.write(body); stream.flush(); os.fsync(stream.fileno())
        for dependency in self.b['dependencies']:
            need(dependency_digest(Path(dependency['source']))==dependency['sha256'],'dependency source changed before copy')
            target=root/dependency['target']; target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            shutil.copytree(dependency['source'],target,symlinks=True)
            need(dependency_digest(target)==dependency['sha256'],'copied dependency graph mismatch')
        dependency_targets={v['target'] for v in self.b['dependencies']}
        for parent,dirs,files in os.walk(root,followlinks=False):
            dirs[:]=[name for name in dirs if str((Path(parent)/name).relative_to(root)) not in dependency_targets]
            for name in files:
                p=Path(parent)/name
                if not p.is_symlink(): os.chmod(p,0o555 if str(p.relative_to(root)) in self.b['release']['executableFiles'] or p.stat().st_mode&0o111 else 0o444)
            for name in dirs:
                p=Path(parent)/name
                if not p.is_symlink(): os.chmod(p,0o555)
        os.chmod(root,0o555)
        for name,digest in self.b['release']['files'].items(): need(sha(protected(root/name,0))==digest,'staged source graph mismatch')
        self.record('stage.json',{'sourceCommit':self.b['sourceCommit'],'files':self.b['release']['files'],
                    'dependencies':self.b['dependencies'],'buildInstallMutation':False})
    def verify_staged(self):
        root=absolute(self.b['release']['path']); ancestry(root,(0,))
        need(root.lstat().st_uid==0 and not root.lstat().st_mode&0o222,'staged release is not immutable root owned')
        deps=[v['target'] for v in self.b['dependencies']]; actual=set()
        for parent,dirs,files in os.walk(root,followlinks=False):
            dirs[:]=[name for name in dirs if str((Path(parent)/name).relative_to(root)) not in deps]
            for name in files:
                p=Path(parent)/name; rel=str(p.relative_to(root))
                need(not p.is_symlink() and rel in self.b['release']['files'],'staged source extra/link file')
                need(not p.lstat().st_mode&0o222 and sha(protected(p,0))==self.b['release']['files'][rel],'staged source changed/writable')
                actual.add(rel)
        need(actual==set(self.b['release']['files']),'staged source graph incomplete')
        for dep in self.b['dependencies']:
            need(dependency_digest(root/dep['target'])==dep['sha256'],'staged dependency graph changed')

    def backup(self):
        source=sqlite3.connect((Path(self.b['data']['path'])/'harness.sqlite').as_uri()+'?mode=ro',uri=True,timeout=3)
        destination=self.journal/'database-before.private.sqlite'; fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600); os.close(fd)
        target=sqlite3.connect(str(destination))
        try:
            source.execute('PRAGMA query_only=ON')
            source.backup(target,pages=128,progress=lambda *args:self.budget(90),sleep=.01)
            need(target.execute('PRAGMA integrity_check').fetchall()==[('ok',)],'private backup integrity failed')
        finally: target.close(); source.close()
        self.record('database-backup.json',{'path':str(destination),'sha256':sha(destination.read_bytes()),'restorationPermitted':False})
    def replace_unit(self,body,expected):
        path=Path(self.b['unit']['path']); original=protected(path,1000); need(sha(original)==expected,'unit changed before mutation')
        self.budget(30); temporary=path.with_name(path.name+'.'+self.b['goId']+'.new')
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(body); stream.flush(); os.fsync(stream.fileno()); os.fchown(stream.fileno(),1000,1000); os.fchmod(stream.fileno(),path.stat().st_mode&0o777)
        need(sha(protected(path,1000))==expected,'unit changed during replacement')
        os.replace(temporary,path); fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    def ordinary_loader(self,options):
        root=self.b['release']['path']; node=options['--node-prefix']+'/bin/node'
        code="import{loadCodexOrdinaryEntry}from './ai-harness/server/dist/codex-ordinary-entry.js';const [approval,key,serverDir,deploymentDir]=process.argv.slice(1);if(!loadCodexOrdinaryEntry(approval,key,{serverDir,deploymentDir}))throw Error('ordinary admission absent');console.log('ORIGINAL_ORDINARY_LOADER_ACCEPTED_SOURCE_ONLY');"
        self.command('original-ordinary-loader',['/usr/sbin/runuser','-u','user','--','/usr/bin/env','-i','HOME=/home/user',
          'PATH=/usr/bin:/bin','LANG=C.UTF-8',node,'--input-type=module','-e',code,options['--codex-ordinary-entry'],
          options['--codex-ordinary-entry-key'],root+'/ai-harness/server',root+'/ai-harness/deploy'],root)
    def fresh_owner(self,options):
        state=self.state(); need(state['ActiveState']=='active' and state['SubState']=='running' and state['NRestarts']=='0','new normal owner not running')
        p=process(int(state['MainPID'])); need(p['uid']==1000 and p['gid']==1000 and p['bootId']==self.b['hostBootId'] and
            p['cgroup']==self.b['owner']['cgroup'] and p['exe']==self.b['owner']['exe'] and state['InvocationID']!=self.b['owner']['invocationId'] and
            p['selectedEnvironment']['AI_HARNESS_WEB_DIST']==self.b['release']['path']+'/ai-harness/web/dist' and
            p['selectedEnvironment']['AI_HARNESS_ENGINE_LAUNCHER']==self.b['release']['path']+'/ai-harness/deploy/run-engine.sh' and
            p['selectedEnvironment']['AI_HARNESS_DATA_DIR']==self.b['data']['path'],'new source/data/owner tuple mismatch')
        args=[p['exe'],self.b['release']['path']+'/ai-harness/server/dist/codex-preview-main.js',options['--codex-preview-receipt'],'65536']
        if '--codex-owned-acceptance-policy' in options:
            args.extend(['image-jobs-unqualified',options['--codex-owned-acceptance-policy']])
        if '--codex-specialist-qualification' in options: args.append(options['--codex-specialist-qualification'])
        need((Path('/proc')/str(p['pid'])/'cmdline').read_bytes()==b'\0'.join(v.encode() for v in args)+b'\0','new command bytes differ from reviewed launcher options')
        need(owner_absent(self.b['owner']) and group_absent(self.b['owner']['pgid']),'old birth/process group retained')
        p['invocationId']=state['InvocationID']; return p
    def health(self):
        self.budget(10); request=urllib.request.Request('http://127.0.0.1:8080/api/health',headers={'Host':'10.156.100.61','Origin':'http://10.156.100.61'})
        with urllib.request.urlopen(request,timeout=5) as response:
            need(response.status==200,'health HTTP failure'); raw=response.read(131073)
        need(len(raw)<=131072,'health response oversized'); value=strict_json(raw)
        need(value.get('status')=='ok' and value.get('engines',{}).get('codex',{}).get('available') is True,'ordinary health unavailable')
        self.record('health.json',{'rawBase64':base64.b64encode(raw).decode(),'sha256':sha(raw),'inferenceTurns':0}); return value
    def rollback(self,prepared,new_owner):
        need(self.b['counts']['rollback']==ROLLBACK,'rollback not explicitly enumerated in GO')
        need(sha(protected(self.b['unit']['path'],1000))==self.b['unit']['candidate']['sha256'],'candidate unit no longer owned')
        state=self.state(); pid=int(state['MainPID'])
        if pid:
            need(new_owner is not None and pid==new_owner['pid'],'rollback refuses an unobserved/uncertain live owner')
            exact_owner(new_owner,state['InvocationID'])
        else: need(state['ActiveState'] in ('inactive','failed'),'rollback service state uncertain')
        database_state(self.b['data']); self.replace_unit(prepared['original'],self.b['unit']['candidate']['sha256'])
        self.manager(['daemon-reload']); self.manager(['restart','ai-harness.service'])
        state=self.state(); need(state['ActiveState']=='active' and state['SubState']=='running','original service rollback not running')
        restored=process(int(state['MainPID'])); need(restored['selectedEnvironment']==self.b['owner']['selectedEnvironment'] and
            restored['exe']==self.b['owner']['exe'] and restored['cgroup']==self.b['owner']['cgroup'],'rollback original owner graph mismatch')
        database_state(self.b['data']); self.record('rollback.json',{'status':'ORIGINAL_UNIT_RESTORED_NO_WORKFLOW_CLAIM','owner':restored})
    def execute(self):
        prepared=self.preflight(); self.claim(); self.record('intent.json',{'goBodySha256':sha(canonical(self.b)),
            'sourceCommit':self.b['sourceCommit'],'owner':prepared['owner'],'idle':prepared['idle'],'vision':prepared['vision'],'inferenceTurns':0})
        self.record('original-unit.private',raw=prepared['original']); changed=False; new_owner=None
        try:
            self.backup()
            if self.b['operation']==STAGE:
                self.stage(prepared); self.verify_staged()
                state=self.state(); exact_owner(self.b['owner'],state['InvocationID']); database_state(self.b['data']); self.vision()
                need(sha(protected(self.b['unit']['path'],1000))==self.b['unit']['sha256'],'stage altered existing unit')
                result={'status':'STAGED_COMPILED_SOURCE_ONLY_NO_RESTART','sourceCommit':self.b['sourceCommit'],
                  'journal':str(self.journal),'nativeWorkflowAcceptance':'NOT_TESTED','inferenceTurns':0,'restarts':0}
                self.record('RESULT.json',result); return result
            self.verify_staged(); self.ordinary_loader(prepared['options']); self.budget(90)
            state=self.state(); exact_owner(self.b['owner'],state['InvocationID']); database_state(self.b['data']); self.vision()
            for ref in self.b['configFiles']: reference(ref)
            changed=True; self.replace_unit(prepared['candidate'],self.b['unit']['sha256'])
            self.manager(['daemon-reload']); self.manager(['restart','ai-harness.service'])
            new_owner=self.fresh_owner(prepared['options']); self.health(); database_state(self.b['data'])
            need(sha(protected(self.b['unit']['path'],1000))==self.b['unit']['candidate']['sha256'],'new unit changed')
            self.record('RESULT.json',{'status':'NORMAL_RESTARTED_HEALTH_ONLY','owner':new_owner,'sourceCommit':self.b['sourceCommit'],
              'inferenceTurns':0,'nativeWorkflowAcceptance':'NOT_TESTED','UIAcceptance':'NOT_TESTED','finishedUtc':utc()})
            return {'status':'NORMAL_RESTARTED_HEALTH_ONLY','journal':str(self.journal),'owner':new_owner}
        except Exception as error:
            self.record('failure.json',{'type':type(error).__name__,'message':str(error),'unitMutationAttempted':changed,'finishedUtc':utc()})
            if changed and self.b['counts']['rollback']==ROLLBACK:
                try: self.rollback(prepared,new_owner)
                except Exception as rollback_error: self.record('rollback-failure.json',{'type':type(rollback_error).__name__,'message':str(rollback_error)})
            raise

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--go',required=True); parser.add_argument('--go-key',required=True)
    parser.add_argument('--execute',action='store_true'); args=parser.parse_args()
    need(sys.platform=='linux' and os.geteuid()==0,'only root on Linux may observe/execute deployment controls')
    helper=absolute(str(Path(__file__).absolute())); helper_raw=protected(helper,0)
    key=protected(args.go_key,0,4096,True); envelope=strict_json(protected(args.go,0,1024*1024,True))
    body=validate_go(envelope,key,time.time(),helper,sha(helper_raw)); control=Control(body)
    if args.execute: result=control.execute()
    else:
        prepared=control.preflight(); result={'status':'PREFLIGHT_SOURCE_AND_CURRENT_TUPLES_MATCH','sourceCommit':body['sourceCommit'],
           'owner':prepared['owner'],'vision':prepared['vision'],'mutations':0,'nativeWorkflowAcceptance':'NOT_TESTED',
           'ordinaryLoaderBeforeRestartRequired':True,'inferenceTurns':0,'readOnlyCommandReceipts':control.readonly_receipts}
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__':
    os.umask(0o077)
    try: main()
    except Exception as error:
        print(json.dumps({'status':'DENIED_OR_FAILED','type':type(error).__name__,'message':str(error)},sort_keys=True),file=sys.stderr)
        raise SystemExit(1)
