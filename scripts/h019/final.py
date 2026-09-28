#!/usr/bin/env python3
"""H019 direct950K adapter; historical framed transport/reader remain unchanged."""
import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time

BASE = Path('/data/build/H019-20260928/worker1-final950k')
LOG = '/data/logs/H019-20260928/worker1-final950k'
UNIT = 'h019-final950k.service'
OWNER = Path('/data/services/mimo-h016-20260927/source/owner.py')
TRANSPORT = Path('/data/build/H018-20260928/worker1-last950k/client.py')
READER = TRANSPORT.with_name('reader.py')
ACTIVE_CAP = 28800
ADMIT_END = 1790568629  # 2026-09-28T04:10:29Z
OUTPUT = 1024
LABEL = 'H019-near950K'
PORT = 30012


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def validate_go(go, now):
    require(go.get('authorized') is True and go.get('purpose') == 'H019_DIRECT950K', 'current_authority_required')
    require(type(go.get('active_cap_seconds')) is int and go['active_cap_seconds'] == ACTIVE_CAP, 'exact_8h_cap_required')
    require(now < go['admit_before_epoch'] <= ADMIT_END
            and go['hard_end_epoch'] == go['admit_before_epoch'] + ACTIVE_CAP, 'finite_admission_required')
    require(go.get('private_api') == {'host': '10.156.100.60', 'port': PORT, 'model': 'mimo-v2.6-pro-rl'}, 'private_api_identity')
    require(go.get('frontier_claim_contract') == 'ordinary-proxy-single-active-chat-lock-v1', 'proxy_claim_required')
    require(set(go.get('acceptance', {})) == {'final_native17', 'production', 'sova'}, 'actual_acceptance_required')
    require(bool(go.get('source_sha256')) and bool(go.get('production_identity')), 'source_and_owner_required')


def request_plan(capacity):
    require(type(capacity) is int and capacity == 950000, 'actual_950000_slot_required')
    return [(LABEL, capacity - OUTPUT - 1, OUTPUT)]


def setup():
    # Use the protected production reader before importing historic dependencies.
    import stat
    for path in (OWNER, *OWNER.parents):
        info = path.lstat()
        require(info.st_uid == 0 and not info.st_mode & 0o022 and not stat.S_ISLNK(info.st_mode), 'protected_owner_required')
    require(hashlib.sha256(OWNER.read_bytes()).hexdigest() == OWNER_SHA, 'owner_pin_changed')
    spec = importlib.util.spec_from_file_location('h019_owner', OWNER)
    o = importlib.util.module_from_spec(spec); spec.loader.exec_module(o)
    require(hashlib.sha256(o.protected(TRANSPORT)).hexdigest() == TRANSPORT_SHA, 'historic_transport_changed')
    spec = importlib.util.spec_from_file_location('h019_transport', TRANSPORT)
    c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
    c.BASE, c.LOG, c.UNIT, c.READER = BASE, LOG, UNIT, READER
    c.validate_go = validate_go
    cfg, cfg_sha = c.read_go(o)
    required = {str(Path(__file__).resolve()), str(TRANSPORT), str(READER), str(OWNER), str(OWNER.with_name('private_proxy.py'))}
    require(required <= set(cfg['source_sha256']), 'current_source_closure_required')
    for path, pin in cfg['source_sha256'].items():
        require(hashlib.sha256(o.protected(path)).hexdigest() == pin, 'source_pin_changed')
    return o, c, cfg, cfg_sha


def settle():
    o, c, cfg, cfg_sha = setup()
    # Historical settlement's purpose check is made against a copy only; on-disk
    # current authority and exact receipt hash remain unchanged.
    require(cfg.get('purpose') == 'H019_DIRECT950K', 'current_authority_required')
    historical = dict(cfg, purpose='H018_LAST_NEAR950K')
    c.owner = lambda: o
    c.read_go = lambda _: (historical, cfg_sha)
    c.settle()

OWNER_SHA = '57ace7da1f84e09cb7ed5f0a72ac18315a9875d4c8c00f87f768288bf1b2c5f8'
TRANSPORT_SHA = '28d61829c6b28067b59db4520ef72a94d5b230cfb28058f2cfe8984525b1f63b'

