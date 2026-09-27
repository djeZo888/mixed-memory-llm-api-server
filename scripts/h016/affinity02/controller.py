#!/usr/bin/env python3
"""Fixed two-profile H016 controller. Independent systemd owner; no inference here."""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import signal
import subprocess
import sys
import time

P = pathlib.Path
BASE = P('/data/build/H016-20260927/worker1-affinity02')
LOG = P('/data/logs/H016-20260927/worker1-affinity02')
PROFILES = ('r10-spread02', 'r11-local02')
UNIT = 'h016-affinity02-20260927.service'
GLOBAL_END = '2026-09-27T17:48:08Z'
SUCCESS = 'PROFILE_BASELINE_COMPLETE_WARM_AWAIT_ROOT'
SETTLED = 'SETTLED_GLM_RESTORED'
STOP_REQUESTED = False
SETTLING = False


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def timestamp(value):
    parsed = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(parsed.tzinfo is not None, 'deadline_needs_timezone')
    return parsed.timestamp()


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def profile_base(profile):
    require(profile in PROFILES, 'unknown_profile')
    return BASE.parent / ('worker1-' + profile)


def profile_log(profile):
    require(profile in PROFILES, 'unknown_profile')
    return LOG.parent / ('worker1-' + profile)


def unit(profile):
    require(profile in PROFILES, 'unknown_profile')
    return 'h016-mimo-profile-20260927-' + profile + '.service'


def command(argv, timeout=15):
    return subprocess.check_output(argv, text=True, stderr=subprocess.PIPE, timeout=timeout)


def properties(name, timeout=15):
    return dict(line.split('=', 1) for line in command([
        'systemctl', 'show', name, '-p',
        'LoadState,MainPID,ControlPID,InvocationID,ActiveState,SubState,ControlGroup,ExecStart,ExecMainStartTimestamp'
    ], timeout=timeout).splitlines())


def source_path(name):
    parts = P(name).parts
    require(not P(name).is_absolute() and '..' not in parts, 'unsafe_source_name')
    if len(parts) == 1:
        return BASE / name
    require(len(parts) == 2 and parts[0] in PROFILES, 'unapproved_source_namespace')
    return profile_base(parts[0]) / parts[1]


def approved(now, admission=True):
    plan = json.loads((BASE / 'PLAN.json').read_text())
    go = json.loads((BASE / 'ROOT-AFFINITY02-GO.json').read_text())
    require(go.get('authorized') is True and go.get('profiles') == list(PROFILES), 'root_go_missing_or_wrong_profiles')
    for field in ('pair_cleanup_utc', 'pair_completion_utc', 'minimum_profile_budget_seconds'):
        require(plan[field] == go[field], 'root_plan_deadline_mismatch_' + field)
    cleanup, completion = timestamp(plan['pair_cleanup_utc']), timestamp(plan['pair_completion_utc'])
    require(cleanup + 450 <= completion <= timestamp(GLOBAL_END), 'invalid_settlement_deadlines')
    require(plan['minimum_profile_budget_seconds'] == 900, 'profile_budget_changed')
    if admission:
        require(now < timestamp(go['expires_utc']), 'root_go_expired')
        require(now + 900 <= cleanup, 'insufficient_first_profile_budget')
    hashes = go.get('source_sha256', {})
    require(json.loads((BASE / 'SOURCE-SHA256.json').read_text()) == hashes,
            'root_go_manifest_closure_mismatch')
    required = {'controller.py', 'PLAN.json'} | {
        profile + '/' + name for profile in PROFILES for name in
        ('candidate_owner.py', 'launch_profile.py', 'benchmark.py', 'verify_retained.py', 'telemetry.py')}
    require(required <= hashes.keys(), 'root_go_incomplete_source_closure')
    for name, digest in hashes.items():
        require(hashlib.sha256(source_path(name).read_bytes()).hexdigest() == digest, 'approved_source_drift_' + name)
    return plan, hashlib.sha256((BASE / 'ROOT-AFFINITY02-GO.json').read_bytes()).hexdigest()


