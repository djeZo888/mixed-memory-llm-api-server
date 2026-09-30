#!/usr/bin/env python3
"""IMAGE21 bounded independent acceptance. No network/key access without live flags.
Task-local; no API implementation imports. Run with the existing API venv, -I -B.
"""
import argparse
import asyncio
import base64
from contextlib import contextmanager
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import threading
import sys
import time
import warnings
from datetime import datetime, timezone

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parent
SOURCE = 'f188e6de8d151a7e571c7e3b5ecb59ef63d32bb7'
ENDPOINT = 'http://10.156.100.60:30006'
ALIAS = 'qwen-image-2.1'
KEY_SOURCE = {'ssh_host': 'ai-vm', 'path': '/data/services/secrets/llm-api-key'}
SSH_ARGV = ['/usr/bin/ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
            'ai-vm', 'sudo', '-n', 'cat', '/data/services/secrets/llm-api-key']
TEXT_SERVICES = [
    {'endpoint': 'http://10.156.100.60:30002', 'model': 'qwen3.8-27b-gpu0', 'context_length': 480000},
    {'endpoint': 'http://10.156.100.60:30004', 'model': 'qwen3.8-27b', 'context_length': 480000}]

PINS = {'runtime_revision': '0cd8be351d0825488f4b81c8931167bbab618eca',
        'model_id': 'Qwen/Qwen-Image-2.1',
        'model_revision': '790c92633540aa0cb11d9abf19eb46d861714758'}
LIMITS = {'encoded_file_bytes': 33554432, 'encoded_total_bytes': 67108864,
          'maximum_pixels_when_qualified': 8294400, 'references': 2,
          'approved_uhd_native_pixels': 8355840, 'n': 1, 'active': 1,
          'waiting': 0, 'budget_seconds': 900}
DEFAULTS = {'size': '1024x1024', 'steps': 40, 'cfg': 1, 'generator_device': 'cpu'}
SEED = 20260923
GEN_PROMPT = ('A studio photograph of one red ceramic teapot with a curved spout and '
              'round lid, centered on a pale wooden table against a plain cream '
              'background. Soft daylight, clear silhouette, no text, no other objects.')
EDIT_PROMPT = ('Change the red ceramic teapot to cobalt blue. Keep the same single '
               'teapot, curved spout, round lid, position, pale wooden table, cream '
               'background and soft daylight. Do not add objects or text.')
Image.MAX_IMAGE_PIXELS = 1024 * 1024


class Stop(Exception):
    """Only fixed local codes may leave the process; never raw exceptions."""


def require(condition, code):
    if not condition:
        raise Stop(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'duplicate_json_key')
            value[key] = item
        return value
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(Stop('invalid_json')))
    except (ValueError, UnicodeError, RecursionError):
        raise Stop('invalid_json') from None


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def profiles(items):
    """Compare only public capability fields; conditioning stays in the receipt."""
    require(isinstance(items, list) and len(items) <= 100, 'receipt_profiles_invalid')
    result = []
    for p in items:
        required = {'operation', 'size', 'references', 'transparent', 'evidence_sha256'}
        require(isinstance(p, dict) and required <= p.keys()
                and not p.keys() - required - {'conditioning', 'native_size', 'crop_bottom'},
                'receipt_profile_fields_invalid')
        q = {k: p[k] for k in required}
        q.update(native_size=p.get('native_size', p['size']), crop_bottom=p.get('crop_bottom', 0))
        require(p['operation'] == 'generation' and type(p['references']) is int
                and p['references'] == 0 and p['transparent'] is False
                and isinstance(p['evidence_sha256'], str)
                and re.fullmatch('[0-9a-f]{64}', p['evidence_sha256']) is not None,
                'receipt_profile_invalid')
        for size in (q['size'], q['native_size']):
            require(isinstance(size, str) and re.fullmatch('[1-9][0-9]{0,3}x[1-9][0-9]{0,3}', size),
                    'receipt_geometry_invalid')
        w, h = map(int, q['size'].split('x'))
        require(w <= 3840 and h <= 2160 and w*h <= 8294400 and type(q['crop_bottom']) is int,
                'receipt_geometry_invalid')
        if q['size'] == '3840x2160':
            require(q['native_size'] == '3840x2176' and q['crop_bottom'] == 16
                    and q['references'] <= 1, 'receipt_geometry_invalid')
        else:
            require(q['native_size'] == q['size'] and q['crop_bottom'] == 0,
                    'receipt_geometry_invalid')
        result.append(q)
    signatures = [(p['operation'], p['size'], p['references'], p['transparent']) for p in result]
    require(len(set(signatures)) == len(signatures), 'duplicate_receipt_profile')
    return sorted(result, key=canonical)


