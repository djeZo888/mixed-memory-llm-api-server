"""Source-only private runner candidate. Root review/release required before use.

Executed via stdin on ai-vm only by Worker1. No automatic retries or recovery.
Payload binds one predeclared case and reviewed source/input hashes.
"""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import urllib.request

SERVICE_SHA = '0edadcb43ec83d369d7bdb66dddc7035962d620475314b0142cb9f047b197586'


def identity(rows):
    return sorted(tuple(row[:2]) for row in rows)


def admission_closed(unit):
    return unit.get('ActiveState') == 'inactive' and unit.get('MainPID') == '0' and unit.get('Result') == 'success' and unit.get('ExecMainStatus') == '0'


def settle_private_case(receipt, check):
    try:
        checks = check()
        receipt['settlement_checks'] = checks
        receipt['native_operation_settled'] = receipt.get('exit_code') == 0 and bool(checks) and all(checks.values())
    except BaseException as error:
        receipt['settlement_error_type'] = type(error).__name__
        receipt['native_operation_settled'] = False
    return receipt['native_operation_settled']


def memory_pass(receipt):
    return bool(receipt.get('native_operation_settled') and not receipt.get('violations') and
        receipt.get('checkpoint_api_stopped_backend_healthy') and receipt.get('telemetry_durable_settled') and
        not any(k in receipt for k in ('runner_error_type', 'settlement_error_type', 'telemetry_error_type', 'final_observation_error_type', 'evidence_error_type')))


def probe_command(container, path):
    return ['docker', 'exec', container, '/usr/bin/timeout', '--signal=TERM', '--kill-after=5s',
            '840s', '/opt/image-venv/bin/python', '-I', '-B', path]


def counters(path):
    return {k: int(v) for k, v in (line.split() for line in Path(path).read_text().splitlines())}


