"""Offline source-successor fixtures; no VM or native model operations."""
import contextlib
import os
from types import SimpleNamespace
from unittest.mock import Mock
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('source_recovery_fixture', Path(__file__).with_name('test_mimo_new_boot_recovery.py'))
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
o, sha, NEW, OLD = f.o, f.sha, f.NEW, f.OLD

class SettledSourceTests(unittest.TestCase):
    def setUp(self):
        f.RecoveryTests.setUp(self)
        self.state.update(status='SETTLED', request_hold=False,
            settlement={'pid_released': True, 'cgroup_empty': True, 'gpu_compute_empty': True},
            primary_failure={'code': 'mandatory_guard_timeout'}, settlement_failure={'code': 'command_timeout'})
        self.proxy.update(active_requests=0, quarantined=False)
        (self.base/'proxy-state.json').write_text(json.dumps(self.proxy))
        self.delta = {str(self.base / 'source/owner.py'): {
            'old': self.old['source_sha256'][str(self.base / 'source/owner.py')],
            'new': self.new['source_sha256'][str(self.base / 'source/owner.py')]}}
        for name, value in [('state.json', self.state), ('source-successor-prior-manifest.json', self.old),
                            ('source-successor-delta.json', self.delta)]:
            (self.base / name).write_text(json.dumps(value))
        (self.base/'source-successor-prior-owner.py').write_bytes(b'old-source')
        self.state_sha = sha((self.base / 'state.json').read_bytes())
        self.delta_sha = sha((self.base / 'source-successor-delta.json').read_bytes())
        self.absence = self.stack.enter_context(patch.object(o, 'settled_source_absence', return_value={'physical_release': 'REBOOT'}))

    def reconcile(self):
        return o.reconcile_settled_source(self.state_sha, NEW, o.digest(self.new), self.delta_sha)

    def test_source_successor_archives_history_and_preserves_selection_generation(self):
        before = {n: (self.base/n).read_bytes() for n in ('state.json','proxy-state.json','guard.json')}
        receipt = self.reconcile()
        self.assertEqual(receipt['status'], 'SETTLED_SOURCE_RECONCILED')
        self.assertEqual(receipt['prior_request_outcome'], 'FAILED_OR_UNKNOWN')
        self.assertEqual(receipt['selection']['generation'], 12)
        archive = o.read(self.base / receipt['archive_name'])
        for n, raw in before.items():
            self.assertEqual((self.base/n).read_bytes(), raw)
            self.assertEqual(archive['files'][n].encode(), raw)
        result, old = o.settled_source_for_start(self.new, receipt['selection'], self.state)
        self.assertEqual(old, self.old)
        o.assert_launch_admission(self.new, receipt['selection'], self.state, result)

    def test_non_source_and_unknown_leaf_or_unreviewed_delta_refuse(self):
        for key, value in [('context', 200000), ('container_name', 'other'), ('memory', {'limit_bytes': 1})]:
            changed = copy.deepcopy(self.new); changed[key] = value
            with self.assertRaises(o.OwnerRefusal): o.reviewed_source_amendment(self.old, changed, self.delta)
        with self.assertRaises(o.OwnerRefusal): o.reviewed_source_amendment(self.old, self.new, {})
        old, new = copy.deepcopy(self.old), copy.deepcopy(self.new)
        old['source_sha256']['/unknown.py'] = 'a'*64
        new['source_sha256']['/unknown.py'] = 'b'*64
        with self.assertRaises(o.OwnerRefusal):
            o.reviewed_source_amendment(old, new, {**self.delta, '/unknown.py': {'old':'a'*64,'new':'b'*64}})

    def test_delta_hash_and_state_drift_refuse_before_archive(self):
        with self.assertRaises(o.OwnerRefusal):
            o.reconcile_settled_source(self.state_sha, NEW, o.digest(self.new), 'a'*64)
        (self.base/'state.json').write_text(json.dumps({**self.state, 'request_hold': True}))
        with self.assertRaises(o.OwnerRefusal): self.reconcile()
        self.assertFalse((self.base / o.settled_source_names(NEW, o.digest(self.new))[0]).exists())

    def test_absence_failure_does_not_change_selection_or_history(self):
        self.absence.side_effect = o.OwnerRefusal('new_boot_owner_present')
        with self.assertRaises(o.OwnerRefusal): self.reconcile()
        self.assertEqual(o.read(self.base/'selection.json'), self.selected)
        self.assertEqual(o.read(self.base/'state.json'), self.state)

    def test_consumed_receipt_tamper_and_owner_drift_refuse(self):
        receipt = self.reconcile()
        with self.assertRaises(o.OwnerRefusal):
            o.settled_source_for_start(self.new, receipt['selection'], {**self.state, 'request_hold': True})
        (self.base/receipt['consumed_name']).write_text('{}')
        with self.assertRaises(o.OwnerRefusal): o.settled_source_for_start(self.new, receipt['selection'], self.state)
        with self.assertRaises(o.OwnerRefusal): self.reconcile()

    def test_prior_owner_bytes_must_match_frozen_manifest(self):
        (self.base/'source-successor-prior-owner.py').write_bytes(b'unknown-owner')
        with self.assertRaisesRegex(o.OwnerRefusal, 'new_boot_archive_changed'): self.reconcile()
        self.assertEqual(o.read(self.base/'selection.json'), self.selected)

    def test_source_prelaunch_failure_then_single_consume_and_rename(self):
        self.reconcile()
        original = (self.base / 'state.json').read_bytes()
        consumed = self.base / o.settled_source_names(NEW, o.digest(self.new))[2]
        class EndFixture(RuntimeError): pass
        old_container = {'Id': 'c'*64, 'State': {'Running': False, 'Pid': 0}}
        new_container = {'Id': 'd'*64, 'State': {'Running': True, 'Pid': 44}}
        def run(argv, *args):
            if argv[:2] == ['systemctl', 'show']: return 'MainPID=0\nActiveState=inactive\n'
            if argv[:2] == ['docker', 'ps']: return 'c'*64
            if argv == ['fixture-create']: return 'd'*64
            return ''
        with contextlib.ExitStack() as stack:
            values = dict(unit_identity=Mock(return_value={'pid':os.getpid(),'invocation_id':'new'}),
                run=Mock(side_effect=run), memory=Mock(return_value={'MemAvailable':1000,'MemTotal':1000}),
                temperature_limit=Mock(return_value=85), sample_guard=Mock(return_value={}),
                memory_policy=Mock(), latch=Mock(side_effect=[o.OwnerRefusal('owned_gpu_latch_unproven'),
                    {'hardware_latched':False}, {'hardware_latched':False}]),
                inspect=Mock(side_effect=lambda name:old_container if name=='c'*64 else new_container),
                exact_container=Mock(side_effect=lambda c,*a:c), create_argv=Mock(return_value=['fixture-create']),
                native_identity=Mock(return_value={'container_id':'d'*64,'pid':44}),
                cgpath=Mock(return_value=Path('/fixture')), read_key=Mock(return_value=b'fixture'),
                native_ready=Mock(side_effect=EndFixture('stop')), record_failure=Mock(), settle_state=Mock())
            for name, value in values.items(): stack.enter_context(patch.object(o,name,value))
            with self.assertRaisesRegex(o.OwnerRefusal,'owned_gpu_latch_unproven'): o.supervise()
            self.assertFalse(consumed.exists())
            self.assertEqual((self.base / 'state.json').read_bytes(), original)
            with self.assertRaises(EndFixture): o.supervise()
            self.assertTrue(consumed.exists())
            successor = o.read(self.base / 'state.json')
            self.assertNotEqual(successor['launch_id'], self.state['launch_id'])
            self.assertEqual(o.read(consumed)['successor_launch_id'], successor['launch_id'])
            values['settle_state'].assert_called_once()
            self.assertEqual([c.args[0][:2] for c in values['run'].call_args_list].count(['docker','rename']),1)

    def test_archive_delta_tamper_refused(self):
        receipt = self.reconcile()
        archive_path = self.base/receipt['archive_name']
        archive_path.chmod(0o600)
        archive = o.read(archive_path)
        archive['files']['source-successor-delta.json'] = '{}'
        archive_path.write_text(json.dumps(archive))
        with self.assertRaisesRegex(o.OwnerRefusal, 'new_boot_archive_changed'):
            o.settled_source_for_start(self.new, receipt['selection'], self.state)

    def test_proxy_active_or_quarantined_refused(self):
        for change in ({'active_requests':1}, {'quarantined':True}, {'quarantined':None}):
            (self.base/'proxy-state.json').write_text(json.dumps({**self.proxy, **change}))
            with self.assertRaises(o.OwnerRefusal): self.reconcile()
            self.assertEqual(o.read(self.base/'selection.json'), self.selected)