def load_receipt(path, expected_sha):
    raw = Path(path).read_bytes()
    require(len(raw) <= 256 * 1024 and sha(raw) == expected_sha, 'receipt_hash_mismatch')
    receipt = strict_json(raw)
    require(isinstance(receipt, dict) and set(receipt) == {'source_commit', 'endpoint', 'qualification', 'key_source', 'text_services'},
            'receipt_fields_invalid')
    require(receipt['source_commit'] == SOURCE and receipt['endpoint'] == ENDPOINT,
            'receipt_source_or_endpoint_mismatch')
    require(receipt['key_source'] == KEY_SOURCE, 'receipt_key_source_mismatch')
    require(canonical(receipt['text_services']) == canonical(TEXT_SERVICES), 'receipt_text_identity_mismatch')
    q = receipt['qualification']
    require(isinstance(q, dict) and set(q) == {'schema_version', *PINS, 'runtime_image_digest', 'profiles'}
            and type(q['schema_version']) is int and q['schema_version'] == 1, 'receipt_manifest_invalid')
    require(all(q[k] == v for k, v in PINS.items()), 'receipt_pins_mismatch')
    digest = q['runtime_image_digest']
    require(isinstance(digest, str) and re.fullmatch('sha256:[0-9a-f]{64}', digest),
            'receipt_digest_missing')
    q = {**q, 'profiles': profiles(q['profiles'])}
    require(bool(q['profiles']), 'receipt_no_measured_generation')
    return {**receipt, 'qualification': q}


def key_format(raw):
    raw = raw[:-1] if raw.endswith(b'\n') else raw
    require(re.fullmatch(rb'[A-Za-z0-9._~+/=-]{32,256}', raw), 'key_format_invalid')
    return raw.decode('ascii')


def remote_key(receipt):
    """Only called by gated main; stdout is bounded memory, stderr is discarded."""
    require(receipt.get('key_source') == KEY_SOURCE, 'receipt_key_source_mismatch')
    proc = None
    try:
        with request_deadline(10):
            proc = subprocess.Popen(SSH_ARGV, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, shell=False)
            raw = proc.stdout.read(258)  # At most257 valid bytes, including one LF.
            require(len(raw) <= 257, 'remote_key_too_large')
            require(proc.wait(timeout=2) == 0, 'remote_key_failed')
            return key_format(raw)
    except Exception:
        raise Stop('remote_key_failed_sanitized') from None
    finally:
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=2)
            except Exception:
                pass
            if proc.stdout is not None:
                proc.stdout.close()


def load_key(args, receipt):
    gate(args)
    require(receipt.get('key_source') == KEY_SOURCE and receipt.get('source_commit') == SOURCE
            and receipt.get('receipt_sha256') == args.receipt_sha256, 'validated_receipt_required')
    return remote_key(receipt) if args.remote_key else protected_key(args.key_file)