def dependency():
    # Only the retained registered-storage adapter is loaded in this process.
    # Candidate-owner modules for the two profiles are isolated by --proof subprocesses.
    sys.path.insert(0, str(profile_base(PROFILES[0])))
    from verify_retained import dependency as retained_dependency
    return retained_dependency()


def save(h, state):
    state['updated_utc'] = utc()
    with h.MountedStorageGuard(h.s) as guard, h.AnchoredRoot(str(LOG), guard) as log:
        h.s.root_payload_guard()
        log.atomic_json('PAIR.json', state)
        h.s.root_payload_guard()


def read_owner(profile):
    path = profile_log(profile) / 'OWNER.json'
    return json.loads(path.read_text()) if path.exists() else None


def owner_ok(owner, settled=False):
    require(owner is not None, 'owner_receipt_missing')
    require(not owner.get('guard_failure'), 'profile_physical_guard_failure')
    allowed = ('owned_supervisor_interrupted',) if settled else ()
    require(not owner.get('error') or owner['error'] in allowed, 'profile_owner_failed')
    require(bool(owner.get('baseline_done_utc')), 'profile_baseline_not_complete')


def proof(profile):
    """Fresh authenticated proof after normal owner settlement; never inference."""
    sys.path.insert(0, str(profile_base(profile)))
    import candidate_owner as owner
    h = owner.dependency()
    state = read_owner(profile)
    props = properties(unit(profile))
    require(props.get('MainPID') == props.get('ControlPID') == '0', 'profile_unit_process_remains')
    require(props.get('ActiveState') in ('inactive', 'failed') or props.get('LoadState') == 'not-found', 'profile_unit_active')
    require(not P('/sys/fs/cgroup/system.slice', unit(profile)).exists(), 'profile_unit_cgroup_present')
    if state and state.get('candidate_id'):
        require(state.get('status') == SETTLED and not state.get('glm_suppressed'), 'owner_not_settled')
        require(all(state.get('native_settled', {}).get(k) is True for k in
                    ('pid_zero', 'cgroup_empty', 'gpu_compute_empty')), 'settlement_evidence_missing')
        candidate = owner.inspect(state['candidate_id'])
        require(candidate['Id'] == state['candidate_id'] and candidate['Image'] == owner.IMAGE and
                candidate['Name'] == '/' + owner.NAME and candidate['State']['Pid'] == 0 and
                not candidate['State']['Running'] and
                candidate['State']['StartedAt'] == state['native_started_at'], 'candidate_generation_or_settlement_changed')
        cg = P(state['native_cgroup'])
        require(not cg.exists() or not (cg / 'cgroup.procs').read_text().strip(), 'native_cgroup_not_empty')
        old_pid = state['native_pid']
        require(not P('/proc', str(old_pid)).exists(), 'old_native_pid_present')
        gpu_pids = owner.run_cmd(['nvidia-smi', '--id=' + owner.GPU,
                                 '--query-compute-apps=pid', '--format=csv,noheader,nounits'])
        require(str(old_pid) not in gpu_pids.split(), 'old_native_gpu_owner_remains')
    else:
        require(not owner.run_cmd(['docker', 'ps', '-aq', '--filter', 'name=^/' + owner.NAME + '$']).strip(),
                'unrecorded_candidate_requires_review')
        require(not state or not state.get('glm_suppressed'), 'unsettled_suppression')
    original = owner.inspect(owner.GLM_ID)
    glm = owner.load_glm(h)
    glm.validate_container(original, json.loads(P(owner.GLM_SOURCE).parent.joinpath('config.json').read_text()),
                           json.loads(P(owner.GLM_SOURCE).parent.joinpath('state.json').read_text()))
    require(original['State']['Running'], 'original_glm_not_running')
    key = owner.read_key(h)
    code, ready = owner.get(30010, '/v1/readiness', key)
    require(code == 200 and ready.get('ready') is True, 'original_glm_not_ready')
    code, info = owner.get(30010, '/get_server_info', key)
    require(code == 200 and info.get('context_length') == 1048576, 'original_glm_identity_changed')
    return {'utc': utc(), 'status': 'PHYSICAL_SETTLEMENT_ORIGINAL_GLM_READY',
            'profile': profile, 'unit': props, 'candidate_id': state.get('candidate_id') if state else None,
            'native_settled': state.get('native_settled') if state else None,
            'original_glm_id': owner.GLM_ID, 'original_glm_ready': True}


