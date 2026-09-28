#!/usr/bin/env python3
"""H025 fixed CHA_FAN3 controller. Import is inert. No inference lifecycle lease."""
from __future__ import annotations
import argparse
import base64
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import http.client
import http.cookies
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import ssl
import stat
import time
import urllib.parse

GPU = 'GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528'
HOST = '10.156.100.40'
PIN = '0f1ee547edbdbca346ea2d884d3271a8f28351d57a16baa911c388198063f7ec'
NODE_HOST, NODE_PORT = '10.156.100.60', 30008
NODE_PATH = '/control/v1/node/status'
PATHS = ('/api/fanctrl/mode', '/api/fanctrl/PWM', '/api/fanctrl/source', '/api/fanctrl/last_source')
THERMAL = '/redfish/v1/Chassis/Self/Thermal'
STATE = Path('/var/lib/sova-cha-fan3')
CREDS = Path('/run/credentials/sova-cha-fan3.service')
BMC_FILE = Path('/home/user/.config/sova-private/bmc.json')
NODE_FILE = Path('/home/user/.config/ai-harness/node-control-key')
HOT, COOL, COOL_SECONDS, POLL, MAX_AGE = 70, 65, 30, 5, 15
BOOT_RE = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z')

class Fault(Exception):
    """Only fixed, nonsecret reason codes belong in this exception."""

@contextmanager
def bounded(seconds=3):
    def timeout(*_):
        raise Fault('request_timeout')
    previous = signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)

