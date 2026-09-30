"""READ ONLY H021-ACCEPT04 settlement attestation; never releases ownership."""
import hashlib
import json
import pathlib
import re
import sqlite3
import subprocess
import sys

SOURCE = '5f95693e8c83bd40ca167b9b8fe2e1520ce51634'
PILOT = 'H021-ACCEPT04'
RELEASE = '/opt/ai-harness/releases/h021-pilot03-' + SOURCE + '/ai-harness'
RECEIPT = '/home/user/.cache/h021-pilot03-deployment/receipt.json'
RECEIPT_SHA = '70e29c313e1b6c0f5edd961300784d3b445f5893d1798297ed31c63d385352dd'
UNIT = '/home/user/.config/systemd/user/ai-harness.service'
UNIT_SHA = '00993f56364eff64f4082f111ea4b738e876e61a01ef24c327de4ffcb6766e3b'
# Deployed build hashes from STAGED-READBACK, binding the attestation semantics.
BUILD = {'broker': 'c34a45577f807e9b9aa4ff94da0ea4a60fab6ad50b01a5d608f98febd25bb31d',
         'codex-engine': 'c233a30f21bdb73c8fec2539cdcc6c6c315c255bfbbf9328e0a260418224a2bc',
         'codex-launcher': '3b25a8a62a0c813e7d887950b253c776064315e09e064802b2fc74da2348ec30',
         'engine': 'c71b49cbe042c933fc79c2ecef6e52b65696040bc4a14e5065a26f7064d8a3b4',
         'gateway-ownership': 'a8ecea7cc2858cc74da0bb8c25da65582da7c0a12485256dbfa29dea20394966'}

CLEANUP_LABEL = 'Owned engine container cleanup confirmed; interrupted work was not replayed'

def physical_releases(db, session):
    """Read additive offline dispositions, never turn accepted work into success.

    Authority remains the source-bound protected operator transaction. A caller's
    idle flag or cleanup label alone cannot substitute for its complete audit.
    Historical deployment pins above deliberately remain unchanged; deployment
    must independently bind these semantics to its actual candidate/build.
    """
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('h036_physical_releases','h036_released_requests')")}
    if not tables:
        return {}, set()
    assert len(tables) == 2, 'incomplete physical release schema'
    released, runs = {}, set()
    for row in db.execute('SELECT * FROM h036_physical_releases WHERE session_id=?', (session,)):
        record = json.loads(row['record'])
        target = record.get('target') or {}
        assert record.get('recoveryId') == row['recovery_id'], 'release ID mismatch'
        assert record.get('physicalRelease') is True and record.get('outcome') == 'interrupted_unknown', 'release outcome mismatch'
        for field, column in (('proofSha256', 'proof_sha256'), ('snapshotSha256', 'snapshot_sha256')):
            assert isinstance(record.get(field), str) and re.fullmatch('[0-9a-f]{64}', record[field]) and record[field] == row[column], 'release digest mismatch'
        assert target.get('sessionId') == session and target.get('runId') == row['run_id'], 'release target mismatch'
        for key in ('workspaceId', 'threadId', 'turnId'):
            assert isinstance(target.get(key), str) and target[key], 'release native identity missing'
        request_ids = target.get('requestIds')
        assert isinstance(request_ids, list) and request_ids and all(isinstance(v, str) and v for v in request_ids) and len(set(request_ids)) == len(request_ids), 'release requests invalid'
        prior_engine, prior_run, prior_session = (record.get(k) or {} for k in ('priorOwnership', 'priorRun', 'priorSession'))
        assert (prior_engine.get('session_id'), prior_engine.get('workspace_id'), prior_engine.get('engine_kind'), prior_engine.get('ownership'), prior_engine.get('active_turn_id')) == (session, target['workspaceId'], 'codex', 'uncertain', target['turnId']), 'release prior native ownership mismatch'
        assert (prior_run.get('id'), prior_run.get('session_id'), prior_run.get('workspace_id'), prior_run.get('status')) == (target['runId'], session, target['workspaceId'], 'interrupted'), 'release prior run mismatch'
        assert (prior_session.get('id'), prior_session.get('workspace_id'), prior_session.get('native_session_id')) == (session, target['workspaceId'], target['threadId']), 'release prior session mismatch'
        current = db.execute('SELECT r.status,r.workspace_id,s.native_session_id,e.engine_kind,e.workspace_id AS engine_workspace FROM runs r JOIN sessions s ON s.id=r.session_id JOIN h021_session_engines e ON e.session_id=s.id WHERE r.id=? AND r.session_id=?', (target['runId'], session)).fetchone()
        assert current and (current['status'], current['workspace_id'], current['native_session_id'], current['engine_kind'], current['engine_workspace']) == ('interrupted', target['workspaceId'], target['threadId'], 'codex', target['workspaceId']), 'release current lineage mismatch'
        events = [(v['type'], json.loads(v['data'])) for v in db.execute("SELECT type,data FROM events WHERE session_id=? AND run_id=? AND type IN ('done','progress')", (session, target['runId']))]
        audit = [(t, d) for t, d in events if d.get('recoveryId') == row['recovery_id'] and d.get('outcome') == 'interrupted_unknown' and d.get('physicalRelease') is True and d.get('proofSha256') == row['proof_sha256']]
        assert any(t == 'done' and d.get('runId') == target['runId'] for t, d in audit), 'release done audit missing'
        assert any(t == 'progress' and d.get('kind') == 'cleanup' and d.get('label') == CLEANUP_LABEL for t, d in audit), 'release cleanup audit missing'
        mappings = list(db.execute('SELECT request_id,original_record FROM h036_released_requests WHERE recovery_id=?', (row['recovery_id'],)))
        assert {v['request_id'] for v in mappings} == set(request_ids), 'release exact request set mismatch'
        for mapping in mappings:
            request = db.execute('SELECT session_id,state,record FROM h021_gateway_requests WHERE id=?', (mapping['request_id'],)).fetchone()
            assert request and request['session_id'] == session and request['record'] == mapping['original_record'], 'release original request changed'
            original = json.loads(request['record'])
            assert original.get('id') == mapping['request_id'] and original.get('sessionId') == session and original.get('state') == request['state'] and request['state'] in ('accepted', 'draining', 'uncertain'), 'release request lineage mismatch'
            released[mapping['request_id']] = {'recoveryId': row['recovery_id'], 'disposition': 'physically_released_interrupted_unknown', 'proofSha256': row['proof_sha256']}
        runs.add(target['runId'])
    # An orphan disposition must not hide a pending request or bypass its audit.
    mapped = {v[0] for v in db.execute('SELECT m.request_id FROM h036_released_requests m JOIN h021_gateway_requests q ON q.id=m.request_id WHERE q.session_id=?', (session,))}
    assert mapped == set(released), 'orphan physical release mapping'
    return released, runs

