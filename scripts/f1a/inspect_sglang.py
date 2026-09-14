#!/usr/bin/env python3
"""Inspect the pinned installed SGLang image without loading a model or server.

Run only in the documented disposable image with /work on guarded /data.
The fixture phase uses synthetic strings; it never reads a real secret.
"""
import argparse
import dataclasses
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace

SOURCE = Path('/sgl-workspace/sglang/python/sglang')
FILES = (
    'launch_server.py', 'srt/server_args.py', 'srt/server_args_config_parser.py',
    'srt/utils/auth.py', 'srt/utils/common.py', 'srt/entrypoints/engine.py',
    'srt/entrypoints/http_server.py', 'srt/models/qwen3_next.py',
    'srt/function_call/function_call_parser.py',
    'srt/function_call/qwen3_coder_detector.py',
    'srt/layers/quantization/fp8.py', 'srt/layers/quantization/fp8_kernel.py',
    'srt/layers/quantization/fp8_utils.py', 'srt/environ.py',
)


def load_file_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def static(output):
    records = {}
    sources = output / 'sources'
    sources.mkdir(exist_ok=True)
    for rel in FILES:
        data = (SOURCE / rel).read_bytes()
        records[rel] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
        (sources / rel.replace('/', '__')).write_bytes(data)
    selected = re.compile(r'is_sm120|sm120|sm_120|api.key.file|SGLANG_API_KEY|redact')
    matches = [f'{p.relative_to(SOURCE)}:{i}:{line}'
               for p in (SOURCE / 'srt').rglob('*.py')
               for i, line in enumerate(p.read_text().splitlines(), 1)
               if selected.search(line)]
    (output / 'support-source-matches.txt').write_text('\n'.join(matches) + '\n')
    return {
        'packages': {name: importlib.metadata.version(name) for name in
                     ('sglang', 'torch', 'transformers', 'flashinfer-python')},
        'source_root': str(SOURCE), 'source_files': records,
        'limits': 'Installed source inspection only; no model, GPU or service started.',
    }