def decode(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise Fault('duplicate_json_key')
            out[k] = v
        return out
    def invalid(_):
        raise Fault('nonfinite_json')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def utc():
    return datetime.now(timezone.utc).isoformat()

def protected(path, maximum=8192):
    path = Path(path)
    for parent in reversed(path.parents):
        s = parent.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid not in (0, os.getuid()) or s.st_mode & 0o022:
            raise Fault('unprotected_parent')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as f:
        s = os.fstat(f.fileno())
        if not stat.S_ISREG(s.st_mode) or s.st_uid not in (0, os.getuid()) or s.st_mode & 0o077 or s.st_nlink != 1:
            raise Fault('unprotected_file')
        raw = f.read(maximum + 1)
    if len(raw) > maximum:
        raise Fault('file_size')
    return raw

class BMC:
    def __init__(self, credential_file):
        self.credential_file = credential_file
        self.cookies = http.cookies.SimpleCookie()
        self.csrf = None
        self.last_login = None
        self.puts = 0
        self.logins = 0

    def secret(self):
        s = decode(protected(self.credential_file))
        if s.get('host') not in (HOST, 'https://' + HOST, 'https://' + HOST + '/') or s.get('username') != 'sova':
            raise Fault('bmc_credential_identity')
        return s

    def call(self, method, path, data=None):
        allowed = (method == 'GET' and path in (*PATHS, THERMAL) or
                   (method, path) in (('POST', '/api/session'), ('DELETE', '/api/session'), ('PUT', PATHS[1])))
        if not allowed:
            raise Fault('forbidden_bmc_route')
        if method == 'PUT':
            validate_payload(data)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # Actual DER pin checked before credentials on each socket.
        c = http.client.HTTPSConnection(HOST, 443, timeout=2, context=ctx)
        with bounded():
            try:
                c.connect()
                if hashlib.sha256(c.sock.getpeercert(binary_form=True)).hexdigest() != PIN:
                    raise Fault('bmc_pin_changed')
                h = {'Accept': 'application/json', 'Connection': 'close', 'X-Requested-With': 'XMLHttpRequest',
                     'Origin': 'https://' + HOST, 'Referer': 'https://' + HOST + '/'}
                body = None
                if method == 'POST':
                    s = self.secret()
                    body = urllib.parse.urlencode({'username': s['username'], 'password': s['password']})
                    h['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
                elif path == THERMAL:
                    s = self.secret()
                    h['Authorization'] = 'Basic ' + base64.b64encode((s['username'] + ':' + s['password']).encode()).decode()
                else:
                    if not self.csrf:
                        raise Fault('bmc_session_missing')
                    h['Cookie'] = '; '.join(k + '=' + v.value for k, v in self.cookies.items())
                    h['X-CSRFTOKEN'] = self.csrf
                if method == 'PUT':
                    body = json.dumps(data, separators=(',', ':'))
                    h['Content-Type'] = 'application/json'
                    self.puts += 1  # Attempt, not proof of success.
                c.request(method, path, body=body, headers=h)
                r = c.getresponse()
                raw = r.read(262145)
                if len(raw) > 262144:
                    raise Fault('bmc_response_size')
                if r.status in (401, 403):
                    raise Fault('bmc_session_expired')
                if r.status != 200:
                    raise Fault('bmc_http_status')
                result = decode(raw) if raw else {}
                if method == 'POST':
                    self.csrf = result.get('CSRFToken')
                    for name, value in r.getheaders():
                        if name.lower() == 'set-cookie':
                            self.cookies.load(value)
                    if result.get('ok') != 0 or not isinstance(self.csrf, str) or not self.csrf:
                        self.csrf = None
                        raise Fault('bmc_login_rejected')
                return result
            finally:
                c.close()

    def login(self):
        now = time.monotonic()
        if self.last_login is not None and now - self.last_login < 60:
            raise Fault('bmc_relogin_throttled')
        self.last_login = now
        self.logins += 1
        self.call('POST', '/api/session')

    def snapshot(self):
        try:
            return {p: self.call('GET', p) for p in PATHS}
        except Fault as e:
            if str(e) != 'bmc_session_expired':
                raise
            self.logout()
            self.login()
            return {p: self.call('GET', p) for p in PATHS}

    def tach(self):
        d = self.call('GET', THERMAL)
        rows = [r for r in d.get('Fans', []) if r.get('Name') == 'CHA_FAN3']
        if len(rows) != 1:
            raise Fault('tach_identity_unavailable')
        r = rows[0]
        value = r.get('Reading')
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise Fault('tach_missing_or_stopped')
        return {'value': value, 'units': r.get('ReadingUnits'), 'name': r['Name']}

    def logout(self):
        if self.csrf:
            try:
                self.call('DELETE', '/api/session')
            except Exception:
                pass
            self.csrf = None
            self.cookies.clear()

def shape(s):
    mode, pwm, source, last = [s[p] for p in PATHS]
    if mode.get('FanMode') != 4 or type(pwm) is not list or len(pwm) != 8:
        raise Fault('mode_or_zone_count')
    t = pwm[3]
    if sum(r.get('PWMName') == 'Zone4(CHA_FAN3)' for r in pwm) != 1 or (t.get('PWMName'), t.get('PWMNum'), t.get('PWMSrc')) != ('Zone4(CHA_FAN3)', 3, 0):
        raise Fault('channel_identity')
    listed = [r for r in source.get('FanSourceList', []) if r.get('PWM') == 'PWM4' and r.get('Name') == 'CHA_FAN3']
    if (any(source.get(k) != 0 for k in ('PWM4_1', 'PWM4_2', 'PWM4_3'))
            or len(listed) != 1 or listed[0].get('Current') != 0 or last.get('PWM4_LastSource') != 0):
        raise Fault('user_disabled_sources_changed')
    pts = t.get('CurrentPWMdata', [])
    if [p.get('Temp') for p in pts] != [20, 45, 65, 90, 100] or pts[-1].get('Duty') != 100:
        raise Fault('curve_knots_changed')
    duties = [p.get('Duty') for p in pts[:4]]
    if len(set(duties)) != 1 or type(duties[0]) is not int or not 0 <= duties[0] <= 100:
        raise Fault('nonuniform_duty')
    return duties[0]

def invariant(s):
    s = copy.deepcopy(s)
    shape(s)
    for p in s[PATHS[1]][3]['CurrentPWMdata'][:4]:
        p['Duty'] = None
    def clean(v):
        if isinstance(v, dict):
            return {k: clean(x) for k, x in v.items() if not re.fullmatch(r'(?:PWM[1-8]_)?LastTemp', k)}
        if isinstance(v, list):
            return [clean(x) for x in v]
        return v
    return clean(s)

def payload(s, duty):
    shape(s)
    if type(duty) is not int or duty not in (40, 80):
        raise Fault('duty_not_allowlisted')
    return {'PWMIndex': 3, 'PWMSrc': 0, 'PWMNum': 3,
            'CurrentPWMdata': ['20', str(duty), '45', str(duty), '65', str(duty), '90', str(duty), 100, 100]}

def validate_payload(v):
    if not any(v == {'PWMIndex': 3, 'PWMSrc': 0, 'PWMNum': 3,
                     'CurrentPWMdata': ['20', str(d), '45', str(d), '65', str(d), '90', str(d), 100, 100]} for d in (40, 80)):
        raise Fault('forbidden_bmc_payload')

def sample(dto, now=None):
    now = time.time() if now is None else now
    def fresh(row):
        if row.get('state') != 'ok' or row.get('freshness') != 'fresh' or row.get('reason') is not None:
            raise Fault('telemetry_not_fresh')
        age = row.get('age_ms')
        if type(age) not in (int, float) or not math.isfinite(age) or not 0 <= age <= MAX_AGE * 1000:
            raise Fault('telemetry_age')
        dt = datetime.fromisoformat(row['observed_at'].replace('Z', '+00:00'))
        if dt.tzinfo is None or not -1 <= now - dt.timestamp() <= MAX_AGE:
            raise Fault('telemetry_timestamp')
    if dto.get('schema_version') != 1 or dto.get('node_id') != 'ai-vm' or not BOOT_RE.fullmatch(dto.get('boot_id') or ''):
        raise Fault('telemetry_node_identity')
    fresh(dto)
    inv = dto['inventory']
    fresh(inv)
    if inv.get('boot_id') != dto['boot_id'] or inv.get('complete') is not True or inv.get('gpu_uuids', []).count(GPU) != 1 or GPU in inv.get('hardware_faults', {}):
        raise Fault('telemetry_inventory_identity')
    rows = [r for r in dto['gpus'] if r.get('uuid') == GPU]
    if len(rows) != 1:
        raise Fault('telemetry_gpu_identity')
    row = rows[0]
    fresh(row)
    temp = row.get('temperature_c')  # Native collector absolute Celsius, not T.Limit.
    if type(temp) not in (int, float) or not math.isfinite(temp) or not 0 <= temp <= 120:
        raise Fault('telemetry_temperature')
    return {'node_boot_id': dto['boot_id'], 'sampled_at': row['observed_at'],
            'temperature_c': temp, 'telemetry_age_seconds': max(row['age_ms'] / 1000, now - datetime.fromisoformat(row['observed_at'].replace('Z', '+00:00')).timestamp())}

class Node:
    def __init__(self, credential_file):
        self.credential_file = credential_file
    def read(self):
        with bounded():
            key = protected(self.credential_file).decode().strip()
            if not key or '\n' in key or '\r' in key:
                raise Fault('node_credential_shape')
            c = http.client.HTTPConnection(NODE_HOST, NODE_PORT, timeout=2)
            try:
                c.request('GET', NODE_PATH, headers={'Authorization': 'Bearer ' + key, 'Connection': 'close'})
                r = c.getresponse()
                raw = r.read(262145)
                if r.status != 200 or len(raw) > 262144:
                    raise Fault('node_http_status_or_size')
                return sample(decode(raw))
            finally:
                c.close()

class Policy:
    def __init__(self):
        self.cool_since = None
        self.last = None
        self.boot = None
    def decide(self, observed, current, now):
        if observed is None:
            self.cool_since = self.last = None
            return max(80, current)
        boot = observed['node_boot_id']
        if boot != self.boot or self.last is None or now - self.last > MAX_AGE:
            self.cool_since = None
        self.boot, self.last = boot, now
        t = observed['temperature_c']
        if t >= HOT:
            self.cool_since = None
            return max(80, current)
        if t > COOL:
            self.cool_since = None
            return current
        if self.cool_since is None:
            self.cool_since = now
        return 40 if now - self.cool_since >= COOL_SECONDS else current

class Store:
    def __init__(self, directory=STATE):
        self.path = Path(directory)
        s = self.path.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o700:
            raise Fault('state_directory_protection')
        self.fd = os.open(self.path / 'controller.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        s = os.fstat(self.fd)
        if s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o600 or not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
            raise Fault('lock_protection')
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd)
            raise Fault('controller_already_running') from None
    def read(self, name):
        try:
            return decode(protected(self.path / name, 65536))
        except FileNotFoundError:
            return None
    def write(self, name, value):
        held, named = os.fstat(self.fd), (self.path / 'controller.lock').lstat()
        if (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino):
            raise Fault('controller_lock_replaced')
        raw = (json.dumps(value, sort_keys=True) + '\n').encode()
        if len(raw) > 65536:
            raise Fault('status_size')
        tmp = self.path / ('.' + name + '.' + str(os.getpid()))
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, 'wb', closefd=False) as f:
                f.write(raw); f.flush(); os.fsync(fd)
            os.replace(tmp, self.path / name)
        finally:
            os.close(fd)
            if tmp.exists():
                tmp.unlink()
    def close(self):
        os.close(self.fd)

class Controller:
    def __init__(self, bmc, store):
        self.bmc, self.store = bmc, store
        self.expected = None
        self.baseline = store.read('baseline.json')
        self.proof = store.read('status.json') or {}
        self.policy = Policy()
        self.last_write_at = None
        self.started_at = utc()
        self.source_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.host_boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    def inspect(self):
        s = self.bmc.snapshot()
        duty = shape(s)
        inv = invariant(s)
        if self.baseline is None:
            self.baseline = inv
            self.store.write('baseline.json', inv)
        if inv != self.baseline:
            raise Fault('bmc_invariant_changed')
        return s, duty
    def command(self, s, current, desired):
        if desired == current:
            return s, current
        self.bmc.call('PUT', PATHS[1], payload(s, desired))
        self.last_write_at = utc()
        after, readback = self.inspect()
        if readback != desired:
            raise Fault('bmc_write_readback_mismatch')
        return after, readback
    def status(self, state, duty, observed=None, error=None, tach=None):
        # Last valid tach/readback remains distinctly timestamped when unavailable.
        previous = self.proof
        self.proof = {'schema_version': 1, 'gpu_uuid': GPU, 'host_boot_id': self.host_boot,
          'pid': os.getpid(), 'source_sha256': self.source_sha, 'started_at': self.started_at,
          'updated_at': utc(), 'state': state, 'errors': [error] if error else [],
          'desired_duty': self.expected, 'readback_duty': duty,
          'readback_kind': 'first_four_curve_duties_not_measured_pwm',
          'readback_at': utc() if duty is not None else previous.get('readback_at'),
          'last_known_readback_duty': duty if duty is not None else previous.get('last_known_readback_duty'),
          'actual_tach': tach['value'] if tach else previous.get('actual_tach'),
          'actual_tach_units': tach['units'] if tach else previous.get('actual_tach_units'),
          'tach_at': utc() if tach else previous.get('tach_at'),
          'last_write_at': self.last_write_at, 'bmc_put_attempts': self.bmc.puts,
          'bmc_logins': self.bmc.logins, 'invariant_sha256': digest(self.baseline),
          'source_bits': [0, 0, 0] if duty is not None else None,
          'mode': 4 if duty is not None else None, 'channel': 'Zone4(CHA_FAN3)/PWMNum3',
          'node_boot_id': None, 'sampled_at': None, 'temperature_c': None, 'telemetry_age_seconds': None}
        if observed:
            self.proof.update(observed)
        self.store.write('status.json', self.proof)
    def high(self):
        s, duty = self.inspect()
        self.expected = max(80, duty)
        return self.command(s, duty, self.expected)[1]
    def terminal(self, error):
        # Persist intent before ONE safe-high attempt. Restart/ExecStopPost must not fight.
        self.store.write('blocked.json', {'at': utc(), 'reason': error, 'high_attempt_reserved': True})
        duty = tach = None
        try:
            duty = self.high()
            tach = self.bmc.tach()
        except Exception:
            error += ':safe_high_unavailable'
        self.status('blocked', duty, error=error, tach=tach)
    def start(self):
        if self.store.read('blocked.json'):
            raise Fault('operator_review_required')
        duty = self.high()
        self.status('starting_high', duty, tach=self.bmc.tach())
    def step(self, node, now=None):
        s, current = self.inspect()
        if current != self.expected:
            raise Fault('competing_writer_or_overwrite')
        observed, error = None, None
        try:
            observed = node.read()
        except Exception as e:
            error = str(e) if isinstance(e, Fault) else 'telemetry_unavailable'
        desired = self.policy.decide(observed, current, time.monotonic() if now is None else now)
        self.expected = desired
        _, duty = self.command(s, current, desired)
        self.status('healthy' if observed else 'degraded_high', duty, observed, error, self.bmc.tach())

def notify(message):
    address = os.environ.get('NOTIFY_SOCKET')
    if address:
        if address.startswith('@'):
            address = '\0' + address[1:]
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.settimeout(1)
            s.connect(address)
            s.sendall(message.encode())

def reason(e):
    return str(e) if isinstance(e, Fault) else 'operation_failed_' + type(e).__name__

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=('inventory', 'run', 'failsafe'))
    args = ap.parse_args()
    os.umask(0o077)
    bmc = BMC(BMC_FILE if args.mode == 'inventory' else CREDS / 'bmc.json')
    if args.mode == 'inventory':
        try:
            bmc.login()
            s = bmc.snapshot()
            print(json.dumps({'at': utc(), 'pin': PIN, 'curve_duty': shape(s), 'snapshot': s,
                              'tach': bmc.tach(), 'node': Node(NODE_FILE).read()}, sort_keys=True))
        finally:
            bmc.logout()
        return 0
    store = Store()
    ctl = Controller(bmc, store)
    stopping = False
    def stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        if store.read('blocked.json'):
            # Preserve original blocker and last proof; no repeated fan writes.
            return 78
        bmc.login()
        if args.mode == 'failsafe':
            duty = ctl.high()
            ctl.status('stopped_high', duty, tach=bmc.tach())
            return 0
        ctl.start()
        notify('READY=1\nWATCHDOG=1')
        node = Node(CREDS / 'node-control-key')
        while not stopping:
            start = time.monotonic()
            ctl.step(node)
            notify('WATCHDOG=1')
            while not stopping and time.monotonic() - start < POLL:
                time.sleep(max(0, min(0.2, POLL - (time.monotonic() - start))))
        duty = ctl.high()
        ctl.status('stopped_high', duty, tach=bmc.tach())
        return 0
    except Exception as e:
        ctl.terminal(reason(e))
        return 78
    finally:
        bmc.logout()
        store.close()

if __name__ == '__main__':
    raise SystemExit(main())
