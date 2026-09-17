"""Bounded operation persistence behind an injected protected storage owner.

This module deliberately has no path loader or production file-store fallback.
The caller supplies reviewed, mount-anchored ``read()`` and ``write(value)``
operations and serializes mutations under the canonical lifecycle lease.
Only operation metadata and digests belong here; request bodies, keys, backend
objects, paths, and raw exception text cannot enter the journal schema.
"""

from __future__ import annotations

import copy
import json
import math
import re
import time


MAX_BYTES = 1024 * 1024
TERMINAL = frozenset({"succeeded", "failed", "interrupted"})
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_OPERATION_ID = re.compile(r"[a-f0-9]{32}\Z")
_SAFE_CODE = re.compile(r"[a-z][a-z0-9_]{0,95}\Z")
_STATE_FIELDS = frozenset({"schema", "generation", "fingerprint", "entries"})
_ENTRY_FIELDS = frozenset({
    "id", "kind", "target", "status", "created_at", "updated_at", "deadline",
    "completed_at", "request_digest", "idempotency_digest", "generation",
    "active_identity", "failure_code", "observed", "state_persisted", "poll_url",
})
_OBSERVED_FIELDS = frozenset({
    "selected", "desired", "observed", "container_running", "active_identity",
    "generation", "state_persisted", "observed_at",
})


class JournalError(RuntimeError):
    """Journal exceptions expose fixed safe codes only."""

    code = "journal_error"

    def __init__(self):
        super().__init__(self.code)


class JournalUnavailable(JournalError):
    code = "journal_unavailable"


class JournalCorrupt(JournalError):
    code = "journal_corrupt"


class JournalInvalid(JournalError):
    code = "journal_invalid"


def empty_state():
    return {"schema": 1, "generation": 0, "fingerprint": None, "entries": {}}


def _number(value):
    # Bound epochs before float conversion: enormous corrupt integers must not
    # escape validation with OverflowError or create unbounded numeric content.
    return type(value) in (int, float) and 0 <= value <= 2**53 and math.isfinite(value)


def _integer(value):
    return type(value) is int and 0 <= value <= 2**63 - 1


def _match(value, pattern, *, nullable=False):
    return (nullable and value is None) or (
        type(value) is str and pattern.fullmatch(value) is not None
    )


def _observed(value):
    if value is None:
        return True
    if type(value) is not dict or set(value) != _OBSERVED_FIELDS:
        return False
    return (
        _match(value["selected"], _IDENTIFIER, nullable=True)
        and value["desired"] in ("running", "stopped", "unknown")
        and value["observed"] in (
            "ready", "loading", "stopped", "failed", "unavailable", "unknown"
        )
        and (value["container_running"] is None or type(value["container_running"]) is bool)
        and _match(value["active_identity"], _DIGEST, nullable=True)
        and _integer(value["generation"])
        and type(value["state_persisted"]) is bool
        and _number(value["observed_at"])
    )


def _entry(key, value):
    if not _match(key, _OPERATION_ID):
        return False
    if type(value) is not dict or set(value) != _ENTRY_FIELDS:
        return False
    terminal = value["status"] in TERMINAL
    return (
        value["id"] == key
        and value["kind"] in ("switch", "stop")
        and _match(value["target"], _IDENTIFIER, nullable=True)
        and (value["kind"] != "switch" or value["target"] is not None)
        and value["status"] in ("pending", "running", "succeeded", "failed", "interrupted")
        and all(_number(value[name]) for name in ("created_at", "updated_at", "deadline"))
        and value["updated_at"] >= value["created_at"]
        and value["deadline"] >= value["created_at"]
        and (
            (_number(value["completed_at"]) and value["completed_at"] >= value["created_at"])
            if terminal else value["completed_at"] is None
        )
        and _match(value["request_digest"], _DIGEST)
        and _match(value["idempotency_digest"], _DIGEST)
        and _integer(value["generation"])
        and _match(value["active_identity"], _DIGEST, nullable=True)
        and _match(value["failure_code"], _SAFE_CODE, nullable=True)
        and _observed(value["observed"])
        and type(value["state_persisted"]) is bool
        and value["poll_url"] == "/control/v1/operations/" + key
    )


class Journal:
    """Validate and bound a durable operation journal.

    ``read`` distinguishes absent state (a new empty journal), corrupt state,
    and unavailable storage. ``save`` returns False if the write did not confirm
    durable success; the caller must not claim persistence or perform a normal
    destructive transition in that case. A False result may include an uncertain
    post-rename fsync failure, so callers must never replay work automatically.

    Terminal operations and their idempotency digests expire together exactly
    ``retention_seconds`` after completion. ``prune`` never evicts an active or
    unexpired operation; a full journal requires admission to fail closed.
    Lifecycle reconciliation of pending/running entries belongs to the owner.
    """

    def __init__(self, store, max_entries=128, retention_seconds=86400, clock=time.time):
        if type(max_entries) is not int or not 1 <= max_entries <= 128:
            raise JournalInvalid()
        if not _number(retention_seconds) or retention_seconds <= 0:
            raise JournalInvalid()
        self.store = store
        self.max_entries = max_entries
        self.retention_seconds = retention_seconds
        self.clock = clock

    def _validated(self, state):
        try:
            if type(state) is not dict or set(state) != _STATE_FIELDS:
                raise ValueError()
            if type(state["schema"]) is not int or state["schema"] != 1:
                raise ValueError()
            if not _integer(state["generation"]) or not _match(state["fingerprint"], _DIGEST, nullable=True):
                raise ValueError()
            entries = state["entries"]
            if type(entries) is not dict or len(entries) > self.max_entries:
                raise ValueError()
            if not all(_entry(key, value) for key, value in entries.items()):
                raise ValueError()
            digests = [entry["idempotency_digest"] for entry in entries.values()]
            if len(digests) != len(set(digests)):
                raise ValueError()
            if sum(entry["status"] not in TERMINAL for entry in entries.values()) > 1:
                raise ValueError()
            encoded = json.dumps(state, allow_nan=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
            if len(encoded) > MAX_BYTES:
                raise ValueError()
            return copy.deepcopy(state)
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
            raise JournalInvalid() from None

    def read(self):
        try:
            value = self.store.read()
        except JournalCorrupt:
            raise JournalCorrupt() from None
        except Exception:
            raise JournalUnavailable() from None
        if value is None:
            return empty_state()
        try:
            return self._validated(value)
        except JournalInvalid:
            raise JournalCorrupt() from None

    def save(self, state):
        value = self._validated(state)
        try:
            self.store.write(value)
        except Exception:
            return False
        return True

    def prune(self, state):
        value = self._validated(state)
        now = self.clock()
        if not _number(now):
            raise JournalInvalid()
        value["entries"] = {
            key: entry for key, entry in value["entries"].items()
            if entry["status"] not in TERMINAL
            or now < entry["completed_at"] + self.retention_seconds
        }
        return value
