"""Cheap benchmark telemetry. Collection is read-only; callers own storage/lease guards.

No process smaps/PSS read exists in the timed collector. Bind cgroup paths to
reviewed container/PID identities before sampling and recheck identities at trial
boundaries. These samples are observations, not a replacement for admission guards.
"""
from __future__ import annotations

import csv
import io
import math
import subprocess
import time
from pathlib import Path
from typing import Callable, Mapping

MIB = 1024 ** 2
GPU_COMMAND = ["nvidia-smi", "--query-gpu=uuid,memory.total,memory.used,memory.free,utilization.gpu,power.draw", "--format=csv,noheader,nounits"]
DECODE_GPU_FIELDS = ('utilization.memory', 'clocks.current.sm', 'clocks.current.memory',
                     'pcie.link.gen.current', 'pcie.link.width.current', 'power.limit')


def _number(value: str, integer: bool = True):
    try:
        result = int(value) if integer else float(value)
        return result if result >= 0 and math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def _pairs(text: str, colon: bool = False) -> dict:
    out = {}
    for line in text.splitlines():
        cells = line.replace(":", " ", 1).split() if colon else line.split()
        if len(cells) >= 2:
            value = _number(cells[1])
            if colon and (len(cells) != 3 or cells[2] != "kB"):
                value = None
            out[cells[0]] = value
    return out


def parse_meminfo(text: str) -> dict:
    data = _pairs(text, colon=True)
    values = {name: None if data.get(key) is None else data[key] * 1024 for name, key in
              (("available_bytes", "MemAvailable"), ("total_bytes", "MemTotal"),
               ("swap_total_bytes", "SwapTotal"), ("swap_free_bytes", "SwapFree"))}
    total, free = values["swap_total_bytes"], values["swap_free_bytes"]
    values["swap_used_bytes"] = total - free if total is not None and free is not None and total >= free else None
    return values


def parse_vmstat(text: str) -> dict:
    data = _pairs(text)
    return {key: data.get(key) for key in ("pgfault", "pgmajfault", "pswpin", "pswpout", "oom_kill")}


def parse_cgroup(files: Mapping[str, str | None]) -> dict:
    stats = _pairs(files.get("memory.stat") or "")
    events = _pairs(files.get("memory.events") or "")
    scalar = lambda key: _number((files.get(key) or "").strip())
    # cgroup-v2 anon is NOT process RSS. There is no portable cgroup-v2 RSS
    # counter; expose null instead of relabeling anon/current as RSS.
    return {"current_bytes": scalar("memory.current"), "anon_bytes": stats.get("anon"),
            "file_bytes": stats.get("file"), "file_mapped_bytes": stats.get("file_mapped"), "rss_bytes": None,
            "rss_unavailable_reason": "cgroup_v2_has_no_rss_counter",
            "kernel_bytes": stats.get("kernel"), "shmem_bytes": stats.get("shmem"),
            "peak_since_cgroup_creation_bytes": scalar("memory.peak"),
            "swap_bytes": scalar("memory.swap.current"),
            "pgfault": stats.get("pgfault"), "pgmajfault": stats.get("pgmajfault"),
            "events": {key: events.get(key) for key in ("low", "high", "max", "oom", "oom_kill", "oom_group_kill")},
            "allocator_workspace_bytes": None}


