"""Bounded public catalog DTOs; no filesystem, network, or model-weight access.

``Catalog`` accepts records supplied by a trusted in-process lifecycle adapter.
This is deliberately not an adapter, acquisition verifier, or profile loader.
``installed`` means the adapter verified protected acquisition evidence;
``small_checks_passed`` means its current bounded profile/mount checks passed.
The adapter must refresh those observations before constructing a new catalog.
Neither flag is inferred from a profile existing or from a saved model list.

Evidence references are opaque IDs, never filenames, URLs, or free-form logs.
The installed source has no production fixture fallback.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import math
import re


MAX_ENTRIES = 128
MAX_EVIDENCE = 8
CAPABILITIES = ("tool_calling", "vision", "reasoning", "json_output", "streaming")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_DEPLOYMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}(?:/[A-Za-z0-9][A-Za-z0-9_.-]{0,95})?\Z")
_REVISION = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")


def _bad() -> None:
    raise ValueError("invalid_catalog")


def _identifier(value: object, pattern: re.Pattern = _ID) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value) or ".." in value:
        _bad()
    return value


def _label(value: object, limit: int = 160) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= limit
            or not value.isascii() or not value.isprintable()
            or any(char in value for char in "/\\<>")):
        _bad()
    return value


def _integer(value: object, maximum: int = 2**63 - 1) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= maximum:
        _bad()
    return value


def _timestamp(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _TIME.fullmatch(value):
        _bad()
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _bad()
    return value


def _observation_time(value: object) -> str | int | float | None:
    if type(value) in (int, float):
        if not 0 <= value <= 253402300799 or not math.isfinite(value):
            _bad()
        return value
    return _timestamp(value)


def _evidence(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (tuple, list)) or len(value) > MAX_EVIDENCE:
        _bad()
    return [_identifier(item) for item in value]


def _capabilities(value: object) -> dict:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        _bad()
    result = {}
    for name in CAPABILITIES:
        item = value.get(name, {})
        if not isinstance(item, dict):
            _bad()
        status = item.get("status", "unknown")
        if not isinstance(status, str) or status not in {"verified", "declared", "unknown"}:
            _bad()
        evidence = _evidence(item.get("evidence"))
        # A parser option or package/source inspection is not a tool-call test.
        kind = item.get("verification_kind")
        if status == "verified" and (not evidence or kind != "end_to_end"):
            status, evidence = "unknown", []
        elif status == "declared" and (not evidence or kind != "declaration"):
            status, evidence = "unknown", []
        elif status == "unknown":
            evidence = []
        result[name] = {"status": status, "evidence": evidence}
    return result


def _requirements(value: object) -> dict:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        _bad()
    result = {}
    for name in ("gpu_bytes", "ram_bytes"):
        item = value.get(name, {})
        if not isinstance(item, dict):
            _bad()
        size = _integer(item.get("bytes"))
        provenance = item.get("provenance", "unknown")
        if not isinstance(provenance, str) or provenance not in {"estimate", "measurement", "unknown"}:
            _bad()
        evidence = _evidence(item.get("evidence"))
        if size is None or provenance == "unknown" or not evidence:
            size, provenance, evidence = None, "unknown", []
        result[name] = {"bytes": size, "provenance": provenance, "evidence": evidence}
    return result


def _endpoint(value: object) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        _bad()
    # A protected adapter supplies the validated host contract; never echo URLs.
    if value.get("host", "127.0.0.1") != "127.0.0.1":
        _bad()
    if value.get("api_prefix", "/v1") != "/v1":
        _bad()
    port = _integer(value.get("port"), 65535)
    if not port or value.get("authentication_required") is not True:
        _bad()
    alias = _identifier(value.get("served_model"))
    return {"base_url": f"http://127.0.0.1:{port}/v1", "served_model": alias,
            "authentication_required": True, "address_scope": "server_loopback",
            "server_relative": True, "ready": False}


class Catalog:
    """Immutable, sanitized installed-entry snapshot with known-ID lookup.

    Required installed DTO fields are deployment_id, model_id, display_name,
    revision (40/64 lowercase hex), backend, runtime, installed=True and
    installed_verified_at (UTC ISO timestamp). Missing acquisition timestamp
    keeps a known ID unavailable and excludes it from the installed listing.
    Optional values stay unknown instead of being inferred from flags.
    ``target`` is metadata lookup only; every start still needs full preflight.
    """

    def __init__(self, records: list[dict] | tuple[dict, ...]):
        if not isinstance(records, (list, tuple)) or len(records) > MAX_ENTRIES:
            _bad()
        self._known: set[str] = set()
        self._records: dict[str, dict] = {}
        for record in records:
            if not isinstance(record, dict):
                _bad()
            identifier = _identifier(record.get("deployment_id"), _DEPLOYMENT)
            if identifier in self._known:
                _bad()
            self._known.add(identifier)
            if record.get("installed") is not True:
                continue
            verified_at = _timestamp(record.get("installed_verified_at"))
            if verified_at is None:
                continue
            revision = record.get("revision")
            if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
                _bad()
            context = _integer(record.get("context_limit"), 2**31 - 1)
            if context == 0:
                _bad()
            quantization = record.get("quantization")
            self._records[identifier] = {
                "deployment_id": identifier,
                "model_id": _identifier(record.get("model_id"), _MODEL),
                "display_name": _label(record.get("display_name")),
                "revision": revision,
                "backend": _identifier(record.get("backend")),
                "runtime": _identifier(record.get("runtime")),
                "context_limit": context,
                "quantization": None if quantization is None else _label(quantization, 64),
                "installed_bytes": _integer(record.get("installed_bytes")),
                "installed_verified_at": verified_at,
                "small_checks_passed": record.get("small_checks_passed") is True,
                "capabilities": _capabilities(record.get("capabilities")),
                "requirements": _requirements(record.get("requirements")),
                "endpoint": _endpoint(record.get("endpoint")),
                "start_revalidation_required": True,
            }

    def target(self, deployment_id: str) -> dict:
        """Return safe metadata or a stable error; never return private profiles."""
        if not isinstance(deployment_id, str) or deployment_id not in self._known:
            raise ValueError("unknown_deployment")
        record = self._records.get(deployment_id)
        if record is None or not record["small_checks_passed"]:
            raise ValueError("target_unavailable")
        return deepcopy(record)

    def public(self, snapshot: dict) -> list[dict]:
        """Merge a fresh trusted observation into allowlisted installed metadata.

        Polling timestamps and saved state alone never establish readiness.
        Loading requires an owned current operation; direct lifecycle changes
        with no owned operation remain unknown until fresh proofs are available.
        """
        if not isinstance(snapshot, dict):
            _bad()
        observed_at = _observation_time(snapshot.get("observed_at"))
        operation = snapshot.get("current_operation")
        if operation is None:
            operation = snapshot.get("last_operation")
        operation = operation if isinstance(operation, dict) else {}
        operation_status = operation.get("status")
        proof = snapshot.get("ready_proof")
        proof = proof if isinstance(proof, dict) else {}
        storage = snapshot.get("storage_available")
        observed = snapshot.get("observation_available") is not False and observed_at is not None
        result = []
        for identifier in sorted(self._records):
            record = deepcopy(self._records[identifier])
            checks = record.pop("small_checks_passed")
            state = "available" if checks else "unavailable"
            selected = snapshot.get("selected") == identifier
            owned = operation.get("target") == identifier
            if storage is False:
                state = "unavailable"
            elif storage is not True or not observed:
                state = "unknown"
            elif not checks:
                state = "unavailable"
            elif owned and operation_status == "running":
                state = "loading"
            elif owned and operation_status == "failed" and not (selected and snapshot.get("observed") == "ready"):
                state = "failed"
            elif selected and snapshot.get("desired") == "running":
                if (snapshot.get("container_running") is True
                        and isinstance(snapshot.get("active_identity"), str)
                        and snapshot["active_identity"]
                        and snapshot.get("observed_deployment", identifier) == identifier
                        and snapshot.get("observed") == "ready"
                        and all(proof.get(key) is True for key in (
                            "trusted_identity", "safe_network", "authenticated_model", "runtime_health"))):
                    state = "ready"
                elif snapshot.get("observed") in ("failed", "unhealthy"):
                    state = "failed"
                else:
                    state = "unknown"
            record["state"] = state
            record["observed_at"] = observed_at
            record["switch_effect"] = "interrupts_inference"
            if record["endpoint"] is not None:
                record["endpoint"]["ready"] = state == "ready"
            result.append(record)
        return result


InstalledCatalog = Catalog
