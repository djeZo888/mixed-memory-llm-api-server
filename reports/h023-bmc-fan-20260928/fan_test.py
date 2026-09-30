#!/usr/bin/env python3
"""Reviewed candidate only. Default makes no network calls. No persistent loop."""
import argparse
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import http.cookies
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import time

PROTECTED = Path('/home/user/.config/sova-private')
DIRECTORY = PROTECTED / 'h023-health-fan01-20260928'
sys.path.insert(0, str(PROTECTED / 'h013-bmc-operator-20260927'))
import probe
import ui_probe

HASHES = {'probe.py': 'c07a4fc9958a50d611ad42c4a3eec547ddb9387ddce8d80ab14b31c49028ecd0',
          'ui_probe.py': 'e13f59b3006e1ef0d10594b6f6397874112720d0d79f111211b77bcad04dcfa9'}
PATHS = ui_probe.PATHS
TARGET = 'Zone4(CHA_FAN3)'
THERMAL = '/redfish/v1/Chassis/Self/Thermal'
ACTION = 'ROOT GO H023 CHA_FAN3 first-four-duty 75->100->75; preserve last 100'

class RequestTimeout(Exception):
    pass

def alarm_timeout(signum, frame):
    raise RequestTimeout('bounded_request')

@contextmanager
def limited_alarm(seconds):
    previous_handler = signal.signal(signal.SIGALRM, alarm_timeout)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)[0]
    started = time.monotonic()
    signal.setitimer(signal.ITIMER_REAL, min(seconds, previous_timer) if previous_timer else seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer:
            signal.setitimer(signal.ITIMER_REAL, max(0.000001, previous_timer-(time.monotonic()-started)))

SAFE_REASONS = set('request_or_deadline_bound method_or_ownership put_bound response_size http_status login_not_accepted thermal_http_status insufficient_write_reserve test_configuration_mismatch restore_not_proved_within_bound mode_or_zone_count target_identity target_mapping original_curve_mismatch source_mismatch'.split())

def reason(exc):
    value = str(exc)
    return {'class':type(exc).__name__, 'reason':value if isinstance(exc, ValueError) and value in SAFE_REASONS else 'exception_details_suppressed'}

def sanitized(v):
    safe = ui_probe.SAFE | set('index TCCMax FanSourceList PWM Name Visible Current Option key value'.split())
    if isinstance(v, dict):
        return {k:sanitized(x) for k,x in v.items() if k in safe or re.fullmatch(r'PWM[1-8]_LastTemp',k)}
    if isinstance(v, list):
        return [sanitized(x) for x in v[:64]]
    return v

def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def normalized(v):
    if isinstance(v, dict):
        return {k: normalized(x) for k, x in v.items()
                if not re.fullmatch(r'(?:PWM[1-8]_)?LastTemp', k)}
    if isinstance(v, list):
        return [normalized(x) for x in v]
    return v

def protected_file(path):
    for parent in (PROTECTED, DIRECTORY):
        s = parent.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o700:
            raise ValueError('private_directory_protection')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        s = os.fstat(f.fileno())
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o600:
            raise ValueError('private_file_protection')
        return f.read(65537)

def authorization(go_sha256, deadline):
    if not re.fullmatch('[0-9a-f]{64}', go_sha256 or ''):
        raise ValueError('go_digest_required')
    raw = protected_file(DIRECTORY / 'ROOT-GO.json')
    if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != go_sha256:
        raise ValueError('go_digest_mismatch')
    go = json.loads(raw)
    if go != {'action': ACTION, 'helper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'deadline_epoch': deadline}:
        raise ValueError('go_marker_mismatch')
    for module, name in ((probe, 'probe.py'), (ui_probe, 'ui_probe.py')):
        if hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() != HASHES[name]:
            raise ValueError('reviewed_source_mismatch')
    if time.time() + 120 > deadline:
        raise ValueError('insufficient_deadline_reserve')

def persist_original(snapshot):
    data = json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode()
    path = DIRECTORY / ('original-' + hashlib.sha256(data).hexdigest() + '.json')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    return hashlib.sha256(data).hexdigest()

def validate_original(s):
    mode, pwm, source, last = [s[p] for p in PATHS]
    if not isinstance(mode, dict) or mode.get('FanMode') != 4 or not isinstance(pwm, list) or len(pwm) != 8:
        raise ValueError('mode_or_zone_count')
    if sum(x.get('PWMName') == TARGET for x in pwm) != 1:
        raise ValueError('target_identity')
    t = pwm[3]
    if (t.get('PWMName'), t.get('PWMNum'), t.get('PWMSrc')) != (TARGET, 3, 0):
        raise ValueError('target_mapping')
    if [(p.get('Temp'),p.get('Duty')) for p in t.get('CurrentPWMdata',[])] != [(20,75),(45,75),(65,75),(90,75),(100,100)]:
        raise ValueError('original_curve_mismatch')
    if any(source.get(k) != v for k,v in {'PWM4_1':1,'PWM4_2':0,'PWM4_3':0}.items()) or last.get('PWM4_LastSource') != 0:
        raise ValueError('source_mismatch')
    return t

def payload(snapshot, duty):
    t = snapshot['/api/fanctrl/PWM'][3]
    pairs = t['CurrentPWMdata']
    flat = [value for p in pairs[:4] for value in (str(p['Temp']), str(duty))]
    flat.extend((pairs[4]['Temp'], pairs[4]['Duty']))
    return {'PWMIndex':3, 'PWMSrc':t['PWMSrc'], 'PWMNum':t['PWMNum'], 'CurrentPWMdata':flat}

def expected(snapshot, duty):
    s = copy.deepcopy(snapshot)
    for p in s['/api/fanctrl/PWM'][3]['CurrentPWMdata'][:4]:
        p['Duty'] = duty
    return s

class Client:
    def __init__(self, deadline):
        self.deadline = deadline
        self.cookies = http.cookies.SimpleCookie()
        self.csrf = None
        self.owned = False
        self.requests = 0
        self.puts = 0
        self.attempted = False
        self.restore_attempted = False
        self.first_write_at = None
        self.receipts = []

    def call(self, method, path, data=None, phase=None):
        if time.time() >= self.deadline or self.requests >= 24:
            raise ValueError('request_or_deadline_bound')
        allowed = (method == 'GET' and path in PATHS or
                   (method, path) in [('POST','/api/session'),('DELETE','/api/session'),('PUT','/api/fanctrl/PWM')])
        if not allowed or method == 'POST' and self.requests or method != 'POST' and not self.owned:
            raise ValueError('method_or_ownership')
        if method == 'PUT' and (phase not in ('test','restore') or self.puts >= 2 or
                phase == 'test' and self.attempted or phase == 'restore' and (not self.attempted or self.restore_attempted)):
            raise ValueError('put_bound')
        c = probe.PinnedConnection()
        c.timeout = 2
        alarm = limited_alarm(3)
        alarm.__enter__()
        try:
            c.connect()  # No credential/cookie/CSRF construction before socket pin.
            headers = {'Accept':'application/json','Connection':'close','X-Requested-With':'XMLHttpRequest',
                       'Origin':'https://' + probe.HOST, 'Referer':'https://' + probe.HOST + '/'}
            body = None
            if method == 'POST':
                import urllib.parse
                secret = probe.credential()
                body = urllib.parse.urlencode({'username':secret['username'],'password':secret['password']})
                headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
            else:
                headers['Cookie'] = '; '.join(k + '=' + v.value for k,v in self.cookies.items())
                headers['X-CSRFTOKEN'] = self.csrf
            if method == 'PUT':
                body = json.dumps(data, separators=(',', ':'))
                headers['Content-Type'] = 'application/json'
                self.puts += 1
                if phase == 'test':
                    self.attempted = True
                    self.first_write_at = time.monotonic()
                else:
                    self.restore_attempted = True
            self.requests += 1
            c.request(method, path, body=body, headers=headers)
            r = c.getresponse()
            raw = r.read(262145)
            self.receipts.append({'method':method,'path':path,'status':r.status,'pin_verified':True,'phase':phase})
            if len(raw) > 262144:
                raise ValueError('response_size')
            if r.status != 200:
                raise ValueError('http_status')
            result = json.loads(raw) if raw else {}
            if method == 'POST':
                self.csrf = result.get('CSRFToken')
                for name, value in r.getheaders():
                    if name.lower() == 'set-cookie':
                        self.cookies.load(value)
                self.owned = result.get('ok') == 0 and isinstance(self.csrf, str) and bool(self.csrf)
                if not self.owned:
                    raise ValueError('login_not_accepted')
            return result
        finally:
            alarm.__exit__(None,None,None)
            c.close()

    def snapshot(self):
        return {path:self.call('GET',path) for path in PATHS}

def thermal():
    with limited_alarm(3):
        r = probe.request(THERMAL)
    if r['status'] != 200:
        raise ValueError('thermal_http_status')
    # probe filtered data retains explicit units if supplied, otherwise absent.
    data = r.get('data') or {}
    fan_keys = {'Name','Reading','ReadingUnits','SensorNumber','MemberId','Status'}
    temp_keys = {'Name','ReadingCelsius','SensorNumber','MemberId','Status'}
    return {'status':r['status'], 'fans':[{k:v for k,v in x.items() if k in fan_keys} for x in data.get('Fans',[])],
            'temperatures':[{k:v for k,v in x.items() if k in temp_keys} for x in data.get('Temperatures',[])],
            'units_note':'Missing ReadingUnits remain unknown; no duty inferred.'}

def execute(client, deadline, settle=time.sleep, capture=thermal, save=persist_original):
    result = {'outcome':'NOT_TESTED', 'restore_proved':False, 'thermal':{}, 'errors':[], 'write_count':0}
    original = None
    transaction_alarm = None
    try:
        client.call('POST','/api/session')
        original = client.snapshot()
        validate_original(original)
        result['original_sha256'] = save(original)
        result['original_filtered'] = {p:sanitized(v) for p,v in original.items()}
        result['thermal']['original'] = capture()
        if time.time() + 120 > deadline:
            raise ValueError('insufficient_write_reserve')
        test_payload = payload(original,100)
        transaction_alarm = limited_alarm(25)
        transaction_alarm.__enter__()
        client.call('PUT','/api/fanctrl/PWM',test_payload,'test')
        settle(10)
        test = client.snapshot()
        result['test_sha256'] = digest(test)
        result['test_filtered'] = {p:sanitized(v) for p,v in test.items()}
        if normalized(test) != normalized(expected(original,100)):
            raise ValueError('test_configuration_mismatch')
        result['test_readback_matches'] = True
        result['thermal']['test'] = capture()
        result['outcome'] = 'TEST_CONFIGURATION_PASS'
    except Exception as exc:
        result['errors'].append({'phase':'preflight_or_test', **reason(exc)})
    finally:
        if transaction_alarm is not None:
            transaction_alarm.__exit__(None,None,None)
        if client.attempted:
            try:
                client.call('PUT','/api/fanctrl/PWM',payload(original,75),'restore')
                result['restore_request_elapsed_seconds'] = round(time.monotonic()-client.first_write_at,3)
                settle(10)
                restored = client.snapshot()
                result['restore_sha256'] = digest(restored)
                result['restore_filtered'] = {p:sanitized(v) for p,v in restored.items()}
                result['restore_proved'] = normalized(restored) == normalized(original)
                result['restore_within_60_seconds'] = time.monotonic()-client.first_write_at <= 60
                result['thermal']['restore'] = capture()
                if not result['restore_proved'] or not result['restore_within_60_seconds']:
                    raise ValueError('restore_not_proved_within_bound')
            except Exception as exc:
                result['errors'].append({'phase':'restore',**reason(exc)})
            if not result['restore_proved']:
                result['manual_fallback'] = 'Restore the exact original CHA_FAN3 curve manually: first four duties 75, final 100; preserve all temperature knots, other headers, mode and source.'
        if client.owned:
            try:
                client.call('DELETE','/api/session')
            except Exception as exc:
                result['errors'].append({'phase':'logout',**reason(exc)})
        result['write_count'] = client.puts
        result['receipts'] = client.receipts
        result['pin_checks'] = probe.PIN_CHECKS
        result['observedAt'] = datetime.now(timezone.utc).isoformat()
        result['outcome'] = ('PASS' if client.attempted and result['restore_proved'] and not result['errors'] else
                             'FAILED_OR_INCOMPLETE' if client.attempted else 'NOT_TESTED')
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', action='store_true')
    p.add_argument('--go-sha256')
    p.add_argument('--deadline', type=float)
    args = p.parse_args()
    if not args.run:
        print(json.dumps({'mode':'READ_ONLY_NO_NETWORK','action':ACTION,'requires':'Exact private ROOT-GO.json hash, helper hash, current snapshot, idle window and deadline'}))
        return
    try:
        if args.deadline is None:
            raise ValueError('deadline_required')
        authorization(args.go_sha256,args.deadline)
        probe.DEADLINE = args.deadline
        result = execute(Client(args.deadline),args.deadline)
    except Exception as exc:
        result = {'outcome':'NOT_TESTED','error_class':type(exc).__name__}
    print(json.dumps(result, sort_keys=True))

if __name__ == '__main__':
    main()
