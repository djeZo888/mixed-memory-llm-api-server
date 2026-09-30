#!/usr/bin/env python3
"""Finite read-only collection; no waiting or request replay."""
import datetime,hashlib,importlib.util,json
from pathlib import Path
P=Path;B=P('/data/services/mimo-h016-20260927');L=P('/data/logs/H018-20260928/worker1-short')
def main():
 owner=B/'source/owner.py';assert hashlib.sha256(owner.read_bytes()).hexdigest()==PINNED_CONFIG['source_sha256'][str(owner)]
 s=importlib.util.spec_from_file_location('collect_owner',owner);o=importlib.util.module_from_spec(s);s.loader.exec_module(o);h=o.setup()
 with h.MountedStorageGuard(h.s) as g:
  h.s.root_payload_guard();o.storage_paths(h,g)
  unit=dict(x.split('=',1) for x in o.run(['systemctl','show','h018-short.service','-p','MainPID,ActiveState,SubState,InvocationID,Result,ExecMainStatus'],3).splitlines())
  state=o.read(B/'state.json');identity={k:state.get(k) for k in ('boot_id','manifest_sha256','supervisor','launch_id','native')};assert identity==PINNED_CONFIG['production_identity']
  out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'unit':unit,'ordinary_state':state,'ordinary_guard':o.read(B/'guard.json'),'receipts':{},'status':'NOT_TERMINAL_RETURN_WITHOUT_WAIT'}
  if unit['MainPID']=='0' and unit['ActiveState'] in ('inactive','failed'):
   names=['CLIENT.json','ALLOCATION.json','FINAL17-QUALIFICATION.json','GUARD-PROGRESS.json','DISPATCH.json','DISPATCH-ATTEMPT.json','FINAL17-READ.txt']
   for label in ('SHORT-TEXT','FINAL17-TURN1','FINAL17-TURN2'):
    names += [label+suffix for suffix in ('.json','-REQUEST.json','-RAW.jsonl','-PROGRESS.jsonl','-GUARD-AFTER.json')]
   for name in names:
    p=L/name
    if p.exists():
     raw=o.protected(p);out['receipts'][name]={'raw':raw.decode(),'sha256':hashlib.sha256(raw).hexdigest(),'remote_path':str(p)}
   out['status']='TERMINAL_COLLECTED' if 'CLIENT.json' in out['receipts'] else 'NOT_DISPATCHED'
   if 'CLIENT.json' in out['receipts']:
    client=json.loads(out['receipts']['CLIENT.json']['raw']);out['client_status']=client['status']
    if client['status']=='PASS_KEEP_WARM':
     helper=module_read_dispatch();key=o.read_key(h)
     transport=helper.module('collect_transport',P('/data/build/H016-20260927/worker1-final13-long/client.py'));transport.check_identity(o,PINNED_CONFIG);o.source_preflight(h,o.read(B/'manifest.json'))
     out['final_read']={'state':state,'actual_usable_context':helper.get('127.0.0.1',30012,'/slots',key)[0]['n_ctx'],'private_usable_context':helper.get('10.156.100.60',30012,'/slots',key)[0]['n_ctx'],'native_ready_predicate':o.native_ready(o.read(B/'manifest.json'),key)}
  h.s.root_payload_guard();print(json.dumps(out))
def module_read_dispatch():
 import types
 m=types.ModuleType('read_helpers');exec(READ_HELPER_SOURCE,m.__dict__);return m
if __name__=='__main__':main()
