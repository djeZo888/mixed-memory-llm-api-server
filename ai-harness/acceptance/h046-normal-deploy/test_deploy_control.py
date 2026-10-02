"""Local pure/fixture denial tests only; no Linux deployment or inference."""
import copy
import hashlib
import hmac
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('deploy_control',Path(__file__).with_name('deploy_control.py'))
c=importlib.util.module_from_spec(spec); spec.loader.exec_module(c)

class Controls(unittest.TestCase):
    def setUp(self):
        self.key=b'k'*32; self.helper=Path('/root/deploy_control.py'); self.helper_sha='a'*64
        self.b={k:{} for k in c.ROOT_FIELDS}
        self.b.update(schema=c.SCHEMA,operation=c.STAGE,approvedBy='root',
         goId='ed7e33b9-c44b-4b88-9596-9173532a18c9',issuedUtc='2026-10-02T12:00:00Z',
         expiresUtc='2026-10-02T12:05:00Z',invocations=1,retries=0,
         counts={'stage':1,'restart':0,'rollback':[]},hostBootId='boot',sourceCommit='b'*40,
         helper={'path':str(self.helper),'sha256':self.helper_sha,'uid':0},
         owner={'uid':1000,'gid':1000,'bootId':'boot'},
         unit={'path':'/home/user/.config/systemd/user/ai-harness.service'},
         release={'path':'/opt/ai-harness/releases/'+'b'*40+'-h046-normal05'})
        self.now=c.timestamp('2026-10-02T12:01:00Z')
    def envelope(self,body=None):
        body=self.b if body is None else body
        return {'body':body,'seal':hmac.new(self.key,c.canonical(body),hashlib.sha256).hexdigest()}
    def validate(self,body=None,now=None):
        return c.validate_go(self.envelope(body),self.key,self.now if now is None else now,self.helper,self.helper_sha)
    def denied(self,field,value):
        b=copy.deepcopy(self.b); b[field]=value
        with self.assertRaises((c.Denied,ValueError,TypeError,KeyError)): self.validate(b)
    def test_fresh_stage_signed_go(self): self.assertEqual(self.validate()['operation'],c.STAGE)
    def test_separate_restart_go_and_optional_rollback(self):
        for rollback in ([],c.ROLLBACK):
            b=copy.deepcopy(self.b); b['operation']=c.RESTART; b['counts']={'stage':0,'restart':1,'rollback':rollback}
            self.assertEqual(self.validate(b)['counts']['restart'],1)
    def test_modified_body_without_new_seal_denied(self):
        e=self.envelope(copy.deepcopy(self.b)); e['body']['invocations']=2
        with self.assertRaises(c.Denied): c.validate_go(e,self.key,self.now,self.helper,self.helper_sha)
    def test_bad_hmac_denied(self):
        e=self.envelope(); e['seal']='0'*64
        with self.assertRaises(c.Denied): c.validate_go(e,self.key,self.now,self.helper,self.helper_sha)
    def test_expired_go_denied(self):
        with self.assertRaises(c.Denied): self.validate(now=c.timestamp('2026-10-02T12:05:00Z'))
    def test_not_issued_go_denied(self):
        with self.assertRaises(c.Denied): self.validate(now=c.timestamp('2026-10-02T11:59:59Z'))
    def test_deadline_reserve_denied(self):
        with self.assertRaises(c.Denied): self.validate(now=c.timestamp('2026-10-02T12:04:30Z'))
    def test_old_phase_or_unknown_operation_denied(self): self.denied('operation','H045_PROMOTE')
    def test_combined_stage_restart_is_not_authority(self): self.denied('operation','STAGE_COMPILED_AND_RESTART_NORMAL_NO_INFERENCE')
    def test_retired_approval_label_denied(self): self.denied('approvedBy','historical-root')
    def test_retries_denied(self): self.denied('retries',1)
    def test_multiple_invocations_denied(self): self.denied('invocations',2)
    def test_boolean_invocations_denied(self): self.denied('invocations',True)
    def test_unknown_root_field_denied(self):
        b=copy.deepcopy(self.b); b['browserTrialSettled']=True
        with self.assertRaises(c.Denied): self.validate(b)
    def test_rollback_not_enumerated_denied(self): self.denied('counts',{'stage':1,'restart':0,'rollback':['restart']})
    def test_stage_cannot_restart(self): self.denied('counts',{'stage':1,'restart':1,'rollback':[]})
    def test_boolean_counts_denied(self): self.denied('counts',{'stage':True,'restart':False,'rollback':[]})
    def test_source_head_release_binding_denied(self): self.denied('release',{'path':'/opt/ai-harness/releases/old-h045'})
    def test_helper_byte_mismatch_denied(self): self.denied('helper',{'path':str(self.helper),'sha256':'c'*64,'uid':0})
    def test_unknown_unit_denied(self): self.denied('unit',{'path':'/etc/systemd/system/unrelated.service'})
    def test_pins_owner_changed_denied(self): self.denied('owner',{'uid':0,'gid':0,'bootId':'boot'})
    def test_duplicate_json_keys_denied(self):
        with self.assertRaises(c.Denied): c.strict_json(b'{"a":1,"a":2}')
    def test_nonfinite_json_denied(self):
        with self.assertRaises(c.Denied): c.strict_json(b'{"a":NaN}')
    def test_relative_paths(self):
        self.assertEqual(c.relative('ai-harness/server/dist/main.js'),'ai-harness/server/dist/main.js')
        for value in ('/etc/passwd','../escape','a/../b','a//b','a/./b','a\\b','a\nfoo',''):
            with self.subTest(value=value),self.assertRaises(c.Denied): c.relative(value)
    def archive(self,members):
        raw=io.BytesIO()
        with tarfile.open(fileobj=raw,mode='w') as a:
            for name,body,kind in members:
                m=tarfile.TarInfo(name); m.type=kind; m.size=len(body) if kind==tarfile.REGTYPE else 0
                if kind==tarfile.SYMTYPE: m.linkname='../escape'
                a.addfile(m,io.BytesIO(body) if kind==tarfile.REGTYPE else None)
        return raw.getvalue()
    def test_exact_archive_accepts_bytes(self):
        raw=self.archive([('ai-harness/server/dist/main.js',b'export{}',tarfile.REGTYPE)])
        self.assertEqual(c.archive_members(raw,{'ai-harness/server/dist/main.js':c.sha(b'export{}')}),{'ai-harness/server/dist/main.js':b'export{}'})
    def test_archive_traversal_denied(self):
        raw=self.archive([('../escape',b'x',tarfile.REGTYPE)])
        with self.assertRaises(c.Denied): c.archive_members(raw,{'../escape':c.sha(b'x')})
    def test_archive_symlink_denied(self):
        raw=self.archive([('a',b'',tarfile.SYMTYPE)])
        with self.assertRaises(c.Denied): c.archive_members(raw,{'a':c.sha(b'')})
    def test_archive_duplicate_denied(self):
        raw=self.archive([('a',b'x',tarfile.REGTYPE),('a',b'x',tarfile.REGTYPE)])
        with self.assertRaises(c.Denied): c.archive_members(raw,{'a':c.sha(b'x')})
    def test_archive_extra_denied(self):
        raw=self.archive([('a',b'x',tarfile.REGTYPE),('b',b'y',tarfile.REGTYPE)])
        with self.assertRaises(c.Denied): c.archive_members(raw,{'a':c.sha(b'x')})
    def test_archive_missing_denied(self):
        raw=self.archive([('a',b'x',tarfile.REGTYPE)])
        with self.assertRaises(c.Denied): c.archive_members(raw,{'a':c.sha(b'x'),'b':c.sha(b'y')})
    def test_archive_wrong_sha_denied(self):
        raw=self.archive([('a',b'x',tarfile.REGTYPE)])
        with self.assertRaises(c.Denied): c.archive_members(raw,{'a':'0'*64})
    def test_json_pointer_decodes(self): self.assertEqual(c.pointer({'a/b':{'~c':'NORMAL'}},'/a~1b/~0c'),'NORMAL')
    def test_process_birth_absence_and_pid_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve(); (root/'12').mkdir()
            fields=['S','1','12','12']+['0']*15+['345']+['0']*8
            (root/'12/stat').write_text('12 (proc) '+' '.join(fields))
            self.assertFalse(c.owner_absent({'pid':12,'startTicks':'345'},root))
            self.assertTrue(c.owner_absent({'pid':12,'startTicks':'234'},root))
            self.assertFalse(c.group_absent(12,root)); self.assertTrue(c.group_absent(99,root))
            (root/'12/stat').unlink(); self.assertTrue(c.owner_absent({'pid':12,'startTicks':'345'},root))
    def test_vision_missing_normal_fails_without_lifecycle(self):
        b=copy.deepcopy(self.b); b['proofs']={'visionNormal':{'receipt':{'path':'/not-present','sha256':'0'*64,'uid':0}}}
        with patch.object(c,'reference',side_effect=FileNotFoundError),self.assertRaises(FileNotFoundError): c.Control(b).vision()
    def test_spent_go_denied_before_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            b=copy.deepcopy(self.b); b['journal']=str(Path(directory).resolve())
            with patch.object(c,'ancestry'),self.assertRaises(c.Denied): c.Control(b).claim()
    def test_dependency_canonical_graph_and_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve(); p=root/'file'; p.write_bytes(b'x'); p.chmod(0o444)
            uid=os.getuid()
            with patch.object(c,'ancestry'):
                self.assertEqual(c.dependency_digest(root,uid),c.sha(c.canonical({'file':{'sha256':c.sha(b'x'),'mode':0o444,'uid':uid}})))
                (root/'escape').symlink_to('../elsewhere')
                with self.assertRaises(c.Denied): c.dependency_digest(root,uid)

