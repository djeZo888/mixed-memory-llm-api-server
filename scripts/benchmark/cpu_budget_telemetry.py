"""Bounded CPU evidence for the closed concurrent 480000 CPU-budget benchmark.

The existing owner supplies verified cgroups/PIDs and pacing. Timed collection
reads no threads, maps, smaps, environments or NUMA data; no subprocess is used.
NUMA snapshots are a separate before/after operation. No physical CPU topology
or cores-needed claim follows from these guest utilization counters.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import time

from . import decode_telemetry as primitive
from .cpu_budget_profiles import CPU_SCOPE, POSTRESTART_SCOPE

STATUS = 'UNAVAILABLE'
CPU_KEYS = primitive.CPU_FIELDS[:8]  # guest/guest_nice are already in user/nice.
CGROUP_KEYS = ('usage_usec', 'user_usec', 'system_usec', 'nr_periods', 'nr_throttled', 'throttled_usec')


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _status(fields):
    return 'AVAILABLE' if fields and all(v is not None for v in fields.values()) else STATUS


def _pressure(path, missing, label):
    rows = {}
    for line in primitive._read(path, missing, label).splitlines():
        values = line.split()
        if not values or values[0] not in {'some', 'full'}:
            continue
        fields = dict(part.split('=', 1) for part in values[1:] if '=' in part)
        row = {'total_usec': primitive._number(fields.get('total'))}
        for key in ('avg10', 'avg60', 'avg300'):
            try:
                value = float(fields.get(key, ''))
                row[key] = value if math.isfinite(value) and 0 <= value <= 100 else None
            except ValueError:
                row[key] = None
        rows[values[0]] = {**row, 'status': _status(row)}
    # Missing/disabled PSI is unavailable, never an invented zero pressure.
    return {kind: rows.get(kind, {'status': STATUS, 'total_usec': None,
                                 'avg10': None, 'avg60': None, 'avg300': None})
            for kind in ('some', 'full')}


def _process_stat(text):
    row = primitive.parse_stat(text)
    fields = text.rpartition(') ')[2].split()
    threads = primitive._number(fields[17]) if row['starttime_ticks'] is not None and len(fields) > 17 else None
    return {**row, 'num_threads': threads if threads is not None and threads > 0 else None}


def collect_sample(cgroups, *, pids, proc_root=Path('/proc'), clock=time.monotonic):
    """Reuse decode diagnostic parsers without per-thread or expensive sampling."""
    primitive._validate_pids(pids, 2048)
    if set(cgroups) != set(pids) or not cgroups or len(cgroups) > 2:
        raise ValueError('closed_cpu_cgroup_inventory_required')
    started, missing = clock(), []
    cpus = {}
    for line in primitive._read(proc_root / 'stat', missing, 'guest.cpu').splitlines():
        parts = line.split()
        if not parts or not (parts[0] == 'cpu' or
                parts[0].startswith('cpu') and parts[0][3:].isascii() and parts[0][3:].isdigit()):
            continue
        fields = {key: primitive._number(parts[i + 1]) if len(parts) > i + 1 else None
                  for i, key in enumerate(primitive.CPU_FIELDS)}
        cpus[parts[0]] = {**fields, 'status': _status({k: fields[k] for k in CPU_KEYS})}
    groups, processes = {}, {}
    for label, path in cgroups.items():
        path = Path(path)
        pairs = dict(line.split() for line in primitive._read(path / 'cpu.stat', missing,
                     label + '.cpu.stat').splitlines() if len(line.split()) == 2)
        fields = {key: primitive._number(pairs.get(key)) for key in CGROUP_KEYS}
        quota = primitive._read(path / 'cpu.max', missing, label + '.cpu.max').split()
        try:
            info = path.stat()
            identity = [info.st_dev, info.st_ino]
        except OSError:
            identity = None
            missing.append(label + '.cgroup_identity')
        groups[label] = {**fields, 'identity': identity, 'status': _status(fields),
            'quota_usec': ('max' if quota[0] == 'max' else primitive._number(quota[0])) if len(quota) == 2 else None,
            'period_usec': primitive._number(quota[1]) if len(quota) == 2 else None,
            'quota_scope': 'owned cgroup cpu.max only; not effective inherited quota or affinity capacity',
            'ancestor_quota_status': STATUS,
            'psi': {kind: _pressure(path / (kind + '.pressure'), missing, label + '.' + kind + '.pressure')
                    for kind in ('cpu', 'memory', 'io')}}
        processes[label] = []
        for pid in pids[label]:
            base = proc_root / str(pid)
            fields = _process_stat(primitive._read(base / 'stat', missing, str(pid) + '.stat'))
            after = primitive.parse_stat(primitive._read(base / 'stat', missing, str(pid) + '.stat_after'))
            stable = fields['starttime_ticks'] is not None and fields['starttime_ticks'] == after['starttime_ticks']
            row = {k: fields[k] for k in ('starttime_ticks', 'utime_ticks', 'stime_ticks')}
            processes[label].append({**row, 'pid': pid, 'generation_stable': stable,
                'num_threads': fields['num_threads'],
                'runtime_thread_count_status': 'AVAILABLE' if fields['num_threads'] is not None and stable else STATUS,
                'status': _status(row) if stable else STATUS})
    pressure = {kind: _pressure(proc_root / 'pressure' / kind, missing, 'guest.' + kind + '.pressure')
                for kind in ('cpu', 'memory', 'io')}
    # Preserve compatibility counters without treating global CPU full zeros as
    # proof of no stalls. CPU some and cgroup CPU full remain interpreted.
    raw_full = pressure['cpu']['full']
    pressure['cpu']['full'] = {'status': STATUS, 'reason': 'system_cpu_full_not_interpreted',
        'total_usec': None, 'avg10': None, 'avg60': None, 'avg300': None,
        'raw_compatibility_counters': raw_full}
    ended = clock()
    return {'schema_version': 1, 'sample_kind': 'cpu_budget', 'timestamp_monotonic_s': started,
        'collection_finished_monotonic_s': ended, 'collection_duration_s': ended - started,
        'clock_ticks_per_second': os.sysconf('SC_CLK_TCK'),
        'guest_cpus': cpus, 'observed_vcpu_count': len(cpus) - int('cpu' in cpus),
        'cgroups': groups, 'processes': processes, 'guest_psi': pressure, 'missing_reads': missing,
        'scope': 'guest counters; no hypervisor pinning/locality evidence; cpuset CPU count is not runtime thread count',
        'scheduler_wait': {'status': STATUS, 'reason': 'per-thread schedstat deliberately not sampled'}}


def numa_snapshot(pids, *, proc_root=Path('/proc'), clock=time.monotonic):
    """Page-only quiescent snapshot; caller must keep outside timed requests."""
    primitive._validate_pids(pids, 2048)
    started, missing, processes = clock(), [], {}
    for label, members in pids.items():
        processes[label] = []
        for pid in members:
            base = proc_root / str(pid)
            before = primitive.parse_stat(primitive._read(base / 'stat', missing, str(pid) + '.stat'))
            raw = primitive._read(base / 'numa_maps', missing, str(pid) + '.numa_maps', 16 * 1024 * 1024)
            after = primitive.parse_stat(primitive._read(base / 'stat', missing, str(pid) + '.stat_after'))
            stable = before['starttime_ticks'] is not None and before['starttime_ticks'] == after['starttime_ticks']
            processes[label].append({'pid': pid, 'process_starttime_ticks': before['starttime_ticks'],
                'generation_stable': stable, 'status': 'AVAILABLE' if raw and stable else STATUS,
                'numa': primitive.parse_numa_maps(raw) if raw and stable else None})
    ended = clock()
    return {'sample_kind': 'cpu_budget_numa_quiescent', 'timestamp_monotonic_s': started,
        'collection_finished_monotonic_s': ended, 'collection_duration_s': ended - started,
        'outside_timed_sampling_required': True, 'processes': processes, 'missing_reads': missing}


def _delta(before, after, keys):
    values = {}
    for key in keys:
        left, right = before.get(key), after.get(key)
        if not _finite(left) or not _finite(right) or left < 0 or right < left:
            return None
        values[key] = right - left
    return values


def _weighted(values):
    """Elapsed-time weighted nearest-rank p95 of observed interval rates."""
    if not values:
        return {'status': STATUS, 'average_core_equivalents': None,
                'p95_interval_core_equivalents': None, 'cpu_time_s': None,
                'observed_wall_s': 0, 'interval_count': 0}
    duration = sum(dt for _, dt in values)
    cpu = sum(rate * dt for rate, dt in values)
    cumulative, p95 = 0, None
    for rate, dt in sorted(values):
        cumulative += dt
        if cumulative >= duration * .95:
            p95 = rate
            break
    return {'status': 'AVAILABLE', 'average_core_equivalents': cpu / duration,
            'p95_interval_core_equivalents': p95, 'cpu_time_s': cpu,
            'observed_wall_s': duration, 'interval_count': len(values)}


def summarize_phase(samples, started, ended, *, phase, time_key='client_observed_monotonic_s'):
    """Summarize intervals selected by client receipt proxy, never native phases.

    CPU denominators use host monotonic sample midpoints, not a subtraction of
    clocks from different hosts. Only consecutive samples observed wholly inside
    the supplied client window are used; no prorating across phase boundaries.
    """
    result = {'phase': phase, 'phase_basis': 'worker client-event/receipt proxy; not native phase timing',
        'status': STATUS, 'window_start': started, 'window_end': ended,
        'clock_alignment': 'client receipt selects phases; host midpoint deltas measure elapsed time; RPC lag uncorrected',
        'p95_method': 'elapsed-time weighted nearest rank of sampled interval core-equivalents',
        'p95_caveat': 'short decode windows and fewer than 20 intervals give coarse, unstable p95; no instantaneous peak or cores-needed proof',
        'cgroups': {}, 'processes': {}, 'process_group_totals': {}, 'guest_cpus': {}, 'psi': {}}
    if not _finite(started) or not _finite(ended) or ended <= started:
        result['reason'] = 'invalid_or_missing_client_phase_bounds'
        return result
    valid = [sample for sample in samples if sample.get('sample_kind') == 'cpu_budget']
    selected = [sample for sample in valid if _finite(sample.get(time_key)) and started <= sample[time_key] <= ended]
    selected_ids = {id(sample) for sample in selected}
    rates, failures, extras = {}, {}, {}
    interval_count, durations = 0, []
    def add(name, amount, dt):
        if amount is None:
            failures[name] = failures.get(name, 0) + 1
        else:
            rates.setdefault(name, []).append((amount / dt, dt))
    for left, right in zip(valid, valid[1:]):
        if id(left) not in selected_ids or id(right) not in selected_ids:
            continue
        def midpoint(sample):
            a, b = sample.get('timestamp_monotonic_s'), sample.get('collection_finished_monotonic_s')
            return (a + b) / 2 if _finite(a) and _finite(b) and b >= a else None
        a, b = midpoint(left), midpoint(right)
        if a is None or b is None or b <= a or right[time_key] <= left[time_key]:
            continue
        dt, hz = b - a, left.get('clock_ticks_per_second')
        if not _finite(hz) or hz <= 0 or hz != right.get('clock_ticks_per_second'):
            continue
        interval_count += 1
        durations.append(dt)
        for label in sorted(set(left.get('cgroups', {})) | set(right.get('cgroups', {}))):
            x, y = left['cgroups'].get(label, {}), right['cgroups'].get(label, {})
            same = x.get('identity') is not None and x.get('identity') == y.get('identity')
            delta = _delta(x, y, ('usage_usec',)) if same else None
            name = ('cgroups', label)
            add(name, delta['usage_usec'] / 1e6 if delta else None, dt)
            extra = extras.setdefault(name, {'throttling_deltas': [], 'quota_samples': []})
            extra['throttling_deltas'].append(_delta(x, y, ('nr_periods', 'nr_throttled', 'throttled_usec')) if same else None)
            for observed in (x, y):
                quota = {key: observed.get(key) for key in ('quota_usec', 'period_usec')}
                if quota not in extra['quota_samples']:
                    extra['quota_samples'].append(quota)
        for label in sorted(set(left.get('processes', {})) | set(right.get('processes', {}))):
            x = {p['pid']: p for p in left['processes'].get(label, [])}
            y = {p['pid']: p for p in right['processes'].get(label, [])}
            total, complete = 0, bool(x) and set(x) == set(y)
            for pid in sorted(set(x) | set(y)):
                p, q = x.get(pid, {}), y.get(pid, {})
                same = (p.get('generation_stable') is True and q.get('generation_stable') is True
                        and p.get('starttime_ticks') == q.get('starttime_ticks'))
                delta = _delta(p, q, ('utime_ticks', 'stime_ticks')) if same else None
                amount = sum(delta.values()) / hz if delta else None
                process_key = ('processes', label + ':' + str(pid))
                add(process_key, amount, dt)
                counts = extras.setdefault(process_key, {'runtime_thread_counts': []})['runtime_thread_counts']
                for observed in (p, q):
                    value = observed.get('num_threads')
                    if value not in counts:
                        counts.append(value)
                complete = complete and amount is not None
                total += amount if amount is not None else 0
            add(('process_group_totals', label), total if complete else None, dt)
        for cpu in sorted({'cpu'} | set(left.get('guest_cpus', {})) | set(right.get('guest_cpus', {}))):
            delta = _delta(left.get('guest_cpus', {}).get(cpu, {}), right.get('guest_cpus', {}).get(cpu, {}), CPU_KEYS)
            name = ('guest_cpus', cpu)
            # Busy excludes idle, iowait and steal; guest fields are not double-counted.
            amount = sum(delta[k] for k in ('user', 'nice', 'system', 'irq', 'softirq')) / hz if delta else None
            add(name, amount, dt)
            extras.setdefault(name, {'steal_time_s': [], 'iowait_time_s': []})['steal_time_s'].append(delta['steal'] / hz if delta else None)
            extras[name]['iowait_time_s'].append(delta['iowait'] / hz if delta else None)
        pressure_pairs = [('guest', left.get('guest_psi', {}), right.get('guest_psi', {}), True)]
        for label in set(left.get('cgroups', {})) | set(right.get('cgroups', {})):
            x, y = left['cgroups'].get(label, {}), right['cgroups'].get(label, {})
            same = x.get('identity') is not None and x.get('identity') == y.get('identity')
            pressure_pairs.append((label, x.get('psi', {}), y.get('psi', {}), same))
        for label, x, y, same in pressure_pairs:
            for resource in ('cpu', 'memory', 'io'):
                for kind in ('some', 'full'):
                    delta = _delta(x.get(resource, {}).get(kind, {}), y.get(resource, {}).get(kind, {}), ('total_usec',)) if same else None
                    add(('psi', ':'.join((label, resource, kind))), delta['total_usec'] / 1e6 if delta else None, dt)
    for category, name in sorted(set(rates) | set(failures)):
        key = (category, name)
        row = _weighted(rates.get(key, []))
        row['unavailable_interval_count'] = failures.get(key, 0)
        if row['status'] == 'AVAILABLE' and row['unavailable_interval_count']:
            row['status'] = 'PARTIAL'
        if category == 'psi':
            row['average_stall_fraction'] = row.pop('average_core_equivalents')
            row['p95_interval_stall_fraction'] = row.pop('p95_interval_core_equivalents')
            row['stall_time_s'] = row.pop('cpu_time_s')
        row.update(extras.get(key, {}))
        if category == 'processes':
            row['runtime_thread_count_status'] = 'AVAILABLE' if all(
                type(value) is int and value > 0 for value in row['runtime_thread_counts']) else STATUS
            row['thread_count_scope'] = 'runtime process threads, not cpuset vCPU budget'
        if category == 'cgroups':
            good = [value for value in row['throttling_deltas'] if value is not None]
            row['throttling'] = {'status': 'AVAILABLE' if len(good) == interval_count else 'PARTIAL' if good else STATUS,
                'available_interval_count': len(good), 'unavailable_interval_count': interval_count-len(good),
                'delta_totals': {key: sum(value[key] for value in good) for key in
                    ('nr_periods', 'nr_throttled', 'throttled_usec')} if good else None}
            row['quota_status'] = 'AVAILABLE' if all(
                q['quota_usec'] is not None and _finite(q['period_usec']) and q['period_usec'] > 0
                for q in row['quota_samples']) else STATUS
            row['quota_changed'] = len(row['quota_samples']) > 1
            row['quota_scope'] = 'owned cgroup cpu.max only; not effective inherited quota or affinity capacity'
            row['ancestor_quota_status'] = STATUS
        result[category][name] = row
    overhead = [s['collection_duration_s'] for s in selected if _finite(s.get('collection_duration_s'))]
    metric_states = [value['status'] for category in ('cgroups', 'process_group_totals', 'guest_cpus', 'psi')
                     for value in result[category].values()]
    availability = ('AVAILABLE' if metric_states and all(value == 'AVAILABLE' for value in metric_states)
                    else 'PARTIAL' if any(value in {'AVAILABLE', 'PARTIAL'} for value in metric_states) else STATUS)
    result.update(status=availability, interval_count=interval_count,
        selected_sample_count=len(selected), requested_window_s=ended-started,
        observed_interval_wall_s=sum(durations),
        sample_interval_s={'minimum': min(durations) if durations else None,
                           'maximum': max(durations) if durations else None},
        sampling_precision={'process_cpu_tick_seconds': sorted({1/s['clock_ticks_per_second'] for s in selected
            if _finite(s.get('clock_ticks_per_second')) and s['clock_ticks_per_second'] > 0}),
            'cgroup_cpu_counter_unit': 'microseconds', 'guest_cpu_counter_unit': 'USER_HZ ticks'},
        collection_overhead={'sample_count': len(overhead), 'total_s': sum(overhead),
            'maximum_s': max(overhead) if overhead else None,
            'fraction_of_observed_span': sum(overhead)/sum(durations) if durations else None,
            'scope': 'non-atomic collector wall time only; existing monitor/RPC/storage overhead and measurement perturbation are separate'},
        unavailable_counters='missing, disabled, changed process/cgroup identity or regressing counters are UNAVAILABLE; no zero substitution')
    if not interval_count:
        result['reason'] = 'fewer_than_two_usable_phase_samples'
    return result


def summarize_measurement(samples, sample_summary, *, scope=CPU_SCOPE):
    """Use request dispatch/drain and output arrival windows; native fields separate."""
    start, end = sample_summary.get('request_started_monotonic_s'), sample_summary.get('request_ended_monotonic_s')
    timing = sample_summary.get('client_timing') or {}
    first, last = timing.get('ttft_any_output_seconds'), timing.get('last_output_seconds')
    first = start + first if _finite(start) and _finite(first) else None
    last = start + last if _finite(start) and _finite(last) else None
    phases = {'request': summarize_phase(samples, start, end, phase='request_dispatch_to_drain'),
        'prefill_proxy': summarize_phase(samples, start, first, phase='dispatch_to_first_output_arrival'),
        'decode_proxy': summarize_phase(samples, first, last, phase='first_to_last_output_arrival')}
    return {**phases, 'counter_evidence': _counter_evidence(phases, scope=scope),
        'native_aggregate_timing': {key: (sample_summary.get('counters') or {}).get(key)
                                  for key in ('prompt_ms', 'decode_ms', 'prompt_tokens', 'decode_tokens')},
        'native_aggregate_is_not_cpu_phase_boundary': True}


def _required_vcpus(scope):
    if scope not in (CPU_SCOPE, POSTRESTART_SCOPE):
        raise ValueError('closed_cpu_evidence_scope_required')
    return 72 if scope == POSTRESTART_SCOPE else 112


def _counter_evidence(phases, *, scope=CPU_SCOPE):
    """Require measured channels, without treating excluded global CPU full as zero."""
    missing = []
    required_vcpus = _required_vcpus(scope)
    groups = sorted(phases['request'].get('cgroups', {}))
    if len(groups) != 2:
        missing.append('request.exact_two_owned_cgroups')
    for phase, summary in phases.items():
        if not summary.get('interval_count'):
            missing.append(phase + '.phase_intervals')
        for category in ('cgroups', 'process_group_totals'):
            for group in groups:
                value = summary.get(category, {}).get(group, {})
                if value.get('status') != 'AVAILABLE':
                    missing.append('.'.join((phase, category, group)))
        for group in groups:
            value = summary.get('cgroups', {}).get(group, {})
            if value.get('quota_status') != 'AVAILABLE' or value.get('quota_changed') is not False:
                missing.append('.'.join((phase, 'quota', group)))
            if value.get('throttling', {}).get('status') != 'AVAILABLE':
                missing.append('.'.join((phase, 'throttling', group)))
        for process, value in summary.get('processes', {}).items():
            if value.get('status') != 'AVAILABLE':
                missing.append('.'.join((phase, 'processes', process)))
        expected_cpus = {'cpu'} | {'cpu' + str(i) for i in range(required_vcpus)}
        if set(summary.get('guest_cpus', {})) != expected_cpus:
            missing.append(phase + '.exact_' + str(required_vcpus) + '_guest_vcpus')
        for name in sorted(expected_cpus):
            value = summary.get('guest_cpus', {}).get(name, {})
            if value.get('status') != 'AVAILABLE' or not value.get('steal_time_s') or any(
                    item is None for item in value.get('steal_time_s', [])):
                missing.append('.'.join((phase, 'guest_cpus', name)))
        for group in ['guest', *groups]:
            for resource in ('cpu', 'memory', 'io'):
                for kind in ('some', 'full'):
                    if (group, resource, kind) == ('guest', 'cpu', 'full'):
                        continue
                    key = ':'.join((group, resource, kind))
                    if summary.get('psi', {}).get(key, {}).get('status') != 'AVAILABLE':
                        missing.append('.'.join((phase, 'psi', key)))
    return {'status': 'COMPLETE' if not missing else 'INCOMPLETE',
        'missing_or_partial': sorted(set(missing)), 'required_guest_vcpus': required_vcpus,
        'explicit_exclusions': ['global cpu.full compatibility counters', 'per-thread scheduler-wait counters',
                                'ancestor/inherited CPU quota; own cgroup cpu.max only'],
        'evidence_boundary': 'observed sampled intervals only; phase edge gaps, RPC lag, short decode p95 and overhead caveats remain',
        'quiescent_numa_and_host_safety': 'SEPARATE_EVIDENCE_REQUIRED',
        'cores_needed': 'NOT_ESTABLISHED_BY_UTILIZATION'}


def comparison_summary(completed):
    """Five-case closed result receipt; timing observations never infer causality."""
    expected = {'A-G65008', 'A-Qnear480K', 'A-Q256K', 'B-G65008', 'B-Qnear480K'}
    errors, observed, paired = [], {}, {}
    if set(completed) != expected:
        errors.append('exact_five_closed_measurements_required')
    for name in sorted(expected):
        row = completed.get(name, {})
        sample = row.get('sample') or {}
        counters, counted = sample.get('counters') or {}, row.get('count') or {}
        timing = sample.get('client_timing') or {}
        start, end = sample.get('request_started_monotonic_s'), sample.get('request_ended_monotonic_s')
        first, last = timing.get('ttft_any_output_seconds'), timing.get('last_output_seconds')
        valid_count = (row.get('native_count_valid') is True and type(counted.get('input_tokens')) is int
            and counted['input_tokens'] > 0 and counters.get('prompt_tokens') == counted['input_tokens']
            and type(counters.get('completion_tokens')) is int and 0 < counters['completion_tokens'] <= 256)
        if (row.get('status') != 'PASS' or not valid_count or row.get('configured_capacity') != 480000
                or row.get('id') != name or row.get('common_input') is not (name == 'A-Q256K')
                or not row.get('fixture_sha256') or row.get('layout') != name[0]):
            errors.append(name + '.inference_identity_or_count_gate')
        if not (_finite(start) and _finite(end) and end > start and _finite(first) and first >= 0
                and _finite(last) and last >= first):
            errors.append(name + '.client_timing_unavailable')
        gate = row.get('cpu_evidence', {}).get('counter_evidence', {})
        if gate.get('status') != 'COMPLETE':
            errors.append(name + '.required_cpu_evidence_incomplete')
        observed[name] = {'status': row.get('status', STATUS), 'fixture_sha256': row.get('fixture_sha256'),
            'configured_capacity': row.get('configured_capacity'), 'counted_input_tokens': counted.get('input_tokens'),
            'native_input_tokens': counters.get('prompt_tokens'), 'actual_completion_tokens': counters.get('completion_tokens'),
            'requested_output_cap': 256, 'body_sha256': counted.get('body_sha256'),
            'native_prompt_ms': counters.get('prompt_ms'), 'native_decode_ms': counters.get('decode_ms'),
            'native_n_minus_one_decode_tps': row.get('native_n_minus_one_decode_tps'),
            'client_request_seconds': end-start if _finite(start) and _finite(end) and end >= start else None,
            'client_ttft_seconds': first if _finite(first) and first >= 0 else None,
            'client_output_arrival_span_seconds': last-first if _finite(first) and _finite(last) and last >= first else None,
            'peer_condition_at_admission': row.get('peer_condition_at_admission'),
            'counter_evidence': gate or {'status': 'INCOMPLETE'}}
    for kind in ('G65008', 'Qnear480K'):
        left, right = observed['A-' + kind], observed['B-' + kind]
        fixture_match = bool(left['fixture_sha256']) and left['fixture_sha256'] == right['fixture_sha256']
        count_match = type(left['native_input_tokens']) is int and left['native_input_tokens'] == right['native_input_tokens']
        if not fixture_match or not count_match:
            errors.append(kind + '.matched_fixture_and_native_input_required')
        ratios = {}
        for key in ('native_prompt_ms', 'native_decode_ms', 'client_request_seconds', 'client_ttft_seconds',
                    'client_output_arrival_span_seconds', 'native_n_minus_one_decode_tps'):
            a, b = left.get(key), right.get(key)
            ratios[key + '_B_over_A'] = b/a if _finite(a) and _finite(b) and a > 0 and b >= 0 else None
        paired[kind] = {'same_logical_fixture': fixture_match, 'same_native_input_count': count_match,
            'same_actual_completion_count': left['actual_completion_tokens'] == right['actual_completion_tokens'],
            'observed_ratios': ratios, 'decode_comparability': 'inspect actual output counts and short decode caveat; max256 is not a measured token count'}
    return {'status': 'COMPLETE' if not errors else 'INCOMPLETE', 'missing_or_partial': errors,
        'observations': observed, 'paired_layouts': paired,
        'layouts': {'A': {'active_vcpus': 112, 'glm_configured_threads': 96, 'qwen_permitted_vcpus': 16,
                          'glm_cpuset': '0-95', 'qwen_cpuset': '96-111'},
                    'B': {'active_vcpus': 96, 'glm_configured_threads': 88, 'qwen_permitted_vcpus': 8,
                          'glm_cpuset': '0-87', 'qwen_cpuset': '96-103'}},
        'scope': 'single observed pair per layout in unchanged112-vCPU guest; no statistical replication or physical pinning/locality proof',
        'common_input_control': 'A-Q256K is its own configured480000 observation; peer condition and actual occupied count preserved',
        'historical_Q700_comparison': 'HISTORICAL_ONLY; no historical timing imported and no claim all700K slowdown came from allocation size',
        'causal_claim': 'NOT_ESTABLISHED', 'cores_needed_from_utilization': 'NOT_ESTABLISHED',
        'acceptance_boundary': 'timed counter receipt only; NUMA, host safety, restoration and root review remain separate requirements'}


def warmup_gate(samples, cid, *, scope=CPU_SCOPE):
    """Prove CPU collection during the existing warmup before long admission.

    Before/after snapshots may bound a short warmup. No sleep, extra inference,
    synthetic counters or telemetry retry is performed here. Isolated missing
    snapshots are retained as gaps while stable valid endpoints may span them.
    """
    required_vcpus = _required_vcpus(scope)
    expected = {'cpu'} | {'cpu' + str(i) for i in range(required_vcpus)}
    gaps, intervals, previous = [], [], None
    observed_threads = {}
    for index, current in enumerate(samples):
        causes = []
        if current.get('sample_kind') != 'cpu_budget':
            causes.append('cpu_collector_unavailable:' + str(current.get('reason') or current.get('error_class') or 'missing_sample_kind'))
        start, finish, client = (current.get(key) for key in ('timestamp_monotonic_s',
            'collection_finished_monotonic_s', 'client_observed_monotonic_s'))
        hz = current.get('clock_ticks_per_second')
        if not (_finite(start) and _finite(finish) and finish >= start and _finite(client)
                and _finite(hz) and hz > 0):
            causes.append('sample_clock_or_tick_rate_unavailable')
        group = current.get('cgroups', {}).get(cid, {})
        if group.get('identity') is None or _delta(group, group, ('usage_usec',)) is None:
            causes.append('owned_cgroup.identity_or_usage_usec_unavailable')
        processes = current.get('processes', {}).get(cid, [])
        if not processes:
            causes.append('owned_process_inventory_unavailable')
        for process in processes:
            if (type(process.get('pid')) is not int or type(process.get('starttime_ticks')) is not int
                    or process.get('generation_stable') is not True
                    or _delta(process, process, ('utime_ticks', 'stime_ticks')) is None):
                causes.append('owned_process.' + str(process.get('pid')) + '.identity_or_cpu_time_unavailable')
            observed_threads[str(process.get('pid'))] = {'num_threads': process.get('num_threads'),
                'status': process.get('runtime_thread_count_status', STATUS)}
        cpus = current.get('guest_cpus', {})
        if set(cpus) != expected:
            causes.append('exact_' + str(required_vcpus) + '_guest_vcpu_inventory_unavailable')
        elif any(_delta(cpus[cpu], cpus[cpu], CPU_KEYS) is None for cpu in expected):
            causes.append('guest_vcpu_counter_unavailable')
        if causes:
            gaps.append({'sample_index': index, 'causes': causes,
                         'missing_reads': current.get('missing_reads', [])})
            continue
        if previous is not None:
            earlier, prior_index = previous
            before = earlier['cgroups'][cid]
            before_processes = {p['pid']: p for p in earlier['processes'][cid]}
            after_processes = {p['pid']: p for p in processes}
            stable = (before['identity'] == group['identity'] and set(before_processes) == set(after_processes)
                and all(before_processes[pid]['starttime_ticks'] == after_processes[pid]['starttime_ticks']
                        for pid in before_processes))
            elapsed = (start + finish - earlier['timestamp_monotonic_s'] - earlier['collection_finished_monotonic_s']) / 2
            if not stable:
                causes.append('owned_cgroup_or_process_identity_changed')
            if (elapsed <= 0 or client <= earlier['client_observed_monotonic_s']
                    or hz != earlier['clock_ticks_per_second']):
                causes.append('nonpositive_elapsed_or_changed_tick_rate')
            cg = _delta(before, group, ('usage_usec',))
            process_deltas = [_delta(before_processes[pid], after_processes.get(pid, {}), ('utime_ticks', 'stime_ticks'))
                              for pid in before_processes]
            if cg is None or any(delta is None for delta in process_deltas):
                causes.append('owned_cpu_counter_regression_or_unavailable')
            if any(_delta(earlier['guest_cpus'][cpu], cpus[cpu], CPU_KEYS) is None for cpu in expected):
                causes.append('guest_vcpu_counter_regression_or_unavailable')
            if causes:
                gaps.append({'sample_index': index, 'prior_sample_index': prior_index, 'causes': causes})
            else:
                process_time = sum(sum(delta.values()) for delta in process_deltas) / hz
                intervals.append({'before_sample_index': prior_index, 'after_sample_index': index,
                    'host_elapsed_s': elapsed, 'cgroup_cpu_time_s': cg['usage_usec'] / 1e6,
                    'process_cpu_time_s': process_time,
                    'all_' + str(required_vcpus) + '_guest_vcpu_deltas_available': True,
                    'isolated_gap_count': index-prior_index-1})
        previous = current, index
    active = [row for row in intervals if row['cgroup_cpu_time_s'] > 0 and row['process_cpu_time_s'] > 0]
    cause = (None if active else 'model_cpu_usage_not_positive' if intervals else
             'cpu_collector_unavailable_throughout_warmup' if previous is None else
             'two_current_same_identity_cpu_snapshots_required')
    return {'status': 'PASS' if active else STATUS, 'cause': cause,
        'sample_count': len(samples), 'valid_interval_count': len(intervals),
        'positive_model_cpu_interval_count': len(active), 'intervals': intervals, 'isolated_gaps': gaps,
        'runtime_threads_by_pid': observed_threads,
        'thread_count_scope': 'per-process num_threads from existing stat read; Q8 is permitted vCPU budget, not runtime thread count',
        'scope': 'existing discarded warmup endpoints; no additional inference, waiting or output extension',
        'failure_action': None if active else 'STOP_BEFORE_LONG_REQUESTS'}
