#!/usr/bin/env python3
"""Observe and collect one exact I2S run using the existing gh credential helper."""
import argparse
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import zipfile

spec = importlib.util.spec_from_file_location("i2p_runnerctl", Path(__file__).parents[1] / "i2p/runnerctl.py")
i2p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(i2p)
REPOSITORY = i2p.REPOSITORY
WORKFLOW = ".github/workflows/i2s-linux.yml"


def validate_run(data, run_id, head):
    if (data.get("id") != run_id or data.get("head_sha") != head or
            data.get("repository", {}).get("full_name") != REPOSITORY or
            data.get("path", "").split("@", 1)[0] != WORKFLOW or
            data.get("head_branch") != "milestone/i2s-storage-linux" or data.get("event") != "push"):
        raise RuntimeError("refuse_mismatched_i2s_run_identity")


def validate_payload(payload, head, run_id, attempt):
    if len(payload) > 1024**2:
        raise RuntimeError("oversized_artifact")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        entries = archive.infolist()
        if len(entries) != 3 or {e.filename for e in entries} != i2p.EVIDENCE_FILES:
            raise RuntimeError("unexpected_artifact_files")
        if any(e.file_size > 1024**2 or e.is_dir() for e in entries):
            raise RuntimeError("unsafe_artifact_entry")
        documents = {e.filename: json.loads(archive.read(e)) for e in entries}
    evidence = documents["evidence.json"]
    if (evidence.get("source_sha") != head or evidence.get("github_run_id") != str(run_id) or
            evidence.get("github_run_attempt") != str(attempt)):
        raise RuntimeError("artifact_content_identity_mismatch")
    return documents


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "collect"))
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    if args.run_id < 1 or not re.fullmatch("[0-9a-f]{40}", args.head):
        parser.error("exact positive run ID and lowercase SHA required")
    api_path = f"repos/{REPOSITORY}/actions/runs/{args.run_id}"
    data = i2p.api(api_path)
    validate_run(data, args.run_id, args.head)
    print(json.dumps({key: data.get(key) for key in
                      ("id", "head_sha", "head_branch", "run_attempt", "status", "conclusion", "html_url")}, indent=2))
    if args.action == "status":
        return
    if data.get("status") != "completed":
        raise RuntimeError("collect_requires_completed_run")
    destination = args.destination
    if destination is None or not destination.is_absolute():
        parser.error("new absolute private destination required")
    parent = destination.parent
    if (not parent.is_dir() or parent.resolve() != parent or parent.is_symlink() or
            parent.stat().st_uid != os.getuid() or parent.stat().st_mode & 0o077 or
            any((p / ".git").exists() for p in (parent, *parent.parents))):
        raise RuntimeError("destination_parent_must_be_owned_private_outside_git")
    expected = f"i2s-evidence-{args.run_id}-{data['run_attempt']}"
    artifacts = i2p.api(api_path + "/artifacts?per_page=100").get("artifacts", [])
    matches = [a for a in artifacts if a.get("name") == expected and not a.get("expired")]
    if len(matches) != 1:
        raise RuntimeError("missing_or_ambiguous_evidence_artifact")
    artifact = matches[0]
    payload = i2p.api(f"repos/{REPOSITORY}/actions/artifacts/{int(artifact['id'])}/zip", binary=True)
    documents = validate_payload(payload, args.head, args.run_id, data["run_attempt"])
    destination.mkdir(mode=0o700)
    for name, document in documents.items():
        with (destination / name).open("x") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(document, stream, indent=2, sort_keys=True)
            stream.write("\n")
    print(json.dumps({"artifact_id": artifact["id"], "name": expected,
                      "digest": artifact.get("digest"), "size_in_bytes": artifact.get("size_in_bytes"),
                      "expires_at": artifact.get("expires_at"), "collection": "sanitized_source_bound_evidence"}, indent=2))


if __name__ == "__main__":
    main()
