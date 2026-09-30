"""Bounded, read-only guest task affinity evidence sampled after FIRST_OUTPUT.

The caller starts this optional thread at FIRST_OUTPUT and saves finish()'s JSON
outside the streaming path. No request, lifecycle, guard, or storage operations.
"""
import datetime
import math
import os
import pathlib
import threading
import time

SAMPLE_OFFSETS = (0.0, 0.5, 1.0, 2.0, 3.0)
STEADY_WINDOW_START_OFFSET = 0.5
MAX_TIDS = 512
MAX_FILE_BYTES = 16384


def _utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='microseconds')


def _read(path):
    with path.open() as stream:
        text = stream.read(MAX_FILE_BYTES + 1)
    if len(text) > MAX_FILE_BYTES:
        raise ValueError('proc_file_bound')
    return text


def parse_stat(text):
    # comm may itself contain spaces and parentheses. Remaining indexes start at
    # field 3 (state); utime/stime=14/15, starttime=22, processor=39.
    fields = text.rsplit(')', 1)[1].split()
    return {'utime_ticks': int(fields[11]), 'stime_ticks': int(fields[12]),
            'starttime_ticks': int(fields[19]), 'last_cpu': int(fields[36])}


def parse_cpu_list(text):
    cpus = set()
    for part in text.strip().split(','):
        ends = part.split('-')
        if len(ends) == 1:
            lo = hi = int(ends[0])
        elif len(ends) == 2:
            lo, hi = map(int, ends)
        else:
            raise ValueError('invalid_cpu_list')
        if not 0 <= lo <= hi < 4096:
            raise ValueError('cpu_list_bound')
        cpus.update(range(lo, hi + 1))
    return sorted(cpus)


def task_snapshot(pid, proc_root='/proc'):
    """At most 512 tasks, two small files per task; no memory map scans."""
    start = time.monotonic()
    base = pathlib.Path(proc_root) / str(pid)
    process_start = parse_stat(_read(base / 'stat'))['starttime_ticks']
    tasks, errors, tids = [], [], []
    with os.scandir(base / 'task') as entries:
        for entry in entries:
            if entry.name.isdecimal():
                tids.append(int(entry.name))
                if len(tids) > MAX_TIDS:
                    raise ValueError('task_count_bound')
    for tid in sorted(tids):
        task = base / 'task' / str(tid)
        try:
            stat = parse_stat(_read(task / 'stat'))
            status = _read(task / 'status')
            allowed = next(line.split(':', 1)[1].strip() for line in status.splitlines()
                           if line.startswith('Cpus_allowed_list:'))
            tasks.append({'tid': tid, **stat, 'allowed_cpu_list': allowed,
                          'allowed_cpus': parse_cpu_list(allowed)})
        except (OSError, ValueError, IndexError, StopIteration) as exc:
            errors.append({'tid': tid, 'error_type': type(exc).__name__})
    if parse_stat(_read(base / 'stat'))['starttime_ticks'] != process_start:
        raise ValueError('native_pid_reused')
    return {'started_monotonic_seconds': start, 'finished_monotonic_seconds': time.monotonic(),
            'utc': _utc(), 'native_starttime_ticks': process_start, 'tasks': tasks,
            'task_read_errors': errors}


def _summarize_window(snapshots, first_output, last_output, expected_cpus, clock_ticks):
    """Only whole snapshots inside the output interval can establish activity."""
    valid = [s for s in snapshots if s['started_monotonic_seconds'] >= first_output
             and s['finished_monotonic_seconds'] <= last_output]
    out = {'qualified_snapshot_count': len(valid), 'all_advancing_tasks': [],
           'substantial_tasks': [], 'singleton_decode_candidates': [],
           'expected_decode_candidate_count': len(expected_cpus),
           'status': 'INCONCLUSIVE',
           'claim_limit': 'Guest placement observations, not source worker identity or physical GPU locality. '
                          'CPU ticks establish activity only within the sampled output interval.'}
    if not expected_cpus or len(set(expected_cpus)) != len(expected_cpus):
        out['reason'] = 'empty_or_duplicate_expected_cpu_configuration'
        return out
    if len(valid) < 2:
        out['reason'] = 'fewer_than_two_whole_snapshots_during_output'
        return out
    if len({s['native_starttime_ticks'] for s in valid}) != 1:
        out['reason'] = 'native_pid_identity_changed'
        return out
    elapsed = valid[-1]['finished_monotonic_seconds'] - valid[0]['finished_monotonic_seconds']
    if elapsed <= 0:
        out['reason'] = 'nonpositive_sample_interval'
        return out
    # Require >=100ms CPU and >=10% of a CPU across the sample, in addition to
    # preserving every task with any advancing tick separately.
    threshold = max(math.ceil(clock_ticks * 0.1), math.ceil(elapsed * clock_ticks * 0.1))
    histories = {}
    for sample in valid:
        for task in sample['tasks']:
            histories.setdefault((task['tid'], task['starttime_ticks']), []).append(task)
    for (tid, starttime), history in sorted(histories.items()):
        if len(history) < 2:
            continue
        first, last = history[0], history[-1]
        user = last['utime_ticks'] - first['utime_ticks']
        system = last['stime_ticks'] - first['stime_ticks']
        if user < 0 or system < 0 or user + system == 0:
            continue
        masks = sorted({tuple(t['allowed_cpus']) for t in history})
        row = {'tid': tid, 'starttime_ticks': starttime,
               'user_tick_delta': user, 'system_tick_delta': system,
               'cpu_seconds': (user + system) / clock_ticks,
               'allowed_cpu_observations': [list(mask) for mask in masks],
               'last_cpu_observations': sorted({t['last_cpu'] for t in history}),
               'snapshot_observations': len(history),
               'substantial_activity': user + system >= threshold}
        out['all_advancing_tasks'].append(row)
        if row['substantial_activity']:
            out['substantial_tasks'].append(row)
            if (len(history) == len(valid) and len(masks) == 1 and len(masks[0]) == 1
                    and masks[0][0] in expected_cpus):
                out['singleton_decode_candidates'].append(row)
    candidates = out['singleton_decode_candidates']
    observed = [row['allowed_cpu_observations'][0][0] for row in candidates]
    complete_reads = all(not s['task_read_errors'] for s in valid)
    matches = len(candidates) == len(expected_cpus) and sorted(observed) == sorted(expected_cpus)
    out.update(sample_interval_seconds=elapsed, substantial_threshold_ticks=threshold,
               substantial_threshold_rule='max(0.1 CPU seconds, 10 percent of sampled wall interval)',
               advancing_tid_count=len(out['all_advancing_tasks']),
               substantial_tid_count=len(out['substantial_tasks']),
               singleton_decode_candidate_count=len(candidates),
               expected_singleton_candidates_observed=matches and complete_reads,
               exact_configured_substantially_active_tids=(matches and complete_reads
                      and len(out['substantial_tasks']) == len(expected_cpus)))
    if not complete_reads:
        out['reason'] = 'some_task_reads_unavailable'
    elif matches:
        out['status'] = 'EXPECTED_SINGLETON_CANDIDATES_OBSERVED'
        out['reason'] = 'Candidate mapping is measured; source worker roles remain unproven.'
    else:
        out['reason'] = 'configured_expected_substantial_singleton_candidates_not_established'
    return out


