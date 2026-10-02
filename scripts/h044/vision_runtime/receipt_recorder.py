"""Original command receipts. SOURCE_ONLY tooling; never fabricates lost births/waits."""
import ctypes
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import struct
import subprocess
import sys
import time
import uuid


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(path):
    b = Path(path).read_bytes()
    return {'sha256': hashlib.sha256(b).hexdigest(), 'bytes': len(b)}


def birth(pid):
    """Kernel birth, including microseconds on Darwin (not ps second precision)."""
    if sys.platform == 'darwin':
        lib = ctypes.CDLL('/usr/lib/libproc.dylib')
        buf = ctypes.create_string_buffer(136)
        n = lib.proc_pidinfo(int(pid), 3, 0, buf, len(buf))
        if n != 136:
            return None
        seconds, micros = struct.unpack_from('QQ', buf.raw, 120)
        return {'kind': 'darwin-proc-bsdinfo', 'seconds': seconds, 'microseconds': micros}
    try:
        raw = Path('/proc/%d/stat' % pid).read_text()
        ticks = raw[raw.rfind(')') + 2:].split()[19]
        return {'kind': 'linux-proc-startticks', 'ticks': ticks,
                'bootId': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    except (OSError, IndexError):
        return None


def inventory(group=None):
    # Original independent ps read uses a gate too, so even a short probe has a
    # genuine kernel birth followed by a direct wait. No recursive recorder.
    readfd, writefd = os.pipe()
    argv = ['/bin/ps', '-axo', 'pid=,ppid=,pgid=,lstart=']
    p = None
    born = None
    started = utc()
    env = {'PATH':'/usr/bin:/bin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'}
    if os.environ.get('TMPDIR'): env['TMPDIR']=os.environ['TMPDIR']
    bootstrap = [sys.executable, '-I', '-c', _GATE, str(readfd), *argv]
    try:
        p = subprocess.Popen(bootstrap, env=env, cwd=os.getcwd(),
                             pass_fds=(readfd,), start_new_session=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        born = birth(p.pid)
        os.write(writefd, b'G'); os.close(writefd); writefd = None
        out, err = p.communicate(timeout=5)
    finally:
        if p is not None and p.returncode is None:
            p.kill(); p.communicate(timeout=5)
        os.close(readfd)
        if writefd is not None: os.close(writefd)
    rows = []
    for line in out.decode(errors='replace').splitlines():
        parts = line.strip().split(None, 3)
        if len(parts) == 4:
            try:
                row = {'pid': int(parts[0]), 'ppid': int(parts[1]),
                       'pgid': int(parts[2]), 'raw': line}
                if group is None or row['pgid'] == group:
                    row['birth'] = birth(row['pid'])
                    row['birthMissing'] = row['birth'] is None
                    rows.append(row)
            except ValueError:
                pass
    return {'utc': utc(), 'selectedGroup': group, 'rows': rows, 'probe': {'argv': argv,
            'bootstrapArgv':bootstrap,'cwd':os.getcwd(),'environment':env,'startUtc':started,'endUtc':utc(),'pid': p.pid, 'pgid': p.pid, 'birth': born, 'birthMissing': born is None,
            'actualExitCode': p.returncode, 'waited': True,
            'recordedBirthAbsent': born is not None and birth(p.pid) != born,
            'stdoutHex': out.hex(), 'stderrHex': err.hex()}}


_GATE = "import os,sys; f=int(sys.argv[1]); b=os.read(f,1); os.close(f); (os.execvpe(sys.argv[2],sys.argv[2:],os.environ) if b==b'G' else sys.exit(125))"


def record(argv, directory, *, cwd=None, environment=None, timeout=120,
           output_cap=16*1024*1024, label='command', fault=None, stdin_data=None, input_bindings=None, evidence='ACTUAL_LOCAL_SOURCE_COMMAND'):
    """Gate execution until genuine child birth is captured; always reap Popen.

    fault is an injected SOURCE fixture callback, not production evidence.
    Partial receipts retain exact missing fields and actual child exit.
    A direct unreaped child is safe to kill even if birth capture failed.
    Group signals require matching kernel birth and the created session group.
    """
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    stem = label + '-' + uuid.uuid4().hex
    paths = {x: directory / (stem + '.' + x) for x in ('stdout', 'stderr', 'receipt.json')}
    env = dict(environment if environment is not None else os.environ)
    receipt = {'schema': 'original-command-v1', 'evidence': evidence,
               'inputBindings': input_bindings, 'argv': list(argv), 'cwd': str(Path(cwd or os.getcwd()).resolve()),
               'environment': env, 'startUtc': utc(), 'endUtc': None,
               'pid': None, 'pgid': None, 'birth': None, 'waited': False,
               'actualExitCode': None, 'inventories': [], 'errors': [], 'missing': [],
               'socketPaths': [], 'timeoutSeconds': timeout, 'outputCapBytes': output_cap,
               'injectedFault': fault is not None, 'stdin': {'sha256': hashlib.sha256(stdin_data).hexdigest(), 'bytes': len(stdin_data)} if stdin_data is not None else None}
    child = None
    gate_r = gate_w = None
    streams = {}
    selector = selectors.DefaultSelector()
    remaining = []
    def inject(point):
        if fault:
            fault(point)
    def settle():
        # poll()/wait() on the original Popen are authoritative for this child;
        # neither a guessed PID nor a possibly reused external group is signalled.
        if child is not None and child.returncode is None:
            same = receipt['birth'] is not None and birth(child.pid) == receipt['birth']
            try:
                if same and receipt['pgid'] == child.pid and os.getpgid(child.pid) == child.pid:
                    os.killpg(child.pid, signal.SIGKILL)
                else:
                    child.kill()  # original, still-unreaped direct child only
            except ProcessLookupError:
                pass
        if child is not None:
            receipt['actualExitCode'] = child.wait(timeout=10)
            receipt['waited'] = True
    try:
        inject('before_logs')
        for key in ('stdout', 'stderr'):
            streams[key] = paths[key].open('xb')
            os.chmod(paths[key], 0o600)
        gate_r, gate_w = os.pipe()
        inject('before_popen')
        bootstrap = [sys.executable, '-I', '-c', _GATE, str(gate_r)] + list(argv)
        receipt['bootstrapArgv'] = bootstrap
        child = subprocess.Popen(bootstrap, cwd=receipt['cwd'], env=env,
                                 pass_fds=(gate_r,), start_new_session=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL)
        receipt['pid'] = child.pid
        inject('after_popen')
        receipt['pgid'] = os.getpgid(child.pid)
        inject('before_birth')
        receipt['birth'] = birth(child.pid)
        if receipt['birth'] is None:
            raise RuntimeError('kernel birth capture missing')
        inject('after_birth')
        first = inventory(receipt['pgid'])
        receipt['inventories'].append(first)
        inject('metadata_write')
        # Durable preparation checkpoint before command release.
        with paths['receipt.json'].open('x') as f:
            json.dump(receipt, f, indent=2)
        os.chmod(paths['receipt.json'], 0o600)
        os.write(gate_w, b'G')
        os.close(gate_w); gate_w = None
        os.close(gate_r); gate_r = None
        deadline = time.monotonic() + timeout
        next_inventory = time.monotonic()
        for key, pipe in [('stdout', child.stdout), ('stderr', child.stderr)]:
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ, key)
        pending_input = memoryview(stdin_data or b'')
        if child.stdin:
            os.set_blocking(child.stdin.fileno(), False)
            if pending_input: selector.register(child.stdin, selectors.EVENT_WRITE, 'stdin')
            else: child.stdin.close()
        total = 0
        while selector.get_map():
            if time.monotonic() >= deadline:
                raise TimeoutError('whole command timeout')
            if time.monotonic() >= next_inventory:
                receipt['inventories'].append(inventory(receipt['pgid']))
                next_inventory = time.monotonic() + 0.25
            for event, _ in selector.select(0.05):
                if event.data == 'stdin':
                    try: n = os.write(event.fileobj.fileno(), pending_input[:65536]); pending_input = pending_input[n:]
                    except BrokenPipeError: pending_input = memoryview(b'')
                    if not pending_input: selector.unregister(event.fileobj); event.fileobj.close()
                    continue
                chunk = os.read(event.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(event.fileobj)
                    continue
                receipt['pendingOutput'] = {'stream': event.data, 'originalBytesHex': chunk.hex()}
                inject('before_log_write')
                streams[event.data].write(chunk)
                del receipt['pendingOutput']
                inject('log_write')
                total += len(chunk)
                if total > output_cap:
                    raise RuntimeError('output cap exceeded; original bytes retained through crossing chunk')
        # Closed pipes do not imply process exit; wait remains bounded.
        receipt['actualExitCode'] = child.wait(timeout=max(0.01, deadline-time.monotonic()))
        receipt['waited'] = True
    except BaseException as exc:
        receipt['errors'].append({'type': type(exc).__name__, 'message': str(exc)})
    finally:
        try:
            settle()
        except BaseException as exc:
            receipt['errors'].append({'type': type(exc).__name__, 'message': str(exc), 'stage': 'settle'})
        for fd in (gate_r, gate_w):
            if fd is not None:
                os.close(fd)
        # Preserve any available trailing bytes following failure/termination.
        if child:
            for key, pipe in [('stdout', child.stdout), ('stderr', child.stderr)]:
                if pipe and not pipe.closed:
                    try:
                        os.set_blocking(pipe.fileno(), False)
                        while True:
                            chunk = os.read(pipe.fileno(), 65536)
                            if not chunk: break
                            if key in streams: streams[key].write(chunk)
                    except (BlockingIOError, OSError) as exc:
                        receipt['errors'].append({'type': type(exc).__name__, 'stage': 'drain', 'message': str(exc)})
                    pipe.close()
        if child and child.stdin and not child.stdin.closed: child.stdin.close()
        selector.close()
        for f in streams.values():
            try: f.flush(); f.close()
            except OSError as exc: receipt['errors'].append({'type': type(exc).__name__, 'stage': 'close', 'message': str(exc)})
        try:
            final = inventory(receipt['pgid'])
            receipt['inventories'].append(final)
            group = receipt['pgid']
            remaining = [r for r in final['rows'] if group is not None and r['pgid'] == group]
            receipt['absence'] = {'checkedUtc': final['utc'], 'recordedBirthAbsent':
                                  receipt['birth'] is not None and birth(receipt['pid']) != receipt['birth'],
                                  'recordedGroupAbsent': group is not None and not remaining,
                                  'remainingGroupRows': remaining}
        except BaseException as exc:
            receipt['errors'].append({'type': type(exc).__name__, 'stage': 'absence', 'message': str(exc)})
        receipt['endUtc'] = utc()
        for key in ('pid', 'pgid', 'birth', 'actualExitCode', 'absence'):
            if receipt.get(key) is None: receipt['missing'].append(key)
        if not receipt['waited']: receipt['missing'].append('directChildWait')
        for key in ('stdout', 'stderr'):
            if paths[key].exists(): receipt[key] = {'path': str(paths[key]), **digest(paths[key])}
            else: receipt['missing'].append(key)
        receipt['status'] = 'COMPLETE' if not receipt['errors'] and not receipt['missing'] and not remaining else 'PARTIAL'
        # Final write errors do not escape child settlement. Original checkpoint
        # remains and caller receives the partial in-memory receipt for fallback.
        try:
            inject('final_write')
            tmp = paths['receipt.json'].with_suffix('.settled.json')
            with tmp.open('x') as f: json.dump(receipt, f, indent=2)
            os.chmod(tmp, 0o600)
            os.replace(tmp, paths['receipt.json'])
        except BaseException as exc:
            receipt['errors'].append({'type': type(exc).__name__, 'stage': 'final_write', 'message': str(exc)})
            receipt['status'] = 'PARTIAL'; receipt['missing'].append('durableFinalReceipt')
            # Preserve the failed original checkpoint, then independently write
            # known original child settlement under a DISTINCT fallback name.
            fallback = directory / (stem + '.caller-settlement.json')
            try:
                with fallback.open('x') as f: json.dump(receipt, f, indent=2)
                os.chmod(fallback, 0o600)
                receipt['settlementFallbackPath'] = str(fallback)
            except BaseException as fallback_error:
                receipt['errors'].append({'type': type(fallback_error).__name__, 'stage': 'settlement_fallback', 'message': str(fallback_error)})
    receipt['receiptPath'] = str(paths['receipt.json'])
    return receipt
