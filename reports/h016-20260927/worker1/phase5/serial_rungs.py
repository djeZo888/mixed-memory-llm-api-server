#!/usr/bin/env python3
"""Root-authorized H016 serial 16K then conditional64K; existing R5 owns native."""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import signal
import sys
import threading
import time

BASE = '/data/build/H016-20260927/worker1-r5'
sys.path.insert(0, BASE)
import candidate_owner as owner
import benchmark
from verify_retained import dependency
from private_proxy import read_key

P = pathlib.Path
LOG = P(owner.LOG)
CID = 'c724b72b99f57f9e72b21bbc2a1fc104a9109b970657d5694ba05c25160a8308'
UNIT = 'h016-mimo-initial-20260927-r5.service'
INVOCATION = '4600b556d5d04305a9157da80149a511'
PINS = {'candidate_owner.py': '11041d78f05bb0522d48b293f0a4283629d4a15f787e8477be6591b4b7faa483', 'benchmark.py': 'ece4d5d801edc10505ae7d7e9e108a8d4a017e76ac436a220b050f0239e75803', 'telemetry.py': '2c0e7483845530cf9b669d699c67b574e0f4a8cbba21dd6c511bc7ddf7f817aa'}
COUNTERS = ['pgmajfault', 'pgscan', 'pgsteal', 'workingset_refault_file']

def kv(s):
    return {k: int(v) for k, v in (line.split() for line in s.splitlines())}

def samples():
    return [json.loads(s) for s in (LOG / 'TELEMETRY.jsonl').read_text().splitlines()]

def boundary():
    cg = P('/sys/fs/cgroup/system.slice/docker-' + CID + '.scope')
    return {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'cgroup': {n: (cg / n).read_text().strip() for n in ['memory.current', 'memory.peak', 'memory.stat', 'memory.events', 'memory.swap.current', 'cpu.stat', 'io.stat']}}

