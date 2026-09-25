#!/usr/bin/env python3
"""Private launcher guard: enter the fixed task slice only after fresh root policy attestation."""
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

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


def main():
    args = sys.argv[1:]
    if args == ['--help']:
        print(__doc__); return
    inside = bool(args and args[0] == '--inside-scope')
    if inside:
        args.pop(0)
    if not args or args.pop(0) != '--' or not args:
        raise ValueError('private launcher arguments required')
    # A fixed sibling ACP supervisor is the only executable target.
    supervisor = Path(__file__).resolve().with_name('redact-acp.py')
    if Path(args[0]) != supervisor:
        raise ValueError('unexpected task supervisor')
    prefix = verify()
    if inside:
        lines = Path('/proc/self/cgroup').read_text().splitlines()
        if len(lines) != 1 or not lines[0].startswith('0::/' + prefix + '/'):
            raise ValueError('task process outside protected slice')
        os.execv(sys.executable, [sys.executable, *args])
    os.execv('/usr/bin/systemd-run', ['/usr/bin/systemd-run', '--user', '--scope', '--quiet',
             '--collect', '--expand-environment=no', '--slice=' + SLICE, sys.executable, str(Path(__file__).resolve()),
             '--inside-scope', '--', *args])


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        print(f'task-egress: refused ({type(error).__name__}); root policy/slice acceptance required', file=sys.stderr)
        sys.exit(64)
