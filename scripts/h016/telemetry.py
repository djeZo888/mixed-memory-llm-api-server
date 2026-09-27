"""Five-second H016 owner telemetry; independent of streaming readers."""
import collections
import json
import os
import pathlib
import signal
import time
import xml.etree.ElementTree as ET
from candidate_owner import gpu_rows, memory, run_cmd, LOG, GPU
P = pathlib.Path


def placement(pid):
    base = P('/proc', str(pid))
    nodes = collections.Counter()
    for line in (base / 'numa_maps').read_text().splitlines():
        for field in line.split():
            if field.startswith('N') and '=' in field and field[1:field.index('=')].isdigit():
                k, v = field.split('=')
                nodes[k] += int(v)
    tasks = []
    for task in (base / 'task').iterdir():
        try:
            fields = (task / 'stat').read_text().rsplit(')', 1)[1].split()
            tasks.append({'tid': int(task.name), 'allowed_cpus': sorted(os.sched_getaffinity(int(task.name))), 'last_cpu': int(fields[36]), 'utime': int(fields[11]), 'stime': int(fields[12]), 'major_faults': int(fields[9])})
        except FileNotFoundError:
            continue
    return {'numa_resident_pages': dict(nodes), 'threads': tasks, 'scope': 'process resident pages; mmap length is not RSS; guest CPU topology only'}


def interrupt_owner():
    os.kill(os.getpid(), signal.SIGTERM)


def monitor(h, state, failed):
    try:
        xml = ET.fromstring(run_cmd(['nvidia-smi', '-q', '-x'], 10))
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
        pid = state['native_pid']
        previous_events = {k: int(v) for k, v in (line.split() for line in (cg / 'memory.events').read_text().splitlines())}
        last_placement = 0
        with h.MountedStorageGuard(h.s) as g, h.AnchoredRoot(LOG, g) as a, a.open('TELEMETRY.jsonl', os.O_WRONLY | os.O_CREAT | os.O_EXCL) as f:
            fd = f.fileno()
            while not failed.is_set():
                rows, mem = gpu_rows(), memory()
                h.require(len(rows) == 4, 'gpu_telemetry_missing')
                sample = {'utc': h.now(), 'gpus': rows, 'temperature_limits_c': limits, 'host': {k: mem[k] for k in ['MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree']}}
                sample['cgroup'] = {n: (cg / n).read_text().strip() for n in ['memory.current', 'memory.stat', 'memory.swap.current', 'memory.events', 'cpu.stat', 'cpuset.cpus.effective', 'cpuset.mems.effective']}
                sample['process_status'] = [x for x in P('/proc', str(pid), 'status').read_text().splitlines() if x.startswith(('VmRSS:', 'RssAnon:', 'RssFile:', 'VmSwap:', 'Cpus_allowed_list:', 'Mems_allowed_list:'))]
                if time.monotonic() - last_placement >= 60:
                    sample['placement'] = placement(pid)
                    last_placement = time.monotonic()
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
        state['guard_failure'] = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        failed.set()
        # Interrupt even a blocking HTTP prefill read; owner finally stops exact native.
        interrupt_owner()
