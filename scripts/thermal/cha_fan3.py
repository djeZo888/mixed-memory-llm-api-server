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
CREDS = Path('/run/sova-cha-fan3-credentials')
BMC_FILE = Path('/home/user/.config/sova-private/bmc.json')
NODE_FILE = Path('/home/user/.config/ai-harness/node-control-key')
HOT, COOL, COOL_SECONDS, POLL, MAX_AGE = 70, 65, 30, 5, 15
HIGH_DUTY, HOT_DUTY, LOW_DUTY = 100, 80, 40
VERY_HOT = 80  # The explicit CHA_FAN3 exception is strictly above 80 C.
BOOT_RE = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z')

class Fault(Exception):
    """Only fixed, nonsecret reason codes belong in this exception."""

class LoweringCancelled(Exception):
    pass

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

def protected(path, maximum=8192, *, missing_ok=False):
    try:
        return _protected(path, maximum)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise Fault('protected_file_unavailable') from None
    except OSError:
        raise Fault('protected_file_unavailable') from None

def valid_file_meta(path, s):
    return (stat.S_ISREG(s.st_mode) and s.st_uid in (0, os.getuid())
            and not s.st_mode & 0o077 and s.st_nlink == 1)

def _protected(path, maximum=8192):
    path = Path(path)
    for parent in reversed(path.parents):
        s = parent.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid not in (0, os.getuid()) or s.st_mode & 0o022:
            raise Fault('unprotected_parent')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as f:
        s = os.fstat(f.fileno())
        if not valid_file_meta(path, s):
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
        self.before_put = None

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
                    if self.before_put is None:
                        raise Fault('actuator_guard_missing')
                    self.before_put(int(data['CurrentPWMdata'][1]))
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
            except (OSError, http.client.HTTPException):
                raise Fault('bmc_transport_unavailable') from None
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
        return {'value': value, 'units': r.get('ReadingUnits'), 'name': r['Name'], 'at': utc()}

    def logout(self):
        if self.csrf:
            try:
                self.call('DELETE', '/api/session')
            except Exception:
                pass
            self.csrf = None
            self.cookies.clear()

def shape(s):
    try:
        return _shape(s)
    except (KeyError, TypeError, IndexError, AttributeError, ValueError):
        raise Fault('malformed_fan_snapshot') from None

def _shape(s):
    mode, pwm, source, last = [s[p] for p in PATHS]
    if mode.get('FanMode') != 4 or type(pwm) is not list or len(pwm) != 8:
        raise Fault('mode_or_zone_count')
    if any(type(r) is not dict for r in pwm) or any(type(x) is not dict for x in (mode, source, last)):
        raise Fault('malformed_fan_snapshot')
    t = pwm[3]
    if sum(r.get('PWMNum') == 3 for r in pwm) != 1:
        raise Fault('channel_identity')
    if sum(r.get('PWMName') == 'Zone4(CHA_FAN3)' for r in pwm) != 1 or (t.get('PWMName'), t.get('PWMNum'), t.get('PWMSrc')) != ('Zone4(CHA_FAN3)', 3, 0):
        raise Fault('channel_identity')
    listed = [r for r in source['FanSourceList'] if r.get('PWM') == 'PWM4' or r.get('Name') == 'CHA_FAN3']
    if len(listed) != 1 or (listed[0].get('PWM'), listed[0].get('Name')) != ('PWM4', 'CHA_FAN3'):
        raise Fault('channel_identity')
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
    shape(s)
    target = copy.deepcopy(s[PATHS[1]][3])
    for point in target['CurrentPWMdata'][:4]:
        point['Duty'] = None
    source = s[PATHS[2]]
    return {'schema_version': 2, 'FanMode': s[PATHS[0]]['FanMode'],
            'array_index': 3, 'target': configuration_only(target),
            'source': {k: source[k] for k in ('PWM4_1', 'PWM4_2', 'PWM4_3')},
            'source_entry': copy.deepcopy(next(r for r in source['FanSourceList'] if r['PWM'] == 'PWM4')),
            'PWM4_LastSource': s[PATHS[3]]['PWM4_LastSource']}

