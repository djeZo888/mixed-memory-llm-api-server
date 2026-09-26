"""Control port bound to the actual L1 lifecycle owner.

Constructor injection is for in-process tests only. The production entrypoint
has fixed installed paths and never accepts a loader, fixture, command or host.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import hashlib
import hmac
from pathlib import Path
from types import SimpleNamespace

from common.lifecycle_lease import _validate_borrowed_lease
from lifecycle.manager import load_manager, recovery_manager
from lifecycle.runtime_io import Docker, LifecycleError, _read_key
from .discovery import discover_records
from .core import Application, digest, safe_error
from .journal import Journal, JournalUnavailable, MAX_BYTES
from .protocol import ControlError, PackageBlocked, StorageUnavailable

JOURNAL_SUFFIX = 'services/llm-control/operations.json'


def _lease(manager, lease):
    _validate_borrowed_lease(lease, system_root=manager.lease_system_root,
                           trusted_uid=manager.trusted_uid)


class ManagerJournalStore:
    """Use L1's registered reader/writer; no guessed disk or root fallback."""
    def __init__(self, manager_loader):
        self.manager_loader = manager_loader

    def read(self):
        try:
            manager = self.manager_loader()
            path = manager.binding.path('data', JOURNAL_SUFFIX)
            local = manager.binding.validate_path('data', path)
            # Absence is checked only after mounted identity/path verification.
            if not local.exists():
                manager.binding.validate_path('data', path)
                return None
            return manager.binding.read_json('data', path, maximum=MAX_BYTES)
        except Exception:
            raise JournalUnavailable() from None

    def write(self, value):
        try:
            manager = self.manager_loader()
            manager.persistent_json(manager.binding.path('data', JOURNAL_SUFFIX), value)
        except Exception:
            raise JournalUnavailable() from None


class ProductionBackend:
    def __init__(self, config_root, *, manager_loader=load_manager,
                 recovery_loader=recovery_manager, catalog_reader=discover_records,
                 control_key=None):
        self.config_root = Path(config_root)
        self.manager_loader, self.recovery_loader = manager_loader, recovery_loader
        self.catalog_reader, self.control_key = catalog_reader, control_key

    def load(self):
        return self.manager_loader(SimpleNamespace(instance=None), self.config_root)

    def open(self, *, recovery=False):
        try:
            manager = (self.recovery_loader(config=self.config_root) if recovery else self.load())
            if not recovery:
                manager.check_mounts()
        except Exception:
            if recovery:
                raise ControlError('recovery_identity_unavailable') from None
            raise StorageUnavailable() from None
        return ManagerSession(manager, self.catalog_reader, self.control_key)


