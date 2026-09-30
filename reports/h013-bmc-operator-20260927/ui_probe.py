#!/usr/bin/env python3
"""One in-memory UI login, four discovered fan GETs, logout only that session.

No setter implementation. Run on ai-harness only after reviewing static UI source.
"""
import argparse
from datetime import datetime, timezone
import http.cookies
import json
import time
import urllib.parse
import probe

PATHS = ('/api/fanctrl/mode', '/api/fanctrl/PWM', '/api/fanctrl/source', '/api/fanctrl/last_source')
SAFE = set('FanMode PWMIndex PWMSrc PWMNum PWMName CurrentPWMdata GenericPWMdata Temp Duty PWMCount PWMOrder FanName FanSpeed FanDuty Mode Index Name Source RPM Unit Units'.split())
SAFE.update('PWM%d_%d' % (i,j) for i in range(1,9) for j in range(1,4))
SAFE.update('PWM%d_LastSource' % i for i in range(1,9))

def clean(v):
    if isinstance(v, list):
        return [clean(x) for x in v[:32]]
    if isinstance(v, dict):
        return {k:clean(x) for k,x in v.items() if k in SAFE}
    return v

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run', action='store_true', required=True)
    ap.parse_args()
    cookies = http.cookies.SimpleCookie()
    csrf = None
    owned = False
    changed_pin = False
    requests = 0
    receipts = []

    def call(method, path):
        nonlocal csrf, requests
        if time.time() >= probe.DEADLINE or requests >= 6:
            raise ValueError('bounds')
        if (method,path) not in [('POST','/api/session'),('DELETE','/api/session')] and not (method == 'GET' and path in PATHS):
            raise ValueError('method_path')
        if method == 'POST' and requests != 0:
            raise ValueError('login_retry_refused')
        if method == 'DELETE' and not owned:
            raise ValueError('not_owned')
        c = probe.PinnedConnection()
        try:
            c.connect()
            headers = {'Accept':'application/json','Connection':'close','X-Requested-With':'XMLHttpRequest','Origin':'https://' + probe.HOST,'Referer':'https://' + probe.HOST + '/'}
            body = None
            if method == 'POST':
                secret = probe.credential()
                body = urllib.parse.urlencode({'username':secret['username'],'password':secret['password']})
                headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
            else:
                if cookies:
                    headers['Cookie'] = '; '.join(k+'='+v.value for k,v in cookies.items())
                if csrf:
                    headers['X-CSRFTOKEN'] = csrf
            requests += 1
            c.request(method,path,body=body,headers=headers)
            r = c.getresponse()
            raw = r.read(262145)
            if len(raw)>262144:
                raise ValueError('response_size')
            for name,value in r.getheaders():
                if name.lower() == 'set-cookie':
                    cookies.load(value)
            data = json.loads(raw)
            receipt = {'method':method,'path':path,'status':r.status,'pin_verified':True}
            if method == 'POST':
                receipt['response_keys'] = sorted(data)
                receipt['login_result'] = {k:data[k] for k in ('ok','privilege','privilege_id','role','role_id','passwordStatus') if k in data}
                csrf = data.get('CSRFToken')
                if r.status != 200:
                    receipt['error_code'] = data.get('code') if isinstance(data.get('code'), (int, float)) else None
                    error = data.get('error')
                    if isinstance(error, str):
                        for secret_value in (secret['username'], secret['password']):
                            error = error.replace(secret_value, '[redacted]')
                        receipt['error'] = error[:200]
            elif method == 'GET':
                receipt['key_paths'] = probe.keypaths(data)
                receipt['data'] = clean(data)
            receipts.append(receipt)
            return r.status,data
        finally:
            c.close()
    try:
        status, data = call('POST','/api/session')
        owned = status == 200 and bool(csrf) and data.get('ok') == 0
        if not owned:
            raise ValueError('login_not_accepted')
        for path in PATHS:
            call('GET',path)
    except probe.PinError:
        changed_pin = True
        receipts.append({'stopped':'PinError'})
    except Exception as exc:
        receipts.append({'stopped':type(exc).__name__})
    finally:
        if owned and not changed_pin:
            try:
                call('DELETE','/api/session')
            except Exception as exc:
                receipts.append({'logout_stopped':type(exc).__name__})
        print(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'host':probe.HOST,'port':443,
                          'pin':probe.PIN,'pin_checks':probe.PIN_CHECKS,'requests':requests,'receipts':receipts},indent=2))

if __name__ == '__main__':
    main()
