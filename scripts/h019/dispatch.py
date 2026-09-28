#!/usr/bin/env python3
"""One H019 conditional dispatch with exact fresh owner evidence; no load or replay."""
import argparse
import datetime
import hashlib
import importlib.util
import json
import time
from pathlib import Path

BASE = Path('/data/build/H019-20260928')
LOG = Path('/data/logs/H019-20260928')
OWNER = Path('/data/services/mimo-h016-20260927/source/owner.py')
OWNER_SHA = 'e5fda2057168c29b1fe6e53da727b337beaf5634ddbc7dbb3d4f2c46602bcd53'
ADMIT_END = 1790568629


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def fresh_latch(o, h, m, state, lease):
    # The sole sample is bracketed by same-boot validation; the held lease is
    # borrowed, never reacquired. The total budget includes the thermal query.
    cycle = time.monotonic()
    with o.bounded(5):
        limit = o.temperature_limit(o.run(['nvidia-smi', '--id=' + o.GPU, '-q', '-x'], 2))
        sample = o.sample_guard(m, state['baseline'], limit, state['native'], proof_boot=state['boot_id'])
        hardware = o.latch(h, state['boot_id'], lease=lease,
                          evidence=sample.get('hardware_validation'), deadline=cycle + 5)
    return sample, hardware


def dispatch(kind):
    import stat
    for path in (OWNER, *OWNER.parents):
        info = path.lstat()
        require(info.st_uid == 0 and not info.st_mode & 0o022 and not stat.S_ISLNK(info.st_mode), 'protected_owner_required')
    require(hashlib.sha256(OWNER.read_bytes()).hexdigest() == OWNER_SHA, 'owner_pin_changed')
    o = module('h019_dispatch_owner', OWNER); h = o.setup()
    suffix = 'worker1-short' if kind == 'short' else 'worker1-final950k'
    work, log = BASE / suffix, LOG / suffix
    cfg = json.loads(o.protected(work / 'CANDIDATE-AUTHORITY.json'))
    require(time.time() < cfg['admit_before_epoch'] <= ADMIT_END, 'current_admission_required')
    source = work / ('short.py' if kind == 'short' else 'final.py')
    require({str(source), str(OWNER), str(Path(__file__).resolve())} <= set(cfg['source_sha256']), 'dispatch_source_closure_required')
    for path, pin in cfg['source_sha256'].items():
        require(hashlib.sha256(o.protected(path)).hexdigest() == pin, 'source_pin_changed')
    client = module('h019_dispatch_client', source)
    if kind == 'final':
        client.validate_go(cfg, time.time())
        for label, proof in cfg['acceptance'].items():
            raw = o.protected(proof['path'])
            require(hashlib.sha256(raw).hexdigest() == proof['sha256'], 'acceptance_pin_changed')
            require(proof['expected_value'] in ('PASS', 'PASSED') and
                    json.loads(raw).get(proof['status_field']) == proof['expected_value'], 'actual_acceptance_required')
    else:
        require(cfg.get('authorized') is True and cfg.get('purpose') == 'H019_SHORT950000', 'short_authority_required')
        require(time.time() + 600 < cfg['hard_end_epoch'] <= ADMIT_END, 'short_completion_budget_required')
    transport = module('h019_dispatch_transport', client.TRANSPORT)
    transport.LOG = str(log)
    m, state, guard = transport.check_identity(o, cfg)
    o.source_preflight(h, m)
    require(o.native_ready(m, o.read_key(h)) is True, 'native_not_ready')
    unit = 'h019-short.service' if kind == 'short' else 'h019-final950k.service'
    fields = o.run(['systemctl', 'show', unit, '-p', 'MainPID,ActiveState,UnitFileState'], 3)
    current = dict(x.split('=', 1) for x in fields.splitlines())
    require(current == {'MainPID': '0', 'ActiveState': 'inactive', 'UnitFileState': 'static'}, 'client_not_inactive_static')
    authority_name = 'AUTHORITY.json' if kind == 'short' else 'ROOT-GO.json'
    require(not (work / authority_name).exists() and not (log / 'CLIENT.json').exists()
            and not (log / 'DISPATCH-ATTEMPT.json').exists(), 'one_attempt_no_replay')
    with h.MountedStorageGuard(h.s) as g:
        o.storage_paths(h, g); h.s.root_payload_guard()
        g.check_path(str(work)); g.check_path(str(log))
        with h.acquire_lease(blocking=False) as lease:
            m, state, guard = transport.check_identity(o, cfg)
            sample, hardware = fresh_latch(o, h, m, state, lease)
            require(time.time() < cfg['admit_before_epoch'], 'admission_closed_before_intent')
            with h.AnchoredRoot(str(work), g) as a:
                a.atomic_json(authority_name, cfg)
            intent = {'status': 'DISPATCH_INTENT', 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      'production_identity': cfg['production_identity'], 'memory_policy': sample['memory_policy'],
                      'hardware': hardware, 'authority_sha256': hashlib.sha256(o.protected(work / authority_name)).hexdigest()}
            with h.AnchoredRoot(str(log), g) as a:
                a.atomic_json('DISPATCH-ATTEMPT.json', intent)
            lease.validate()
    # No lifecycle lease or storage scan spans systemd dispatch/inference.
    require(time.time() < cfg['admit_before_epoch'], 'admission_closed_before_start')
    o.run(['systemctl', 'start', unit], 10)
    print(json.dumps({'status': 'DISPATCHED_VERIFY_ACTUAL_START_SEPARATELY', 'unit': unit,
                      'staging_lease_released_before_dispatch': True}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=('short', 'final'))
    try:
        dispatch(parser.parse_args().kind)
    except BaseException as exc:
        print(json.dumps({'status': 'REFUSED_OR_FAILED_NO_RETRY', 'error_type': type(exc).__name__}))
        raise SystemExit(1)
