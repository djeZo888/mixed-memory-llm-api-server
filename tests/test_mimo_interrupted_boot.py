"""Offline unclean-boot regressions; OS and launch boundaries cannot run live."""
import contextlib
import copy
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('interrupted_boot_fixture',
                                             Path(__file__).with_name('test_mimo_new_boot_recovery.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)

o, OLD, NEW, sha = fixture.o, fixture.OLD, fixture.NEW, fixture.sha
ABSENCE = o.old_boot_absence


class InterruptedBootTests(unittest.TestCase):
    def setUp(self):
        fixture.RecoveryTests.setUp(self)
        self.old.update(context=480000, parallel=1, image_id=o.IMAGE, native_argv=['--ctx-size', '480000'])
        self.new = copy.deepcopy(self.old)
        self.new['source_sha256'][str(self.base / 'source/owner.py')] = sha(b'new-reviewed-source')
        self.selected.update(generation=13, manifest_sha256=o.digest(self.old))
        self.state.update(status='RUNNING', request_hold=False, proxy_started=True,
                          manifest_sha256=o.digest(self.old), container_id='c'*64,
                          predecessor_recovery={'status': 'HISTORICAL_CONTEXT_TIMEOUT', 'retain': True})
        self.state['native'].update(started_at='old-start', pid_start_ticks='8666481',
                                   image_id=o.IMAGE, name=self.old['container_name'])
        self.state['supervisor'].update(unit=o.UNIT, invocation_id='b'*32)
        self.state['proxy'].update(parent_pid=self.state['supervisor']['pid'], pid_start_ticks='8737077')
        self.proxy = {k: copy.deepcopy(self.state[k]) for k in ('boot_id', 'launch_id', 'native')}
        self.proxy.update(self.state['proxy'], schema_version=2, active_requests=1, quarantined=False)
        self.guard = {k: copy.deepcopy(self.state[k]) for k in
                      ('boot_id', 'manifest_sha256', 'selection', 'supervisor', 'native', 'proxy')}
        self.guard.update(schema_version=2, status='ok', hardware_latched=False, proxy_disposition=self.proxy)
        self.files.update({'manifest.json': self.new, 'new-boot-prior-manifest-'+NEW+'.json': self.old,
                           'state.json': self.state, 'proxy-state.json': self.proxy,
                           'guard.json': self.guard, 'selection.json': self.selected})
        self.save_inputs()
        self.absence.side_effect = ABSENCE
        self.case = None
        self.container = {
            'Id': 'c'*64, 'Name': '/'+self.old['container_name'], 'Image': o.IMAGE,
            'State': {'Running': False, 'Pid': 0, 'Status': 'exited', 'ExitCode': 255,
                      'OOMKilled': False, 'StartedAt': 'old-start'},
            'Config': {'Entrypoint': ['/usr/bin/numactl'],
                       'Cmd': ['--interleave=0-7', '/opt/llama/llama-server']+self.old['native_argv'],
                       'Labels': {'io.h016.owner': o.OWNER, 'io.h016.manifest': o.digest(self.old),
                                  'io.h016.launch': self.state['launch_id']}},
            'HostConfig': {'Memory': 704, 'MemorySwap': 704, 'ReadonlyRootfs': True,
                           'NetworkMode': 'host', 'RestartPolicy': {'Name': 'no'},
                           'Privileged': False, 'CgroupParent': o.MEMORY_SLICE,
                           'CpusetCpus': '0-7,16-71', 'CpusetMems': '0-7', 'CapDrop': ['ALL'],
                           'DeviceRequests': [{'DeviceIDs': [o.GPU]}]},
            'Mounts': [{'Type': 'bind', 'Destination': dest, 'Source': source, 'RW': False}
                       for dest, source in {
                           '/models': '/data/models-large/mimo-v2.6-pro-rl-ba4eabb7',
                           '/run/secrets/llm-api-key': '/data/services/secrets/llm-api-key',
                           '/usr/bin/numactl': str(self.base/'source/numactl'),
                           '/usr/lib/x86_64-linux-gnu/libnuma.so.1': str(self.base/'source/libnuma.so.1.0.0')}.items()]}
        exists = Path.exists
        def physical_exists(path):
            if str(path).startswith('/proc/'):
                return self.case in ('native', 'supervisor', 'proxy') and str(path) == '/proc/'+str(self.state[self.case]['pid'])
            if str(path).startswith('/sys/fs/cgroup/'):
                return self.case == 'cgroup'
            return exists(path)
        self.stack.enter_context(patch.object(Path, 'exists', physical_exists))
        read_text = Path.read_text
        self.stack.enter_context(patch.object(Path, 'read_text', lambda p, *a, **kw:
            '91' if str(p).startswith('/sys/fs/cgroup/') else read_text(p, *a, **kw)))
        self.stack.enter_context(patch.object(o, 'inspect', side_effect=lambda _: self.container))
        self.stack.enter_context(patch.object(o, 'ticks', return_value='fixture-current-pid'))
        self.run = self.stack.enter_context(patch.object(o, 'run', side_effect=self.physical_run))

    def physical_run(self, argv, *args):
        if argv[0] == 'systemctl':
            unit = 'MainPID=0\nActiveState=inactive\nSubState=dead\nInvocationID=\nJob=\n'
            if self.case == 'unit': return unit.replace('MainPID=0', 'MainPID=99')
            if self.case == 'job': return unit.replace('Job=\n', 'Job=23/start\n')
            return unit
        if argv[0] == 'nvidia-smi': return '91' if self.case == 'gpu' else ''
        if argv[0] == 'ss': return 'LISTEN 127.0.0.1:30012' if self.case == 'listener' else ''
        self.fail('Unexpected external boundary: '+repr(argv))

    def save_inputs(self):
        for name, value in self.files.items():
            (self.base/name).write_text(json.dumps(value))
        self.state_sha = sha((self.base/'state.json').read_bytes())

    def reconcile(self):
        return o.reconcile_new_boot(self.state_sha, NEW, o.digest(self.new), interrupted_running=True)

    def test_reboot_archives_original_active_request_without_fabricated_settlement(self):
        before = {p.name:p.read_bytes() for p in self.base.iterdir() if p.is_file()}
        receipt = self.reconcile()
        self.assertEqual(receipt['transition'], o.INTERRUPTED_BOOT_TRANSITION)
        self.assertEqual(receipt['prior_request_outcome'], 'FAILED_OR_UNKNOWN')
        archive = o.read(self.base/receipt['archive_name'])
        for name in ('state.json', 'proxy-state.json', 'guard.json'):
            self.assertEqual((self.base/name).read_bytes(), before[name])
            self.assertEqual(archive['files'][name].encode(), before[name])
        self.assertEqual(json.loads(archive['files']['state.json'])['status'], 'RUNNING')
        self.assertEqual(json.loads(archive['files']['proxy-state.json'])['active_requests'], 1)
        self.assertEqual((self.base/receipt['archive_name']).stat().st_mode & 0o777, 0o400)
        self.assertEqual(o.read(self.base/'selection.json'), {**self.selected, 'manifest_sha256':o.digest(self.new)})
        self.assertEqual(o.supervise(dry_run=True)['status'], 'SOURCE_PREFLIGHT_ONLY')
        self.assertEqual(self.new['context'], 480000)
        self.assertEqual(self.new['native_argv'], self.old['native_argv'])

    def test_explicit_flag_and_current_boot_receipt_are_required(self):
        with self.assertRaises(o.OwnerRefusal):
            o.reconcile_new_boot(self.state_sha, NEW, o.digest(self.new))
        (self.base/'selection.json').write_text(json.dumps({**self.selected, 'manifest_sha256':o.digest(self.new)}))
        with self.assertRaisesRegex(o.OwnerRefusal, 'prior_owner_or_request_unsettled'):
            o.supervise(dry_run=True)
        with patch.object(o, 'BOOT', SimpleNamespace(read_text=lambda:OLD)):
            with self.assertRaisesRegex(o.OwnerRefusal, 'prior_owner_or_request_unsettled'):
                o.supervise(dry_run=True)
        self.assertFalse((self.base/o.recovery_receipt_name(NEW)).exists())

    def test_each_surviving_owner_or_physical_resource_refuses_before_archive(self):
        for self.case in ('native', 'supervisor', 'proxy', 'unit', 'job', 'cgroup', 'gpu', 'listener'):
            with self.subTest(resource=self.case), self.assertRaises(o.OwnerRefusal): self.reconcile()
            self.assertFalse((self.base/o.recovery_names(NEW)[0]).exists())
        self.case = None
        self.container['State'].update(Running=True, Pid=55)
        with self.assertRaises(o.OwnerRefusal): self.reconcile()

    def test_same_boot_and_wrong_current_boot_refuse(self):
        for current in (OLD, '12345678-1234-1234-1234-123456789abc'):
            with self.subTest(boot=current), patch.object(o, 'BOOT', SimpleNamespace(read_text=lambda:current)):
                with self.assertRaises(o.OwnerRefusal): self.reconcile()

    def test_wrong_native_generation_image_gpu_or_launch_refuses(self):
        original = copy.deepcopy(self.container)
        changes = [('Id', 'd'*64), ('Image', 'sha256:'+'e'*64), ('started', 'new-start'),
                   ('gpu', 'GPU-unrelated'), ('launch', 'd'*32), ('oom', True)]
        for field, value in changes:
            self.container = copy.deepcopy(original)
            if field == 'started': self.container['State']['StartedAt'] = value
            elif field == 'oom': self.container['State']['OOMKilled'] = value
            elif field == 'gpu': self.container['HostConfig']['DeviceRequests'][0]['DeviceIDs'] = [value]
            elif field == 'launch': self.container['Config']['Labels']['io.h016.launch'] = value
            else: self.container[field] = value
            with self.subTest(field=field), self.assertRaises(o.OwnerRefusal): self.reconcile()

    def test_source_state_and_proxy_guard_identity_pins_refuse(self):
        original = {name: (self.base/name).read_bytes() for name in ('state.json','proxy-state.json','guard.json')}
        for name, field, value in [('state.json','launch_id','d'*32),
                                   ('proxy-state.json','boot_id',NEW), ('proxy-state.json','launch_id','d'*32),
                                   ('proxy-state.json','active_requests',0), ('proxy-state.json','pid',99),
                                   ('guard.json','native',{}), ('guard.json','selection',{})]:
            changed = json.loads(original[name]); changed[field] = value
            (self.base/name).write_text(json.dumps(changed))
            with self.subTest(name=name, field=field), self.assertRaises(o.OwnerRefusal): self.reconcile()
            (self.base/name).write_bytes(original[name])
        (self.base/'source/owner.py').write_bytes(b'unreviewed')
        with self.assertRaisesRegex(o.OwnerRefusal,'source_only_amendment_required'): self.reconcile()

    def test_internally_mismatched_recorded_native_or_supervisor_refuses(self):
        for field, value in [('container_id','d'*64), ('supervisor',{'pid':605245,'unit':'foreign','invocation_id':'b'*32})]:
            state={**self.state,field:value}
            with self.subTest(field=field), self.assertRaises(o.OwnerRefusal):
                o.interrupted_running_owner(self.old,state,self.proxy,self.guard)

    def test_proxy_drift_during_reconciliation_is_not_archived_or_admitted(self):
        def drift(*args, **kwargs):
            proof = ABSENCE(*args, **kwargs)
            (self.base/'proxy-state.json').write_text(json.dumps({**self.proxy,'active_requests':0}))
            return proof
        self.absence.side_effect = drift
        with self.assertRaises(o.OwnerRefusal): self.reconcile()
        self.assertFalse((self.base/o.recovery_names(NEW)[0]).exists())

    def test_duplicate_reconciliation_and_consumption_refuse(self):
        fixture.RecoveryTests.test_duplicate_command_and_consumption_refuse(self)

    def test_partial_archive_and_selection_interruption_cannot_admit(self):
        fixture.RecoveryTests.test_partial_archive_write_cannot_admit(self)
        fixture.RecoveryTests.test_selection_write_failure_keeps_old_state_and_cannot_replay(self)

    def test_receipt_write_interruption_preserves_archive_and_cannot_replay(self):
        original = o.exclusive_recovery_write
        def fail_receipt(h, guard, name, value):
            if name == o.recovery_receipt_name(NEW): raise InterruptedError('fixture receipt interruption')
            return original(h, guard, name, value)
        with patch.object(o, 'exclusive_recovery_write', side_effect=fail_receipt):
            with self.assertRaises(InterruptedError): self.reconcile()
        self.assertTrue((self.base/o.recovery_names(NEW)[0]).exists())
        with self.assertRaises(FileExistsError): self.reconcile()
        self.assertEqual(o.read(self.base/'state.json'), self.state)

    def test_start_rechecks_receipt_and_original_bytes(self):
        receipt = self.reconcile()
        (self.base/o.recovery_receipt_name(NEW)).chmod(0o600)  # Deliberate administrative tampering.
        for field, value in [('transition',None), ('current_boot_id',OLD), ('prior_state_digest','0'*64),
                             ('manifest_sha256','0'*64), ('prior_request_outcome','SUCCESS')]:
            (self.base/o.recovery_receipt_name(NEW)).write_text(json.dumps({**receipt,field:value}))
            with self.subTest(field=field), self.assertRaises(o.OwnerRefusal): o.supervise(dry_run=True)
        (self.base/o.recovery_receipt_name(NEW)).write_text(json.dumps(receipt))
        for name, value in [('proxy-state.json',{**self.proxy,'active_requests':0}),
                            ('guard.json',{**self.guard,'status':'changed'})]:
            original=(self.base/name).read_bytes()
            (self.base/name).write_text(json.dumps(value))
            with self.subTest(drift=name), self.assertRaisesRegex(o.OwnerRefusal,'new_boot_archive_changed'):
                o.supervise(dry_run=True)
            (self.base/name).write_bytes(original)

    @contextlib.contextmanager
    def launch_boundaries(self):
        class EndFixture(RuntimeError): pass
        successor = {'pid':os.getpid(),'invocation_id':'new'}
        def run(argv, *args):
            if argv[:2] == ['systemctl','show'] and argv[2] == o.UNIT:
                return f'MainPID={os.getpid()}\nActiveState=active\nInvocationID=new\nJob=\n'
            if argv[:2] == ['systemctl','show']: return 'MainPID=0\nActiveState=inactive\n'
            if argv[:2] == ['docker','ps']: return 'c'*64
            if argv == ['fixture-create']: return 'd'*64
            if argv[0] in ('nvidia-smi','ss') or argv[:2] in (['docker','rename'],['docker','start']): return ''
            self.fail('Unexpected launch boundary: '+repr(argv))
        new = {'Id':'d'*64, 'State':{'Running':True, 'Pid':44}}
        exact = o.exact_container
        values = dict(unit_identity=Mock(return_value=successor), run=Mock(side_effect=run),
            memory=Mock(return_value={'MemAvailable':1000,'MemTotal':1000}),
            temperature_limit=Mock(return_value=85), sample_guard=Mock(return_value={}),
            memory_policy=Mock(), latch=Mock(return_value={'hardware_latched':False}),
            inspect=Mock(side_effect=lambda name:self.container if name=='c'*64 else new),
            exact_container=Mock(side_effect=lambda c,*a:exact(c,*a) if c['Id']=='c'*64 else c),
            create_argv=Mock(return_value=['fixture-create']), native_identity=Mock(return_value={'container_id':'d'*64,'pid':44}),
            cgpath=Mock(return_value=Path('/fixture')), read_key=Mock(return_value=b'fixture'),
            native_ready=Mock(side_effect=EndFixture('fixture end before serving')), record_failure=Mock(), settle_state=Mock())
        with contextlib.ExitStack() as stack:
            for name, value in values.items(): stack.enter_context(patch.object(o,name,value))
            yield EndFixture, values

    def test_explicit_admission_owns_once_and_keeps_interrupted_request_unknown(self):
        receipt = self.reconcile()
        archive_bytes = (self.base/receipt['archive_name']).read_bytes()
        with self.launch_boundaries() as (end, calls):
            with self.assertRaises(end): o.supervise()
            successor = o.read(self.base/'state.json')
            consumed = o.read(self.base/o.recovery_names(NEW)[1])
            self.assertEqual(consumed['successor_launch_id'],successor['launch_id'])
            self.assertNotEqual(successor['launch_id'], self.state['launch_id'])
            self.assertEqual(successor['predecessor_recovery']['prior_request_outcome'],'FAILED_OR_UNKNOWN')
            self.assertEqual((self.base/receipt['archive_name']).read_bytes(), archive_bytes)
            self.assertEqual(o.read(self.base/'proxy-state.json')['active_requests'], 1)
            self.assertEqual([c.args[0][:2] for c in calls['run'].call_args_list].count(['docker','rename']),1)
            with self.assertRaises(o.OwnerRefusal): o.supervise()

    def test_surviving_resource_at_start_cannot_consume(self):
        self.reconcile()
        self.case='proxy'
        with self.launch_boundaries():
            with self.assertRaises(o.OwnerRefusal): o.supervise()
        self.assertFalse((self.base/o.recovery_names(NEW)[1]).exists())
        self.assertEqual(o.read(self.base/'state.json'), self.state)

    def test_interrupted_consumption_cannot_replay_or_rename_predecessor(self):
        self.reconcile()
        with self.launch_boundaries() as (_, calls), patch.object(o,'exclusive_recovery_write',side_effect=InterruptedError('fixture consumption interruption')):
            with self.assertRaises(InterruptedError): o.supervise()
            self.assertNotEqual(o.read(self.base/'state.json')['launch_id'],self.state['launch_id'])
            self.assertFalse(any(c.args[0][:2] == ['docker','rename'] for c in calls['run'].call_args_list))
            with self.assertRaises(o.OwnerRefusal): o.supervise()


if __name__ == '__main__': unittest.main()
