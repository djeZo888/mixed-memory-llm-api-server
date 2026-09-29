import datetime,hashlib,importlib.util,json,subprocess,time,urllib.request,urllib.error
from pathlib import Path
spec=importlib.util.spec_from_file_location('deploy','/data/backups/H029-FINALCONTROL03-stage/DEPLOY-CONTROL.py');d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
p=json.loads((d.STAGE/'CONTROL-DEPLOY-PROPOSAL.json').read_text());tr=json.loads((d.BACKUP/'TRANSITION.json').read_text());receipt=Path(p['receiptPath']);r=json.loads(receipt.read_text())
out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'closuresMatch':{root:all(d.sha(Path(root)/name)==digest for name,digest in p['successorSourceSha256'].items()) for root in p['changesBySourceRoot']},'allClosureFiles':82,'receiptRawSha256':d.sha(receipt),'receiptCanonicalSha256':d.receipt_sha256(r),'containers':d.native_identity(p),'services':{unit:subprocess.check_output(['systemctl','is-active',unit],text=True).strip() for unit in ['llm-control.service','llm-node.service']}}
out['nativeUnchanged']=out['containers']==tr['containersAfter']
i=json.loads(Path('/data/services/llm-manager/deployment-instance.json').read_text());out['instanceReceiptMatches']=i['concurrent_pair_acceptance']['sha256']==out['receiptCanonicalSha256']==tr['successorReceiptSha256']
key=Path('/etc/llm-server/control-api-key').read_text().strip();started=time.monotonic()
try:
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:30000/control/v1/status',headers={'Authorization':'Bearer '+key}),timeout=30) as response:body=json.load(response);status=response.status
except urllib.error.HTTPError as e:status=e.code;body=json.load(e)
out['control']={'httpStatus':status,'elapsedMs':round((time.monotonic()-started)*1000),'response':body}
print(json.dumps(out,indent=2))
