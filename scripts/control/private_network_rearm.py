#!/usr/bin/env python3
"""Bounded recovery runs for existing enabled PRIVATEAPI transport sockets only.

The unchanged private_network.py apply/check commands own all installation,
source-receipt, interface and ingress guards. This helper cannot enable sockets,
change network configuration, or start an upstream/model service.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

HELPER = Path('/usr/local/lib/llm-server/private-network/private_network_rearm.py')
NETWORK_HELPER = '/usr/local/lib/llm-server/private-network/private_network.py'
SYSTEMCTL = '/usr/bin/systemctl'
SOCKETS = tuple(f'llm-private-{role}.socket' for role in
               ('control', 'glm', 'qwen38', 'image', 'node', 'frontier', 'ada200k'))
DELAYS = (0, 5, 15, 30)
BUDGET_SECONDS = 90
ENABLED = ('enabled', 'enabled-runtime')


class RearmError(ValueError):
    """Bounded, nonsecret recovery diagnostic."""


def expected_units():
    return {
        'llm-private-network-rearm.service': '''# H028 finite recovery; existing socket enablement remains authoritative.
[Unit]
Description=Bounded recovery of enabled private API sockets
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -I -B /usr/local/lib/llm-server/private-network/private_network_rearm.py rearm
TimeoutStartSec=120
Restart=no
UMask=0077
LimitCORE=0
''',
        'llm-private-network-rearm.timer': '''# H028 slow observation; bounded runs cannot overlap on this single service.
[Unit]
Description=Observe and recover private API sockets after boot or late network return

[Timer]
OnBootSec=45s
OnUnitInactiveSec=60s
AccuracySec=1s
Unit=llm-private-network-rearm.service
Persistent=no

[Install]
WantedBy=timers.target
''',
    }


def _command(args, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RearmError('recovery time budget exhausted')
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=False,
                                timeout=min(60, remaining),
                                env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
    except (OSError, subprocess.TimeoutExpired):
        raise RearmError('fixed host command unavailable or timed out') from None
    if result.returncode != 0:
        # Only the fixed reviewed helper emits diagnostics; no environment,
        # arbitrary command output, addresses, credentials or unit dumps.
        detail = result.stderr.strip()[:240] if NETWORK_HELPER in args else ''
        raise RearmError('guarded ingress refused' + (': ' + detail if detail else '')
                         if NETWORK_HELPER in args else 'socket operation failed')
    if len(result.stdout) > 65536:
        raise RearmError('host command output too large')
    return result.stdout


def _show(name, deadline):
    raw = _command([SYSTEMCTL, 'show', name,
                    '--property=UnitFileState,ActiveState'], deadline)
    return dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)


def rearm_once(deadline):
    """Rearm only enabled stopped sockets, through unchanged exact guards."""
    candidates = []
    pending = False
    for name in SOCKETS:
        info = _show(name, deadline)
        if info.get('UnitFileState') not in ENABLED:
            continue
        state = info.get('ActiveState')
        if state in ('inactive', 'failed'):
            candidates.append(name)
        elif state != 'active':
            pending = True
    if not candidates:
        if pending:
            raise RearmError('enabled socket activation still pending')
        return 'no enabled stopped sockets; upstream readiness unknown'
    for action in ('apply', 'check'):
        _command(['/usr/bin/python3', '-I', '-B', NETWORK_HELPER, action], deadline)
    for name in candidates:
        # Respect an operator disable between discovery and action. The guarded
        # apply/check above independently rejects all existing unit/drop-in drift.
        info = _show(name, deadline)
        if info.get('UnitFileState') not in ENABLED:
            continue
        if info.get('ActiveState') == 'failed':
            _command([SYSTEMCTL, 'reset-failed', name], deadline)
        if info.get('ActiveState') in ('inactive', 'failed'):
            # Do not wait on systemd device jobs; the next finite attempt observes
            # actual activation. Starting this socket has no model dependencies.
            _command([SYSTEMCTL, '--no-block', 'start', name], deadline)
    for name in SOCKETS:
        info = _show(name, deadline)
        if info.get('UnitFileState') in ENABLED and info.get('ActiveState') != 'active':
            raise RearmError('enabled socket activation still pending')
    return 'enabled private sockets active; upstream readiness unknown'


def recover():
    deadline = time.monotonic() + BUDGET_SECONDS
    last = 'not attempted'
    for number, delay in enumerate(DELAYS, 1):
        if time.monotonic() + delay >= deadline:
            break
        if delay:
            time.sleep(delay)
        try:
            return rearm_once(deadline)
        except RearmError as exc:
            last = str(exc)
            print(f'private transport recovery attempt {number}/{len(DELAYS)}: {last}',
                  file=sys.stderr, flush=True)
    raise RearmError('bounded recovery run exhausted; next timer observation remains scheduled: ' + last)


def source_check():
    root = Path(__file__).resolve().parents[2]
    for name, content in expected_units().items():
        if (root / 'configs/network' / name).read_bytes() != content.encode():
            raise RearmError('source recovery unit drift')
    return 'finite recovery source units passed; systemd runtime NOT_TESTED'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('rearm', 'source-check'))
    args = parser.parse_args(argv)
    try:
        if args.action == 'source-check':
            print(source_check())
        else:
            if os.geteuid() != 0 or sys.platform != 'linux' or Path(__file__).absolute() != HELPER:
                raise RearmError('requires fixed installed helper under Linux root')
            print(recover())
        return 0
    except (RearmError, OSError) as exc:
        print('private transport recovery refused: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
