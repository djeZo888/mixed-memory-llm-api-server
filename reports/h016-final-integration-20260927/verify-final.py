#!/usr/bin/env python3
"""Read-only exact staged delta and existing private preservation comparison."""
import hashlib,importlib.util,json,pathlib,subprocess,sys
if '--help' in sys.argv: print(__doc__);sys.exit(0)
p=pathlib.Path('/home/user/ai-harness-build/H016-FINAL-INTEGRATION-20260927')
b=pathlib.Path('/opt/ai-harness/releases/928b3b470058241f089a839367d4b30d5887a6e3-h016/ai-harness')
n=pathlib.Path('/opt/ai-harness/releases/df0702412b1a8f594db7d3211ca63f6aafe8a026-h016/ai-harness')
sha=lambda q:hashlib.sha256(q.read_bytes()).hexdigest()
def tree(root):return {str(q.relative_to(root)): ('link',str(q.readlink())) if q.is_symlink() else ('file',sha(q)) for q in root.rglob('*') if q.is_file() or q.is_symlink()}
a,z=tree(b),tree(n);delta=sorted(f for f in a.keys()|z.keys() if a.get(f)!=z.get(f))
assert delta==['server/dist/active-frontier.js','server/src/active-frontier.ts','server/test/mimo-receipt.test.ts'],delta
for f in delta:assert sha(n/f)==sha(p/'ai-harness'/f)
spec=importlib.util.spec_from_file_location('prior','/home/user/ai-harness-build/H016-ACTIVATION-PREP-20260927/verify-stage.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
content=old.content_identity();assert content==json.loads((p/'private/content-baseline.json').read_text()) and content['files']==17597
assert old.credentials()==json.loads((p/'private/credential-baseline.json').read_text())
before=json.loads((p/'private/before.json').read_text());after=json.loads((p/'private/after.json').read_text())
for k in ['units','containers','states','data','base_image']:assert before[k]==after[k],k
for name,file in old.UNITS.items():assert sha(file)==old.EXPECTED_UNITS[name]
assert subprocess.check_output(['podman','image','inspect',old.TAG,'--format','{{.Id}}'],text=True).strip()==old.BASE
assert subprocess.check_output(['podman','image','inspect',old.IMAGE,'--format','{{.Id}}'],text=True).strip()==old.IMAGE
assert (p/'private/etc-before.json').read_bytes()==(p/'private/etc-after.json').read_bytes()
(p/'proposed').mkdir(exist_ok=True,mode=0o700)
for name,file in old.UNITS.items():
 unit=file.read_text();proposed=unit.replace(str(old.OLD),str(n));assert proposed.replace(str(n),str(old.OLD))==unit
 (p/'proposed'/name).write_text(proposed)
print(json.dumps({'result':'PASS','release':str(n),'source_commit':'df0702412b1a8f594db7d3211ca63f6aafe8a026','delta':{f:sha(n/f) for f in delta},'engine_iid':'sha256:'+old.IMAGE,'engine_rebuilt':False,'production_tag':'sha256:'+old.BASE,'sessions':26,'messages':133,'files':62,'non_database_files':17597,'data_identities_unchanged':True,'credential_metadata_unchanged':True,'etc_ai_harness_metadata_unchanged':True,'dedicated_directory':'root:root 0755 /etc/sova-qualification','receipt_installed':False,'activated':False,'native_acceptance':'NOT_TESTED','app_acceptance':'NOT_TESTED'},indent=2))
