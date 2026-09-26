"""Independent node API projection. GET reads cached memory only.

The observer and canonical action-owner ports are injected. This component never
loads a lifecycle manager, probes native health, takes a lifecycle/storage lock,
or reconciles service state. Unknown metadata is not an availability promise.
"""
from __future__ import annotations

import json
import math
import re

UUID = re.compile(r'GPU-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z')
BOOT = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z')
IDENTIFIER = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,95}\Z')
SERVICES = {
    'qwen-gpu0': ('GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237',),
    'qwen-gpu1': ('GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528',),
    'image': ('GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23',),
    'control': (),
}
LEGACY_TARGETS = {'qwen-gpu0': 'glm', 'qwen-gpu1': 'qwen'}
CAPABILITIES = {'qwen-gpu0': {'chat.completions'}, 'qwen-gpu1': {'chat.completions'},
                'image': {'images.generations', 'images.edits'}, 'control': {'model.control'}}
RESOURCE_FIELDS = {
    'cpu': ('percent', 'logical_count'),
    'memory': ('total_bytes', 'available_bytes', 'swap_total_bytes', 'swap_free_bytes',
               'pressure_some_avg10', 'pressure_full_avg10'),
    'disk': ('total_bytes', 'available_bytes', 'read_bytes_per_second', 'write_bytes_per_second'),
    'network': ('rx_bytes_per_second', 'tx_bytes_per_second'),
}
GPU_NUMBERS = ('index', 'memory_total_mib', 'memory_used_mib', 'temperature_c',
               'temperature_min_c', 'temperature_max_c', 'ecc_uncorrected_volatile',
               'power_draw_w', 'power_limit_w', 'pcie_generation', 'pcie_width',
               'pcie_generation_max', 'pcie_width_max')
REASONS = {'not_observed', 'collector_failed', 'collector_timeout', 'stale_observation',
           'hardware_missing', 'hardware_fault', 'hardware_latch_unknown', 'readiness_unknown',
           'service_stopped', 'service_failed', 'service_busy', 'service_starting',
           'software_quarantine', 'unqualified', 'boot_changed', 'inventory_unknown',
           'unsupported', 'observation_unavailable'}


def number(value):
    return value if type(value) in (int, float) and 0 <= value <= 2**53 and math.isfinite(value) else None


def integer(value):
    return value if type(value) is int and 0 <= value < 2**63 else None


def identifier(value):
    return value if type(value) is str and IDENTIFIER.fullmatch(value) else None


def boolean(value):
    return value if type(value) is bool else None


def reason(value):
    return value if type(value) is str and value in REASONS else None


def unknown():
    return {'state': 'unknown', 'observed_at': None, 'age_ms': None,
            'freshness': 'unknown', 'reason': 'not_observed'}


def envelope(sample):
    return {key: sample[key] for key in unknown()}


def valid(sample):
    return sample['state'] == 'ok' and sample['freshness'] == 'fresh'


def negative_hardware_current(raw, required, boot_id, extra_age_ms=0):
    age = number(raw.get('hardware_validation_age_ms'))
    return (raw.get('hardware_latched') is False and age is not None
            and number(extra_age_ms) is not None and age + extra_age_ms <= 15000
            and raw.get('hardware_validated_boot_id') == boot_id
            and raw.get('hardware_validated_gpu_uuids') == list(required))


