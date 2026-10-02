"""Source fixtures only: fixed bridge and current Docker owner rejection paths."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest import mock
import build_graph,control,observer,lifecycle

class PrivateNetworkControlTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  with tempfile.TemporaryDirectory() as directory, mock.patch.object(build_graph,'OUT',Path(directory)):
   cls.graph=build_graph.build()
 def fixture(self):
  nid='a'*64;nonce='d'*64;ids={'interpretation':'b'*64,'ocr':'c'*64}
  labels={'io.h044.vision.owner':control.NETWORK_OWNER,'io.h044.vision.nonce':nonce}
  n={'Id':nid,'Internal':True,'Driver':'bridge','Labels':labels,'IPAM':{'Config':[{'Subnet':'172.31.243.0/28'}]},'Containers':{cid:{'IPv4Address':control.MODEL_ADDRESSES[role]+'/28'} for role,cid in ids.items()}}
  containers={role:{'Id':cid,'State':{'Running':True},'Config':{'Labels':labels},'HostConfig':{'NetworkMode':nid,'PortBindings':{}},'NetworkSettings':{'Networks':{'owned-bridge':{'NetworkID':nid,'IPAddress':control.MODEL_ADDRESSES[role],'IPAMConfig':{'IPv4Address':control.MODEL_ADDRESSES[role]}}}}} for role,cid in ids.items()}
  return n,containers,dict(network_id=nid,nonce=nonce,container_ids=ids)
 def test_generated_graph_has_exact_role_origins(self):
  self.assertEqual(control.model_origins(self.graph),{'interpretation':'http://172.31.243.2:18191','ocr':'http://172.31.243.3:18192'})
  control.validate_graph(self.graph)
 def test_graph_rejects_egress_role_swap_and_cli_overrides(self):
  changes=[lambda g:g['runtime']['network'].update(internal=False),lambda g:g['runtime']['network'].update(subnet='172.31.244.0/28'),lambda g:g['runtime']['containers'][0].update(privateIp='172.31.243.3'),lambda g:g['runtime']['service']['modelOrigins'].update(interpretation='http://example.com:18191')]
  for change in changes:
   g=copy.deepcopy(self.graph);change(g)
   with self.assertRaises(control.Refused):control.model_origins(g)
  for flag in (['--net','host'],['--net=host'],['--network=host'],['--ip','172.31.243.4'],['--publish','18191:18191'],['-p18191:18191']):
   g=copy.deepcopy(self.graph);g['runtime']['containers'][0]['createArgv']+=flag
   with self.subTest(flag=flag),self.assertRaises(control.Refused):control.model_origins(g)
 def test_exact_current_owners_pass(self):
  n,c,b=self.fixture();self.assertEqual(control.validate_network_owners(self.graph,n,c,**b)['networkId'],b['network_id'])
 def test_actual_wrong_ip_network_or_owner_rejected(self):
  for field,value in (('IPAddress','172.31.243.3'),('NetworkID','e'*64),('IPAMConfig',{'IPv4Address':'172.31.243.4'})):
   n,c,b=self.fixture();c['interpretation']['NetworkSettings']['Networks']['owned-bridge'][field]=value
   with self.subTest(field=field),self.assertRaises(control.Refused):control.validate_network_owners(self.graph,n,c,**b)
  for change in (lambda n:n.update(Internal=False),lambda n:n['Labels'].update({'io.h044.vision.nonce':'e'*64}),lambda n:n['Containers'].update({'f'*64:{'IPv4Address':'172.31.243.4/28'}})):
   n,c,b=self.fixture();change(n)
   with self.assertRaises(control.Refused):control.validate_network_owners(self.graph,n,c,**b)
 def test_actual_second_network_or_published_port_rejected(self):
  for mutate in (lambda c:c['interpretation']['NetworkSettings']['Networks'].update(other={}),lambda c:c['interpretation']['HostConfig'].update(PortBindings={'18191/tcp':[{'HostPort':'18191'}]})):
   n,c,b=self.fixture();mutate(c)
   with self.assertRaises(control.Refused):control.validate_network_owners(self.graph,n,c,**b)
 def test_root_current_readback_uses_original_ids_and_receipts(self):
  n,c,b=self.fixture();owners=[{'role':role,'id':cid,'nonce':b['nonce'],'bootId':'boot'} for role,cid in b['container_ids'].items()]
  def read(path,uid):return control.canonical(dict(id=b['network_id'],nonce=b['nonce'],bootId='boot') if '/network-' in path else owners)
  values={b['network_id']:n,**{b['container_ids'][role]:value for role,value in c.items()}}
  def selected(argv):return {'exitCode':0},control.canonical(values[argv[-1]])
  with mock.patch.object(control,'read_private',side_effect=read),mock.patch.object(Path,'read_text',return_value='boot'),mock.patch.object(observer,'selected',side_effect=selected) as readback:
   self.assertEqual(control.verify_current_network(self.graph,b['nonce'])['containerIds'],b['container_ids']);self.assertEqual(readback.call_count,3)
 def test_residency_invokes_current_network_validation(self):
  owners=[{'role':role,'id':str(i),'nonce':'d'*64} for i,role in enumerate(control.MODEL_ADDRESSES)]
  sample={'containers':[{'value':{'id':o['id']}} for o in owners]}
  with mock.patch.object(observer,'snapshot',return_value=sample),mock.patch.object(observer,'protected_instances',return_value=[]),mock.patch.object(control,'verify_current_network',side_effect=control.Refused('wrong_network')) as check:
   with self.assertRaisesRegex(control.Refused,'wrong_network'):observer.residency_sample(self.graph,owners)
   self.assertEqual(check.call_count,1)
 def test_load_rejects_network_before_returning_owners(self):
  graph=copy.deepcopy(self.graph);graph['rootOwnerEvidence']['imageId']='sha256:'+'e'*64
  with mock.patch.object(lifecycle,'check_enabled'),mock.patch.object(lifecycle,'record_created',side_effect=[{'id':'a'*64},{'id':'b'*64},{'id':'c'*64}]),mock.patch.object(lifecycle,'start_created',side_effect=lambda created,*args:created),mock.patch.object(control,'exclusive') as journal,mock.patch.object(control,'verify_current_network',side_effect=control.Refused('wrong_network')) as check:
   with self.assertRaisesRegex(control.Refused,'wrong_network'):lifecycle.load(graph,'d'*64,0)
   self.assertEqual(journal.call_count,1);check.assert_called_once_with(graph,'d'*64)

if __name__=='__main__':unittest.main()
