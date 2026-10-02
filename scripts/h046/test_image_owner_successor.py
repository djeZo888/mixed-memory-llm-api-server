#!/usr/bin/env python3
"""Offline archive/CAS/current stopped-owner refusals; no live model actions."""
import copy
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
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
        parent = os.fstat(held.directory)
        binding = {'path':m.LATCH_PATH,'protectedMetadata':m.identity(held)[2:6],
            'parentIdentity':[parent.st_dev,parent.st_ino,parent.st_mode,parent.st_uid,parent.st_gid],
            'semantic':m.mutable_semantic(m.LATCH_PATH,held.raw),'temperatureLimitC':None}
        record.mutable_descriptors = {m.LATCH_PATH:m.MutableDescriptor(str(path),binding,audit=lambda _:None,
            trusted_uid=os.getuid(),fixture_root=self.fixture.path)}
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
        actual = json.loads((Path(__file__).resolve().parents[2]/'output/mutable-discovery06.json').read_text())
        guard = actual['descriptors'][m.GUARD_PATH]['value']
        guard['observed_at'] = guard['sample']['hardware_validation']['observed_at'] = now.isoformat()
        go['mutableSourceSha256'] = m.MUTABLE_SOURCE_SHA
        go['mutableSourceIdentity'] = {p:v['identity'] for p,v in actual['sources'].items()}
        go['mutableDescriptorBinding'] = {p:{'path':p,'protectedMetadata':v['identity'][2:6],
            'parentIdentity':v['parentIdentity'],'temperatureLimitC':actual['guardTemperatureLimitC'] if p == m.GUARD_PATH else None,
            'semantic':m.mutable_semantic(p,core.encode(v['value']),temperature_limit=actual['guardTemperatureLimitC'])}
            for p,v in actual['descriptors'].items()}
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
        if not source.exists():source = Path(__file__).resolve().parents[3]/'references/current-read_SOURCE-GRAPH03.json'
        if not source.exists():self.skipTest('private current read packet is exported with worker output')
        graph = json.loads(source.read_text())
        canonical = Path(__file__).resolve().parents[3]/'output/canonical-read02/stdout'
        if not canonical.exists():self.skipTest('actual frozen canonical read packet is exported with worker output')
        control = packet.build(graph,'/run/llmctl/h046-image-stopped-cas-offline-shape-test',
                               Path(__file__).resolve().parents[2],json.loads(canonical.read_text()),
                               json.loads((Path(__file__).resolve().parents[2]/'output/mutable-discovery06.json').read_text()))
        self.assertEqual(control['status'],'SOURCE_ONLY_REVIEW_REQUEST_NOT_GO')
        self.assertEqual(set(control['stoppedUnits']['llm-image-api.service']),
            {'Id','MainPID','ControlPID','ActiveState','ControlGroup','InvocationID','Job','NeedDaemonReload'})
        self.assertEqual(len(control['expectedFileIdentity']['config']),9)
        self.assertEqual(control['residentBindings']['MiMo']['container']['id'],graph['residentBindings']['MiMo']['container']['id'])
        self.assertIn('/boot/efi',control['canonicalStorageBinding']['findmntTargets'])
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


