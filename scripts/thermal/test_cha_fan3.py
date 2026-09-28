"""Focused H025 synthetic fixtures. Run on ai-harness; no real network/fan writes."""
import copy
from datetime import datetime, timezone
import importlib.util
import json
import os
import stat
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('fan', Path(__file__).with_name('cha_fan3.py'))
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
BOOT = '17ac5d50-a6a4-4df1-8f9e-7bfc3db5f125'

def snapshot(duty=75):
    pwm = [{'PWMName': 'other' + str(i), 'PWMNum': i, 'PWMSrc': 0,
            'CurrentPWMdata': [{'Temp': t, 'Duty': 100, 'index': j} for j, t in enumerate((20,45,65,90,100))]} for i in range(8)]
    pwm[3]['PWMName'] = 'Zone4(CHA_FAN3)'
    for p in pwm[3]['CurrentPWMdata'][:4]: p['Duty'] = duty
    return dict(zip(f.PATHS, ({'FanMode':4}, pwm,
        {'PWM4_1':0,'PWM4_2':0,'PWM4_3':0,'FanSourceList':[{'PWM':'PWM4','Name':'CHA_FAN3','Current':0}]},
        {'PWM4_LastSource':0,'PWM4_LastTemp':40})))

def observed(t=65, boot=BOOT):
    return {'temperature_c':t,'node_boot_id':boot,'sampled_at':f.utc(),'telemetry_age_seconds':0}

def dto(now=1000):
    env={'state':'ok','freshness':'fresh','reason':None,'age_ms':0,
         'observed_at':datetime.fromtimestamp(now,timezone.utc).isoformat()}
    return {**env,'schema_version':1,'node_id':'ai-vm','boot_id':BOOT,
      'inventory':{**env,'boot_id':BOOT,'complete':True,'gpu_uuids':[f.GPU],'hardware_faults':{}},
      'gpus':[{**env,'uuid':f.GPU,'temperature_c':65}]}

class MemoryStore:
    def __init__(self): self.values={}
    def read(self,n): return copy.deepcopy(self.values.get(n))
    def write(self,n,v): self.values[n]=copy.deepcopy(v)
    def assert_held(self): pass
class FakeBMC:
    def __init__(self,d=75): self.s=snapshot(d);self.puts=0;self.logins=1;self.reject=False;self.csrf='synthetic'
    def snapshot(self): return copy.deepcopy(self.s)
    def tach(self): return {'value':3000,'units':None,'name':'CHA_FAN3','at':f.utc()}
    def call(self,m,p,data):
        f.validate_payload(data);self.puts+=1
        if not self.reject:
            for point in self.s[f.PATHS[1]][3]['CurrentPWMdata'][:4]: point['Duty']=int(data['CurrentPWMdata'][1])
class FakeNode:
    def __init__(self,t=65): self.t=t
    def read(self):
        if self.t is None: raise f.Fault('telemetry_not_fresh')
        return observed(self.t)

class PolicyTests(unittest.TestCase):
    def test_threshold70_immediate(self):
        self.assertEqual(f.Policy().decide(observed(70),40,0),80)
    def test_hold69_low(self): self.assertEqual(f.Policy().decide(observed(69),40,0),40)
    def test_hold66_high(self): self.assertEqual(f.Policy().decide(observed(66),80,0),80)
    def test_cool65_stable30(self):
        p=f.Policy()
        for t in range(0,30,5): self.assertEqual(p.decide(observed(),80,t),80)
        self.assertEqual(p.decide(observed(),80,30),40)
    def test_warm_resets_cool(self):
        p=f.Policy()
        for t in range(0,25,5): p.decide(observed(),80,t)
        p.decide(observed(66),80,25)
        self.assertEqual(p.decide(observed(),80,30),80)
    def test_stale_raises_low(self): self.assertEqual(f.Policy().decide(None,40,0),80)
    def test_stale_preserves_higher(self): self.assertEqual(f.Policy().decide(None,100,0),100)
    def test_hot_preserves_higher(self): self.assertEqual(f.Policy().decide(observed(75),100,0),100)
    def test_gap_resets_cool(self):
        p=f.Policy();p.decide(observed(),80,0)
        self.assertEqual(p.decide(observed(),80,31),80)
    def test_boot_resets_cool(self):
        p=f.Policy()
        for t in range(0,30,5):p.decide(observed(),80,t)
        self.assertEqual(p.decide(observed(65,'new-boot'),80,30),80)
    def test_restart_cool_reset(self):
        p=f.Policy();p.decide(observed(),80,0)
        self.assertEqual(f.Policy().decide(observed(),80,35),80)

