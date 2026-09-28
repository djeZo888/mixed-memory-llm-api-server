#!/usr/bin/env python3
"""Stage only the two authentic H019 PASS receipts; no authority or dispatch."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat

BASE = Path('/data/build/H019-20260928')
LOG = Path('/data/logs/H019-20260928')
OWNER = Path('/data/services/mimo-h016-20260927/source/owner.py')
OWNER_SHA = 'e5fda2057168c29b1fe6e53da727b337beaf5634ddbc7dbb3d4f2c46602bcd53'
PROOFS = {
    'final_native17': {'path': str(LOG / 'worker1-short/FINAL17-QUALIFICATION.json'),
        'sha256': 'a3e0d9ab4589d8f1a79b6154fda08be1b64fece1dcbaeb1876ef1e677ce4d923',
        'status_field': 'status', 'expected_value': 'PASS'},
    'production': {'path': str(LOG / 'worker1-short/ALLOCATION.json'),
        'sha256': '290564ca19af632e118e536fff35699e928131d44c010391e23d0db5c0e7e184',
        'status_field': 'status', 'expected_value': 'PASS'},
}


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def main():
    for path in (OWNER, *OWNER.parents):
        info = path.lstat()
        require(info.st_uid == 0 and not info.st_mode & 0o022 and not stat.S_ISLNK(info.st_mode), 'owner_not_protected')
    require(hashlib.sha256(OWNER.read_bytes()).hexdigest() == OWNER_SHA, 'owner_pin_changed')
    spec = importlib.util.spec_from_file_location('h019_acceptance_owner', OWNER)
    o = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(o)
    h = o.setup()
    state = o.read(o.BASE / 'state.json')
    require(state['status'] == 'RUNNING' and state['request_hold'] is False, 'ready_owner_required')
    manifest = o.read(o.BASE / 'manifest.json')
    o.require_selected(manifest)
    require(o.digest(manifest) == state['manifest_sha256'] == 'd8bd9326118458774ac2b585e6029faa2a607d195001d85e14c5d238f6c05be4', 'manifest_changed')
    require(state['launch_id'] == 'b23d112359424d909862207e30f0c9d7', 'launch_changed')
    values = {}
    for label, proof in PROOFS.items():
        raw = o.protected(proof['path'])
        require(hashlib.sha256(raw).hexdigest() == proof['sha256'], 'receipt_pin_changed')
        values[label] = json.loads(raw)
        require(values[label]['status'] == 'PASS', 'actual_pass_required')
    identity = {k: state[k] for k in ('boot_id', 'manifest_sha256', 'supervisor', 'launch_id', 'native')}
    require(values['production']['production_identity'] == identity, 'allocation_identity_changed')
    markers = [BASE / 'acceptance.json', BASE / 'worker1-final950k/CANDIDATE-AUTHORITY.json',
        BASE / 'worker1-final950k/ROOT-GO.json', LOG / 'worker1-final950k/DISPATCH-ATTEMPT.json',
        LOG / 'worker1-final950k/CLIENT.json']
    require(all(not p.exists() and not p.is_symlink() for p in markers), 'existing_attempt_no_overwrite')
    lock = Path('/run/llmctl/lifecycle.lock').stat()
    require((lock.st_dev, lock.st_ino) == (26, 1838), 'canonical_lock_changed')
    raw = (json.dumps(PROOFS, sort_keys=True, indent=2) + '\n').encode()
    # All code/input transfer precedes this guard. No lifecycle lease is held.
    with h.MountedStorageGuard(h.s) as g, h.AnchoredRoot(str(BASE), g) as a:
        o.storage_paths(h, g)
        h.s.root_payload_guard()
        with a.open('acceptance.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) as stream:
            stream.write(raw)
            stream.fsync()
        a.check()
        require(o.protected(BASE / 'acceptance.json') == raw, 'acceptance_readback_changed')
        h.s.root_payload_guard()
    print(json.dumps({'status': 'ACCEPTANCE_STAGED_NO_DISPATCH', 'path': str(BASE / 'acceptance.json'),
        'sha256': hashlib.sha256(raw).hexdigest(), 'entries': sorted(PROOFS)}))


if __name__ == '__main__':
    main()
