#!/usr/bin/env python3
"""Launch one staged H039 CPU-only artifact job; collect one immediate receipt.

Run on the Mac using the existing ai-vm alias. No polling, retry or GPU load.
Output is outside Git. A failed launch is preserved and never silently repeated.
"""
import argparse
import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import shlex
import subprocess

GUARDS = "/data/services/releases/h005-boot-restore-20260925/scripts"
RECOVERY_CUTOFF = datetime.datetime(2026, 10, 1, 2, 25, tzinfo=datetime.timezone.utc).timestamp()
H040_WINDOW = "h040-20261001"
H040_START = datetime.datetime(2026, 10, 1, 2, 26, 10, tzinfo=datetime.timezone.utc).timestamp()
H040_CUTOFF = datetime.datetime(2026, 10, 1, 4, 26, 10, tzinfo=datetime.timezone.utc).timestamp()


def remote(command):
    return subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12", "ai-vm", shlex.join(command)],
                          text=True, capture_output=True, timeout=45)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True)
    parser.add_argument("--attempt")
    parser.add_argument("--deadline-utc")
    parser.add_argument("--network-timeout-seconds", type=float, default=180)
    parser.add_argument("--expected-root-device", type=int)
    parser.add_argument("--expected-root-inode", type=int)
    parser.add_argument("--reviewed-window", help="explicit reviewed H040 continuation, never a general deadline override")
    parser.add_argument("--expected-original-status-sha256")
    parser.add_argument("--expected-original-manifest-sha256")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--reviewed-retry", action="store_true", help="explicit operator gate after root GO through INBOX")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"h039-vision-[a-z0-9-]{1,70}", args.job):
        raise ValueError("invalid_job_name")
    attempt = args.attempt or args.job
    if not re.fullmatch(r"h039-vision-[a-z0-9-]{1,70}", attempt):
        raise ValueError("invalid_attempt_name")
    if args.attempt:
        if attempt == args.job or not args.deadline_utc or args.expected_root_device is None or args.expected_root_inode is None:
            raise ValueError("distinct_attempt_deadline_and_root_identity_required")
        if not args.prepare_only and not args.reviewed_retry:
            raise ValueError("root_review_required")
    cutoff = RECOVERY_CUTOFF
    if args.reviewed_window is not None:
        if args.reviewed_window != H040_WINDOW:
            raise ValueError("unknown_reviewed_window")
        if not args.attempt or not attempt.startswith(args.job + "-h040-"):
            raise ValueError("h040_requires_distinct_tied_attempt")
        for value in (args.expected_original_status_sha256, args.expected_original_manifest_sha256):
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError("reviewed_original_receipt_hashes_required")
        if not math.isfinite(args.network_timeout_seconds) or not 1 <= args.network_timeout_seconds <= 180:
            raise ValueError("h040_network_timeout_must_be_1_to_180_seconds")
        cutoff = H040_CUTOFF
    if not math.isfinite(args.network_timeout_seconds) or not 1 <= args.network_timeout_seconds <= 600:
        raise ValueError("invalid_bounded_network_timeout")
    if args.receipt.exists():
        raise ValueError("receipt_already_exists")
    # Use VM time for the absolute two-hour work deadline.
    clock = remote(["/usr/bin/date", "+%s"])
    if clock.returncode:
        raise RuntimeError("vm_clock_unavailable")
    launch_epoch = int(clock.stdout.strip())
    if args.reviewed_window and launch_epoch < H040_START:
        raise ValueError("reviewed_window_not_open")
    deadline = int(datetime.datetime.fromisoformat(args.deadline_utc.replace("Z", "+00:00")).timestamp()) if args.deadline_utc else launch_epoch + 7200
    if not 0 < deadline - launch_epoch <= 7200 or deadline > cutoff:
        raise ValueError("deadline_outside_reviewed_recovery_window")
    maximum_seconds = deadline - launch_epoch
    unit = attempt + ".service"
    build = "/data/build/" + attempt
    logs = "/data/logs/" + attempt
    models = "/data/models-large/" + args.job
    command = ["/usr/bin/python3", "-I", build + "/artifact_job.py", "--guard-scripts", GUARDS,
               "--manifest", build + "/artifacts.lock.json", "--job", args.job, "--deadline-epoch", str(deadline),
               "--network-timeout-seconds", str(args.network_timeout_seconds)]
    if args.attempt:
        command += ["--attempt", attempt, "--expected-root-device", str(args.expected_root_device), "--expected-root-inode", str(args.expected_root_inode)]
    if args.reviewed_window:
        command += ["--reviewed-window", args.reviewed_window,
                    "--expected-original-status-sha256", args.expected_original_status_sha256,
                    "--expected-original-manifest-sha256", args.expected_original_manifest_sha256]
    properties = ["Type=exec", "Restart=no", "RuntimeMaxSec=" + str(maximum_seconds) + "s", "TimeoutStopSec=15s", "KillMode=control-group",
                  "MemoryMax=1G", "Nice=10", "IOWeight=20", "NoNewPrivileges=yes",
                  "ProtectHome=yes", "ProtectKernelTunables=yes", "ProtectKernelModules=yes", "ProtectControlGroups=yes",
                  "StandardOutput=null", "StandardError=journal",
                  "ExecStopPost=" + shlex.join(command + ["--finalize"])]
    argv = ["sudo", "-n", "systemd-run", "--unit", unit, "--description", "H039 bounded official vision artifact preparation"]
    for value in properties:
        argv += ["--property", value]
    argv += ["--", *command]
    receipt = {"schema": "h039-durable-download-launch-v1", "unit": unit, "job": args.job, "attempt": attempt,
               "launchEpoch": launch_epoch, "deadlineEpoch": deadline,
               "launchUtc": datetime.datetime.fromtimestamp(launch_epoch, datetime.timezone.utc).isoformat(),
               "deadlineUtc": datetime.datetime.fromtimestamp(deadline, datetime.timezone.utc).isoformat(),
               "maximumWorkSeconds": maximum_seconds, "supervisorStopGraceSeconds": 15, "automaticRetries": 0,
               "networkTimeoutSeconds": args.network_timeout_seconds, "expectedRootDevice": args.expected_root_device,
               "reviewedWindow": {"id": args.reviewed_window or "h039-expired-default", "cutoffEpoch": cutoff},
               "expectedRootInode": args.expected_root_inode, "sourceBuildRoot": build,
               "manifestPath": build + "/artifacts.lock.json", "statusPath": logs + "/status.json",
               "receiptManifestPath": logs + "/manifest.json", "artifactRoot": models,
               "canonicalLifecycleLeaseHeldDuringJob": True, "gpuLoads": 0, "properties": properties,
               "command": command, "supervisorArgv": argv,
               "status": "READY_FOR_ROOT_REVIEW" if args.prepare_only else "LAUNCH_REQUESTED"}
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    if args.prepare_only:
        print(json.dumps({k: receipt.get(k) for k in ("status", "unit", "artifactRoot", "deadlineUtc", "networkTimeoutSeconds")}))
        return 0
    started = remote(argv)
    receipt.update(launchExit=started.returncode, status="STARTED_NOT_VERIFIED" if started.returncode == 0 else "LAUNCH_FAILED")
    receipt["privateStderrDigest"] = {"sha256": hashlib.sha256(started.stderr.encode()).hexdigest(),
                                      "bytes": len(started.stderr.encode()), "exitCode": started.returncode}
    # Never expose manager/HTTP raw logs or environment in the compact receipt.
    if started.returncode == 0:
        observed = remote(["sudo", "-n", "systemctl", "show", unit, "--no-pager", "-p", "Id", "-p", "MainPID",
                           "-p", "ActiveState", "-p", "SubState", "-p", "Result", "-p", "ExecMainCode", "-p", "ExecMainStatus",
                           "-p", "RuntimeMaxUSec", "-p", "Restart", "-p", "ExecMainStartTimestamp"])
        receipt["supervisorSnapshotExit"] = observed.returncode
        receipt["supervisorSnapshot"] = dict(line.split("=", 1) for line in observed.stdout.splitlines() if "=" in line)
        code = "import json; from pathlib import Path; p=Path(" + repr(logs + "/status.json") + "); print(json.dumps(json.loads(p.read_text())))"
        snapshot = remote(["sudo", "-n", "/usr/bin/python3", "-I", "-c", code])
        receipt["artifactSnapshotExit"] = snapshot.returncode
        if snapshot.returncode == 0:
            receipt["artifactSnapshot"] = json.loads(snapshot.stdout)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: receipt.get(k) for k in ("status", "unit", "launchUtc", "deadlineUtc", "statusPath", "supervisorSnapshot")}))
    return started.returncode


if __name__ == "__main__":
    raise SystemExit(main())
