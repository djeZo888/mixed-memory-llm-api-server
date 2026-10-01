"""Host-only bounded nonce channel for the existing task supervisor; no native payloads."""
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import selectors
import stat
import subprocess
import sys
import time
import uuid

SOURCES = ('run-codex.sh', 'engine/task-egress.py', 'engine/redact-acp.py',
           'engine/codex_receipts.py', 'engine/codex_native_trace.py', 'security/chromium-seccomp.json',
           'codex/config.toml', 'codex/models.json')
MAX_BYTES = 32768


def protected(path, directory=False):
    info = path.lstat()
    mode = 0o700 if directory else 0o600
    if stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != mode:
        raise ValueError('unsafe private receipt channel')
    if directory and (not stat.S_ISDIR(info.st_mode) or path.resolve() != path):
        raise ValueError('unsafe receipt directory')
    if not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 2 <= info.st_size <= MAX_BYTES):
        raise ValueError('unsafe receipt file')


def read_private(path):
    protected(path)
    before = path.lstat()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (info.st_uid != os.getuid() or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600
            or not stat.S_ISREG(info.st_mode) or (before.st_dev,before.st_ino)!=(info.st_dev,info.st_ino)):
            raise ValueError('receipt identity changed')
        raw = os.read(fd, MAX_BYTES + 1)
        if len(raw) != info.st_size or len(raw) > MAX_BYTES:
            raise ValueError('receipt bound exceeded')
        after = path.lstat(); final = os.fstat(fd)
        stable = lambda q:(q.st_dev,q.st_ino,q.st_size,q.st_mtime_ns,q.st_ctime_ns,q.st_nlink)
        if stable(info)!=stable(final) or stable(info)!=stable(after):raise ValueError('original changed during read')
        return json.loads(raw)
    finally:
        os.close(fd)


def channel():
    directory = os.environ.get('AI_HARNESS_CODEX_RECEIPT_DIR')
    nonce = os.environ.get('AI_HARNESS_CODEX_RECEIPT_NONCE')
    if not directory and not nonce:
        return None
    if not directory or not nonce or re.fullmatch('[0-9a-f]{64}', nonce) is None:
        raise ValueError('incomplete receipt transport')
    root = Path('/run/user') / str(os.getuid()) / 'ai-harness-codex-receipts'
    path = Path(directory)
    if path.parent != root or not path.name.startswith('run-'):
        raise ValueError('unexpected host-only receipt root')
    protected(root, True); protected(path, True)
    value = read_private(path / 'request.json')
    required = {'nonce', 'runId', 'sessionId', 'startedAtMs', 'uid', 'profileDir', 'workspace', 'deploymentDir', 'imageJobsQualified', 'gid', 'sources'}
    if set(value) != required | ({'nativeTraceMode'} if 'nativeTraceMode' in value else set()) or value.get('nativeTraceMode') not in (None,'post-sampling-token-usage-v1') or value.get('nativeTraceMode') != os.environ.get('AI_HARNESS_CODEX_TRACE_MODE') or value['nonce'] != nonce or value['uid'] != os.getuid() or value['gid'] != os.getgid() or value['sessionId'] != os.environ.get('AI_HARNESS_SESSION_ID') or not all(isinstance(value[k], str) and re.fullmatch('[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', value[k]) for k in ('runId','sessionId')):
        raise ValueError('unbound receipt request')
    deployment = Path(__file__).resolve().parent.parent
    if value['deploymentDir'] != str(deployment) or type(value['imageJobsQualified']) is not bool:
        raise ValueError('unbound receipt deployment')
    for scope in ('profileDir', 'workspace'):
        p = Path(value[scope])
        if not p.is_absolute() or p.resolve() != p or p == root or p in root.parents or root in p.parents or p == deployment or p in deployment.parents:
            raise ValueError('receipt/source overlap with native scope')
    if set(value['sources']) != set(SOURCES):
        raise ValueError('incomplete source receipt')
    for relative, expected in value['sources'].items():
        p = deployment / relative; info = p.lstat()
        for parent in (p.parent, *p.parents):
            if parent == deployment.parent: break
            s = parent.lstat()
            if stat.S_ISLNK(s.st_mode) or not stat.S_ISDIR(s.st_mode) or s.st_uid not in (0, os.getuid()) or s.st_mode & 0o022: raise ValueError('unsafe receipt source ancestry')
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, os.getuid()) or info.st_mode & 0o022 or hashlib.sha256(p.read_bytes()).hexdigest() != expected:
            raise ValueError('unreviewed receipt producer bytes')
    return path, value