def validate(q):
    assert q.get('exactSource') == SOURCE and q.get('pilotId') == PILOT, 'source/pilot mismatch'
    for key in ('sessionId', 'runId'):
        assert isinstance(q.get(key), str) and re.fullmatch(r'[A-Za-z0-9._-]{1,128}', q[key]), 'invalid ID'

def deployment():
    raw = pathlib.Path(RECEIPT).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RECEIPT_SHA, 'deployment receipt mismatch'
    receipt = json.loads(raw)
    assert receipt['head'] == SOURCE and receipt['release'] == RELEASE
    assert receipt['candidateUnit']['sha256'] == UNIT_SHA
    assert hashlib.sha256(pathlib.Path(UNIT).read_bytes()).hexdigest() == UNIT_SHA, 'unit mismatch'
    state = dict(line.split('=', 1) for line in subprocess.check_output(
        ['systemctl', '--user', 'show', 'ai-harness.service', '-p', 'WorkingDirectory', '-p', 'FragmentPath', '-p', 'ActiveState'],
        timeout=5, text=True).splitlines())
    assert state == {'WorkingDirectory': RELEASE + '/server', 'FragmentPath': UNIT, 'ActiveState': 'active'}, 'active release mismatch'
    for name, digest in BUILD.items():
        assert hashlib.sha256(pathlib.Path(RELEASE + '/server/dist/' + name + '.js').read_bytes()).hexdigest() == digest, 'deployed semantics mismatch'
    return {'exactSource': SOURCE, 'pilotId': PILOT, 'release': RELEASE, 'receiptSha256': RECEIPT_SHA, 'unitSha256': UNIT_SHA, 'semanticBuildHashes': BUILD}

