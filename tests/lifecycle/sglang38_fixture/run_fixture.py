#!/usr/bin/env python3
"""Run the reviewed Q38S auth fixture against an already installed pinned image.

This helper never pulls an image. It accepts no production model/key mounts,
GPUs, network, additional environment, commands, or flags. Run storage guards
before and after this separately authorized worker1 gate. --output must be a
new JSON file beneath an existing protected registered data-root directory on
a filesystem distinct from /. Registration is the caller's L1 responsibility.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


IMAGE_ID = "sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813"
IMAGE_REFERENCE = "lmsysorg/sglang@sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262"
SOURCE_REVISION = "0bcd822377da7b5718e674eaf9c870d349424dd1"
CHECKS = (
    "native_routes_and_final_chain", "native_prepare_and_normalization",
    "health_starting_503_up_200", "sentinel_absence", "injection_failure_child_cleanup",
    "spawn_import", "unsupported_modes", "raw_resolved_workerargs_sentinel_absence",
    "native_sse_disconnect", "ordinary_http_auth", "server_info_sentinel_absence",
    "websocket_denial", "native_freeze_gc_has_no_key", "warmup_failure_and_timeout_cleanup",
    "native_false_warmup_not_ready", "native_parser_template_synthetic",
)


class FixtureError(Exception):
    """Only fixed codes may leave this driver."""


def require(value, code):
    if not value:
        raise FixtureError(code)


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise FixtureError("arguments_invalid")


def parse_options(argv):
    parser = Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def read_provenance(repo):
    require(repo.is_absolute() and repo.resolve() == repo and repo.is_dir(),
            "repository_path_invalid")
    require(re.fullmatch(r"/[A-Za-z0-9_./ -]+", str(repo)) is not None,
            "repository_mount_syntax_invalid")
    root = repo / "tests/lifecycle/sglang38_fixture"
    expected = json.loads((root / "provenance.json").read_text())
    require(expected["image_id"] == IMAGE_ID
            and expected["image_reference"] == IMAGE_REFERENCE
            and expected["source_revision"] == SOURCE_REVISION,
            "provenance_identity_mismatch")
    require(expected["launcher_path"] == "scripts/runtime/sglang38_file_auth.py",
            "launcher_path_invalid")
    launcher_path = repo / expected["launcher_path"]
    require(hashlib.sha256(launcher_path.read_bytes()).hexdigest() == expected["launcher_sha256"],
            "launcher_hash_mismatch")
    require(set(expected["fixture_sha256"]) == {"run_fixture.py", "run_pinned_image.py", "auth_native.py", "chat_template.jinja"},
            "fixture_manifest_invalid")
    for name, identity in expected["fixture_sha256"].items():
        require(hashlib.sha256((root / name).read_bytes()).hexdigest() == identity,
                "fixture_hash_mismatch")
    spec = importlib.util.spec_from_file_location("q38s_fixture_launcher_config", launcher_path)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    return expected, launcher.CACHE_ENVIRONMENT


def verify_image(inspected):
    require(isinstance(inspected, list) and len(inspected) == 1, "image_inspect_invalid")
    image = inspected[0]
    require(isinstance(image, dict), "image_inspect_invalid")
    digests = image.get("RepoDigests")
    require(isinstance(digests, list) and all(isinstance(item, str) for item in digests),
            "image_inspect_invalid")
    require(image.get("Id") == IMAGE_ID and IMAGE_REFERENCE in digests,
            "image_digest_identity_mismatch")
    require(image.get("Os") == "linux" and image.get("Architecture") == "amd64",
            "image_platform_mismatch")
    labels = image.get("Config", {}).get("Labels", {})
    require(labels.get("org.opencontainers.image.revision") == SOURCE_REVISION,
            "image_revision_mismatch")
    return {"image_id": IMAGE_ID, "image_reference": IMAGE_REFERENCE,
            "source_revision": SOURCE_REVISION, "os": "linux", "architecture": "amd64"}


def docker_command(repo, cache_environment, context):
    require(context in (131072, 262144), "context_invalid")
    require(re.fullmatch(r"/[A-Za-z0-9_./ -]+", str(repo)) is not None,
            "repository_mount_syntax_invalid")
    command = ["docker", "run", "--rm", "--pull=never", "--network", "none",
               "--runtime", "runc", "--log-driver", "none",
               "--env", "NVIDIA_VISIBLE_DEVICES=void", "--env", "CUDA_VISIBLE_DEVICES=",
               "--platform", "linux/amd64", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "--pids-limit", "128", "--memory", "8g", "--shm-size", "64m",
               "--user", "0:0", "--workdir", "/cache", "--entrypoint", "python3",
               "--mount", f"type=bind,src={repo},dst=/fixture,readonly",
               "--tmpfs", "/models:rw,nosuid,nodev,noexec,size=8m,mode=0700",
               "--tmpfs", "/run/secrets:rw,nosuid,nodev,noexec,size=1m,mode=0700",
               "--tmpfs", "/cache:rw,nosuid,nodev,size=1g,mode=0700",
               "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m,mode=1777"]
    # No host environment is forwarded and HOME retains the image default.
    for name, value in sorted(cache_environment.items()):
        command += ["--env", f"{name}={value}"]
    return command + [IMAGE_REFERENCE, "-B",
        "/fixture/tests/lifecycle/sglang38_fixture/run_pinned_image.py", "--actual-image",
        "--repo", "/fixture", "--context", str(context)]


def check_native_result(result, provenance, context):
    require(result.get("status") == "PASS_ACTUAL_INSTALLED_SOURCE_FIXTURE"
            and result.get("image_identity_verification") == "HOST_DOCKER_INSPECT_REQUIRED"
            and result.get("configured_context") == context, "native_fixture_did_not_pass")
    require(result.get("image_id_pin") == IMAGE_ID
            and result.get("image_reference") == IMAGE_REFERENCE
            and result.get("source_revision") == SOURCE_REVISION
            and result.get("launcher_sha256") == provenance["launcher_sha256"]
            and result.get("fixture_sha256") == provenance["fixture_sha256"]
            and result.get("source_hashes") == {
                name: item["sha256"] for name, item in provenance["sources"].items()},
            "native_provenance_mismatch")
    require(all(result.get(check) == "PASS" for check in CHECKS), "native_check_failed")
    require(result.get("model_loading") == "STUBBED_NOT_TESTED"
            and result.get("gpu_execution") == "NOT_TESTED"
            and result.get("native_lifespan_model_serving_initialization") == "NOT_TESTED"
            and result.get("live_inference_and_agent_acceptance") == "NOT_TESTED",
            "native_evidence_boundary_missing")


def validate_output_path(path):
    require(path.is_absolute() and path.parent.resolve() == path.parent
            and path.suffix == ".json" and not path.exists() and not path.is_symlink(),
            "output_path_invalid")
    require(path.parent.stat().st_dev != Path("/").stat().st_dev,
            "evidence_on_root_filesystem_refused")
    for ancestor in (path.parent, *path.parent.parents):
        meta = ancestor.lstat()
        require(stat.S_ISDIR(meta.st_mode) and not stat.S_ISLNK(meta.st_mode)
                and meta.st_uid in (0, os.geteuid()) and not meta.st_mode & 0o022,
                "output_ancestor_unprotected")


def write_receipt(output, receipt):
    """Anchor publication to one protected directory; fail on detach/rebinding.

    This is fixture evidence output only. I1c must admit this directory using
    L1's actual registered-root binding before calling this helper. Runtime
    receipt import/publication belongs to that canonical anchored storage API.
    """
    validate_output_path(output)
    directory = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    created = False
    identity = None

    def unchanged():
        before, current = os.fstat(directory), output.parent.stat()
        require((before.st_dev, before.st_ino) == (current.st_dev, current.st_ino),
                "evidence_directory_rebound")

    try:
        validate_output_path(output)
        unchanged()
        fd = os.open(output.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        created = True
        meta = os.fstat(fd)
        identity = (meta.st_dev, meta.st_ino)
        with os.fdopen(fd, "w") as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory)
        unchanged()
    except BaseException:
        if created:
            meta = os.stat(output.name, dir_fd=directory, follow_symlinks=False)
            if (meta.st_dev, meta.st_ino) == identity:
                os.unlink(output.name, dir_fd=directory)
                os.fsync(directory)
        raise
    finally:
        os.close(directory)


def run(repo, output):
    validate_output_path(output)
    provenance, cache_environment = read_provenance(repo)
    inspected = subprocess.run(["docker", "image", "inspect", IMAGE_REFERENCE],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=30, check=False)
    require(inspected.returncode == 0, "pinned_image_not_installed")
    image = verify_image(json.loads(inspected.stdout))
    results = []
    for context in (131072, 262144):
        child = subprocess.run(docker_command(repo, cache_environment, context),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=600, check=False)
        require(child.returncode == 0 and len(child.stdout) <= 131072
                and child.stderr == b"", "actual_image_fixture_failed")
        result = json.loads(child.stdout)
        check_native_result(result, provenance, context)
        results.append(result)
    receipt = {"schema_version": 1, "kind": "q38s_actual_image_auth", "status": "PASS",
        "image_id": IMAGE_ID, "image_reference": IMAGE_REFERENCE,
        "source_revision": SOURCE_REVISION, "launcher_sha256": provenance["launcher_sha256"],
        "fixture_sha256": provenance["fixture_sha256"],
        "source_hashes": {name: item["sha256"] for name, item in provenance["sources"].items()},
        "checks": {check: "PASS" for check in CHECKS}, "contexts": [131072, 262144],
        "image_identity_verification": "HOST_DOCKER_INSPECT_AND_PINNED_RUN",
        "docker_inspect": image, "native_results": results,
        "model_execution": "NOT_TESTED", "native_lifespan": "NOT_TESTED",
        "live_inference_and_agent_acceptance": "NOT_TESTED"}
    write_receipt(output, receipt)
    return receipt


def main(argv=None):
    try:
        options = parse_options(sys.argv[1:] if argv is None else argv)
        receipt = run(options.repo, options.output)
        print(json.dumps({"status": receipt["status"], "kind": receipt["kind"],
                          "model_execution": "NOT_TESTED"}, sort_keys=True))
        return 0
    except Exception:
        # Docker/native exception text may contain environment or backend data.
        print(json.dumps({"status": "FAIL", "code": "q38s_image_fixture_failed"}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
