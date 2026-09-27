#!/usr/bin/env python3
"""Root-reviewed LAST request; source-only until protected explicit GO exists."""
import argparse
import contextlib
import datetime
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time
import types

BASE = Path('/data/build/H016-20260927/worker1-final13-long')
LOG = '/data/logs/H016-20260927/worker1-final13-long'
OWNER = Path('/data/services/mimo-h016-20260927/source/owner.py')
UNIT = 'h016-final13-long.service'
HOST, PORT = '10.156.100.60', 30012
ACTIVE_CAP = 8 * 60 * 60
OUTPUT = 1024
LABEL = 'LAST-near1M'
COUNT_CAP = 15


def request_plan(capacity):
    return [('LAST-64K', 65536, 256), (LABEL, token_target(capacity), OUTPUT)]


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def owner():
    # Trust the same protected ancestry contract before importing privileged code.
    import stat
    for p in [OWNER, *OWNER.parents]:
        st = p.lstat()
        require(st.st_uid == 0 and not st.st_mode & 0o022 and not stat.S_ISLNK(st.st_mode), 'owner_protected_ancestry')
    return load_module('long_production_owner', OWNER)


def validate_go(go, now):
    require(go.get('authorized') is True and go.get('purpose') == 'H016_LAST_NEAR1M', 'root_go_required')
    require(type(go.get('active_cap_seconds')) is int and go['active_cap_seconds'] == ACTIVE_CAP, 'exact_8h_cap_required')
    require(now < go['admit_before_epoch'] <= go['hard_end_epoch'] - ACTIVE_CAP, 'finite_admission_required')
    require(go.get('private_api') == {'host': HOST, 'port': PORT, 'model': 'mimo-v2.6-pro-rl'}, 'private_api_identity')
    require(go.get('w2_exclusive_frontier_sova_paused') is True and go.get('other_three_loaded_idle') is True
            and go.get('lane_exclusive_until_epoch', 0) >= go['hard_end_epoch'], 'exclusive_lane_authority_required')
    require(set(go.get('acceptance', {})) == {'final_native17', 'production', 'sova'}, 'all_acceptance_proofs_required')
    require(isinstance(go.get('source_sha256'), dict) and go['source_sha256'], 'source_pins_required')
    require(isinstance(go.get('production_identity'), dict) and go['production_identity'], 'actual_owner_required')


def token_target(capacity):
    require(type(capacity) is int and capacity in (1000000, 1000192), 'actual_near1m_slot_required')
    target = capacity - OUTPUT - 1
    require(target + OUTPUT <= capacity - 1, 'output_and_native_slot_reserve')
    return target


def write(o, h, name, value):
    with h.MountedStorageGuard(h.s) as g, h.AnchoredRoot(LOG, g) as a:
        h.s.root_payload_guard()
        a.atomic_json(name, value)
        h.s.root_payload_guard()


def check_identity(o, go, allow_active=False):
    manifest = o.read(o.BASE / 'manifest.json')
    o.validate_manifest(manifest)
    require(o.digest(manifest) == go['manifest_sha256'], 'production_manifest_changed')
    o.require_selected(manifest)
    state = o.read(o.BASE / 'state.json')
    actual = {k: state.get(k) for k in ('boot_id', 'manifest_sha256', 'supervisor', 'launch_id', 'native')}
    require(actual == go['production_identity'] and state.get('status') == 'RUNNING'
            and state.get('request_hold') is False, 'production_owner_changed_or_held')
    unit = dict(x.split('=', 1) for x in o.run(['systemctl', 'show', o.UNIT, '-p', 'MainPID,InvocationID,ActiveState'], 2).splitlines())
    require(unit['ActiveState'] == 'active' and int(unit['MainPID']) == state['supervisor']['pid']
            and unit['InvocationID'] == state['supervisor']['invocation_id'], 'production_supervisor_changed')
    guard = o.read(o.BASE / 'guard.json')
    require(guard.get('status') == 'ok' and guard.get('native') == state['native']
            and guard.get('supervisor') == state['supervisor'] and guard.get('boot_id') == state['boot_id']
            and guard.get('manifest_sha256') == go['manifest_sha256']
            and 0 <= time.monotonic() - guard.get('observed_monotonic_s', 0) <= 15
            and guard.get('hardware_latched') is False, 'fresh_existing_owner_guard_required')
    proxy = o.read(o.BASE / 'proxy-state.json')
    require(proxy.get('launch_id') == state['launch_id'] and proxy.get('native') == state['native']
            and proxy.get('quarantined') is False and proxy.get('active_requests') in ((0, 1) if allow_active else (0,)),
            'production_lane_not_clean')
    return manifest, state, guard


