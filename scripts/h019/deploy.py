#!/usr/bin/env python3
"""Root-reviewed H019 source deployment only. Never selects, stops or loads a model."""
import base64
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import time

BASE = Path('/data/build/H019-20260928')
PACKAGE = BASE / 'package'
SERVICE = Path('/data/services/mimo-h016-20260927')
OWNER = SERVICE / 'source/owner.py'
OLD_OWNER = '218c890f1f3d8f7f80998aaf5cf7463c32febf5e454713f40da76a9ed60027d0'
OLD_POLICY = 'c779739a1776ea919f491a60a34811639e2df934a94ea909053710e4864e7229'
OLD_MANIFEST = '952ac402a3f76b31da1e80bdb0b92541b61374737c4850aa8d4a5937fad2fcee'
END = 1790568629


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    require(time.time() < END, 'foreground_window_closed')
    # Bootstrap using exactly the currently deployed, historical trusted owner.
    for p in (OWNER, *OWNER.parents):
        info = p.lstat()
        require(info.st_uid == 0 and not info.st_mode & 0o022 and not stat.S_ISLNK(info.st_mode), 'protected_owner_required')
    require(sha(OWNER.read_bytes()) == OLD_OWNER, 'old_owner_changed')
    spec = importlib.util.spec_from_file_location('h019_deploy_owner', OWNER)
    o = importlib.util.module_from_spec(spec); spec.loader.exec_module(o); h = o.setup()
    entries = json.loads(o.protected(PACKAGE / 'scripts/h019/deployment-files.json'))
    content = {}
    for dest, row in entries.items():
        require(dest.startswith(('/data/build/H019-20260928/', '/data/services/mimo-h016-20260927/',
                                  '/usr/local/lib/llm-server/', '/etc/systemd/system/')), 'target_outside_review')
        raw = o.protected(PACKAGE / row['source'])
        require(sha(raw) == row['sha256'], 'candidate_source_pin_changed')
        content[dest] = raw
    old = o.read(SERVICE / 'manifest.json')
    require(o.digest(old) == OLD_MANIFEST, 'old_manifest_changed')
    o.source_preflight(h, old)
    state, selection = o.read(SERVICE / 'state.json'), o.selection()
    require(state['status'] == 'SETTLED' and state.get('request_hold') is False, 'old_mimo_unsettled')
    require(selection == {'schema_version': 1, 'generation': 11, 'selected_frontier': 'glm-5.3-flash'}, 'selection_changed')
    for target in ('control-api', 'node-api'):
        p = '/usr/local/lib/llm-server/' + target + '/scripts/lifecycle/hardware_policy.py'
        require(sha(o.protected(p)) == OLD_POLICY, 'old_policy_changed')
    def show(unit):
        return dict(x.split('=', 1) for x in o.run(['systemctl', 'show', unit,
            '-p', 'MainPID,ActiveState,SubState,InvocationID'], 3).splitlines())
    require(show(o.UNIT)['MainPID'] == '0', 'mimo_owner_still_active')
    before = {unit:show(unit) for unit in ('llm-control.service', 'llm-node.service')}
    require(all(v['ActiveState'] == 'active' for v in before.values()), 'expected_api_services_changed')
    lock_before = o.LEASE_PATH.stat()
    identity = [lock_before.st_dev, lock_before.st_ino]
    # Complete lifecycle storage scans occur outside the canonical critical section.
    with h.MountedStorageGuard(h.s) as g:
        h.s.root_payload_guard(); o.storage_paths(h, g)
        for path in (str(BASE), str(BASE / 'package')): g.check_path(path)
        require(not (BASE / 'DEPLOY.json').exists() and not (BASE / 'BACKUP.json').exists(), 'one_deployment_no_replay')
        for root in ('/data/build', '/data/logs'):
            with h.AnchoredRoot(root, g) as a:
                a.mkdir('H019-20260928/worker1-short'); a.mkdir('H019-20260928/worker1-final950k')
        backup = {}
        for dest in set(content) | {str(SERVICE / n) for n in ('state.json', 'selection.json', 'guard.json', 'proxy-state.json')}:
            path = Path(dest)
            if path.exists():
                raw = o.protected(path)
                backup[dest] = {'sha256': sha(raw), 'mode': stat.S_IMODE(path.stat().st_mode),
                                'base64': base64.b64encode(raw).decode()}
            else:
                require(not path.is_symlink(), 'target_symlink')
                backup[dest] = {'prior': 'ABSENT'}
        with h.AnchoredRoot(str(BASE), g) as a:
            with a.open('BACKUP.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400) as f:
                f.write((json.dumps(backup, sort_keys=True) + '\n').encode())
    # Stop API processes normally so neither retains an imported old policy.
    # Never stop them while holding the lock they may need for orderly shutdown.
    o.run(['systemctl', 'stop', 'llm-node.service', 'llm-control.service'], 25)
    mutations = []
    with h.MountedStorageGuard(h.s) as g:
        with h.acquire_lease(blocking=False) as lease:
            require([o.LEASE_PATH.stat().st_dev, o.LEASE_PATH.stat().st_ino] == identity, 'canonical_lock_changed')
            require(o.selection() == selection, 'selection_changed_during_deploy')
            for dest, raw in content.items():
                path = Path(dest)
                if dest.startswith('/data/'):
                    g.check_path(dest)
                    with h.AnchoredRoot(str(path.parent), g) as a:
                        with a.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600) as f:
                            f.write(raw)
                else:
                    # Root-owned system source, same-directory atomic replacement.
                    for parent in path.parents:
                        info = parent.lstat()
                        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
                                'untrusted_system_parent')
                    tmp = path.with_name(path.name + '.h019-new')
                    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
                    with os.fdopen(fd, 'wb') as f:
                        f.write(raw); f.flush(); os.fsync(f.fileno())
                    os.replace(tmp, path)
                require(sha(o.protected(path)) == entries[dest]['sha256'], 'installed_source_mismatch')
                mutations.append({'path': dest, 'sha256': entries[dest]['sha256']})
            lease.validate()
        h.s.root_payload_guard()
    # Only new independent client units require this reload; model units unchanged.
    o.run(['systemctl', 'daemon-reload'], 10)
    o.run(['systemctl', 'start', 'llm-control.service', 'llm-node.service'], 15)
    after = {unit:show(unit) for unit in before}
    require(all(v['ActiveState'] == 'active' and v['MainPID'] != '0' and
                v['InvocationID'] != before[u]['InvocationID'] for u,v in after.items()), 'api_restart_unproven')
    require(o.selection() == selection, 'selection_changed')
    require([o.LEASE_PATH.stat().st_dev, o.LEASE_PATH.stat().st_ino] == identity, 'canonical_lock_changed')
    record = {'status': 'SOURCE_DEPLOYED_OBSERVATION_REQUIRED_BEFORE_MODEL_LOAD',
              'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'mutations': mutations,
              'canonical_identity': identity, 'selection': selection, 'api_before': before, 'api_after': after,
              'backup': str(BASE / 'BACKUP.json'), 'backup_sha256': sha(o.protected(BASE / 'BACKUP.json')),
              'model_lifecycle_changed': False, 'image_release_changed': False}
    with h.MountedStorageGuard(h.s) as g, h.AnchoredRoot(str(BASE), g) as a:
        a.atomic_json('DEPLOY.json', record)
    print(json.dumps(record))

if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        # Partial deployments remain explicit; never silently restart/rollback a model.
        print(json.dumps({'status': 'DEPLOY_FAILED_NO_AUTORETRY', 'error_type': type(exc).__name__}))
        raise SystemExit(1)