class NodeStatus:
    def __init__(self, observers):
        self.observers = observers

    def _read(self, name):
        try:
            return self.observers.read(name)
        except KeyError:
            return dict(unknown(), value=None)

    def snapshot(self):
        boot = self._read('boot')
        b = boot['value'] or {}
        boot_id = b.get('boot_id')
        boot_id = boot_id if type(boot_id) is str and BOOT.fullmatch(boot_id) else None
        result = dict(schema_version=1, node_id='ai-vm', boot_id=boot_id,
                      generation=integer(b.get('generation')),
                      affected_services=list(SERVICES), **envelope(boot))
        inv = self._read('inventory')
        value = inv['value'] or {}
        ids = value.get('gpu_uuids')
        inventory_valid = (valid(inv) and valid(boot) and boot_id is not None
                           and value.get('boot_id') == boot_id and value.get('complete') is True
                           and type(ids) is list and len(ids) <= 64
                           and all(type(u) is str and UUID.fullmatch(u) for u in ids)
                           and len(set(ids)) == len(ids))
        faults = value.get('hardware_faults', {})
        from .hardware_latch import HARDWARE_FAULT_CODES
        faults_valid = (type(faults) is dict and len(faults) <= 64 and all(
            type(u) is str and UUID.fullmatch(u) and type(code) is str and code in HARDWARE_FAULT_CODES
            for u, code in faults.items()))
        inventory_valid = inventory_valid and faults_valid
        result['inventory'] = dict(envelope(inv), boot_id=value.get('boot_id') if
            type(value.get('boot_id')) is str and BOOT.fullmatch(value['boot_id']) else None,
            complete=inventory_valid, observation_id=identifier(value.get('observation_id')),
            gpu_uuids=ids if inventory_valid else [], hardware_faults=faults if inventory_valid else {})
        if valid(inv) and not inventory_valid:
            # A successful collector receipt is not proof that malformed,
            # partial or other-boot inventory is complete hardware evidence.
            result['inventory'].update(state='unknown', reason='inventory_unknown')
        result['resources'] = {}
        for name, fields in RESOURCE_FIELDS.items():
            sample = self._read(name)
            raw = sample['value'] or {}
            result['resources'][name] = dict(envelope(sample), **{k: number(raw.get(k)) for k in fields})
        disk_sample = self._read('disk')
        disk_raw = disk_sample['value'] or {}
        disk_volumes = disk_raw.get('volumes', [])
        result['resources']['disk']['volumes'] = []
        for volume_id in ('root', 'data', 'models'):
            candidates = [v for v in disk_volumes if type(v) is dict and v.get('volume_id') == volume_id] if type(disk_volumes) is list else []
            raw = candidates[0] if len(candidates) == 1 else {}
            # Child capture times remain authoritative; a new parent must not
            # make failed or cached mount capacity look fresh.
            age = integer(raw.get('age_ms'))
            outer_age = integer(disk_sample.get('age_ms'))
            age = age + outer_age if age is not None and outer_age is not None else None
            observed = raw.get('observed_at')
            observed = observed if type(observed) is str and re.fullmatch(r'[0-9T:+.Z-]{20,40}', observed) else None
            state = raw.get('state') if raw.get('state') in ('ok', 'unknown', 'unavailable') else 'unknown'
            if not valid(disk_sample) and state == 'ok':
                state = 'unknown'
            mount = raw.get('mount_point')
            mount = mount if type(mount) is str and len(mount) <= 256 and re.fullmatch(r'/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]*', mount) and '..' not in mount.split('/') else None
            fs_uuid = raw.get('filesystem_uuid')
            fs_uuid = fs_uuid if type(fs_uuid) is str and re.fullmatch(r'[A-Za-z0-9-]{1,128}', fs_uuid) else None
            fs_type = raw.get('filesystem_type')
            fs_type = fs_type if type(fs_type) is str and re.fullmatch(r'[a-zA-Z0-9_.-]{1,32}', fs_type) else None
            why = raw.get('reason') if raw.get('reason') in ('registration_unknown', 'mount_identity_unavailable', 'capacity_unavailable') else None
            row = dict(volume_id=volume_id, mount_point=mount, filesystem_uuid=fs_uuid,
                filesystem_type=fs_type, state=state, reason=why, observed_at=observed,
                age_ms=age, freshness='unknown' if age is None else ('fresh' if age <= 15000 else 'stale'),
                **{k: number(raw.get(k)) for k in RESOURCE_FIELDS['disk']})
            if raw.get('state') != 'ok':
                for k in RESOURCE_FIELDS['disk']:
                    row[k] = None
            result['resources']['disk']['volumes'].append(row)
        result['services'] = []
        for service_id, required in SERVICES.items():
            sample = self._read(service_id)
            raw = sample['value'] or {}
            current = valid(sample) and valid(boot) and boot_id is not None and raw.get('boot_id') == boot_id
            # Persisted positive latch survives stale/unknown telemetry. A
            # negative or unreadable latch never becomes proven-safe by default.
            latched = boolean(raw.get('hardware_latched'))
            if latched is False and required and not negative_hardware_current(raw, required, boot_id, sample.get('age_ms')):
                latched = None
            if latched is not True and not current:
                latched = None
            ready = boolean(raw.get('ready')) if current else None
            admitting = boolean(raw.get('admitting')) if current else None
            available = 'unknown'
            why = reason(raw.get('reason')) if current else 'observation_unavailable'
            if latched:
                hardware_reason = raw.get('reason')
                available, why = 'unavailable', (hardware_reason if hardware_reason in
                    ('hardware_missing', 'hardware_fault') else 'hardware_latch_unknown')
                ready = admitting = False
            elif current and latched is False and ready is True:
                available = 'available'
            elif current and ready is False and why in ('service_stopped', 'service_failed', 'unqualified', 'software_quarantine'):
                available = 'unavailable'
            elif latched is None:
                why = 'hardware_latch_unknown' if required else why
            capabilities = raw.get('installed_capabilities', [])
            capabilities = [c for c in capabilities if type(c) is str and c in CAPABILITIES[service_id]] if type(capabilities) is list else []
            # Installation evidence may remain when runtime observation stales;
            # consumers still see availability and observation envelope separately.
            item = dict(envelope(sample), service_id=service_id,
                        generation=integer(raw.get('generation')), affected_services=[service_id],
                        installed_capabilities=sorted(set(capabilities)), availability=available,
                        ready=ready, admitting=admitting, hardware_latched=latched,
                        hardware_latched_boot_id=raw.get('hardware_latched_boot_id') if type(raw.get('hardware_latched_boot_id')) is str and BOOT.fullmatch(raw['hardware_latched_boot_id']) else None,
                        required_gpu_uuids=list(required), activity=raw.get('activity') if current and
                        raw.get('activity') in ('busy', 'idle', 'unknown') else 'unknown',
                        queue_depth=integer(raw.get('queue_depth')) if current else None,
                        active_requests=integer(raw.get('active_requests')) if current else None,
                        deployment_id=identifier(raw.get('deployment_id')), model_alias=identifier(raw.get('model_alias')),
                        configured_context_tokens=integer(raw.get('configured_context_tokens')),
                        max_output_tokens=integer(raw.get('max_output_tokens')), operation_profiles=[])
            item['reason'] = why
            profiles = raw.get('operation_profiles', [])
            if type(profiles) is list:
                for profile in profiles[:16]:
                    if (type(profile) is dict and profile.get('operation') in ('generation', 'edit') and
                            profile.get('size') in ('1024x1024', '1024x576', '1216x704', '1472x832', '1760x992', '1920x1080', '1536x864')):
                        entry = {k: profile[k] for k in ('operation', 'size')}
                        if type(profile.get('references')) is int and 0 <= profile['references'] <= 2:
                            entry['references'] = profile['references']
                        if type(profile.get('transparent')) is bool:
                            entry['transparent'] = profile['transparent']
                        item['operation_profiles'].append(entry)
            result['services'].append(item)
        from .node_observation import aggregate_generation
        result['generation'] = aggregate_generation(boot_id, result['services'])
        node_sample = self._read('node')
        node_raw = node_sample['value'] or {}
        result['node_manager'] = dict(envelope(node_sample), service_id='node',
            running=boolean(node_raw.get('running')) if valid(node_sample) else None,
            generation=integer(node_raw.get('generation')), actions=[])
        telemetry = self._read('gpu_metrics')
        rows = (telemetry['value'] or {}).get('gpus', [])
        rows = rows if type(rows) is list else []
        samples = {row['uuid']: telemetry for row in rows if type(row) is dict
                   and type(row.get('uuid')) is str and UUID.fullmatch(row['uuid'])}
        # Fixed required GPUs plus inventory-discovered IDs use independent
        # capacity. Unknown/unassigned card failure cannot stall a healthy one.
        known = {u for required in SERVICES.values() for u in required}
        known.update(result['inventory']['gpu_uuids'])
        known.add('GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528')
        for gpu_uuid in sorted(known):
            sample = self._read('gpu:' + gpu_uuid)
            if sample['value'] is None and sample['reason'] == 'not_observed':
                if gpu_uuid not in result['inventory']['gpu_uuids']:
                    continue
                # Inventory discovery must not hide an extra unassigned GPU.
                # It gets no new thread, automatic assignment, or metric claims.
                sample = dict(unknown(), value={'boot_id': boot_id, 'gpus': [{'uuid': gpu_uuid}]})
            candidates = (sample['value'] or {}).get('gpus', [])
            if type(candidates) is not list or len(candidates) != 1 or type(candidates[0]) is not dict or candidates[0].get('uuid') != gpu_uuid:
                candidates = [{'uuid': gpu_uuid}]
            rows = [row for row in rows if type(row) is not dict or row.get('uuid') != gpu_uuid]
            rows.extend(candidates)
            samples[gpu_uuid] = sample
        # Only UUID-unique metric records are projected; no ordinal substitution.
        result['gpus'] = []
        for row in rows[:64]:
            if type(row) is not dict or type(row.get('uuid')) is not str or not UUID.fullmatch(row['uuid']):
                continue
            if sum(type(r) is dict and r.get('uuid') == row['uuid'] for r in rows) != 1:
                continue
            uuid = row['uuid']
            telemetry = samples[uuid]
            metric_envelope = envelope(telemetry)
            current = valid(boot) and boot_id is not None and (telemetry['value'] or {}).get('boot_id') == boot_id
            if not current and metric_envelope['state'] == 'ok':
                metric_envelope.update(state='unknown', reason='boot_changed')
            target = dict(metric_envelope, uuid=uuid, generation=integer(row.get('generation')) if current else None,
                          affected_services=[s for s, requirements in SERVICES.items() if uuid in requirements],
                          **{k: number(row.get(k)) for k in GPU_NUMBERS})
            target['name'] = row.get('name') if type(row.get('name')) is str and re.fullmatch(r'[A-Za-z0-9 .()-]{1,96}', row['name']) else None
            target['pci_bus_id'] = row.get('pci_bus_id') if type(row.get('pci_bus_id')) is str and re.fullmatch(r'[0-9a-fA-F]{4,8}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]', row['pci_bus_id']) else None
            target['ecc_mode'] = row.get('ecc_mode') if row.get('ecc_mode') in ('enabled', 'disabled') else None
            target['sampling_since'] = row.get('sampling_since') if type(row.get('sampling_since')) is str and re.fullmatch(r'[0-9T:+.Z-]{20,40}', row['sampling_since']) else None
            target['generation'] = aggregate_generation(boot_id, [row for row in result['services'] if row['service_id'] in target['affected_services']], uuid)
            result['gpus'].append(target)
        return result


