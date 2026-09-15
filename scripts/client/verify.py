#!/usr/bin/env python3
"""Run the fixed ordinary-user OpenCode verification in a new private directory.

This is client evidence, not an installer receipt or overall server acceptance.
"""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import sys
import time
import urllib.request
import urllib.error
import uuid

sys.dont_write_bytecode = True

from client_common import (ClientError, KEY_ENV, PROVIDER, VERSION, binary_path,
                           isolated_env, json_bytes, load_key, write_new)
from verify_events import FIXED_ARGV, FIXED_COMMAND, parse_events, run_bounded
from verify_integrity import verify_client

SOURCE = Path(__file__).resolve().parent
SOURCE_FILES = tuple(sorted((
    "bootstrap.py", "client_common.py", "launch.py", "package.json", "package-lock.json",
    "verify.py", "verify_events.py", "verify_integrity.py",
    "verifier_fixture/text_utils.py", "verifier_fixture/test_text_utils.py",
)))
MAX_OUTPUT = 8 * 1024 * 1024


class VerifyError(Exception):
    """Only fixed error codes may cross the report boundary."""


def require(condition, code):
    if not condition:
        raise VerifyError(code)


def digest(value):
    # Identical serialization to core.digest, without installer dependencies.
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def source_manifest():
    files = {"scripts/client/" + name: sha((SOURCE / name).read_bytes()) for name in SOURCE_FILES}
    return {"files": files, "source_sha256": digest(files),
            "test_sha256": sha((SOURCE / "verifier_fixture/test_text_utils.py").read_bytes()),
            "test_command_sha256": digest(list(FIXED_ARGV))}


def safe_path(value, *, fresh=False):
    path = Path(value)
    require(path.is_absolute() and ".." not in path.parts and not any(ord(c) < 32 for c in str(path)), "unsafe_path")
    for parent in reversed((path, *path.parents)):
        if not parent.exists() and not parent.is_symlink():
            continue
        info = parent.lstat()
        require(not stat.S_ISLNK(info.st_mode), "symlink_path")
        require(info.st_uid in (0, os.getuid()) and not info.st_mode & 0o022, "unsafe_path_ancestor")
    if fresh:
        require(not path.exists() and not path.is_symlink() and path.parent.is_dir(), "output_must_be_fresh")
        # No raw event artifacts or disposable model workspaces inside source Git.
        require(not any((parent / ".git").exists() for parent in path.parents), "output_inside_repository")
    return path


def read_owned(path, limit=1024 * 1024):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1
                and not info.st_mode & 0o077, "unsafe_workspace_file")
        data = stream.read(limit + 1)
        require(len(data) <= limit, "workspace_file_limit")
        return data


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise VerifyError("endpoint_redirect_denied")


def observe_model(settings, key, timeout):
    # No environment proxy, redirect, alternate endpoint, generation or raw-body option.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(settings["base_url"] + "/models",
                                     headers={"Authorization": "Bearer " + key})
    with opener.open(request, timeout=min(15, timeout)) as response:
        require(response.status == 200, "model_identity_http_failure")
        body = response.read(1024 * 1024 + 1)
    require(len(body) <= 1024 * 1024, "model_identity_output_limit")
    value = json.loads(body)
    require(isinstance(value, dict) and isinstance(value.get("data"), list), "model_identity_malformed")
    ids = [item.get("id") for item in value["data"] if isinstance(item, dict)]
    require(ids == [settings["model"]], "model_identity_mismatch")
    return settings["model"]


def initial_classification(result):
    output = (result["stdout"] + result["stderr"]).decode("utf-8", "replace")
    match = re.search(r"FAILED \(failures=(\d+)\)\s*$", output)
    imports = len(re.findall(r"(?:ImportError|ModuleNotFoundError):", output))
    failures = int(match.group(1)) if match else 0
    okay = (result["exit_code"] > 0 and failures == 5 and imports == 0
            and "Ran 3 tests" in output and not result["timed_out"]
            and not result["output_limited"] and result["process_tree_reaped"])
    return {"classification": "assertion_failure" if okay else "unexpected_baseline",
            "assertion_failures": failures, "import_errors": imports, "exit_code": result["exit_code"]}


def passing_test(result):
    output = (result["stdout"] + result["stderr"]).decode("utf-8", "replace")
    return (result["exit_code"] == 0 and re.search(r"Ran 3 tests\b", output) is not None
            and re.search(r"\nOK\s*$", output) is not None and not result["timed_out"]
            and not result["output_limited"] and result["process_tree_reaped"])


def clean_process(result):
    return {key: value for key, value in result.items() if key not in ("stdout", "stderr")}


def scrub(value, secrets):
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    if isinstance(value, str):
        for secret in sorted(set(secrets), key=len, reverse=True):
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, dict):
        return {key: scrub(item, secrets) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(item, secrets) for item in value]
    return value



