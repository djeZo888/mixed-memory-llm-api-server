#!/usr/bin/env python3
"""One independent affinity controller; no lease spans child dispatch."""
import argparse
import json
import subprocess
import time
import datetime
from pathlib import Path
from authority import validate, BASE

UNIT = 'h016-affinity14-20260927.service'

def main(run=False):
    go, plan = validate()
    end = datetime.datetime.fromisoformat(plan['pair_cleanup_utc'].replace('Z','+00:00')).timestamp()
    assert time.time()+900 < end, 'insufficient_pair_budget'
    props = subprocess.check_output(['systemctl','show',UNIT,'-p','LoadState','--value'],text=True).strip()
    assert props == 'not-found', 'unit_exists_no_replay'
    argv = ['systemd-run','--unit='+UNIT,'--property=Type=exec','--property=Restart=no',
            '--property=RuntimeMaxSec='+str(int(end-time.time())), '--property=TimeoutStopSec=450',
            '--property=KillMode=mixed','--property=UMask=0077','--property=WorkingDirectory='+str(BASE),
            '--property=StandardOutput=null','--property=StandardError=null',
            '--property=ExecStopPost=/usr/bin/python3 -B '+str(BASE)+'/controller.py --settle',
            '/usr/bin/python3','-B',str(BASE)+'/controller.py','--run']
    result = {'status':'PREFLIGHT_ONLY','command':argv,'plan':plan,'unit':UNIT}
    if run:
        subprocess.run(argv,check=True,stdout=subprocess.DEVNULL,timeout=10)
        result['status']='SYSTEMD_DISPATCHED_READBACK_REQUIRED'
        result['unit_readback']=subprocess.check_output(['systemctl','show',UNIT,'-p','MainPID,ControlPID,InvocationID,ActiveState,SubState,ControlGroup,ExecMainStartTimestamp,RuntimeMaxUSec,TimeoutStopUSec'],text=True)
    print(json.dumps(result))

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',action='store_true');p.add_argument('--dry-run',action='store_true');a=p.parse_args();main(a.run and not a.dry_run)
