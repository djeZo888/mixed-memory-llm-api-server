#!/usr/bin/env python3
"""Pin only the two H039 public repositories; never read HF credentials."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import urllib.parse
import urllib.request

APPROVED = ("Qwen/Qwen3.5-9B", "PaddlePaddle/PaddleOCR-VL-1.6")


def public_get(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


def safe_name(name):
    if not isinstance(name, str) or not name or name.startswith("/") or "\\" in name:
        raise ValueError("unsafe_artifact_name")
    if any(p in ("", ".", "..") for p in name.split("/")):
        raise ValueError("unsafe_artifact_name")
    return str(PurePosixPath(name))


def pin(model):
    if model not in APPROVED:
        raise ValueError("unapproved_model")
    data = json.loads(public_get("https://huggingface.co/api/models/" + model + "?blobs=true"))
    revision = data["sha"]
    if data.get("private") or data.get("gated") or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("public_pinned_repository_required")
    files = []
    for item in data["siblings"]:
        name = safe_name(item["rfilename"])
        size = item["size"]
        url = "https://huggingface.co/" + model + "/resolve/" + revision + "/" + urllib.parse.quote(name)
        if item.get("lfs"):
            checksum = item["lfs"]["sha256"]
            if item["lfs"]["size"] != size:
                raise ValueError("lfs_size_mismatch")
            source = "official_hf_lfs_sha256"
        else:
            if size > 16 * 1024 * 1024:
                raise ValueError("non_lfs_metadata_too_large")
            blob = public_get(url)
            git_hash = hashlib.sha1(b"blob " + str(len(blob)).encode() + b"\0" + blob).hexdigest()
            if len(blob) != size or git_hash != item["blobId"]:
                raise ValueError("official_git_blob_mismatch")
            checksum, source = hashlib.sha256(blob).hexdigest(), "sha256_of_git_blob_verified_public_file"
        files.append({"path": name, "size": size, "sha256": checksum,
                      "checksumSource": source, "gitBlobId": item["blobId"]})
    return {"repo": model, "revision": revision, "directory": model.split("/")[1].lower() + "-" + revision,
            "files": files, "totalBytes": sum(f["size"] for f in files),
            "weightFiles": sum(f["path"].endswith(".safetensors") for f in files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = {"schema": "h039-official-artifacts-v1", "pinnedUtc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "models": [pin(model) for model in APPROVED]}
    args.output.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"status": "PINNED_EXPECTED_HASHES", "models": [
        {k: m[k] for k in ("repo", "revision", "totalBytes", "weightFiles")} for m in manifest["models"]]}))


if __name__ == "__main__":
    main()
