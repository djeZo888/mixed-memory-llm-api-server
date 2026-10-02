#!/usr/bin/env python3
"""Bounded, read-only H046 host/legacy-ledger originals. Never an admission API.

INPUT.metadata (or INPUT itself): application {unit,unitFile,unitSha256,owner},
generalOwners {qwen1:owner,qwen2:owner,mimo:owner}, database
{path,identity,retainedSessionIds,retainedUncertainOwners?}, protectedFiles
[{path,identity}]. Historical uncertain owners default to []; a root-signed
exact list may retain only [session_id,'uncertain',active_turn_id,'interrupted'].
These database rows do not establish absence of live native processes or the
gateway's private RAM owner UUID; independently observed birth proof is required.
Owner is
exact bootId/uid/pid/startTicks/pgid/cgroupPath. File identity is exact
dev/ino/uid/gid/mode/nlink (integer permission bits). Secrets are never read.
"""
import argparse
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import sqlite3
import stat
import subprocess
import time

from key_inventory import InventoryError, observe_remote_owners

MAX_ROWS = 200000
MAX_BYTES = 64 * 1024 * 1024
FILE_FIELDS = ('dev', 'ino', 'uid', 'gid', 'mode', 'nlink')
ANCESTOR_FIELDS = (*FILE_FIELDS, 'size', 'mtimeNs', 'ctimeNs')
OWNER_FIELDS = ('bootId', 'uid', 'pid', 'startTicks', 'pgid', 'cgroupPath')


class Refused(Exception):
    pass


def need(value, message):
    if not value:
        raise Refused(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            need(key not in value, 'duplicate JSON key')
            value[key] = item
        return value
    return json.loads(raw.decode('utf-8', errors='strict'), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(Refused('nonfinite JSON')))


def path(value):
    need(isinstance(value, str) and value.startswith('/') and '\x00' not in value,
         'absolute path required')
    result = Path(value)
    need(str(result) == value and result.resolve() == result, 'canonical path required')
    return result


def ancestor_identity(info):
    return dict(zip(ANCESTOR_FIELDS, (info.st_dev, info.st_ino, info.st_uid,
                info.st_gid, stat.S_IMODE(info.st_mode), info.st_nlink,
                info.st_size, info.st_mtime_ns, info.st_ctime_ns)))


def observe_private_group_ancestor(value, info, approval):
    """Observe only; control binds this INPUT member to root HMAC before launch.

    INPUT.privateGroupAncestor is {path, identity}; identity has all nine
    ANCESTOR_FIELDS. Caller-supplied account/group claims are never evidence.
    """
    need(isinstance(approval, dict) and set(approval) == {'path', 'identity'} and
         approval['path'] == str(value) == '/home/user/.local' and
         os.getuid() == os.geteuid() == 1000, 'exact private-group ancestor required')
    expected = approval['identity']
    need(isinstance(expected, dict) and set(expected) == set(ANCESTOR_FIELDS) and
         all(type(v) is int for v in expected.values()) and
         expected['uid'] == expected['gid'] == 1000 and expected['mode'] == 0o775,
         'exact private-group descriptor required')
    need(path(str(value)) == value and stat.S_ISDIR(info.st_mode) and
         ancestor_identity(info) == expected, 'private-group ancestor changed')
    fd = os.open(value, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(fd)
        need(stat.S_ISDIR(opened.st_mode) and ancestor_identity(opened) == expected,
             'private-group named FD changed')
        accounts = pwd.getpwall()
        members = [p for p in accounts if p.pw_gid == 1000 or p.pw_uid == 1000]
        def account(p):
            return (p.pw_name, p.pw_uid, p.pw_gid, p.pw_dir)
        ordinary = ('user', 1000, 1000, '/home/user')
        need([account(p) for p in members] == [ordinary] and
             account(pwd.getpwuid(1000)) == account(pwd.getpwnam('user')) == ordinary,
             'private-group primary membership changed')
        def group(g):
            return (g.gr_name, g.gr_gid, tuple(g.gr_mem))
        current = grp.getgrgid(1000)
        need(current.gr_name == 'user' and current.gr_gid == 1000 and
             list(current.gr_mem) in ([], ['user']) and
             group(grp.getgrnam('user')) == group(current) and
             [group(g) for g in grp.getgrall() if g.gr_gid == 1000 or
              g.gr_name == 'user'] == [group(current)],
             'private-group supplementary membership changed')
        need(path(str(value)) == value and ancestor_identity(os.fstat(fd)) == expected and
             ancestor_identity(value.lstat()) == expected,
             'private-group ancestor changed during observation')
        return {'path': str(value), 'identity': expected.copy(),
                'group': {'name': current.gr_name, 'gid': current.gr_gid,
                          'supplementaryMembers': list(current.gr_mem)},
                'primaryMembers': [{'name': 'user', 'uid': 1000, 'gid': 1000}]}
    except (KeyError, OSError) as error:
        raise Refused('private-group observation unavailable') from error
    finally:
        os.close(fd)


def check_ancestor(value, info, uid, private_group_ancestor=None):
    need(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode) and
         info.st_uid in (0, uid), 'unsafe path ancestry')
    if str(value) == '/home/user/.local' and private_group_ancestor is not None:
        need(uid == 1000, 'private-group owner mismatch')
        observe_private_group_ancestor(value, info, private_group_ancestor)
    else:
        need(not info.st_mode & 0o022, 'unsafe path ancestry')


def ancestry(value, private=False, private_group_ancestor=None):
    value = path(str(value))
    for current in (value, *value.parents):
        info = current.lstat()
        check_ancestor(current, info, os.getuid(), private_group_ancestor)
    if private:
        need(value.stat().st_uid == os.getuid() and value.stat().st_mode & 0o777 == 0o700,
             'private owned parent required')


def file_identity(value):
    info = value.lstat()
    need(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode) and
         info.st_nlink == 1, 'regular single-link original required')
    return dict(zip(FILE_FIELDS, (info.st_dev, info.st_ino, info.st_uid, info.st_gid,
                                  stat.S_IMODE(info.st_mode), info.st_nlink)))


