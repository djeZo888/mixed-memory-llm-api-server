#!/usr/bin/env python3
"""Build deterministic local source closure; never contacts or deploys to a host."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / 'scripts/h019'
BUILD = '/data/build/H019-20260928'
SERVICE = '/data/services/mimo-h016-20260927'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    manifest = json.loads((ROOT / 'scripts/h018/manifest.candidate.json').read_text())
    sources = manifest['source_sha256']
    sources[SERVICE + '/source/owner.py'] = sha(ROOT / 'scripts/runtime/mimo/owner.py')
    for name in sources:
        if name.endswith('/lifecycle/hardware_policy.py'):
            sources[name] = sha(ROOT / 'scripts/lifecycle/hardware_policy.py')
    (HERE / 'manifest.candidate.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    files = {
        SERVICE + '/source/owner.py': 'scripts/runtime/mimo/owner.py',
        SERVICE + '/manifest.json': 'scripts/h019/manifest.candidate.json',
        '/usr/local/lib/llm-server/control-api/scripts/lifecycle/hardware_policy.py': 'scripts/lifecycle/hardware_policy.py',
        '/usr/local/lib/llm-server/node-api/scripts/lifecycle/hardware_policy.py': 'scripts/lifecycle/hardware_policy.py',
        BUILD + '/worker1-short/short.py': 'scripts/h019/short.py',
        BUILD + '/worker1-final950k/final.py': 'scripts/h019/final.py',
    }
    for name in ('dispatch.py', 'prepare_authority.py', 'observe.py', 'deploy.py'):
        files[BUILD + '/' + name] = 'scripts/h019/' + name
    for name in ('h019-short.service', 'h019-final950k.service'):
        files['/etc/systemd/system/' + name] = 'scripts/h019/' + name
    external = json.loads((HERE / 'historical-dependencies.json').read_text())
    closure = {**sources, **external, **{dest: sha(ROOT / src) for dest, src in files.items()}}
    (HERE / 'client-closure.json').write_text(json.dumps(closure, indent=2, sort_keys=True) + '\n')
    files[BUILD + '/client-closure.json'] = 'scripts/h019/client-closure.json'
    deployment = {dest: {'source': src, 'sha256': sha(ROOT / src)} for dest, src in files.items()}
    (HERE / 'deployment-files.json').write_text(json.dumps(deployment, indent=2, sort_keys=True) + '\n')
    return deployment

if __name__ == '__main__':
    print(json.dumps({'status': 'LOCAL_PACKAGE_ONLY', 'targets': len(build())}))
