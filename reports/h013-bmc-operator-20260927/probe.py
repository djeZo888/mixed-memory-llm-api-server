#!/usr/bin/env python3
"""Bounded read-only BMC discovery. Run only on ai-harness; no writes or sessions."""
import argparse
import base64
import hashlib
import http.client
import json
import os
import re
import socket
import ssl
import stat
import sys
import time
import zlib
from datetime import datetime, timezone

HOST = '10.156.100.40'
PIN = '0f1ee547edbdbca346ea2d884d3271a8f28351d57a16baa911c388198063f7ec'
CREDENTIAL = '/home/user/.config/sova-private/bmc.json'
DEADLINE = 1790486340  # 2026-09-27 05:19:00 UTC; earlier than launch + 20min.
PIN_CHECKS = 0
REQUESTS = 0

class PinError(Exception):
    pass

class PinnedConnection(http.client.HTTPSConnection):
    def __init__(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE  # exact leaf pin enforced on this socket below
        super().__init__(HOST, 443, timeout=6, context=context)

    def connect(self):
        global PIN_CHECKS
        super().connect()
        digest = hashlib.sha256(self.sock.getpeercert(binary_form=True)).hexdigest()
        PIN_CHECKS += 1
        if digest != PIN:
            self.close()
            raise PinError('peer_certificate_pin_changed')

def credential():
    for path in ('/home', '/home/user', '/home/user/.config', '/home/user/.config/sova-private'):
        s = os.lstat(path)
        if not stat.S_ISDIR(s.st_mode) or s.st_uid not in (0, os.getuid()) or s.st_mode & 0o022:
            raise ValueError('unprotected_credential_parent')
        if path.endswith(('.config', 'sova-private')) and stat.S_IMODE(s.st_mode) != 0o700:
            raise ValueError('private_parent_mode')
    fd = os.open(CREDENTIAL, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        s = os.fstat(f.fileno())
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o600:
            raise ValueError('unprotected_credential_file')
        c = json.load(f)
    if c.get('host') not in (HOST, 'https://' + HOST, 'https://' + HOST + '/') or c.get('username') != 'sova':
        raise ValueError('credential_target_or_identity_mismatch')
    return c

SAFE_KEYS = set('''PWM Index Source FanDuty1 FanDuty2 FanDuty3 FanDuty4 FanDuty5 FanMode FanIndex FanName FanCount Name Index index name duty mode pwm fan_name fan_index fan_count fan_mode Temperature1 Temperature2 Temperature3 Temperature4 Temperature5 @odata.id @odata.type @odata.context Id Name Description Manufacturer Model FirmwareVersion RedfishVersion Product Vendor RtpVersion Members Members@odata.count Chassis Managers Thermal ThermalSubsystem Fans Sensors Controls AccountService Roles RoleId IsPredefined AssignedPrivileges OemPrivileges PrivilegeMap OperationMap GET PATCH PUT POST DELETE Privilege Privileges Entity Targets PropertyOverrides ResourceURI Registry RegistryEntries Mappings JsonSchemas Registries Location Uri Language PublicationUri OwningEntity RegistryVersion Oem Ami AMI Status State Health HealthRollup Reading ReadingUnits ReadingType ReadingCelsius ReadingVolts PhysicalContext PhysicalSubContext SensorNumber MemberId FanName FanSpeed FanSpeedPercent FanSpeedRPM CurrentReading CurrentDuty Duty DutyCycle Mode FanMode ControlMode SpeedRPM SpeedPercent SpeedControlPercent SpeedControlPercent@Redfish.AllowableValues SpeedControlRPM FanSpeedPercent@Redfish.AllowableValues LowerThresholdCritical UpperThresholdCritical LowerThresholdNonCritical UpperThresholdNonCritical LowerThresholdFatal UpperThresholdFatal MinReadingRange MaxReadingRange RelatedItem Redundancy Temperatures Actions target @Redfish.ActionInfo Parameters DataType Required AllowableValues MinimumValue MaximumValue MinValue MaxValue SetPoint ControlType SetPointUnits AllowableMin AllowableMax AllowableIncrement Links LogServices ServiceEnabled SupportedApplyTimes PrivilegeRegistry error code MessageId Resolution MessageArgs MinReadingRangeTemp MaxReadingRangeTemp OwnerLUN @Message.ExtendedInfo'''.split())

def filtered(value, parent=''):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in SAFE_KEYS or k.endswith('@Redfish.AllowableValues') or k.endswith('@Redfish.ActionInfo') or (parent == 'Actions' and k.startswith('#')):
                out[k] = filtered(v, k)
        return out
    if isinstance(value, list):
        return [filtered(v, parent) for v in value[:150]]
    return value

def keypaths(value, prefix=''):
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in ([prefix + k] + keypaths(v, prefix + k + '.'))][:700]
    if isinstance(value, list) and value:
        return keypaths(value[0], prefix + '[].')
    return []


def request(path, method='GET', auth=True):
    global REQUESTS
    if time.time() >= DEADLINE or REQUESTS >= 30:
        raise ValueError('request_bound_reached')
    if method not in ('GET', 'OPTIONS') or not path.startswith('/') or path.startswith('//') or any(c in path for c in '\r\n?#'):
        raise ValueError('unsafe_request')
    c = PinnedConnection()
    try:
        c.connect()  # require actual socket pin before constructing any auth header
        headers = {'Accept': 'application/json', 'Accept-Encoding': 'identity', 'Connection': 'close'}
        if auth:
            secret = credential()
            headers['Authorization'] = 'Basic ' + base64.b64encode((secret['username'] + ':' + secret['password']).encode()).decode()
        REQUESTS += 1
        c.request(method, path, headers=headers)
        r = c.getresponse()
        body = r.read(2097153)
        if len(body) > 2097152:
            raise ValueError('response_size_limit')
        if r.getheader('Content-Encoding') == 'gzip' or body[:2] == b'\x1f\x8b':
            dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
            body = dec.decompress(body, 16777217)
            if len(body) > 16777216 or not dec.eof:
                raise ValueError('decoded_size_limit')
        receipt = {'method': method, 'path': path, 'status': r.status, 'pin_verified': True,
                   'allow': r.getheader('Allow'), 'content_type': r.getheader('Content-Type')}
        if 300 <= r.status < 400:
            receipt['redirect_refused'] = True
            return receipt
        try:
            data = json.loads(body)
            receipt['top_keys'] = sorted(data) if isinstance(data, dict) else []
            receipt['data'] = filtered(data)
            if path.endswith('/Thermal') or path == '/redfish/v1/Managers/Self':
                receipt['key_paths'] = keypaths(data)
            if path.startswith('/redfish/v1/JsonSchemas/') and path.endswith('.json'):
                receipt['schema'] = data  # public static schema, never a current configuration
            if 'Mappings' in receipt['data']:
                receipt['data']['Mappings'] = [m for m in receipt['data']['Mappings'] if m.get('Entity') in ('AccountService','Role','ManagerAccount','Thermal','Sensor','AMIChassisPowerThermal','AMISensor')]
                receipt['mapping_filter'] = 'thermal_sensor_account_role_only'
        except (ValueError, TypeError):
            receipt['non_json_bytes'] = len(body)
            receipt['sha256'] = hashlib.sha256(body).hexdigest()
            if path.endswith('.js'):
                source = body.decode('utf-8', 'replace')
                pattern = r'fan[_/-]?(?:control|mode|speed)|pwm|full.?speed'
                modules = list(re.finditer(r'(?:define|l)\("([^"]+)"', source))
                selected = []
                for i, match in enumerate(modules):
                    name = match.group(1)
                    if ('fan_control' in name or 'fanctrl' in name or 'login' in name.lower()) and not name.startswith(('text!', 'i18n!')):
                        end = modules[i+1].start() if i+1 < len(modules) else len(source)
                        selected.append({'module': name, 'source': source[match.start():end][:60000]})
                receipt['fan_modules'] = selected[:30]
                spans = []
                for match in re.finditer(r'/api/fanctrl/', source):
                    start, end = max(0, match.start()-2500), min(len(source), match.end()+4500)
                    if spans and start <= spans[-1][1]:
                        spans[-1][1] = max(spans[-1][1], end)
                    else:
                        spans.append([start,end])
                receipt['fan_api_source'] = []  # full filtered fan modules supersede overlapping excerpts
                # Static login implementation only; no authenticated response or account data.
                spans = []
                for match in re.finditer(r'url:"/api/session"', source):
                    spans.append(source[max(0,match.start()-700):match.end()+1000])
                receipt['login_source'] = spans[:5]
                receipt['xhr_header_source'] = [source[max(0,m.start()-250):m.end()+350] for m in re.finditer(r'X-Requested-With', source)][:3]
                receipt['ajax_setup'] = [source[max(0,m.start()-100):m.end()+900] for m in list(re.finditer(r'ajaxSetup\(', source))[:15]]
                receipt['fan_api_paths'] = sorted(set(re.findall(r'/api/[^"\s<>]*fan[^"\s<>]*', source)))[:50]
            if path == '/':
                receipt['assets'] = re.findall(r'(?:src|data-main)=["\']([^"\']+)', body.decode('utf-8', 'replace'))
        return receipt
    finally:
        c.close()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('paths', nargs='+', help='Previously advertised exact resource paths')
    p.add_argument('--options', action='store_true')
    p.add_argument('--public', action='store_true')
    a = p.parse_args()
    receipts = []
    try:
        for path in a.paths:
            receipts.append(request(path, 'OPTIONS' if a.options else 'GET', not a.public))
    except Exception as exc:
        # Exception values may contain server/private data: log only known-safe classes.
        receipts.append({'stopped': type(exc).__name__})
    print(json.dumps({'at': datetime.now(timezone.utc).isoformat(), 'host': HOST, 'port': 443,
                      'pin': PIN, 'pin_checks': PIN_CHECKS, 'requests': REQUESTS, 'receipts': receipts}, indent=2))

if __name__ == '__main__':
    main()
