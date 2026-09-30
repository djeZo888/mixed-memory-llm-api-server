#!/usr/bin/env python3
"""Unexecuted local correction for the operator's shell continuation error.

This exact H025 namespace is consumed. This helper must refuse it. It is retained
for review, not permission to retry. No reviewed driver or guest source changed.
"""
import subprocess


PREFLIGHT = r'''
import datetime, hashlib, json, sys, time
from pathlib import Path
base = Path('/data/logs/H025-TEST01-20260928')
assert not (base / 'overlap').exists(), 'Consumed campaign; no replay'
sys.path.insert(0, str(base / 'driver'))
from contract import validate_go, digest
from driver import package
from fan_status import validate_fan
from native import protected
mr, gr = protected(base / 'manifest.json'), protected(base / 'go.json')
assert hashlib.sha256(mr).hexdigest() == 'e28ea767005c16b2634350d41207a75dada3ebc2ba4d3c5f110f5bcf8e8ab202'
assert hashlib.sha256(gr).hexdigest() == 'f6110e47e41c79926e3a31ec687558300a65728cadcda8c5b62cc4995b788bbc'
m, g = json.loads(mr), json.loads(gr)
now = datetime.datetime.now(datetime.timezone.utc)
validate_go(g, m, 'B', package()['package_sha256'], now.isoformat())
assert (datetime.datetime.fromisoformat(g['admission_deadline_utc'].replace('Z', '+00:00')) - now).total_seconds() >= 300
validate_fan(m, json.loads(protected(m['fan_status_path'])), now.isoformat(), time.monotonic())
'''

LAUNCH = [
    'ssh', '-o', 'BatchMode=yes', 'ai-vm',
    'sudo -n systemd-run --unit=h025-test01-overlap.service '
    '--property=Type=exec --property=Restart=no --property=UMask=0077 '
    '--property=WorkingDirectory=/data/logs/H025-TEST01-20260928/driver '
    '/usr/bin/python3 -B /data/logs/H025-TEST01-20260928/driver/driver.py '
    '--manifest /data/logs/H025-TEST01-20260928/manifest.json '
    '--go /data/logs/H025-TEST01-20260928/go.json --phase B --run '
    '--journal /data/logs/H025-TEST01-20260928/overlap',
]


def main():
    # A nonzero SSH/Python preflight raises and makes LAUNCH unreachable.
    subprocess.run(
        ['ssh', '-o', 'BatchMode=yes', 'ai-vm', 'sudo -n python3 -B -'],
        input=PREFLIGHT, text=True, check=True, timeout=15,
    )
    subprocess.run(LAUNCH, check=True, timeout=15)


if __name__ == '__main__':
    main()
