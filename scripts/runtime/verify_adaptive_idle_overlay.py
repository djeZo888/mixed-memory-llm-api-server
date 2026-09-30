"""Read-only launch guard for a reviewed adaptive-idle overlay digest.

Callers must supply a digest pinned in reviewed launch source/configuration,
never a value from the receipt itself, a request, or an environment override.
Parent image/owner/storage admission checks remain separately mandatory.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


PACKAGE_ROOTS = {
    "text": "/sgl-workspace/sglang/python/sglang",
    "image": "/opt/image-venv/lib/python3.12/site-packages/sglang",
}
CORE_KEYS = ("schema_version", "target", "upstream_revision", "parent_image_reference",
             "native_package_root", "installed_preconditions", "input_raw_sha256",
             "patch_raw_sha256", "output_raw_sha256", "verifier_raw_sha256")


def verify_installed(receipt_path, expected_digest, target):
    if not isinstance(expected_digest, str) or not re.fullmatch("[0-9a-f]{64}", expected_digest):
        raise ValueError("adaptive_overlay_expected_digest_invalid")
    if target not in PACKAGE_ROOTS:
        raise ValueError("adaptive_overlay_target_invalid")
    receipt_path = Path(receipt_path)
    if receipt_path.is_symlink():
        raise ValueError("adaptive_overlay_receipt_invalid")
    receipt = json.loads(receipt_path.read_text())
    try:
        core = {key: receipt[key] for key in CORE_KEYS}
    except (KeyError, TypeError):
        raise ValueError("adaptive_overlay_receipt_invalid") from None
    actual = hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected_digest or receipt.get("overlay_sha256") != expected_digest:
        raise ValueError("adaptive_overlay_digest_mismatch")
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != core["verifier_raw_sha256"]:
        raise ValueError("adaptive_overlay_verifier_mismatch")
    package = PACKAGE_ROOTS[target]
    if core["target"] != target or core["native_package_root"] != package:
        raise ValueError("adaptive_overlay_target_mismatch")
    final = dict(core["input_raw_sha256"])
    final.update(core["output_raw_sha256"])
    checks = dict(core["installed_preconditions"])
    for name, sha in final.items():
        relative = Path(name)
        if not name.startswith("python/sglang/") or ".." in relative.parts:
            raise ValueError("adaptive_overlay_path_invalid")
        checks[package + "/" + name[len("python/sglang/"):]] = sha
    for name, sha in checks.items():
        path = Path(name)
        if not name.startswith(package + "/") or ".." in path.parts:
            raise ValueError("adaptive_overlay_path_invalid")
        package_path = Path(package)
        if (any(part.is_symlink() for part in (path, *path.parents)
                if part == package_path or package_path in part.parents)
                or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != sha):
            raise ValueError("adaptive_overlay_installed_source_mismatch")
    return {"target": target, "overlay_sha256": actual, "verified_files": len(checks)}
