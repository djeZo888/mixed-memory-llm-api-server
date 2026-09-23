"""Root-authorized C01-only no-inflight receipt; no signals, recovery or inference."""
import ast
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
import urllib.request

FAILED_SHA = '6ff05a981433d782d3b918338a27f803c243707d892cbbd52119a6c124ae02b5'
AUTHORITY_SHA = 'da2f9bc819c7f68b656643dcbafdcf6e9c719eca09ce5ee2e38a03070148392d'
HELPER_SHA = '2f873367b813a93edbe77cced162fa5ccd26f11fa86aacb48f0412f6979ba6c6'
SOURCE_PINS = {
    '/usr/local/lib/llm-server/image-api/scripts/image_api/app.py': '4cad82ce35d4650c7f3242bd6816769010c6a52510fae1c3c26b8789acdc0d22',
    '/usr/local/lib/llm-server/image-api/scripts/image_api/backend.py': '64a5ceccb247e7c7ed646cc3ae9af89aeffb7aebd862c11604786a2041db9485',
    '/usr/local/lib/llm-server/image-api/scripts/image_api/serve.py': '0d19743ab91ea4f8cafe2bf6d7ddd9d56d2248604da23c711a19f825ba4b6d2e',
}


def process_identity(rows):
    return sorted(tuple(row[:2]) for row in rows)