def protected_key(path):
    """Existing local protected file only. Never search, copy or log the path/key."""
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'key_path_not_absolute')
    for parent in reversed(path.parents):
        s = parent.lstat()
        require(stat.S_ISDIR(s.st_mode) and s.st_uid in (0, os.geteuid())
                and not s.st_mode & 0o022, 'key_ancestry_not_protected')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        s = os.fstat(fd)
        require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1
                and s.st_uid in (0, os.geteuid()) and stat.S_IMODE(s.st_mode) in (0o400, 0o600)
                and 32 <= s.st_size <= 257, 'key_file_not_protected')
        raw = os.read(fd, 258)
    finally:
        os.close(fd)
    return key_format(raw)


def png_info(raw):
    require(len(raw) <= 32 * 1024 * 1024 and raw.startswith(b'\x89PNG\r\n\x1a\n'), 'not_png')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as im:
                require(im.format == 'PNG' and im.size == (1024, 1024)
                        and getattr(im, 'n_frames', 1) == 1, 'png_dimensions_or_frames')
                im.verify()
            with Image.open(io.BytesIO(raw)) as im:
                im.load()
                require(not im.info, 'unexpected_png_metadata')
                mode = im.mode
    except Stop:
        raise
    except Exception:
        raise Stop('png_decode_failed') from None
    return {'sha256': sha(raw), 'bytes': len(raw), 'width': 1024, 'height': 1024,
            'format': 'PNG', 'mode': mode, 'alpha_qualification': 'NOT_TESTED'}


def decode_output(value):
    require(isinstance(value, dict) and set(value) == {'created', 'data'}
            and type(value['created']) is int and value['created'] >= 0, 'response_schema_invalid')
    data = value['data']
    require(isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict)
            and set(data[0]) == {'b64_json'} and isinstance(data[0]['b64_json'], str)
            and len(data[0]['b64_json']) <= 48 * 1024 * 1024, 'response_image_schema_invalid')
    try:
        raw = base64.b64decode(data[0]['b64_json'], validate=True)
    except (ValueError, UnicodeError):
        raise Stop('invalid_base64') from None
    return raw, png_info(raw)


def payload(edit=False):
    return {'model': ALIAS, 'prompt': EDIT_PROMPT if edit else GEN_PROMPT, 'size': '1024x1024',
            'n': 1, 'seed': SEED, 'response_format': 'b64_json', 'background': 'opaque'}


def invalid_cases():
    tiny = io.BytesIO()
    Image.new('RGB', (1, 1)).save(tiny, format='PNG')
    return [
        ('n_2', '/v1/images/generations', {'json': {**payload(), 'n': 2}}, 'invalid_request'),
        ('runtime_field', '/v1/images/generations',
         {'json': {**payload(), 'generator_device': 'cpu'}}, 'invalid_request'),
        ('unsupported_size', '/v1/images/generations',
         {'json': {**payload(), 'size': '4096x4096'}}, 'unsupported_size'),
        ('mask', '/v1/images/edits', {'data': {k: str(v) for k, v in payload(True).items()},
         'files': [('image', ('reference.png', tiny.getvalue(), 'image/png')),
                   ('mask', ('mask.png', tiny.getvalue(), 'image/png'))]}, 'invalid_request')]


