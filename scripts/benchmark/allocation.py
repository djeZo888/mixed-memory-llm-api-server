"""Offline allocation evidence parsers and fail-closed pre-request checks.

GLM native records reuse the shipped D3 parser. Qwen raw patterns were verified
against actual pinned installed source during read-only BENCHPREP. RUN must bind
all inputs to the current container/load and retain raw-log hash privately.
No parsing result alone establishes weights identity, readiness or safe request.
"""
from __future__ import annotations

import math
import re

from d3t import guards
from benchmark.profiles import GLM_DECODE_DIAG_CAMPAIGN, GLM_DECODE_PROFILE_CAMPAIGN, GLM_DECODE_DIAG_CAPACITIES, glm_decode_diag_manifest

GIB = 1024 ** 3


def parse_glm_log(text: str) -> dict:
    """Exact D3 byte diagnostics plus rounded human weight/offload observations.

    Cache/compute native bytes are preferred to rounded human MiB lines. Human
    model buffers remain log-labeled MiB, never claimed as exact weight bytes.
    """
    state = {"log_lines": 0, "errors": {key: 0 for key in guards.ERROR_PATTERNS}}
    buffers, offloaded, malformed = {}, None, False
    host_pending, host_compute = {}, None
    for line in text.splitlines():
        try:
            guards.parse_log_line(line, state)
        except guards.Error:
            malformed = True
        marker = line.find("D3T_NATIVE_V1")
        record = line[marker:].rstrip("\r\n") if marker >= 0 else ""
        if record.startswith("D3T_NATIVE_V1 kind=graph "):
            host_pending = {}
        host = re.fullmatch(r"D3T_NATIVE_V1 kind=compute backend=(CPU|CUDA_Host) bytes=(\d+)", record)
        if host:
            backend, count = host.groups()
            if backend in host_pending:
                malformed = True
            host_pending[backend] = int(count)
        if record == "D3T_NATIVE_V1 kind=end":
            host_compute = dict(host_pending)
        match = re.search(r"load_tensors:\s+(CPU(?:_Mapped)?|CUDA_Host|CUDA\d+) model buffer size\s*=\s*([0-9]+\.[0-9]+) MiB", line)
        if match:
            backend, value = match.groups()
            if backend in buffers:
                malformed = True  # concatenated loads or ambiguous duplicates
            buffers[backend] = float(value)
        match = re.search(r"offloaded (\d+)/(\d+) layers to GPU", line)
        if match:
            value = tuple(map(int, match.groups()))
            if offloaded is not None or value[0] > value[1]:
                malformed = True
            offloaded = value
    native = state.get("native")
    if state.get("native_group_open"):
        malformed = True
    return {"kind": "glm", "parser_status": "HARNESS_FAILURE" if malformed else "PARSED",
            "configured_context": native.get("n_ctx") if native else None,
            "native": native, "weights_mib_log_label": buffers or None,
            "host_weights_mib_log_label": {k: v for k, v in buffers.items() if k in {"CPU", "CPU_Mapped", "CUDA_Host"}} or None,
            "device_weights_mib_log_label": {k: v for k, v in buffers.items() if re.fullmatch(r"CUDA\d+", k)} or None,
            "host_compute_bytes": host_compute or None,
            "host_workspace_bytes": sum(host_compute.values()) if host_compute else None,
            "host_workspace_scope": "native RAM compute buffers; separate from CUDA device workspace, commonly included in cgroup anon",
            "offloaded_layers": offloaded[0] if offloaded else None,
            "total_layers": offloaded[1] if offloaded else None,
            "slot_count": state.get("slot_count"), "slot_context": state.get("slot_context"),
            "runtime_errors": state["errors"],
            "scope": "current-load raw native log; model identity and N76 still require reviewed live manifest proof"}


