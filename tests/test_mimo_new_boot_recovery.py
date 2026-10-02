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
_REAL_OLD_BOOT_ABSENCE = o.old_boot_absence

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


class HeldNoRequestTests(unittest.TestCase):
    """Exact history and real canonical/storage classes; OS samples are synthetic.

    No status-only positive: archive fsync/exclusivity, registered mount/path
    checks, flock provenance, complete owner joins and actual physical verifier
    execute. UID/system-root/mountinfo are explicit Mac fixture seams.
    """
    def setUp(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
        from common import lifecycle_lease as canonical
        from install import storage_io as io
        self.canonical, self.io = canonical, io
        self.output = Path(os.environ['TMPDIR'])
        # Anchored I/O rejects writable /tmp ancestors: use protected checkout.
        fixture_parent = Path(__file__).resolve().parents[2] / 'output'
        original_tmp = tempfile.TemporaryDirectory
        with patch.object(tempfile, 'TemporaryDirectory', side_effect=lambda: original_tmp(dir=fixture_parent)):
            RecoveryTests.setUp(self)
        self.old.update(owner=o.OWNER, service_id=o.MODEL, qualified=True,
                        context=480000, parallel=1, max_output_tokens=65536, image_id=o.IMAGE,
                        native_argv=[])
        self.new = copy.deepcopy(self.old)
        self.new['source_sha256'][str(self.base / 'source/owner.py')] = sha(b'new-reviewed-source')
        self.selected['manifest_sha256'] = o.digest(self.old)
        cid = 'c' * 64
        self.state.update(status='HELD', request_hold=False, settlement=None, proxy_started=True,
            container_id=cid, manifest_sha256=o.digest(self.old),
            native={'pid':605646, 'pid_start_ticks':'1234', 'container_id':cid,
                    'name':self.old['container_name'], 'image_id':o.IMAGE,
                    'started_at':'2026-09-30T13:25:28.371703005Z'},
            supervisor={'pid':605245, 'unit':o.UNIT, 'invocation_id':'b'*32},
            proxy={'pid':777446, 'pid_start_ticks':'5678', 'parent_pid':605245})
        self.proxy = {'schema_version':2, **{k:self.state[k] for k in ('boot_id','launch_id','native')},
                      **self.state['proxy'], 'active_requests':0, 'quarantined':False}
        self.guard = {'schema_version':2, 'status':'ok', 'hardware_latched':False,
                      'manifest_sha256':o.digest(self.old), 'proxy_disposition':self.proxy,
                      **{k:self.state[k] for k in ('boot_id','selection','supervisor','native','proxy')}}
        self.inputs = {'state.json':self.state, 'proxy-state.json':self.proxy, 'guard.json':self.guard,
                      'selection.json':self.selected, 'new-boot-prior-manifest.json':self.old}
        for n,v in {**self.inputs,'manifest.json':self.new}.items():
            (self.base/o.new_boot_input_name(n,NEW)).write_text(json.dumps(v,indent=1)+'\n')
        self.state_sha = sha((self.base/'state.json').read_bytes())
        self.originals = {n:(self.base/o.new_boot_input_name(n,NEW)).read_bytes()
                          for n in (*self.inputs,'new-boot-prior-owner.py')}
        self.system_root = self.base/'system'; (self.system_root/'etc/local-ai-server').mkdir(parents=True)
        info=self.base.stat();identity={'path':str(self.base),'mount':str(self.base),'uuid':'fixture-storage',
            'fstype':'ext4','device':f'{os.major(info.st_dev)}:{os.minor(info.st_dev)}'}
        snapshot={'schema_version':1,'data':dict(identity),'models':dict(identity),
                  'roots':{'state':str(self.base),'models':str(self.base)}}
        registry=self.system_root/'etc/local-ai-server/storage.json'
        registry.write_text(json.dumps(snapshot));registry.chmod(0o600)
        self.storage=SimpleNamespace(owner=os.getuid(),system_root=self.system_root,
            guard=lambda:copy.deepcopy(snapshot),root_payload_guard=lambda:self.assertTrue(self.held))
        self.mountinfo='1 0 0:1 / / rw - ext4 /dev/root rw\n'+f"2 1 {identity['device']} / {self.base} rw - ext4 /dev/data rw\n"
        mount_init=io.MountedStorageGuard.__init__
        self.stack.enter_context(patch.object(io.MountedStorageGuard,'__init__',
            lambda g,storage:mount_init(g,storage,mountinfo_reader=lambda:self.mountinfo)))
        anchor_init=io.AnchoredRoot.__init__
        self.stack.enter_context(patch.object(io.AnchoredRoot,'__init__',
            lambda root,path,guard:anchor_init(root,path,guard,uid=os.getuid())))
        validate=canonical._validate_borrowed_lease
        self.stack.enter_context(patch.object(canonical,'_validate_borrowed_lease',
            lambda lease:validate(lease,system_root=self.system_root,trusted_uid=os.getuid())))
        @contextlib.contextmanager
        def acquire(**kwargs):
            self.assertEqual(kwargs,{'blocking':False})
            with canonical.acquire_lease(system_root=self.system_root,trusted_uid=os.getuid(),**kwargs) as lease:
                self.held=True
                try:yield lease
                finally:self.held=False
        self.helper.acquire_lease=acquire;self.helper.s=self.storage
        self.helper.MountedStorageGuard=io.MountedStorageGuard;self.helper.AnchoredRoot=io.AnchoredRoot
        self.writes=[]
        def write(h,name,value):
            self.assertTrue(self.held)
            if name=='selection.json':
                archive=o.read(self.base/o.recovery_names(NEW)[0])
                self.assertEqual({n:v.encode() for n,v in archive['files'].items()},self.originals)
            self.writes.append(name)
            with io.MountedStorageGuard(self.storage) as guard,io.AnchoredRoot(str(self.base),guard) as root:
                root.atomic_json(name,value)
        self.stack.enter_context(patch.object(o,'write',side_effect=write))
        self.stack.enter_context(patch.object(o,'storage_paths',side_effect=lambda h,g:g.check_path(str(self.base))))
        self.container={'Id':cid,'Name':'/'+self.old['container_name'],'Image':o.IMAGE,
            'Config':{'Entrypoint':['/usr/bin/numactl'],'Cmd':['--interleave=0-7','/opt/llama/llama-server'],
                'Labels':{'io.h016.owner':o.OWNER,'io.h016.manifest':o.digest(self.old),'io.h016.launch':self.state['launch_id']}},
            'HostConfig':{'Memory':704,'MemorySwap':704,'ReadonlyRootfs':True,'NetworkMode':'host',
                'RestartPolicy':{'Name':'no'},'Privileged':False,'CgroupParent':o.MEMORY_SLICE,
                'CpusetCpus':'0-7,16-71','CpusetMems':'0-7','CapDrop':['ALL'],
                'DeviceRequests':[{'DeviceIDs':[o.GPU]}]},
            'Mounts':[{'Type':'bind','Destination':d,'Source':src,'RW':False} for d,src in [
                ('/models','/data/models-large/mimo-v2.6-pro-rl-ba4eabb7'),
                ('/run/secrets/llm-api-key','/data/services/secrets/llm-api-key'),
                ('/usr/bin/numactl',str(self.base/'source/numactl')),
                ('/usr/lib/x86_64-linux-gnu/libnuma.so.1',str(self.base/'source/libnuma.so.1.0.0'))]],
            'State':{'Running':False,'Pid':0,'Status':'exited','StartedAt':self.state['native']['started_at']}}
        self.physical='ok'
        def run(argv,*args):
            if argv[0]=='systemctl':
                return 'MainPID=0\nActiveState='+('active' if self.physical=='unit' else 'inactive')+'\nSubState=dead\nInvocationID=\nJob=\n'
            if argv[0]=='nvidia-smi':return '123' if self.physical=='gpu' else ''
            if argv[0]=='ss':return 'LISTEN 30012' if self.physical=='listener' else ''
            self.fail(argv)
        self.stack.enter_context(patch.object(o,'run',side_effect=run))
        self.stack.enter_context(patch.object(o,'inspect',side_effect=lambda _:self.container))
        self.stack.enter_context(patch.object(o,'ticks',return_value='99999'))
        actual_exists=Path.exists
        self.stack.enter_context(patch.object(Path,'exists',lambda path:
            self.physical=='proc' if str(path).startswith('/proc/') else actual_exists(path)))
        self.absence.side_effect=lambda *a,**kw:_REAL_OLD_BOOT_ABSENCE(*a,**kw)

    def reconcile(self):return o.reconcile_new_boot(self.state_sha,NEW,o.digest(self.new))

    def assert_history(self):
        for name,raw in self.originals.items():
            if name!='selection.json':self.assertEqual((self.base/o.new_boot_input_name(name,NEW)).read_bytes(),raw)

    def test_joined_held_false_archives_raw_bytes_before_cas_and_admits_future_start(self):
        receipt=self.reconcile();self.assert_history()
        self.assertEqual(receipt['transition'],o.HELD_IDLE_BOOT_TRANSITION)
        self.assertEqual(receipt['prior_request_outcome'],'FAILED_OR_UNKNOWN')
        self.assertEqual(receipt['input_sha256'],{n:sha(b) for n,b in self.originals.items()})
        self.assertEqual(self.writes,['selection.json'])
        for name in (receipt['archive_name'],o.recovery_receipt_name(NEW),'new-boot-selection-'+NEW+'.json'):
            self.assertEqual((self.base/name).stat().st_mode&0o777,0o400)
        result,old=o.recovery_for_start(self.new,receipt['selection'],self.state)
        o.assert_launch_admission(self.new,receipt['selection'],self.state,result)
        self.assertEqual(old,self.old)
        self.assertIs(self.state['request_hold'],False)
        with self.assertRaises(o.OwnerRefusal):o.assert_launch_admission(self.new,receipt['selection'],self.state)

    def test_complete_join_negatives_refuse_without_any_history_mutation(self):
        cases=[('sameboot','state',{'boot_id':NEW}),('wrongstatus','state',{'status':'RUNNING'}),
            ('wrongholdtype','state',{'request_hold':0}),('proxyboot','proxy',{'boot_id':NEW}),
            ('proxyidentity','proxy',{'pid_start_ticks':'999'}),('active','proxy',{'active_requests':1}),
            ('ambiguous','proxy',{'quarantined':True}),('guardstatus','guard',{'status':'failed'}),
            ('guardjoin','guard',{'supervisor':{'pid':1}}),('guardsource','guard',{'manifest_sha256':'f'*64}),
            ('guarddisposition','guard',{'proxy_disposition':{}}),('nativeidentity','state',{'container_id':'d'*64})]
        for name,target,change in cases:
            with self.subTest(case=name):
                values={'state':copy.deepcopy(self.state),'proxy':copy.deepcopy(self.proxy),'guard':copy.deepcopy(self.guard)}
                values[target].update(change)
                if target=='state':
                    # Rejoin boot/native where appropriate: rejection must reach actual physical guards too.
                    values['proxy'].update({k:values['state'][k] for k in ('boot_id','launch_id','native')})
                    values['guard'].update({k:values['state'][k] for k in ('boot_id','supervisor','native','proxy')})
                    values['guard']['proxy_disposition']=values['proxy']
                for key,file in [('state','state.json'),('proxy','proxy-state.json'),('guard','guard.json')]:
                    (self.base/file).write_text(json.dumps(values[key]))
                expected=sha((self.base/'state.json').read_bytes())
                with self.assertRaises(o.OwnerRefusal):o.reconcile_new_boot(expected,NEW,o.digest(self.new))
                self.assertFalse((self.base/o.recovery_names(NEW)[0]).exists());self.assertFalse(self.writes)
        for n,b in self.originals.items(): (self.base/o.new_boot_input_name(n,NEW)).write_bytes(b)

    def test_physical_current_unit_container_proc_gpu_and_listener_refuse(self):
        for case in ('unit','container','proc','gpu','listener','identity'):
            with self.subTest(case=case):
                self.physical=case
                saved=copy.deepcopy(self.container)
                if case=='container':self.container['State'].update(Running=True,Pid=99)
                if case=='identity':self.container['Config']['Labels']['io.h016.launch']='d'*32
                try:
                    with self.assertRaises(o.OwnerRefusal):self.reconcile()
                    self.assert_history();self.assertFalse(self.writes)
                finally:self.container=saved

    def test_current_source_or_prior_owner_hash_mismatch_refuse(self):
        (self.base/'source/owner.py').write_bytes(b'wrong-source')
        with self.assertRaisesRegex(o.OwnerRefusal,'source_only_amendment_required'):self.reconcile()
        (self.base/'source/owner.py').write_bytes(b'new-reviewed-source')
        (self.base/o.new_boot_input_name('new-boot-prior-owner.py',NEW)).write_bytes(b'wrong-prior')
        with self.assertRaisesRegex(o.OwnerRefusal,'new_boot_archive_changed'):self.reconcile()
        self.assertFalse(self.writes)

    def test_missing_canonical_lease_and_registered_storage_capability_refuse(self):
        acquire=self.helper.acquire_lease
        @contextlib.contextmanager
        def fake_acquire(**kw):
            self.held=True
            try:yield SimpleNamespace(validate=lambda:None)
            finally:self.held=False
        self.helper.acquire_lease=fake_acquire
        with self.assertRaises(self.canonical.LeaseError):self.reconcile()
        self.helper.acquire_lease=acquire
        registry=self.system_root/'etc/local-ai-server/storage.json'
        registry.write_text('{}')
        with self.assertRaises(self.io.StorageIOError):self.reconcile()
        self.assertFalse(self.writes)

    def test_selection_byte_race_with_equal_json_refuses_after_archive_before_cas(self):
        original=o.exclusive_recovery_write
        def race(h,g,n,v):
            original(h,g,n,v)
            if n==o.recovery_receipt_name(NEW):
                (self.base/'selection.json').write_bytes(self.originals['selection.json']+b' ')
        with patch.object(o,'exclusive_recovery_write',side_effect=race):
            with self.assertRaises(o.OwnerRefusal):self.reconcile()
        self.assertFalse(self.writes);self.assert_history()
        self.assertFalse((self.base/('new-boot-selection-'+NEW+'.json')).exists())

    def test_archive_corruption_and_original_drift_cannot_admit(self):
        receipt=self.reconcile()
        for n in ('proxy-state.json','guard.json','new-boot-prior-owner.py'):
            path=self.base/o.new_boot_input_name(n,NEW);before=path.read_bytes();path.write_bytes(before+b' ')
            with self.assertRaises(o.OwnerRefusal):o.recovery_for_start(self.new,receipt['selection'],self.state)
            path.write_bytes(before)
        archive=self.base/receipt['archive_name'];archive.chmod(0o600);archive.write_text('{}')
        with self.assertRaises(o.OwnerRefusal):o.recovery_for_start(self.new,receipt['selection'],self.state)

    def test_archive_permissions_and_completion_marker_are_required(self):
        receipt=self.reconcile()
        for name in (receipt['archive_name'],o.recovery_receipt_name(NEW),'new-boot-selection-'+NEW+'.json'):
            path=self.base/name;path.chmod(0o600)
            with self.assertRaisesRegex(o.OwnerRefusal,'new_boot_archive_changed'):
                o.recovery_for_start(self.new,receipt['selection'],self.state)
            path.chmod(0o400)
        marker=self.base/('new-boot-selection-'+NEW+'.json')
        marker.chmod(0o600);value=o.read(marker);value['selection_sha256']='f'*64
        marker.write_text(json.dumps(value));marker.chmod(0o400)
        with self.assertRaisesRegex(o.OwnerRefusal,'new_boot_recovery_invalid'):
            o.recovery_for_start(self.new,receipt['selection'],self.state)

    def test_lookalike_storage_class_and_closed_lease_cannot_replace_capabilities(self):
        with self.helper.acquire_lease(blocking=False) as lease,self.io.MountedStorageGuard(self.storage) as guard:
            original=self.helper.AnchoredRoot
            self.helper.AnchoredRoot=type('AnchoredRoot',(),{})
            with self.assertRaises(o.OwnerRefusal):o.held_recovery_capabilities(self.helper,lease,guard)
            self.helper.AnchoredRoot=original
            o.held_recovery_capabilities(self.helper,lease,guard)
        with self.assertRaises(self.canonical.LeaseError):o.held_recovery_capabilities(self.helper,lease,guard)

    def test_postwrite_guard_failure_has_no_start_capability_or_automatic_rollback(self):
        original=self.storage.root_payload_guard
        def postcheck():
            if self.writes:raise self.io.StorageIOError('synthetic-storage-loss-after-write')
            original()
        self.storage.root_payload_guard=postcheck
        with self.assertRaises(self.io.StorageIOError):self.reconcile()
        self.assert_history();self.assertEqual(self.writes,['selection.json'])
        self.storage.root_payload_guard=original
        with self.assertRaises(FileNotFoundError):o.recovery_for_start(self.new,o.selection(),self.state)

    def test_selection_write_committed_then_failed_has_no_start_capability(self):
        def failed(h,n,v):
            (self.base/n).write_text(json.dumps(v));raise OSError('synthetic-postwrite-failure')
        with patch.object(o,'write',side_effect=failed):
            with self.assertRaises(OSError):self.reconcile()
        self.assert_history()
        with self.assertRaises(FileNotFoundError):o.recovery_for_start(self.new,o.selection(),self.state)
        with self.assertRaises(o.OwnerRefusal):self.reconcile()
        # The ordinary rollback still requires SETTLED; no HELD latch/clear bypass.
        with self.assertRaisesRegex(o.OwnerRefusal,'rollback_requires_exact_settlement'):
            o.rollback_glm(self.helper,self.new,o.selection())

if __name__ == '__main__': unittest.main()
