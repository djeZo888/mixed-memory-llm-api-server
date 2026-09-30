# Fixed H013 emergency settlement only. Prepend vm-common, PARAMETERS, PREFIX.
# Separate systemd job: 420s maximum, no inference, start/resume or retry.
import importlib.util, types, signal
LOG='/data/logs/flash-h008-20260926'
OUT=LOG+'/'+PREFIX+'-SETTLEMENT.json'
LANES=('qwen1','flash','qwen0','image')  # Passive Server first.
def load_owner(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def validate_exact(lane,value):
 expected=PARAMETERS['containers'][lane]
 assert {**{k:value[k] for k in ('Id','Image')},'StartedAt':value['State']['StartedAt']}==expected,'exact_owner_identity_changed'
 assert value['HostConfig']['RestartPolicy']['Name']=='no','restart_policy_changed'
 return value

def inspect_exact(lane):
 cid=PARAMETERS['containers'][lane]['Id']
 q=subprocess.run(['docker','inspect',cid],capture_output=True,text=True,timeout=5)
 if q.returncode:
  assert lane=='image' and 'no such object' in q.stderr.lower(),'owned_inspect_failed'
  return None
 return validate_exact(lane,json.loads(q.stdout)[0])

def owner_action(lane,lease):
 # Validate current production owner receipt BEFORE the authorized short stop.
 # Return existing bookkeeping action; it runs only after native PID/cgroup settle.
 if lane=='flash':
  m=load_owner('/data/services/flash-h008-20260926/source/owner.py','h013_flash_owner')
  state=json.loads(P(m.BASE+'/state.json').read_text());desired=state['desired']
  assert state['container']['id']==PARAMETERS['containers'][lane]['Id']
  cfg=json.loads(P(m.BASE+'/config.json').read_text())
  m.validate_container(inspect_exact(lane),cfg,state)
  def finish():
   m.operate('halt',borrowed=lease)
   assert json.loads(P(m.BASE+'/state.json').read_text())['desired']==desired
 elif lane.startswith('qwen'):
  from lifecycle.manager import load_manager
  m=load_manager(types.SimpleNamespace(instance=None),P(ROOT)/'configs')
  target='qwen' if lane=='qwen1' else 'glm';st=m.read_state();slot=st['slots'][target]
  assert slot['container']['id']==PARAMETERS['containers'][lane]['Id']
  m.trusted_container(slot['container'])
  intent={k:slot[k] for k in ('selected','desired','boot_policy')}
  def finish():
   m.dispatch('boot-stop',lease=lease,target=target,expected_generation=slot['generation'])
   after=m.read_state()['slots'][target];assert {k:after[k] for k in intent}==intent
 else:
  m=load_owner('/data/services/image21-runtime-20260923/source/service.py','h013_image_owner')
  m.OPERATION_DEADLINE=time.monotonic()+60
  owner=m.Runtime();owner.lease=lease;st=owner.state()
  assert st['container']['id']==PARAMETERS['containers'][lane]['Id']
  owner.inspect_owned(st)
  def finish():owner.reset_owned()
 return finish

def short_stop(lane,value,cg,lease):
 lease.validate();validate_exact(lane,value)
 finish=owner_action(lane,lease)
 # Revalidate after receipt/import checks, before this sole direct mutation.
 current=inspect_exact(lane);assert current is not None,'owned_container_disappeared'
 if current['State']['Running']:
  subprocess.run(['docker','stop','--time','3',PARAMETERS['containers'][lane]['Id']],check=True,capture_output=True,text=True,timeout=12)
 current=inspect_exact(lane)
 assert current is not None and not current['State']['Running'] and current['State']['Pid']==0 and not current['State']['Restarting'],'short_stop_unproven'
 assert cg is None or not cg.exists() or not (cg/'cgroup.procs').read_text().strip(),'owned_cgroup_not_empty'
 finish()  # Existing owner sees already-stopped exact container; intent unchanged.


def write_receipt(receipt):
 with transaction() as (_,g):s.root_payload_guard();status(OUT,receipt,g);s.root_payload_guard()

def main():
 deadline=time.monotonic()+400
 receipt={'utc':now(),'status':'SETTLING','owner':PREFIX,'no_reload':True,'lanes':{}}
 try:
  assert not P(OUT).exists(),'settlement_no_replay'
  assert P('/proc/sys/kernel/random/boot_id').read_text().strip()==PARAMETERS['boot']
  for path,h in PARAMETERS['source_matches'].items():assert hashlib.sha256(P(path).read_bytes()).hexdigest()==h,'source_changed'
  trigger=json.loads(P(LOG,PREFIX+'-CANCEL.json').read_text())
  assert trigger['boot']==PARAMETERS['boot'] and trigger['containers']==PARAMETERS['containers'],'trigger_identity_changed'
  owned=trigger['targets'];assert set(owned).issubset(LANES),'unknown_lane'
  for lane,ids in owned.items():
   assert ids and len(ids)<=12
   for request_id in ids:
    assert request_id.startswith(PREFIX+'-'+lane+'-')
    index=int(request_id.rsplit('-',1)[1]);assert 0<=index<(8 if lane=='image' else 1 if lane=='flash' else 12)
    row=json.loads(P(LOG,request_id+'-OWNER.json').read_text());assert row['request_id']==request_id
  receipt['request_ids']=owned;write_receipt(receipt)
  for lane in LANES:
   if not owned.get(lane):receipt['lanes'][lane]={'status':'NOT_SUBMITTED'};continue
   try:
    with transaction() as (lease,g):
     s.root_payload_guard();value=inspect_exact(lane)
     cg=None
     if value and value['State']['Running']:
      cg=P('/sys/fs/cgroup'+P('/proc',str(value['State']['Pid']),'cgroup').read_text().split('::')[1].strip())
     if value is not None:short_stop(lane,value,cg,lease)
     value=inspect_exact(lane)
     assert value is None or (not value['State']['Running'] and value['State']['Pid']==0 and not value['State']['Restarting']),'native_still_running'
     assert cg is None or not cg.exists() or not (cg/'cgroup.procs').read_text().strip(),'owned_cgroup_not_empty'
     s.root_payload_guard()
     receipt['lanes'][lane]={'status':'SETTLED','container_id':PARAMETERS['containers'][lane]['Id'],'pid_zero_or_absent':True,'empty_cgroup':True}
   except Exception as e:receipt['lanes'][lane]={'status':'FAILED_UNPROVEN','error_type':type(e).__name__}
   write_receipt(receipt)
  receipt['status']='SETTLED' if all(v['status'] in ('SETTLED','NOT_SUBMITTED') for v in receipt['lanes'].values()) else 'FAILED_NATIVE_SETTLEMENT_UNPROVEN'
 except BaseException as e:receipt.update(status='FAILED_NATIVE_SETTLEMENT_UNPROVEN',error_type=type(e).__name__)
 finally:
  receipt['end_utc']=now();write_receipt(receipt)
if __name__=='__main__':main()