def write_once(path, name, value):
    """Publish complete bytes atomically, then durable readiness; never replace originals."""
    if re.fullmatch(r'[a-z][a-z0-9-]{0,63}', name) is None:
        raise ValueError('unsafe receipt name')
    raw = json.dumps(value, separators=(',', ':'), allow_nan=False).encode()
    if not 2 <= len(raw) <= MAX_BYTES:
        raise ValueError('receipt bound exceeded')
    protected(path, True)
    temporary = path / ('.receipt-' + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        remaining = raw
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0: raise OSError('receipt write made no progress')
            remaining = remaining[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.link(temporary, path / (name + '.json'), follow_symlinks=False)
    finally:
        temporary.unlink()
    directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
        fd = os.open(path / (name + '.ready'), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try: os.fsync(fd)
        finally: os.close(fd)
        os.fsync(directory)
    finally: os.close(directory)


def process_identity(pid=None):
    pid = os.getpid() if pid is None else pid
    proc = Path('/proc') / str(pid)
    raw = (proc / 'stat').read_text(); fields = raw[raw.rfind(')') + 2:].split()
    ids = next(line.split()[1:] for line in (proc / 'status').read_text().splitlines() if line.startswith('Uid:'))
    if ids != [str(os.getuid())] * 4: raise ValueError('producer UID mismatch')
    cg = (proc / 'cgroup').read_text().strip()
    if not cg.startswith('0::/') or '\n' in cg:
        raise ValueError('unqualified cgroup identity')
    again = (proc / 'stat').read_text(); after = again[again.rfind(')') + 2:].split()
    if fields[19] != after[19]: raise ValueError('producer birth changed')
    return {'pid': pid, 'startTicks': fields[19], 'uid': os.getuid(),
            'bootId': Path('/proc/sys/kernel/random/boot_id').read_text().strip(), 'cgroupPath': cg[3:]}


def original(config, name):
    path, binding = config
    ready = path / (name + '.ready'); info = ready.lstat()
    if (stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
        or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size != 0):
        raise ValueError('original not durably ready')
    value = read_private(path / (name + '.json'))
    schemas = {'scope-intent':'codex-scope-intent-v1','scope-creator':'codex-scope-creator-v1',
               'scope':'codex-scope-original-v1','producer':'codex-producer-original-v1',
               'cli':'codex-cli-original-v1','cli-terminal':'codex-cli-terminal-v1',
               'cleanup':'codex-cleanup-original-v1','scope-terminal':'codex-scope-terminal-v1'}
    if name not in schemas or value.get('schema') != schemas[name]:
        raise ValueError('untrusted original causal schema')
    if any(value.get(k) != binding[k] for k in ('nonce', 'runId', 'sessionId', 'sources')):
        raise ValueError('unbound original causal receipt')
    return value


def causal(config, schema, **facts):
    _, binding = config
    return dict(schema=schema, nonce=binding['nonce'], runId=binding['runId'],
                sessionId=binding['sessionId'], sources=binding['sources'], checkedAtMs=int(time.time()*1000), **facts)


def publish_scope_intent(config, unit, parent):
    if re.fullmatch(r'ai-harness-codex-[0-9a-f]{32}\.scope', unit) is None:
        raise ValueError('scope unit must be source-chosen unique original')
    value = causal(config, 'codex-scope-intent-v1', unit=unit, parent=parent,
                   creationState='PENDING', interpreter=str(Path(sys.executable).resolve()),
                   creatorSource=str(Path(__file__).resolve().with_name('task-egress.py')),
                   redactorSource=str(Path(__file__).resolve().with_name('redact-acp.py')),
                   intendedChain=['engine/task-egress.py:create-scope', '/usr/bin/systemd-run',
                                  'engine/task-egress.py:inside-scope', 'engine/redact-acp.py'])
    write_once(config[0], 'scope-intent', value); return value


def publish_scope_creator(config, intent, creator):
    if original(config, 'scope-intent') != intent or process_identity(intent['parent']['pid']) != intent['parent']:
        raise ValueError('scope creator lost original parent')
    value = causal(config, 'codex-scope-creator-v1', unit=intent['unit'], parent=intent['parent'], creator=creator)
    write_once(config[0], 'scope-creator', value); return value


def verify_creator(config, unit):
    intent = original(config, 'scope-intent'); creator = original(config, 'scope-creator')
    if intent['unit'] != unit or creator['unit'] != unit or creator['parent'] != intent['parent']:
        raise ValueError('contradictory scope creation originals')
    if process_identity() != creator['creator'] or process_identity(os.getppid()) != intent['parent']:
        raise ValueError('unowned creation subprocess')
    return intent, creator


def scope_original(config, prefix):
    intent = original(config, 'scope-intent'); creator = original(config, 'scope-creator'); me = process_identity()
    if creator['parent'] != intent['parent'] or creator['unit'] != intent['unit']:
        raise ValueError('contradictory original scope chain')
    expected = '/' + prefix + '/' + intent['unit']
    if me['cgroupPath'] != expected: raise ValueError('actual scope differs from original intent')
    # systemd255 scope attaches its own PID then execs the command. Require that
    # observed same-PID/birth chain; different runtime semantics fail closed.
    if any(me[k] != creator['creator'][k] for k in ('pid','startTicks','uid','bootId')):
        raise ValueError('inside scope is not the original exec creator')
    parent = process_identity(os.getppid())
    if parent != intent['parent']:
        raise ValueError('original parent lost')
    chain = [me, parent]
    result = subprocess.run(['/usr/bin/systemctl', '--user', '--no-ask-password', '--no-pager', 'show',
                             intent['unit'], '--property=Id,LoadState,ActiveState,ControlGroup,InvocationID'],
                            capture_output=True, timeout=3, check=False)
    if result.returncode != 0: raise ValueError('actual scope inspection failed')
    values = dict(line.split('=', 1) for line in result.stdout.decode().splitlines() if '=' in line)
    if (values.get('Id') != intent['unit'] or values.get('LoadState') != 'loaded'
        or values.get('ActiveState') != 'active' or values.get('ControlGroup') != expected
        or re.fullmatch('[0-9a-f]{32}', values.get('InvocationID', '')) is None):
        raise ValueError('actual scope not authenticated')
    scope_path = Path('/sys/fs/cgroup') / expected.lstrip('/')
    info = scope_path.lstat()
    if not stat.S_ISDIR(info.st_mode) or scope_path.resolve() != scope_path or info.st_uid != os.getuid():
        raise ValueError('unsafe actual scope inode')
    value = causal(config, 'codex-scope-original-v1', unit=intent['unit'], parent=intent['parent'],
                   creator=creator['creator'], producer=me, ancestorChain=chain,
                   scope=dict(path=expected, dev=info.st_dev, inode=info.st_ino,
                              invocationId=values['InvocationID']), inspectionExit=result.returncode)
    write_once(config[0], 'scope', value); return value


def publish_producer(config, producer, container):
    scope = original(config, 'scope')
    if scope['producer'] != producer or process_identity() != producer:
        raise ValueError('redactor must be the actual original scoped producer')
    if re.fullmatch('ai-harness-[0-9a-f]{32}', container) is None:
        raise ValueError('unbound random container name')
    value = causal(config, 'codex-producer-original-v1', producer=producer,
                   containerName=container, unit=scope['unit'], scope=scope['scope'],
                   parent=scope['parent'], creator=scope['creator'], childCreationState='NOT_STARTED')
    write_once(config[0], 'producer', value); return value


def publish_scope_terminal(config, intent, creator, raw_exit, requested_signal, failure):
    value = causal(config, 'codex-scope-terminal-v1', unit=intent['unit'], parent=intent['parent'],
                   creator=creator, creatorExit=raw_exit, creatorReaped=type(raw_exit) is int,
                   requestedSignal=requested_signal, failureClass=type(failure).__name__ if failure else None,
                   failureSha256=hashlib.sha256(str(failure).encode()).hexdigest() if failure else None,
                   resourceState='UNKNOWN')
    write_once(config[0], 'scope-terminal', value)


def publish_egress(prefix):
    config = channel()
    if config is None:
        return
    path, _ = config
    source = Path('/run/ai-harness-egress/verified.json')
    raw = source.read_bytes(); value = json.loads(raw)
    now = time.clock_gettime(time.CLOCK_BOOTTIME)
    me = process_identity()
    if value['boot_id'] != me['bootId'] or value['uid'] != os.getuid() or value['cgroup_path'] != prefix or not me['cgroupPath'].startswith('/' + prefix + '/') or not 0 <= now - value['checked_boottime'] <= 6:
        raise ValueError('stale receipt egress provenance')
    result = {'bootId': value['boot_id'], 'uid': value['uid'], 'cgroupPath': prefix,
              'cgroupInode': value['cgroup_inode'], 'nftSha256': value['nft_sha256'],
              'checkedBoottime': value['checked_boottime'], 'receiptSha256': hashlib.sha256(raw).hexdigest()}
    write_once(path, 'egress', result)


def capture(podman, args, timeout=3):
    # Inspect output can include the scoped token. It is never logged or copied into a receipt.
    process = subprocess.Popen([podman, '--remote=false', *args], stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    selector = None
    deadline = time.monotonic() + timeout; result = bytearray()
    try:
        selector = selectors.DefaultSelector(); selector.register(process.stdout, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise ValueError('bounded native inspection timed out')
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk: break
            result.extend(chunk)
            if len(result) > 1024 * 1024:
                raise ValueError('native inspection size exceeded')
        if process.wait(timeout=max(0.001, deadline-time.monotonic())) != 0:
            raise ValueError('bounded native inspection failed')
        return bytes(result)
    finally:
        try:
            if selector is not None: selector.close()
        finally:
            try: process.stdout.close()
            finally:
                try:
                    if process.poll() is None: process.kill()
                finally:
                    # Never communicate after timeout; always attempt the real reap.
                    process.wait(timeout=1)


def inspect_launch(podman, container, args, config):
    path, binding = config
    gate = original(config, 'producer')
    if gate['producer'] != process_identity() or gate['containerName'] != container:
        raise ValueError('missing genuine original launch producer gate')
    # Fresh nonce is deliberately absent from the native environment and all mounts.
    forbidden = str(path.parent)
    volumes = []
    for i, arg in enumerate(args):
        if arg == '--volume':
            src, dst, options = args[i+1].split(':')
            if src == forbidden or src.startswith(forbidden+'/') or forbidden.startswith(src+'/'):
                raise ValueError('receipt channel exposed to native mount')
            volumes.append({'source': src, 'destination': dst, 'rw': options.startswith('rw,'), 'type': 'bind'})
    if len(volumes) != 7:
        raise ValueError('unexpected receipt mount policy')
    deadline = time.monotonic() + 10
    while True:
        try:
            values = json.loads(capture(podman, ['inspect', container]))
            c = values[0]
            if not c['State']['Running']:
                raise ValueError('native process not running')
            break
        except (ValueError, KeyError, IndexError):
            if time.monotonic() >= deadline:
                raise ValueError('native launch identity unavailable')
            time.sleep(0.05)
    host, native = c['HostConfig'], c['Config']
    if c['Name'].removeprefix('/') != container:
        raise ValueError('actual native container name mismatch')
    actual_mounts = [{'source': m['Source'], 'destination': m['Destination'], 'rw': m['RW'], 'type': m['Type']} for m in c['Mounts'] if m['Type'] == 'bind']
    additional_mounts = [{'source': m.get('Source', ''), 'destination': m['Destination'], 'rw': m['RW'], 'type': m['Type']} for m in c['Mounts'] if m['Type'] != 'bind']
    # Do not silently hide an image-declared volume or an extra oracle mount.
    # Podman inspection formats themselves still require Linux qualification.
    if (any(m['type'] != 'tmpfs' or m['source'] != '' or m['rw'] is not True or m['destination'] not in ('/tmp', '/run', '/var/tmp') for m in additional_mounts)
            or len({m['destination'] for m in additional_mounts}) != len(additional_mounts)):
        raise ValueError('unexpected additional native mount')
    sort = lambda xs: sorted(xs, key=lambda m: (m['source'],m['destination']))
    caps = sorted(x.upper() for x in host['CapDrop'])
    security = host['SecurityOpt']
    if (sort(actual_mounts) != sort(volumes) or host['Privileged'] is not False or host['ReadonlyRootfs'] is not True or caps != ['ALL'] or c.get('EffectiveCaps') != [] or host['NetworkMode'] != 'slirp4netns:allow_host_loopback=true' or host['UsernsMode'] != 'keep-id' or native['User'] != str(os.getuid())+':'+str(os.getgid()) or native['WorkingDir'] != binding['workspace'] or 'no-new-privileges' not in security or not any(s.startswith('seccomp=') for s in security)):
        raise ValueError('actual native isolation differs from reviewed launch')
    if capture(podman, ['info','--format','{{.Host.Security.Rootless}}']).strip() != b'true':
        raise ValueError('actual rootless inspection failed')
    image = json.loads(capture(podman, ['image','inspect',c['Image']]))[0]
    labels = image['Config']['Labels']; image_id = image['Id'].removeprefix('sha256:')
    if image_id != 'd8841743002e16de1f9269a850a2f06a73055688befec4c309778ca8a4c11aad' or labels.get('org.opencontainers.image.revision') != '064c6b8c737f5b41d171fdda80bd9ef10ad06eb3' or labels.get('org.opencontainers.image.ai-harness.patchset') != 'dd0ff12a651db4cc8521cddb8e5094c5a197ca87cef6b7ec797343da67d9f1ec':
        raise ValueError('actual image pin mismatch')
    egress = read_private(path / 'egress.json')
    result = dict(schema='codex-launch-v1', nonce=binding['nonce'], runId=binding['runId'], sessionId=binding['sessionId'],
                  checkedAtMs=int(time.time()*1000), producer=process_identity(), sources=binding['sources'], egress=egress,
                  container={'id': c['Id'], 'name': container, 'imageId': 'sha256:'+image_id,
                   'imageRevision': labels['org.opencontainers.image.revision'], 'imagePatchset': labels['org.opencontainers.image.ai-harness.patchset'],
                   'pid': c['State']['Pid'], 'pidStartTicks': process_identity(c['State']['Pid'])['startTicks'],
                   'rootless': True, 'user': native['User'], 'network': host['NetworkMode'], 'capDrop': caps,
                   'securityOpt': security, 'readOnly': host['ReadonlyRootfs'], 'privileged': host['Privileged'],
                   'mounts': sort(actual_mounts), 'additionalMounts': sort(additional_mounts), 'workdir': native['WorkingDir'], 'profileDir': binding['profileDir'], 'workspace': binding['workspace']})
    if binding.get('nativeTraceMode'):
        expected={'RUST_LOG':'off,codex_core::session::turn=trace','LOG_FORMAT':'json'}
        observed={}
        for key in expected:
            values=[x[len(key)+1:] for x in native.get('Env',[]) if x.startswith(key+'=')]
            if values != [expected[key]]:raise ValueError('trace environment not independently observed')
            observed[key]=values[0]
        write_once(path,'trace-env',{'schema':'codex-trace-env-v1','nonce':binding['nonce'],'runId':binding['runId'],'sessionId':binding['sessionId'],'producer':result['producer'],'containerId':c['Id'],'environment':observed})
    write_once(path, 'launch', result)
    return result


def publish_settlement(config, producer, container, native_id, raw_exit, requested_stop,
                       cli_reaped, rm_exit, exists_exit, pipes_joined):
    if config is None:
        return
    path, binding = config
    write_once(path, 'settlement', dict(schema='codex-settlement-v1', nonce=binding['nonce'], runId=binding['runId'], sessionId=binding['sessionId'], checkedAtMs=int(time.time()*1000), producer=producer,
               containerName=container, containerId=native_id, engineExitStatus=raw_exit, requestedStop=requested_stop,
               cliReaped=cli_reaped, rmExit=rm_exit, existsExit=exists_exit, pipesJoined=pipes_joined,
               cleanupOk=cli_reaped and rm_exit == 0 and exists_exit == 1 and pipes_joined))


def publish_failure(config, producer, phase, error):
    """Out-of-band fixed phase/class/hash. No raw error, config, token or stderr."""
    if phase not in ['bootstrap','spawn','inspect-launch','run','cleanup']:
        raise ValueError('untrusted failure phase')
    path,binding=config
    result=dict(schema='codex-launch-failure-v1',nonce=binding['nonce'],sessionId=binding['sessionId'],runId=binding['runId'],producer=producer,phase=phase,errorClass=type(error).__name__,messageSha256=hashlib.sha256(str(error).encode()).hexdigest(),checkedAtMs=int(time.time()*1000))
    write_once(path,'failure',result)


def publish_cli(config, producer, container, pid):
    value = original(config, 'producer')
    if value['producer'] != producer or value['containerName'] != container:
        raise ValueError('unbound CLI creation')
    child = process_identity(pid)
    write_once(config[0], 'cli', causal(config, 'codex-cli-original-v1', producer=producer,
               containerName=container, child=child, pgid=os.getpgid(pid)))


def publish_cleanup(config, producer, container, process, rm_exit, exists_exit,
                    pipes_joined, pipe_error, requested_signal, observed_error):
    # Additive facts do not change the strict existing launch/settlement schema.
    write_once(config[0], 'cleanup', causal(config, 'codex-cleanup-original-v1', producer=producer,
               containerName=container, childCreated=process is not None,
               childPid=process.pid if process is not None else None,
               cliExit=process.returncode if process is not None else None,
               cliReaped=process is not None and type(process.returncode) is int,
               rmExit=rm_exit, existsExit=exists_exit, pipesJoined=pipes_joined,
               pipeError=pipe_error, requestedSignal=requested_signal, observedError=observed_error))


def publish_cli_terminal(config, producer, container, process):
    if process is None or type(process.returncode) is not int: return
    write_once(config[0], 'cli-terminal', causal(config, 'codex-cli-terminal-v1',
               producer=producer, containerName=container, childPid=process.pid,
               actualExit=process.returncode, reaped=True))


def publish_cleanup_terminal(config, producer, container, name, pid, identity, raw_exit, error):
    if name not in ('rm-terminal','exists-terminal'):raise ValueError('unexpected owned cleanup command')
    write_once(config[0], name, causal(config, 'codex-cleanup-command-v1', producer=producer,
               containerName=container, childPid=pid, child=identity, actualExit=raw_exit,
               reaped=type(raw_exit) is int, errorClass=type(error).__name__ if error else None,
               errorSha256=hashlib.sha256(str(error).encode()).hexdigest() if error else None))


def verify_child_gate(config, producer, container):
    """Reuse unchanged root attestation guard immediately before Podman Popen."""
    gate = original(config, 'producer')
    if gate['producer'] != producer or gate['containerName'] != container or process_identity() != producer:
        raise ValueError('original producer changed before child creation')
    guard = runpy.run_path(str(Path(__file__).resolve().with_name('task-egress.py')))
    prefix = guard['verify']()
    if producer['cgroupPath'] != '/' + prefix + '/' + gate['unit']:
        raise ValueError('actual producer left original protected scope')
