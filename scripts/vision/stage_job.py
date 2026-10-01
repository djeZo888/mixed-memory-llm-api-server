#!/usr/bin/env python3
"""Guarded bootstrap: stage two owned task files, not a production release."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


class Runner:
    def run(self, argv, *, timeout=30, env=None):
        return subprocess.run(argv, timeout=timeout, check=True, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guard-scripts", required=True)
    parser.add_argument("--job", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"h039-vision-[a-z0-9-]{1,70}", args.job):
        raise ValueError("invalid_job_name")
    payload = json.loads(sys.stdin.buffer.read(256 * 1024))
    if set(payload) != {"artifact_job.py", "artifacts.lock.json"}:
        raise ValueError("only_owned_job_payload_allowed")
    files = {name: base64.b64decode(value, validate=True) for name, value in payload.items()}
    if any(len(v) > 128 * 1024 for v in files.values()):
        raise ValueError("oversized_job_payload")
    sys.path.insert(0, args.guard_scripts)
    from common.lifecycle_lease import acquire_lease
    from lifecycle.storage_binding import RegisteredStorageBinding
    from install import storage_io
    with acquire_lease(blocking=False):
        binding = RegisteredStorageBinding.load(Runner())
        with binding.mounted_guard(storage_io) as guard:
            for role in ("build", "logs", "models"):
                with storage_io.AnchoredRoot(binding.path(role), guard) as root:
                    root.mkdir(args.job)
                    if role == "build":
                        for name, body in files.items():
                            with root.open(args.job + "/" + name, os.O_CREAT | os.O_EXCL | os.O_WRONLY) as stream:
                                stream.write(body)
                                stream.fsync()
                    if role == "logs":
                        root.atomic_json(args.job + "/status.json", {"schema": "h039-artifact-status-v1", "job": args.job,
                            "status": "PLANNED", "verifiedFiles": 0, "verifiedWeightFiles": 0, "artifacts": []})
        print(json.dumps({"status": "STAGED_NOT_STARTED", "job": args.job, "files": {
            k: {"bytes": len(v), "sha256": hashlib.sha256(v).hexdigest()} for k, v in files.items()},
            "capacity": binding.verify()["capacity"]}))


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        print(json.dumps({"status": "FAILED", "failureType": type(exc).__name__}), file=sys.stderr)
        sys.exit(1)
