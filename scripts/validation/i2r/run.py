#!/usr/bin/env python3
"""Actual package ownership proof with synthetic packages on hosted Ubuntu only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "scripts"))
from validation.i2p.run import capability, validate_context  # reviewed gates; no primitive rerun

PLAN = {
    "scope": "actual_systemd_canonical_lease_synthetic_package",
    "binds": ["/usr/bin/apt-get", "/usr/bin/dpkg"],
    "readonly_binds": True,
    "canonical_lock": "/run/llmctl/lifecycle.lock",
    "cleanup": "exact owned identities; retain fake mounts if scope quiescence unknown",
    "not_tested": ["real_package_installation", "reboot", "GPU_installation",
                   "Docker_daemon_ownership", "agent_readiness",
                   "I1c_scope_storage_lifetime", "I1c_mount_loss_gate_marker_writes"],
}


def safe_code(exc):
    code = getattr(exc, "code", "")
    if not re.fullmatch(r"[a-zA-Z0-9_:.-]{1,120}", str(code)):
        code = type(exc).__name__
    return code


def write_json(path, value):
    data = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    if len(data) > 1024 * 1024:
        raise RuntimeError("evidence_size_bound")
    path.write_bytes(data)
    path.chmod(0o600)


def manifest(repo):
    paths = []
    for relative in ("scripts", "configs"):
        for path in sorted((repo / relative).rglob("*")):
            if "__pycache__" in path.parts:
                continue
            if path.is_symlink():
                raise RuntimeError("source_symlink_refused")
            if path.is_file():
                paths.append(path)
    paths += [repo / ".github/workflows/i2r-linux.yml"]
    paths += sorted((repo / "tests/validation").glob("test_i2r*.py"))
    return {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths}


def seal_source(repo, source):
    before = manifest(repo)
    source.mkdir(mode=0o700)
    for relative, expected in before.items():
        dest = source / relative
        dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with dest.open("xb") as stream:
            stream.write((repo / relative).read_bytes())
        dest.chmod(0o600)
        if hashlib.sha256(dest.read_bytes()).hexdigest() != expected:
            raise RuntimeError("sealed_source_hash_mismatch")
    if manifest(repo) != before or manifest(source) != before:
        raise RuntimeError("source_changed_during_seal")
    return before


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps(PLAN, sort_keys=True, indent=2))
        return 0
    keys = ("GITHUB_ACTIONS", "RUNNER_ENVIRONMENT", "GITHUB_REPOSITORY", "GITHUB_SHA",
            "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "I2P_DISPOSABLE_ACK", "RUNNER_TEMP",
            "ImageOS", "ImageVersion", "I2R_BIND_ACK")
    context = {key: os.environ.get(key, "") for key in keys}
    validate_context(context)
    if context["I2R_BIND_ACK"] != "readonly-fake-apt-dpkg-on-ephemeral-ubuntu-only":
        raise RuntimeError("requires_exact_i2r_bind_ack")
    temp = Path(context["RUNNER_TEMP"])
    if not temp.is_absolute() or temp.is_symlink() or not temp.is_dir():
        raise RuntimeError("unsafe_runner_temp")
    if (args.output_dir is None or args.output_dir.parent.resolve() != temp.resolve()
            or args.output_dir.exists() or args.output_dir.is_symlink()):
        raise RuntimeError("output_must_be_new_under_runner_temp")
    # No mutation before the reviewed capability gate.
    observed = capability(temp)
    if Path("/run/llmctl").exists() or Path("/run/llmctl").is_symlink():
        raise RuntimeError("refuse_preexisting_canonical_lock_namespace")
    os.umask(0o077)
    args.output_dir.mkdir(mode=0o700)
    workdir = Path("/run") / ("i2r-" + uuid.uuid4().hex)
    workdir.mkdir(mode=0o700)
    evidence = {
        "schema": 1, "status": "FAIL", "source_sha": context["GITHUB_SHA"],
        "github_run_id": context["GITHUB_RUN_ID"],
        "github_run_attempt": context["GITHUB_RUN_ATTEMPT"],
        "run_url": "https://github.com/" + context["GITHUB_REPOSITORY"]
                   + "/actions/runs/" + context["GITHUB_RUN_ID"],
        "namespace": workdir.name, "capability": observed,
        "image_os": context["ImageOS"], "image_version": context["ImageVersion"],
        "image_immutable_pin": False, "matrix": {"status": "NOT_TESTED"},
        "preparation": {"status": "NOT_TESTED"}, "cleanup": {"status": "NOT_TESTED"},
        "not_tested": PLAN["not_tested"],
    }
    started = time.monotonic()
    fixture = None
    try:
        source = workdir / "source"
        hashes = seal_source(REPO, source)
        write_json(args.output_dir / "source-manifest.json", {
            "source_sha": context["GITHUB_SHA"], "sha256": hashes})
        write_json(args.output_dir / "plan.json", PLAN)
        sys.path.insert(0, str(source / "scripts"))
        sys.path.insert(0, str(source / "scripts/validation/i2r"))
        import guardian
        import matrix
        import preparation
        evidence["cgroup_mount"] = [
            row for row in guardian._mounts()
            if row["target"] == "/sys/fs/cgroup" and row["filesystem"] == "cgroup2"
        ]
        fixture_root = workdir / "fixture"
        fixture_root.mkdir(mode=0o700)
        print("I2R hosted capability PASS; sealed source ready", flush=True)
        with guardian.fake_packages(fixture_root,
                                    cleanup=lambda: matrix.cleanup_owned(fixture_root)) as fixture:
            evidence["preparation"] = preparation.run(fixture_root)
            evidence["matrix"] = matrix.run(fixture_root)
        evidence["cleanup"] = fixture["evidence"]
        if all(evidence[key].get("status") == "PASS"
               for key in ("matrix", "preparation", "cleanup")):
            evidence["status"] = "PASS"
    except BaseException as exc:
        evidence["failure_code"] = safe_code(exc)
        evidence["failure_type"] = type(exc).__name__
    finally:
        if fixture is not None:
            evidence["cleanup"] = fixture["evidence"]
        else:
            # The guardian may have refused or restored partial bindings before
            # yielding. Its bounded private structured evidence still matters.
            saved = workdir / "fixture/fake-packages/bindings.json"
            if saved.is_file() and not saved.is_symlink() and saved.stat().st_size <= 1024 * 1024:
                evidence["cleanup"] = json.loads(saved.read_text())
        evidence["elapsed_seconds"] = round(time.monotonic() - started, 3)
        write_json(args.output_dir / "evidence.json", evidence)
    print("I2R actual systemd + synthetic package result: " + evidence["status"], flush=True)
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