def write_private(path, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as out:
        out.write(raw)


def evidence_dir():
    p = ROOT / 'evidence'
    p.mkdir(mode=0o700, exist_ok=True)
    s = p.lstat()
    require(stat.S_ISDIR(s.st_mode) and s.st_uid == os.geteuid()
            and stat.S_IMODE(s.st_mode) == 0o700, 'evidence_directory_not_private')
    return p


@contextmanager
def request_deadline(seconds):
    """Absolute CLI wall budget, beyond httpx's individual inactivity timeouts."""
    def expired(signum, frame):
        raise Stop('client_deadline_outcome_unknown_stop_report_no_retry')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class Session:
    def __init__(self, key, receipt, log):
        self.key, self.receipt, self.log = key, receipt, log
        self.client = httpx.Client(base_url=ENDPOINT, trust_env=False, follow_redirects=False,
                                   transport=httpx.HTTPTransport(retries=0),
                                   timeout=httpx.Timeout(10, connect=5, write=30, pool=5))

    def request(self, name, method, route, *, auth='real', image=False, **kwargs):
        headers = {} if auth == 'missing' else {'Authorization': 'Bearer ' + (
            self.key if auth == 'real' else ('x' if self.key != 'x' else 'y'))}
        start = time.monotonic()
        # No raw bodies, response headers, URL paths from the server or exception text logged.
        item = {'check': name, 'status': 'STARTED', 'at': datetime.now(timezone.utc).isoformat()}
        self.log.append(item)
        try:
            with request_deadline(960 if image else 15), self.client.stream(method, route, headers=headers,
                                    timeout=httpx.Timeout(960 if image else 10, connect=5, write=30, pool=5),
                                    **kwargs) as response:
                item['http_status'] = response.status_code
                retry = response.headers.get('retry-after')
                item['retry_after_1'] = retry == '1'
                raw = bytearray()
                cap = 48 * 1024 * 1024 if image else 256 * 1024
                for chunk in response.iter_bytes():
                    require(len(raw) + len(chunk) <= cap, 'response_too_large')
                    raw.extend(chunk)
                item['response_bytes'] = len(raw)
                value = strict_json(bytes(raw))
                if isinstance(value, dict) and isinstance(value.get('error'), dict):
                    code = value['error'].get('code')
                    if code in ('unauthorized', 'invalid_request', 'unsupported_size', 'busy', 'not_ready',
                                'unqualified_profile', 'backend_unavailable', 'request_timeout',
                                'internal_error', 'input_too_large', 'invalid_image', 'unsupported_media_type'):
                        item['error_code'] = code
                return response.status_code, value, retry
        finally:
            item['elapsed_seconds'] = round(time.monotonic() - start, 3)
            item['status'] = 'RECEIVED' if 'response_bytes' in item else 'INCOMPLETE'

    def error(self, name, route, kwargs, expected=400, code='invalid_request'):
        status, value, _ = self.request(name, 'POST', route, **kwargs)
        require(status == expected and value == {'error': {'code': code, 'message': code.replace('_', ' ')}},
                'unexpected_invalid_request_result')
        self.log[-1]['status'] = 'LIVE_PASS'

    def ready(self, idle=False):
        status, value, _ = self.request('readiness', 'GET', '/health/ready')
        require(status == 200 and isinstance(value, dict) and set(value) == {'ready', 'busy', 'admitting', 'state'}
                and value['ready'] is True and type(value['busy']) is bool
                and value['admitting'] is (not value['busy']) and value['state'] == 'ready',
                'service_not_ready_or_invalid_state')
        self.log[-1].update(status='LIVE_PASS', service=value)
        require(not idle or not value['busy'], 'service_busy_stop')
        return value

    def capabilities(self):
        status, value, _ = self.request('capabilities', 'GET', '/v1/image-capabilities')
        q = self.receipt['qualification']
        expected_keys = {*PINS, 'runtime_image_digest', 'model', 'profiles', 'limits', 'defaults',
                         'masks', 'response_format', 'output_format', 'ready', 'busy', 'admitting', 'state'}
        require(status == 200 and isinstance(value, dict) and set(value) == expected_keys,
                'capability_schema_mismatch')
        require(all(value[k] == q[k] for k in (*PINS, 'runtime_image_digest'))
                and value['model'] == ALIAS and canonical(profiles(value['profiles'])) == canonical(q['profiles'])
                and canonical(value['limits']) == canonical(LIMITS)
                and canonical(value['defaults']) == canonical(DEFAULTS)
                and value['masks'] is False and value['response_format'] == 'b64_json'
                and value['output_format'] == 'png', 'capability_receipt_mismatch')
        require(type(value['ready']) is bool and type(value['busy']) is bool
                and type(value['admitting']) is bool and value['state'] in ('startup', 'recovering', 'ready', 'closed', 'unqualified')
                and value['admitting'] is (value['ready'] and not value['busy']), 'capability_state_invalid')
        self.log[-1].update(status='LIVE_PASS', measured_profiles=q['profiles'], configured_limits=LIMITS,
                           defaults=DEFAULTS, runtime_image_digest=q['runtime_image_digest'],
                           service={k: value[k] for k in ('ready', 'busy', 'admitting', 'state')})

    def close(self):
        self.client.close()
        self.key = None


def run_mode(s, mode, evidence):
    if mode == 'read':
        for auth in ('missing', 'wrong'):
            status, value, _ = s.request(auth + '_auth', 'GET', '/health/live', auth=auth)
            require(status == 401 and value == {'error': {'code': 'unauthorized', 'message': 'unauthorized'}},
                    'auth_expectation_failed')
            s.log[-1]['status'] = 'LIVE_PASS'
        status, value, _ = s.request('liveness', 'GET', '/health/live')
        require(status == 200 and value == {'live': True}, 'liveness_failed')
        s.log[-1]['status'] = 'LIVE_PASS'
        s.ready()
        status, value, _ = s.request('models', 'GET', '/v1/models')
        require(status == 200 and value == {'object': 'list', 'data': [
            {'id': ALIAS, 'object': 'model', 'owned_by': 'local'}]}, 'models_mismatch')
        s.log[-1]['status'] = 'LIVE_PASS'
        s.capabilities()
        return 'LIVE_PASS'
    if mode == 'busy':
        before = s.ready()
        status, value, retry = s.request('invalid_busy_contender', 'POST', '/v1/images/generations',
                                       json={**payload(), 'n': 2})
        if status == 429:
            require(retry == '1' and value == {'error': {'code': 'busy', 'message': 'busy'}}, 'busy_contract_mismatch')
            s.log[-1]['status'] = 'LIVE_PASS'
            return 'LIVE_PASS' if before['busy'] else 'PARTIAL'
        require(status == 400 and value == {'error': {'code': 'invalid_request', 'message': 'invalid request'}},
                'unexpected_busy_probe_result')
        s.log[-1]['status'] = 'PARTIAL'
        s.log[-1]['classification'] = 'RACED_PROBE' if before['busy'] else 'OCCUPANCY_NOT_OBSERVED'
        return 'PARTIAL'
    s.capabilities()
    s.ready(idle=True)
    if mode == 'invalid':
        for name, route, kwargs, code in invalid_cases():
            s.error(name, route, kwargs, code=code)
        return 'LIVE_PASS'
    if mode == 'reject-edit':
        require(all(p['operation'] == 'generation' for p in s.receipt['qualification']['profiles']),
                'edit_profile_present_stop')
        reference = (evidence / 'baseline-generation.png').read_bytes()
        ref_info = png_info(reference)
        s.log.append({'check': 'edit_reference', 'status': 'SOURCE/OFFLINE_PASS',
                      'sha256': ref_info['sha256']})
        s.error('reject_edit', '/v1/images/edits',
                {'data': {k: str(v) for k, v in payload(True).items()},
                 'files': {'image': ('reference.png', reference, 'image/png')}},
                code='unqualified_profile')
        return 'LIVE_PASS'
    require(mode == 'generate', 'unsupported_mode')
    require(any(p['size'] == '1024x1024' for p in s.receipt['qualification']['profiles']),
            'baseline_profile_not_in_receipt')
    write_private(evidence / 'baseline-generation.attempt.json',
                  {'operation': 'generation', 'source_commit': SOURCE, 'request': payload(),
                   'started_utc': datetime.now(timezone.utc).isoformat(),
                   'receipt_sha256': s.receipt['receipt_sha256'], 'retry_authorized': False})
    probes = {'check': 'concurrent_qwen', 'status': 'NOT_TESTED', 'checks': [], 'text_windows': []}
    started = threading.Event()
    worker = threading.Thread(target=concurrent_probes, args=(s.key, started, probes), daemon=True)
    worker.start()
    image_start = time.monotonic()
    started.set()
    try:
        status, value, _ = s.request('generation', 'POST', '/v1/images/generations', image=True, json=payload())
        image_end = time.monotonic()
        require(status == 200, 'accepted_call_failed_stop_report_no_retry')
        raw, info = decode_output(value)
        write_private(evidence / 'baseline-generation.png', raw)
        s.log[-1].update(status='LIVE_PASS', image=info, artifact='evidence/baseline-generation.png',
                         visual_prompt_success='NOT_TESTED')
    finally:
        worker.join(61)  # Helper has its own60s async total budget; no signal use off main thread.
        require(not worker.is_alive(), 'probe_join_failed_stop_report')
        s.log.append(probes)
    probes['image_window'] = [image_start, image_end]
    if 'failure_code' not in probes:
        probes['status'] = check_overlap(image_start, image_end, probes['text_windows'],
                                        probes.get('busy_confirmed', False))
    require('failure_code' not in probes, 'concurrent_probe_failed_stop_report')
    return 'PARTIAL'  # Visual acceptance remains independent even if overlap passes.


def check_overlap(image_start, image_end, windows, busy_confirmed):
    return ('LIVE_PASS' if busy_confirmed and len(windows) == 2
            and all(image_start <= start < end <= image_end for start, end in windows) else 'PARTIAL')


def text_payload(service):
    require(service in TEXT_SERVICES, 'text_identity_not_fixed')
    return {'model': service['model'], 'messages': [{'role': 'user', 'content': 'Reply exactly OK.'}],
            'max_tokens': 8, 'temperature': 0, 'stream': False}


async def probe_request(client, key, url, *, data=None):
    """Only fixed URLs supplied internally; bounded async helper, never signals."""
    async def once():
        async with client.stream('GET' if data is None else 'POST', url,
                                 headers={'Authorization': 'Bearer ' + key},
                                 **({} if data is None else {'json': data})) as response:
            raw = bytearray()
            async for part in response.aiter_bytes():
                require(len(raw) + len(part) <= 65536, 'probe_response_too_large')
                raw.extend(part)
            return response.status_code, strict_json(bytes(raw)), response.headers.get('retry-after')
    return await asyncio.wait_for(once(), timeout=15)


async def text_probe_pair(key, result):
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False,
                                transport=httpx.AsyncHTTPTransport(retries=0), timeout=10) as client:
        status, state, _ = await probe_request(client, key, ENDPOINT + '/health/ready')
        result['checks'].append({'check': 'concurrent_readiness', 'http_status': status})
        require(status == 200 and isinstance(state, dict) and state.get('ready') is True,
                'concurrent_readiness_failed')
        status, value, retry = await probe_request(client, key, ENDPOINT + '/v1/images/generations',
                                                   data={**payload(), 'n': 2})
        result['checks'].append({'check': 'invalid_n2_busy', 'http_status': status, 'retry_after_1': retry == '1'})
        if status == 400 and value == {'error': {'code': 'invalid_request', 'message': 'invalid request'}}:
            result.update(status='PARTIAL', classification='RACED_PROBE', busy_confirmed=False)
            return
        require(status == 429 and retry == '1' and value == {'error': {'code': 'busy', 'message': 'busy'}},
                'concurrent_busy_failed')
        result['busy_confirmed'] = True
        result['checks'][-1]['healthy_busy_readiness'] = (
            state == {'ready': True, 'busy': True, 'admitting': False, 'state': 'ready'})
        for service in TEXT_SERVICES:
            start = time.monotonic()
            status, value, _ = await probe_request(client, key, service['endpoint'] + '/v1/chat/completions',
                                                    data=text_payload(service))
            end = time.monotonic()
            item = {'check': service['model'], 'http_status': status,
                    'context_length_from_receipt': service['context_length'],
                    'elapsed_seconds': round(end-start, 3)}
            result['checks'].append(item)
            require(status == 200 and isinstance(value, dict) and value.get('model') == service['model'],
                    'text_response_identity_failed')
            choices = value.get('choices')
            require(isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict),
                    'text_response_invalid')
            message = choices[0].get('message')
            content = message.get('content') if isinstance(message, dict) else None
            require(isinstance(content, str) and bool(content.strip()), 'text_response_empty')
            # Do not persist returned text (could contain paths/secrets); only nonempty/count evidence.
            item.update(nonempty=True, characters=len(content))
            result['text_windows'].append([start, end])


