#!/usr/bin/env python3
"""Exact 1M fixture construction ONLY, never sends inference.

Runs with the unchanged pinned tokenizer in a future reviewed owner. The native
/v1/tokenize parity response must still be checked before dispatch. Offline mocks
are not native counts. This file also supports a bounded short qualification body.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from context_profile import TARGET, OUTPUT, select, require_budget

BASE_FIXTURE_HASH = '66b05346d3a43dd3442c25149522d931bad7453d514e3569b34853950387c2ab'
MAX_BODY = 16 * 1024 * 1024

def fixture_module():
    path = Path(__file__).with_name('fixture_native.py')
    if hashlib.sha256(path.read_bytes()).hexdigest() != BASE_FIXTURE_HASH:
        raise ValueError('fixture_source_drift')
    import importlib.util
    spec = importlib.util.spec_from_file_location('h010_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def build(tokenizer, seed):
    if not isinstance(seed, str) or not seed or len(seed) > 128:
        raise ValueError('fresh_seed_required')
    result = fixture_module().build_fixture(tokenizer, TARGET, 'H011-manual1m:' + seed)
    payload = result['payload']
    payload['max_tokens'] = OUTPUT
    result['payload_sha256'] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    raw = json.dumps({**payload, 'stream':True,
                      'stream_options':{'include_usage':True,'continuous_usage_stats':True}}).encode()
    if len(raw) > MAX_BODY:
        raise ValueError('request_too_large')
    if result['rendered_tokens'] != TARGET or result['requested_input_tokens'] != TARGET:
        raise ValueError('exact_native_target_not_met')
    require_budget(TARGET, OUTPUT, select('manual1m'))
    result.update(schema='h011.exact-1m-fixture.v1', serialized_request_bytes=len(raw),
                  native_tokenize_parity='REQUIRED_BEFORE_INFERENCE', output_includes_reasoning=True)
    return result

def short_payload():
    return {'model':'glm-5.3-flash','messages':[{'role':'user','content':'Reply exactly READY.'}],
            'max_tokens':32, 'temperature':0, 'reasoning_effort':'high',
            'chat_template_kwargs':{'clear_thinking':True}}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed', required=True)
    args = p.parse_args()
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained('/models', local_files_only=True)
    print(json.dumps(build(tokenizer, args.seed), separators=(',', ':')))

if __name__ == '__main__':
    main()
