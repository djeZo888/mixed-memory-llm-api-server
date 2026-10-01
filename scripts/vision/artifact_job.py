#!/usr/bin/env python3
"""CPU-only, one-attempt public artifact acquisition using installed storage guards.

No model imports, package installation, GPU access, credentials or route changes.
The canonical lifecycle lease is held for the write transaction. Partials and
hash failures are retained; an explicit reviewed rerun can resume exact ranges.
"""
import argparse
import contextlib
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request

APPROVED = {"Qwen/Qwen3.5-9B", "PaddlePaddle/PaddleOCR-VL-1.6"}
CHUNK = 1024 * 1024
RESERVE_BYTES = 64 * 1024**3


class JobFailure(Exception):
    pass


def validate_manifest(manifest):
    models = manifest.get("models", [])
    if len(models) != 2 or {m["repo"] for m in models} != APPROVED:
        raise JobFailure("approved_pair_required")
    for model in models:
        revision = model["revision"]
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise JobFailure("immutable_revision_required")
        expected_dir = model["repo"].split("/")[1].lower() + "-" + revision
        if model["directory"] != expected_dir or not model["files"]:
            raise JobFailure("invalid_model_directory")
        names = set()
        for item in model["files"]:
            name = item["path"]
            if (not isinstance(name, str) or not name or name.startswith("/") or "\\" in name
                    or any(p in ("", ".", "..") for p in name.split("/")) or name in names
                    or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
                    or type(item["size"]) is not int or item["size"] < 0):
                raise JobFailure("invalid_artifact")
            names.add(name)
    return manifest


def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def check_deadline(deadline):
    if time.time() >= deadline:
        raise JobFailure("deadline_exceeded")


def digest(stream, deadline):
    value = hashlib.sha256()
    stream.seek(0)
    while True:
        check_deadline(deadline)
        block = stream.read(CHUNK)
        if not block:
            return value.hexdigest()
        value.update(block)


def transfer(root, relative, model, item, deadline, progress):
    """Never overwrite a final artifact or discard a failed/incomplete partial."""
    final = root.stat(relative, missing_ok=True)
    if final is not None:
        if final.st_size != item["size"]:
            raise JobFailure("existing_final_size_mismatch")
        with root.open(relative) as stream:
            if digest(stream, deadline) != item["sha256"]:
                raise JobFailure("existing_final_hash_mismatch")
        progress("HASH_VERIFIED_REUSED", item["size"])
        return
    parent = str(Path(relative).parent)
    root.mkdir(parent)
    partial = relative + ".partial"
    with root.open(partial, os.O_CREAT | os.O_RDWR) as stream:
        offset = stream.stat().st_size
        if offset > item["size"]:
            raise JobFailure("partial_larger_than_expected")
        progress("PARTIAL", offset)
        if offset < item["size"]:
            url = "https://huggingface.co/" + model["repo"] + "/resolve/" + model["revision"] + "/" + urllib.parse.quote(item["path"])
            headers = {"Accept-Encoding": "identity", "User-Agent": "H039-public-artifact-preparation/1"}
            if offset:
                headers["Range"] = "bytes=" + str(offset) + "-"
            check_deadline(deadline)
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=min(30, max(1, deadline-time.time()))) as response:
                if offset:
                    wanted = f"bytes {offset}-{item['size']-1}/{item['size']}"
                    if response.status != 206 or response.headers.get("Content-Range") != wanted:
                        raise JobFailure("resume_range_not_honored")
                elif response.status != 200:
                    raise JobFailure("unexpected_download_status")
                stream.seek(offset)
                notified = time.monotonic()
                while offset < item["size"]:
                    check_deadline(deadline)
                    if os.fstatvfs(root.fileno()).f_bavail * os.fstatvfs(root.fileno()).f_frsize < RESERVE_BYTES:
                        raise JobFailure("model_disk_reserve_exhausted")
                    block = response.read(min(CHUNK, item["size"] - offset))
                    if not block:
                        raise JobFailure("incomplete_response")
                    stream.write(block)
                    offset += len(block)
                    if time.monotonic() - notified >= 10:
                        progress("PARTIAL", offset)
                        notified = time.monotonic()
                if response.read(1):
                    raise JobFailure("response_exceeds_expected_size")
        stream.fsync()
        progress("DOWNLOADED_NOT_HASH_VERIFIED", offset)
        if digest(stream, deadline) != item["sha256"]:
            progress("HASH_MISMATCH_RETAINED", offset)
            raise JobFailure("download_hash_mismatch")
    root.replace(partial, relative)
    progress("HASH_VERIFIED", item["size"])