class UnitControls(unittest.TestCase):
    def fixture(self):
        root='/opt/ai-harness/releases/'+'b'*40+'-h046-normal05'; launcher=root+'/ai-harness/deploy/run-server.sh'
        args=[launcher,'--node-prefix','/node','--app-dir',root+'/ai-harness','--data-dir','/private/data',
              '--inference-key-file','/private/key','--engine-launcher',root+'/ai-harness/deploy/run-engine.sh',
              '--codex-preview-receipt','/private/preview','--codex-ordinary-entry','/private/approval',
              '--codex-ordinary-entry-key','/private/ordinary-key']
        original=b'[Service]\nExecStart=/old/start\nWorkingDirectory=/old/server\nRestart=no\n'
        candidate=('[Service]\nExecStart='+' '.join(args)+'\nWorkingDirectory='+root+'/ai-harness/server\nRestart=no\n').encode()
        b={'release':{'path':root},'data':{'path':'/private/data'},'owner':{'exe':'/node/bin/node'},
           'proofs':{'ordinaryApproval':{'path':'/private/approval'},'ordinaryKey':{'path':'/private/ordinary-key'}}}
        return original,candidate,{'argv':args},b
    def test_unit_exact_paths_accept(self):
        original,candidate,spec,b=self.fixture(); self.assertEqual(c.unit_candidate(original,candidate,spec,b)['--data-dir'],'/private/data')
    def test_unit_unrelated_directive_change_denied(self):
        original,candidate,spec,b=self.fixture()
        with self.assertRaises(c.Denied): c.unit_candidate(original,candidate+b'ExecStartPre=/bin/true\n',spec,b)
    def test_unit_auto_retry_denied(self):
        original,candidate,spec,b=self.fixture()
        with self.assertRaises(c.Denied): c.unit_candidate(original,candidate.replace(b'Restart=no',b'Restart=always'),spec,b)
    def test_unit_raw_gate_denied(self):
        original,candidate,spec,b=self.fixture(); spec['argv']+=['--codex-image-jobs-reviewed','true']
        candidate=candidate.replace(b'\nWorkingDirectory',b' --codex-image-jobs-reviewed true\nWorkingDirectory')
        with self.assertRaises(c.Denied): c.unit_candidate(original,candidate,spec,b)
    def test_unit_new_protected_paths_accept(self):
        original,candidate,spec,b=self.fixture(); spec['argv']+=['--codex-generation-acceptance','/private/not-yet-published']
        candidate=candidate.replace(b'\nWorkingDirectory',b' --codex-generation-acceptance /private/not-yet-published\nWorkingDirectory')
        self.assertEqual(c.unit_candidate(original,candidate,spec,b)['--codex-generation-acceptance'],'/private/not-yet-published')
    def test_unit_output_pin_change_denied(self):
        original,candidate,spec,b=self.fixture(); spec['argv']+=['--codex-preview-output-limit','1024']
        candidate=candidate.replace(b'\nWorkingDirectory',b' --codex-preview-output-limit 1024\nWorkingDirectory')
        with self.assertRaises(c.Denied): c.unit_candidate(original,candidate,spec,b)


