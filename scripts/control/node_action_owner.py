"""Protected node operation adapter; delegates all lifecycle work to existing owners.

A single admission/execution slot takes the existing canonical lifecycle lease.
There is no model selector, scheduler, alternate lock, automatic retry, or recovery
engine here. Disk I/O can occupy that slot indefinitely without replacement-thread
growth; HTTP admission times out independently and status remains cached.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import threading
import time
from types import SimpleNamespace
import uuid

from common.lifecycle_lease import acquire_lease, LeaseBusy
from .node_actions import (ActionRequest, DurableReceipt, NodeActionError, SERVICES,
                           BOOT, ERRORS, _receipt, matches, require)

MAX_BYTES = 1024 * 1024
MAX_OPERATIONS = 128
JOURNAL_SUFFIX = 'llm-node/operations.json'
CONFIG_ROOT = Path('/usr/local/lib/llm-server/node-api/configs')
TERMINAL = {'succeeded', 'failed', 'interrupted'}
DIGEST = re.compile('[0-9a-f]{64}')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def current_boot():
    value = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    require(matches(BOOT, value), 'observation_unavailable')
    return value


def utc():
    return datetime.now(timezone.utc).isoformat()


class RegisteredNodeStore:
    """Use existing protected registered manager writer; never root fallback."""
    def __init__(self, manager_loader):
        self.manager_loader = manager_loader

    def read(self):
        manager = self.manager_loader()
        path = manager.binding.path('services', JOURNAL_SUFFIX)
        local = manager.binding.validate_path('services', path)
        if not local.exists():
            manager.binding.validate_path('services', path)
            return None
        return manager.binding.read_json('services', path, maximum=MAX_BYTES)

    def write(self, value):
        manager = self.manager_loader()
        guard = manager.binding.storage.root_payload_guard
        guard(manager.binding.registry, roles=('data',))
        try:
            manager.persistent_json(manager.binding.path('services', JOURNAL_SUFFIX), value)
        finally:
            guard(manager.binding.registry, roles=('data',))


def validated_journal(value):
    if value is None:
        return {'schema_version': 1, 'operations': {}}
    try:
        require(type(value) is dict and set(value) == {'schema_version', 'operations'}
                and type(value['schema_version']) is int and value['schema_version'] == 1,
                'storage_unavailable')
        entries = value['operations']
        require(type(entries) is dict and len(entries) <= MAX_OPERATIONS, 'storage_unavailable')
        keys = []
        for operation_id, entry in entries.items():
            require(type(entry) is dict and set(entry) == {'receipt', 'request_digest', 'key_digest',
                'dispatch_recorded', 'audit'}, 'storage_unavailable')
            _receipt(DurableReceipt(entry['receipt'], True), operation_id=operation_id)
            require(all(matches(DIGEST, entry[k]) for k in ('request_digest', 'key_digest'))
                    and type(entry['dispatch_recorded']) is bool, 'storage_unavailable')
            audit = entry['audit']
            require(type(audit) is list and 1 <= len(audit) <= 8, 'storage_unavailable')
            for item in audit:
                require(type(item) is dict and set(item) == {'at', 'event', 'reason'}
                        and type(item['at']) is str and len(item['at']) <= 40
                        and item['event'] in {'accepted', 'dispatch', 'succeeded', 'failed',
                                              'interrupted', 'unknown'}
                        and (item['reason'] is None or item['reason'] in ERRORS), 'storage_unavailable')
            keys.append(entry['key_digest'])
        require(len(set(keys)) == len(keys) and
                len(json.dumps(value, allow_nan=False).encode()) <= MAX_BYTES, 'storage_unavailable')
        return copy.deepcopy(value)
    except Exception:
        raise NodeActionError('storage_unavailable') from None


class _Ticket:
    def __init__(self, request, deadline):
        self.request, self.deadline = request, deadline
        self.condition = threading.Condition()
        self.result = self.error = None
        self.expired = False

    def answer(self, *, result=None, error=None):
        with self.condition:
            self.result, self.error = result, error
            self.condition.notify_all()


class ProductionNodeActionOwner:
    """One bounded slot; CAS and journal before dispatch using canonical lease.

    identity_reader(request, lease, deadline) must independently read protected
    canonical identity, ownership and boot latch. It must not use harness idle
    claims, passive metric timestamps or cached GET status as mutation authority.
    dispatcher performs existing owner calls only, with the same lease when the
    call is in-process. Fixed systemd jobs acquire that lease in their own owner
    after scheduling; completion is observed after releasing this lease.
    """
    def __init__(self, store, identity_reader, dispatcher, *, lease_factory=acquire_lease,
                 boot_reader=current_boot, monotonic=time.monotonic, transition_seconds=1920, autostart=True):
        self.store, self.identity_reader, self.dispatcher = store, identity_reader, dispatcher
        self.lease_factory, self.boot_reader, self.monotonic = lease_factory, boot_reader, monotonic
        self.transition_seconds = transition_seconds
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._pending = None
        self._busy = self._closed = self._loaded = False
        self._state = {'schema_version': 1, 'operations': {}}
        self._thread = threading.Thread(target=self._work, name='node-owner-adapter', daemon=True)
        if autostart:
            self.start()

    def start(self):
        # Production calls only after the fixed listener is successfully bound;
        # a second failed bind must not reconcile the running owner's journal.
        with self._lock:
            require(not self._closed, 'owner_unavailable')
            if self._thread.ident is None:
                self._thread.start()
            self._wake.set()

    def close(self):
        with self._lock:
            self._closed = True
            if self._pending is not None:
                self._pending.answer(error=NodeActionError('owner_unavailable'))
                self._pending = None
        self._wake.set()
        if self._thread.ident is not None:
            self._thread.join(timeout=.1)
        return not self._thread.is_alive()

    def _save(self, state):
        state = validated_journal(state)
        try:
            require(self.store.write(state) is not False, 'storage_unavailable')
        except Exception:
            # A rename/fsync/post-guard error may have persisted the record.
            # Re-read before any subsequent admission; never overwrite it from
            # a stale in-memory cache and accidentally replay the same key.
            with self._lock:
                self._loaded = False
            raise NodeActionError('storage_unavailable') from None
        with self._lock:
            self._state = state

    def _load(self):
        try:
            state = validated_journal(self.store.read())
            boot = self.boot_reader()
            require(matches(BOOT, boot), 'observation_unavailable')
            changed = False
            for entry in state['operations'].values():
                receipt = entry['receipt']
                if receipt['status'] not in TERMINAL:
                    reboot = receipt['action'] == 'node.reboot' and entry['dispatch_recorded']
                    success = reboot and receipt['expected_boot_id'] != boot
                    status = 'succeeded' if success else 'unknown' if reboot else 'interrupted'
                    reason = None if success else 'reboot_pending' if reboot else 'operation_interrupted'
                    if receipt['status'] != status or receipt['reason'] != reason:
                        receipt.update(status=status, reason=reason, updated_at=utc())
                        entry['audit'].append({'at': receipt['updated_at'], 'event': status, 'reason': reason})
                        changed = True
            if changed:
                self._save(state)
            else:
                with self._lock:
                    self._state = state
            self._loaded = True
        except Exception:
            self._loaded = False
            raise NodeActionError('storage_unavailable') from None

    def _replay(self, request):
        key = digest(request.idempotency_key)
        for entry in self._state['operations'].values():
            if entry['key_digest'] == key:
                require(entry['request_digest'] == digest(request.wire()), 'idempotency_conflict')
                return DurableReceipt(copy.deepcopy(entry['receipt']), True)
        return None

    def accept(self, request, *, deadline):
        with self._lock:
            replay = self._replay(request) if self._loaded else None
            if replay is not None:
                return replay
            require(not self._closed, 'owner_unavailable')
            require(not self._busy and self._pending is None, 'lifecycle_busy')
            require(self.monotonic() < deadline, 'deadline_exceeded')
            ticket = self._pending = _Ticket(request, deadline)
            self._wake.set()
        with ticket.condition:
            while ticket.result is None and ticket.error is None:
                remaining = deadline - self.monotonic()
                if remaining <= 0:
                    ticket.expired = True
                    raise NodeActionError('deadline_exceeded')
                ticket.condition.wait(remaining)
            if ticket.error is not None:
                raise ticket.error
            return ticket.result

    def operation(self, operation_id, *, deadline):
        require(self.monotonic() < deadline, 'deadline_exceeded')
        with self._lock:
            entry = self._state['operations'].get(operation_id)
            require(entry is not None, 'operation_unknown')
            return DurableReceipt(copy.deepcopy(entry['receipt']), True)

    def _identity(self, request, lease, deadline):
        lease.validate()
        require(not self._closed, 'owner_unavailable')
        require(self.monotonic() < deadline, 'deadline_exceeded')
        value = self.identity_reader(request, lease, deadline)
        require(type(value) is dict and value.get('boot_id') == request.expected_boot_id
                and value.get('generation') == request.expected_generation, 'stale_state')
        require(value.get('ownership_valid') is True, 'observation_unavailable')
        affected = value.get('affected_services')
        require(type(affected) is list and len(set(affected)) == len(affected)
                and all(s in SERVICES for s in affected), 'observation_unavailable')
        if request.service_id:
            require(affected == [request.service_id], 'observation_unavailable')
        if request.action == 'node.reboot':
            require(set(affected) == SERVICES, 'observation_unavailable')
        if request.action in {'service.start', 'service.restart'} and request.service_id != 'control':
            inherited = (value.get('hardware_latched') is True
                         and matches(BOOT, value.get('hardware_latched_boot_id'))
                         and value['hardware_latched_boot_id'] != request.expected_boot_id)
            # This admits only an audited hardware-validation attempt. The owner
            # validates the exact UUID, then final CAS refuses if clearing the
            # inherited latch changes generation. It does not start the service.
            require(value.get('hardware_latched') is False or inherited, 'hardware_unavailable')
        require(request.action == 'service.start' or request.allow_interrupt, 'interruption_ack_required')
        return value

    def _record(self, request, identity):
        require(len(self._state['operations']) < MAX_OPERATIONS, 'journal_full')
        operation_id, now = uuid.uuid4().hex, utc()
        receipt = dict(schema_version=1, operation_id=operation_id, node_id='ai-vm',
                       action=request.action, service_id=request.service_id, gpu_uuid=request.gpu_uuid,
                       status='accepted', poll_url='/control/v1/node/operations/' + operation_id,
                       created_at=now, updated_at=now, reason=None,
                       affected_services=list(identity['affected_services']),
                       expected_boot_id=request.expected_boot_id, expected_generation=request.expected_generation)
        entry = dict(receipt=receipt, key_digest=digest(request.idempotency_key),
                     request_digest=digest(request.wire()), dispatch_recorded=False,
                     audit=[{'at': now, 'event': 'accepted', 'reason': None}])
        state = copy.deepcopy(self._state)
        state['operations'][operation_id] = entry
        self._save(state)
        return operation_id

    def _update(self, operation_id, status, reason=None, *, dispatch=False):
        state = copy.deepcopy(self._state)
        entry = state['operations'][operation_id]
        entry['receipt'].update(status=status, reason=reason, updated_at=utc())
        entry['dispatch_recorded'] |= dispatch
        entry['audit'].append({'at': entry['receipt']['updated_at'],
                               'event': 'dispatch' if dispatch else status, 'reason': reason})
        self._save(state)

    def _finish(self, operation_id, status, reason=None):
        # Status GET never reconciles. Completion metadata shares the canonical
        # lease too; failure leaves durable running/unknown state for recovery.
        with self.lease_factory(blocking=False) as lease:
            lease.validate()
            self._update(operation_id, status, reason)

    def _work(self):
        while True:
            signaled = self._wake.wait(timeout=5)
            self._wake.clear()
            if not signaled and self._loaded:
                continue
            with self._lock:
                if self._closed and self._pending is None:
                    return
                ticket, self._pending = self._pending, None
                self._busy = True
            operation_id = None
            try:
                result = request = None
                transition_deadline = self.monotonic() + self.transition_seconds
                with self.lease_factory(blocking=False) as lease:
                    if not self._loaded:
                        self._load()
                    if ticket is not None:
                        request = ticket.request
                        replay = self._replay(request)
                        if replay is not None:
                            ticket.answer(result=replay)
                        else:
                            identity = self._identity(request, lease, ticket.deadline)
                            self.dispatcher.preflight(request, identity, lease, ticket.deadline)
                            require(not ticket.expired and self.monotonic() < ticket.deadline, 'deadline_exceeded')
                            operation_id = self._record(request, identity)
                            # If durable write exhausted admission budget, do not mutate.
                            with ticket.condition:
                                require(not ticket.expired and self.monotonic() < ticket.deadline, 'deadline_exceeded')
                                ticket.answer(result=DurableReceipt(copy.deepcopy(
                                    self._state['operations'][operation_id]['receipt']), True))
                            identity = self._identity(request, lease, transition_deadline)
                            # Audit is durable before *any* dispatched owner mutation.
                            self._update(operation_id, 'running', dispatch=True)
                            identity = self._identity(request, lease, transition_deadline)
                            result = self.dispatcher.dispatch(request, identity, lease, transition_deadline)
                # systemd backend owners need the same lease after job dispatch.
                if operation_id is not None:
                    self.dispatcher.complete(request, result, transition_deadline)
                    if request.action == 'node.reboot':
                        self._finish(operation_id, 'unknown', 'reboot_pending')
                    else:
                        self._finish(operation_id, 'succeeded')
            except Exception as exc:
                code = 'lifecycle_busy' if isinstance(exc, LeaseBusy) else (
                    exc.code if isinstance(exc, NodeActionError) else 'operation_failed')
                if operation_id is not None:
                    try:
                        self._finish(operation_id, 'failed', code)
                    except Exception:
                        pass  # Last durable running state is uncertain; never replay.
                if ticket is not None and ticket.result is None:
                    ticket.answer(error=NodeActionError(code))
            finally:
                with self._lock:
                    self._busy = False


class FixedOwnerDispatcher:
    """Fixed owner bindings, including control recovery without control HTTP.

    Dedicated GPU reset remains unsupported on this VM until a reviewed native
    scope proof is supplied. A UUID parameter alone does not establish safe reset
    scope. No global reset command, Proxmox path, or VM reset assumption exists.
    """
    UNITS = {'control': ('llm-control.service',),
             'image': ('llm-image-api.service', 'llm-image-backend.service')}

    def __init__(self, manager_loader, *, command=None, identity_reader=None,
                 reset_proof=None, control_key=None, monotonic=time.monotonic, sleep=time.sleep):
        self.manager_loader, self.identity_reader = manager_loader, identity_reader
        self.command = command or self._command
        self.reset_proof, self.control_key = reset_proof, control_key
        self.monotonic, self.sleep = monotonic, sleep

    def _command(self, argv, seconds):
        from .node_collectors import command
        return command(argv, seconds)

    def _remaining(self, deadline, cap=2):
        remaining = min(cap, deadline - self.monotonic())
        require(remaining > 0, 'deadline_exceeded')
        return remaining

    def _systemd(self, unit, deadline):
        # Unit comes exclusively from fixed mappings, never the request.
        raw = self.command(['/usr/bin/systemctl', 'show', unit, '--no-pager',
                            '--property=LoadState,ActiveState,SubState,InvocationID,MainPID,Job'],
                           self._remaining(deadline))
        value = dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)
        require(value.get('LoadState') == 'loaded' and value.get('ActiveState') in
                {'active', 'inactive', 'failed', 'activating', 'deactivating', 'reloading'},
                'observation_unavailable')
        require(type(value.get('MainPID')) is str and value['MainPID'].isdigit()
                and 0 <= int(value['MainPID']) < 2**31, 'observation_unavailable')
        return value

    def _reset(self, request, identity, lease, deadline):
        require(self.reset_proof is not None, 'reset_scope_unproven')
        proof = self.reset_proof(request.gpu_uuid, lease, deadline)
        require(type(proof) is dict and proof.get('boot_id') == request.expected_boot_id
                and proof.get('gpu_uuid') == request.gpu_uuid
                and proof.get('dedicated_scope') == [request.gpu_uuid]
                and proof.get('supported') is True
                and proof.get('os_consumers_complete') is True, 'reset_scope_unproven')
        require(proof.get('os_consumers') == [] and proof.get('all_affected_services_stopped') is True
                and proof.get('affected_services') == identity['affected_services'], 'consumers_present')
        return proof

    def preflight(self, request, identity, lease, deadline):
        lease.validate()
        if request.action == 'gpu.reset':
            self._reset(request, identity, lease, deadline)
        elif request.action.startswith('service.') and request.service_id in self.UNITS:
            for unit in self.UNITS[request.service_id]:
                self._systemd(unit, deadline)
        elif request.lifecycle_target:
            # Full storage, source, package, placement and latch guards remain
            # in Manager.dispatch immediately before its owned mutation.
            require(type(identity.get('canonical_generation')) is int
                    and identity['canonical_generation'] >= 0, 'observation_unavailable')
        elif request.action != 'node.reboot':
            raise NodeActionError('unsupported_action')

    def _validate_inherited_image(self, request, identity, lease, deadline):
        if identity.get('hardware_latched') is not True:
            return
        require(matches(BOOT, identity.get('hardware_latched_boot_id'))
                and identity['hardware_latched_boot_id'] != request.expected_boot_id,
                'hardware_unavailable')
        require(self.identity_reader is not None, 'observation_unavailable')
        from lifecycle.hardware_policy import HardwarePolicy, RegisteredLatchStore
        from .node import SERVICES as GPU_REQUIREMENTS
        binding = self.identity_reader.binding(self._remaining(deadline))
        def run(argv, *, timeout=2):
            return self.command(argv, self._remaining(deadline, timeout))
        def boot():
            raw = self.identity_reader.boot()
            return {'boot_id': raw['boot_id'], 'uptime_seconds': raw.get('uptime_seconds', raw.get('boot_age_seconds'))}
        HardwarePolicy(RegisteredLatchStore(binding, lease=lease), lease=lease,
                       run=run, boot=boot).require_start(GPU_REQUIREMENTS['image'])

    def _recheck(self, request, identity, lease, deadline):
        # Slow preflight/source checks must not move CAS away from the actual
        # final owner call. The production reader is independently read-only.
        lease.validate()
        self._remaining(deadline)
        if self.identity_reader is not None:
            current = self.identity_reader(request, lease, deadline)
            require(current.get('boot_id') == request.expected_boot_id
                    and current.get('generation') == request.expected_generation, 'stale_state')
            require(current.get('ownership_valid') is True
                    and current.get('affected_services') == identity['affected_services'], 'observation_unavailable')
            if request.action in {'service.start', 'service.restart'} and request.service_id != 'control':
                require(current.get('hardware_latched') is False, 'hardware_unavailable')
        self._remaining(deadline)

    @staticmethod
    def _owned_invocation(value, *, running):
        require(type(value) is dict and matches(DIGEST, value.get('container_id'))
                and type(value.get('pid')) is int and 0 <= value['pid'] < 2**31
                and type(value.get('started_at')) is str and 1 <= len(value['started_at']) <= 128,
                'observation_unavailable')
        require(value['pid'] > 0 if running else value['pid'] == 0, 'observation_unavailable')
        return value

    def _settlement(self, request, before, after, deadline, *, old_absence_proven=False):
        if request.action not in {'service.stop', 'service.restart'}:
            return
        require(self.identity_reader is not None and after.get('ownership_valid') is True
                and after.get('boot_id') == request.expected_boot_id, 'observation_unavailable')
        old = before.get('owner_identity')
        # A new currently selected container alone cannot prove an orphan old
        # invocation is gone. The independent reader must inspect that OLD ID.
        if old is None and request.action == 'service.restart':
            # A healthy replacement now occupies the fixed name. Its presence
            # cannot invalidate absence that was independently proven under the
            # lease immediately before this operation's dispatch.
            require(old_absence_proven is True, 'observation_unavailable')
        else:
            require(self.identity_reader.old_owner_settled(request.service_id, old,
                        self._remaining(deadline)) is True, 'observation_unavailable')
        current = after.get('owner_identity')
        if request.action == 'service.stop':
            require(after.get('running') is False, 'observation_unavailable')
            if request.service_id == 'image':
                require(after.get('backend_running') is False, 'observation_unavailable')
            if current is not None:
                self._owned_invocation(current, running=False)
            return
        require(after.get('running') is True, 'observation_unavailable')
        current = self._owned_invocation(current, running=True)
        if old is not None:
            require(type(old) is dict and matches(DIGEST, old.get('container_id')),
                    'observation_unavailable')
            if current['container_id'] == old['container_id']:
                require(current['started_at'] != old.get('started_at')
                        and current['pid'] != old.get('pid'), 'observation_unavailable')
            if request.service_id == 'image':
                require(type(current.get('run_id')) is str and
                        re.fullmatch('[0-9a-f]{32}', current['run_id']) is not None
                        and current['run_id'] != old.get('run_id'), 'observation_unavailable')

    def _capture_old_absence(self, request, identity, lease, deadline):
        if (request.action != 'service.restart' or request.service_id == 'control'
                or identity.get('owner_identity') is not None):
            return False
        lease.validate()
        require(self.identity_reader is not None and self.identity_reader.old_owner_settled(
                request.service_id, None, self._remaining(deadline)) is True, 'observation_unavailable')
        return True

    def dispatch(self, request, identity, lease, deadline):
        lease.validate()
        if request.lifecycle_target:
            from .adapter import ManagerSession
            from .protocol import Deadline
            manager = self.manager_loader()
            session = ManagerSession(manager, None, self.control_key)
            if request.action in {'service.start', 'service.restart'}:
                session.preflight(identity['selected'], lease, Deadline(deadline), slot=request.lifecycle_target)
            self._recheck(request, identity, lease, deadline)
            old_absence_proven = self._capture_old_absence(request, identity, lease, deadline)
            if old_absence_proven:
                self._recheck(request, identity, lease, deadline)
            with session._bounded(Deadline(deadline)):
                result = manager.dispatch(request.action.split('.')[1], lease=lease,
                    target=request.lifecycle_target, expected_generation=identity['canonical_generation'])
            if request.action in {'service.stop', 'service.restart'}:
                require(self.identity_reader is not None, 'observation_unavailable')
                after = self.identity_reader.service(request.service_id, self._remaining(deadline))
                self._settlement(request, identity, after, deadline, old_absence_proven=old_absence_proven)
            return {'kind': 'manager', 'result': result}
        if request.action == 'gpu.reset':
            self._reset(request, identity, lease, deadline)
            self._recheck(request, identity, lease, deadline)
            self.command(['/usr/bin/nvidia-smi', '--gpu-reset', '-i', request.gpu_uuid],
                         self._remaining(deadline, 30))
            return {'kind': 'reset'}
        if request.action == 'node.reboot':
            self._recheck(request, identity, lease, deadline)
            self.command(['/usr/bin/systemctl', '--no-block', 'reboot'], self._remaining(deadline))
            return {'kind': 'reboot'}
        if request.service_id == 'image' and request.action in {'service.start', 'service.restart'}:
            self._validate_inherited_image(request, identity, lease, deadline)
        units = self.UNITS[request.service_id]
        old = {unit: self._systemd(unit, deadline) for unit in units}
        action = request.action.split('.')[1]
        # The public image owner starts/reconciles backend. Stop both owners;
        # never leave a still-running native backend behind an inactive API.
        selected = units if action == 'stop' else units[:1]
        self._recheck(request, identity, lease, deadline)
        old_absence_proven = self._capture_old_absence(request, identity, lease, deadline)
        if old_absence_proven:
            self._recheck(request, identity, lease, deadline)
        self.command(['/usr/bin/systemctl', '--no-block', action, *selected], self._remaining(deadline))
        return {'kind': 'systemd', 'old': old, 'units': selected, 'action': action, 'before': copy.deepcopy(identity), 'old_absence_proven': old_absence_proven}

    def complete(self, request, result, deadline):
        if result['kind'] in {'manager', 'reset', 'reboot'}:
            return
        while True:
            current = {unit: self._systemd(unit, deadline) for unit in result['units']}
            stopped = result['action'] == 'stop'
            desired = all(v['ActiveState'] == ('inactive' if stopped else 'active')
                          and (int(v['MainPID']) == 0 if stopped else int(v['MainPID']) > 0)
                          and v.get('Job') in {'', '0', '[0, /]'} for v in current.values())
            restarted = result['action'] != 'restart' or all(
                v.get('InvocationID') and v['InvocationID'] != result['old'][u].get('InvocationID')
                and (int(result['old'][u]['MainPID']) == 0 or v['MainPID'] != result['old'][u]['MainPID'])
                for u, v in current.items())
            if any(v['ActiveState'] == 'failed' for v in current.values()):
                raise NodeActionError('operation_failed')
            if desired and restarted:
                if request.service_id == 'image':
                    require(self.identity_reader is not None, 'observation_unavailable')
                    # Independent concrete backend ownership after delegated job.
                    try:
                        observed = self.identity_reader.observe('image', self._remaining(deadline))
                    except Exception:
                        # Startup ownership/HTTP publication can be temporarily
                        # unknown. Poll passively without replaying the action.
                        self.sleep(min(.25, self._remaining(deadline)))
                        continue
                    require(observed.get('ownership_valid') is True, 'observation_unavailable')
                    if stopped:
                        require(observed.get('backend_running') is False and observed.get('running') is False, 'observation_unavailable')
                    elif observed.get('running') is not True or observed.get('ready') is not True:
                        self.sleep(min(.25, self._remaining(deadline)))
                        continue
                    self._settlement(request, result['before'], observed, deadline,
                                     old_absence_proven=result.get('old_absence_proven') is True)
                return
            self.sleep(min(.25, self._remaining(deadline)))


def production_owner(identity_reader, *, control_key, config_root=CONFIG_ROOT):
    """Lazy construction: failed storage/control/chat never prevents node listen."""
    def manager_loader():
        from lifecycle.manager import load_manager
        return load_manager(SimpleNamespace(instance=None), Path(config_root))
    return ProductionNodeActionOwner(RegisteredNodeStore(manager_loader), identity_reader,
        FixedOwnerDispatcher(manager_loader, identity_reader=identity_reader, control_key=control_key), autostart=False)
