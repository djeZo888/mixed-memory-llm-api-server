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
import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path

from common.lifecycle_lease import _validate_borrowed_lease
from control.hardware_latch import HardwareLatch, ProtectedHardwareLatch, LatchStorageUnavailable, _timestamp, MAX_AGE_MS
from lifecycle.runtime_io import LifecycleError

STATE_SUFFIX = 'llm-manager/hardware-latch.json'
INITIALIZATION_SUFFIX = 'llm-manager/hardware-latch.initialized.json'
INITIALIZATION_REVIEW_SUFFIX = 'llm-manager/evidence/h005-latch-first-install.reviewed.json'
GPU_UUIDS = ('GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237',
             'GPU-69acfa26-8b60-61b5-702d-aee252c163cc',
             'GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23')
UUID = re.compile(r'GPU-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z')
BOOT = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z')
BOOT_PROBE_BUDGET_SECONDS = 30.0
BOOT_PROBE_BACKOFF_SECONDS = 0.5


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

    def initialize(self):
        """Explicit first activation only; never called by starts or observers.

        An exclusive durable marker precedes the exclusive state creation. A
        partial initialization stays closed for reviewed recovery; retry cannot
        erase old state or interpret a deleted latch as a first installation.
        The protected review must attest absence across retained owner releases.
        """
        from control.hardware_latch import empty_state
        from lifecycle.storage_binding import _entered_storage_context
        _validate_borrowed_lease(self.lease, system_root=self.system_root, trusted_uid=self.trusted_uid)
        review = self.binding.read_json('services', self.binding.path('services', INITIALIZATION_REVIEW_SUFFIX))
        if (set(review) != {'schema_version', 'kind', 'status', 'reviewed_source_commit', 'absence_evidence_sha256'}
                or type(review['schema_version']) is not int or review['schema_version'] != 1
                or review['kind'] != 'h005-latch-first-install'
                or review['status'] != 'REVIEWED_NO_PRIOR_STATE'
                or not re.fullmatch(r'[0-9a-f]{40}', str(review['reviewed_source_commit']))
                or not re.fullmatch(r'[0-9a-f]{64}', str(review['absence_evidence_sha256']))):
            raise LifecycleError('hardware_latch_first_install_review_required')
        if self.storage_io is None:
            from install import storage_io
        else:
            storage_io = self.storage_io
        self.binding.storage.root_payload_guard(self.binding.registry, roles=('data',))
        for suffix in (STATE_SUFFIX, INITIALIZATION_SUFFIX):
            self.binding.validate_path('services', self.binding.path('services', suffix))
        try:
            with self.binding.mounted_guard(storage_io, roles=('data',)) as guard:
                with _entered_storage_context(storage_io.AnchoredRoot(self.binding.path('services'), guard)) as anchored:
                    # Parent provisioning is a separate reviewed publication step.
                    if any(anchored.stat(name, missing_ok=True) is not None
                           for name in (STATE_SUFFIX, INITIALIZATION_SUFFIX)):
                        raise LifecycleError('hardware_latch_already_initialized_or_present')
                    marker = {'schema_version': 1, 'kind': 'h005-latch-initialization',
                              'review_sha256': hashlib.sha256(json.dumps(review, sort_keys=True,
                                  separators=(',', ':')).encode()).hexdigest()}
                    for name, value in ((INITIALIZATION_SUFFIX, marker), (STATE_SUFFIX, empty_state())):
                        with anchored.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) as stream:
                            stream.write((json.dumps(value, sort_keys=True) + '\n').encode())
                            stream.fsync()
                        with anchored.directory('llm-manager') as parent:
                            os.fsync(parent.fileno())
                    anchored.check()
        finally:
            self.binding.storage.root_payload_guard(self.binding.registry, roles=('data',))
        _validate_borrowed_lease(self.lease, system_root=self.system_root, trusted_uid=self.trusted_uid)
        return self.read()

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
                    HardwareLatch(anchored.read_json(STATE_SUFFIX, max_bytes=65536))
                    HardwareLatch(value)
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
                 system_root=Path('/'), trusted_uid=0, wall=time.time, monotonic=time.monotonic,
                 sleep=time.sleep):
        self.store, self.lease, self.run, self.boot = store, lease, run, boot
        self.system_root, self.trusted_uid, self.wall = system_root, trusted_uid, wall
        self.monotonic = monotonic
        self.sleep = sleep

    def _owner(self):
        _validate_borrowed_lease(self.lease, system_root=self.system_root, trusted_uid=self.trusted_uid)
        return ProtectedHardwareLatch(self.store)

    def collect_inventory(self, *, timeout=2):
        before = self.boot()
        raw = self.run(['/usr/bin/nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader,nounits'], timeout=timeout)
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

    def require_start(self, gpu_uuids, *, boot_restore=False, diagnostic=None):
        """Boot may wait briefly for exact hardware evidence, never replay a start.

        The thirty-second probe/sleep budget includes at most one inventory fallback.
        Guards, protected writes and native startup are not retried. Manual calls
        retain one exact probe. A successful query is always checked on this boot;
        unknown evidence never admits a start, even when the budget expires.
        """
        required = tuple(gpu_uuids)
        if not required or len(set(required)) != len(required) or any(gpu not in GPU_UUIDS for gpu in required):
            raise LifecycleError('hardware_requirement_invalid')
        latch = self._owner()
        before = self.boot()
        for gpu in required:
            started = self.monotonic()
            deadline = started + BOOT_PROBE_BUDGET_SECONDS
            attempts = []
            def report(result):
                if diagnostic is not None:
                    diagnostic({'schema_version': 1, 'boot_id': before['boot_id'],
                        'gpu_uuid': gpu, 'boot_restore': boot_restore,
                        'budget_seconds': BOOT_PROBE_BUDGET_SECONDS if boot_restore else 2,
                        'attempts': attempts, 'result': result,
                        'elapsed_ms': round(max(0, self.monotonic() - started) * 1000, 3)})
            saved = latch.export_state()['targets'].get(gpu)
            if saved and saved['hardware_latched'] and saved['boot_id'] == before['boot_id']:
                report(saved['reason'])
                raise LifecycleError(saved['reason'])
            inventory_attempted = False
            outcome = 'unknown'
            for _ in range(61 if boot_restore else 1):
                _validate_borrowed_lease(self.lease, system_root=self.system_root, trusted_uid=self.trusted_uid)
                remaining = deadline - self.monotonic()
                if boot_restore and remaining <= 0:
                    break
                if self.boot()['boot_id'] != before['boot_id']:
                    report('boot_changed')
                    raise LifecycleError('hardware_target_unknown')
                probe_started = self.monotonic()
                remaining = deadline - probe_started
                if boot_restore and remaining <= 0:
                    break
                timeout = min(2, remaining) if boot_restore else 2
                outcome = 'exact_uuid'
                try:
                    raw = self.run(['/usr/bin/nvidia-smi', '--id=' + gpu, '--query-gpu=uuid',
                                    '--format=csv,noheader,nounits'], timeout=timeout)
                    if not isinstance(raw, str) or len(raw) > 4096 or raw.strip() != gpu:
                        outcome = 'invalid_result'
                except (OSError, RuntimeError, ValueError, subprocess.SubprocessError, LifecycleError) as exc:
                    # Enumerated codes only: never retain raw output/exception text.
                    outcome = ('timeout' if isinstance(exc, subprocess.TimeoutExpired)
                               or isinstance(exc, LifecycleError) and exc.code == 'command_timeout'
                               else exc.code if isinstance(exc, LifecycleError)
                               and exc.code in {'command_failed', 'command_unavailable'} else 'probe_failed')
                ended = self.monotonic()
                observed_at = datetime.datetime.fromtimestamp(self.wall(), datetime.timezone.utc).isoformat()
                if ended - probe_started > timeout:
                    outcome = 'timeout'
                if self.boot()['boot_id'] != before['boot_id']:
                    outcome = 'boot_changed'
                attempts.append({'kind': 'target', 'outcome': outcome,
                    'observed_at': observed_at,
                    'duration_ms': round(max(0, ended - probe_started) * 1000, 3)})
                if outcome == 'exact_uuid':
                    report('exact_uuid')
                    # Keep the probe's timestamp through diagnostic/protected I/O.
                    # Existing freshness and same-boot latch checks still apply.
                    result = self.validate_required(gpu, current_boot_id=before['boot_id'],
                        observed_at=observed_at, observation_id=uuid.uuid4().hex)
                    if result['hardware_latched']:
                        raise LifecycleError(result['reason'])
                    # validate_required rereads protected state. Later targets'
                    # inventory fallback must retain this newly written proof.
                    latch = self._owner()
                    break
                if outcome == 'boot_changed':
                    report('boot_changed')
                    raise LifecycleError('hardware_target_unknown')
                # UNKNOWN alone cannot prove absence. Preserve the single
                # complete-inventory fallback, never repeat global NVML queries.
                remaining = deadline - self.monotonic()
                if not inventory_attempted and (not boot_restore or remaining > 0):
                    inventory_attempted = True
                    probe_started = self.monotonic()
                    inventory_outcome = 'inventory_unknown'
                    try:
                        inventory, identity = self.collect_inventory(timeout=min(2, remaining) if boot_restore else 2)
                        inventory_outcome = 'complete'
                    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError, LifecycleError):
                        inventory = None
                    attempts.append({'kind': 'inventory', 'outcome': inventory_outcome,
                        'duration_ms': round(max(0, self.monotonic() - probe_started) * 1000, 3)})
                    if inventory is not None and identity['boot_id'] == before['boot_id']:
                        # This fallback diagnoses the failed target only; it
                        # cannot revoke an independent exact-positive peer.
                        saved = latch.export_state()['targets'].get(gpu)
                        inherited_positive = (boot_restore and saved and saved['hardware_latched']
                            and saved['boot_id'] != before['boot_id']
                            and gpu in inventory['gpu_uuids'] and gpu not in inventory['hardware_faults'])
                        # Presence in a global fallback must not clear inherited
                        # protection while this target's exact probe is UNKNOWN.
                        if not inherited_positive:
                            latch.observe(gpu, inventory, current_boot_id=identity['boot_id'],
                                          boot_age_seconds=identity['uptime_seconds'])
                saved = latch.export_state()['targets'].get(gpu)
                if (saved and saved['hardware_latched']
                        and (not boot_restore or saved['boot_id'] == before['boot_id'])):
                    report(saved['reason'])
                    raise LifecycleError(saved['reason'])
                if boot_restore:
                    self.sleep(min(BOOT_PROBE_BACKOFF_SECONDS, max(0, deadline - self.monotonic())))
            else:
                outcome = 'unknown'
            if outcome != 'exact_uuid':
                report('unknown')
                saved = latch.export_state()['targets'].get(gpu)
                raise LifecycleError(saved['reason'] if saved and saved['hardware_latched']
                                     else 'hardware_target_unknown') from None
        return True