def readback(db, q, binding):
    validate(q)
    session, run = q['sessionId'], q['runId']
    db.row_factory = sqlite3.Row
    db.execute('BEGIN')
    try:
        r = db.execute('select id,session_id,workspace_id,status from runs where id=? and session_id=?', (run, session)).fetchone()
        assert r, 'run missing'
        e = db.execute('select e.engine_kind,e.ownership,e.active_turn_id,s.native_session_id as native_thread_id from h021_session_engines e join sessions s on s.id=e.session_id where e.session_id=?', (session,)).fetchone()
        assert e and e['engine_kind'] in ('codex', 'minimax'), 'engine unknown'
        active = [dict(v) for v in db.execute("select id,status from runs where session_id=? and status not in ('completed','cancelled','failed','interrupted')", (session,))]
        quarantine = db.execute('select reason from quarantined_workspaces where id=?', (r['workspace_id'],)).fetchone()
        released, released_runs = physical_releases(db, session)
        requests = []
        for row in db.execute('select id,state,record from h021_gateway_requests where session_id=?', (session,)):
            v = json.loads(row['record'])
            assert v['id'] == row['id'] and v['sessionId'] == session and v['state'] == row['state'], 'request ownership mismatch'
            receipt = {k: v[k] for k in ('id', 'sessionId', 'state', 'lane', 'updatedAt', 'accounting') if k in v}
            if row['id'] in released:
                receipt['physicalRelease'] = released[row['id']]
            requests.append(receipt)
        pending = [v['id'] for v in requests if v['state'] != 'settled' and v['id'] not in released]
        images = []
        for row in db.execute('select id,data from h003_image_jobs where session_id=?', (session,)):
            j = json.loads(row['data'])['job']
            assert j['id'] == row['id'] and j['sessionId'] == session, 'image ownership mismatch'
            images.append({'id': j['id'], 'state': j['state'], 'errorCode': (j.get('error') or {}).get('code')})
        # Unknown/interrupted image work remains fail closed. Unrelated sessions do not block.
        image_pending = [j['id'] for j in images if j['state'] not in ('completed', 'cancelled', 'failed') or j['errorCode'] in ('image_completion_unknown', 'server_stopped', 'server_restarted')]
        # Global lane quarantine/uncertainty can belong to another chat. Only
        # these owned jobs and their durable ambiguity codes affect this result.
        events = [(v['type'], json.loads(v['data'])) for v in db.execute("select type,data from events where session_id=? and run_id=? and type in ('done','progress')", (session, run))]
        done = any(t == 'done' and d.get('runId') == run for t, d in events)
        cleanup = any(t == 'progress' and d.get('kind') == 'cleanup' and d.get('label') == CLEANUP_LABEL for t, d in events)
        # Source-bound broker completion already waits native delegation settlement;
        # failed/interrupted outcomes require the explicit exact-container cleanup event. Codex idle is
        # persisted only after exact supervisor cleanup + children + gateway drain.
        native = e['ownership'] == 'idle' and e['active_turn_id'] is None and (r['status'] not in ('failed', 'interrupted') or cleanup)
        settled = r['status'] in ('completed', 'cancelled', 'failed', 'interrupted') and done and native and not active and not quarantine and not pending and not image_pending
        return {'sessionId': session, 'runId': run, 'settled': bool(settled),
            'physicallySettledInterruptedUnknown': bool(settled and run in released_runs),
            'completedSuccess': bool(settled and r['status'] == 'completed'), 'evidence': {
            'binding': binding, 'authority': 'source-bound broker/native supervisor/child cleanup, protected offline physical-release audit and durable per-session gateway/image records; no PID-only proof',
            'engine': dict(e), 'runStatus': r['status'], 'doneEvent': done, 'cleanupEvent': cleanup,
            'activeRuns': active, 'quarantined': bool(quarantine), 'unsettledRequests': pending,
            'imagePending': image_pending, 'imageReceipts': images, 'requestReceipts': requests}}
    finally:
        db.rollback()

if __name__ == '__main__':
    try:
        q = json.load(sys.stdin)
        validate(q)
        binding = deployment()
        with sqlite3.connect('file:/home/user/.local/share/ai-harness/harness.sqlite?mode=ro', uri=True) as db:
            result = readback(db, q, binding)
        # Bind both sides of the read-only transaction to unchanged deployment.
        assert deployment() == binding
        print(json.dumps(result))
    except Exception:
        print(json.dumps({'sessionId': locals().get('q', {}).get('sessionId'), 'settled': False, 'evidence': {'error': 'source-bound settlement unconfirmed'}}))
        sys.exit(1)