class ManagerSession:
    def __init__(self, manager, catalog_reader, control_key=None):
        self.manager, self.catalog_reader, self.control_key = manager, catalog_reader, control_key
        self._generations = {}

    @contextmanager
    def _bounded(self, deadline):
        """Cap existing L1 external call budgets, without abandoning its lease.

        A filesystem/kernel call cannot be forcibly cancelled by a Python
        deadline. HTTP slots remain occupied until such a call actually returns.
        No second transition is admitted while an owner call is outstanding.
        """
        manager = self.manager
        originals = {}
        def timed(function):
            def call(*args, **kwargs):
                kwargs['timeout'] = min(kwargs.get('timeout', 30), deadline.remaining())
                result = function(*args, **kwargs)
                deadline.remaining()
                return result
            return call
        for name in ('run', 'probe', 'sglang_probe'):
            originals[name] = getattr(manager, name)
            setattr(manager, name, timed(originals[name]))
        original_sleep = manager.sleep
        manager.sleep = lambda seconds: original_sleep(min(seconds, deadline.remaining()))
        # Actual Docker.run is the common external I/O seam. Controlled test
        # Docker objects may provide their own methods and need no subprocess cap.
        docker_run = manager.docker.run if type(manager.docker) is Docker else None
        if docker_run is not None:
            manager.docker.run = timed(docker_run)
        storage_runner = getattr(getattr(getattr(manager, 'binding', None), 'storage', None), 'runner', None)
        storage_run = getattr(storage_runner, 'run', None)
        if storage_run is not None:
            storage_runner.run = timed(storage_run)
        try:
            deadline.remaining()
            yield
            deadline.remaining()
        finally:
            for name, function in originals.items():
                setattr(manager, name, function)
            manager.sleep = original_sleep
            if docker_run is not None:
                manager.docker.run = docker_run
            if storage_run is not None:
                storage_runner.run = storage_run

    def _separate_key(self, deployment):
        if self.control_key is None:  # Explicit test construction only.
            return
        if deployment.get('legacy'):
            raise ControlError('target_unavailable', 409)
        try:
            key = _read_key(deployment['auth']['key_file']).encode('ascii')
            if hmac.compare_digest(self.control_key, key):
                raise ValueError
        except Exception:
            raise ControlError('credential_separation_unverified') from None

    def observe(self, deadline):
        manager = self.manager
        recovery = manager.recovery_only
        with self._bounded(deadline):
            try:
                if not recovery:
                    manager.check_mounts()  # BOTH roles; data-only is not Ready.
                state = manager.read_state(recovery=recovery)
            except Exception:
                if recovery:
                    raise ControlError('recovery_identity_unavailable') from None
                raise StorageUnavailable() from None
            if state.get('schema_version') == 3:
                slots = state.get('slots')
                if type(slots) is not dict or set(slots) != {'glm', 'qwen'}:
                    raise ControlError('observation_unavailable')
                raw = {'schema_version': 3, 'slots': {}, 'recovery_trusted': recovery}
                for slot in ('glm', 'qwen'):
                    item = dict(slots[slot], state_persisted=state.get('state_persisted', True))
                    try:
                        raw['slots'][slot] = self._observe_slot(item, deadline, recovery, slot=slot)
                    except StorageUnavailable:
                        raise
                    except ControlError:
                        raw['slots'][slot] = dict(item, observation_available=False,
                                                  storage_available=not recovery, container_running=None,
                                                  ready_proof={}, endpoint=None, failure='observation_unavailable')
                    raw['slots'][slot]['slot'] = slot
                    self._generations[slot] = slots[slot]['generation']
                return raw
            if recovery and state.get('container') is None:
                raise ControlError('recovery_identity_unavailable')
            return self._observe_slot(state, deadline, recovery)

    def _observe_slot(self, state, deadline, recovery, *, slot=None):
        manager = self.manager
        raw = copy.deepcopy(state)
        identity = state.get('container')
        if state.get('pending_create') is not None:
            if slot not in {'glm', 'qwen'}:
                raise ControlError('observation_unavailable')
            try:
                identity = manager.pending_identity(state)
                raw['container'] = copy.deepcopy(identity)
                raw['pending_create_fingerprint'] = digest(state['pending_create'])
                # Empty inventory alone cannot settle a dispatched create.
                raw['pending_absence_verified'] = (identity is None
                    and state['pending_create'].get('dispatch') == 'not_dispatched')
            except Exception:
                raise ControlError('recovery_identity_unavailable' if recovery else 'observation_unavailable') from None
        try:
            container = manager.trusted_container(identity) if identity else None
        except Exception:
            raise ControlError('recovery_identity_unavailable' if recovery else 'observation_unavailable') from None
        running = manager.running(container)
        raw.update(container_running=running, observation_available=True,
                   storage_available=not recovery,
                   state_persisted=not recovery and state.get('state_persisted', True),
                   observed='unknown' if running else 'stopped', recovery_trusted=recovery)
        raw['ready_proof'] = {}
        raw['endpoint'] = None
        raw['model_id'] = None
        selected_deployment = None
        if not recovery and state.get('selected'):
            try:
                selected = manager.deployment(state['selected'])
                if not selected.get('legacy') and selected['endpoint']['port'] != 30000:
                    raw['endpoint'] = {**selected['endpoint'], 'authentication_required': True}
                    raw['model_id'] = selected['_model']['repo_id']
                selected_deployment = selected
            except Exception:
                pass
        if identity:
            # StartedAt changes even when L1 reuses the same immutable
            # container. It is observed Docker metadata, not saved Ready.
            started = (container or {}).get('State', {}).get('StartedAt')
            if running and (type(started) is not str or not 1 <= len(started) <= 128
                            or not started.isascii() or not started.isprintable()):
                raise ControlError('observation_unavailable')
            raw['container']['generation'] = hashlib.sha256(
                (identity['image_id'] + '\0' + (started or 'absent')).encode()).hexdigest()
        if not recovery and running:
            try:
                # Reuse only this observation's successful resolution.
                deployment = (selected_deployment if selected_deployment is not None
                              and state['selected'] == identity['deployment']
                              else manager.deployment(identity['deployment']))
                self._separate_key(deployment)
                manager.network_check(container, deployment)
                if not deployment.get('legacy'):
                    manager.validate_reused_contract(container, deployment)
                    code = manager.probe_deployment(deployment, min(
                        deployment['launch']['request_timeout_seconds'], deadline.remaining()))
                    after = manager.trusted_container(identity)
                    stable = (manager.running(after) and after['State'].get('StartedAt') == started)
                    healthy = after.get('State', {}).get('Health', {}).get('Status') != 'unhealthy'
                    try:
                        manager.check_mounts()
                    except Exception:
                        raise StorageUnavailable() from None
                    ready = code == 'ready' and healthy and stable
                    raw['observed'] = 'ready' if ready else 'unhealthy'
                    raw['ready_proof'] = {key: ready for key in (
                        'trusted_identity', 'safe_network', 'authenticated_model', 'runtime_health')}
            except ControlError as exc:
                if exc.code != 'credential_separation_unverified':
                    raise
                raw['observed'] = 'unhealthy'
                raw['failure'] = exc.code
            except LifecycleError as exc:
                raw['observed'] = 'unhealthy'
                raw['failure'] = safe_error(exc, None)
            except Exception:
                raw['observed'] = 'unhealthy'
        # Recovery never opens deployments/config/keys or probes inference.
        return raw

    def catalog(self, deadline):
        if self.manager.recovery_only:
            return []
        with self._bounded(deadline):
            return self.catalog_reader(self.manager, deadline)

    def check_admission(self, lease, deadline):
        _lease(self.manager, lease)
        if self.manager.recovery_only:
            raise StorageUnavailable()
        with self._bounded(deadline):
            try:
                self.manager.check_package_admission()
            except Exception:
                raise PackageBlocked() from None

    @contextmanager
    def _hardware_owner(self, lease):
        """Bind already-held canonical authority during pre-dispatch checks.

        preflight intentionally runs before Manager.dispatch (and before old
        target stop), so dispatch has not bound its lease yet. Restore the
        prior binding even on refusal; no new lock or borrowed FD is created.
        """
        _lease(self.manager, lease)
        missing = object()
        previous = getattr(self.manager, '_hardware_lease', missing)
        self.manager._hardware_lease = lease
        try:
            yield
        finally:
            if previous is missing:
                del self.manager._hardware_lease
            else:
                self.manager._hardware_lease = previous

    def preflight(self, target, lease, deadline, *, slot=None):
        _lease(self.manager, lease)
        if self.manager.recovery_only:
            raise StorageUnavailable()
        with self._bounded(deadline), self._hardware_owner(lease):
            try:
                self.manager.check_package_admission()
                deployment = self.manager.deployment(target)
                if deployment['endpoint']['port'] == 30000:
                    raise ControlError('target_unavailable', 409)
                self._separate_key(deployment)
                if slot is not None:
                    from .catalog import model_slot
                    if model_slot(deployment['_model']['repo_id'], deployment['id']) != slot:
                        raise ControlError('target_mismatch', 409)
                self.manager.preflight_slot_admission(deployment, slot)
                self.manager.prepare_start(deployment)
                # Required with base L1; also safe with L1B's repeated seam.
                # Validate actual image ID/tag/entrypoint BEFORE the old stop.
                self.manager.create_args(deployment)
            except LifecycleError as exc:
                raise ControlError(safe_error(exc, 'preflight_failed')) from None
            except Exception:
                raise ControlError('preflight_failed') from None

    def _dispatch(self, action, lease, deadline, deployment=None, *, slot=None, boot_policy=None):
        _lease(self.manager, lease)
        with self._bounded(deadline):
            kwargs = {}
            if slot is not None:
                if slot not in self._generations:
                    raise ControlError('observation_unavailable')
                kwargs = {'target': slot, 'expected_generation': self._generations[slot]}
            if boot_policy is not None:
                kwargs['boot_policy'] = boot_policy
            result = self.manager.dispatch(action, deployment_id=deployment, lease=lease, **kwargs)
            if slot is not None:
                state = self.manager.read_state(recovery=self.manager.recovery_only)
                self._generations[slot] = state['slots'][slot]['generation']
            return result

    def stop(self, lease, deadline, *, slot=None):
        return self._dispatch('stop', lease, deadline, slot=slot)

    def select(self, target, lease, deadline, *, slot=None):
        _lease(self.manager, lease)
        with self._bounded(deadline):
            state = self.manager.read_state()
            if slot is not None:
                state = state['slots'][slot]
            boot_policy = state.get('boot_policy')
            if type(boot_policy) is not str or boot_policy not in ('manual', 'resume'):
                raise ControlError('observation_unavailable')
            return self._dispatch('select', lease, deadline, target, slot=slot, boot_policy=boot_policy)

    def start(self, lease, deadline, *, slot=None):
        return self._dispatch('start', lease, deadline, slot=slot)


def production_application(config_root, control_key, *, advertised_policy=None, readiness_identity=None):
    backend = ProductionBackend(config_root, control_key=control_key)
    return Application(backend, Journal(ManagerJournalStore(backend.load)),
                       read_seconds=60, admission_seconds=60,
                       advertised_policy=advertised_policy, readiness_identity=readiness_identity)
