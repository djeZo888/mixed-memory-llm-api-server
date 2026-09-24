"""Offline fixture checks only: substitutes every host/runtime/lifecycle operation."""
import argparse
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / 'reports/h003-image-api-activate-20260923/deployment-tools/install.py'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True, help='private result directory outside Git')
OUT = parser.parse_args().output.resolve()
assert ROOT not in OUT.parents and OUT != ROOT, 'result must remain outside Git'
OUT.mkdir(mode=0o700, parents=True, exist_ok=True)


def load():
    spec = importlib.util.spec_from_file_location('transaction', HELPER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


m = load()
payload = {'source_commit': m.COMMIT,
           'source': {name: (ROOT / 'scripts/image_api' / name).read_text() for name in m.EXPECTED},
           'qualification': (ROOT / 'reports/image21-fhd-20260923/qualification.json').read_text()}
payload['manifest_sha256'] = m.sha(payload['qualification'].encode())
m.check_payload(payload)
checks = ['known six-generation fixture passes; NOT final approved manifest']


def rejected(name, value):
    try:
        m.check_payload(value)
    except Exception:
        checks.append(name + ': rejected')
    else:
        raise AssertionError(name + ' accepted')


p = copy.deepcopy(payload); p['source_commit'] = 'f6e69d'; rejected('wrong source commit', p)
p = copy.deepcopy(payload); p['source']['app.py'] += '\n'; rejected('wrong reviewed app bytes', p)
p = copy.deepcopy(payload); p['manifest_sha256'] = '0' * 64; rejected('wrong manifest digest', p)
for name, mutate in [
    ('changed generation evidence', lambda q: q['profiles'][0].update(evidence_sha256='0' * 64)),
    ('invented generation record', lambda q: q['profiles'].append({**q['profiles'][0], 'size': '512x512', 'native_size': '512x512'})),
    ('transparent edit', lambda q: q['profiles'].append({**q['profiles'][0], 'operation': 'edit', 'references': 1, 'transparent': True})),
    ('FHD two-reference edit', lambda q: q['profiles'].append({**q['profiles'][-1], 'operation': 'edit', 'references': 2})),
    ('boolean crop', lambda q: q['profiles'].append({**q['profiles'][0], 'operation': 'edit', 'references': 1, 'crop_bottom': False})),
]:
    p = copy.deepcopy(payload); q = json.loads(p['qualification']); mutate(q)
    p['qualification'] = json.dumps(q); p['manifest_sha256'] = m.sha(p['qualification'].encode())
    rejected(name, p)
q = json.loads(payload['qualification'])
q['profiles'].append({**q['profiles'][0], 'operation': 'edit', 'references': 1})
p = copy.deepcopy(payload); p['qualification'] = json.dumps(q)
p['manifest_sha256'] = m.sha(p['qualification'].encode()); m.check_payload(p)
checks.append('schema-valid edit fixture passes without edit-count hardcoding; no measured/approval claim')
run = subprocess.run([sys.executable, '-B', str(HELPER), '--check-payload'], input=json.dumps(payload),
                     text=True, capture_output=True)
assert run.returncode == 0, run.stderr
assert json.loads(run.stdout)['status'] == 'PAYLOAD_INTEGRITY_ONLY_NO_ACTIVATION_AUTHORITY'
assert 'service' not in sys.modules
checks.append('offline CLI passes; canonical host owner never imported')

old_source = {name: subprocess.check_output(['git', 'show',
              '36c7c2d2ee8d9ed59e9310e708eb640c5aecad5e:scripts/image_api/' + name], cwd=ROOT)
              for name in m.EXPECTED}
assert {name: m.sha(raw) for name, raw in old_source.items()} == m.PREVIOUS
faults = []


class Anchor:
    def __init__(self, path, _guard): self.path = Path(path)
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def mkdir(self, path, mode): (self.path / path).mkdir(mode=mode)
    @contextlib.contextmanager
    def open(self, path, _flags):
        with (self.path / path).open('xb') as stream:
            yield SimpleNamespace(write=stream.write, fsync=stream.flush)
    def atomic_json(self, path, value):
        (self.path / path).write_text(json.dumps(value))


for fault in ('replace_succeeded_then_readback_failed', 'final_guard_failed_after_receipt'):
    mod = load()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        mod.SOURCE = root / 'source'; mod.SOURCE.mkdir()
        for name, raw in old_source.items(): (mod.SOURCE / name).write_bytes(raw)
        mod.CONFIG = root / 'config'; mod.CONFIG.write_text(payload['qualification'])
        mod.KEY = root / 'key'; mod.KEY.write_text('fixture-no-real-secret')
        mod.RUNTIME = root / 'runtime'; mod.RUNTIME.mkdir(); (mod.RUNTIME / 'config.json').write_text('{}')
        services = root / 'services'; services.mkdir(); mod.BASE = services / 'transaction'
        unit_path = root / 'unit'; unit_path.write_text('fixture unit')
        mod.TARGETS = (mod.SOURCE / 'app.py', mod.SOURCE / 'protocol.py', mod.CONFIG)
        original = {str(path): path.read_bytes() for path in mod.TARGETS}
        state = {'container': {'id': 'fixture-model'}, 'run_id': 'fixture-run'}
        binding = SimpleNamespace(path=lambda name: str(services),
                                  mounted_guard=lambda storage: contextlib.nullcontext(None))
        guards = [0]
        def guard():
            guards[0] += 1
            # install order: initial, pre-mutation, post-mutation, final receipt.
            if fault == 'final_guard_failed_after_receipt' and guards[0] == 4:
                raise RuntimeError('fixture guard failure after receipt')
        runtime = SimpleNamespace(binding=binding, guards=guard, state=lambda: state,
                                  verify_resident=lambda state: None, check_network=lambda state: None)
        service = SimpleNamespace(acquire_lease=lambda **kwargs: contextlib.nullcontext(None),
                                  protected_file=lambda path, **kwargs: Path(path).read_bytes(),
                                  storage_io=SimpleNamespace(AnchoredRoot=Anchor))
        mod.host_tools = lambda: (service, runtime)
        mod.stopped = lambda: {'FragmentPath': str(unit_path)}
        mod.texts = lambda: ['fixture-text-identities']
        mod.command = lambda args: ''
        writes = []
        def atomic(path, raw, meta, protected):
            path.write_bytes(raw)
            writes.append(str(path))
            if fault == 'replace_succeeded_then_readback_failed' and len(writes) == 1:
                raise RuntimeError('fixture readback after replacement')
        mod.atomic = atomic
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stderr(stderr): mod.install(payload)
        except RuntimeError:
            pass
        else:
            raise AssertionError('injected failure accepted')
        assert all(path.read_bytes() == original[str(path)] for path in mod.TARGETS)
        result = json.loads((mod.BASE / 'compensation.json').read_text())
        assert result['status'] == 'COMPENSATED_API_STOPPED'
        if fault == 'final_guard_failed_after_receipt':
            assert json.loads((mod.BASE / 'installed.json').read_text())['status'].startswith('PROVISIONAL_')
        faults.append({'fault': fault, 'exact_three_original_bytes_restored': True,
                       'durable_compensation': result, 'stderr': stderr.getvalue().strip()})

result = {'helper_sha256': m.sha(HELPER.read_bytes()), 'checks': checks, 'fault_checks': faults,
          'host_contact': False, 'host_owner_imported': False, 'inference': 0,
          'scope': 'Payload parser plus simulated host transaction; no real protected FS/systemd/VM validation'}
(OUT / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