def adapter(reader, o, h, deadline):
    original = http.client.HTTPConnection
    class PrivateConnection(original):
        def __init__(self, host, port=None, *args, **kwargs):
            require((host, port) == ('127.0.0.1', 30012), 'reader_endpoint_changed')
            super().__init__(HOST, PORT, *args, **kwargs)
        def connect(self):
            super().connect()
            if getattr(self, '_count_deadline', None):
                self.sock.settimeout(max(.001, self._count_deadline - time.monotonic()))
        def request(self, method, url, *args, **kwargs):
            if method == 'POST' and url == '/v1/chat/completions/input_tokens':
                self._count_deadline = time.monotonic() + COUNT_CAP
                self.timeout = min(self.timeout or COUNT_CAP, COUNT_CAP)
            result = super().request(method, url, *args, **kwargs)
            if method == 'POST' and url == '/v1/chat/completions':
                write(o, h, getattr(reader, 'active_label', LABEL) + '-BODY-SENT.json', {'event': 'BODY_SENT', 'utc': reader.utc_now(),
                    'monotonic_seconds': time.monotonic()})
            return result
    reader.http = types.SimpleNamespace(client=types.SimpleNamespace(HTTPConnection=PrivateConnection))
    reader.LOG = LOG
    reader.CLIENT_END = reader.ADMIT_END = deadline
    original_count = reader.count
    def bounded_count(key, payload):
        started_count = time.monotonic()
        value = original_count(key, payload)
        elapsed = time.monotonic() - started_count
        require(elapsed <= COUNT_CAP, 'count_exceeded_15s_no_dispatch')
        reader.last_count_seconds = elapsed
        return value
    reader.count = bounded_count
    reader.save = lambda hh, name, value: write(o, hh, name, value)
    def get(port, path, key):
        require(port == PORT, 'reader_get_port_changed')
        c = original(HOST, PORT, timeout=5)
        try:
            c.request('GET', path, headers={'Authorization': 'Bearer ' + key.decode()})
            r = c.getresponse()
            raw = r.read(1024 * 1024 + 1)
            require(len(raw) <= 1024 * 1024, 'private_response_bound')
            return r.status, json.loads(raw)
        finally:
            c.close()
    reader.get = get


def read_go(o):
    raw = o.protected(BASE / 'ROOT-GO.json')
    go = json.loads(raw)
    return go, sha(raw)


def preflight(o, go):
    validate_go(go, time.time())
    require(str(Path(__file__).resolve()) in go['source_sha256'] and str(OWNER) in go['source_sha256'], 'client_and_owner_pins_required')
    reader_dir = Path(go['reader_directory'])
    require(reader_dir.is_absolute() and str(reader_dir).startswith('/data/build/H016-20260927/'), 'registered_reader_path_required')
    required = {'benchmark.py', 'candidate_owner.py', 'telemetry.py', 'verify_retained.py', 'private_proxy.py'}
    require({str(reader_dir / x) for x in required} <= set(go['source_sha256']), 'reader_closure_pins_required')
    for path, pin in go['source_sha256'].items():
        require(o.HEX.fullmatch(pin) and sha(o.protected(path)) == pin, 'source_pin_changed')
    for label, proof in go['acceptance'].items():
        raw = o.protected(proof['path'])
        require(sha(raw) == proof['sha256'], 'acceptance_pin_changed_' + label)
        value = json.loads(raw)
        # Root names the existing receipt's status field/value, preserving its schema.
        require(proof.get('expected_value') in ('PASS', 'PASSED') and value.get(proof['status_field']) == proof['expected_value'],
                'actual_acceptance_not_pass_' + label)
    h = o.setup()
    manifest, state, guard = check_identity(o, go)
    o.source_preflight(h, manifest)
    token_target(manifest['context'])
    own = dict(x.split('=', 1) for x in o.run(['systemctl', 'show', UNIT, '-p', 'MainPID,InvocationID,ActiveState,ControlGroup'], 2).splitlines())
    cg = Path('/proc/self/cgroup').read_text().split('::', 1)[1].strip()
    require(own['ActiveState'] in ('active', 'activating') and int(own['MainPID']) == os.getpid()
            and own['InvocationID'] == os.environ.get('INVOCATION_ID') and cg == own['ControlGroup'], 'independent_systemd_owner_required')
    return h, manifest, state, guard, reader_dir