def run_process(*args, **kwargs):
    """The child supervisor owns its timeout and must finish cleanup uninterrupted.

    Temporarily suspend the outer HTTP/I/O alarm. Every production call passes
    the remaining overall budget to run_bounded. If that budget expires, retain
    its partial output and cleanup result before the next remaining() refusal.
    """
    timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()
    if timer[0]:
        signal.setitimer(signal.ITIMER_REAL, 0)
    try:
        return run_bounded(*args, **kwargs)
    finally:
        left = timer[0] - (time.monotonic() - started)
        if timer[0] and left > 0:
            signal.setitimer(signal.ITIMER_REAL, left, timer[1])


def versions(prefix, workspace, env, remaining):
    values = {}
    for name, command in (("node", [shutil.which("node") or "node", "--version"]),
                          ("npm", [shutil.which("npm") or "npm", "--version"]),
                          ("opencode", [str(binary_path(prefix)), "--version"])):
        result = run_process(command, workspace, env, timeout=min(30, remaining()), max_output=65536)
        require(result["exit_code"] == 0 and result["process_tree_reaped"] and not result["output_limited"]
                and not result["timed_out"], "client_version_failed")
        value = result["stdout"].decode("ascii").strip()
        require(re.fullmatch(r"v?\d+\.\d+\.\d+", value) is not None, "client_version_malformed")
        values[name + "_version"] = value
    require(values["opencode_version"] == VERSION, "client_version_mismatch")
    # verify_client checks installed plugin bytes against the reviewed package lock.
    plugin = prefix / "xdg/config/opencode/node_modules/@opencode-ai/plugin/package.json"
    values["plugin_version"] = json.loads(plugin.read_bytes())["version"]
    return values


