"""Discover installed metadata through the actual registered lifecycle owner.

Only protected deployment/model/runtime profiles and the existing lifecycle
completion receipt schema are inputs. No weight directory is enumerated, no
artifact is opened or hashed, no key is read, and saved intent is never consulted.
``installed_verified_at`` is the time receipt metadata was checked by this call,
not an acquisition timestamp or a claim of freshly verified model payloads.

The production caller supplies a Manager from ``load_manager``. Its explicit
``test_paths`` seam is solely for worker fixtures; it is never API configuration.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import stat

from lifecycle.manager import LEGACY, Manager
from lifecycle.runtime_io import LifecycleError
from lifecycle.storage_binding import BindingError

from .catalog import Catalog, MAX_ENTRIES, _DEPLOYMENT
from .protocol import ControlError


_EXPECTED_ERRORS = (LifecycleError, BindingError, OSError, ValueError, TypeError,
                    KeyError, AttributeError, IndexError)


def _check_deadline(deadline):
    if deadline is not None:
        deadline.remaining()


def _deployment_ids(manager):
    """Bound directory enumeration; every file is subsequently opened by L1."""
    directory = manager.config_root / 'deployments'
    if directory.resolve() != directory:
        raise ControlError('catalog_unavailable')
    if not manager.test_paths:
        for path in (directory, *directory.parents):
            meta = path.stat()
            if not stat.S_ISDIR(meta.st_mode) or meta.st_uid != 0 or meta.st_mode & 0o022:
                raise ControlError('catalog_unavailable')
    identifiers = []
    # Bound all names, including unexpected files, before sorting. This is a
    # reviewed source directory; a flooded directory is a configuration error.
    with os.scandir(directory) as entries:
        for count, entry in enumerate(entries, 1):
            if count > MAX_ENTRIES + 16:
                raise ControlError('catalog_unavailable')
            if not entry.name.endswith('.json'):
                continue
            identifier = entry.name[:-5]
            if not _DEPLOYMENT.fullmatch(identifier) or '..' in identifier:
                raise ControlError('catalog_unavailable')
            identifiers.append(identifier)
            if len(identifiers) > MAX_ENTRIES:
                raise ControlError('catalog_unavailable')
    return sorted(identifiers)


def _installed_receipt(manager, deployment):
    """Use L1's actual generic receipt validation without artifact traversal."""
    model = deployment['_model']
    evidence = manager.instance.get('model_integrity', {}).get(deployment['model'], {})
    if not isinstance(evidence, dict):
        raise LifecycleError('acquisition_completion_required')
    receipt = evidence.get('completion_manifest')
    acquisition = Path(manager.binding.path('data', 'services/llm-manager/acquisition'))
    # L1's explicit historical import can accept a historical D1 attestation.
    # A catalog entry requires the protected installed receipt as well; legacy
    # saved intent or source proof never creates an installed listing.
    if (not isinstance(receipt, str) or Path(receipt).parent != acquisition
            or '..' in Path(receipt).parts):
        raise LifecycleError('acquisition_completion_required')
    manager.check_completion(deployment)
    manifest = model.get('manifest_sha256')
    if manifest is not None:
        complete = manager.binding.read_json('data', receipt)
        if (evidence.get('manifest_sha256') != manifest
                or complete.get('manifest_sha256') != manifest):
            raise LifecycleError('acquisition_completion_identity_mismatch')


def discover_records(manager: Manager, deadline=None) -> list[dict]:
    """Return bounded allowlisted Catalog inputs for an actual loaded Manager.

    Registered but unsupported/incomplete deployments remain known unavailable
    IDs. Unregistered names and historical CLI-only IDs are never synthesized.
    ``small_checks_passed`` requires current source/mount and runtime attestation
    checks. It does not promise local-image availability, readiness, capacity, or
    successful start; mutation preflight remains mandatory under the lease.

    Existing source schemas have no structured capability verification or GPU/
    RAM measurement records. These values remain unknown, including tool calling
    when a parser flag exists. The existing Catalog DTO handles fresh observed
    readiness separately and renders only server-relative loopback endpoints.
    """
    if not isinstance(manager, Manager) or manager.recovery_only or manager.binding is None:
        raise ControlError('catalog_unavailable')
    _check_deadline(deadline)
    try:
        identifiers = _deployment_ids(manager)
    except _EXPECTED_ERRORS:
        raise ControlError('catalog_unavailable') from None
    records = []
    for identifier in identifiers:
        _check_deadline(deadline)
        unavailable = {'deployment_id': identifier, 'installed': False}
        if identifier in LEGACY:
            records.append(unavailable)
            continue
        try:
            deployment = manager.deployment(identifier)
            if deployment.get('legacy'):
                raise LifecycleError('acquisition_completion_required')
            _check_deadline(deadline)
            _installed_receipt(manager, deployment)
            _check_deadline(deadline)
            model = deployment['_model']
            endpoint = deployment['endpoint']
            record = {
                'deployment_id': identifier,
                'model_id': model['repo_id'],
                'display_name': model.get('display_name', model['id']),
                'revision': model['revision'],
                'backend': deployment['_runtime']['backend'],
                'runtime': deployment['runtime'],
                'context_limit': deployment['launch']['context_size'],
                'quantization': model.get('quantization'),
                'installed_bytes': model['total_bytes'],
                'installed': True,
                'installed_verified_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                'small_checks_passed': False,
                'capabilities': {},
                'requirements': {},
                'endpoint': {name: endpoint[name] for name in ('host', 'port', 'api_prefix', 'served_model')},
            }
            record['endpoint']['authentication_required'] = True
            from lifecycle import concurrent_profiles as pair
            if pair.is_pair(deployment):
                try:
                    accepted = pair.check_acceptance(deployment, manager.instance)
                    slot = pair.slot_for_deployment(identifier)
                    capacity = accepted['slots'][slot]
                    record['context_acceptance'] = {
                        'accepted_configured_tokens': capacity['configured_context'],
                        'verified_occupied_tokens': capacity['largest_occupied_context'],
                        'evidence': ['concurrent-' + manager.instance['concurrent_pair_acceptance']['sha256']],
                    }
                except _EXPECTED_ERRORS:
                    pass

            try:
                manager.check_sources(deployment)
                _check_deadline(deadline)
                manager.image_evidence(deployment)
                # The fixed control listener owns 30000. An installed inference
                # profile on that port stays visible but cannot be selected.
                record['small_checks_passed'] = endpoint['port'] != 30000
            except _EXPECTED_ERRORS:
                pass
            _check_deadline(deadline)
            # Validate the whole public DTO here. A malformed optional label or
            # unsupported scalar cannot poison or leak through another record.
            Catalog([record])
            records.append(record)
        except _EXPECTED_ERRORS:
            records.append(unavailable)
    _check_deadline(deadline)
    return records


def discover_catalog(manager: Manager, deadline=None) -> Catalog:
    return Catalog(discover_records(manager, deadline))
