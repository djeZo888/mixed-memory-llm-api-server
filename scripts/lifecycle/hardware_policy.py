"""Protected boot hardware policy shared by existing owners, never a lifecycle.

The state file must be provisioned once by the reviewed activation transition.
Missing/corrupt state is unknown and denies start, never silently initialized.
Writers borrow the canonical lease; read-only node projections never write.
Exact target probes admit healthy independent owners even if a peer/unassigned
GPU prevents global NVML inventory. Shared driver failures can still prevent
such probes; no driver isolation is claimed.
"""
from __future__ import annotations

import datetime
import re
import subprocess
import time
import uuid
from pathlib import Path

from common.lifecycle_lease import _validate_borrowed_lease
from control.hardware_latch import HardwareLatch, ProtectedHardwareLatch, LatchStorageUnavailable, _timestamp, MAX_AGE_MS
from lifecycle.runtime_io import LifecycleError

STATE_SUFFIX = 'llm-manager/hardware-latch.json'
GPU_UUIDS = ('GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237',
             'GPU-69acfa26-8b60-61b5-702d-aee252c163cc',
             'GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23')
UUID = re.compile(r'GPU-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z')
BOOT = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z')


def boot_identity():
    before = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    age = float(Path('/proc/uptime').read_text().split()[0])
    after = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if before != after or not BOOT.fullmatch(before) or not 0 <= age < 2**53:
        raise LifecycleError('hardware_boot_identity_unknown')
    return {'boot_id': before, 'uptime_seconds': age}


