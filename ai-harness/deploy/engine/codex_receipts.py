"""Host-only bounded nonce channel for the existing task supervisor; no native payloads."""
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import time

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
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('receipt identity changed')
        raw = os.read(fd, MAX_BYTES + 1)
        if len(raw) != info.st_size or len(raw) > MAX_BYTES:
            raise ValueError('receipt bound exceeded')
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
    raw = json.dumps(value, separators=(',', ':'), allow_nan=False).encode()
    if len(raw) > MAX_BYTES:
        raise ValueError('receipt bound exceeded')
    protected(path, True)
    fd = os.open(path / (name + '.json'), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        while raw:
            written = os.write(fd, raw); raw = raw[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    fd = os.open(path / (name + '.ready'), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.fsync(fd); os.close(fd)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY); os.fsync(fd); os.close(fd)


def process_identity(pid=None):
    pid = pid or os.getpid()
    text = Path('/proc') / str(pid) / 'stat'
    raw = text.read_text(); fields = raw[raw.rfind(')') + 2:].split()
    cg = (Path('/proc') / str(pid) / 'cgroup').read_text().strip()
    if not cg.startswith('0::/') or '\n' in cg:
        raise ValueError('unqualified cgroup identity')
    return {'pid': pid, 'startTicks': fields[19], 'uid': os.getuid(),
            'bootId': Path('/proc/sys/kernel/random/boot_id').read_text().strip(), 'cgroupPath': cg[3:]}


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
    selector = selectors.DefaultSelector(); selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout; result = bytearray()
    try:
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
        selector.close(); process.stdout.close()
        if process.poll() is None:
            process.kill()
        # Never communicate() after timeout: a retained pipe can outlive its CLI.
        process.wait(timeout=1)


def inspect_launch(podman, container, args, config):
    path, binding = config
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
