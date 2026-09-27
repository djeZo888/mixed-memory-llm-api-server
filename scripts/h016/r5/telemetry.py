"""Five-second H016 owner telemetry; independent of streaming readers."""
import collections
import json
import os
import pathlib
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from candidate_owner import gpu_rows, memory, run_cmd, LOG, GPU
P = pathlib.Path


def placement(pid):
    base = P('/proc', str(pid))
    nodes = collections.Counter()
    anonymous = collections.Counter()
    policies = collections.Counter()
    for line in (base / 'numa_maps').read_text().splitlines():
        fields = line.split()
        policies[fields[1]] += 1
        anonymous_vma = any(x.startswith('anon=') for x in fields) and not any(x.startswith('file=') for x in fields)
        for field in fields:
            if field.startswith('N') and '=' in field and field[1:field.index('=')].isdigit():
                k, v = field.split('=')
                nodes[k] += int(v)
                if anonymous_vma:
                    anonymous[k] += int(v)
    tasks = []
    for task in (base / 'task').iterdir():
        try:
            fields = (task / 'stat').read_text().rsplit(')', 1)[1].split()
            tasks.append({'tid': int(task.name), 'allowed_cpus': sorted(os.sched_getaffinity(int(task.name))), 'last_cpu': int(fields[36]), 'utime': int(fields[11]), 'stime': int(fields[12]), 'major_faults': int(fields[9])})
        except FileNotFoundError:
            continue
    return {'numa_resident_pages': dict(nodes), 'anonymous_vma_resident_pages_per_node': dict(anonymous), 'numa_policies': dict(policies), 'page_bytes': os.sysconf('SC_PAGE_SIZE'), 'threads': tasks, 'scope': 'process resident pages; mmap length is not RSS; guest CPU topology only'}


def bounded_placement(pid, timeout=3):
    """Optional post-load diagnostic; never called by the mandatory guard loop.

    A stuck proc mapping reader is unavailable evidence, not a physical failure.
    Kill only this child on timeout; even an uninterruptible child cannot make
    this caller wait indefinitely. Retain its exact PID/settled state for audit.
    """
    started = time.monotonic()
    try:
        child = subprocess.Popen([sys.executable, '-B', '-c',
            'import json,sys; from telemetry import placement; print(json.dumps(placement(int(sys.argv[1]))))',
            str(pid)], cwd=str(P(__file__).parent), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError as exc:
        return {'status': 'UNAVAILABLE', 'reason': 'diagnostic_start_' + type(exc).__name__}
    try:
        raw, _ = child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            child.kill()
        except ProcessLookupError:
            pass
        settled = False
        try:
            child.wait(timeout=.2)
            settled = True
        except subprocess.TimeoutExpired:
            pass
        child.stdout.close()
        return {'status': 'UNAVAILABLE', 'reason': 'timeout', 'diagnostic_pid': child.pid,
                'diagnostic_settled': settled, 'seconds': time.monotonic() - started}
    if child.returncode:
        return {'status': 'UNAVAILABLE', 'reason': 'diagnostic_exit', 'exit_code': child.returncode,
                'diagnostic_pid': child.pid, 'diagnostic_settled': True}
    try:
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError('diagnostic_object_required')
    except (ValueError, UnicodeError):
        return {'status': 'UNAVAILABLE', 'reason': 'invalid_diagnostic_output', 'diagnostic_pid': child.pid,
                'diagnostic_settled': True}
    return {**result, 'status': 'AVAILABLE', 'diagnostic_pid': child.pid,
            'diagnostic_settled': True, 'seconds': time.monotonic() - started}


def interrupt_owner():
    os.kill(os.getpid(), signal.SIGTERM)


def monitor(h, state, failed):
    try:
        xml = ET.fromstring(run_cmd(['nvidia-smi', '-q', '-x'], 2))
        limits = {}
        for gpu in xml.findall('gpu'):
            thresholds = [85]
            for name in ['gpu_temp_slow_threshold', 'gpu_temp_shutdown_threshold']:
                value = gpu.findtext('temperature/' + name, '')
                try:
                    # These named XML fields are absolute Celsius, unlike T.Limit margins.
                    number = float(value.split()[0])
                    if 0 < number < 150 and 'C' in value:
                        thresholds.append(number)
                except (ValueError, IndexError):
                    pass
            limits[gpu.findtext('uuid')] = min(thresholds)
        cg = P(state['native_cgroup'])
        previous_events = {k: int(v) for k, v in (line.split() for line in (cg / 'memory.events').read_text().splitlines())}
        with h.MountedStorageGuard(h.s) as g, h.AnchoredRoot(LOG, g) as a, a.open('TELEMETRY.jsonl', os.O_WRONLY | os.O_CREAT | os.O_EXCL) as f:
            fd = f.fileno()
            while not failed.is_set():
                rows, mem = gpu_rows(timeout=2), memory()
                h.require(len(rows) == 4, 'gpu_telemetry_missing')
                sample = {'utc': h.now(), 'gpus': rows, 'temperature_limits_c': limits, 'host': {k: mem[k] for k in ['MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree']}}
                sample['cgroup'] = {n: (cg / n).read_text().strip() for n in ['memory.current', 'memory.stat', 'memory.swap.current', 'memory.events', 'cpu.stat', 'cpuset.cpus.effective', 'cpuset.mems.effective']}
                # Cgroup files are authority. No process status/maps/smaps or
                # diagnostic subprocess belongs on this five-second safety path.
                f.check()
                os.write(fd, (json.dumps(sample) + '\n').encode())
                h.require(mem['MemAvailable'] >= .15 * mem['MemTotal'], 'host_reserve_breached')
                for row in rows:
                    uid = row['uuid']
                    h.require(uid in limits and row['temp_c'] < limits[uid], 'gpu_temperature_cutoff')
                    reserve = row['total_mib'] * (.07 if uid == GPU else .05) if uid in [GPU, 'GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23'] else 16 * 1024
                    h.require(row['free_mib'] >= reserve, 'gpu_reserve_breached')
                events = {k: int(v) for k, v in (line.split() for line in sample['cgroup']['memory.events'].splitlines())}
                h.require(int(sample['cgroup']['memory.swap.current']) == 0 and all(events.get(k, 0) == previous_events.get(k, 0) for k in ['oom', 'oom_kill']), 'candidate_swap_or_oom')
                failed.wait(5)
    except BaseException as exc:
        if failed.is_set():
            return  # Owner settlement already began; never interrupt its finally again.
        state['guard_failure'] = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        failed.set()
        # Interrupt even a blocking HTTP prefill read; owner finally stops exact native.
        interrupt_owner()
