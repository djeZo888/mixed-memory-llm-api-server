"""One optional protected CPU sample; no model launch, mutation, or CUDA runner.

The caller owns the lifecycle lease and live GO. Perf receives signals only on
its own Popen handle, never the target. All trace bytes stay in registered logs.
"""
from __future__ import annotations

import copy
import math
import os
from pathlib import Path
import secrets
import signal
import subprocess
import threading
import time

from .decode_diag import capture_is_decode
from .lifecycle import require

TRACE_LIMIT = 1023 * 1024**2
STDERR_LIMIT = 64 * 1024
MAX_CAPTURE_SECONDS = 5.0
# Leave one second for SIGINT flush, then kill only the profiler if needed.
SAMPLE_SECONDS = 4.0
PERF = '/usr/bin/perf'
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'}
LAUNCHER = '''import ctypes,os,resource,signal,sys
parent=os.getppid()
resource.setrlimit(resource.RLIMIT_FSIZE,(int(sys.argv[1]),int(sys.argv[1])))
if ctypes.CDLL(None).prctl(1,signal.SIGKILL,0,0,0) != 0 or os.getppid()!=parent:
    sys.exit(125)
os.execv(sys.argv[2],sys.argv[2:])
'''


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def client_progress(value):
    """Allowlist only; event counts establish progress and are never tokens."""
    value = value if isinstance(value, dict) else {}
    return {key: value.get(key) for key in (
        'monotonic_s', 'request_started_monotonic_s', 'first_output_monotonic_s',
        'last_output_monotonic_s', 'output_event_count', 'native_predicted_n',
        'capture_start_rpc_before_monotonic_s', 'capture_complete_rpc_after_monotonic_s')}


def positive_client(value):
    return (all(finite(value.get(k)) for k in ('monotonic_s', 'request_started_monotonic_s',
            'first_output_monotonic_s', 'last_output_monotonic_s'))
        and value['request_started_monotonic_s'] <= value['first_output_monotonic_s']
        <= value['last_output_monotonic_s'] <= value['monotonic_s']
        and type(value.get('output_event_count')) is int and value['output_event_count'] > 0
        and type(value.get('native_predicted_n')) is int and value['native_predicted_n'] > 0)


def client_bracket(before, after):
    """Both boundaries are worker-clock RPC witnesses; host clocks never mix."""
    left = after.get('capture_start_rpc_before_monotonic_s')
    right = after.get('capture_complete_rpc_after_monotonic_s')
    return (positive_client(before) and positive_client(after)
        and before['request_started_monotonic_s'] == after['request_started_monotonic_s']
        and finite(left) and finite(right)
        and before['last_output_monotonic_s'] <= before['monotonic_s'] <= left < right
        < after['last_output_monotonic_s'] <= after['monotonic_s']
        and after['output_event_count'] > before['output_event_count']
        and after['native_predicted_n'] > before['native_predicted_n'])


def target_identity(host, cid):
    _container, _cgroup, pids = host.identity(cid)
    matches = []
    for pid in pids:
        base = Path('/proc') / str(pid)
        if Path(os.readlink(base / 'exe')).name == 'llama-server':
            start = int((base / 'stat').read_text().split(') ', 1)[1].split()[19])
            matches.append({'pid': pid, 'starttime_ticks': start})
    require(len(matches) == 1, 'decode_capture_unique_native_pid_required')
    return matches[0]


def perf_argv(pid):
    require(type(pid) is int and pid > 0, 'decode_capture_pid_required')
    return ['/usr/bin/python3', '-I', '-B', '-c', LAUNCHER, str(TRACE_LIMIT), PERF,
            'record', '-e', 'cpu-clock:u', '-F', '49', '-p', str(pid),
            '--clockid', 'mono', '--no-buildid-cache', '-o', '-']