def settle():
    o = owner()
    go, go_sha = read_go(o)
    try:
        result = o.read(Path(LOG) / 'CLIENT.json')
    except FileNotFoundError:
        return
    require(result.get('go_sha256') == go_sha, 'client_authority_changed')
    require(go.get('authorized') is True and go.get('purpose') == 'H016_LAST_NEAR1M', 'settlement_root_go_required')
    require({str(OWNER), str(Path(__file__).resolve())} <= set(go.get('source_sha256', {})), 'settlement_pins_required')
    for path, pin in go['source_sha256'].items():
        require(o.HEX.fullmatch(pin) and sha(o.protected(path)) == pin, 'settlement_source_changed')
    if result.get('status') == 'PASS_KEEP_WARM' or not result.get('request_may_be_active'):
        return
    # Never change selection or restart a model. The reviewed unit's ExecStopPost
    # performs exact container/PID/cgroup/GPU settlement, preserving request hold.
    state = o.read(o.BASE / 'state.json')
    expected = go['production_identity']
    require(all(state.get(k) == v for k, v in expected.items()), 'failure_owner_identity_changed')
    if state.get('status') == 'SETTLED':
        return
    unit = dict(x.split('=', 1) for x in o.run(['systemctl', 'show', o.UNIT, '-p', 'MainPID,InvocationID'], 2).splitlines())
    require(unit['InvocationID'] == expected['supervisor']['invocation_id']
            and int(unit['MainPID']) == expected['supervisor']['pid'], 'failure_supervisor_changed')
    o.run(['systemctl', 'stop', o.UNIT], 55)
    final = o.read(o.BASE / 'state.json')
    require(final.get('status') == 'SETTLED' and final.get('settlement') ==
            {'pid_released': True, 'cgroup_empty': True, 'gpu_compute_empty': True}, 'existing_owner_settlement_unproven')


def run():
    o = owner()
    go, go_sha = read_go(o)
    h, manifest, state, guard, reader_dir = preflight(o, go)
    started = time.time()
    deadline = min(started + ACTIVE_CAP, go['hard_end_epoch'])
    result = {'status': 'PREPARING', 'go_sha256': go_sha, 'started_epoch': started,
              'hard_end_epoch': deadline, 'completed_rungs': [], 'stages': {'LAST-64K': 'QUEUED', LABEL: 'QUEUED_AFTER_64K_PASS'}, 'production_identity': go['production_identity'], 'request_may_be_active': False}
    require(not Path(LOG, 'CLIENT.json').exists(), 'single_attempt_no_replay')
    write(o, h, 'CLIENT.json', result)
    sys.path.insert(0, str(reader_dir))
    reader = load_module('long_reviewed_reader', reader_dir / 'benchmark.py')
    adapter(reader, o, h, deadline)
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
            # A later rung is reachable only after prior semantic/transport/idle PASS.
            check_identity(o, go)
            reader.active_label = label
            result['stages'][label] = 'PREPARING'
            write(o, h, 'CLIENT.json', result)
            payload, _, codes = reader.fixture(key, target, 'H016-' + label + '-20260927', failed.is_set)
            payload['max_tokens'] = output
            exact, _ = reader.count(key, payload)
            require(exact == target and exact + output <= manifest['context'] - 1, 'exact_prompt_output_reserve')
            forecast = exact / 61 + output / 7.76 + 300
            require(time.time() + forecast < deadline, 'measured_completion_estimate_exceeds_cap')
            result['stages'][label] = 'RUNNING'
            result.update(status=label + '_RUNNING', request_may_be_active=True,
                          exact_input_tokens=exact, output_budget=output, actual_slot=manifest['context'],
                          admission_planning_seconds=forecast, final_count_seconds=reader.last_count_seconds)
            write(o, h, 'CLIENT.json', result)
            row = reader.request(h, key, payload, label, failed, manifest['context'], planning_seconds=forecast)
            reader.record_semantics(h, label, row, reader.fixture_correct(row, codes), 'long_fixture_semantics_failed')
            require(row.get('done') is True and row.get('full_http_drain') is True
                    and row.get('native_settlement', {}).get('status') == 'AUTHENTICATED_SLOT_IDLE_AFTER_FULL_DRAIN',
                    'long_terminal_and_idle_proof_required')
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
