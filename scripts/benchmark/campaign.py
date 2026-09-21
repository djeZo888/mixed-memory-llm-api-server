"""Offline benchmark campaign primitives; no service or inference operations.

The future RUN owner supplies guarded persistence and actual observed durations.
Pure scheduling results are illustrative until populated from live timestamps.
"""
from __future__ import annotations

import copy
from functools import wraps
import json
import math
import os
import time
import threading
from pathlib import Path
from typing import Callable

BUDGET_SECONDS = 6 * 60 * 60
MAX_REQUEST_SECONDS = 7200
GIB = 1024 ** 3
CACHE_HYPOTHESES = {"glm": 95232, "qwen": 65536}
STATES = {"READY", "PASS", "SKIP_UNSAFE_PLACEMENT", "STOP_ALLOCATION_FAILURE",
          "STOP_SUSTAINED_MODEL_SWAP_GROWTH", "STOP_OOM", "STOP_CORRECTNESS_REGRESSION",
          "HARNESS_FAILURE", "STOP_BUDGET", "RESTORING", "RESTORED", "RESTORE_FAILED"}


def _budget_serialized(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._mutex:
            return method(self, *args, **kwargs)
    return call


class CampaignBudget:
    """Durable six-hour wall budget; owner is the existing canonical lease holder.

    before_write/after_write are mandatory guard callbacks; offline tests use
    explicit no-ops. Default filesystem persistence is WORKER-LOCAL ONLY. On ai-vm
    declare storage_scope="ai-vm" and supply paired read(path)->bytes|None and
    persist(path,bytes) adapters using the installed AnchoredRoot writer contract.
    The callbacks own protected ancestry, registered mount/path validation and
    atomic durable writes; before/after guards alone cannot replace anchoring.
    Callback mode performs no direct filesystem operations. Mixed lanes share
    this one budget instance; its reentrant thread mutex serializes admission,
    ledger writes, phase transitions and snapshot reads. This is no alternative
    lifecycle/file lock. A backwards wall clock fails closed. Restoration is a terminal
    phase and does not consume or reopen measurement budget.
    """
    budget_seconds = BUDGET_SECONDS

    def __init__(self, path: Path, *, before_write: Callable, after_write: Callable,
                 clock: Callable[[], float] = time.time,
                 read: Callable[[Path], bytes | None] | None = None,
                 persist: Callable[[Path, bytes], None] | None = None,
                 storage_scope: str = "worker-local"):
        self._mutex = threading.RLock()
        self.path = Path(path)
        self.before_write, self.after_write, self.clock = before_write, after_write, clock
        if storage_scope not in {"worker-local", "ai-vm"}:
            raise ValueError("invalid_budget_storage_scope")
        if (read is None) != (persist is None):
            raise ValueError("paired_anchored_read_and_persist_required")
        if read is not None and (not callable(read) or not callable(persist)):
            raise ValueError("invalid_anchored_persistence_callbacks")
        if persist is None and (storage_scope == "ai-vm" or self.path == Path("/data") or Path("/data") in self.path.parents):
            raise ValueError("ai_vm_requires_anchored_persistence")
        self.read, self.persist = read, persist
        with self._mutex:
            raw = read(self.path) if read is not None else (self.path.read_bytes() if self.path.exists() else None)
            if raw is not None and not isinstance(raw, bytes):
                raise ValueError("budget_reader_must_return_bytes_or_none")
            self._data = json.loads(raw) if raw is not None else None
            if self._data is not None:
                self._validate()

    @property
    @_budget_serialized
    def data(self):
        """Consistent detached snapshot; callers cannot mutate shared state."""
        return copy.deepcopy(self._data)

    def _validate(self):
        d = self._data
        if (not isinstance(d, dict) or d.get("schema") != 1 or d.get("budget_seconds") != self.budget_seconds
                or d.get("phase") not in {"MEASURING", "RESTORING", "RESTORED", "RESTORE_FAILED"}
                or d.get("start_kind") not in {"maintenance", "model_trial"}
                or type(d.get("started_at")) not in (int, float)
                or type(d.get("last_seen_at")) not in (int, float)
                or not math.isfinite(d["started_at"]) or not math.isfinite(d["last_seen_at"])
                or d["last_seen_at"] < d["started_at"]):
            raise ValueError("invalid_budget_ledger")
        if d["phase"] != "MEASURING" and (type(d.get("restoration_started_at")) not in (int, float)
                or not d["started_at"] <= d["restoration_started_at"] <= d["last_seen_at"]):
            raise ValueError("invalid_restoration_budget_boundary")

    def _save(self):
        payload = (json.dumps(self._data, sort_keys=True) + "\n").encode("utf-8")
        self.before_write()
        if self.persist is not None:
            self.persist(self.path, payload)
            self.after_write()
            return
        # This branch is explicitly worker-local and is never a VM writer.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".pending")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            parent_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        finally:
            if temporary.exists():
                temporary.unlink()
        self.after_write()

    @_budget_serialized
    def start(self, kind: str):
        if self._data is not None:
            raise ValueError("budget_already_started")
        if kind not in {"maintenance", "model_trial"}:
            raise ValueError("start_at_first_maintenance_or_model_trial")
        now = self.clock()
        if not math.isfinite(now) or now < 0:
            raise ValueError("invalid_clock")
        self._data = {"schema": 1, "budget_seconds": self.budget_seconds, "phase": "MEASURING",
                     "start_kind": kind, "started_at": now, "last_seen_at": now,
                     "restoration_started_at": None}
        self._save()
        return dict(self._data)

    @_budget_serialized
    def checkpoint(self):
        if self._data is None:
            raise ValueError("budget_not_started")
        now = self.clock()
        if not math.isfinite(now) or now < self._data["last_seen_at"]:
            raise ValueError("wall_clock_regressed_stop_campaign")
        self._data["last_seen_at"] = now
        self._save()
        boundary = self._data["restoration_started_at"] if self._data["phase"] != "MEASURING" else now
        return max(0, self.budget_seconds - (boundary - self._data["started_at"]))

    @_budget_serialized
    def request_timeout(self, requested_s: float = MAX_REQUEST_SECONDS) -> float:
        if not math.isfinite(requested_s) or not 0 < requested_s <= MAX_REQUEST_SECONDS:
            raise ValueError("request_timeout_out_of_bounds")
        remaining = self.checkpoint()
        if self._data["phase"] != "MEASURING" or remaining <= 0:
            raise ValueError("STOP_BUDGET")
        # Shorten to remaining budget, never start a second unbounded timer.
        return min(requested_s, remaining)

    @_budget_serialized
    def begin_restoration(self):
        self.checkpoint()
        if self._data["phase"] != "MEASURING":
            raise ValueError("restoration_already_started")
        self._data["phase"] = "RESTORING"
        self._data["restoration_started_at"] = self._data["last_seen_at"]
        self._save()

    @_budget_serialized
    def finish_restoration(self, verified: bool):
        if self._data is None or self._data["phase"] != "RESTORING" or type(verified) is not bool:
            raise ValueError("restoration_not_active")
        self.checkpoint()
        self._data["phase"] = "RESTORED" if verified else "RESTORE_FAILED"
        self._save()


def trial_decision(*, unsafe=False, allocation_failed=False, oom=False, swap_growth=False,
                   harness_valid=True, correctness_passed=True, budget_expired=False) -> dict:
    """No retry or cancellation action. Unsafe/OOM evidence is independent of parser health."""
    state = ("SKIP_UNSAFE_PLACEMENT" if unsafe else "STOP_OOM" if oom else
             "STOP_ALLOCATION_FAILURE" if allocation_failed else
             "STOP_SUSTAINED_MODEL_SWAP_GROWTH" if swap_growth else
             "HARNESS_FAILURE" if not harness_valid else "STOP_BUDGET" if budget_expired else
             "STOP_CORRECTNESS_REGRESSION" if not correctness_passed else "PASS")
    return {"state": state, "automatic_retry": False, "cancel_healthy_inference_for_report_error": False,
            "model_correctness_attributable": harness_valid,
            "next_action": "repair_harness_preserve_running_request_and_raw_evidence" if state == "HARNESS_FAILURE" else
                           "review_stop_restore_as_needed" if state != "PASS" else "next_reviewed_trial"}


def mixed_schedule(jobs: list[dict], durations: dict[str, float], mode: str, *, switch_s: float = 0,
                   restore_s: float = 0) -> dict:
    """Deterministic predicted/post-hoc A/B schedule; never sends requests.

    Same jobs/arrivals/fixture hashes must be passed to both. Durations should be
    measured separately in A/B to capture interference, not assumed transferable.
    A starts with Qwen ready, batches all four Qwen jobs, switches once to GLM.
    B starts with both ready. Initial readiness/load cost is reported separately.
    """
    if mode not in {"A", "B"} or len(jobs) != 5:
        raise ValueError("invalid_mixed_workload")
    ids = [j["id"] for j in jobs]
    if len(set(ids)) != 5 or sorted(j["model"] for j in jobs) != ["glm", "qwen", "qwen", "qwen", "qwen"]:
        raise ValueError("requires_one_glm_four_qwen")
    for value in [switch_s, restore_s] + [j["arrival_s"] for j in jobs] + [durations.get(j["id"], -1) for j in jobs]:
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("invalid_schedule_time")
    if any(not isinstance(j.get("fixture_sha256"), str) or len(j["fixture_sha256"]) != 64
           or any(c not in "0123456789abcdef" for c in j["fixture_sha256"]) for j in jobs):
        raise ValueError("missing_fixture_identity")
    qwen = sorted((j for j in jobs if j["model"] == "qwen"), key=lambda j: (j["arrival_s"], ids.index(j["id"])))
    glm = next(j for j in jobs if j["model"] == "glm")
    timeline = []
    q_ready = 0.0
    for job in qwen:
        start = max(q_ready, job["arrival_s"])
        q_ready = start + durations[job["id"]]
        timeline.append({**job, "start_s": start, "end_s": q_ready,
                         "queue_delay_s": start - job["arrival_s"], "service_s": durations[job["id"]],
                         "latency_s": q_ready - job["arrival_s"]})
    glm_ready = q_ready + switch_s if mode == "A" else 0
    start = max(glm_ready, glm["arrival_s"])
    end = start + durations[glm["id"]]
    timeline.append({**glm, "start_s": start, "end_s": end, "queue_delay_s": start - glm["arrival_s"],
                     "service_s": durations[glm["id"]], "latency_s": end - glm["arrival_s"]})
    finish = max(q_ready, end)
    first_arrival = min(j["arrival_s"] for j in jobs)
    return {"mode": mode, "timing_basis": "supplied_durations_not_live_measurement",
            "timeline": sorted(timeline, key=lambda j: (j["start_s"], j["id"])),
            "makespan_s": finish - first_arrival, "completion_from_ready_s": finish,
            "switch_s": switch_s if mode == "A" else 0, "return_to_original_model_s": restore_s,
            "completion_including_restoration_from_ready_s": finish + restore_s,
            "initial_readiness_load_s": None, "interference": "compare_each_job_to_its_own_isolated_model_baseline",
            "memory": "attach_actual_per_model_and_host_telemetry"}


def memory_projection(model: str, configured_tokens: int, components: dict, *,
                      target_tokens: list[int], published_max_tokens: int,
                      observed_cache_bytes: int | None = None) -> dict:
    """Aggregate memory only: no GPU-distribution, speed or quality extrapolation.

    components = weights_bytes/runtime_bytes/workspace_bytes and
    measured_host_demand_bytes, gpu_count. Actual allocation needed to verify KV
    hypothesis. Per-GPU fit requires observed placement fractions and peaks in RUN.
    """
    if model not in CACHE_HYPOTHESES or type(configured_tokens) is not int or configured_tokens <= 0:
        raise ValueError("invalid_memory_model")
    required = {"weights_bytes", "runtime_bytes", "workspace_bytes", "measured_host_demand_bytes", "gpu_count"}
    if not required <= components.keys() or any(type(components[k]) is not int or components[k] < 0 for k in required) or components["gpu_count"] not in (1, 2):
        raise ValueError("invalid_memory_components")
    if type(published_max_tokens) is not int or published_max_tokens < configured_tokens:
        raise ValueError("invalid_published_max")
    allowed = {131072, 262144, 524288, published_max_tokens}
    if not target_tokens or any(type(t) is not int or t not in allowed or t > published_max_tokens for t in target_tokens):
        raise ValueError("only_reviewed_memory_projection_targets")
    if observed_cache_bytes is not None and (type(observed_cache_bytes) is not int or observed_cache_bytes <= 0):
        raise ValueError("invalid_observed_cache")
    hypothesis = CACHE_HYPOTHESES[model]
    measured_slope = observed_cache_bytes / configured_tokens if observed_cache_bytes is not None else None
    fixed = sum(components[k] for k in ("weights_bytes", "runtime_bytes", "workspace_bytes"))
    reserve = components["gpu_count"] * 16 * GIB
    slope = measured_slope if measured_slope is not None else hypothesis
    return {"model": model, "configured_tokens": configured_tokens, "components": dict(components),
            "cache_hypothesis_bytes_per_token_aggregate": hypothesis,
            "observed_cache_bytes": observed_cache_bytes, "observed_bytes_per_configured_token": measured_slope,
            "hypothesis_relative_error": None if measured_slope is None else (measured_slope - hypothesis) / hypothesis,
            "projection_basis": "single_observed_allocation_linear_cache_only_not_verified_scaling" if observed_cache_bytes is not None else "unverified_cache_hypothesis",
            "minimum_reserve_bytes_per_gpu": 16 * GIB,
            "recommended_ram_bytes_at_measured_configuration": math.ceil(components["measured_host_demand_bytes"] * 1.25),
            "projections": [{"configured_tokens": t, "cache_bytes_aggregate": math.ceil(slope * t),
                             "total_bytes_aggregate_including_gpu_reserve": fixed + math.ceil(slope * t) + reserve,
                             "per_gpu_fit": "NOT_ESTABLISHED", "host_ram_at_target": None}
                            for t in target_tokens],
            "limits": ["verify exact runtime cache allocations and placement before decisions",
                       "aggregate sum is not a single-device fit claim", "workspace growth and maximum runtime support unverified",
                       "no speed or quality extrapolation", "allocation-only trials do not establish occupied-context correctness"]}
