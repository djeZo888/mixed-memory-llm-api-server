"""One explicit body-bound retrieval request on the retained actual72 pair.

Pure validation and injected native counting only. The retained controller owns
the one-use durable admission, host proof, six-hour segment, dispatch and hold.
Invalid mailbox data never authorizes release, cleanup, inference or a retry.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
import re
import stat
import time

from agent import protocol
from . import client, cpu_budget_profiles as profile, fixtures, g1_ladder

POLICY = {'measurement_admission_seconds': 21600, 'request_timeout_seconds': 7200,
          'request_clock_starts': 'HTTP_DISPATCH', 'admission_deadline_refuses_new_only': True}
FIELDS = {'decision', 'source_commit', 'owner_run_session_id', 'followup_session_id', 'campaign', 'preset',
          'warm_hold_receipt_sha256', 'placement', 'manifest_sha256', 'request_sha256',
          'fixture_sha256', 'request_id', 'policy'}
# Metadata extracted only after verifying postrestart72_run.SAVED archive hashes.
# No private prompt or answer text is embedded here.
PRESETS = {
    'P-G4K': {'placement': 'G1', 'seed': '53fedfbaa93f687629b4e742', 'records': 108,
        'fixture_sha256': '180b713b5cf87105155aab55503fe2fe71d18dee9eb87cc203ddcd38dc8aa785',
        'scorer_sha256': 'd19a400194815132669308381cccfdaca2ecaf4ef5e5a44c2291ce9ae6429336',
        'input_tokens_minimum': 3420, 'input_tokens_maximum': 3674},
    'P-G65008': {'placement': 'G1', 'seed': 'g1-ladder-fixture-1729', 'records': 2028,
        'fixture_sha256': '8214b5e8ec95364fdc611b4650978630cf662db629c06d7276b148361d7a1478',
        'scorer_sha256': 'd85569deb3b7d499971c443658550255913ce1c3c76970db73b08bed2207beaa',
        'input_tokens_minimum': 64896, 'input_tokens_maximum': 65024},
    'P-Qnear480K': {'placement': 'Q1', 'seed': 'concurrent-qwen-fixture-1729', 'records': 12150,
        'fixture_sha256': 'dbd2c2eedc28fdfdbf922a196ca286e7ba43049528618e21679a6e9fd4c59cd6',
        'scorer_sha256': 'a1b26b49f2759c9953068b8f1a5a269a80e75ea6bce951ec2f2d385195327293',
        'input_tokens_minimum': 479360, 'input_tokens_maximum': 479488},
}


def _require(condition, code):
    if not condition:
        raise ValueError(code)


def validate_go(value, armed, hold_sha, *, completed_ids=(), used_sessions=()):
    """Reject stale controls before the caller performs any native count/read."""
    _require(type(value) is dict and set(value) == FIELDS, 'followup_exact_GO_fields_required')
    _require(armed.get('scope') == profile.POSTRESTART_SCOPE and
             armed.get('campaign') == profile.POSTRESTART_CAMPAIGN and
             value.get('decision') == 'GO' and value.get('source_commit') == armed.get('source_commit') and
             value.get('owner_run_session_id') == armed.get('session_id') and
             value.get('campaign') == armed.get('campaign') and
             value.get('warm_hold_receipt_sha256') == hold_sha,
             'followup_source_owner_campaign_hold_mismatch')
    _require(isinstance(value['source_commit'], str) and bool(re.fullmatch(r'[0-9a-f]{40}', value['source_commit'])),
             'followup_source_commit_invalid')
    session = value['followup_session_id']
    _require(isinstance(session, str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{8,96}', session)) and
             session != armed['session_id'] and not used_sessions, 'followup_fresh_one_use_session_required')
    identifier = value['request_id']
    _require(isinstance(identifier, str) and bool(re.fullmatch(r'F-[A-Za-z0-9_-]{6,64}', identifier)) and
             identifier not in completed_ids, 'followup_unique_request_id_required')
    _require(value.get('placement') in ('G1', 'Q1'), 'followup_closed_model_required')
    _require(isinstance(value.get('preset'), str) and value['preset'] in PRESETS and
             PRESETS[value['preset']]['placement'] == value['placement'], 'followup_closed_preset_required')
    manifest = profile.postrestart_manifest(value['placement'])
    _require(value.get('manifest_sha256') == fixtures.digest(fixtures.canonical(manifest)),
             'followup_exact_manifest_required')
    for name in ('warm_hold_receipt_sha256', 'manifest_sha256', 'request_sha256', 'fixture_sha256'):
        _require(isinstance(value.get(name), str) and bool(re.fullmatch(r'[0-9a-f]{64}', value[name])),
                 'followup_digest_required')
    _require(fixtures.canonical(value.get('policy')) == fixtures.canonical(POLICY),
             'followup_independent_clock_policy_required')
    return copy.deepcopy(value)


def _private_read(path, maximum):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        meta = os.fstat(fd)
        _require(stat.S_ISREG(meta.st_mode) and stat.S_IMODE(meta.st_mode) == 0o600 and
                 meta.st_uid == os.geteuid() and meta.st_nlink == 1 and 0 < meta.st_size <= maximum,
                 'followup_private_regular_file_required')
        with os.fdopen(fd, 'rb', closefd=False) as source:
            raw = source.read(maximum + 1)
        after = os.fstat(fd)
        _require(len(raw) == meta.st_size and (meta.st_size, meta.st_mtime_ns, meta.st_ctime_ns) ==
                 (after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'followup_mailbox_changed_during_read')
        return raw
    finally:
        os.close(fd)


def validate_payload(go, request_raw, fixture_raw):
    _require(fixtures.digest(request_raw) == go['request_sha256'] and
             fixtures.digest(fixture_raw) == go['fixture_sha256'], 'followup_exact_payload_digest_required')
    sample = protocol.strict_json_loads(fixture_raw)
    fixtures.serialize_validate(sample)
    preset = PRESETS[go['preset']]
    _require(all(sample.get(field) == preset[field] for field in ('seed', 'records', 'fixture_sha256')) and
             fixtures.digest(fixtures.canonical(sample['scorer'])) == preset['scorer_sha256'],
             'followup_exact_historical_logical_fixture_required')
    _require(sample['kind'] == 'retrieval' and type(sample['body']['max_tokens']) is int and
             sample['body']['max_tokens'] == 256 and sample['nonce'].startswith('fresh-'),
             'followup_retrieval_fresh_prefix_256_required')
    reference = fixtures.build_sample(sample['body']['model'], sample['records'], sample['seed'], sample['nonce'])
    _require(fixtures.canonical(sample) == fixtures.canonical(reference), 'followup_exact_fixture_required')
    model = 'bench-glm-5.3' if go['placement'] == 'G1' else 'bench-qwen3.8-27b'
    _require(sample['body']['model'] == model, 'followup_payload_model_mismatch')
    expected = protocol.strict_json_loads(g1_ladder.body_bytes(sample) if go['placement'] == 'G1'
                                        else fixtures.serialize_validate(sample))
    body = protocol.strict_json_loads(request_raw)
    # Permit JSON 1 or 1.0 for temperature only, preserving the supplied exact
    # bytes for counting/dispatch. Every other value and type remains closed.
    _require(type(body.get('temperature')) in (int, float) and body['temperature'] == expected['temperature'],
             'followup_sampling_changed')
    expected['temperature'] = body['temperature']
    _require(fixtures.canonical(body) == fixtures.canonical(expected), 'followup_exact_request_policy_required')
    return sample


def read_candidate(state, armed, hold_sha, *, completed_ids=(), used_sessions=()):
    """Read only fixed private files, preserving body bytes and nonce freshness."""
    state = Path(state)
    private = client.private_artifact_directory(state / 'private')
    go = validate_go(protocol.strict_json_loads(_private_read(state / 'followup-GO.json', 16384)),
                     armed, hold_sha, completed_ids=completed_ids, used_sessions=used_sessions)
    _require(not any((private / (go['request_id'] + suffix)).exists() for suffix in
                     ('.request.json', '-count.json', '-fixture.json', '.response.sse')) and
             not (state / (go['request_id'] + '-result.json')).exists(), 'followup_request_id_already_used')
    raw = _private_read(private / 'followup.request.json', 64 * 1024 * 1024)
    fixture_raw = _private_read(private / 'followup.fixture.json', 64 * 1024 * 1024)
    sample = validate_payload(go, raw, fixture_raw)
    # Fresh relative to every preserved request in this task, including a
    # failed or partially captured request. Do not read bulk response data.
    prefix = 'trial-prefix=' + sample['nonce'] + '\n'
    for path in private.glob('*.request.json'):
        if path.name == 'followup.request.json':
            continue
        previous = protocol.strict_json_loads(_private_read(path, 64 * 1024 * 1024))
        _require(not any(isinstance(message.get('content'), str) and message['content'].startswith(prefix)
                         for message in previous.get('messages', [])), 'followup_prefix_already_dispatched')
    return {'go': go, 'raw': raw, 'sample': sample, 'fixture_raw': fixture_raw,
            'manifest': profile.postrestart_manifest(go['placement']),
            'validated_go_sha256': fixtures.digest(fixtures.canonical(go))}


def prepare_job(candidate, cid, counter, *, templates, clock=time.monotonic):
    """Count exactly once after GO validation; never fit, dispatch or write."""
    started = clock()
    go, raw, manifest = candidate['go'], candidate['raw'], candidate['manifest']
    _require(fixtures.digest(fixtures.canonical(go)) == candidate['validated_go_sha256'],
             'followup_GO_changed_before_count')
    _require(manifest == profile.postrestart_manifest(go['placement']) and
             fixtures.digest(fixtures.canonical(manifest)) == go['manifest_sha256'],
             'followup_manifest_changed_before_count')
    sample = validate_payload(go, raw, candidate['fixture_raw'])
    _require(fixtures.canonical(sample) == fixtures.canonical(candidate['sample']), 'followup_fixture_changed_before_count')
    count = fixtures.validate_count(counter(raw), raw, 480000)
    preset = PRESETS[go['preset']]
    _require(count['template_sha256'] == templates[go['placement']] and count['input_tokens'] + 512 <= 480000 and
             preset['input_tokens_minimum'] <= count['input_tokens'] <= preset['input_tokens_maximum'],
             'followup_native_template_or_capacity_mismatch_no_refit')
    return {'id': go['request_id'], 'cid': cid, 'sample': sample, 'raw': raw, 'count': count,
            'manifest_sha256': go['manifest_sha256'], 'generation': False,
            'preparation_seconds': clock() - started,
            'followup_session_id': go['followup_session_id'],
            'followup_GO_sha256': fixtures.digest(fixtures.canonical(go))}
