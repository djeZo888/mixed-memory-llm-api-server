#!/usr/bin/env python3
"""Install the reviewed OpenCode client without changing machine configuration."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True

from client_common import (ClientError, VERSION, absolute_path, binary_path, config_for,
                           endpoint, isolated_env, json_bytes, key_env_name, model_id,
                           native_package, private_dir, refuse_managed_preferences,
                           reasoning_effort, run_capture, runtime_dir, verify_install, write_new)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--prefix", required=True, help="New/managed absolute private installation prefix")
    result.add_argument("--base-url", required=True, help="Exact localhost API base URL including port and /v1")
    result.add_argument("--model", required=True, help="Exact model ID published by the API")
    auth = result.add_mutually_exclusive_group(required=True)
    auth.add_argument("--api-key-file", help="Absolute protected newline-free key file; not opened during bootstrap")
    auth.add_argument("--api-key-env", help="Environment variable NAME, never its value")
    auth.add_argument("--auth-disabled", action="store_true", help="Explicit unauthenticated localhost configuration")
    result.add_argument("--context-tokens", required=True, type=int, help="Operator-supplied model context limit")
    result.add_argument("--output-tokens", required=True, type=int, help="Operator-supplied output limit")
    result.add_argument("--reasoning-effort", type=reasoning_effort,
                        help="Optional literal low; omitted by default (new prefix required to change)")
    result.add_argument("--dry-run", "--plan", action="store_true", help="Validate and describe only; no writes/network/processes")
    return result


def bootstrap(args):
    # Python process-local umask; no mutation of the calling shell's environment.
    os.umask(0o077)
    prefix = absolute_path(args.prefix)
    if prefix == Path.home().resolve() or prefix == Path("/") or not prefix.parent.is_dir():
        raise ClientError("Prefix must be a dedicated child of an existing directory")
    if Path(args.prefix).is_symlink():
        raise ClientError("Installation prefix must not be a symlink")
    if not 0 < args.output_tokens < args.context_tokens:
        raise ClientError("Require 0 < output-tokens < context-tokens")
    auth = {"kind": "disabled"}
    if args.api_key_file:
        # Canonicalize only the parent; preserve final symlink for launch-time refusal.
        path = Path(args.api_key_file)
        if not path.is_absolute():
            raise ClientError("Key file reference must be absolute")
        auth = {"kind": "file", "reference": str(absolute_path(str(path.parent)) / path.name)}
    if args.api_key_env:
        auth = {"kind": "env", "reference": key_env_name(args.api_key_env)}
    source = Path(__file__).resolve().parent
    lock = (source / "package-lock.json").read_bytes()
    settings = {"version": VERSION, "base_url": endpoint(args.base_url), "model": model_id(args.model),
                "auth": auth, "context_tokens": args.context_tokens, "output_tokens": args.output_tokens,
                "lock_sha256": hashlib.sha256(lock).hexdigest()}
    if args.reasoning_effort is not None:
        settings["reasoning_effort"] = reasoning_effort(args.reasoning_effort)
    native_package()
    refuse_managed_preferences()
    existed = prefix.exists()
    if existed:
        private_dir(prefix)
        if any(prefix.iterdir()):
            if not (prefix / "bootstrap.json").is_file():
                raise ClientError("Refuse nonempty unmanaged prefix; choose a fresh directory")
            if verify_install(prefix) != settings:
                raise ClientError("Existing installation/configuration differs; choose a new prefix")
            for name in ("package.json", "package-lock.json"):
                if (runtime_dir(prefix) / name).read_bytes() != (source / name).read_bytes():
                    raise ClientError("Installed package manifest/lock changed; choose a new prefix")
            for target, origin in (("opencode-client", "launch.py"), ("client_common.py", "client_common.py")):
                if (prefix / "bin" / target).read_bytes() != (source / origin).read_bytes():
                    raise ClientError("Installed launcher changed; choose a new prefix")
    if args.dry_run:
        print(json.dumps({"action": "verify" if existed and any(prefix.iterdir()) else "install",
                          "version": VERSION, "prefix": str(prefix), "base_url": settings["base_url"],
                          "model": settings["model"], "auth_kind": auth["kind"],
                          **({"reasoning_effort": settings["reasoning_effort"]} if "reasoning_effort" in settings else {}),
                          "lock_sha256": settings["lock_sha256"], "mutations": False}))
        return
    env = isolated_env(prefix)
    if not (prefix / "bootstrap.json").exists():
        # Check prerequisites before creating the installation tree. No npm config/auth reads.
        node = shutil.which("node")
        npm = shutil.which("npm")
        if not node or not npm:
            raise ClientError("Provision Node.js 24.15+ (24.x) and npm 10+ first; bootstrap does not install them")
        node_version = run_capture([node, "--version"], source, env).strip()
        node_parts = tuple(int(part) for part in node_version.lstrip("v").split("."))
        if node_parts[0] != 24 or node_parts < (24, 15, 0):
            raise ClientError("This dependency lock requires Node.js 24.15+ within 24.x (tested with 24.21.0)")
        private_dir(prefix, create=True)
        for name in ("bin", "xdg", "xdg/config", "xdg/data", "xdg/cache", "xdg/state", "xdg/config/opencode",
                     "npm", "npm/cache", "npm/logs", "tmp", "bun-cache", "managed", "discovery-home"):
            private_dir(prefix / name, create=True)
        for name in ("userconfig", "globalconfig"):
            write_new(prefix / "npm" / name, b"")
        npm_version = run_capture([npm, "--version"], prefix, env).strip()
        if int(npm_version.split(".")[0]) < 10:
            raise ClientError("Bootstrap requires npm 10+ (tested with npm 11)")
        for name in ("package.json", "package-lock.json"):
            write_new(runtime_dir(prefix) / name, (source / name).read_bytes())
        print("Installing integrity-locked OpenCode " + VERSION + " under the private prefix", flush=True)
        # Official native package is invoked directly; skip wrapper postinstall's fallback installs.
        run_capture([npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund", "--include=optional"],
                    runtime_dir(prefix), env, timeout=600)
        for target, origin in (("opencode-client", "launch.py"), ("client_common.py", "client_common.py")):
            write_new(prefix / "bin" / target, (source / origin).read_bytes(), 0o700 if target == "opencode-client" else 0o600)
        write_new(prefix / "opencode.json", json_bytes(config_for(settings)))
        write_new(prefix / "models.json", b"{}\n")
        write_new(prefix / "bootstrap.json", json_bytes(settings))
    verify_install(prefix)
    version = run_capture([str(binary_path(prefix)), "--version"], prefix, env).strip()
    if version != VERSION:
        raise ClientError("Actual CLI version does not match pin")
    print("PASS: installed CLI " + version + "; launcher " + str(prefix / "bin" / "opencode-client"))


def main():
    try:
        bootstrap(parser().parse_args())
    except (ClientError, OSError, ValueError, KeyError, subprocess.SubprocessError):
        # Error detail is intentionally bounded; no environment, file contents or child output.
        error = sys.exception() if hasattr(sys, "exception") else sys.exc_info()[1]
        print("ERROR: " + (str(error) if isinstance(error, ClientError) else "Bootstrap I/O or child execution failed"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
