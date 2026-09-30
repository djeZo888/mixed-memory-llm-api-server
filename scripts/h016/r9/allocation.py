#!/usr/bin/env python3
"""Pure MiMo allocation evidence; call only at phase boundaries, never in guards.

The caller owns bounded log capture, current container/image binding, protected
writes and admission. This module runs no command and authorizes no operation.
Native rounded MiB labels are retained as such; calculated bytes are separate.
Slot/API/argv context alone never establishes actual allocated KV capacity.
"""
from __future__ import annotations

import hashlib
import math
import re

MIB = 1024 ** 2
GLOBAL_BYTES_PER_CELL = 51200
MAX_LOG_BYTES = 64 * MIB
_NUMBER = r"([0-9]+(?:\.[0-9]+)?)"
_BACKEND = r"(CPU(?:_Mapped|_REPACK)?|CUDA_Host|CUDA\d+)"


def parse_native_allocation(raw_text: str, expected_context: int, *,
                            expected_pool_context: int | None = None,
                            expected_usable_context: int | None = None) -> dict:
    """Fail-closed extraction of one load's native global/SWA F16 allocation.

    Expected pinned log shapes: creating non-SWA/SWA KV cache, KV buffer size,
    size=(cells,layers,seqs), context n_ctx, and compute buffer size. A current
    native log with suppressed INFO diagnostics correctly returns UNPROVEN.
    Padding is accepted only when expected_pool_context is explicitly supplied
    by the caller from its separately validated root decision. No auto-padding.
    """
    if type(expected_context) is not int or expected_context <= 0:
        raise ValueError('expected_context must be a positive integer')
    if expected_usable_context is None:
        expected_usable_context = expected_context
    if type(expected_usable_context) is not int or (expected_context, expected_usable_context) not in (
            (expected_context, expected_context), (1000000, 1000192)):
        raise ValueError('usable context must be exact or reviewed million-context rounding')
    if expected_pool_context is None:
        expected_pool_context = expected_context
    if type(expected_pool_context) is not int or expected_pool_context < expected_usable_context:
        raise ValueError('expected_pool_context must be an explicit integer at least expected usable context')
    raw = raw_text.encode('utf-8')
    if len(raw) > MAX_LOG_BYTES:
        raise ValueError('native allocation log exceeds bounded capture size')
    reasons, contexts, slots, pools = [], [], [], {}
    model, workspace, output, workspace_events = {}, {}, {}, []
    current = None
    for ordinal, line in enumerate(raw_text.splitlines(), 1):
        match = re.search(r'\bn_ctx\s*=\s*(\d+)\s*$', line)
        if match:
            contexts.append(int(match.group(1)))
        match = re.search(r'initializing, n_slots = (\d+), n_ctx_slot = (\d+), kv_unified', line)
        if match:
            slots.append({'slots': int(match.group(1)), 'context': int(match.group(2))})
        match = re.search(r'creating\s+(non-SWA|SWA) KV cache, size = (\d+) cells', line)
        if match:
            kind = 'global' if match.group(1) == 'non-SWA' else 'swa'
            if kind in pools:
                reasons.append('duplicate_' + kind + '_pool')
            current = {'requested_cells_log': int(match.group(2)), 'buffers_mib_log_label': {},
                       'creation_line': ordinal, 'summary': None}
            pools[kind] = current
        match = re.search(_BACKEND + r'\s+KV buffer size\s*=\s*' + _NUMBER + r' MiB', line)
        if match:
            if current is None:
                reasons.append('kv_buffer_without_pool')
            else:
                backend, value = match.groups()
                if backend in current['buffers_mib_log_label']:
                    reasons.append('duplicate_kv_buffer')
                current['buffers_mib_log_label'][backend] = float(value)
        match = re.search(r'\bsize\s*=\s*' + _NUMBER + r' MiB\s*\(\s*(\d+) cells,\s*(\d+) layers,\s*'
                          r'(\d+)/(\d+) seqs\),\s*K \(([^)]+)\):\s*' + _NUMBER
                          + r' MiB,\s*V \(([^)]+)\):\s*' + _NUMBER + r' MiB', line)
        if match:
            if current is None:
                reasons.append('kv_summary_without_pool')
            else:
                if current['summary'] is not None:
                    reasons.append('duplicate_kv_summary')
                total, cells, layers, sequences, streams, kt, km, vt, vm = match.groups()
                current['summary'] = {'mib_log_label': float(total), 'cells': int(cells),
                    'layers': int(layers), 'streams': int(streams), 'sequences': int(sequences),
                    'k_type': kt, 'k_mib_log_label': float(km), 'v_type': vt,
                    'v_mib_log_label': float(vm), 'line': ordinal}
        match = re.search(_BACKEND + r'\s+(model|compute|output) buffer size\s*=\s*'
                          + _NUMBER + r' MiB', line)
        if match:
            backend, kind, value = match.groups()
            destination = {'model': model, 'compute': workspace, 'output': output}[kind]
            if backend in destination and kind != 'compute':
                reasons.append('duplicate_' + kind + '_buffer')
            destination[backend] = float(value)
            if kind == 'compute':
                workspace_events.append({'backend': backend, 'mib_log_label': float(value), 'line': ordinal})

    def need(condition, reason):
        if not condition:
            reasons.append(reason)

    need(contexts == [expected_pool_context], 'native_context_missing_duplicate_or_mismatched')
    need(slots == [{'slots': 1, 'context': expected_usable_context}], 'single_slot_context_missing_or_mismatched')
    for kind, cells, layers, bytes_per_cell in [
            ('global', expected_pool_context, 10, GLOBAL_BYTES_PER_CELL),
            ('swa', 768, 60, 60 * 8 * (192 + 128) * 2)]:
        pool = pools.get(kind)
        need(pool is not None, kind + '_pool_missing')
        if pool is None:
            continue
        summary = pool['summary']
        need(summary is not None, kind + '_allocation_summary_missing')
        if summary is None:
            continue
        need(pool['requested_cells_log'] == summary['cells'] == cells, kind + '_actual_cells_mismatch')
        need(summary['layers'] == layers and summary['streams'] == summary['sequences'] == 1,
             kind + '_layer_or_sequence_mismatch')
        need(summary['k_type'] == summary['v_type'] == 'f16', kind + '_not_f16')
        expected_mib = bytes_per_cell * cells / MIB
        need(abs(summary['mib_log_label'] - expected_mib) <= .011, kind + '_size_mismatch')
        need(abs(summary['k_mib_log_label'] - expected_mib * .6) <= .011 and
             abs(summary['v_mib_log_label'] - expected_mib * .4) <= .011, kind + '_k_v_size_mismatch')
        buffers = pool['buffers_mib_log_label']
        need(set(buffers) == {'CUDA0'}, kind + '_device_buffer_missing_or_mismatched')
        need(abs(sum(buffers.values()) - summary['mib_log_label']) <= .021,
             kind + '_buffer_summary_size_mismatch')
    need(model.get('CUDA0', 0) > 0, 'device_model_buffer_missing')
    need(workspace.get('CUDA0', 0) > 0, 'device_workspace_buffer_missing')
    global_summary = (pools.get('global') or {}).get('summary') or {}
    actual_cells = global_summary.get('cells')
    return {'status': 'PROVEN' if not reasons else 'UNPROVEN', 'reasons': sorted(set(reasons)),
        'raw_log_sha256': hashlib.sha256(raw).hexdigest(), 'raw_log_bytes': len(raw),
        'configured_context': expected_context, 'native_context_records': contexts,
        'usable_context_tokens': expected_usable_context, 'expected_physical_pool_cells': expected_pool_context,
        'slot_records': slots, 'actual_global_pool_cells': actual_cells,
        'pool_padding_cells': actual_cells - expected_usable_context if actual_cells is not None else None,
        'occupied_input_tokens': None, 'occupied_scope': 'Not established by allocation logs.',
        'global_kv_bytes_formula': '51200 * actual_global_pool_cells',
        'global_kv_bytes_calculated': GLOBAL_BYTES_PER_CELL * actual_cells if actual_cells is not None else None,
        'pools': pools, 'model_buffers_mib_log_label': model,
        'workspace_buffers_mib_log_label': workspace, 'workspace_buffer_records': workspace_events,
        'output_buffers_mib_log_label': output,
        'units': 'Native MiB values are rounded labels; calculated bytes are separately identified.',
        'scope': 'Allocation only; usable slot context and physical padded cells remain distinct. '
                 'No model identity, occupied-context, semantic, or application qualification.'}


