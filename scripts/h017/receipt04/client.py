#!/usr/bin/env python3
"""One independent H017 short text and authentic R9 full17 continuation job."""
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

BASE = Path('/data/build/H017-20260927/worker1-receipt04/short')
LOG = '/data/logs/H017-20260927/worker1-receipt04-short'
UNIT = 'h017-receipt04-short.service'
OWNER = Path('/data/services/mimo-h016-20260927/source/owner.py')
OWNER_SHA = 'dd9c10c75214fbbf8f1d5566618ac35bafa17f709ffc12ec3f84003dc9e30786'
TRANSPORT = Path('/data/build/H016-20260927/worker1-final13-long/client.py')
READER = TRANSPORT.with_name('reader.py')
R9 = Path('/data/build/H016-20260927/worker1-r9')


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def setup():
    import stat
    for path in (OWNER, *OWNER.parents):
        info = path.lstat()
        require(info.st_uid == 0 and not info.st_mode & 0o022 and not stat.S_ISLNK(info.st_mode), 'protected_owner_required')
    require(hashlib.sha256(OWNER.read_bytes()).hexdigest() == OWNER_SHA, 'owner_pin_changed')
    o = module('short_owner', OWNER)
    cfg = json.loads(o.protected(BASE / 'AUTHORITY.json'))
    require(cfg['authorized'] is True and cfg['purpose'] == 'H017_SHORT950000', 'short_authority_required')
    required = {str(Path(__file__).resolve()), str(OWNER), str(TRANSPORT), str(READER)}
    required |= {str(R9 / x) for x in ('candidate_owner.py', 'telemetry.py', 'verify_retained.py', 'private_proxy.py')}
    require(required <= cfg['source_sha256'].keys(), 'short_source_closure_required')
    for path, pin in cfg['source_sha256'].items():
        require(hashlib.sha256(o.protected(path)).hexdigest() == pin, 'short_source_pin_changed')
    c = module('short_transport', TRANSPORT)
    c.LOG, c.BASE, c.UNIT = LOG, BASE, UNIT
    return o, o.setup(), c, cfg


def settle():
    o, h, c, cfg = setup()
    try:
        result = o.read(Path(LOG) / 'CLIENT.json')
    except FileNotFoundError:
        return
    if not result.get('request_may_be_active'):
        return
    state = o.read(o.BASE / 'state.json')
    require(all(state.get(k) == v for k, v in cfg['production_identity'].items()), 'settlement_owner_changed')
    if state.get('status') == 'SETTLED':
        return
    unit = dict(x.split('=', 1) for x in o.run(['systemctl', 'show', o.UNIT, '-p', 'MainPID,InvocationID'], 2).splitlines())
    require(unit['InvocationID'] == state['supervisor']['invocation_id'] and int(unit['MainPID']) == state['supervisor']['pid'], 'settlement_supervisor_changed')
    o.run(['systemctl', 'stop', o.UNIT], 55)
    final = o.read(o.BASE / 'state.json')
    require(final.get('status') == 'SETTLED' and final.get('settlement') ==
            {'pid_released': True, 'cgroup_empty': True, 'gpu_compute_empty': True}, 'exact_settlement_unproven')


