#!/usr/bin/env python3
"""H043 fixed passive image readback and DISABLED native workflow proposal.

No service imports, status CLI, inference, authentication, lifecycle or installation.
The only public modes are --observe and --proposal; neither can execute a workflow.
Readback (including idle or ready metadata) never qualifies a live workflow.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import sys
import time

SCHEMA = "h043-image-passive-v1"
HOST = "ai-vm"
GPU = "GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23"
VISION_GPU = "GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf"
GPU_PATTERN = r"GPU-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
OWNER = "IMAGE21-RUNTIME-20260923"
BASE = "/data/services/image21-runtime-20260923"
RELEASE = "/data/services/releases/h037-image-placement-20260930"
REV = "790c92633540aa0cb11d9abf19eb46d861714758"
UPSTREAM = "0cd8be351d0825488f4b81c8931167bbab618eca"
PLATFORM = "sha256:50a3bfd20fc931f05fc5fc919b0445abbce30d5c7716424d697a7ab6708c08ef"
CONFIG = "sha256:3f6178faa74c4a9bcb95ed4304dbee57473efa8913a793e067014af4a98281ad"
PARENT = "sha256:dafbccb763cff6a6aa3777c7c0a8cc185d838bd4b9f61bec8007f57f2c7233f8"
MODEL = "/data/models-large/qwen-image-2.1-" + REV
UNIT = "llm-image-backend.service"
NAME = "llm-image-backend"
RUNTIME_FILES = ("native_request.py", "native_server.py", "service.py", "telemetry.py")
RELEASE_FILES = (
    "scripts/common/lifecycle_lease.py", "scripts/common/registered-storage.py",
    "scripts/control/__init__.py", "scripts/control/installation.py", "scripts/control/hardware_latch.py",
    "scripts/install/__init__.py", "scripts/install/storage.py", "scripts/install/storage_io.py",
    "scripts/lifecycle/__init__.py", "scripts/lifecycle/manager.py", "scripts/lifecycle/runtime_io.py",
    "scripts/lifecycle/storage_binding.py", "scripts/lifecycle/qwen_next.py", "scripts/lifecycle/slot_state.py",
    "scripts/lifecycle/hardware_policy.py", "scripts/runtime/qwen38_oci.py",
    "scripts/runtime/h005_runtime_binding.py", "configs/runtimes/h005-runtime-binding.json",
    "scripts/runtime/verify_adaptive_idle_overlay.py", "scripts/runtime/adaptive_idle_sources.json",
    "scripts/runtime/adaptive_idle_source_gate.py", "scripts/runtime/build_adaptive_idle_overlay.py",
    "scripts/runtime/adaptive_idle.py", "scripts/runtime/adaptive_text.py", "scripts/runtime/adaptive_text_drain.py",
    "scripts/runtime/adaptive_diffusion.py", "scripts/runtime/adaptive_diffusion_drain.py",
    "scripts/runtime/patches/text-adaptive-idle.patch", "scripts/runtime/patches/text-adaptive-drain.patch",
    "scripts/runtime/patches/text-adaptive-grammar.patch", "scripts/runtime/patches/diffusion-adaptive-idle.patch",
    "scripts/runtime/patches/diffusion-adaptive-drain.patch", "scripts/image_runtime/source-closure.json",
)
API_FILES = ("__init__.py", "serve.py", "protection.py", "protocol.py", "uploads.py", "backend.py", "app.py")
API_ROOT = "/usr/local/lib/llm-server/image-api/scripts/image_api"
HELPER = "/usr/local/libexec/llm-image-backend-recover"
READ_PATHS = frozenset(
    [BASE + "/" + p + ".json" for p in ("config", "state", "operation", "recovery")]
    + [MODEL + "/CHECKPOINT-RECEIPT.json", "/opt/llmctl/adaptive-idle/image.json", "/etc/llm-server/image-api.json",
       "/proc/sys/kernel/random/boot_id", "/proc/meminfo", HELPER, "/etc/systemd/system/" + UNIT,
       "/opt/llmctl/adaptive-idle/verify.py", "/etc/systemd/system/llm-image-api.service"]
    + [BASE + "/source/" + p for p in RUNTIME_FILES]
    + [RELEASE + "/" + p for p in RELEASE_FILES]
    + [API_ROOT + "/" + p for p in API_FILES]
)
SYSTEMD_FIELDS = (
    "Id", "User", "Group", "MainPID", "ControlPID", "ExecMainPID", "InvocationID", "ControlGroup",
    "ActiveState", "SubState", "Result", "ExecMainCode", "ExecMainStatus", "ExecMainStartTimestampMonotonic",
    "ExecMainExitTimestampMonotonic", "ActiveEnterTimestampMonotonic", "FragmentPath", "NeedDaemonReload",
)
# Go templates select fields at the daemon: never request Config.Env, command lines,
# Docker logs, all labels or full inspection and redact them after the fact.
CONTAINER_FORMAT = '''{"id":{{json .Id}},"name":{{json .Name}},"image":{{json .Image}},"configImage":{{json .Config.Image}},"created":{{json .Created}},"pid":{{json .State.Pid}},"status":{{json .State.Status}},"running":{{json .State.Running}},"oomKilled":{{json .State.OOMKilled}},"exitCode":{{json .State.ExitCode}},"startedAt":{{json .State.StartedAt}},"finishedAt":{{json .State.FinishedAt}},"owner":{{json (index .Config.Labels "io.llm-image.owner")}},"invocation":{{json (index .Config.Labels "io.llm-image.invocation")}},"gpu":{{json (index .Config.Labels "io.llm-image.gpu")}},"memory":{{json .HostConfig.Memory}},"memorySwap":{{json .HostConfig.MemorySwap}},"cpuset":{{json .HostConfig.CpusetCpus}},"mems":{{json .HostConfig.CpusetMems}},"privileged":{{json .HostConfig.Privileged}},"readonly":{{json .HostConfig.ReadonlyRootfs}},"restart":{{json .HostConfig.RestartPolicy.Name}},"devices":[{{range $i,$d := .HostConfig.DeviceRequests}}{{if $i}},{{end}}{"driver":{{json $d.Driver}},"count":{{json $d.Count}},"ids":{{json $d.DeviceIDs}},"capabilities":{{json $d.Capabilities}}}{{end}}],"mounts":[{{range $i,$m := .Mounts}}{{if $i}},{{end}}{"type":{{json $m.Type}},"source":{{json $m.Source}},"destination":{{json $m.Destination}},"rw":{{json $m.RW}}}{{end}}]}'''
IMAGE_FORMAT = '''{"id":{{json .Id}},"repoDigests":{{json .RepoDigests}},"os":{{json .Os}},"architecture":{{json .Architecture}},"created":{{json .Created}}}'''
COMMANDS = {
    "gpu_inventory": (("/usr/bin/nvidia-smi", "--query-gpu=uuid,pci.bus_id,memory.total,memory.used,memory.free,temperature.gpu", "--format=csv,noheader,nounits"), 5),
    "gpu_processes": (("/usr/bin/nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_memory", "--format=csv,noheader,nounits"), 5),
    "image_link": (("/usr/bin/nvidia-smi", "--id=" + GPU, "--query-gpu=uuid,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max", "--format=csv,noheader,nounits"), 5),
    "systemd_owner": (("/usr/bin/systemctl", "show", UNIT, "--property=" + ",".join(SYSTEMD_FIELDS)), 5),
    "native_container": (("/usr/bin/docker", "container", "inspect", "--format", CONTAINER_FORMAT, NAME), 5),
    "native_image": (("/usr/bin/docker", "image", "inspect", "--format", IMAGE_FORMAT, PLATFORM), 5),
    "image_ports": (("/usr/bin/ss", "-H", "-ltn", "sport = :30006 or sport = :30007"), 5),
}
SSH = ("/usr/bin/ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
       "-o", "ConnectionAttempts=1", "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=1",
       HOST, "/usr/bin/python3", "-I", "-B", "-", "--remote-observe")
CAPS = {"commandCount": 7, "commandSeconds": 5, "commandStdoutBytes": 65536,
        "commandStderrBytes": 8192, "remoteSeconds": 75, "transportSeconds": 90,
        "transportStdoutBytes": 1048576, "fileCount": 64, "fileBytes": 262144,
        "totalFileBytes": 4194304, "jsonBytes": 65536, "processCount": 16,
        "gpuCount": 8, "gpuProcessCount": 64, "mountCount": 12}


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class Refused(ValueError):
    pass


def strict_json(raw, *, maximum=65536, depth_cap=8, string_cap=1024):
    if len(raw) > maximum:
        raise Refused("json_byte_cap")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Refused("duplicate_json_key")
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(Refused("nonfinite_json")))
    def bounded(v, depth=0):
        if depth > depth_cap:
            raise Refused("json_depth_cap")
        if isinstance(v, (dict, list)):
            if len(v) > 128:
                raise Refused("json_count_cap")
            for item in (v.values() if isinstance(v, dict) else v):
                bounded(item, depth + 1)
        elif isinstance(v, str) and len(v) > string_cap:
            raise Refused("json_string_cap")
    bounded(value)
    return value


def safe_error(raw):
    """Keep bounded nonsecret diagnostics from fixed observations only."""
    value = raw.decode("utf-8", "replace")
    value = re.sub(r"(?i)(authorization|bearer|token|password|secret|api[_-]?key)(\s*[:=]?\s*)\S+", r"\1\2[REDACTED]", value)
    return value


def run_bounded(argv, *, timeout, stdout_cap, stdin=b"", host=HOST, cwd="/"):
    """Internal fixed invocations; streaming caps and actual owned child exit.

    No shell, environment dump, inherited token variables or unbounded communicate.
    Timeout/cap kills only this reader's newly spawned observation/SSH child.
    This is never a backend cancellation/settlement proof.
    """
    started = utc()
    receipt = {"argv": list(argv), "cwd": cwd, "host": host, "startedUtc": started,
               "timeoutSeconds": timeout, "stdoutByteCap": stdout_cap,
               "stderrByteCap": CAPS["commandStderrBytes"], "stdinBytes": len(stdin),
               "stdinSha256": sha(stdin), "exitCode": None, "outcome": "UNKNOWN"}
    if tuple(argv) not in {SSH, *(item[0] for item in COMMANDS.values())}:
        raise Refused("command_not_allowlisted")
    if not 0 < timeout <= CAPS["transportSeconds"] or not 0 < stdout_cap <= CAPS["transportStdoutBytes"] or len(stdin) > 131072:
        raise Refused("invocation_cap_invalid")
    streams = {"stdout": bytearray(), "stderr": bytearray()}
    try:
        child = subprocess.Popen(list(argv), cwd=cwd, stdin=subprocess.PIPE if stdin else subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}, shell=False)
    except OSError as exc:
        receipt.update(finishedUtc=utc(), failure="spawn_refused", errno=exc.errno)
        return receipt, b"", b""
    receipt["observerPid"] = child.pid
    deadline = time.monotonic() + timeout
    reason = None
    pending = memoryview(stdin)
    selector = selectors.DefaultSelector()
    for key in ("stdout", "stderr"):
        pipe = getattr(child, key)
        os.set_blocking(pipe.fileno(), False)
        selector.register(pipe, selectors.EVENT_READ, key)
    if stdin:
        os.set_blocking(child.stdin.fileno(), False)
        selector.register(child.stdin, selectors.EVENT_WRITE, "stdin")
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                reason = "time_cap"
                break
            for item, _ in selector.select(min(remaining, .1)):
                if item.data == "stdin":
                    try:
                        written = os.write(item.fd, pending[:8192])
                        pending = pending[written:]
                    except BrokenPipeError:
                        pending = memoryview(b"")
                    if not pending:
                        selector.unregister(item.fileobj)
                        item.fileobj.close()
                    continue
                chunk = os.read(item.fd, 8192)
                if not chunk:
                    selector.unregister(item.fileobj)
                    continue
                cap = stdout_cap if item.data == "stdout" else CAPS["commandStderrBytes"]
                room = cap - len(streams[item.data])
                streams[item.data].extend(chunk[:room])
                if len(chunk) > room:
                    reason = item.data + "_byte_cap"
                    break
            if reason:
                break
        if reason or child.poll() is None and time.monotonic() >= deadline:
            reason = reason or "time_cap"
            child.kill()  # exact Popen child; never a service, container, GPU PID or process group
        try:
            receipt["exitCode"] = child.wait(timeout=max(.1, min(1, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            child.kill()
            reason = reason or "time_cap"
            try:
                receipt["exitCode"] = child.wait(timeout=1)
            except subprocess.TimeoutExpired:
                receipt["failure"] = "owned_observer_unreaped"
    finally:
        selector.close()
        for pipe in (child.stdin, child.stdout, child.stderr):
            if pipe is not None:
                pipe.close()
    out, err = bytes(streams["stdout"]), bytes(streams["stderr"])
    receipt.update(finishedUtc=utc(), stdoutBytes=len(out), stderrBytes=len(err),
                   stdoutSha256=sha(out), stderrSha256=sha(err),
                   capturedBytesComplete=reason is None,
                   outcome="READBACK" if type(receipt["exitCode"]) is int and receipt["exitCode"] == 0 and not reason else "FAILED")
    if reason:
        receipt["failure"] = reason
    return receipt, out, err


def command(name, deadline):
    # No request-derived commands, host, filesystem paths or options.
    argv, budget = COMMANDS[name]
    budget = min(budget, deadline - time.monotonic())
    if budget <= 0:
        return {"name": name, "outcome": "NOT_TESTED", "failure": "remote_time_cap", "exitCode": None}, None
    receipt, raw, err = run_bounded(argv, timeout=budget, stdout_cap=CAPS["commandStdoutBytes"])
    receipt["name"] = name
    receipt["stderrLog"] = safe_error(err)
    value = None
    if receipt["outcome"] == "READBACK":
        try:
            value = parse_command(name, raw)
            receipt["stdoutLog"] = raw.decode("utf-8")
            receipt["stdoutLogKind"] = "validated_nonsecret_original"
        except (ValueError, KeyError, TypeError, UnicodeError, IndexError):
            receipt.update(outcome="FAILED", failure="invalid_selected_output", stdoutLogKind="omitted_unvalidated_output")
    else:
        # A failed selected command can return a partial/unvalidated object.
        # Keep its original stream hash and stderr, never log unchecked fields.
        receipt["stdoutLogKind"] = "omitted_failed_unvalidated_output"
    return receipt, value


def identity(value, pattern):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise Refused("invalid_identity")
    return value


def parse_command(name, raw):
    text = raw.decode("utf-8")
    if name in ("gpu_inventory", "gpu_processes", "image_link"):
        rows = list(csv.reader(text.splitlines()))
        limit = CAPS["gpuProcessCount"] if name == "gpu_processes" else CAPS["gpuCount"]
        if len(rows) > limit:
            raise Refused("inventory_count_cap")
        result = []
        for row in rows:
            row = [v.strip() for v in row]
            wanted = 6 if name == "gpu_inventory" else 3 if name == "gpu_processes" else 5
            if len(row) != wanted:
                raise Refused("inventory_shape")
            identity(row[0], GPU_PATTERN)
            if name == "gpu_inventory":
                identity(row[1], r"[0-9A-Fa-f]{4,8}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}\.[0-7]")
                fields = ("uuid", "bdf", "totalMiB", "usedMiB", "freeMiB", "temperatureC")
                numbers = range(2, 6)
            elif name == "gpu_processes":
                fields = ("uuid", "pid", "usedMiB")
                numbers = range(1, 3)
            else:
                fields = ("uuid", "currentGen", "maxGen", "currentWidth", "maxWidth")
                numbers = range(1, 5)
            for i in numbers:
                if row[i] in ("[N/A]", "N/A", "[Not Supported]"):
                    row[i] = None
                elif row[i].isdigit():
                    row[i] = int(row[i])
                else:
                    raise Refused("inventory_number")
            result.append(dict(zip(fields, row)))
        if name == "gpu_inventory" and len({r["uuid"] for r in result}) != len(result):
            raise Refused("duplicate_gpu_identity")
        if name == "gpu_processes" and any(type(r["pid"]) is not int or r["pid"] <= 0 for r in result):
            raise Refused("invalid_gpu_pid")
        return result
    if name == "systemd_owner":
        result = {}
        for line in text.splitlines():
            key, value = line.split("=", 1)
            if key not in SYSTEMD_FIELDS or key in result or len(value) > 256:
                raise Refused("systemd_selected_fields")
            identity(value, r"[A-Za-z0-9_./:@\\\- ]*")
            result[key] = value
        if set(result) != set(SYSTEMD_FIELDS):
            raise Refused("systemd_missing_fields")
        return result
    if name == "image_ports":
        rows = text.splitlines()
        if len(rows) > 16:
            raise Refused("port_count_cap")
        for line in rows:
            fields = line.split()
            if len(fields) != 5 or fields[0] != "LISTEN" or fields[3].rsplit(":", 1)[-1] not in ("30006", "30007"):
                raise Refused("port_shape")
        return rows
    value = strict_json(raw)
    if not isinstance(value, dict):
        raise Refused("docker_shape")
    if name == "native_image":
        if set(value) != {"id", "repoDigests", "os", "architecture", "created"}:
            raise Refused("image_fields")
        identity(value["id"], r"sha256:[0-9a-f]{64}")
        identity(value["os"], r"[a-z0-9_-]{1,32}")
        identity(value["architecture"], r"[a-z0-9_-]{1,32}")
        if value["repoDigests"] is not None and not isinstance(value["repoDigests"], list):
            raise Refused("repo_digest_type")
        for digest in value["repoDigests"] or []:
            identity(digest, r"[A-Za-z0-9_./:@-]{1,256}")
        identity(value["created"], r"[0-9TZ:.+\-]{1,64}")
        return value
    expected = {"id", "name", "image", "configImage", "created", "pid", "status", "running", "oomKilled",
                "exitCode", "startedAt", "finishedAt", "owner", "invocation", "gpu", "memory", "memorySwap",
                "cpuset", "mems", "privileged", "readonly", "restart", "devices", "mounts"}
    if set(value) != expected or len(value["mounts"]) > CAPS["mountCount"] or len(value["devices"]) > 4:
        raise Refused("container_fields")
    for field, pattern in {"id": r"[0-9a-f]{64}", "name": r"/llm-image-backend", "image": r"sha256:[0-9a-f]{64}",
                           "configImage": r"sha256:[0-9a-f]{64}", "owner": r"[A-Z0-9-]{1,64}",
                           "invocation": r"[0-9a-f]{32}", "gpu": GPU_PATTERN,
                           "status": r"[a-z]{1,32}", "restart": r"[a-z-]{0,32}",
                           "cpuset": r"[0-9,-]{0,64}", "mems": r"[0-9,-]{0,64}"}.items():
        identity(value[field], pattern)
    for field in ("created", "startedAt", "finishedAt"):
        identity(value[field], r"[0-9TZ:.+\-]{1,64}")
    for field in ("pid", "exitCode", "memory", "memorySwap"):
        if type(value[field]) is not int or field != "exitCode" and value[field] < 0:
            raise Refused("container_integer")
    for field in ("running", "oomKilled", "privileged", "readonly"):
        if type(value[field]) is not bool:
            raise Refused("container_boolean")
    for mount in value["mounts"]:
        if set(mount) != {"type", "source", "destination", "rw"} or type(mount["rw"]) is not bool:
            raise Refused("mount_fields")
        identity(mount["type"], r"[a-z]{1,16}")
        for field in ("source", "destination"):
            identity(mount[field], r"/[A-Za-z0-9_./-]{0,255}")
    for device in value["devices"]:
        if set(device) != {"driver", "count", "ids", "capabilities"} or type(device["count"]) is not int:
            raise Refused("device_fields")
        identity(device["driver"], r"[a-z]{0,16}")
        if device["ids"] is not None and not isinstance(device["ids"], list) or not isinstance(device["capabilities"], list):
            raise Refused("device_array_type")
        for selected in device["ids"] or []:
            identity(selected, GPU_PATTERN)
        for group in device["capabilities"] or []:
            if not isinstance(group, list):
                raise Refused("capability_group_type")
            for capability in group:
                identity(capability, r"[a-z]{1,16}")
    return value


class Files:
    """Fixed read-only roots; no data-derived source/path selection."""
    def __init__(self, deadline):
        self.deadline, self.count, self.bytes = deadline, 0, 0
        self.receipts = []

    def read(self, path, *, protected=True, cap=None):
        started = utc()
        receipt = {"path": path, "host": HOST, "startedUtc": started, "outcome": "UNKNOWN"}
        self.receipts.append(receipt)
        fd = directory = None
        try:
            if path not in READ_PATHS or not protected and path not in ("/proc/meminfo", "/proc/sys/kernel/random/boot_id"):
                raise Refused("file_not_allowlisted")
            if time.monotonic() >= self.deadline or self.count >= CAPS["fileCount"]:
                raise Refused("file_time_or_count_cap")
            self.count += 1
            target = Path(path)
            directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
            for part in target.parts[1:-1]:
                next_directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = next_directory
                info = os.fstat(directory)
                if protected and (info.st_uid != 0 or info.st_mode & 0o022):
                    raise Refused("protected_ancestry_refused")
            fd = os.open(target.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            info = os.fstat(fd)
            receipt["metadata"] = {"uid": info.st_uid, "gid": info.st_gid, "mode": oct(stat.S_IMODE(info.st_mode)),
                                   "device": info.st_dev, "inode": info.st_ino, "nlink": info.st_nlink,
                                   "size": info.st_size, "mtimeNs": info.st_mtime_ns}
            if not stat.S_ISREG(info.st_mode) or protected and (info.st_uid != 0 or info.st_mode & 0o022 or info.st_nlink != 1):
                raise Refused("protected_regular_file_refused")
            limit = cap or CAPS["fileBytes"]
            if info.st_size > limit:
                raise Refused("file_byte_cap")
            raw = bytearray()
            while True:
                if time.monotonic() >= self.deadline:
                    raise Refused("file_time_cap")
                chunk = os.read(fd, min(8192, limit + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                self.bytes += len(chunk)
                if len(raw) > limit or self.bytes > CAPS["totalFileBytes"]:
                    raise Refused("file_byte_cap")
            after = os.fstat(fd)
            signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_uid, s.st_gid, s.st_mode, s.st_nlink)
            if signature(info) != signature(after):
                raise Refused("file_changed_during_read")
            if signature(os.stat(target.name, dir_fd=directory, follow_symlinks=False)) != signature(info):
                raise Refused("file_path_changed")
            receipt.update(outcome="READBACK", sha256=sha(raw), bytesRead=len(raw))
            return bytes(raw), receipt
        except (OSError, Refused) as exc:
            receipt.update(outcome="FAILED", failure=exc.args[0] if isinstance(exc, Refused) else "file_read_refused",
                           errno=getattr(exc, "errno", None))
            return None, receipt
        finally:
            if fd is not None:
                os.close(fd)
            if directory is not None:
                os.close(directory)
            receipt["finishedUtc"] = utc()


def project_record(kind, value):
    """Explicit nonsecret fields only. Recovery tokens/env/history are excluded."""
    if not isinstance(value, dict):
        raise Refused("record_not_object")
    fields = {
        "config": ("schema_version", "owner", "gpu_uuid", "image_id", "source_commit", "checkpoint_revision", "checkpoint_receipt_sha256", "network_id"),
        "state": ("schema_version", "owner", "phase", "boot", "boot_id", "run_id", "updated_utc", "completed_utc", "failure_code"),
        "operation": ("schema_version", "owner", "boot", "action", "status", "phase", "pid", "invocation_id", "config_sha256"),
        "recovery": ("schema_version", "owner", "boot", "status", "phase", "pid", "config_sha256", "prior_invocation", "child_start"),
        "checkpoint": ("status", "revision", "file_count", "total_bytes"),
        "overlay": ("schema_version", "status", "runtime_revision", "image_id", "image_config_digest", "overlay_sha256", "verifier_sha256"),
        "api_config": ("schema_version", "runtime_revision", "runtime_image_digest", "model_id", "model_revision"),
    }[kind]
    result = {}
    for field in fields:
        if field not in value:
            continue
        v = value[field]
        if v is not None and type(v) not in (str, int, bool):
            raise Refused("selected_field_type")
        if isinstance(v, str):
            identity(v, r"[A-Za-z0-9_/.:+\-]{0,128}" if kind == "api_config" and field == "model_id" else r"[A-Za-z0-9_:.+\-]{0,128}")
        result[field] = v
    if kind == "config":
        result["checkpointPathMatchesFixed"] = value.get("checkpoint_path") == MODEL
        for field, expected in (("source_sha256", RUNTIME_FILES), ("release_source_sha256", RELEASE_FILES)):
            mapping = value.get(field)
            result[field + "_keys_exact"] = isinstance(mapping, dict) and set(mapping) == set(expected)
            result[field] = {}
            if isinstance(mapping, dict):
                for key in expected:
                    if key in mapping:
                        result[field][key] = identity(mapping[key], r"[0-9a-f]{64}")
    if kind == "state":
        container = value.get("container")
        if container is None:
            result["container"] = None
        elif isinstance(container, dict):
            result["container"] = {"id": identity(container.get("id"), r"[0-9a-f]{64}")}
        else:
            raise Refused("state_container_invalid")
    if kind == "api_config":
        result["profiles"] = []
        profiles = value.get("profiles")
        if profiles is not None:
            if not isinstance(profiles, list) or len(profiles) > 16:
                raise Refused("profile_count_cap")
            for profile in profiles:
                row = {key: profile[key] for key in ("operation", "size", "references", "transparent", "evidence_sha256") if key in profile}
                for key, v in row.items():
                    if type(v) not in (str, int, bool):
                        raise Refused("profile_value_type")
                    if isinstance(v, str):
                        identity(v, r"[A-Za-z0-9_:.\-]{1,128}")
                result["profiles"].append(row)
    return result


def read_record(files, kind, path):
    raw, receipt = files.read(path, cap=CAPS["jsonBytes"])
    if raw is None:
        return {"receipt": receipt, "fields": None}
    try:
        fields = project_record(kind, strict_json(raw))
    except (ValueError, TypeError, KeyError) as exc:
        receipt.update(outcome="FAILED", failure="selected_record_invalid",
                       selectionFailure=exc.args[0] if isinstance(exc, Refused) else "invalid_record_encoding_or_shape")
        fields = None
    return {"receipt": receipt, "fields": fields}


def proc_stamp(pid, boot, deadline):
    # Only validated observed PID data selects a bounded /proc identity; no argv/environ.
    if type(pid) is not int or not 0 < pid < 2**31:
        return {"pid": pid, "outcome": "UNKNOWN", "failure": "pid_unavailable"}
    try:
        values = {}
        hashes = {}
        for name in ("stat", "status", "cgroup"):
            if time.monotonic() >= deadline:
                return {"pid": pid, "outcome": "NOT_TESTED", "failure": "remote_time_cap"}
            with open("/proc/" + str(pid) + "/" + name, "rb") as stream:
                raw = stream.read(8193)
            if len(raw) > 8192:
                raise Refused("proc_byte_cap")
            values[name] = raw.decode("ascii")
            hashes[name] = sha(raw)
        tail = values["stat"].rsplit(")", 1)[1].split()
        uid_line = next(line for line in values["status"].splitlines() if line.startswith("Uid:"))
        return {"pid": pid, "outcome": "READBACK", "bootId": boot, "startTicks": int(tail[19]),
                "state": tail[0], "uids": [int(x) for x in uid_line.split()[1:]],
                "cgroup": [identity(line, r"[A-Za-z0-9_./:@\\\-]{1,512}") for line in values["cgroup"].splitlines()],
                "capturedUtc": utc(), "ownership": "UNPROVEN", "argvRead": False, "selectedProcRawSha256": hashes}
    except (OSError, ValueError, StopIteration, IndexError):
        return {"pid": pid, "outcome": "FAILED", "failure": "proc_identity_unavailable", "capturedUtc": utc()}


def source_graph(files):
    paths = [(BASE + "/source/" + p, "source_sha256", p) for p in RUNTIME_FILES]
    paths += [(RELEASE + "/" + p, "release_source_sha256", p) for p in RELEASE_FILES]
    paths += [(API_ROOT + "/" + p, "external_review_required", p) for p in API_FILES]
    paths += [(HELPER, "external_review_required", HELPER),
              ("/etc/systemd/system/" + UNIT, "external_review_required", UNIT),
              ("/etc/systemd/system/llm-image-api.service", "external_review_required", "llm-image-api.service"),
              ("/opt/llmctl/adaptive-idle/verify.py", "external_review_required", "overlay_verifier")]
    rows = []
    for path, scope, key in paths:
        _, receipt = files.read(path)
        rows.append({"path": path, "scope": scope, "key": key, "receipt": receipt})
    return rows


def remote_observe():
    start = utc()
    deadline = time.monotonic() + CAPS["remoteSeconds"]
    files = Files(deadline)
    boot_raw, boot_receipt = files.read("/proc/sys/kernel/random/boot_id", protected=False, cap=128)
    boot = None
    if boot_raw is not None:
        try:
            boot = identity(boot_raw.decode().strip(), r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
        except ValueError:
            boot_receipt.update(outcome="FAILED", failure="invalid_boot_identity")
    receipts, values = [], {}
    for name in COMMANDS:
        receipt, value = command(name, deadline)
        receipts.append(receipt)
        values[name] = value
    records = {key: read_record(files, key, BASE + "/" + key + ".json") for key in ("config", "state", "operation", "recovery")}
    records["checkpoint"] = read_record(files, "checkpoint", MODEL + "/CHECKPOINT-RECEIPT.json")
    records["overlay"] = read_record(files, "overlay", "/opt/llmctl/adaptive-idle/image.json")
    records["api_config"] = read_record(files, "api_config", "/etc/llm-server/image-api.json")
    graph = source_graph(files)
    # Mount sources are metadata-only and restricted to the four exact expected roots.
    mount_metadata = []
    for path in (MODEL, BASE + "/source", BASE + "/work"):
        if time.monotonic() >= deadline:
            mount_metadata.append({"path": path, "outcome": "NOT_TESTED", "failure": "remote_time_cap"})
            continue
        try:
            info = os.lstat(path)
            mount_metadata.append({"path": path, "outcome": "READBACK", "realpathMatches": os.path.realpath(path) == path,
                                   "uid": info.st_uid, "mode": oct(stat.S_IMODE(info.st_mode)), "device": info.st_dev,
                                   "inode": info.st_ino, "isDirectory": stat.S_ISDIR(info.st_mode)})
        except OSError as exc:
            mount_metadata.append({"path": path, "outcome": "FAILED", "errno": exc.errno})
    memory = {}
    mem_raw, mem_receipt = files.read("/proc/meminfo", protected=False, cap=8192)
    if mem_raw:
        for line in mem_raw.decode().splitlines():
            key, value = line.split(":", 1)
            if key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
                memory[key + "Bytes"] = int(value.strip().split()[0]) * 1024
    pids = set()
    for field in ("MainPID", "ControlPID", "ExecMainPID"):
        v = (values.get("systemd_owner") or {}).get(field, "")
        if v.isdigit() and int(v):
            pids.add(int(v))
    container = values.get("native_container") or {}
    if type(container.get("pid")) is int and container["pid"] > 0:
        pids.add(container["pid"])
    for row in values.get("gpu_processes") or []:
        if row["uuid"] == GPU and type(row["pid"]) is int and row["pid"] > 0:
            pids.add(row["pid"])
    proc_capped = len(pids) > CAPS["processCount"]
    processes = [proc_stamp(pid, boot, deadline) for pid in sorted(pids)[:CAPS["processCount"]]]
    boot_after_raw, boot_after_receipt = files.read("/proc/sys/kernel/random/boot_id", protected=False, cap=128)
    stable = boot is not None and boot_after_raw is not None and boot_after_raw.decode().strip() == boot
    result = {"schema": SCHEMA, "origin": "LIVE_PASSIVE_READBACK", "host": HOST, "startedUtc": start,
              "finishedUtc": utc(), "caps": CAPS, "bootId": boot, "bootStable": stable,
              "bootReceipts": [boot_receipt, boot_after_receipt], "commands": receipts, "selected": values,
              "records": records, "sourceGraph": graph, "mountMetadata": mount_metadata,
              "hostMemory": memory, "hostMemoryReceipt": mem_receipt, "processes": processes,
              "processInventoryCapped": proc_capped, "fileCount": files.count, "fileBytesRead": files.bytes,
              "httpReadiness": {"result": "NOT_TESTED", "reason": "API /health/ready mutates Owner state; installed endpoint purity/authenticity not established"},
              "usb4": {"result": "NOT_TESTED", "reason": "guest PCIe readback is not cable identity or sustained USB4 load qualification"},
              "workflowAcceptance": {"generation": "NOT_TESTED", "followup_edit": "NOT_TESTED", "child": "NOT_TESTED"}}
    result["layers"] = assess(result)
    result["observationResult"] = "READBACK" if (stable and not proc_capped
        and all(r.get("outcome") == "READBACK" for r in receipts + files.receipts)
        and all(r.get("outcome") == "READBACK" for r in processes + mount_metadata)) else "PARTIAL"
    return result


def assess(observation):
    """Conservative layered conclusions; this function cannot produce workflow PASS."""
    values = observation.get("selected", {})
    config = (observation.get("records", {}).get("config") or {}).get("fields") or {}
    checkpoints = (observation.get("records", {}).get("checkpoint") or {}).get("fields") or {}
    gpus = values.get("gpu_inventory")
    image = values.get("native_image")
    container = values.get("native_container")
    state = (observation.get("records", {}).get("state") or {}).get("fields") or {}
    api = (observation.get("records", {}).get("api_config") or {}).get("fields") or {}
    graph = observation.get("sourceGraph", [])
    source_ok = bool(graph) and all(row["receipt"].get("outcome") == "READBACK" for row in graph)
    closure_rows = [row for row in graph if row["scope"] != "external_review_required"]
    closure_ok = source_ok and len(closure_rows) == len(RUNTIME_FILES) + len(RELEASE_FILES)
    for row in closure_rows:
        closure_ok = closure_ok and config.get(row["scope"], {}).get(row["key"]) == row["receipt"].get("sha256")
    closure_ok = closure_ok and config.get("source_sha256_keys_exact") is True and config.get("release_source_sha256_keys_exact") is True
    model_ok = (checkpoints.get("status") == "COMPLETE_VERIFIED" and checkpoints.get("revision") == REV
                and checkpoints.get("file_count") == 26 and checkpoints.get("total_bytes") == 33131614782
                and config.get("checkpointPathMatchesFixed") is True
                and config.get("checkpoint_receipt_sha256") == ((observation.get("records", {}).get("checkpoint") or {}).get("receipt") or {}).get("sha256"))
    platform_ok = bool(image) and image.get("id") == CONFIG and (config.get("image_id") == PLATFORM)
    owner_matches = (bool(container) and container.get("owner") == OWNER and container.get("gpu") == GPU
                     and container.get("configImage") == PLATFORM and container.get("image") == CONFIG
                     and container.get("id") == (state.get("container") or {}).get("id")
                     and config.get("owner") == state.get("owner") == OWNER and config.get("gpu_uuid") == GPU
                     and container.get("invocation") == state.get("run_id") and observation.get("bootStable") is True)
    return {
        "intendedPlacement": {"result": "DECLARED", "imageGpu": GPU, "excludedVisionGpu": VISION_GPU,
                              "bothPresent": None if gpus is None else {GPU, VISION_GPU}.issubset({r["uuid"] for r in gpus}),
                              "configuredGpu": config.get("gpu_uuid"), "matchesIntended": config.get("gpu_uuid") == GPU},
        "installedSource": {"result": "READBACK" if source_ok else "UNKNOWN", "protectedClosureHashesMatch": bool(closure_ok),
                            "externalDeliveryManifestReviewed": False},
        "platformIdentity": {"result": "READBACK" if image else "UNKNOWN", "platformConfigBindingMatches": platform_ok,
                             "platformManifest": PLATFORM, "configDigest": CONFIG, "parentOnlyInsufficient": PARENT},
        "apiConfiguration": {"result": "READBACK" if api else "UNKNOWN", "recordedRuntimeImageDigest": api.get("runtime_image_digest"),
                             "matchesRequiredPlatformManifest": api.get("runtime_image_digest") == PLATFORM if api else None,
                             "parentOnlyBinding": api.get("runtime_image_digest") == PARENT if api else None,
                             "staticProfilesAreLiveReadiness": False},
        "modelArtifact": {"result": "READBACK" if checkpoints else "UNKNOWN", "retainedReceiptMatches": model_ok,
                          "weightsRehashed": False, "loaded": "UNKNOWN"},
        "processRuntime": {"result": "READBACK" if values.get("systemd_owner") else "UNKNOWN",
                           "selectedOwnerIdentityMatches": owner_matches, "authenticOwnershipProven": False,
                           "modelReadiness": "NOT_TESTED", "admissionReadiness": "NOT_TESTED"},
        "liveWorkflowAcceptance": {"result": "NOT_TESTED", "generation": "NOT_TESTED", "followup_edit": "NOT_TESTED", "child": "NOT_TESTED"},
    }


def proposal():
    """Reviewable exact seams, no GO, fake credentials, IDs or executable workload."""
    return {
        "schema": "h043-image-disabled-workflow-proposal-v1", "enabled": False, "execution": "DISABLED",
        "rootGo": None, "aRuntimeGate": "PENDING_EXTERNAL_EVIDENCE_DO_NOT_WAIT", "workflowResult": "NOT_TESTED",
        "identity": {"host": HOST, "unit": UNIT, "containerName": NAME, "owner": OWNER, "imageGpu": GPU,
                     "excludedVisionGpu": VISION_GPU, "modelRevision": REV, "runtimeRevision": UPSTREAM,
                     "platformManifest": PLATFORM, "configDigest": CONFIG, "parentImage": PARENT,
                     "configPath": BASE + "/config.json", "statePath": BASE + "/state.json",
                     "checkpointReceipt": MODEL + "/CHECKPOINT-RECEIPT.json", "bootId": None,
                     "containerId": None, "invocationId": None, "processBirth": None,
                     "note": "None means required current observation/review, never an invented schema/credential/owner."},
        "reviewGraph": {"runtimeRoot": BASE + "/source", "runtimeFiles": list(RUNTIME_FILES),
                        "releaseRoot": RELEASE, "releaseFiles": list(RELEASE_FILES), "apiRoot": API_ROOT,
                        "apiFiles": list(API_FILES), "fixedRecoveryHelper": HELPER,
                        "required": "Exact observed raw SHA256s plus root external delivery manifest for API/units/helper/native-overlay/image receipts; compare before any GO"},
        "admission": [
            "A first native no-generation startup/owned shutdown qualifies independently; preserve Codex 0.158.0/064c and 480000/400000/65536.",
            "Fresh exact finite root GO binds reviewed source/helper/config hashes, ai-vm boot, GPU5d, image manifest/config, protected state hash, service invocation, PID birth/cgroup, container ID, operation, route and deadline.",
            "Existing registered-storage, canonical lifecycle lease/freeze, hardware freshness/latch, source closure and authenticated gateway/session scope must validate; unknown owners remain untouched.",
            "No protected specialist/global qualification write in this task; root's existing scoped image ticket must authorize the finite native main/child tools without faking retained-live evidence.",
            "owned-acceptance.ts tickets expire within30minutes and bind one actual run; each dependent fresh run needs separately reviewed current scope. MCP3300s timeout is a ceiling, never ticket/deadline extension. Preserve same app chat for edit while recording actual new native run identity.",
            "image_capabilities({query:capabilities}) must truthfully advertise ready/admitting and exact generation/edit profiles; generation profiles never authorize edit sizes.",
            "Current GPU5d absence/ownership must be proven; keep GPU14 vision, both Blackwell Qwens and unrelated services/owners intact. No weight hash/download or alternative image engine.",
        ],
        "finiteScope": {"generationPosts": 1, "editPosts": 1, "childArtifactHandoffs": 1, "automaticResubmissions": 0,
                        "activeImages": 1, "outputsPerInvocation": 1, "referencesMaximum": 2,
                        "nativeBackendRequestSeconds": 900, "mcpToolSeconds": 3300,
                        "adapterPollBudgetSeconds": 3000, "deadline": None,
                        "note": "Root chooses a finite window sufficient for actual queues/drains. Missing time produces unfinished receipts; this source phase never waits for models."},
        "stages": [
            {"id": "S0-current-identity", "dispatch": "NONE", "requirements": "Use this passive readback, then root verifies lease/admission, A gate, raw source graph/hash manifest, boot/config/state/owner tuple and current authenticated native tool roster."},
            {"id": "S1-fullhd-generation", "interface": "native image_generate via ai-harness/tools/image/image-mcp.mjs -> image.mjs -> ImageBroker.submit -> ImageUpstream -> image_api -> owned native backend",
             "arguments": {"prompt": "Create one opaque illustration of a red cube beside a blue sphere on a neutral background.", "size": "1920x1080", "seed": 43001},
             "requirements": "Exactly one ordinary same-chat tool POST; record authentic app session/currentRun, native session/run, requestId/jobId/revision/operation/config/boot/container, seed and decoded PNG SHA256. Native1920x1088, crop bottom8 only, public1920x1080; original native/raw artifact+dimensions+hash preservation requires the separately reviewed missing capture seam before this stage can qualify. Profile geometry is not a raw-output receipt. 40steps/CFG1 eager BF16/FP32 torch_sdpa; no offload/quant/cache.",
             "terminal": "Image job completed + Store.deliverImageResult durable delivery + owned backend drain, not native turn completion alone."},
            {"id": "S2-same-chat-fresh-seed-edit", "interface": "image_edit -> ImageBroker.binding/sourceSeeds -> imageFiles.snapshot/frozen -> guarded saved image job",
             "arguments": {"prompt": "Change the cube to green; keep the sphere blue and preserve the composition.", "size": "1536x864", "seed": 43002, "references": [{"fileId": None}]},
             "requirements": "Use actual S1 current-session-owned artifact fileId; reject absent IDs. Verify43002 differs from every known source/ancestor seed. Require advertised1536x864 edit/one-reference profile; choose1024x1024 only in a separately reviewed successor if1536 unavailable, never retry/substitute generation. FullHD-to1536x864 is an actual canvas change: retain raw original/snapshot hashes and exact target padding/crop plan in saved awaiting_approval job.",
             "approval": "Only actual authenticated user click/card issues approvalToken and approves same job + approvalHash. Native tool cannot issue token, approve, resize locally or forge flags. Return immediately awaiting approval; later fresh native session may do one image_status({jobId:actualSavedId}) lookup. No paid wait/loop.",
             "terminal": "Same saved job completed with fresh artifact/version, source/reference hashes/dimensions and real durable result receipt. No PASS while pending approval/draining/uncertain."},
            {"id": "S3-native-child-owned-handoff", "interface": "CodexChildren depth-one ownership + codex-engine child notification routing + Store.deliverImageResult + imageFiles",
             "arguments": None,
             "requirements": "Fresh native worker child via retained delegation tool, actual child native/app session/run/parent correlation and owned scoped image/artifact capability. Hand off authentic S2 artifact/result with accessible source-owned fileId or anchored relative workspacePath, SHA256/dimensions and parent job/revision/result links; prove child ownership/access and parent delivery. Never copy ID across sessions or infer access from path. No additional generation in this finite scope.",
             "blocker": "Protected child image workflow evidence requires a real image tool workflow, not a text/file-only child receipt. If existing child cannot inherit guarded artifact capability/ownership or root requires child generation, stop and propose a separately reviewed exact extra operation; do not silently fabricate qualification.",
             "terminal": "Actual native child session/run/tool/result/owned artifact and parent notification+settlement receipts, not synthetic MCP fixture or child text success."},
            {"id": "S4-drain-and-review", "dispatch": "NONE unless separate exact reviewed rollback scope",
             "requirements": "Retain request/job/native session/run IDs and transcriptSHA256/settlementSHA256; backend completion and native drain are separate from assistant turn end. Original command receipts use sanitized argv/cwd/host/UTC/int exit/raw stream hashes. Root may review retained-live generation/followup_edit/child evidence against codex-specialist-qualification.ts; no fixture or idle metadata PASS."},
        ],
        "resources": {"beforeDuringAfter": "Sample exact GPU5d UUID/BDF/temp/process birth/VRAM and guest hostMemAvailable/no swap, baseline/current PCIe generation+width before/during/after and peak minima with timestamp/sample gaps. Read host USB4/cable identity/currentlink only under separately exact passive host scope; user-reported40Gbps0.5m is not load evidence.",
                      "gpuFreeMinimumPercent": 5, "hostAvailableMinimumPercent": 15, "cpuSet": "8-15",
                      "memoryBytes": 96 * 1024**3, "memorySwapBytes": 96 * 1024**3,
                      "thermal": "Preserve current integrated GPU and CHA_FAN3 policies/owners; no BMC/fan changes. Root-reviewed thermal guard/current fresh telemetry required; source cannot authorize load after stale/fault telemetry.",
                      "usb4Result": "NOT_TESTED", "samplePeakResult": "NOT_TESTED"},
        "rollback": {"enabled": False, "requirements": "Stop admission and retain uncertain jobs first. Explicit authorized stop/cancel drains active image work; never claim instant GPU cancellation. Only separately reviewed exact authentic image operation/container/service/PID birth/cgroup/config+boot may settle through retained owned helper. Inspect source graph and current protected operation/recovery state first; no generic sudo/reset/kill, no name-only adoption, no latch clear. Unknown owners and normal runtimes survive. A denied/missing helper is failure, not permission to weaken guards.",
                     "helperReferenceOnly": HELPER, "completion": "Actual owned command int exit, operation/native completion receipt, exact absence/residency proof and protected state/config unchanged-or-authentic successor hashes; preserve initial failures."},
        "missingEvidence": ["A live gate", "current protected installed source/config/owner/VMboot review", "live model/admission readiness",
                            "authenticated canvas-change card approval", "real ordinary generation/edit/child result settlement",
                            "USB4 sustained-load/current hostlink and sampled resource/thermal peak", "finite exact root GO"],
        "genuineMissingImplementation": [
            {"source": "scripts/image_api/protocol.py:public_output", "gap": "Crops native1920x1088 and returns only public1920x1080 PNG. Ordinary ImageFiles.save hashes only public artifact; no raw pre-crop hash/artifact retention seam. Future separately owned capture implementation required before raw provenance can PASS."},
            {"source": "ai-harness/server/src/codex-engine.ts + codex-children.ts", "gap": "Child notifications return before parent completedImageStatus processing. Terminal-item validation does not emit structured child image result consumption/handoff proof; actual original child MCP/final and authorized artifact/result receipts needed, with a separately owned implementation if retained interfaces cannot provide them."},
            {"source": "scripts/image_runtime/native_request.py", "gap": "Fixed native1024x1024 seed42 baseline is not an ordinary FullHD/edit/child workflow runner. No request to run it or bypass guarded broker."},
        ],
    }


def observe():
    # The exact reviewed source goes on stdin, never into shared storage or argv.
    raw = Path(__file__).read_bytes()
    if len(raw) > 131072:
        raise Refused("probe_source_byte_cap")
    receipt, out, err = run_bounded(SSH, timeout=CAPS["transportSeconds"], stdout_cap=CAPS["transportStdoutBytes"],
                                    stdin=raw, host="mac-worker1", cwd=str(Path.cwd()))
    receipt["stderrLog"] = safe_error(err)
    observation = None
    if receipt["outcome"] == "READBACK":
        try:
            # Remote report uses larger fixed cap than each selected protected JSON.
            observation = strict_json(out, maximum=CAPS["transportStdoutBytes"], depth_cap=12, string_cap=CAPS["commandStdoutBytes"])
            if observation.get("schema") != SCHEMA or observation.get("host") != HOST or observation.get("origin") != "LIVE_PASSIVE_READBACK":
                raise Refused("remote_identity_invalid")
            if observation.get("workflowAcceptance") != {"generation": "NOT_TESTED", "followup_edit": "NOT_TESTED", "child": "NOT_TESTED"}:
                raise Refused("workflow_acceptance_invalid")
            commands = observation.get("commands")
            if not isinstance(commands, list) or len(commands) != len(COMMANDS) or {r.get("name") for r in commands} != set(COMMANDS):
                raise Refused("remote_command_inventory_invalid")
            for row in commands:
                if row.get("argv") is not None and row["argv"] != list(COMMANDS[row["name"]][0]):
                    raise Refused("remote_command_identity_invalid")
                if row.get("exitCode") is not None and type(row["exitCode"]) is not int:
                    raise Refused("remote_exit_invalid")
            if observation.get("layers") != assess(observation):
                raise Refused("remote_layer_claim_invalid")
        except (ValueError, AttributeError, TypeError, KeyError, RecursionError, UnicodeError):
            receipt.update(outcome="FAILED", failure="remote_report_invalid")
            observation = None
    return {"schema": "h043-image-observation-envelope-v1", "transportReceipt": receipt,
            "observation": observation, "workflowAcceptance": "NOT_TESTED"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--observe", action="store_true", help="bounded passive ai-vm observations only")
    group.add_argument("--proposal", action="store_true", help="print disabled exact workflow proposal; no execution")
    group.add_argument("--remote-observe", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.proposal:
        result = proposal()
    elif args.remote_observe:
        result = remote_observe()
    else:
        result = observe()
    print(json.dumps(result, sort_keys=True, indent=2))
    # Command failures remain explicit in report; transport/remote failures fail CLI.
    if args.observe:
        return 0 if result["transportReceipt"]["outcome"] == "READBACK" and result["observation"].get("observationResult") == "READBACK" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
