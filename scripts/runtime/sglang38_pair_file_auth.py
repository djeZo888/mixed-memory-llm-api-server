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
import threading
from types import SimpleNamespace

BASE_SHA256 = "e507ed81d1e3954afea1d31eb9f0bc7ef7ab8b9a76bb571499e1a5f9c53c7da4"
CONTEXT = 480000
ADAPTIVE_OVERLAY_SHA256 = 'b7f03476fe13779ed4867e4ca509dcba2861431210b6a264cf551558b5927a27'
ADAPTIVE_VERIFIER_SHA256 = '554c6ffc6c76fef28a3c778cd25ee1160a21a771906f95a7fea3418682ece00d'
SLOTS = {'gpu0': {'port': 30002, 'served_model_name': 'qwen3.8-27b-gpu0'},
         'gpu1': {'port': 30004, 'served_model_name': 'qwen3.8-27b'}}


def verify_adaptive_overlay():
    # This guard is additional to protected lifecycle/image acceptance. A
    # historical parent image alone cannot provide the reviewed native source.
    verifier = Path('/opt/llmctl/adaptive-idle/verify.py')
    if (verifier.is_symlink()
            or hashlib.sha256(verifier.read_bytes()).hexdigest() != ADAPTIVE_VERIFIER_SHA256):
        raise ValueError('adaptive_overlay_verifier_mismatch')
    spec = importlib.util.spec_from_file_location('text_adaptive_verifier', verifier)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify_installed('/opt/llmctl/adaptive-idle/text.json',
                                   ADAPTIVE_OVERLAY_SHA256, 'text')


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


def install_readiness(base, http_server, slot, warmup_complete):
    """Expose only the existing internal state, behind native file-backed auth.

    The authenticated warmup's completion is a separate prerequisite: an Up
    value from another native path cannot admit a still-starting instance.
    This route never invokes health, submits work, or touches scheduler state.
    """
    from fastapi.responses import JSONResponse

    app = http_server.app
    if (not getattr(app, "_llmctl_file_auth_installed", False)
            or getattr(app, "middleware_stack", None)
            or any(getattr(route, "path", None) == "/v1/readiness" for route in app.routes)):
        raise base.LaunchError("pair_readiness_installation_invalid")
    alias = SLOTS[slot]["served_model_name"]

    async def readiness():
        manager = getattr(getattr(http_server, "_global_state", None), "tokenizer_manager", None)
        status = getattr(manager, "server_status", None)
        status_type = getattr(http_server, "ServerStatus", None)
        state = "unknown"
        if (isinstance(status_type, type) and type(status) is status_type
                and getattr(manager, "served_model_name", None) == alias):
            if status is getattr(status_type, "Starting", None):
                state = "starting"
            elif status is getattr(status_type, "Up", None):
                state = "up" if warmup_complete.is_set() else "starting"
            elif status is getattr(status_type, "UnHealthy", None):
                state = "unhealthy"
        ready = state == "up"
        return JSONResponse({"schema_version": 1, "model_alias": alias, "ready": ready,
                             "state": state, "admitting": None}, status_code=200 if ready else 503)

    app.add_api_route("/v1/readiness", readiness, methods=["GET"], include_in_schema=False)


def bind_variant(base, slot):
    """Check the fixed changed fields, reusing every unchanged base check."""
    argv = backend_argv(base, slot)
    original_validate, original_environment = base.validate_server_args, base.validate_environment
    original_auth, original_warmup = base.install_auth, base.make_warmup
    warmup_complete = threading.Event()
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

    def install_auth(http_server, add_api_key_middleware, key):
        original_auth(http_server, add_api_key_middleware, key)
        install_readiness(base, http_server, slot, warmup_complete)

    def make_warmup(http_server, key, abort, ready, startup_deadline, timeout=600):
        def completed():
            ready()
            warmup_complete.set()

        return original_warmup(http_server, key, abort, completed, startup_deadline, timeout)

    base.parse_options = parse
    base.validate_server_args = validate
    base.validate_environment = lambda context=None: original_environment(base.EXTENSION_CONTEXT)
    base.install_auth = install_auth
    base.make_warmup = make_warmup
    return expected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--slot', choices=tuple(SLOTS), required=True)
    import sys
    arguments = sys.argv[1:] if argv is None else argv
    options = parser.parse_args(arguments)
    if arguments != ['--slot', options.slot]:
        parser.error('only one canonical --slot argument is accepted')
    verify_adaptive_overlay()
    base = pinned_base("/opt/llmctl/sglang38_file_auth.py")
    return base.main(bind_variant(base, options.slot))


if __name__ == "__main__":
    raise SystemExit(main())