def non_target(s):
    out = configuration_only(copy.deepcopy(s))
    out[PATHS[0]].pop('FanMode', None)
    out[PATHS[1]][3] = None
    for key in ('PWM4_1', 'PWM4_2', 'PWM4_3'):
        out[PATHS[2]].pop(key, None)
    out[PATHS[2]]['FanSourceList'] = [r for r in out[PATHS[2]]['FanSourceList'] if r['PWM'] != 'PWM4']
    out[PATHS[3]].pop('PWM4_LastSource', None)
    return out

def configuration_only(v):
    # Last-selected source is observation, not the configured /source mask.
    if isinstance(v, dict):
        return {k: configuration_only(x) for k, x in v.items()
                if not re.fullmatch(r'(?:PWM[1-8]_)?LastTemp|PWM[1235678]_LastSource', k)}
    if isinstance(v, list):
        return [configuration_only(x) for x in v]
    return v

def configuration_diff(before, after):
    rows = []
    def value(v):
        raw = json.dumps(v, sort_keys=True)
        return v if len(raw) <= 512 else {'value_sha256': digest(v), 'encoded_size': len(raw)}
    def walk(a, b, path):
        if len(rows) >= 32:
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(a.keys() | b.keys()):
                walk(a.get(key), b.get(key), path + '/' + key)
        elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, path + '/' + str(i))
        elif a != b:
            rows.append({'path': path, 'before': value(a), 'after': value(b)})
    walk(before, after, '')
    return rows

def payload(s, duty):
    shape(s)
    if type(duty) is not int or duty not in (LOW_DUTY, HOT_DUTY, HIGH_DUTY):
        raise Fault('duty_not_allowlisted')
    return {'PWMIndex': 3, 'PWMSrc': 0, 'PWMNum': 3,
            'CurrentPWMdata': ['20', str(duty), '45', str(duty), '65', str(duty), '90', str(duty), 100, 100]}

