#!/usr/bin/env python3
"""Two closed Qwen slots, layered on the unchanged pinned auth launcher.

Only --slot gpu0 or --slot gpu1 is accepted. No user context, TP, port,
environment or native-argument surface is exposed.
The base retains key handling, native auth, resolving-view checks, cancellation,
child cleanup and authenticated warmup. Import and --help are inert.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

BASE_SHA256 = "e507ed81d1e3954afea1d31eb9f0bc7ef7ab8b9a76bb571499e1a5f9c53c7da4"
CONTEXT = 480000
SLOTS = {'gpu0': {'port': 30002, 'served_model_name': 'qwen3.8-27b-gpu0'},
         'gpu1': {'port': 30004, 'served_model_name': 'qwen3.8-27b'}}


def pinned_base(path):
    path = Path(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != BASE_SHA256:
        raise ValueError("pair_auth_source_mismatch")
    spec = importlib.util.spec_from_file_location("pair_pinned_auth", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def backend_argv(base, slot):
    if not isinstance(slot, str) or slot not in SLOTS:
        raise base.LaunchError("pair_slot_invalid")
    flags = dict(base.FIXED_FLAGS)
    flags["--port"] = str(SLOTS[slot]['port'])
    flags["--served-model-name"] = SLOTS[slot]['served_model_name']
    flags["--json-model-override-args"] = base.EXTENSION_OVERRIDE_JSON
    return ([value for item in flags.items() for value in item]
            + ["--context-length", str(CONTEXT), "--max-total-tokens", str(CONTEXT)]
            + list(base.BOOLEAN_FLAGS))


class _View:
    def __init__(self, original, overrides):
        self.original, self.overrides = original, overrides

    def __getattr__(self, name):
        return self.overrides[name] if name in self.overrides else getattr(self.original, name)


def bind_variant(base, slot):
    """Check the fixed changed fields, reusing every unchanged base check."""
    argv = backend_argv(base, slot)
    original_validate, original_environment = base.validate_server_args, base.validate_environment
    changed = {"context_length": CONTEXT, "max_total_tokens": CONTEXT, "tp_size": 1,
               **SLOTS[slot]}
    projected = {"context_length": base.EXTENSION_CONTEXT,
                 "max_total_tokens": base.EXTENSION_CONTEXT, "tp_size": 2,
                 "port": 30004, "served_model_name": "qwen3.8-27b"}

    def validate(args, *, resolved=False):
        if any(type(getattr(args, key, None)) is not type(value) or getattr(args, key) != value
               for key, value in changed.items()):
            raise base.LaunchError("pair_server_tuple_invalid")
        original_validate(_View(args, projected), resolved=resolved)

    expected = ["--key-file", "/run/secrets/llm-api-key", "--warmup-timeout", "600", *argv]

    def parse(args):
        if args != expected:
            raise base.LaunchError("pair_launch_arguments_invalid")
        return SimpleNamespace(key_file="/run/secrets/llm-api-key", warmup_timeout="600",
                               context_length=str(CONTEXT)), argv

    base.parse_options = parse
    base.validate_server_args = validate
    base.validate_environment = lambda context=None: original_environment(base.EXTENSION_CONTEXT)
    return expected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--slot', choices=tuple(SLOTS), required=True)
    import sys
    arguments = sys.argv[1:] if argv is None else argv
    options = parser.parse_args(arguments)
    if arguments != ['--slot', options.slot]:
        parser.error('only one canonical --slot argument is accepted')
    base = pinned_base("/opt/llmctl/sglang38_file_auth.py")
    return base.main(bind_variant(base, options.slot))


if __name__ == "__main__":
    raise SystemExit(main())
