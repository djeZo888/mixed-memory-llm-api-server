"""Flash successor and independent passive hardware policy, synthetic only."""
import copy
import unittest
from tests.lifecycle.test_concurrent_profiles import bound,receipt,pair,LifecycleError
from tests.test_node_projection import Cached,sample
from control.node import NodeStatus,SERVICES
from control.node_actions import ActionRequest,NodeActionError

class Integration(unittest.TestCase):
    def successor(self):
        d=bound(pair.QWEN0_PROFILE);value,instance=receipt(d);prior=copy.deepcopy(value)
        b=d['_storage_binding'];b.documents[b.path('data','services/llm-manager/evidence/h008-qwen1-commission.accepted.json')]=prior
        value['h008_flash_source_transition']={'kind':'source-only-flash-integration','predecessor_sha256':pair.receipt_sha256(prior)}
        instance['concurrent_pair_acceptance']['sha256']=pair.receipt_sha256(value)
        return d,value,instance
    def test_successor_retains_dated_qwen_measurements(self):
        d,v,i=self.successor();self.assertEqual(pair.check_acceptance(d,i)['accepted_mode'],'dual-qwen')
        v['evidence'].append('invented recertification');i['concurrent_pair_acceptance']['sha256']=pair.receipt_sha256(v)
        with self.assertRaisesRegex(LifecycleError,'measurements_changed'):pair.check_acceptance(d,i)
    def test_reserved_flash_blocks_old_glm_mode(self):
        d,v,i=self.successor()
        with self.assertRaisesRegex(LifecycleError,'historical_glm_disabled'):pair.check_acceptance(d,i,mode='glm-qwen')
    def test_missing_flash_gpu_only_affects_frontier(self):
        boot='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        values={'boot':sample({'boot_id':boot}), 'inventory':sample({'boot_id':boot,'complete':True,
            'gpu_uuids':[u for k,ids in SERVICES.items() if k!='glm-5.3-flash' for u in ids], 'hardware_faults':{}})}
        for service in ['qwen-gpu0','qwen-gpu1','image','glm-5.3-flash']:
            values[service]=sample({'boot_id':boot,'ready':True,'running':True,'hardware_latched':False,
                'hardware_validation_age_ms':0,'hardware_validated_boot_id':boot,'hardware_validated_gpu_uuids':list(SERVICES[service])})
        values['glm-5.3-flash']=sample({'boot_id':boot,'hardware_latched':True,
            'hardware_latched_boot_id':boot,'ready':False,'reason':'hardware_missing'})
        snapshot=NodeStatus(Cached(values)).snapshot();states={s['service_id']:s for s in snapshot['services']}
        self.assertEqual(states['glm-5.3-flash']['availability'],'unavailable')
        for service in ['qwen-gpu0','qwen-gpu1','image']:self.assertEqual(states[service]['availability'],'available')
    def test_flash_gains_no_service_action_authority(self):
        from control.node_actions import SERVICES as action_services
        self.assertNotIn('glm-5.3-flash',action_services)
if __name__=='__main__':unittest.main()
