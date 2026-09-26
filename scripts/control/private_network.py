#!/usr/bin/env python3
"""N1S fixed host INPUT transport. No model, credential, HTTP or installer logic.

Public read-only API: load_policy() -> fresh dict, raises PrivateNetworkError.
The CLI alone can change the one owned IPv4 filter chain/jump. See
 docs/private-network.md for the later, separately approved N1VM sequence.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys

POLICY = Path('/etc/llm-server/network.json')
HELPER = Path('/usr/local/lib/llm-server/private-network/private_network.py')
STATE = Path('/etc/llm-server/private-network-state.json')
LOCK = Path('/run/llm-private-network.lock')
UNIT_DIR = Path('/etc/systemd/system')
IPTABLES = '/usr/sbin/iptables'
IP = '/usr/sbin/ip'
SYSTEMCTL = '/usr/bin/systemctl'
PROXYD = '/usr/lib/systemd/systemd-socket-proxyd'
CHAIN = 'LLM-PRIVATE-IN'
TAG = 'llm-private-n1s-v1'
EXPECTED = {
    'schema_version': 1, 'mode': 'socket_proxyd_private_ipv4',
    'interface': 'enp6s18', 'private_address': '10.156.100.60',
    'prefix_length': 24, 'allowed_client_ipv4': ['10.156.100.0/24'],
    'ports': {'control': 30000, 'glm': 30002, 'qwen38': 30004, 'image': 30006, 'node': 30008},
}


class PrivateNetworkError(ValueError):
    """Fail-closed, nonsecret diagnostic."""


def _require(condition, message):
    if not condition:
        raise PrivateNetworkError(message)


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    try:
        return json.loads(raw.decode('utf-8') if isinstance(raw, bytes) else raw, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise PrivateNetworkError('invalid strict JSON') from None


def _validate_policy(raw):
    _require(len(raw) <= 4096, 'policy too large')
    value = _json(raw)
    # Serialized equality also distinguishes true/1 and 24.0/24.
    _require(json.dumps(value, sort_keys=True) == json.dumps(EXPECTED, sort_keys=True),
             'policy differs from reviewed fixed schema')
    return value


def _protected(path, mode, maximum=1024 * 1024):
    """Walk with no-follow descriptors; root-only protected parents and file."""
    path = Path(path)
    _require(path.is_absolute() and '..' not in path.parts, 'unsafe path')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            meta = os.fstat(fd)
            _require(meta.st_uid == 0 and not meta.st_mode & 0o022,
                     'unprotected parent')
        file_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            before = os.fstat(file_fd)
            _require(stat.S_ISREG(before.st_mode) and before.st_uid == 0
                     and before.st_nlink == 1 and stat.S_IMODE(before.st_mode) == mode
                     and before.st_size <= maximum, 'unprotected or oversized file')
            raw = os.read(file_fd, maximum + 1)
            after = os.fstat(file_fd)
            current = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
            signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns,
                                   s.st_ctime_ns, s.st_mode, s.st_uid, s.st_nlink)
            _require(len(raw) == before.st_size and signature(before) == signature(after)
                     and signature(before) == signature(current), 'file changed during read')
            return raw
        finally:
            os.close(file_fd)
    except OSError:
        raise PrivateNetworkError('missing or unsafe protected file') from None
    finally:
        os.close(fd)


def load_policy():
    """Read the fixed protected policy; no overrides, commands or readiness claim."""
    return _validate_policy(_protected(POLICY, 0o600, 4096))


def expected_units():
    """Exact reviewed transport units; no deployment/model dependencies."""
    units = {}
    for role, port in (("control", 30000), ("glm", 30002), ("qwen38", 30004), ("image", 30006), ("node", 30008)):
        name = "llm-private-" + role
        units[name + ".socket"] = f"""# N1S owned transport: edits require source/policy review.
[Unit]
Description=Private IPv4 TCP transport for {role}
# Late network ordering must not inherit Before=sockets.target.
DefaultDependencies=no
Requires=sysinit.target
Wants=network-online.target
After=sysinit.target network-online.target
Before=shutdown.target
Conflicts=shutdown.target

