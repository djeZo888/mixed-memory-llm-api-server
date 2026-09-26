"""Exact scoped NUMA seccomp admission; no GPU/live acceptance claims."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('flash_owner',root/'scripts/runtime/flash/owner.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class NumaSeccomp(unittest.TestCase):
 def test_exact_profile_and_legacy_are_separately_bound(self):
  profile=json.loads((root/'scripts/runtime/flash/numa-seccomp.json').read_text())
  config={'numa_seccomp_sha256':m.NUMA_SECCOMP_SHA256}
  options=['no-new-privileges','seccomp='+json.dumps(profile)]
  self.assertTrue(m.security_options_valid(options,config))
  self.assertTrue(m.security_options_valid(['no-new-privileges'],{}))
  self.assertFalse(m.security_options_valid(['no-new-privileges'],config))
  self.assertFalse(m.security_options_valid(options,{}))
  self.assertFalse(m.security_options_valid(['no-new-privileges','seccomp=unconfined'],config))
  bad=copy.deepcopy(profile);bad['defaultAction']='SCMP_ACT_ALLOW'
  self.assertFalse(m.security_options_valid(['no-new-privileges','seccomp='+json.dumps(bad)],config))
if __name__=='__main__':unittest.main()
