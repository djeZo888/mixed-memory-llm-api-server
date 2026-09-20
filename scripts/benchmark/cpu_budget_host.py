"""Narrow native and admission proofs for the closed 480K CPU comparison."""
from __future__ import annotations

import math
from pathlib import Path
import re

from .lifecycle import require
from .cpu_budget_profiles import CAPACITY, CPU_SCOPE, POSTRESTART_SCOPE, postrestart_manifest


def qwen_native_view(info):
    """Resolve flat/nested native configuration without accepting conflicts.

    Scheduler allocation remains independent: fields only in server_args cannot
    establish native pool/input allocation.
    """
    require(isinstance(info, dict), 'cpu_native_info_unavailable')
    args = info.get('server_args', info)
    require(isinstance(args, dict), 'cpu_native_context_mismatch')
    states = info.get('internal_states', [])
    require(isinstance(states, list) and len(states) <= 1 and all(isinstance(v, dict) for v in states),
            'cpu_native_states_invalid')
    resolved = dict(args)
    for name, expected in (('context_length', CAPACITY), ('tp_size', 1)):
        values = [row[name] for row in [info, args, *states] if name in row]
        require(values and all(type(value) is int and value == expected for value in values),
                'cpu_native_context_mismatch')
        resolved[name] = expected
    return resolved


def qwen_native_diagnostic(info):
    """Safe field projection only; at most two states expose cardinality failure."""
    names = ('context_length', 'tp_size', 'max_total_num_tokens', 'max_req_input_len', 'max_req_len')
    types = {int: 'int', float: 'float', bool: 'bool', str: 'str',
             dict: 'dict', list: 'list', type(None): 'NoneType'}
    def fields(container):
        result = {}
        for name in names:
            present = isinstance(container, dict) and name in container
            value = container[name] if present else None
            row = {'present': present, 'type': types.get(type(value), 'other') if present else None}
            if type(value) is int or (type(value) is float and math.isfinite(value)):
                row['value'] = value
            result[name] = row
        return result
    root = info if isinstance(info, dict) else {}
    states = root.get('internal_states')
    return {'top_level': fields(root), 'server_args': fields(root.get('server_args')),
            'internal_states': [fields(state) for state in states[:2]] if isinstance(states, list) else []}


def qwen_native_proof(info, *, scope=CPU_SCOPE):
    """Require actual scheduler pool/input limits, independently of arguments.

    Same pinned scheduler reserve semantics as concurrent_profiles.native_capacity.
    Top-level and single internal-state values must agree; argv is never proof.
    """
    require(scope in (CPU_SCOPE, POSTRESTART_SCOPE), 'cpu_native_scope_mismatch')
    require(isinstance(info, dict), 'cpu_native_info_unavailable')
    args = qwen_native_view(info) if scope == POSTRESTART_SCOPE else info.get('server_args', info)
    require(isinstance(args, dict) and type(args.get('context_length')) is int and
            args['context_length'] == CAPACITY and type(args.get('tp_size')) is int and args['tp_size'] == 1,
            'cpu_native_context_mismatch')
    states = info.get('internal_states', [])
    require(isinstance(states, list) and len(states) <= 1 and all(isinstance(v, dict) for v in states),
            'cpu_native_states_invalid')
    def actual(name, optional=False):
        values = [v[name] for v in [info, *states] if name in v]
        if not values and optional:
            return None
        require(values and all(type(v) is int and v > 0 and v == values[0] for v in values),
                'cpu_native_pool_or_input_unavailable')
        return values[0]
    pool, limit, request = actual('max_total_num_tokens'), actual('max_req_input_len'), actual('max_req_len', True)
    require(pool == CAPACITY and limit == CAPACITY - 6 and request in (None, CAPACITY - 1),
            'cpu_native_pool_or_input_mismatch')
    return {'configured_context': CAPACITY, 'native_pool_tokens': pool,
            'native_input_limit': limit, 'native_request_limit': request,
            'basis': 'actual_scheduler_top_level_or_single_internal_state'}


def pre_retirement_admission(host, original):
    from .host import collect_sample, concurrent_capacity_policy
    if host.scope == POSTRESTART_SCOPE:
        state = original['manager']
        require(state.get('desired') == 'stopped' and state.get('observed') == 'stopped'
                and state.get('container_running') is False and state.get('boot_policy') == 'manual',
                'postrestart_original_STOPPED_manual_required')
        production = 'captured_original_STOPPED_manual_preserved_for_canonical_restore'
    else:
        require(host.scope == CPU_SCOPE and original['manager']['selected'] ==
                'qwen38-27b-1000000-yarn4-tp2-bf16kv' and original['manager']['desired'] == 'running',
                'cpu_original_singleton_required')
        production = 'original_QwenTP2_1M_preserved_for_canonical_restore'
    sample = collect_sample({})
    available = sample['host'].get('available_bytes')
    policy = concurrent_capacity_policy(host.scope)
    require(type(available) is int and available >= policy['preload_host_available_minimum_bytes'],
            'cpu_fresh_host_admission_failed')
    return {'host_available_bytes': available, 'minimum_bytes': policy['preload_host_available_minimum_bytes'],
            'policy': policy, 'production': production}


