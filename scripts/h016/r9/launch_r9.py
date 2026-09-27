#!/usr/bin/env python3
"""Exact R9 systemd dispatch; --run only after direct root GO for this packet."""
import argparse
import json
import pathlib
import subprocess
import time
from candidate_owner import BASE, LOG, HARD_END, ADMIT_END, SETTLE_START, preflight, save, run_cmd
from verify_retained import dependency


def main(run=False):
    h = dependency()
    h.require(time.time() + 1200 + 2400 < HARD_END - 1200, 'insufficient_load_and_final_qualification_window')
    cfg, proof = preflight(h)
    unit = 'h016-mimo-final-20260927-r9.service'
    h.require(run_cmd(['systemctl', 'show', unit, '-p', 'LoadState', '--value']).strip() == 'not-found', 'r9_unit_exists_no_replay')
    remaining = int(SETTLE_START - time.time())
    argv = ['systemd-run', '--unit=' + unit, '--property=Type=exec', '--property=Restart=no',
            '--property=RuntimeMaxSec=' + str(remaining), '--property=TimeoutStopSec=420',
            '--property=KillMode=mixed', '--property=UMask=0077',
            '--property=WorkingDirectory=' + BASE, '--property=StandardOutput=null', '--property=StandardError=null',
            '--property=ExecStopPost=/usr/bin/python3 -B ' + BASE + '/candidate_owner.py --settle',
            '/usr/bin/python3', '-B', BASE + '/candidate_owner.py', '--run']
    receipt = {'utc': h.now(), 'status': 'REVIEWED_PREFLIGHT_NO_DISPATCH', 'unit': unit,
               'command': argv, 'native_argv': cfg['native_argv'], 'proof': proof,
               'source_hashes': json.loads(pathlib.Path(BASE, 'SOURCE-SHA256.json').read_text()),
               'admission_end_utc': cfg['admission_end_utc'], 'settlement_utc': cfg['request_end_utc'],
               'global_end_utc': cfg['global_end_utc'], 'no_inference_dispatched_by_launcher': True}
    if run:
        save(h, 'INITIAL-LAUNCH.json', receipt)
        # All parent preflight/save transactions are closed. The independent
        # child performs its authoritative preflight and lease acquisition.
        subprocess.run(argv, check=True, stdout=subprocess.DEVNULL, timeout=10)
        receipt['status'] = 'SYSTEMD_DISPATCHED_READBACK_REQUIRED'
        receipt['unit_readback'] = run_cmd(['systemctl', 'show', unit, '-p',
            'MainPID,InvocationID,ExecMainStartTimestamp,ActiveState,SubState,ControlGroup,RuntimeMaxUSec,TimeoutStopUSec'])
        save(h, 'INITIAL-LAUNCH.json', receipt)
    print(json.dumps(receipt))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    a = p.parse_args()
    main(run=a.run and not a.dry_run)
