"""Optional, root-reviewed R6 CPU profiling of the second short decode only."""
import contextlib
import datetime
import os
import signal
import subprocess
import threading
import time

EVENTS = 'task-clock,context-switches,cpu-migrations,page-faults,cycles,instructions,cache-references,cache-misses'


class Perf:
    def __init__(self, h, pid, log):
        self.h, self.pid, self.log = h, int(pid), log
        self.stack = contextlib.ExitStack()
        self.children = []
        self.error = None
        self.timer = None
        self.file = None
        self.lock = threading.Lock()
        self.started = None

    def _drain(self, item):
        try:
            size = 0
            while True:
                chunk = item['process'].stderr.read1(65536)
                if not chunk:
                    return
                size += len(chunk)
                if size > 1024 * 1024:
                    item['error'] = 'stderr_bound'
                    item['process'].send_signal(signal.SIGINT)
                    return
                item['chunks'].append(chunk)
        except Exception as exc:
            item['error'] = type(exc).__name__

    def _launch(self, name, argv, fds=()):
        p = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                             pass_fds=fds)
        item = {'name': name, 'argv': argv, 'process': p, 'chunks': [], 'error': None}
        self.children.append(item)
        item['thread'] = threading.Thread(target=self._drain, args=(item,), daemon=True)
        item['thread'].start()

    def _stop(self):
        with self.lock:
            # Signal all exact children before bounded waits; never signal native PID.
            for item in self.children:
                p = item['process']
                if p.poll() is None:
                    try:
                        p.send_signal(signal.SIGINT)
                    except ProcessLookupError:
                        pass
                    except OSError as exc:
                        item['error'] = type(exc).__name__
            for item in self.children:
                p = item['process']
                try:
                    p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    try:
                        p.kill()
                    except ProcessLookupError:
                        pass
                    except OSError as exc:
                        item['error'] = type(exc).__name__
                    try:
                        p.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        item['error'] = 'profiler_child_unsettled'
                except OSError as exc:
                    item['error'] = type(exc).__name__

    def start(self):
        self.started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            # Boundary transaction ends before any profiler starts.
            with self.h.transaction():
                self.h.s.root_payload_guard()
            guard = self.stack.enter_context(self.h.MountedStorageGuard(self.h.s))
            anchor = self.stack.enter_context(self.h.AnchoredRoot(self.log, guard))
            self.file = self.stack.enter_context(anchor.open('PROFILE128-perf.data',
                        os.O_RDWR | os.O_CREAT | os.O_EXCL))
            fd = self.file.fileno()
            # The systemd owner is already root. No sudo helper or permission changes.
            self.timer = threading.Timer(240, self._stop)
            self.timer.daemon = True
            self.timer.start()
            self._launch('stat', ['perf', 'stat', '-p', str(self.pid), '-e', EVENTS])
            self._launch('record', ['perf', 'record', '-F', '49', '-e', 'cpu-clock',
                         '--call-graph', 'fp', '-p', str(self.pid), '-B', '-N',
                         '-o', '/proc/self/fd/' + str(fd)], (fd,))
            time.sleep(.2)  # Detect immediate unsupported/permission failures, no retry.
        except Exception as exc:
            self.error = type(exc).__name__
        return self

    def available(self):
        """Pre-request liveness only, never proof that counters are supported."""
        return self.error is None and any(x['process'].poll() is None for x in self.children)

    def finish(self):
        rows, report = [], {'status': 'UNAVAILABLE', 'reason': 'record_not_available'}
        if self.timer:
            self.timer.cancel()
        try:
            self._stop()
            for item in self.children:
                item['thread'].join(timeout=1)
                p = item['process']
                raw = b''.join(list(item['chunks'])).decode(errors='replace')
                reason = item['error']
                if p.poll() is None or item['thread'].is_alive():
                    reason = reason or 'profiler_not_settled_or_drained'
                if p.returncode not in [0, -signal.SIGINT]:
                    reason = reason or 'profiler_exit_' + str(p.returncode)
                if any(x in raw.lower() for x in ['<not supported>', '<not counted>', 'permission', 'access denied']):
                    reason = reason or 'unsupported_or_unavailable_counters'
                rows.append({'name': item['name'], 'argv': item['argv'], 'pid': p.pid,
                             'exit_code': p.returncode, 'raw_stderr': raw,
                             'settled': p.poll() is not None,
                             'status': 'UNAVAILABLE' if reason else 'AVAILABLE', 'reason': reason})
            if self.file:
                self.file.check()
                if any(r['name'] == 'record' and r['status'] == 'AVAILABLE' for r in rows):
                    fd = self.file.fileno()
                    argv = ['perf', 'report', '--stdio', '--no-children', '--sort', 'symbol',
                            '--call-graph', 'none', '--percent-limit', '0.5',
                            '--symfs', '/proc/' + str(self.pid) + '/root',
                            '-i', '/proc/self/fd/' + str(fd)]
                    r = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       pass_fds=(fd,), timeout=15)
                    report = {'status': 'AVAILABLE' if r.returncode == 0 else 'UNAVAILABLE',
                              'argv': argv, 'exit_code': r.returncode,
                              'raw_stdout': r.stdout.decode(errors='replace'),
                              'raw_stderr': r.stderr.decode(errors='replace')}
                self.file.check()
            with self.h.transaction():
                self.h.s.root_payload_guard()
        except Exception as exc:
            self.error = type(exc).__name__
        finally:
            try:
                self.stack.close()
            except Exception as exc:
                self.error = type(exc).__name__
        return {'status': 'AVAILABLE' if not self.error and any(r['status'] == 'AVAILABLE' for r in rows) else 'UNAVAILABLE',
                'reason': self.error, 'started_utc': self.started,
                'finished_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'attach_pid': self.pid, 'max_seconds': 240, 'collectors': rows, 'report': report,
                'scope': 'CPU samples/counters only; cache misses are not host DRAM GB/s.',
                'data_file': self.log + '/PROFILE128-perf.data'}