def required_host_demand(cgroup: dict, *, required_file_backed_bytes: int,
                         host_workspace_bytes: int | None = None,
                         workspace_in_anon: bool = True, file_basis: str) -> dict:
    """Measured required components, separating reclaimable file cache.

    Retain all mapped file pages and shmem conservatively, or a larger reviewed
    necessary resident file-weight amount. Never subtract all file pages blindly.
    Native CUDA_Host workspace usually already contributes to cgroup anon; record
    it separately without double counting. Unknown native workspace is allowed
    only when the measured anon total includes runtime workspace.
    """
    required_keys = ("anon_bytes", "kernel_bytes", "file_bytes", "file_mapped_bytes", "shmem_bytes")
    if not isinstance(cgroup, dict) or any(type(cgroup.get(k)) is not int or cgroup[k] < 0 for k in required_keys):
        raise ValueError("host_demand_components_unavailable")
    if (type(required_file_backed_bytes) is not int or required_file_backed_bytes < 0
            or not isinstance(file_basis, str) or not file_basis or len(file_basis) > 512
            or type(workspace_in_anon) is not bool):
        raise ValueError("required_file_or_workspace_basis_unavailable")
    if host_workspace_bytes is not None and (type(host_workspace_bytes) is not int or host_workspace_bytes < 0):
        raise ValueError("native_workspace_invalid")
    if not workspace_in_anon and host_workspace_bytes is None:
        raise ValueError("unaccounted_host_workspace")
    if workspace_in_anon and host_workspace_bytes is not None and host_workspace_bytes > cgroup["anon_bytes"]:
        raise ValueError("native_workspace_exceeds_measured_anon")
    file_total = cgroup["file_bytes"]
    if any(cgroup[k] > file_total for k in ("file_mapped_bytes", "shmem_bytes")) or required_file_backed_bytes > file_total:
        raise ValueError("required_file_accounting_inconsistent")
    # mapped and shmem may overlap; their sum, capped by all charged file pages,
    # is conservative and keeps both out of the reclaimable-cache deduction.
    retained_file = max(required_file_backed_bytes,
                        min(file_total, cgroup["file_mapped_bytes"] + cgroup["shmem_bytes"]))
    extra_workspace = 0 if workspace_in_anon else host_workspace_bytes
    required = cgroup["anon_bytes"] + cgroup["kernel_bytes"] + retained_file + extra_workspace
    if required <= 0:
        raise ValueError("measured_host_demand_empty")
    return {"schema": 1, "evidence_status": "MEASURED_COMPONENTS", "required_bytes": required,
            "anon_bytes": cgroup["anon_bytes"], "kernel_bytes": cgroup["kernel_bytes"],
            "file_bytes": file_total, "file_mapped_bytes": cgroup["file_mapped_bytes"],
            "shmem_bytes": cgroup["shmem_bytes"], "required_file_backed_bytes": retained_file,
            "reclaimable_file_bytes": file_total - retained_file, "file_basis": file_basis,
            "host_workspace_bytes": host_workspace_bytes, "workspace_extra_bytes": extra_workspace,
            "workspace_accounting": "included_in_measured_anon" if workspace_in_anon else "additional_to_measured_anon",
            "cgroup_current_bytes": cgroup.get("current_bytes"),
            "measurement_scope": "sampled_required_components; verify proposed cap during actual future load"}


def parse_process_status(text: str) -> dict:
    data = _pairs(text, colon=True)
    return {key: None if data.get(native) is None else data[native] * 1024 for key, native in
            (("rss_bytes", "VmRSS"), ("swap_bytes", "VmSwap"), ("peak_rss_bytes", "VmHWM"))}


def parse_gpu_csv(text: str, *, decode_diagnostic=False) -> list[dict]:
    out = []
    seen = set()
    for cells in csv.reader(io.StringIO(text)):
        cells = [cell.strip() for cell in cells]
        if not cells:
            continue
        if len(cells) != (12 if decode_diagnostic else 6) or not cells[0].startswith("GPU-") or cells[0] in seen:
            raise ValueError("malformed_or_duplicate_gpu_row")
        seen.add(cells[0])
        values = [_number(cell, integer=False) for cell in cells[1:]]
        out.append({"uuid": cells[0], "total_bytes": None if values[0] is None else int(values[0] * MIB),
                    "used_bytes": None if values[1] is None else int(values[1] * MIB),
                    "free_bytes": None if values[2] is None else int(values[2] * MIB),
                    "utilization_percent": values[3], "power_watts": values[4],
                    "allocator_workspace_bytes": None})
        if decode_diagnostic:
            names = ('memory_utilization_percent', 'sm_clock_mhz', 'memory_clock_mhz',
                     'pcie_link_generation', 'pcie_link_width', 'power_limit_watts')
            out[-1]['decode_fields'] = dict(zip(names, values[5:]))
            out[-1]['decode_missing_fields'] = [name for name, value in out[-1]['decode_fields'].items() if value is None]
            out[-1]['pcie_throughput'] = None  # Link state is not transfer throughput.
    return out


