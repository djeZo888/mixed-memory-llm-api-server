#!/usr/bin/env python3
"""Offline fixture tests only; no real socket access."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / 'repo/reports/h013-bmc-operator-20260927'))
spec = importlib.util.spec_from_file_location('fan_test', BASE/'fan_test.py')
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)

def original():
    old = json.loads((BASE/'repo/reports/h015-bmc-admin-20260927/RECEIPT.json').read_text())
    out = {x['path']:x['data'] for x in old['receipts'] if x['method']=='GET'}
    for zone in out['/api/fanctrl/PWM']:
        for field in ('CurrentPWMdata','GenericPWMdata'):
            for n,p in enumerate(zone[field]):
                p['index']=n
                p['TCCMax']=100
    for p in out['/api/fanctrl/PWM'][3]['CurrentPWMdata'][:4]: p['Duty']=75
    out['/api/fanctrl/PWM'][3]['TCCMax']=100
    out['/api/fanctrl/last_source']['PWM4_LastTemp']=30
    return out

class Fake:
    def __init__(self, failure=None):
        self.owned=False; self.attempted=False; self.restore_attempted=False
        self.puts=0; self.first_write_at=None; self.receipts=[]
        self.state=original(); self.failure=failure; self.reads=0; self.writes=[]
    def call(self, method,path,data=None,phase=None):
        if method=='POST': self.owned=True
        if method=='PUT':
            self.puts+=1; self.writes.append(copy.deepcopy(data))
            if phase=='test':
                self.attempted=True; self.first_write_at=time.monotonic()
                self.state=f.expected(self.state,100)
                if self.failure=='ambiguous': raise TimeoutError()
            else:
                self.restore_attempted=True
                if self.failure=='restore': raise f.probe.PinError()
                self.state=original()
    def snapshot(self):
        self.reads+=1
        if self.reads==2 and self.failure=='read': raise ValueError()
        s=copy.deepcopy(self.state)
        if self.reads==2 and self.failure=='other_header': s['/api/fanctrl/PWM'][0]['PWMSrc']=1
        if self.reads==2: s['/api/fanctrl/last_source']['PWM4_LastTemp']=32
        return s

class Tests(unittest.TestCase):
    def setUp(self):
        self.network=patch.object(f.probe.socket,'create_connection',side_effect=AssertionError('offline only'))
        self.network.start()
    def tearDown(self): self.network.stop()
    def run_fake(self, fail=None):
        c=Fake(fail)
        r=f.execute(c,time.time()+200,settle=lambda _:None,capture=lambda:{'raw':1},save=f.digest)
        return c,r
    def test_exact_payload_and_scope(self):
        s=original(); f.validate_original(s)
        p=f.payload(s,100)
        self.assertEqual(p,{'PWMIndex':3,'PWMSrc':0,'PWMNum':3,'CurrentPWMdata':['20','100','45','100','65','100','90','100',100,100]})
        changed=f.expected(s,100)
        self.assertEqual(changed['/api/fanctrl/PWM'][3]['TCCMax'],100)
        self.assertNotEqual(changed,s)
    def test_happy_restore_and_dynamic_temp(self):
        c,r=self.run_fake(); self.assertEqual(r['outcome'],'PASS'); self.assertEqual(c.puts,2)
        self.assertEqual(c.writes[1],f.payload(original(),75))
        self.assertEqual(c.state,original())
        self.assertEqual(r['restore_filtered'],r['original_filtered'])
        for zone in c.state['/api/fanctrl/PWM']:
            for field in ('CurrentPWMdata','GenericPWMdata'):
                self.assertEqual([p['index'] for p in zone[field]],list(range(5)))
    def test_ambiguous_write_restores_once(self):
        c,r=self.run_fake('ambiguous'); self.assertTrue(r['restore_proved']); self.assertEqual(c.puts,2)
    def test_failed_test_read_restores(self):
        c,r=self.run_fake('read'); self.assertTrue(r['restore_proved']); self.assertEqual(c.puts,2)
    def test_other_header_detected(self):
        c,r=self.run_fake('other_header'); self.assertNotEqual(r['outcome'],'PASS'); self.assertTrue(r['restore_proved'])
    def test_restore_pin_failure_no_retry(self):
        c,r=self.run_fake('restore'); self.assertFalse(r['restore_proved']); self.assertEqual(c.puts,2); self.assertIn('manual_fallback',r)
    def test_non75_preflight_rejected(self):
        s=original(); s['/api/fanctrl/PWM'][3]['CurrentPWMdata'][0]['Duty']=74
        with self.assertRaises(ValueError): f.validate_original(s)
    def test_static_source_and_tcc_are_compared(self):
        a=original(); b=copy.deepcopy(a); b['/api/fanctrl/last_source']['PWM4_LastSource']=1
        self.assertNotEqual(f.normalized(a),f.normalized(b))
        b=copy.deepcopy(a); b['/api/fanctrl/PWM'][3]['TCCMax']=90
        self.assertNotEqual(f.normalized(a),f.normalized(b))
    def test_deadline_prevents_write(self):
        c=Fake(); r=f.execute(c,time.time()+20,settle=lambda _:None,capture=lambda:{},save=f.digest)
        self.assertEqual(c.puts,0); self.assertEqual(r['outcome'],'NOT_TESTED')
    def test_client_pin_precedes_credential(self):
        class BadPin:
            def connect(self): raise f.probe.PinError()
            def close(self): pass
        with patch.object(f.probe,'PinnedConnection',BadPin), patch.object(f.probe,'credential',side_effect=AssertionError('credential before pin')):
            with self.assertRaises(f.probe.PinError): f.Client(time.time()+200).call('POST','/api/session')
    def test_attempt_marked_before_send_failure(self):
        c=f.Client(time.time()+200); c.owned=True; c.csrf='offline-placeholder'
        class Conn:
            def connect(self): pass
            def request(self,*args,**kw):
                assert c.attempted and c.puts==1
                raise TimeoutError()
            def close(self): pass
        with patch.object(f.probe,'PinnedConnection',Conn), self.assertRaises(TimeoutError):
            c.call('PUT','/api/fanctrl/PWM',f.payload(original(),100),'test')
        self.assertTrue(c.attempted)
    def test_sanitized_source_and_reason(self):
        value={'FanSourceList':[{'PWM':3,'Name':'CPU','Visible':1,'Current':1,'Option':[{'key':0,'value':'CPU'}]}], 'PWM4_LastTemp':30, 'CSRFToken':'not-output'}
        safe=f.sanitized(value)
        self.assertNotIn('CSRFToken',safe); self.assertIn('PWM4_LastTemp',safe)
        self.assertEqual(safe['FanSourceList'],value['FanSourceList'])
        self.assertEqual(f.reason(ValueError('untrusted-secret'))['reason'],'exception_details_suppressed')

if __name__=='__main__': unittest.main()
