"""Offline exact 950000 -> 480000 transition; no lifecycle or model calls."""
import contextlib
import copy
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('context_same_boot_fixture',
    Path(__file__).with_name('test_mimo_same_boot_source.py'))
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
o, sha, BOOT = f.o, f.sha, f.BOOT


class ContextReductionTests(unittest.TestCase):
    save = f.SameBootSourceTests.save

    def setUp(self):
        f.SameBootSourceTests.setUp(self)
        raw = Path(__file__).resolve().parents[1].joinpath('scripts/runtime/mimo/launch.json').read_bytes()
        (self.base / 'source/launch.json').write_bytes(raw)
        self.old.update(native_argv=json.loads(raw)['native_argv'] + ['--no-host'],
                        no_host=True, max_output_tokens=65536, parallel=1,
                        runtime_revision=o.RUNTIME_REVISION, required_gpu_uuids=[o.GPU])
        self.old['source_sha256'][str(self.base / 'source/launch.json')] = sha(raw)
        self.new = copy.deepcopy(self.old)
        self.new['context'] = 480000
        for flag in ('--ctx-size', '--kv-unified-per-slot'):
            self.new['native_argv'][self.new['native_argv'].index(flag) + 1] = '480000'
        self.new['source_sha256'][str(self.base / 'source/owner.py')] = sha(b'new-reviewed-source')
        self.delta = self.delta_for(self.new)
        self.selected['manifest_sha256'] = o.digest(self.old)
        self.state.update(manifest_sha256=o.digest(self.old), selection=self.selected)
        self.guard.update(manifest_sha256=o.digest(self.old), selection=self.selected)
        self.running = copy.deepcopy(self.state)
        for n,v in [('manifest.json',self.old),('selection.json',self.selected),('state.json',self.state),
                    ('guard.json',self.guard),(o.CONTEXT_DELTA,self.delta),(o.CONTEXT_MANIFEST,self.new)]:
            self.save(n,v)
        self.delta_sha = sha((self.base / o.CONTEXT_DELTA).read_bytes())

    def delta_for(self, new):
        path = str(self.base / 'source/owner.py')
        return {'schema_version': 1, 'transition': o.CONTEXT_TRANSITION,
                'prior_manifest_sha256': o.digest(self.old), 'manifest_sha256': o.digest(new),
                'source_sha256': {path: {'old': self.old['source_sha256'][path],
                                       'new': new['source_sha256'][path]}}}

    def prepare(self):
        return o.prepare_source_stop(sha((self.base / 'state.json').read_bytes()), BOOT,
                                     o.digest(self.old), self.delta_sha, context_reduction=True)

    def finish_stop(self):
        f.SameBootSourceTests.finish_stop(self)

    def reconcile(self):
        return o.reconcile_settled_source(sha((self.base / 'state.json').read_bytes()), BOOT,
            o.digest(self.new), self.delta_sha, same_boot=True, context_reduction=True)

    def test_exact_pair_prepares_reconciles_and_keeps_source_receipts_and_history(self):
        self.save('historical-failure.json', {'status':'HELD','error':'command_timeout'})
        old_receipt = self.base / 'historical-failure.json'
        prior = {n:(self.base/n).read_bytes() for n in ('state.json','manifest.json','selection.json')}
        intent = self.prepare()
        self.assertEqual(intent['status'], 'CONTEXT_REDUCTION_PREPARED')
        for n,raw in prior.items():self.assertEqual((self.base/n).read_bytes(),raw)
        self.assertEqual(intent['files']['source/owner.py'], 'old-source')
        self.finish_stop()
        prior_state = (self.base/'state.json').read_bytes()
        receipt = self.reconcile()
        self.assertEqual(receipt['status'], o.CONTEXT_STATUS)
        self.assertEqual(receipt['transition'], o.CONTEXT_TRANSITION)
        self.assertEqual(receipt['selection']['generation'], 13)
        self.assertEqual((self.base/'state.json').read_bytes(),prior_state)
        archive = o.read(self.base / receipt['archive_name'])
        self.assertEqual(archive['files']['state.json'].encode(),prior_state)
        self.assertEqual(json.loads(archive['files']['state.json'])['primary_failure']['code'],'owner_interrupted')
        self.assertEqual(o.read(old_receipt), {'status':'HELD','error':'command_timeout'})
        actual,old = o.settled_source_for_start(self.new,receipt['selection'],self.state)
        self.assertEqual(old,self.old)
        o.assert_launch_admission(self.new,receipt['selection'],self.state,actual)
        self.physical.assert_called_once_with(self.old,self.state,BOOT,same_boot=True)
        with self.assertRaises(o.OwnerRefusal):self.reconcile()
        (self.base/receipt['consumed_name']).write_text('{}')
        with self.assertRaisesRegex(o.OwnerRefusal,'new_boot_recovery_consumed'):
            o.settled_source_for_start(self.new,receipt['selection'],self.state)

    def test_arbitrary_profile_runtime_gpu_or_increase_is_never_authorized(self):
        changes = [('context',950001),('context',479999),('context',480000.0),('max_output_tokens',32768),
                   ('parallel',2),('runtime_revision','other'),('required_gpu_uuids',['other']),
                   ('no_host',False),('memory',{'limit_bytes':705})]
        for key,value in changes:
            with self.subTest(key=key,value=value):
                new=copy.deepcopy(self.new);new[key]=value
                with self.assertRaises(o.OwnerRefusal):
                    o.reviewed_context_reduction(self.old,new,self.delta_for(new),preparing=True)
        for flag in ('--threads','--threads-batch','--cache-type-k','--cpu-mask','--ctx-size','--kv-unified-per-slot'):
            new=copy.deepcopy(self.new);new['native_argv'][new['native_argv'].index(flag)+1]='other'
            with self.subTest(flag=flag),self.assertRaises(o.OwnerRefusal):
                o.reviewed_context_reduction(self.old,new,self.delta_for(new),preparing=True)
        new=copy.deepcopy(self.new);new['source_sha256'][str(self.base/'source/launch.json')]='a'*64
        with self.assertRaises(o.OwnerRefusal):o.reviewed_context_reduction(self.old,new,self.delta_for(new),preparing=True)
        old=copy.deepcopy(self.old);old['context']=960000
        with self.assertRaises(o.OwnerRefusal):o.reviewed_context_reduction(old,self.new,self.delta,preparing=True)
        new=copy.deepcopy(self.new);new['native_argv'] += ['--ctx-size','480000']
        with self.assertRaises(o.OwnerRefusal):o.reviewed_context_reduction(self.old,new,self.delta_for(new),preparing=True)

    def test_source_only_interface_still_refuses_context_delta(self):
        (self.base/'source/owner.py').write_bytes(b'new-reviewed-source')
        with self.assertRaises(o.OwnerRefusal):o.reviewed_source_amendment(self.old,self.new,self.delta['source_sha256'])

    def test_preparation_active_unknown_hardware_or_drift_refuses_without_intent(self):
        cases=[('proxy-state.json',{**self.proxy,'active_requests':1}),
               ('proxy-state.json',{**self.proxy,'quarantined':True}),
               ('guard.json',{**self.guard,'hardware_latched':True}),
               ('selection.json',{**self.selected,'generation':13}),
               (o.CONTEXT_MANIFEST,{**self.new,'context':950001})]
        for name,value in cases:
            raw=(self.base/name).read_bytes()
            with self.subTest(name=name):
                self.save(name,value)
                with self.assertRaises(o.OwnerRefusal):self.prepare()
                self.assertFalse((self.base/o.transition_stop_name(self.state,True)).exists())
                (self.base/name).write_bytes(raw)
        with patch.object(o,'BOOT',Mock(read_text=lambda:f.f.OLD)),self.assertRaises(o.OwnerRefusal):self.prepare()
        (self.base/'source/owner.py').write_bytes(b'drift')
        with self.assertRaises(o.OwnerRefusal):self.prepare()

    def test_missing_intent_physical_release_or_changed_boot_refuses(self):
        self.finish_stop()
        with self.assertRaises(FileNotFoundError):self.reconcile()
        self.save('manifest.json',self.old);self.save('state.json',self.running)
        (self.base/'source/owner.py').write_bytes(b'old-source')
        self.prepare();self.finish_stop()
        self.physical.side_effect=o.OwnerRefusal('new_boot_owner_present')
        with self.assertRaises(o.OwnerRefusal):self.reconcile()
        self.assertFalse((self.base/o.context_reduction_names(BOOT,o.digest(self.new))[0]).exists())
        self.assertEqual(o.read(self.base/'selection.json'),self.selected)
        self.physical.side_effect=None
        with patch.object(o,'BOOT',Mock(read_text=lambda:f.f.OLD)),self.assertRaises(o.OwnerRefusal):self.reconcile()

    def test_failed_uncertain_or_late_timeout_stays_visible_and_refuses(self):
        self.prepare();self.finish_stop()
        clean=copy.deepcopy(self.state)
        for change in ({'request_hold':True},{'status':'HELD'},
                       {'settlement_failure':{'code':'command_timeout','phase':'SETTLING','operation':'settlement'}},
                       {'primary_failure':{'code':'mandatory_guard_timeout','phase':'RUNNING'}},
                       {'settlement':None}):
            with self.subTest(change=change):
                self.save('state.json',{**clean,**change});raw=(self.base/'state.json').read_bytes()
                with self.assertRaises(o.OwnerRefusal):self.reconcile()
                self.assertEqual((self.base/'state.json').read_bytes(),raw)
                self.assertEqual(o.read(self.base/'selection.json'),self.selected)
        with self.assertRaises(o.OwnerRefusal):
            o.reconcile_settled_source('a'*64,BOOT,o.digest(self.new),self.delta_sha,
                                      same_boot=True,stop_timeout=True,context_reduction=True)

    def test_partial_selection_mutation_cannot_be_replayed(self):
        self.prepare();self.finish_stop()
        with patch.object(o,'write',side_effect=OSError('injected selection write failure')):
            with self.assertRaises(OSError):self.reconcile()
        self.assertEqual(o.read(self.base/'selection.json'),self.selected)
        with self.assertRaises(o.OwnerRefusal):self.reconcile()
        with self.assertRaises(o.OwnerRefusal):o.settled_source_for_start(self.new,self.selected,self.state)

    def test_start_preserves_old_native_and_consumes_once(self):
        # Reuse the real supervise fixture with its injected preflight failure,
        # followed by a single create/start. No actual native action occurs.
        f.SameBootSourceTests.test_start_preflight_failure_preserves_predecessor_then_consumes_and_renames_once(self)

    def install_fixture(self):
        spec=importlib.util.spec_from_file_location('context_install_fixture',
            Path(__file__).resolve().parents[1]/'reports/h036-mimo-480k01/install-candidate.py')
        installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
        self.prepare()
        # The old owner settles before installation; retain the old live files.
        self.finish_stop()
        self.save('manifest.json',self.old)
        (self.base/'source/owner.py').write_bytes(b'old-source')
        candidate=self.base/'candidate.py';candidate.write_bytes(b'new-reviewed-source')
        intent=self.base/o.transition_stop_name(self.state,True)
        pins={'ownerNewSha256':sha(candidate.read_bytes()),'ownerOldSha256':sha(b'old-source'),
            'bootId':BOOT,'priorLaunchId':self.state['launch_id'],
            'manifestOldRawSha256':sha((self.base/'manifest.json').read_bytes()),
            'manifestOldSha256':o.digest(self.old),'manifestNewSha256':o.digest(self.new),
            'selectionOldRawSha256':sha((self.base/'selection.json').read_bytes()),
            'deltaRawSha256':self.delta_sha}
        # Same anchored fixture used by the existing owner tests, plus atomic
        # rename supplied here. Real storage anchoring is unchanged production code.
        owner=self
        def replace(root,source,destination):
            self.assertTrue(owner.held)
            os.replace(owner.base/source,owner.base/destination)
        self.helper.AnchoredRoot.replace=replace
        return installer, pins, candidate, sha((self.base/'state.json').read_bytes()),sha(intent.read_bytes())

    def test_stopped_install_archives_old_bytes_and_reconciles_without_replay(self):
        installer,pins,candidate,state_sha,intent_sha=self.install_fixture()
        result=installer.install(o,pins,candidate,state_sha,intent_sha)
        marker=o.read(self.base/result['attempt'])
        self.assertEqual(marker['files']['source/owner.py'],'old-source')
        self.assertEqual(json.loads(marker['files']['manifest.json']),self.old)
        self.assertEqual(o.read(self.base/'state.json'),self.state)
        self.assertEqual(o.read(self.base/'selection.json'),self.selected)
        self.assertEqual(o.read(self.base/'manifest.json'),self.new)
        with self.assertRaises(o.OwnerRefusal):installer.install(o,pins,candidate,state_sha,intent_sha)
        self.assertEqual(self.reconcile()['status'],o.CONTEXT_STATUS)

    def test_partial_install_is_not_replayed_or_promoted(self):
        installer,pins,candidate,state_sha,intent_sha=self.install_fixture()
        with patch.object(o,'write',side_effect=OSError('injected manifest write failure')):
            with self.assertRaises(OSError):installer.install(o,pins,candidate,state_sha,intent_sha)
        self.assertEqual((self.base/'source/owner.py').read_bytes(),b'new-reviewed-source')
        self.assertEqual(o.read(self.base/'manifest.json'),self.old)
        self.assertEqual(o.read(self.base/'state.json'),self.state)
        self.assertEqual(o.read(self.base/'selection.json'),self.selected)
        with self.assertRaises(o.OwnerRefusal):installer.install(o,pins,candidate,state_sha,intent_sha)
        with self.assertRaises(o.OwnerRefusal):self.reconcile()

    def test_install_changed_state_or_physical_owner_refuses_before_attempt(self):
        installer,pins,candidate,state_sha,intent_sha=self.install_fixture()
        with self.assertRaises(o.OwnerRefusal):installer.install(o,pins,candidate,'a'*64,intent_sha)
        self.physical.side_effect=o.OwnerRefusal('new_boot_owner_present')
        with self.assertRaises(o.OwnerRefusal):installer.install(o,pins,candidate,state_sha,intent_sha)
        self.assertEqual(o.read(self.base/'manifest.json'),self.old)
        self.assertEqual((self.base/'source/owner.py').read_bytes(),b'old-source')
        self.assertFalse(any(self.base.glob('context-reduction-install-*.json')))

    def test_post_receipt_drift_hardware_and_archive_never_admits_start(self):
        self.prepare();self.finish_stop();receipt=self.reconcile()
        for name,value in [('proxy-state.json',{**self.proxy,'active_requests':1}),
                           ('guard.json',{**self.guard,'hardware_latched':True}),
                           (o.transition_stop_name(self.state,True),{})]:
            raw=(self.base/name).read_bytes();(self.base/name).chmod(0o600)
            self.save(name,value)
            try:
                with self.assertRaises(o.OwnerRefusal):o.settled_source_for_start(self.new,receipt['selection'],self.state)
            finally:(self.base/name).write_bytes(raw)
        raw=(self.base/'source/owner.py').read_bytes()
        (self.base/'source/owner.py').write_bytes(b'drift')
        with self.assertRaises(o.OwnerRefusal):o.settled_source_for_start(self.new,receipt['selection'],self.state)
        (self.base/'source/owner.py').write_bytes(raw)
        archive=self.base/receipt['archive_name'];archive.chmod(0o600);archive.write_text('{}')
        with self.assertRaises(o.OwnerRefusal):o.settled_source_for_start(self.new,receipt['selection'],self.state)


    def test_old_and_new_native_configs_are_checked_against_their_own_manifests(self):
        # Restore real exact_container: fixture above stubs OS identity reads.
        spec=importlib.util.spec_from_file_location('exact_context_owner',Path(o.__file__))
        exact=importlib.util.module_from_spec(spec);spec.loader.exec_module(exact)
        exact.BASE=self.base
        for manifest in (self.old,self.new):
            c={'Id':'c'*64,'Name':'/'+manifest['container_name'],'Image':o.IMAGE,
               'State':{'Running':False,'Pid':0,'StartedAt':'original'},
               'Config':{'Entrypoint':['/usr/bin/numactl'],
                   'Cmd':['--interleave=0-7','/opt/llama/llama-server']+manifest['native_argv'],
                   'Labels':{'io.h016.owner':o.OWNER,'io.h016.manifest':o.digest(manifest),'io.h016.launch':'a'*32}},
               'HostConfig':{'Memory':704,'MemorySwap':704,'ReadonlyRootfs':True,'NetworkMode':'host',
                   'RestartPolicy':{'Name':'no'},'Privileged':False,'CgroupParent':o.MEMORY_SLICE,
                   'CpusetCpus':'0-7,16-71','CpusetMems':'0-7','CapDrop':['ALL'],
                   'DeviceRequests':[{'DeviceIDs':[o.GPU]}]},
               'Mounts':[{'Type':'bind','Destination':dest,'Source':src,'RW':False} for dest,src in {
                   '/models':'/data/models-large/mimo-v2.6-pro-rl-ba4eabb7',
                   '/run/secrets/llm-api-key':'/data/services/secrets/llm-api-key',
                   '/usr/bin/numactl':str(self.base/'source/numactl'),
                   '/usr/lib/x86_64-linux-gnu/libnuma.so.1':str(self.base/'source/libnuma.so.1.0.0')}.items()]}
            state={'launch_id':'a'*32,'native':{'container_id':'c'*64,'started_at':'original'}}
            exact.exact_container(c,manifest,state)
            other=self.new if manifest==self.old else self.old
            with self.assertRaises(exact.OwnerRefusal):exact.exact_container(c,other,state)
            argv=o.launch_args(manifest)
            self.assertEqual(argv[argv.index('--threads')+1],'8')
            self.assertEqual(argv[argv.index('--threads-batch')+1],'64')


if __name__=='__main__':unittest.main()
