#!/usr/bin/env python3
"""Replay actual frozen native_ready with patched get only, without host contacts.
Usage: replay-native-ready.py PRIVATE_R9_JSON
Emits sanitized field diagnostics and hashes only; retained raw stays outside Git.
"""
import hashlib,importlib.util,json,pathlib,sys
from unittest.mock import patch
if '--help' in sys.argv:print(__doc__);sys.exit(0)
repo=pathlib.Path(__file__).resolve().parents[2];raw=pathlib.Path(sys.argv[1]);x=json.loads(raw.read_text())
source=repo/'scripts/runtime/mimo/owner.py';spec=importlib.util.spec_from_file_location('h017_frozen_owner',source);o=importlib.util.module_from_spec(spec);spec.loader.exec_module(o)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
props,slots=x['actual_props']['value'],x['actual_slots']['value']
def get(path,key):
 item=x[{'/props':'actual_props','/slots':'actual_slots'}[path]]
 return item['http_status'],item['value']
results=[]
with patch.object(o,'get',side_effect=get):
 for name in ['FAILED-MANIFEST.json','REPAIR-MANIFEST.proposed.json']:
  file=repo/'reports/h016-production-deploy17-20260927'/name;m=json.loads(file.read_text())
  assert o.native_ready(m,b'offline-fixture') is True
  results.append({'manifest':name,'manifestSha256':sha(file),'context':m['context'],'nativeReady':True})
print(json.dumps({'ownerSha256':sha(source),'rawR9Sha256':sha(raw),'httpStatuses':[x['actual_props']['http_status'],x['actual_slots']['http_status']],'propsContext':props['default_generation_settings']['n_ctx'],'slotContext':slots[0]['n_ctx'],'slotIsProcessing':slots[0]['is_processing'],'templateBytes':len(props['chat_template'].encode()),'templateSha256':hashlib.sha256(props['chat_template'].encode()).hexdigest(),'toolTemplateKeyPresent':'chat_template_tool_use' in props,'manifests':results,'deterministicReadySnapshotIncompatibility':False,'originalLiveFailureCause':'UNKNOWN','currentReadinessProven':False,'contacts':0},indent=2))
