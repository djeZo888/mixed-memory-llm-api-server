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
        e = db.execute('select engine_kind,ownership,active_turn_id,native_thread_id from h021_session_engines where session_id=?', (session,)).fetchone()
        assert e and e['engine_kind'] in ('codex', 'minimax'), 'engine unknown'
        active = [dict(v) for v in db.execute("select id,status from runs where session_id=? and status not in ('completed','cancelled','failed','interrupted')", (session,))]
        quarantine = db.execute('select reason from quarantined_workspaces where id=?', (r['workspace_id'],)).fetchone()
        requests = []
        for row in db.execute('select id,state,record from h021_gateway_requests where session_id=?', (session,)):
            v = json.loads(row['record'])
            assert v['id'] == row['id'] and v['sessionId'] == session and v['state'] == row['state'], 'request ownership mismatch'
            requests.append({k: v[k] for k in ('id', 'sessionId', 'state', 'lane', 'updatedAt', 'accounting') if k in v})
        pending = [v['id'] for v in requests if v['state'] != 'settled']
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
        cleanup = any(t == 'progress' and d.get('kind') == 'cleanup' and d.get('label') == 'Owned engine container cleanup confirmed; interrupted work was not replayed' for t, d in events)
        # Source-bound broker completion already waits native delegation settlement;
        # failure requires its explicit exact-container cleanup event. Codex idle is
        # persisted only after exact supervisor cleanup + children + gateway drain.
        native = e['ownership'] == 'idle' and e['active_turn_id'] is None and (r['status'] != 'failed' or cleanup)
        settled = r['status'] in ('completed', 'cancelled', 'failed') and done and native and not active and not quarantine and not pending and not image_pending
        return {'sessionId': session, 'runId': run, 'settled': bool(settled), 'evidence': {
            'binding': binding, 'authority': 'source-bound broker/native supervisor/child cleanup and durable per-session gateway/image records; no PID-only proof',
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
