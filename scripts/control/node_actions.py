"""Strict H005 typed action boundary for the protected canonical owner adapter.

No HTTP input selects a command, path, URL, unit, model, or deployment. The
production owner persists and audits before dispatch under the existing lease.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import re
import time
from typing import Protocol


NODE = 'ai-vm'
SERVICE_TARGETS = {'qwen-gpu0': 'glm', 'qwen-gpu1': 'qwen'}
SERVICES = frozenset((*SERVICE_TARGETS, 'image', 'control'))
ACTIONS = frozenset(('service.start', 'service.stop', 'service.restart', 'gpu.reset', 'node.reboot'))
BOOT = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
GPU = re.compile(r'GPU-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
# Registration is separate from discovery. Extra inventory GPUs remain visible
# but do not become action targets, acquire model assignments, or gain reset scope.
REGISTERED_GPUS = frozenset((
    'GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237',
    'GPU-69acfa26-8b60-61b5-702d-aee252c163cc',
    'GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23',
    'GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528',
))
KEY = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}')
OPID = re.compile(r'[0-9a-f]{32}')
STATUSES = frozenset(('accepted', 'running', 'succeeded', 'failed', 'interrupted', 'unknown'))
ERRORS = {
    'invalid_request': 400, 'operation_unknown': 404,
    'idempotency_conflict': 409, 'stale_state': 409, 'interruption_ack_required': 409,
    'lifecycle_busy': 409, 'hardware_unavailable': 409,
    'unsupported_action': 422,
    'owner_unavailable': 503, 'storage_unavailable': 503,
    'deadline_exceeded': 503, 'observation_unavailable': 503,
    'invalid_owner_receipt': 503, 'operation_interrupted': 503,
    'operation_failed': 503, 'reset_scope_unproven': 422,
    'consumers_present': 409, 'reboot_pending': 503, 'journal_full': 503,
}


class NodeActionError(Exception):
    def __init__(self, code):
        self.code = code if code in ERRORS else 'owner_unavailable'
        self.status = ERRORS[self.code]
        super().__init__(self.code)


def require(condition, code='invalid_request'):
    if not condition:
        raise NodeActionError(code)


def matches(pattern, value):
    return type(value) is str and pattern.fullmatch(value) is not None


@dataclass(frozen=True)
class ActionRequest:
    schema_version: int
    node_id: str
    action: str
    idempotency_key: str
    expected_boot_id: str
    expected_generation: int
    allow_interrupt: bool
    service_id: str | None = None
    gpu_uuid: str | None = None

    @classmethod
    def parse(cls, value):
        require(type(value) is dict and type(value.get('action')) is str and value['action'] in ACTIONS)
        action = value['action']
        keys = {'schema_version', 'node_id', 'action', 'idempotency_key',
                'expected_boot_id', 'expected_generation', 'allow_interrupt'}
        if action.startswith('service.'):
            keys.add('service_id')
            require(type(value.get('service_id')) is str and value['service_id'] in SERVICES)
        elif action == 'gpu.reset':
            keys.add('gpu_uuid')
            require(matches(GPU, value.get('gpu_uuid')) and value['gpu_uuid'] in REGISTERED_GPUS)
        require(set(value) == keys)
        require(type(value['schema_version']) is int and value['schema_version'] == 1
                and value['node_id'] == NODE and type(value['node_id']) is str
                and matches(KEY, value['idempotency_key'])
                and matches(BOOT, value['expected_boot_id'])
                and type(value['expected_generation']) is int
                and 0 <= value['expected_generation'] < 2**63
                and type(value['allow_interrupt']) is bool)
        return cls(**value)

    @property
    def lifecycle_target(self):
        """Registered placement mapping only; never choose another deployment."""
        return SERVICE_TARGETS.get(self.service_id)

    def wire(self):
        value = asdict(self)
        if self.service_id is None:
            value.pop('service_id')
        if self.gpu_uuid is None:
            value.pop('gpu_uuid')
        return value


@dataclass(frozen=True)
class DurableReceipt:
    """Internal owner attestation; never deserialized from HTTP input.

    The reviewed owner alone may attest its protected journal write. The bool
    is not evidence that arbitrary adapters are durable; production requires
    adapter review and actual protected-owner acceptance separately.
    """
    receipt: dict
    durable: bool


class CanonicalActionOwner(Protocol):
    def accept(self, request: ActionRequest, *, deadline: float) -> DurableReceipt:
        """Replay/check/record under canonical ownership; async execute once.

        Exact repeats return the original receipt even after boot/generation
        changes; key mismatch raises idempotency_conflict. A new request must
        check deadline, boot/generation, registered impact, latch and work under
        the canonical lease before persistence or dispatch. Never blind replay
        unfinished mutations after restart. No competing model lifecycle or alternate lifecycle lock.
        """
        ...

    def operation(self, operation_id: str, *, deadline: float) -> DurableReceipt:
        """Read bounded cached durable receipt; no reconcile/probe/mutation."""
        ...


def _utc(value):
    if type(value) is not str or len(value) > 40:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.utcoffset() == timedelta(0)
    except ValueError:
        return False


def _receipt(result, *, request=None, operation_id=None):
    require(type(result) is DurableReceipt and result.durable is True, 'invalid_owner_receipt')
    value = result.receipt
    keys = {'schema_version', 'operation_id', 'node_id', 'action', 'service_id', 'gpu_uuid',
            'status', 'poll_url', 'created_at', 'updated_at', 'reason', 'affected_services',
            'expected_boot_id', 'expected_generation'}
    require(type(value) is dict and set(value) == keys, 'invalid_owner_receipt')
    require(type(value['schema_version']) is int and value['schema_version'] == 1
            and value['node_id'] == NODE and matches(OPID, value['operation_id'])
            and value['action'] in ACTIONS
            and ((value['action'].startswith('service.') and value['service_id'] in SERVICES and value['gpu_uuid'] is None)
                 or (value['action'] == 'gpu.reset' and value['service_id'] is None and matches(GPU, value['gpu_uuid']) and value['gpu_uuid'] in REGISTERED_GPUS)
                 or (value['action'] == 'node.reboot' and value['service_id'] is None and value['gpu_uuid'] is None))
            and value['status'] in STATUSES
            and value['poll_url'] == '/control/v1/node/operations/' + value['operation_id']
            and _utc(value['created_at']) and _utc(value['updated_at'])
            and (value['reason'] is None or value['reason'] in ERRORS)
            and type(value['affected_services']) is list
            and all(type(s) is str and s in SERVICES for s in value['affected_services'])
            and len(set(value['affected_services'])) == len(value['affected_services'])
            and (not value['action'].startswith('service.') or value['affected_services'] == [value['service_id']])
            and (value['action'] != 'node.reboot' or set(value['affected_services']) == SERVICES)
            and matches(BOOT, value['expected_boot_id'])
            and type(value['expected_generation']) is int and 0 <= value['expected_generation'] < 2**63,
            'invalid_owner_receipt')
    if request is not None:
        require(all(value[name] == getattr(request, name) for name in
                    ('node_id', 'action', 'service_id', 'gpu_uuid', 'expected_boot_id', 'expected_generation')),
                'invalid_owner_receipt')
    if operation_id is not None:
        require(value['operation_id'] == operation_id, 'invalid_owner_receipt')
    # Copy only validated wire fields. Credentials/request keys are not receipts.
    return {**value, 'affected_services': list(value['affected_services'])}


class NodeActions:
    def __init__(self, owner: CanonicalActionOwner | None = None, *, monotonic=time.monotonic):
        self.owner, self.monotonic = owner, monotonic

    def submit(self, payload):
        try:
            request = ActionRequest.parse(payload)
            require(self.owner is not None, 'unsupported_action')
            require(request.action == 'service.start' or request.allow_interrupt, 'interruption_ack_required')
            deadline = self.monotonic() + 2
            result = self.owner.accept(request, deadline=deadline)
            require(self.monotonic() < deadline, 'deadline_exceeded')
            return 202, _receipt(result, request=request)
        except NodeActionError as exc:
            return exc.status, {'error': {'code': exc.code}}
        except Exception:
            return 503, {'error': {'code': 'owner_unavailable'}}

    def operation(self, operation_id):
        try:
            require(matches(OPID, operation_id), 'operation_unknown')
            require(self.owner is not None, 'operation_unknown')
            deadline = self.monotonic() + 2
            result = self.owner.operation(operation_id, deadline=deadline)
            require(self.monotonic() < deadline, 'deadline_exceeded')
            return 200, _receipt(result, operation_id=operation_id)
        except NodeActionError as exc:
            return exc.status, {'error': {'code': exc.code}}
        except Exception:
            return 503, {'error': {'code': 'owner_unavailable'}}
