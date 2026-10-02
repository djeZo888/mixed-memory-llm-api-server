"""Local pure/fixture denial tests only; no Linux deployment or inference."""
import copy
from contextlib import contextmanager
import hashlib
import hmac
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import shlex
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

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

class RestartKeyRoleControls(unittest.TestCase):
    @contextmanager
    def fixture(self):
        # Real reads/chmod and ancestry checks; only Linux ownership is simulated
        # because this source phase runs on a Mac without UID1000/root files.
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory).resolve(); keydir=base/'ordinary'; godir=base/'root-go'
            keydir.mkdir(mode=0o700); godir.mkdir(mode=0o700)
            keypath=keydir/'existing-key'; keypath.write_bytes(b'k'*32); keypath.chmod(0o600)
            gopath=godir/'RESTART.signed.json'; gopath.write_bytes(b'{}'); gopath.chmod(0o600)
            actual_lstat=Path.lstat; overrides={}
            def linux_metadata(path,*args,**kwargs):
                st=actual_lstat(path,*args,**kwargs)
                values={name:getattr(st,name) for name in dir(st) if name.startswith('st_')}
                values['st_uid']=1000 if path in (keypath,keydir) else 0
                if c.stat.S_ISDIR(st.st_mode) and path not in (keydir,godir): values['st_mode']&=~0o022
                fields=('st_mode','st_ino','st_dev','st_nlink','st_uid','st_gid','st_size')
                for index,value in overrides.get(path,{}).items(): values[fields[index]]=value
                return SimpleNamespace(**values)
            with patch.object(Path,'lstat',linux_metadata):
                source=Controls(); source.setUp(); b=copy.deepcopy(source.b)
                b.update(operation=c.RESTART,counts={'stage':0,'restart':1,'rollback':[]},
                         proofs={'ordinaryKey':{'path':str(keypath),'identity':c.identity(keypath)},
                                 'ordinaryApproval':{'path':str(base/'original-approval')},'visionNormal':{'enabled':False}},
                         configFiles=[])
                yield base,keypath,gopath,b,source,overrides
    def test_exact_restart_reader_and_root_go_main_without_key_hash(self):
        with self.fixture() as (base,keypath,gopath,b,source,overrides):
            self.assertEqual(c.restart_ordinary_key(str(keypath),b),source.key)
            helper=Path(c.__file__).resolve()
            b['helper']={'path':str(helper),'sha256':c.sha(helper.read_bytes()),'uid':0}
            gopath.write_bytes(c.canonical(source.envelope(b))+b'\n')
            with patch.object(c.sys,'platform','linux'),patch.object(c.os,'geteuid',return_value=0),\
                 patch.object(c.sys,'argv',['deploy_control','--go',str(gopath),'--go-key',str(keypath)]),\
                 patch.object(c.time,'time',return_value=source.now),patch.object(c,'protected',wraps=c.protected) as reads,\
                 patch.object(c,'sha',wraps=c.sha) as hashes,patch.object(c.Control,'execute',side_effect=AssertionError('live execute')),\
                 patch.object(c.Control,'preflight',return_value={'owner':{},'vision':{'enabled':False}}) as preflight,\
                 patch.object(c.sys,'stdout',new_callable=io.StringIO) as stdout:
                c.main(); preflight.assert_called_once()
                self.assertEqual(json.loads(stdout.getvalue())['mutations'],0)
                self.assertTrue(any(str(call.args[0])==str(keypath) and call.args[1:]==(1000,32,True) for call in reads.call_args_list))
                self.assertFalse(any(call.args[0]==source.key for call in hashes.call_args_list))
                gopath.chmod(0o400)
                with self.assertRaisesRegex(c.Denied,'root0600'): c.main()
                gopath.chmod(0o600); gopath.parent.chmod(0o755)
                with self.assertRaisesRegex(c.Denied,'root0700'): c.main()
                gopath.parent.chmod(0o700); b['operation']=c.STAGE; b['counts']={'stage':1,'restart':0,'rollback':[]}
                gopath.write_bytes(c.canonical(source.envelope(b)))
                with patch.object(c,'restart_ordinary_key',side_effect=AssertionError('STAGE ordinary fallback')),self.assertRaises(c.Denied): c.main()
    def test_key_uid_mode_size_parent_identity_and_alias_refusals(self):
        cases=('uid','mode0400','mode0640','size31','size33','parentUid','parentMode','ancestor',
               'inode','booleanIdentity','linkCount','alias','symlink','pathMismatch','duringRead')
        for case in cases:
            with self.subTest(case=case),self.fixture() as (base,keypath,gopath,b,source,overrides):
                if case=='uid': overrides[keypath]={4:0}
                if case.startswith('mode'): keypath.chmod(int(case[4:],8))
                if case.startswith('size'): keypath.write_bytes(b'k'*int(case[4:]))
                if case=='parentUid': overrides[keypath.parent]={4:0}
                if case=='parentMode': keypath.parent.chmod(0o755)
                if case=='ancestor': overrides[base]={0:c.stat.S_IFDIR|0o777}
                if case=='inode': b['proofs']['ordinaryKey']['identity']['ino']+=1
                if case=='booleanIdentity': b['proofs']['ordinaryKey']['identity']['nlink']=True
                if case=='linkCount': overrides[keypath]={3:2}
                if case in ('uid','mode0400','mode0640','size31','size33','linkCount'):
                    b['proofs']['ordinaryKey']['identity']=c.identity(keypath)
                path=str(keypath)
                if case=='alias': path=str(keypath.parent)+'/../ordinary/existing-key'; b['proofs']['ordinaryKey']['path']=path
                if case=='symlink':
                    alias=keypath.parent/'alias'; alias.symlink_to(keypath); path=str(alias); b['proofs']['ordinaryKey']['path']=path
                if case=='pathMismatch': path=str(base/'native-checkpoint-key')
                if case=='duringRead':
                    actual_read=c.protected
                    def changed(*args):
                        raw=actual_read(*args); keypath.chmod(0o400); return raw
                    with patch.object(c,'protected',side_effect=changed),self.assertRaisesRegex(c.Denied,'changed while reading'):
                        c.restart_ordinary_key(path,b)
                else:
                    with self.assertRaises(c.Denied): c.restart_ordinary_key(path,b)
    def test_config_key_digest_refused_before_any_read_and_loader_path_join(self):
        with self.fixture() as (base,keypath,gopath,b,source,overrides):
            b['configFiles']=[{'path':str(base/'current-source-sidecar'),'uid':1000,'sha256':'a'*64},
                              {'path':str(keypath),'uid':1000,'sha256':'b'*64}]
            with patch.object(c,'reference',side_effect=AssertionError('config read before key exclusion')),\
                 self.assertRaisesRegex(c.Denied,'identity proof'): c.configuration_files(b)
            original,candidate,spec,unitbody=UnitControls().fixture()
            candidate=candidate.replace(b'/private/ordinary-key',str(keypath).encode())
            spec['argv']=[str(keypath) if v=='/private/ordinary-key' else v for v in spec['argv']]
            unitbody['proofs']['ordinaryKey']=b['proofs']['ordinaryKey']
            self.assertEqual(c.unit_candidate(original,candidate,spec,unitbody)['--codex-ordinary-entry-key'],str(keypath))
            unitbody['proofs']['ordinaryKey']['path']=str(base/'native-checkpoint-key')
            with self.assertRaisesRegex(c.Denied,'credential tuple'): c.unit_candidate(original,candidate,spec,unitbody)
    def test_current_restart_preflight_vision_off_with_original_approval(self):
        with self.fixture() as (base,keypath,gopath,b,source,overrides):
            root=base/'release'; root.mkdir(); unit=base/'unit'; unit.write_bytes(b'old')
            overrides[unit]={4:1000}
            q={'binaryVersion':'0.158.0','upstream':'064c6b8c737f5b41d171fdda80bd9ef10ad06eb3'}
            for name in ('launch','settlement','protocolAck','binary'): q.update({name+'Path':str(base/name),name+'Sha256':'c'*64})
            body={'qualification':q}; approval=c.canonical({'body':body,'seal':hmac.new(source.key,c.canonical(body),hashlib.sha256).hexdigest()})
            content={'ai-harness/source-commit.txt':b['sourceCommit'].encode()+b'\n'}
            raw=source.archive([(name,value,tarfile.REGTYPE) for name,value in content.items()])
            ref=lambda name:{'path':str(base/name),'sha256':'a'*64,'uid':1000}
            b.update(journal=str(base/'journal'),release={'path':str(root),'files':{k:c.sha(v) for k,v in content.items()},'executableFiles':[]},
                     archives=[{'archive':ref('archive'),'files':{k:c.sha(v) for k,v in content.items()}}],dependencies=[],
                     unit={'path':str(unit),'sha256':c.sha(b'old'),'candidate':ref('candidate')},data={'path':str(base/'data')},
                     owner={'pid':10,'selectedEnvironment':{'AI_HARNESS_DATA_DIR':str(base/'data')}})
            b['proofs']['ordinaryApproval']=ref('original-approval'); b['configFiles']=[ref('current-source-sidecar')]
            def evidence(item,*args):
                if item['path']==str(base/'archive'): return raw
                if item['path']==str(base/'original-approval'): return approval
                return b'evidence'
            ctl=c.Control(b); original_read=Path.read_text
            def boot(path,*a,**kw): return b['hostBootId'] if str(path)=='/proc/sys/kernel/random/boot_id' else original_read(path,*a,**kw)
            with patch.object(Path,'read_text',boot),patch.object(c,'reference',side_effect=evidence),\
                 patch.object(c,'unit_candidate',return_value={}),patch.object(ctl,'verify_staged') as staged,\
                 patch.object(ctl,'state',return_value={'ActiveState':'active','SubState':'running','NRestarts':'0','MainPID':'10','InvocationID':'id'}),\
                 patch.object(c,'exact_owner',return_value=b['owner']),patch.object(c,'database_state',return_value={'activeRuns':0}),\
                 patch.object(ctl,'remote_vision',side_effect=AssertionError('vision contacted')):
                result=ctl.preflight(); staged.assert_called_once()
                self.assertEqual(result['idle']['activeRuns'],0); self.assertEqual(result['vision']['scope'],'ORDINARY_NO_VISION')

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


