"""Fixed passive Linux collectors. No lifecycle owner, HTTP health or shell.

These collectors report observed process state, never infer model readiness from
a running PID. Protected readiness/latch owner adapters are a separate admission
gate. Each external command has a2s deadline and bounded streamed output; a stuck
kernel wait occupies its observer slot, with no unbounded replacement workers.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET

from .node import BOOT, UUID, SERVICES
from .passive import utc

SPARE_UUID = 'GPU-69acfa26-8b60-61b5-702d-aee252c163cc'
GPU_UUIDS = tuple(dict.fromkeys(u for values in SERVICES.values() for u in values))
CONTAINERS = {'glm-5.3-flash': 'llm-frontier-flash', 'qwen-gpu0': 'llmctl-qwen38-27b-q0-480000-yarn4-bf16kv',
              'qwen-gpu1': 'llmctl-qwen38-27b-q1-server-480000-yarn4-bf16kv',
              'image': 'llm-image-backend'}
MAX_OUTPUT = 256 * 1024


def command(argv, seconds):
    """Bound captured bytes as well as time; never use shell or print stderr."""
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
    deadline = time.monotonic() + seconds
    data = bytearray()
    try:
        os.set_blocking(process.stdout.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('collector_timeout')
                if not selector.select(remaining):
                    raise TimeoutError('collector_timeout')
                chunk = os.read(process.stdout.fileno(), min(65536, MAX_OUTPUT + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > MAX_OUTPUT:
                    raise ValueError('collector_output_limit')
        if process.wait(timeout=max(0.001, deadline - time.monotonic())) != 0:
            raise ValueError('collector_failed')
        return data.decode('utf-8')
    finally:
        if process.poll() is None:
            process.kill()
            # If kernel cannot settle child, caller keeps its one slot. No
            # replacement thread/process is spawned while this wait remains.
            process.wait()
        process.stdout.close()


def boot_identity():
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    uptime = float(Path('/proc/uptime').read_text().split()[0])
    if not BOOT.fullmatch(boot_id) or not 0 <= uptime < 2**53:
        raise ValueError('boot_identity_unknown')
    return {'boot_id': boot_id, 'boot_age_seconds': uptime}


def collect_boot(_seconds):
    return boot_identity()


def collect_inventory(seconds, *, run=command, boot=boot_identity):
    before = boot()
    output = run(['/usr/bin/nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader,nounits'], seconds)
    after = boot()
    rows = [line.strip() for line in output.splitlines() if line.strip()]
    if (before['boot_id'] != after['boot_id'] or len(rows) > 64 or
            not all(UUID.fullmatch(row) for row in rows) or len(rows) != len(set(rows))):
        raise ValueError('inventory_unknown')
    # Success with no rows is a complete empty inventory. Failed NVML init is
    # raised by command and never translated into successful absence evidence.
    return {**after, 'complete': True, 'observation_id': uuid.uuid4().hex,
            'gpu_uuids': rows, 'hardware_faults': {}}


def _numeric(text):
    if type(text) is not str or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?(?: (?:MiB|W|C)|x)?', text.strip()):
        return None
    return float(re.match(r'[0-9]+(?:\.[0-9]+)?', text.strip())[0])


class GpuCollector:
    def __init__(self, gpu_uuid, *, run=command, boot=boot_identity, wall=time.time):
        if not UUID.fullmatch(gpu_uuid):
            raise ValueError('invalid_gpu_uuid')
        self.gpu_uuid, self.run, self.boot, self.wall = gpu_uuid, run, boot, wall
        self.extrema_boot = self.minimum = self.maximum = self.since = None
        self.last_proof = None

    def __call__(self, seconds):
        before = self.boot()
        output = self.run(['/usr/bin/nvidia-smi', '--id=' + self.gpu_uuid, '-q', '-x'], seconds)
        after = self.boot()
        if before['boot_id'] != after['boot_id'] or '<!ENTITY' in output:
            raise ValueError('gpu_observation_unknown')
        document = ET.fromstring(output)
        records = document.findall('gpu')
        if len(records) != 1 or records[0].findtext('uuid') != self.gpu_uuid:
            raise ValueError('gpu_identity_unknown')
        record = records[0]
        paths = {'memory_total_mib': 'fb_memory_usage/total', 'memory_used_mib': 'fb_memory_usage/used',
                 'temperature_c': 'temperature/gpu_temp',
                 'ecc_uncorrected_volatile': 'ecc_errors/volatile/uncorrected/total',
                 'power_draw_w': 'gpu_power_readings/instant_power_draw',
                 'power_limit_w': 'gpu_power_readings/current_power_limit',
                 'pcie_generation': 'pci/pci_gpu_link_info/pcie_gen/current_link_gen',
                 'pcie_generation_max': 'pci/pci_gpu_link_info/pcie_gen/max_link_gen',
                 'pcie_width': 'pci/pci_gpu_link_info/link_widths/current_link_width',
                 'pcie_width_max': 'pci/pci_gpu_link_info/link_widths/max_link_width'}
        fields = {key: _numeric(record.findtext(path)) for key, path in paths.items()}
        temp = fields['temperature_c']
        if self.extrema_boot != after['boot_id']:
            self.minimum = self.maximum = self.since = None
            self.extrema_boot = after['boot_id']
        if temp is not None:
            self.minimum = temp if self.minimum is None else min(self.minimum, temp)
            self.maximum = temp if self.maximum is None else max(self.maximum, temp)
            self.since = self.since or utc(self.wall())
        self.last_proof = (dict(gpu_uuid=self.gpu_uuid, boot_id=after['boot_id'],
            observed_at=utc(self.wall()), observation_id=uuid.uuid4().hex), time.monotonic())
        ecc = record.findtext('ecc_mode/current_ecc')
        return {'boot_id': after['boot_id'], 'gpus': [{'uuid': self.gpu_uuid, **fields,
            'name': record.findtext('product_name'), 'index': None,
            'pci_bus_id': record.findtext('pci/pci_bus_id'),
            'ecc_mode': ecc.lower() if ecc in ('Enabled', 'Disabled') else None,
            'temperature_min_c': self.minimum, 'temperature_max_c': self.maximum,
            'sampling_since': self.since}]}


def service_collector(service_id, *, run=command, boot=boot_identity):
    if service_id not in SERVICES:
        raise ValueError('unknown_service')
    def collect(seconds):
        identity = boot()
        if service_id == 'control':
            output = run(['/usr/bin/systemctl', 'show', 'llm-control.service',
                          '--property=ActiveState', '--value'], seconds).strip()
            if output not in ('active', 'inactive', 'failed', 'activating', 'deactivating', 'reloading'):
                raise ValueError('unknown_service_state')
            running = output in ('active', 'reloading')
        else:
            # Exact fixed names; never return Config.Env, argv, logs or raw inspect.
            name = CONTAINERS[service_id]
            output = run(['/usr/bin/docker', 'inspect', '--format',
                          '{{json .Name}} {{json .State.Running}}', name], seconds)
            fields = output.strip().split()
            if len(fields) != 2 or json.loads(fields[0]) != '/' + name or fields[1] not in ('true', 'false'):
                raise ValueError('unknown_service_state')
            running = fields[1] == 'true'
        if boot()['boot_id'] != identity['boot_id']:
            raise ValueError('boot_changed')
        return {'boot_id': identity['boot_id'], 'ready': None if running else False,
                'admitting': None if running else False,
                'reason': 'readiness_unknown' if running else 'service_stopped',
                'activity': 'unknown', 'queue_depth': None, 'active_requests': None,
                'hardware_latched': None}
    return collect


class CpuCollector:
    def __init__(self, read=lambda: Path('/proc/stat').read_text(), count=os.cpu_count):
        self.read, self.count, self.previous = read, count, None

    def __call__(self, _seconds):
        line = self.read().splitlines()[0].split()
        if line[0] != 'cpu' or len(line) < 9:
            raise ValueError('cpu_unknown')
        counters = [int(v) for v in line[1:9]]  # guest already included in user/nice
        total, idle = sum(counters), counters[3] + counters[4]
        percent = None
        if self.previous is not None:
            dt, di = total - self.previous[0], idle - self.previous[1]
            if dt > 0 and 0 <= di <= dt:
                percent = 100 * (dt - di) / dt
        self.previous = (total, idle)
        return {'percent': percent, 'logical_count': self.count()}


def collect_memory(_seconds):
    fields = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        name, value = line.split(':', 1)
        if name in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'):
            fields[name] = int(value.split()[0]) * 1024
    result = {key: fields.get(name) for key, name in
              [('total_bytes', 'MemTotal'), ('available_bytes', 'MemAvailable'),
               ('swap_total_bytes', 'SwapTotal'), ('swap_free_bytes', 'SwapFree')]}
    result.update(pressure_some_avg10=None, pressure_full_avg10=None)
    try:
        for line in Path('/proc/pressure/memory').read_text().splitlines():
            parts = line.split()
            if parts[0] in ('some', 'full'):
                result['pressure_' + parts[0] + '_avg10'] = float(dict(p.split('=', 1) for p in parts[1:])['avg10'])
    except (OSError, ValueError, KeyError):
        pass
    return result


class InventoryCollector:
    def __init__(self):
        self.last_proof = None

    def __call__(self, seconds):
        value = collect_inventory(seconds)
        self.last_proof = (dict(value, observed_at=utc(time.time())), time.monotonic())
        return value


class HardwareEvidenceCollector:
    """One bounded scheduled producer serializes latch proofs; never GET.

    Exact-target proof remains independent of a failed global inventory. Failed
    writes never publish false and no replacement threads are created. All
    receipts retain their original capture time through storage/lease delays.
    """
    def __init__(self, inventory, gpus):
        self.inventory, self.gpus = inventory, gpus

    def __call__(self, seconds):
        from common.lifecycle_lease import acquire_lease
        from lifecycle.hardware_policy import HardwarePolicy, RegisteredLatchStore, GPU_UUIDS
        from .node_observation import production_binding
        with acquire_lease(blocking=False) as lease:
            binding = production_binding(seconds)
            policy = HardwarePolicy(RegisteredLatchStore(binding, lease=lease), lease=lease)
            proof = self.inventory.last_proof
            if proof is not None:
                raw, captured = proof
                age_ms = int(max(0, time.monotonic() - captured) * 1000)
                inventory = dict(raw, state='ok', freshness='fresh' if age_ms <= 15000 else 'stale', age_ms=age_ms)
                policy.observe_inventory(inventory, boot_age_seconds=raw['boot_age_seconds'] + age_ms / 1000)
            for collector in self.gpus:
                if collector.gpu_uuid not in GPU_UUIDS or collector.last_proof is None:
                    continue
                raw, captured = collector.last_proof
                if time.monotonic() - captured > 15:
                    continue
                policy.validate_required(collector.gpu_uuid, current_boot_id=raw['boot_id'],
                    observed_at=raw['observed_at'], observation_id=raw['observation_id'])
        return {'state': 'persisted'}


def production_callbacks(identity_reader=None, *, control_key=None):
    from .node_observation import CanonicalIdentityReader, PassiveServiceCollector
    from .node_resources import resource_callbacks
    reader = identity_reader or CanonicalIdentityReader()
    inventory = InventoryCollector()
    gpus = [GpuCollector(gpu) for gpu in GPU_UUIDS]
    result = {'boot': collect_boot, 'inventory': inventory,
              'cpu': CpuCollector(), 'memory': collect_memory}
    result.update({service: PassiveServiceCollector(service, reader,
        control_key=control_key if service == 'control' else None) for service in (*SERVICES, 'node')})
    result.update(resource_callbacks())
    result.update({'gpu:' + collector.gpu_uuid: collector for collector in gpus})
    result['hardware_evidence'] = HardwareEvidenceCollector(inventory, gpus)
    return result
