"""Read-only canonical owner identities and passive authenticated readiness.

No Manager.status, control GET/reconcile, image owner.probe, native health, or
writes occur here. Identity generations exclude readiness, activity and metrics.
Only fixed registered paths, unit names, UUIDs and native routes are reachable.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import math
from pathlib import Path
import re
import socket
import threading
import time

from .installation import protected_file, _key, InstallationError
from .node import BOOT, SERVICES, LEGACY_TARGETS, negative_hardware_current, required_gpus
from .node_collectors import boot_identity, command

HEX = re.compile(r'[0-9a-f]{64}\Z')
DEPLOYMENTS = {
    'qwen38-27b-q0-480000-yarn4-bf16kv': ('qwen-gpu0', 'qwen3.8-27b-gpu0', 30002),
    'qwen38-27b-q1-server-480000-yarn4-bf16kv': ('qwen-gpu1', 'qwen3.8-27b', 30004),
    'glm-5.3-ud-q4-k-xl-g1-480000': ('qwen-gpu0', 'glm-5.3', 30002),
}
TEXT_OWNER = 'mixed-memory-llm-api-server'
IMAGE_OWNER = 'IMAGE21-RUNTIME-20260923'
IMAGE_ALIAS = 'qwen-image-2.1'
IMAGE_RUNTIME = '0cd8be351d0825488f4b81c8931167bbab618eca'
IMAGE_REVISION = '790c92633540aa0cb11d9abf19eb46d861714758'
PROFILE_ROOT = Path('/usr/local/lib/llm-server/node-api/configs/deployments')
UNITS = {'control': 'llm-control.service', 'image': 'llm-image-api.service',
         'node': 'llm-node.service', 'mimo': 'llm-frontier-mimo.service'}
MIMO = 'mimo-v2.6-pro-rl'
MIMO_BASE = '/data/services/mimo-h016-20260927'
MIMO_OWNER = 'H016-MIMO-PERSISTENT-20260927'
MIMO_IMAGE = 'sha256:cdb6efd75f53a8b453f866f30511b0f5c8d19440d3adaaf419e97bde1c2bf21e'
MIMO_REVISION = 'ba4eabb78b6c51ffd873ec73b9e12b0f64aced5d'
MIMO_TEMPLATE = '16b2dac352c6cf1aef8b0a976618c76deb28c5bf3aba4c8b788fb846aa3769a4'
MIMO_BUILD = 'b1-7ac59a6'
MIMO_MODEL_PATH = '/models/MXFP4/MiMo-V2.6-Pro-RL-MXFP4-00001-of-00013.gguf'
# Exact historical 480K and pending H013 1M source identities, not qualification.
# Publish capacity only after authenticated native allocation agrees below.
FLASH_CONTEXT_SOURCES = {
    480000: {
        'file_auth.py': '841e7968e89504fd4f03210476423a49e2145c9d2b7cc4d7d32fc65a780405b8',
        'tokenize_adapter.py': '31273f8be764a526f62da55e0038b87cb90fef7b05468de184e840ca4d6eec55',
        'idle.py': '030037024701cacf1f0accff8edb273cd7d1c290df53f87077fb740aec38638b',
    },
    1048576: {
        'file_auth.py': '5cad2c509e5c82cd7162f7a10ded2d08c4af768a20dbb9d8ddafb9a49fa5ecbb',
        'tokenize_adapter.py': 'f5f863fd41732a7e56cb73e883471572819ac4554b687befd8e6205006509386',
        'idle.py': '3fd14b64793b79d97da179c98606c1f9b58a05420fe3eb01096d0301e63086e4',
    },
}
FLASH_COMMON_SOURCES = {
    'owner.py': 'd4a628876b8643a01277039ab744e87a2218e3b87e2c6207e2d67816b570a4b1',
    'tool_runtime.py': 'bd44a5a2970bfe5cc4c789b526a6b8b605b7bfb0d4a650da83adc0a43ac346fa',
    'native-source-pins.json': 'b5fab69c0466d61adda5ea02494e87bab61beff2bc0194f28b3ac4aa7d77f195',
    'numa-seccomp.json': '835759ce29944318d0a8de36cc62940e79125a15eedec3448fde1edd3fa320bf',
}


def flash_source_context(config, read):
    from runtime.flash.owner import BASE
    manifest = config.get('source_sha256', {})
    names = {'file_auth.py', 'tokenize_adapter.py', 'idle.py', 'owner.py',
             'tool_runtime.py', 'native-source-pins.json', 'numa-seccomp.json'}
    if type(manifest) is not dict or set(manifest) != names:
        raise ValueError('frontier_source_manifest_unknown')
    if any(manifest[name] != digest for name, digest in FLASH_COMMON_SOURCES.items()):
        raise ValueError('frontier_common_source_unknown')
    for name, digest in manifest.items():
        if (type(digest) is not str or not HEX.fullmatch(digest)
                or hashlib.sha256(read(Path(BASE) / 'source' / name,
                    modes={0o644}, maximum=1024*1024)).hexdigest() != digest):
            raise ValueError('frontier_source_identity_changed')
    for context, pins in FLASH_CONTEXT_SOURCES.items():
        if all(manifest[name] == digest for name, digest in pins.items()):
            return context
    raise ValueError('frontier_context_source_unknown')


def flash_native_context(code, value, context):
    if code != 200 or type(context) is not int or context not in FLASH_CONTEXT_SOURCES or type(value) is not dict:
        raise ValueError('frontier_native_capacity_unknown')
    states = value.get('internal_states', [])
    if type(states) is not list or any(type(row) is not dict for row in states):
        raise ValueError('frontier_native_capacity_unknown')
    expected = {'context_length': context, 'max_total_tokens': context,
                'max_total_num_tokens': context, 'max_req_input_len': context - 6}
    for field, expected_value in expected.items():
        values = [row[field] for row in [value, *states] if field in row]
        if not values or any(type(v) is not int or v != expected_value for v in values):
            raise ValueError('frontier_native_capacity_mismatch')
    return {'configured_context_tokens': context,
            'deployment_id': 'glm-5.3-flash-' + str(context) + '-fp8-kt'}


def generation(value):
    """Deterministic JSON-safe CAS token derived only from canonical semantics."""
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:7], 'big') >> 3


def canonical_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def mimo_native_readiness(props_response, slots_response, manifest):
    """Native allocation agrees with a protected qualification of this invocation.

    Plain /slots is the debug-OFF route. Slot activity never proves GPU idle or
    releases a quarantined request lane; the control DTO leaves admission null.
    """
    code, props = props_response
    slot_code, slots = slots_response
    if (code != 200 or type(props) is not dict or props.get('model_alias') != MIMO
            or props.get('is_sleeping') is not False
            or props.get('build_info') != manifest.get('build_info')
            or props.get('model_path') != manifest.get('model_path')
            or type(props.get('chat_template')) is not str
            or hashlib.sha256(props['chat_template'].encode()).hexdigest() != manifest.get('template_sha256')
            or type(props.get('total_slots')) is not int or props['total_slots'] != 1
            or type(props.get('default_generation_settings')) is not dict
            or type(props['default_generation_settings'].get('n_ctx')) is not int
            or props['default_generation_settings']['n_ctx'] != manifest.get('context')
            or slot_code != 200 or type(slots) is not list or len(slots) != 1
            or type(slots[0]) is not dict or type(slots[0].get('id')) is not int
            or slots[0]['id'] != manifest.get('slot_id')
            or type(slots[0].get('n_ctx')) is not int or slots[0]['n_ctx'] != manifest.get('context')
            or type(slots[0].get('is_processing')) is not bool
            or slots[0].get('speculative') is not False or 'prompt' in slots[0] or 'generated' in slots[0]
            or any(props.get('modalities', {}).get(k) is not False for k in ('vision', 'video', 'audio'))
            or (None if 'chat_template_tool_use' not in props else
                hashlib.sha256(props['chat_template_tool_use'].encode()).hexdigest()
                if type(props['chat_template_tool_use']) is str else 'invalid') != manifest.get('tool_template_sha256')):
        raise ValueError('mimo_native_identity_or_capacity_unknown')
    return {'ready': True, 'admitting': None, 'reason': None, 'activity': 'unknown',
            'configured_context_tokens': manifest['context'],
            'deployment_id': 'mimo-v2.6-pro-rl-' + str(manifest['context']) + '-mxfp4'}


def strict_json(raw):
    def pairs(items):
        value = {}
        for key, entry in items:
            if key in value:
                raise ValueError('duplicate_key')
            value[key] = entry
        return value
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


def native_get(port, path, key, seconds):
    if (port, path) not in ((30002, '/v1/readiness'), (30004, '/v1/readiness'),
                            (30010, '/v1/readiness'), (30010, '/get_server_info'),
                            (30012, '/props'), (30012, '/slots'),
                            (30014, '/v1/readiness'), (30014, '/get_server_info'),
                            (30006, '/v1/image-capabilities'), (30000, '/control/v1/readiness')):
        raise ValueError('unregistered_passive_route')
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=max(.001, seconds))
    deadline = time.monotonic() + seconds
    timer = None
    try:
        conn.connect()
        connected_socket = conn.sock
        def expire():
            try:
                connected_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        timer = threading.Timer(max(0, deadline - time.monotonic()), expire)
        timer.daemon = True
        timer.start()
        conn.request('GET', path, headers={'Authorization': 'Bearer ' + key.decode('ascii'),
                                         'Connection': 'close'})
        response = conn.getresponse()
        if response.status not in (200, 503):
            raise ValueError('passive_auth_or_route_failure')
        body = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            # Socket timeout alone is not a whole-body deadline on trickled bytes.
            if conn.sock is not None:
                conn.sock.settimeout(remaining)
            chunk = response.read1(min(4096, 65537 - len(body)))
            if not chunk:
                break
            body.extend(chunk)
            if len(body) > 65536:
                raise ValueError('passive_body_limit')
        return response.status, strict_json(body)
    finally:
        if timer is not None:
            timer.cancel()
            timer.join()
        conn.close()


def control_readiness(code, value, identity):
    """Accept only the supported passive API response from this native unit."""
    unit = identity.get('unit_identity', {})
    if (code != 200 or type(value) is not dict or set(value) != {
            'schema_version', 'service_id', 'readiness_kind', 'ready',
            'boot_id', 'invocation_id', 'main_pid'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or value['service_id'] != 'control' or value['readiness_kind'] != 'process_api'
            or value['ready'] is not True
            or type(value['boot_id']) is not str or not BOOT.fullmatch(value['boot_id'])
            or value['boot_id'] != identity.get('boot_id')
            or type(value['invocation_id']) is not str or not re.fullmatch('[0-9a-f]{32}', value['invocation_id'])
            or value['invocation_id'] != unit.get('InvocationID')
            or type(value['main_pid']) is not int or value['main_pid'] <= 0
            or str(value['main_pid']) != unit.get('MainPID')
            or unit.get('Id') != UNITS['control'] or unit.get('ActiveState') not in ('active', 'reloading')
            or identity.get('ownership_valid') is not True):
        raise ValueError('invalid_passive_control_readiness')
    return {'ready': True, 'admitting': None, 'activity': 'unknown', 'reason': None}


def text_readiness(code, value, alias):
    if (type(value) is not dict or set(value) != {'schema_version', 'model_alias', 'ready', 'state', 'admitting'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or value['model_alias'] != alias or type(value['ready']) is not bool
            or value['state'] not in ('starting', 'up', 'unhealthy', 'unknown')
            or value['admitting'] is not None
            or value['ready'] != (value['state'] == 'up')
            or code != (200 if value['ready'] else 503)):
        raise ValueError('invalid_passive_readiness')
    return {'ready': value['ready'], 'admitting': None, 'activity': 'unknown',
            'reason': None if value['ready'] else
                ('service_starting' if value['state'] == 'starting' else 'readiness_unknown')}


def profiles(value):
    if type(value) is not list or len(value) > 32:
        raise ValueError('invalid_installed_profiles')
    result = []
    for p in value:
        if (type(p) is not dict or p.get('operation') not in ('generation', 'edit')
                or p.get('size') not in ('1024x1024', '1024x576', '1216x704', '1472x832',
                                       '1760x992', '1920x1080', '1536x864')
                or type(p.get('references')) is not int or not 0 <= p['references'] <= 2
                or p.get('transparent') is not False
                or p['references'] not in ((0,) if p.get('operation') == 'generation' else (1, 2))
                or type(p.get('evidence_sha256')) is not str or not HEX.fullmatch(p['evidence_sha256'])):
            raise ValueError('invalid_installed_profiles')
        if p['size'] == '1920x1080':
            if (p.get('native_size') != '1920x1088' or p.get('crop_bottom') != 8
                    or p['references'] not in ((0,) if p['operation'] == 'generation' else (1,))):
                raise ValueError('invalid_installed_geometry')
        elif p.get('native_size', p['size']) != p['size'] or p.get('crop_bottom', 0) != 0:
            raise ValueError('invalid_installed_geometry')
        row = {key: p[key] for key in ('operation', 'size', 'references', 'transparent')}
        if row in result:
            raise ValueError('duplicate_installed_profile')
        result.append(row)
    return result


def image_readiness(code, value):
    if (code != 200 or type(value) is not dict or value.get('model') != IMAGE_ALIAS
            or any(type(value.get(k)) is not bool for k in ('ready', 'admitting', 'busy'))
            or value.get('state') not in ('startup', 'ready', 'recovering', 'closed', 'unqualified')
            or value['admitting'] != (value['ready'] and not value['busy'])):
        raise ValueError('invalid_passive_image_status')
    return {'ready': value['ready'], 'admitting': value['admitting'],
            'activity': 'busy' if value['busy'] else 'unknown',
            'active_requests': 1 if value['busy'] else None,
            'reason': 'service_busy' if value['ready'] and value['busy'] else
                (None if value['ready'] else 'readiness_unknown')}


def production_binding(seconds):
    from lifecycle.storage_binding import RegisteredStorageBinding
    from lifecycle.manager import StorageRunner
    deadline = time.monotonic() + seconds
    class BoundedRunner(StorageRunner):
        def run(self, argv, **kwargs):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('observation_deadline')
            kwargs['timeout'] = min(kwargs.get('timeout', remaining), remaining)
            return super().run(argv, **kwargs)
    return RegisteredStorageBinding.read_registered(BoundedRunner())


def production_latch(binding, uuids):
    from lifecycle.hardware_policy import read_latch_status
    return read_latch_status(binding, uuids, current_boot_id=boot_identity()['boot_id'])


class CanonicalIdentityReader:
    def __init__(self, *, run=command, boot=boot_identity, binding=production_binding,
                 latch=production_latch, read=protected_file, clock=time.monotonic):
        self.run, self.boot, self.binding, self.latch, self.read, self.clock = run, boot, binding, latch, read, clock

    def _unit(self, service_id, seconds):
        value = self.run(['/usr/bin/systemctl', 'show', UNITS[service_id],
            '--property=Id,ActiveState,SubState,InvocationID,MainPID'], seconds)
        raw = dict(line.split('=', 1) for line in value.strip().splitlines())
        if (raw.get('Id') != UNITS[service_id] or raw.get('ActiveState') not in
                ('active', 'inactive', 'failed', 'activating', 'deactivating', 'reloading')
                or not re.fullmatch('[0-9a-f]{0,32}', raw.get('InvocationID', ''))
                or not re.fullmatch('[0-9]+', raw.get('MainPID', ''))):
            raise ValueError('unit_identity_unknown')
        return {k: raw[k] for k in ('Id', 'ActiveState', 'InvocationID', 'MainPID')}

    def _container(self, identity, seconds, labels):
        if (type(identity) is not dict or type(identity.get('id')) is not str or not HEX.fullmatch(identity['id'])
                or type(identity.get('image_id')) is not str or not re.fullmatch('sha256:[0-9a-f]{64}', identity['image_id'])
                or type(identity.get('name')) is not str or not re.fullmatch('[a-zA-Z0-9_.-]{1,128}', identity['name'])):
            raise ValueError('container_identity_unknown')
        if any(type(value) is not str or not value or len(value) > 128 for value in labels.values()):
            raise ValueError('container_owner_labels_unknown')
        # Only selected labels and process facts, never full inspect or Config.Env.
        fields = ['.Id', '.Name', '.Image', '.State.Running', '.State.StartedAt', '.State.Pid']
        template = '[' + ','.join('{{json ' + field + '}}' for field in fields)
        for label in labels:
            template += ',{{json (index .Config.Labels "' + label + '")}}'
        template += ']'
        values = strict_json(self.run(['/usr/bin/docker', 'inspect', '--format', template, identity['id']], seconds))
        if (type(values) is not list or len(values) != 6 + len(labels)
                or values[:3] != [identity['id'], '/' + identity['name'], identity['image_id']]
                or type(values[3]) is not bool or type(values[4]) is not str or not 1 <= len(values[4]) <= 128
                or type(values[5]) is not int or values[5] < 0
                or (values[3] and values[5] == 0) or (not values[3] and values[5] != 0)
                or values[6:] != list(labels.values())):
            raise ValueError('container_ownership_unknown')
        return {'container_id': values[0], 'running': values[3], 'started_at': values[4], 'pid': values[5], 'run_id': None}

    def service(self, service_id, seconds=2):
        # Keep independently read positive hardware evidence even if a process
        # or metadata observation fails. An unproven identity never gets a CAS.
        result = {}
        try:
            return self._service(service_id, seconds, result)
        except Exception as error:
            if not result:
                result = {'boot_id': None, 'hardware_latched': None,
                          'hardware_latched_boot_id': None}
            # Failure can occur after a slow process/metadata read. The success
            # path's age accounting did not run, so this old negative proof
            # must not be published with a newly fresh outer observation.
            if result.get('hardware_latched') is False:
                result['hardware_latched'] = None
            result.update(generation=None, ownership_valid=False, running=None,
                backend_running=None, ready=False if result.get('hardware_latched') is True else None,
                admitting=False if result.get('hardware_latched') is True else None,
                activity='unknown', queue_depth=None, active_requests=None)
            if result.get('hardware_latched') is not True:
                result['reason'] = 'observation_unavailable'
            if service_id == 'image' and error.args and error.args[0] == 'image_selection_changed':
                result.pop('imageGPU', None)
            return result

    def _absent(self, name, seconds):
        raw = self.run(['/usr/bin/docker', 'container', 'ls', '--all', '--no-trunc',
                        '--filter', 'name=^/' + name + '$', '--format', '{{.ID}}'], seconds)
        if raw.strip():
            raise ValueError('unrecorded_owner_container')

    def _mimo(self, binding, boot_id, remaining, result):
        manifest = binding.read_json('services', MIMO_BASE + '/manifest.json')
        state = binding.read_json('services', MIMO_BASE + '/state.json')
        guard = binding.read_json('services', MIMO_BASE + '/guard.json')
        selection = result['frontier_selection']
        digest = canonical_sha256(manifest)
        native = state.get('native', {})
        if (manifest.get('schema_version') != 2 or manifest.get('owner') != MIMO_OWNER
                or manifest.get('service_id') != MIMO or manifest.get('qualified') is not True
                or manifest.get('required_gpu_uuids') != list(SERVICES[MIMO])
                or manifest.get('image_id') != MIMO_IMAGE or manifest.get('model_revision') != MIMO_REVISION
                or type(manifest.get('context')) is not int or not 65536 < manifest['context'] <= 1048576
                or manifest.get('parallel') != 1 or manifest.get('slot_id') != 0
                or manifest.get('template_sha256') != MIMO_TEMPLATE
                or manifest.get('build_info') != MIMO_BUILD or manifest.get('model_path') != MIMO_MODEL_PATH
                or state.get('schema_version') != 2 or state.get('status') != 'RUNNING'
                or state.get('manifest_sha256') != digest or state.get('boot_id') != boot_id
                or selection.get('manifest_sha256') != digest or state.get('selection') != selection
                or type(native) is not dict or native.get('image_id') != MIMO_IMAGE
                or native.get('name') != manifest.get('container_name')
                or type(native.get('pid')) is not int or native['pid'] <= 0
                or type(native.get('pid_start_ticks')) is not str
                or not re.fullmatch('[0-9]+', native['pid_start_ticks'])):
            raise ValueError('mimo_qualification_unknown')
        owner = self._container({'id': native.get('container_id'), 'image_id': MIMO_IMAGE,
            'name': manifest['container_name']}, remaining(), {'io.h016.owner': MIMO_OWNER,
            'io.h016.manifest': digest, 'io.h016.launch': state['launch_id']})
        if (not owner['running'] or owner['pid'] != native['pid'] or owner['started_at'] != native.get('started_at')):
            raise ValueError('mimo_native_invocation_changed')
        proc = self.run(['/usr/bin/cat', '/proc/' + str(native['pid']) + '/stat'], remaining())
        if proc.rsplit(')', 1)[-1].split()[19] != native['pid_start_ticks']:
            raise ValueError('mimo_native_pid_reused')
        supervisor = state.get('supervisor', {})
        unit = self._unit('mimo', remaining())
        if (supervisor.get('unit') != UNITS['mimo'] or unit['ActiveState'] != 'active'
                or unit['MainPID'] != str(supervisor.get('pid'))
                or unit['InvocationID'] != supervisor.get('invocation_id')
                or guard.get('supervisor') != supervisor):
            raise ValueError('mimo_supervision_unknown')
        child = state.get('proxy', {})
        proxy = guard.get('proxy_disposition') or {}
        observed = guard.get('observed_monotonic_s')
        if (guard.get('schema_version') != 2 or guard.get('status') != 'ok'
                or guard.get('boot_id') != boot_id or guard.get('manifest_sha256') != digest
                or guard.get('selection') != selection or guard.get('native') != native
                or guard.get('hardware_latched') is not False or guard.get('proxy') != child
                or type(observed) not in (int, float) or not math.isfinite(observed)
                or not 0 <= self.clock() - observed <= 15
                or proxy.get('schema_version') != 2 or proxy.get('boot_id') != boot_id
                or proxy.get('native') != native or proxy.get('launch_id') != state.get('launch_id')
                or child.get('parent_pid') != supervisor.get('pid')
                or any(proxy.get(k) != child.get(k) for k in ('pid', 'pid_start_ticks', 'parent_pid'))
                or type(child.get('pid')) is not int or child['pid'] <= 0
                or type(proxy.get('active_requests')) is not int or proxy['active_requests'] not in (0, 1)
                or type(proxy.get('quarantined')) is not bool):
            raise ValueError('mimo_guard_or_proxy_unknown')
        proc = self.run(['/usr/bin/cat', '/proc/' + str(child['pid']) + '/stat'], remaining()).rsplit(')', 1)[-1].split()
        if proc[19] != child['pid_start_ticks'] or proc[1] != str(supervisor['pid']):
            raise ValueError('mimo_proxy_child_changed')
        result.update(selected=MIMO, model_alias=MIMO, max_output_tokens=65536,
            configured_context_tokens=None, deployment_id=None, installed_capabilities=['chat.completions'],
            owner_identity=owner, running=True, ownership_valid=True, mimo_manifest=manifest,
            guard_age_ms=(self.clock() - observed) * 1000, guard_boot_id=boot_id,
            software_quarantined=proxy['quarantined'])
        if proxy['quarantined']:
            result.update(ready=False, admitting=False, reason='software_quarantine')
        return [digest, state, owner, proxy['quarantined']]

    def _service(self, service_id, seconds, result):
        if service_id not in SERVICES and service_id != 'node':
            raise ValueError('unregistered_service')
        boot = self.boot()
        deadline = self.clock() + seconds
        remaining = lambda: max(.001, deadline - self.clock())
        result.update({'service_id': service_id, 'boot_id': boot['boot_id'], 'ready': None, 'admitting': None,
            'activity': 'unknown', 'queue_depth': None, 'active_requests': None,
            'hardware_latched': None, 'hardware_latched_boot_id': None,
            'reason': 'observation_unavailable', 'generation': None,
            'ownership_valid': False, 'running': None, 'installed_capabilities': []})
        if service_id in ('control', 'node'):
            unit = self._unit(service_id, remaining())
            result.update(hardware_latched=False, ownership_valid=True,
                running=unit['ActiveState'] in ('active', 'reloading'),
                installed_capabilities=['model.control'] if service_id == 'control' else ['node.status'],
                generation=generation([boot['boot_id'], unit]), unit_identity=unit,
                main_pid=int(unit['MainPID']), invocation_id=unit['InvocationID'])
            if not result['running']:
                result.update(ready=False, admitting=False, reason='service_failed' if unit['ActiveState'] == 'failed' else 'service_stopped')
            return result
        binding = self.binding(remaining())
        required = SERVICES[service_id]
        if service_id == 'image':
            from lifecycle.runtime_io import image_gpu_uuid
            config_path = binding.path('services', 'image21-runtime-20260923/config.json')
            binding.validate_path('services', config_path)
            config_raw = self.read(Path(config_path), modes={0o600}, maximum=131072)
            runtime_config = strict_json(config_raw)
            if (type(runtime_config.get('schema_version')) is not int
                    or runtime_config['schema_version'] != 1 or runtime_config.get('owner') != IMAGE_OWNER
                    or binding.read_json('services', config_path) != runtime_config):
                raise ValueError('image_selection_unknown')
            required = (image_gpu_uuid(runtime_config),)
            result['imageGPU'] = dict(uuid=required[0],
                selectionConfigSha256=hashlib.sha256(config_raw).hexdigest(), bootId=boot['boot_id'])
        result.update(self.latch(binding, required))
        if service_id in (MIMO, 'glm-5.3-flash'):
            selection = binding.read_json('services', MIMO_BASE + '/selection.json')
            if (type(selection.get('schema_version')) is not int or selection['schema_version'] != 1
                    or selection.get('selected_frontier') not in (MIMO, 'glm-5.3-flash')
                    or type(selection.get('generation')) is not int or selection['generation'] <= 0):
                raise ValueError('frontier_selection_unknown')
            result['frontier_selection'] = selection
            result['frontier_selected'] = selection['selected_frontier'] == service_id
            if service_id == MIMO and not result['frontier_selected']:
                # A selected rollback is not proof that a dormant candidate is absent.
                result.update(model_alias=MIMO, ready=False, admitting=False, reason='unqualified')
                return result
        if service_id in LEGACY_TARGETS:
            state = binding.read_json('data', binding.path('data', 'services/llm-manager/active/active.json'))
            if state.get('schema_version') != 3 or set(state.get('slots', {})) != {'glm', 'qwen'}:
                raise ValueError('canonical_state_unknown')
            slot = state['slots'][LEGACY_TARGETS[service_id]]
            selected = slot.get('selected')
            if (selected not in DEPLOYMENTS or DEPLOYMENTS[selected][0] != service_id
                    or type(slot.get('generation')) is not int or slot['generation'] < 0
                    or slot.get('desired') not in ('running', 'stopped') or slot.get('pending_create') is not None):
                raise ValueError('canonical_selection_unknown')
            instance = binding.read_json('data', binding.path('data', 'services/llm-manager/deployment-instance.json'))
            identity = slot.get('container')
            owner = None
            if identity is not None:
                if (identity.get('owner') != TEXT_OWNER or identity.get('deployment') != selected
                        or identity.get('name') != 'llmctl-' + selected
                        or type(identity.get('instance')) is not str
                        or identity['instance'] != instance.get('id')):
                    raise ValueError('canonical_owner_unknown')
                owner = self._container(identity, remaining(), {
                    'io.llmctl.owner': TEXT_OWNER, 'io.llmctl.instance': identity.get('instance'),
                    'io.llmctl.deployment': selected})
            else:
                self._absent('llmctl-' + selected, remaining())
            result.update(selected=selected, deployment_id=selected, model_alias=DEPLOYMENTS[selected][1],
                canonical_generation=slot['generation'], configured_context_tokens=None,
                installed_capabilities=[], running=owner['running'] if owner else False,
                owner_identity=owner, ownership_valid=True)
            try:
                profile = strict_json(self.read(PROFILE_ROOT / (selected + '.json'), maximum=131072))
                if (profile.get('id') != selected or profile.get('container_name') != 'llmctl-' + selected
                        or profile.get('endpoint') != {'host':'127.0.0.1','port':DEPLOYMENTS[selected][2],
                            'api_prefix':'/v1','served_model':DEPLOYMENTS[selected][1]}
                        or profile.get('launch',{}).get('context_size') != 480000
                        or profile.get('launch',{}).get('gpus') != list(SERVICES[service_id])):
                    raise ValueError('installed_profile_unknown')
                result.update(configured_context_tokens=480000, installed_capabilities=['chat.completions'])
            except Exception:
                pass  # Owner stop remains observable even if installed profile metadata is unavailable.
            semantics = [slot['generation'], selected, slot['desired'], identity, owner]
        elif service_id == MIMO:
            semantics = self._mimo(binding, boot['boot_id'], remaining, result)
        elif service_id == 'glm-5.3-flash':
            from runtime.flash.owner import validate_container, BASE, NAME, OWNER, GPU
            state = binding.read_json('services', BASE + '/state.json')
            config = binding.read_json('services', BASE + '/config.json')
            identity = state.get('container')
            if state.get('owner') != OWNER or state.get('schema_version') != 1:
                raise ValueError('frontier_owner_unknown')
            owner = None
            if identity is not None:
                owner = self._container(identity, remaining(), {'io.llm-frontier.owner':OWNER,
                    'io.llm-frontier.gpu':GPU})
                raw = strict_json(self.run(['/usr/bin/docker','inspect',identity['id']],remaining()))
                validate_container(raw[0], config, state)
            else:
                self._absent(NAME, remaining())
            binding.validate_path('services', BASE + '/source')
            source_context = flash_source_context(config, self.read)
            result.update(selected='glm-5.3-flash', deployment_id=None,
                model_alias='glm-5.3-flash', configured_context_tokens=None, max_output_tokens=65536,
                source_context_tokens=source_context,
                installed_capabilities=['chat.completions'], owner_identity=owner,
                running=bool(owner and owner['running']), ownership_valid=True)
            semantics = [state, owner, config['source_sha256']]
        else:
            state = binding.read_json('services', binding.path('services', 'image21-runtime-20260923/state.json'))
            if state.get('schema_version') != 1 or state.get('owner') != IMAGE_OWNER:
                raise ValueError('image_owner_unknown')
            unit = self._unit('image', remaining())
            identity = state.get('container')
            owner = None
            if identity is not None:
                if (identity.get('image_id') != runtime_config.get('image_id')
                        or type(state.get('run_id')) is not str
                        or not re.fullmatch('[0-9a-f]{32}', state['run_id'])):
                    raise ValueError('image_config_ownership_unknown')
                owner = self._container({**identity, 'name': 'llm-image-backend'}, remaining(), {
                    'io.llm-image.owner': IMAGE_OWNER, 'io.llm-image.invocation': state.get('run_id'),
                    'io.llm-image.gpu': required[0]})
                from lifecycle.runtime_io import validate_image_container
                native = strict_json(self.run(['/usr/bin/docker', 'inspect', identity['id']], remaining()))
                if type(native) is not list or len(native) != 1:
                    raise ValueError('image_container_unknown')
                validate_image_container(native[0], state, runtime_config)
            else:
                self._absent('llm-image-backend', remaining())
            config = strict_json(self.read(Path('/etc/llm-server/image-api.json'), modes={0o644}, maximum=131072))
            if (config.get('runtime_revision') != IMAGE_RUNTIME or config.get('model_revision') != IMAGE_REVISION
                    or config.get('model_id') != 'Qwen/Qwen-Image-2.1'):
                raise ValueError('image_installation_unknown')
            installed = profiles(config.get('profiles'))
            result.update(deployment_id='image21-runtime-20260923', model_alias=IMAGE_ALIAS,
                operation_profiles=installed, installed_capabilities=sorted({
                    'images.generations' if p['operation'] == 'generation' else 'images.edits' for p in installed}),
                owner_identity={**owner, 'run_id':state['run_id']} if owner else None,
                backend_running=owner['running'] if owner else False,
                running=bool(owner and owner['running'] and unit['ActiveState'] == 'active'), ownership_valid=True)
            if (self.read(Path(config_path), modes={0o600}, maximum=131072) != config_raw
                    or binding.read_json('services', config_path) != runtime_config):
                raise ValueError('image_selection_changed')
            semantics = [state.get('run_id'), identity, owner, unit, result['imageGPU']]
        if self.boot()['boot_id'] != boot['boot_id'] or self.clock() >= deadline:
            raise ValueError('observation_changed_or_expired')
        if service_id in (MIMO, 'glm-5.3-flash'):
            semantics = [semantics, selection]
        result['generation'] = generation([boot['boot_id'], semantics, result['identity']]) if result.get('identity') is not None else None
        if result.get('hardware_latched') is False:
            result['hardware_validation_age_ms'] = result.get('hardware_validation_age_ms', 15001) + max(0, seconds - remaining()) * 1000
            if not negative_hardware_current(result, required, boot['boot_id']):
                result['hardware_latched'] = None
        if not result['running'] and result.get('hardware_latched') is not True:
            result.update(ready=False, admitting=False, reason='service_stopped')
        if result.get('hardware_latched') is True:
            result.update(ready=False, admitting=False)
        if result.get('frontier_selected') is False:
            result.update(ready=False, admitting=False, reason='unqualified')
        return result

    def old_owner_settled(self, service_id, old_identity, seconds=2):
        """Concrete old Docker invocation proof for stop/restart receipts only.

        This read is never called by a status GET. A replacement's readiness
        cannot hide an old container still running. No raw inspect/env is read.
        """
        if service_id not in LEGACY_TARGETS and service_id != 'image':
            raise ValueError('unregistered_owner')
        if old_identity is None:
            # Re-prove absence of fixed registered names; missing metadata alone
            # cannot settle a quarantined request. No user-selected name exists.
            names = ['llm-image-backend'] if service_id == 'image' else [
                'llmctl-' + name for name, spec in DEPLOYMENTS.items() if spec[0] == service_id]
            deadline = self.clock() + seconds
            for name in names:
                remaining = deadline - self.clock()
                if remaining <= 0:
                    raise TimeoutError('settlement_deadline')
                self._absent(name, remaining)
            return True
        if (type(old_identity) is not dict or type(old_identity.get('container_id')) is not str
                or not HEX.fullmatch(old_identity['container_id'])
                or type(old_identity.get('pid')) is not int or old_identity['pid'] < 0
                or type(old_identity.get('started_at')) is not str
                or not 1 <= len(old_identity['started_at']) <= 128):
            raise ValueError('old_owner_unknown')
        deadline = self.clock() + seconds
        def budget():
            remaining = deadline - self.clock()
            if remaining <= 0:
                raise TimeoutError('settlement_deadline')
            return remaining
        cid = old_identity['container_id']
        output = self.run(['/usr/bin/docker', 'container', 'ls', '--all', '--no-trunc',
                           '--filter', 'id=' + cid, '--format', '{{.ID}}'], budget())
        rows = output.strip().splitlines()
        if not rows:
            return True
        if rows != [cid]:
            raise ValueError('old_owner_inventory_ambiguous')
        fields = '[{{json .Id}},{{json .State.Running}},{{json .State.Pid}},{{json .State.StartedAt}}]'
        raw = strict_json(self.run(['/usr/bin/docker', 'inspect', '--format', fields, cid], budget()))
        if (type(raw) is not list or len(raw) != 4 or raw[0] != cid or type(raw[1]) is not bool
                or type(raw[2]) is not int or raw[2] < 0 or type(raw[3]) is not str
                or not 1 <= len(raw[3]) <= 128):
            raise ValueError('old_owner_process_unknown')
        if not raw[1]:
            return raw[2] == 0
        # Existing canonical restart stops before starting the same container.
        # Require both immutable start-time change and a distinct live main PID.
        return (raw[2] > 0 and raw[2] != old_identity['pid']
                and raw[3] != old_identity['started_at'])

    def observe(self, service_id, seconds=2):
        return PassiveServiceCollector(service_id, self)(seconds)

    def __call__(self, request, lease, deadline):
        lease.validate()
        boot = self.boot()['boot_id']
        seconds = max(.001, deadline - self.clock())
        if request.service_id is not None:
            row = self.service(request.service_id, seconds)
            return {**row, 'affected_services': [request.service_id]}
        affected = list(SERVICES) if not request.gpu_uuid else [
            s for s, ids in SERVICES.items() if request.gpu_uuid in ids]
        captured = {}
        if request.gpu_uuid:
            image = self.service('image', max(.001, deadline - self.clock()))
            selected = required_gpus('image', image)
            # Unknown selection cannot prove a reset disjoint from image.
            if not selected or request.gpu_uuid in selected:
                affected.append('image')
                captured['image'] = image
        rows = [captured[s] if s in captured else
                self.service(s, max(.001, deadline - self.clock())) for s in affected]
        if self.boot()['boot_id'] != boot:
            raise ValueError('boot_changed')
        return {'boot_id': boot, 'generation': aggregate_generation(boot, rows, request.gpu_uuid),
                'affected_services': affected, 'ownership_valid': all(r['ownership_valid'] for r in rows),
                'hardware_latched': any(r.get('hardware_latched') is True for r in rows),
                'running': any(r.get('running') is not False for r in rows)}


def aggregate_generation(boot_id, rows, gpu_uuid=None):
    if boot_id is None or any(type(r.get('generation')) is not int for r in rows):
        return None
    return generation([boot_id, gpu_uuid, [r['generation'] for r in rows]])


ADA_SERVICE = 'qwen-ada200k'
ADA_ALIAS = 'qwen3.8-27b-ada200k'
ADA_BASE = '/data/services/qwen-ada200k-h028-20260929'
ADA_GPU = 'GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf'
ADA_RETIRED_NATIVE = '5deb31661139ce99a1556aedef7438f22f27c8578b953eda9227095df5c03ebb'
ADA_AUTH_PATH = '/data/services/llm-manager/adapters/sglang38_file_auth.py'
ADA_AUTH_SHA256 = 'e507ed81d1e3954afea1d31eb9f0bc7ef7ab8b9a76bb571499e1a5f9c53c7da4'
ADA_SOURCES = {
    'ada_owner.py': '53ba6bcfb99f099809ee180356ca9e260baf3a82b6dbbe8022e39cf163180a70',
    'ada_launcher.py': '0c050ceea238d702d20c93eb082e99cce1b19ccb3712f2eb837d2ff0177fcf46',
    'ada_supervisor.py': '78946c5bc2789044e38a8e180e4d4fea78aae8350c65546c3bff411313ec5105',
}


def ada_native_capacity(code, value):
    if code != 200 or type(value) is not dict:
        raise ValueError('ada_capacity_unknown')
    states = value.get('internal_states', [])
    if type(states) is not list or any(type(row) is not dict for row in states):
        raise ValueError('ada_capacity_unknown')
    for field, expected in {'context_length': 200000, 'max_total_tokens': 200000,
            'max_total_num_tokens': 200000, 'max_req_input_len': 199994}.items():
        values = [row[field] for row in [value, *states] if field in row]
        if not values or any(type(v) is not int or v != expected for v in values):
            raise ValueError('ada_capacity_mismatch')


def ada_retirement(receipt, container, unit, listeners, boot):
    """Protected, dated retirement proof plus current retained-owner absence.

    The recorded GPU memory sample precedes image placement. Current image GPU
    use and later boots cannot invalidate that durable intent; fresh current-boot
    checks must still establish that the retained native stays stopped.
    """
    expected = {'schema_version': 1, 'kind': 'h037-ada200k-retirement',
        'service_id': ADA_SERVICE, 'unit': 'qwen-ada200k.service',
        'gpu_uuid': ADA_GPU, 'native_id': ADA_RETIRED_NATIVE,
        'container_retained': True, 'history_retained': True,
        'listener_absent': True, 'gpu_processes': []}
    if (type(boot) is not str or not BOOT.fullmatch(boot)
            or type(receipt) is not dict or set(receipt) != set(expected) | {'boot_id', 'observed_at_utc', 'gpu_used_memory_mib'}
            or any(type(receipt[k]) is not type(v) or receipt[k] != v for k, v in expected.items())
            or type(receipt['boot_id']) is not str or not BOOT.fullmatch(receipt['boot_id'])
            or type(receipt['observed_at_utc']) is not str
            or type(receipt['gpu_used_memory_mib']) is not int or not 0 <= receipt['gpu_used_memory_mib'] <= 2**53
            or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)', receipt['observed_at_utc'])
            or container.get('Id') != ADA_RETIRED_NATIVE
            or container.get('State', {}).get('Running') is not False
            or type(container['State'].get('Pid')) is not int or container['State']['Pid'] != 0
            or unit != {'Id': 'qwen-ada200k.service', 'ActiveState': 'inactive',
                        'UnitFileState': 'disabled', 'MainPID': '0', 'ControlPID': '0', 'Job': ''}
            or type(listeners) is not str or len(listeners) > 65536):
        raise ValueError('ada_retirement_unproven')
    for line in listeners.splitlines():
        fields = line.split()
        if len(fields) < 4 or fields[0] != 'LISTEN' or fields[3].rsplit(':', 1)[-1] == '30014':
            raise ValueError('ada_retirement_listener_unproven')
    return True


class AdaPassiveCollector:
    """Fixed read-only Ada instance. No owner operation or lifecycle authority."""
    def __init__(self, reader, *, get=native_get, clock=time.monotonic):
        self.reader, self.get, self.clock = reader, get, clock

    def __call__(self, seconds):
        deadline = self.clock() + seconds
        def remaining():
            left = deadline - self.clock()
            if left <= 0:
                raise TimeoutError('observation_deadline')
            return left
        boot = self.reader.boot()['boot_id']
        binding = self.reader.binding(remaining())
        def read(path, mode=0o600):
            binding.validate_path('data', path)
            remaining()
            return self.reader.read(Path(path), modes={mode}, maximum=65536)
        config_raw, state_raw = read(ADA_BASE + '/config.json'), read(ADA_BASE + '/state.json')
        config, state = strict_json(config_raw), strict_json(state_raw)
        auth_source = read(ADA_AUTH_PATH, 0o644)
        if hashlib.sha256(auth_source).hexdigest() != ADA_AUTH_SHA256:
            raise ValueError('ada_auth_source_changed')
        sources = {}
        for name, digest in ADA_SOURCES.items():
            raw = read(ADA_BASE + '/source/' + name, 0o644)
            if config.get('source_sha256', {}).get(name) != digest or hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError('ada_source_identity_changed')
            sources[name] = raw
        # This exact reviewed owner module has inert imports and definitions.
        # Never call operate(), storage(), or its CLI entry point.
        owner = {'__name__': '_passive_ada_owner'}
        exec(compile(sources['ada_owner.py'], 'pinned_ada_owner.py', 'exec'), owner)
        identity = state.get('container') or {}
        container_id = identity.get('id')
        if type(container_id) is not str or not HEX.fullmatch(container_id):
            raise ValueError('ada_container_unknown')
        def inspect():
            values = strict_json(self.reader.run(['/usr/bin/docker', 'inspect', container_id], remaining()))
            if type(values) is not list or len(values) != 1 or type(values[0]) is not dict:
                raise ValueError('ada_container_unknown')
            owner['validate_container'](values[0], config, state)
            return values[0]
        first = inspect()
        running = first.get('State', {}).get('Running')
        if type(running) is not bool:
            raise ValueError('ada_process_unknown')
        result = {'boot_id': boot, 'model_alias': ADA_ALIAS,
            'deployment_id': 'qwen-ada200k-h028-20260929', 'ready': False if not running else None,
            'reason': 'service_stopped' if not running else 'readiness_unknown',
            'configured_context_tokens': None, 'functional_qualified': None,
            'present': True, 'retired': False}
        if running:
            key = _key(read('/data/services/secrets/llm-api-key'))
            status = text_readiness(*self.get(30014, '/v1/readiness', key, remaining()), ADA_ALIAS)
            ada_native_capacity(*self.get(30014, '/get_server_info', key, remaining()))
            result.update(status, configured_context_tokens=200000)
        else:
            try:
                retirement_raw = read(ADA_BASE + '/retirement.json')
            except (FileNotFoundError, InstallationError):
                # An absent/unreadable optional marker never proves retirement.
                retirement_raw = None
            if retirement_raw is not None:
                unit = dict(line.split('=', 1) for line in self.reader.run(
                    ['/usr/bin/systemctl', 'show', 'qwen-ada200k.service',
                     '--property=Id,ActiveState,UnitFileState,MainPID,ControlPID,Job'], remaining()).splitlines())
                listeners = self.reader.run(['/usr/bin/ss', '-H', '-ltn'], remaining())
                result['retired'] = ada_retirement(strict_json(retirement_raw), first, unit, listeners, boot)
                if read(ADA_BASE + '/retirement.json') != retirement_raw:
                    raise ValueError('ada_retirement_changed')
        final = inspect()
        if (first.get('State') != final.get('State') or self.reader.boot()['boot_id'] != boot
                or read(ADA_BASE + '/config.json') != config_raw or read(ADA_BASE + '/state.json') != state_raw):
            raise ValueError('ada_identity_changed')
        if (read(ADA_AUTH_PATH, 0o644) != auth_source or any(
                read(ADA_BASE + '/source/' + name, 0o644) != raw for name, raw in sources.items())):
            raise ValueError('ada_source_identity_changed')
        remaining()
        return result


class PassiveServiceCollector:
    def __init__(self, service_id, reader, *, get=native_get, clock=time.monotonic, control_key=None):
        self.service_id, self.reader, self.get, self.clock = service_id, reader, get, clock
        self._control_key = control_key
        self._positive = None
        self._positive_gpus = ()

    def __call__(self, seconds):
        started = self.clock()
        result = self.reader.service(self.service_id, seconds)
        required = required_gpus(self.service_id, result) if self.service_id in SERVICES else ()
        if result.get('hardware_latched') is False and required and not negative_hardware_current(result, required, result.get('boot_id')):
            result['hardware_latched'] = None
        if result.get('hardware_latched') is True:
            self._positive = {key: result.get(key) for key in
                ('hardware_latched', 'hardware_latched_boot_id', 'reason')}
            self._positive_gpus = required
        elif self._positive is not None and (self.service_id != 'image'
                or required and required == self._positive_gpus):
            # A storage outage or a same-boot negative cannot erase positive
            # evidence. Only the protected owner can validate another boot.
            # Image selection changes cannot transfer that proof to another GPU.
            if (result.get('hardware_latched') is False and result.get('boot_id') is not None
                    and result['boot_id'] != self._positive.get('hardware_latched_boot_id')):
                self._positive = None
            else:
                result.update(self._positive)
                result.update(ready=False, admitting=False, generation=None)
        if (not result.get('running') or self.service_id == 'node'
                or result.get('frontier_selected') is False or result.get('software_quarantined') is True):
            return result
        if self.service_id == 'control':
            # Independent of storage/model owners; reuse the validated startup
            # credential. Native identity brackets the actual authenticated GET.
            def remaining():
                budget = seconds - (self.clock() - started)
                if budget <= 0:
                    raise TimeoutError()
                return budget
            try:
                if self._control_key is None:
                    raise ValueError('control_credential_unavailable')
                status = control_readiness(*self.get(30000, '/control/v1/readiness',
                    self._control_key, remaining()), result)
                current = self.reader._unit('control', remaining())
                if (current != result.get('unit_identity')
                        or self.reader.boot()['boot_id'] != result['boot_id']):
                    raise ValueError('control_identity_changed')
                remaining()
                result.update(status)
            except Exception:
                result.update(ready=None, admitting=None, reason='readiness_unknown')
            return result
        identity_completed = self.clock()
        try:
            binding = self.reader.binding(max(.001, seconds - (self.clock() - started)))
            key_path = binding.path('data', 'services/secrets/llm-api-key')
            binding.validate_path('data', key_path)
            key = _key(self.reader.read(Path(key_path), modes={0o600}, maximum=257))
            if self.service_id == MIMO:
                status = mimo_native_readiness(
                    self.get(30012, '/props', key, max(.001, seconds - (self.clock() - started))),
                    self.get(30012, '/slots', key, max(.001, seconds - (self.clock() - started))),
                    result.get('mimo_manifest', {}))
                current = self.reader.service(MIMO, max(.001, seconds - (self.clock() - started)))
                if (type(result.get('generation')) is not int or type(current.get('generation')) is not int
                        or not current.get('ownership_valid') or not current.get('running')
                        or current.get('frontier_selected') is not True or current.get('software_quarantined') is not False
                        or current.get('generation') != result.get('generation')
                        or self.clock() - started >= seconds):
                    raise ValueError('mimo_readback_identity_changed')
                # Admission intentionally remains unknown: native slot idle alone is insufficient.
                result.update(guard_age_ms=current['guard_age_ms'], guard_boot_id=current['guard_boot_id'])
            elif self.service_id == 'glm-5.3-flash':
                response = self.get(30010, '/v1/readiness', key, max(.001, seconds - (self.clock() - started)))
                status = text_readiness(*response, 'glm-5.3-flash')
                if status['ready']:
                    capacity = flash_native_context(*self.get(30010, '/get_server_info', key,
                        max(.001, seconds - (self.clock() - started))), result.get('source_context_tokens'))
                    # Bracket readback with the same source/container/boot identity.
                    current = self.reader.service(self.service_id, max(.001, seconds - (self.clock() - started)))
                    if (type(result.get('generation')) is not int or type(current.get('generation')) is not int
                            or not current.get('ownership_valid') or not current.get('running')
                            or current.get('frontier_selected') is not True
                            or current.get('frontier_selection') != result.get('frontier_selection')
                            or current.get('generation') != result.get('generation')
                            or self.clock() - started >= seconds):
                        raise ValueError('frontier_capacity_identity_changed')
                    status.update(capacity)
            elif self.service_id == 'image':
                response = self.get(30006, '/v1/image-capabilities', key, max(.001, seconds - (self.clock() - started)))
                status = image_readiness(*response)
                current = self.reader.service('image', max(.001, seconds - (self.clock() - started)))
                if (type(result.get('generation')) is not int
                        or current.get('generation') != result['generation']
                        or current.get('imageGPU') != result.get('imageGPU')
                        or not current.get('ownership_valid') or not current.get('running')
                        or self.clock() - started >= seconds):
                    raise ValueError('image_readback_identity_changed')
            elif result.get('selected') in DEPLOYMENTS and result['selected'].startswith('qwen38-'):
                _, alias, port = DEPLOYMENTS[result['selected']]
                response = self.get(port, '/v1/readiness', key, max(.001, seconds - (self.clock() - started)))
                status = text_readiness(*response, alias)
            else:
                # Optional GLM lacks the newly frozen text route; no generating fallback.
                status = {'ready': None, 'admitting': None, 'reason': 'readiness_unknown'}
            if self.reader.boot()['boot_id'] != result['boot_id']:
                raise ValueError('boot_changed')
            if result.get('hardware_latched') is not True:
                result.update(status)
        except Exception:
            if result.get('hardware_latched') is not True:
                result.update(ready=None, admitting=None, reason='readiness_unknown')
        if result.get('hardware_latched') is False and required:
            result['hardware_validation_age_ms'] += max(0, self.clock() - identity_completed) * 1000
            if not negative_hardware_current(result, required, result.get('boot_id')):
                result['hardware_latched'] = None
        return result