def verify(prefix, output_dir, timeout=1800):
    os.umask(0o077)
    require(os.getuid() > 0, "ordinary_user_required")
    require(type(timeout) is int and 1 <= timeout <= 1800, "timeout_out_of_range")
    prefix = safe_path(prefix)
    output_dir = safe_path(output_dir, fresh=True)
    require(prefix not in output_dir.parents, "output_inside_prefix")
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), "conflicting_process_timer")
    output_dir.mkdir(mode=0o700)
    deadline = time.monotonic() + timeout
    def remaining():
        value = deadline - time.monotonic()
        require(value > 0, "overall_timeout")
        return value
    report = {"schema_version": 1, "evidence_class": "ordinary_client_verification", "status": "FAIL",
              "run_id": str(uuid.uuid4()), "client_uid": os.getuid(), "started": now(),
              "checks": {name: False for name in (
                  "file_reads", "implementation_edit", "exact_test_command", "passing_tool_result",
                  "final_response", "immutable_tests", "independent_final_rerun", "process_tree_reaped")},
              "failures": [], "protocol_acceptance": "NOT_ASSESSED", "server_readiness": "NOT_ASSESSED"}
    raw, secrets = {}, []
    previous_handler = signal.getsignal(signal.SIGALRM)
    def expired(signum, frame):
        raise VerifyError("overall_timeout")
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        report["artifacts"] = source_manifest()
        report["phase"] = "client_integrity"
        settings, integrity = verify_client(prefix, timeout=min(30, remaining()))
        report["client_integrity"] = integrity
        require(settings["auth"]["kind"] in ("file", "env"), "authenticated_prefix_required")
        report.update({"endpoint": settings["base_url"], "model": settings["model"],
                       "settings": {name: settings.get(name) for name in
                                    ("context_tokens", "output_tokens", "reasoning_effort")}})
        workspace = output_dir / "workspace"
        workspace.mkdir(mode=0o700)
        for name in ("text_utils.py", "test_text_utils.py"):
            write_new(workspace / name, (SOURCE / "verifier_fixture" / name).read_bytes())
        before = {path.name: sha(read_owned(path)) for path in workspace.iterdir()}
        report["tests_before_sha256"] = before["test_text_utils.py"]
        env = isolated_env(prefix)
        report["phase"] = "client_versions"
        report["client_versions"] = versions(prefix, workspace, env, remaining)
        report["phase"] = "initial_test"
        initial = run_process(list(FIXED_ARGV), workspace, env, timeout=min(30, remaining()), max_output=65536)
        raw["initial_test"] = initial
        report["initial_test"] = initial_classification(initial)
        require(report["initial_test"]["classification"] == "assertion_failure", "baseline_not_expected_assertions")
        report["phase"] = "credential_and_model_identity_before"
        encoded_key = load_key(settings["auth"])
        key = json.loads('"' + encoded_key + '"')
        secrets = [key, encoded_key]
        env[KEY_ENV] = encoded_key
        report["observed_model_before"] = observe_model(settings, key, remaining())
        env["OPENCODE_PERMISSION"] = json.dumps({
            "*": "deny", "read": "allow", "glob": "allow", "grep": "allow", "external_directory": "deny",
            # Pinned 1.18.31 asks edit permission relative to context.worktree.
            # For this deliberately non-Git workspace that worktree is POSIX /.
            "edit": {"*": "deny", str((workspace / "text_utils.py").relative_to("/")): "allow"},
            "bash": {"*": "deny", FIXED_COMMAND: "allow"},
        })
        prompt = ("Read BOTH text_utils.py and test_text_utils.py in the current workspace. "
                  "Fix word_count in text_utils.py so it counts words separated by any whitespace "
                  "and returns zero for empty input. Edit ONLY text_utils.py. Do not modify tests or add files. "
                  "After editing, run exactly `" + FIXED_COMMAND + "` in the current workspace using bash. "
                  "Observe its passing test result, then give a brief final answer. Use the exact existing filenames.").encode()
        report["phase"] = "opencode_agent"
        result = run_process([str(binary_path(prefix)), "run", "--format", "json", "--model",
                              PROVIDER + "/" + settings["model"]], workspace, env, input=prompt,
                             timeout=remaining(), max_output=MAX_OUTPUT)
        raw["opencode"] = result
        report["process"] = clean_process(result)
        native = parse_events(result["stdout"], workspace)
        report["native"] = native
        report["checks"].update(native["checks"])
        report["failures"].extend(native["failures"])
        report["checks"]["process_tree_reaped"] = result["process_tree_reaped"]
        # All of these are independent host observations after the native process is gone.
        require(result["process_tree_reaped"], "process_cleanup_failed")
        require(set(path.name for path in workspace.iterdir()) == set(before), "workspace_extra_or_missing_files")
        after = {path.name: sha(read_owned(path)) for path in workspace.iterdir()}
        report["tests_after_sha256"] = after["test_text_utils.py"]
        report["checks"]["immutable_tests"] = before["test_text_utils.py"] == after["test_text_utils.py"]
        report["implementation_hashes"] = {"before": before["text_utils.py"], "after": after["text_utils.py"]}
        report["checks"]["implementation_edit"] &= before["text_utils.py"] != after["text_utils.py"]
        require(report["checks"]["immutable_tests"], "immutable_tests_changed")
        # The independent test process does not need the inference credential.
        env.pop(KEY_ENV, None)
        # Never run a modified test; only the exact immutable reviewed bytes execute.
        report["phase"] = "independent_final_test"
        final = run_process(list(FIXED_ARGV), workspace, env, timeout=min(30, remaining()), max_output=65536)
        raw["final_test"] = final
        report["final_test"] = clean_process(final)
        report["checks"]["independent_final_rerun"] = passing_test(final)
        report["checks"]["process_tree_reaped"] &= final["process_tree_reaped"]
        require(set(path.name for path in workspace.iterdir()) == set(before), "workspace_changed_during_final_test")
        report["tests_after_sha256"] = sha(read_owned(workspace / "test_text_utils.py"))
        report["checks"]["immutable_tests"] &= report["tests_after_sha256"] == before["test_text_utils.py"]
        require(report["checks"]["immutable_tests"], "immutable_tests_changed_during_final_test")
        require(sha(read_owned(workspace / "text_utils.py")) == after["text_utils.py"], "implementation_changed_during_final_test")
        report["phase"] = "model_identity_and_integrity_after"
        report["observed_model_after"] = observe_model(settings, key, remaining())
        verify_client(prefix, timeout=min(30, remaining()))
        require(source_manifest() == report["artifacts"], "verifier_source_changed")
        require(not result["timed_out"], "opencode_timeout")
        require(not result["output_limited"], "opencode_output_limit")
        require(result["exit_code"] == 0, "opencode_process_failed")
        require(native["result"] == "pass" and all(report["checks"].values()), "client_checks_failed")
        report["status"] = "PASS"
        report["phase"] = "complete"
    except Exception as error:
        # Neither library exceptions nor remote/native text are diagnostic codes.
        code = str(error) if isinstance(error, VerifyError) else "client_verification_failed"
        if isinstance(error, urllib.error.HTTPError):
            code = "model_identity_http_failure"
            report["http_status"] = error.code
        elif isinstance(error, urllib.error.URLError):
            code = "model_identity_transport_failure"
            number = getattr(error.reason, "errno", None)
            if type(number) is int:
                report["transport_errno"] = number
            # Local Python/macOS privacy denial is not evidence of a server or firewall failure.
        report["failures"].append(code)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        report["finished"] = now()
        artifact = json_bytes(scrub(raw, secrets))
        report["raw_evidence_sha256"] = sha(artifact)
        report["raw_evidence_file"] = "raw-evidence.json"
        write_new(output_dir / "raw-evidence.json", artifact)
        write_new(output_dir / "report.json", json_bytes(scrub(report, secrets)))
    return report


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--prefix", required=True, help="Existing configured private OpenCode prefix")
    result.add_argument("--output-dir", required=True, help="Fresh absolute output directory outside Git and the prefix")
    result.add_argument("--timeout-seconds", type=int, default=1800, help="Overall wall-time budget, 1..1800 seconds")
    return result


def main():
    args = parser().parse_args()
    try:
        report = verify(args.prefix, args.output_dir, args.timeout_seconds)
        print(json.dumps({"status": report["status"], "report": str(Path(args.output_dir) / "report.json")}))
        return 0 if report["status"] == "PASS" else 1
    except Exception:
        print("FAIL: verifier_preflight_failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