def main(payload):
    authority = base64.b64decode(payload['root_authority'], validate=True)
    helper = base64.b64decode(payload['original_helper'], validate=True)
    assert hashlib.sha256(authority).hexdigest() == AUTHORITY_SHA
    assert hashlib.sha256(helper).hexdigest() == HELPER_SHA
    path = Path('/data/services/image21-runtime-20260923/source/service.py')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == '0edadcb43ec83d369d7bdb66dddc7035962d620475314b0142cb9f047b197586'
    spec = importlib.util.spec_from_file_location('runtime', path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    r = m.Runtime()
    with m.acquire_lease(blocking=False):
        r.guards()
        target = m.BASE / 'receipts/H003-CAPACITY-RECONCILIATION-C01.json'
        assert not target.exists(), 'no_repeat_reconciliation'
        raw = (m.BASE / 'receipts/H003-CAPACITY-WINDOW.json').read_bytes()
        assert hashlib.sha256(raw).hexdigest() == FAILED_SHA
        failed = json.loads(raw)
        assert failed['clean_stop_proved'] is False and failed['private_requests'] == 0
        assert failed['signal_sent'] == 'SIGTERM_MAIN' and failed['error_type'] == 'AssertionError'
        source_excerpts = {}
        for name, digest in SOURCE_PINS.items():
            source = Path(name).read_text()
            assert hashlib.sha256(source.encode()).hexdigest() == digest
            source_excerpts[name] = [ast.get_source_segment(source, node) for node in ast.walk(ast.parse(source))
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in ('status', 'claim', 'close', 'ready')]
        fields = ['Id', 'MainPID', 'ActiveState', 'FreezerState', 'ExecMainStartTimestamp', 'ControlGroup', 'Result', 'ExecMainStatus', 'ExecMainCode', 'SubState', 'ExecMainExitTimestamp']
        unit = dict(line.split('=', 1) for line in m.run(['systemctl', 'show', 'llm-image-api.service',
            *[x for k in fields for x in ('-p', k)]]).stdout.splitlines())
        assert all(unit[k] == v for k, v in {'MainPID': '0', 'ActiveState': 'inactive', 'SubState': 'dead',
            'Result': 'success', 'ExecMainCode': '2', 'ExecMainStatus': '15'}.items())
        assert unit['ExecMainStartTimestamp'] == failed['api_before']['ExecMainStartTimestamp']
        assert unit['ExecMainExitTimestamp'] == 'Wed 2026-09-23 13:05:46 UTC'
        assert not Path('/proc/' + failed['api_before']['MainPID']).exists()
        with socket.socket() as sock:
            sock.settimeout(1)
            assert sock.connect_ex(('127.0.0.1', 30006)) != 0
        state = r.state()
        assert state['warm'] and state['phase'] == 'warm'
        for case in ('C01', 'C02', 'C03', 'C04'):
            assert not (m.BASE / 'work/evidence' / state['run_id'] / ('H003-CAPACITY-' + case)).exists()
            assert not (m.BASE / 'receipts' / ('H003-CAPACITY-' + case + '-receipt.json')).exists()
        backend = r.verify_resident(state)
        assert backend['container_id'] == failed['backend_before']['container_id']
        assert backend['started_at'] == failed['backend_before']['started_at']
        assert process_identity(backend['gpu_processes']) == process_identity(failed['backend_before']['gpu_processes'])
        models = []
        for name, *_ in failed['models_before']:
            d = json.loads(m.run(['docker', 'inspect', name]).stdout)[0]
            assert d['State']['Running'] and not d['State']['OOMKilled']
            models.append([name, d['Id'], d['Image'], d['State']['Pid'], d['State']['StartedAt']])
        assert models == failed['models_before']
        spec = importlib.util.spec_from_file_location('approved_key', '/usr/local/lib/llm-server/image-api/examples/generate.py')
        keys = importlib.util.module_from_spec(spec); spec.loader.exec_module(keys)
        def get(port, route):
            request = urllib.request.Request(f'http://127.0.0.1:{port}{route}', headers={'Authorization': 'Bearer ' + keys.read_key()})
            with urllib.request.urlopen(request, timeout=4) as response:
                raw = response.read(65536)
                assert response.status == 200
                return json.loads(raw) if raw else None
        health = {'image': get(30007, '/health'), 'text': {str(port): {'health': get(port, '/health'), 'models': get(port, '/v1/models')} for port in (30002, 30004)}}
        assert health['image'] == {'status': 'ok'}
        assert all(value['models']['data'][0]['max_model_len'] == 480000 for value in health['text'].values())
        receipt = {'evidence_type': 'H003_C01_COORDINATED_NO_INFLIGHT_V1', 'case': 'C01', 'utc': m.now(),
            'reconciliation_source_commit': payload['reconciliation_source_commit'], 'source_commit': failed['source_commit'],
            'clean_stop_proved': False, 'asgi_cleanup': 'UNPROVEN', 'original_failed_receipt_sha256': FAILED_SHA,
            'original_failed_receipt': failed, 'authority_sha256': AUTHORITY_SHA, 'root_authority': authority.decode(),
            'pre_stop_helper_sha256': HELPER_SHA,
            'pre_stop_ready_proof': 'Exact helper asserts ready=true,busy=false,admitting=true,state=ready before receipt construction and SIGTERM. Existing signal_sent proves that assertion was passed.',
            'pre_stop_helper_excerpt': '\n'.join(helper.decode().splitlines()[37:52]),
            'installed_source_sha256': SOURCE_PINS, 'source_excerpts': source_excerpts,
            'coordinated_no_call_interval': True, 'coordination_from_utc': '2026-09-23T13:05:00Z',
            'coordination_through': 'This receipt and C01 dispatch under the retained root sole-caller window',
            'no_inflight_native_operation_proved': True, 'private_requests': 0,
            'old_api_process_absent': True, 'loopback_api_listener_absent': True,
            'canonical_lease': True, 'guards': 'PASS', 'api_after': unit, 'backend_after': backend,
            'models_after': models, 'health': health,
            'limitations': ['Task-only controlled no-call coordination is an explicit root attestation, not universal traffic instrumentation.',
                'Health proves availability, not scheduler idleness. No-inflight evidence is the pre-SIGTERM owner=None assertion plus coordinated no-call interval and unchanged ownership.',
                'ASGI/HTTP-client cleanup remains unproven; original failed shutdown receipt is unchanged.',
                'Does not authorize production admission, later cases, generic killed exits, restart or warmup.']}
        r.guards()
        with r.anchor() as anchor:
            anchor.atomic_json('receipts/H003-CAPACITY-RECONCILIATION-C01.json', receipt)
        assert hashlib.sha256((m.BASE / 'receipts/H003-CAPACITY-WINDOW.json').read_bytes()).hexdigest() == FAILED_SHA
        print(json.dumps(receipt, indent=2), flush=True)


if __name__ == '__main__':
    main(json.load(sys.stdin))