def concurrent_probes(key, started, result):
    try:
        require(started.wait(5), 'generation_start_not_observed')
        asyncio.run(asyncio.wait_for(text_probe_pair(key, result), timeout=60))
    except Exception:
        result.update(status='PARTIAL', failure_code='concurrent_probe_failed_sanitized')



def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('read', 'invalid', 'generate', 'reject-edit', 'busy'))
    p.add_argument('--receipt', help='Secret-free receipt projection specified in COMMANDS.md')
    p.add_argument('--receipt-sha256', help='Coordinator-reviewed SHA256 of that exact receipt file')
    keys = p.add_mutually_exclusive_group()
    keys.add_argument('--remote-key', action='store_true', help='Receipt-confirmed ai-vm protected key to memory; live only')
    keys.add_argument('--key-file', help='Existing protected Worker2 key path supplied by coordinator; never key value')
    p.add_argument('--live-authorized', action='store_true', help='Use only after explicit current live authorization')
    p.add_argument('--image-owner-handoff', action='store_true', help='Current exclusive window required for generation/reject-edit')
    return p


def gate(args):
    require(args.live_authorized, 'live_authorization_required')
    require(args.receipt and args.receipt_sha256 and (args.key_file or args.remote_key), 'receipt_and_existing_key_path_required')
    require(args.mode not in ('generate', 'reject-edit') or args.image_owner_handoff, 'image_ownership_handoff_required')


