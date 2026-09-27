#!/usr/bin/env python3
"""Offline UI session tests, without contacting any network."""
import contextlib
import io
import json
import sys
import unittest
from unittest.mock import patch
import ui_probe

class UITests(unittest.TestCase):
    def exercise(self, login_ok=False, fail_second_pin=False):
        calls=[]
        connections=[]
        secret='offline-private-sentinel'
        token='offline-token-sentinel'
        class Response:
            def __init__(self,method):
                self.method=method
                self.status=200 if login_ok or method!='POST' else 401
            def read(self,n):
                if self.method=='POST':
                    data={'ok':0,'privilege':3,'CSRFToken':token} if login_ok else {'code':1009,'error':'Could not login'}
                else: data={'FanMode':4}
                return json.dumps(data).encode()
            def getheaders(self):
                return [('Set-Cookie','test_owned_cookie='+token)] if login_ok and self.method=='POST' else []
        class Connection:
            def connect(self):
                connections.append(self)
                if fail_second_pin and len(connections)==2:
                    raise ui_probe.probe.PinError()
                self.pinned=True
            def request(self,method,path,body=None,headers=None):
                assert self.pinned
                self.method=method
                calls.append((method,path))
                assert (method,path) in [('POST','/api/session'),('DELETE','/api/session')] or method=='GET' and path in ui_probe.PATHS
                if method=='POST': assert 'X-Requested-With' in headers
            def getresponse(self): return Response(self.method)
            def close(self): pass
        output=io.StringIO()
        with patch.object(sys,'argv',['ui_probe.py','--run']), patch.object(ui_probe.probe,'PinnedConnection',Connection), patch.object(ui_probe.probe,'credential',return_value={'username':'sova','password':secret}), patch.object(ui_probe.time,'time',return_value=ui_probe.probe.DEADLINE-60), patch.object(ui_probe.probe.socket,'create_connection',side_effect=AssertionError('network forbidden')), contextlib.redirect_stdout(output):
            ui_probe.main()
        text=output.getvalue()
        self.assertNotIn(secret,text)
        self.assertNotIn(token,text)
        self.assertNotIn('test_owned_cookie',text)
        return calls,json.loads(text)

    def test_failed_login_has_no_retry_reads_or_logout(self):
        calls,result=self.exercise()
        self.assertEqual(calls,[('POST','/api/session')])
        self.assertEqual(result['receipts'][0]['error_code'],1009)

    def test_only_owned_successful_session_logs_out_after_four_gets(self):
        calls,result=self.exercise(login_ok=True)
        self.assertEqual(calls,[('POST','/api/session')]+[('GET',x) for x in ui_probe.PATHS]+[('DELETE','/api/session')])

    def test_changed_pin_stops_without_logout_retry(self):
        calls,result=self.exercise(login_ok=True,fail_second_pin=True)
        self.assertEqual(calls,[('POST','/api/session')])
        self.assertEqual(result['receipts'][-1],{'stopped':'PinError'})

if __name__=='__main__':
    unittest.main()
