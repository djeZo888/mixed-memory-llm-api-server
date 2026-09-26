"""Production passive adapter seams; fixture HTTP only, no native inference."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from control import node_observation as n
from control.node import NodeStatus, SERVICES
from tests.test_node_projection import Cached, sample

BOOT = '37e425eb-3d3e-4070-80a0-5ecfb39604f1'
OLD = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
DEPLOY = next(iter(n.DEPLOYMENTS))
IDENTITY = {'id': 'a'*64, 'name': 'llmctl-'+DEPLOY, 'image_id': 'sha256:'+'b'*64,
            'owner': n.TEXT_OWNER, 'instance': 'test-instance', 'deployment': DEPLOY}
SLOT = {'selected': DEPLOY, 'generation': 7, 'desired': 'running', 'pending_create': None, 'container': IDENTITY}

class Binding:
    def __init__(self): self.slot = copy.deepcopy(SLOT)
    def path(self, role, suffix): return '/data/'+suffix
    def validate_path(self, role, path): return Path(path)
    def read_json(self, role, path):
        if path.endswith('deployment-instance.json'): return {'id': 'test-instance'}
        return {'schema_version': 3, 'slots': {'glm': self.slot, 'qwen': {}}}

class PassiveProductionTests(unittest.TestCase):
    def setUp(self):
        self.binding = Binding(); self.calls=[]; self.latch = {'hardware_latched': False, 'hardware_latched_boot_id': None, 'reason': None,
            'identity': [[SERVICES['qwen-gpu0'][0],BOOT,'validated']], 'hardware_validation_age_ms':0,
            'hardware_validated_boot_id':BOOT,'hardware_validated_gpu_uuids':list(SERVICES['qwen-gpu0'])}
        def run(argv, seconds):
            self.calls.append(argv)
            return json.dumps([IDENTITY['id'], '/'+IDENTITY['name'], IDENTITY['image_id'], True,
                               '2026-09-25T10:00:00Z', 1234, n.TEXT_OWNER, 'test-instance', DEPLOY])
        self.reader=n.CanonicalIdentityReader(run=run,boot=lambda:{'boot_id':BOOT},binding=lambda _:self.binding,
            latch=lambda *_:dict(self.latch),read=self.read)
    def read(self,path,**kwargs):
        if path.parent == n.PROFILE_ROOT:
            return json.dumps(dict(id=DEPLOY,container_name='llmctl-'+DEPLOY,
                endpoint=dict(host='127.0.0.1',port=30002,api_prefix='/v1',served_model='qwen3.8-27b-gpu0'),
                launch=dict(context_size=480000,gpus=list(SERVICES['qwen-gpu0'])))).encode()
        return b'fixture-secret-key-never-exported-1234'

    def test_real_canonical_container_labels_and_selection_projection(self):
        row=self.reader.service('qwen-gpu0')
        self.assertEqual(row['canonical_generation'],7)
        self.assertEqual(row['configured_context_tokens'],480000)
        self.assertEqual(row['model_alias'],'qwen3.8-27b-gpu0')
        self.assertTrue(row['ownership_valid']);self.assertIsNone(row['ready'])
        self.assertEqual(row['owner_identity']['pid'],1234)
        self.assertNotIn('.Config.Env',str(self.calls)); self.assertNotIn('/health',str(self.calls))
        self.binding.slot['container']['instance']='wrong'
        self.assertFalse(self.reader.service('qwen-gpu0')['ownership_valid'])
    def test_passive_auth_route_exact_alias_and_no_idle_claim(self):
        calls=[]
        def get(port,path,key,seconds):
            calls.append((port,path,key))
            return 200, {'schema_version':1,'model_alias':'qwen3.8-27b-gpu0','ready':True,'state':'up','admitting':None}
        row=n.PassiveServiceCollector('qwen-gpu0',self.reader,get=get)(2)
        self.assertTrue(row['ready']);self.assertIsNone(row['admitting']);self.assertEqual(row['activity'],'unknown')
        self.assertIsNone(row['queue_depth']);self.assertIsNone(row['active_requests'])
        self.assertEqual(calls[0][:2],(30002,'/v1/readiness'))
        self.assertNotIn('fixture-secret',json.dumps(row))
    def test_identity_generation_excludes_readiness_but_changes_selection_latch_owner(self):
        first=self.reader.service('qwen-gpu0')['generation']
        self.binding.slot['observed']='unhealthy';self.binding.slot['updated_at']=999
        self.assertEqual(self.reader.service('qwen-gpu0')['generation'],first)
        self.binding.slot['generation']+=1
        self.assertNotEqual(self.reader.service('qwen-gpu0')['generation'],first)
        second=self.reader.service('qwen-gpu0')['generation']
        self.latch.update(hardware_latched=True,hardware_latched_boot_id=OLD,reason='hardware_missing',identity=[[SERVICES['qwen-gpu0'][0],OLD,'hardware_missing']])
        self.assertNotEqual(self.reader.service('qwen-gpu0')['generation'],second)
    def test_sticky_hardware_latch_survives_http_success(self):
        self.latch.update(hardware_latched=True,hardware_latched_boot_id=OLD,reason='hardware_missing',identity=[[SERVICES['qwen-gpu0'][0],OLD,'hardware_missing']])
        row=n.PassiveServiceCollector('qwen-gpu0',self.reader,get=lambda *_:(200,{
            'schema_version':1,'model_alias':'qwen3.8-27b-gpu0','ready':True,'state':'up','admitting':None}))(2)
        self.assertFalse(row['ready']);self.assertEqual(row['hardware_latched_boot_id'],OLD)
        snapshot=NodeStatus(Cached({'boot':sample({'boot_id':BOOT}),'qwen-gpu0':sample(row)})).snapshot()
        service=snapshot['services'][0]
        self.assertEqual(service['hardware_latched_boot_id'],OLD)
        self.assertEqual(service['availability'],'unavailable')
    def test_readiness_auth_timeout_wrong_alias_are_unknown_not_missing(self):
        for callback in (lambda *_:(401,{}), lambda *_:(200,{'schema_version':1,'model_alias':'wrong','ready':True,'state':'up','admitting':None})):
            row=n.PassiveServiceCollector('qwen-gpu0',self.reader,get=callback)(2)
            self.assertIsNone(row['ready']);self.assertFalse(row['hardware_latched'])
            self.assertEqual(row['reason'],'readiness_unknown')
    def test_strict_up_and_http_status_pair(self):
        for state in ('starting','unhealthy','unknown'):
            value={'schema_version':1,'model_alias':'m','ready':False,'state':state,'admitting':None}
            self.assertFalse(n.text_readiness(503,value,'m')['ready'])
            with self.assertRaises(ValueError):n.text_readiness(200,value,'m')
        with self.assertRaises(ValueError):n.text_readiness(200,{'schema_version':True,'model_alias':'m','ready':True,'state':'up','admitting':None},'m')
    def test_busy_image_is_available_backpressure_without_idle_inference(self):
        value={'model':n.IMAGE_ALIAS,'ready':True,'admitting':False,'busy':True,'state':'ready'}
        row=n.image_readiness(200,value)
        row.update(boot_id=BOOT, hardware_latched=False, hardware_validation_age_ms=0,
            hardware_validated_boot_id=BOOT,hardware_validated_gpu_uuids=list(SERVICES['image']))
        snapshot=NodeStatus(Cached({'boot':sample({'boot_id':BOOT}),'image':sample(row)})).snapshot()
        service=next(s for s in snapshot['services'] if s['service_id']=='image')
        self.assertEqual(service['availability'],'available');self.assertFalse(service['admitting'])
        self.assertEqual(service['activity'],'busy')
        value.update(busy=False,admitting=True)
        self.assertEqual(n.image_readiness(200,value)['activity'],'unknown')
    def test_fault_map_and_malformed_fault_metadata(self):
        gpu=SERVICES['qwen-gpu0'][0]
        base={'boot_id':BOOT,'complete':True,'gpu_uuids':[],'hardware_faults':{gpu:'gpu_fallen_off_bus'}}
        def snapshot(inv):return NodeStatus(Cached({'boot':sample({'boot_id':BOOT}),'inventory':sample(inv)})).snapshot()['inventory']
        self.assertEqual(snapshot(base)['hardware_faults'],base['hardware_faults'])
        for bad in ({gpu:'NVML init failed'}, [], {'0':'gpu_fallen_off_bus'}):
            row=snapshot({**base,'hardware_faults':bad})
            self.assertFalse(row['complete']);self.assertEqual(row['state'],'unknown')
    def test_late_process_failure_cannot_refresh_old_negative_hardware_proof(self):
        clock = [0.0]
        self.reader.clock = lambda: clock[0]
        self.latch['hardware_validation_age_ms'] = 14000
        def fail_after_latch(*_):
            clock[0] = 1.8  # Total collector remains under 2s, proof is now 15.8s old.
            raise TimeoutError('fixture-process-timeout')
        self.reader.run = fail_after_latch
        collector = n.PassiveServiceCollector('qwen-gpu0', self.reader, clock=lambda: clock[0])
        row = collector(2)
        self.assertIsNone(row['hardware_latched'])
        snapshot = NodeStatus(Cached({'boot': sample({'boot_id': BOOT}),
                                     'qwen-gpu0': sample(row)})).snapshot()
        service = snapshot['services'][0]
        self.assertIsNone(service['hardware_latched'])
        self.assertEqual(service['availability'], 'unknown')
        self.assertIsNone(service['generation'])

    def test_process_failure_keeps_authoritative_inherited_positive_latch(self):
        self.latch.update(hardware_latched=True,hardware_latched_boot_id=OLD,reason='hardware_missing',identity=[[SERVICES['qwen-gpu0'][0],OLD,'hardware_missing']])
        self.reader.run=lambda *_: (_ for _ in ()).throw(TimeoutError())
        row=self.reader.service('qwen-gpu0')
        self.assertTrue(row['hardware_latched']);self.assertEqual(row['hardware_latched_boot_id'],OLD)
        self.assertIsNone(row['generation']);self.assertFalse(row['ownership_valid']);self.assertFalse(row['ready'])

    def test_passive_prior_positive_survives_registration_outage_until_valid_newboot(self):
        self.latch.update(hardware_latched=True,hardware_latched_boot_id=BOOT,reason='hardware_missing')
        collector=n.PassiveServiceCollector('qwen-gpu0',self.reader)
        self.assertTrue(collector(2)['hardware_latched'])
        original=self.reader.binding
        self.reader.binding=lambda _: (_ for _ in ()).throw(OSError())
        row=collector(2)
        self.assertTrue(row['hardware_latched']);self.assertEqual(row['hardware_latched_boot_id'],BOOT)
        self.reader.boot=lambda:{'boot_id':OLD}
        self.assertTrue(collector(2)['hardware_latched'])
        self.reader.binding=original
        self.latch.update(hardware_latched=False,hardware_latched_boot_id=None,reason=None,hardware_validated_boot_id=OLD)
        self.assertFalse(collector(2)['hardware_latched'])

    def test_image_startup_is_temporary_unknown_not_permanent_unavailable(self):
        row=n.image_readiness(200,dict(model=n.IMAGE_ALIAS,ready=False,admitting=False,busy=False,state='startup'))
        row.update(boot_id=BOOT,hardware_latched=False)
        snapshot=NodeStatus(Cached({'boot':sample({'boot_id':BOOT}),'image':sample(row)})).snapshot()
        image=next(row for row in snapshot['services'] if row['service_id']=='image')
        self.assertEqual(image['availability'],'unknown')

    def test_profile_metadata_preserves_qualified_geometry_no_transparency_expansion(self):
        profile=dict(operation='edit',size='1920x1080',references=1,transparent=False,
                     evidence_sha256='a'*64,native_size='1920x1088',crop_bottom=8)
        self.assertEqual(n.profiles([profile])[0]['references'],1)
        for changes in ({'transparent':True},{'references':2},{'crop_bottom':0}):
            with self.assertRaises(ValueError):n.profiles([{**profile,**changes}])

    def test_unreadable_installed_profile_is_unknown_without_blocking_owner_stop_identity(self):
        self.reader.read=lambda *_a,**_kw: (_ for _ in ()).throw(OSError())
        row=self.reader.service('qwen-gpu0')
        self.assertTrue(row['ownership_valid']);self.assertIsNone(row['configured_context_tokens'])
        self.assertEqual(row['installed_capabilities'],[])

    def test_old_invocation_settlement_requires_absence_or_concrete_changed_process(self):
        old=dict(container_id='a'*64,pid=1234,started_at='2026-09-25T10:00:00Z')
        outputs=['a'*64+'\n',json.dumps(['a'*64,True,1234,old['started_at']])]
        def run(*_):return outputs.pop(0)
        self.reader.run=run
        self.assertFalse(self.reader.old_owner_settled('image',old))
        outputs.extend(['a'*64+'\n',json.dumps(['a'*64,False,0,old['started_at']])])
        self.assertTrue(self.reader.old_owner_settled('image',old))
        outputs.extend(['a'*64+'\n',json.dumps(['a'*64,True,2345,'2026-09-25T11:00:00Z'])])
        self.assertTrue(self.reader.old_owner_settled('qwen-gpu0',old))
        outputs.extend([''])
        self.assertTrue(self.reader.old_owner_settled('image',old))
        outputs.extend(['a'*64+'\n',json.dumps(['a'*64,False,1234,old['started_at']])])
        self.assertFalse(self.reader.old_owner_settled('image',old))
        self.reader.run=lambda *_: (_ for _ in ()).throw(TimeoutError())
        with self.assertRaises(TimeoutError):self.reader.old_owner_settled('image',old)

    def test_canonical_action_cas_uses_same_token_no_readiness(self):
        class Lease:
            def validate(self):pass
        class Request:service_id='qwen-gpu0';gpu_uuid=None
        expected=self.reader.service('qwen-gpu0')['generation']
        row=self.reader(Request(),Lease(),self.reader.clock()+2)
        self.assertEqual(row['generation'],expected);self.assertEqual(row['affected_services'],['qwen-gpu0'])

if __name__=='__main__':unittest.main()