class Runner:
    def run(self, argv, *, timeout=30, env=None):
        return subprocess.run(argv, timeout=timeout, check=True, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              stdin=subprocess.DEVNULL,
                              env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guard-scripts", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--deadline-epoch", type=float, required=True)
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"h039-vision-[a-z0-9-]{1,70}", args.job):
        raise JobFailure("invalid_job_name")
    if not args.finalize and not 0 < args.deadline_epoch - time.time() <= 7200:
        raise JobFailure("deadline_must_be_within_two_hours")
    sys.path.insert(0, args.guard_scripts)
    from common.lifecycle_lease import acquire_lease
    from lifecycle.storage_binding import RegisteredStorageBinding
    from install import storage_io
    manifest = validate_manifest(json.loads(args.manifest.read_text()))
    # Nonblocking contention is a retained failure; there is no retry loop.
    with acquire_lease(blocking=False) as lease:
        binding = RegisteredStorageBinding.load(Runner())
        with binding.mounted_guard(storage_io) as guard, contextlib.ExitStack() as stack:
            logs = stack.enter_context(storage_io.AnchoredRoot(binding.path("logs"), guard))
            logs.mkdir(args.job)
            receipts = stack.enter_context(logs.directory(args.job))
            if args.finalize:
                status = receipts.read_json("status.json")
                status["supervisor"] = {k: os.environ.get(k) for k in ("SERVICE_RESULT", "EXIT_CODE", "EXIT_STATUS")}
                if status["status"] == "PLANNED":
                    status.update(status="FAILED", failureCode="failed_before_running_receipt", finishedUtc=timestamp())
                elif status["status"] == "RUNNING":
                    status.update(status="TIMED_OUT" if time.time() >= args.deadline_epoch or os.environ.get("SERVICE_RESULT") == "timeout" else "STOPPED", finishedUtc=timestamp())
                receipts.atomic_json("status.json", status)
                return 0
            models = stack.enter_context(storage_io.AnchoredRoot(binding.path("models"), guard))
            models.mkdir(args.job)
            destination = stack.enter_context(models.directory(args.job))
            total = sum(f["size"] for m in manifest["models"] for f in m["files"])
            if binding.verify()["capacity"]["model_available_bytes"] < total + RESERVE_BYTES:
                raise JobFailure("insufficient_model_disk_capacity")
            state = {"schema": "h039-artifact-status-v1", "job": args.job, "status": "RUNNING",
                     "pid": os.getpid(), "startedUtc": timestamp(), "deadlineEpoch": args.deadline_epoch,
                     "expectedBytes": total, "verifiedFiles": 0, "verifiedWeightFiles": 0,
                     "artifacts": [], "terminalReceipt": str(Path(binding.path("logs"))/args.job/"status.json")}
            receipts.atomic_json("manifest.json", manifest)
            receipts.atomic_json("status.json", state)
            def stop(_signal, _frame):
                raise JobFailure("deadline_exceeded" if time.time() >= args.deadline_epoch else "supervisor_stop")
            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
            signal.signal(signal.SIGALRM, stop)
            signal.setitimer(signal.ITIMER_REAL, max(0.01, args.deadline_epoch-time.time()))
            try:
                for model in manifest["models"]:
                    # Small metadata first; a shard is never called verified from bytes alone.
                    for item in sorted(model["files"], key=lambda f: (f["size"] > 64*1024**2, f["path"])):
                        row = {"repo": model["repo"], "revision": model["revision"], "path": item["path"],
                               "expectedBytes": item["size"], "expectedSha256": item["sha256"], "status": "PENDING", "bytes": 0}
                        state["artifacts"].append(row)
                        def progress(status, count):
                            lease.validate()
                            row.update(status=status, bytes=count)
                            state["updatedUtc"] = timestamp()
                            state["verifiedFiles"] = sum(r["status"].startswith("HASH_VERIFIED") for r in state["artifacts"])
                            state["verifiedWeightFiles"] = sum(r["status"].startswith("HASH_VERIFIED") and r["path"].endswith(".safetensors") for r in state["artifacts"])
                            receipts.atomic_json("status.json", state)
                        transfer(destination, model["directory"] + "/" + item["path"], model, item, args.deadline_epoch, progress)
                state["status"] = "VERIFIED"
            except BaseException as exc:
                code = str(exc) if isinstance(exc, JobFailure) else type(exc).__name__
                state.update(status="TIMED_OUT" if code == "deadline_exceeded" else "FAILED", failureCode=code)
                # Actual retained bytes, including the final unreported chunk.
                if state["artifacts"]:
                    row = state["artifacts"][-1]
                    partial = destination.stat(model["directory"] + "/" + row["path"] + ".partial", missing_ok=True)
                    if partial is not None:
                        row["bytes"] = partial.st_size
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                state["finishedUtc"] = timestamp()
                receipts.atomic_json("status.json", state)
            return 0 if state["status"] == "VERIFIED" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BaseException as exc:
        # Never log raw HTTP exceptions (signed URLs) or protected environments.
        print(json.dumps({"status": "FAILED_BEFORE_OR_AFTER_RECEIPT", "failureType": type(exc).__name__}), file=sys.stderr)
        sys.exit(1)
