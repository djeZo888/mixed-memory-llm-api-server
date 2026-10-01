import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime_plan import plan
ROOT=Path(__file__).resolve().parents[3]
class RuntimeTests(unittest.TestCase):
    def setUp(self):self.config=json.loads((ROOT/'configs/vision/h043-candidate.json').read_text())
    def test_exact_disabled_graph(self):
        p=plan(self.config);self.assertFalse(p['execute']);self.assertEqual(p['gpuUuidProposed'],'GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf');self.assertEqual(len(p['servers']),2)
        for s in p['servers']:
            self.assertFalse(s['execute']);self.assertFalse(s['remoteCodeExecution']);self.assertNotIn('--trust-remote-code',s['argv']);self.assertIn('--disable-uvicorn-access-log',s['argv']);self.assertIn('VLLM_API_KEY',s['environment']);self.assertEqual(s['environment']['HF_HUB_OFFLINE'],'1')
        self.assertFalse(p['ownerGraph']['privateIngress']['enabled']);self.assertTrue(p['ownerGraph']['telemetry'])
    def test_reject_activation_profile_pins_and_budget(self):
        for mutate in [lambda c:c.update(activation='ENABLED'),lambda c:c['service'].update(enabled=True),lambda c:c['profiles']['16k'].update(maxImagePixels=2097153),lambda c:c['models'][0].update(revision='0'*40),lambda c:c['models'][0].update(gpuMemoryUtilization=.9)]:
            c=copy.deepcopy(self.config);mutate(c)
            with self.assertRaises(ValueError):plan(c)
    def test_h039_plan_still_readable_history_unmodified(self):
        c=json.loads((ROOT/'configs/vision/h039-candidate.json').read_text());self.assertFalse(plan(c)['execute']);self.assertFalse(plan(c,'32k')['execute'])
if __name__=='__main__':unittest.main()
