"""Cold two-pin delivery reuses interrupted-boot archives; every OS edge is fake."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('cold_interrupted_fixture',
                                             Path(__file__).with_name('test_mimo_interrupted_boot.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
o, OLD, NEW, sha = fixture.o, fixture.OLD, fixture.NEW, fixture.sha
NODE = '/usr/local/lib/llm-server/node-api/scripts/control/node_observation.py'
DELTA = 'new-boot-source-delta.json'


class ColdSourceTests(fixture.InterruptedBootTests):
    def setUp(self):
        super().setUp()
        self.node = self.base / 'node_observation.py'
        self.node.write_bytes(b'reviewed-ada-observer')
        self.old['source_sha256'][NODE] = sha(b'prior-ada-observer')
        self.new['source_sha256'][NODE] = sha(self.node.read_bytes())
        self.selected['manifest_sha256'] = o.digest(self.old)
        self.state['manifest_sha256'] = o.digest(self.old)
        self.guard.update(manifest_sha256=o.digest(self.old), selection=copy.deepcopy(self.selected))
        self.container['Config']['Labels']['io.h016.manifest'] = o.digest(self.old)
        self.stack.enter_context(patch.object(o, 'protected', side_effect=lambda p:
            self.node.read_bytes() if str(p) == NODE else Path(p).read_bytes()))
        self.delta = {p: {'old': self.old['source_sha256'][p], 'new': self.new['source_sha256'][p]}
                      for p in (str(self.base/'source/owner.py'), NODE)}
        self.delta_path = self.base/('new-boot-source-delta-'+NEW+'.json')
        self.delta_path.write_text(json.dumps(self.delta, indent=2)+'\n')
        self.delta_sha = sha(self.delta_path.read_bytes())
        (self.base/('new-boot-prior-node-observation-'+NEW+'.py')).write_bytes(b'prior-ada-observer')
        self.save_inputs()

    def reconcile(self):
        return o.reconcile_new_boot(self.state_sha, NEW, o.digest(self.new), interrupted_running=True,
                                    expected_delta_sha256=self.delta_sha)

    def test_source_state_and_proxy_guard_identity_pins_refuse(self):
        # The parent's owner-only refusal code is deliberately unchanged.
        self.node.write_bytes(b'unreviewed-node')
        with self.assertRaisesRegex(o.OwnerRefusal, 'source_successor_invalid'): self.reconcile()
        self.assertFalse((self.base/o.recovery_names(NEW)[0]).exists())

    def test_both_pins_archived_before_one_create_and_start_without_intermediate_load(self):
        originals = {name:(self.base/name).read_bytes() for name in ('state.json','proxy-state.json','guard.json')}
        receipt = self.reconcile()
        self.assertFalse(any(c.args[0][0] == 'docker' for c in self.run.call_args_list))
        self.assertEqual(receipt['reviewed_delta_sha256'], self.delta_sha)
        archive = o.read(self.base/receipt['archive_name'])
        self.assertEqual(archive['files'][DELTA].encode(), self.delta_path.read_bytes())
        for name, raw in originals.items():
            self.assertEqual(archive['files'][name].encode(), raw)
            self.assertEqual((self.base/name).read_bytes(), raw)
        self.assertEqual(archive['files']['new-boot-prior-node-observation.py'], 'prior-ada-observer')
        with self.launch_boundaries() as (end, calls):
            with self.assertRaises(end): o.supervise()
            commands = [c.args[0] for c in calls['run'].call_args_list]
            self.assertEqual(commands.count(['fixture-create']), 1)
            self.assertEqual(sum(v[:2] == ['docker','start'] for v in commands), 1)
            self.assertFalse(any(v[:2] in (['docker','stop'],['docker','rm']) for v in commands))
            self.assertEqual(o.read(self.base/'state.json')['selection']['generation'], 13)
            self.assertEqual(o.read(self.base/'proxy-state.json')['active_requests'], 1)
            with self.assertRaises(o.OwnerRefusal): o.supervise()
            self.assertEqual(sum(c.args[0][:2] == ['docker','start'] for c in calls['run'].call_args_list), 1)

    def test_explicit_hash_and_interrupted_flag_required(self):
        with self.assertRaisesRegex(o.OwnerRefusal, 'source_only_amendment_required'):
            o.reconcile_new_boot(self.state_sha, NEW, o.digest(self.new), interrupted_running=True)
        with self.assertRaisesRegex(o.OwnerRefusal, 'new_boot_recovery_invalid'):
            o.reconcile_new_boot(self.state_sha, NEW, o.digest(self.new), expected_delta_sha256=self.delta_sha)
        for value in ('', 'wrong', '0'*64):
            with self.subTest(value=value), self.assertRaises(o.OwnerRefusal):
                o.reconcile_new_boot(self.state_sha, NEW, o.digest(self.new), interrupted_running=True,
                                     expected_delta_sha256=value)
        self.assertFalse((self.base/o.recovery_names(NEW)[0]).exists())

    def test_exact_old_and_new_source_closure_and_narrow_allowlist(self):
        files = {'new-boot-prior-owner.py':'old-source',
                 'new-boot-prior-node-observation.py':'prior-ada-observer'}
        def check(old, new, delta):
            raw = json.dumps(delta); o.interrupted_source_amendment(old,new,{**files,DELTA:raw},sha(raw.encode()))
        check(self.old,self.new,self.delta)
        for path in (str(self.base/'source/owner.py'), NODE):
            for which in ('old','new'):
                delta=copy.deepcopy(self.delta);delta[path][which]='f'*64
                with self.subTest(path=path,which=which), self.assertRaises(o.OwnerRefusal):
                    check(self.old,self.new,delta)
        for path in ('/usr/local/lib/llm-server/node-api/scripts/control/node.py',
                     '/usr/local/lib/llm-server/control-api/scripts/control/node_observation.py',
                     str(self.base/'source/private_proxy.py')):
            old,new=copy.deepcopy(self.old),copy.deepcopy(self.new)
            old['source_sha256'][path]='1'*64;new['source_sha256'][path]='2'*64
            delta={**self.delta,path:{'old':'1'*64,'new':'2'*64}}
            with self.subTest(extra=path), self.assertRaises(o.OwnerRefusal):check(old,new,delta)
        for drop in (NODE, str(self.base/'source/owner.py')):
            with self.subTest(missing=drop), self.assertRaises(o.OwnerRefusal):
                check(self.old,self.new,{k:v for k,v in self.delta.items() if k!=drop})
        for field,value in [('context',950000),('parallel',2),('image_id','sha256:'+'e'*64),
                             ('required_gpu_uuids',['GPU-other']),('model_revision','other'),
                             ('native_argv',['--ctx-size','950000']),('memory',{'limit_bytes':99})]:
            new=copy.deepcopy(self.new);new[field]=value
            with self.subTest(field=field), self.assertRaises(o.OwnerRefusal):check(self.old,new,self.delta)
        files['new-boot-prior-node-observation.py']='forged-original'
        with self.assertRaisesRegex(o.OwnerRefusal,'new_boot_archive_changed'):check(self.old,self.new,self.delta)

    def test_delta_prior_source_receipt_and_installed_source_drift_cannot_admit(self):
        receipt = self.reconcile()
        names = [self.delta_path, self.node, self.base/'source/owner.py',
                 self.base/('new-boot-prior-node-observation-'+NEW+'.py'),
                 self.base/('new-boot-prior-owner-'+NEW+'.py'),
                 self.base/('new-boot-prior-manifest-'+NEW+'.json')]
        for path in names:
            original=path.read_bytes();path.write_bytes(original+b'\n')
            with self.subTest(path=path.name), self.assertRaises(o.OwnerRefusal):o.supervise(dry_run=True)
            path.write_bytes(original)
        rp=self.base/o.recovery_receipt_name(NEW);rp.chmod(0o600)
        for value in (None,'0'*64):
            rp.write_text(json.dumps({**receipt,'reviewed_delta_sha256':value}))
            with self.subTest(receipt=value),self.assertRaises(o.OwnerRefusal):o.supervise(dry_run=True)
        rp.write_text(json.dumps(receipt))
        self.assertFalse((self.base/o.recovery_names(NEW)[1]).exists())

    def test_archive_tampering_and_later_boot_do_not_admit(self):
        receipt=self.reconcile(); path=self.base/receipt['archive_name']; original=path.read_bytes()
        path.chmod(0o600);path.write_bytes(original+b'\n')
        with self.assertRaisesRegex(o.OwnerRefusal,'new_boot_archive_changed'):o.supervise(dry_run=True)
        path.write_bytes(original)
        with patch.object(o,'BOOT',SimpleNamespace(read_text=lambda: '12345678-1234-1234-1234-123456789abc')):
            with self.assertRaises(o.OwnerRefusal):o.supervise(dry_run=True)
        self.assertFalse((self.base/o.recovery_names(NEW)[1]).exists())

    def test_delta_drift_during_absence_check_prevents_archive(self):
        def drift(*args,**kwargs):
            result=fixture.ABSENCE(*args,**kwargs);self.delta_path.write_bytes(self.delta_path.read_bytes()+b'\n');return result
        self.absence.side_effect=drift
        with self.assertRaises(o.OwnerRefusal):self.reconcile()
        self.assertFalse((self.base/o.recovery_names(NEW)[0]).exists())


if __name__ == '__main__': unittest.main()
