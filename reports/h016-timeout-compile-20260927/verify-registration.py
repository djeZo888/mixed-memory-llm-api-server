#!/usr/bin/env python3
"""Offline exact canonical patch registration replay on retained upstream blobs."""
import pathlib,json,hashlib,subprocess,sys
if '--help' in sys.argv:print(__doc__);sys.exit(0)
t=pathlib.Path(sys.argv[1]).resolve();reg=t/'registration';src=t/'native-source';dst=t/'registration-fixture';dst.mkdir()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
j=json.loads((reg/'identity.json').read_text());assert sha(reg/'SHA256SUMS')==j['patchSetSha256']
for f in j['files']:
 r=subprocess.run(['git','show',j['sourceRevision']+':'+f['path']],cwd=src,capture_output=True)
 if f['originalSha256'] is None:assert r.returncode!=0;continue
 assert r.returncode==0 and hashlib.sha256(r.stdout).hexdigest()==f['originalSha256'],f['path']
 p=dst/f['path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(r.stdout)
for patch in j['patches']:
 p=reg/patch['path'];assert sha(p)==patch['sha256'];opts=['--unidiff-zero'] if p.name=='0011-mimo-request-budget.patch' else []
 for check in [['--check'],[]]:subprocess.run(['git','apply',*opts,*check,str(p)],cwd=dst,check=True)
for f in j['files']:assert sha(dst/f['path'])==f['patchedSha256'],f['path']
print(json.dumps({'result':'PASS','sourceRevision':j['sourceRevision'],'files':len(j['files']),'patches':len(j['patches']),'patchSetSha256':j['patchSetSha256'],'zeroContextAppliedOnlyTo0011':True},indent=2))
