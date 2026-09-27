import hashlib,importlib.util,pathlib,subprocess,tempfile,unittest,os
spec=importlib.util.spec_from_file_location('rollback',pathlib.Path(__file__).with_name('rollback-managed-profiles.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
source=pathlib.Path(__file__).resolve().parents[2]
new=subprocess.check_output(['node','--input-type=module','-e',"import {frontierAgentMarkdown} from './ai-harness/deploy/engine/configure-profile.mjs'; process.stdout.write(frontierAgentMarkdown())"],cwd=source)
class Rollback(unittest.TestCase):
 def test_dry_run_apply_idempotence_and_custom_preservation(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp).resolve();p=root/'one/state/agents/frontier/agent.md';p.parent.mkdir(parents=True,mode=0o700);p.write_bytes(new);p.chmod(0o600)
   history=root/'one/history.json';history.write_bytes(b'preserve identity and history')
   self.assertEqual(m.migration(root)['exact_1m_to_480k'],1);self.assertEqual(p.read_bytes(),new)
   custom=root/'two/state/agents/frontier/agent.md';custom.parent.mkdir(parents=True,mode=0o700);custom.write_bytes(new+b'custom');custom.chmod(0o600)
   with self.assertRaisesRegex(AssertionError,'custom'):m.migration(root,True)
   self.assertEqual(p.read_bytes(),new);custom.unlink();custom.parent.rmdir()
   self.assertEqual(m.migration(root,True)['exact_1m_to_480k'],1);self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),m.OLD)
   self.assertEqual(m.migration(root,True)['already_480k'],1);self.assertEqual(history.read_bytes(),b'preserve identity and history')
 def test_unsafe_links_and_modes_refused(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp).resolve();p=root/'state/agents/frontier/agent.md';p.parent.mkdir(parents=True,mode=0o700);p.write_bytes(new);p.chmod(0o620)
   with self.assertRaisesRegex(AssertionError,'unsafe'):m.migration(root,True)
   p.chmod(0o600);os.link(p,root/'linked')
   with self.assertRaisesRegex(AssertionError,'unsafe'):m.migration(root,True)
   (root/'linked').unlink();p.unlink();p.symlink_to(root/'other')
   with self.assertRaisesRegex(AssertionError,'unsafe'):m.migration(root,True)
if __name__=='__main__':unittest.main()