def validate_payload(v):
    if not any(v == {'PWMIndex': 3, 'PWMSrc': 0, 'PWMNum': 3,
                     'CurrentPWMdata': ['20', str(d), '45', str(d), '65', str(d), '90', str(d), 100, 100]} for d in (LOW_DUTY, HOT_DUTY, HIGH_DUTY)):
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
            return HIGH_DUTY
        boot = observed['node_boot_id']
        if boot != self.boot or self.last is None or now - self.last > MAX_AGE:
            self.cool_since = None
        self.boot, self.last = boot, now
        t = observed['temperature_c']
        if t > VERY_HOT:
            self.cool_since = None
            return HIGH_DUTY
        if t >= HOT:
            self.cool_since = None
            return max(HOT_DUTY, current)
        if t > COOL:
            self.cool_since = None
            return current
        if self.cool_since is None:
            self.cool_since = now
        return LOW_DUTY if now - self.cool_since >= COOL_SECONDS else current

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
        raw = protected(self.path / name, 65536, missing_ok=True)
        return None if raw is None else decode(raw)
    def assert_held(self):
        try:
            held, named = os.fstat(self.fd), (self.path / 'controller.lock').lstat()
        except OSError:
            raise Fault('controller_lock_unavailable') from None
        if (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino):
            raise Fault('controller_lock_replaced')
    def write(self, name, value):
        self.assert_held()
        raw = (json.dumps(value, sort_keys=True) + '\n').encode()
        if len(raw) > 65536:
            raise Fault('status_size')
        tmp = self.path / ('.' + name + '.' + str(os.getpid()))
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, 'wb', closefd=False) as f:
                f.write(raw); f.flush(); os.fsync(fd)
            os.replace(tmp, self.path / name)
            directory_fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory_fd)  # Durable latch BEFORE its one reserved high attempt.
            finally:
                os.close(directory_fd)
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
        self.desired = None
        self.baseline = store.read('baseline.json')
        self.proof = store.read('status.json') or {}
        if type(self.proof.get('readback_duty')) is int:
            self.expected = self.proof['readback_duty']
        self.readback_at = self.proof.get('readback_at')
        self.stopping = lambda: False
        self.bmc.before_put = self.actuator_guard
        self.policy = Policy()
        self.last_write_at = None
        self.started_at = utc()
        self.recovering = True
        self.source_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.host_boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    def inspect(self, receipt=None):
        if self.baseline is not None and (not isinstance(self.baseline, dict) or self.baseline.get('schema_version') != 2):
            raise Fault('baseline_migration_required')
        s = self.bmc.snapshot()
        if receipt:
            self.store.write(receipt, s)
        duty = shape(s)
        inv = invariant(s)
        if self.baseline is None:
            self.baseline = inv
            self.store.write('baseline.json', inv)
        if inv != self.baseline:
            self.store.write('invariant-mismatch.json', {'at': utc(),
                'baseline_sha256': digest(self.baseline), 'observed_sha256': digest(inv),
                'differences': configuration_diff(self.baseline, inv), 'limit': 32})
            raise Fault('bmc_invariant_changed')
        self.readback_at = utc()
        return s, duty
    def actuator_guard(self, duty):
        self.store.assert_held()
        if duty == LOW_DUTY and self.stopping():
            raise LoweringCancelled()
    def command(self, s, current, desired):
        payload(s, desired)  # Reject a legacy/new forbidden target before intent writes.
        self.desired = desired
        if desired == current:
            self.expected = current  # Caller just independently inspected this readback.
            return s, current
        s, fresh_duty = self.inspect()
        if fresh_duty != current:
            raise Fault('competing_writer_or_overwrite')
        self.store.write('write-pre-snapshot.json', s)
        intent = {'at': utc(), 'before_duty': current, 'desired_duty': desired,
                  'invariant_sha256': digest(self.baseline), 'state': 'prepared'}
        self.store.write('pending-write.json', intent)
        try:
            self.actuator_guard(desired)
            self.bmc.call('PUT', PATHS[1], payload(s, desired))
            self.last_write_at = utc()
            after, readback = self.inspect(receipt='write-post-snapshot.json')
            self.store.write('non-target-audit.json', {'at': utc(),
                'before_sha256': digest(s), 'after_sha256': digest(after),
                'differences': configuration_diff(non_target(s), non_target(after)), 'limit': 32,
                'attribution': 'unknown'})
            if readback != desired:
                raise Fault('bmc_write_readback_mismatch')
            self.store.write('pending-write.json', dict(intent, state='verified', readback_at=utc()))
            self.expected = readback
            return after, readback
        except LoweringCancelled:
            self.expected = current
            self.store.write('pending-write.json', dict(intent, state='verified', cancelled_before_send=True))
            return s, current
        except Exception as e:
            # Keep uncertain original write separate from the reserved high attempt.
            try:
                self.store.write('uncertain-write.json', dict(intent, state='uncertain', error=reason(e)))
            finally:
                raise Fault('bmc_write_pending_readback' if transient(e) else 'bmc_write_uncertain') from None
    def status(self, state, duty, observed=None, error=None, tach=None):
        # Last valid tach/readback remains distinctly timestamped when unavailable.
        previous = self.proof
        self.proof = {'schema_version': 1, 'gpu_uuid': GPU, 'host_boot_id': self.host_boot,
          'pid': os.getpid(), 'source_sha256': self.source_sha, 'started_at': self.started_at,
          'updated_at': utc(), 'state': state, 'errors': [error] if error else [],
          'desired_duty': self.desired, 'confirmed_expected_duty': self.expected, 'readback_duty': duty,
          'readback_kind': 'first_four_curve_duties_not_measured_pwm',
          'readback_at': self.readback_at if duty is not None else previous.get('readback_at'),
          'last_known_readback_duty': duty if duty is not None else previous.get('last_known_readback_duty'),
          'actual_tach': tach['value'] if tach else previous.get('actual_tach'),
          'actual_tach_units': tach['units'] if tach else previous.get('actual_tach_units'),
          'tach_at': tach.get('at') if tach else previous.get('tach_at'),
          'last_write_at': self.last_write_at, 'bmc_put_attempts': self.bmc.puts,
          'bmc_logins': self.bmc.logins, 'invariant_sha256': digest(self.baseline),
          'source_bits': [0, 0, 0] if duty is not None else None,
          'mode': 4 if duty is not None else None, 'channel': 'Zone4(CHA_FAN3)/PWMNum3',
          'node_boot_id': None, 'sampled_at': None, 'temperature_c': None, 'telemetry_age_seconds': None}
        if observed:
            self.proof.update(observed)
        self.store.write('status.json', self.proof)
    def reconcile_pending(self):
        pending = self.store.read('pending-write.json')
        if not pending or pending.get('state') == 'verified':
            return
        if (pending.get('state') != 'prepared' or type(pending.get('desired_duty')) is not int
                or pending['desired_duty'] not in (LOW_DUTY, HOT_DUTY, HIGH_DUTY)
                or type(pending.get('before_duty')) is not int
                or not 0 <= pending['before_duty'] <= 100
                or pending.get('invariant_sha256') != digest(self.baseline)):
            raise Fault('write_record_invalid')
        _, duty = self.inspect()  # READ ONLY until full invariant and exact state proved.
        if duty not in (pending['desired_duty'], pending['before_duty']):
            raise Fault('ambiguous_write_conflicting_readback')
        self.store.write('pending-write.json', dict(pending, state='verified',
                         reconciled_readback_duty=duty, readback_at=utc()))
        self.expected = duty
        self.policy = Policy()  # Outage never counts toward the cool dwell.

    def high(self, check_expected=False):
        self.desired = HIGH_DUTY
        self.reconcile_pending()
        s, duty = self.inspect()
        if check_expected and self.expected is not None and duty != self.expected:
            raise Fault('competing_writer_or_overwrite')
        return self.command(s, duty, HIGH_DUTY)[1]
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
        duty = self.high(check_expected=True)
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
        self.desired = desired
        _, duty = self.command(s, current, desired)
        self.status('healthy' if observed else 'degraded_high', duty, observed, error, self.bmc.tach())

    def cycle(self, node):
        """Transport loss retries with bounded backoff; integrity loss never retries."""
        try:
            if not self.bmc.csrf:
                self.bmc.login()
            if self.recovering:
                self.start()
            self.step(node)
            self.recovering = False
            return True
        except Exception as e:
            if not transient(e):
                raise
            self.policy = Policy()
            self.recovering = True
            duty = tach = None
            error = reason(e)
            try:
                # Fresh readback precedes any new high command, never a PUT replay.
                duty = self.high(check_expected=True)
                tach = self.bmc.tach()
            except Exception as high_error:
                if not transient(high_error):
                    raise
                error += ':safe_high_unavailable'
            self.status('degraded_high' if duty == HIGH_DUTY else 'degraded_unknown',
                        duty, error=error, tach=tach)
            return False

