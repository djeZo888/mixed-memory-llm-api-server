#!/usr/bin/env python3
"""Bind already reviewed H019 sources to the actual ready generation; no dispatch."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

BASE = Path('/data/build/H019-20260928')
OWNER = Path('/data/services/mimo-h016-20260927/source/owner.py')
OWNER_SHA = 'e5fda2057168c29b1fe6e53da727b337beaf5634ddbc7dbb3d4f2c46602bcd53'
ADMIT_END = 1790568629


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=('short', 'final'))
    parser.add_argument('--acceptance', type=Path)
    args = parser.parse_args()
    import stat
    for path in (OWNER, *OWNER.parents):
        info = path.lstat()
        require(info.st_uid == 0 and not info.st_mode & 0o022 and not stat.S_ISLNK(info.st_mode), 'protected_owner_required')
    require(hashlib.sha256(OWNER.read_bytes()).hexdigest() == OWNER_SHA, 'owner_pin_changed')
    spec = importlib.util.spec_from_file_location('h019_authority_owner', OWNER)
    o = importlib.util.module_from_spec(spec); spec.loader.exec_module(o); h = o.setup()
    pins = json.loads(o.protected(BASE / 'client-closure.json'))
    for path, pin in pins.items():
        require(hashlib.sha256(o.protected(path)).hexdigest() == pin, 'source_pin_changed')
    manifest, state = o.read(o.BASE / 'manifest.json'), o.read(o.BASE / 'state.json')
    require(state['status'] == 'RUNNING' and not state['request_hold'], 'actual_ready_owner_required')
    o.require_selected(manifest)
    require(state['manifest_sha256'] == o.digest(manifest), 'actual_manifest_required')
    cfg = {'authorized': True, 'purpose': 'H019_SHORT950000' if args.kind == 'short' else 'H019_DIRECT950K',
           'active_cap_seconds': 900 if args.kind == 'short' else 28800,
           'admit_before_epoch': ADMIT_END - 1 if args.kind == 'short' else ADMIT_END,
           'hard_end_epoch': ADMIT_END if args.kind == 'short' else ADMIT_END + 28800,
           'manifest_sha256': o.digest(manifest), 'source_sha256': pins,
           'production_identity': {k:state[k] for k in ('boot_id', 'manifest_sha256', 'supervisor', 'launch_id', 'native')},
           'reader_directory': '/data/build/H016-20260927/worker1-r9',
           'private_api': {'host': '10.156.100.60', 'port': 30012, 'model': 'mimo-v2.6-pro-rl'},
           'frontier_claim_contract': 'ordinary-proxy-single-active-chat-lock-v1'}
    if args.kind == 'final':
        require(args.acceptance is not None, 'native_and_production_receipts_required')
        cfg['acceptance'] = json.loads(o.protected(args.acceptance))
        require(set(cfg['acceptance']) in ({'final_native17', 'production'},
                {'final_native17', 'production', 'sova'}), 'native_and_production_receipts_required')
        cfg['sova_status'] = 'PASS' if 'sova' in cfg['acceptance'] else 'PENDING_NOT_TESTED_APP_PAUSED'
        for proof in cfg['acceptance'].values():
            raw = o.protected(proof['path'])
            require(hashlib.sha256(raw).hexdigest() == proof['sha256'], 'receipt_pin_changed')
            require(proof['expected_value'] in ('PASS', 'PASSED') and
                    json.loads(raw).get(proof['status_field']) == proof['expected_value'], 'actual_pass_required')
    work = BASE / ('worker1-short' if args.kind == 'short' else 'worker1-final950k')
    with h.MountedStorageGuard(h.s) as g, h.AnchoredRoot(str(work), g) as a:
        h.s.root_payload_guard()
        require(not (work / 'CANDIDATE-AUTHORITY.json').exists(), 'candidate_already_exists_review_no_replay')
        a.atomic_json('CANDIDATE-AUTHORITY.json', cfg)
        h.s.root_payload_guard()
    print(json.dumps({'status': 'CANDIDATE_AUTHORITY_WRITTEN_NO_DISPATCH', 'path': str(work / 'CANDIDATE-AUTHORITY.json')}))

if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        print(json.dumps({'status': 'REFUSED', 'error_type': type(exc).__name__}))
        raise SystemExit(1)
