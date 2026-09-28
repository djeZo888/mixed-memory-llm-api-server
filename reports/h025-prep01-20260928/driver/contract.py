"""H025 fixed offline preparation contract. No transport, credential or shell access."""
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from urllib.parse import urlsplit

LANES = ('flash', 'qwen0', 'qwen1', 'image')
TEXT = LANES[:3]
SCHEMA = 'h025-thermal-v1'
OWNER_ABI = 'h025-reviewed-owner-v1'
SHA = re.compile(r'^[0-9a-f]{64}$')
UUID = re.compile(r'^GPU-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$')

class Refusal(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise Refusal(message)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def utc_seconds(value):
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(dt.tzinfo is not None, 'UTC timezone required')
        require(dt.utcoffset().total_seconds() == 0, 'UTC required')
        return dt.timestamp()
    except (TypeError, AttributeError, ValueError) as exc:
        raise Refusal('invalid UTC timestamp') from exc

def number(value):
    return type(value) in (int, float) and math.isfinite(value)

def nonempty(value):
    return isinstance(value, str) and bool(value.strip()) and not any(
        word in value.upper() for word in ('REQUIRED', 'PLACEHOLDER', 'UNKNOWN', 'TODO', 'EXAMPLE'))

def sha(value):
    require(isinstance(value, str) and SHA.fullmatch(value), 'sha256 required')

def validate_manifest(m):
    """Required shape + closed policy. Pins are data, never executable commands."""
    require(m.get('schema') == SCHEMA and m.get('task_id', '').startswith('H025-'), 'H025 schema/task required')
    require(m.get('review_state') == 'REVIEWED_CURRENT', 'placeholder/unreviewed deployment refused')
    require(m.get('owner_abi') == OWNER_ABI, 'missing reviewed owner contract')
    require(nonempty(m.get('boot_id')) and nonempty(m.get('deployment_id')), 'fresh boot/deployment required')
    utc_seconds(m['captured_utc'])
    sha(m['deployment_manifest_sha256'])
    sha(m['owner_adapter_sha256'])
    require(m.get('source_sha256'), 'source pins required')
    for path, value in m['source_sha256'].items():
        require(path.startswith('/') and '..' not in path.split('/'), 'absolute exact source path required')
        sha(value)
    require(set(m.get('lanes', {})) == set(LANES), 'all four lanes required')
    uuids = []
    for name, lane in m['lanes'].items():
        require(UUID.fullmatch(lane.get('gpu_uuid', '')), 'exact GPU UUID required')
        uuids.append(lane['gpu_uuid'])
        require(nonempty(lane.get('gpu_type')), 'GPU type required')
        require(lane.get('gpu_family') == ('Ada' if name == 'image' else 'Blackwell'), 'GPU family mismatch')
        require(nonempty(lane.get('model')) and nonempty(lane.get('runtime')), 'runtime/model required')
        endpoint = urlsplit(lane.get('endpoint', ''))
        require(endpoint.scheme in ('http', 'https') and endpoint.hostname and endpoint.port,
                'exact endpoint required')
        require(not endpoint.username and not endpoint.password and not endpoint.query and not endpoint.fragment
                and endpoint.path in ('', '/'), 'endpoint must not contain secrets/path')
        if name == 'flash':
            require(endpoint.port == 30010 and endpoint.hostname == '127.0.0.1'
                    and lane['model'] == 'glm-5.3-flash', 'retained GLM native endpoint required')
        require(nonempty(lane.get('auth_ref')), 'private auth reference required; never credential')
        required_identity = ('container', 'owner_state', 'config_sha256') if name == 'flash' else ('container', 'generation', 'runtime_profile') if name.startswith('qwen') else ('container', 'run_id')
        require(lane.get('identity') and all(lane['identity'].get(k) for k in required_identity), 'current lane-specific identity required')
        require(lane.get('owner_contract') and all(nonempty(lane['owner_contract'].get(k)) for k in
                ('claim', 'preflight', 'settlement', 'stop_exact')), 'source-backed owner contract required')
        sha(lane['owner_contract']['source_sha256'])
        require(lane['owner_contract'].get('lane_local_stop') is True, 'broad stop forbidden')
        require(lane['owner_contract'].get('authenticated_native_proof') is True, 'physical owner proof required')
        for key in ('power_limit_w', 'reserve_mib', 'critical_c'):
            require(number(lane.get(key)) and lane[key] > 0, 'positive '+key+' required')
        require(lane.get('ecc_current') in ('Enabled', 'Disabled') and
                lane.get('ecc_pending') in ('Enabled', 'Disabled'), 'ECC baseline required')
        if name in TEXT:
            require(lane.get('context_tokens') == (1048576 if name == 'flash' else 480000), 'context policy drift')
            require((lane.get('output_ceiling') == 65536 if name == 'flash' else
                     type(lane.get('output_ceiling')) is int and lane['output_ceiling'] >= 128), 'configured output ceiling required')
            require(lane.get('count_path') == ('/v1/tokenize' if name == 'flash' else lane.get('count_path'))
                    and nonempty(lane.get('count_path')) and lane['count_path'].startswith('/'), 'native count endpoint required')
            require(lane.get('count_field') in ('input_tokens', 'count', 'prompt_tokens'), 'native count field required')
            if name.startswith('qwen'):
                require(lane['count_path']=='/v1/tokenize' and lane['count_field']=='count','native Qwen tokenize required')
                sha(lane['template_sha256'])
            if name == 'flash':
                require(lane['count_field'] == 'count', 'GLM native count required')
            require(lane.get('request_path') == '/v1/chat/completions', 'text endpoint required')
        else:
            require(lane.get('request_path') == '/v1/images/generations', 'image endpoint required')
            require(lane.get('native_defaults') == {'steps': 40, 'guidance': 1, 'shift': 1}, 'approved image 40/1/1 required')
            require(nonempty(lane['owner_contract'].get('spool_cleanup')), 'approved owned spool cleanup required')
        require(not any(k in lane for k in ('command', 'shell', 'rpc', 'token', 'authorization')), 'executable/credential configuration forbidden')
    require(len(set(uuids)) == 4, 'duplicate GPU UUID')
    bounds = m.get('bounds', {})
    require(bounds.get('B') == {'admission_seconds': 300}, 'phase B bounds')
    for key, cap in (('settlement_seconds', 1020), ('request_seconds', 900), ('max_requests_per_lane', 1000)):
        require(type(bounds.get(key)) is int and 1 <= bounds[key] <= cap, 'finite '+key+' required')
    require(bounds['request_seconds'] == 900 and bounds['settlement_seconds'] >= 960, '900s request plus finite stop reserve required')
    require(m.get('workload') == {'flash_input_range': [16000, 16384], 'qwen_input_range': [4096, 16384],
            'max_output_tokens': 128, 'image_size': '1920x1080', 'image_n': 1}, 'workload drift')
    guard = m.get('guard', {})
    require(guard.get('temperature_c') == 85 and guard.get('sample_period_seconds') == 1, 'guard policy drift')
    require(number(guard.get('max_sample_delay_seconds')) and 1 <= guard['max_sample_delay_seconds'] <= 5,
            'bounded telemetry freshness required')
    require(number(guard.get('min_guest_ram_fraction')) and .15 <= guard['min_guest_ram_fraction'] <= 1,
            'guest reserve floor required')
    fan = m.get('external_fan', {})
    require(fan == {'header':'CHA_FAN3','zone':4,'pwm':3,'low_percent':40,'high_percent':80,
                   'low_c':65,'high_c':70,'driver_writes':False}, 'reviewed H025 fan policy required')
    require(m.get('fan_status_path','').startswith('/data/logs/H025-') and
            '..' not in m['fan_status_path'].split('/'), 'task-owned fan mirror required')
    require(m.get('fan_controller') and m['fan_controller'].get('idle_actuator_result')=='PASS', 'reviewed idle fan actuator required')
    for key in ('source_sha256','invariant_sha256','idle_actuator_receipt_sha256'):sha(m['fan_controller'][key])
    require(m.get('power_writes') is False, 'power changes forbidden')
    return m

def validate_go(go, m, phase, package_sha256, now_utc):
    validate_manifest(m)
    require(phase == 'B', 'one separate phase required')
    require(go.get('action') == 'ROOT GO H025 PHASE '+phase and go.get('phase') == phase,
            'latest root policy requires one separate grant per phase')
    require('phases' not in go, 'automatic batch progression forbidden')
    require(go.get('task_id') == m['task_id'] and go.get('deployment_sha256') == digest(m), 'GO deployment mismatch')
    require(go.get('package_sha256') == package_sha256, 'GO source mismatch')
    sha(package_sha256)
    require(go.get('boot_id') == m['boot_id'] and nonempty(go.get('go_id')), 'GO current boot/id required')
    now = utc_seconds(now_utc)
    require(utc_seconds(go['not_before_utc']) <= now < utc_seconds(go['admission_deadline_utc']), 'GO expired/not yet valid')
    require(0 < utc_seconds(go['admission_deadline_utc']) - utc_seconds(go['not_before_utc']) <= 390,
            'GO preparation plus admission window exceeds390s bound')
    require(utc_seconds(go['admission_deadline_utc'])<=utc_seconds('2026-09-28T20:05:00Z') and utc_seconds(go['settlement_deadline_utc'])<=utc_seconds('2026-09-28T20:20:00Z'),'H025 absolute cutoff')
    require(utc_seconds(go['admission_deadline_utc']) < utc_seconds(go['settlement_deadline_utc']) <=
            utc_seconds(go['admission_deadline_utc']) + m['bounds']['settlement_seconds'], 'GO settlement bound')
    require(utc_seconds(go['settlement_deadline_utc'])-utc_seconds(go['admission_deadline_utc']) >= m['bounds']['request_seconds']+60,
            'full request and settlement reserve after admission required')
    require(go.get('quiet_confirmed') is True and nonempty(go.get('global_admission_receipt')),
            'current global ownership/quiet receipt required')
    return go

def text_body(m, lane, prefix, text, max_tokens=128):
    require(lane in TEXT and nonempty(prefix) and isinstance(text, str) and text, 'fresh text input required')
    require(type(max_tokens) is int and 1 <= max_tokens <= 128, 'short output required')
    body = {'model': m['lanes'][lane]['model'], 'messages': [{'role': 'user', 'content': prefix+'\n'+text}],
            'max_tokens': max_tokens, 'stream': True, 'stream_options': {'include_usage': True},
            'chat_template_kwargs': {'enable_thinking': False}}
    if lane == 'flash':
        body.update(reasoning_effort='high',chat_template_kwargs={'clear_thinking':True})
    return body

def image_body(m, prefix):
    require(nonempty(prefix), 'fresh image prefix required')
    return {'model': m['lanes']['image']['model'], 'prompt': prefix+' A wide alpine lake landscape, autumn light, no text.',
            'size': '1920x1080', 'n': 1, 'response_format': 'b64_json'}

def validate_body(m, lane, body, prefix):
    if lane in TEXT:
        require(set(body) == set(text_body(m, lane, prefix, 'x', body.get('max_tokens', 0))), 'unexpected text body fields')
        require(len(body.get('messages', [])) == 1 and body['messages'][0].get('role') == 'user', 'canonical messages required')
        content = body['messages'][0].get('content', '')
        require(content.startswith(prefix+'\n') and len(content) > len(prefix)+1, 'fresh varied prefix must lead request')
        expected = text_body(m, lane, prefix, content[len(prefix)+1:], body['max_tokens'])
        require(body == expected, 'canonical text body mismatch')
    else:
        require(body == image_body(m, prefix), 'canonical image body mismatch')
    return canonical(body)

def validate_count(m, lane, body_hash, result):
    require(result.get('body_sha256') == body_hash and result.get('native') is True
            and result.get('http_status') == 200, 'native canonical-body count required')
    require(result.get('endpoint') == m['lanes'][lane]['count_path'], 'native count route mismatch')
    field = m['lanes'][lane]['count_field']
    count = result.get('response', {}).get(field)
    low, high = m['workload']['flash_input_range' if lane == 'flash' else 'qwen_input_range']
    require(type(count) is int and low <= count <= high, 'native count outside occupied range; no estimate/fallback')
    return count
