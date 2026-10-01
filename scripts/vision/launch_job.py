#!/usr/bin/env python3
"""Launch one staged H039 CPU-only artifact job; collect one immediate receipt.

Run on the Mac using the existing ai-vm alias. No polling, retry or GPU load.
Output is outside Git. A failed launch is preserved and never silently repeated.
"""
import argparse
import datetime
import json
from pathlib import Path
import re
import shlex
import subprocess

GUARDS = "/data/services/releases/h005-boot-restore-20260925/scripts"


def remote(command):
    return subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12", "ai-vm", shlex.join(command)],
                          text=True, capture_output=True, timeout=45)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"h039-vision-[a-z0-9-]{1,70}", args.job):
        raise ValueError("invalid_job_name")
    # Use VM time for the absolute two-hour work deadline.
    clock = remote(["/usr/bin/date", "+%s"])
    if clock.returncode:
        raise RuntimeError("vm_clock_unavailable")
    launch_epoch = int(clock.stdout.strip())
    deadline = launch_epoch + 7200
    unit = args.job + ".service"
    build = "/data/build/" + args.job
    logs = "/data/logs/" + args.job
    models = "/data/models-large/" + args.job
    command = ["/usr/bin/python3", "-I", build + "/artifact_job.py", "--guard-scripts", GUARDS,
               "--manifest", build + "/artifacts.lock.json", "--job", args.job, "--deadline-epoch", str(deadline)]
    properties = ["Type=exec", "Restart=no", "RuntimeMaxSec=7200s", "TimeoutStopSec=15s", "KillMode=control-group",
                  "MemoryMax=1G", "Nice=10", "IOWeight=20", "NoNewPrivileges=yes",
                  "ProtectHome=yes", "ProtectKernelTunables=yes", "ProtectKernelModules=yes", "ProtectControlGroups=yes",
                  "StandardOutput=null", "StandardError=journal",
                  "ExecStopPost=" + shlex.join(command + ["--finalize"])]
    argv = ["sudo", "-n", "systemd-run", "--unit", unit, "--description", "H039 bounded official vision artifact preparation"]
    for value in properties:
        argv += ["--property", value]
    argv += ["--", *command]
    receipt = {"schema": "h039-durable-download-launch-v1", "unit": unit, "job": args.job,
               "launchEpoch": launch_epoch, "deadlineEpoch": deadline,
               "launchUtc": datetime.datetime.fromtimestamp(launch_epoch, datetime.timezone.utc).isoformat(),
               "deadlineUtc": datetime.datetime.fromtimestamp(deadline, datetime.timezone.utc).isoformat(),
               "maximumWorkSeconds": 7200, "supervisorStopGraceSeconds": 15, "automaticRetries": 0,
               "manifestPath": build + "/artifacts.lock.json", "statusPath": logs + "/status.json",
               "receiptManifestPath": logs + "/manifest.json", "artifactRoot": models,
               "canonicalLifecycleLeaseHeldDuringJob": True, "gpuLoads": 0, "properties": properties,
               "status": "LAUNCH_REQUESTED"}
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    started = remote(argv)
    receipt.update(launchExit=started.returncode, status="STARTED_NOT_VERIFIED" if started.returncode == 0 else "LAUNCH_FAILED")
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