def summarize(snapshots, first_output, last_output, expected_cpus, clock_ticks):
    """Keep transition evidence; separately assess a fixed later bounded window.

    The later window always begins at FIRST_OUTPUT + 0.5s. It is never selected
    adaptively to discard a failed sample and never upgrades the full-window
    status. The existing five bounded snapshots are the only observations.
    """
    out = _summarize_window(snapshots, first_output, last_output, expected_cpus, clock_ticks)
    out['window_scope'] = 'full_sampled_output_interval_including_initial_transition'
    steady = _summarize_window(snapshots, first_output + STEADY_WINDOW_START_OFFSET,
                               last_output, expected_cpus, clock_ticks)
    steady['window_start_offset_seconds'] = STEADY_WINDOW_START_OFFSET
    steady['window_scope'] = 'fixed_later_sampled_output_interval_only'
    out['steady_bounded_window'] = steady
    return out


class DecodeAffinity:
    def __init__(self, native_pid, expected_cpus, configured_batch_cpus, proc_root='/proc'):
        self.pid = int(native_pid)
        self.expected_cpus = sorted(expected_cpus)
        self.batch_cpus = sorted(set(configured_batch_cpus))
        self.proc_root = proc_root
        self.snapshots = []
        self.errors = []
        self.stop = threading.Event()
        self.thread = None
        self.first_utc = None
        self.first_mono = None
        self.clock_ticks = os.sysconf('SC_CLK_TCK')

    def start(self, first_output_utc, first_output_monotonic_seconds):
        """Nonblocking; all /proc reads are in the independent daemon thread."""
        if self.thread is not None:
            return
        self.first_utc = first_output_utc
        self.first_mono = first_output_monotonic_seconds
        self.thread = threading.Thread(target=self._run, name='h016-decode-affinity', daemon=True)
        try:
            self.thread.start()
        except Exception as exc:
            self.errors.append({'phase': 'thread_start', 'error_type': type(exc).__name__})
            self.thread = None

    def _run(self):
        try:
            for offset in SAMPLE_OFFSETS:
                delay = max(0, self.first_mono + offset - time.monotonic())
                if self.stop.wait(delay):
                    break
                # Avoid a delayed diagnostic becoming an unbounded later scan.
                if time.monotonic() > self.first_mono + SAMPLE_OFFSETS[-1] + 0.5:
                    self.errors.append({'phase': 'sample', 'error_type': 'sampling_deadline'})
                    break
                self.snapshots.append(task_snapshot(self.pid, self.proc_root))
        except Exception as exc:
            self.errors.append({'phase': 'sample', 'error_type': type(exc).__name__})

    def finish(self, last_output_monotonic_seconds=None):
        """Call after stream drain/failure; bounded join, no request failure."""
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=2.0)
        alive = self.thread is not None and self.thread.is_alive()
        result = {'schema': 'h016-affinity14-decode-v1', 'native_pid': self.pid,
                  'scope': 'guest CPU placement only', 'clock_ticks_per_second': self.clock_ticks,
                  'first_output_utc': self.first_utc,
                  'first_output_monotonic_seconds': self.first_mono,
                  'last_output_monotonic_seconds': last_output_monotonic_seconds,
                  'configured_decode_cpus': self.expected_cpus,
                  'configured_batch_cpus': self.batch_cpus,
                  'batch_claim': 'Configuration only; decode-window task masks do not establish active batch workers.',
                  'maximum_tids': MAX_TIDS, 'sample_offsets_seconds': list(SAMPLE_OFFSETS),
                  'snapshots': list(self.snapshots), 'errors': list(self.errors),
                  'diagnostic_thread_alive': alive}
        if alive or self.errors or self.first_mono is None or last_output_monotonic_seconds is None:
            result.update(status='UNAVAILABLE', reason='diagnostic_error_or_missing_output_boundary')
        else:
            result.update(summarize(result['snapshots'], self.first_mono,
                                    last_output_monotonic_seconds, self.expected_cpus, self.clock_ticks))
        return result
