#!/usr/bin/env python3
"""Fixed H016 candidate load/guard/settlement. Run only after direct root GO."""
import argparse
import datetime
import hashlib
import http.client
import importlib.util
import json
import os
import pathlib
import signal
import subprocess
import sys
import threading
import time
from verify_retained import dependency, LOG
from private_proxy import read_key

P = pathlib.Path
BASE = '/data/build/H016-20260927/worker1-r12-spread4'
NAME = 'llm-h016-mimo-pro-r12-spread4'
GPU = 'GPU-69acfa26-8b60-61b5-702d-aee252c163cc'
IMAGE = 'sha256:cdb6efd75f53a8b453f866f30511b0f5c8d19440d3adaaf419e97bde1c2bf21e'
GLM_ID = '2b5e5e386f70678cefebbfcb66cfdab568e9b3744abfb366f03a66ea7fdb03ab'
GLM_SOURCE = '/data/services/flash-h008-20260926/source'
GLM_OWNER_SHA = 'd4a628876b8643a01277039ab744e87a2218e3b87e2c6207e2d67816b570a4b1'
SERVICE = 'llm-frontier-flash.service'
CONFIG = json.loads(P(__file__).with_name('LAUNCH.json').read_text())
ADMIT_END = datetime.datetime.fromisoformat(CONFIG['admission_end_utc'].replace('Z','+00:00')).timestamp()
CLIENT_END = datetime.datetime.fromisoformat(CONFIG['client_end_utc'].replace('Z','+00:00')).timestamp()
HARD_END = datetime.datetime.fromisoformat(CONFIG['request_end_utc'].replace('Z','+00:00')).timestamp()
PRESERVED = ['llmctl-qwen38-27b-q0-480000-yarn4-bf16kv', 'llmctl-qwen38-27b-q1-server-480000-yarn4-bf16kv', 'llm-image-backend']


def run_cmd(argv, timeout=30):
    return subprocess.check_output(argv, text=True, stderr=subprocess.PIPE, timeout=timeout)


def inspect(name):
    return json.loads(run_cmd(['docker', 'inspect', name]))[0]


def memory():
    return {x.split(':')[0]: int(x.split()[1]) * 1024 for x in P('/proc/meminfo').read_text().splitlines()}


def cgpath(pid):
    return P('/sys/fs/cgroup' + P('/proc', str(pid), 'cgroup').read_text().split('::')[1].strip())


def gpu_rows(timeout=8):
    rows = []
    raw = run_cmd(['nvidia-smi', '--query-gpu=uuid,memory.total,memory.used,memory.free,temperature.gpu,utilization.gpu,power.draw', '--format=csv,noheader,nounits'], timeout)
    for line in raw.splitlines():
        values = [x.strip() for x in line.split(',')]
        rows.append(dict(zip(['uuid', 'total_mib', 'used_mib', 'free_mib', 'temp_c', 'util_pct', 'board_w'], [values[0]] + [float(x) for x in values[1:]])))
    return rows


def get(port, path, key):
    c = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        c.request('GET', path, headers={'Authorization': 'Bearer ' + key.decode()})
        r = c.getresponse()
        b = r.read(2 * 1024 * 1024)
        return r.status, json.loads(b)
    finally:
        c.close()


def save(h, name, value):
    with h.transaction() as g, h.AnchoredRoot(LOG, g) as a:
        a.atomic_json(name, value)


