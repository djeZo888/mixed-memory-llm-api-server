#!/usr/bin/env python3
"""Read-only normalized evidence check; never installs or accepts a runtime.

H004 hashes stripped decoded text, not raw bytes. Matching it is useful before
review, but it cannot supply the exact-source attestation required for activation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


MANIFEST = Path(__file__).with_name("adaptive_idle_sources.json")


def verify(root, target):
    manifest = json.loads(MANIFEST.read_text())
    if target not in ("text", "image"):
        raise ValueError("invalid_native_target")
    root = Path(root).resolve(strict=True)
    checked = {}
    for relative, expected in manifest[target]["files"].items():
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError("pinned_native_source_missing")
        # A source package may not redirect a parent outside the supplied root.
        if root not in path.resolve(strict=True).parents:
            raise ValueError("pinned_native_source_outside_root")
        raw = path.read_bytes()
        # Derive both receipts from one read. Match Path.read_text()'s universal
        # newline decoding used by H004, without racing two separate reads.
        normalized = raw.decode().replace("\r\n", "\n").replace("\r", "\n").strip()
        actual = hashlib.sha256(normalized.encode()).hexdigest()
        if actual != expected:
            raise ValueError("pinned_native_source_hash_mismatch")
        checked[relative] = {"normalized_sha256": actual,
                             "raw_sha256": hashlib.sha256(raw).hexdigest()}
    return {"target": target, "upstream_revision": manifest[target]["upstream_revision"],
            "source_identity": "matched_retained_normalized_text_only", "files": checked,
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
