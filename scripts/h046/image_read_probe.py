#!/usr/bin/env python3
"""Fixed, read-only H046 image source/owner probe; emit no raw configuration.

Run through a root-authorized stdin interpreter, without lifecycle or inference
commands. This observation does not confer admission or mutation authority.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

BASE = Path('/data/services/image21-runtime-20260923')
MODEL = Path('/data/models-large/qwen-image-2.1-790c92633540aa0cb11d9abf19eb46d861714758')
RELEASE = Path('/data/services/releases/h037-image-placement-20260930')
ARCHIVE = Path('/data/services/h044-evidence/I-image04-current-owner-424b2823')
API = Path('/usr/local/lib/llm-server/image-api')
EXTERNAL = 'GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23'
READING = 'GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf'
HISTORICAL_CID = '7978d53e33a5502ba7a3b6cf5e6d10a63cfec60829950e565b9a2c4a111579cc'
PATHS = {k: BASE / (k + '.json') for k in ('config', 'state', 'operation', 'recovery')}
PATHS.update(api=Path('/etc/llm-server/image-api.json'), checkpoint=MODEL / 'CHECKPOINT-RECEIPT.json')
PEERS = {
    'Qwen0': 'llmctl-qwen38-27b-q0-480000-yarn4-bf16kv',
    'Qwen1': 'llmctl-qwen38-27b-q1-server-480000-yarn4-bf16kv',
    'MiMo': 'llm-frontier-mimo-production',
    'visionA': '9ac67ee133605261f68fddeb91a9fe272fd43bd3df2fe2af0ef2d8c0aa9e007b',
    'visionB': '959d9c1c63e0108828795b07c496d327123c52040bb55b445bc7f5179ad7d903',
}
PEER_FILES = (
    '/usr/local/lib/llm-server/control-api/configs/deployments/qwen38-27b-q0-480000-yarn4-bf16kv.json',
    '/usr/local/lib/llm-server/control-api/configs/deployments/qwen38-27b-q1-server-480000-yarn4-bf16kv.json',
    '/usr/local/lib/llm-server/control-api/configs/runtimes/h005-runtime-binding.json',
    '/usr/local/lib/llm-server/control-api/configs/runtimes/sglang-qwen38-0.5.19.json',
    '/data/services/mimo-h016-20260927/manifest.json',
    '/data/services/mimo-h016-20260927/selection.json',
    '/data/services/mimo-h016-20260927/state.json',
    '/data/services/mimo-h016-20260927/proxy-state.json',
    '/data/services/mimo-h016-20260927/guard.json',
    '/data/services/mimo-h016-20260927/source/launch.json',
    '/data/services/mimo-h016-20260927/source/owner.py',
    '/data/services/mimo-h016-20260927/source/private_proxy.py',
    '/opt/llm-technical-vision/h044-v03/configs/vision/h043-candidate.json',
    '/data/logs/h044-vision-v03/RUNTIME-GRAPH.json',
)
CGROUP_FIELDS = ('memory.current', 'memory.peak', 'memory.max', 'memory.stat', 'memory.swap.current',
                 'memory.swap.max', 'memory.events', 'memory.events.local',
                 'memory.pressure', 'cgroup.events', 'cgroup.procs', 'pids.current', 'pids.max')


def sha(b):
    return hashlib.sha256(b).hexdigest()


def signature(s):
    return {k: v for k, v in zip(
        ('dev', 'inode', 'mode', 'uid', 'gid', 'nlink', 'size', 'mtimeNs', 'ctimeNs'),
        (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
         s.st_size, s.st_mtime_ns, s.st_ctime_ns))}


def file(path, *, raw=False):
    """No symlink following; prove named/held signature stability while hashing."""
    p = Path(path)
    result = {'path': str(p)}
    fd = None
    try:
        s = p.lstat()
        result['signature'] = signature(s)
        if not stat.S_ISREG(s.st_mode):
            result['type'] = 'directory' if stat.S_ISDIR(s.st_mode) else 'other'
            return (result, None) if raw else result
        if s.st_size > 4000000:
            raise ValueError('fixed_probe_size_bound')
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(fd)
        if signature(before) != signature(s):
            raise ValueError('named_fd_mismatch')
        chunks = []
        while True:
            b = os.read(fd, 65536)
            if not b:
                break
            chunks.append(b)
        b = b''.join(chunks)
        result['sha256'] = sha(b)
        result['stable'] = (signature(os.fstat(fd)) == signature(p.lstat()) == signature(s)
                            and len(b) == s.st_size)
        if not result['stable']:
            raise ValueError('file_changed_during_probe')
        return (result, b) if raw else result
    except Exception as exc:
        result['error'] = type(exc).__name__
        return (result, None) if raw else result
    finally:
        if fd is not None:
            os.close(fd)


def command(argv, timeout=12):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                           env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
        return {'argv': argv, 'actualExitCode': p.returncode, 'directReaped': True,
                'stdout': p.stdout, 'stderr': p.stderr}
    except Exception as exc:
        return {'argv': argv, 'error': type(exc).__name__}


def executable(path):
    """Stream exactly approved root-owned binaries under a separate finite cap."""
    result = {'path': str(path)}
    fd = None
    try:
        if path not in ('/usr/bin/python3.12', '/usr/bin/docker', '/usr/bin/dockerd'):
            raise ValueError('executable_path_refused')
        before = os.lstat(path)
        result['signature'] = signature(before)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or before.st_nlink != 1
                or before.st_mode & 0o022 or not 0 < before.st_size <= 200000000):
            raise ValueError('protected_executable_refused')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        if signature(os.fstat(fd)) != signature(before):
            raise ValueError('executable_named_fd_race')
        digest = hashlib.sha256(); count = 0
        while True:
            data = os.read(fd, 65536)
            if not data:
                break
            count += len(data)
            if count > 200000000:
                raise ValueError('executable_size_bound')
            digest.update(data)
        result['stable'] = (count == before.st_size and signature(os.fstat(fd)) ==
                            signature(os.lstat(path)) == signature(before))
        if not result['stable']:
            raise ValueError('executable_changed_during_probe')
        result['sha256'] = digest.hexdigest()
    except Exception as exc:
        result['error'] = type(exc).__name__
    finally:
        if fd is not None:
            os.close(fd)
    return result


def proc(pid):
    result = {'pid': pid}
    try:
        p = Path('/proc') / str(pid)
        text = (p / 'stat').read_text()
        rest = text[text.rfind(')') + 2:].split()
        result.update(state=rest[0], ppid=int(rest[1]), pgid=int(rest[2]),
                      sid=int(rest[3]), startTicks=int(rest[19]),
                      exe=os.readlink(p / 'exe'),
                      cgroup=(p / 'cgroup').read_text().splitlines())
        status = (p / 'status').read_text().splitlines()
        result['uidTuple'] = [int(x) for x in next(l for l in status if l.startswith('Uid:')).split()[1:]]
        # Do not read command lines; exact executable/birth/cgroup identifies this owner.
        result['kernelIdentity'] = kernel_identity(pid)
        if result['exe'] in ('/usr/bin/python3.12', '/usr/bin/python3', '/usr/bin/docker'):
            result['exeSHA256'] = executable(result['exe']).get('sha256')
        after = (p / 'stat').read_text()
        ar = after[after.rfind(')') + 2:].split()
        result['birthStable'] = (int(ar[19]) == result['startTicks']
                                  and int(ar[2]) == result['pgid'])
        result['present'] = True
    except FileNotFoundError:
        result['present'] = False
    except Exception as exc:
        result['error'] = type(exc).__name__
    return result


def kernel_identity(pid):
    """Same strict current running-process shape as the canonical recorder.

    The executable identity uses the underlying held kernel reference, rather
    than the /proc symlink inode. No command line or environment is read.
    """
    def birth():
        text = (Path('/proc') / str(pid) / 'stat').read_text()
        fields = text.rsplit(')', 1)[1].split()
        if int(text.split(' ', 1)[0]) != pid or len(fields) < 20:
            raise ValueError('invalid_stat_observation')
        return {'pid': pid, 'ppid': int(fields[1]), 'pgid': int(fields[2]),
                'sid': int(fields[3]), 'startTicks': fields[19]}, fields[0]
    def uids():
        values = [line.split()[1:] for line in (p / 'status').read_text().splitlines()
                  if line.startswith('Uid:')]
        if len(values) != 1 or len(values[0]) != 4 or len(set(values[0])) != 1:
            raise ValueError('strict_four_UID_refusal')
        return values[0]
    p = Path('/proc') / str(pid)
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    a, state = birth()
    if state == 'Z':
        raise ValueError('current_peer_zombie_refusal')
    before_uid = uids()
    cg = (p / 'cgroup').read_text().strip()
    if not cg.startswith('0::/') or '\n' in cg:
        raise ValueError('strict_single_cgroup_refusal')
    s = (p / 'exe').stat()
    executable = {'path': os.readlink(p / 'exe'), 'device': s.st_dev, 'inode': s.st_ino}
    after_uid = uids()
    b, after_state = birth()
    if (a['pid'] != b['pid'] or a['startTicks'] != b['startTicks']
            or before_uid != after_uid or (p / 'cgroup').read_text().strip() != cg
            or Path('/proc/sys/kernel/random/boot_id').read_text().strip() != boot
            or after_state == 'Z'):
        raise ValueError('strict_current_identity_race')
    s = (p / 'exe').stat()
    if (os.readlink(p / 'exe') != executable['path'] or
            (s.st_dev, s.st_ino) != (executable['device'], executable['inode'])):
        raise ValueError('strict_executable_race')
    result = dict(b, bootId=boot, uid=int(before_uid[0]),
                  uidTuple=[int(x) for x in before_uid], cgroupPath=cg[3:], executable=executable)
    if a != b:
        result['basicObservations'] = [dict(a, bootId=boot), dict(b, bootId=boot)]
    return result


def cgroup(path):
    result = {'path': path}
    if not path.startswith('/') or '..' in Path(path).parts:
        return {'error': 'cgroup_path_refused'}
    root = Path('/sys/fs/cgroup' + path)
    try:
        result['directory'] = file(root)
        result['exists'] = root.exists()
        if result['exists']:
            result['values'] = {}
            for name in CGROUP_FIELDS:
                try:
                    result['values'][name] = (root / name).read_text().strip()
                except Exception as exc:
                    result['values'][name] = {'error': type(exc).__name__}
    except Exception as exc:
        result['error'] = type(exc).__name__
    return result


def inspect_container(name):
    fmt = ('{"id":{{json .Id}},"name":{{json .Name}},"image":{{json .Image}},'
           '"configImage":{{json .Config.Image}},'
           '"classificationMounts":{{json .Mounts}},'
           '"state":{"Status":{{json .State.Status}},"Running":{{json .State.Running}},'
           '"Pid":{{json .State.Pid}},"ExitCode":{{json .State.ExitCode}},'
           '"OOMKilled":{{json .State.OOMKilled}},"StartedAt":{{json .State.StartedAt}},'
           '"FinishedAt":{{json .State.FinishedAt}}},"memoryMax":{{json .HostConfig.Memory}},'
           '"memorySwapMax":{{json .HostConfig.MemorySwap}},'
           '"deviceRequests":{{json .HostConfig.DeviceRequests}}}')
    read = command(['/usr/bin/docker', 'container', 'inspect', name, '--format', fmt])
    result = {'selector': name, 'read': read}
    if read.get('actualExitCode') != 0:
        return result
    try:
        value = json.loads(read.pop('stdout'))
        mounts = value.pop('classificationMounts', [])
        model_sources = [v.get('Source', '') for v in mounts
                         if type(v) is dict and v.get('Source', '').startswith('/data/models-large/')]
        value['workloadClassification'] = ('VisionOCR' if any('paddleocr-vl-1.6-' in s.lower() for s in model_sources)
            else 'VisionQwen' if any('qwen3.5-9b-' in s.lower() for s in model_sources) else 'unclassified')
        result['identity'] = value
        pid = value['state']['Pid']
        if type(pid) is int and pid > 0:
            result['process'] = proc(pid)
            for line in result['process'].get('cgroup', []):
                if line.startswith('0::'):
                    result['cgroup'] = cgroup(line[3:])
        else:
            result['cgroup'] = cgroup('/system.slice/docker-' + value['id'] + '.scope')
    except Exception as exc:
        result['error'] = type(exc).__name__
    return result


def safe_selection(name, b):
    try:
        value = json.loads(b)
        keys = {'owner', 'schema_version', 'boot', 'status', 'phase', 'gpu_uuid',
                'image_id', 'run_id', 'pid', 'warm', 'source_commit', 'network_id',
                'checkpoint_revision', 'checkpoint_path', 'checkpoint_receipt_sha256',
                'runtime_image_digest', 'runtime_revision', 'model_id', 'model_revision'}
        result = {'keys': sorted(value), 'selected': {k: v for k, v in value.items()
                  if k in keys and isinstance(v, (str, int, bool, type(None)))}}
        if name == 'config':
            result['sourceMaps'] = {k: value[k] for k in ('source_sha256', 'release_source_sha256')}
        if name == 'api':
            # Keep profiles/private prompt content byte-protected, but make invariance reviewable.
            result['profilesCanonicalSHA256'] = sha(json.dumps(value.get('profiles'), sort_keys=True,
                                                                separators=(',', ':')).encode())
        if name in ('state', 'operation', 'recovery'):
            allowed = ('id', 'image_id', 'pid', 'Pid', 'start_ticks', 'StartedAt', 'running',
                       'status', 'exitCode', 'boot', 'pgid', 'cgroup', 'exe', 'startTicks')
            result['selectedNestedOwner'] = {k: {a: x for a, x in v.items() if a in allowed}
                for k, v in value.items() if k in ('container', 'native_generation', 'process')
                and type(v) is dict}
        return result
    except Exception as exc:
        return {'parseError': type(exc).__name__}


def source_graph(config_raw):
    result = {'runtime': {}, 'release': {}, 'api': {}}
    try:
        config = json.loads(config_raw)
        for field, root, bucket in (('source_sha256', BASE / 'source', 'runtime'),
                                     ('release_source_sha256', RELEASE, 'release')):
            for name, expected in config[field].items():
                if type(name) is not str or Path(name).is_absolute() or '..' in Path(name).parts:
                    raise ValueError('source_path_refused')
                result[bucket][name] = file(root / name)
                result[bucket][name]['expectedSHA256'] = expected
                result[bucket][name]['matchesExpected'] = result[bucket][name].get('sha256') == expected
        for name in ('__init__.py', 'app.py', 'backend.py', 'protection.py',
                     'protocol.py', 'serve.py', 'uploads.py'):
            path = API / 'scripts/image_api' / name
            result['api'][str(path)] = file(path)
        result['unitsAndHelper'] = {p: file(p) for p in (
            '/usr/local/libexec/llm-image-backend-recover',
            '/etc/systemd/system/llm-image-api.service',
            '/etc/systemd/system/llm-image-backend.service')}
    except Exception as exc:
        result['error'] = type(exc).__name__
    return result


def main():
    boot = lambda: Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    r = {'schema': 'h046-image-fresh-read-v1', 'bootBefore': boot(), 'uid': os.getuid(),
         'startedUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'lifecycleInvoked': False, 'inferenceInvoked': False, 'nativeQualification': 'NOT_TESTED'}
    r['sixCurrentFiles'] = {}
    raw = {}
    for name, path in PATHS.items():
        metadata, b = file(path, raw=True)
        r['sixCurrentFiles'][name] = metadata
        if b is not None:
            raw[name] = b
            metadata.update(safe_selection(name, b))
    r['archive'] = {'directory': file(ARCHIVE), 'files': {}}
    try:
        r['archive']['entries'] = sorted(os.listdir(ARCHIVE))
    except Exception as exc:
        r['archive']['error'] = type(exc).__name__
    for name in (*[n + '.original.json' for n in PATHS], 'manifest.json'):
        metadata, b = file(ARCHIVE / name, raw=True)
        r['archive']['files'][name] = metadata
        if name == 'manifest.json' and b is not None:
            # Fixed manifest consists only of original hashes; never publish arbitrary added fields.
            try:
                j = json.loads(b)
                if set(j) == {'fileSha256'}:
                    r['archive']['manifest'] = j
                elif (set(j) == {'schema', 'files'} and j['schema'] == 'h044-six-raw-archive-v1'
                      and type(j['files']) is dict
                      and all(type(v) is str and re.fullmatch('[0-9a-f]{64}', v)
                              for v in j['files'].values())):
                    r['archive']['manifest'] = j
                elif all(type(v) is str and re.fullmatch('[0-9a-f]{64}', v) for v in j.values()):
                    r['archive']['manifest'] = j
                else:
                    r['archive']['manifestKeys'] = sorted(j)
            except Exception as exc:
                r['archive']['manifestParseError'] = type(exc).__name__
    r['sourceGraph'] = source_graph(raw.get('config', b'{}'))
    r['peerFiles'] = {p: file(p) for p in PEER_FILES}
    r['peerSourceMaps'] = {}
    for peer, path, field in (
            ('MiMo', '/data/services/mimo-h016-20260927/manifest.json', 'source_sha256'),
            ('Vision', '/data/logs/h044-vision-v03/RUNTIME-GRAPH.json', 'sourceManifest')):
        metadata, b = file(path, raw=True)
        try:
            value = json.loads(b)[field]
            if (type(value) is not dict or len(value) > 256 or
                    any(type(k) is not str or len(k) > 512 or type(v) is not str
                        or not re.fullmatch('[0-9a-f]{64}', v) for k, v in value.items())):
                raise ValueError('peer_source_map_refused')
            r['peerSourceMaps'][peer] = {'path': path, 'file': metadata, 'field': field, 'map': value}
        except Exception as exc:
            r['peerSourceMaps'][peer] = {'path': path, 'file': metadata, 'error': type(exc).__name__}
    latch_path = '/data/services/llm-manager/hardware-latch.json'
    metadata, b = file(latch_path, raw=True)
    r['externalHardwareLatch'] = {'file': metadata, 'selectedTarget': EXTERNAL,
                                 'canonicalValidation': 'REQUIRED_BY_CURRENT_ROOT_HELPER'}
    try:
        value = json.loads(b)
        targets = value['targets']
        if type(targets) is not dict:
            raise ValueError('hardware_latch_targets_invalid')
        target = targets.get(EXTERNAL)
        r['externalHardwareLatch'].update(schemaVersion=value.get('schema_version'),
                                         targetEntryPresent=EXTERNAL in targets)
        if target is not None:
            if type(target) is not dict:
                raise ValueError('hardware_latch_target_invalid')
            r['externalHardwareLatch']['selectedStatus'] = {
                key: target.get(key) for key in ('boot_id', 'hardware_latched', 'reason', 'hardware_fault_code')}
            r['externalHardwareLatch']['pendingEntryPresent'] = 'pending' in target
    except Exception as exc:
        r['externalHardwareLatch']['error'] = type(exc).__name__
    r['executables'] = {p: executable(p) for p in ('/usr/bin/python3.12', '/usr/bin/docker', '/usr/bin/dockerd')}
    r['executables']['/usr/bin/python3'] = file('/usr/bin/python3')
    try:
        r['executables']['/usr/bin/python3']['symlinkTarget'] = os.readlink('/usr/bin/python3')
        r['executables']['/usr/bin/python3']['resolvedTarget'] = os.path.realpath('/usr/bin/python3')
    except Exception as exc:
        r['executables']['/usr/bin/python3']['symlinkError'] = type(exc).__name__
    r['dockerDaemon'] = command(['/usr/bin/docker', 'info', '--format',
                                 '{"id":{{json .ID}},"cgroupDriver":{{json .CgroupDriver}},"cgroupVersion":{{json .CgroupVersion}}}'])
    r['currentPeers'] = {name: inspect_container(selector) for name, selector in PEERS.items()}
    for old_key in ('visionA', 'visionB'):
        new_key = r['currentPeers'][old_key].get('identity', {}).get('workloadClassification')
        if new_key in ('VisionQwen', 'VisionOCR') and new_key not in r['currentPeers']:
            r['currentPeers'][new_key] = r['currentPeers'].pop(old_key)
    r['stoppedBackend'] = inspect_container('llm-image-backend')
    r['historicalBackend'] = inspect_container(HISTORICAL_CID)
    r['backendInventories'] = {name: command(['/usr/bin/docker', 'ps', '--all', '--no-trunc',
        '--filter', value, '--format', '{{.ID}} {{.Names}}']) for name, value in (
        ('named', 'name=^/llm-image-backend$'), ('historical', 'id=' + HISTORICAL_CID))}
    units = ('llm-image-api.service', 'llm-image-backend.service')
    r['imageUnits'] = {unit: command(['systemctl', 'show', unit,
        '--property=Id,LoadState,ActiveState,SubState,MainPID,ControlPID,ExecMainStatus,InvocationID,FragmentPath,ControlGroup,Job,NeedDaemonReload,ExecMainStartTimestampMonotonic,ExecMainExitTimestampMonotonic'])
        for unit in units}
    r['stoppedCgroups'] = {path: cgroup(path) for path in (
        '/system.slice/llm-image-api.service', '/system.slice/llm-image-backend.service',
        '/system.slice/docker-' + HISTORICAL_CID + '.scope')}
    r['historicalPidsCurrentObservationOnly'] = {str(pid): proc(pid) for pid in (11783, 13527, 10956, 9066)}
    r['imagePort'] = command(['ss', '-H', '-ltn', 'sport = :30007'])
    r['hostMeminfo'] = {k: int(v.strip().split()[0]) * 1024 for k, v in
        (line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
        if k in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree')}
    r['hostMemoryPressure'] = Path('/proc/pressure/memory').read_text().strip()
    r['hostVMEvents'] = {k: int(v) for k, v in
        (line.split() for line in Path('/proc/vmstat').read_text().splitlines())
        if k in ('oom_kill', 'pgmajfault', 'pswpin', 'pswpout')}
    r['gpus'] = {u: command(['nvidia-smi', '--id=' + u,
        '--query-gpu=uuid,name,pci.bus_id,memory.total,memory.used,memory.free,temperature.gpu,utilization.gpu,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max',
        '--format=csv,noheader,nounits']) for u in (EXTERNAL, READING)}
    r['gpuCompute'] = command(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid,process_name,used_memory',
                               '--format=csv,noheader,nounits'])
    r['gpuFaultObservation'] = command(['journalctl', '-k', '-b', '--no-pager',
        '--grep=NVRM|Xid|AER:|aer:|[Tt]hunderbolt|[Uu][Ss][Bb]4|pcieport', '-n', '250'])
    r['oci'] = {digest: file('/data/containerd/root/io.containerd.content.v1.content/blobs/sha256/' + digest)
        for digest in ('50a3bfd20fc931f05fc5fc919b0445abbce30d5c7716424d697a7ab6708c08ef',
                       '3f6178faa74c4a9bcb95ed4304dbee57473efa8913a793e067014af4a98281ad')}
    r['bootAfter'] = boot()
    r['archive']['directoryAfter'] = file(ARCHIVE)
    r['archive']['directoryStable'] = (r['archive']['directory'].get('signature') ==
                                       r['archive']['directoryAfter'].get('signature'))
    r['finishedUtc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    print(json.dumps(r, sort_keys=True))


if __name__ == '__main__':
    main()