class RegressionControls(unittest.TestCase):
    def test_zero_size_source_allowed_private_approval_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory).resolve()/'empty'; p.write_bytes(b''); p.chmod(0o600)
            with patch.object(c,'ancestry'):
                self.assertEqual(c.protected(p,os.getuid()),b'')
                with self.assertRaises(c.Denied): c.protected(p,os.getuid(),private=True)
    def test_staging_preserves_approved_dependency_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory).resolve(); source=base/'cache'; source.mkdir(); dep=source/'file'; dep.write_bytes(b'x'); dep.chmod(0o644)
            b={'expiresUtc':'2099-01-01T00:00:00Z','sourceCommit':'b'*40,'release':{'path':str(base/'release'),'files':{'ai-harness/source-commit.txt':c.sha(b'head')},'executableFiles':[]},
               'dependencies':[{'source':str(source),'target':'ai-harness/server/node_modules','sha256':'a'*64}]}
            ctl=c.Control(b)
            with patch.object(ctl,'record'),patch.object(c,'dependency_digest',return_value='a'*64),patch.object(c,'protected',side_effect=lambda path,*args:Path(path).read_bytes()):
                ctl.stage({'contents':{'ai-harness/source-commit.txt':b'head'}})
            self.assertEqual((base/'release/ai-harness/server/node_modules/file').stat().st_mode&0o777,0o644)
            self.assertEqual((base/'release/ai-harness/source-commit.txt').stat().st_mode&0o777,0o444)
    def test_private_data_checks_only_leaf_for_private_mask(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve(); root.chmod(0o700)
            old_lstat=Path.lstat
            def service_leaf(path,*args,**kwargs):
                st=old_lstat(path,*args,**kwargs)
                if path==root:
                    values=list(st); values[4]=1000; return os.stat_result(values)
                return st
            with patch.object(Path,'lstat',service_leaf),patch.object(c,'ancestry') as ancestors:
                with self.assertRaises(FileNotFoundError): c.database_state({'path':str(root)})
                ancestors.assert_called_once_with(root.parent,(0,1000),0o022)
            root.chmod(0o755)
            with patch.object(Path,'lstat',service_leaf),patch.object(c,'ancestry'),self.assertRaises(c.Denied): c.database_state({'path':str(root)})

if __name__=='__main__': unittest.main()