def settle_profile(h, state, profile):
    global SETTLING
    previous = SETTLING
    SETTLING = True
    try:
        return _settle_profile(h, state, profile)
    finally:
        SETTLING = previous


def _settle_profile(h, state, profile):
    entry = state['profiles'][profile]
    props = properties(unit(profile))
    if props.get('LoadState') != 'not-found':
        require(str(profile_base(profile) / 'candidate_owner.py') in props.get('ExecStart', ''), 'unit_owner_path_changed')
        expected = entry.get('invocation_id')
        require(not expected or props.get('InvocationID') == expected, 'profile_invocation_changed')
        if not expected:
            # Launch intent and initial absence were persisted before the only systemd submission.
            require(entry.get('launch_intent_utc') and entry.get('unit_absent_before_launch'), 'no_owned_launch_intent')
            entry['invocation_id'] = props.get('InvocationID')
        entry['normal_stop_requested_utc'] = utc()
        save(h, state)
        command(['systemctl', 'stop', '--no-block', unit(profile)])
    end = time.monotonic() + 420
    last = None
    while time.monotonic() < end:
        props = properties(unit(profile), timeout=min(15, max(.1, end - time.monotonic())))
        if props.get('MainPID') == props.get('ControlPID') == '0':
            try:
                raw = command(['/usr/bin/python3', '-B', str(BASE / 'controller.py'), '--proof', profile],
                              timeout=min(25, max(.1, end - time.monotonic())))
                entry['settlement'] = json.loads(raw)
                entry['status'] = 'SETTLED_ORIGINAL_GLM_READY'
                save(h, state)
                return
            except (subprocess.SubprocessError, ValueError) as exc:
                last = type(exc).__name__
        time.sleep(min(2, max(0, end - time.monotonic())))
    raise RuntimeError('normal_settlement_not_proven_' + str(last))


def wait_baseline(profile, cleanup):
    while time.time() < cleanup:
        owner = read_owner(profile)
        if owner:
            require(not owner.get('guard_failure') and not owner.get('error'), 'profile_failed_no_second_profile')
            if owner.get('status') == SUCCESS:
                owner_ok(owner)
                sample = json.loads((profile_log(profile) / 'BASELINE128.json').read_text())
                require(sample.get('done') is True and sample.get('full_http_drain') is True and
                        sample.get('status') == 'TRANSPORT_COMPLETE' and sample.get('expected_input_tokens') == 83,
                        'baseline_stream_not_complete')
                return {'candidate_id': owner['candidate_id'], 'native_pid': owner['native_pid'],
                        'native_started_at': owner['native_started_at'], 'baseline_done_utc': owner['baseline_done_utc'],
                        'baseline_sha256': hashlib.sha256((profile_log(profile) / 'BASELINE128.json').read_bytes()).hexdigest()}
            require(owner.get('status') != SETTLED, 'profile_settled_before_baseline')
        props = properties(unit(profile))
        require(props.get('ActiveState') in ('active', 'activating'), 'profile_owner_unit_stopped')
        time.sleep(2)
    raise RuntimeError('pair_cleanup_deadline')