def main(argv=None):
    os.umask(0o077)
    logging.disable(logging.CRITICAL)  # Suppress dependency/debug logging, including inherited configuration.
    args = parser().parse_args(argv)
    result = {'mode': args.mode, 'source_commit': SOURCE, 'status': 'NOT_TESTED', 'checks': []}
    session = None
    evidence = None
    exit_code = 1
    try:
        gate(args)  # Before receipt/key reads, evidence writes or HTTP client construction.
        receipt = load_receipt(args.receipt, args.receipt_sha256)
        receipt['receipt_sha256'] = args.receipt_sha256
        result['receipt_sha256'] = args.receipt_sha256
        evidence = evidence_dir()
        if args.mode == 'generate':
            op = 'generation'
            require(not (evidence / ('baseline-' + op + '.attempt.json')).exists(), 'prior_attempt_stop_no_retry')
        session = Session(load_key(args, receipt), receipt, result['checks'])
        result['status'] = run_mode(session, args.mode, evidence)
        exit_code = 0
    except Stop as exc:
        result.update(status='NOT_TESTED' if session is None else 'PARTIAL', failure_code=exc.args[0])
    except KeyboardInterrupt:
        result.update(status='PARTIAL', failure_code='interrupted_outcome_unknown_stop_report_no_retry')
    except Exception:
        result.update(status='NOT_TESTED' if session is None else 'PARTIAL',
                      failure_code='sanitized_client_failure_stop_report_no_retry')
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                result.update(status='PARTIAL', failure_code='client_close_failed_stop_report')
                exit_code = 1
        # Print summaries only; response bodies/header values/key paths never enter result.
        if evidence is not None:
            try:
                target = evidence / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '-' + args.mode + '.json')
                write_private(target, result)
            except Exception:
                result.update(status='PARTIAL', failure_code='evidence_write_failed_stop_report')
                exit_code = 1
        print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
