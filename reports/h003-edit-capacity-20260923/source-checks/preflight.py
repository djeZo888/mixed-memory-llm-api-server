"""Read-only ai-vm receipt; execute over stdin, never stage or request inference."""
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import urllib.request

path = pathlib.Path('/data/services/image21-runtime-20260923/source/service.py')
assert hashlib.sha256(path.read_bytes()).hexdigest() == '0edadcb43ec83d369d7bdb66dddc7035962d620475314b0142cb9f047b197586'
spec = importlib.util.spec_from_file_location('runtime', path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
r = m.Runtime()
spec = importlib.util.spec_from_file_location('approved_loader', '/usr/local/lib/llm-server/image-api/examples/generate.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
key = h.read_key()

def get(port, route):
    request = urllib.request.Request(f'http://127.0.0.1:{port}{route}', headers={'Authorization': 'Bearer ' + key})
    with urllib.request.urlopen(request, timeout=4) as response:
        raw = response.read(65536)
        return {'status': response.status, 'body': json.loads(raw) if raw else None}

with m.acquire_lease(blocking=False):
    r.guards()
    state = r.state()
    resident = r.verify_resident(state)
    containers = []
    for cid in m.run(['docker', 'ps', '-q', '--no-trunc']).stdout.split():
        d = json.loads(m.run(['docker', 'inspect', cid]).stdout)[0]
        pid = d['State']['Pid']
        cg = pathlib.Path('/sys/fs/cgroup') / pathlib.Path(f'/proc/{pid}/cgroup').read_text().strip().split('::', 1)[1].lstrip('/')
        counters = {}
        for name in ('memory.current', 'memory.max', 'memory.swap.current', 'memory.events', 'memory.swap.events'):
            counters[name] = (cg / name).read_text().strip() if (cg / name).exists() else None
        containers.append({'id': cid, 'name': d['Name'], 'image': d['Image'], 'pid': pid,
                           'started': d['State']['StartedAt'], 'cgroup': str(cg), 'counters': counters})
    result = {'utc': m.now(), 'guards': 'pass', 'canonical_lease': 'acquired read-only',
              'runtime_config_sha256': hashlib.sha256((m.BASE / 'config.json').read_bytes()).hexdigest(),
              'phase': state['phase'], 'warm': state['warm'], 'run_id': state['run_id'],
              'resident': resident, 'containers': containers, 'tmp': r.tmp_snapshot(state['run_id']),
              'ready': get(30006, '/health/ready'), 'capabilities': get(30006, '/v1/image-capabilities'),
              'text': {str(port): {'health': get(port, '/health'), 'models': get(port, '/v1/models')} for port in (30002, 30004)},
              'units': m.run(['systemctl', 'show', 'llm-image-api.service', 'llm-image-backend.service', '-p', 'Id', '-p', 'MainPID', '-p', 'ExecMainStartTimestamp', '-p', 'ActiveState', '-p', 'UnitFileState', '-p', 'FreezerState', '-p', 'ControlGroup']).stdout,
              'devices': m.run(['nvidia-smi', '--query-gpu=index,uuid,memory.total,memory.free', '--format=csv,noheader,nounits']).stdout,
              'gpu_processes': m.run(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid,used_memory', '--format=csv,noheader,nounits']).stdout,
              'swap': {line.split()[0]: int(line.split()[1]) for line in pathlib.Path('/proc/vmstat').read_text().splitlines() if line.split()[0] in ('pswpin', 'pswpout')},
              'host_memory': {line.split(':')[0]: line.split(':')[1].strip() for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if line.split(':')[0] in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree')},
              'inference_requests': 0, 'mutations': 0}
    print(json.dumps(result, indent=2))