def run_pair():
    plan, go_hash = approved(time.time())
    h = dependency()
    require(not (LOG / 'PAIR.json').exists(), 'pair_exists_no_replay')
    controller = properties(UNIT)
    require(controller.get('MainPID') == str(os.getpid()) and controller.get('InvocationID'), 'controller_not_independent_systemd_owner')
    state = {'status': 'ADMITTED', 'started_utc': utc(), 'pid': os.getpid(),
             'controller_unit': UNIT, 'controller_invocation_id': controller['InvocationID'],
             'root_go_sha256': go_hash, 'plan': plan, 'profiles': {}}
    save(h, state)
    current = None
    try:
        for profile in PROFILES:
            require(not STOP_REQUESTED, 'controller_stop_requested_no_next_profile')
            require(time.time() + plan['minimum_profile_budget_seconds'] <= timestamp(plan['pair_cleanup_utc']),
                    'insufficient_next_profile_budget')
            require(properties(unit(profile)).get('LoadState') == 'not-found', 'profile_unit_exists_no_replay')
            require(read_owner(profile) is None, 'profile_owner_exists_no_replay')
            current = profile
            state['current_profile'] = profile
            state['status'] = 'PROFILE_LAUNCHING'
            entry = {'status': 'LAUNCH_INTENT', 'launch_intent_utc': utc(), 'unit_absent_before_launch': True}
            state['profiles'][profile] = entry
            save(h, state)
            # No canonical lease or storage transaction surrounds the independent child launch.
            launched = json.loads(command(['/usr/bin/python3', '-B', str(profile_base(profile) / 'launch_profile.py'), '--run'], timeout=75))
            require(launched['status'] == 'SYSTEMD_DISPATCHED_READBACK_REQUIRED', 'launcher_did_not_dispatch')
            props = properties(unit(profile))
            require(props.get('MainPID', '0') != '0' and props.get('InvocationID') and
                    str(profile_base(profile) / 'candidate_owner.py') in props.get('ExecStart', ''), 'launch_owner_not_proven')
            entry.update(status='INDEPENDENT_OWNER_RUNNING', invocation_id=props['InvocationID'],
                         supervisor_pid=int(props['MainPID']), unit_readback=props, launch_receipt=launched)
            state['status'] = 'PROFILE_RUNNING'
            save(h, state)
            entry['baseline'] = wait_baseline(profile, timestamp(plan['pair_cleanup_utc']))
            save(h, state)
            settle_profile(h, state, profile)
            owner_ok(read_owner(profile), settled=True)
            current = None
        state['status'] = 'PAIR_COMPLETE_ORIGINAL_GLM_READY_AWAIT_ROOT_WINNER'
        state['completed_utc'] = utc()
        save(h, state)
        return 0
    except BaseException as exc:
        state.update(status='PAIR_FAILED_SETTLING_NO_REPLAY', error=str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__)
        save(h, state)
        raise
    finally:
        if current:
            settle_profile(h, state, current)
            state['status'] = 'PAIR_STOPPED_ORIGINAL_GLM_READY_NO_REPLAY'
            save(h, state)


def settle_pair():
    approved(time.time(), admission=False)
    h = dependency()
    path = LOG / 'PAIR.json'
    if not path.exists():
        return
    state = json.loads(path.read_text())
    current = state.get('current_profile')
    if current and current in state['profiles']:
        settle_profile(h, state, current)
    if state['status'] != 'PAIR_COMPLETE_ORIGINAL_GLM_READY_AWAIT_ROOT_WINNER':
        state['status'] = 'PAIR_STOPPED_ORIGINAL_GLM_READY_NO_REPLAY'
        save(h, state)


def interrupted(*_):
    global STOP_REQUESTED
    STOP_REQUESTED = True
    # Do not interrupt normal cleanup. The flag prevents admission of profile B.
    # systemd TimeoutStopSec remains the outer bound if cleanup itself stalls.
    if not SETTLING:
        raise RuntimeError('owned_pair_controller_interrupted')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--run', action='store_true')
    choice.add_argument('--settle', action='store_true')
    choice.add_argument('--proof', choices=PROFILES)
    choice.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.dry_run:
        plan, go_hash = approved(time.time())
        print(json.dumps({'status': 'APPROVED_BYTES_NO_DISPATCH', 'plan': plan, 'root_go_sha256': go_hash}))
    elif args.proof:
        print(json.dumps(proof(args.proof)))
    elif args.settle:
        signal.signal(signal.SIGTERM, interrupted)
        settle_pair()
    else:
        signal.signal(signal.SIGTERM, interrupted)
        raise SystemExit(run_pair())