def transient(e):
    return (isinstance(e, Fault) and str(e) in {
                'request_timeout', 'bmc_transport_unavailable', 'bmc_write_pending_readback', 'bmc_http_status', 'bmc_session_expired',
                'bmc_session_missing', 'bmc_relogin_throttled', 'bmc_login_rejected',
                'bmc_response_size', 'tach_identity_unavailable', 'tach_missing_or_stopped'})

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
    ctl.stopping = lambda: stopping
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        if store.read('blocked.json'):
            # Preserve original blocker and last proof; no repeated fan writes.
            return 78
        if args.mode == 'failsafe':
            bmc.login()
            duty = ctl.high()
            ctl.status('stopped_high', duty, tach=bmc.tach())
            return 0
        node = Node(CREDS / 'node-control-key')
        backoff = POLL
        while not stopping:
            start = time.monotonic()
            healthy_cycle = ctl.cycle(node)
            backoff = POLL if healthy_cycle else min(30, backoff * 2)
            notify('READY=1\nWATCHDOG=1')  # Process ready; status remains degraded on outage.
            next_heartbeat = time.monotonic() + 5
            while not stopping and time.monotonic() - start < backoff:
                if time.monotonic() >= next_heartbeat:
                    notify('WATCHDOG=1')
                    next_heartbeat = time.monotonic() + 5
                time.sleep(max(0, min(0.2, backoff - (time.monotonic() - start))))
        duty = ctl.high()
        ctl.status('stopped_high', duty, tach=bmc.tach())
        return 0
    except Exception as e:
        if transient(e):
            # Stop/failsafe transport outage: expose unavailable, retain restart path.
            ctl.status('stopped_unavailable', None, error=reason(e))
            return 1
        ctl.terminal(reason(e))
        return 78
    finally:
        bmc.logout()
        store.close()

if __name__ == '__main__':
    raise SystemExit(main())
