#!/usr/bin/env python3
"""Closed 700160 pair mode of the unchanged actual-image auth fixture.

The fixture-only seams select the production pair wrapper and one discovery
GPU. The original auth/parser/cache/failure-child implementation is reused.
There is no source-extracted native fallback and no model execution claim.
"""
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
import argparse
import importlib.util
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inner = load('q38pair_original_inner', HERE / 'run_pinned_image.py')
contract = load('q38pair_actual_contract', HERE / 'run_pair_fixture.py')


def parse_options(argv):
    parser = inner.Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--actual-image', action='store_true', required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--context', type=int, choices=(contract.CONTEXT,), required=True)
    parser.add_argument('--internal-scenario', choices=inner.SCENARIOS, default='all', help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv=None):
    original_verify = inner.verify_sources
    original_discovery = inner.cuda_discovery_fixture

    def verify(repo):
        original_verify(repo)  # Every legacy/native source hash stays required.
        contract.pair_identity(repo)
        return repo / 'tests/lifecycle/sglang38_fixture/pair_launcher.py'

    def discovery(torch, context=contract.CONTEXT):
        contract.host.require(context == contract.CONTEXT, 'pair_fixture_context_invalid')
        return original_discovery(torch, 131072)  # Exact one-GPU discovery stub.

    with ExitStack() as stack:
        for name, value in {
                'EXTENSION_CONTEXT': contract.CONTEXT,
                'parse_options': parse_options,
                '__file__': __file__,  # Independent abort children use this same mode.
                'verify_sources': verify,
                'fixture_contract': lambda repo: contract,
                'cuda_discovery_fixture': discovery}.items():
            stack.enter_context(patch.object(inner, name, value))
        arguments = sys.argv[1:] if argv is None else argv
        try:
            options = inner.parse_options(arguments)
            contract.host.require(type(options.context) is int and options.context == contract.CONTEXT,
                                  'pair_fixture_context_invalid')
        except Exception:
            print(json.dumps({'status': 'FAIL', 'code': 'pair_fixture_arguments_invalid'}))
            return 2
        return inner.main(arguments)


if __name__ == '__main__':
    raise SystemExit(main())
