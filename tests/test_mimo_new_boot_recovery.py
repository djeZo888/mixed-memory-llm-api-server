"""Offline new-boot recovery fixtures; never contact Docker, systemd or GPUs."""
import contextlib
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('recovery_owner', Path(__file__).resolve().parents[1] / 'scripts/runtime/mimo/owner.py')
o = importlib.util.module_from_spec(spec)
spec.loader.exec_module(o)
OLD = '6535a867-8e27-49d9-8a04-4ecc1adb1e32'
NEW = '17ac5d50-a6a4-4df1-8f9e-7bfc3db5f125'
sha = lambda b: hashlib.sha256(b).hexdigest()

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(o, 'BASE', self.base))
        self.stack.enter_context(patch.object(o, 'BOOT', SimpleNamespace(read_text=lambda: NEW)))
        self.stack.enter_context(patch.object(o, 'protected', side_effect=lambda p: Path(p).read_bytes()))
        (self.base / 'source').mkdir()
        (self.base / 'source/owner.py').write_bytes(b'new-reviewed-source')
        self.old = {'container_name': 'llm-frontier-mimo-production', 'context': 950000,
                    'memory': {'limit_bytes': 704}, 'source_sha256': {str(self.base / 'source/owner.py'): sha(b'old-source')}}
        self.new = copy.deepcopy(self.old)
        self.new['source_sha256'][str(self.base / 'source/owner.py')] = sha(b'new-reviewed-source')
        self.selected = {'schema_version': 1, 'selected_frontier': o.MODEL, 'generation': 12, 'manifest_sha256': o.digest(self.old)}
        self.state = {'schema_version': 2, 'status': 'HELD', 'request_hold': True,
                      'boot_id': OLD, 'manifest_sha256': o.digest(self.old), 'launch_id': 'a' * 32,
                      'selection': self.selected, 'native': {'pid': 605646, 'container_id': 'c' * 64},
                      'supervisor': {'pid': 605245}, 'proxy': {'pid': 777446},
                      'native_cgroup': '/sys/fs/cgroup/llmmimo.slice/docker-' + 'c' * 64 + '.scope'}
        self.proxy = {k: self.state[k] for k in ('boot_id', 'launch_id', 'native')}
        self.files = {'manifest.json': self.new, ('new-boot-prior-manifest-'+NEW+'.json'): self.old,
                      'state.json': self.state, 'proxy-state.json': self.proxy,
                      'guard.json': {'boot_id': OLD, 'manifest_sha256': o.digest(self.old)}, 'selection.json': self.selected}
        for name, v in self.files.items():
            (self.base / name).write_text(json.dumps(v))
        (self.base / ('new-boot-prior-owner-'+NEW+'.py')).write_bytes(b'old-source')
        self.held = False
        owner = self
        class Stream:
            def __init__(self, fd): self.f = os.fdopen(fd, 'wb')
            def __enter__(self): return self
            def __exit__(self, *a): self.f.close()
            def write(self, raw): self.f.write(raw)
            def fsync(self): self.f.flush(); os.fsync(self.f.fileno())
        class Root:
            def __init__(self, *a): pass
            def __enter__(self): self.assert_held(); self.fd = os.open(owner.base, os.O_RDONLY); return self
            def __exit__(self, *a): os.close(self.fd)
            def fileno(self): self.assert_held(); return self.fd
            def assert_held(self): assert owner.held
            def check(self): self.assert_held()
            def open(self, name, flags, mode): return Stream(os.open(owner.base / name, flags, mode))
        @contextlib.contextmanager
        def acquire(**kwargs):
            assert kwargs == {'blocking': False} and not owner.held
            owner.held = True
            try: yield SimpleNamespace(validate=lambda: self.assertTrue(owner.held))
            finally: owner.held = False
        self.helper = SimpleNamespace(acquire_lease=acquire, MountedStorageGuard=lambda _:contextlib.nullcontext(None),
            AnchoredRoot=Root, s=SimpleNamespace(root_payload_guard=lambda: self.assertTrue(self.held)))
        self.stack.enter_context(patch.object(o, 'setup', return_value=self.helper))
        # This fixture owns a synthetic lease; real admission is covered by
        # test_mimo_startup_admission's actual temporary canonical flock.
        self.stack.enter_context(patch.object(o, 'startup_lease',
            side_effect=lambda h, boot: h.acquire_lease(blocking=False)))
        self.stack.enter_context(patch.object(o, 'source_preflight'))
        self.stack.enter_context(patch.object(o, 'storage_paths'))
        def write(h, name, v):
            self.assertTrue(self.held)
            (self.base / name).write_text(json.dumps(v))
        self.stack.enter_context(patch.object(o, 'write', side_effect=write))
        self.absence = self.stack.enter_context(patch.object(o, 'old_boot_absence', return_value={'physical_release': 'REBOOT'}))
        self.state_sha = sha((self.base / 'state.json').read_bytes())

    def reconcile(self):
        return o.reconcile_new_boot(self.state_sha, NEW, o.digest(self.new))

    def test_success_keeps_exact_held_history_and_source_only_selection(self):
        before = {p.name:p.read_bytes() for p in self.base.iterdir() if p.is_file()}
        receipt = self.reconcile()
        self.assertEqual(receipt['prior_request_outcome'], 'FAILED_OR_UNKNOWN')
        for name in ('state.json', 'proxy-state.json', 'guard.json'):
            self.assertEqual((self.base / name).read_bytes(), before[name])
        archive = o.read(self.base / receipt['archive_name'])
        self.assertEqual(archive['files']['state.json'].encode(), before['state.json'])
        self.assertEqual(o.read(self.base / 'selection.json'), {**self.selected, 'manifest_sha256':o.digest(self.new)})
        self.assertEqual((self.base / receipt['archive_name']).stat().st_mode & 0o777, 0o400)
        current = o.read(self.base / 'selection.json')
        actual, old = o.recovery_for_start(self.new, current, self.state)
        o.assert_launch_admission(self.new, current, self.state, actual)
        self.assertEqual(old, self.old)
        self.assertTrue(self.state['request_hold'])
        self.assertEqual(self.state['status'], 'HELD')

    def test_duplicate_command_and_consumption_refuse(self):
        receipt = self.reconcile()
        with self.assertRaises(o.OwnerRefusal): self.reconcile()
        consumed = self.base / o.recovery_names(NEW)[1]
        consumed.write_text('{}')
        with self.assertRaisesRegex(o.OwnerRefusal, 'new_boot_recovery_consumed'):
            o.recovery_for_start(self.new, receipt['selection'], self.state)

    def test_current_profile_or_runtime_change_refused(self):
        for field, value in [('context', 16384), ('memory', {'limit_bytes': 99}), ('container_name', 'other')]:
            new = copy.deepcopy(self.new); new[field] = value
            with self.assertRaisesRegex(o.OwnerRefusal, 'source_only_amendment_required'):
                o.source_only_amendment(self.old, new)

    def test_changed_state_and_unknown_prior_source_refused_before_archive(self):
        (self.base / 'state.json').write_text(json.dumps({**self.state, 'request_hold': False}))
        with self.assertRaises(o.OwnerRefusal): self.reconcile()
        self.assertFalse((self.base / o.recovery_receipt_name(NEW)).exists())
        (self.base / 'state.json').write_text(json.dumps(self.state))
        (self.base / ('new-boot-prior-owner-'+NEW+'.py')).write_bytes(b'unknown')
        with self.assertRaisesRegex(o.OwnerRefusal, 'new_boot_archive_changed'): self.reconcile()

    def test_absence_failure_never_writes_archive_or_selection(self):
        self.absence.side_effect = o.OwnerRefusal('new_boot_owner_present')
        with self.assertRaises(o.OwnerRefusal): self.reconcile()
        self.assertEqual(o.read(self.base / 'selection.json'), self.selected)
        self.assertFalse((self.base / o.recovery_receipt_name(NEW)).exists())

    def test_partial_archive_write_cannot_admit(self):
        with patch.object(o, 'exclusive_recovery_write', side_effect=OSError('fixture')):
            with self.assertRaises(OSError): self.reconcile()
        self.assertEqual(o.read(self.base / 'selection.json'), self.selected)
        with self.assertRaises(FileNotFoundError):
            o.recovery_for_start(self.new, self.selected, self.state)

    def test_archive_tamper_and_state_drift_refuse(self):
        receipt = self.reconcile()
        with self.assertRaises(o.OwnerRefusal):
            o.recovery_for_start(self.new, receipt['selection'], {**self.state, 'launch_id':'b'*32})
        (self.base / receipt['archive_name']).chmod(0o600)
        (self.base / receipt['archive_name']).write_text('{}')
        with self.assertRaisesRegex(o.OwnerRefusal, 'new_boot_archive_changed'):
            o.recovery_for_start(self.new, receipt['selection'], self.state)

    def test_selection_write_failure_keeps_old_state_and_cannot_replay(self):
        with patch.object(o, 'write', side_effect=OSError('fixture')):
            with self.assertRaises(OSError): self.reconcile()
        self.assertEqual(o.read(self.base / 'state.json'), self.state)
        self.assertEqual(o.read(self.base / 'selection.json'), self.selected)
        self.assertTrue((self.base / o.recovery_receipt_name(NEW)).exists())
        with self.assertRaises(o.OwnerRefusal): self.reconcile()
        with self.assertRaises(o.OwnerRefusal):
            o.recovery_for_start(self.new, self.selected, self.state)

    def test_consumption_write_is_exclusive_and_readback_checked(self):
        name = o.recovery_names(NEW)[1]
        with self.helper.acquire_lease(blocking=False):
            o.exclusive_recovery_write(self.helper, None, name, {'launch': 'one'})
            with self.assertRaises(FileExistsError):
                o.exclusive_recovery_write(self.helper, None, name, {'launch': 'two'})
        self.assertEqual(o.read(self.base / name), {'launch': 'one'})

    def test_transient_preflight_failure_does_not_consume_then_retry_owns_once(self):
        self.reconcile()
        original = (self.base / 'state.json').read_bytes()
        consumed = self.base / o.recovery_names(NEW)[1]
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

    def test_recovery_receipt_is_scoped_to_boot(self):
        self.assertNotEqual(o.recovery_receipt_name(OLD), o.recovery_receipt_name(NEW))

    def test_invalid_boot_and_unreconciled_held_admission_refuse(self):
        for boot in (None, '', 'bad', NEW.upper()):
            with self.assertRaises(o.OwnerRefusal): o.recovery_names(boot)
        with self.assertRaises(o.OwnerRefusal):
            o.assert_launch_admission(self.old, self.selected, self.state)

