#!/usr/bin/env python3
"""Launch the pinned local-provider OpenCode in an explicitly selected workspace."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True

from client_common import (ClientError, KEY_ENV, PROVIDER, VERSION, absolute_path, binary_path,
                           config_for, encode_key, isolated_env, load_key, run_capture, verify_install)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--workspace", required=True, help="Absolute existing workspace; tools run as your OS user, not in a sandbox")
    result.add_argument("--plan", action="store_true", help="Validate launcher/config without writes, processes, or loading keys")
    result.add_argument("--allow-edit", action="store_true", help="Allow model file edits for this invocation")
    result.add_argument("--allow-test-command", help="Exact bash test command to allow; no glob characters (run mode only)")
    result.add_argument("--prompt-file", help="UTF-8 prompt file for run mode, sent on stdin, never argv")
    result.add_argument("command", choices=("version", "help", "run-help", "config-help", "check", "chat", "run"))
    return result


def launch(args, prefix=None):
    os.umask(0o077)
    prefix = prefix or Path(__file__).resolve().parent.parent
    settings = verify_install(prefix)
    workspace = absolute_path(args.workspace)
    if not workspace.is_dir():
        raise ClientError("Workspace must be an existing directory")
    if args.command != "run" and (args.prompt_file or args.allow_test_command):
        raise ClientError("Prompt file and test-command permission require run mode")
    if args.command == "run" and not args.prompt_file:
        raise ClientError("run requires --prompt-file")
    if args.allow_edit and args.command not in ("run", "chat"):
        raise ClientError("Edit permission requires run or chat mode")
    if args.allow_test_command and (any(c in args.allow_test_command for c in "*?[]\n\r") or not args.allow_test_command.strip()):
        raise ClientError("Test permission must be one nonempty exact command without wildcards/newlines")
    if args.plan:
        print(json.dumps({"version": VERSION, "workspace": str(workspace), "command": args.command,
                          "model": PROVIDER + "/" + settings["model"], "auth_kind": settings["auth"]["kind"],
                          "mutations": False, "key_loaded": False}))
        return 0
    env = isolated_env(prefix)
    binary = str(binary_path(prefix))
    simple = {"version": ["--version"], "help": ["--help"], "run-help": ["run", "--help"],
              "config-help": ["debug", "config", "--help"]}
    if args.command in simple:
        print(run_capture([binary] + simple[args.command], workspace, env, include_stderr=True), end="")
        return 0
    if args.command == "check":
        # Synthetic punctuation exercises interpolation; no real file/env key is loaded.
        dummy = b'v0-dummy-"\\-{file:/not-a-real-key}'
        env[KEY_ENV] = encode_key(dummy)
        actual = json.loads(run_capture([binary, "debug", "config"], workspace, env))
        expected = config_for(settings)
        if settings["auth"]["kind"] != "disabled":
            expected["provider"][PROVIDER]["options"]["apiKey"] = dummy.decode("ascii")
        for key, value in expected.items():
            if actual.get(key) != value:
                raise ClientError("Installed CLI resolved configuration differs from bootstrap")
        models = run_capture([binary, "models", PROVIDER], workspace, env).splitlines()
        if models != [PROVIDER + "/" + settings["model"]]:
            raise ClientError("Installed CLI provider/model list differs from explicit local selection")
        print("PASS: installed CLI resolved local configuration/model and byte-preserving dummy key; no inference or real key loaded")
        return 0
    if settings["auth"]["kind"] != "disabled":
        env[KEY_ENV] = load_key(settings["auth"])
    permissions = {}
    if args.allow_edit:
        permissions["edit"] = "allow"
    if args.allow_test_command:
        permissions["bash"] = {"*": "deny", args.allow_test_command: "allow"}
    if permissions:
        env["OPENCODE_PERMISSION"] = json.dumps(permissions)
    selection = ["--model", PROVIDER + "/" + settings["model"]]
    if args.command == "chat":
        return subprocess.run([binary] + selection, cwd=workspace, env=env).returncode
    prompt = Path(args.prompt_file).read_bytes()
    if not prompt or len(prompt) > 1024 * 1024:
        raise ClientError("Prompt file must contain 1..1048576 bytes")
    prompt.decode("utf-8")
    return subprocess.run([binary, "run", "--format", "json"] + selection,
                          cwd=workspace, env=env, input=prompt).returncode


def main():
    try:
        return launch(parser().parse_args())
    except (ClientError, OSError, ValueError, KeyError, subprocess.SubprocessError):
        error = sys.exception() if hasattr(sys, "exception") else sys.exc_info()[1]
        print("ERROR: " + (str(error) if isinstance(error, ClientError) else "Client I/O or child execution failed"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
