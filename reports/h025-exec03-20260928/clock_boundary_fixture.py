#!/usr/bin/env python3
"""One offline clock-boundary fixture. Never reads credentials or contacts models."""
from pathlib import Path
import json
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'h025-prep01-20260928' / 'driver'))
from contract import Refusal, digest, validate_go
from driver import package
from test_driver import manifest

def main():
    m = manifest()
    p = package()
    g = dict(action='ROOT GO H025 PHASE B', phase='B', task_id=m['task_id'],
             go_id='OFFLINE-CLOCK-FIXTURE-NOT-LIVE-GO', boot_id=m['boot_id'],
             deployment_sha256=digest(m), package_sha256=p['package_sha256'],
             quiet_confirmed=True, global_admission_receipt='offline-fixture-only',
             not_before_utc='2026-09-28T20:08:30Z',
             admission_deadline_utc='2026-09-28T20:15:00Z',
             settlement_deadline_utc='2026-09-28T20:32:00Z')
    now = '2026-09-28T20:09:00Z'
    validate_go(g, m, 'B', p['package_sha256'], now)
    results = {'new_valid_admission_201500_settlement_203200': 'PASS'}
    for name, changes in (
        ('late_admission_201501', dict(not_before_utc='2026-09-28T20:08:31Z', admission_deadline_utc='2026-09-28T20:15:01Z', settlement_deadline_utc='2026-09-28T20:32:01Z')),
        ('late_absolute_settlement_203501', dict(settlement_deadline_utc='2026-09-28T20:35:01Z')),
    ):
        try:
            validate_go(dict(g, **changes), m, 'B', p['package_sha256'], now)
        except Refusal as exc:
            assert str(exc) == 'H025 absolute cutoff', str(exc)
            results[name] = 'PASS_REFUSED_ABSOLUTE_CUTOFF'
        else:
            raise AssertionError(name + ' accepted')
    print(json.dumps({'status': 'PASS', 'scope': 'one offline clock-boundary fixture only', 'cases': results, 'package': p}, indent=2))

if __name__ == '__main__':
    main()
