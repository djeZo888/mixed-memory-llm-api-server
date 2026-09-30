"""Exact scoped affinity pair authority; no runtime reconfiguration."""
import datetime
import hashlib
import json
from pathlib import Path

PROFILES = ['r12-spread4', 'r13-spread2']
BASE = Path('/data/build/H016-20260927/worker1-affinity14')


def validate(profile_base=None):
    go = json.loads((BASE / 'ROOT-AFFINITY14-GO.json').read_text())
    plan = json.loads((BASE / 'PLAN.json').read_text())
    now = datetime.datetime.now(datetime.timezone.utc)
    assert go.get('authorized') is True and go.get('profiles') == PROFILES, 'root_scope'
    assert now < datetime.datetime.fromisoformat(go['expires_utc'].replace('Z', '+00:00')), 'go_expired'
    for key in ['profiles', 'client_end_utc', 'pair_cleanup_utc', 'pair_completion_utc', 'minimum_profile_budget_seconds', 'global_end_utc', 'latest_profile_start_utc', 'second_requires_native_tps_gt']:
        assert go[key] == plan[key], 'root_deadline_mismatch'
    cleanup = datetime.datetime.fromisoformat(plan['pair_cleanup_utc'].replace('Z', '+00:00'))
    end = datetime.datetime.fromisoformat(plan['pair_completion_utc'].replace('Z', '+00:00'))
    assert plan['client_end_utc'] == '2026-09-27T17:48:00Z' and plan['pair_cleanup_utc'] == '2026-09-27T17:50:00Z', 'fixed_client_cleanup'
    assert plan['pair_completion_utc'] == '2026-09-27T17:57:30Z' and plan['global_end_utc'] == '2026-09-27T18:33:08Z', 'fixed_settlement_global'
    assert plan['latest_profile_start_utc'] == go['expires_utc'] == '2026-09-27T17:35:00Z', 'fixed_go_expiry'
    assert plan['second_requires_native_tps_gt'] == 9.209882711781072, 'fixed_second_threshold'
    assert now < cleanup and (end-cleanup).total_seconds() >= 450, 'cleanup_budget'
    assert end <= datetime.datetime(2026, 9, 27, 18, 33, 8, tzinfo=datetime.timezone.utc), 'hard_end'
    assert plan['minimum_profile_budget_seconds'] == 900, 'profile_budget'
    manifest = json.loads((BASE / 'SOURCE-SHA256.json').read_text())
    assert manifest == go['source_sha256'], 'exact_source_closure'
    for name, digest in manifest.items():
        parts = Path(name).parts
        assert '..' not in parts and not Path(name).is_absolute(), 'source_name'
        path = BASE / name if len(parts) == 1 else BASE.parent / ('worker1-' + parts[0]) / parts[1]
        assert len(parts) == 1 or (len(parts) == 2 and parts[0] in PROFILES), 'source_scope'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, 'source_drift'
    if profile_base:
        cfg = json.loads((Path(profile_base) / 'LAUNCH.json').read_text())
        assert cfg['profile'] in PROFILES and cfg['request_end_utc'] == plan['pair_cleanup_utc'], 'profile_plan'
        assert cfg['admission_end_utc'] == cfg['client_end_utc'] == plan['client_end_utc'], 'profile_client_deadline'
        assert cfg['pair_completion_utc'] == plan['pair_completion_utc'] and cfg['global_end_utc'] == plan['global_end_utc'], 'profile_final_deadlines'
    return go, plan