def parse_qwen_log(text: str, server_facts: dict) -> dict:
    """Parse exact pinned source log phrases; never equate VA bounds with allocation.

    Source SHA256s verified read-only in BENCHPREP allocation-source.json:
    model_executor/model_runner.py b40efe0c7fb87d6f3baf5f9df3e755b9138247f82505183c564b4f8b1bc6663a
    mem_cache/memory_pool.py 7955db1470ea36b99eb43483a5bd999dbda62119ff54aee7f9e8e01f31b2a9b5
    """
    events, malformed = [], False
    number = r"([0-9]+\.[0-9]+)"
    for ordinal, line in enumerate(text.splitlines(), 1):
        rank = re.search(r"\bTP(\d+)\b", line)
        base = {"line_ordinal": ordinal}
        if rank:
            base["tp_rank"] = int(rank.group(1))
        if "Load weight end." in line:
            weight = re.search(r"avail mem=" + number + r" GB, mem usage=" + number + r" GB\.", line)
            if weight:
                events.append({**base, "phase": "weights_end", "available_gb_log_label": float(weight.group(1)),
                               "memory_usage_gb_log_label": float(weight.group(2))})
            else:
                malformed = True
        if "#tokens:" in line and ("is allocated." in line or "VA upper bound" in line):
            cache = re.search(r"is allocated\. dtype: (?:torch\.)?bfloat16, #tokens: (\d+), K size: "
                              + number + r" GB, V size: " + number + r" GB", line)
            if cache:
                events.append({**base, "phase": "kv_allocated", "cache_tokens": int(cache.group(1)),
                               "k_size_gb_log_label": float(cache.group(2)), "v_size_gb_log_label": float(cache.group(3))})
            else:
                malformed = True  # virtual reservation/unknown dtype is not allocated BF16 K/V
    parsed = parse_qwen_log_facts(events, server_facts)
    if malformed:
        parsed["parser_status"] = "HARNESS_FAILURE"
    parsed["raw_extraction"] = "pinned_installed_source_log_phrases"
    return parsed


def parse_qwen_log_facts(events: list[dict], server_facts: dict) -> dict:
    """Validate reviewed numeric log-event extraction plus native server facts.

    Schema provenance: reports/q38retry-tp2-1m-evidence/handoff.json numeric_events.
    parse_qwen_log provides the exact installed-source raw extraction above;
    unavailable rank is allowed only for independently reported TP1.
    """
    tp = server_facts.get("tp_size")
    ranks, malformed = {}, False
    for event in events:
        phase = event.get("phase")
        if phase not in {"weights_end", "kv_allocated"}:
            continue
        rank = event.get("tp_rank", 0 if tp == 1 else None)
        if type(rank) is not int or type(tp) is not int or tp not in (1, 2) or not 0 <= rank < tp:
            malformed = True
            continue
        row = ranks.setdefault(rank, {"weights_gb_log_label": None, "cache_tokens": None,
                                      "k_gb_log_label": None, "v_gb_log_label": None,
                                      "workspace_bytes": None})
        names = {"weights_end": {"weights_gb_log_label": "memory_usage_gb_log_label"},
                 "kv_allocated": {"cache_tokens": "cache_tokens", "k_gb_log_label": "k_size_gb_log_label",
                                  "v_gb_log_label": "v_size_gb_log_label"}}[phase]
        for output, source in names.items():
            value = event.get(source)
            valid = type(value) in (int, float) and math.isfinite(value) and value > 0
            if output == "cache_tokens":
                valid = valid and type(value) is int
            if not valid or row[output] is not None:
                malformed = True
            else:
                row[output] = value
    return {"kind": "qwen", "parser_status": "HARNESS_FAILURE" if malformed else "PARSED",
            "configured_context": server_facts.get("context_length"),
            "actual_pool_tokens": server_facts.get("max_total_num_tokens"),
            "configured_pool_tokens": server_facts.get("max_total_tokens"),
            "tp_size": tp, "cache_dtype": server_facts.get("kv_cache_dtype"),
            "weight_quantization": server_facts.get("quantization"),
            "ranks": ranks, "units": "GB labels retained; no conversion to bytes without verified source semantics",
            "scope": "current-load numeric extraction and native server facts; caller must bind current container/load"}