def postrestart_cpu_proof(manifest, container, cgroup, pids, *,
                         proc_root=Path('/proc'), sys_root=Path('/sys/devices/system')):
    """Quiescent actual72 affinity/node proof, without changing any affinity.

    This is guest topology and allowed-node evidence only. Supplied physical
    host affinity belongs to a separate provenance record; no pinning, NUMA
    residency exclusivity or bandwidth claim is inferred here.
    """
    from .profiles import cpu_set
    from .decode_telemetry import parse_stat, _validate_pids
    from .cpu_budget_telemetry import numa_snapshot
    require(manifest == postrestart_manifest(manifest.get('placement')), 'postrestart_exact_manifest_required')
    _validate_pids({'owned': pids}, 2048)
    require(bool(pids), 'postrestart_owned_processes_required')
    def read(path):
        with Path(path).open('r') as source:
            value = source.read(1024 * 1024 + 1)
        require(len(value) <= 1024 * 1024, 'postrestart_topology_read_limit')
        return value.strip()
    online = read(sys_root / 'cpu/online')
    nodes_online = read(sys_root / 'node/online')
    require(cpu_set(online) == set(range(72)), 'postrestart_exact_72_online_required')
    require(cpu_set(nodes_online) == set(range(8)), 'postrestart_exact_eight_nodes_required')
    nodes, assigned = {}, set()
    for node in range(8):
        node_path = sys_root / 'node' / ('node' + str(node))
        cpulist = read(node_path / 'cpulist')
        members = cpu_set(cpulist) if cpulist else set()
        require(not assigned & members, 'postrestart_guest_node_cpu_overlap')
        assigned |= members
        totals = re.findall(r'^Node\s+' + str(node) + r'\s+MemTotal:\s+(\d+)\s+kB$',
                            read(node_path / 'meminfo'), re.MULTILINE)
        require(len(totals) == 1 and int(totals[0]) > 0, 'postrestart_guest_node_memory_unproved')
        nodes[str(node)] = {'guest_cpulist': cpulist, 'guest_mem_total_bytes': int(totals[0]) * 1024}
    require(assigned == set(range(72)), 'postrestart_guest_node_cpu_union_mismatch')
    expected = cpu_set(manifest['guest_cpuset'])
    effective = read(Path(cgroup) / 'cpuset.cpus.effective')
    mems = read(Path(cgroup) / 'cpuset.mems.effective')
    config = container['HostConfig']
    require(config.get('CpusetCpus') == manifest['guest_cpuset'] and cpu_set(effective) == expected,
            'postrestart_effective_cpus_mismatch')
    require(config.get('CpusetMems', '') in ('', '0-7') and cpu_set(mems) == set(range(8)),
            'postrestart_all_memory_nodes_required')
    processes = []
    for pid in pids:
        base = proc_root / str(pid)
        before = parse_stat(read(base / 'stat'))
        fields = dict(line.split(':', 1) for line in read(base / 'status').splitlines() if ':' in line)
        after = parse_stat(read(base / 'stat'))
        require(before['starttime_ticks'] is not None and before['starttime_ticks'] == after['starttime_ticks'],
                'postrestart_process_generation_changed')
        allowed, allowed_mems = fields.get('Cpus_allowed_list', '').strip(), fields.get('Mems_allowed_list', '').strip()
        require(cpu_set(allowed) == expected and cpu_set(allowed_mems) == set(range(8)),
                'postrestart_process_allowed_scope_mismatch')
        processes.append({'pid': pid, 'process_starttime_ticks': before['starttime_ticks'],
                          'cpus_allowed_list': allowed, 'mems_allowed_list': allowed_mems})
    numa = numa_snapshot({'owned': pids}, proc_root=proc_root)
    require(all(row['status'] == 'AVAILABLE' and row['process_starttime_ticks'] == expected_row['process_starttime_ticks']
                for row, expected_row in zip(numa['processes']['owned'], processes)),
            'postrestart_quiescent_numa_unproved')
    return {'status': 'PASS', 'guest_online_cpus': online, 'guest_online_nodes': nodes_online,
            'guest_nodes': nodes, 'guest_node_memory_total_bytes': sum(v['guest_mem_total_bytes'] for v in nodes.values()),
            'cgroup_cpus_effective': effective, 'cgroup_mems_effective': mems,
            'processes': processes, 'numa_pages': numa,
            'shared_cpu_budget': 'G0-71 and Q0-7 share72 guest CPUs',
            'outside_timed_requests_required': True,
            'physical_host_mapping': 'separate user-supplied configuration; not observed by this guest proof',
            'evidence_boundary': 'no exclusive physical pinning, full bandwidth or physical RAM residency proof'}


def resident_obligations(host):
    """Use existing both-cap remaining obligations; no charged-cache credit."""
    from .host import collect_sample
    from .concurrent_validate import memory_obligations, identity_stamp
    active = [r['resource']['id'] for r in host.owner.resources
              if r['state'] == 'RUNNING' and r['resource']['id'] in host.load_manifests]
    before = {cid: identity_stamp(host, cid) for cid in active}
    identities = {cid: host.identity(cid) for cid in active}
    sample = collect_sample({cid: row[1] for cid, row in identities.items()},
                            pids={cid: row[2] for cid, row in identities.items()})
    require(set(sample['cgroups']) == set(active), 'cpu_resident_inventory_changed')
    result = memory_obligations(sample, host.load_manifests)
    require(before == {cid: identity_stamp(host, cid) for cid in active}, 'cpu_resident_identity_changed')
    result['identities'] = before
    return result
