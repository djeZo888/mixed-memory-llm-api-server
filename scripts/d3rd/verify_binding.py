#!/usr/bin/env python3
"""Read-only D3RD source binding check; no Docker, host access or publication.

This is a bounded consistency check over the reviewed, retained measurement and
source files. It does not authenticate the operator or establish runtime/model
acceptance. Manager consumes a protected operator attestation, not this checker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = "llama-cpp-v0.4.1-d3br"
PROOF = "reports/d3rp-runtime-proof.json"
EVIDENCE = "reports/d3rp-contract-evidence/"
D1 = "configs/runtimes/llama-cpp-v0.4.1-d1.json"
DEPLOYMENTS = (
    "configs/deployments/glm-5.3-ud-q4-k-xl-n76-32k.json",
    "configs/deployments/glm-5.3-ud-q4-k-xl-n76-native1m.json",
)


class BindingError(ValueError):
    """A retained measurement or selected source contract does not agree."""


def require(condition, message):
    if not condition:
        raise BindingError(message)


def read(root: Path, relative: str) -> bytes:
    path = Path(relative)
    require(not path.is_absolute() and ".." not in path.parts, "unsafe evidence path")
    target = root / path
    require(target.is_file() and not target.is_symlink()
            and all(not parent.is_symlink() for parent in target.parents),
            "missing/nonregular/symlink source: " + relative)
    return target.read_bytes()


def digest(root, relative):
    return hashlib.sha256(read(root, relative)).hexdigest()


def document(root, relative):
    return json.loads(read(root, relative))


def verify_measurements(root, proof, runtime):
    """Cross-check retained actual observations against this selected recipe.

    The reviewed input receipt is the trust origin. Hashes establish consistency
    of these delivered bytes, not remote attestation of Docker or the operator.
    """
    def evidence(name):
        path = EVIDENCE + name
        require(path in proof["evidence_sha256"], "unlisted evidence: " + name)
        return read(root, path)

    def record(name):
        return json.loads(evidence(name))

    def sha_manifest(payload):
        rows = {}
        for line in payload.decode().splitlines():
            match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
            require(match is not None, "invalid recipe manifest line")
            digest_value, name = match.groups()
            require(name not in rows, "duplicate recipe manifest entry")
            rows[name] = digest_value
        return rows

    for path, expected in proof["evidence_sha256"].items():
        require(path.startswith(EVIDENCE) and re.fullmatch(r"[0-9a-f]{64}", expected),
                "invalid evidence digest entry")
        require(digest(root, path) == expected, "evidence digest mismatch: " + path)
    required = {"image-identity.json", "llama-server-version.txt", "llama-server-help.txt",
                "llama-server-list-devices.txt", "source-commit.txt", "source-tree.txt",
                "source-provenance.json", "build-recipe-sha256.txt", "CMakeCache.txt",
                "nvcc-version.txt", "build-packages.tsv", "d3b2-build-observation.json",
                "image-index.json", "image-amd64-manifest.json", "host-build-recipe-sha256.txt",
                "source-preflight.json", "registered-build-before.json", "registered-build-after.json",
                "guard-close.json", "VM-GUARDS.json"}
    require({EVIDENCE + name for name in required} == proof["evidence_sha256"].keys(),
            "selected actual evidence set mismatch")
    require(proof["input_proof"]["sha256"] ==
            "1d500eae56d6e777b944b2492071c8b3dd28ea350b04f5c72da5b7bd70d052c9",
            "unreviewed input proof receipt")

    reviewed = document(root, "reports/d3br-evidence/provenance.json")
    manifest = document(root, "containers/llama-cpp/d3p-source.json")
    require(manifest == reviewed["source"], "reviewed source manifest mismatch")
    expected_source = dict(manifest, source_state="verified-patched", derived_commit=None)
    source = record("source-provenance.json")
    require(source == expected_source and proof["source"] == source,
            "patched source provenance mismatch")
    require(runtime["source_derivation"] == dict(source, upstream_source_clean=True),
            "runtime source derivation mismatch")
    require(evidence("source-commit.txt").decode().strip() == manifest["upstream_commit"]
            and evidence("source-tree.txt").decode().strip() == manifest["derived_tree"],
            "source commit/tree mismatch")
    require(proof["source_commit"] == runtime["source_revision"] == manifest["upstream_commit"]
            and proof["source_release"] == runtime["source_release"] == "v0.4.1"
            and proof["derived_tree"] == manifest["derived_tree"]
            and proof["upstream_tree"] == manifest["upstream_tree"]
            and proof["patch_sha256"] == manifest["patch_sha256"]
            and proof["derived_commit"] is None
            and proof["source_state"] == "verified-patched"
            and proof["upstream_source_clean"] is True,
            "upstream/patched derivation mismatch")
    require("source_clean" not in proof and "source_clean" not in runtime
            and "source_clean" not in runtime.get("validation", {}),
            "ambiguous patched source cleanliness")

    recipes = reviewed["build_recipe_sha256"]
    require(len(recipes) == 6 and proof["build_recipe_sha256"] == recipes,
            "reviewed six-recipe map mismatch")
    for path, expected in recipes.items():
        require(digest(root, path) == expected, "recipe source digest mismatch: " + path)
    expected_recipes = {Path(path).name: value for path, value in recipes.items()}
    require(sha_manifest(evidence("build-recipe-sha256.txt")) == expected_recipes,
            "image recipe manifest mismatch")
    observed = record("d3b2-build-observation.json")
    require(all(observed["input_proof"][key] == proof["input_proof"][key]
                for key in ("original_path", "sha256")), "input receipt reference mismatch")
    require(observed["recipe_sha256"] == expected_recipes
            and observed["host_recipe_manifest_sha256"] == observed["image_recipe_manifest_sha256"]
            == hashlib.sha256(evidence("build-recipe-sha256.txt")).hexdigest(),
            "host/image recipe mismatch")
    require(observed["source"] == source and observed["cli"]["source_provenance"] == source,
            "build observation source mismatch")
    require(observed["status"] == "PASS_BUILD_CLI_ENUMERATION_ONLY"
            and observed["actual_build_attempts"] == 1
            and type(observed["build_exit"]) is int and observed["build_exit"] == 0
            and type(observed["job_exit"]) is int and observed["job_exit"] == 0
            and observed["owner_commit"] == "c7155099e4d8d096b0e946352fbf01e3a9072ab9",
            "successful actual build observation required")
    require(proof["build_status"] == observed["status"]
            and proof["build_exit"] == observed["build_exit"]
            and proof["build_source_commit"] == observed["owner_commit"]
            and runtime["validation"]["status"] == observed["status"],
            "source proof build status mismatch")
    require(all(proof[key] == observed[key] for key in
                ("actual_build_attempts", "build_started_utc", "build_finished_utc")),
            "source proof build timing/count mismatch")
    require(all(proof[key] == "NOT_TESTED" for key in
                ("glm_inference", "tool_calls", "occupied_context", "fusion_and_workspace", "live_acceptance"))
            and proof["service_activation"] == "NOT_PERFORMED", "source proof acceptance overstated")

    d1 = document(root, D1)
    image_id = proof["image_id"]
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", image_id)
            and image_id != d1["validation"]["image_id"], "wrong/D1 image identity")
    tag = "local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d3p-" + manifest["patch_sha256"][:12]
    require(runtime["id"] == RUNTIME and proof["image_tag"] == runtime["image_tag"] == tag
            and runtime["validation"]["image_id"] == image_id,
            "runtime image/tag mismatch")
    for field in ("kind", "backend", "source_repository", "entrypoint", "network_mode",
                  "environment", "build_contract"):
        require(runtime[field] == d1[field], "runtime baseline contract changed: " + field)
    require(proof["entrypoint"] == runtime["entrypoint"] and proof["platform"] == "linux/amd64",
            "image entrypoint/platform mismatch")
    require(proof["image_index_sha256"] == image_id.removeprefix("sha256:"),
            "Docker image/index identity mismatch")
    for field in ("image_id", "image_tag", "image_index_sha256", "image_config_sha256",
                  "platform_manifest_sha256", "entrypoint", "platform", "oci_labels", "binary_sha256"):
        require(observed[field] == proof[field], "build observation identity mismatch: " + field)
    for field in ("image_config_sha256", "platform_manifest_sha256", "binary_sha256"):
        require(re.fullmatch(r"[0-9a-f]{64}", proof[field]), "invalid measured digest: " + field)
    labels = {
        "org.opencontainers.image.source": manifest["upstream_repository"],
        "org.opencontainers.image.revision": manifest["derived_tree"],
        "org.opencontainers.image.version": "v0.4.1+d3p",
        "local.d1.cuda.architectures": d1["build_contract"]["cmake_cuda_architectures"],
        "local.d3p.source.kind": "upstream-plus-checked-patch",
        "local.d3p.source.revision-kind": "git-tree",
        "local.d3p.source.upstream-commit": manifest["upstream_commit"],
        "local.d3p.source.patch-sha256": manifest["patch_sha256"],
        "local.d3p.source.derived-tree": manifest["derived_tree"],
    }
    require(all(proof["oci_labels"].get(key) == value for key, value in labels.items()),
            "OCI source derivation label mismatch")
    identity = record("image-identity.json")
    # This file is the selected, sanitized Docker observation; never full inspect.
    for field in ("image_id", "image_tag", "image_index_sha256", "image_config_sha256",
                  "platform_manifest_sha256", "entrypoint", "platform", "oci_labels"):
        require(identity[field] == proof[field], "retained image identity mismatch: " + field)
    require(identity["repo_digests"] == observed["repo_digests"] == proof["repo_digests"]
            == ["local/llama-cpp@" + image_id], "image repository digest mismatch")
    require(hashlib.sha256(evidence("image-index.json")).hexdigest() == proof["image_index_sha256"]
            and hashlib.sha256(evidence("image-amd64-manifest.json")).hexdigest()
            == proof["platform_manifest_sha256"], "raw image manifest digest mismatch")
    index = record("image-index.json")
    platform_manifest = record("image-amd64-manifest.json")
    platforms = [item for item in index["manifests"]
                 if item.get("platform") == {"architecture": "amd64", "os": "linux"}]
    require(index["schemaVersion"] == platform_manifest["schemaVersion"] == 2
            and len(platforms) == 1
            and platforms[0]["digest"] == "sha256:" + proof["platform_manifest_sha256"]
            and platforms[0]["size"] == len(evidence("image-amd64-manifest.json"))
            and platform_manifest["config"]["digest"] == "sha256:" + proof["image_config_sha256"],
            "index/platform/config descriptor mismatch")
    # The raw config and binary are not distributed here. Their digests remain
    # measured references; no assertion of hashing those absent bytes is made.

    cli = observed["cli"]
    flags = d1["required_cli_flags"] + ["--n-cpu-moe"]
    help_text = evidence("llama-server-help.txt").decode()
    declarations = "\n".join(line for line in help_text.splitlines() if line.startswith("-"))
    help_flags = set(re.findall(r"(?<![A-Za-z0-9_-])--[a-z][a-z0-9-]*", declarations))
    require(set(flags) <= help_flags, "measured help missing required flag")
    require(runtime["required_cli_flags"] == runtime["validation"]["supported_flags"]
            == proof["supported_flags"] == cli["supported_flags_for_d3rd"] == flags,
            "measured 17-flag contract mismatch")
    modes = proof["supported_load_modes"]
    require(modes == cli["supported_load_modes"] == runtime["validation"]["supported_load_modes"]
            and "none" in modes and len(modes) == len(set(modes)), "measured load modes mismatch")
    mode_section = help_text[help_text.index("--load-mode"):]
    next_option = re.search(r"\n[^\n]*--[a-z]", mode_section[1:])
    if next_option:
        mode_section = mode_section[:next_option.start() + 1]
    require(re.findall(r"^\s+- ([a-z+]+):", mode_section, re.M) == modes,
            "load modes differ from measured help")
    version = evidence("llama-server-version.txt").decode()
    devices = evidence("llama-server-list-devices.txt").decode()
    compiler = evidence("nvcc-version.txt").decode()
    require(version == proof["version_stdout"] == cli["server_version"]
            == runtime["validation"]["version_stdout"]
            and compiler == proof["compiler_stdout"] == cli["nvcc_version"]
            and devices == proof["devices_stdout"], "verbatim measured output mismatch")
    device_lines = [line.strip() for line in devices.splitlines() if re.match(r"\s*CUDA[0-9]+:", line)]
    enumeration = observed["device_enumeration"]
    require([line.split(":", 1)[0] for line in device_lines] == proof["devices"]
            == runtime["validation"]["devices"] == enumeration["devices"] == ["CUDA0", "CUDA1"]
            and device_lines == enumeration["exact_device_lines"]
            and enumeration["image_id"] == image_id and enumeration["exit_code"] == 0
            and enumeration["status"] == "PASS_ENUMERATION_ONLY"
            and enumeration["output_sha256"] == hashlib.sha256(evidence("llama-server-list-devices.txt")).hexdigest(),
            "CUDA0/CUDA1 measured enumeration mismatch")
    containers = cli["containers"]
    require(len(containers) == 2 and {item["kind"] for item in containers} == {"version", "help"},
            "model-free CLI observations missing")
    for item in containers:
        require(item["image_id"] == image_id and item["status"] == "exited" and item["exit_code"] == 0
                and item["cli_sha256"] == hashlib.sha256(evidence("llama-server-" + item["kind"] + ".txt")).hexdigest(),
                "CLI observation output/image mismatch")
    require(cli["binary_sha256"] == proof["binary_sha256"], "measured binary mismatch")
    artifacts = cli["in_image_artifact_sha256"]
    require(artifacts["llama-server"] == proof["binary_sha256"], "binary artifact digest mismatch")
    for name in ("CMakeCache.txt", "source-provenance.json", "nvcc-version.txt", "source-commit.txt",
                 "build-recipe-sha256.txt", "source-tree.txt", "build-packages.tsv"):
        require(artifacts[name] == hashlib.sha256(evidence(name)).hexdigest(),
                "in-image artifact digest mismatch: " + name)
    cmake = dict(line.split("=", 1) for line in evidence("CMakeCache.txt").decode().splitlines()
                 if "=" in line and not line.startswith(("#", "//")))
    require(all(cmake.get(key) == value for key, value in cli["cmake"].items()),
            "measured CMake cache mismatch")
    require(any(key.startswith("CMAKE_CUDA_ARCHITECTURES:") and value == "120a-real"
                for key, value in cmake.items()) and cmake.get("GGML_CUDA:BOOL") == "ON",
            "measured CUDA build contract mismatch")
    require(evidence("host-build-recipe-sha256.txt") == evidence("build-recipe-sha256.txt"),
            "original host/image recipe evidence mismatch")
    require(record("source-preflight.json") == dict(manifest, source_state="verified-upstream", derived_commit=None),
            "upstream clean preflight mismatch")
    guard_close = record("guard-close.json")
    require(guard_close["status"] == "PASS_FINAL_AFTER_ENUMERATION_CLEANUP",
            "final supplied guard result failed")
    require(proof["final_guards"] == {
        "status": guard_close["status"],
        "evidence": [EVIDENCE + name for name in
                     ("registered-build-before.json", "registered-build-after.json", "guard-close.json")],
        "warnings": guard_close["registered_root_guard"]["warnings"]}, "final guard summary mismatch")
    guard_contract = record("VM-GUARDS.json")
    expected_guards = list(guard_contract["guards"].values()) + [
        guard_contract["registered_host"]["guard"], guard_contract["registered_host"]["dependency"]]
    expected_guards = {item["path"]: item["sha256"] for item in expected_guards}
    actual_guards = guard_close["guard_sources"]
    require(len(actual_guards) == len(expected_guards)
            and {item["path"]: item["sha256"] for item in actual_guards} == expected_guards
            and all(item["ordinary_single_link_file"] is True and item["protected_root_ancestors"] is True
                    for item in actual_guards), "supplied guard source contract mismatch")
    for name, value in reviewed["protected_guard_source"]["source_sha256"].items():
        path = reviewed["protected_guard_source"]["installed_root"] + "/" + name
        require(expected_guards.get(path) == value, "reviewed registered guard source mismatch")
    for guard in (record("registered-build-before.json"), record("registered-build-after.json"),
                  guard_close["registered_root_guard"]):
        require(guard["verified_roles"] == ["data", "models"]
                and guard["data"]["path"] == guard["data"]["mount"] == "/data"
                and guard["models"]["path"] == guard["models"]["mount"] == "/data/models-large"
                and guard["root_payload_scan"]["status"] == "pass"
                and guard["capacity"]["root_available_bytes"] >= 4 * 1024**3
                and guard["capacity"]["shared_model_filesystem"] is False,
                "supplied registered build/final guard failed")
        require(all(guard["roots"][key] == value for key, value in {
            "build": "/data/build", "containerd": "/data/containerd", "docker": "/data/docker",
            "hf_cache": "/data/hf-cache", "logs": "/data/logs", "models": "/data/models-large",
            "secrets": "/data/services/secrets", "services": "/data/services"}.items()),
                "supplied guard data roots mismatch")


def verify_profiles(root, runtime):
    # Import the unchanged reviewed generator, not a second deployment template.
    import sys
    sys.path.insert(0, str(root / "scripts"))
    from d3t.profiles import generate_plan
    plan = generate_plan(root)
    for relative, proposal in zip(DEPLOYMENTS, plan["proposals"][:2]):
        profile = document(root, relative)
        require(set(profile) == set(proposal), "deployment shape changed")
        for key in proposal.keys() - {"runtime", "purpose", "notes"}:
            require(profile[key] == proposal[key], "deployment field changed: " + key)
        require(profile["runtime"] == RUNTIME, "deployment runtime mismatch")
        require("declared" in profile["purpose"].lower()
                and "NOT_TESTED" in profile["purpose"], "deployment acceptance overstated")
        require(profile["notes"] and all(isinstance(note, str) for note in profile["notes"]),
                "deployment notes missing")
    return plan


def verify_inventory(root, proof, runtime):
    selection_path = "configs/control/ai-vm-live-snapshot.json"
    selection = document(root, selection_path)
    glm = next(row for row in selection["offered_models"] if row["network_role"] == "glm")
    runtime_path = f"configs/runtimes/{RUNTIME}.json"
    require(glm["runtime"] == RUNTIME and glm["runtime_source"] == runtime_path
            and glm["runtime_sha256"] == digest(root, runtime_path), "snapshot runtime mismatch")
    require(glm["measured_image_id"] == proof["image_id"], "snapshot image mismatch")
    require(glm["patched_image_proof"] == {"path": PROOF, "sha256": digest(root, PROOF)},
            "snapshot proof mismatch")
    require(glm["recipe_dependency_closure"] == proof["build_recipe_sha256"],
            "snapshot recipe mismatch")
    deployments = {path: digest(root, path) for path in DEPLOYMENTS}
    require(glm["deployment_sources"] == deployments
            and glm["deployment_source"] == DEPLOYMENTS[0]
            and glm["deployment_sha256"] == deployments[DEPLOYMENTS[0]],
            "snapshot deployment mismatch")
    require(selection["live_acceptance"] == "NOT_TESTED"
            and glm["context_evidence"] == "declared_only"
            and glm["capability_status"] == "NOT_TESTED", "snapshot acceptance overstated")
    inventory = document(root, "reports/l2-source-closure-sha256.json")
    require(inventory["profile_selection_sha256"] == digest(root, selection_path),
            "inventory selection mismatch")
    require(inventory["closure_manifest_sha256"] == digest(root, "scripts/control/source-closure.json"),
            "inventory closure mismatch")
    dependencies = set(proof["evidence_sha256"]) | set(proof["build_recipe_sha256"])
    dependencies |= {PROOF, runtime_path, *DEPLOYMENTS, "reports/d3br-evidence/provenance.json"}
    require(dependencies <= inventory["files"].keys(), "inventory missing GLM dependencies")
    for path, expected in (inventory["files"] | selection["fixed_profile_sha256"]).items():
        require(digest(root, path) == expected, "inventory digest mismatch: " + path)


def verify(root: Path = ROOT, *, inventory: bool = True) -> dict:
    root = root.resolve()
    proof = document(root, PROOF)
    runtime = document(root, f"configs/runtimes/{RUNTIME}.json")
    verify_measurements(root, proof, runtime)
    verify_profiles(root, runtime)
    if inventory:
        verify_inventory(root, proof, runtime)
    return {"status": "PASS_SOURCE_BINDING_ONLY", "image_id": proof["image_id"],
            "contexts": [32768, 1048576], "live_acceptance": "NOT_TESTED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--root", type=Path, default=ROOT, help="reviewed source tree (read only)")
    args = parser.parse_args()
    try:
        result = verify(args.root)
    except (BindingError, OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        parser.exit(1, "D3RD binding refused: " + str(error) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
