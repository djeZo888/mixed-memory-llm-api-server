#!/usr/bin/env python3
"""Compare built image inventory/layers against its exact retained base and allowlist."""
import hashlib,json,pathlib,sys
if '--help' in sys.argv: print(__doc__);sys.exit(0)
t=pathlib.Path('/home/user/ai-harness-build/H016-MIMO-BUILD-20260927')
def read(n):return json.loads((t/n).read_text())
b=read('base-inventory.json');n=read('candidate-inventory.json');m=read('overlay-manifest.json')
a={x['path']:x for x in m['changed_file_allowlist']};delta={k for k in b.keys()|n.keys() if b.get(k)!=n.get(k)}
assert delta==set(a),{'unexpected':list(delta-set(a)),'missing':list(set(a)-delta)}
for k in delta:assert n[k][1]==a[k]['sha256'],k
bi=read('base-inspect.json')[0];ni=read('candidate-inspect.json')[0]
assert ni['RootFS']['Layers'][:len(bi['RootFS']['Layers'])]==bi['RootFS']['Layers']
assert ni['Id']!=bi['Id']
assert ni['Config']['Labels']['org.opencontainers.image.ai-harness.patchset']==m['patchset']
def digest(rows):return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
groups={}
for prefix in ['/opt/minimax/node_modules/','/opt/minimax/embedded/','/opt/minimax/native/','/opt/minimax/vendor/','/opt/ai-harness/tools/','/opt/ai-harness/skills/','/opt/ai-harness-python/','/usr/lib/chromium/','/usr/local/bin/','/usr/local/lib/','/usr/bin/']:
 rows={k:v for k,v in b.items() if k.startswith(prefix)}; assert rows;assert rows=={k:v for k,v in n.items() if k.startswith(prefix)},prefix
 groups[prefix]={'entries':len(rows),'sha256':digest(rows),'unchanged':True}
result={'result':'PASS','base_image':m['base_image'],'image':'sha256:'+ni['Id'].removeprefix('sha256:'),'base_layers_preserved':True,'base_layer_count':len(bi['RootFS']['Layers']),'new_layer_count':len(ni['RootFS']['Layers'])-len(bi['RootFS']['Layers']),'changed_files':len(delta),'compared_inventory_entries':len(n),'allowlist_sha256':digest(m['changed_file_allowlist']),'labels':ni['Config']['Labels'],'unchanged_groups':groups}
(t/'overlay-verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