class NodeApplication:
    """Only node routes; same existing authenticated transport implementation."""
    def __init__(self, status, actions=None):
        self.status, self.actions = status, actions

    def handle(self, method, path, headers, body):
        if method == 'GET' and path == '/control/v1/node/status':
            return 200, self.status.snapshot()
        if method == 'GET' and path.startswith('/control/v1/node/operations/'):
            opid = path.rsplit('/', 1)[1]
            if self.actions is not None:
                return self.actions.operation(opid)
            return 404, {'error': {'code': 'operation_unknown'}}
        if method == 'POST' and path == '/control/v1/node/actions':
            def pairs(items):
                value = {}
                for key, entry in items:
                    if key in value:
                        raise ValueError('duplicate_key')
                    value[key] = entry
                return value
            try:
                if len(body) > 4096:
                    raise ValueError('body_limit')
                value = json.loads(body.decode('utf-8'), object_pairs_hook=pairs,
                                   parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            except (ValueError, UnicodeError, RecursionError):
                return 400, {'error': {'code': 'invalid_request'}}
            if self.actions is not None:
                return self.actions.submit(value)
            return 422, {'error': {'code': 'unsupported_action'}}
        return 404, {'error': {'code': 'unknown_route'}}

    def close(self):
        self.status.observers.close()