class PhysicalTests(unittest.TestCase):
    def test_systemd_job_requires_explicit_empty_or_zero_property(self):
        # Live systemctl show emits Job= for no queued job; a missing property
        # or an unknown/active representation must not become absence proof.
        cid = 'c' * 64
        old = {'container_name': 'llm-frontier-mimo-production'}
        state = {'schema_version': 2, 'status': 'HELD', 'request_hold': True,
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
                        self.assertEqual(o.old_boot_absence(old, state, NEW)['physical_release'], 'REBOOT')
                    else:
                        with self.assertRaisesRegex(o.OwnerRefusal, 'new_boot_owner_present'):
                            o.old_boot_absence(old, state, NEW)

    def test_same_boot_live_pid_unit_container_cgroup_gpu_listener_refuse(self):
        # Use the actual physical verifier with all operating-system boundaries mocked.
        cid='c'*64
        old={'container_name':'llm-frontier-mimo-production'}
        state={'schema_version':2,'status':'HELD','request_hold':True,'boot_id':OLD,
               'manifest_sha256':o.digest(old),'native':{'pid':10,'container_id':cid},
               'supervisor':{'pid':11},'proxy':{'pid':12},
               'native_cgroup':'/sys/fs/cgroup/llmmimo.slice/docker-'+cid+'.scope'}
        container={'Id':cid,'State':{'Running':False,'Pid':0,'Status':'exited'}}
        unit='MainPID=0\nActiveState=inactive\nSubState=dead\nInvocationID=\nJob=\n'
        cases=['ok','sameboot','pid','unit','running','cgroup','gpu','listener','private_proxy','bootchanged']
        for case in cases:
            with self.subTest(case=case):
                s=copy.deepcopy(state); c=copy.deepcopy(container)
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
                    if case=='ok': self.assertEqual(o.old_boot_absence(old,s,NEW)['physical_release'],'REBOOT')
                    else:
                        with self.assertRaises(o.OwnerRefusal): o.old_boot_absence(old,s,NEW)

if __name__ == '__main__': unittest.main()
