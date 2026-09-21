"""Opt-in decode diagnostics; callers own identity, five-second pacing and guards.

No inference, attachment, storage writes or smaps reads. Counters are cumulative;
compare threads only across matching (pid, process_starttime, tid, starttime).
Quiescent collection is separate and must never run inside a timed request.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import time

CPU_FIELDS = ('user', 'nice', 'system', 'idle', 'iowait', 'irq', 'softirq', 'steal', 'guest', 'guest_nice')
STAT_FIELDS = {'minflt': 7, 'majflt': 9, 'utime_ticks': 11, 'stime_ticks': 12,
               'starttime_ticks': 19, 'processor': 36}
ENV_PATTERNS = {
    'OMP_WAIT_POLICY': r'(?i:active|passive)', 'GOMP_SPINCOUNT': r'(?i:[0-9]+[kmg]?|infinite)',
    'OMP_PROC_BIND': r'(?i:true|false|(?:primary|master|close|spread)(?:,(?:primary|master|close|spread))*)',
    'OMP_PLACES': r'(?i:(?:threads|cores|sockets|ll_caches|numa_domains)(?:\([0-9]+\))?|[0-9{},:! +\-]+)',
    'OMP_NUM_THREADS': r'[0-9]+(?:,[0-9]+)*', 'OMP_DYNAMIC': r'(?i:true|false)',
    'OMP_THREAD_LIMIT': r'[0-9]+', 'GGML_CUDA_DISABLE_GRAPHS': r'(?i:0|1|true|false)',
}
LIBRARY_NAME = re.compile(r'(?:libggml-cpu[^/ ]*|libgomp)\.so(?:\.[0-9]+)*\Z')


def _number(value):
    return int(value) if isinstance(value, str) and value.isascii() and value.isdigit() else None


def _read(path, missing, field, maximum=262144):
    try:
        with path.open('rb') as source:
            data = source.read(maximum + 1)
        if len(data) > maximum:
            raise ValueError('bounded_read_exceeded')
        return data.decode('utf-8', errors='strict')
    except (OSError, UnicodeError, ValueError):
        missing.append(field)
        return ''


def parse_stat(text):
    """Linux comm may contain spaces and closing parentheses; never retain it."""
    prefix, sep, tail = text.rpartition(') ')
    fields = tail.split() if sep and re.match(r'^[0-9]+ \(', prefix) else []
    return {name: _number(fields[index]) if len(fields) > index else None
            for name, index in STAT_FIELDS.items()}


def parse_status(text):
    fields = dict(line.split(':', 1) for line in text.splitlines() if ':' in line)
    out = {name: _number(fields.get(name, '').strip()) for name in
           ('voluntary_ctxt_switches', 'nonvoluntary_ctxt_switches')}
    for name in ('Cpus_allowed_list', 'Mems_allowed_list'):
        value = fields.get(name, '').strip()
        out[name] = value if re.fullmatch(r'[0-9]+(?:[-,][0-9]+)*', value) else None
    return out


def parse_policy_environment(text):
    fields = dict(part.split('=', 1) for part in text.split('\0') if '=' in part)
    return {key: (None if key not in fields else fields[key] if len(fields[key]) <= 256 and
                  re.fullmatch(pattern, fields[key]) else 'REDACTED')
            for key, pattern in ENV_PATTERNS.items()}


def parse_numa_maps(text):
    pages = {}
    for line in text.splitlines():
        for node, count in re.findall(r'(?:^|\s)N([0-9]+)=([0-9]+)(?=\s|$)', line):
            pages[node] = pages.get(node, 0) + int(count)
    return {'node_pages': pages, 'total_reported_node_pages': sum(pages.values()),
            'unit': 'numa_maps pages; not bytes; no physical topology inference'}


def _validate_pids(pids, max_threads):
    values = [pid for members in pids.values() for pid in members]
    if (type(max_threads) is not int or not 1 <= max_threads <= 2048 or len(values) > 128 or
            any(type(pid) is not int or pid <= 0 for pid in values) or len(set(values)) != len(values)):
        raise ValueError('invalid_owned_pid_inventory_or_thread_bound')


def collect_decode_sample(cgroups, *, pids, proc_root=Path('/proc'), max_threads=2048,
                          clock=time.monotonic):
    """Cheap bounded snapshot; missing/partial fields remain explicit, not zero."""
    _validate_pids(pids, max_threads)
    started, missing, processes, groups, remaining = clock(), [], {}, {}, max_threads
    cpu_lines = _read(proc_root / 'stat', missing, 'host.cpu').splitlines()
    cpu = next((line.split()[1:] for line in cpu_lines if line.startswith('cpu ')), [])
    host = {name: _number(cpu[i]) if len(cpu) > i else None for i, name in enumerate(CPU_FIELDS)}
    load = _read(proc_root / 'loadavg', missing, 'host.loadavg').split()
    schedstats = _read(proc_root / 'sys/kernel/sched_schedstats', missing, 'host.sched_schedstats', 32).strip()
    scheduler_wait_status = {'0': 'DISABLED', '1': 'ENABLED'}.get(schedstats, 'UNAVAILABLE')
    runnable = load[3].split('/') if len(load) >= 4 else []
    host['runnable_tasks'] = _number(runnable[0]) if len(runnable) == 2 else None
    host['total_tasks'] = _number(runnable[1]) if len(runnable) == 2 else None
    for label, path in cgroups.items():
        pairs = dict(line.split() for line in _read(path / 'cpu.stat', missing, label + '.cpu.stat').splitlines()
                     if len(line.split()) == 2)
        group = {key: _number(pairs.get(key)) for key in
                 ('usage_usec', 'user_usec', 'system_usec', 'nr_periods', 'nr_throttled', 'throttled_usec')}
        quota = _read(path / 'cpu.max', missing, label + '.cpu.max').split()
        group['quota_usec'] = ('max' if quota[0] == 'max' else _number(quota[0])) if len(quota) == 2 else None
        group['period_usec'] = _number(quota[1]) if len(quota) == 2 else None
        group['missing_fields'] = [key for key, value in group.items() if value is None]
        groups[label] = group
    for label, members in pids.items():
        processes[label] = []
        for pid in members:
            base, prefix = proc_root / str(pid), str(pid)
            before = parse_stat(_read(base / 'stat', missing, prefix + '.stat'))['starttime_ticks']
            try:
                tids = []
                with os.scandir(base / 'task') as entries:
                    for entry in entries:
                        if entry.name.isascii() and entry.name.isdigit():
                            tids.append(int(entry.name))
                            if len(tids) > remaining:
                                break
                truncated, tids = len(tids) > remaining, sorted(tids[:remaining])
            except OSError:
                missing.append(prefix + '.task')
                truncated, tids = False, []
            rows = []
            for tid in tids:
                task, name = base / 'task' / str(tid), prefix + '.' + str(tid)
                row = {'tid': tid, **parse_stat(_read(task / 'stat', missing, name + '.stat')),
                       **parse_status(_read(task / 'status', missing, name + '.status'))}
                sched = _read(task / 'schedstat', missing, name + '.schedstat').split()
                raw_schedstat = {key: _number(sched[i]) if len(sched) == 3 else None for i, key in
                                enumerate(('runtime_ns', 'runqueue_ns', 'timeslices'))}
                # Disabled schedstats can expose zeros that do not measure no
                # waiting. Retain raw data separately; gate all supported fields.
                row['raw_schedstat'] = raw_schedstat
                row['scheduler_wait_available'] = (scheduler_wait_status == 'ENABLED' and
                                                  all(value is not None for value in raw_schedstat.values()))
                row.update({key: value if row['scheduler_wait_available'] else None
                            for key, value in raw_schedstat.items()})
                end = parse_stat(_read(task / 'stat', missing, name + '.stat_after'))['starttime_ticks']
                row['generation_stable'] = row['starttime_ticks'] is not None and row['starttime_ticks'] == end
                row['missing_fields'] = [key for key, value in row.items() if value is None]
                rows.append(row)
            remaining -= len(rows)
            after = parse_stat(_read(base / 'stat', missing, prefix + '.stat_after'))['starttime_ticks']
            processes[label].append({'pid': pid, 'process_starttime_ticks': before,
                'generation_stable': before is not None and before == after,
                'threads_truncated': truncated, 'threads': rows})
    ended = clock()
    return {'sample_kind': 'decode_cpu', 'timestamp_monotonic_s': started,
            'collection_finished_monotonic_s': ended, 'collection_duration_s': ended - started,
            'clock_ticks_per_second': os.sysconf('SC_CLK_TCK'), 'host_cpu': host,
            'scheduler_wait_available': scheduler_wait_status == 'ENABLED',
            'scheduler_wait_status': scheduler_wait_status,
            'host_missing_fields': [key for key, value in host.items() if value is None],
            'cgroups': groups, 'processes': processes, 'missing_reads': missing,
            'scope': 'guest cumulative counters; guest and guest_nice included in user and nice'}


def _library_identity(path, device, inode, readelf, timeout):
    """Inspect the mapped inode, never claim a replacement pathname is loaded."""
    out = {'build_id': None, 'needed': [], 'status': 'UNAVAILABLE'}
    if readelf is None or timeout <= 0:
        return out
    try:
        with path.open('rb') as binary:
            info = os.fstat(binary.fileno())
            if (info.st_ino != inode or (os.major(info.st_dev), os.minor(info.st_dev)) != device or
                    info.st_size > 128 * 1024 * 1024):
                out['status'] = 'MAPPED_INODE_CHANGED_OR_FILE_TOO_LARGE'
                return out
            reply = subprocess.run([readelf, '-n', '-d', '--', '/proc/self/fd/' + str(binary.fileno())],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                pass_fds=(binary.fileno(),), timeout=timeout, check=False,
                env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
        if reply.returncode or len(reply.stdout) > 262144:
            return out
        text = reply.stdout.decode('utf-8', errors='replace')
        match = re.search(r'Build ID: ([a-fA-F0-9]+)', text)
        out.update(build_id=match.group(1).lower() if match else None,
                   needed=sorted(set(re.findall(r'\(NEEDED\).*\[([a-zA-Z0-9_.+\-]+)\]', text))),
                   status='OK' if match else 'BUILD_ID_UNAVAILABLE')
    except (OSError, subprocess.SubprocessError):
        pass
    return out


def quiescent_snapshot(pids, *, proc_root=Path('/proc'), clock=time.monotonic):
    """Before/after only: NUMA pages, effective policy and loaded CPU libraries.

    Library inspection has an aggregate ten-second budget and at most eight
    unique mapped inodes. No arbitrary environment, paths or maps are returned.
    """
    _validate_pids(pids, 2048)
    started, missing, result, inspected = clock(), [], {}, {}
    readelf = shutil.which('readelf', path='/usr/bin:/bin')
    for label, members in pids.items():
        result[label] = []
        for pid in members:
            base, name = proc_root / str(pid), str(pid)
            generation = parse_stat(_read(base / 'stat', missing, name + '.stat'))['starttime_ticks']
            numa = _read(base / 'numa_maps', missing, name + '.numa_maps', 16 * 1024 * 1024)
            row = {'pid': pid, 'process_starttime_ticks': generation,
                   'numa': parse_numa_maps(numa) if numa else None,
                   'policy_environment': parse_policy_environment(_read(base / 'environ', missing, name + '.environ')),
                   'libraries': []}
            mappings = _read(base / 'maps', missing, name + '.maps', 16 * 1024 * 1024)
            seen = set()
            for line in mappings.splitlines():
                parts = line.split(None, 5)
                if len(parts) != 6:
                    continue
                mapped_path = parts[5].removesuffix(' (deleted)')
                library = Path(mapped_path).name
                if not LIBRARY_NAME.fullmatch(library):
                    continue
                try:
                    device, inode = tuple(int(n, 16) for n in parts[3].split(':')), int(parts[4])
                    if len(device) != 2 or not Path(mapped_path).is_absolute() or '..' in Path(mapped_path).parts:
                        raise ValueError('invalid_mapping')
                    key = (device, inode)
                    if key in seen:
                        continue
                    seen.add(key)
                    if mapped_path != parts[5]:
                        row['libraries'].append({'name': library, 'status': 'MAPPED_FILE_DELETED',
                                                 'build_id': None, 'needed': []})
                        continue
                    if key not in inspected and len(inspected) < 8:
                        inspected[key] = _library_identity(base / 'root' / mapped_path.lstrip('/'), device, inode,
                            readelf, min(2, 10 - (clock() - started)))
                    identity = inspected.get(key, {'status': 'LIBRARY_INSPECTION_BOUND'})
                except ValueError:
                    identity = {'status': 'INVALID_MAPPING'}
                row['libraries'].append({'name': library, **identity})
            end = parse_stat(_read(base / 'stat', missing, name + '.stat_after'))['starttime_ticks']
            row['generation_stable'] = generation is not None and generation == end
            result[label].append(row)
    ended = clock()
    return {'sample_kind': 'decode_quiescent', 'timestamp_monotonic_s': started,
            'collection_finished_monotonic_s': ended, 'collection_duration_s': ended - started,
            'processes': result, 'missing_reads': missing, 'readelf_available': readelf is not None}
