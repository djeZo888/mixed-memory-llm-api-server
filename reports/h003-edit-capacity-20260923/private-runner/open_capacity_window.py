"""Reviewed one-time graceful wrapper stop proposal. NEVER called this source turn."""
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
import urllib.request


def main(payload):
    assert payload['root_release'] == 'OPEN_PRIVATE_CAPACITY_WINDOW'
    path = Path('/data/services/image21-runtime-20260923/source/service.py')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == '0edadcb43ec83d369d7bdb66dddc7035962d620475314b0142cb9f047b197586'
    spec = importlib.util.spec_from_file_location('runtime', path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    r = m.Runtime()
    def unit():
        keys = ['MainPID', 'ActiveState', 'SubState', 'Result', 'ExecMainCode', 'ExecMainStatus', 'ExecMainStartTimestamp', 'ControlGroup']
        return dict(line.split('=', 1) for line in m.run(['systemctl', 'show', 'llm-image-api.service',
                    *[x for k in keys for x in ('-p', k)]]).stdout.splitlines())
    def models():
        values = []
        for name in ('llm-image-backend', 'llmctl-qwen38-27b-q0-480000-yarn4-bf16kv', 'llmctl-qwen38-27b-q1-480000-yarn4-bf16kv'):
            d = json.loads(m.run(['docker', 'inspect', name]).stdout)[0]
            values.append([name, d['Id'], d['Image'], d['State']['Pid'], d['State']['StartedAt']])
        return values
    with m.acquire_lease(blocking=False):
        r.guards()
        receipt_path = m.BASE / 'receipts/H003-CAPACITY-WINDOW.json'
        assert not receipt_path.exists(), 'window_already_attempted_no_repeat'
        state = r.state()
        before = r.verify_resident(state)
        api = unit()
        assert api['ActiveState'] == 'active' and int(api['MainPID']) > 0
        old_models = models()
        spec = importlib.util.spec_from_file_location('approved_key', '/usr/local/lib/llm-server/image-api/examples/generate.py')
        keys = importlib.util.module_from_spec(spec); spec.loader.exec_module(keys)
        req = urllib.request.Request('http://127.0.0.1:30006/health/ready', headers={'Authorization': 'Bearer ' + keys.read_key()})
        with urllib.request.urlopen(req, timeout=4) as response:
            ready = json.load(response)
        assert ready == {'ready': True, 'busy': False, 'admitting': True, 'state': 'ready'}
        receipt = {'source_commit': payload['root_reviewed_source_commit'], 'api_before': api,
                   'backend_before': before, 'models_before': old_models, 'clean_stop_proved': False,
                   'private_requests': 0, 'utc': m.now()}
        try:
            # Owner.close drains any request racing the earlier GET. Do not force
            # kill/restart; only clean process exit plus unchanged backend passes.
            m.run(['systemctl', 'stop', 'llm-image-api.service'], timeout=1830)
            after = unit()
            assert after['ActiveState'] == 'inactive' and after['SubState'] == 'dead'
            assert after['MainPID'] == '0' and after['Result'] == 'success'
            assert after['ExecMainCode'] == '1' and after['ExecMainStatus'] == '0'
            assert not Path('/proc/' + api['MainPID']).exists()
            with socket.socket() as sock:
                sock.settimeout(1)
                assert sock.connect_ex(('127.0.0.1', 30006)) != 0
            r.guards()
            backend = r.verify_resident(state)
            assert backend['container_id'] == before['container_id'] and backend['started_at'] == before['started_at']
            assert sorted(row[:2] for row in backend['gpu_processes']) == sorted(row[:2] for row in before['gpu_processes'])
            assert models() == old_models
            receipt.update(api_after=after, backend_after=backend, models_after=old_models,
                           old_api_process_absent=True, loopback_api_listener_absent=True, clean_stop_proved=True)
        except BaseException as error:
            receipt['error_type'] = type(error).__name__
        finally:
            # No automatic restart: final reviewed activation uses the one reload.
            try:
                with r.anchor() as anchor:
                    anchor.atomic_json('receipts/H003-CAPACITY-WINDOW.json', receipt)
            finally:
                print(json.dumps(receipt, indent=2), flush=True)
        return receipt


if __name__ == '__main__':
    main(json.load(sys.stdin))