class OptionalVisionControls(unittest.TestCase):
    now=c.timestamp('2026-10-02T12:40:00Z')
    def fixture(self):
        owner={'pid':123,'startTicks':456,'ppid':1,'pgid':123,'cgroup':'0::/vision.service\n',
               'exe':'/usr/bin/python3','uid':1000,'bootId':'ai-vm-boot'}
        sources=[{'file':{'path':'/opt/vision/service.py','sha256':'c'*64,'uid':0},'receiptPointer':'/sources/service'}]
        value={'state':'NORMAL','at':'2026-10-02T12:39:59Z','owner':copy.deepcopy(owner),'sources':{'service':'c'*64}}
        v={'enabled':True,'receipt':{'path':'/root/vision-original.json','sha256':'a'*64,'uid':0},
           'reviewedAt':'2026-10-02T12:39:59Z','statePointer':'/state','observedAtPointer':'/at',
           'owner':owner,'ownerPointers':{k:'/owner/'+k for k in owner},'sources':sources,
           'remote':{'host':'10.156.100.60','port':22,'user':'user','bootId':'ai-vm-boot',
                     'identityFile':{'path':'/root/.ssh/existing','identity':{}},
                     'knownHosts':{'path':'/root/.ssh/known_hosts','sha256':'d'*64,'uid':0}}}
        b={'operation':c.RESTART,'expiresUtc':'2099-01-01T00:00:00Z','hostBootId':'ai-harness-boot','proofs':{'visionNormal':v}}
        remote={'host':'ai-vm','bootId':'ai-vm-boot','owner':copy.deepcopy(owner),
                'sources':{'/opt/vision/service.py':'c'*64},'observedAt':'2026-10-02T12:40:00Z'}
        return c.Control(b),value,remote
    def run_proof(self,ctl,value,remote):
        with patch.object(c.time,'time',return_value=self.now),patch.object(c,'reference',return_value=c.canonical(value)),\
             patch.object(ctl,'remote_vision',return_value=remote),patch.object(c,'process',side_effect=AssertionError('local producer join')):
            return ctl.vision()
    def test_stage_has_no_optional_vision_dependency(self):
        for proof in ({},{'visionNormal':{'enabled':True}},{'visionNormal':{'receipt':'absent'}}):
            ctl=c.Control({'operation':c.STAGE,'expiresUtc':'2099-01-01T00:00:00Z','proofs':proof})
            with patch.object(c,'reference',side_effect=AssertionError),patch.object(c,'process',side_effect=AssertionError),\
                 patch.object(ctl,'remote_vision',side_effect=AssertionError):
                self.assertFalse(ctl.vision()['required'])
    def test_ordinary_restart_disabled_vision_has_no_remote_or_receipt_dependency(self):
        ctl,_,_=self.fixture(); ctl.b['proofs']['visionNormal']={'enabled':False}
        with patch.object(c,'reference',side_effect=AssertionError),patch.object(c,'process',side_effect=AssertionError),\
             patch.object(ctl,'remote_vision',side_effect=AssertionError):
            self.assertEqual(ctl.vision()['scope'],'ORDINARY_NO_VISION')
    def test_restart_requires_explicit_boolean_scope(self):
        for value in (None,{}, {'enabled':'false'}, {'enabled':0}, {'enabled':False,'receipt':{}}, {'enabled':True}):
            ctl,_,_=self.fixture(); ctl.b['proofs']['visionNormal']=value
            with self.subTest(value=value),self.assertRaises(c.Denied): ctl.vision()
    def test_enabled_vision_accepts_exact_remote_receipt_birth_and_source(self):
        ctl,value,remote=self.fixture(); result=self.run_proof(ctl,value,remote)
        self.assertTrue(result['required']); self.assertEqual(result['remoteHost'],'10.156.100.60')
        self.assertFalse(result['newQualificationClaimed'])
    def test_enabled_missing_original_receipt_denied(self):
        ctl,_,_=self.fixture()
        with patch.object(c,'reference',side_effect=FileNotFoundError),patch.object(ctl,'remote_vision') as ssh,\
             self.assertRaises(FileNotFoundError): ctl.vision()
        ssh.assert_not_called()
    def test_enabled_wrong_boot_birth_source_stale_and_malformed_remote_denied(self):
        mutations=[lambda r:r.update(bootId='wrong'),lambda r:r['owner'].update(startTicks=457),
                   lambda r:r['owner'].update(uid=True),lambda r:r.update(sources={'/opt/vision/service.py':'0'*64}),
                   lambda r:r.update(observedAt='2026-10-02T12:39:44Z'),
                   lambda r:r.update(observedAt='2026-10-02T12:40:01Z'),lambda r:r.update(host='ai-harness'),
                   lambda r:r.update(extra='unbound')]
        for mutate in mutations:
            ctl,value,remote=self.fixture(); mutate(remote)
            with self.subTest(remote=remote),self.assertRaises(c.Denied): self.run_proof(ctl,value,remote)
    def test_enabled_original_state_owner_source_and_review_staleness_denied(self):
        for key in ('state','birth','source','observedAt','reviewedAt','ownerType'):
            ctl,value,remote=self.fixture()
            if key=='state': value['state']='DEGRADED'
            if key=='birth': value['owner']['startTicks']=999
            if key=='ownerType': value['owner']['ppid']=True
            if key=='source': value['sources']['service']='0'*64
            if key=='observedAt': value['at']='2026-10-02T12:37:59Z'
            if key=='reviewedAt': ctl.b['proofs']['visionNormal']['reviewedAt']='2026-10-02T12:37:59Z'
            with self.subTest(key=key),self.assertRaises(c.Denied): self.run_proof(ctl,value,remote)
    def command_fixture(self,ctl):
        v=ctl.b['proofs']['visionNormal']; key_identity={'dev':1,'ino':2,'uid':0,'gid':0,'mode':0o600,'nlink':1,'size':32,'mtimeNs':1,'ctimeNs':1}
        v['remote']['identityFile']['identity']=key_identity
        return v,key_identity
    def make_argv(self,ctl,v,key_identity):
        with patch.object(c,'absolute',side_effect=Path),patch.object(c,'ancestry'),\
             patch.object(c,'identity',return_value=key_identity),patch.object(Path,'lstat',return_value=Mock(st_mode=0o100600)),\
             patch.object(c,'reference',return_value=b'known host'):
            return ctl.vision_command(v)
    def test_exact_remote_command_is_bounded_no_ambient_config_and_script_compiles(self):
        ctl,_,_=self.fixture(); v,key=self.command_fixture(ctl); argv=self.make_argv(ctl,v,key)
        self.assertEqual(argv[0],'/usr/bin/ssh'); self.assertEqual(argv[-2],'user@10.156.100.60')
        for option in ('StrictHostKeyChecking=yes','IdentityAgent=none','ClearAllForwardings=yes','UpdateHostKeys=no'):
            self.assertIn(option,argv)
        python=shlex.split(argv[-1]); self.assertEqual(python[:5],['/usr/bin/python3','-I','-B','-S','-c'])
        compile(python[5],'<exact-remote-vision-probe>','exec')
        self.assertIn('signal.alarm(10)',python[5]); self.assertNotIn('iterdir',python[5])
    def test_remote_wrong_host_boot_key_inode_sources_denied_before_ssh(self):
        for key in ('host','boot','key','empty','duplicate','source'):
            ctl,_,_=self.fixture(); v,identity=self.command_fixture(ctl)
            if key=='host': v['remote']['host']='10.156.100.61'
            if key=='boot': v['remote']['bootId']='ai-harness-boot'
            if key=='key': v['remote']['identityFile']['identity']=dict(identity,ino=99)
            if key=='empty': v['sources']=[]
            if key=='duplicate': v['sources']*=2
            if key=='source': v['sources'][0]['file']['path']='/opt/../secret'
            with self.subTest(key=key),self.assertRaises(c.Denied): self.make_argv(ctl,v,identity)
    def test_original_birth_schema_retains_integer_ticks_ppid_and_raw_cgroup(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve(); p=root/'123'; p.mkdir(); (root/'sys/kernel/random').mkdir(parents=True)
            (root/'sys/kernel/random/boot_id').write_text('remote-boot\n')
            fields=['S','1','123','123']+['0']*15+['456']+['0']*8
            (p/'stat').write_text('123 (vision) '+' '.join(fields))
            (p/'status').write_text('Uid:\t1000\t1000\t1000\t1000\nGid:\t1000\t1000\t1000\t1000\n')
            (p/'cgroup').write_text('0::/vision.service\n'); (p/'cmdline').write_bytes(b'python3\0vision.py\0')
            (p/'environ').write_bytes(b''); (p/'exe').symlink_to('/usr/bin/python3')
            observed=c.vision_process(123,root)
            self.assertEqual(observed['startTicks'],456); self.assertIs(type(observed['startTicks']),int)
            self.assertEqual(observed['ppid'],1); self.assertEqual(observed['cgroup'],'0::/vision.service\n')
            ctl,_,_=self.fixture(); v,key=self.command_fixture(ctl); argv=self.make_argv(ctl,v,key)
            probe=shlex.split(argv[-1])[5].split('\nsignal.alarm(10)')[0]
            namespace={}; exec(probe,namespace)
            self.assertEqual(namespace['vision_process'](123,root),observed)
            source=root/'service.py'; source.write_bytes(b'print(1)\n'); source.chmod(0o444)
            with patch.dict(namespace,ancestry=lambda *args:None):
                self.assertEqual(namespace['reference']({'path':str(source),'sha256':c.sha(source.read_bytes()),'uid':os.getuid()}),source.read_bytes())
    def test_ssh_failure_original_exit_and_stdout_stderr_are_retained(self):
        ctl,_,_=self.fixture(); child=Mock(pid=777,returncode=255); child.communicate.return_value=(b'partial stdout',b'host-key failure')
        with patch.object(ctl,'vision_command',return_value=['/usr/bin/ssh','exact-reviewed-command']),\
             patch.object(c.subprocess,'Popen',return_value=child),patch.object(c,'spawned_birth',return_value={'pid':777}),\
             patch.object(c,'owner_absent',return_value=True),patch.object(c,'group_absent',return_value=True),self.assertRaises(c.Denied):
            ctl.remote_vision(ctl.b['proofs']['visionNormal'])
        receipt=ctl.readonly_receipts[0]
        self.assertEqual(receipt['actualExitCode'],255); self.assertTrue(receipt['integerWait'])
        self.assertEqual(receipt['stderrSha256'],c.sha(b'host-key failure')); self.assertTrue(receipt['processGroupAbsent'])
        self.assertEqual(c.base64.b64decode(receipt['stdoutBase64']),b'partial stdout')
    def test_ssh_timeout_has_actual_wait_and_original_partial_bytes(self):
        ctl,_,_=self.fixture(); child=Mock(pid=777,returncode=-9)
        child.communicate.side_effect=[subprocess.TimeoutExpired('ssh',15), (b'partial',b'timeout stderr')]
        with patch.object(ctl,'vision_command',return_value=['/usr/bin/ssh','exact-reviewed-command']),\
             patch.object(c.subprocess,'Popen',return_value=child),patch.object(c,'spawned_birth',return_value={'pid':777}),\
             patch.object(c,'owner_absent',return_value=False),patch.object(c,'group_absent',return_value=True),\
             patch.object(c.os,'killpg') as kill,self.assertRaises(c.Denied): ctl.remote_vision(ctl.b['proofs']['visionNormal'])
        kill.assert_called_once_with(777,c.signal.SIGKILL)
        receipt=ctl.readonly_receipts[0]; self.assertEqual(receipt['actualExitCode'],-9); self.assertTrue(receipt['timedOut'])
        self.assertEqual(receipt['stdoutSha256'],c.sha(b'partial'))

class RestartPreservationControls(unittest.TestCase):
    def fixture(self):
        b={'operation':c.RESTART,'expiresUtc':'2099-01-01T00:00:00Z','sourceCommit':'b'*40,
           'counts':{'rollback':[]},'proofs':{'visionNormal':{'enabled':False},'ordinaryKey':{'path':'/private/ordinary-key'}},'owner':{'pid':10},
           'data':{'path':'/private/data'},'unit':{'path':'/private/unit','sha256':c.sha(b'old'),
                                             'candidate':{'sha256':c.sha(b'new')}},'configFiles':[]}
        prepared={'original':b'old','candidate':b'new','options':{},'owner':b['owner'],'idle':{},'vision':{'enabled':False}}
        return c.Control(b),prepared
    def execute_fixture(self,ctl,prepared,loader_error=None,owner_error=None,db_error=None,vision_error=None):
        calls=[]
        def mark(name,result=None,error=None):
            def f(*args,**kwargs):
                calls.append(name)
                if error: raise error
                return result
            return f
        records=[]
        with patch.object(ctl,'preflight',return_value=prepared),patch.object(ctl,'claim',side_effect=mark('claim')),\
             patch.object(ctl,'record',side_effect=lambda name,*a,**k:records.append((name,a,k))),\
             patch.object(ctl,'backup',side_effect=mark('backup')),patch.object(ctl,'verify_staged',side_effect=mark('verify')),\
             patch.object(ctl,'ordinary_loader',side_effect=mark('loader',error=loader_error)),\
             patch.object(ctl,'state',return_value={'InvocationID':'original'}),\
             patch.object(c,'exact_owner',side_effect=mark('owner',error=owner_error)),\
             patch.object(c,'database_state',side_effect=mark('db',error=db_error)),\
             patch.object(ctl,'vision',side_effect=mark('vision',error=vision_error) if vision_error else ctl.vision),\
             patch.object(ctl,'replace_unit',side_effect=mark('replace')),patch.object(ctl,'manager',side_effect=mark('manager')),\
             patch.object(ctl,'fresh_owner',return_value={'pid':20}),patch.object(ctl,'health',side_effect=mark('health')),\
             patch.object(c,'protected',return_value=b'new'):
            try: return ctl.execute(),calls,records
            except c.Denied as e: return e,calls,records
    def test_ordinary_restart_disabled_vision_keeps_loader_backup_owner_db_order(self):
        ctl,prepared=self.fixture(); result,calls,records=self.execute_fixture(ctl,prepared)
        self.assertEqual(result['status'],'NORMAL_RESTARTED_HEALTH_ONLY')
        self.assertEqual(calls[:7],['claim','backup','verify','loader','owner','db','replace'])
        self.assertIn('RESULT.json',[v[0] for v in records])
    def test_required_loader_owner_db_and_enabled_vision_failure_prevent_unit_mutation(self):
        for guard in ('loader','owner','db','vision'):
            ctl,prepared=self.fixture()
            result,calls,records=self.execute_fixture(ctl,prepared,**{guard+'_error':c.Denied(guard+' failure')})
            self.assertIsInstance(result,c.Denied); self.assertNotIn('replace',calls)
            self.assertEqual(calls[0],'claim'); self.assertIn('failure.json',[v[0] for v in records])
            failure=next(v for v in records if v[0]=='failure.json')[1][0]
            self.assertFalse(failure['unitMutationAttempted'])
    def test_preflight_stage_without_vision_preserves_real_source_hmac_native_pins_and_key_inode_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory).resolve(); root=base/'release'; data=base/'data'; unit=base/'unit'; keypath=base/'key'
            key=b'k'*32; keypath.write_bytes(key); unit.write_bytes(b'old')
            q={'binaryVersion':'0.158.0','upstream':'064c6b8c737f5b41d171fdda80bd9ef10ad06eb3'}
            for name in ('launch','settlement','protocolAck','binary'): q.update({name+'Path':str(base/name),name+'Sha256':'c'*64})
            def approval():
                body={'qualification':q}; return c.canonical({'body':body,'seal':hmac.new(key,c.canonical(body),hashlib.sha256).hexdigest()})
            content={'ai-harness/source-commit.txt':b'b'*40+b'\n'}
            raw=Controls().archive([(name,value,tarfile.REGTYPE) for name,value in content.items()])
            ref=lambda name:{'path':str(base/name),'sha256':'a'*64,'uid':0}
            keyid=c.identity(keypath)
            owner={'pid':10,'selectedEnvironment':{'AI_HARNESS_DATA_DIR':str(data)}}
            b={'operation':c.STAGE,'expiresUtc':'2099-01-01T00:00:00Z','hostBootId':'local-boot','journal':str(base/'journal'),
               'sourceCommit':'b'*40,'release':{'path':str(root),'files':{k:c.sha(v) for k,v in content.items()},'executableFiles':[]},
               'archives':[{'archive':ref('archive'),'files':{k:c.sha(v) for k,v in content.items()}}],'dependencies':[],
               'configFiles':[],'proofs':{'ordinaryApproval':ref('approval'),'ordinaryKey':{'path':str(keypath),'identity':keyid}},
               'unit':{'path':str(unit),'sha256':c.sha(b'old'),'candidate':ref('candidate')},'owner':owner,'data':{'path':str(data)}}
            original_read=Path.read_text
            def boot(path,*a,**kw):
                return 'local-boot' if str(path)=='/proc/sys/kernel/random/boot_id' else original_read(path,*a,**kw)
            def read(ref,*a):
                if ref['path']==str(base/'archive'): return raw
                if ref['path']==str(base/'approval'): return approval()
                return b'evidence'
            def protect(path,*a): return key if str(path)==str(keypath) else b'old'
            ctl=c.Control(b)
            with patch.object(Path,'read_text',boot),patch.object(c,'ancestry'),patch.object(c,'reference',side_effect=read),\
                 patch.object(c,'protected',side_effect=protect),patch.object(c,'unit_candidate',return_value={}),\
                 patch.object(ctl,'state',return_value={'ActiveState':'active','SubState':'running','NRestarts':'0','MainPID':'10','InvocationID':'id'}),\
                 patch.object(c,'exact_owner',return_value=owner),patch.object(c,'database_state',return_value={'activeRuns':0}),\
                 patch.object(ctl,'remote_vision',side_effect=AssertionError('optional vision contacted')):
                self.assertFalse(ctl.preflight()['vision']['required'])
                q['binaryVersion']='0.159.0'
                with self.assertRaisesRegex(c.Denied,'native pins'): ctl.preflight()
                q['binaryVersion']='0.158.0'; b['proofs']['ordinaryKey']['identity']=dict(keyid,ino=0)
                with self.assertRaisesRegex(c.Denied,'key identity'): ctl.preflight()
                b['proofs']['ordinaryKey']['identity']=keyid; b['sourceCommit']='d'*40
                with self.assertRaisesRegex(c.Denied,'source commit'): ctl.preflight()
    def test_real_database_denies_active_runs_retained_owner_or_history_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve(); root.chmod(0o700); db=root/'harness.sqlite'
            con=sqlite3.connect(db)
            con.executescript("CREATE TABLE sessions(id TEXT,status TEXT); CREATE TABLE messages(session_id TEXT,text TEXT);"
              "CREATE TABLE runs(session_id TEXT,status TEXT); CREATE TABLE events(session_id TEXT,text TEXT);"
              "CREATE TABLE h021_session_engines(session_id TEXT,ownership TEXT,active_turn_id TEXT);"
              "CREATE TABLE h003_image_jobs(id INTEGER,data TEXT); INSERT INTO sessions VALUES('original','idle');"
              "INSERT INTO messages VALUES('original','history'); INSERT INTO h021_session_engines VALUES('original','idle',NULL);")
            con.commit(); projection={}
            for table,column in [('sessions','id'),('messages','session_id'),('runs','session_id'),('events','session_id'),('h021_session_engines','session_id')]:
                cursor=con.execute('SELECT * FROM '+table+' WHERE '+column+'=? ORDER BY rowid',('original',))
                projection[table]={'columns':[v[0] for v in cursor.description],'rows':cursor.fetchall()}
            dbid={k:v for k,v in c.identity(db).items() if k in ('dev','ino','uid','gid','mode','nlink')}; dbid['uid']=1000
            spec={'path':str(root),'databaseIdentity':dbid,'retainedOwners':[],'preservedSessionId':'original','preservedSessionSha256':c.sha(c.canonical(projection))}
            actual_lstat=Path.lstat; actual_identity=c.identity
            def service_lstat(path,*args,**kwargs):
                st=actual_lstat(path,*args,**kwargs)
                if path==root:
                    values=list(st); values[4]=1000; return os.stat_result(values)
                return st
            def service_identity(path):
                result=actual_identity(path)
                if path==db: result['uid']=1000
                return result
            with patch.object(c,'ancestry'),patch.object(Path,'lstat',service_lstat),patch.object(c,'identity',side_effect=service_identity):
                self.assertEqual(c.database_state(spec)['activeRuns'],0)
                con.execute("INSERT INTO runs VALUES('other','running')"); con.commit()
                with self.assertRaisesRegex(c.Denied,'non-idle'): c.database_state(spec)
                con.execute('DELETE FROM runs'); con.execute("UPDATE h021_session_engines SET ownership='uncertain'"); con.commit()
                with self.assertRaisesRegex(c.Denied,'retained owner'): c.database_state(spec)
                con.execute("UPDATE h021_session_engines SET ownership='idle'"); con.execute("UPDATE messages SET text='changed'"); con.commit()
                with self.assertRaisesRegex(c.Denied,'original user session'): c.database_state(spec)
            con.close()
    def test_normal_exact_owner_still_checks_full_app_tuple_and_invocation(self):
        observed={'pid':10,'startTicks':'123','bootId':'boot','uid':1000,'gid':1000,'pgid':10,
                  'cgroup':'0::/app','exe':'/node','cmdlineSha256':'a'*64,'selectedEnvironment':{'AI_HARNESS_DATA_DIR':'/data'}}
        expected=dict(observed,invocationId='original')
        with patch.object(c,'process',return_value=observed):
            self.assertEqual(c.exact_owner(expected,'original'),observed)
            for field,value in [('startTicks','wrong'),('bootId','wrong'),('cmdlineSha256','b'*64),('invocationId','wrong')]:
                bad=dict(expected,**{field:value})
                with self.subTest(field=field),self.assertRaises(c.Denied): c.exact_owner(bad,'original')
    def test_unit_compare_and_swap_denial_occurs_before_write(self):
        ctl,_=self.fixture()
        with patch.object(c,'protected',return_value=b'changed'),patch.object(c.os,'open') as write,\
             self.assertRaises(c.Denied): ctl.replace_unit(b'new',c.sha(b'old'))
        write.assert_not_called()
    def test_rollback_requires_explicit_counts_and_current_candidate_owner(self):
        ctl,prepared=self.fixture()
        with patch.object(c,'protected') as read,self.assertRaises(c.Denied): ctl.rollback(prepared,None)
        read.assert_not_called(); ctl.b['counts']['rollback']=c.ROLLBACK
        with patch.object(c,'protected',return_value=b'other'),patch.object(ctl,'replace_unit') as write,\
             self.assertRaises(c.Denied): ctl.rollback(prepared,None)
        write.assert_not_called()

if __name__=='__main__': unittest.main()
