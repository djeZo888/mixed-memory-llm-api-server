#!/usr/bin/env python3
"""One-shot H013 power discovery; stdin execution on ai-harness only, no sampler."""
import base64
import hashlib
import http.client
import json
import os
import signal
import socket
import ssl
import stat
import time
from datetime import datetime, timezone

HOST = '10.156.100.40'
PORT = 443
PIN = '0f1ee547edbdbca346ea2d884d3271a8f28351d57a16baa911c388198063f7ec'
CREDENTIAL = '/home/user/.config/sova-private/bmc.json'
START = '2026-09-27T06:14:11Z'
HARD_DEADLINE = '2026-09-27T06:24:11Z'
# Close private work before wrapper expiry, leaving local packaging time.
DEADLINE = datetime.fromisoformat('2026-09-27T06:23:00+00:00').timestamp()
MAX_GETS = 8
CHASSIS = '/redfish/v1/Chassis/Self'
ALLOWED = {CHASSIS}
REQUESTS = 0
PIN_CHECKS = 0

class PinError(Exception):
    pass

class RequestDeadline(Exception):
    pass

class PinnedConnection(http.client.HTTPSConnection):
    def __init__(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE  # This socket requires the exact leaf pin.
        super().__init__(HOST, PORT, timeout=5, context=context)

    def connect(self):
        global PIN_CHECKS
        super().connect()
        digest = hashlib.sha256(self.sock.getpeercert(binary_form=True)).hexdigest()
        if digest != PIN:
            self.close()
            raise PinError('pin_changed')
        PIN_CHECKS += 1


def credential():
    for path in ('/home', '/home/user', '/home/user/.config', '/home/user/.config/sova-private'):
        s = os.lstat(path)
        if not stat.S_ISDIR(s.st_mode) or s.st_uid not in (0, os.getuid()) or s.st_mode & 0o022:
            raise ValueError('unprotected_parent')
        if path.endswith(('.config', 'sova-private')) and stat.S_IMODE(s.st_mode) != 0o700:
            raise ValueError('private_parent_mode')
    fd = os.open(CREDENTIAL, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        s = os.fstat(f.fileno())
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o600:
            raise ValueError('unprotected_file')
        c = json.load(f)
    if c.get('host') not in (HOST, 'https://' + HOST, 'https://' + HOST + '/') or c.get('username') != 'sova':
        raise ValueError('credential_identity')
    return c


SAFE = set('''@odata.id @odata.type Id MemberId Name Description Status State Health HealthRollup Power PowerSubsystem Sensors PowerControl PowerSupplies PowerConsumedWatts PowerInputWatts PowerOutputWatts PowerAllocatedWatts PowerAvailableWatts PowerCapacityWatts PowerSupplyType LineInputVoltage LineInputVoltageType LastPowerOutputWatts InputRanges OutputWattage MinReadingRange MaxReadingRange Reading ReadingUnits ReadingType ReadingTime ReadingCelsius ReadingVolts ReadingWatts ReadingAmps ReadingJoules ReadingkWh ReadingTimestamp Timestamp SampleTime SamplingInterval SensingInterval PhysicalContext PhysicalSubContext ElectricalContext SensorNumber OwnerLUN RelatedItem DataSourceUri Metrics PowerMetrics IntervalInMin AverageConsumedWatts MinConsumedWatts MaxConsumedWatts AverageReading MinReading MaxReading PeakReading PeakReadingTime LowestReading LowestReadingTime Accuracy Precision Resolution Calibration Offset Oem Ami AMI Label SensorType Unit Units Value InputPower OutputPower PowerWatts EnergyJoules EnergykWh LifetimeReading LifetimeStartDateTime ResetTime Members Members@odata.count PowerControl@odata.count PowerSupplies@odata.count Voltages@odata.count Redundancy@odata.count error code MessageId'''.split())


def filtered(value):
    if isinstance(value, dict):
        return {k: filtered(v) for k, v in value.items() if k in SAFE}
    if isinstance(value, list):
        if len(value) > 100:
            raise ValueError('array_bound')
        return [filtered(v) for v in value]
    return value


def now():
    return datetime.now(timezone.utc).isoformat()


def timeout_handler(signum, frame):
    raise RequestDeadline('request_deadline')


def request(path):
    global REQUESTS
    if time.time() >= DEADLINE or REQUESTS >= MAX_GETS:
        raise ValueError('task_bound')
    if path not in ALLOWED or not path.startswith('/') or path.startswith('//') or any(c in path for c in '\r\n?#'):
        raise ValueError('endpoint_bound')
    connection = PinnedConnection()
    started = now()
    begin = time.monotonic()
    signal.setitimer(signal.ITIMER_REAL, min(10, DEADLINE-time.time()))
    try:
        connection.connect()  # Pin actual TLS socket BEFORE loading credentials/header construction.
        secret = credential()
        auth = 'Basic ' + base64.b64encode((secret['username'] + ':' + secret['password']).encode()).decode()
        REQUESTS += 1
        connection.request('GET', path, headers={'Accept': 'application/json', 'Accept-Encoding': 'identity',
                                                 'Connection': 'close', 'Authorization': auth})
        response = connection.getresponse()
        body = response.read(1048577)
        if len(body) > 1048576:
            raise ValueError('response_bound')
        receipt = {'method': 'GET', 'path': path, 'status': response.status,
                   'request_started_utc': started, 'response_received_utc': now(),
                   'elapsed_seconds': round(time.monotonic()-begin, 6), 'pin_verified': True,
                   'response_bytes': len(body), 'response_sha256': hashlib.sha256(body).hexdigest(),
                   'content_type': response.getheader('Content-Type'),
                   'http_date': response.getheader('Date'), 'http_age': response.getheader('Age'),
                   'http_last_modified': response.getheader('Last-Modified')}
        if 300 <= response.status < 400:
            receipt['redirect_refused'] = True
            return receipt
        if response.getheader('Content-Encoding') not in (None, 'identity'):
            receipt['unsupported_encoding'] = True
            return receipt
        try:
            data = json.loads(body)
        except (ValueError, TypeError):
            receipt['non_json'] = True
            return receipt
        receipt['top_keys'] = sorted(data) if isinstance(data, dict) else []
        receipt['data'] = filtered(data)
        return receipt
    finally:
        connection.close()
        signal.setitimer(signal.ITIMER_REAL, 0)


def advertised(data, key):
    item = data.get(key)
    path = item.get('@odata.id') if isinstance(item, dict) else None
    if path is None:
        return None
    if not isinstance(path, str) or not path.startswith(CHASSIS + '/') or any(c in path for c in '\r\n?#'):
        raise ValueError('advertised_endpoint_scope')
    ALLOWED.add(path)
    return path


def main():
    receipts = []
    signal.signal(signal.SIGALRM, timeout_handler)
    try:
        if socket.gethostname() != 'aiharness':
            raise ValueError('wrong_execution_host')
        chassis = request(CHASSIS)
        receipts.append(chassis)
        if chassis['status'] == 200:
            data = chassis.get('data', {})
            # Follow only the exact advertised Power link; no guessed endpoints/crawl.
            path = advertised(data, 'Power')
            if path:
                receipts.append(request(path))
    except Exception as exc:
        receipts.append({'stopped': type(exc).__name__})  # Never exception text or headers.
    print(json.dumps({'task': 'H013-BMC-POWER-20260927', 'wrapper_started_utc': START,
                      'wrapper_deadline_utc': HARD_DEADLINE, 'probe_deadline_epoch': DEADLINE,
                      'execution_host': 'ai-harness', 'host': HOST, 'port': PORT, 'pin': PIN,
                      'requests': REQUESTS, 'successful_actual_socket_pin_checks': PIN_CHECKS,
                      'finished_utc': now(), 'receipts': receipts}, indent=2))


if __name__ == '__main__':
    main()