def sample(cgroups):
    def query(selector):
        result = subprocess.run(['nvidia-smi', selector, '--format=csv,noheader,nounits'],
                                capture_output=True, text=True, check=True, timeout=3)
        return [[part.strip() for part in line.split(',')] for line in result.stdout.splitlines()]
    mem = {line.split(':')[0]: int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    vm = counters('/proc/vmstat')
    return {'monotonic': time.monotonic(), 'utc_epoch': time.time(),
            'devices': query('--query-gpu=uuid,memory.total,memory.free'),
            'processes': query('--query-compute-apps=gpu_uuid,pid,used_memory'),
            'host_available': mem['MemAvailable'], 'host_total': mem['MemTotal'],
            'swap': {k: vm[k] for k in ('pswpin', 'pswpout')},
            'cgroups': {name: {'memory.current': int((path / 'memory.current').read_text()),
                              'memory.max': (path / 'memory.max').read_text().strip(),
                              'memory.swap.current': int((path / 'memory.swap.current').read_text()),
                              'memory.events': counters(path / 'memory.events'),
                              'memory.swap.events': counters(path / 'memory.swap.events')}
                       for name, path in cgroups.items()}}


def violations(current, first):
    problems = []
    if len(current['devices']) != 3 or any(float(free) * 20 < float(total) for _, total, free in current['devices']):
        problems.append('device_reserve')
    if current['host_available'] * 100 < current['host_total'] * 15:
        problems.append('host_reserve')
    if current['swap'] != first['swap']:
        problems.append('new_global_swap_activity')
    if identity(current['processes']) != identity(first['processes']):
        problems.append('gpu_process_identity_changed')
    for name, cg in current['cgroups'].items():
        old = first['cgroups'][name]
        if cg['memory.swap.current'] != old['memory.swap.current']:
            problems.append(name + ':swap_changed')
        if cg['memory.events'] != old['memory.events'] or cg['memory.swap.events'] != old['memory.swap.events']:
            problems.append(name + ':memory_events_changed')
    return problems


def main(payload):
    case = payload['case']
    assert case['id'] in ('C01', 'C02', 'C03', 'C04')
    assert payload['root_reviewed_source_commit'] == case['source_candidate']
    assert payload['coordinated_call_release'] == case['id']
    assert payload['sole_request_owner_confirmed'] is True
    assert case['state'] == 'PREDECLARED_NOT_DISPATCHED'
    assert len(case['references']) == (2 if case['id'] == 'C04' else 1)
    if case['id'] != 'C01':
        assert payload['headroom_forecast']['minimum_ada_free_fraction'] >= .05
        assert payload['headroom_forecast']['measured_predecessor'] == ('C02' if case['id'] == 'C03' else 'C01')
    path = Path('/data/services/image21-runtime-20260923/source/service.py')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == SERVICE_SHA
    spec = importlib.util.spec_from_file_location('runtime', path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    r = m.Runtime()
    def unit():
        fields = ['Id', 'MainPID', 'ActiveState', 'FreezerState', 'ExecMainStartTimestamp', 'ControlGroup', 'Result', 'ExecMainStatus']
        return dict(line.split('=', 1) for line in m.run(['systemctl', 'show', 'llm-image-api.service',
                    *[x for field in fields for x in ('-p', field)]]).stdout.splitlines())
    def model_identities():
        names = ['llm-image-backend', 'llmctl-qwen38-27b-q0-480000-yarn4-bf16kv', 'llmctl-qwen38-27b-q1-480000-yarn4-bf16kv']
        result = []
        for name in names:
            d = json.loads(m.run(['docker', 'inspect', name]).stdout)[0]
            assert d['State']['Running'] and not d['State']['OOMKilled']
            result.append((name, d['Id'], d['Image'], d['State']['Pid'], d['State']['StartedAt']))
        return result
    with m.acquire_lease(blocking=False):
        r.guards()
        state = r.state()
        before = r.verify_resident(state)
        original_unit = unit()
        assert admission_closed(original_unit)
        window_raw = (m.BASE / 'receipts/H003-CAPACITY-WINDOW.json').read_bytes()
        assert hashlib.sha256(window_raw).hexdigest() == payload['window_receipt_sha256']
        window = json.loads(window_raw)
        assert window['clean_stop_proved'] is True
        assert before['container_id'] == window['backend_after']['container_id']
        assert identity(before['gpu_processes']) == identity(window['backend_after']['gpu_processes'])
        original_models = model_identities()
        assert [list(row) for row in original_models] == window['models_after']
        cgroups = {}
        for name, cid, image, pid, started in original_models:
            rel = Path(f'/proc/{pid}/cgroup').read_text().strip().split('::', 1)[1]
            cgroups[name] = Path('/sys/fs/cgroup') / rel.lstrip('/')
        first = sample(cgroups)
        assert not violations(first, first)
        name = 'H003-CAPACITY-' + case['id']
        case = {**case, 'run_id': state['run_id']}
        files = dict(payload['files'])
        required = {'probe.py', 'candidate_protocol.py', 'candidate_codec.py', *[f'input-{i + 1}.png' for i in range(len(case['references']))]}
        assert set(files) == required
        for filename, item in files.items():
            raw = base64.b64decode(item['data'], validate=True)
            assert len(raw) <= 32 * 1024 * 1024 and hashlib.sha256(raw).hexdigest() == item['sha256']
        files['case.json'] = {'data': base64.b64encode(json.dumps(case).encode()).decode()}
        codec_source = base64.b64decode(files['candidate_codec.py']['data']).decode()
        codec_input = {'case': case, 'protocol': files['candidate_protocol.py'],
                       'originals': [files[f'input-{i + 1}.png'] for i in range(len(case['references']))]}
        def codec(action, response=None):
            data = {**codec_input, 'action': action}
            if response is not None:
                data['response'] = base64.b64encode(response).decode()
            result = subprocess.run(['/data/services/image-api/venv/bin/python', '-I', '-B', '-c', codec_source],
                                    input=json.dumps(data), capture_output=True, text=True, check=True, timeout=30)
            return json.loads(result.stdout)
        stage = '''import base64,importlib.util,json,os,sys
spec=importlib.util.spec_from_file_location('owned','/runtime/native_request.py');n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n)
p=json.load(sys.stdin);fd=n.open_run_directory(p['run_id']);os.mkdir(p['name'],0o700,dir_fd=fd)
child=os.open(p['name'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
for name,item in p['files'].items():n.write_exclusive(child,name,base64.b64decode(item['data'],validate=True))
os.fsync(child);os.close(child);os.fsync(fd);os.close(fd)
'''
        receipt = {'case': case['id'], 'source_commit': case['source_candidate'], 'before': before,
                   'api_before': original_unit, 'models_before': original_models, 'sample_before': first,
                   'dispatches': 0, 'api_intentionally_stopped': True, 'native_operation_settled': False, 'violations': []}
        receipt['headroom_forecast'] = payload.get('headroom_forecast')
        stop = threading.Event()
        sampler = None
        probe_path = '/work/evidence/' + state['run_id'] + '/' + name + '/probe.py'
        host_case = m.BASE / 'work/evidence' / state['run_id'] / name
        try:
            prepared = codec('prepare')  # Existing adapter dependencies, wrapper stays stopped.
            receipt['preparation_pillow'] = prepared['pillow']
            for i, item in enumerate(prepared['working']):
                files[f'input-{i + 1}.png'] = item
            files['prepared.json'] = {'data': base64.b64encode(json.dumps({
                'run_id': state['run_id'], 'native': prepared['native'],
                'working_sha256': [x['sha256'] for x in prepared['working']]}).encode()).decode()}
            with r.anchor() as anchor:
                subprocess.run(['docker', 'exec', '-i', state['container']['id'], '/opt/image-venv/bin/python', '-I', '-B', '-c', stage],
                    input=json.dumps({'run_id': state['run_id'], 'name': name, 'files': files}), text=True, capture_output=True, check=True, timeout=30)
                anchor.check()
            receipt['staging_complete'] = True
            assert unit() == original_unit and admission_closed(unit())
            r.guards()
            with r.anchor() as anchor:
                with anchor.open('receipts/' + name + '-telemetry.jsonl', os.O_WRONLY | os.O_CREAT | os.O_EXCL) as output:
                    def monitor():
                        try:
                            while not stop.is_set():
                                current = sample(cgroups)
                                receipt['violations'] = sorted(set(receipt['violations'] + violations(current, first)))
                                output.write((json.dumps(current) + '\n').encode())
                                receipt['last_sample'] = current
                                stop.wait(.25)
                        except BaseException as error:
                            receipt['telemetry_error_type'] = type(error).__name__
                    sampler = threading.Thread(target=monitor, daemon=True)
                    sampler.start()
                    # A fresh successful sample must precede dispatch.
                    deadline = time.monotonic() + 10
                    while 'last_sample' not in receipt and sampler.is_alive() and time.monotonic() < deadline:
                        time.sleep(.05)
                    assert 'last_sample' in receipt and not receipt['violations'] and 'telemetry_error_type' not in receipt
                    receipt['dispatches'] = 1
                    try:
                        proc = subprocess.run(probe_command(state['container']['id'], probe_path),
                                              capture_output=True, text=True, timeout=855)
                        receipt['exit_code'] = proc.returncode
                        # Do not copy payloads or native errors into Git/report streams.
                        receipt['probe_stderr_present'] = bool(proc.stderr)
                        if proc.returncode == 0:
                            delivered = codec('deliver', (host_case / 'native-response.json').read_bytes())
                            raw = base64.b64decode(delivered['delivered'], validate=True)
                            receipt['delivered_sha256'] = hashlib.sha256(raw).hexdigest()
                            receipt['delivered_seed'] = delivered['seed']
                            save_delivery = '''import base64,importlib.util,json,os,sys
spec=importlib.util.spec_from_file_location('owned','/runtime/native_request.py');n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n)
p=json.load(sys.stdin);fd=n.open_run_directory(p['run_id']);child=os.open(p['name'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
n.write_exclusive(child,'delivered.png',base64.b64decode(p['data'],validate=True));os.fsync(child);os.close(child);os.close(fd)
'''
                            subprocess.run(['docker', 'exec', '-i', state['container']['id'], '/opt/image-venv/bin/python', '-I', '-B', '-c', save_delivery],
                                input=json.dumps({'run_id': state['run_id'], 'name': name, 'data': delivered['delivered']}),
                                capture_output=True, text=True, check=True, timeout=30)
                            receipt['adapter_delivery_validated'] = True
                    finally:
                        # Keep sampling until owned native settlement is checked; wrapper stays stopped.
                        def check():
                            r.guards()
                            after = r.verify_resident(state)
                            status = unit()
                            top = m.run(['docker', 'top', state['container']['id'], '-eo', 'pid,args']).stdout
                            result = json.loads((host_case / 'probe-result.json').read_text()) if (host_case / 'probe-result.json').is_file() else {}
                            receipt.update(after=after, probe_result=result)
                            stop.set()
                            sampler.join(timeout=8)
                            assert not sampler.is_alive(), 'telemetry_not_settled'
                            output.fsync()
                            anchor.check()
                            receipt['telemetry_durable_settled'] = True
                            final_sample = sample(cgroups)
                            receipt['violations'] = sorted(set(receipt['violations'] + violations(final_sample, first)))
                            receipt['settlement_sample'] = final_sample
                            return {'decoded_success': receipt.get('adapter_delivery_validated') is True and result.get('http_status') == 200,
                                    'owned_probe_absent': not any(probe_path in line for line in top.splitlines()[1:]),
                                    'same_backend_contexts': identity(after['gpu_processes']) == identity(before['gpu_processes']),
                                    'same_models': model_identities() == original_models,
                                    'api_remains_stopped': status == original_unit and admission_closed(status),
                                    'fresh_guards_and_reserve': True,
                                    'telemetry_complete': receipt['telemetry_durable_settled'] and 'telemetry_error_type' not in receipt}
                        settle_private_case(receipt, check)
                        stop.set()
                        sampler.join(timeout=8)
                        assert not sampler.is_alive(), 'telemetry_not_settled'
                        output.fsync()
                anchor.check()
        except BaseException as error:
            receipt['runner_error_type'] = type(error).__name__
        finally:
            stop.set()
            if sampler is not None:
                sampler.join(timeout=8)
            # No per-case API start. A killed HTTP client is never native settlement.
            try:
                receipt['api_after'] = unit()
                r.guards()
                receipt['backend_final'] = r.verify_resident(state)
                receipt['checkpoint_api_stopped_backend_healthy'] = (receipt['api_after'] == original_unit and admission_closed(receipt['api_after']) and model_identities() == original_models)
                receipt['sample_after'] = sample(cgroups)
                receipt['swap_delta'] = {k: receipt['sample_after']['swap'][k] - first['swap'][k] for k in first['swap']}
                receipt['violations'] = sorted(set(receipt['violations'] + violations(receipt['sample_after'], first)))
            except BaseException as error:
                receipt['final_observation_error_type'] = type(error).__name__
            receipt['qualification_memory_pass'] = memory_pass(receipt)
            receipt['accepted_model_executions'] = 1 if receipt.get('probe_result', {}).get('http_status') == 200 else None
            receipt['budget_slot_reserved_on_ambiguity'] = bool(receipt['dispatches'] and receipt['accepted_model_executions'] is None)
            # A reserve/event failure stops the ladder even if the request safely settled.
            try:
                with r.anchor() as anchor:
                    anchor.atomic_json('receipts/' + name + '-receipt.json', receipt)
            except BaseException as error:
                receipt['evidence_error_type'] = type(error).__name__
                receipt['qualification_memory_pass'] = False
            finally:
                print(json.dumps(receipt, indent=2), flush=True)
        return receipt


if __name__ == '__main__':
    main(json.load(sys.stdin))