def run():
    o, h, c, cfg = setup()
    require(time.time() < cfg['admit_before_epoch'], 'short_admission_closed')
    require(cfg['active_cap_seconds'] == 900, 'short_exact_runtime_required')
    deadline = min(time.time() + 900, cfg['hard_end_epoch'])
    require(time.time() + 600 < deadline, 'short_completion_budget_required')
    manifest, state, guard = c.check_identity(o, cfg)
    o.source_preflight(h, manifest)
    require(manifest['context'] == 950000, 'actual950000_manifest_required')
    own = dict(x.split('=', 1) for x in o.run(['systemctl', 'show', UNIT, '-p', 'MainPID,InvocationID,ActiveState,ControlGroup'], 2).splitlines())
    require(int(own['MainPID']) == os.getpid() and own['InvocationID'] == os.environ.get('INVOCATION_ID')
            and own['ActiveState'] in ('active', 'activating')
            and Path('/proc/self/cgroup').read_text().split('::', 1)[1].strip() == own['ControlGroup'], 'independent_systemd_required')
    require(not Path(LOG, 'CLIENT.json').exists(), 'one_attempt_no_replay')
    sys.path.insert(0, str(R9))
    reader = module('short_reader', READER)
    result = {'status': 'PREPARING', 'started_utc': reader.utc_now(), 'production_identity': cfg['production_identity'],
              'request_may_be_active': False, 'deadline_epoch': deadline, 'completed': []}
    def save():
        c.write(o, h, 'CLIENT.json', result)
    def busy(evidence):
        result.update(status='BUSY_NOT_SUBMITTED', request_may_be_active=False, owned_disposition=evidence)
        save()
    def drained(row):
        require(row.get('done') is True and row.get('full_http_drain') is True, 'owned_completion_required')
        result.update(request_may_be_active=False, owned_disposition=row['owned_stream_disposition'])
        save()
    c.adapter(reader, o, h, deadline, on_local_busy=busy)
    connection = reader.http.client.HTTPConnection
    class ShortConnection(connection):
        def request(self, method, url, *args, **kwargs):
            if method == 'POST' and url == '/v1/chat/completions':
                result.update(status=reader.active_label + '_RUNNING', request_may_be_active=True)
                save()  # Persist possible submission before network transmission.
            return super().request(method, url, *args, **kwargs)
    reader.http.client.HTTPConnection = ShortConnection
    key = o.read_key(h)
    require(o.native_ready(manifest, key) is True, 'ordinary_native_not_ready')
    code, slots = reader.get(30012, '/slots', key)
    require(code == 200 and len(slots) == 1 and slots[0].get('n_ctx') == 950000 and slots[0].get('is_processing') is False, 'private950000_idle_required')
    code, props = reader.get(30012, '/props', key)
    require(code == 200 and props['default_generation_settings']['n_ctx'] == 950000, 'private_props950000_required')
    # Canonical node read is separate from the inference transport and uses its protected key.
    import http.client
    conn = http.client.HTTPConnection('127.0.0.1', 30008, timeout=4)
    try:
        conn.request('GET', '/control/v1/node/status', headers={'Authorization': 'Bearer ' + o.protected('/etc/llm-server/control-api-key').strip().decode()})
        response = conn.getresponse(); raw = response.read(2097153)
        require(response.status == 200 and len(raw) <= 2097152, 'node_read_failed')
        node = json.loads(raw)
    finally:
        conn.close()
    rows = [r for r in node['services'] if r['service_id'] == o.MODEL]
    require(len(rows) == 1 and rows[0]['ready'] is True and rows[0]['freshness'] == 'fresh'
            and rows[0]['hardware_latched'] is False and node['node_manager']['actions'] == [], 'canonical_node_not_ready_unlatched')
    save()
    c.write(o, h, 'ALLOCATION.json', {'status': 'PASS', 'utc': reader.utc_now(), 'actual_usable_context': 950000,
            'props': props, 'slots': slots, 'guard': guard, 'node': rows[0], 'production_identity': cfg['production_identity'],
            'scope': 'Current ordinary allocation and ready private API only; no occupied950000 claim.'})
    class Guard:
        def is_set(self):
            require(time.time() < deadline, 'short_active_deadline')
            return False
    failed = Guard()
    def alarm(*_):
        failed.is_set()
        _, _, current = c.check_identity(o, cfg, allow_active=True)
        c.write(o, h, 'GUARD-PROGRESS.json', current)
    def interrupted(*_):
        raise RuntimeError('short_client_interrupted')
    def phase(hh, kk, payload, label, ff, ss, planning_seconds, **kwargs):
        c.check_identity(o, cfg)
        reader.active_label = label
        row = reader.request(hh, kk, payload, label, ff, 950000, planning_seconds,
                             on_owned_stream_drained=drained)
        require(row['expected_input_tokens'] == row['usage']['prompt_tokens'], 'count_usage_mismatch')
        for _ in range(25):
            if o.read(o.BASE / 'proxy-state.json').get('active_requests') == 0:
                break
            time.sleep(.2)
        _, _, after = c.check_identity(o, cfg)
        reader.save(hh, label + '-GUARD-AFTER.json', after)
        result['completed'].append(label);save()
        return row
    reader.phase_request = phase
    signal.signal(signal.SIGTERM, interrupted);signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGALRM, alarm);signal.setitimer(signal.ITIMER_REAL, 5, 5)
    try:
        tiny = reader.body('Reply with exactly READY.', thinking=False, output=32)
        text = phase(h, key, tiny, 'SHORT-TEXT', failed, state, 30)
        reader.record_semantics(h, 'SHORT-TEXT', text, text['finish_reason'] == 'stop'
                                and not text['tool_calls'] and text['content'].strip() == 'READY', 'short_text_incorrect')
        reader.production_pair(h, key, failed, {'context': 950000, 'allocated_context': 950000, 'threads': 8}, [])
        result.update(status='PASS_KEEP_WARM', finished_utc=reader.utc_now())
        save()
    except c.LocalBusyNotSubmitted:
        pass
    except BaseException as exc:
        result.update(status='FAILED_NO_RETRY', error_type=type(exc).__name__, finished_utc=reader.utc_now())
        save()
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('run', 'settle'))
    args = parser.parse_args()
    try:
        run() if args.action == 'run' else settle()
    except BaseException as exc:
        print(json.dumps({'status': 'REFUSED_OR_FAILED', 'error_type': type(exc).__name__}), flush=True)
        return 1
    print(json.dumps({'status': 'COMPLETE', 'action': args.action}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