class TelemetryTests(unittest.TestCase):
    def test_valid_absolute_celsius(self): self.assertEqual(f.sample(dto(),1000)['temperature_c'],65)
    def test_stale_age(self):
        d=dto();d['gpus'][0]['age_ms']=15001
        with self.assertRaises(f.Fault): f.sample(d,1000)
    def test_stale_timestamp(self):
        with self.assertRaises(f.Fault): f.sample(dto(),1016)
    def test_future_timestamp(self):
        with self.assertRaises(f.Fault): f.sample(dto(),997)
    def test_missing_uuid(self):
        d=dto();d['gpus'][0]['uuid']='wrong'
        with self.assertRaises(f.Fault):f.sample(d,1000)
    def test_duplicate_uuid(self):
        d=dto();d['gpus']*=2
        with self.assertRaises(f.Fault):f.sample(d,1000)
    def test_inventory_boot_mismatch(self):
        d=dto();d['inventory']['boot_id']='different'
        with self.assertRaises(f.Fault):f.sample(d,1000)
    def test_unknown_row(self):
        d=dto();d['gpus'][0]['state']='unknown'
        with self.assertRaises(f.Fault):f.sample(d,1000)
    def test_invalid_temp(self):
        for t in (None,True,float('nan'),float('inf'),-1,121):
            d=dto();d['gpus'][0]['temperature_c']=t
            with self.assertRaises(f.Fault):f.sample(d,1000)
    def test_duplicate_and_nonfinite_json(self):
        for raw in ('{"a":1,"a":2}','{"a":NaN}'):
            with self.assertRaises(f.Fault):f.decode(raw)

class ChannelTests(unittest.TestCase):
    def test_exact_payload_and_other_zones_unchanged(self):
        s=snapshot();before=copy.deepcopy(s);p=f.payload(s,40)
        f.validate_payload(p);self.assertEqual(s,before);self.assertEqual(p['CurrentPWMdata'][-2:],[100,100])
    def test_wrong_channel(self):
        for key in ('PWMNum','PWMSrc'):
            s=snapshot();s[f.PATHS[1]][3][key]=7
            with self.assertRaises(f.Fault):f.shape(s)
    def test_cpu_source_disabled_required(self):
        for bit in ('PWM4_1','PWM4_2','PWM4_3'):
            s=snapshot();s[f.PATHS[2]][bit]=1
            with self.assertRaises(f.Fault):f.shape(s)
    def test_full_source_mask_required(self):
        s=snapshot();s[f.PATHS[2]]['FanSourceList'][0]['Current']=65536
        with self.assertRaises(f.Fault):f.shape(s)
    def test_mode_knots_and_final100_required(self):
        for mutate in (lambda s:s[f.PATHS[0]].update(FanMode=1),lambda s:s[f.PATHS[1]][3]['CurrentPWMdata'][2].update(Temp=66),lambda s:s[f.PATHS[1]][3]['CurrentPWMdata'][4].update(Duty=80)):
            s=snapshot();mutate(s)
            with self.assertRaises(f.Fault):f.shape(s)
    def test_no_other_payload_or_duties(self):
        for d in (0,75,100):
            with self.assertRaises(f.Fault):f.payload(snapshot(),d)
        p=f.payload(snapshot(),40);p['PWMIndex']=2
        with self.assertRaises(f.Fault):f.validate_payload(p)
    def test_unadvertised_route_before_network(self):
        with self.assertRaises(f.Fault):f.BMC(None).call('PUT','/api/fanctrl/source',{})
    def test_dynamic_temperature_ignored_only(self):
        a=snapshot();b=copy.deepcopy(a);b[f.PATHS[3]]['PWM4_LastTemp']=55
        self.assertEqual(f.invariant(a),f.invariant(b))
        b[f.PATHS[1]][0]['PWMSrc']=3
        self.assertNotEqual(f.invariant(a),f.invariant(b))

