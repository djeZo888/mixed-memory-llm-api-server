#!/usr/bin/env python3
"""Exact-path, metadata-only key discovery. No SSH, recursive scan or key read.

The native evidence key is NOT an ordinary approval key. Native launch receipts
are producer-owned file-channel receipts; checkpoint retention separately uses
<data-dir>/harness.sqlite.h041-native-evidence.key. Only paths explicitly carried
by the current service unit/current process are recognized ordinary key paths.
This inventory does not assert absence outside that finite recognized scope.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat

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