def run():
    o, c, go, go_sha = setup()
    h, manifest, state, guard, reader_dir = c.preflight(o, go)
    write = c.write
    check_identity = c.check_identity
    adapter = c.adapter
    load_module = c.load_module
    LocalBusyNotSubmitted = c.LocalBusyNotSubmitted
    started = time.time()
    deadline = min(started + ACTIVE_CAP, go['hard_end_epoch'])
    result = {'status': 'PREPARING', 'go_sha256': go_sha, 'started_epoch': started,
              'hard_end_epoch': deadline, 'completed_rungs': [], 'stages': {LABEL: 'QUEUED'}, 'production_identity': go['production_identity'], 'request_may_be_active': False}
    require(not Path(LOG, 'CLIENT.json').exists(), 'single_attempt_no_replay')
    write(o, h, 'CLIENT.json', result)
    sys.path.insert(0, str(reader_dir))
    reader = load_module('long_reviewed_reader', READER)
    def busy_not_submitted(evidence):
        result['stages'][reader.active_label] = 'BUSY_NOT_SUBMITTED'
        result.update(status='BUSY_NOT_SUBMITTED', request_may_be_active=False,
                      owned_disposition={**evidence, 'label': reader.active_label}, finished_epoch=time.time())
        write(o, h, 'CLIENT.json', result)
    def own_stream_drained(row):
        disposition = row.get('owned_stream_disposition', {})
        require(disposition.get('status') == 'OWN_STREAM_TERMINAL_FULL_DRAIN' and
                row.get('done') is True and row.get('full_http_drain') is True,
                'own_stream_completion_evidence_required')
        result.update(request_may_be_active=False, owned_disposition={**disposition, 'label': reader.active_label},
                      full_http_drain=True, last_completed_receipt=reader.active_label + '.json')
        write(o, h, 'CLIENT.json', result)
    adapter(reader, o, h, deadline, on_local_busy=busy_not_submitted)
    # Historical adapter sets both clocks to execution end; current admission
    # must close before 04:10:29 even if counting/staging crosses that boundary.
    reader.ADMIT_END = min(deadline, go['admit_before_epoch'])
    key = o.read_key(h)
    require(o.native_ready(manifest, key) is True, 'actual_production_native_not_ready')
    code, slots = reader.get(PORT, '/slots', key)
    require(code == 200 and len(slots) == 1 and slots[0].get('n_ctx') == manifest['context']
            and slots[0].get('is_processing') is False, 'private_api_actual_slot_required')
    guard_stack = contextlib.ExitStack()
    mounted = guard_stack.enter_context(h.MountedStorageGuard(h.s))
    anchored = guard_stack.enter_context(h.AnchoredRoot(LOG, mounted))
    guard_file = guard_stack.enter_context(anchored.open('GUARD-PROGRESS.jsonl', os.O_WRONLY | os.O_CREAT | os.O_EXCL))
    class ExistingOwnerGuard:
        def is_set(self):
            # No filesystem, lifecycle lock, systemctl, or guard sampling per delta.
            require(time.time() < deadline, 'finite_active_deadline')
            return False
    failed = ExistingOwnerGuard()
    def alarm(*_):
        failed.is_set()
        _, _, sample = check_identity(o, go, allow_active=True)
        raw = (json.dumps(sample, separators=(',', ':')) + '\n').encode()
        require(os.write(guard_file.fileno(), raw) == len(raw), 'guard_receipt_short_write')
    def interrupted(*_):
        raise RuntimeError('long_client_interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, 5, 5)
    try:
        write(o, h, 'GUARD-BEFORE.json', guard)
        for label, target, output in request_plan(manifest['context']):
            # Exactly one direct near-950K request; no 64K precondition.
            check_identity(o, go)
            reader.active_label = label
            result['stages'][label] = 'PREPARING'
            write(o, h, 'CLIENT.json', result)
            payload, _, codes = reader.fixture(key, target, 'H019-' + label + '-20260928', failed.is_set)
            payload['max_tokens'] = output
            exact, _ = reader.count(key, payload)
            require(exact == target and exact + output <= manifest['context'] - 1, 'exact_prompt_output_reserve')
            forecast = exact / 61 + output / 7.76 + 300
            require(time.time() + forecast < deadline, 'measured_completion_estimate_exceeds_cap')
            require(time.time() < go['admit_before_epoch'], 'admission_closed_before_dispatch')
            result['stages'][label] = 'RUNNING'
            result.update(status=label + '_RUNNING', request_may_be_active=True,
                          dispatch_preparation_epoch=time.time(), execution_cap_seconds=ACTIVE_CAP,
                          owned_disposition={'status': 'UNKNOWN_POSSIBLY_SUBMITTED', 'label': label},
                          exact_input_tokens=exact, output_budget=output, actual_slot=manifest['context'],
                          admission_planning_seconds=forecast, final_count_seconds=reader.last_count_seconds)
            write(o, h, 'CLIENT.json', result)
            row = reader.request(h, key, payload, label, failed, manifest['context'], planning_seconds=forecast,
                                 on_owned_stream_drained=own_stream_drained)
            reader.record_semantics(h, label, row, reader.fixture_correct(row, codes), 'long_fixture_semantics_failed')
            require(row.get('done') is True and row.get('full_http_drain') is True
                    and row.get('native_settlement', {}).get('status') == 'AUTHENTICATED_SLOT_IDLE_AFTER_FULL_DRAIN',
                    'long_terminal_and_idle_proof_required')
            # OUR completion was durably cleared inside the reader before its
            # first global probe. Shared-lane availability can only stop this
            # chain; it cannot turn another caller into our unsettled request.
            require(result.get('request_may_be_active') is False, 'own_completion_callback_missing')
            # Allow the existing private proxy's final disposition publication to settle.
            for _ in range(25):
                proxy = o.read(o.BASE / 'proxy-state.json')
                if proxy.get('active_requests') == 0:
                    break
                time.sleep(.2)
            _, _, final_guard = check_identity(o, go)
            write(o, h, label + '-GUARD-AFTER.json', final_guard)
            result['stages'][label] = 'PASS'
            result['completed_rungs'].append(target)
            result.update(status=label + '_PASS', request_may_be_active=False,
                          full_http_drain=True, last_completed_receipt=label + '.json')
            write(o, h, 'CLIENT.json', result)
        result.update(status='PASS_KEEP_WARM', finished_epoch=time.time())
    except LocalBusyNotSubmitted:
        require(result.get('status') == 'BUSY_NOT_SUBMITTED' and result.get('request_may_be_active') is False,
                'local_busy_disposition_not_persisted')
        return
    except BaseException as exc:
        result.update(status='FAILED_NO_RETRY', error_type=type(exc).__name__, finished_epoch=time.time())
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        guard_stack.close()
        write(o, h, 'CLIENT.json', result)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['run', 'settle'])
    args = p.parse_args()
    try:
        run() if args.action == 'run' else settle()
    except BaseException as exc:
        print(json.dumps({'status': 'REFUSED_OR_FAILED', 'error_type': type(exc).__name__}))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
