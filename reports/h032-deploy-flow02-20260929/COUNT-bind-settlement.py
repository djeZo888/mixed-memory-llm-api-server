from pathlib import Path
import hashlib,json,re
p=Path(__file__).resolve().parent;sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
a=json.loads((p/'ACTIVATION.json').read_text());r=json.loads((p/'BUILD-RECEIPT.json').read_text());assert a['state']=='APP_STATUS_HEALTH_PASS' and a['source']==r['sourceHead'];source=a['source'];release=a['release'];unit=a['appUnitSha256'];remote='/home/user/.cache/h032-deploy-flow02'
mods={n[len('server/dist/'):-3]:h for n,h in r['files'].items() if n.startswith('server/dist/') and n.endswith('.js')}
b={'schema':1,'head':source,'pilotId':'H032-DEPLOY-FLOW02','release':release,'activationReceiptPath':'/home/user/.cache/h032-count-update-release/ACTIVATION.json','activationReceiptSha256':sha(p/'ACTIVATION.json'),'acceptAfter':a['completedUtc'],'candidateUnit':{'path':'/home/user/.config/systemd/user/ai-harness.service','sha256':unit},'semanticBuildHashes':mods,'buildReceiptSha256':sha(p/'BUILD-RECEIPT.json'),'imageId':r['image']['imageId'],'codexPolicySha256':r['image']['policySha256'],'hostPolicySha256':r['hostPolicySha256'],'configReplacements':r['configReplacements'],'limits':'Future exact owned runs only; unchanged settlement predicates; independent H028 status untouched.'}
f=p/'DEPLOYMENT-BINDING.json';f.write_text(json.dumps(b,indent=2)+'\n');old=Path('/Users/agent/CodexProjects/llm-orchestration/tasks/H030-FLOW03-20260929/private/settlement-readback.py');reader=old.read_text()
constants={'SOURCE':source,'PILOT':'H032-DEPLOY-FLOW02','RELEASE':release,'RECEIPT':remote+'/DEPLOYMENT-BINDING.json','RECEIPT_SHA':sha(f),'UNIT':b['candidateUnit']['path'],'UNIT_SHA':unit,'BUILD':mods}
for n,v in constants.items():reader,c=re.subn('^'+n+' = .*$',lambda _:n+' = '+repr(v),reader,count=1,flags=re.M);assert c==1
h=p/'settlement-readback.py';h.write_text(reader)
(p.parent.parent/'output/COUNT-SETTLEMENT-BINDING.json').write_text(json.dumps({'source':source,'bindingSha256':sha(f),'helperSha256':sha(h),'helperPath':remote+'/settlement-readback.py','compiledModules':len(mods),'semanticChange':False,'nativeImageId':r['image']['imageId'],'unitSha256':unit},indent=2)+'\n')
