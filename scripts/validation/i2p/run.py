#!/usr/bin/env python3
"""Real primitives on an explicitly authorized ephemeral GitHub Linux VM only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import tempfile
import time
import uuid


def command(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=15,
                            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
    if result.returncode:
        raise RuntimeError("capability_command_failed:" + Path(argv[0]).name)
    return result.stdout.strip()


def validate_context(context):
    """An accidental-production guard, not a security boundary against root."""
    expected = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
                "GITHUB_REPOSITORY": "djeZo888/mixed-memory-llm-api-server",
                "I2P_DISPOSABLE_ACK": "github-hosted-ubuntu-24.04"}
    for key, value in expected.items():
        if context.get(key) != value:
            raise RuntimeError("refuse_context:" + key)
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        if not re.fullmatch(r"[1-9][0-9]*", context.get(key, "")):
            raise RuntimeError("refuse_context:" + key)
    if not re.fullmatch(r"[0-9a-f]{40}", context.get("GITHUB_SHA", "")):
        raise RuntimeError("refuse_context:GITHUB_SHA")


def capability(temp_root):
    if platform.system() != "Linux" or os.geteuid() != 0:
        raise RuntimeError("requires_disposable_linux_root")
    release = {}
    for line in Path("/etc/os-release").read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            release[key] = value.strip('"')
    if release.get("ID") != "ubuntu" or release.get("VERSION_ID") != "24.04":
        raise RuntimeError("requires_ubuntu_24_04")
    if platform.machine() != "x86_64" or command(["dpkg", "--print-architecture"]) != "amd64":
        raise RuntimeError("requires_real_amd64")
    if Path("/proc/1/comm").read_text().strip() != "systemd":
        raise RuntimeError("requires_systemd_pid1")
    if command(["stat", "-fc", "%T", "/sys/fs/cgroup"]) != "cgroup2fs":
        raise RuntimeError("requires_cgroup_v2")
    if command(["systemd-detect-virt", "--vm"]) in ("none", ""):
        raise RuntimeError("requires_virtual_machine")
    container = subprocess.run(["systemd-detect-virt", "--container", "--quiet"],
                               capture_output=True, timeout=15,
                               env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
    if container.returncode != 1:
        raise RuntimeError("containers_are_not_authorized")
    if not Path("/sys/fs/cgroup/cgroup.controllers").is_file():
        raise RuntimeError("missing_cgroup_controllers")
    for tool in ("systemd-run", "systemctl", "losetup", "mkfs.ext4", "blkid",
                 "findmnt", "mount", "umount", "wipefs", "lsblk"):
        if not shutil.which(tool):
            raise RuntimeError("missing_tool:" + tool)
    if not stat.S_ISCHR(Path("/dev/loop-control").stat().st_mode):
        raise RuntimeError("missing_loop_control")
    free = shutil.disk_usage(temp_root).free
    if free < 1024**3:
        raise RuntimeError("requires_1GiB_job_temp_free")
    return {"status": "PASS", "os": release.get("PRETTY_NAME"),
            "architecture": platform.machine(), "debian_architecture": "amd64",
            "kernel": platform.release(), "pid1": "systemd", "cgroup": "v2",
            "controllers": Path("/sys/fs/cgroup/cgroup.controllers").read_text().split(),
            "virtualization": command(["systemd-detect-virt", "--vm"]),
            "effective_uid": os.geteuid(), "cpu_count": os.cpu_count(),
            "memory_kib": int(re.search(r"^MemTotal:\s+(\d+)",
                                Path("/proc/meminfo").read_text(), re.M)[1]),
            "free_bytes_before": free,
            "systemd_version": command(["systemctl", "--version"]).splitlines()[0]}


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    path.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="describe bounds; no Linux mutation")
    parser.add_argument("--output-dir", type=Path, help="new private evidence directory under RUNNER_TEMP")
    args = parser.parse_args()
    plan = {"scope": "primitive_proof_only", "systemd": "two bounded fake-package transient units",
            "storage": "one exclusive 64MiB sparse file and its recorded loop only",
            "cleanup": "identity checked units/mount/loop; preserve backing and evidence",
            "not_tested": ["installer", "I1R watcher", "I1S storage", "apt", "GPU", "reboot"]}
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return 0
    keys = ("GITHUB_ACTIONS", "RUNNER_ENVIRONMENT", "GITHUB_REPOSITORY", "GITHUB_SHA",
            "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "I2P_DISPOSABLE_ACK", "RUNNER_TEMP",
            "ImageOS", "ImageVersion")
    context = {key: os.environ.get(key, "") for key in keys}
    validate_context(context)
    temp_root = Path(context["RUNNER_TEMP"])
    if not temp_root.is_absolute() or temp_root.is_symlink() or not temp_root.is_dir():
        raise RuntimeError("unsafe_runner_temp")
    if args.output_dir is None or args.output_dir.parent.resolve() != temp_root.resolve():
        raise RuntimeError("output_must_be_new_directory_directly_under_runner_temp")
    os.umask(0o077)
    args.output_dir.mkdir(mode=0o700)  # exclusive; refuse stale/symlink destinations
    run_id = "i2p-" + uuid.uuid4().hex
    workdir = Path(tempfile.mkdtemp(prefix=run_id + "-", dir=temp_root))
    started = time.time()
    evidence = {"schema": 1, "status": "FAIL", "run_id": run_id, "plan": plan,
                "source_sha": context["GITHUB_SHA"], "github_run_id": context["GITHUB_RUN_ID"],
                "github_run_attempt": context["GITHUB_RUN_ATTEMPT"],
                "image_os": context["ImageOS"], "image_version": context["ImageVersion"],
                "image_immutable_pin": False, "workdir": str(workdir),
                "capability": {"status": "NOT_TESTED"},
                "systemd": {"status": "NOT_TESTED"}, "loop": {"status": "NOT_TESTED"}}
    write_json(args.output_dir / "plan.json", plan)
    source_root = Path(__file__).resolve().parent
    manifest = {str(p.relative_to(source_root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(source_root.glob("*.py"))}
    write_json(args.output_dir / "source-manifest.json", manifest)
    try:
        evidence["capability"] = capability(temp_root)
        print("I2P capability PASS: real Ubuntu24.04 amd64 systemd PID1 cgroupv2 VM", flush=True)
        import systemd_probe
        import loop_probe
        systemd_dir = workdir / "systemd"
        loop_dir = workdir / "loop"
        systemd_dir.mkdir(mode=0o700)
        loop_dir.mkdir(mode=0o700)
        evidence["systemd"] = systemd_probe.run(systemd_dir, run_id)
        write_json(args.output_dir / "evidence.json", evidence)
        if evidence["systemd"].get("status") != "PASS":
            raise RuntimeError("systemd_probe_failed")
        print("I2P systemd probe completed", flush=True)
        evidence["loop"] = loop_probe.run(loop_dir, run_id)
        if evidence["loop"].get("status") != "PASS":
            raise RuntimeError("loop_probe_failed")
        evidence["status"] = "PASS"
    except Exception as exc:
        # Probe errors are fixed messages; never relay captured command stdout/stderr.
        evidence["failure_type"] = type(exc).__name__
        evidence["failure_code"] = str(exc)[:240]
    finally:
        evidence["elapsed_seconds"] = round(time.time() - started, 3)
        evidence["free_bytes_after"] = shutil.disk_usage(temp_root).free
        write_json(args.output_dir / "evidence.json", evidence)
    print("I2P result: " + evidence["status"], flush=True)
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
