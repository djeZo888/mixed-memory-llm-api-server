#!/usr/bin/env python3
"""Control one exact I2P hosted workflow run using existing gh authentication."""
import argparse
import io
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

REPOSITORY = "djeZo888/mixed-memory-llm-api-server"
WORKFLOW = ".github/workflows/i2p-linux.yml"
EVIDENCE_FILES = {"evidence.json", "source-manifest.json", "plan.json"}


def api(path, method="GET", binary=False):
    result = subprocess.run(["gh", "api", "--method", method, path],
                            capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError("gh_api_failed; inspect authentication or run permission separately")
    return result.stdout if binary else json.loads(result.stdout or b"{}")


def validate_run(data, run_id, head):
    if (data.get("id") != run_id or data.get("head_sha") != head or
            data.get("repository", {}).get("full_name") != REPOSITORY or
            data.get("path", "").split("@", 1)[0] != WORKFLOW or
            not data.get("head_branch", "").startswith("milestone/i2") or
            data.get("event") not in ("push", "workflow_dispatch")):
        raise RuntimeError("refuse_mismatched_run_identity")


def unpack_evidence(payload, destination):
    if len(payload) > 1024 * 1024:
        raise RuntimeError("oversized_artifact")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        entries = archive.infolist()
        if {entry.filename for entry in entries} != EVIDENCE_FILES or len(entries) != 3:
            raise RuntimeError("unexpected_artifact_files")
        if any(entry.file_size > 1024 * 1024 or entry.is_dir() for entry in entries):
            raise RuntimeError("unsafe_artifact_entry")
        documents = {entry.filename: json.loads(archive.read(entry)) for entry in entries}
    destination.mkdir(mode=0o700)  # must be new; no overwrite or symlink following
    for name, document in documents.items():
        path = destination / name
        with path.open("x") as stream:
            json.dump(document, stream, indent=2, sort_keys=True)
            stream.write("\n")
        path.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "rerun", "collect", "stop"))
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--head", required=True, help="exact reviewed 40-hex source commit")
    parser.add_argument("--dry-run", action="store_true", help="validate identity; do not mutate/download")
    parser.add_argument("--destination", type=Path, help="new private directory outside Git for collect")
    args = parser.parse_args()
    if args.run_id < 1 or not re.fullmatch(r"[0-9a-f]{40}", args.head):
        parser.error("positive run ID and exact lowercase commit required")
    path = f"repos/{REPOSITORY}/actions/runs/{args.run_id}"
    data = api(path)
    validate_run(data, args.run_id, args.head)
    print(json.dumps({key: data.get(key) for key in
                      ("id", "head_sha", "head_branch", "run_attempt", "status", "conclusion", "html_url")}, indent=2))
    if args.dry_run or args.action == "status":
        return
    if args.action == "stop":
        if data.get("status") == "completed":
            raise RuntimeError("refuse_cancel_completed_run")
        api(path + "/cancel", method="POST")
    elif args.action == "rerun":
        if data.get("status") != "completed":
            raise RuntimeError("refuse_rerun_incomplete_run")
        api(path + "/rerun", method="POST")
    else:
        if data.get("status") != "completed":
            raise RuntimeError("collect_requires_completed_run")
        if args.destination is None or not args.destination.is_absolute():
            parser.error("collect needs absolute --destination outside Git")
        parent = args.destination.parent
        if not parent.is_dir() or parent.resolve() != parent or parent.is_symlink():
            raise RuntimeError("unsafe_destination_parent")
        if parent.stat().st_uid != os.getuid() or parent.stat().st_mode & 0o077:
            raise RuntimeError("destination_parent_must_be_owned_private_0700")
        if any((ancestor / ".git").exists() for ancestor in (parent, *parent.parents)):
            raise RuntimeError("artifacts_must_be_outside_git")
        expected = f"i2p-evidence-{args.run_id}-{data['run_attempt']}"
        artifacts = api(path + "/artifacts?per_page=100").get("artifacts", [])
        matches = [item for item in artifacts if item.get("name") == expected and not item.get("expired")]
        if len(matches) != 1:
            raise RuntimeError("missing_or_ambiguous_evidence_artifact")
        artifact = matches[0]
        payload = api(f"repos/{REPOSITORY}/actions/artifacts/{int(artifact['id'])}/zip", binary=True)
        unpack_evidence(payload, args.destination)
        evidence = json.loads((args.destination / "evidence.json").read_text())
        if (evidence.get("source_sha") != args.head or
                evidence.get("github_run_id") != str(args.run_id) or
                evidence.get("github_run_attempt") != str(data["run_attempt"])):
            raise RuntimeError("artifact_content_identity_mismatch; retained_for_review")
        print("sanitized_evidence_collected")


if __name__ == "__main__":
    main()
