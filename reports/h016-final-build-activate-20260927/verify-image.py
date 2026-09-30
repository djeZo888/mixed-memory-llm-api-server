#!/usr/bin/env python3
"""Verify final COPY inventory against retained exact6641 base. No inference."""
import hashlib,json,pathlib,sys
if '--help' in sys.argv:print(__doc__);sys.exit(0)
t=pathlib.Path('/home/user/ai-harness-build/H016-FINAL-BUILD-ACTIVATE-20260927');p=t/'private'
read=lambda f:json.loads(f.read_text());sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
b=read(pathlib.Path('/home/user/ai-harness-build/H016-MIMO-BUILD-20260927/candidate-inventory.json'));n=read(p/'final-inventory.json')
payload=t/'final-stage/payload';allow={'/'+str(f.relative_to(payload)):f for f in payload.rglob('*') if f.is_file()}
delta={k for k in b.keys()|n.keys() if b.get(k)!=n.get(k)}
assert delta<=set(allow),{'unexpected':sorted(delta-set(allow))}
for k,f in allow.items():
 assert n[k][0]=='file' and n[k][1]==sha(f) and n[k][2]==f.stat().st_size,k
 assert n[k][3]==f.stat().st_mode&0o777 and n[k][-2:]==[0,0],k
bi=read(p/'base-inspect.json')[0];ni=read(p/'final-inspect.json')[0]
assert bi['Id'].removeprefix('sha256:')=='6641df04cf4e8375029639a67c22da7c3ff4719d2b8e58748572f049de8fb022'
assert ni['RootFS']['Layers'][:-1]==bi['RootFS']['Layers']
labels=ni.get('Labels') or ni['Config']['Labels']
assert labels['org.opencontainers.image.ai-harness.source']==(t/'SOURCE-COMMIT').read_text().strip()
assert labels['org.opencontainers.image.ai-harness.native-source']=='b948889814648ad761f40a18260ddbe6351c6bbf'
assert labels['org.opencontainers.image.ai-harness.patchset']=='38d7b6a7978e5e95e69db790cf2e3465a0e33ddd27124b1b7af387518e9722bf'
assert (payload/'opt/minimax/patched-source-revision.txt').read_text().strip()==labels['org.opencontainers.image.ai-harness.native-source']
assert n['/opt/minimax/cli.js'][3]&0o111
print(json.dumps({'result':'PASS','source':labels['org.opencontainers.image.ai-harness.source'],'image':ni['Id'],'base':bi['Id'],'baseLayers':len(bi['RootFS']['Layers']),'additionalLayers':1,'inventoryEntries':len(n),'payloadFiles':len(allow),'changedEntries':len(delta),'allNonPayloadEntriesUnchanged':True,'payloadSha256':{k:sha(f) for k,f in sorted(allow.items())},'inference':False},indent=2))
