#!/usr/bin/env python3
"""Opt-in native client proof to a synthetic server on this worker's private IPv4.

Copies an existing reviewed dependency tree into bootstrap-generated fresh prefixes.
No npm install, model inference, remote endpoint, real key, or TLS bypass is used.
Runs a loopback control first. Evidence contains only fixed classifications/counts.
"""

import argparse
import contextlib
import hashlib
import io
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import threading
from unittest import mock

sys.dont_write_bytecode = True
CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT))
import bootstrap
from client_common import (VERSION, absolute_path, binary_path, isolated_env,
                           json_bytes, private_dir, runtime_dir, verify_install,
                           write_new)
from wire_fixture import FixtureError, Handler, WireServer, child, require

PRIVATE_NETS = tuple(ipaddress.IPv4Network(value) for value in
                     ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


class PrivateUnavailable(FixtureError):
    """No private exchange occurred; loopback still supplies the native control."""


def confirm_own_private_ipv4(value):
    """Read addresses before permitting a literal, specific private bind."""
    try:
        address = ipaddress.IPv4Address(value)
    except (ipaddress.AddressValueError, TypeError):
        raise FixtureError("canonical_private_ipv4_required") from None
    require(type(value) is str and str(address) == value
            and any(address in network for network in PRIVATE_NETS),
            "canonical_private_ipv4_required")
    require(sys.platform == "darwin", "address_confirmation_not_supported_on_this_platform")
    result = subprocess.run(["/sbin/ifconfig"], capture_output=True, text=True,
                            timeout=10, check=True)
    addresses = re.findall(r"^\s+inet ([0-9.]+) netmask ", result.stdout, re.MULTILINE)
    require(value in addresses, "private_address_not_assigned_to_this_worker")
    return value


class ExactHandler(Handler):
    def do_POST(self):
        if self.headers.get_all("Host", []) != [self.server.expected_host]:
            self.server.failure = "unexpected_host"
            self.send_error(400, "Synthetic fixture rejected request")
            return
        super().do_POST()


class OwnAddressServer(WireServer):
    def verify_request(self, request, client_address):
        # A private fixture never accepts requests from another LAN host.
        return client_address[0] == self.server_address[0]


def offline_bootstrap(prefix, base, key_file, source_prefix):
    """Only substitute npm ci with a copy; bootstrap owns every generated file."""
    source_runtime = runtime_dir(source_prefix)
    for name in ("package.json", "package-lock.json"):
        require((source_runtime / name).read_bytes() == (CLIENT / name).read_bytes(),
                "source_dependency_lock_mismatch")
    for package in ("opencode-ai", "@opencode-ai/plugin", bootstrap.native_package()):
        manifest = json.loads((source_runtime / "node_modules" / package / "package.json").read_text())
        require(manifest.get("version") == VERSION, "source_dependency_version_mismatch")
    real_capture = bootstrap.run_capture

    def capture(argv, cwd, env, **kwargs):
        if len(argv) > 1 and argv[1] == "ci":
            require(argv[2:] == ["--ignore-scripts", "--no-audit", "--no-fund", "--include=optional"],
                    "unexpected_install_command")
            shutil.copytree(source_runtime / "node_modules", cwd / "node_modules", symlinks=True)
            return ""
        return real_capture(argv, cwd, env, **kwargs)

    args = bootstrap.parser().parse_args([
        "--prefix", str(prefix), "--base-url", base, "--model", "n1c-synthetic",
        "--context-tokens", "32768", "--output-tokens", "2048",
        "--api-key-file", str(key_file)])
    with mock.patch.object(bootstrap, "run_capture", side_effect=capture), contextlib.redirect_stdout(io.StringIO()):
        bootstrap.bootstrap(args)
    verify_install(prefix)
    require(hashlib.sha256(binary_path(prefix).read_bytes()).digest()
            == hashlib.sha256(binary_path(source_prefix).read_bytes()).digest(),
            "copied_native_binary_mismatch")


def run_case(work_root, source_prefix, address, label, key, key_file):
    try:
        server = OwnAddressServer((address, 0), ExactHandler)
    except OSError:
        if label == "private":
            raise PrivateUnavailable("private_bind_unavailable") from None
        raise
    server.lock = threading.Lock()
    server.key, server.model, server.effort, server.mode = key, "n1c-synthetic", None, "ordinary"
    server.workspace, server.marker = work_root, "unused-synthetic-marker"
    server.records, server.tool_rounds, server.failure, server.received = [], 0, None, 0
    server.expected_host = address + ":" + str(server.server_port)
    base = "http://" + server.expected_host + "/v1"
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    native_run_started = False
    try:
        prefix = work_root / (label + "-prefix")
        offline_bootstrap(prefix, base, key_file, source_prefix)
        workspace = work_root / (label + "-workspace")
        workspace.mkdir(mode=0o700)
        prompt = work_root / (label + "-prompt.txt")
        write_new(prompt, b"Reply with a short greeting without using tools.\n")
        env = isolated_env(prefix)
        require("NODE_TLS_REJECT_UNAUTHORIZED" not in env, "tls_bypass_environment_forbidden")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        launcher = prefix / "bin" / "opencode-client"
        child([sys.executable, str(launcher), "--workspace", str(workspace), "check"],
              work_root, env, 60, key)
        native_run_started = True
        output = child([sys.executable, str(launcher), "--workspace", str(workspace),
                        "--prompt-file", str(prompt), "run"], work_root, env, 60, key)
        require(server.failure is None, server.failure or "server_failure")
        events = [json.loads(line) for line in output.splitlines() if line.strip()]
        require(not any(event.get("type") == "error" for event in events), "opencode_error_event")
        require(any(event.get("type") == "text" and event.get("part", {}).get("text")
                    == "A2O_SYNTHETIC_DONE" for event in events), "missing_final_text_event")
        require(bool(server.records) and all(record["authenticated"] for record in server.records),
                "authenticated_request_missing")
        require(not list(workspace.iterdir()), "workspace_mutated")
        return {"status": "PASS", "base_url": base, "exact_requested_url": base + "/chat/completions",
                "host_and_path_checked": True, "synthetic_bearer_checked": True,
                "request_count": len(server.records), "client_config_check": "PASS",
                "native_version_check": "PASS", "tls_bypass_enabled": False}
    except FixtureError as error:
        # A failed URL/header/auth check is a real FAIL. Only an unavailable
        # native transport with no request reaching this server is NOT_TESTED.
        if (label == "private" and native_run_started and not server.received
                and server.failure is None and str(error) == "child_timeout"):
            raise PrivateUnavailable("native_private_timeout_no_requests") from None
        raise
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        require(not thread.is_alive(), "server_thread_survived_cleanup")


def run_fixture(work_root, source_prefix, private_address):
    # Fail before outputs, bootstrap, or listening if the caller selects another host.
    address = confirm_own_private_ipv4(private_address)
    repo = CLIENT.parents[1]
    require(work_root != repo and repo not in work_root.parents
            and not any((parent / ".git").exists() for parent in work_root.parents),
            "work_root_must_be_outside_git")
    require(not work_root.exists() and not work_root.is_symlink(), "work_root_must_be_new")
    require(work_root.parent.is_dir(), "work_root_parent_missing")
    os.umask(0o077)
    work_root.mkdir(mode=0o700)
    private_dir(work_root)
    key = secrets.token_hex(32).encode("ascii")
    key_file = work_root / "disposable-key"
    write_new(key_file, key)
    evidence = {"status": "IN_PROGRESS", "client_version": VERSION,
                "claim": "same_worker_actual_client_to_synthetic_server_only",
                "live_llm_acceptance": False, "separate_host_reachability": "NOT_TESTED",
                "dependency_setup": "existing_pinned_tree_copy_into_bootstrap_generated_prefix",
                "own_private_address_confirmed": True}
    try:
        evidence["loopback"] = run_case(work_root, source_prefix, "127.0.0.1", "loopback", key, key_file)
        try:
            evidence["private_ipv4"] = run_case(work_root, source_prefix, address, "private", key, key_file)
        except PrivateUnavailable as error:
            evidence["private_ipv4"] = {"status": "NOT_TESTED", "reason": str(error),
                                        "request_count": 0}
        for path in work_root.rglob("*"):
            if path == key_file or not path.is_file() or path.is_symlink():
                continue
            with path.open("rb") as stream:
                tail = b""
                while block := stream.read(1024 * 1024):
                    require(key not in tail + block, "credential_persisted_outside_key_file")
                    tail = block[-len(key):]
        evidence["credential_scan"] = "PASS"
        evidence["status"] = "PASS" if evidence["private_ipv4"]["status"] == "PASS" else "PARTIAL"
        return evidence
    finally:
        key_file.unlink(missing_ok=True)
        evidence["synthetic_key_removed"] = not key_file.exists()
        if evidence["status"] == "IN_PROGRESS":
            evidence["status"] = "FAIL"
        write_new(work_root / "wire-evidence.json", json_bytes(evidence))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", required=True, help="New absolute private directory outside Git")
    parser.add_argument("--source-prefix", required=True, help="Existing pinned dependency prefix, read-only source")
    parser.add_argument("--private-address", required=True, help="This Mac worker's own canonical RFC1918 IPv4")
    args = parser.parse_args()
    try:
        evidence = run_fixture(absolute_path(args.work_root), absolute_path(args.source_prefix), args.private_address)
        print(json.dumps(evidence, indent=2))
        return 0 if evidence["status"] == "PASS" else 2
    except Exception as error:
        print("FAIL: " + (str(error) if isinstance(error, FixtureError) else "fixture_error_details_withheld"),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