class ControllerTests(unittest.TestCase):
    def make(self,d=75):
        b=FakeBMC(d);s=MemoryStore();c=f.Controller(b,s);return c,b,s
    def test_start_high_then40_once_after30(self):
        c,b,s=self.make();c.start();self.assertEqual(b.puts,1)
        for t in range(0,36,5):c.step(FakeNode(),t)
        self.assertEqual(b.puts,2);self.assertEqual(c.proof['readback_duty'],40)
        c.step(FakeNode(),40);self.assertEqual(b.puts,2)
    def test_stale_after_low_raises80(self):
        c,b,s=self.make();c.start()
        for t in range(0,31,5):c.step(FakeNode(),t)
        c.step(FakeNode(None),35)
        self.assertEqual(c.proof['state'],'degraded_high');self.assertEqual(c.proof['readback_duty'],80)
        self.assertIsNone(c.proof['temperature_c'])
    def test_competitor_one_high_and_latch(self):
        c,b,s=self.make();c.start()
        for p in b.s[f.PATHS[1]][3]['CurrentPWMdata'][:4]:p['Duty']=40
        with self.assertRaisesRegex(f.Fault,'competing_writer'):c.step(FakeNode(),0)
        c.terminal('competing_writer_or_overwrite')
        self.assertEqual(b.puts,2);self.assertTrue(s.read('blocked.json'));self.assertEqual(c.proof['state'],'blocked')
        with self.assertRaisesRegex(f.Fault,'operator_review_required'):f.Controller(b,s).start()
        self.assertEqual(b.puts,2)
    def test_source_drift_no_write_even_failsafe(self):
        c,b,s=self.make();c.start();b.s[f.PATHS[2]]['PWM4_1']=1
        c.terminal('user_disabled_sources_changed')
        self.assertEqual(b.puts,1);self.assertIn('safe_high_unavailable',c.proof['errors'][0])
    def test_other_zone_drift_no_write(self):
        c,b,s=self.make();c.start();b.s[f.PATHS[1]][0]['PWMSrc']=1
        c.terminal('bmc_invariant_changed');self.assertEqual(b.puts,1)
    def test_readback_mismatch_latches_bounded(self):
        c,b,s=self.make();b.reject=True
        with self.assertRaisesRegex(f.Fault,'write_uncertain'):c.start()
        c.terminal('bmc_write_readback_mismatch')
        self.assertEqual(b.puts,2);self.assertEqual(c.proof['state'],'blocked')
    def test_start100_retained_no_write(self):
        c,b,s=self.make(100);c.start();self.assertEqual(b.puts,0);self.assertEqual(c.proof['readback_duty'],100)
    def test_high_stop_never_restores75(self):
        c,b,s=self.make(40);self.assertEqual(c.high(),80)
        self.assertEqual(c.high(),80);self.assertEqual(b.puts,1)
    def test_transient_outage_then_recovery(self):
        c,b,s=self.make(40);c.start();c.recovering=False
        for p in b.s[f.PATHS[1]][3]['CurrentPWMdata'][:4]:p['Duty']=40
        c.expected=40
        original=b.snapshot
        with patch.object(b,'snapshot',side_effect=f.Fault('bmc_transport_unavailable')):
            self.assertFalse(c.cycle(FakeNode()))
        self.assertEqual(c.proof['state'],'degraded_unknown')
        self.assertIsNone(s.read('blocked.json'))
        self.assertTrue(c.cycle(FakeNode()))
        self.assertEqual(c.proof['readback_duty'],80)
        self.assertEqual(c.proof['state'],'healthy')
        self.assertIsNone(s.read('blocked.json'))
    def test_transient_can_prove_high_once(self):
        c,b,s=self.make(40);c.start();c.recovering=False
        for p in b.s[f.PATHS[1]][3]['CurrentPWMdata'][:4]:p['Duty']=40
        c.expected=40;original=b.snapshot
        with patch.object(b,'snapshot',side_effect=[f.Fault('bmc_transport_unavailable'),original(),snapshot(80)]):
            self.assertFalse(c.cycle(FakeNode()))
        self.assertEqual(c.proof['state'],'degraded_high')
        self.assertEqual(c.proof['readback_duty'],80)
    def test_invariant_fault_is_not_recoverable(self):
        c,b,s=self.make();c.start();c.recovering=False
        b.s[f.PATHS[2]]['PWM4_1']=1
        with self.assertRaisesRegex(f.Fault,'user_disabled'):c.cycle(FakeNode())
        self.assertFalse(f.transient(f.Fault('user_disabled_sources_changed')))
    def test_ambiguous_put_reconciles_read_only_no_replay(self):
        c,b,s=self.make(40);original=b.call
        def ambiguous(*args):original(*args);raise f.Fault('bmc_transport_unavailable')
        with patch.object(b,'call',side_effect=ambiguous):
            self.assertFalse(c.cycle(FakeNode()))
        self.assertEqual(b.puts,1)
        self.assertEqual(s.read('uncertain-write.json')['desired_duty'],80)
        self.assertEqual(s.read('pending-write.json')['state'],'verified')
        self.assertIsNone(s.read('blocked.json'))
        self.assertTrue(c.cycle(FakeNode()))
        self.assertEqual(b.puts,1)  # Fresh read proves high; NO replay.
    def test_ambiguous_put_absence_retries_reads_only(self):
        c,b,s=self.make(40);original=b.call
        def ambiguous(*args):original(*args);raise f.Fault('bmc_transport_unavailable')
        with patch.object(b,'call',side_effect=ambiguous):
            with self.assertRaisesRegex(f.Fault,'pending_readback'):c.start()
        with patch.object(b,'snapshot',side_effect=f.Fault('bmc_transport_unavailable')):
            for _ in range(3):self.assertFalse(c.cycle(FakeNode()))
        self.assertEqual(b.puts,1)
        self.assertEqual(c.proof['state'],'degraded_unknown')
        self.assertTrue(c.cycle(FakeNode()))
        self.assertEqual(b.puts,1)
    def test_interrupted_low_write_restart_goes_high_after_reconciliation(self):
        c,b,s=self.make(40);c.inspect()
        s.write('pending-write.json',{'state':'prepared','before_duty':80,'desired_duty':40,
                'invariant_sha256':f.digest(c.baseline)})
        c.start();self.assertEqual(c.proof['readback_duty'],80)
        self.assertEqual(b.puts,1)
    def test_ambiguous_put_conflicting_duty_hard_block(self):
        c,b,s=self.make(60);c.inspect()
        s.write('pending-write.json',{'state':'prepared','before_duty':40,'desired_duty':80,
                'invariant_sha256':f.digest(c.baseline)})
        with self.assertRaisesRegex(f.Fault,'ambiguous_write_conflicting'):c.cycle(FakeNode())
        self.assertEqual(b.puts,0)
    def test_stop_during_telemetry_read_cancels_low(self):
        c,b,s=self.make();c.start()
        for t in range(0,30,5):c.step(FakeNode(),t)
        node=FakeNode()
        def read():c.stopping=lambda:True;return observed()
        node.read=read;c.step(node,30)
        self.assertEqual(b.puts,1);self.assertEqual(c.proof['readback_duty'],80)
        self.assertEqual(c.high(),80);self.assertEqual(b.puts,1)
    def test_actuator_guard_after_durable_intent(self):
        c,b,s=self.make();c.start();original=s.write;lost=[False]
        def write(n,v):original(n,v);lost[0]=n=='pending-write.json'
        def held():
            if lost[0]:raise f.Fault('controller_lock_replaced')
        s.write=write;s.assert_held=held
        with self.assertRaises(f.Fault):c.command(b.snapshot(),80,40)
        self.assertEqual(b.puts,1)
    def test_status_retains_acquisition_times(self):
        c,b,s=self.make();c.start();c.readback_at='2000-01-01T00:00:00+00:00'
        tach={'value':3000,'units':None,'at':'2000-01-01T00:00:01+00:00'}
        c.status('healthy',80,observed(),tach=tach)
        self.assertEqual(c.proof['readback_at'],'2000-01-01T00:00:00+00:00')
        self.assertEqual(c.proof['tach_at'],tach['at'])
        c.status('degraded_unknown',None,error='request_timeout')
        self.assertEqual(c.proof['readback_at'],'2000-01-01T00:00:00+00:00')
        self.assertEqual(c.proof['tach_at'],tach['at'])
    def test_local_io_errors_are_not_transport_recovery(self):
        self.assertFalse(f.transient(OSError('synthetic local fsync failure')))
        self.assertFalse(f.transient(f.Fault('protected_file_unavailable')))
        self.assertTrue(f.transient(f.Fault('bmc_transport_unavailable')))
    def test_status_unknown_units_and_compact(self):
        c,b,s=self.make();c.start();c.step(FakeNode(),0)
        self.assertIsNone(c.proof['actual_tach_units']);self.assertLess(len(json.dumps(c.proof)),4096)
        self.assertIn('not_measured_pwm',c.proof['readback_kind'])

