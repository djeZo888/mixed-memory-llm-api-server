"""Focused exact-file admission checks; no network, VM or installer work."""
import importlib.util,json,pathlib,tempfile,unittest
spec=importlib.util.spec_from_file_location('prep',pathlib.Path(__file__).with_name('prep.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
BASE=json.loads(pathlib.Path(__file__).parents[2].joinpath('reports/h014-backend-prep-20260927/SELECTED-ARTIFACT.json').read_text())
class Admission(unittest.TestCase):
 def check_manifest(self,v):
  with tempfile.TemporaryDirectory() as d:
   m.RUN=d;pathlib.Path(d,'SELECTED-ARTIFACT.json').write_text(json.dumps(v));return m.manifest()
 def test_exact_pass(self):self.assertEqual(len(self.check_manifest(BASE)['files']),13)
 def test_code_commit_not_model_revision(self):
  v=dict(BASE,revision='54744f3d16d237837919ae604ce78b90731bcb4c')
  with self.assertRaisesRegex(RuntimeError,'artifact_identity'):self.check_manifest(v)
 def test_extra_flash_refused(self):
  v=dict(BASE,files=BASE['files']+[BASE['files'][0]])
  with self.assertRaisesRegex(RuntimeError,'artifact_files'):self.check_manifest(v)
 def test_bad_hash_refused(self):
  v=json.loads(json.dumps(BASE));v['files'][0]['lfs']['sha256']='invalid'
  with self.assertRaisesRegex(RuntimeError,'artifact_size_hash'):self.check_manifest(v)
if __name__=='__main__':unittest.main()
