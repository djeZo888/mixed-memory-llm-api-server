#!/usr/bin/env python3
"""Exact-path, metadata-only key discovery. No SSH, recursive scan or key read.

The native evidence key is NOT an ordinary approval key. Native launch receipts
are producer-owned file-channel receipts; checkpoint retention separately uses
<data-dir>/harness.sqlite.h041-native-evidence.key. Only paths explicitly carried
by the current service unit/current process are recognized ordinary key paths.
This inventory does not assert absence outside that finite recognized scope.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import time

SOURCE_PATHS = ('deploy/run-server.sh', 'deploy/run-codex.sh',
                'deploy/engine/codex_receipts.py', 'server/src/main.ts',
                'server/src/app.ts', 'server/src/session-checkpoint.ts',
                'server/src/codex-ordinary-entry.ts', 'server/src/codex-receipts.ts')
SELECTED_ENV = ('AI_HARNESS_DATA_DIR', 'AI_HARNESS_ENGINE_LAUNCHER',
                'AI_HARNESS_CODEX_ORDINARY_ENTRY_FILE',
                'AI_HARNESS_CODEX_ORDINARY_ENTRY_KEY_FILE',
                'AI_HARNESS_NODE_CONTROL_KEY_FILE')
SELECTED_OPTIONS = ('--data-dir', '--app-dir', '--engine-launcher',
                    '--codex-ordinary-entry', '--codex-ordinary-entry-key',
                    '--inference-key-file', '--frontier-key-file',
                    '--browser-approval-key-file', '--node-control-key-file')


class InventoryError(RuntimeError):
    pass


def need(condition, reason):
    if not condition:
        raise InventoryError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def absolute(value):
    need(isinstance(value, str) and value.startswith('/') and
         all(ord(c) >= 32 for c in value), 'noncanonical absolute path')
    p = Path(value)
    need(str(p) == value and '..' not in p.parts and p.resolve() == p,
         'path alias/symlink denied')
    return p


def identity(path):
    st = Path(path).lstat()
    return {'dev': st.st_dev, 'ino': st.st_ino, 'uid': st.st_uid,
            'gid': st.st_gid, 'mode': stat.S_IMODE(st.st_mode), 'nlink': st.st_nlink,
            'size': st.st_size, 'mtimeNs': st.st_mtime_ns, 'ctimeNs': st.st_ctime_ns}


def ancestry(path, owners):
    for p in (Path(path), *Path(path).parents):
        st = p.lstat()
        need(stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode) and
             st.st_uid in owners and not st.st_mode & 0o022, 'unprotected ancestry')


def bounded_read(path, cap=524288):
    p = absolute(str(path)); before = identity(p)
    need(stat.S_ISREG(p.lstat().st_mode) and before['nlink'] == 1 and
         0 < before['size'] <= cap, 'unsafe or oversized observation file')
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(fd)
        need((opened.st_dev, opened.st_ino) == (before['dev'], before['ino']),
             'observation inode changed')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(cap + 1)
        need(len(raw) == before['size'] and identity(p) == before, 'observation changed')
        return raw
    finally:
        os.close(fd)


def file_metadata(path, expected_uid):
    p = absolute(str(path))
    try:
        st = p.lstat()
    except FileNotFoundError:
        return {'path': str(p), 'state': 'ABSENT'}
    value = identity(p)
    safe = stat.S_ISREG(st.st_mode) and value['uid'] == expected_uid and \
        value['nlink'] == 1 and value['mode'] == 0o600 and value['size'] == 32
    try:
        ancestry(p.parent, (0, expected_uid))
    except (InventoryError, OSError):
        safe = False
    return {'path': str(p), 'state': 'PRESENT', 'identity': value,
            'protected32B': safe, 'keyBytesRead': False}


def observe_process(pid, proc_root=Path('/proc')):
    need(type(pid) is int and pid > 0, 'invalid owner PID')
    p = proc_root / str(pid)
    first = (p / 'stat').read_bytes()
    fields = first.decode().rsplit(')', 1)[1].split()
    need(len(fields) > 19 and fields[0] not in ('Z', 'X'), 'owner is exited/zombie')
    status = (p / 'status').read_text()
    ids = [int(x) for x in status.split('Uid:', 1)[1].splitlines()[0].split()]
    gids = [int(x) for x in status.split('Gid:', 1)[1].splitlines()[0].split()]
    need(len(set(ids)) == len(set(gids)) == 1, 'changing owner IDs')
    raw_env = (p / 'environ').read_bytes()
    need(len(raw_env) <= 262144, 'owner environment exceeds private bound')
    selected = {}
    for item in raw_env.split(b'\0'):
        name, sep, value = item.partition(b'=')
        if sep and name.decode('ascii', errors='ignore') in SELECTED_ENV:
            key = name.decode('ascii')
            need(key not in selected, 'duplicate selected environment entry')
            selected[key] = value.decode('utf-8', errors='strict')
    cmdline = (p / 'cmdline').read_bytes()
    need(len(cmdline) <= 262144, 'owner command exceeds bound')
    result = {'pid': pid, 'startTicks': fields[19], 'uid': ids[0], 'gid': gids[0],
              'bootId': (proc_root / 'sys/kernel/random/boot_id').read_text().strip(),
              'pgid': int(fields[2]), 'cgroup': (p / 'cgroup').read_text().strip(),
              'exe': os.readlink(p / 'exe'),
              'cmdlineSha256': hashlib.sha256(cmdline).hexdigest(),
              'selectedEnvironment': selected}
    need((p / 'stat').read_bytes().decode().rsplit(')', 1)[1].split()[19] == fields[19],
         'owner birth changed during inventory')
    return result



REMOTE_OWNER_FIELDS = {'bootId', 'uid', 'pid', 'startTicks', 'pgid', 'cgroupPath',
                       'executable', 'cmdlineSha256', 'sourceFiles'}
REMOTE_POLICY_FIELDS = {'schema', 'purpose', 'localHost', 'remoteHost', 'kernelHost',
                        'sourceCommit', 'bindingId', 'collectorSha256', 'sshArgv',
                        'beforePath', 'afterPath', 'afterAnchor', 'clockDomain'}


def root_original(filename):
    """Root-frozen, nonsecret observation; never an SSH credential/key reader."""
    p = absolute(filename)
    ancestry(p.parent, (0,))
    before = identity(p)
    need(before['uid'] == 0 and before['mode'] in (0o600, 0o640, 0o644) and
         before['nlink'] == 1, 'remote original must be immutable to app UID1000')
    raw = bounded_read(p, 1048576)
    need(identity(p) == before, 'root remote original changed')
    return raw


def remote_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate remote original JSON key')
            result[key] = value
        return result
    return json.loads(raw.decode('utf-8', errors='strict'), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(InventoryError('nonfinite remote original')))


def utc(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    need(parsed.utcoffset() == dt.timedelta(0), 'remote original requires UTC')
    return parsed.timestamp()


def observe_remote_owners(expected, policy, stage='before', originals=None):
    """Consume finite root SSH ORIGINALS. Foreign PIDs never enter local /proc.

    Root collects/publishes one immutable original immediately before the
    carrier, and a different original after its owned shutdown. This helper
    does not start a collector, use SSH, create a key, or qualify native receipts.
    """
    need(isinstance(expected, dict) and set(expected) == {'qwen1', 'qwen2', 'mimo'},
         'exact three remote model owners required')
    need(isinstance(policy, dict) and set(policy) == REMOTE_POLICY_FIELDS and
         policy['schema'] == 'h046-root-remote-owner-policy-v1' and
         policy['purpose'] in ('native-carrier', 'ordinary-key-create') and
         policy['localHost'] == 'aiharness' and policy['remoteHost'] == 'ai-vm' and
         policy['clockDomain'] == 'ai-harness-realtime-utc' and
         os.uname().nodename == policy['localHost'] and
         isinstance(policy['kernelHost'], str) and policy['kernelHost'] != policy['localHost'] and
         len(policy['kernelHost']) <= 128 and
         len(policy['bindingId']) == 64 and all(c in '0123456789abcdef' for c in policy['bindingId']) and
         len(policy['sourceCommit']) == 40 and all(c in '0123456789abcdef' for c in policy['sourceCommit']) and
         len(policy['collectorSha256']) == 64 and all(c in '0123456789abcdef' for c in policy['collectorSha256']),
         'exact local ai-harness / remote ai-vm source-bound policy required')
    need(stage in ('before', 'after') and policy['beforePath'] != policy['afterPath'],
         'distinct before/after remote originals required')
    for phase in ('before', 'after'):
        need(Path(policy[phase + 'Path']).name == policy['bindingId'] + '.' + phase + '.remote-original.json',
             'finite binding-specific remote original slot required')
    argv = policy['sshArgv']
    need(isinstance(argv, list) and 3 <= len(argv) <= 64 and argv[0].endswith('/ssh') and
         all(isinstance(x, str) and x and not any(ord(c) < 32 for c in x) for x in argv) and
         'BatchMode=yes' in argv and 'ForwardAgent=no' in argv and
         'ClearAllForwardings=yes' in argv, 'root original requires exact nonforwarding SSH argv')
    # A bounded read-only grace allows root's already-authorized finite collector
    # to publish the after original after the existing scope-terminal marker.
    deadline = time.monotonic() + (2 if stage == 'after' else 0)
    while True:
        try:
            raw = root_original(policy[stage + 'Path']); break
        except FileNotFoundError:
            if time.monotonic() >= deadline:
                raise InventoryError('fresh root remote original unavailable')
            time.sleep(0.05)
    packet = remote_json(raw)
    need(isinstance(packet, dict) and set(packet) == {'schema', 'stage', 'policySha256',
         'startedUtc', 'finishedUtc', 'argv', 'actualExitCode', 'stdin', 'stdout', 'stderr', 'anchor'} and
         packet['schema'] == 'h046-root-remote-owner-original-v1' and packet['stage'] == stage and
         packet['policySha256'] == hashlib.sha256(canonical(policy)).hexdigest() and
         packet['argv'] == argv and type(packet['actualExitCode']) is int and
         packet['actualExitCode'] == 0 and
         isinstance(packet['stdin'], str) and isinstance(packet['stdout'], str) and
         isinstance(packet['stderr'], str) and
         hashlib.sha256(packet['stdin'].encode()).hexdigest() == policy['collectorSha256'],
         'root SSH original/source/policy/actual integer exit mismatch')
    now = time.time(); started = utc(packet['startedUtc']); finished = utc(packet['finishedUtc'])
    need(started <= finished <= now and now - started <= (30 if stage == 'before' else 60),
         'remote original is stale/future or collection was not immediate')
    if stage == 'before':
        need(packet['anchor'] is None, 'before observation cannot claim shutdown')
    else:
        anchor = absolute(policy['afterAnchor'])
        if policy['purpose'] == 'native-carrier':
            need(anchor.name == 'channel-scope-terminal.json', 'exact original owned shutdown anchor required')
            anchor_raw = bounded_read(anchor, 65536)
            need(packet['anchor'] == {'path': str(anchor), 'sha256': hashlib.sha256(anchor_raw).hexdigest()},
                 'remote after original is not bound to owned shutdown original')
        else:
            need(packet['anchor'] == {'path': str(anchor), 'identity': identity(anchor)} and
                 file_metadata(anchor, 1000).get('protected32B') is True,
                 'remote after original is not bound to exact ordinary32B creation')
        need(anchor.stat().st_mtime <= started <= anchor.stat().st_mtime + 5,
             'remote after collection must start immediately after owned action closure')
    if originals is not None:
        captured = {'path': policy[stage + 'Path'], 'sha256': hashlib.sha256(raw).hexdigest(),
                    'rawUtf8': raw.decode('utf-8')}
        need(not originals or originals == captured, 'root original replaced during bounded snapshot')
        originals.update(captured)
    observed = remote_json(packet['stdout'].encode())
    need(isinstance(observed, dict) and set(observed) == {'host', 'kernelHost', 'owners'} and
         observed['host'] == 'ai-vm' and observed['kernelHost'] == policy['kernelHost'] and
         isinstance(observed['owners'], dict) and set(observed['owners']) == set(expected),
         'actual remote SSH host / kernel host / three owners mismatch')
    boots = set()
    for name, owner in expected.items():
        need(isinstance(owner, dict) and set(owner) == REMOTE_OWNER_FIELDS and
             type(owner['uid']) is int and owner['uid'] >= 0 and
             type(owner['pid']) is int and owner['pid'] > 0 and
             type(owner['pgid']) is int and owner['pgid'] > 0 and
             isinstance(owner['startTicks'], str) and owner['startTicks'].isdigit() and
             isinstance(owner['bootId'], str) and len(owner['bootId']) == 36 and
             isinstance(owner['cgroupPath'], str) and owner['cgroupPath'].startswith('/') and
             isinstance(owner['executable'], dict) and set(owner['executable']) == {'path', 'sha256', 'identity'} and
             isinstance(owner['sourceFiles'], dict) and 1 <= len(owner['sourceFiles']) <= 16 and
             len(owner['cmdlineSha256']) == 64 and all(c in '0123456789abcdef' for c in owner['cmdlineSha256']),
             'complete remote kernel/executable/source owner required')
        for source in [owner['executable'], *owner['sourceFiles'].values()]:
            need(set(source) == {'path', 'sha256', 'identity'} and
                 isinstance(source['path'], str) and source['path'].startswith('/') and
                 len(source['sha256']) == 64 and all(c in '0123456789abcdef' for c in source['sha256']) and
                 isinstance(source['identity'], dict) and
                 set(source['identity']) == {'dev', 'ino', 'uid', 'gid', 'mode', 'nlink', 'size', 'mtimeNs', 'ctimeNs'} and
                 all(type(v) is int for v in source['identity'].values()) and
                 source['identity'].get('uid') in (0, owner['uid']) and
                 type(source['identity'].get('mode')) is int and not source['identity']['mode'] & 0o022 and
                 source['identity'].get('nlink') == 1,
                 'remote executable/source identity must be exact protected original')
        need(observed['owners'][name] == owner, 'actual remote boot/birth/group/cgroup/executable/source changed')
        boots.add(owner['bootId'])
    need(len(boots) == 1 and len({v['pid'] for v in expected.values()}) == 3,
         'three distinct owners must share ai-vm boot domain')
    # Stable identity only: temporal original hashes stay in root's original
    # files, reviewed before signing; they must not break frozen before/after joins.
    return {name: dict(host='ai-vm', kernelHost=policy['kernelHost'], **owner)
            for name, owner in observed['owners'].items()}

def unit_options(raw):
    text = raw.decode('utf-8', errors='strict')
    need('\x00' not in text, 'invalid unit')
    lines = [x.removeprefix('ExecStart=') for x in text.splitlines() if x.startswith('ExecStart=')]
    need(len(lines) == 1 and '\\' not in lines[0] and '\n' not in lines[0],
         'unsupported unit ExecStart syntax; exact source review required')
    argv = shlex.split(lines[0], posix=True)
    need(argv and argv[0].endswith('/deploy/run-server.sh'), 'unknown current server launcher')
    options = {}
    for index, token in enumerate(argv):
        if token in SELECTED_OPTIONS:
            need(token not in options and index + 1 < len(argv), 'ambiguous unit option')
            value = argv[index + 1]
            # Current unit uses systemd LoadCredential; resolve only from the
            # selected current owner path, never from guessed credential roots.
            options[token] = value if token == '--node-control-key-file' and value == '%d/node-control-key' else str(absolute(value))
    need('--data-dir' in options and '--app-dir' in options, 'unit current path metadata missing')
    return options


def inventory(unit_path, owner_pid, source_root, proc_root=Path('/proc')):
    root = absolute(str(source_root)); sources = {}
    for relative in SOURCE_PATHS:
        raw = bounded_read(root / relative)
        sources[relative] = hashlib.sha256(raw).hexdigest()
        if relative == 'server/src/app.ts':
            need(b'path.join(temporary.root, "harness.sqlite")' in raw,
                 'unsupported current Store database derivation')
        if relative == 'server/src/session-checkpoint.ts':
            need(b'store.databasePath+".h041-native-evidence.key"' in raw,
                 'unsupported current native evidence key derivation')
    unit = absolute(str(unit_path)); unit_raw = bounded_read(unit, 131072)
    options = unit_options(unit_raw); owner = observe_process(owner_pid, proc_root)
    env = owner['selectedEnvironment']; data = options['--data-dir']
    if options.get('--node-control-key-file') == '%d/node-control-key':
        need(bool(env.get('AI_HARNESS_NODE_CONTROL_KEY_FILE')), 'current systemd credential path unavailable')
        options['--node-control-key-file'] = str(absolute(env['AI_HARNESS_NODE_CONTROL_KEY_FILE']))
    need(env.get('AI_HARNESS_DATA_DIR') == data, 'unit/current owner DATA_DIR mismatch')
    need(options['--app-dir'] == str(root), 'unit/current inspected source root mismatch')
    for option, variable in (('--engine-launcher', 'AI_HARNESS_ENGINE_LAUNCHER'),
                             ('--codex-ordinary-entry', 'AI_HARNESS_CODEX_ORDINARY_ENTRY_FILE'),
                             ('--codex-ordinary-entry-key', 'AI_HARNESS_CODEX_ORDINARY_ENTRY_KEY_FILE')):
        if option in options:
            need(env.get(variable) == options[option], 'unit/current owner selected path mismatch')
        elif env.get(variable):
            need(option == '--engine-launcher', 'unrecognized ambient ordinary path denied')
    native = str(absolute(data) / 'harness.sqlite.h041-native-evidence.key')
    ordinary = sorted({p for p in (options.get('--codex-ordinary-entry-key'),
                                   env.get('AI_HARNESS_CODEX_ORDINARY_ENTRY_KEY_FILE')) if p})
    need(native not in ordinary, 'native evidence key cannot be ordinary approval key')
    observed = [file_metadata(p, owner['uid']) for p in ordinary]
    return {'schema': 'h046-exact-key-inventory-v1', 'mode': 'READ_ONLY_METADATA',
            'scope': 'CURRENT_UNIT_AND_SELECTED_OWNER_PATHS_ONLY', 'owner': owner,
            'unit': {'path': str(unit), 'sha256': hashlib.sha256(unit_raw).hexdigest(),
                     'identity': identity(unit)}, 'sourceRoot': str(root),
            'sourceFiles': sources, 'sourceGraphSha256': hashlib.sha256(canonical(sources)).hexdigest(),
            'dataDir': data, 'databasePath': data + '/harness.sqlite',
            'nativeEvidenceKey': file_metadata(native, owner['uid']),
            'ordinaryApprovalKeys': observed,
            'ordinaryKeyStatus': 'ADOPT_EXISTING' if any(x['state'] == 'PRESENT' for x in observed)
              else 'NO_CONFIGURED_KEY' if not observed else 'RECOGNIZED_PATHS_ABSENT',
            'protectedCredentialPaths': sorted({options[x] for x in SELECTED_OPTIONS
              if x.endswith('-key-file') and x in options}),
            'globalAbsenceProven': False, 'keyBytesRead': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unit', required=True)
    parser.add_argument('--owner-pid', type=int, required=True)
    parser.add_argument('--source-root', required=True)
    args = parser.parse_args()
    print(json.dumps(inventory(args.unit, args.owner_pid, args.source_root), sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status': 'DENIED', 'reason': str(error), 'keyBytesRead': False}))
        raise SystemExit(1)
