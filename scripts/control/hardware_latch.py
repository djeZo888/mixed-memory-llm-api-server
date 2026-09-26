"""Pure boot-scoped GPU hardware evidence, plus an injected persistence port.

An observation producer calls ``observe``; passive GET handlers only read its
cached result. The producer must supply trustworthy boot identity, current boot
age and the inventory receipt's age. Two distinct successful COMPLETE fresh
inventories collected after boot grace prove absence. A typed hardware fault
may latch immediately, including during boot grace. An unsuccessful
NVML call, stale telemetry, or a generic driver error proves neither.

HardwareLatch has no filesystem, collector, lifecycle or storage-lock access.
Production must restore/export its state with protected registered storage, or
use ProtectedHardwareLatch with the existing reviewed read/write owner. Missing
or unreadable persisted state is not permission to recreate an empty latch.
The persistence port must serialize producer writes; it is never called by a
status GET. There is intentionally no clear/reset API.

Exact inventory input: state="ok", freshness="fresh", age_ms in [0,15000],
complete=True, boot_id matching current_boot_id, observed_at UTC ISO8601,
gpu_uuids=[exact canonical GPU UUIDs]. Optional observation_id is a bounded
receipt string; optional hardware_faults maps UUID to HARDWARE_FAULT_CODES.
Unknown fields do not establish evidence. The caller supplies current
boot_age_seconds from the same boot, independently of application uptime.
The two receipts must have increasing observed_at, distinct IDs when supplied,
and the same missing/fault classification (including exact hardware fault code).
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import math
import re


BOOT_GRACE_SECONDS = 120
MAX_AGE_MS = 15_000
MAX_TARGETS = 64
HARDWARE_FAULT_CODES = frozenset({
    "gpu_fallen_off_bus", "gpu_unrecoverable_hardware_fault",
})
_UUID = re.compile(r"GPU-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
_BOOT = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
_RECORD_FIELDS = frozenset({"boot_id", "hardware_latched", "reason", "hardware_fault_code", "evidence"})
_EVIDENCE_FIELDS = frozenset({"observed_at", "observation_id"})


class LatchStateInvalid(ValueError):
    def __init__(self):
        super().__init__("hardware_latch_state_invalid")


class LatchStorageUnavailable(RuntimeError):
    def __init__(self):
        super().__init__("hardware_latch_storage_unavailable")


def empty_state():
    """Only initialize this through a reviewed first-install storage owner."""
    return {"schema_version": 1, "targets": {}}


def _match(value, pattern):
    return type(value) is str and pattern.fullmatch(value) is not None


def _number(value):
    return type(value) in (int, float) and 0 <= value <= 2**53 and math.isfinite(value)


def _timestamp(value):
    if type(value) is not str or len(value) > 40:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
            return None
        return parsed.astimezone(timezone.utc).timestamp()
    except (ValueError, OverflowError):
        return None


def _receipt(value):
    if type(value) is not dict or set(value) != _EVIDENCE_FIELDS:
        return False
    identifier = value["observation_id"]
    return _timestamp(value["observed_at"]) is not None and (
        identifier is None or (type(identifier) is str and 1 <= len(identifier) <= 128)
    )


def _validate_state(state):
    if (type(state) is not dict or set(state) not in ({"schema_version", "targets"}, {"schema_version", "targets", "validated"})
            or type(state["schema_version"]) is not int or state["schema_version"] != 1
            or type(state["targets"]) is not dict or len(state["targets"]) > MAX_TARGETS):
        raise LatchStateInvalid()
    validated = state.get("validated", {})
    if type(validated) is not dict or len(validated) > MAX_TARGETS:
        raise LatchStateInvalid()
    for uuid, proof in validated.items():
        if (not _match(uuid, _UUID) or type(proof) is not dict
                or set(proof) != {"boot_id", "observed_at", "observation_id"}
                or not _match(proof["boot_id"], _BOOT)
                or not _receipt({key: proof[key] for key in _EVIDENCE_FIELDS})):
            raise LatchStateInvalid()
    for uuid, record in state["targets"].items():
        if (not _match(uuid, _UUID) or type(record) is not dict
                or set(record) not in (_RECORD_FIELDS, _RECORD_FIELDS | {"pending"}) or not _match(record["boot_id"], _BOOT)
                or type(record["hardware_latched"]) is not bool
                or record["reason"] not in ("hardware_missing", "hardware_fault")
                or (record["hardware_fault_code"] is not None
                    and (type(record["hardware_fault_code"]) is not str
                         or record["hardware_fault_code"] not in HARDWARE_FAULT_CODES))
                or (record["reason"] == "hardware_missing") != (record["hardware_fault_code"] is None)
                or type(record["evidence"]) is not list
                or not 1 <= len(record["evidence"]) <= 2
                or any(not _receipt(receipt) for receipt in record["evidence"])
                or record["hardware_latched"] != (len(record["evidence"]) == 2
                    or record["reason"] == "hardware_fault")):
            raise LatchStateInvalid()
        pending = record.get("pending")
        if pending is not None:
            if (not record["hardware_latched"] or type(pending) is not dict
                    or "pending" in pending or pending.get("boot_id") == record["boot_id"]):
                raise LatchStateInvalid()
            _validate_state({"schema_version": 1, "targets": {uuid: pending}})
            if pending["hardware_latched"]:
                raise LatchStateInvalid()
        evidence = record["evidence"]
        if len(evidence) == 2 and not _distinct_newer(evidence[1], evidence[0]):
            raise LatchStateInvalid()
    return copy.deepcopy(state)


def _distinct_newer(receipt, previous):
    return (
        _timestamp(receipt["observed_at"]) > _timestamp(previous["observed_at"])
        and (receipt["observation_id"] is None
             or previous["observation_id"] is None
             or receipt["observation_id"] != previous["observation_id"])
    )


def _inventory(inventory, current_boot_id, boot_age_seconds):
    """Return validated evidence, or None without converting uncertainty to loss."""
    if (not _match(current_boot_id, _BOOT) or not _number(boot_age_seconds)
            or type(inventory) is not dict
            or inventory.get("state") != "ok"
            or inventory.get("freshness") != "fresh"
            or inventory.get("complete") is not True
            or inventory.get("boot_id") != current_boot_id
            or not _number(inventory.get("age_ms"))
            or inventory["age_ms"] > MAX_AGE_MS):
        return None
    receipt = {"observed_at": inventory.get("observed_at"),
               "observation_id": inventory.get("observation_id")}
    if not _receipt(receipt):
        return None
    uuids = inventory.get("gpu_uuids")
    if (type(uuids) is not list or len(uuids) > MAX_TARGETS
            or any(not _match(uuid, _UUID) for uuid in uuids)
            or len(set(uuids)) != len(uuids)):
        return None
    faults = inventory.get("hardware_faults", {})
    # These codes mean explicit hardware evidence from a trusted collector;
    # generic NVML errors or ECC counters MUST NOT be mapped to them.
    if (type(faults) is not dict or len(faults) > MAX_TARGETS
            or any(not _match(uuid, _UUID) or type(code) is not str
                   or code not in HARDWARE_FAULT_CODES
                   for uuid, code in faults.items())):
        return None
    observed_boot_age = boot_age_seconds - inventory["age_ms"] / 1000
    if observed_boot_age < 0:
        return None
    return set(uuids), faults, receipt, observed_boot_age


class HardwareLatch:
    """Single-producer state machine; export/restore persists pending proof too.

    ``hardware_latched`` is not a readiness assertion. No latch plus unknown
    evidence leaves service hardware availability unknown. The caller combines
    this result with software status and installation capability separately.
    """

    def __init__(self, state=None):
        self._state = _validate_state(empty_state() if state is None else state)

    def export_state(self):
        return copy.deepcopy(self._state)

    def _result(self, gpu_uuid, evidence_state):
        record = self._state["targets"].get(gpu_uuid)
        latched = record is not None and record["hardware_latched"]
        return {
            "hardware_latched": latched,
            "reason": record["reason"] if latched else None,
            "evidence_state": evidence_state,
            "latched_boot_id": record["boot_id"] if latched else None,
            "confirmation_count": len(record["evidence"]) if record else 0,
        }

    def observe(self, gpu_uuid, inventory, *, current_boot_id, boot_age_seconds):
        if not _match(gpu_uuid, _UUID):
            raise LatchStateInvalid()
        validated = _inventory(inventory, current_boot_id, boot_age_seconds)
        if validated is None:
            return self._result(gpu_uuid, "unknown")
        uuids, faults, receipt, observed_boot_age = validated
        proof = self._state.get("validated", {}).get(gpu_uuid)
        if (gpu_uuid not in faults and proof and proof["boot_id"] == current_boot_id
                and _timestamp(receipt["observed_at"]) <= _timestamp(proof["observed_at"])):
            # Replaying old inventory cannot supersede a newer exact probe.
            return self._result(gpu_uuid, "unknown")
        record = self._state["targets"].get(gpu_uuid)
        evidence_state = ("fault" if gpu_uuid in faults else
                          "healthy" if gpu_uuid in uuids else "missing")
        inherited = record if record and record["hardware_latched"] else None
        if inherited:
            # Late recovery/reset cannot clear this boot's proven failure.
            if inherited["boot_id"] == current_boot_id:
                return self._result(gpu_uuid, evidence_state)
            if evidence_state == "healthy":
                del self._state["targets"][gpu_uuid]
                return self._result(gpu_uuid, "healthy")
            # Preserve inherited protection while collecting the NEW boot proof.
            record = inherited.get("pending")
        if evidence_state == "healthy":
            self._state["targets"].pop(gpu_uuid, None)
            return self._result(gpu_uuid, "healthy")
        if observed_boot_age < BOOT_GRACE_SECONDS and evidence_state != "fault":
            return self._result(gpu_uuid, "boot_grace")
        self._state.get("validated", {}).pop(gpu_uuid, None)
        reason = "hardware_fault" if evidence_state == "fault" else "hardware_missing"
        fault_code = faults.get(gpu_uuid)
        if (record is None or record["boot_id"] != current_boot_id
                or record["reason"] != reason
                or record["hardware_fault_code"] != fault_code):
            if gpu_uuid not in self._state["targets"] and len(self._state["targets"]) >= MAX_TARGETS:
                raise LatchStateInvalid()
            record = {"boot_id": current_boot_id, "hardware_latched": evidence_state == "fault",
                      "reason": reason, "hardware_fault_code": fault_code,
                      "evidence": [receipt]}
        elif _distinct_newer(receipt, record["evidence"][-1]):
            record["evidence"].append(receipt)
            record["hardware_latched"] = True
        if inherited and not record["hardware_latched"]:
            inherited["pending"] = record
        else:
            self._state["targets"][gpu_uuid] = record
        return self._result(gpu_uuid, evidence_state)

    def validate_required(self, gpu_uuid, *, current_boot_id, receipt=None):
        """Called only after the owner validates an exact successful UUID probe.

        Unlike observe(), this makes NO complete inventory/absence claim. A
        caller must prove the boot did not change across the target-only probe.
        """
        if not _match(gpu_uuid, _UUID) or not _match(current_boot_id, _BOOT):
            raise LatchStateInvalid()
        if receipt is not None and not _receipt(receipt):
            raise LatchStateInvalid()
        record = self._state["targets"].get(gpu_uuid)
        if record and record["hardware_latched"] and record["boot_id"] == current_boot_id:
            return self._result(gpu_uuid, "healthy")
        pending = record.get("pending") if record and record["hardware_latched"] else record
        if (receipt is not None and pending and pending["boot_id"] == current_boot_id
                and _timestamp(receipt["observed_at"]) <= _timestamp(pending["evidence"][-1]["observed_at"])):
            # A still-fresh cached exact probe can predate a later absence proof.
            # Never let replay erase pending/current-boot hardware evidence.
            return self._result(gpu_uuid, "unknown")
        self._state["targets"].pop(gpu_uuid, None)
        if receipt is not None:
            self._state.setdefault("validated", {})[gpu_uuid] = {"boot_id": current_boot_id, **receipt}
        return self._result(gpu_uuid, "healthy")


class ProtectedHardwareLatch:
    """Persist before publishing transitions, using an injected protected owner.

    ``store.read()`` returns validated protected state, never None on I/O error;
    ``store.write(state)`` atomically replaces it using registered/anchored
    guards. No path, unguarded fallback or new lifecycle owner exists here.
    An exception means admission must fail closed; do not recreate empty state.
    The old in-memory state remains intact on a failed write, allowing retry.
    """

    def __init__(self, store):
        self._store = store
        try:
            state = store.read()
            if state is None:
                raise LatchStateInvalid()
            self._latch = HardwareLatch(state)
        except Exception:
            raise LatchStorageUnavailable() from None

    def export_state(self):
        return self._latch.export_state()

    def observe(self, gpu_uuid, inventory, *, current_boot_id, boot_age_seconds):
        candidate = HardwareLatch(self._latch.export_state())
        result = candidate.observe(gpu_uuid, inventory, current_boot_id=current_boot_id,
                                   boot_age_seconds=boot_age_seconds)
        if candidate.export_state() != self._latch.export_state():
            try:
                self._store.write(candidate.export_state())
            except Exception:
                raise LatchStorageUnavailable() from None
            self._latch = candidate
        return result

    def validate_required(self, gpu_uuid, *, current_boot_id, receipt=None):
        candidate = HardwareLatch(self._latch.export_state())
        result = candidate.validate_required(gpu_uuid, current_boot_id=current_boot_id, receipt=receipt)
        if candidate.export_state() != self._latch.export_state():
            try:
                self._store.write(candidate.export_state())
            except Exception:
                raise LatchStorageUnavailable() from None
            self._latch = candidate
        return result
