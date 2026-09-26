#!/usr/bin/env python3
"""Closed480K two-slot pair mode of the unchanged actual-image auth fixture.

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


class _Contract:
    def __init__(self, slot, adaptive=False):
        self.slot = slot
        self.adaptive = adaptive

    def __getattr__(self, name):
        return getattr(contract, name)

    def extension_identity(self, repo, provenance=None):
        return contract.pair_identity(repo, provenance, slot=self.slot, adaptive=self.adaptive)


def parse_options(argv):
    parser = inner.Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--actual-image', action='store_true', required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--slot', choices=tuple(contract.PROFILES), required=True)
    parser.add_argument('--context', type=int, choices=(contract.CONTEXT,), required=True)
    parser.add_argument('--adaptive-overlay', action='store_true')
    parser.add_argument('--internal-scenario', choices=inner.SCENARIOS, default='all', help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    try:
        options = parse_options(arguments)
    except Exception:
        print(json.dumps({'status': 'FAIL', 'code': 'pair_fixture_arguments_invalid'}))
        return 2
    slot = options.slot
    adaptive = options.adaptive_overlay
    variant = load('q38pair_slot_wrapper', ROOT / 'scripts/runtime/sglang38_pair_file_auth.py').SLOTS[slot]
    original_verify = inner.verify_sources
    original_discovery = inner.cuda_discovery_fixture

    def verify(repo):
        original_verify(repo)  # Every legacy/native source hash stays required.
        contract.pair_identity(repo, slot=slot, adaptive=adaptive)
        if adaptive:
            # The CPU-only actual-image fixture checks the same installed
            # verifier/overlay closure as the production pair launcher.
            load('q38pair_overlay_guard', repo / 'scripts/runtime/sglang38_pair_file_auth.py').verify_adaptive_overlay()
        return repo / 'tests/lifecycle/sglang38_fixture/pair_launcher.py'

    def discovery(torch, context=contract.CONTEXT):
        contract.host.require(context == contract.CONTEXT, 'pair_fixture_context_invalid')
        return original_discovery(torch, 131072)  # Exact one-GPU discovery stub.

    with ExitStack() as stack:
        if adaptive:
            oci = contract.runtime_binding(ROOT).text_oci()
            for name, value in {'IMAGE_ID': oci.IMAGE_ID, 'IMAGE_REFERENCE': oci.IMAGE_REFERENCE,
                                'DRAIN_TARGET': 'text',
                                'source_provenance': lambda repo: contract.adaptive_provenance(repo)[0]}.items():
                stack.enter_context(patch.object(inner, name, value))
        for name, value in {
                'EXTENSION_CONTEXT': contract.CONTEXT,
                'ALIAS': variant['served_model_name'], 'PORT': variant['port'],
                'FIXTURE_SLOT': slot,
                'CHILD_ARGUMENTS': ('--slot', slot, *(['--adaptive-overlay'] if adaptive else [])),
                'parse_options': parse_options,
                '__file__': __file__,  # Independent abort children use this same mode.
                'verify_sources': verify,
                'fixture_contract': lambda repo: _Contract(slot, adaptive),
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