def compose_phase(proof: dict | None, phase: str, gpu_rows: list[dict], memory: dict,
                  frontier_uuid: str, native_identity: dict, *, occupied_input_tokens: int | None = None,
                  reserved_mib: float | None = None, utc: str | None = None,
                  monotonic: float | None = None, cgroup: dict | None = None) -> dict:
    """Compose caller-captured cheap phase counters, without collecting or writing.

    Pass reserved_mib only from the separate actual NVML/nvidia-smi reserved
    readback. total-used-free remains an independent arithmetic residual.
    cgroup is optional memory.current/stat/swap evidence, not added to host RAM.
    """
    errors = []
    rows = [row for row in gpu_rows if row.get('uuid') == frontier_uuid]
    frontier = dict(rows[0]) if len(rows) == 1 else {}

    def finite(value):
        return type(value) in (int, float) and math.isfinite(value) and value >= 0

    valid_gpu = len(rows) == 1 and all(finite(frontier.get(key)) for key in
                                      ('total_mib', 'used_mib', 'free_mib'))
    valid_gpu = valid_gpu and frontier.get('total_mib', 0) > 0
    if not valid_gpu:
        errors.append('frontier_memory_readback_missing_or_invalid')
    if reserved_mib is not None and not finite(reserved_mib):
        raise ValueError('reserved_mib must be an actual nonnegative finite readback or None')
    counters = {}
    if valid_gpu:
        total, used, free = (frontier[key] for key in ('total_mib', 'used_mib', 'free_mib'))
        residual = total - used - free
        if used > total or free > total or residual < -2:
            errors.append('frontier_memory_accounting_invalid')
        logged_device_mib = None
        component_proof = proof.get('components', proof) if proof is not None else None
        if component_proof is not None and component_proof.get('status') == 'PROVEN':
            logged_device_mib = sum(component_proof.get(k, {}).get('CUDA0', 0) for k in
                ('model_buffers_mib_log_label', 'workspace_buffers_mib_log_label', 'output_buffers_mib_log_label'))
            logged_device_mib += sum(p['buffers_mib_log_label'].get('CUDA0', 0)
                                     for p in component_proof.get('pools', {}).values())
        counters = {'total_mib': total, 'used_mib': used, 'free_mib': free,
            'arithmetic_unaccounted_mib': residual, 'reserved_mib_readback': reserved_mib,
            'residual_minus_reserved_mib': residual - reserved_mib if reserved_mib is not None else None,
            'reserve_floor_mib': .07 * total, 'margin_above_reserve_mib': free - .07 * total,
            'reserve_pass': free >= .07 * total, 'logged_device_components_mib_rounded': logged_device_mib,
            'used_minus_logged_components_mib': used - logged_device_mib if logged_device_mib is not None else None,
            'accounting_note': 'Residual is unaccounted, not a measurement of reserved memory; '
                               'used-minus-components also includes unlisted/rounded/runtime allocations.'}
    host_total, host_available = memory.get('MemTotal'), memory.get('MemAvailable')
    valid_host = finite(host_total) and finite(host_available) and host_total > 0 and host_available <= host_total
    if not valid_host:
        errors.append('host_memory_readback_missing_or_invalid')
    if occupied_input_tokens is not None and (type(occupied_input_tokens) is not int or occupied_input_tokens < 0):
        raise ValueError('occupied_input_tokens must be a separately verified native prompt count')
    return {'phase': phase, 'utc': utc, 'monotonic': monotonic,
        'capture_status': 'CAPTURED' if not errors else 'INVALID', 'errors': errors,
        'native_identity': {key: native_identity[key] for key in
            ('candidate_id', 'container_id', 'native_pid', 'native_started_at', 'image') if key in native_identity},
        'allocation': proof, 'frontier': counters,
        'gpu_readback': [{k: r[k] for k in ('uuid', 'total_mib', 'used_mib', 'free_mib', 'temp_c') if k in r}
                         for r in gpu_rows],
        'host_memory_bytes': {k: memory[k] for k in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree') if k in memory},
        'host_reserve_pass': host_available >= .15 * host_total if valid_host else None,
        'cgroup_memory': cgroup, 'cgroup_note': 'memory.current includes reclaimable file cache; '
                                             'do not add it to host used memory.',
        'occupied_input_tokens': occupied_input_tokens,
        'occupied_scope': 'Separate caller-verified request prompt usage; allocation is not occupation.',
        'bandwidth_scope': 'No host DRAM or GPU VRAM byte-rate counters are captured here.'}