[Socket]
ListenStream=10.156.100.60:{port}
Accept=no
FreeBind=no
BindToDevice=enp6s18
Service={name}.service
ExecStartPre=/usr/bin/python3 -I -B /usr/local/lib/llm-server/private-network/private_network.py apply
ExecStartPre=/usr/bin/python3 -I -B /usr/local/lib/llm-server/private-network/private_network.py check

[Install]
WantedBy=multi-user.target
"""
        units[name + ".service"] = f"""# N1S owned transport: edits require source/policy review.
[Unit]
Description=Opaque TCP forwarding for private {role}
Requires={name}.socket
BindsTo={name}.socket
After={name}.socket network-online.target

[Service]
Type=notify
DynamicUser=yes
NoNewPrivileges=yes
# Only this root precondition inspects protected policy and effective INPUT rules.
ExecStartPre=+/usr/bin/python3 -I -B /usr/local/lib/llm-server/private-network/private_network.py check
ExecStart=/usr/lib/systemd/systemd-socket-proxyd --connections-max=16 127.0.0.1:{port}
PrivateNetwork=no
PrivateTmp=yes
ProtectHome=yes
LimitCORE=0
StandardOutput=null
StandardError=null
"""
    return units



def _run(args):
    try:
        proc = subprocess.run(args, check=False, capture_output=True, text=True,
                              timeout=15, env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin',
                                               'LC_ALL': 'C'})
    except (OSError, subprocess.TimeoutExpired):
        raise PrivateNetworkError('required host command unavailable or timed out') from None
    _require(proc.returncode == 0, 'required host command failed (details suppressed)')
    _require(len(proc.stdout) <= 1024 * 1024, 'host command output too large')
    return proc.stdout


def _ipt(*args):
    return _run([IPTABLES, '-w', '5', '-t', 'filter', *args])


def _show(name):
    raw = _run([SYSTEMCTL, 'show', name, '--property=FragmentPath,DropInPaths,'
                'NeedDaemonReload,ActiveState,UnitFileState'])
    return dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)


def _units_stopped():
    for name in expected_units():
        info = _show(name)
        _require(info.get('ActiveState') in ('inactive', 'failed')
                 and info.get('UnitFileState') in (('disabled',) if name.endswith('.socket')
                                                   else ('static', 'disabled')),
                 'stop all ten transport units and disable sockets before ingress removal')


def _installation():
    _require(os.geteuid() == 0 and sys.platform == 'linux', 'requires Linux root')
    _require(Path(__file__).absolute() == HELPER, 'run the fixed reviewed installed helper')
    policy_raw = _protected(POLICY, 0o600, 4096)
    _validate_policy(policy_raw)
    blobs = {'helper': _protected(HELPER, 0o644), 'policy': policy_raw}
    for name, expected in expected_units().items():
        raw = _protected(UNIT_DIR / name, 0o644, 16384)
        _require(raw == expected.encode(), 'installed unit drift')
        info = _show(name)
        _require(info.get('FragmentPath') == str(UNIT_DIR / name)
                 and info.get('DropInPaths') == '' and info.get('NeedDaemonReload') == 'no',
                 'effective unit drift or daemon-reload required')
        # Catch pending/unloaded drop-ins too, including type and dash-prefix ones.
        suffix = name.rsplit('.', 1)[1]
        for base in ('/etc/systemd/system', '/run/systemd/system', '/usr/local/lib/systemd/system',
                     '/usr/lib/systemd/system', '/lib/systemd/system', '/run/systemd/generator',
                     '/run/systemd/generator.early', '/run/systemd/generator.late',
                     '/run/systemd/transient', '/etc/systemd/system.control',
                     '/run/systemd/system.control'):
            for directory in (name + '.d', name + '.wants', name + '.requires',
                              name + '.upholds', suffix + '.d', 'llm-.' + suffix + '.d',
                              'llm-private-.' + suffix + '.d'):
                path = Path(base) / directory
                _require(not path.exists() and not path.is_symlink(), 'unit drop-in or dependency directory present')
        blobs[name] = raw
    _require(Path(PROXYD).is_file() and os.access(PROXYD, os.X_OK), 'proxyd unavailable')
    # Allow only canonical Ubuntu 8 security-update patches: 16-19, 20-99, 100+.
    _require(re.fullmatch(r'255\.4-1ubuntu8\.(?:1[6-9]|[2-9][0-9]|[1-9][0-9]{2,})',
                         _run(['/usr/bin/dpkg-query', '--show', '--showformat=${Version}', 'systemd']))
             is not None, 'systemd package outside approved security-update family')
    return {key: hashlib.sha256(raw).hexdigest() for key, raw in blobs.items()}


def _interface():
    data = _json(_run([IP, '-j', '-4', 'address', 'show', 'dev', 'enp6s18']))
    _require(type(data) is list and len(data) == 1, 'missing interface')
    link = data[0]
    _require(type(link) is dict and type(link.get('flags')) is list
             and type(link.get('addr_info')) is list
             and all(type(a) is dict for a in link['addr_info']), 'invalid interface response')
    _require(link.get('ifname') == 'enp6s18' and 'UP' in link.get('flags', [])
             and link.get('operstate') == 'UP', 'interface not up')
    found = [a for a in link.get('addr_info', []) if a.get('family') == 'inet'
             and a.get('local') == '10.156.100.60' and a.get('prefixlen') == 24
             and a.get('scope') == 'global' and not a.get('tentative', False)
             and not a.get('dadfailed', False) and a.get('valid_life_time') != 0]
    _require(len(found) == 1, 'exact private address/prefix unavailable')


def _rules():
    jump = ['-d', '10.156.100.60/32', '-p', 'tcp', '-m', 'multiport', '--dports',
            '30000,30002,30004,30006,30008', '-m', 'comment', '--comment', TAG, '-j', CHAIN]
    rules = [
        ['-i', 'lo', '-m', 'comment', '--comment', TAG + ':loopback', '-j', 'ACCEPT'],
        ['-s', '10.156.100.0/24', '-i', 'enp6s18', '-m', 'comment', '--comment',
         TAG + ':lan', '-j', 'ACCEPT'],
        ['-m', 'comment', '--comment', TAG + ':deny', '-j', 'DROP'],
    ]
    return jump, rules


def _snapshot():
    return _ipt('-S')


def _inspect(raw, partial=False):
    """Only exact ordered owned rules; jump must be first INPUT rule, always."""
    rows = [shlex.split(line) for line in raw.splitlines() if line]
    jump, rules = _rules()
    desired_jump = ['-A', 'INPUT', *jump]
    desired_rules = [['-A', CHAIN, *rule] for rule in rules]
    declarations = [row for row in rows if row[:2] == ['-N', CHAIN]]
    chain_rows = [row for row in rows if row[:2] == ['-A', CHAIN]]
    references = [row for row in rows if any(row[i] in ('-j', '-g') and row[i+1] == CHAIN
                  for i in range(len(row)-1))]
    tagged = [row for row in rows if any(TAG in field for field in row)]
    allowed = [desired_jump, *desired_rules]
    _require(all(row in allowed for row in tagged), 'foreign or changed ownership tag')
    _require(references in ([], [desired_jump]), 'unowned or duplicate chain reference')
    _require(declarations in ([], [['-N', CHAIN]]), 'unexpected chain declaration')
    if not declarations:
        _require(not chain_rows and not references and not tagged, 'orphaned owned rules')
        return 'absent', []
    _require(chain_rows == desired_rules or (partial and not references
             and chain_rows == desired_rules[:len(chain_rows)]), 'owned chain drift')
    if references:
        inputs = [row for row in rows if row[:2] == ['-A', 'INPUT']]
        _require(inputs and inputs[0] == desired_jump, 'owned jump is not first INPUT rule')
        _require(chain_rows == desired_rules, 'incomplete chain with live jump')
        return 'complete', chain_rows
    _require(partial, 'missing owned INPUT jump')
    return 'partial', chain_rows


def _state(signature):
    if not STATE.exists() and not STATE.is_symlink():
        return None
    value = _json(_protected(STATE, 0o600))
    _require(type(value) is dict and set(value) == {'owner', 'signature', 'before_filter'}
             and value['owner'] == TAG and value['signature'] == signature
             and type(value['before_filter']) is str, 'ownership or source/policy drift')
    _require(_inspect(value['before_filter'])[0] == 'absent', 'invalid original filter backup')
    return value


def _write_state(signature, before):
    # A durable pre-mutation receipt is ownership evidence, never firewall readiness.
    _require(len(before.encode()) <= 262144, 'filter backup exceeds bounded receipt')
    raw = (json.dumps({'owner': TAG, 'signature': signature, 'before_filter': before},
                      sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(STATE, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        directory = os.open(STATE.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        # Keep the receipt on interrupted/failed persistence; invalid receipts fail closed.
        raise


@contextmanager
def _lock():
    fd = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        meta = os.fstat(fd)
        _require(stat.S_ISREG(meta.st_mode) and meta.st_uid == 0 and meta.st_nlink == 1
                 and stat.S_IMODE(meta.st_mode) == 0o600, 'unsafe helper lock')
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _remove_rules(raw):
    status, chain_rows = _inspect(raw, partial=True)
    jump, _ = _rules()
    if status == 'complete':
        _ipt('-D', 'INPUT', *jump)
    if status != 'absent':
        for row in reversed(chain_rows):
            _ipt('-D', CHAIN, *row[2:])
        _ipt('-X', CHAIN)
    _require(_inspect(_snapshot())[0] == 'absent', 'inverse did not remove owned rules')


def operate(action, dry_run=False):
    """Fixed CLI operations. All mutations require matching reviewed installation."""
    signature = _installation()
    # Removal must remain possible after loss of the private interface.
    if action != 'remove':
        _interface()
    with _lock():
        receipt = _state(signature)
        before = _snapshot()
        status, _ = _inspect(before, partial=action == 'remove')
        _require(receipt is not None or status == 'absent', 'preexisting unowned chain/jump')
        if action == 'preflight':
            return 'preflight passed; no readiness claim'
        if action == 'check':
            _require(receipt is not None and status == 'complete', 'effective owned ingress missing')
            return 'effective ingress and transport configuration passed; upstream readiness unknown'
        if action == 'remove':
            _units_stopped()
            _require(receipt is not None or status == 'absent', 'no inverse ownership')
            if not dry_run:
                _remove_rules(before)
            return 'inverse dry-run passed' if dry_run else 'owned ingress removed; backup retained'
        _require(action == 'apply', 'unknown operation')
        if status == 'complete':
            return 'exact owned ingress already effective'
        # Initial activation or reboot: build unreachable chain before inserting first INPUT jump.
        _require(status == 'absent', 'partial state requires stopped-unit inverse')
        if dry_run:
            return 'apply dry-run passed: create three-rule chain, insert first INPUT jump'
        if receipt is None:
            _write_state(signature, before)
        jump, rules = _rules()
        _ipt('-N', CHAIN)
        for rule in rules:
            _ipt('-A', CHAIN, *rule)
        # Inspect again before making chain reachable; reject external interference.
        _inspect(_snapshot(), partial=True)
        _ipt('-I', 'INPUT', '1', *jump)
        _require(_inspect(_snapshot())[0] == 'complete', 'effective ingress verification failed')
        return 'owned ingress applied and verified; sockets may now run their check'


def source_check():
    root = Path(__file__).resolve().parents[2]
    _validate_policy((root / 'configs/network/ai-vm-private-api.json').read_bytes())
    for name, content in expected_units().items():
        _require((root / 'configs/network' / name).read_bytes() == content.encode(),
                 'source unit drift')
    return 'fixed source policy and eight exact units passed (systemd runtime NOT_TESTED)'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('source-check', 'preflight', 'check', 'apply', 'remove'))
    parser.add_argument('--dry-run', action='store_true', help='inspect apply/inverse without rule writes')
    args = parser.parse_args(argv)
    try:
        _require(not args.dry_run or args.action in ('apply', 'remove'), 'dry-run is only for apply/remove')
        print(source_check() if args.action == 'source-check' else operate(args.action, args.dry_run))
        return 0
    except (PrivateNetworkError, OSError, ValueError) as exc:
        print('private network refused: ' + (str(exc) if isinstance(exc, PrivateNetworkError)
                                            else 'host operation failed'), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
