#!/usr/bin/env python3
"""Offline archive/CAS/current stopped-owner refusals; no live model actions."""
import copy
import datetime
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
import py_compile
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'h044'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
spec = importlib.util.spec_from_file_location('_h044_fixture',Path(__file__).resolve().parents[1]/'h044'/'test_image_owner_reconcile.py')
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
import image_owner_successor as m
core = m.core


class ArchiveTests(unittest.TestCase):
    setUp = old.RealWriterTests.setUp
    guard = old.RealWriterTests.guard
    actual = old.RealWriterTests.actual
    verify = old.RealWriterTests.verify

    def populate(self):
        files = {}
        for k,v in self.original.items():
            p = self.fixture.archive_path/(k+'.original.json'); p.write_bytes(v); p.chmod(0o400)
        manifest = core.encode({'schema':'h044-six-raw-archive-v1','files':{k:core.sha(v) for k,v in self.original.items()}})
        p = self.fixture.archive_path/'manifest.json'; p.write_bytes(manifest); p.chmod(0o400)
        for p in self.fixture.archive_path.iterdir():
            held = core.ProtectedFile(str(p),trusted_uid=os.getuid(),fixture_root=self.fixture.path)
            files[p.name] = held; self.addCleanup(held.close)
        return files,core.sha(manifest)

    def transaction(self):
        archived,digest = self.populate()
        self.archive_original = {k:(v.raw,core.signature(v.before)) for k,v in archived.items()}
        return m.ArchiveTransaction(self.files,self.fixture.archive,self.guard,
            anchors={k:self.fixture.anchor for k in ('config','state','operation','recovery')},
            archive_files=archived,manifest_sha=digest)

    def assert_archive_unchanged(self):
        for name,(raw,signature) in self.archive_original.items():
            p = self.fixture.archive_path/name
            self.assertEqual(p.read_bytes(),raw); self.assertEqual(core.signature(p.stat()),signature)

    def test_populated_archive_adopts_all_seven_without_rewrite(self):
        tx = self.transaction(); result = tx.apply(self.successors,self.verify)
        self.assertEqual(result['journal'],['ADOPTED_ALL_SEVEN_IMMUTABLE_ORIGINALS','COMMITTED_NORMAL_REGISTRATION'])
        self.assert_archive_unchanged()
        self.assertEqual(self.actual()['checkpoint'],self.original['checkpoint'])

    def test_archive_hash_bytes_manifest_extra_mode_inode_refusals(self):
        # Each mutation is rejected before any protected original changes.
        tx = self.transaction(); held = tx.archive_files['api.original.json']; path = Path(held.path)
        path.chmod(0o600); path.write_bytes(b'{}')
        with self.assertRaises(core.Refused): tx.apply(self.successors,self.verify)
        self.assertEqual(self.actual(),self.original)

    def test_identical_archive_bytes_replaced_inode_refuses(self):
        tx = self.transaction(); p = self.fixture.archive_path/'manifest.json'
        new = self.fixture.archive_path/'foreign'; new.write_bytes(p.read_bytes()); new.chmod(0o400); os.replace(new,p)
        with self.assertRaises(core.Refused): tx.apply(self.successors,self.verify)
        self.assertEqual(self.actual(),self.original)

    def test_manifest_hash_wrong_and_extra_leaf_refuse(self):
        tx = self.transaction(); tx.manifest_sha = '0'*64
        with self.assertRaises(core.Refused): tx.apply(self.successors,self.verify)
        self.assertEqual(self.actual(),self.original)
        tx.manifest_sha = core.sha(tx.archive_files['manifest.json'].raw)
        (self.fixture.archive_path/'extra').write_bytes(b'preserve')
        with self.assertRaises(core.Refused): tx.apply(self.successors,self.verify)
        self.assertEqual(self.actual(),self.original)

    def test_conditional_rollback_restores_exact_bytes_preserves_archive(self):
        tx = self.transaction()
        with self.assertRaisesRegex(RuntimeError,'registration'):
            tx.apply(self.successors,lambda:(_ for _ in ()).throw(RuntimeError('registration')))
        self.assertEqual(self.actual(),self.original); self.assert_archive_unchanged()

    def test_foreign_identical_successor_inode_is_not_rolled_back(self):
        tx = self.transaction()
        def foreign():
            p = self.fixture.runtime/'api.json'; new = self.fixture.runtime/'foreign'
            new.write_bytes(p.read_bytes()); new.chmod(0o600); os.replace(new,p)
            raise RuntimeError('registration')
        with self.assertRaises(core.RollbackFailed): tx.apply(self.successors,foreign)
        self.assertEqual(self.actual()['api'],self.successors['api']); self.assert_archive_unchanged()

    def test_restart_schema_and_history_tokens_checkpoint_profiles_preserved(self):
        values = copy.deepcopy(self.values)
        values['operation']['recovery'] = values['recovery']['token']
        values['recovery'].update(phase='restart',child_start=core.INVOCATION)
        values['state'].update(historical_failure={'old':'failure'},last_native_actions={'old':'keep'})
        raw = {k:core.encode(v) for k,v in values.items()}; expected = {k:core.sha(v) for k,v in raw.items()}
        result = m.stopped_successors(raw,values['config'],{'pid':123,'start_ticks':456},expected=expected)
        self.assertEqual(result['config'],raw['config'].replace(core.READING_GPU.encode(),core.EXTERNAL_GPU.encode()))
        self.assertEqual(result['api'],raw['api'].replace(core.PARENT.encode(),core.PLATFORM.encode()))
        state = core.strict(result['state'])
        self.assertEqual(state['historical_failure'],values['state']['historical_failure'])
        self.assertEqual(state['last_native_actions'],values['state']['last_native_actions'])
        self.assertIn(b'"historical_failure": {\n    "old": "failure"\n  }',result['state'])
        self.assertEqual(state['phase'],'stopped'); self.assertIsNone(state['container'])
        self.assertEqual(state['native_actions'],{}); self.assertIsNone(state['native_generation'])
        for key in ('operation','recovery'):
            self.assertEqual(core.strict(result[key])['status'],'complete')
            self.assertEqual(core.strict(result[key])['boot'],core.BOOT)
        self.assertNotIn('checkpoint',result)
        wrong = copy.deepcopy(values); wrong['operation']['recovery'] = 'f'*32
        changed = {k:core.encode(v) for k,v in wrong.items()}
        with self.assertRaises(core.Refused):m.stopped_successors(changed,wrong['config'],{'pid':123,'start_ticks':456},
            expected={k:core.sha(v) for k,v in changed.items()})

    def test_dedicated_executable_stream_large_binary_config_bound_unchanged(self):
        path = self.fixture.path/'synthetic-binary'; raw = b'X'*(262144+17)
        path.write_bytes(raw); path.chmod(0o500)
        with m.ProtectedExecutable(str(path),trusted_uid=os.getuid(),fixture_root=self.fixture.path) as held:
            self.assertEqual(held.whole_sha256,core.sha(raw)); held.check()
            self.assertFalse(hasattr(held,'raw'))
            path.chmod(0o600); path.write_bytes(raw[:-1]+b'Y')
            with self.assertRaises(core.Refused):held.check()
        with self.assertRaises(core.Refused):core.ProtectedFile(str(path),trusted_uid=os.getuid(),fixture_root=self.fixture.path)
        too_large = self.fixture.path/'too-large'
        with too_large.open('wb') as out:out.truncate(128*1024**2+1)
        too_large.chmod(0o500)
        with self.assertRaises(core.Refused):m.ProtectedExecutable(str(too_large),trusted_uid=os.getuid(),fixture_root=self.fixture.path)

    def test_readonly_hardware_keeps_latch_bytes_and_refuses_existing_target(self):
        from control.hardware_latch import empty_state
        from lifecycle.hardware_policy import HardwarePolicy
        path = self.fixture.path/'latch.json'; path.write_bytes(core.encode(empty_state())); path.chmod(0o600)
        held = core.ProtectedFile(str(path),trusted_uid=os.getuid(),fixture_root=self.fixture.path)
        self.addCleanup(held.close)
        record = object.__new__(m.StoppedRecord)
        record.protected_sources = {m.LATCH_PATH:held}
        record.go = {'hardwareLatchIdentity':m.identity(held),'hardwareLatchSha256':core.sha(held.raw)}
        record.runtime = SimpleNamespace(hardware_observation={'boot':core.BOOT,
            'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'observation_id':'fixture-probe'})
        record.lease = None; record.services_check = lambda:None
        original_init = HardwarePolicy.__init__
        def init(policy,*args,**kwargs):
            original_init(policy,*args,**kwargs);policy.boot=lambda:{'boot_id':core.BOOT}
        with patch.object(HardwarePolicy,'__init__',new=init),\
             patch.object(HardwarePolicy,'_owner',return_value=SimpleNamespace(export_state=lambda:empty_state())):
            record.hardware_readonly()
            self.assertEqual(path.read_bytes(),held.raw)
            record.runtime.hardware_observation['observed_at'] = '2020-01-01T00:00:00+00:00'
            with self.assertRaisesRegex(core.Refused,'stale'):record.hardware_readonly()
        saved = {'schema_version':1,'targets':{core.EXTERNAL_GPU:{'hardware_latched':True,'boot_id':core.OLD_BOOT}}}
        with patch.object(HardwarePolicy,'__init__',new=init),\
             patch.object(HardwarePolicy,'_owner',return_value=SimpleNamespace(export_state=lambda:saved)):
            with self.assertRaisesRegex(core.Refused,'must_not_clear'):record.hardware_readonly()
        self.assertEqual(path.read_bytes(),held.raw)


class ControlTests(unittest.TestCase):
    def go(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        go = m.request() | {'status':'GO','issuedBy':'root','bootId':core.BOOT,'sourceSha256':'a'*64,
            'ownerSourceSha256':core.OWNER_SOURCE_SHA,'notBeforeUtc':now.isoformat(),
            'expiresUtc':(now+datetime.timedelta(seconds=180)).isoformat(),
            'helperSha256':{'/stage/helper':'b'*64},'apiCanonicalSourceSha256':{k:'c'*64 for k in core.API_FILES},
            'peerFileSha256':{'/peer':'d'*64},'residentBindings':{k:{} for k in ('Qwen0','Qwen1','MiMo','VisionQwen','VisionOCR')},
            'expectedFileIdentity':{k:[1]*9 for k in core.PATHS},
            'archiveFileIdentity':{k:[1]*9 for k in {k+'.original.json' for k in core.PATHS}|{'manifest.json'}},
            'stoppedUnits':{k:{} for k in m.UNITS},'cachedPublicOCIPaths':{'manifest':'/m','config':'/c'},
            'archiveDirectoryIdentity':[1,2,3,0,0],'apiUnitRawSha256':'e'*64,'backendUnitRawSha256':'f'*64,
            'dockerBinarySha256':'0'*64,'daemonId':'daemon','pythonSha256':'1'*64,'rootStage':'/stage',
            'hardwareLatchSha256':'2'*64,'hardwareLatchIdentity':[1]*9}
        return go,now

    def test_historical_go_stale_boot_bool_expiry_partial_peers_refuse(self):
        go,now = self.go(); m.validate_go(go,'a'*64,now)
        for key,value in [('phase','I-image04'),('bootId',core.OLD_BOOT),('maximumInvocations',True),
                          ('archiveManifestSha256','f'*64),('residentBindings',{'MiMo':{}}),
                          ('nativeImageStartPermitted',True)]:
            wrong = copy.deepcopy(go); wrong[key] = value
            with self.assertRaises(core.Refused):m.validate_go(wrong,'a'*64,now)
        with self.assertRaises(core.Refused):m.validate_go(go,'a'*64,now+datetime.timedelta(seconds=180))

    def test_state_token_splicing_retains_nested_history_raw_bytes(self):
        raw = b'{ "history" : {"escaped":"\\u0061", "old": [1, 2]}, "phase":"loading" }\n'
        changed = m.replace_fields(raw,{'phase':'stopped','container':None})
        self.assertIn(b'"history" : {"escaped":"\\u0061", "old": [1, 2]}',changed)
        self.assertEqual(core.strict(changed)['phase'],'stopped')

    def test_source_only_import_ignores_existing_matching_cached_code(self):
        fixture = old.ActualStorageFixture(); self.addCleanup(fixture.close)
        path = fixture.path/'cache_fixture.py'
        cached = b'MARKER = "cached"\n'; source = b'MARKER = "source"\n'
        self.assertEqual(len(cached),len(source))
        path.write_bytes(cached); timestamp = path.stat().st_mtime_ns
        py_compile.compile(str(path),doraise=True)
        path.write_bytes(source); os.utime(path,ns=(timestamp,timestamp))
        prefix = str(fixture.path/'ABSENT-PYC-CACHE')
        with patch.object(sys,'pycache_prefix',prefix),patch.object(sys,'dont_write_bytecode',True):
            spec = importlib.util.spec_from_file_location('_cache_source_fixture',path)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            self.assertEqual(module.MARKER,'source');self.assertFalse(Path(prefix).exists())

    def test_exact_actual_read_packet_builds_nonexecutable_control(self):
        import image_control_packet as packet
        source = Path(__file__).resolve().parents[3]/'output/current-read/SOURCE-GRAPH03.json'
        if not source.exists():self.skipTest('private current read packet is exported with worker output')
        graph = json.loads(source.read_text())
        control = packet.build(graph,'/run/llmctl/h046-image-stopped-cas-offline-shape-test',
                               Path(__file__).resolve().parents[2])
        self.assertEqual(control['status'],'SOURCE_ONLY_REVIEW_REQUEST_NOT_GO')
        self.assertEqual(set(control['stoppedUnits']['llm-image-api.service']),
            {'Id','MainPID','ControlPID','ActiveState','ControlGroup','InvocationID','Job','NeedDaemonReload'})
        self.assertEqual(len(control['expectedFileIdentity']['config']),9)
        self.assertEqual(control['residentBindings']['MiMo']['container']['id'],graph['residentBindings']['MiMo']['container']['id'])
        with self.assertRaises(core.Refused):m.validate_go(control,control['sourceSha256'],datetime.datetime.now(datetime.timezone.utc))

    def test_exact_positive_read_commands_refuse_mutation_and_extra_flags(self):
        from image_executor import read_argv_allowed
        go = {'residentBindings':{'Qwen0':{'container':{'id':'a'*64}}}}
        valid = ['/usr/bin/nvidia-smi','--id='+core.EXTERNAL_GPU,'--query-gpu=uuid','--format=csv,noheader,nounits']
        self.assertTrue(read_argv_allowed(valid,core,go))
        for flag in ('-lgc','--lock-gpu-clocks','-fan','-pm','--power-limit','--gpu-reset'):
            self.assertFalse(read_argv_allowed(valid+[flag,'1'],core,go))
            self.assertFalse(read_argv_allowed(['/usr/bin/nvidia-smi',flag,'1'],core,go))
        for argv in (['/usr/bin/docker','container','ls','--all','--no-trunc','--format','{{json .}}','--filter','label=secret'],
            ['/usr/bin/docker','image','inspect','--format','{{json .Config.Env}}',core.PLATFORM],
            ['/usr/bin/systemctl','show','unrelated.service'],['/usr/bin/systemctl','start','llm-image-api.service'],
            ['/usr/bin/findmnt','--json','--mount','/dev/bad'],['/usr/bin/df','--output=avail','--block-size=1','/unrelated']):
            self.assertFalse(read_argv_allowed(argv,core,go))

    def test_stopped_proof_has_no_historical_pid_dependency(self):
        source = Path(m.__file__).read_text()
        current = source[source.index('def fresh_stopped('):source.index('class StoppedRecord')]
        self.assertNotIn('/proc/11783',current)
        self.assertNotIn('API_OWNER',current)
        unit = {'MainPID':'0'}
        record = SimpleNamespace(check=lambda:None,module=None,go={'stoppedUnits':{k:unit for k in m.UNITS},'apiCanonicalSourceSha256':{}},
                                 runtime=SimpleNamespace(prove_absent=lambda _:None))
        with patch.object(core,'_unit',return_value=unit),patch.object(core,'_absent'),patch.object(m,'Path') as paths:
            paths.return_value.iterdir.return_value = []
            proof = m.fresh_stopped(record)
            self.assertFalse(proof['historicalPidUsed']); self.assertEqual(proof['currentImageOwner'],'ABSENT')
        with patch.object(core,'_unit',return_value={'MainPID':'1'}):
            with self.assertRaises(core.Refused):m.fresh_stopped(record)

    def test_current_foreign_detached_api_command_refuses(self):
        stat_raw = b'123 (python) '+b' '.join([b'S']+[b'1']*25)
        entries = {'stat':SimpleNamespace(read_bytes=lambda:stat_raw),
                   'cmdline':SimpleNamespace(read_bytes=lambda:core.API_FILES[1].encode()+b'\0'),
                   'cgroup':SimpleNamespace(read_text=lambda:'0::/foreign.slice')}
        class Proc:
            name = '123'
            def __truediv__(self,key):return entries[key]
        unit = {'MainPID':'0'}
        record = SimpleNamespace(check=lambda:None,module=None,go={'stoppedUnits':{k:unit for k in m.UNITS},'apiCanonicalSourceSha256':{}},
            runtime=SimpleNamespace(prove_absent=lambda _:None))
        with patch.object(core,'_unit',return_value=unit),patch.object(core,'_absent'),patch.object(m,'Path') as paths:
            paths.return_value.iterdir.return_value = [Proc()]
            with self.assertRaisesRegex(core.Refused,'foreign_or_active'):m.fresh_stopped(record)


if __name__ == '__main__':unittest.main(verbosity=2)