def allocation_gate(manifest: dict, parsed: dict, observed: dict, *, strict_g1=False, strict_glmrepair=False) -> dict:
    """Pure admission decision; missing current proof refuses, never becomes zero.

    observed must be produced by root-reviewed protected inspection: image_ref,
    device_request_uuids, cuda_uuid_order, native_argv, model identity, GPU free
    bytes, and raw_log_sha256 for this exact load. This function does not collect
    or authenticate those facts, acquire lease or authorize requests.
    """
    reasons = []
    def need(condition, reason):
        if not condition:
            reasons.append(reason)
    expected_uuids = manifest["gpu_uuids"]
    capacity = manifest["configured_capacity"]
    decode_diag = manifest.get("campaign") in (GLM_DECODE_DIAG_CAMPAIGN, GLM_DECODE_PROFILE_CAMPAIGN)
    exact_decode_diag = (decode_diag and type(capacity) is int and capacity in GLM_DECODE_DIAG_CAPACITIES
                         and (manifest.get("campaign") != GLM_DECODE_PROFILE_CAMPAIGN or capacity == 65536)
                         and manifest == glm_decode_diag_manifest(capacity, campaign=manifest["campaign"]))
    if decode_diag:
        need(exact_decode_diag, "glm_decode_diag_exact_manifest_required")
    need(parsed.get("parser_status") == "PARSED", "allocation_parser_failure")
    need(observed.get("image_ref") == manifest["image"], "current_image_proof_missing_or_mismatched")
    need(observed.get("model") == manifest["model"], "current_weight_identity_proof_missing_or_mismatched")
    need(observed.get("native_argv") == manifest["native_argv"], "current_native_arguments_mismatch")
    need(observed.get("device_request_uuids") == expected_uuids, "device_request_uuid_mismatch")
    need(observed.get("cuda_uuid_order") == expected_uuids, "cuda_ordinal_uuid_mapping_missing_or_mismatched")
    need(isinstance(observed.get("raw_log_sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", observed["raw_log_sha256"]),
         "current_raw_allocation_log_identity_missing")
    need(parsed.get("configured_context") == capacity, "configured_context_unproved")
    free = observed.get("gpu_free_bytes", {})
    for uuid in expected_uuids:
        need(type(free.get(uuid)) is int and free[uuid] >= 16 * GIB, "gpu_reserve_unproved:" + uuid)
    if manifest["placement"].startswith("G"):
        native = parsed.get("native") or {}
        devices = {"CUDA" + str(i) for i in range(len(expected_uuids))}
        need(parsed.get("kind") == "glm", "wrong_allocation_parser")
        need(native.get("n_ctx_seq") == capacity and native.get("n_seq_max") == 1 and native.get("no_alloc") == 0,
             "native_allocation_context_or_slot_unproved")
        # Pinned b29c606 src/llama-context.cpp:245 clamps causal n_batch to
        # n_ctx. Retain --batch-size 2048; admit the 1K clamp only for the exact
        # frozen diagnostic manifest, never by capacity or a caller flag alone.
        expected_batch = min(2048, capacity) if exact_decode_diag else 2048
        need(native.get("n_batch") == expected_batch and native.get("n_ubatch") == 512,
             "native_batch_mismatch")
        need(native.get("flash_attn") == 1 and native.get("fused_lid") == 1, "native_fusion_unproved")
        for kind in ("cache", "compute"):
            values = native.get(kind + "_bytes") or {}
            need(set(values) == devices and all(type(v) is int and v > 0 for v in values.values()),
                 "native_" + kind + "_allocation_unproved")
        if strict_g1 or decode_diag or strict_glmrepair and manifest["placement"] == "G1":
            need(manifest["placement"] == "G1" and devices == {"CUDA0"}, "g1_single_device_required")
            need(native.get("cache_bytes") == {"CUDA0": 95232 * capacity},
                 "g1_f16_cache_bytes_mismatch")
            need(native.get("fa_nodes") == 78 and native.get("lid_nodes") == 21,
                 "g1_main_indexer_graph_mismatch")
        if strict_glmrepair:
            need(capacity == 4096 and ((manifest["placement"] == "G2" and devices == {"CUDA0", "CUDA1"})
                                      or (manifest["placement"] == "G1" and devices == {"CUDA0"})),
                 "glmrepair_matched_gpu_placement_required")
            cache = native.get("cache_bytes") or {}
            need(all(type(v) is int for v in cache.values()) and sum(cache.values()) == 95232 * capacity,
                 "glmrepair_f16_cache_total_mismatch")
            need(native.get("fa_nodes") == 78 and native.get("lid_nodes") == 21,
                 "glmrepair_main_indexer_graph_mismatch")
        if strict_glmrepair or decode_diag:
            limits = observed.get("container_memory_limits") or {}
            need(limits == {"docker_memory_bytes": 640 * GIB, "docker_memory_swap_bytes": 640 * GIB,
                            "cgroup_memory_max": str(640 * GIB), "cgroup_memory_swap_max": "0"},
                 "glmrepair_effective_memory_limits_unproved")
            cpu = observed.get("container_cpu_limits") or {}
            need(cpu.get("docker_cpuset_cpus") == "0-95" and cpu.get("cgroup_cpuset_cpus_effective") == "0-95" and
                 all(cpu.get(k) == 0 for k in ("docker_nano_cpus", "docker_cpu_quota", "docker_cpu_period")) and
                 bool(re.fullmatch(r"max [1-9][0-9]*", cpu.get("cgroup_cpu_max", ""))),
                 "glmrepair_effective_cpu_limits_unproved")
        weights = parsed.get("weights_mib_log_label") or {}
        need(devices <= weights.keys() and any(k in {"CPU", "CPU_Mapped", "CUDA_Host"} for k in weights), "cpu_gpu_weight_allocation_unproved")
        expected = manifest.get("glm_offload_expectation") or {}
        counts = (expected.get("offloaded_layers"), expected.get("total_layers"))
        reviewed = (all(type(value) is int and value > 0 for value in counts)
                    and counts[0] <= counts[1] and expected.get("evidence_status") == "REVIEWED_LOG_COUNT_SEMANTICS"
                    and isinstance(expected.get("provenance"), str) and bool(expected["provenance"]))
        need(reviewed, "reviewed_exact_offload_counts_missing")
        need(reviewed and (parsed.get("offloaded_layers"), parsed.get("total_layers")) == counts,
             "actual_gpu_offload_counts_mismatch")
        need(parsed.get("slot_count") == 1 and parsed.get("slot_context") == capacity, "runtime_slot_context_unproved")
        need(all(v == 0 for v in parsed.get("runtime_errors", {}).values()) and bool(parsed.get("runtime_errors")), "runtime_error_or_missing_diagnostics")
    else:
        tp = len(expected_uuids)
        need(parsed.get("kind") == "qwen" and parsed.get("tp_size") == tp, "native_tp_unproved")
        need(parsed.get("actual_pool_tokens") == capacity and parsed.get("configured_pool_tokens") == capacity,
             "actual_and_configured_pool_unproved")
        need(parsed.get("cache_dtype") == "bfloat16" and parsed.get("weight_quantization") == "fp8", "qwen_cache_or_weight_dtype_unproved")
        ranks = parsed.get("ranks") or {}
        need(set(ranks) == set(range(tp)) and all(row.get("cache_tokens") == capacity and
             all(row.get(key) is not None for key in ("weights_gb_log_label", "k_gb_log_label", "v_gb_log_label"))
             for row in ranks.values()), "per_rank_weights_and_cache_unproved")
    return {"status": "ALLOCATION_PROOF_ACCEPTED" if not reasons else "STOP_ALLOCATION_PROOF",
            "reasons": reasons, "inference_or_correctness_acceptance": "NOT_ESTABLISHED",
            "reserve_scope": "current sampled free bytes; monitor during timed requests"}
