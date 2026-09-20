"""Authenticated transport's bounded router and single lifecycle executor.

The private handoff slot is never a FIFO: one nonblocking admission guard covers
handoff AND the complete transition. Only its single executor thread acquires
the canonical lease, creates a fresh backend session, and holds that same lease
through validation, compare-and-swap, persistence and outcome. Reads use separate
fresh sessions and never wait for a model startup.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import hashlib
import json
import queue
import re
import threading
import time
import uuid

from common.lifecycle_lease import acquire_lease, LeaseBusy, LeaseError
from .catalog import Catalog, _endpoint, advertised_endpoint
from .journal import JournalCorrupt, JournalUnavailable
from .protocol import ControlError, Deadline, PackageBlocked, StorageUnavailable

ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,95}\Z")
IDENTITY = re.compile(r"[0-9a-f]{64}\Z")
OPID = re.compile(r"[0-9a-f]{32}\Z")
KEY = re.compile(r"[a-zA-Z0-9_.:-]{1,128}\Z")
SAFE_CODES = frozenset({
    "catalog_unavailable", "credential_separation_unverified",
    "invalid_request", "unknown_route", "method_not_allowed", "unknown_deployment",
    "target_unavailable", "target_required", "target_mismatch", "already_running", "lifecycle_busy", "stale_state", "interruption_ack_required",
    "idempotency_conflict", "storage_unavailable", "owner_unavailable",
    "production_adapter_unavailable", "package_admission_unavailable",
    "journal_unavailable", "journal_corrupt", "journal_full", "admission_timeout",
    "observation_unavailable", "preflight_failed", "stop_not_proven", "start_failed",
    "transition_failed", "deadline_exceeded", "service_interrupted",
    "recovery_identity_unavailable", "service_closed", "operation_unknown",
})


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def identifier(value):
    return value if type(value) is str and ID.fullmatch(value) else None


def safe_error(exc, fallback="transition_failed"):
    code = getattr(exc, "code", None)
    return code if type(code) is str and code in SAFE_CODES else fallback


def _identity(container):
    if type(container) is not dict:
        return None
    values = [container.get(k) for k in ("instance", "deployment", "id", "generation")]
    if not all(type(v) is str and 0 < len(v) <= 256 and v.isascii()
               and not any(ord(c) < 33 or ord(c) > 126 for c in v) for v in values):
        return None
    if identifier(values[0]) is None or identifier(values[1]) is None:
        return None
    return digest(values)


def observation(raw):
    """Project private lifecycle data; saved state and model-list-only never Ready."""
    if type(raw) is not dict:
        raise ControlError("observation_unavailable")
    if raw.get("schema_version") == 3:
        if type(raw["schema_version"]) is not int:
            raise ControlError("observation_unavailable")
        if type(raw.get("slots")) is not dict or set(raw["slots"]) != {"glm", "qwen"}:
            raise ControlError("observation_unavailable")
        slots, fingerprints = {}, {}
        for target in ("glm", "qwen"):
            slot = raw["slots"][target]
            if type(slot) is not dict or type(slot.get("generation")) is not int or slot["generation"] < 0:
                raise ControlError("observation_unavailable")
            slots[target], fingerprints[target] = observation(slot)
            slots[target]["slot"] = target
            if fingerprints[target] is not None:
                fingerprints[target] = digest([fingerprints[target], slot["generation"]])
        return {"schema_version": 2, "mode": "pair", "slots": slots,
                "storage_available": all(item["storage_available"] for item in slots.values()),
                "state_persisted": all(item["state_persisted"] for item in slots.values()),
                "observation_available": all(item["observation_available"] for item in slots.values()),
                "observed_at": time.time(), "failure_code": None}, fingerprints
    fresh = raw.get("observation_available") is True
    running = raw.get("container_running") if type(raw.get("container_running")) is bool else None
    container_id = _identity(raw.get("container"))
    active = container_id if fresh and running is True else None
    selected = identifier(raw.get("selected"))
    desired = raw.get("desired") if raw.get("desired") in {"running", "stopped"} else "unknown"
    deployment = identifier((raw.get("container") or {}).get("deployment")) if type(raw.get("container")) is dict else None
    proof = raw.get("ready_proof") or {}
    ready = (fresh and raw.get("storage_available") is True and active is not None and desired == "running" and selected == deployment
             and raw.get("observed") == "ready" and type(proof) is dict
             and all(proof.get(k) is True for k in
                     ("trusted_identity", "safe_network", "authenticated_model", "runtime_health")))
    if not fresh:
        state = "unavailable" if raw.get("storage_available") is False else "unknown"
    elif raw.get("storage_available") is not True and running is not False:
        state = "unavailable" if raw.get("storage_available") is False else "unknown"
    elif ready:
        state = "ready"
    elif running is False:
        state = "failed" if desired == "running" else "stopped"
    elif raw.get("observed") in {"failed", "unhealthy"}:
        state = "failed"
    else:
        state = "unknown"
    result = {"selected": selected, "desired": desired, "observed": state,
              "observed_deployment": deployment if active else None,
              "container_running": running if fresh else None, "active_identity": active,
              "observed_at": time.time(), "observation_available": fresh,
              "storage_available": raw.get("storage_available") is True,
              "state_persisted": raw.get("state_persisted") is True,
              "ready_proof": {k: ready for k in
                  ("trusted_identity", "safe_network", "authenticated_model", "runtime_health")},
              "failure_code": raw.get("failure") if raw.get("failure") in SAFE_CODES else None}
    try:
        result["endpoint"] = _endpoint(raw.get("endpoint"))
    except ValueError:
        result["endpoint"] = None
    if result["endpoint"] is not None:
        result["endpoint"]["ready"] = ready
    # Health or polling times do not change semantic generation. Immutable start
    # identity, saved selection/intent and actual running state do.
    fingerprint = digest([selected, desired, container_id, running]) if fresh else None
    return result, fingerprint


def scoped(snapshot, target=None):
    """Resolve a fixed slot; never silently choose one of two selections."""
    if snapshot.get("mode") != "pair":
        if target is not None:
            raise ControlError("target_unavailable", 409)
        return snapshot
    if target is None:
        selected = [name for name, item in snapshot["slots"].items() if item["selected"] is not None]
        if len(selected) != 1:
            raise ControlError("target_required", 409)
        target = selected[0]
    return snapshot["slots"][target]


def trusted_recovery(snapshot, raw, target=None):
    selected = scoped(snapshot, target)
    if raw.get('recovery_trusted') is not True or not selected['observation_available']:
        return False
    if snapshot.get('mode') == 'pair':
        private = raw['slots'][selected['slot']]
        # A stopped pending create still has an exactly inspected immutable
        # identity; the slot fingerprint binds it even though active is null.
        return _identity(private.get('container')) is not None
    return selected['active_identity'] is not None


def public_outcome(snapshot):
    return {k: snapshot[k] for k in ("selected", "desired", "observed", "container_running",
            "active_identity", "generation", "state_persisted", "observed_at")}


def public_operation(op):
    result = {k: copy.deepcopy(op[k]) for k in ("id", "kind", "target", "status", "created_at",
            "updated_at", "deadline", "completed_at", "generation", "active_identity",
            "failure_code", "observed", "state_persisted", "poll_url")}
    if "slot" in op:
        result["slot"] = op["slot"]
    result["failure_code"] = op["failure_code"] if type(op["failure_code"]) is str and op["failure_code"] in SAFE_CODES else None
    result["observed"] = public_outcome(op["observed"]) if op["observed"] is not None else None
    return result


class _Ticket:
    def __init__(self, kind, request=None, key=None):
        self.kind, self.request, self.key = kind, request, key
        self.condition = threading.Condition()
        self.result = None
        self.cancelled = False
        self.expires_at = None

    def reply(self, value):
        with self.condition:
            if self.cancelled or (self.expires_at is not None and time.monotonic() >= self.expires_at):
                self.cancelled = True
                self.condition.notify_all()
                return False
            self.result = value
            self.condition.notify_all()
            return True

    def wait(self, seconds):
        with self.condition:
            self.expires_at = time.monotonic() + seconds
            if not self.condition.wait_for(lambda: self.result is not None or self.cancelled, seconds) or self.cancelled:
                self.cancelled = True
                raise ControlError("admission_timeout")
            return self.result


class Application:
    def __init__(self, backend, journal, *, lease_factory=acquire_lease,
                 transition_seconds=8000, admission_seconds=10, read_seconds=10,
                 advertised_policy=None):
        if not 0 < transition_seconds <= 14400 or not 0 < admission_seconds <= 10 or not 0 < read_seconds <= 10:
            raise ValueError("invalid_deadlines")
        self.backend, self.journal, self.lease_factory = backend, journal, lease_factory
        self.advertised_policy = copy.deepcopy(advertised_policy)
        self.transition_seconds, self.admission_seconds, self.read_seconds = transition_seconds, admission_seconds, read_seconds
        self._state_lock = threading.RLock()
        self._admission = threading.Lock()
        self._handoff = queue.Queue(maxsize=1)
        self._closed = False
        self._current = None
        self._volatile = {}
        self._journal_error = None
        self._persisted = True
        try:
            self._state = journal.read()
        except (JournalCorrupt, JournalUnavailable) as exc:
            self._state = {"schema": 1, "generation": 0, "fingerprint": None, "entries": {}}
            self._journal_error = "journal_corrupt" if isinstance(exc, JournalCorrupt) else "journal_unavailable"
            self._persisted = False
        self._reconciled = False
        self._worker = threading.Thread(target=self._work, name="control-transition", daemon=True)
        self._worker.start()

    def close(self):
        self._closed = True
        # Never terminate a thread that owns a minted lease or release it from
        # another thread. Caller can observe False while bounded work finishes.
        if not self._admission.acquire(blocking=False):
            return False
        try:
            self._handoff.put_nowait(None)
        finally:
            self._admission.release()
        self._worker.join(timeout=2)
        return not self._worker.is_alive()

    def _save(self, *, volatile=False):
        if self._journal_error is not None:
            ok = False  # Never overwrite a corrupt journal to regain admission.
        else:
            try:
                ok = self.journal.save(self._state)
            except Exception:
                ok = False
        self._persisted = ok
        if not ok and not volatile:
            raise ControlError(self._journal_error or "journal_unavailable")
        if ok:
            self._journal_error = None
        return ok

    def _reconcile(self, snapshot, fingerprint, *, volatile=False):
        if fingerprint is None:
            raise ControlError("observation_unavailable")
        with self._state_lock:
            if self._journal_error == "journal_unavailable":
                # A failed startup read is not evidence of an empty journal.
                # Reload it under canonical ownership before any durable write.
                previous_generation = self._state["generation"]
                previous_slots = copy.deepcopy(self._state.get("slots", {}))
                try:
                    self._state = self.journal.read()
                except (JournalCorrupt, JournalUnavailable) as exc:
                    self._journal_error = "journal_corrupt" if isinstance(exc, JournalCorrupt) else "journal_unavailable"
                    if not volatile:
                        raise ControlError(self._journal_error) from None
                else:
                    self._journal_error = None
                    restored_generation = self._state["generation"]
                    self._state["generation"] = max(restored_generation, previous_generation)
                    self._persisted = restored_generation >= previous_generation
                    if previous_slots:
                        if self._state['schema'] == 1:
                            self._state.update(schema=2, slots=previous_slots)
                            self._persisted = False
                        else:
                            for name, item in previous_slots.items():
                                if item['generation'] > self._state['slots'][name]['generation']:
                                    self._state['slots'][name] = item
                                    self._persisted = False
                    self._reconciled = False
            pair = snapshot.get("mode") == "pair"
            changed = False
            if pair:
                if self._state["schema"] == 1:
                    self._state.update(schema=2, slots={name: {"generation": self._state["generation"], "fingerprint": None}
                                                      for name in ("glm", "qwen")})
                    changed = True
                for name, item in snapshot["slots"].items():
                    saved_slot = self._state["slots"][name]
                    if fingerprint[name] is not None and saved_slot["fingerprint"] != fingerprint[name]:
                        saved_slot["generation"] += 1
                        saved_slot["fingerprint"] = fingerprint[name]
                        changed = True
                    item["generation"] = saved_slot["generation"]
            else:
                changed = fingerprint != self._state["fingerprint"]
            if changed and not pair:
                self._state["generation"] += 1
                self._state["fingerprint"] = fingerprint
            if not pair:
                snapshot["generation"] = self._state["generation"]
            pending = [op for op in self._state["entries"].values() if op["status"] in {"pending", "running"}]
            recovered = pending if not self._reconciled else []
            if not self._reconciled:
                for op in pending:
                    try:
                        current = scoped(snapshot, op.get("slot"))
                    except ControlError:
                        current, _ = observation({"storage_available": False})
                        current["generation"] = self._state["generation"]
                    op.update(status="interrupted", failure_code="service_interrupted", updated_at=time.time(),
                              completed_at=time.time(), observed=public_outcome(current),
                              generation=current["generation"], active_identity=current["active_identity"],
                              state_persisted=snapshot["state_persisted"] and not volatile)
                self._reconciled = True
            if changed or (pending and self._current is None) or not self._persisted:
                try:
                    saved = self._save(volatile=volatile)
                except Exception:
                    for op in recovered:
                        op["state_persisted"] = False
                    raise
                if not saved:
                    for op in recovered:
                        op["state_persisted"] = False
            elif self._journal_error and not volatile:
                raise ControlError(self._journal_error)
            snapshot["state_persisted"] = snapshot["state_persisted"] and self._persisted
            if pair:
                for item in snapshot["slots"].values():
                    item["state_persisted"] = item["state_persisted"] and self._persisted
        return snapshot

    def _get_session(self, stop=False):
        try:
            return self.backend.open(), False
        except StorageUnavailable:
            if stop:
                return self.backend.open(recovery=True), True
            raise

    def _operations(self):
        return {**self._state["entries"], **self._volatile}

    @contextmanager
    def _read_state(self):
        # A slow protected storage write must not consume unbounded HTTP read
        # time. Healthy loading uses an immediately available in-memory view.
        if not self._state_lock.acquire(timeout=0.1):
            raise ControlError("journal_unavailable")
        try:
            yield
        finally:
            self._state_lock.release()

    def _recover_stop(self, request, deadline):
        session = self.backend.open(recovery=True)
        (snapshot, fingerprint), raw = self._fresh(session, deadline)
        if not trusted_recovery(snapshot, raw, request.get("target")):
            raise ControlError("recovery_identity_unavailable")
        snapshot = scoped(self._reconcile(snapshot, fingerprint, volatile=True), request.get("target"))
        if request["expected_active"] != snapshot["active_identity"] or request["expected_generation"] != snapshot["generation"]:
            raise ControlError("stale_state", 409)
        return session, snapshot

    def _make_volatile(self, op):
        # A failed update does not revoke an acknowledged durable receipt. Keep
        # that same operation in entries so a later successful save preserves
        # its idempotency digest and final outcome across process restart.
        # New recovery-only operations still live solely in the volatile map.
        if len(self._volatile) >= 16:
            del self._volatile[min(self._volatile, key=lambda key: self._volatile[key]["created_at"])]
        self._volatile[op["id"]] = op
        op["state_persisted"] = False

    def _fresh(self, session=None, deadline=None):
        deadline = deadline or Deadline.after(self.read_seconds)
        session = session or self.backend.open()
        deadline.remaining()
        raw = session.observe(deadline)
        deadline.remaining()
        return observation(raw), raw

    def _recovery_observation(self, deadline):
        # This is an explicit U1 fixture port, not a call to a guessed L1
        # status API. Production binding must prove the exact /run-only read.
        session = self.backend.open(recovery=True)
        (snapshot, fingerprint), raw = self._fresh(session, deadline)
        if raw.get("recovery_trusted") is not True or fingerprint is None:
            raise ControlError("recovery_identity_unavailable")
        snapshot["state_persisted"] = False
        snapshot["storage_available"] = False
        for item in snapshot["slots"].values() if snapshot.get("mode") == "pair" else [snapshot]:
            item["state_persisted"] = False
            item["storage_available"] = False
            if item["container_running"] is not False:
                item["observed"] = "unavailable"
                item["ready_proof"] = {key: False for key in item["ready_proof"]}
        return snapshot, fingerprint

    def _try_refresh(self):
        if self._closed or not self._admission.acquire(blocking=False):
            return
        ticket = _Ticket("refresh")
        self._handoff.put_nowait(ticket)
        try:
            ticket.wait(self.admission_seconds)
        except ControlError:
            pass

    def _read(self, catalog=False, target=None):
        self._try_refresh()
        raw = {}
        try:
            deadline = Deadline.after(self.read_seconds)
            session = self.backend.open()
            (snapshot, fingerprint), raw = self._fresh(session, deadline)
            records = session.catalog(deadline) if catalog else None
            deadline.remaining()
        except Exception as exc:
            raw = {}
            try:
                if not isinstance(exc, StorageUnavailable):
                    raise exc
                snapshot, fingerprint = self._recovery_observation(Deadline.after(self.read_seconds))
            except Exception:
                snapshot, fingerprint = observation({"storage_available": False if isinstance(exc, StorageUnavailable) else None})
            snapshot["failure_code"] = safe_error(exc, "observation_unavailable")
            records = [] if catalog else None
        pair = snapshot.get("mode") == "pair"
        with self._read_state():
            operations = self._operations()
            current = operations.get(self._current)
            items = snapshot["slots"].items() if pair else [(None, snapshot)]
            for name, item in items:
                saved = self._state.get("slots", {}).get(name, {}) if pair else self._state
                item["generation"] = saved.get("generation", 0)
                fp = fingerprint.get(name) if pair else fingerprint
                item["generation_current"] = fp is not None and fp == saved.get("fingerprint")
                item["state_persisted"] = item["state_persisted"] and self._persisted
                op = current if current and current.get("slot") == name else None
                item["current_operation"] = public_operation(op) if op else None
                finished = [entry for entry in operations.values() if entry.get("slot") == name
                            and entry["completed_at"] is not None
                            and time.time() - entry["completed_at"] < self.journal.retention_seconds]
                previous = max(finished, key=lambda entry: entry["completed_at"]) if finished else None
                item["last_operation"] = public_operation(previous) if previous else None
                for field in ("current_operation", "last_operation"):
                    if item[field] is not None:
                        item[field]["state_persisted"] = item[field]["state_persisted"] and self._persisted
                if op and op["status"] == "running" and op["kind"] in {"switch", "start", "restart"}:
                    item["observed"] = "loading"
                item["freshness"] = "fresh" if item["observation_available"] else "unavailable"
                item["switch_effect"] = "interrupts_target_inference" if pair else "interrupts_inference"
                item["schema_version"] = 2 if pair else 1
                item["failure_code"] = item["failure_code"] or self._journal_error
            snapshot["state_persisted"] = snapshot["state_persisted"] and self._persisted
        if catalog:
            snapshot["entries"] = Catalog(records).public(snapshot, advertised_policy=self.advertised_policy)
        for name, item in snapshot["slots"].items() if pair else [(None, snapshot)]:
            private = raw.get("slots", {}).get(name, {}) if pair else raw
            item["endpoint"] = advertised_endpoint(item["endpoint"], private.get("model_id"), self.advertised_policy)
            item.pop("ready_proof", None)
        return 200, scoped(snapshot, target) if target is not None else snapshot

    @staticmethod
    def _request(kind, body, headers):
        if len(body) > 4096 or headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise ControlError("invalid_request", 400)
        def pairs(items):
            value = {}
            for key, item in items:
                if key in value:
                    raise ValueError
                value[key] = item
            return value
        try:
            request = json.loads(body.decode("utf-8"), object_pairs_hook=pairs,
                                 parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeError, RecursionError):
            raise ControlError("invalid_request", 400) from None
        fields = {"expected_active", "expected_generation"}
        if kind in {"switch", "start"}:
            fields.add("deployment_id")
        if kind in {"switch", "restart"}:
            fields.add("allow_interrupt")
        if type(request) is not dict or set(request) not in (fields, fields | {"target"}):
            raise ControlError("invalid_request", 400)
        active, generation = request["expected_active"], request["expected_generation"]
        if ((active is not None and (type(active) is not str or not IDENTITY.fullmatch(active)))
                or type(generation) is not int or not 0 <= generation < 2**63
                or (kind in {"switch", "start"} and identifier(request["deployment_id"]) is None)
                or (kind in {"switch", "restart"} and type(request["allow_interrupt"]) is not bool)
                or ("target" in request and (type(request["target"]) is not str or request["target"] not in {"glm", "qwen"}))):
            raise ControlError("invalid_request", 400)
        key = headers.get("idempotency-key", "")
        if not KEY.fullmatch(key):
            raise ControlError("invalid_request", 400)
        return request, key

    def handle(self, method, path, headers, body):
        try:
            if self._closed:
                raise ControlError("service_closed")
            if method == "GET" and path in {"/control/v1/catalog", "/control/v1/status"}:
                return self._read(path.endswith("catalog"))
            if method == "GET" and path in {"/control/v1/status/glm", "/control/v1/status/qwen"}:
                return self._read(target=path.rsplit("/", 1)[1])
            if method == "GET" and path.startswith("/control/v1/operations/"):
                opid = path.removeprefix("/control/v1/operations/")
                if not OPID.fullmatch(opid):
                    raise ControlError("operation_unknown", 404)
                self._try_refresh()
                with self._read_state():
                    op = self._operations().get(opid)
                    if op is None or (op["completed_at"] is not None and time.time() - op["completed_at"] >= self.journal.retention_seconds):
                        raise ControlError("operation_unknown", 404)
                    result = public_operation(op)
                    if not self._reconciled and result["status"] in {"pending", "running"}:
                        result.update(status="interrupted", failure_code="service_interrupted", state_persisted=False)
                    result["state_persisted"] = result["state_persisted"] and self._persisted
                    return 200, result
            if method == "POST" and path in {"/control/v1/switch", "/control/v1/stop", "/control/v1/start", "/control/v1/restart"}:
                kind = path.rsplit("/", 1)[1]
                request, key = self._request(kind, body, headers)
                return self._submit(kind, request, key)
            raise ControlError("unknown_route", 404)
        except ControlError as exc:
            return exc.status if exc.status in {400,404,409,503} else 503, {"error": {"code": safe_error(exc)}}
        except Exception:
            return 503, {"error": {"code": "owner_unavailable"}}

    def _replay(self, kind, request, key):
        key_hash, req_hash = digest(key), digest([kind, request])
        for op in self._operations().values():
            if op["completed_at"] is not None and time.time() - op["completed_at"] >= self.journal.retention_seconds:
                continue
            if op["idempotency_digest"] == key_hash:
                if op["request_digest"] != req_hash:
                    raise ControlError("idempotency_conflict", 409)
                result = public_operation(op)
                result["state_persisted"] = result["state_persisted"] and self._persisted
                return 202, {"operation": result, "replayed": True,
                             "state_persisted": result["state_persisted"]}
        return None

    def _submit(self, kind, request, key):
        # A concurrent durable write must not turn conflict admission into a
        # blocking queue. Replay is available only when its snapshot is ready.
        if not self._state_lock.acquire(blocking=False):
            raise ControlError("lifecycle_busy", 409)
        try:
            replay = self._replay(kind, request, key)
            if replay:
                if not self._reconciled and replay[1]["operation"]["status"] in {"pending", "running"}:
                    replay[1]["operation"].update(status="interrupted", failure_code="service_interrupted",
                                                state_persisted=False)
                    replay[1]["state_persisted"] = False
                return replay
        finally:
            self._state_lock.release()
        if not self._admission.acquire(blocking=False):
            raise ControlError("lifecycle_busy", 409)
        ticket = _Ticket(kind, request, key)
        self._handoff.put_nowait(ticket)
        return ticket.wait(self.admission_seconds)

    def _work(self):
        while True:
            ticket = self._handoff.get()
            if ticket is None:
                return
            try:
                with self.lease_factory(blocking=False) as lease:
                    with ticket.condition:
                        if ticket.cancelled:
                            continue
                    if ticket.kind == "refresh":
                        try:
                            (snapshot, fingerprint), _ = self._fresh()
                            self._reconcile(snapshot, fingerprint)
                        except StorageUnavailable:
                            snapshot, fingerprint = self._recovery_observation(Deadline.after(self.read_seconds))
                            self._reconcile(snapshot, fingerprint, volatile=True)
                        ticket.reply((200, {}))
                    else:
                        self._transition(ticket, lease)
            except LeaseBusy:
                ticket.reply((409, {"error": {"code": "lifecycle_busy"}}))
            except LeaseError:
                ticket.reply((503, {"error": {"code": "owner_unavailable"}}))
            except Exception as exc:
                status = exc.status if isinstance(exc, ControlError) else 503
                ticket.reply((status, {"error": {"code": safe_error(exc, "owner_unavailable")}}))
            finally:
                with self._state_lock:
                    self._current = None
                self._admission.release()
            if self._closed:
                return

    def _transition(self, ticket, lease):
        transition_deadline = Deadline.after(self.transition_seconds)
        # Before the receipt, metadata/admission must use the ticket budget,
        # never a model-start timeout. The actual loader remains synchronous;
        # cancellation still prevents mutation when it eventually returns.
        deadline = Deadline(min(transition_deadline.end, ticket.expires_at or
                                time.monotonic() + self.admission_seconds))
        session, recovery = self._get_session(ticket.kind == "stop")
        try:
            if not recovery:
                session.check_admission(lease, deadline)
        except (StorageUnavailable, PackageBlocked):
            if ticket.kind != "stop":
                raise
            session, recovery = self.backend.open(recovery=True), True
        (snapshot, fingerprint), raw = self._fresh(session, deadline)
        if recovery and not trusted_recovery(snapshot, raw, ticket.request.get("target")):
            raise ControlError("recovery_identity_unavailable")
        # Persistent receipts are mandatory for normal work. Their absence may
        # only redirect an explicit stop into the exact trusted recovery port.
        try:
            snapshot = self._reconcile(snapshot, fingerprint, volatile=recovery)
            with self._state_lock:
                self._state = self.journal.prune(self._state)
                if len(self._state["entries"]) >= self.journal.max_entries and not recovery:
                    raise ControlError("journal_full")
        except ControlError as exc:
            if ticket.kind != "stop" or exc.code not in {"journal_unavailable", "journal_corrupt", "journal_full"}:
                raise
            session, recovery = self.backend.open(recovery=True), True
            (snapshot, fingerprint), raw = self._fresh(session, deadline)
            if not trusted_recovery(snapshot, raw, ticket.request.get("target")):
                raise ControlError("recovery_identity_unavailable")
            snapshot = self._reconcile(snapshot, fingerprint, volatile=True)
        request = ticket.request
        snapshot = scoped(snapshot, request.get("target"))
        slot = snapshot.get("slot")
        kwargs = {"slot": slot} if slot is not None else {}
        with self._state_lock:
            replay = self._replay(ticket.kind, request, ticket.key)
            if replay:
                ticket.reply(replay)
                return
        if request["expected_active"] != snapshot["active_identity"] or request["expected_generation"] != snapshot["generation"]:
            raise ControlError("stale_state", 409)
        if snapshot["container_running"] is None or (snapshot["container_running"] and snapshot["active_identity"] is None):
            raise ControlError("observation_unavailable")
        target = request.get("deployment_id") or snapshot["selected"]
        if ticket.kind in {"switch", "start", "restart"}:
            if not snapshot["storage_available"]:
                raise StorageUnavailable()
            try:
                record = Catalog(session.catalog(deadline)).target(target)
                if slot is not None and record.get("slot") != slot:
                    raise ControlError("target_mismatch", 409)
            except ValueError as exc:
                code = str(exc)
                raise ControlError(code if code in {"unknown_deployment", "target_unavailable"} else "target_unavailable",
                                   404 if code == "unknown_deployment" else 409) from None
            if ticket.kind == "start" and snapshot["container_running"]:
                raise ControlError("already_running", 409)
            if snapshot["active_identity"] is not None and not request.get("allow_interrupt", False):
                raise ControlError("interruption_ack_required", 409)
        now, opid = time.time(), uuid.uuid4().hex
        operation = {"id": opid, "kind": ticket.kind,
                     "target": target if slot is not None or ticket.kind != "stop" else None, "status": "pending",
                     "created_at": now, "updated_at": now, "deadline": now + transition_deadline.remaining(),
                     "completed_at": None, "request_digest": digest([ticket.kind, request]),
                     "idempotency_digest": digest(ticket.key), "generation": snapshot["generation"],
                     "active_identity": snapshot["active_identity"], "failure_code": None,
                     "observed": public_outcome(snapshot), "state_persisted": not recovery,
                     "poll_url": "/control/v1/operations/" + opid}
        if slot is not None:
            operation["slot"] = slot
        # Storage may block; never hold the receipt condition while persisting.
        # The waiter can expire independently, and reply atomically refuses an
        # expired receipt before any lifecycle mutation is attempted.
        with ticket.condition:
            if ticket.cancelled or (ticket.expires_at is not None and time.monotonic() >= ticket.expires_at):
                ticket.cancelled = True
                ticket.condition.notify_all()
                return
        with self._state_lock:
            if recovery:
                # Separate bounded volatile results never evict a durable
                # idempotency receipt. Recovery keys expire on restart or
                # after 16 later recovery stops, explicitly documented.
                self._make_volatile(operation)
                persisted = False
            else:
                self._state["entries"][opid] = operation
                try:
                    persisted = self._save()
                except Exception:
                    if ticket.kind == "stop":
                        try:
                            session, snapshot = self._recover_stop(request, deadline)
                        except Exception:
                            operation.update(status="interrupted", failure_code="recovery_identity_unavailable",
                                             updated_at=time.time(), completed_at=time.time(), state_persisted=False)
                            raise
                        recovery, persisted = True, False
                        self._make_volatile(operation)
                    else:
                        # Retain an uncertain receipt; never execute normal work.
                        operation.update(status="interrupted", failure_code="journal_unavailable",
                                         updated_at=time.time(), completed_at=time.time(), state_persisted=False)
                        raise
            operation["state_persisted"] = persisted and not recovery
            if not ticket.reply((202, {"operation": public_operation(operation), "replayed": False,
                                      "state_persisted": operation["state_persisted"]})):
                operation.update(status="interrupted", failure_code="admission_timeout",
                                 updated_at=time.time(), completed_at=time.time(), state_persisted=False)
                if not recovery:
                    self._save(volatile=True)
                return
            self._current = opid
        deadline = transition_deadline
        try:
            with self._state_lock:
                operation.update(status="running", updated_at=time.time())
                if not recovery:
                    try:
                        self._save()
                    except ControlError:
                        if ticket.kind != "stop":
                            raise
                        session, snapshot = self._recover_stop(request, deadline)
                        recovery = True
                        self._make_volatile(operation)
            if ticket.kind in {"switch", "start", "restart"}:
                deadline.remaining()
                session.preflight(target, lease, deadline, **kwargs)
                deadline.remaining()
            if snapshot["container_running"] or ticket.kind == "stop":
                deadline.remaining()
                session.stop(lease, deadline, **kwargs)
                deadline.remaining()
                (stopped, stopped_fp), _ = self._fresh(session, deadline)
                stopped = scoped(self._reconcile(stopped, stopped_fp, volatile=recovery), slot)
                if stopped["container_running"] is not False or stopped["active_identity"] is not None:
                    raise ControlError("stop_not_proven")
            if ticket.kind in {"switch", "start", "restart"}:
                deadline.remaining()
                if ticket.kind != "restart":
                    session.select(target, lease, deadline, **kwargs)
                    deadline.remaining()
                session.start(lease, deadline, **kwargs)
                deadline.remaining()
            (outcome, final_fp), _ = self._fresh(session, deadline)
            outcome = scoped(self._reconcile(outcome, final_fp, volatile=recovery), slot)
            if ticket.kind in {"switch", "start", "restart"} and (outcome["observed"] != "ready" or outcome["selected"] != target):
                raise ControlError("start_failed")
            if ticket.kind == "stop" and outcome["container_running"] is not False:
                raise ControlError("stop_not_proven")
            status, failure = "succeeded", None
        except Exception as exc:
            status, failure = "failed", safe_error(exc)
            try:
                (outcome, final_fp), _ = self._fresh(session)
                outcome = scoped(self._reconcile(outcome, final_fp, volatile=True), slot)
            except Exception:
                outcome, _ = observation({"storage_available": False})
                outcome["generation"] = (self._state.get("slots", {}).get(slot, {}).get("generation", 0)
                                         if slot is not None else self._state["generation"])
                outcome["state_persisted"] = False
        with self._state_lock:
            operation.update(status=status, failure_code=failure, updated_at=time.time(), completed_at=time.time(),
                             generation=outcome["generation"], active_identity=outcome["active_identity"],
                             observed=public_outcome(outcome), state_persisted=outcome["state_persisted"] and not recovery)
            if not self._save(volatile=True):
                operation["state_persisted"] = False
