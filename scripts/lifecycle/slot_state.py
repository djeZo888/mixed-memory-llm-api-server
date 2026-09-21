"""Fixed GPU0/GPU1 state grammar. No I/O or runtime discovery.

Kept in the storage-loss recovery closure: validation never loads profiles.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from .runtime_io import LifecycleError

SLOTS = ('glm', 'qwen')  # Legacy keys: GPU0 flexible, GPU1 Qwen; deterministic boot order.
HEX = re.compile(r'[0-9a-f]{64}\Z')
ID = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}\Z')
PENDING_IDENTITY_FIELDS = frozenset({'image_id', 'name', 'owner', 'instance', 'deployment'})


def require(ok, code):
    if not ok:
        raise LifecycleError(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def deployment_slot(identifier):
    # State recovery must work without config/model mounts. Admission still loads
    # and validates exact profiles before any start/select, never this prefix.
    if isinstance(identifier, str):
        if identifier == 'qwen38-27b-q0-480000-yarn4-bf16kv':
            return 'glm'
        if identifier.startswith('glm-5.3-ud-q4-k-xl-'):
            return 'glm'
        if identifier.startswith('qwen38-27b-'):
            return 'qwen'
    return None


def empty_slot():
    return {'selected': None, 'desired': 'stopped', 'boot_policy': 'manual',
            'observed': 'stopped', 'container': None, 'container_running': False,
            'failure': None, 'generation': 0, 'pending_create': None}


def validate_slot(slot, target, identity_validator):
    require(isinstance(slot, dict), 'invalid_slot_state')
    allowed = set(empty_slot()) | {'last_selected'}
    require(set(empty_slot()) <= set(slot) <= allowed, 'invalid_slot_fields')
    require(type(slot['generation']) is int and slot['generation'] >= 0, 'invalid_slot_generation')
    require(slot['desired'] in {'running', 'stopped'} and slot['boot_policy'] in {'manual', 'resume'}
            and slot['observed'] in {'unknown', 'stopped', 'starting', 'ready', 'unhealthy', 'failed'}, 'invalid_slot_intent')
    selected = slot['selected']
    require(selected is None or isinstance(selected, str) and bool(ID.fullmatch(selected))
            and deployment_slot(selected) == target, 'slot_deployment_mismatch')
    require(selected is not None or slot['desired'] == 'stopped' and slot['container'] is None,
            'invalid_empty_slot')
    require(slot['container_running'] is None or type(slot['container_running']) is bool, 'invalid_running_state')
    failure = slot['failure']
    require(failure is None or isinstance(failure, str) and str(LifecycleError(failure)) == failure,
            'invalid_failure_code')
    if slot.get('last_selected') is not None:
        require(isinstance(slot['last_selected'], str) and bool(ID.fullmatch(slot['last_selected']))
                and deployment_slot(slot['last_selected']) == target, 'slot_previous_deployment_mismatch')
    pending = slot.get('pending_create')
    if pending is not None:
        require(isinstance(pending, dict) and PENDING_IDENTITY_FIELDS <= set(pending)
                <= PENDING_IDENTITY_FIELDS | {'dispatch'},
                'invalid_pending_create')
        # Older records carry no dispatch proof and must remain uncertain.
        require(type(pending.get('dispatch', 'uncertain')) is str
                and pending.get('dispatch', 'uncertain') in {'not_dispatched', 'uncertain'},
                'invalid_pending_create_dispatch')
        identity_validator({**pending, 'id': '0' * 64})
        require(pending['deployment'] == selected and slot['container'] is None, 'pending_create_identity_mismatch')
    identity = slot['container']
    if identity is not None:
        identity_validator(identity)
        require(set(identity) <= {'id', 'image_id', 'name', 'owner', 'instance', 'deployment', 'legacy'}
                and identity['deployment'] == selected and not identity.get('legacy', False),
                'slot_container_identity_mismatch')


def validate(state, identity_validator):
    require(isinstance(state, dict) and type(state.get('schema_version')) is int and state.get('schema_version') == 3, 'invalid_state_version')
    require(set(state) <= {'schema_version', 'slots', 'migration', 'updated_at', 'state_persisted', 'failure'}
            and {'schema_version', 'slots', 'migration'} <= set(state), 'invalid_slots_state_fields')
    slots = state['slots']
    require(isinstance(slots, dict) and set(slots) == set(SLOTS), 'invalid_fixed_slots')
    for target in SLOTS:
        validate_slot(slots[target], target, identity_validator)
    identities = [slot['container'] for slot in slots.values() if slot['container']]
    owners = [slot['container'] or slot.get('pending_create') for slot in slots.values()
              if slot['container'] or slot.get('pending_create')]
    require(len({x['id'] for x in identities}) == len(identities)
            and len({x['name'] for x in owners}) == len(owners), 'duplicate_slot_identity')
    migration = state['migration']
    require(isinstance(migration, dict) and set(migration) == {'from_schema', 'backup_sha256'}
            and type(migration['from_schema']) is int and migration['from_schema'] == 2 and HEX.fullmatch(str(migration['backup_sha256'])),
            'invalid_slot_migration')
    require(type(state.get('updated_at', 0)) is int, 'invalid_state_timestamp')
    require('state_persisted' not in state or type(state['state_persisted']) is bool, 'invalid_persistence_state')
    require(state.get('failure') in {None, 'recovery_journal_invalid_primary_used'}, 'invalid_failure_code')
    return copy.deepcopy(state)


def migrate(singleton, backup_digest):
    require(singleton['schema_version'] == 2 and not singleton.get('migrated_from'), 'slot_migration_v2_required')
    target = deployment_slot(singleton['selected'])
    require(singleton['selected'] is None or target in SLOTS, 'slot_migration_unknown_deployment')
    result = {'schema_version': 3, 'slots': {name: empty_slot() for name in SLOTS},
              'migration': {'from_schema': 2, 'backup_sha256': backup_digest}}
    if target:
        result['slots'][target].update({key: copy.deepcopy(singleton[key])
                                       for key in empty_slot() if key not in {'generation', 'pending_create'}})
        # Stored intent is not a fresh observation, even when v2 said ready.
        result['slots'][target].update(observed='unknown', container_running=None)
    return result
