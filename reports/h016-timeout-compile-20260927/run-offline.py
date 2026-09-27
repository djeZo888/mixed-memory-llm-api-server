#!/usr/bin/env python3
"""Run focused actual compiled payload on immutable runtime, network disabled."""
import pathlib,subprocess,sys,datetime,json
if '--help' in sys.argv:print(__doc__);sys.exit(0)
t=pathlib.Path('/home/user/ai-harness-build/H016-TIMEOUT-COMPILE-20260927')
with (t/'pre-probe-guard.json').open('w') as f:subprocess.run(['python3',str(t/'artifact-guard.py')],stdout=f,check=True)
cmd=['timeout','--signal=TERM','--kill-after=5s','45s','podman','run','--rm','--network','none','--read-only','--user','0:0','--name','h016-timeout-probe14','--tmpfs','/tmp:rw,nosuid,nodev','--entrypoint','node','-v',f'{t}:/work:ro','-v',f'{t}/packaged/chunks:/opt/minimax/chunks:ro','-v',f'{t}/native-probes-check.mjs:/opt/minimax/native-probes-check.mjs:ro','-v',f'{t}/packaged-base/native-probes.mjs:/opt/minimax/native-probes-baseline.mjs:ro']
for p in (t/'payload/opt/minimax').iterdir():
 if p.is_file():cmd+=['-v',f'{p}:/opt/minimax/{p.name}:ro']
cmd+=['sha256:6641df04cf4e8375029639a67c22da7c3ff4719d2b8e58748572f049de8fb022','/work/offline-probe.mjs']
(t/'offline-command.json').write_text(json.dumps(cmd,indent=2)+'\n')
start=datetime.datetime.now(datetime.timezone.utc).isoformat()
with (t/'offline-probe.json').open('w') as out,(t/'offline-probe.stderr').open('w') as err:r=subprocess.run(cmd,stdout=out,stderr=err)
(t/'offline-exit.json').write_text(json.dumps({'startedUtc':start,'finishedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exitCode':r.returncode},indent=2)+'\n')
with (t/'post-probe-guard.json').open('w') as f:subprocess.run(['python3',str(t/'artifact-guard.py')],stdout=f,check=True)
print((t/'offline-exit.json').read_text());sys.exit(r.returncode)
