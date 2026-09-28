#!/usr/bin/env python3
"""After authentic short02 qualification, enable selected owner without reload."""
import datetime,hashlib,importlib.util,json,os
from pathlib import Path
P=Path;B=P('/data/services/mimo-h016-20260927');L=P('/data/logs/H018-20260928/worker1-short02')
def require(ok,why):
 if not ok:raise RuntimeError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def module(name,p):
 spec=importlib.util.spec_from_file_location(name,p);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
def main():
 owner=B/'source/owner.py';require(sha(owner.read_bytes())==CONFIG['source_sha256'][str(owner)],'owner_pin_changed')
 o=module('enable_owner',owner);h=o.setup()
 transport=module('enable_transport',P('/data/build/H016-20260927/worker1-final13-long/client.py'))
 with o.settlement_lease(h) as lease,h.MountedStorageGuard(h.s) as g:
  h.s.root_payload_guard();o.storage_paths(h,g)
  require(o.selection()==CONFIG['selection'],'selection_changed')
  for name,pin in QUALIFIED_RECEIPTS.items():require(sha(o.protected(L/name))==pin,'qualification_receipt_changed')
  client=o.read(L/'CLIENT.json');native=o.read(L/'FINAL17-QUALIFICATION.json')
  require(client['status']=='PASS_KEEP_WARM' and client['request_may_be_active'] is False and client['production_identity']==CONFIG['production_identity'],'client_not_qualified')
  require(native['status']=='PASS' and native['native_tool_qualification'] is True and native['configured_context']==native['allocated_context']==950000,'native_not_qualified')
  short=dict(x.split('=',1) for x in o.run(['systemctl','show','h018-short02.service','-p','MainPID,ActiveState,Result,ExecMainStatus'],3).splitlines());require(short['MainPID']=='0' and short['ActiveState']=='inactive' and short['Result']=='success' and short['ExecMainStatus']=='0','short_not_successfully_finished')
  for path,pin in CONFIG['source_sha256'].items():require(sha(o.protected(path))==pin,'source_changed')
  manifest,state,guard=transport.check_identity(o,CONFIG);o.source_preflight(h,manifest)
  key=o.read_key(h);require(o.native_ready(manifest,key) is True,'native_not_ready')
  import types
  helper=types.ModuleType('existing_read_helper');exec(READ_HELPER_SOURCE,helper.__dict__)
  slots=helper.get('127.0.0.1',30012,'/slots',key);private=helper.get('10.156.100.60',30012,'/slots',key)
  for rows in (slots,private):require(len(rows)==1 and rows[0]['n_ctx']==950000 and rows[0]['is_processing'] is False,'current_not_idle950000')
  node=helper.get('127.0.0.1',30008,'/control/v1/node/status',o.protected('/etc/llm-server/control-api-key').strip())
  rows=[r for r in node['services'] if r['service_id']==o.MODEL];require(len(rows)==1 and rows[0]['ready'] is True and rows[0]['freshness']=='fresh' and rows[0]['hardware_latched'] is False and node['node_manager']['actions']==[],'canonical_not_ready')
  lease.validate();o.run(['systemctl','enable','--no-reload',o.UNIT],5)
  link=P('/etc/systemd/system/multi-user.target.wants')/o.UNIT
  require(link.is_symlink() and link.resolve()==P('/etc/systemd/system')/o.UNIT,'enabled_symlink_readback_failed')
  require(o.selection()==CONFIG['selection'],'selection_changed_after')
  manifest,after,afterguard=transport.check_identity(o,CONFIG)
  ordinary=dict(x.split('=',1) for x in o.run(['systemctl','show',o.UNIT,'-p','MainPID,ActiveState,InvocationID'],3).splitlines())
  require(ordinary['MainPID']==str(CONFIG['production_identity']['supervisor']['pid']) and ordinary['InvocationID']==CONFIG['production_identity']['supervisor']['invocation_id'] and ordinary['ActiveState']=='active','owner_changed_after')
  h.s.root_payload_guard();lease.validate()
  print(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'QUALIFIED_SELECTED_ENABLED_NO_RELOAD','production_identity':CONFIG['production_identity'],'selection':CONFIG['selection'],'enabled_symlink':str(link),'enabled_target':os.readlink(link),'ordinary_unit':ordinary,'short_unit':short,'current_idle':{'native_slots':slots,'private_slots':private,'proxy_disposition':o.read(B/'proxy-state.json'),'canonical_node':rows[0],'guard':afterguard},'qualified_receipts':QUALIFIED_RECEIPTS,'manager_reload':False,'model_restart':False}))
if __name__=='__main__':main()
