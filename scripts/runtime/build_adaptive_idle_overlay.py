#!/usr/bin/env python3
"""Prepare a deterministic pinned overlay build context OFFLINE; never build/install.

The source root must contain the exact official files named in the manifest.
All anchors are checked before transformation. Output is published only after
every patch, path check and Python compile succeeds. Existing output is refused.
The generated Dockerfile rechecks native raw bytes in the immutable parent image
before copying changed modules, preserving unmodified upstream dependencies.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

try:
    from .adaptive_idle_source_gate import MANIFEST, read_sources
except ImportError:
    from adaptive_idle_source_gate import MANIFEST, read_sources


RUNTIME = Path(__file__).resolve().parent


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def safe_relative(name):
    path = Path(name)
    if not name or path.is_absolute() or ".." in path.parts or str(path) != name:
        raise ValueError("overlay_path_invalid")
    return path


def patch_paths(raw):
    old, new = [], []
    for line in raw.decode("utf-8").splitlines():
        if line.startswith("--- "):
            old.append(line[4:].split("\t", 1)[0])
        elif line.startswith("+++ "):
            new.append(line[4:].split("\t", 1)[0])
    if not old or len(old) != len(new):
        raise ValueError("overlay_patch_paths_invalid")
    paths = []
    for before, after in zip(old, new):
        if not before.startswith("a/") or not after.startswith("b/") or before[2:] != after[2:]:
            raise ValueError("overlay_patch_paths_invalid")
        paths.append(str(safe_relative(before[2:])))
    if len(set(paths)) != len(paths):
        raise ValueError("overlay_patch_paths_invalid")
    return paths


def native_path(spec, relative):
    prefix = "python/sglang/"
    if not relative.startswith(prefix):
        raise ValueError("overlay_native_path_invalid")
    return spec["native_package_root"] + "/" + relative[len(prefix):]


def dockerfile(spec, target, core, overlay_digest):
    checks = {native_path(spec, key): value for key, value in core["input_raw_sha256"].items()}
    checks.update(spec.get("installed_preconditions", {}))
    commands = ["printf '%s\\n' " + " ".join("'" + sha + "  " + path + "'" for path, sha in sorted(checks.items())) + " | sha256sum -c -"]
    for relative in sorted(spec["helpers"]):
        commands.append("test ! -e '" + native_path(spec, relative) + "'")
    lines = ["# Generated offline; building and activation require separate authorization.",
             "FROM " + spec["image_reference"],
             'LABEL io.llmctl.adaptive-idle.overlay-sha256="' + overlay_digest + '"',
             "RUN " + json.dumps(["/bin/sh", "-ec", " && ".join(commands)])]
    for relative in sorted(core["output_raw_sha256"]):
        lines.append("COPY " + json.dumps(["files/" + relative, native_path(spec, relative)]))
    lines.append("COPY " + json.dumps(["provenance.json", "/opt/llmctl/adaptive-idle/" + target + ".json"]))
    lines.append("COPY " + json.dumps(["verify.py", "/opt/llmctl/adaptive-idle/verify.py"]))
    return ("\n".join(lines) + "\n").encode()


def prepare(root, target, output, *, manifest_path=MANIFEST, runtime=RUNTIME):
    manifest = json.loads(Path(manifest_path).read_text())
    sources = read_sources(root, target, manifest)  # No output created on drift.
    spec = manifest[target]
    verifier = (Path(runtime) / "verify_adaptive_idle_overlay.py").read_bytes()
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("overlay_output_exists")
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise ValueError("overlay_output_parent_invalid")
    patches, touched = {}, set()
    for name in spec["patches"]:
        path = Path(runtime) / safe_relative(name)
        if path.is_symlink():
            raise ValueError("overlay_patch_path_invalid")
        raw = path.read_bytes()
        paths = patch_paths(raw)
        if not set(paths) <= set(sources):
            raise ValueError("overlay_unpinned_patch_target")
        patches[name] = raw
        touched.update(paths)
    helpers = {}
    for relative, name in spec["helpers"].items():
        safe_relative(relative)
        native_path(spec, relative)
        if relative in sources:
            raise ValueError("overlay_helper_overwrites_upstream")
        path = Path(runtime) / safe_relative(name)
        if path.is_symlink():
            raise ValueError("overlay_helper_path_invalid")
        helpers[relative] = path.read_bytes()
    with tempfile.TemporaryDirectory(prefix="adaptive-idle-") as temporary:
        stage = Path(temporary)
        for relative, raw in sources.items():
            path = stage / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        for raw in patches.values():
            for check in (True, False):
                command = ["git", "apply", "--whitespace=nowarn"] + (["--check"] if check else []) + ["-"]
                result = subprocess.run(command, input=raw, cwd=stage, capture_output=True)
                if result.returncode:
                    raise ValueError("overlay_patch_does_not_apply")
        produced = {relative: (stage / relative).read_bytes() for relative in sorted(touched)}
        produced.update(helpers)
        # Compile complete modules without imports, GPU dependencies or .pyc writes.
        for relative, raw in produced.items():
            tree = ast.parse(raw, filename=relative)
            compile(tree, relative, "exec")
        core = {"schema_version": 1, "target": target,
                "upstream_revision": spec["upstream_revision"],
                "parent_image_reference": spec["image_reference"],
                "native_package_root": spec["native_package_root"],
                "installed_preconditions": spec.get("installed_preconditions", {}),
                "verifier_raw_sha256": digest(verifier),
                "input_raw_sha256": {key: digest(raw) for key, raw in sources.items()},
                "patch_raw_sha256": {key: digest(raw) for key, raw in patches.items()},
                "output_raw_sha256": {key: digest(raw) for key, raw in produced.items()}}
        overlay_digest = digest(canonical(core))
        recipe = dockerfile(spec, target, core, overlay_digest)
        receipt = {**core, "overlay_sha256": overlay_digest,
                   "dockerfile_sha256": digest(recipe),
                   "source_identity": "official_pinned_upstream_raw_bytes",
                   "installed_raw_verified_files": spec.get("installed_raw_verified_files", []),
                   "source_observation": manifest.get("source_observation"),
                   "new_image_identity": None, "image_built": False,
                   "native_integration_accepted": False,
                   "verification": ["all_input_raw_hashes", "exact_patch_application", "complete_output_ast_compile"],
                   "live_acceptance": "NOT_TESTED"}
        # Publish once, atomically on the output filesystem. No partial overlay
        # survives hash, patch, syntax or output-path failures.
        pending = Path(tempfile.mkdtemp(prefix=".adaptive-idle-", dir=output.parent))
        try:
            for relative, raw in produced.items():
                path = pending / "files" / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            (pending / "Dockerfile").write_bytes(recipe)
            (pending / "verify.py").write_bytes(verifier)
            (pending / "provenance.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            if output.exists() or output.is_symlink():
                raise ValueError("overlay_output_exists")
            os.rename(pending, output)
        finally:
            if pending.exists():
                shutil.rmtree(pending)
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--target", choices=("text", "image"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    try:
        receipt = prepare(options.root, options.target, options.output)
    except (OSError, ValueError, SyntaxError) as error:
        code = str(error) if isinstance(error, ValueError) else "overlay_preparation_failed"
        parser.exit(1, code + "\n")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