class CpuCapture:
    def __init__(self, host, cid, before):
        self.host, self.cid = host, cid
        self.client_before = client_progress(before)
        require(positive_client(self.client_before), 'decode_capture_positive_output_required')
        self.capture_id = 'cpu-' + secrets.token_hex(12)
        self.cancel = threading.Event()
        self.lock = threading.Lock()
        self.result = {'capture_id': self.capture_id, 'kind': 'cpu_perf', 'capture_complete': False,
                       'status': 'STARTING', 'host_valid': False, 'target_alive': None,
                       'safety_stop_required': False, 'sse_events_are_not_tokens': True,
                       'maximum_capture_seconds': MAX_CAPTURE_SECONDS,
                       'requested_sample_seconds': SAMPLE_SECONDS,
                       'maximum_trace_bytes': TRACE_LIMIT,
                       'symbol_resolution': 'NOT_INSPECTED_PRIVATE_TRACE',
                       'cuda_capture': 'NOT_IMPLEMENTED_INSTALLED_CLI_REVIEW_REQUIRED'}
        self.thread = threading.Thread(target=self._run, name=self.capture_id, daemon=True)

    def start(self):
        self.thread.start()
        return self.status()

    def status(self, after=None):
        with self.lock:
            result = copy.deepcopy(self.result)
        result['client_valid'] = bool(result['capture_complete'] and
            client_bracket(self.client_before, client_progress(after)))
        result['decode_contained'] = bool(result['host_valid'] and result['client_valid'])
        return result

    def stop(self):
        self.cancel.set()
        self.thread.join(timeout=15)
        require(not self.thread.is_alive(), 'decode_capture_stop_incomplete')

    def _run(self):
        host, result, target, process = self.host, dict(self.result), None, None
        stage, started, ended = 'guards', None, None
        stderr = bytearray()
        reader = None
        try:
            host.guards(host.owner.lease)
            require(host.budget.checkpoint() >= 15, 'STOP_BUDGET')
            stage = 'identity'
            target = target_identity(host, self.cid)
            result['target'] = target
            suffix = host.campaign + '/private-captures/' + self.capture_id
            stage = 'storage'
            with host.binding.mounted_guard(host.storage_io, roles=('data',)) as guard:
                with host.storage_io.AnchoredRoot(host.binding.path('logs'), guard) as anchor:
                    anchor.mkdir(suffix, mode=0o700, parents=True)
                    with anchor.open(suffix + '/perf.data', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) as out:
                        stage = 'native_before'
                        before = host.decode_progress(self.cid)
                        result['before'] = before
                        require(before.get('is_processing') is True and type(before.get('n_decoded')) is int
                                and before['n_decoded'] > 0 and type(before.get('slot_id')) is int
                                and type(before.get('task_id')) is int, 'decode_capture_native_progress_required')
                        require(target_identity(host, self.cid) == target, 'decode_capture_target_changed')
                        require(not self.cancel.is_set(), 'decode_capture_cancelled')
                        stage = 'profiler'
                        started = time.monotonic()
                        process = subprocess.Popen(perf_argv(target['pid']), stdin=subprocess.DEVNULL,
                            stdout=out.fileno(), stderr=subprocess.PIPE, env=ENV, start_new_session=True)
                        def drain():
                            while True:
                                block = process.stderr.read(4096)
                                if not block:
                                    break
                                if len(stderr) < STDERR_LIMIT:
                                    stderr.extend(block[:STDERR_LIMIT - len(stderr)])
                        reader = threading.Thread(target=drain, daemon=True)
                        reader.start()
                        interrupted = False
                        while process.poll() is None:
                            elapsed = time.monotonic() - started
                            if (self.cancel.is_set() or elapsed >= SAMPLE_SECONDS) and not interrupted:
                                process.send_signal(signal.SIGINT)
                                interrupted = True
                            if elapsed >= MAX_CAPTURE_SECONDS:
                                process.kill()
                                result['profiler_forced_stop'] = True
                                break
                            stage = 'storage'
                            host.owner.lease.validate()
                            require(out.check().st_size <= TRACE_LIMIT, 'decode_capture_trace_bound')
                            stage = 'profiler'
                            time.sleep(0.1)
                        process.wait(timeout=1)
                        ended = time.monotonic()
                        reader.join(timeout=1)
                        result.update(profiler_returncode=process.returncode,
                                      private_trace_relative_path=suffix + '/perf.data',
                                      trace_bytes=out.check().st_size)
                        stage = 'native_after'
                        after = host.decode_progress(self.cid)
                        result['after'] = after
                        result['host_valid'] = (capture_is_decode(before, after, started, ended)
                            and interrupted and ended - started >= SAMPLE_SECONDS and result['trace_bytes'] > 0
                            and ended - started <= MAX_CAPTURE_SECONDS + 0.25
                            and process.returncode in (0, -signal.SIGINT)
                            and not self.cancel.is_set() and not result.get('profiler_forced_stop'))
                        stage = 'storage'
                        out.fsync()
                    stage = 'storage'
                    with anchor.open(suffix + '/perf.stderr', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) as err:
                        err.write(bytes(stderr)); err.fsync()
                    anchor.check()
            result['status'] = 'CAPTURED' if result['host_valid'] else 'UNAVAILABLE'
        except Exception as exc:
            result.update(status='UNAVAILABLE', error_class=type(exc).__name__, error_stage=stage)
            # Only registered-storage/lease/budget failures are safety failures;
            # missing counters, profiler errors and unsupported events are optional.
            result['safety_stop_required'] = stage in {'guards', 'storage'}
        finally:
            try:
                if process is not None and process.poll() is None:
                    process.send_signal(signal.SIGINT)
                    try:
                        process.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=1)
            except Exception as exc:
                result.update(host_valid=False, safety_stop_required=True,
                              profiler_cleanup_error_class=type(exc).__name__)
            if process is not None and ended is None:
                ended = time.monotonic()
            if reader is not None:
                reader.join(timeout=1)
            if process is not None and process.stderr is not None and (reader is None or not reader.is_alive()):
                process.stderr.close()
            result['profiler_alive'] = process is not None and process.poll() is None
            if result['profiler_alive']:
                result.update(host_valid=False, safety_stop_required=True)
            try:
                result['target_alive'] = target is not None and target_identity(host, self.cid) == target
            except Exception as exc:
                result.update(target_alive=False, survival_error_class=type(exc).__name__)
            if target is not None and result['target_alive'] is not True:
                result['safety_stop_required'] = True
                result['host_valid'] = False
            try:
                host.guards(host.owner.lease)
            except Exception as exc:
                result.update(safety_stop_required=True, host_valid=False,
                              post_guard_error_class=type(exc).__name__)
            result.update(capture_complete=True, started_monotonic_s=started, ended_monotonic_s=ended)
            with self.lock:
                self.result = result


def stop_captures(host, cid=None):
    for capture in getattr(host, '_decode_cpu_captures', {}).values():
        if cid is None or capture.cid == cid:
            capture.stop()