class SettledPhysicalTests(unittest.TestCase):
    def test_systemd_job_requires_explicit_empty_or_zero_property(self):
        # Live systemctl show emits Job= for no queued job; a missing property
        # or an unknown/active representation must not become absence proof.
        cid = 'c' * 64
        old = {'container_name': 'llm-frontier-mimo-production'}
        state = {'schema_version': 2, 'status': 'SETTLED', 'request_hold': False, 'settlement': {'pid_released':True,'cgroup_empty':True,'gpu_compute_empty':True},
                 'boot_id': OLD, 'manifest_sha256': o.digest(old),
                 'native': {'pid': 10, 'container_id': cid},
                 'supervisor': {'pid': 11}, 'proxy': {'pid': 12},
                 'native_cgroup': '/sys/fs/cgroup/llmmimo.slice/docker-' + cid + '.scope'}
        container = {'Id': cid, 'State': {'Running': False, 'Pid': 0, 'Status': 'exited'}}
        for job, allowed in [('', True), ('0', True), (None, False), ('312/start', False),
                             ('312', False), ('unknown', False), (' ', False),
                             ('0 garbage', False), (' 0', False)]:
            with self.subTest(job=job):
                unit = 'MainPID=0\nActiveState=inactive\nSubState=dead\nInvocationID=\n'
                if job is not None:
                    unit += 'Job=' + job + '\n'
                with patch.object(o, 'BOOT', SimpleNamespace(read_text=lambda: NEW)), \
                     patch.object(o, 'run', side_effect=lambda argv, *a: unit if argv[0] == 'systemctl' else ''), \
                     patch.object(o, 'inspect', return_value=container), \
                     patch.object(o, 'exact_container', side_effect=lambda c, *a: c), \
                     patch.object(Path, 'exists', return_value=False):
                    if allowed:
                        self.assertEqual(o.settled_source_absence(old, state, NEW)['physical_release'], 'REBOOT')
                    else:
                        with self.assertRaisesRegex(o.OwnerRefusal, 'new_boot_owner_present'):
                            o.settled_source_absence(old, state, NEW)

    def test_same_boot_live_pid_unit_container_cgroup_gpu_listener_refuse(self):
        # Use the actual physical verifier with all operating-system boundaries mocked.
        cid='c'*64
        old={'container_name':'llm-frontier-mimo-production'}
        state={'schema_version':2,'status':'SETTLED','request_hold':False,'settlement':{'pid_released':True,'cgroup_empty':True,'gpu_compute_empty':True},'boot_id':OLD,
               'manifest_sha256':o.digest(old),'native':{'pid':10,'container_id':cid},
               'supervisor':{'pid':11},'proxy':{'pid':12},
               'native_cgroup':'/sys/fs/cgroup/llmmimo.slice/docker-'+cid+'.scope'}
        container={'Id':cid,'State':{'Running':False,'Pid':0,'Status':'exited'}}
        unit='MainPID=0\nActiveState=inactive\nSubState=dead\nInvocationID=\nJob=\n'
        cases=['ok','sameboot','pid','unit','running','cgroup','gpu','listener','private_proxy','bootchanged','held','requestheld','unsettled']
        for case in cases:
            with self.subTest(case=case):
                s=copy.deepcopy(state); c=copy.deepcopy(container)
                if case=='held': s['status']='HELD'
                if case=='requestheld': s['request_hold']=True
                if case=='unsettled': s['settlement']['gpu_compute_empty']=False
                if case=='sameboot': s['boot_id']=NEW
                if case=='running': c['State']['Running']=True;c['State']['Pid']=55
                def run(argv,*args):
                    if argv[0]=='systemctl': return unit.replace('MainPID=0','MainPID=99') if case=='unit' else unit
                    if argv[0]=='nvidia-smi': return '99' if case=='gpu' else ''
                    if argv[0]=='ss': return 'LISTEN 0 99 '+('10.156.100.60' if case=='private_proxy' else '127.0.0.1')+':30012 0.0.0.0:*' if case in ('listener','private_proxy') else ''
                    self.fail(argv)
                def exists(path):
                    return (str(path).startswith('/proc/') and case=='pid') or (str(path).startswith('/sys/') and case=='cgroup')
                with patch.object(o,'BOOT',SimpleNamespace(read_text=lambda:OLD if case=='bootchanged' else NEW)), \
                     patch.object(o,'run',side_effect=run),patch.object(o,'inspect',return_value=c), \
                     patch.object(o,'exact_container',side_effect=lambda c,*a:c), \
                     patch.object(Path,'exists',exists),patch.object(Path,'read_text',return_value='99'):
                    if case=='ok': self.assertEqual(o.settled_source_absence(old,s,NEW)['physical_release'],'REBOOT')
                    else:
                        with self.assertRaises(o.OwnerRefusal): o.settled_source_absence(old,s,NEW)

if __name__ == '__main__': unittest.main()