def main():
    h = dependency()
    failed = threading.Event()
    state = {'pid': os.getpid(), 'utc': h.now(), 'native_id': CID, 'native_pid': 2782009, 'body_sent': False, 'status': 'CHECKING', 'rungs': {}}
    def save():
        state['updated_utc'] = h.now()
        owner.save(h, 'SERIAL-RUNGS.json', state)
    def admit(prior):
        for name, sha in PINS.items():
            h.require(hashlib.sha256(P(BASE, name).read_bytes()).hexdigest() == sha, 'source_drift')
        unit = dict(x.split('=', 1) for x in owner.run_cmd(['systemctl', 'show', UNIT, '-p', 'MainPID,ActiveState,SubState,InvocationID']).splitlines())
        h.require(unit == {'MainPID': '2779569', 'ActiveState': 'active', 'SubState': 'running', 'InvocationID': INVOCATION}, 'owner_unit_changed')
        o = json.loads((LOG / 'OWNER.json').read_text())
        h.require(o['candidate_id'] == CID and o['native_pid'] == 2782009 and o['status'] == 'QUALIFIED_FIRST4K_WARM_AWAIT_ROOT_NEXT_STAGE' and not o.get('guard_failure'), 'owner_changed')
        c = owner.inspect(CID)
        h.require(c['State']['Running'] and c['State']['Pid'] == 2782009 and c['State']['StartedAt'] == '2026-09-27T12:37:37.213589148Z' and c['Image'] == owner.IMAGE, 'native_changed')
        row = json.loads((LOG / ('BENCH' + str(prior) + '.json')).read_text())
        h.require(row['status'] == 'TRANSPORT_COMPLETE' and row['correctness'] == 'PASS' and row['finish_reason'] == 'stop' and row['done'] and row['full_http_drain'], 'prior_not_pass')
        ts = samples(); t = ts[-1]
        age = time.time() - datetime.datetime.fromisoformat(t['utc']).timestamp()
        h.require(0 <= age <= 10, 'mandatory_guard_stale')
        h.require(t['host']['MemAvailable'] >= .15 * t['host']['MemTotal'], 'host_reserve')
        h.require(len(t['gpus']) == 4, 'gpu_missing')
        for g in t['gpus']:
            uid = g['uuid']; reserve = g['total_mib'] * (.07 if uid == owner.GPU else .05) if uid in [owner.GPU, 'GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23'] else 16384
            h.require(g['free_mib'] >= reserve and g['temp_c'] < t['temperature_limits_c'][uid], 'gpu_guard')
        ev = kv(t['cgroup']['memory.events'])
        h.require(int(t['cgroup']['memory.swap.current']) == 0 and ev['oom'] == ev['oom_kill'] == 0, 'swap_oom')
        interval = [x for x in ts if row['started_utc'] <= x['utc'] <= row['finished_utc']]
        h.require(len(interval) >= 2, 'missing_phase_samples')
        first, last = kv(interval[0]['cgroup']['memory.stat']), kv(t['cgroup']['memory.stat'])
        h.require(all(first[k] == last[k] for k in COUNTERS), 'fault_or_reclaim_growth_no_automatic_next_rung')
        status, slots = owner.get(30012, '/slots', key)
        h.require(status == 200 and isinstance(slots, list) and len(slots) == 1 and slots[0].get('is_processing') is False, 'native_slot_not_idle')
        h.require(time.time() < owner.ADMIT_END, 'admission_closed')
        return {'utc': h.now(), 'guard_utc': t['utc'], 'guard_age_seconds': age, 'prior': prior, 'phase_samples': len(interval), 'counters_constant': {k: last[k] for k in COUNTERS}, 'slot_idle': True}
    original_connection = benchmark.http.client.HTTPConnection
    class TrackedConnection(original_connection):
        def request(self, method, url, *args, **kwargs):
            result = super().request(method, url, *args, **kwargs)
            if method == 'POST' and url == '/v1/chat/completions':
                state.update(body_sent=True, body_sent_utc=h.now(), status='BODY_SENT')
                state['rungs'][str(state['target'])].update(body_sent=True, body_sent_utc=state['body_sent_utc'])
                save()
            return result
    def interrupted(*_):
        failed.set()
        raise TimeoutError('serial_stage_interrupted_no_retry')
    signal.signal(signal.SIGTERM, interrupted)
    try:
        key = read_key(h)
        with h.transaction() as guard, h.AnchoredRoot(str(LOG), guard) as log:
            for n in ['SERIAL-RUNGS.json', 'BENCH16384.json', 'BENCH65536.json']:
                h.require(log.stat(n, missing_ok=True) is None, 'prior_stage_exists_no_retry')
            log.atomic_json('SERIAL-RUNGS.json', state)
        benchmark.http.client.HTTPConnection = TrackedConnection
        for target, prior in [(16384, 4096), (65536, 16384)]:
            gate = admit(prior)
            if target == 65536:
                previous = json.loads((LOG / 'BENCH16384.json').read_text())
                nt = previous['native_timings']
                estimate = 4 * nt['prompt_ms'] / 1000 + nt['predicted_ms'] / 1000
                state['projection64k'] = {'prefill_scale': 4, 'actual_decode_seconds': nt['predicted_ms'] / 1000, 'estimated_seconds': estimate, 'estimated_finish_utc': datetime.datetime.fromtimestamp(time.time() + estimate, datetime.timezone.utc).isoformat(), 'planning_only': True}
                save()
                owner.save(h, 'ROOT-NOTICE-SERIAL.json', {'utc': h.now(), 'target': 16384, 'result': state['rungs']['16384']['result'], 'projection64k': state['projection64k'], 'next': 'CONDITIONAL_SINGLE64K'})
                cutoff = datetime.datetime(2026, 9, 27, 13, 30, tzinfo=datetime.timezone.utc).timestamp()
                if time.time() + estimate >= cutoff:
                    state['status'] = '16K_COMPLETE_64K_TIME_GATE_DECLINED'; save(); return 0
            state.update(target=target, body_sent=False, status='BUILDING_FRESH_FIXTURE')
            state['rungs'][str(target)] = {'admission': gate, 'body_sent': False}; save()
            payload, raw, codes = benchmark.fixture(key, target, 'root-go-' + str(target) + '-' + h.now())
            gate = admit(prior)
            if target == 65536:
                h.require(time.time() + estimate < cutoff, '64k_time_gate_after_fixture')
            h.require(payload['max_tokens'] == 256 and payload['chat_template_kwargs']['enable_thinking'] is False, 'fixed_parameters')
            state['rungs'][str(target)].update(admission=gate, before=boundary(), request_sha256=hashlib.sha256(raw).hexdigest())
            state['status'] = 'ADMITTED'; save()
            row = benchmark.request(h, key, payload, 'BENCH' + str(target), failed)
            after = boundary()
            row['correctness'] = 'PASS' if row['finish_reason'] == 'stop' and all(code in row['content'] for code in codes + ['323', '4095']) else 'FAIL_OR_TRUNCATED'
            owner.save(h, 'BENCH' + str(target) + '.json', row)
            state['rungs'][str(target)].update(after=after, result={k: v for k, v in row.items() if k not in ['content', 'reasoning_content', 'tool_calls', 'response_id']})
            state['status'] = str(target) + '_COMPLETE'; save()
            owner.save(h, 'ROOT-NOTICE-SERIAL.json', {'utc': h.now(), 'target': target, 'result': state['rungs'][str(target)]['result'], 'phase_boundaries': {'before': state['rungs'][str(target)]['before'], 'after': after}})
            h.require(row['correctness'] == 'PASS', 'rung_correctness_failed_no_retry')
        state['status'] = '16K_64K_COMPLETE'; save(); return 0
    except BaseException as exc:
        state.update(status='STOPPED_NO_RETRY', error_type=type(exc).__name__, error=str(exc) if isinstance(exc, (RuntimeError, TimeoutError)) else type(exc).__name__)
        save(); return 1
    finally:
        benchmark.http.client.HTTPConnection = original_connection

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if args.run:
        raise SystemExit(main())