class StoreTests(unittest.TestCase):
    def test_singleton_and_atomic_private(self):
        # Private directory under /home/user: protected() intentionally rejects /tmp.
        with tempfile.TemporaryDirectory(dir=str(Path.home())) as p:
            os.chmod(p,0o700);s=f.Store(p)
            try:
                with self.assertRaisesRegex(f.Fault,'already_running'):f.Store(p)
                s.write('status.json',{'ok':1});self.assertEqual(s.read('status.json'),{'ok':1})
                self.assertEqual(os.stat(Path(p)/'status.json').st_mode & 0o777,0o600)
            finally:s.close()
    def test_latch_file_and_parent_are_fsynced(self):
        with tempfile.TemporaryDirectory(dir=str(Path.home())) as p:
            os.chmod(p,0o700);s=f.Store(p);kinds=[];real=os.fsync
            def sync(fd):
                kinds.append(stat.S_ISDIR(os.fstat(fd).st_mode));real(fd)
            try:
                with patch.object(f.os,'fsync',side_effect=sync):s.write('blocked.json',{'high_attempt_reserved':True})
                self.assertEqual(kinds,[False,True])
            finally:s.close()
    def test_lock_replacement(self):
        with tempfile.TemporaryDirectory(dir=str(Path.home())) as p:
            os.chmod(p,0o700);s=f.Store(p)
            try:
                os.unlink(Path(p)/'controller.lock');Path(p,'controller.lock').touch(mode=0o600)
                with self.assertRaisesRegex(f.Fault,'lock_replaced'):s.write('status.json',{})
            finally:s.close()

if __name__=='__main__':unittest.main(verbosity=2)
