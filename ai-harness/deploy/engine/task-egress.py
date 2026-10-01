#!/usr/bin/env python3
"""Private launcher guard: enter the fixed task slice only after fresh root policy attestation."""
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import runpy
import select
import signal
import subprocess
import uuid

RECEIPT = Path('/run/ai-harness-egress/verified.json')
SLICE = 'aiharnesstasks.slice'


def validate(value, uid, boot_id, inode, boottime):
    prefix = f'user.slice/user-{uid}.slice/user@{uid}.service/{SLICE}'
    if (value.get('schema') != 'h005-task-egress-v1' or value.get('uid') != uid
        or value.get('boot_id') != boot_id or value.get('cgroup_path') != prefix
        or value.get('cgroup_inode') != inode
        or not isinstance(value.get('nft_sha256'), str)
        or re.fullmatch(r'[0-9a-f]{64}', value['nft_sha256']) is None
        or type(value.get('checked_boottime')) not in (int, float)
        or not 0 <= boottime - value['checked_boottime'] <= 6):
        raise ValueError('fresh boot-bound root policy attestation required')
    return prefix


def verify():
    for path in (RECEIPT, *RECEIPT.parents):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('unsafe policy attestation ancestry')
    value = json.loads(RECEIPT.read_text())
    uid = os.getuid()
    prefix = f'user.slice/user-{uid}.slice/user@{uid}.service/{SLICE}'
    return validate(value, uid, Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                    (Path('/sys/fs/cgroup') / prefix).stat().st_ino,
                    time.clock_gettime(time.CLOCK_BOOTTIME))


def receipt_module():
    return runpy.run_path(str(Path(__file__).resolve().with_name('codex_receipts.py')))


def supervise_scope(args, receipts, config):
    """Hold the actual creator behind a pipe until durable original intent AND birth."""
    unit = 'ai-harness-codex-' + uuid.uuid4().hex + '.scope'
    parent = receipts['process_identity']()
    intent = receipts['publish_scope_intent'](config, unit, parent)
    process = None; creator = None; failure = None; requested = [0]; raw_exit = None; stop_deadline = None
    read_fd, write_fd = os.pipe()
    def stop(number, _frame): requested[0] = number
    handlers = {n: signal.signal(n, stop) for n in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    try:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                                    '--create-scope', str(read_fd), unit, '--', *args],
                                   pass_fds=(read_fd,), start_new_session=True)
        os.close(read_fd); read_fd = None
        creator = receipts['process_identity'](process.pid)
        receipts['publish_scope_creator'](config, intent, creator)
        if requested[0]: raise InterruptedError('stop before creation gate release')
        os.write(write_fd, b'G'); os.close(write_fd); write_fd = None
        # Normal receipt-backed chats remain nonexpiring. Finite qualification
        # invocation authority belongs to the reviewed external caller.
        forwarded = False; stop_deadline = None
        while True:
            try:
                raw_exit = process.wait(timeout=0.1); break
            except subprocess.TimeoutExpired: pass
            if requested[0] and not forwarded:
                observed = receipts['process_identity'](process.pid)
                if any(observed[k] != creator[k] for k in ('pid','startTicks','bootId','uid')):
                    raise ValueError('creator birth changed before signal')
                os.killpg(process.pid, requested[0]); forwarded = True; stop_deadline = time.monotonic() + 45
            if stop_deadline is not None and time.monotonic() >= stop_deadline:
                failure = TimeoutError('scope creator did not settle after owned stop')
                break
    except Exception as error:
        failure = error
    finally:
        for fd in (read_fd, write_fd):
            if fd is not None: os.close(fd)
        # The gate closes on every pre-release failure. Only this fresh creator group is owned.
        if process is not None and raw_exit is None:
            try:
                raw_exit = process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                try:
                    observed = receipts['process_identity'](process.pid)
                    if creator is None or any(observed[k] != creator[k] for k in ('pid','startTicks','bootId','uid')):
                        raise ValueError('creator identity unavailable for owned cleanup')
                    os.killpg(process.pid, signal.SIGKILL if stop_deadline is not None else signal.SIGTERM)
                    try: raw_exit = process.wait(timeout=2 if stop_deadline is not None else 45)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL); raw_exit = process.wait(timeout=2)
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    if failure is None: failure = error
        # Persist actual integer terminal before any fallible scope inventory/postcheck.
        try: receipts['publish_scope_terminal'](config, intent, creator, raw_exit, requested[0], failure)
        finally:
            for number, handler in handlers.items(): signal.signal(number, handler)
    if failure is not None or type(raw_exit) is not int: return 125
    return raw_exit if raw_exit >= 0 else 128 - raw_exit


def main():
    args = sys.argv[1:]
    if args == ['--help']:
        print(__doc__); return 0
    inside = bool(args and args[0] == '--inside-scope')
    creating = bool(args and args[0] == '--create-scope')
    gate = unit = None
    if inside:
        args.pop(0); unit = args.pop(0)
    if creating:
        args.pop(0); gate = int(args.pop(0)); unit = args.pop(0)
    if not args or args.pop(0) != '--' or not args:
        raise ValueError('private launcher arguments required')
    supervisor = Path(__file__).resolve().with_name('redact-acp.py')
    if Path(args[0]) != supervisor:
        raise ValueError('unexpected task supervisor')
    prefix = verify()
    receipts = receipt_module(); config = receipts['channel']()
    if creating:
        if config is None: raise ValueError('original creation channel required')
        if not select.select([gate], [], [], 5)[0] or os.read(gate, 2) != b'G':
            raise ValueError('creator gate not released')
        os.close(gate)
        receipts['verify_creator'](config, unit)
        os.execv('/usr/bin/systemd-run', ['/usr/bin/systemd-run', '--user', '--scope', '--quiet',
                 '--collect', '--expand-environment=no', '--slice=' + SLICE, '--unit=' + unit,
                 sys.executable, str(Path(__file__).resolve()), '--inside-scope', unit, '--', *args])
    if inside:
        lines = Path('/proc/self/cgroup').read_text().splitlines()
        if len(lines) != 1 or not lines[0].startswith('0::/' + prefix + '/'):
            raise ValueError('task process outside protected slice')
        receipts['publish_egress'](prefix)
        if config is not None:
            if not unit: raise ValueError('missing original exact scope unit')
            receipts['scope_original'](config, prefix)
        os.execv(sys.executable, [sys.executable, *args])
    if config is not None:
        return supervise_scope(args, receipts, config)
    # Preserve the ordinary non-receipt launcher. It supplies no H043 causal proof.
    os.execv('/usr/bin/systemd-run', ['/usr/bin/systemd-run', '--user', '--scope', '--quiet',
             '--collect', '--expand-environment=no', '--slice=' + SLICE, sys.executable,
             str(Path(__file__).resolve()), '--inside-scope', '-', '--', *args])


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        try:
            receipts = receipt_module(); config = receipts['channel']()
            if config is not None:
                receipts['write_once'](config[0], 'scope-failure', receipts['causal'](config,
                    'codex-scope-failure-v1', producer=receipts['process_identity'](),
                    errorClass=type(error).__name__, resourceState='UNKNOWN'))
        except Exception: pass
        print(f'task-egress: refused ({type(error).__name__}); root policy/slice acceptance required', file=sys.stderr)
        sys.exit(64)
