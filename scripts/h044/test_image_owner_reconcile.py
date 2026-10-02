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

    def test_cli_is_request_only_no_runtime_write_or_signals(self):
        source=Path(m.__file__).read_text()
        self.assertNotIn('os.kill',source)
        self.assertNotIn('systemctl',source)
        self.assertNotIn('docker',source)
        self.assertNotIn('atomic_json',source)
        self.assertEqual(m.request()['runtimeWriter'],'NOT_IMPLEMENTED; schema/guard/settlement review required')


if __name__=='__main__': unittest.main(verbosity=2)
