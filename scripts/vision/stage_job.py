#!/usr/bin/env python3
"""Guarded bootstrap: stage two owned task files, not a production release."""
import argparse
import base64
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

H040_WINDOW = "h040-20261001"
H040_START = datetime.datetime(2026, 10, 1, 2, 26, 10, tzinfo=datetime.timezone.utc).timestamp()
H040_CUTOFF = datetime.datetime(2026, 10, 1, 4, 26, 10, tzinfo=datetime.timezone.utc).timestamp()
RECOVERY_CUTOFF = datetime.datetime(2026, 10, 1, 2, 25, tzinfo=datetime.timezone.utc).timestamp()


class StageFailure(Exception):
    def __init__(self, code, command_receipt=None):
        self.code, self.command_receipt = code, command_receipt
        super().__init__(code)


class Runner:
    def run(self, argv, *, timeout=30, env=None):
        try:
            result = subprocess.run(argv, timeout=timeout, check=False, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    stdin=subprocess.DEVNULL,
                                    env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
        except subprocess.TimeoutExpired as exc:
            body = exc.stderr or b""
            if isinstance(body, str):
                body = body.encode()
            raise StageFailure("stage_guard_command_timeout", {"exitCode": None, "timedOut": True,
                "stderrSha256": hashlib.sha256(body).hexdigest(), "stderrBytes": len(body)}) from None
        if result.returncode:
            body = result.stderr.encode()
            raise StageFailure("stage_guard_command_failed", {"exitCode": result.returncode,
                "stderrSha256": hashlib.sha256(body).hexdigest(), "stderrBytes": len(body)})
        return result.stdout


def receipt_hash(root, name):
    value = hashlib.sha256()
    with root.open(name) as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                return value.hexdigest()
            value.update(block)


def fsync_attempt_directory(root, attempt):
    """Persist newly created entries through the held, checked storage anchor."""
    with root.directory(attempt) as directory:
        directory.check()
        os.fsync(directory.fileno())
        directory.check()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guard-scripts", required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--artifact-job", help="reuse this original artifact namespace; do not create a second model root")
    parser.add_argument("--reviewed-window")
    parser.add_argument("--deadline-epoch", type=float)
    parser.add_argument("--expected-root-device", type=int)
    parser.add_argument("--expected-root-inode", type=int)
    parser.add_argument("--expected-original-status-sha256")
    parser.add_argument("--expected-original-manifest-sha256")
    parser.add_argument("--expected-worker-sha256")
    parser.add_argument("--expected-manifest-sha256")
    args = parser.parse_args()
    if not re.fullmatch(r"h039-vision-[a-z0-9-]{1,70}", args.job):
        raise StageFailure("invalid_job_name")
    if args.artifact_job and (not re.fullmatch(r"h039-vision-[a-z0-9-]{1,70}", args.artifact_job) or args.artifact_job == args.job):
        raise StageFailure("distinct_original_artifact_job_required")
    authority = {"id": "h039-expired-default", "cutoffEpoch": RECOVERY_CUTOFF}
    if args.reviewed_window is not None:
        if args.reviewed_window != H040_WINDOW:
            raise StageFailure("unknown_reviewed_window")
        if not args.artifact_job or not args.job.startswith(args.artifact_job + "-h040-"):
            raise StageFailure("h040_requires_distinct_tied_attempt")
        if time.time() < H040_START:
            raise StageFailure("reviewed_window_not_open")
        if args.deadline_epoch is None or not math.isfinite(args.deadline_epoch) or not 0 < args.deadline_epoch - time.time() <= 7200 or args.deadline_epoch > H040_CUTOFF:
            raise StageFailure("deadline_outside_reviewed_recovery_window")
        for value in (args.expected_worker_sha256, args.expected_manifest_sha256,
                      args.expected_original_status_sha256, args.expected_original_manifest_sha256):
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise StageFailure("reviewed_payload_and_receipt_hashes_required")
        authority = {"id": H040_WINDOW, "cutoffEpoch": H040_CUTOFF}
    elif time.time() >= RECOVERY_CUTOFF:
        raise StageFailure("old_review_window_expired")
    if args.artifact_job and (args.expected_root_device is None or args.expected_root_inode is None):
        raise StageFailure("reviewed_original_root_identity_required")
    payload = json.loads(sys.stdin.buffer.read(256 * 1024))
    if set(payload) != {"artifact_job.py", "artifacts.lock.json"}:
        raise StageFailure("only_owned_job_payload_allowed")
    files = {name: base64.b64decode(value, validate=True) for name, value in payload.items()}
    if any(len(v) > 128 * 1024 for v in files.values()):
        raise StageFailure("oversized_job_payload")
    for name, expected in (("artifact_job.py", args.expected_worker_sha256), ("artifacts.lock.json", args.expected_manifest_sha256)):
        if expected is not None and hashlib.sha256(files[name]).hexdigest() != expected:
            raise StageFailure("reviewed_payload_hash_mismatch")
    sys.path.insert(0, args.guard_scripts)
    from common.lifecycle_lease import acquire_lease
    from lifecycle.storage_binding import RegisteredStorageBinding
    from install import storage_io
    def check_window():
        if time.time() >= (args.deadline_epoch if args.reviewed_window else RECOVERY_CUTOFF):
            raise StageFailure("deadline_outside_reviewed_recovery_window")
    with acquire_lease(blocking=False):
        binding = RegisteredStorageBinding.load(Runner())
        with binding.mounted_guard(storage_io) as guard:
            if args.artifact_job:
                with storage_io.AnchoredRoot(binding.path("logs") + "/" + args.artifact_job, guard) as original:
                    for name, expected in (("status.json", args.expected_original_status_sha256),
                                           ("manifest.json", args.expected_original_manifest_sha256)):
                        if expected is not None and receipt_hash(original, name) != expected:
                            raise StageFailure("original_receipt_hash_changed")
                    if original.read_json("manifest.json") != json.loads(files["artifacts.lock.json"]):
                        raise StageFailure("original_manifest_must_match_exactly")
                    if original.read_json("status.json")["status"] not in ("FAILED", "TIMED_OUT", "STOPPED"):
                        raise StageFailure("original_attempt_must_be_failed_or_stopped")
                with storage_io.AnchoredRoot(binding.path("models"), guard) as root:
                    info = root.stat(args.artifact_job)
                    if (info.st_dev, info.st_ino) != (args.expected_root_device, args.expected_root_inode):
                        raise StageFailure("original_artifact_root_identity_changed")
            # Refuse adoption/re-staging here. Partial namespaces remain evidence
            # for root to inspect; no cleanup or implicit retry.
            for role in ("build", "logs"):
                with storage_io.AnchoredRoot(binding.path(role), guard) as root:
                    if root.stat(args.job, missing_ok=True) is not None:
                        raise StageFailure("attempt_namespace_already_exists")
            with storage_io.AnchoredRoot(binding.path("logs"), guard) as root:
                check_window()
                root.mkdir(args.job)
                check_window()
                with root.open(args.job + "/stage.claim.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY) as stream:
                    stream.write(json.dumps({"job": args.artifact_job or args.job, "attempt": args.job,
                        "reviewedWindow": authority, "deadlineEpoch": args.deadline_epoch,
                        "pid": os.getpid(), "payloadHashes": {name: hashlib.sha256(body).hexdigest() for name, body in files.items()}}).encode())
                    stream.fsync()
                fsync_attempt_directory(root, args.job)
            for role in ("build", "logs", "models"):
                with storage_io.AnchoredRoot(binding.path(role), guard) as root:
                    if role == "models" and args.artifact_job:
                        continue
                    check_window()
                    root.mkdir(args.job)
                    if role == "build":
                        for name, body in files.items():
                            check_window()
                            with root.open(args.job + "/" + name, os.O_CREAT | os.O_EXCL | os.O_WRONLY) as stream:
                                stream.write(body)
                                stream.fsync()
                    if role == "logs":
                        check_window()
                        with root.open(args.job + "/status.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY) as stream:
                            stream.write(json.dumps({"schema": "h039-artifact-status-v1", "job": args.artifact_job or args.job,
                                "attempt": args.job, "reviewedWindow": authority, "deadlineEpoch": args.deadline_epoch,
                                "status": "PLANNED", "verifiedFiles": 0, "verifiedWeightFiles": 0, "artifacts": []}).encode())
                            stream.fsync()
                    fsync_attempt_directory(root, args.job)
        print(json.dumps({"status": "STAGED_NOT_STARTED", "job": args.job, "reviewedWindow": authority, "files": {
            k: {"bytes": len(v), "sha256": hashlib.sha256(v).hexdigest()} for k, v in files.items()},
            "capacity": binding.verify()["capacity"]}))
    return 0


def cli():
    try:
        return main()
    except Exception as exc:
        # Only a stable guard code/type and private command stderr digest/exit.
        # No exception text, raw subprocess output, URLs or environments.
        failure = {"status": "FAILED", "failureType": type(exc).__name__}
        code = getattr(exc, "code", None)
        if isinstance(code, str) and re.fullmatch(r"[a-z0-9_]{1,100}", code):
            failure["failureCode"] = code
        if isinstance(exc, StageFailure) and exc.command_receipt is not None:
            failure["privateCommandReceipt"] = exc.command_receipt
        print(json.dumps(failure), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(cli())
