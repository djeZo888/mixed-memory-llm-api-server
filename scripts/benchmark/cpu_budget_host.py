"""Narrow native and admission proofs for the closed 480K CPU comparison."""
from __future__ import annotations

from .lifecycle import require
from .cpu_budget_profiles import CAPACITY, CPU_SCOPE


def qwen_native_proof(info):
    """Require actual scheduler pool/input limits, independently of arguments.

    Same pinned scheduler reserve semantics as concurrent_profiles.native_capacity.
    Top-level and single internal-state values must agree; argv is never proof.
    """
    require(isinstance(info, dict), 'cpu_native_info_unavailable')
    args = info.get('server_args', {})
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
    require(host.scope == CPU_SCOPE and original['manager']['selected'] ==
            'qwen38-27b-1000000-yarn4-tp2-bf16kv' and original['manager']['desired'] == 'running',
            'cpu_original_singleton_required')
    sample = collect_sample({})
    available = sample['host'].get('available_bytes')
    policy = concurrent_capacity_policy(CPU_SCOPE)
    require(type(available) is int and available >= policy['preload_host_available_minimum_bytes'],
            'cpu_fresh_host_admission_failed')
    return {'host_available_bytes': available, 'minimum_bytes': policy['preload_host_available_minimum_bytes'],
            'policy': policy, 'production': 'original_QwenTP2_1M_preserved_for_canonical_restore'}


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