def match_identity(value, expected, private=False, private_group_ancestor=None):
    need(isinstance(expected, dict) and set(expected) == set(FILE_FIELDS) and
         all(type(v) is int for v in expected.values()), 'exact file identity required')
    ancestry(value.parent, private, private_group_ancestor)
    actual = file_identity(value)
    need(actual == expected, 'original inode/ownership changed')
    return actual


def observe_protected(item, database_path, private_group_ancestor=None):
    need(isinstance(item, dict) and set(item) == {'path', 'identity'},
         'exact protected original specification required')
    value = path(item['path'])
    if item['identity'] is None:
        need(str(value) == str(path(database_path)) + '.h041-native-evidence.key',
             'absence allowed only for source-derived native evidence key')
        ancestry(value.parent, True, private_group_ancestor)
        try:
            value.lstat()
        except FileNotFoundError:
            return {'path': str(value), 'identity': None, 'state': 'ABSENT'}
        raise Refused('source-derived native evidence key no longer absent')
    actual = match_identity(value, item['identity'], True, private_group_ancestor)
    need(actual['uid'] == os.getuid() and actual['mode'] == 0o600,
         'protected original is not private')
    return {'path': str(value), 'identity': actual}


def private_read(value, maximum, private_group_ancestor=None):
    ancestry(value.parent, True, private_group_ancestor)
    fd = os.open(value, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and
             stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1 and
             1 <= info.st_size <= maximum, 'unsafe private input')
        raw = os.read(fd, maximum + 1)
        after = os.fstat(fd)
        need(len(raw) == info.st_size and (info.st_dev, info.st_ino, info.st_size,
             info.st_mtime_ns, info.st_ctime_ns) == (after.st_dev, after.st_ino,
             after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'changing private input')
        return raw
    finally:
        os.close(fd)


def observe_owner(expected):
    need(isinstance(expected, dict) and set(expected) == set(OWNER_FIELDS),
         'exact owner tuple required')
    need(type(expected['pid']) is int and expected['pid'] > 0 and
         type(expected['uid']) is int and expected['uid'] >= 0 and
         type(expected['pgid']) is int and expected['pgid'] > 0 and
         isinstance(expected['startTicks'], str) and expected['startTicks'].isdigit(),
         'invalid owner tuple')
    proc = Path('/proc') / str(expected['pid'])
    before = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
    ids = next(line.split()[1:] for line in (proc / 'status').read_text().splitlines()
               if line.startswith('Uid:'))
    need(ids == [str(expected['uid'])] * 4, 'actual owner UID mismatch')
    cgroup = (proc / 'cgroup').read_text().strip()
    need(cgroup.startswith('0::/') and '\n' not in cgroup, 'unqualified owner cgroup')
    after = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
    need(before[19] == after[19] and before[2] == after[2], 'owner birth changed')
    actual = {'bootId': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'uid': expected['uid'], 'pid': expected['pid'], 'startTicks': before[19],
              'pgid': int(before[2]), 'cgroupPath': cgroup[3:]}
    need(actual == expected, 'actual owner differs from root tuple')
    return actual


def observe_unit(spec, owner, private_group_ancestor=None):
    need(isinstance(spec.get('unit'), str) and
         re.fullmatch(r'[A-Za-z0-9_.@-]{1,200}\.service', spec['unit']), 'service unit required')
    need(owner['uid'] == os.getuid(), 'unit snapshot must run as application owner')
    source = path(spec['unitFile']); ancestry(source.parent, private_group_ancestor=private_group_ancestor)
    info = source.lstat()
    need(stat.S_ISREG(info.st_mode) and info.st_uid in (0, os.getuid()) and
         not info.st_mode & 0o022 and sha(source.read_bytes()) == spec['unitSha256'],
         'actual service source changed')
    properties = ('Id', 'LoadState', 'ActiveState', 'SubState', 'MainPID', 'FragmentPath',
                  'DropInPaths', 'ControlGroup', 'InvocationID')
    result = subprocess.run(['/usr/bin/systemctl', '--user', '--no-ask-password',
                             '--no-pager', 'show', spec['unit'], '--property=' + ','.join(properties)],
                            capture_output=True, timeout=3, check=False,
                            env={'PATH': '/usr/bin:/bin', 'HOME': str(Path.home()),
                                 'XDG_RUNTIME_DIR': '/run/user/' + str(os.getuid())})
    need(result.returncode == 0 and len(result.stdout) <= 16384, 'unit inspection failed')
    values = dict(line.split('=', 1) for line in result.stdout.decode('utf-8').splitlines()
                  if '=' in line)
    need(set(values) == set(properties) and values['Id'] == spec['unit'] and
         values['LoadState'] == 'loaded' and values['ActiveState'] == 'active' and
         values['SubState'] == 'running' and values['MainPID'] == str(owner['pid']) and
         values['FragmentPath'] == str(source) and values['DropInPaths'] == '' and
         values['ControlGroup'] == owner['cgroupPath'] and
         re.fullmatch('[0-9a-f]{32}', values['InvocationID']) is not None,
         'unit is not exact current application owner')
    return {'properties': values, 'source': {'path': str(source),
            'sha256': spec['unitSha256'], 'identity': file_identity(source)}, 'inspectionExit': 0}


def digest_cursor(cursor, budget):
    columns = [column[0] for column in cursor.description]
    digest = hashlib.sha256(); digest.update(canonical(columns)); digest.update(b'\n')
    count = 0
    for row in cursor:
        raw = canonical([{'sqliteBlobSHA256': sha(v), 'bytes': len(v)}
                         if isinstance(v, bytes) else v for v in row])
        budget[0] += 1; budget[1] += len(raw)
        need(budget[0] <= MAX_ROWS and budget[1] <= MAX_BYTES, 'complete ledger exceeds bound')
        digest.update(raw); digest.update(b'\n'); count += 1
    return {'columns': columns, 'rows': count, 'sha256': digest.hexdigest()}


def observe_database(spec, private_group_ancestor=None):
    database = path(spec['path']); identity = match_identity(database, spec['identity'], True, private_group_ancestor)
    need(identity['uid'] == os.getuid() and identity['mode'] == 0o600,
         'database must be service-private')
    ids = spec['retainedSessionIds']
    need(isinstance(ids, list) and 1 <= len(ids) <= 64 and len(set(ids)) == len(ids) and
         all(isinstance(s, str) and re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', s) for s in ids),
         'retained session identifiers required')
    connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=3)
    deadline = time.monotonic() + 8
    connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
    try:
        connection.execute('PRAGMA query_only=ON'); connection.execute('BEGIN')
        active = connection.execute("SELECT COUNT(*) FROM runs WHERE status IN ('queued','running','cancelling')").fetchone()[0]
        owners = [list(row) for row in connection.execute("SELECT e.session_id,e.ownership,e.active_turn_id,s.status FROM h021_session_engines e LEFT JOIN sessions s ON s.id=e.session_id WHERE e.active_turn_id IS NOT NULL OR e.ownership!='idle' ORDER BY e.session_id")]
        retained_owners = spec.get('retainedUncertainOwners', [])
        need(isinstance(retained_owners, list) and len(retained_owners) <= 64 and
             all(isinstance(row, list) and len(row) == 4 and row[1] == 'uncertain' and
                 row[3] == 'interrupted' and isinstance(row[0], str) and
                 re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', row[0]) and
                 isinstance(row[2], str) and re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', row[2])
                 for row in retained_owners) and
             len({row[0] for row in retained_owners}) == len(retained_owners) and
             retained_owners == sorted(retained_owners, key=lambda row: row[0]),
             'only exact root-listed interrupted uncertain originals may be retained')
        need(active == 0 and owners == retained_owners,
             'active runs or unapproved/current nonidle native engines present')
        preserved_ids = sorted(set(ids + [row[0] for row in retained_owners]))
        request_ids = [row[0] for row in connection.execute('SELECT id FROM h021_gateway_requests ORDER BY id')]
        need(len(request_ids) <= MAX_ROWS and len(set(request_ids)) == len(request_ids) and
             all(isinstance(v, str) and 1 <= len(v) <= 512 for v in request_ids),
             'incomplete/invalid retained request identifiers')
        counts = {'requestsByState': dict(connection.execute('SELECT state,COUNT(*) FROM h021_gateway_requests GROUP BY state ORDER BY state')),
                  'runsByStatus': dict(connection.execute('SELECT status,COUNT(*) FROM runs GROUP BY status ORDER BY status')),
                  'activeRuns': active, 'nonidleEngines': len(owners),
                  'retainedUncertainOwners': owners}
        sequence = {'global': connection.execute('SELECT COALESCE(MAX(sequence),0) FROM h041_gateway_admissions').fetchone()[0],
                    'sessions': {sid: connection.execute('SELECT COALESCE(MAX(sequence),0) FROM h041_gateway_admissions WHERE session_id=?', (sid,)).fetchone()[0] for sid in preserved_ids}}
        budget = [0, 0]
        retained = {'gatewayRequests': digest_cursor(connection.execute('SELECT * FROM h021_gateway_requests ORDER BY rowid'), budget),
                    'gatewayAdmissions': digest_cursor(connection.execute('SELECT * FROM h041_gateway_admissions ORDER BY sequence'), budget),
                    'nonidleNativeEngineOriginals': digest_cursor(connection.execute("SELECT e.*,s.* FROM h021_session_engines e LEFT JOIN sessions s ON s.id=e.session_id WHERE e.active_turn_id IS NOT NULL OR e.ownership!='idle' ORDER BY e.session_id"), budget),
                    'sessions': {}}
        direct = [('sessions', 'id'), ('messages', 'session_id'), ('runs', 'session_id'),
                  ('events', 'session_id'), ('files', 'session_id'), ('handoffs', 'session_id'),
                  ('h021_session_engines', 'session_id'), ('h041_workspace_recovery_reservations', 'session_id'),
                  ('h002_activities', 'session_id'), ('h029_message_submissions', 'session_id'),
                  ('h024_compaction_actions', 'session_id'), ('h036_image_status_refs', 'session_id'),
                  ('h003_image_jobs', 'session_id')]
        related = {'h004_file_sources': ('file_id', 'files'), 'h003_image_file_meta': ('file_id', 'files'),
                   'h002_file_refs': ('file_id', 'files'), 'h002_file_names': ('file_id', 'files'),
                   'h002_message_meta': ('message_id', 'messages'), 'h035_image_results': ('message_id', 'messages'),
                   'h003_run_image_refs': ('run_id', 'runs'), 'h002_subagents': ('run_id', 'runs'),
                   'h030_handoff_targets': ('run_id', 'runs')}
        for sid in preserved_ids:
            tables = {}
            for table, column in direct:
                tables[table] = digest_cursor(connection.execute('SELECT * FROM ' + table + ' WHERE ' + column + '=? ORDER BY rowid', (sid,)), budget)
            need(tables['sessions']['rows'] == 1, 'retained original session missing')
            for table, (column, parent) in related.items():
                tables[table] = digest_cursor(connection.execute('SELECT * FROM ' + table + ' WHERE ' + column + ' IN (SELECT id FROM ' + parent + ' WHERE session_id=?) ORDER BY rowid', (sid,)), budget)
            tables['h003_image_outputs'] = digest_cursor(connection.execute('SELECT * FROM h003_image_outputs WHERE workspace_id IN (SELECT workspace_id FROM sessions WHERE id=?) ORDER BY rowid', (sid,)), budget)
            # Recovery-only tables are created lazily by the existing Store.
            releases = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('h036_physical_releases','h036_released_requests') ORDER BY name").fetchall()
            need(len(releases) in (0, 2), 'incomplete original release schema')
            if releases:
                tables['h036_physical_releases'] = digest_cursor(connection.execute('SELECT * FROM h036_physical_releases WHERE session_id=? ORDER BY rowid', (sid,)), budget)
                tables['h036_released_requests'] = digest_cursor(connection.execute('SELECT * FROM h036_released_requests WHERE recovery_id IN (SELECT recovery_id FROM h036_physical_releases WHERE session_id=?) ORDER BY rowid', (sid,)), budget)
            retained['sessions'][sid] = tables
        need(file_identity(database) == identity, 'database inode changed during read')
        return identity, sequence, request_ids, retained, counts
    finally:
        connection.close()


def snapshot(input_value, stage='before', originals=None):
    private_group_ancestor = input_value.get('privateGroupAncestor')
    spec = input_value.get('metadata', input_value)
    need(isinstance(spec, dict) and set(spec) == {'application', 'generalOwners', 'remoteOwnerObservation', 'database', 'protectedFiles'}, 'exact metadata specification required')
    need(os.getuid() == os.geteuid() == 1000 and spec['application']['owner']['uid'] == 1000 and
         spec['application']['unit'] == 'ai-harness.service' and
         spec['application']['unitFile'] == '/home/user/.config/systemd/user/ai-harness.service' and
         spec['database']['path'] == '/home/user/.local/share/ai-harness/harness.sqlite',
         'exact UID1000 local application/unit/database required')
    helper = Path(__file__).with_name('key_inventory.py').resolve()
    need(input_value.get('fileGraph', {}).get(str(helper)) == sha(helper.read_bytes()),
         'remote observation helper omitted from frozen source graph')
    need(spec['remoteOwnerObservation']['purpose'] == 'native-carrier' and
         spec['remoteOwnerObservation']['sourceCommit'] == input_value['appSourceCommit'] and
         spec['remoteOwnerObservation']['bindingId'] == input_value['controlRunId'] and
         spec['remoteOwnerObservation']['afterAnchor'] == str(Path(input_value['output']) / 'channel-scope-terminal.json'),
         'remote original policy differs from exact carrier input')
    application = observe_owner(spec['application']['owner'])
    unit = observe_unit(spec['application'], application, private_group_ancestor)
    need(set(spec['generalOwners']) == {'qwen1', 'qwen2', 'mimo'}, 'all three general owners required')
    general = observe_remote_owners(spec['generalOwners'], spec['remoteOwnerObservation'], stage, originals)
    need(isinstance(spec['protectedFiles'], list) and 1 <= len(spec['protectedFiles']) <= 32,
         'protected original credential/key inodes required')
    protected = []
    for item in spec['protectedFiles']:
        protected.append(observe_protected(item, spec['database']['path'], private_group_ancestor))
    database, sequence, request_ids, retained, counts = observe_database(spec['database'], private_group_ancestor)
    need(observe_owner(application) == application and observe_unit(spec['application'], application, private_group_ancestor) == unit,
         'application changed during snapshot')
    need(observe_remote_owners(spec['generalOwners'], spec['remoteOwnerObservation'], stage, originals) == general,
         'root original remote owners changed during snapshot')
    for item in protected:
        again = observe_protected({'path': item['path'], 'identity': item['identity']}, spec['database']['path'], private_group_ancestor)
        need(again == item, 'protected inode/absence changed during snapshot')
    return {'schema': 'legacy-gateway-retained-id-observation-v1',
            'identity': {'applicationHost': 'ai-harness', 'applicationKernelHost': 'aiharness',
                         'applicationOwner': application, 'unit': unit, 'database': database,
                         'admissionSequence': sequence, 'protectedOriginals': protected},
            'requestIds': request_ids, 'retainedRecords': retained, 'counts': counts,
            'nativeOwners': general}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        input_value = strict_json(private_read(path(args.input), 262144))
        output = path(args.output); ancestry(output.parent, True, input_value.get('privateGroupAncestor'))
        allowed = {str(Path(input_value['output']) / name): stage for name, stage in
                   [('driver-preflight.json', 'before'), ('gateway-before.json', 'before'),
                    ('gateway-after.json', 'after'), ('driver-postflight.json', 'after')]}
        need(str(output) in allowed, 'only exact frozen carrier/driver snapshot paths permitted')
        originals = {}
        result = snapshot(input_value, allowed[str(output)], originals)
        original_output = Path(str(output) + '.remote-original.json')
        fd = os.open(original_output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(os.dup(fd), 'wb') as stream:
                stream.write(canonical(originals) + b'\n'); stream.flush(); os.fsync(stream.fileno())
        finally:
            os.close(fd)
        raw = canonical(result) + b'\n'; need(len(raw) <= 8 * 1024 * 1024, 'snapshot output exceeds bound')
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            remaining = raw
            while remaining:
                written = os.write(fd, remaining); need(written > 0, 'output write failed')
                remaining = remaining[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        print(json.dumps({'status': 'READ_ONLY_ORIGINALS', 'sha256': sha(raw), 'bytes': len(raw)}))
        return 0
    except (Refused, InventoryError, OSError, ValueError, sqlite3.Error, subprocess.SubprocessError, KeyError, TypeError) as error:
        # Never print raw rows, unit stderr, environment, credentials or exception payloads.
        print(json.dumps({'status': 'REFUSED', 'errorClass': type(error).__name__}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
