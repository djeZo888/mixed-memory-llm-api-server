#!/usr/bin/env python3
"""Verify the fixed D3P upstream and patch, then apply only that patch.

--check-only verifies the derived tree using temporary Git objects/index and
leaves the source checkout unchanged. There is no source-ref or manifest override.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

UPSTREAM_REPOSITORY = "https://github.com/ggml-org/llama.cpp"
UPSTREAM_COMMIT = "b29c606e28a01b1bc8c1351026a0fa6e616bf6c4"
JINJA_FIX_ANCESTOR = "ae9afff8d2c012ca760eb9c2adf41961cf6f6232"
PATCH_FILE = "strict-model-chat.patch"
MANIFEST_FILE = "d3p-source.json"
FIELDS = {
    "schema_version", "upstream_repository", "upstream_commit", "upstream_tree",
    "jinja_fix_ancestor", "patch_file", "patch_sha256", "derived_tree",
}


def git(source, *args, extra_env=None):
    # Ambient Git overrides must not redirect the checkout, index or objects.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
         "-C", str(source), *args], env=env, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError("git " + args[0] + " failed: " +
                           result.stderr.decode(errors="replace").strip())
    return result.stdout


def load_manifest(recipe):
    path = recipe / MANIFEST_FILE
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("manifest must be an ordinary adjacent file")
    manifest = json.loads(path.read_text())
    if not isinstance(manifest, dict) or set(manifest) != FIELDS:
        raise RuntimeError("manifest fields do not match the D3P contract")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise RuntimeError("unsupported manifest schema_version")
    fixed = {"upstream_repository": UPSTREAM_REPOSITORY,
             "upstream_commit": UPSTREAM_COMMIT,
             "jinja_fix_ancestor": JINJA_FIX_ANCESTOR,
             "patch_file": PATCH_FILE}
    for key, expected in fixed.items():
        if manifest[key] != expected:
            raise RuntimeError("unapproved manifest identity: " + key)
    for key, size in (("upstream_tree", 40), ("derived_tree", 40),
                      ("patch_sha256", 64)):
        if not isinstance(manifest[key], str) or not re.fullmatch(
                "[0-9a-f]{" + str(size) + "}", manifest[key]):
            raise RuntimeError("invalid manifest digest: " + key)
    if manifest["upstream_tree"] == manifest["derived_tree"]:
        raise RuntimeError("D3P patch must change the upstream tree")
    patch = recipe / PATCH_FILE
    if patch.is_symlink() or not patch.is_file():
        raise RuntimeError("patch must be an ordinary adjacent file")
    if hashlib.sha256(patch.read_bytes()).hexdigest() != manifest["patch_sha256"]:
        raise RuntimeError("patch SHA256 mismatch")
    return manifest, patch


def verify_tracked_bytes(source):
    # Verify raw bytes and modes, including flags that can hide dirt from status.
    for entry in git(source, "ls-files", "--stage", "-z").split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, expected, stage = metadata.decode().split()
        path = source / os.fsdecode(name)
        if stage != "0" or mode not in ("100644", "100755", "120000"):
            raise RuntimeError("unsupported or unmerged tracked entry")
        if mode == "120000":
            if not path.is_symlink():
                raise RuntimeError("tracked symlink changed")
            content = os.fsencode(os.readlink(path))
        else:
            if path.is_symlink() or not path.is_file():
                raise RuntimeError("tracked file missing or replaced")
            if bool(path.stat().st_mode & 0o111) != (mode == "100755"):
                raise RuntimeError("tracked executable mode changed")
            content = path.read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        if actual != expected:
            raise RuntimeError("tracked content differs from pinned Git blob: " + os.fsdecode(name))


def verify_upstream(source, manifest):
    if source.is_symlink() or not source.is_dir():
        raise RuntimeError("source must be an ordinary checkout directory")
    source = source.resolve()
    if (source / ".git").is_symlink() or not (source / ".git").is_dir():
        raise RuntimeError("source requires a self-contained .git directory")
    if (source / ".git/objects/info/alternates").exists():
        raise RuntimeError("source must not depend on an external Git object store")
    if Path(os.fsdecode(git(source, "rev-parse", "--show-toplevel")).strip()).resolve() != source:
        raise RuntimeError("source is not the checkout root")
    if git(source, "rev-parse", "HEAD").decode().strip() != UPSTREAM_COMMIT:
        raise RuntimeError("upstream commit mismatch")
    if git(source, "rev-parse", "HEAD^{tree}").decode().strip() != manifest["upstream_tree"]:
        raise RuntimeError("upstream tree mismatch")
    git(source, "merge-base", "--is-ancestor", JINJA_FIX_ANCESTOR, "HEAD")
    if git(source, "status", "--porcelain=v1", "--untracked-files=all", "--ignored=matching"):
        raise RuntimeError("source is dirty (including untracked or ignored files)")
    if any(entry[:1] != b"H" for entry in
           git(source, "ls-files", "-v", "-z").split(b"\0") if entry):
        raise RuntimeError("source index has hidden or nonordinary tracked entries")
    git(source, "diff-index", "--cached", "--quiet", "HEAD", "--")
    verify_tracked_bytes(source)
    return source


def prepare(source, recipe, check_only=False):
    manifest, patch = load_manifest(recipe)
    source = verify_upstream(source, manifest)
    # Prove the future tree without modifying the checkout or its object store.
    with tempfile.TemporaryDirectory(prefix="d3p-verify-") as temporary:
        temporary = Path(temporary)
        objects = temporary / "objects"
        objects.mkdir()
        env = {"GIT_INDEX_FILE": str(temporary / "index"),
               "GIT_OBJECT_DIRECTORY": str(objects),
               "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(source / ".git/objects")}
        git(source, "read-tree", "HEAD", extra_env=env)
        git(source, "apply", "--cached", "--whitespace=error-all", str(patch), extra_env=env)
        derived = git(source, "write-tree", extra_env=env).decode().strip()
        if derived != manifest["derived_tree"]:
            raise RuntimeError("derived tree mismatch; source remains unchanged")
    if not check_only:
        # apply --index validates worktree/index agreement again and is atomic on
        # rejected hunks (no --reject, --3way, offset override or fuzzy fallback).
        git(source, "apply", "--check", "--index", "--whitespace=error-all", str(patch))
        git(source, "apply", "--index", "--whitespace=error-all", str(patch))
        if git(source, "write-tree").decode().strip() != manifest["derived_tree"]:
            raise RuntimeError("applied tree mismatch; compilation prohibited")
        verify_tracked_bytes(source)
        if git(source, "ls-files", "--others", "--exclude-standard") or git(
                source, "ls-files", "--others", "--ignored", "--exclude-standard"):
            raise RuntimeError("unexpected files after patch; compilation prohibited")
    return {**manifest, "source_state": "verified-upstream" if check_only else "verified-patched",
            "derived_commit": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="clean exact upstream checkout, including .git")
    parser.add_argument("--check-only", "--dry-run", action="store_true",
                        help="verify without changing the source checkout")
    args = parser.parse_args()
    try:
        result = prepare(args.source, Path(__file__).resolve().parent, args.check_only)
    except (RuntimeError, OSError, ValueError) as error:
        print("STOP: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