def _read(path: Path, errors: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        # Paths and exception messages are omitted from shareable samples.
        errors.append("read_" + type(exc).__name__)
        return ""


def collect_sample(cgroups: Mapping[str, Path], *, pids: Mapping[str, list[int]] | None = None,
                   proc_root: Path = Path("/proc"), gpu_reader: Callable[[], str] | None = None,
                   clock: Callable[[], float] = time.monotonic, decode_diagnostic=False) -> dict:
    """One cheap read. pids must include all known model worker processes.

    Root RUN must establish protected cgroup/container identity and process start
    identity before calling; RSS sums can double-count shared pages. Missing
    workers or unavailable status is explicit, never an invented zero.
    """
    started = clock()
    errors = []
    host = parse_meminfo(_read(proc_root / "meminfo", errors))
    faults = parse_vmstat(_read(proc_root / "vmstat", errors))
    groups = {}
    for identity, path in cgroups.items():
        files = {name: _read(path / name, errors) for name in
                 ("memory.current", "memory.stat", "memory.events", "memory.peak", "memory.swap.current")}
        groups[identity] = parse_cgroup(files)
    process = {}
    for identity, members in (pids or {}).items():
        if any(type(pid) is not int or pid <= 0 for pid in members) or len(set(members)) != len(members):
            raise ValueError("invalid_pid_inventory")
        rows = [parse_process_status(_read(proc_root / str(pid) / "status", errors)) for pid in members]
        process[identity] = {"known_process_count": len(rows), "rss_scope": "sum_known_processes_may_double_count_shared_pages",
                             "rss_bytes": sum(r["rss_bytes"] for r in rows) if rows and all(r["rss_bytes"] is not None for r in rows) else None,
                             "swap_bytes": sum(r["swap_bytes"] for r in rows) if rows and all(r["swap_bytes"] is not None for r in rows) else None}
    try:
        gpu_command = list(GPU_COMMAND)
        if decode_diagnostic:
            gpu_command[1] += ',' + ','.join(DECODE_GPU_FIELDS)
        raw = gpu_reader() if gpu_reader else subprocess.run(gpu_command, check=True, capture_output=True, text=True, timeout=2).stdout
        gpus = parse_gpu_csv(raw, decode_diagnostic=decode_diagnostic)
        if not gpus:
            errors.append("gpu_inventory_unavailable")
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        errors.append("gpu_" + type(exc).__name__)
        gpus = []
        if decode_diagnostic and gpu_reader is None:
            # An unsupported optional clock/PCIe field must not erase the
            # existing memory-reserve safety query. A failed base query still
            # leaves reserve evidence unavailable and the safety gate closed.
            try:
                raw = subprocess.run(GPU_COMMAND, check=True, capture_output=True,
                                     text=True, timeout=2).stdout
                gpus = parse_gpu_csv(raw)
                for row in gpus:
                    row["decode_fields_status"] = "UNAVAILABLE"
                    row["pcie_throughput"] = None
                errors.append("optional_decode_gpu_fields_unavailable")
            except (OSError, subprocess.SubprocessError, ValueError) as base_exc:
                errors.append("base_gpu_" + type(base_exc).__name__)
    ended = clock()
    return {"sample_kind": "cheap", "timestamp_monotonic_s": started,
            "collection_finished_monotonic_s": ended, "collection_duration_s": ended - started,
            "host": host, "vmstat": faults, "cgroups": groups, "processes": process,
            "gpus": gpus, "errors": errors, "pss_bytes": None,
            "pss_unavailable_reason": "quiescent_checkpoint_only"}


def sample_series(stop, emit: Callable[[dict], None], collector: Callable[[], dict], *,
                  interval_s: float = 1.0, clock: Callable[[], float] = time.monotonic) -> dict:
    """Background sampler until a threading.Event is set; never signals inference.

    Report/emit failures are harness errors: keep collecting until request owner
    stops this sampler. No retry or lifecycle callback is accepted here.
    """
    if not 0.5 <= interval_s <= 2:
        raise ValueError("cheap_sample_interval_outside_reviewed_range")
    counts = {"collected": 0, "collection_errors": 0, "emit_errors": 0}
    deadline = clock()
    while not stop.is_set():
        try:
            row = collector()
            counts["collected"] += 1
            try:
                emit(row)
            except Exception:
                counts["emit_errors"] += 1
        except Exception:
            counts["collection_errors"] += 1
        deadline += interval_s
        # Do not catch up with a burst after a slow read.
        now = clock()
        if deadline < now:
            deadline = now + interval_s
        stop.wait(max(0, deadline - now))
    return counts


def _flatten(value: dict, prefix: str = "") -> dict:
    out = {}
    for key, item in value.items():
        path = prefix + key
        if isinstance(item, dict):
            out.update(_flatten(item, path + "."))
        elif isinstance(item, list) and key == "gpus":
            for gpu in item:
                out.update(_flatten(gpu, path + "." + gpu["uuid"] + "."))
        elif item is None or (type(item) in (int, float) and math.isfinite(item)):
            out[path] = item
    return out


def summarize_samples(samples: list[dict], request_start: float, request_end: float,
                      interval_s: float = 1.0) -> dict:
    if request_end <= request_start or interval_s <= 0:
        raise ValueError("invalid_telemetry_window")
    rows = sorted((row for row in samples if request_start <= row["timestamp_monotonic_s"] <= request_end),
                  key=lambda row: row["timestamp_monotonic_s"])
    times = [row["timestamp_monotonic_s"] for row in rows]
    span = request_end - request_start
    covered_intervals = [(max(request_start, t - interval_s / 2), min(request_end, t + interval_s / 2)) for t in times]
    covered = 0.0
    right = request_start
    for left, end in covered_intervals:
        covered += max(0, end - max(left, right))
        right = max(right, end)
    flattened = [_flatten(row) for row in rows]
    keys = set().union(*(row.keys() for row in flattened)) if rows else set()
    metrics = {}
    for key in sorted(keys):
        available = [row[key] for row in flattened if row.get(key) is not None]
        metrics[key] = {"available_samples": len(available), "total_samples": len(rows),
                        "sampled_peak": max(available) if available else None,
                        "sampled_minimum": min(available) if available else None,
                        "first": available[0] if available else None, "last": available[-1] if available else None}
        if key.startswith("vmstat.") or ".events." in key or key.endswith((".pgfault", ".pgmajfault")):
            counter_valid = len(available) >= 2 and all(b >= a for a, b in zip(available, available[1:]))
            metrics[key]["observed_counter_delta"] = available[-1] - available[0] if counter_valid else None
            metrics[key]["counter_reset_or_insufficient_samples"] = not counter_valid
    return {"sample_count": len(rows), "nominal_interval_s": interval_s,
            "coverage_fraction_estimate": covered / span, "coverage_method": "union_of_half_interval_windows_not_continuous_observation",
            "leading_gap_s": times[0] - request_start if times else span,
            "trailing_gap_s": request_end - times[-1] if times else span,
            "maximum_sample_gap_s": max([b - a for a, b in zip(times, times[1:])], default=None),
            "collection_overhead_s": sum(row.get("collection_duration_s", 0) for row in rows),
            "collection_overhead_fraction": sum(row.get("collection_duration_s", 0) for row in rows) / span,
            "overhead_limit": "collection wall time only; performance perturbation requires paired measurement",
            "metrics": metrics, "peak_scope": "sampled; memory.peak covers cgroup lifetime, not request only"}


def model_swap_state(baseline_bytes: int | None, observed_bytes: list[int | None], sustained_samples: int = 3) -> str:
    """Host swap alone never establishes model growth; use owned cgroup bytes."""
    if type(sustained_samples) is not int or sustained_samples < 2:
        raise ValueError("sustained_swap_requires_multiple_samples")
    if type(baseline_bytes) is not int or baseline_bytes < 0:
        return "UNAVAILABLE"
    consecutive = 0
    normalized = []
    for value in observed_bytes:
        valid = type(value) is int and value >= 0
        normalized.append(value if valid else None)
        consecutive = consecutive + 1 if valid and value > baseline_bytes else 0
        if consecutive >= sustained_samples:
            # A later fall/unavailable reading does not erase an observed stop.
            return "STOP_SUSTAINED_MODEL_SWAP_GROWTH"
    if len(normalized) < sustained_samples or any(v is None for v in normalized[-sustained_samples:]):
        return "UNAVAILABLE"
    return "NO_SUSTAINED_GROWTH_OBSERVED"
