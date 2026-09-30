#!/usr/bin/env python3
"""Verify final COPY inventory against retained final46 base. No inference."""
import hashlib,json,pathlib,sys
if '--help' in sys.argv:print(__doc__);sys.exit(0)
t=pathlib.Path('/home/user/ai-harness-build/H018-HARNESS-PREP01-20260928');p=t/'private'
read=lambda f:json.loads(f.read_text());sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
base_inventory=pathlib.Path('/home/user/ai-harness-build/H016-FINAL-BUILD-ACTIVATE-20260927/private/final-inventory.json')
assert sha(base_inventory)=='7846eb5f9befb44e55cc4c62cfe15e114bb21c7ef7f10a9cdb410491da2d9fcf'
b=read(base_inventory);n=read(p/'final-inventory.json')
payload=t/'final-stage/payload';allow={'/'+str(f.relative_to(payload)):f for f in payload.rglob('*') if f.is_file()}
delta={k for k in b.keys()|n.keys() if b.get(k)!=n.get(k)}
assert delta<=set(allow),{'unexpected':sorted(delta-set(allow))}
for k,f in allow.items():
 assert n[k][0]=='file' and n[k][1]==sha(f) and n[k][2]==f.stat().st_size,k
 assert n[k][3]==f.stat().st_mode&0o777 and n[k][-2:]==[0,0],k
bi=read(p/'base-inspect.json')[0];ni=read(p/'final-inspect.json')[0]
assert bi['Id'].removeprefix('sha256:')=='46feffff8fe00e5993a8e0d35f5a7932f82ee43ef91d87759f568c3a6029dc1e'
assert ni['RootFS']['Layers'][:-1]==bi['RootFS']['Layers']
labels=ni.get('Labels') or ni['Config']['Labels']
assert labels['org.opencontainers.image.ai-harness.source']==(t/'SOURCE-COMMIT').read_text().strip()
assert labels['org.opencontainers.image.ai-harness.native-source']=='b948889814648ad761f40a18260ddbe6351c6bbf'
assert labels['org.opencontainers.image.ai-harness.patchset']=='38d7b6a7978e5e95e69db790cf2e3465a0e33ddd27124b1b7af387518e9722bf'
assert n['/opt/minimax/patched-source-revision.txt']==b['/opt/minimax/patched-source-revision.txt']
assert n['/opt/minimax/cli.js'][3]&0o111
print(json.dumps({'result':'PASS','source':labels['org.opencontainers.image.ai-harness.source'],'image':ni['Id'],'base':bi['Id'],'baseLayers':len(bi['RootFS']['Layers']),'additionalLayers':1,'inventoryEntries':len(n),'payloadFiles':len(allow),'changedEntries':len(delta),'allNonPayloadEntriesUnchanged':True,'payloadSha256':{k:sha(f) for k,f in sorted(allow.items())},'inference':False},indent=2))