def fixtures(output):
    auth = load_file_module('f1a_installed_auth', SOURCE / 'srt/utils/auth.py')
    key = 'F1A-SYNTHETIC-FIXTURE-NOT-A-CREDENTIAL'
    auth_cases = {}
    for path in ('/v1/models', '/v1/chat/completions', '/health', '/health_generate', '/metrics'):
        for name, header in (('missing', None), ('wrong', 'Bearer incorrect-fixture'),
                             ('correct', 'Bearer ' + key)):
            result = auth.decide_request_auth(method='GET', path=path,
                authorization_header=header, api_key=key, admin_api_key=None,
                auth_level=auth.AuthLevel.NORMAL)
            expected = path.startswith(('/health', '/metrics')) or name == 'correct'
            assert result.allowed == expected
            auth_cases[path + ':' + name] = dataclasses.asdict(result)

    config = load_file_module('f1a_installed_config', SOURCE / 'srt/server_args_config_parser.py')
    fixture = output / 'synthetic-auth.yaml'
    descriptor = os.open(fixture, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as handle:
        handle.write('api-key: ' + key + '\n')
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument('--api-key')
        parser.add_argument('--config')
        cli = ['--config', str(fixture)]
        merged = config.ConfigArgumentMerger(parser).merge_config_with_args(cli)
        assert parser.parse_args(merged).api_key == key
        assert key not in cli and key not in sys.argv
    finally:
        fixture.unlink()

    # Import only the argument class, without constructing ServerArgs or starting
    # model discovery. Repr is tested on a default-filled uninitialized object.
    from sglang.srt.server_args import ServerArgs
    args = object.__new__(ServerArgs)
    for field in dataclasses.fields(ServerArgs):
        if field.default is not dataclasses.MISSING:
            value = field.default
        elif field.default_factory is not dataclasses.MISSING:
            value = field.default_factory()
        else:
            value = None
        setattr(args, field.name, value)
    args.api_key = key
    leaks_repr = key in repr(args)
    cli_parser = argparse.ArgumentParser()
    ServerArgs.add_cli_args(cli_parser)
    options = ['--model-path', '--tokenizer-path', '--served-model-name', '--host',
               '--port', '--config', '--api-key', '--api-key-file', '--trust-remote-code',
               '--tool-call-parser', '--reasoning-parser', '--context-length',
               '--tp-size', '--mem-fraction-static', '--max-running-requests',
               '--attention-backend', '--linear-attn-backend', '--moe-runner-backend',
               '--quantization', '--fp8-gemm-backend', '--load-format', '--tokenizer-worker-num',
               '--cuda-graph-backend-decode', '--cuda-graph-backend-prefill']
    actions = {opt: cli_parser._option_string_actions.get(opt) for opt in options}
    option_contract = {opt: None if action is None else
                       {'dest': action.dest, 'default': str(action.default),
                        'choices': list(action.choices) if action.choices is not None else None,
                        'help': action.help} for opt, action in actions.items()}
    (output / 'actual-parser-help.txt').write_text(cli_parser.format_help())
    from sglang.srt.function_call.qwen3_coder_detector import Qwen3CoderDetector
    tool = SimpleNamespace(type='function', function=SimpleNamespace(
        name='fixture_add', parameters={'properties': {'n': {'type': 'integer'}}}))
    parsed = Qwen3CoderDetector().detect_and_parse(
        '<tool_call><function=fixture_add><parameter=n>7</parameter></function></tool_call>', [tool])
    assert len(parsed.calls) == 1 and parsed.calls[0].name == 'fixture_add'
    assert json.loads(parsed.calls[0].parameters) == {'n': 7}
    return {'auth_decisions': auth_cases, 'native_yaml_key_parsed': True,
            'yaml_key_absent_from_os_argv': True, 'api_key_repr_leaks': leaks_repr,
            'api_key_asdict_leaks': dataclasses.asdict(args)['api_key'] == key,
            'qwen3_coder_synthetic_parse': 'PASS',
            'option_contract': option_contract,
            'limits': 'Synthetic pure auth, config merger and argument repr only; no model/server initialization.'}


def kernel_smoke():
    import torch
    from sglang.srt.layers.quantization.fp8_utils import triton_w8a8_block_fp8_linear
    result = []
    for index in range(torch.cuda.device_count()):
        with torch.cuda.device(index):
            x = torch.ones((16, 128), dtype=torch.bfloat16, device='cuda')
            w = torch.full((128, 128), 0.125, dtype=torch.bfloat16, device='cuda').to(torch.float8_e4m3fn)
            scale = torch.ones((1, 1), dtype=torch.float32, device='cuda')
            actual = triton_w8a8_block_fp8_linear(x, w, [128, 128], scale)
            torch.cuda.synchronize()
            expected = torch.full_like(actual, 16)
            error = float((actual.float() - expected.float()).abs().max().item())
            assert actual.shape == (16, 128) and error <= 0.125
            result.append({'device_index': index, 'name': torch.cuda.get_device_name(index),
                           'compute_capability': list(torch.cuda.get_device_capability(index)),
                           'max_absolute_error': error, 'shape_m_n_k': [16, 128, 128],
                           'torch_peak_allocated_bytes': torch.cuda.max_memory_allocated(index)})
    assert result, 'no CUDA devices available'
    return {'cuda_block_fp8_linear_smoke': result,
            'limits': 'Tiny installed Triton FP8 linear kernel only; no model, MoE, GDN, attention, collective or service test.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('static', 'fixtures', 'kernel'), required=True)
    parser.add_argument('--output', type=Path, default=Path('/work/evidence'))
    args = parser.parse_args()
    if not args.output.is_dir() or args.output.is_symlink():
        parser.error('output must be an existing nonsymlink directory on the task mount')
    result = {'static': lambda: static(args.output), 'fixtures': lambda: fixtures(args.output),
              'kernel': kernel_smoke}[args.phase]()
    encoded = json.dumps(result, indent=2, default=str) + '\n'
    (args.output / ('installed-' + args.phase + '.json')).write_text(encoded)
    print(encoded)


if __name__ == '__main__':
    main()
