"""Retain original finite check stdout/stderr and actual integer wait receipts."""
import argparse, datetime, hashlib, json, os
from pathlib import Path
import subprocess


def run(argv, cwd, out, name, timeout=180):
    out = Path(out).resolve(); out.mkdir(mode=0o700,exist_ok=True)
    stem=out/name
    if any(Path(str(stem)+suffix).exists() for suffix in ['.stdout','.stderr','.json']):
        raise ValueError('original check outputs exist; choose a new suffixed name')
    start=datetime.datetime.now(datetime.timezone.utc).isoformat()
    env=dict(os.environ,PATH='/opt/homebrew/opt/node@24/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',PYTHONDONTWRITEBYTECODE='1')
    with open(str(stem)+'.stdout','xb') as stdout,open(str(stem)+'.stderr','xb') as stderr:
        proc=subprocess.Popen(argv,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr)
        timed_out=False
        try: exit_code=proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out=True;proc.terminate()
            try: exit_code=proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();exit_code=proc.wait()
    receipt={'argv':argv,'cwd':str(Path(cwd).resolve()),'pid':proc.pid,'startedUtc':start,'finishedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'actualExitCode':exit_code,'timedOut':timed_out,
             'stdoutSha256':hashlib.sha256(Path(str(stem)+'.stdout').read_bytes()).hexdigest(),'stderrSha256':hashlib.sha256(Path(str(stem)+'.stderr').read_bytes()).hexdigest()}
    Path(str(stem)+'.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cwd',required=True);p.add_argument('--out',required=True);p.add_argument('--name',required=True);p.add_argument('--timeout',type=int,default=180);p.add_argument('command',nargs=argparse.REMAINDER)
    a=p.parse_args();command=a.command[1:] if a.command[:1]==['--'] else a.command
    r=run(command,a.cwd,a.out,a.name,a.timeout);print(json.dumps(r));raise SystemExit(r['actualExitCode'])
