"""Fresh source timestamps and fresh bridge receipts are independent gates."""
import copy,unittest
from test_driver import manifest,sample,Clock
from fan_status import validate_fan
from contract import Refusal
class FanStatus(unittest.TestCase):
 def test_exact_current_controller(self):
  c=Clock();m=manifest();s=sample(m,c)['external_fan'];self.assertEqual(validate_fan(m,s,c()['utc'],c.t)['readback_duty'],40)
 def test_stale_source_cannot_be_refreshed_by_bridge(self):
  c=Clock();m=manifest();s=sample(m,c)['external_fan'];c.advance(16);s.update(received_utc=c()['utc'],received_monotonic=c.t)
  with self.assertRaises(Refusal):validate_fan(m,s,c()['utc'],c.t)
 def test_bridge_death_cannot_be_hidden_by_source_freshness(self):
  c=Clock();m=manifest();s=sample(m,c)['external_fan'];c.advance(6)
  with self.assertRaises(Refusal):validate_fan(m,s,c()['utc'],c.t)
 def test_each_controller_fault_blocks(self):
  c=Clock();m=manifest();source=sample(m,c)['external_fan']
  for key,value in [('pid',43),('state','blocked'),('errors',['uncertain']),('source_bits',[1,0,0]),('mode',3),('readback_duty',80),('actual_tach',0),('actual_tach_units','rpm'),('node_boot_id','old'),('source_sha256','c'*64)]:
   s=copy.deepcopy(source);s['controller'][key]=value
   with self.subTest(key=key),self.assertRaises(Refusal):validate_fan(m,s,c()['utc'],c.t)
if __name__=='__main__':unittest.main()
