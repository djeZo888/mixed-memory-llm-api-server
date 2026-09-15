#!/usr/bin/env python3
"""Source-bound I2S evidence on one explicitly guarded disposable hosted VM."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
CONTEXT_KEYS = ("GITHUB_ACTIONS", "RUNNER_ENVIRONMENT", "GITHUB_REPOSITORY", "GITHUB_SHA",
                "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "I2P_DISPOSABLE_ACK", "RUNNER_TEMP",
                "ImageOS", "ImageVersion")
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1"}
PLAN = {
    "scope": "actual_owned_loop_and_private_scratch_mounts_only",
    "shipped": "tests/install/loop_disk_transaction.sh --dry-run then --apply, unchanged",
    "loop_backing_bytes_each": 256 * 1024**2,
    "aggregate_backing_budget_bytes": 2 * 1024**3,
    "allocation": "sequential internally allocated protected /run files; no device argument",
    "writer": "own blank tmpfs and same-device scratch binds in private mount namespace",
    "process": "exact-owned disposable DiskIO adapter child, separate from real tool death",
    "cleanup": "identity checked exact resources only; uncertainty preserves state and fails",
    "not_tested": ["production root exclusion", "physical 4Kn", "I1O canonical admission",
                   "I1O autonomous child deadline", "I1c role-aware persistence/conversion",
                   "real package installation", "GPU installation", "model/image installation", "reboot"],
}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def source_manifest():
    paths = [ROOT / "tests/install/loop_disk_transaction.sh", ROOT / "tests/install/loop_disk_transaction.py",
             ROOT / ".github/workflows/i2s-linux.yml"]
    for directory in ("scripts/validation/i2s", "scripts/validation/i2p", "scripts/install", "scripts/lifecycle", "scripts/common"):
        paths.extend((ROOT / directory).rglob("*.py"))
    paths.extend((ROOT / "tests/validation").glob("test_i2s*.py"))
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(paths)) if p.is_file()}


def write_json(path, data):
    # The output directory is newly allocated 0700 under the guarded runner temp.
    if path.is_symlink():
        raise RuntimeError("refuse_output_symlink")
    with path.open("w") as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write("\n")


def bounded(argv, *, env, timeout=180, limit=65536):
    """Bound output/time without unsafe tree killing on uncertain disk ownership.

    On deadline/output breach, stop the matrix and preserve state for whole-VM
    disposal. Do not advertise successful owned cleanup or race live disk tools.
    """
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL, env=env, cwd=ROOT)
    poll = selectors.DefaultSelector()
    poll.register(process.stdout, selectors.EVENT_READ)
    output = bytearray()
    deadline = time.monotonic() + timeout
    try:
        while poll.get_map():
            if time.monotonic() >= deadline:
                return {"status": "FAIL", "error": "deadline_ownership_pending_vm_disposal",
                        "pid": process.pid, "cleanup": "INCOMPLETE", "returncode": process.poll()}
            for key, _ in poll.select(min(0.25, max(0, deadline - time.monotonic()))):
                chunk = os.read(key.fd, 4096)
                if not chunk:
                    poll.unregister(key.fileobj)
                else:
                    output.extend(chunk)
                    if len(output) > limit:
                        return {"status": "FAIL", "error": "output_bound_ownership_pending_vm_disposal",
                                "pid": process.pid, "cleanup": "INCOMPLETE", "returncode": process.poll()}
        try:
            code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            return {"status": "FAIL", "error": "deadline_ownership_pending_vm_disposal",
                    "pid": process.pid, "cleanup": "INCOMPLETE", "returncode": None}
        return {"status": "PASS" if code == 0 else "FAIL", "returncode": code,
                "output": output.decode("utf-8", errors="replace")}
    finally:
        poll.close()
        process.stdout.close()


def safe_environment(context):
    return dict(ENV, **{key: context[key] for key in CONTEXT_KEYS})


def cleanup_uncertain(value):
    if isinstance(value, dict):
        value = value.get("status", "UNKNOWN")
    return value != "PASS"


def namespace_cleanup_confirmed(result):
    return (result.get("stop_reason") is None and
            all(isinstance(result.get(key), dict)
                and not cleanup_uncertain(result[key].get("cleanup", "UNKNOWN"))
                for key in ("writer", "process")))


def loop_inventory():
    # Read only loop associations; never enumerate a physical formatting candidate.
    result = subprocess.run(["losetup", "--list", "--json", "--output", "NAME,BACK-FILE,BACK-INO,BACK-MAJ:MIN,OFFSET,SIZELIMIT"],
                            capture_output=True, text=True, timeout=10, env=ENV, check=True)
    return json.loads(result.stdout).get("loopdevices", [])


def namespace_child(output_dir):
    parent = os.environ.get("I2S_PARENT_NAMESPACE", "")
    if not parent or os.readlink("/proc/self/ns/mnt") == parent:
        raise RuntimeError("private_mount_namespace_required")
    propagation = subprocess.run(["findmnt", "--raw", "--noheadings", "--output", "PROPAGATION", "--target", "/"],
                                 capture_output=True, text=True, timeout=10, check=True, env=ENV)
    if propagation.stdout.strip() != "private":
        raise RuntimeError("private_propagation_required")
    result = {"status": "FAIL", "namespace": os.readlink("/proc/self/ns/mnt"), "parent_namespace": parent}
    # Independent cases are still executed after an expected production failure.
    # Each probe owns its cleanup. Uncertain cleanup stops subsequent probes.
    for key, filename in (("writer", "writer_probe.py"), ("process", "process_probe.py")):
        try:
            module = load(Path(__file__).with_name(filename), "i2s_" + key)
            result[key] = module.run_probe()
        except Exception as exc:
            result[key] = {"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)[:500],
                           "cleanup": "UNKNOWN"}
        write_json(output_dir / "namespace.json", result)
        if cleanup_uncertain(result[key].get("cleanup", "UNKNOWN")):
            result["stop_reason"] = "probe_ownership_unresolved"
            write_json(output_dir / "namespace.json", result)
            return 1
    result["status"] = "PASS" if all(result[k].get("status") == "PASS" for k in ("writer", "process")) else "FAIL"
    write_json(output_dir / "namespace.json", result)
    return 0 if result["status"] == "PASS" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--namespace-apply", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps(PLAN, indent=2))
        return 0
    context = {key: os.environ.get(key, "") for key in CONTEXT_KEYS}
    i2p = load(ROOT / "scripts/validation/i2p/run.py", "i2s_i2p_guard")
    i2p.validate_context(context)
    temp = Path(context["RUNNER_TEMP"])
    if not temp.is_absolute() or not temp.is_dir() or temp.is_symlink():
        raise RuntimeError("unsafe_runner_temp")
    if args.output_dir is None or args.output_dir.parent != temp or args.output_dir.is_symlink():
        raise RuntimeError("output_must_be_direct_runner_temp_child")
    if args.namespace_apply:
        i2p.capability(temp)
        if args.output_dir.stat().st_uid != 0 or args.output_dir.stat().st_mode & 0o077:
            raise RuntimeError("unsafe_private_output")
        return namespace_child(args.output_dir)
    os.umask(0o077)
    args.output_dir.mkdir(mode=0o700)
    evidence = {"schema": 1, "status": "FAIL", "source_sha": context["GITHUB_SHA"],
                "github_run_id": context["GITHUB_RUN_ID"], "github_run_attempt": context["GITHUB_RUN_ATTEMPT"],
                "image_os": context["ImageOS"], "image_version": context["ImageVersion"],
                "capability": {"status": "NOT_TESTED"}, "plan": PLAN, "not_tested": PLAN["not_tested"],
                "shipped": {"status": "NOT_TESTED"}, "extended_loop": {"status": "NOT_TESTED"},
                "namespace_probes": {"status": "NOT_TESTED"}}
    write_json(args.output_dir / "plan.json", PLAN)
    write_json(args.output_dir / "source-manifest.json", source_manifest())
    started = time.monotonic()
    env = safe_environment(context)
    try:
        evidence["capability"] = i2p.capability(temp)
        actual_sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        if actual_sha != context["GITHUB_SHA"]:
            raise RuntimeError("source_sha_mismatch")
        tools = {"sfdisk": ["sfdisk", "--version"], "losetup": ["losetup", "--version"],
                 "mkfs.ext4": ["mkfs.ext4", "-V"], "e2fsck": ["e2fsck", "-V"],
                 "mount": ["mount", "--version"], "udevadm": ["udevadm", "--version"],
                 "python": ["python3", "--version"]}
        evidence["tool_versions"] = {name: bounded(argv, env=env, timeout=10, limit=4096) for name, argv in tools.items()}
        before_namespace = os.readlink("/proc/self/ns/mnt")
        before_loops = loop_inventory()
        before_scratch = set(Path("/run").glob("i1s-loop-*"))
        wrapper = str(ROOT / "tests/install/loop_disk_transaction.sh")
        evidence["shipped_dry_run"] = bounded(["bash", wrapper, "--dry-run"], env=env, timeout=30)
        write_json(args.output_dir / "evidence.json", evidence)
        if evidence["shipped_dry_run"]["status"] != "PASS":
            raise RuntimeError("shipped_prerequisite_blocker_no_apply")
        evidence["shipped"] = bounded(["bash", wrapper, "--apply"], env=env, timeout=240)
        after_loops = loop_inventory()
        new_scratch = sorted(str(p) for p in set(Path("/run").glob("i1s-loop-*")) - before_scratch)
        evidence["shipped_cleanup_observer"] = {
            "parent_namespace_unchanged": os.readlink("/proc/self/ns/mnt") == before_namespace,
            "loop_associations_unchanged": before_loops == after_loops,
            "remaining_new_scratch": new_scratch,
            "scope": "independent parent-namespace observer; no cleanup mutations"}
        write_json(args.output_dir / "evidence.json", evidence)
        if evidence["shipped"].get("cleanup") == "INCOMPLETE" or before_loops != after_loops or new_scratch:
            raise RuntimeError("shipped_cleanup_unresolved_stop_matrix")
        env["I2S_PARENT_NAMESPACE"] = before_namespace
        namespace = bounded(["unshare", "--mount", "--propagation", "private", "python3", "-B", str(Path(__file__).resolve()),
                             "--namespace-apply", "--output-dir", str(args.output_dir)], env=env, timeout=120)
        evidence["namespace_process"] = namespace
        if (args.output_dir / "namespace.json").is_file():
            evidence["namespace_probes"] = json.loads((args.output_dir / "namespace.json").read_text())
        if namespace.get("cleanup") == "INCOMPLETE":
            raise RuntimeError("namespace_cleanup_unresolved_stop_matrix")
        if not namespace_cleanup_confirmed(evidence["namespace_probes"]):
            raise RuntimeError("probe_cleanup_unresolved_stop_matrix")
        loop_command = ["unshare", "--mount", "--propagation", "private", "python3", "-I", "-B",
                        str(Path(__file__).with_name("loop_matrix.py")), "--apply", "--output", str(args.output_dir / "loop-matrix.json")]
        evidence["extended_loop_process"] = bounded(loop_command, env=env, timeout=420)
        if (args.output_dir / "loop-matrix.json").is_file():
            evidence["extended_loop"] = json.loads((args.output_dir / "loop-matrix.json").read_text())
        evidence["status"] = "PASS" if all(evidence[k].get("status") == "PASS" for k in ("shipped", "namespace_probes", "extended_loop")) else "FAIL"
    except Exception as exc:
        evidence["error_type"] = type(exc).__name__
        evidence["error"] = str(exc)[:500]
    finally:
        evidence["elapsed_seconds"] = round(time.monotonic() - started, 3)
        write_json(args.output_dir / "evidence.json", evidence)
    print("I2S result: " + evidence["status"], flush=True)
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