def load_glm(h):
    h.require(hashlib.sha256(P(GLM_SOURCE, 'owner.py').read_bytes()).hexdigest() == GLM_OWNER_SHA, 'glm_owner_drift')
    spec = importlib.util.spec_from_file_location('glm_owner', P(GLM_SOURCE, 'owner.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def require_r9_settled(h):
    """Exact R9 predecessor proof; never stop, extend, hotpatch or adopt R9."""
    old_log = P('/data/logs/H016-20260927/worker1-r9')
    old = json.loads((old_log / 'OWNER.json').read_text())
    cid = 'e281df9fb64d87e32668cc4da2e368d41c2a48fe0b3d7b8d4923615a84d3807e'
    h.require(old['candidate_id'] == cid and old['native_pid'] == 2391866 and
              old['pid'] == 2388016 and
              old['native_started_at'] == '2026-09-27T16:45:17.969315454Z', 'r9_identity_changed')
    h.require(old['status'] == 'SETTLED_GLM_RESTORED' and not old['glm_suppressed'] and
              old.get('glm_restored_utc') and all(old['native_settled'][k] is True
              for k in ['pid_zero', 'cgroup_empty', 'gpu_compute_empty']), 'r9_not_normally_settled')
    c = inspect(cid)
    h.require(c['Id'] == cid and c['Image'] == IMAGE and c['Name'] == '/llm-h016-mimo-pro-r9' and
              not c['State']['Running'] and c['State']['Pid'] == 0 and
              c['State']['StartedAt'] == old['native_started_at'], 'r9_native_not_settled')
    unit = 'h016-mimo-final-20260927-r9.service'
    props = dict(x.split('=', 1) for x in run_cmd(['systemctl', 'show', unit, '-p',
                     'MainPID,ControlPID,ActiveState,InvocationID']).splitlines())
    h.require(props.get('InvocationID') == 'f7d09bc5011543f99d321e1bdd4e5adb', 'r9_invocation_changed')
    h.require(props.get('MainPID') == props.get('ControlPID') == '0' and
              props.get('ActiveState') in ['inactive', 'failed'], 'r9_owner_active')
    h.require(not P('/sys/fs/cgroup/system.slice', unit).exists(), 'r9_unit_cgroup_present')
    cg = P(old['native_cgroup'])
    h.require(not cg.exists() or not (cg / 'cgroup.procs').read_text().strip(), 'r9_native_cgroup_not_empty')
    h.require(not P('/proc/2391866').exists() and not P('/proc/2388016').exists(), 'r9_process_present')
    h.require(not old.get('proxy_pid') or not P('/proc', str(old['proxy_pid'])).exists(), 'r9_proxy_present')
    gpu_pids = run_cmd(['nvidia-smi', '--id=' + GPU, '--query-compute-apps=pid', '--format=csv,noheader,nounits'])
    h.require('2391866' not in gpu_pids.split(), 'r9_gpu_compute_owner_remains')
    # GLM now legitimately occupies frontier memory; prior empty-GPU settlement
    # plus absent exact R9 PID proves retirement without demanding GLM be stopped.
    key = read_key(h)
    code, ready = get(30010, '/v1/readiness', key)
    h.require(code == 200 and ready.get('ready') is True, 'r9_original_glm_not_ready')
    old_rows = {row['container']: row for row in old['proof']['native_idle']}
    preserved = []
    for name in PRESERVED:
        current = inspect(name)
        row = old_rows.get(current['Id'])
        h.require(current['State']['Running'] and row is not None and
                  current['State']['StartedAt'] == row['started_at'], 'r9_preserved_model_changed')
        preserved.append({'name': name, 'container': current['Id'], 'started_at': current['State']['StartedAt']})
    return {'utc': h.now(), 'status': 'EXACT_R9_SETTLED_GLM_READY_PRESERVED3_UNCHANGED',
            'owner_sha256': hashlib.sha256((old_log / 'OWNER.json').read_bytes()).hexdigest(),
            'candidate_id': cid, 'native_settled': old['native_settled'], 'unit': props,
            'original_glm_ready': True, 'preserved': preserved}


def capture_native_log(h, state, label):
    """Retain every emitted log line privately; never filter backend selection."""
    if not state.get('candidate_id'):
        return
    result = subprocess.run(['docker', 'logs', '--timestamps', state['candidate_id']],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15)
    raw = result.stdout
    h.require(result.returncode == 0, 'native_log_capture_failed')
    save(h, label + '.json', {'utc': h.now(), 'container_id': state['candidate_id'],
         'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
         'unfiltered': True, 'text': raw.decode('utf-8', errors='replace')})


def preflight(h):
    predecessor = require_r9_settled(h)
    from authority import validate
    validate(BASE)
    with h.transaction() as g, h.AnchoredRoot(BASE, g) as a:
        hashes = json.loads(P(BASE, 'SOURCE-SHA256.json').read_text())
        for name, digest in hashes.items():
            h.require('/' not in name, 'source_name')
            a.check(name)
            h.require(hashlib.sha256(P(BASE, name).read_bytes()).hexdigest() == digest, 'candidate_source_drift')
        h.require(hashes.get('numactl') == 'f3944bcd7848d64424f8daf27f350b03d7f3281b2fb9be5eaaba0ddd0e72efb8' and hashes.get('libnuma.so.1.0.0') == '02d7582c5d391e460e56aa67a414360e3183b968206645b9123f9dc7bff5d009', 'interleave_dependency_pins')
        cfg = json.loads(P(BASE, 'LAUNCH.json').read_text())
        q = json.loads(P(BASE, 'HARNESS-QUIET-01.json').read_text())
        h.require(q['status'] == 'QUIET_APP_STOPPED_SEARCH_STATUS_ADMIN_PRESERVED' and q['after_units']['ai-harness.service']['MainPID'] == '0' and q['after_data']['frontier_requests']['count'] == 0, 'upper_owner_not_quiet')
        verified = json.loads(P('/data/logs/H016-20260927/worker1', 'VERIFICATION-STATUS.json').read_text())
        h.require(verified['status'] == 'VERIFIED_AND_INVENTORIED' and verified['verified_shards'] == 13, 'weights_unverified')
        h.require(P('/proc/sys/kernel/random/boot_id').read_text().strip() == h.BOOT, 'boot_changed')
        h.require(inspect(IMAGE)['Id'] == IMAGE, 'image_identity')
        h.require(not run_cmd(['docker', 'ps', '-aq', '--filter', 'name=^/' + NAME + '$']).strip(), 'candidate_exists_inspect_before_resume')
        h.require(not P(LOG, 'OWNER.json').exists(), 'prior_owner_exists_no_replay')
        h.require(not run_cmd(['ss', '-ltnH', 'sport = :30012']).strip(), 'candidate_port_busy')
        for name in PRESERVED:
            h.require(inspect(name)['State']['Running'], 'preserved_model_not_running')
        glm = load_glm(h)
        original = inspect(GLM_ID)
        glm.validate_container(original, json.loads(P(GLM_SOURCE).parent.joinpath('config.json').read_text()), json.loads(P(GLM_SOURCE).parent.joinpath('state.json').read_text()))
        h.require(original['State']['Running'], 'glm_not_running')
        # Pinned scheduler blocks on poll only after its explicit native queues are empty.
        # Coupled with stopped upper owner, two stable scheduler CPU/poll observations.
        rows = []
        for name in [GLM_ID] + PRESERVED:
            c = inspect(name)
            cg = cgpath(c['State']['Pid'])
            sched = []
            for pid in (cg / 'cgroup.procs').read_text().split():
                comm = P('/proc', pid, 'comm').read_text().strip()
                if comm.startswith(('sglang::schedul', 'sgl_diffusion::')):
                    w = P('/proc', pid, 'wchan').read_text().strip()
                    h.require('poll' in w, 'native_scheduler_not_waiting')
                    sched.append({'pid': int(pid), 'wchan': w, 'stat': P('/proc', pid, 'stat').read_text()})
            h.require(len(sched) == 1, 'native_scheduler_identity_ambiguous')
            rows.append({'container': c['Id'], 'started_at': c['State']['StartedAt'], 'scheduler': sched[0]})
        time.sleep(1)
        for row in rows:
            pid = row['scheduler']['pid']
            old = row['scheduler']['stat'].rsplit(')', 1)[1].split()
            new = P('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
            row['scheduler']['cpu_ticks_before_after'] = [old[11:13], new[11:13]]
            h.require('poll' in P('/proc', str(pid), 'wchan').read_text(), 'native_scheduler_not_waiting')
        key = read_key(h)
        for port in [30002, 30004, 30010]:
            status, info = get(port, '/get_server_info', key)
            h.require(status == 200 and info.get('context_length') == (1048576 if port == 30010 else 480000), 'preserved_native_identity')
        h.require(all(x['util_pct'] == 0 for x in gpu_rows()), 'native_gpu_busy')
        return cfg, {'utc': h.now(), 'predecessor': predecessor, 'native_idle': rows, 'quiet_receipt_sha256': hashes['HARNESS-QUIET-01.json'], 'sources': hashes}


# /etc contains the installed regular unit, so conventional /run/systemd/system
# runtime masking would be shadowed. This higher-priority *runtime* control path
# is in systemd-analyze unit-paths; original /etc unit/enabled symlink stay intact.
SUPPRESSION = P('/run/systemd/system.control/llm-frontier-flash.service')


def suppress(enable):
    import stat
    if enable:
        SUPPRESSION.parent.mkdir(mode=0o755, exist_ok=True)
        for parent in [SUPPRESSION.parent, *SUPPRESSION.parent.parents]:
            st = parent.lstat()
            if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
                raise RuntimeError('suppression_ancestry')
        os.symlink('/dev/null', SUPPRESSION)  # Exclusive: never replace an existing owner.
    elif SUPPRESSION.is_symlink():
        if os.readlink(SUPPRESSION) != '/dev/null':
            raise RuntimeError('suppression_changed')
        SUPPRESSION.unlink()
    elif SUPPRESSION.exists():
        raise RuntimeError('suppression_not_owned_link')
    run_cmd(['systemctl', 'daemon-reload'])
    load_state = run_cmd(['systemctl', 'show', SERVICE, '-p', 'LoadState', '--value']).strip()
    if enable and load_state != 'masked':
        raise RuntimeError('runtime_mask_not_effective')
    if not enable and load_state != 'loaded':
        raise RuntimeError('original_service_not_loaded')


def settle(h):
    state_path = P(LOG, 'OWNER.json')
    if not state_path.exists():
        return
    state = json.loads(state_path.read_text())
    cid = state.get('candidate_id')
    if cid:
        c = inspect(cid)
        h.require(c['Id'] == cid and c['Image'] == IMAGE and c['Name'] == '/' + NAME and c['Config']['Labels'].get('io.h016.owner') == 'H016-20260927', 'candidate_settlement_identity')
        h.require(not state.get('native_started_at') or c['State']['StartedAt'] == state['native_started_at'], 'candidate_generation_changed')
        old_pid = c['State']['Pid']
        cg = cgpath(old_pid) if old_pid else None
        with h.transaction():
            if c['State']['Running']:
                run_cmd(['docker', 'stop', '--time', '3' if state.get('guard_failure') else '20', cid], 10 if state.get('guard_failure') else 35)
        c = inspect(cid)
        h.require(not c['State']['Running'] and c['State']['Pid'] == 0, 'candidate_not_stopped')
        h.require(cg is None or not cg.exists() or not (cg / 'cgroup.procs').read_text().strip(), 'candidate_cgroup_not_empty')
        pids = run_cmd(['nvidia-smi', '--id=' + GPU, '--query-compute-apps=pid', '--format=csv,noheader,nounits'])
        h.require(not pids.strip(), 'frontier_compute_owner_remains')
        state['native_settled'] = {'utc': h.now(), 'pid_zero': True, 'cgroup_empty': True, 'gpu_compute_empty': True}
        save(h, 'OWNER.json', state)
    if state.get('glm_suppressed'):
        # Runtime mask only: original enabled symlink and desired-running state preserved.
        suppress(False)
        run_cmd(['systemctl', 'start', SERVICE], 190)
        key = read_key(h)
        end = min(time.time() + 300, HARD_END + 420)
        while time.time() < end:
            try:
                status, value = get(30010, '/v1/readiness', key)
                if status == 200 and value.get('ready') is True:
                    break
            except (OSError, http.client.HTTPException, ValueError):
                pass  # Normal asynchronous startup may not yet bind the socket.
            time.sleep(2)
        else:
            raise RuntimeError('glm_restore_readiness_failed')
        h.require(inspect(GLM_ID)['State']['Running'], 'original_glm_not_restored')
        state.update(glm_suppressed=False, glm_restored_utc=h.now(), status='SETTLED_GLM_RESTORED')
        save(h, 'OWNER.json', state)


def cleanup_proxy_and_settle(h, proxy):
    try:
        if proxy and proxy.poll() is None:
            proxy.terminate()
            try:
                proxy.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proxy.kill()
                proxy.wait(timeout=3)
    finally:
        settle(h)


def interrupted(*_):
    raise RuntimeError('owned_supervisor_interrupted')


def main(run=False):
    h = dependency()
    cfg, proof = preflight(h)
    if not run:
        print(json.dumps({'status': 'PREFLIGHT_ONLY_NO_MUTATION', 'proof': proof, 'native_argv': cfg['native_argv']}))
        return
    key = read_key(h)
    state = {'status': 'ADMITTED', 'started_utc': h.now(), 'pid': os.getpid(), 'proof': proof, 'glm_suppressed': False}
    save(h, 'OWNER.json', state)
    failed = threading.Event()
    proxy = None
    exit_code = 1
    try:
        # No lease held around systemctl: ExecStop borrows its own canonical owner transaction.
        state['glm_suppressed'] = True
        save(h, 'OWNER.json', state)
        suppress(True)
        old_pid = inspect(GLM_ID)['State']['Pid']
        old_cgroup = cgpath(old_pid)
        # Masked reload can remove ExecStop; invoke the exact validated owner explicitly.
        load_glm(h).operate('halt')
        run_cmd(['systemctl', 'stop', SERVICE], 70)
        h.require(not P('/proc', str(old_pid)).exists(), 'old_glm_pid_present')
        h.require(not old_cgroup.exists() or not (old_cgroup / 'cgroup.procs').read_text().strip(), 'old_glm_cgroup_not_empty')
        old = inspect(GLM_ID)
        h.require(not old['State']['Running'] and old['State']['Pid'] == 0, 'old_glm_not_settled')
        h.require(not run_cmd(['nvidia-smi', '--id=' + GPU, '--query-compute-apps=pid', '--format=csv,noheader,nounits']).strip(), 'old_frontier_compute_remains')
        frontier = next(x for x in gpu_rows() if x['uuid'] == GPU)
        h.require(frontier['free_mib'] >= frontier['total_mib'] * .93 and frontier['temp_c'] < 85, 'frontier_start_reserve_or_temperature')
        mem = memory()
        limit = int((mem['MemAvailable'] - .15 * mem['MemTotal'] - 16 * 1024**3) // 1024**3) * 1024**3
        h.require(limit >= 704 * 1024**3, 'candidate_host_budget_insufficient_for_fixed_704gib')
        limit = 704 * 1024**3
        state.update(post_glm_baseline={k: mem[k] for k in ['MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree']}, memory_limit_bytes=limit, old_glm_settled_utc=h.now())
        argv = ['docker', 'create', '--name', NAME, '--network', 'host', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--security-opt', 'seccomp=' + GLM_SOURCE + '/numa-seccomp.json', '--log-driver', 'local', '--log-opt', 'max-size=64m', '--log-opt', 'max-file=2', '--restart', 'no', '--cpuset-cpus', '0-7,16-71', '--cpuset-mems', '0-7', '--memory', str(limit), '--memory-swap', str(limit), '--gpus', 'device=' + GPU, '--label', 'io.h016.owner=H016-20260927', '--mount', 'type=bind,src=' + h.MODEL + ',dst=/models,readonly', '--mount', 'type=bind,src=/data/services/secrets/llm-api-key,dst=/run/secrets/llm-api-key,readonly', '--tmpfs', '/tmp:rw,noexec,nosuid,size=1g', '--env', 'CUDA_CACHE_DISABLE=1', '--env', 'OMP_NUM_THREADS=1', '--env', 'GOMP_SPINCOUNT=0', '--mount', 'type=bind,src=' + BASE + '/numactl,dst=/usr/bin/numactl,readonly', '--mount', 'type=bind,src=' + BASE + '/libnuma.so.1.0.0,dst=/usr/lib/x86_64-linux-gnu/libnuma.so.1,readonly', '--entrypoint', '/usr/bin/numactl', IMAGE, '--interleave=0-7', '/opt/llama/llama-server'] + cfg['native_argv']
        with h.acquire_lease(blocking=False) as lease, h.MountedStorageGuard(h.s) as g:
            h.s.root_payload_guard()
            from lifecycle.storage_binding import RegisteredStorageBinding
            from lifecycle.manager import StorageRunner
            from lifecycle.hardware_policy import HardwarePolicy, RegisteredLatchStore
            from control.node_collectors import boot_identity
            binding = RegisteredStorageBinding.read_registered(StorageRunner())
            def boot():
                b = boot_identity()
                return {'boot_id': b['boot_id'], 'uptime_seconds': b['boot_age_seconds']}
            HardwarePolicy(RegisteredLatchStore(binding, lease=lease), lease=lease, run=lambda a, timeout=2: run_cmd(a, timeout), boot=boot).require_start([GPU])
            for path in [h.MODEL, '/data/docker', '/data/containerd', GLM_SOURCE]:
                g.check_path(path)
            state['candidate_id'] = run_cmd(argv).strip()
            # Record exact owner before start, permitting ExecStopPost recovery after interruption.
            with h.AnchoredRoot(LOG, g) as log:
                log.atomic_json('OWNER.json', state)
            run_cmd(['docker', 'start', state['candidate_id']])
            h.s.root_payload_guard()
        c = inspect(state['candidate_id'])
        state.update(native_pid=c['State']['Pid'], native_started_at=c['State']['StartedAt'], status='LOADING', native_cgroup=str(cgpath(c['State']['Pid'])))
        save(h, 'OWNER.json', state)
        from telemetry import monitor
        watcher = threading.Thread(target=monitor, args=(h, state, failed), daemon=True)
        watcher.start()
        load_end = min(time.time() + 1200, ADMIT_END)
        while time.time() < load_end and not failed.is_set():
            h.require(inspect(state['candidate_id'])['State']['Running'], 'native_exited_loading')
            try:
                code, props = get(30012, '/props', key)
                if code == 200 and props.get('model_alias') == 'mimo-v2.6-pro-rl' and props.get('is_sleeping') is False:
                    break
            except (OSError, ValueError):
                pass
            time.sleep(5)
        else:
            raise RuntimeError('load_guard_or_deadline')
        from native_identity import compact_identity, validate_identity
        observed = {'utc': h.now(), 'owner_id': state['candidate_id'], 'pid': state['native_pid'], **compact_identity(props)}
        # Persist only identity fields, before every individually diagnosed assertion.
        save(h, 'NATIVE-OBSERVED.json', observed)
        validate_identity(observed)
        save(h, 'NATIVE-IDENTITY.json', observed)
        capture_native_log(h, state, 'NATIVE-STARTUP-FULL')
        from telemetry import bounded_placement
        save(h, 'POST-LOAD-PLACEMENT.json', bounded_placement(state['native_pid']))
        proxy = subprocess.Popen(['/usr/bin/python3', '-B', BASE + '/private_proxy.py'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        state.update(proxy_pid=proxy.pid, status='NATIVE_UP_ACCEPTANCE_RUNNING')
        save(h, 'OWNER.json', state)
        from benchmark import qualify
        qualify(h, key, failed)
        h.require(not failed.is_set() and proxy.poll() is None, 'guard_or_proxy_failed')
        state.update(status='PROFILE_BASELINE_COMPLETE_WARM_AWAIT_ROOT', baseline_done_utc=h.now())
        save(h, 'OWNER.json', state)
        # Independent guard retains warm owner for serial follow-up/W2; no paid CLI wait.
        while time.time() < HARD_END:
            h.require(not failed.is_set() and proxy.poll() is None and inspect(state['candidate_id'])['State']['Running'], 'warm_owner_guard_failed')
            time.sleep(5)
        # No persistent adoption in initial packet: bounded deadline always settles.
        # Later adoption code must be separately reviewed before any W2 activation.
        state['status'] = 'DEADLINE_SETTLING_UNADOPTED_CANDIDATE'
        save(h, 'OWNER.json', state)
    except BaseException as exc:
        state.update(status='FAILED_SETTLING', error_type=type(exc).__name__, error=str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__)
        save(h, 'OWNER.json', state)
    finally:
        failed.set()
        try:
            cleanup_proxy_and_settle(h, proxy)
        finally:
            capture_native_log(h, state, 'NATIVE-FINAL-FULL')
    return exit_code


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--settle', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.settle:
        h = dependency()
        settle(h)
    else:
        signal.signal(signal.SIGTERM, interrupted)
        raise SystemExit(main(run=args.run and not args.dry_run) or 0)
