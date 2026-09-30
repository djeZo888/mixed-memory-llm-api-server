#!/usr/bin/env python3
"""Render/apply only the H005 task egress table; never flush another firewall table."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

CONFIG = Path('/etc/ai-harness/task-egress.json')
RECEIPT = Path('/run/ai-harness-egress/verified.json')
TABLE = 'ai_harness_tasks'
NFT = '/usr/sbin/nft'


def protected(path, directory=False):
    path = Path(path)
    for item in (path, *path.parents):
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('path must have root-owned nonwritable ancestry')
    if directory != path.is_dir():
        raise ValueError('wrong protected path type')


def config_value(value):
    if set(value) != {'schema', 'uid', 'dns_servers'} or value['schema'] != 'h005-task-egress-v1':
        raise ValueError('unsupported task egress configuration')
    if type(value['uid']) is not int or not 1 <= value['uid'] < 2**31:
        raise ValueError('ordinary service UID required')
    dns = value['dns_servers']
    if not isinstance(dns, list) or not 1 <= len(dns) <= 4 or len(set(dns)) != len(dns):
        raise ValueError('one to four exact DNS addresses required')
    for addr in dns:
        ip = ipaddress.ip_address(addr)
        if str(ip) != addr or ip.is_multicast or ip.is_unspecified:
            raise ValueError('canonical unicast DNS address required')
    return value


def cgroup_path(uid):
    return f'user.slice/user-{uid}.slice/user@{uid}.service/aiharnesstasks.slice'


def render(config):
    config_value(config)
    lines = [f'table inet {TABLE} {{', ' chain task_out {']
    # slirp translates container 10.0.2.2 to host loopback. No other host port.
    lines += ['  ip daddr 127.0.0.1 tcp dport { 8081, 8082 } accept']
    for addr in config['dns_servers']:
        family = 'ip6' if ':' in addr else 'ip'
        lines.append(f'  {family} daddr {addr} meta l4proto {{ tcp, udp }} th dport 53 accept')
    lines += [
        '  fib daddr type local reject',
        '  ip daddr { 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.0.0.0/24, 192.0.2.0/24, 192.88.99.0/24, 192.168.0.0/16, 198.18.0.0/15, 198.51.100.0/24, 203.0.113.0/24, 224.0.0.0/3 } reject',
        '  ip6 daddr { ::/128, ::1/128, ::ffff:0:0/96, 64:ff9b::/96, 64:ff9b:1::/48, 100::/64, 2001::/32, 2001:db8::/32, 2002::/16, fc00::/7, fe80::/10, fec0::/10, ff00::/8 } reject',
        '  tcp dport { 80, 443 } accept',
        '  reject', ' }', ' chain output {',
        '  type filter hook output priority -10; policy accept;',
        f'  socket cgroupv2 level 4 "{cgroup_path(config["uid"])}" jump task_out',
        ' }', '}',
    ]
    return '\n'.join(lines) + '\n'


def nft(args, input_text=None):
    return subprocess.run([NFT, *args], input=input_text, text=True, capture_output=True,
                          check=True, timeout=2).stdout


def live_digest():
    value = json.loads(nft(['--json', 'list', 'table', 'inet', TABLE]))
    # nft version/generation metadata is not table identity. No counters are installed.
    entries = [entry for entry in value['nftables'] if 'metainfo' not in entry]
    return hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def write_receipt(config, inode, digest):
    value = {'schema': 'h005-task-egress-v1', 'uid': config['uid'],
             'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
             'cgroup_path': cgroup_path(config['uid']), 'cgroup_inode': inode,
             'nft_sha256': digest, 'checked_boottime': time.clock_gettime(time.CLOCK_BOOTTIME)}
    temporary = RECEIPT.with_suffix('.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(value, stream); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, RECEIPT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--dry-run', action='store_true', help='validate and print only the scoped table')
    action.add_argument('--apply-watch', action='store_true', help='root only: atomically replace own table and attest every 2s')
    args = parser.parse_args()
    protected(CONFIG)
    config = config_value(json.loads(CONFIG.read_text()))
    content = render(config)
    if args.dry_run:
        print(content, end=''); return
    if os.geteuid() != 0:
        raise ValueError('root required')
    protected(RECEIPT.parent, directory=True)
    path = Path('/sys/fs/cgroup') / cgroup_path(config['uid'])
    inode = path.stat().st_ino
    RECEIPT.unlink(missing_ok=True)
    # Delete our table only, in the same atomic nft transaction as its replacement.
    exists = subprocess.run([NFT, 'list', 'table', 'inet', TABLE], capture_output=True, timeout=2)
    if exists.returncode not in (0, 1):
        raise ValueError('cannot inspect existing scoped table')
    transaction = (f'delete table inet {TABLE}\n' if exists.returncode == 0 else '') + content
    nft(['--check', '--file', '-'], transaction)
    nft(['--file', '-'], transaction)
    digest = live_digest()
    try:
        while True:
            if path.stat().st_ino != inode or live_digest() != digest:
                raise ValueError('live task egress policy identity changed')
            write_receipt(config, inode, digest)
            time.sleep(2)
    finally:
        RECEIPT.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        # Do not dump command outputs/configuration in service logs.
        print(f'task-egress-policy: refused ({type(error).__name__})', file=sys.stderr)
        sys.exit(1)
