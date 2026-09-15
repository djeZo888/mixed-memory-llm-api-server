"""Explicit fresh rendering and historical import; no implicit relocation.

I1b/I1c owns registration, key provisioning and instance installation. These
helpers bind reviewed instance evidence without changing any evidence bytes,
state, container, model, key or existing directory ownership.
"""
from __future__ import annotations

import copy
from pathlib import Path

from common.lifecycle_lease import LifecycleLease, _validate_borrowed_lease
from .runtime_io import LifecycleError
from .storage_binding import _entered_storage_context


def require(value, code):
    if not value:
        raise LifecycleError(code)


def render_fresh_instance(template, binding, instance_id):
    """Return a fresh unactivated template with explicit registered identity.

    This function writes nothing. An existing instance must use the separately
    locked historical import or an independently reviewed stopped migration.
    """
    from .manager import ID_RE
    require(isinstance(instance_id, str) and bool(ID_RE.fullmatch(instance_id)), 'invalid_instance_id')
    require(template.get('storage_identity') is None, 'fresh_template_required')
    require('required_mounts' not in template, 'historical_instance_requires_explicit_import')
    require(not any(e.get('verified') is True for e in template.get('model_integrity', {}).values()),
            'fresh_template_cannot_adopt_model_evidence')
    require(not any(e.get('auth_gate_passed') is True for e in template.get('runtime_evidence', {}).values()),
            'fresh_template_cannot_adopt_auth_evidence')
    binding.verify()
    value = copy.deepcopy(template)
    value.update(id=instance_id, storage_identity=binding.identity)
    require(value['paths']['state'] == {'role': 'data', 'suffix': 'services/llm-manager/active'}, 'unsafe_state_path')
    for evidence in value.get('model_integrity', {}).values():
        completion = evidence.get('completion_manifest')
        if completion is not None:
            require(isinstance(completion, dict) and set(completion) == {'role', 'suffix'}
                    and completion['role'] == 'data'
                    and Path(completion['suffix']).parent == Path('services/llm-manager/acquisition'),
                    'invalid_completion_template')
            evidence['completion_manifest'] = binding.path('data', completion['suffix'])
    return value


def import_historical_instance(binding, *, lease, storage_io):
    """Explicitly bind the existing /data deployment instance under its lease.

    The caller supplies the actual I1b storage_io module, never an arbitrary FD.
    Only adds storage_identity and historical_import to the protected instance;
    all existing fields are preserved verbatim. No state or artifact is written.
    """
    require(type(lease) is LifecycleLease, 'invalid_borrowed_lease')
    _validate_borrowed_lease(lease, system_root=binding.storage.system_root, trusted_uid=binding.storage.owner)
    binding.verify()
    require(binding.path('data') == '/data' and binding.path('models') == '/data/models-large',
            'historical_paths_must_be_preserved')
    require(binding.registry['data']['mount'] == '/data'
            and binding.registry['models']['mount'] == '/data/models-large', 'historical_mounts_must_be_preserved')
    path = binding.path('data', 'services/llm-manager/deployment-instance.json')
    old = binding.read_json('data', path)
    require(old.get('schema_version') == 1, 'invalid_instance_version')
    existing_identity = old.get('storage_identity')
    require(existing_identity is None or existing_identity == binding.identity, 'registry_instance_identity_mismatch')
    require(old.get('paths') == {'state': '/data/services/llm-manager/active',
                                'lock': '/run/llmctl/lifecycle.lock',
                                'recovery': '/run/llmctl/recovery.json'}, 'historical_paths_must_be_preserved')
    expected = [{'target': binding.registry[role]['mount'], 'uuid': binding.registry[role]['uuid'],
                 'filesystem': binding.registry[role]['fstype']} for role in ('data', 'models')]
    mounts = old.get('required_mounts')
    require(isinstance(mounts, list) and len(mounts) == 2
            and sorted(mounts, key=lambda m: m['target']) == sorted(expected, key=lambda m: m['target']),
            'historical_mount_identity_mismatch')
    value = copy.deepcopy(old)
    value.update(storage_identity=binding.identity, historical_import=True)
    if value == old:
        return value
    # Keep host completion evidence literal. Do not rewrite model_root or receipts.
    for evidence in old.get('model_integrity', {}).values():
        completion = evidence.get('completion_manifest')
        if completion is not None:
            require(isinstance(completion, str)
                    and Path(completion).parent == Path('/data/services/llm-manager/acquisition')
                    and '..' not in Path(completion).parts, 'historical_completion_path_invalid')
    lease.validate()
    with binding.mounted_guard(storage_io, roles=('data',)) as guard:
        with _entered_storage_context(storage_io.AnchoredRoot('/data', guard)) as anchor:
            # Re-read through the anchored descriptor to refuse a concurrent replacement.
            require(anchor.read_json('services/llm-manager/deployment-instance.json') == old,
                    'historical_instance_changed')
            lease.validate()
            anchor.atomic_json('services/llm-manager/deployment-instance.json', value)
            anchor.check()
    return value
