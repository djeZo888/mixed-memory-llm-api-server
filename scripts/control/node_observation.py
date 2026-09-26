"""Read-only canonical owner identities and passive authenticated readiness.

No Manager.status, control GET/reconcile, image owner.probe, native health, or
writes occur here. Identity generations exclude readiness, activity and metrics.
Only fixed registered paths, unit names, UUIDs and native routes are reachable.
"""
from __future__ import annotations

import hashlib
import http.client
import json
from pathlib import Path
import re
import socket
import threading
import time

from .installation import protected_file, _key
from .node import BOOT, SERVICES, LEGACY_TARGETS, negative_hardware_current
from .node_collectors import boot_identity, command

HEX = re.compile(r'[0-9a-f]{64}\Z')
DEPLOYMENTS = {
    'qwen38-27b-q0-480000-yarn4-bf16kv': ('qwen-gpu0', 'qwen3.8-27b-gpu0', 30002),
    'qwen38-27b-q1-480000-yarn4-bf16kv': ('qwen-gpu1', 'qwen3.8-27b', 30004),
    'glm-5.3-ud-q4-k-xl-g1-480000': ('qwen-gpu0', 'glm-5.3', 30002),
}
TEXT_OWNER = 'mixed-memory-llm-api-server'
IMAGE_OWNER = 'IMAGE21-RUNTIME-20260923'
IMAGE_ALIAS = 'qwen-image-2.1'
IMAGE_RUNTIME = '0cd8be351d0825488f4b81c8931167bbab618eca'
IMAGE_REVISION = '790c92633540aa0cb11d9abf19eb46d861714758'
PROFILE_ROOT = Path('/usr/local/lib/llm-server/node-api/configs/deployments')
UNITS = {'control': 'llm-control.service', 'image': 'llm-image-api.service',
         'node': 'llm-node.service'}


def generation(value):
    """Deterministic JSON-safe CAS token derived only from canonical semantics."""
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:7], 'big') >> 3


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
        except Exception:
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
            return result

    def _absent(self, name, seconds):
        raw = self.run(['/usr/bin/docker', 'container', 'ls', '--all', '--no-trunc',
                        '--filter', 'name=^/' + name + '$', '--format', '{{.ID}}'], seconds)
        if raw.strip():
            raise ValueError('unrecorded_owner_container')

    def _service(self, service_id, seconds, result):
        if service_id not in SERVICES and service_id != 'node':
            raise ValueError('unregistered_service')
        boot = self.boot()
        deadline = self.clock() + seconds
        remaining = lambda: max(.001, deadline - self.clock())
        result.update({'boot_id': boot['boot_id'], 'ready': None, 'admitting': None,
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
        result.update(self.latch(binding, SERVICES[service_id]))
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
        else:
            state = binding.read_json('services', binding.path('services', 'image21-runtime-20260923/state.json'))
            if state.get('schema_version') != 1 or state.get('owner') != IMAGE_OWNER:
                raise ValueError('image_owner_unknown')
            runtime_config = binding.read_json('services', binding.path('services', 'image21-runtime-20260923/config.json'))
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
                    'io.llm-image.gpu': SERVICES['image'][0]})
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
            semantics = [state.get('run_id'), identity, owner, unit]
        if self.boot()['boot_id'] != boot['boot_id'] or self.clock() >= deadline:
            raise ValueError('observation_changed_or_expired')
        result['generation'] = generation([boot['boot_id'], semantics, result['identity']]) if result.get('identity') is not None else None
        if result.get('hardware_latched') is False:
            result['hardware_validation_age_ms'] = result.get('hardware_validation_age_ms', 15001) + max(0, seconds - remaining()) * 1000
            if not negative_hardware_current(result, SERVICES[service_id], boot['boot_id']):
                result['hardware_latched'] = None
        if not result['running'] and result.get('hardware_latched') is not True:
            result.update(ready=False, admitting=False, reason='service_stopped')
        if result.get('hardware_latched') is True:
            result.update(ready=False, admitting=False)
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
        affected = [s for s, ids in SERVICES.items() if request.gpu_uuid in ids] if request.gpu_uuid else list(SERVICES)
        rows = [self.service(s, max(.001, deadline - self.clock())) for s in affected]
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


class PassiveServiceCollector:
    def __init__(self, service_id, reader, *, get=native_get, clock=time.monotonic, control_key=None):
        self.service_id, self.reader, self.get, self.clock = service_id, reader, get, clock
        self._control_key = control_key
        self._positive = None

    def __call__(self, seconds):
        started = self.clock()
        result = self.reader.service(self.service_id, seconds)
        if result.get('hardware_latched') is False and SERVICES.get(self.service_id) and not negative_hardware_current(result, SERVICES[self.service_id], result.get('boot_id')):
            result['hardware_latched'] = None
        if result.get('hardware_latched') is True:
            self._positive = {key: result.get(key) for key in
                ('hardware_latched', 'hardware_latched_boot_id', 'reason')}
        elif self._positive is not None:
            # A storage outage or a same-boot negative cannot erase positive
            # evidence. Only the protected owner can validate another boot.
            if (result.get('hardware_latched') is False and result.get('boot_id') is not None
                    and result['boot_id'] != self._positive.get('hardware_latched_boot_id')):
                self._positive = None
            else:
                result.update(self._positive)
                result.update(ready=False, admitting=False, generation=None)
        if not result.get('running') or self.service_id == 'node':
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
            if self.service_id == 'image':
                response = self.get(30006, '/v1/image-capabilities', key, max(.001, seconds - (self.clock() - started)))
                status = image_readiness(*response)
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
        if result.get('hardware_latched') is False and self.service_id in SERVICES and SERVICES[self.service_id]:
            result['hardware_validation_age_ms'] += max(0, self.clock() - identity_completed) * 1000
            if not negative_hardware_current(result, SERVICES[self.service_id], result.get('boot_id')):
                result['hardware_latched'] = None
        return result
