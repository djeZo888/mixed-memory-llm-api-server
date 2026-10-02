#!/usr/bin/env python3
"""Synthetic current-owner/CAS/protected-FD checks, no Linux/model imports."""
import copy
import datetime
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import contextlib
import fcntl
import hashlib

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common.lifecycle_lease import acquire_lease, LifecycleLease, LeaseError
from install.storage import Storage
from install.storage_io import AnchoredRoot, MountedStorageGuard, GuardedFile
from lifecycle.storage_binding import RegisteredStorageBinding, _BoundMountedGuard

spec=importlib.util.spec_from_file_location('image_owner_reconcile',Path(__file__).with_name('image_owner_reconcile.py'))
m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m)


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.maps=({'native'+str(i):'a'*64 for i in range(4)},
                   {'release'+str(i):'b'*64 for i in range(33)})
        checkpoint={'status':'COMPLETE_VERIFIED','revision':m.REVISION,'file_count':26,'total_bytes':33131614782,
                    'preserve':['saved weights; no rehash']}
        self.values={
            'checkpoint':checkpoint,
            'config':{'schema_version':1,'owner':m.OWNER,'gpu_uuid':m.READING_GPU,'image_id':m.PLATFORM,
                'network_id':m.NETWORK_ID,
                'source_commit':m.SOURCE,'checkpoint_revision':m.REVISION,'checkpoint_path':m.MODEL,
                'checkpoint_receipt_sha256':m.sha(json.dumps(checkpoint).encode()),
                'source_sha256':self.maps[0],'release_source_sha256':self.maps[1],
                'protected_credential':'SYNTHETIC-SECRET-NOT-EXPORTED','unknown':{'keep':True}},
            'state':{'schema_version':1,'owner':m.OWNER,'run_id':m.INVOCATION,
                'container':{'id':m.CID,'image_id':m.PLATFORM},'phase':'loading','warm':False,
                'native_generation':{'pid':13527,'Pid':13527,'start_ticks':2853,
                    'StartedAt':'2026-10-01T02:07:48.872235338Z'},
                'native_actions':{'create':'received','start':'received'},'prior_receipts':{'keep':True}},
            'operation':{'boot':m.OLD_BOOT,'status':'active','gpu_uuid':m.READING_GPU,'pid':10956,
                'token':'c'*32,'recovery':'d'*32,'invocation_id':m.INVOCATION,'action':'start'},
            'recovery':{'boot':m.OLD_BOOT,'status':'active','gpu_uuid':m.READING_GPU,'pid':10955,
                'token':'d'*32,'process':{'pid':10955,'start_ticks':2800},'phase':'restart','child_start':m.INVOCATION},
            'api':{'schema_version':1,'model_id':'Qwen/Qwen-Image-2.1','runtime_revision':m.SOURCE,
                'model_revision':m.REVISION,'runtime_image_digest':m.PARENT,
                'profiles':[{'operation':'edit','evidence_sha256':'e'*64}],
                'credentials':{'key':'SYNTHETIC-SECRET-NOT-EXPORTED'}}}
        self.evidence={'origin':'CURRENT_ROOT_PROTECTED_READ','bootBefore':m.BOOT,'bootAfter':m.BOOT,
            'container':{'id':m.CID,'owner':m.OWNER,'invocation':m.INVOCATION,'image':m.PLATFORM,
                'configImage':m.PLATFORM,'gpu':m.READING_GPU,'status':'exited','running':False,'pid':0,'exitCode':255},
            'apiOwner':{'boot':m.BOOT,'unit':'llm-image-api.service','cgroup':'0::/system.slice/llm-image-api.service',
                'exe':'/usr/bin/python3.12','stable':True,'pid':11783,'pgid':11783,'startTicks':2769,
                'invocation':'add9855d26bf4eab96b7574c7f0c8af8'},
            'peerBeforeFileSha256':{'peer':'a'*64},'peerAfterFileSha256':{'peer':'a'*64},
            'hardware':{'gpuUuid':m.EXTERNAL_GPU,'boot':m.BOOT,'stableReadingGpu':m.READING_GPU},
            'apiHealthOrReadyInvoked':False}

    def raw(self): return {k:json.dumps(v).encode() for k,v in self.values.items()}
    def proposal(self,evidence=None):
        raw=self.raw(); expected={k:m.sha(v) for k,v in raw.items()}
        return m.propose(raw,evidence or self.evidence,self.maps,expected=expected)

    def test_full_raw_preservation_narrow_delta_and_no_secret_export(self):
        before=copy.deepcopy(self.values); p=self.proposal()
        runtime=json.loads(p.runtime_successor); api=json.loads(p.api_successor)
        expected=copy.deepcopy(before['config']); expected['gpu_uuid']=m.EXTERNAL_GPU
        self.assertEqual(runtime,expected)
        expected=copy.deepcopy(before['api']); expected['runtime_image_digest']=m.PLATFORM
        self.assertEqual(api,expected); self.assertEqual(before,self.values)
        self.assertNotIn('SYNTHETIC-SECRET',json.dumps(p.public()))
        self.assertNotIn('SYNTHETIC-SECRET',repr(p))
        self.assertFalse(p.public()['runtimeWriteAuthority'])
        self.assertIn('state',p.public()['unchanged'])

    def test_real_current_hashes_are_not_synthetic_authority(self):
        with self.assertRaises(m.Refused): m.propose(self.raw(),self.evidence,self.maps)
        raw=self.raw(); expected={k:m.sha(v) for k,v in raw.items()}; raw['state']+=b' '
        with self.assertRaises(m.Refused): m.propose(raw,self.evidence,self.maps,expected=expected)

    def test_current_boot_and_exact_stopped_owner(self):
        for key,value in (('id','f'*64),('owner','other'),('invocation','f'*32),('gpu',m.EXTERNAL_GPU),
                          ('image',m.CONFIG),('configImage',m.PARENT),('running',True),('pid',False),('exitCode',0)):
            e=copy.deepcopy(self.evidence); e['container'][key]=value
            with self.assertRaises(m.Refused): self.proposal(e)
        e=copy.deepcopy(self.evidence); e['bootAfter']=m.OLD_BOOT
        with self.assertRaises(m.Refused): self.proposal(e)

    def test_current_api_owner_peer_invariance_and_no_admission(self):
        for mutate in (
            lambda e:e['apiOwner'].update(boot=m.OLD_BOOT),
            lambda e:e['apiOwner'].update(pid=True),
            lambda e:e['apiOwner'].update(pid=11784),
            lambda e:e['apiOwner'].update(stable=False),
            lambda e:e.update(peerAfterFileSha256={'peer':'b'*64}),
            lambda e:e.update(apiHealthOrReadyInvoked=True),
            lambda e:e['hardware'].update(gpuUuid=m.READING_GPU)):
            e=copy.deepcopy(self.evidence); mutate(e)
            with self.assertRaises(m.Refused): self.proposal(e)

    def test_prior_boot_pid_never_current_authority(self):
        for mutate in (
            lambda v:v['operation'].update(boot=m.BOOT),
            lambda v:v['recovery'].update(token='e'*32),
            lambda v:v['recovery'].update(process={'pid':10955,'start_ticks':True}),
            lambda v:v['state']['native_generation'].update(start_ticks=2854),
            lambda v:v['state'].update(owner='other')):
            original=copy.deepcopy(self.values); mutate(self.values)
            with self.assertRaises(m.Refused): self.proposal()
            self.values=original
        self.assertEqual(self.proposal().public()['priorPid']['authority'],
            'NONE; never signal or adopt on current boot')

    def test_strict_schema_and_source_pins(self):
        for target,key,value in (('config','schema_version',True),('config','image_id',m.PARENT),
                ('config','source_commit','other'),('api','runtime_image_digest',m.PLATFORM),
                ('checkpoint','file_count',True),('checkpoint','status','INCOMPLETE')):
            original=copy.deepcopy(self.values); self.values[target][key]=value
            with self.assertRaises(m.Refused): self.proposal()
            self.values=original
        for raw in (b'{"a":1,"a":2}',b'{"x":NaN}',b'x'*262145):
            with self.assertRaises(m.Refused): m.strict(raw)

    def test_protected_fd_rejects_symlink_hardlink_mode_and_byte_change(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'original.json'; path.write_bytes(b'{}'); path.chmod(0o600)
            options={'trusted_uid':os.getuid(),'fixture_root':root}
            with m.ProtectedFile(str(path),**options) as held:
                self.assertEqual(held.raw,b'{}'); path.write_bytes(b'{"x":1}')
                with self.assertRaises(m.Refused): held.check()
            path.chmod(0o666)
            with self.assertRaises(m.Refused): m.ProtectedFile(str(path),**options)
            path.chmod(0o600); link=Path(root)/'link'; link.symlink_to(path)
            with self.assertRaises((m.Refused,OSError)): m.ProtectedFile(str(link),**options)
            os.link(path,Path(root)/'hard')
            with self.assertRaises(m.Refused): m.ProtectedFile(str(path),**options)

    def test_ancestor_swap_refused_on_held_descriptor(self):
        with tempfile.TemporaryDirectory() as root:
            sub=Path(root)/'sub'; sub.mkdir(mode=0o700); path=sub/'original'; path.write_bytes(b'{}'); path.chmod(0o600)
            with m.ProtectedFile(str(path),trusted_uid=os.getuid(),fixture_root=root) as held:
                sub.rename(Path(root)/'old'); sub.mkdir(mode=0o700)
                with self.assertRaises(m.Refused): held.check()

    def test_new_exact_archive_go_never_grants_runtime_cas(self):
        now=datetime.datetime(2026,10,2,tzinfo=datetime.timezone.utc)
        go={'status':'GO','issuedBy':'root','phase':'I-image03','bootId':m.BOOT,'sourceSha256':'a'*64,
            'expectedFileSha256':m.EXPECTED,'archiveDestination':m.ARCHIVE,'maximumInvocations':1,
            'runtimeCASPermitted':False,'actions':['read_current_six_raw','archive_exact_originals_only'],
            'notBeforeUtc':now.isoformat(),'expiresUtc':(now+datetime.timedelta(seconds=90)).isoformat()}
        m.validate_archive_go(go,'a'*64,now)
        for key,value in (('maximumInvocations',True),('runtimeCASPermitted',True),('bootId',m.OLD_BOOT),
                          ('sourceSha256','b'*64),('archiveDestination','/tmp/archive')):
            bad=copy.deepcopy(go); bad[key]=value
            with self.assertRaises(m.Refused): m.validate_archive_go(bad,'a'*64,now)
        with self.assertRaises(m.Refused):
            m.validate_archive_go(go,'a'*64,now+datetime.timedelta(seconds=91))

    def test_cli_is_request_only_and_production_entry_requires_registered_capability(self):
        self.assertEqual(m.request()['runtimeWriter'],'IMPLEMENTED_GUARDED_ARCHIVE_CAS_ROLLBACK')
        for value in (None, True, {}, object()):
            with self.assertRaises(m.Refused): m.reconcile_current(value)
        with self.assertRaises(m.RequirementsMissing): m.ProductionSession()
        forged=object.__new__(m.ProductionSession)
        with self.assertRaises(m.Refused): forged.check()
        with self.assertRaises(m.RequirementsMissing): m.CachedOCI()
        forged=object.__new__(m.CachedOCI)
        with self.assertRaises(m.Refused): forged.check()

    def test_actual_reset_phase_can_precede_the_old_operation(self):
        self.values['recovery'].update(phase='reset',child_start=None,prior_invocation=m.INVOCATION)
        self.values['operation']['recovery']=None
        self.proposal()
        self.values['recovery']['child_start']=m.INVOCATION
        with self.assertRaises(m.Refused): self.proposal()

    def test_scalar_change_preserves_all_other_raw_bytes(self):
        raw=(' { "gpu_uuid" : '+json.dumps(m.READING_GPU)+', "secret" : "s\\u0065cret", '
             '"history" : { "gpu_uuid" : "nested-unchanged" } }\n').encode()
        after=m.replace_scalar(raw,'gpu_uuid',m.READING_GPU,m.EXTERNAL_GPU)
        self.assertEqual(after,raw.replace(m.READING_GPU.encode(),m.EXTERNAL_GPU.encode()))
        self.assertIn(b's\\u0065cret',after)
        with self.assertRaises(m.Refused): m.replace_scalar(raw,'gpu_uuid',m.EXTERNAL_GPU,m.READING_GPU)

class ActualStorageFixture:
    """Canonical guard classes; only mount/block discovery is synthetic.

    Fixtures are below protected private output because the production I1b
    ancestry checker deliberately refuses world-writable /private/tmp. Test
    commands still use this phase's recorded protected TMPDIR environment.
    """
    def __init__(self):
        output=Path(__file__).resolve().parents[3]/'output'
        self.tmp=tempfile.TemporaryDirectory(prefix='writer-fs-',dir=output)
        self.path=Path(self.tmp.name)
        self.data=self.path/'data';self.data.mkdir(mode=0o700)
        self.storage=Storage({'data_dir':str(self.data),'model_dir':str(self.data),
            'data_uuid':'synthetic-uuid','model_uuid':'synthetic-uuid'},None,system_root=self.path)
        self.storage._local=lambda path:Path(path) if Path(path)==self.path or self.path in Path(path).parents else self.path/str(path).lstrip('/')
        roots=self.storage._roots()
        for path in roots.values(): Path(path).mkdir(parents=True,exist_ok=True)
        info=self.data.stat();device=f'{os.major(info.st_dev)}:{os.minor(info.st_dev)}'
        row={'path':str(self.data),'mount':str(self.data),'uuid':'synthetic-uuid','fstype':'ext4',
            'device':device,'source':'/dev/synthetic','parents':['/dev/synthetic']}
        self.snapshot={'schema_version':1,'storage_mode':'existing','data':dict(row),'models':dict(row),'roots':roots}
        registration=self.path/'etc/local-ai-server/storage.json';registration.parent.mkdir(parents=True)
        registration.write_text(json.dumps(self.snapshot));registration.chmod(0o600)
        # Actual verify/registry/root_payload_guard/MountedStorageGuard run.
        self.storage._snapshot=lambda:copy.deepcopy(self.snapshot)
        self.storage._capacity=lambda _: {'root_available_bytes':100*1024**3,
            'data_available_bytes':100*1024**3,'model_available_bytes':100*1024**3}
        self.mountinfo='1 0 0:1 / / rw - ext4 /dev/synthetic-root rw\n'+f'2 1 {device} / {self.data} rw - ext4 /dev/synthetic rw\n'
        self.binding=RegisteredStorageBinding(self.storage,self.snapshot)
        self.mounted=MountedStorageGuard(self.storage,mountinfo_reader=lambda:self.mountinfo)
        self.bound=_BoundMountedGuard(self.mounted,self.binding._identity)
        self.runtime=self.data/'runtime';self.runtime.mkdir(mode=0o700)
        self.archive_path=self.data/'archive';self.archive_path.mkdir(mode=0o700)
        self.anchor=AnchoredRoot(str(self.runtime),self.bound,uid=os.getuid())
        self.archive=AnchoredRoot(str(self.archive_path),self.bound,uid=os.getuid())
    def close(self):
        self.anchor.close();self.archive.close();self.mounted.close();self.tmp.cleanup()


class RealWriterTests(unittest.TestCase):
    def setUp(self):
        self.fixture=ActualStorageFixture();self.addCleanup(self.fixture.close)
        base=ReconcileTests();base.setUp()
        self.values=copy.deepcopy(base.values)
        self.values['recovery'].update(phase='reset',child_start=None,prior_invocation=m.INVOCATION)
        self.values['config']['checkpoint_receipt_sha256']=m.sha(m.encode(self.values['checkpoint']))
        digest=m.sha(json.dumps(self.values['config'],sort_keys=True,separators=(',',':')).encode())
        self.values['operation'].update(config_sha256=digest,prior_state_sha256='f'*64,recovery=None)
        self.values['recovery']['config_sha256']=digest
        self.files={}
        for key in m.PATHS:
            leaf=self.fixture.runtime/(key+'.json');leaf.write_bytes(m.encode(self.values[key]));leaf.chmod(0o600)
            held=m.ProtectedFile(str(leaf),trusted_uid=os.getuid(),fixture_root=self.fixture.path)
            self.files[key]=held;self.addCleanup(held.close)
        self.original={k:v.raw for k,v in self.files.items()}
        self.successors={k:m.encode(dict(self.values[k],fixture_successor=True))
            for k in ('config','state','operation','recovery','api')}
        self.successors['config']=m.replace_scalar(self.original['config'],'gpu_uuid',m.READING_GPU,m.EXTERNAL_GPU)
        self.successors['api']=m.replace_scalar(self.original['api'],'runtime_image_digest',m.PARENT,m.PLATFORM)
        self.guard_calls=0
    def guard(self):
        self.guard_calls+=1;self.fixture.bound();self.fixture.anchor.check();self.fixture.archive.check()
    def transaction(self):
        return m.RawTransaction(self.files,self.fixture.archive,self.guard,
            anchors={k:self.fixture.anchor for k in ('config','state','operation','recovery')})
    def actual(self): return {k:Path(v.path).read_bytes() for k,v in self.files.items()}
    def verify(self):
        actual=self.actual()
        self.assertEqual(json.loads(actual['config'])['gpu_uuid'],m.EXTERNAL_GPU)
        self.assertEqual(json.loads(actual['api'])['runtime_image_digest'],m.PLATFORM)
        self.assertEqual(json.loads(actual['recovery'])['status'],'active')
        for key in m.PATHS:
            self.assertEqual((self.fixture.archive_path/(key+'.original.json')).read_bytes(),self.original[key])

    def test_real_archive_cas_registration_and_credentials_history_bytes(self):
        tx=self.transaction();result=tx.apply(self.successors,self.verify)
        self.assertEqual(result['journal'],['ALL_SIX_DURABLE_BEFORE_MUTATION','COMMITTED_NORMAL_REGISTRATION'])
        for key in m.PATHS:
            self.assertEqual(self.actual()[key],self.successors.get(key,self.original[key]))
            archive=self.fixture.archive_path/(key+'.original.json')
            self.assertEqual(archive.read_bytes(),self.original[key]);self.assertEqual(archive.stat().st_mode&0o777,0o400)
        self.assertEqual(self.actual()['checkpoint'],self.original['checkpoint'])
        self.assertIn(b'SYNTHETIC-SECRET',self.actual()['config'])
        self.assertNotIn('SYNTHETIC-SECRET',json.dumps(result));self.assertGreater(self.guard_calls,20)

    def test_short_write_archive_and_stage_uses_actual_filesystem(self):
        actual=os.write
        with patch.object(os,'write',side_effect=lambda fd,data:actual(fd,data[:7])):
            self.transaction().apply(self.successors,self.verify)
        self.assertEqual(self.actual()['config'],self.successors['config'])

    def test_archive_failure_never_mutates_any_original(self):
        actual=GuardedFile.write
        def fail(stream,data):
            if stream.name=='recovery.original.json': raise OSError('synthetic archive failure')
            return actual(stream,data)
        with patch.object(GuardedFile,'write',new=fail):
            with self.assertRaises(OSError): self.transaction().apply(self.successors,self.verify)
        self.assertEqual(self.actual(),self.original)

    def test_normal_registration_failure_rolls_back_every_byte(self):
        tx=self.transaction()
        with self.assertRaisesRegex(RuntimeError,'registration-failure'):
            tx.apply(self.successors,lambda:(_ for _ in ()).throw(RuntimeError('registration-failure')))
        self.assertEqual(self.actual(),self.original)
        self.assertIn('ROLLED_BACK_EXACT_ORIGINAL_BYTES',tx.journal)

    def test_post_exchange_exception_actual_promotion_is_rolled_back(self):
        tx=self.transaction();actual=m.exchange;calls=[]
        def after(directory,source,destination):
            actual(directory,source,destination);calls.append(destination)
            if len(calls)==3: raise OSError('synthetic after exchange')
        with patch.object(m,'exchange',side_effect=after):
            with self.assertRaises(OSError): tx.apply(self.successors,self.verify)
        self.assertEqual(self.actual(),self.original)

    def test_foreign_cas_race_is_restored_and_never_overwritten(self):
        tx=self.transaction();actual=m.exchange;raced=[];foreign=b'{"foreign":"preserve"}\n'
        def race(directory,source,destination):
            if not raced:
                raced.append(destination)
                path=self.fixture.runtime/destination
                replacement=self.fixture.runtime/'foreign';replacement.write_bytes(foreign);replacement.chmod(0o600)
                os.replace(replacement,path)
            return actual(directory,source,destination)
        with patch.object(m,'exchange',side_effect=race):
            with self.assertRaises(m.RollbackFailed): tx.apply(self.successors,self.verify)
        self.assertEqual((self.fixture.runtime/raced[0]).read_bytes(),foreign)
        for key in m.PATHS:
            if Path(self.files[key].path).name!=raced[0]:self.assertEqual(self.actual()[key],self.original[key])

    def test_rollback_failure_is_explicit_and_preserves_raw_archive(self):
        tx=self.transaction();actual=m.exchange
        def refuse_rollback(directory,source,destination):
            if 'rollback' in source: raise OSError('synthetic rollback failure')
            return actual(directory,source,destination)
        with patch.object(m,'exchange',side_effect=refuse_rollback):
            with self.assertRaises(m.RollbackFailed):
                tx.apply(self.successors,lambda:(_ for _ in ()).throw(RuntimeError('registration-failure')))
        self.assertIn('ROLLBACK_FAILED_ADMISSION_MUST_REMAIN_CLOSED',tx.journal)
        for key in m.PATHS:self.assertEqual((self.fixture.archive_path/(key+'.original.json')).read_bytes(),self.original[key])
        self.assertEqual(json.loads(self.actual()['recovery'])['status'],'active')

    def test_immutable_archive_corruption_blocks_all_original_mutations(self):
        tx=self.transaction();actual=tx.stage;done=[]
        def corrupt(key,raw,tag):
            result=actual(key,raw,tag)
            if not done:
                done.append(True);path=self.fixture.archive_path/'checkpoint.original.json';path.chmod(0o600);path.write_bytes(b'{}')
            return result
        with patch.object(tx,'stage',side_effect=corrupt):
            with self.assertRaises((m.Refused,m.RollbackFailed)):tx.apply(self.successors,self.verify)
        self.assertEqual(self.actual(),self.original)

    def test_full_byte_change_or_symlink_rejects_before_archive(self):
        self.fixture.runtime.joinpath('api.json').write_bytes(b'{"changed":true}')
        with self.assertRaises(m.Refused):self.transaction().apply(self.successors,self.verify)
        self.assertEqual(list(self.fixture.archive_path.iterdir()),[])

    def test_same_boot_unknown_owners_and_gpu_presence_are_refusals(self):
        # Real absence reader distinguishes ENOENT from unreadable/present.
        with self.assertRaises(m.RequirementsMissing):m._absent(self.files['state'].path,'owner_present')
        with patch.object(m.os,'stat',side_effect=PermissionError):
            with self.assertRaises(m.RequirementsMissing):m._absent('/synthetic','unknown_owner')
        with patch.object(m.os,'stat',side_effect=FileNotFoundError):m._absent('/synthetic','unknown_owner')
        with self.assertRaises(m.Refused):m.reconcile_current({'boot':m.BOOT,'ready':True,'gpuAbsent':True})

    def test_canonical_registered_guard_positive_and_spoof_refusal(self):
        f=self.fixture
        with acquire_lease(system_root=f.path,trusted_uid=os.getuid(),blocking=False) as lease:
            with f.anchor.open('recovery.lock',os.O_RDWR|os.O_CREAT) as model:
                with f.anchor.open('operation.lock',os.O_RDWR|os.O_CREAT) as operation:
                    fcntl.flock(model.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                    fcntl.flock(operation.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                    m._canonical_guards(lease,f.anchor,f.bound,f.binding,model,operation)
                    Storage.root_payload_guard(f.storage,f.binding.registry)
                    Fake=type('LifecycleLease',(),{'__module__':'common.lifecycle_lease','validate':lambda _:None})
                    with self.assertRaises(m.Refused):m._canonical_guards(Fake(),f.anchor,f.bound,f.binding,model,operation)
                    forged=object.__new__(LifecycleLease)
                    with self.assertRaises(LeaseError):m._canonical_guards(forged,f.anchor,f.bound,f.binding,model,operation)
                    with self.assertRaises(m.Refused):m._canonical_guards(lease,f.anchor,None,f.binding,model,operation)
                    with self.assertRaises(m.Refused):m._canonical_guards(lease,f.anchor,f.bound,f.binding,None,operation)
                    f.mountinfo=f.mountinfo.splitlines()[0]+'\n'
                    with self.assertRaises(Exception):m._canonical_guards(lease,f.anchor,f.bound,f.binding,model,operation)
        with self.assertRaises(LeaseError):lease.validate()

    def test_exact_go_rejects_old_phase_boot_expiry_bool_and_missing_inputs(self):
        now=datetime.datetime.now(datetime.timezone.utc)
        go={'status':'GO','issuedBy':'root','phase':'I-image04','bootId':m.BOOT,'sourceSha256':'a'*64,
            'expectedFileSha256':m.EXPECTED,'archiveDestination':m.ARCHIVE,'maximumInvocations':1,
            'actions':m.request()['actions'],'ownerSourceSha256':m.OWNER_SOURCE_SHA,
            'notBeforeUtc':now.isoformat(),'expiresUtc':(now+datetime.timedelta(seconds=120)).isoformat(),
            'dockerBinarySha256':'b'*64,'daemonId':'synthetic-daemon','apiStoppedProofPath':'/synthetic/proof',
            'apiStoppedProofSha256':'c'*64,'apiBeforeObservationPath':'/synthetic/before',
            'apiBeforeObservationWholeFileSha256':'e'*64,'peerFileSha256':{'/synthetic/peer':'d'*64}}
        m.validate_writer_go(go,'a'*64,now)
        for key,value in [('phase','I-image03'),('bootId',m.OLD_BOOT),('maximumInvocations',True),
            ('ownerSourceSha256','f'*64),('dockerBinarySha256',None),('peerFileSha256',{})]:
            wrong=copy.deepcopy(go);wrong[key]=value
            with self.assertRaises(m.Refused):m.validate_writer_go(wrong,'a'*64,now)
        with self.assertRaises(m.Refused):m.validate_writer_go(go,'a'*64,now+datetime.timedelta(seconds=121))

    def test_complete_actual_reset_raw_schema_and_current_owner_refusals(self):
        raw=self.original;expected={k:m.sha(v) for k,v in raw.items()}
        parsed=m.validate_current_raw(raw,self.values['config'],expected=expected)
        self.assertEqual(parsed[3]['phase'],'reset')
        for target,key,value in [('recovery','phase','restart'),('recovery','child_start',m.INVOCATION),
            ('recovery','boot',m.BOOT),('operation','boot',m.BOOT),('operation','pid',True),
            ('operation','config_sha256','e'*64),('state','schema_version',True),('recovery','process',None)]:
            wrong=copy.deepcopy(self.values);wrong[target][key]=value
            changed={k:m.encode(v) for k,v in wrong.items()}
            with self.assertRaises(m.Refused):m.validate_current_raw(changed,wrong['config'],
                expected={k:m.sha(v) for k,v in changed.items()})
        with self.assertRaises(m.Refused):m.validate_current_raw(raw,self.values['config'])

    def test_api_current_owner_reader_is_closed_without_exact_go(self):
        with self.assertRaises(m.Refused):m.current_api_owner_proof({})
        source=Path(m.__file__).read_text()
        self.assertNotIn('os.kill',source)
        self.assertNotIn("'systemctl','stop'",source)
        self.assertNotIn('reset_owned()',source)


    def test_oci_no_dictionary_or_descriptor_name_can_mint_qualification(self):
        with self.assertRaises(m.Refused):m.verify_image_registry_bytes(b'{}',b'{}')
        with self.assertRaises(m.Refused):m.verify_image_registry_bytes(b'x'*7832,b'{}')
        with self.assertRaises(m.Refused):m.read_cached_oci({}).__enter__()
        forged=object.__new__(m.CachedOCI)
        with self.assertRaises(m.Refused):forged.check()
        # Metadata checker uses image constants, never Qwen model pins.
        self.assertEqual(m.CONFIG,'sha256:3f6178faa74c4a9bcb95ed4304dbee57473efa8913a793e067014af4a98281ad')

    def test_actual_native_guards_refuse_running_inventory_gpu_and_unknown_absence(self):
        from image_runtime import service as owner
        runtime=object.__new__(owner.Runtime);runtime.config={'gpu_uuid':m.EXTERNAL_GPU}
        from types import SimpleNamespace
        with patch.object(owner,'run',return_value=SimpleNamespace(stdout=m.EXTERNAL_GPU+', 42\n')):
            with self.assertRaisesRegex(RuntimeError,'already_present'):runtime.require_ada_idle()
        with patch.object(owner,'run',return_value=SimpleNamespace(stdout='')):runtime.require_ada_idle()
        present=json.dumps({'ID':m.CID,'Names':'llm-image-backend'})+'\n'
        with patch.object(owner,'run',return_value=SimpleNamespace(stdout=present)):
            with self.assertRaisesRegex(RuntimeError,'absence_unproven'):runtime.prove_absent(m.CID)
        with patch.object(owner,'run',side_effect=RuntimeError('owned_command_failed')):
            with self.assertRaises(RuntimeError):runtime.prove_absent(m.CID)

    def test_actual_root_payload_guard_and_registry_drift_fail_closed(self):
        payload=self.fixture.path/'opt/forbidden.bin';payload.parent.mkdir()
        with payload.open('wb') as output:output.truncate(129*1024**2)
        with self.assertRaisesRegex(Exception,'large model/cache/archive payload'):
            Storage.root_payload_guard(self.fixture.storage,self.fixture.binding.registry)
        registry=self.fixture.path/'etc/local-ai-server/storage.json';registry.write_bytes(b'{}')
        with self.assertRaises(Exception):self.fixture.bound()

    def test_authenticated_public_metadata_relationship_uses_real_held_bytes_offline(self):
        # Synthetic public metadata has its own test-only hashes. No claim about
        # the unavailable real50a3/config3f61 bytes follows from this fixture.
        config=m.encode({'os':'linux','architecture':'amd64','config':{'Labels':{
            'org.opencontainers.image.revision':m.SOURCE,'io.llmctl.adaptive-idle.overlay-sha256':m.OVERLAY}}})
        digest='sha256:'+m.sha(config)
        manifest=m.encode({'schemaVersion':2,'mediaType':'application/vnd.oci.image.manifest.v1+json',
            'config':{'mediaType':'application/vnd.oci.image.config.v1+json','digest':digest,'size':len(config)}})
        manifest+=b' '*(7832-len(manifest))
        path=self.fixture.path/'public';path.mkdir(mode=0o700)
        for name,raw in [('manifest',manifest),('config',config)]:
            (path/name).write_bytes(raw);(path/name).chmod(0o600)
        original=m.ProtectedFile
        def fixture_file(pathname):return original(pathname,trusted_uid=os.getuid(),fixture_root=self.fixture.path)
        with patch.object(m,'PLATFORM','sha256:'+m.sha(manifest)),patch.object(m,'CONFIG',digest),patch.object(m,'ProtectedFile',side_effect=fixture_file):
            with m.read_cached_oci({'cachedPublicOCIPaths':{'manifest':str(path/'manifest'),'config':str(path/'config')}}) as capability:
                capability.check()
                (path/'config').write_bytes(config+b' ')
                with self.assertRaises(m.Refused):capability.check()
            with self.assertRaises(m.Refused):capability.check()



if __name__=='__main__':unittest.main(verbosity=2)
