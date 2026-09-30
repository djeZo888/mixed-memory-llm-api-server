"""Optional R6 request activity; buffered counters, never a safety guard."""
import datetime
import os
import pathlib
import subprocess
import threading
import time

GPU_ARGV = ['nvidia-smi', 'dmon', '-i', 'GPU-69acfa26-8b60-61b5-702d-aee252c163cc',
            '-s', 'ut', '-d', '5', '-c', '240', '-o', 'DT']


def boundary(pid, cgroup):
    """One cheap optional boundary snapshot; no sampler or GPU command starts."""
    activity = Activity(pid, cgroup)
    try:
        activity._sample('boundary')
        return {'status': 'AVAILABLE', 'clock_ticks_per_second': os.sysconf('SC_CLK_TCK'),
                **activity.samples[0]}
    except Exception as exc:
        return {'status': 'UNAVAILABLE', 'reason': type(exc).__name__}


class Activity:
    """Call start before the request, finish after full drain; save at boundary."""

    def __init__(self, pid, cgroup):
        self.pid = int(pid)
        self.proc = pathlib.Path('/proc', str(self.pid))
        self.cgroup = pathlib.Path(cgroup)
        self.samples = []
        self.identity = None
        self.error = None
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.gpu = None
        self.gpu_thread = None
        self.gpu_chunks = []
        self.gpu_error = None
        self.gpu_started_utc = None

    def _gpu_drain(self):
        size = 0
        try:
            while True:
                chunk = self.gpu.stdout.read1(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > 1024 * 1024:
                    self.gpu_error = 'optional_dmon_output_bound'
                    self.gpu.terminate()
                    break
                self.gpu_chunks.append(chunk)
        except Exception as exc:
            self.gpu_error = type(exc).__name__

    def _gpu_finish(self):
        if self.gpu is not None and self.gpu.poll() is None:
            try:
                self.gpu.terminate()
                self.gpu.wait(timeout=1)
            except subprocess.TimeoutExpired:
                try:
                    self.gpu.kill()
                    self.gpu.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.gpu_error = 'optional_dmon_unsettled'
            except OSError as exc:
                self.gpu_error = type(exc).__name__
        if self.gpu_thread is not None:
            self.gpu_thread.join(timeout=1)
        settled = self.gpu is not None and self.gpu.poll() is not None
        drained = self.gpu_thread is not None and not self.gpu_thread.is_alive()
        if drained:
            self.gpu.stdout.close()
        raw = b''.join(list(self.gpu_chunks)).decode(errors='replace')
        lines = [line for line in raw.splitlines() if line.strip() and not line.lstrip().startswith('#')]
        unsupported = any(token in {'-', 'N/A'} for line in lines for token in line.split())
        reason = self.gpu_error
        if not reason and (not settled or not drained):
            reason = 'optional_dmon_not_settled_and_drained'
        if not reason and not lines:
            reason = 'optional_dmon_no_samples'
        if not reason and unsupported:
            reason = 'unsupported_fields_in_raw_dmon'
        if not reason and self.gpu.returncode not in [0, -15, -9]:
            reason = 'optional_dmon_nonzero_exit'
        return {'status': 'UNAVAILABLE' if reason else 'AVAILABLE', 'reason': reason,
                'argv': GPU_ARGV, 'pid': self.gpu.pid if self.gpu else None,
                'started_utc': self.gpu_started_utc,
                'finished_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'exit_code': self.gpu.returncode if self.gpu else None,
                'sampler_settled': settled, 'pipe_drained': drained, 'raw': raw,
                'scope': 'Utilization and PCIe Rx/Tx only; retain emitted units and local date/time exactly. PCIe throughput is not GPU VRAM bandwidth.'}

    def _sample(self, phase):
        # stat field 22 (starttime) distinguishes reuse of the same numeric PID.
        fields = (self.proc / 'stat').read_text().rsplit(')', 1)[1].split()
        identity = {'pid': self.pid, 'start_ticks': int(fields[19])}
        if self.identity is None:
            self.identity = identity
        elif identity != self.identity:
            raise RuntimeError('native_generation_changed')
        row = {
            'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'monotonic_seconds': time.monotonic(),
            'phase': phase,
            'native_identity': identity,
            'process': {
                'utime_ticks': int(fields[11]), 'stime_ticks': int(fields[12]),
                'minor_faults': int(fields[7]), 'major_faults': int(fields[9]),
                'io': {key.rstrip(':'): int(value) for key, value in
                       (line.split() for line in (self.proc / 'io').read_text().splitlines())},
            },
            'cgroup': {},
        }
        for name in ['cpu.stat', 'memory.events']:
            row['cgroup'][name] = {key: int(value) for key, value in
                                   (line.split() for line in (self.cgroup / name).read_text().splitlines())}
        for name in ['memory.current', 'memory.swap.current']:
            row['cgroup'][name] = int((self.cgroup / name).read_text())
        row['cgroup']['io.stat'] = {
            fields[0]: {key: int(value) for key, value in
                        (entry.split('=', 1) for entry in fields[1:])}
            for fields in (line.split() for line in (self.cgroup / 'io.stat').read_text().splitlines())
            if fields
        }
        # Recheck after the group of reads; never combine two process generations.
        after = (self.proc / 'stat').read_text().rsplit(')', 1)[1].split()
        if int(after[19]) != identity['start_ticks']:
            raise RuntimeError('native_generation_changed')
        row['sample_end_monotonic_seconds'] = time.monotonic()
        self.samples.append(row)

    def _run(self):
        try:
            self._sample('before')
            self.ready.set()
            while not self.stop.wait(1):
                if len(self.samples) >= 1200:
                    raise RuntimeError('optional_sampling_limit_1200')
                self._sample('periodic')
            self._sample('after')
        except Exception as exc:
            self.error = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        finally:
            self.ready.set()

    def start(self):
        try:
            self.thread.start()
            if not self.ready.wait(1):
                self.error = 'optional_first_sample_timeout'
                self.stop.set()
        except Exception as exc:
            self.error = type(exc).__name__
            self.ready.set()
        try:
            self.gpu = subprocess.Popen(GPU_ARGV, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT)
            self.gpu_started_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self.gpu_thread = threading.Thread(target=self._gpu_drain, daemon=True)
            self.gpu_thread.start()
        except Exception as exc:
            self.gpu_error = type(exc).__name__
        return self

    def finish(self):
        self.stop.set()
        if self.thread.ident is not None:
            self.thread.join(timeout=2)
        alive = self.thread.is_alive()
        samples = list(self.samples)
        reason = 'optional_sampler_still_running' if alive else self.error
        try:
            gpu = self._gpu_finish()
        except Exception as exc:
            gpu = {'status': 'UNAVAILABLE', 'reason': type(exc).__name__,
                   'argv': GPU_ARGV, 'pid': self.gpu.pid if self.gpu else None,
                   'sampler_settled': self.gpu is not None and self.gpu.poll() is not None,
                   'raw': b''.join(list(self.gpu_chunks)).decode(errors='replace')}
        return {
            'status': 'UNAVAILABLE' if reason else 'AVAILABLE',
            'reason': reason,
            'native_identity': self.identity,
            'clock_ticks_per_second': os.sysconf('SC_CLK_TCK'),
            'period_seconds': 1,
            'sampler_settled': not alive,
            'before': samples[0] if samples else None,
            'after': samples[-1] if samples and samples[-1]['phase'] == 'after' else None,
            'samples': samples,
            'scope': 'Native process CPU/fault/I/O and container counters; not host DRAM or GPU VRAM bandwidth.',
            'host_dram_gb_s': {'status': 'UNAVAILABLE', 'reason': 'No approved actual host memory-controller counter fixture.'},
            'gpu_vram_gb_s': {'status': 'UNAVAILABLE', 'reason': 'No approved actual GPU memory-byte counter fixture.'},
            'gpu_activity_pcie': gpu,
        }