def _run(argv, *, timeout=2):
    result = subprocess.run(argv, timeout=timeout, capture_output=True, text=True,
                            env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
    if result.returncode:
        raise LifecycleError('hardware_inventory_unknown')
    return result.stdout


class RegisteredLatchStore:
    def __init__(self, binding, *, lease=None, storage_io=None,
                 system_root=Path('/'), trusted_uid=0):
        self.binding, self.lease, self.storage_io = binding, lease, storage_io
        self.system_root, self.trusted_uid = system_root, trusted_uid

    def read(self):
        return self.binding.read_json('services', self.binding.path('services', STATE_SUFFIX), maximum=65536)

    def write(self, value):
        _validate_borrowed_lease(self.lease, system_root=self.system_root, trusted_uid=self.trusted_uid)
        if self.storage_io is None:
            from install import storage_io
        else:
            storage_io = self.storage_io
        from lifecycle.storage_binding import _entered_storage_context
        # Same registered root-payload guard as the installed owner helper,
        # before and after every AI-service state write; no helper path fallback.
        self.binding.storage.root_payload_guard(self.binding.registry, roles=('data',))
        self.binding.validate_path('services', self.binding.path('services', STATE_SUFFIX))
        try:
            with self.binding.mounted_guard(storage_io, roles=('data',)) as guard:
                with _entered_storage_context(storage_io.AnchoredRoot(self.binding.path('services'), guard)) as anchored:
                    # No mkdir/bootstrap fallback. Activation must install protected state.
                    anchored.atomic_json(STATE_SUFFIX, value)
                    anchored.check()
        finally:
            self.binding.storage.root_payload_guard(self.binding.registry, roles=('data',))
        _validate_borrowed_lease(self.lease, system_root=self.system_root, trusted_uid=self.trusted_uid)


def read_latch_status(binding, gpu_uuids, *, current_boot_id=None, wall=time.time):
    """Safe passive fixed-path projection; storage outage returns explicit unknown.

    identity excludes observation timestamps/pending counts; use it for target
    generation. Positive inherited-boot protection retains its original boot ID.
    """
    unknown = {'hardware_latched': None, 'hardware_latched_boot_id': None,
               'reason': 'hardware_latch_unknown', 'identity': None}
    try:
        required = tuple(gpu_uuids)
        if not required or any(gpu not in GPU_UUIDS for gpu in required):
            return unknown
        state = HardwareLatch(RegisteredLatchStore(binding).read()).export_state()
        positives = [(gpu, state['targets'][gpu]) for gpu in required
                     if state['targets'].get(gpu, {}).get('hardware_latched') is True]
        identity = []
        for gpu in required:
            record = state['targets'].get(gpu, {})
            proof = state.get('validated', {}).get(gpu, {})
            if record.get('hardware_latched') is True:
                identity.append([gpu, record['boot_id'], record['reason'], record['hardware_fault_code']])
            elif proof:
                identity.append([gpu, proof['boot_id'], 'validated'])
            else:
                identity.append([gpu, 'unvalidated'])
        # Proof age affects availability, never canonical semantic generation.
        # A valid protected read with missing/stale proof still has identity.
        unknown = {**unknown, 'identity': identity}
        if positives:
            return {'hardware_latched': True, 'hardware_latched_boot_id': positives[0][1]['boot_id'],
                    'reason': positives[0][1]['reason'], 'identity': identity}
        current_boot_id = current_boot_id or boot_identity()['boot_id']
        if not BOOT.fullmatch(current_boot_id):
            return unknown
        proofs = state.get('validated', {})
        ages = []
        now = wall()
        for gpu in required:
            proof = proofs.get(gpu, {})
            observed = _timestamp(proof.get('observed_at'))
            if (proof.get('boot_id') != current_boot_id or observed is None
                    or not 0 <= (now - observed) * 1000 <= MAX_AGE_MS):
                return unknown
            ages.append((now - observed) * 1000)
        return {'hardware_latched': False, 'hardware_latched_boot_id': None, 'reason': None,
                'hardware_validation_age_ms': max(ages),
                'hardware_validated_boot_id': current_boot_id,
                'hardware_validated_gpu_uuids': list(required),
                'identity': identity}

    except Exception:
        return unknown


class HardwarePolicy:
    """Producer/start gate invoked inside the existing owner's canonical lease."""
    def __init__(self, store, *, lease, run=_run, boot=boot_identity,
                 system_root=Path('/'), trusted_uid=0, wall=time.time, monotonic=time.monotonic):
        self.store, self.lease, self.run, self.boot = store, lease, run, boot
        self.system_root, self.trusted_uid, self.wall = system_root, trusted_uid, wall
        self.monotonic = monotonic

    def _owner(self):
        _validate_borrowed_lease(self.lease, system_root=self.system_root, trusted_uid=self.trusted_uid)
        return ProtectedHardwareLatch(self.store)

    def collect_inventory(self):
        before = self.boot()
        raw = self.run(['/usr/bin/nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader,nounits'], timeout=2)
        after = self.boot()
        if not isinstance(raw, str) or len(raw) > 65536 or before['boot_id'] != after['boot_id']:
            raise LifecycleError('hardware_inventory_unknown')
        rows = [line.strip() for line in raw.splitlines() if line.strip()]
        if len(rows) > 64 or any(not UUID.fullmatch(row) for row in rows) or len(set(rows)) != len(rows):
            raise LifecycleError('hardware_inventory_unknown')
        return dict(state='ok', freshness='fresh', age_ms=0, complete=True,
                    boot_id=after['boot_id'], gpu_uuids=rows, hardware_faults={},
                    observation_id=uuid.uuid4().hex,
                    observed_at=datetime.datetime.fromtimestamp(self.wall(), datetime.timezone.utc).isoformat()), after

    def observe_inventory(self, inventory, *, boot_age_seconds):
        started = self.monotonic()
        latch = self._owner()
        boot = self.boot()
        results = {}
        for gpu in GPU_UUIDS:
            value = dict(inventory)
            # Storage/lease work must not make delayed hardware evidence fresh.
            if type(value.get('age_ms')) in (int, float):
                value['age_ms'] += max(0, self.monotonic() - started) * 1000
            results[gpu] = latch.observe(gpu, value, current_boot_id=boot['boot_id'],
                                         boot_age_seconds=boot['uptime_seconds'])
        return results

    def validate_required(self, gpu_uuid, *, current_boot_id, observed_at, observation_id):
        """Trusted exact-UUID collector result; not an HTTP readiness assertion.

        The producer proves exact UUID identity and boot stability across its
        hardware probe. This method checks freshness again AFTER protected read.
        Same-boot positive latches remain sticky; only inherited protection may
        clear. Caller supplies no file path and must already hold canonical lease.
        """
        if gpu_uuid not in GPU_UUIDS or not BOOT.fullmatch(current_boot_id):
            raise LifecycleError('hardware_requirement_invalid')
        latch = self._owner()
        boot = self.boot()
        observed = _timestamp(observed_at)
        if (boot['boot_id'] != current_boot_id or observed is None
                or not 0 <= (self.wall() - observed) * 1000 <= MAX_AGE_MS):
            raise LifecycleError('hardware_validation_stale')
        return latch.validate_required(gpu_uuid, current_boot_id=current_boot_id,
                                       receipt={'observed_at': observed_at, 'observation_id': observation_id})

    def require_start(self, gpu_uuids):
        required = tuple(gpu_uuids)
        if not required or len(set(required)) != len(required) or any(gpu not in GPU_UUIDS for gpu in required):
            raise LifecycleError('hardware_requirement_invalid')
        latch = self._owner()
        before = self.boot()
        for gpu in required:
            saved = latch.export_state()['targets'].get(gpu)
            if saved and saved['hardware_latched'] and saved['boot_id'] == before['boot_id']:
                raise LifecycleError(saved['reason'])
            try:
                raw = self.run(['/usr/bin/nvidia-smi', '--id=' + gpu, '--query-gpu=uuid',
                                '--format=csv,noheader,nounits'], timeout=2)
                after = self.boot()
                if not isinstance(raw, str) or len(raw) > 4096 or raw.strip() != gpu or before['boot_id'] != after['boot_id']:
                    raise LifecycleError('hardware_target_unknown')
            except Exception:
                # A target error itself is UNKNOWN. Only a separate successful
                # complete inventory can prove absence; no message/error parsing.
                try:
                    inventory, identity = self.collect_inventory()
                    for target in required:
                        latch.observe(target, inventory, current_boot_id=identity['boot_id'],
                                      boot_age_seconds=identity['uptime_seconds'])
                except (OSError, RuntimeError, ValueError, subprocess.SubprocessError, LifecycleError):
                    pass
                saved = latch.export_state()['targets'].get(gpu)
                raise LifecycleError(saved['reason'] if saved and saved['hardware_latched']
                                     else 'hardware_target_unknown') from None
            result = latch.validate_required(gpu, current_boot_id=after['boot_id'],
                receipt={'observed_at': datetime.datetime.fromtimestamp(self.wall(), datetime.timezone.utc).isoformat(),
                         'observation_id': uuid.uuid4().hex})
            if result['hardware_latched']:
                raise LifecycleError(result['reason'])
        return True
