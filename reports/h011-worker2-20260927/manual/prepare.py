#!/usr/bin/env python3
"""Materialize an OFFLINE source candidate; no deployment, network or inference.

Every baseline byte is pinned. Changes are exact, single-site edits into a NEW
output directory; production source and manifests are never written. The output
is a review candidate; all live operations remain unverified until Worker1 checks
the exact staged manifest and current protected owner state.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
from build_request_driver import build as build_driver

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RUNTIME = REPO / 'scripts/runtime/flash'
FIXTURE = REPO / 'reports/h010-flash64k-20260927/driver/fixture_native.py'

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('exact_source_edit_mismatch')
    return text.replace(old, new, 1)

def sources():
    pins = json.loads((HERE / 'baseline-sha256.json').read_text())
    base = {}
    for name, expected in pins.items():
        path = FIXTURE if name == 'fixture_native.py' else (FIXTURE.with_name(name) if name == 'qualify-body.py' else RUNTIME / name)
        raw = path.read_bytes()
        if digest(raw) != expected:
            raise ValueError('baseline_source_drift:' + name)
        base[name] = raw
    return base

def candidate(base):
    out = {name:raw for name,raw in base.items() if name != 'qualify-body.py'}
    text = base['file_auth.py'].decode()
    text = once(text, 'PORT = 30010\nBOUNDS = {\'max_input_tokens\':479993, \'max_total_tokens\':479998}',
                'from context_profile import select\n\nPORT = 30010\nBOUNDS = select().bounds')
    text = once(text, 'def __init__(self, app, *, key, server, request_type):',
                'def __init__(self, app, *, key, server, request_type, profile=None):')
    text = once(text, '        self.active = False',
                '        self.active = False\n        self.profile = profile or select()')
    text = once(text, 'serving_chat=self.server.app.state.openai_serving_chat)',
                'serving_chat=self.server.app.state.openai_serving_chat, context_limit=self.profile.context)')
    text = once(text, "counted['count'] > BOUNDS['max_input_tokens'] or counted['count'] + requested > BOUNDS['max_total_tokens']",
                "counted['count'] > self.profile.bounds['max_input_tokens'] or counted['count'] + requested > self.profile.bounds['max_total_tokens']")
    text = once(text, '    parser.parse_args()',
                "    parser.add_argument('--profile', choices=('production480k','manual1m'), default='production480k')\n    profile=select(parser.parse_args().profile)\n    port=profile.port")
    text = once(text, "'--port',str(PORT)", "'--port',str(port)")
    text = once(text, "'--context-length','480000','--max-total-tokens','480000'",
                "'--context-length',str(profile.context),'--max-total-tokens',str(profile.context)")
    text = once(text, 'args.context_length==args.max_total_tokens==480000',
                'args.context_length==args.max_total_tokens==profile.context')
    text = once(text, 'install_tokenize_route(server,ChatCompletionRequest)',
                'install_tokenize_route(server,ChatCompletionRequest,context_limit=profile.context)')
    text = once(text, 'server.app.add_middleware(ContractMiddleware,key=key,server=server,request_type=ChatCompletionRequest)',
                'server.app.add_middleware(ContractMiddleware,key=key,server=server,request_type=ChatCompletionRequest,profile=profile)')
    text = once(text, "HTTPConnection('127.0.0.1',PORT,timeout=300)",
                "HTTPConnection('127.0.0.1',port,timeout=300)")
    out['file_auth.py'] = text.encode()
    text = base['tokenize_adapter.py'].decode()
    text = once(text, 'import json', 'import json\nfrom context_profile import from_context')
    text = once(text, 'def count_native(payload, *, request_type, serving_chat):',
                'def count_native(payload, *, request_type, serving_chat, context_limit=CONTEXT):')
    text = once(text, '    normalized = normalized_text_request(payload)',
                '    from_context(context_limit)\n    normalized = normalized_text_request(payload)')
    text = once(text, "'context_limit': CONTEXT", "'context_limit': context_limit")
    text = once(text, 'def install_tokenize_route(http_server, request_type):',
                'def install_tokenize_route(http_server, request_type, *, context_limit=CONTEXT):')
    text = once(text, '    app = http_server.app', '    from_context(context_limit)\n    app = http_server.app')
    text = once(text, 'serving_chat=request.app.state.openai_serving_chat)',
                'serving_chat=request.app.state.openai_serving_chat, context_limit=context_limit)')
    out['tokenize_adapter.py'] = text.encode()
    text = base['idle.py'].decode()
    text = once(text, 'import time', 'import time\nfrom context_profile import from_context, verify_allocation')
    text = once(text, "        if native != {'context':480000,'pool':480000,'max_req_len':479999,'max_req_input_len':479994}:\n            raise RuntimeError('flash_native_allocation_mismatch')",
                "        profile = from_context(self.server_args.context_length)\n        if self.server_args.max_total_tokens != profile.context or self.server_args.port != profile.port:\n            raise RuntimeError('flash_context_profile_mismatch')\n        verify_allocation(native, profile)")
    out['idle.py'] = text.encode()
    out['context_profile.py'] = (HERE / 'context_profile.py').read_bytes()
    out['fixture_1m.py'] = (HERE / 'fixture_1m.py').read_bytes()
    out['request_driver.py'] = build_driver(FIXTURE.with_name('qualify-body.py'))
    out['manual.py'] = (HERE / 'manual.py').read_bytes()
    out['baseline-sha256.json'] = (HERE / 'baseline-sha256.json').read_bytes()
    for name, raw in out.items():
        if name.endswith('.py'):
            compile(raw, name, 'exec')
    return out

def prepare(destination):
    base = sources()
    out = candidate(base)
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    for name, raw in out.items():
        (destination / name).write_bytes(raw)
    manifest = {name: digest(raw) for name, raw in out.items()}
    (destination / 'candidate-sha256.json').write_text(json.dumps(manifest, indent=2) + '\n')
    patch = ''.join(''.join(difflib.unified_diff(base[name].decode().splitlines(True), raw.decode().splitlines(True),
                           fromfile='production/' + name, tofile='candidate/' + name))
                    for name, raw in out.items() if name in base and raw != base[name])
    (destination / 'context-only.patch').write_text(patch)
    return {'status':'PREPARED_OFFLINE_NOT_EXECUTED', 'runnable_source_candidate':True, 'live_verified':False,
            'requires':'exact root review, Worker1 staging and fresh explicit harness/client settlement acknowledgement',
            'production_modified':False, 'manifest':manifest}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New local candidate directory; must not exist')
    args = parser.parse_args()
    print(json.dumps(prepare(args.output), indent=2))

if __name__ == '__main__':
    main()
