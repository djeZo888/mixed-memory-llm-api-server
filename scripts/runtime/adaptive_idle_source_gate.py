#!/usr/bin/env python3
"""Verify exact pinned source bytes offline; never accept a runtime.

Historical H004 normalized hashes remain in the manifest as dated evidence.
Raw pins identify official upstream blobs. The manifest separately names the
files whose identical bytes were read from the selected installed containers;
other helper pins do not claim installed equality. This check contacts no host.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


MANIFEST = Path(__file__).with_name("adaptive_idle_sources.json")


def read_sources(root, target, manifest=None):
    manifest = json.loads(MANIFEST.read_text()) if manifest is None else manifest
    if target not in ("text", "image"):
        raise ValueError("invalid_native_target")
    root = Path(root).resolve(strict=True)
    sources = {}
    for relative, expected in manifest[target]["files"].items():
        name = Path(relative)
        if name.is_absolute() or ".." in name.parts:
            raise ValueError("pinned_native_source_path_invalid")
        path = root / relative
        if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents) if p != root and root in (p, *p.parents)):
            raise ValueError("pinned_native_source_missing")
        # A source package may not redirect a parent outside the supplied root.
        if root not in path.resolve(strict=True).parents:
            raise ValueError("pinned_native_source_outside_root")
        raw = path.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected:
            raise ValueError("pinned_native_source_hash_mismatch")
        sources[relative] = raw
    return sources


def verify(root, target):
    manifest = json.loads(MANIFEST.read_text())
    sources = read_sources(root, target, manifest)
    checked = {relative: {"raw_sha256": hashlib.sha256(raw).hexdigest()}
               for relative, raw in sources.items()}
    return {"target": target, "upstream_revision": manifest[target]["upstream_revision"],
            "source_identity": "matched_official_upstream_raw_bytes", "files": checked,
            "installed_raw_verified_files": manifest[target].get("installed_raw_verified_files", []),
            "source_observation": manifest.get("source_observation"),
            "native_integration_accepted": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--target", required=True, choices=("text", "image"))
    options = parser.parse_args()
    try:
        result = verify(options.root, options.target)
    except (ValueError, OSError) as error:
        code = str(error) if isinstance(error, ValueError) else "pinned_native_source_unreadable"
        parser.exit(1, code + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