class CanonicalArgvTests(unittest.TestCase):
    """Run actual frozen Storage methods; replace discovery transport only.

    The private read packet is an actual protected SSH read, not a fixture
    whitelist. Filesystem/discovery replies below are isolated test data; these
    tests make no SSH calls or hardware, service, lease or inference operations.
    """
    @classmethod
    def setUpClass(cls):
        cls.phase = Path(__file__).resolve().parents[3]
        cls.packet_path = cls.phase/'output/canonical-read02/stdout'
        if not cls.packet_path.exists():
            raise unittest.SkipTest('actual frozen canonical SSH packet required')
        cls.packet = json.loads(cls.packet_path.read_text())
        cls.source_raws = {path:value['text'].encode('utf-8') for path,value in cls.packet['sources'].items()}
        cls.storage_path = core.RELEASE+'/scripts/install/storage.py'
        cls.storage_module = SimpleNamespace(__name__='_actual_frozen_canonical_storage',__file__=cls.storage_path)
        exec(compile(cls.source_raws[cls.storage_path],cls.storage_path,'exec'),cls.storage_module.__dict__)
        import image_executor
        cls.executor = image_executor

    def binding(self):
        return self.executor.canonical_storage_binding(copy.deepcopy(self.packet))

    def go(self):
        return {'canonicalStorageBinding':self.binding(),'rootStage':'/run/llmctl/h046-image-stopped-cas-pyc-test',
            'residentBindings':{'Qwen0':{'container':{'id':'a'*64}}}}

    def allowed(self,argv,go=None):
        return self.executor.read_argv_allowed(argv,core,self.go() if go is None else go)

    def test_actual_packet_sha_closes_all_seven_local_canonical_sources(self):
        expected = {
            core.BASE+'/source/service.py':'scripts/image_runtime/service.py',
            **{core.RELEASE+'/'+name:name for name in (
                'scripts/install/storage.py','scripts/install/storage_io.py',
                'scripts/lifecycle/manager.py','scripts/lifecycle/runtime_io.py',
                'scripts/lifecycle/storage_binding.py','scripts/common/registered-storage.py')}}
        self.assertEqual(set(self.source_raws),set(expected))
        for path,relative in expected.items():
            with self.subTest(path=path):
                raw = self.source_raws[path]
                self.assertEqual(hashlib.sha256(raw).hexdigest(),self.packet['sources'][path]['sha256'])
                self.assertEqual((self.phase/'repo'/relative).read_bytes(),raw)
        self.assertEqual(self.packet['schema'],'h046-canonical-readonly-argv-source-packet-v1')
        for field in ('sharedHostWrites','inferenceInvoked','lifecycleInvoked'):
            self.assertIs(self.packet[field],False)

    def frozen_storage(self):
        """Real protected-registry parsing plus full mount/capacity verifier."""
        tmp = tempfile.TemporaryDirectory(prefix='canonical-argv-',dir=self.phase/'output')
        self.addCleanup(tmp.cleanup); root = Path(tmp.name)
        registration = copy.deepcopy(self.packet['storageRegistration']['registration'])
        for path in {'/proc/self','/etc/local-ai-server',*registration['roots'].values(),
                     *[registration[role][field] for role in ('data','models') for field in ('path','mount')],
                     *[path for path,entry in self.packet['bootPaths'].items() if entry['exists']]}:
            local = root/path.lstrip('/'); local.mkdir(parents=True,exist_ok=True)
            local.chmod(0o700)
        registry_file = root/'etc/local-ai-server/storage.json'
        registry_file.write_text(json.dumps(registration));registry_file.chmod(0o600)
        root_mount = {'target':'/','source':'/dev/canonical-test-root','uuid':'root-test-uuid',
                      'fstype':'ext4','options':'rw','maj:min':'0:1'}
        blockrows = [{'name':'/dev/canonical-test-root','path':'/dev/canonical-test-root',
                      'type':'disk','ro':False,'maj:min':'0:1','uuid':'root-test-uuid'}]
        for role in ('data','models'):
            entry = registration[role]
            parents = [p for p in entry['parents'] if p != entry['source']]
            for parent in parents:
                if not any(row['path']==parent for row in blockrows):
                    blockrows.append({'name':parent,'path':parent,'type':'disk','ro':False,
                                      'maj:min':'9:'+str(len(blockrows)), 'uuid':None})
            blockrows.append({'name':entry['source'],'path':entry['source'],'type':'part' if parents else 'disk',
                              'pkname':parents[0] if parents else None,'ro':False,
                              'maj:min':entry['device'],'uuid':entry['uuid'],'mountpoints':[entry['mount']]})
        (root/'proc/self/mountinfo').write_text('1 0 0:1 / / rw - ext4 /dev/canonical-test-root rw\n'+
            ''.join(f'{index} 1 {registration[role]["device"]} / {registration[role]["mount"]} rw - ext4 {registration[role]["source"]} rw\n'
                    for index,role in enumerate(('data','models'),2)))
        calls = []; test = self
        class Runner:
            def run(self,argv,*,timeout=30):
                calls.append(list(argv))
                test.assertTrue(test.allowed(argv),repr(argv))
                if argv[0]=='lsblk':return json.dumps({'blockdevices':blockrows})
                if argv[0]=='df':return 'Avail\n107374182400\n'
                if argv[0]=='findmnt':
                    path = argv[-1]
                    if path=='/' or path in test.packet['bootPaths']:mount = root_mount
                    else:
                        role = 'models' if path==registration['models']['path'] else 'data'
                        entry = registration[role]
                        mount = {'target':entry['mount'],'source':entry['source'],'uuid':entry['uuid'],
                                 'fstype':entry['fstype'],'options':'rw','maj:min':entry['device']}
                    return json.dumps({'filesystems':[mount]})
                test.fail('unexpected canonical discovery command '+repr(argv))
        config = {name:registration[role][field] for name,role,field in (
            ('data_dir','data','path'),('data_uuid','data','uuid'),
            ('model_dir','models','path'),('model_uuid','models','uuid'))}
        config['storage_mode'] = registration['storage_mode']
        storage = self.storage_module.Storage(config,Runner(),system_root=root)
        return storage,calls

    def test_frozen_verify_full_and_role_calls_cover_every_current_target(self):
        storage,calls = self.frozen_storage()
        self.assertEqual(storage._roots(),self.packet['storageRegistration']['registration']['roots'])
        for roles in (('data','models'),('data',),('models',)):
            with self.subTest(roles=roles):
                snapshot = storage.verify(roles=roles)
                self.assertEqual(snapshot['verified_roles'],list(roles))
        self.assertEqual({argv[-1] for argv in calls if argv[0]=='findmnt'},set(self.packet['findmntTargets']))
        self.assertEqual({argv[-1] for argv in calls if argv[0]=='df'},set(self.packet['dfTargets']))
        self.assertTrue(any(argv[-1]=='/boot/efi' for argv in calls if argv[0]=='findmnt'))

    def test_every_current_findmnt_df_exact_shape_aliases_and_extra_flags(self):
        binding = self.binding();go = self.go()
        for binary,targets,prefix in (
                ('findmnt',binding['findmntTargets'],['--json','--output','TARGET,SOURCE,UUID,FSTYPE,OPTIONS,MAJ:MIN','--target']),
                ('df',binding['dfTargets'],['--output=avail','--block-size=1'])):
            for path in targets:
                for alias in (binary,'/usr/bin/'+binary):
                    argv = [alias,*prefix,path]
                    with self.subTest(argv=argv):
                        self.assertTrue(self.allowed(argv,go))
                        self.assertFalse(self.allowed([*argv,'--extra'],go))
                        self.assertFalse(self.allowed([*argv[:-1],'/unregistered'],go))
                        self.assertFalse(self.allowed([*argv[:-1],path+'/../extra'],go))
                for executable in ('/opt/bin/'+binary,'/bin/'+binary,'//usr/bin/'+binary):
                    self.assertFalse(self.allowed([executable,*prefix,path],go))
        self.assertFalse(self.allowed(['findmnt','--json','--output','SOURCE','--target','/data'],go))
        self.assertFalse(self.allowed(['findmnt','--json','--output','TARGET,SOURCE,UUID,FSTYPE,OPTIONS,MAJ:MIN','--target','/data','--evaluate'],go))
        self.assertFalse(self.allowed(['df','--output=avail','--block-size=1','/data','--total'],go))
        for go_value in ({},{'canonicalStorageBinding':None}):
            self.assertFalse(self.allowed(['findmnt','--json','--output','TARGET,SOURCE,UUID,FSTYPE,OPTIONS,MAJ:MIN','--target','/'],go_value))
            self.assertFalse(self.allowed(['df','--output=avail','--block-size=1','/'],go_value))

    def test_actual_source_bytes_changed_and_binding_target_or_config_changes_refuse(self):
        original = self.binding()
        self.executor.validate_storage_binding(original,self.source_raws)
        for path in self.source_raws:
            changed = dict(self.source_raws);changed[path] += b'\n# changed canonical source\n'
            with self.subTest(source=path),self.assertRaises((ValueError,core.Refused)):
                self.executor.validate_storage_binding(original,changed)
        mutations = (
            lambda b:b['findmntTargets'].append('/data/extra'),
            lambda b:b['findmntTargets'].remove('/boot/efi'),
            lambda b:b['dfTargets'].append('/data/logs'),
            lambda b:b['registration']['roots'].update(logs='/data/elsewhere'),
            lambda b:b['registration']['roots'].update(extra='/data/export'),
            lambda b:b['registration']['data'].update(path='/other'),
            lambda b:b['registration']['models'].update(mount='/different'),
            lambda b:b['sourceSha256'].update({self.storage_path:'0'*64}))
        for mutate in mutations:
            changed = copy.deepcopy(original);mutate(changed)
            with self.subTest(changed=changed),self.assertRaises((ValueError,core.Refused)):
                self.executor.validate_storage_binding(changed,self.source_raws)

    def test_held_actual_binding_rejects_source_registry_boot_and_target_inode_drift(self):
        e = self.executor;binding = self.binding()
        def stat_value(identity):
            return SimpleNamespace(**dict(zip(('st_dev','st_ino','st_mode','st_uid','st_gid',
                'st_nlink','st_size','st_mtime_ns','st_ctime_ns'),identity)))
        held = {};current_bytes = {};directories = copy.deepcopy(binding['targetDirectoryIdentity'])
        existence = {path:value['exists'] for path,value in binding['bootPaths'].items()}
        regraw = (json.dumps(binding['registration'],sort_keys=True,indent=2)+'\n').encode()
        self.assertEqual(hashlib.sha256(regraw).hexdigest(),binding['registrationSha256'])
        class Protected:
            def __init__(self,path):
                self.path=path;self.fd=len(held)+100
                self.raw=regraw if path==e.REGISTRATION else self_source[path]
                self.before=stat_value(binding['registrationIdentity'] if path==e.REGISTRATION else binding['sourceIdentity'][path])
                held[path]=self;current_bytes[self.fd]=self.raw
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def check(self):pass
        self_source=self.source_raws
        def lstat(path):
            identity=directories[str(path)]
            return stat_value([*identity,2,4096,0,0])
        with patch.object(e.os,'pread',side_effect=lambda fd,n,offset:current_bytes[fd][:n]),\
             patch.object(e.os.path,'lexists',side_effect=lambda path:existence[str(path)]),\
             patch.object(Path,'lstat',new=lstat):
            guard=e.CanonicalStorageGuard(binding,SimpleNamespace(ProtectedFile=Protected))
            self.addCleanup(guard.close);guard.check()
            for path in (*e.CANONICAL_SHA256,e.REGISTRATION):
                file=held[path];original=file.before.st_ino
                file.before.st_ino+=1
                with self.subTest(inode=path),self.assertRaisesRegex(ValueError,'inode changed'):
                    guard.check()
                file.before.st_ino=original
                before=current_bytes[file.fd];current_bytes[file.fd]=before+b' '
                with self.subTest(bytes=path),self.assertRaises(ValueError):guard.check()
                current_bytes[file.fd]=before
            file=held[e.REGISTRATION];original=file.raw
            changed=copy.deepcopy(binding['registration']);changed['roots']['logs']='/data/foreign-logs'
            file.raw=(json.dumps(changed,sort_keys=True,indent=2)+'\n').encode()
            current_bytes[file.fd]=file.raw
            with self.assertRaisesRegex(ValueError,'registration config/inode changed'):guard.check()
            file.raw=original;current_bytes[file.fd]=original
            for path in directories:
                directories[path][1]+=1
                with self.subTest(directory_inode=path),self.assertRaisesRegex(ValueError,'directory inode changed'):
                    guard.check()
                directories[path][1]-=1
            existence['/boot/efi']=False
            with self.assertRaisesRegex(ValueError,'boot target set changed'):guard.check()
            existence['/boot/efi']=True;guard.check()

    def test_canonical_helper_emitted_cache_prefix_is_exact_and_report_flags_refuse(self):
        e=self.executor;go=self.go();path=e.RELEASE+'/scripts/common/registered-storage.py'
        for extra in ([],['--root-guard']):
            for interpreter in ('/usr/bin/python3','/usr/bin/python3.12'):
                argv=[interpreter,'-I','-B',path,'--json',*extra]
                emitted=e.storage_guard_argv(argv,core,go)
                expected=['/usr/bin/python3.12','-I','-B','-X',
                    'pycache_prefix='+go['rootStage']+'/NO-PYC-CACHE',path,'--json',*extra]
                self.assertEqual(emitted,expected);self.assertTrue(self.allowed(argv,go))
                self.assertTrue(self.allowed(emitted,go))
                for changed in (
                    [*emitted,'--report','/data/logs/test.json'],
                    [*emitted,'--json'],
                    [*emitted[:4],'pycache_prefix=/codex/unbound',*emitted[5:]],
                    [*emitted[:4],emitted[4]+'/extra',*emitted[5:]],
                    [*emitted[:3],'-S',*emitted[3:]],
                    [*emitted[:3],'-E',*emitted[3:]]):
                    self.assertFalse(self.allowed(changed,go))
        for extra in (['--report','/data/logs/test.json'],['--root-guard','--report','/data/logs/test.json'],['--report'],['--json']):
            argv=['/usr/bin/python3.12','-I','-B',path,'--json',*extra]
            self.assertFalse(self.allowed(argv,go))

    def test_source_cache_prefix_ignores_existing_timestamp_size_matched_pyc(self):
        """Retain a matching stale-cache fixture for separate direct-child checks."""
        root=Path(tempfile.mkdtemp(prefix='tests-canonical-cache-',dir=self.phase/'output'))
        fixture=root/'fixture.py';cached=b'VALUE = "cached"\n';source=b'VALUE = "source"\n'
        self.assertEqual(len(cached),len(source))
        fixture.write_bytes(cached);timestamp=fixture.stat().st_mtime_ns
        with patch.object(sys,'pycache_prefix',None):py_compile.compile(str(fixture),doraise=True)
        fixture.write_bytes(source);os.utime(fixture,ns=(timestamp,timestamp))
        prefix=root/'NO-PYC-CACHE';self.assertFalse(prefix.exists())
        script=root/'read-source.py'
        script.write_text('import importlib.util,json,sys\nfrom pathlib import Path\n'
            'p=Path(__file__).with_name("fixture.py")\n'
            's=importlib.util.spec_from_file_location("frozen_cache_fixture",p)\n'
            'm=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n'
            'print(json.dumps({"value":m.VALUE,"isolated":sys.flags.isolated,"noBytecode":sys.flags.dont_write_bytecode,"cachePrefix":sys.pycache_prefix}))\n')
        for cache_prefix,expected in ((None,'cached'),(str(prefix),'source')):
            with patch.object(sys,'pycache_prefix',cache_prefix),patch.object(sys,'dont_write_bytecode',True):
                spec=importlib.util.spec_from_file_location('_matching_stale_cache_fixture',fixture)
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                self.assertEqual(module.VALUE,expected)
        (root/'PROOF-REQUEST.json').write_text(json.dumps({
            'status':'OFFLINE_MATCHING_CACHE_FIXTURE; actual direct child checks required separately',
            'baselineArgv':[sys.executable,'-I','-B',str(script)],
            'sourceArgv':[sys.executable,'-I','-B','-X','pycache_prefix='+str(prefix),str(script)],
            'fixtureSourceSha256':hashlib.sha256(source).hexdigest(),
            'cachedSourceSha256':hashlib.sha256(cached).hexdigest(),
            'fixtureSize':len(source),'fixtureMtimeNs':timestamp},sort_keys=True,indent=2)+'\n')
        self.assertFalse(prefix.exists())

    def test_aliases_only_preserve_exact_known_gpu_docker_systemctl_shapes(self):
        go = self.go()
        for alias in ('nvidia-smi','/usr/bin/nvidia-smi'):
            exact = [alias,'--id='+core.EXTERNAL_GPU,'--query-gpu=uuid','--format=csv,noheader,nounits']
            self.assertTrue(self.allowed(exact,go))
            for flag in ('--lock-gpu-clocks','-lgc','--fan','-fan','--persistence-mode','-pm','--gpu-reset','--power-limit'):
                self.assertFalse(self.allowed([*exact,flag,'1'],go))
                self.assertFalse(self.allowed([alias,flag,'1'],go))
            self.assertFalse(self.allowed([alias,'--query-gpu=uuid','--format=csv,noheader,nounits'],go))
            self.assertFalse(self.allowed([alias,'--id='+core.READING_GPU,*exact[2:]],go))
        for alias in ('docker','/usr/bin/docker'):
            self.assertTrue(self.allowed([alias,'info','--format','{{.ID}}'],go))
            self.assertFalse(self.allowed([alias,'info','--format','{{json .}}'],go))
            self.assertFalse(self.allowed([alias,'container','ls','--all','--no-trunc','--format','{{json .}}','--filter','status=exited'],go))
            self.assertFalse(self.allowed([alias,'container','start','a'*64],go))
        properties = '--property=Id,MainPID,ControlPID,ActiveState,ControlGroup,InvocationID,Job,NeedDaemonReload'
        for alias in ('systemctl','/usr/bin/systemctl'):
            for unit in m.UNITS:
                self.assertTrue(self.allowed([alias,'show',unit,properties],go))
                self.assertFalse(self.allowed([alias,'show',unit,properties,'--all'],go))
                self.assertFalse(self.allowed([alias,'start',unit],go))
            self.assertFalse(self.allowed([alias,'show','unrelated.service',properties],go))


if __name__ == '__main__':unittest.main(verbosity=2)
