"""ACTIVATE02 retained state shape; all physical/source operations are fixtures."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('context_fixture', Path(__file__).with_name('test_mimo_context_reduction.py'))
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
o, sha, BOOT = f.o, f.sha, f.BOOT
RETAINED = json.loads(Path(__file__).with_name('fixtures').joinpath('mimo-h036-stop-timeout.json').read_text())


class ContextTimeoutTests(unittest.TestCase):
    save = f.ContextReductionTests.save
    delta_for = f.ContextReductionTests.delta_for

    def setUp(self):
        f.ContextReductionTests.setUp(self)
        # Retain complete before/after shape, including the old source-only
        # predecessor receipt, not merely the two failure dictionaries.
        for attr, key in [('state', 'state'), ('running', 'before')]:
            value = copy.deepcopy(RETAINED[key])
            value.update(boot_id=BOOT, manifest_sha256=o.digest(self.old), selection=self.selected)
            setattr(self, attr, value)
        self.proxy = dict(schema_version=2, **self.state['proxy'], active_requests=0, quarantined=False,
                          **{k:self.state[k] for k in ('boot_id','launch_id','native')})
        self.guard.update(**{k:self.state[k] for k in ('boot_id','selection','native','supervisor','proxy')},
                          observed_at=RETAINED['guard_observed_at'])
        for n,v in [('state.json',self.state),('proxy-state.json',self.proxy),('guard.json',self.guard)]:
            self.save(n,v)
        self.original = copy.deepcopy(self.new)
        self.intent_name = o.transition_stop_name(self.state, True)
        files = {n:(self.base/n).read_text() for n in ('manifest.json','selection.json','proxy-state.json',
                 'guard.json','source/owner.py',o.CONTEXT_MANIFEST,o.CONTEXT_DELTA)}
        files['state.json'] = json.dumps(self.running)
        self.save(self.intent_name, {'schema_version':1,'status':'CONTEXT_REDUCTION_PREPARED',
                  'current_boot_id':BOOT,'launch_id':self.state['launch_id'], 'files':files,
                  'prior_state_digest':o.digest(self.running),'prior_manifest_sha256':o.digest(self.old),
                  'reviewed_delta_sha256':self.delta_sha,'hardware_proof':{'hardware_latched':False}})
        self.intent_sha = sha((self.base/self.intent_name).read_bytes())
        self.new['source_sha256'][str(self.base/'source/owner.py')] = sha(b'corrected-owner')
        self.corrected = self.delta_for(self.new)
        self.save(o.CONTEXT_CORRECTED_MANIFEST,self.new)
        self.save(o.CONTEXT_CORRECTED_DELTA,self.corrected)
        self.corrected_sha = sha((self.base/o.CONTEXT_CORRECTED_DELTA).read_bytes())
        self.native.update(Id=self.state['native']['container_id'],
                           State={'Running':False,'Pid':0,'Status':'exited','OOMKilled':False})
        self.physical.return_value.update(container_id=self.state['native']['container_id'],
            native_pid_absent=True,cgroup_empty=True,gpu_compute_empty=True,owner_absent=True)
        self.os_run.reset_mock()

    def args(self):
        return [sha((self.base/'state.json').read_bytes()),BOOT,o.digest(self.old),self.delta_sha,
                self.intent_sha,self.corrected_sha,o.digest(self.new)]

    def prepare(self):
        return o.prepare_source_stop_timeout(*self.args(),context_reduction=True)

    def supplement_sha(self):
        return sha((self.base/o.source_supplement_name(self.state,True)).read_bytes())

    def install(self):
        self.save('manifest.json',self.new)
        (self.base/'source/owner.py').write_bytes(b'corrected-owner')

    def reconcile(self):
        return o.reconcile_settled_source(self.args()[0],BOOT,o.digest(self.new),self.corrected_sha,
            same_boot=True,stop_timeout=True,context_reduction=True,expected_supplement_sha256=self.supplement_sha())

    def snapshot(self):
        return {str(p.relative_to(self.base)):p.read_bytes() for p in self.base.rglob('*') if p.is_file()}

    def test_explicit_continuation_preserves_fault_pair_intent_and_consumption(self):
        before=self.snapshot()
        supplement=self.prepare()
        self.assertEqual(supplement['status'],o.CONTEXT_TIMEOUT_STATUS)
        self.assertEqual(supplement['original_manifest_sha256'],o.digest(self.original))
        for n,raw in before.items():self.assertEqual((self.base/n).read_bytes(),raw)
        with self.assertRaises(FileExistsError):self.prepare()
        self.install()
        # Normal clean stop and source-only interfaces still refuse.
        with self.assertRaises(o.OwnerRefusal):f.ContextReductionTests.reconcile(self)
        with self.assertRaises(o.OwnerRefusal):
            o.reviewed_source_amendment(self.old,self.new,self.corrected['source_sha256'])
        receipt=self.reconcile()
        self.assertEqual(receipt['transition'],o.CONTEXT_TIMEOUT_TRANSITION)
        self.assertEqual(receipt['prior_request_outcome'],o.STOP_TIMEOUT_OUTCOME)
        self.assertEqual(receipt['selection']['generation'],13)
        self.assertEqual(o.settled_source_for_start(self.new,receipt['selection'],self.state)[0],receipt)
        archive=o.read(self.base/receipt['archive_name'])['files']
        for n in ('state.json',self.intent_name,o.CONTEXT_MANIFEST,o.CONTEXT_DELTA):
            self.assertEqual(archive[n].encode(),before[n])
            self.assertEqual((self.base/n).read_bytes(),before[n])
        with self.assertRaises(o.OwnerRefusal):self.reconcile()
        self.os_run.assert_not_called()  # No stop/start/body in continuation.
        self.assertFalse((self.base/receipt['consumed_name']).exists())
        self.save(receipt['consumed_name'],{})
        with self.assertRaisesRegex(o.OwnerRefusal,'new_boot_recovery_consumed'):
            o.settled_source_for_start(self.new,receipt['selection'],self.state)

    def test_wrong_failure_active_unknown_proxy_boot_source_selection_or_release_refuses(self):
        cases=[]
        for field in ('primary_failure','settlement_failure'):
            for key,value in [('code','mandatory_guard_timeout'),('phase','LOADING'),
                              ('operation','native_readiness'),('unknown',True)]:
                changed=copy.deepcopy(self.state);changed[field][key]=value
                cases.append(('state.json',changed))
        cases += [('state.json',{**self.state,**change}) for change in
                  ({'request_hold':True},{'settlement':None},{'receipt_failure':{}},{'status':'HELD'})]
        cases += [('proxy-state.json',{**self.proxy,**change}) for change in
                  ({'active_requests':1},{'active_requests':None},{'active_requests':False},
                   {'quarantined':True},{'quarantined':None},{'pid':1})]
        cases += [('selection.json',{**self.selected,'generation':13}),
                  ('guard.json',{**self.guard,'hardware_latched':True})]
        for name,value in cases:
            raw=(self.base/name).read_bytes();self.save(name,value);before=self.snapshot()
            with self.subTest(name=name,value=value),self.assertRaises(o.OwnerRefusal):self.prepare()
            self.assertEqual(self.snapshot(),before);(self.base/name).write_bytes(raw)
        with patch.object(o,'BOOT',Mock(read_text=lambda:'changed')),self.assertRaises(o.OwnerRefusal):self.prepare()
        with patch.object(o,'source_preflight',side_effect=o.OwnerRefusal('deployed_source_closure_required')), \
             self.assertRaises(o.OwnerRefusal):self.prepare()
        with patch.object(o,'settled_source_absence',side_effect=o.OwnerRefusal('new_boot_owner_present')), \
             self.assertRaises(o.OwnerRefusal):self.prepare()
        with patch.object(o,'latch',side_effect=o.OwnerRefusal('owned_gpu_latch_unproven')),self.assertRaises(o.OwnerRefusal):self.prepare()

    def test_pin_chain_requires_exact_original_and_only_corrective_owner(self):
        for i in range(7):
            args=self.args();args[i]='changed' if i==1 else 'e'*64
            with self.subTest(pin=i),self.assertRaises(o.OwnerRefusal):
                o.prepare_source_stop_timeout(*args,context_reduction=True)
        for key,value in [('context',479999),('max_output_tokens',32768),('parallel',2),
                          ('required_gpu_uuids',['other']),('memory',{}),('runtime_revision','changed')]:
            new=copy.deepcopy(self.new);new[key]=value
            with self.subTest(key=key),self.assertRaises(o.OwnerRefusal):
                o.context_timeout_proposal(self.old,json.dumps(self.original),json.dumps(self.delta),
                                           json.dumps(self.delta_for(new)),new)
        # Even a self-consistent capacity proposal cannot replace prepared bytes.
        raw=(self.base/o.CONTEXT_MANIFEST).read_bytes()
        other=copy.deepcopy(self.original);other['source_sha256'][str(self.base/'source/owner.py')]='e'*64
        self.save(o.CONTEXT_MANIFEST,other)
        with self.assertRaises(o.OwnerRefusal):self.prepare()
        (self.base/o.CONTEXT_MANIFEST).write_bytes(raw)
        (self.base/'source/owner.py').write_bytes(b'drift')
        with self.assertRaises(o.OwnerRefusal):self.prepare()

    def install_fixture(self):
        self.prepare()
        path=Path(__file__).resolve().parents[1]/'reports/h036-mimo-recover03/install-candidate.py'
        spec=importlib.util.spec_from_file_location('timeout_context_installer',path)
        installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
        candidate=self.base/'candidate.py';candidate.write_bytes(b'corrected-owner')
        pins={'ownerNewSha256':sha(candidate.read_bytes()),'ownerOldSha256':sha(b'old-source'),
              'bootId':BOOT,'priorLaunchId':self.state['launch_id'],'manifestOldSha256':o.digest(self.old),
              'manifestNewSha256':o.digest(self.new),'originalDeltaRawSha256':self.delta_sha,
              'deltaRawSha256':self.corrected_sha,'stoppedStateSha256':self.args()[0],
              'intentRawSha256':self.intent_sha}
        for key,name in [('manifestOldRawSha256','manifest.json'),('selectionOldRawSha256','selection.json'),
                         ('originalManifestRawSha256',o.CONTEXT_MANIFEST),('manifestNewRawSha256',o.CONTEXT_CORRECTED_MANIFEST)]:
            pins[key]=sha((self.base/name).read_bytes())
        owner=self
        def replace(root,source,destination):
            owner.assertTrue(owner.held);os.replace(owner.base/source,owner.base/destination)
        self.helper.AnchoredRoot.replace=replace
        return installer,pins,candidate

    def test_stopped_helper_installs_only_amended_pair_and_refuses_partial_replay(self):
        installer,pins,candidate=self.install_fixture()
        args=(o,pins,candidate,self.args()[0],self.intent_sha,self.supplement_sha())
        with patch.object(o,'write',side_effect=OSError('injected manifest failure')):
            with self.assertRaises(OSError):installer.install(*args)
        self.assertEqual(o.read(self.base/'manifest.json'),self.old)
        self.assertEqual(o.read(self.base/'state.json'),self.state)
        self.assertEqual(o.read(self.base/'selection.json'),self.selected)
        self.assertTrue(list(self.base.glob('context-reduction-install-*.json')))
        with self.assertRaises(o.OwnerRefusal):installer.install(*args)
        with self.assertRaises(o.OwnerRefusal):self.reconcile()
        self.os_run.assert_not_called()

    def test_helper_requires_physical_release_then_reconciles_once(self):
        installer,pins,candidate=self.install_fixture()
        args=(o,pins,candidate,self.args()[0],self.intent_sha,self.supplement_sha())
        with patch.object(o,'timeout_physical',side_effect=o.OwnerRefusal('new_boot_owner_present')):
            with self.assertRaises(o.OwnerRefusal):installer.install(*args)
        self.assertFalse(list(self.base.glob('context-reduction-install-*.json')))
        installer.install(*args)
        receipt=self.reconcile()
        self.assertEqual(o.settled_source_for_start(self.new,receipt['selection'],self.state)[0],receipt)
        with self.assertRaises(o.OwnerRefusal):installer.install(*args)

    def test_real_supervise_path_refuses_preflight_then_consumes_and_renames_once(self):
        self.prepare();self.install()
        self.prepare=lambda:None
        self.finish_stop=lambda:None
        supervise=o.supervise;commands=[]
        def observe_supervise():
            run=o.run;start=len(run.call_args_list)
            try:return supervise()
            finally:commands.extend(c.args[0] for c in run.call_args_list[start:])
        with patch.object(o,'timeout_physical',return_value=self.physical.return_value) as physical, \
             patch.object(o,'supervise',side_effect=observe_supervise):
            f.f.SameBootSourceTests.test_start_preflight_failure_preserves_predecessor_then_consumes_and_renames_once(self)
        self.assertEqual(physical.call_count,3)  # Reconcile + both start admissions.
        self.assertIn('successor',physical.call_args.kwargs)
        self.assertEqual(commands.count(['fixture-create']),1)
        self.assertEqual(sum(c[:2]==['docker','start'] for c in commands),1)
        self.assertEqual(sum(c[:2]==['docker','rename'] for c in commands),1)
        self.assertFalse(any(c[:2] in (['docker','stop'],['docker','rm']) for c in commands))

    def test_post_receipt_raw_tamper_and_wrong_transition_cannot_admit(self):
        self.prepare();self.install();receipt=self.reconcile()
        targets=[self.intent_name,o.source_supplement_name(self.state,True),receipt['archive_name'],
                 'state.json','proxy-state.json','guard.json',o.CONTEXT_DELTA,o.CONTEXT_MANIFEST,
                 o.CONTEXT_CORRECTED_DELTA,o.CONTEXT_CORRECTED_MANIFEST]
        for name in targets:
            p=self.base/name;raw=p.read_bytes();p.chmod(0o600);p.write_bytes(raw+b'\n')
            try:
                with self.subTest(name=name),self.assertRaises(o.OwnerRefusal):
                    o.settled_source_for_start(self.new,receipt['selection'],self.state)
            finally:p.write_bytes(raw)
        name=o.context_reduction_names(BOOT,o.digest(self.new))[1]
        (self.base/name).chmod(0o600)
        for transition in (o.STOP_TIMEOUT_TRANSITION,o.CONTEXT_TRANSITION,'NEW_BOOT'):
            self.save(name,{**receipt,'transition':transition})
            with self.subTest(transition=transition),self.assertRaises(o.OwnerRefusal):
                o.settled_source_for_start(self.new,receipt['selection'],self.state)

    def test_exact_private_capture_chain_when_explicitly_supplied(self):
        evidence=os.environ.get('H036_ACTUAL_EVIDENCE_DIR')
        if not evidence:self.skipTest('exact private captures supplied outside Git only')
        captured=Path(evidence)
        actual_base=Path('/data/services/mimo-h016-20260927')
        state=json.loads((captured/'state.json').read_bytes());boot=state['boot_id']
        intent_name=o.transition_stop_name(state,True)
        self.assertEqual(sha((captured/intent_name).read_bytes()),
                         '287e044d6ff2baad3aaf19e9b3f8e2cd14f655210f3805cb2a6b29f8e4aadc53')
        names=('state.json','manifest.json','selection.json','proxy-state.json','guard.json',
               intent_name,o.CONTEXT_DELTA,o.CONTEXT_MANIFEST,'source/owner.py','source/launch.json')
        before={n:(captured/n).read_bytes() for n in names}
        for n,raw in before.items():(self.base/n).write_bytes(raw)
        old=json.loads(before['manifest.json']);original=json.loads(before[o.CONTEXT_MANIFEST])
        proposed=copy.deepcopy(original)
        owner_path=str(actual_base/'source/owner.py')
        candidate=Path(o.__file__).read_bytes()
        proposed['source_sha256'][owner_path]=sha(candidate)
        corrected=json.loads(before[o.CONTEXT_DELTA])
        corrected['manifest_sha256']=o.digest(proposed)
        corrected['source_sha256'][owner_path]['new']=sha(candidate)
        self.save(o.CONTEXT_CORRECTED_MANIFEST,proposed);self.save(o.CONTEXT_CORRECTED_DELTA,corrected)
        real_exists=Path.exists
        def exists(path):
            if path.is_relative_to(actual_base):return real_exists(self.base/path.relative_to(actual_base))
            return real_exists(path)
        def protected(path):return (self.base/Path(path).relative_to(actual_base)).read_bytes()
        physical={**self.physical.return_value,'old_boot_id':boot,'current_boot_id':boot,
                  'container_id':state['native']['container_id']}
        with patch.object(o,'BASE',actual_base),patch.object(o,'BOOT',Mock(read_text=lambda:boot)), \
             patch.object(o,'protected',side_effect=protected),patch.object(Path,'exists',exists), \
             patch.object(o,'settled_source_absence',return_value=physical):
            args=[sha(before['state.json']),boot,o.digest(old),sha(before[o.CONTEXT_DELTA]),
                  sha(before[intent_name]),sha((self.base/o.CONTEXT_CORRECTED_DELTA).read_bytes()),o.digest(proposed)]
            supplement=o.prepare_source_stop_timeout(*args,context_reduction=True)
            for n,raw in before.items():self.assertEqual((self.base/n).read_bytes(),raw)
            self.save('manifest.json',proposed);(self.base/'source/owner.py').write_bytes(candidate)
            receipt=o.reconcile_settled_source(args[0],boot,args[6],args[5],same_boot=True,
                stop_timeout=True,context_reduction=True,
                expected_supplement_sha256=sha((self.base/o.source_supplement_name(state,True)).read_bytes()))
            self.assertEqual(o.settled_source_for_start(proposed,receipt['selection'],state)[0],receipt)
            for n in ('state.json',intent_name,o.CONTEXT_DELTA,o.CONTEXT_MANIFEST):
                self.assertEqual((self.base/n).read_bytes(),before[n])
            self.assertEqual(supplement['intent_sha256'],args[4])
            self.assertEqual(state['primary_failure'],RETAINED['state']['primary_failure'])
            self.assertEqual(state['settlement_failure'],RETAINED['state']['settlement_failure'])


if __name__=='__main__':unittest.main()
