#!/usr/bin/env python3
"""Benchmark-only closed tuples layered on the unchanged pinned file-auth launcher.

Mounted only in benchmark containers. Import/help are inert. The existing
launcher retains key reading, native middleware, alias validation, environment,
raw/resolved configuration validation, worker cleanup and authenticated warmup.
Production launcher/profile bytes and production catalog remain unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

PIN = "e507ed81d1e3954afea1d31eb9f0bc7ef7ab8b9a76bb571499e1a5f9c53c7da4"
CAPACITIES = (4096, 16384, 65536)  # 131072 requires a later root source decision.


def pinned_base(path):
    path = Path(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != PIN:
        raise ValueError("benchmark_auth_source_mismatch")
    spec = importlib.util.spec_from_file_location("benchmark_pinned_auth", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def variant(base, context, tp):
    if type(context) is not int or context not in CAPACITIES or type(tp) is not int or tp not in (1, 2):
        raise ValueError("benchmark_tuple_unreviewed")
    # Keep the production factor4 YaRN, cache and execution settings at every
    # rung/placement. Only context/pool, TP, alias and container port differ.
    flags = dict(base.FIXED_FLAGS)
    flags.update({"--tp-size": str(tp), "--port": "31004",
                  "--served-model-name": "bench-qwen3.8-27b",
                  "--json-model-override-args": base.EXTENSION_OVERRIDE_JSON})
    return ([x for pair in flags.items() for x in pair]
            + ["--context-length", str(context), "--max-total-tokens", str(context)]
            + list(base.BOOLEAN_FLAGS))


class _View:
    def __init__(self, original, overrides):
        self.original, self.overrides = original, overrides

    def __getattr__(self, name):
        return self.overrides[name] if name in self.overrides else getattr(self.original, name)


def bind_variant(base, context, tp):
    """Bind one validated tuple in a fresh launcher module, before key access.

    Check each changed field exactly, then project those fields to the existing
    extension contract so every unchanged native mode check is reused. The
    original resolving-view validator still compares raw/resolved tuple values.
    No change to native ServerArgs, credentials or serialization is made.
    """
    argv = variant(base, context, tp)
    original_validate = base.validate_server_args
    original_environment = base.validate_environment
    changed = {"context_length": context, "max_total_tokens": context,
               "tp_size": tp, "port": 31004,
               "served_model_name": "bench-qwen3.8-27b"}
    projection = {"context_length": base.EXTENSION_CONTEXT,
                  "max_total_tokens": base.EXTENSION_CONTEXT, "tp_size": 2,
                  "port": 30004, "served_model_name": "qwen3.8-27b"}

    def validate(args, *, resolved=False):
        if any(type(getattr(args, k, None)) is not type(v) or getattr(args, k) != v
               for k, v in changed.items()):
            raise base.LaunchError("benchmark_server_tuple_invalid")
        original_validate(_View(args, projection), resolved=resolved)

    def parse(args):
        expected = ["--key-file", "/run/secrets/llm-api-key", "--warmup-timeout", "600", *argv]
        if args != expected:
            raise base.LaunchError("benchmark_launch_arguments_invalid")
        return SimpleNamespace(key_file="/run/secrets/llm-api-key",
                               warmup_timeout="600", context_length=str(context)), argv

    base.parse_options = parse
    base.validate_server_args = validate
    base.validate_environment = lambda context=None: original_environment(base.EXTENSION_CONTEXT)
    return ["--key-file", "/run/secrets/llm-api-key", "--warmup-timeout", "600", *argv]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--context", required=True, type=int, choices=CAPACITIES)
    parser.add_argument("--tp", required=True, type=int, choices=(1, 2))
    options = parser.parse_args(argv)
    base = pinned_base("/opt/llmctl/sglang38_file_auth.py")
    return base.main(bind_variant(base, options.context, options.tp))


if __name__ == "__main__":
    raise SystemExit(main())
