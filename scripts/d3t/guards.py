"""Concrete D3T telemetry: cheap 1 Hz reads and full memory checkpoints.

Adapted from reports/d3-evidence/operator-code/snapshot-d3.py.txt. No observer,
lease or external evidence adapters. The later live CLI owns its request and
passes exact reviewed container/image IDs. No key is read by this module.
"""
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import select
import stat
import subprocess
import sys
import time
from agent.protocol import AgentError

GIB = 1024 ** 3
NATIVE_CONTEXT = 1048576
BASELINE_IMAGE = "sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62"
MOUNTS = {"/data": "8daf56f1-5649-4163-9d87-919c2d271875",
          "/data/models-large": "a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a"}
ERROR_PATTERNS = {
    "cuda": r"CUDA error|unsupported.*(?:kernel|arch)|NVRM: Xid",
    "oom": r"out of memory|\bOOM\b|Killed process",
    "storage": r"SIGBUS|I/O error|EXT4-fs error|Buffer I/O|blk_update_request.*error",
    "runtime": r"GGML_ASSERT|illegal instruction|error:|failed to (?:allocate|reserve)",
    "fusion_fallback": r"(?:Flash Attention|Lightning Indexer).*not supported|(?:flash_attn|fused_lid).*disabled",
}


class Error(AgentError):
    """Safe fixed diagnostic; never contains raw command/log output."""


def parse_log_line(line, state):
    """Consume one Docker log message; retain numeric diagnostics only."""
    state["log_lines"] += 1
    for name, pattern in ERROR_PATTERNS.items():
        state["errors"][name] += len(re.findall(pattern, line, re.I))
    slot = re.search(r"initializing, n_slots = (\d+), n_ctx_slot = (\d+)", line)
    if slot:
        state["slot_count"], state["slot_context"] = map(int, slot.groups())
    threads = re.search(r"threadpool init, n_threads = (\d+)", line)
    if threads:
        state["n_threads"] = int(threads.group(1))
    marker = line.find("D3T_NATIVE_V1")
    if marker < 0:
        return
    record = line[marker:].rstrip("\r\n")
    names = ("n_ctx", "n_ctx_seq", "n_seq_max", "n_batch", "n_ubatch", "flash_attn",
             "fused_lid", "lid_nodes", "fa_nodes", "no_alloc")
    graph = re.fullmatch("D3T_NATIVE_V1 kind=graph " + " ".join(name + r"=(\d+)" for name in names), record)
    if graph:
        if state.get("native_group_open"):
            raise Error("incomplete_native_group")
        candidate = dict(zip(names, map(int, graph.groups())))
        candidate.update({"graph_log_line": state["log_lines"], "compute_bytes": {},
                          "cache_bytes": {}, "compute_log_lines": {}, "cache_log_lines": {}})
        state.update(native=None, native_pending=candidate, native_group_open=True, native_phase="compute")
        if candidate["fused_lid"] != 1 or candidate["flash_attn"] != 1 or candidate["no_alloc"] != 0:
            state["errors"]["fusion_fallback"] += 1
        return
    if record == "D3T_NATIVE_V1 kind=end":
        if not state.get("native_group_open"):
            raise Error("unexpected_native_end")
        state["native_pending"]["end_log_line"] = state["log_lines"]
        state["native"] = state["native_pending"]
        state["native_group_open"] = False
        return
    buffer = re.fullmatch(r"D3T_NATIVE_V1 kind=(compute|cache) backend=(.+) bytes=(\d+)", record)
    if not buffer or not state.get("native_group_open"):
        raise Error("malformed_or_unordered_native_diagnostic")
    kind, backend, byte_count = buffer.groups()
    if len(backend) > 256 or kind == "compute" and state["native_phase"] == "cache":
        raise Error("native_buffer_order_or_name_invalid")
    state["native_phase"] = kind
    if backend in ("CUDA0", "CUDA1"):
        candidate = state["native_pending"]
        if backend in candidate[kind + "_bytes"]:
            raise Error("duplicate_native_required_backend")
        candidate[kind + "_bytes"][backend] = int(byte_count)
        candidate[kind + "_log_lines"][backend] = state["log_lines"]


def validate_snapshot(sample):
    """Enforce measured resource/state gates; missing native records refuse."""
    try:
        if sample.get("status") == "STOP":
            raise Error("telemetry_collection_failed")
        if sample["schema_version"] != 2 or sample["sample_kind"] not in ("cheap", "full"):
            raise Error("unknown_telemetry_schema")
        full = sample["sample_kind"] == "full"
        duration = sample["sample_elapsed_seconds"]
        if type(duration) not in (int, float) or not 0 <= duration <= (30 if full else 2):
            raise Error("snapshot_collection_too_slow_or_invalid")
        container = sample["container"]
        if (container["running"] is not True or any(container[key] is not False for key in
                ("oom_killed", "paused", "restarting", "dead"))
                or type(container["restart_count"]) is not int or container["restart_count"] < 0):
            raise Error("container_not_safe_running")
        if (type(sample["process_start_ticks"]) is not int or sample["process_start_ticks"] <= 0
                or sample["process_state"] not in ("R", "S", "D", "I")):
            raise Error("process_identity_or_state_invalid")
        if type(sample["root_available_bytes"]) is not int or sample["root_available_bytes"] < 4 * GIB:
            raise Error("root_below_4gib")
        if sample["mounts"] != MOUNTS:
            raise Error("mount_uuid_mismatch")
        if (len(sample["gpus"]) != 2 or {g["index"] for g in sample["gpus"]} != {0, 1}
                or len({g["uuid"] for g in sample["gpus"]}) != 2):
            raise Error("requires_two_exact_gpus")
        for gpu in sample["gpus"]:
            if (type(gpu["index"]) is not int or not isinstance(gpu["uuid"], str) or not gpu["uuid"]
                    or type(gpu["free_bytes"]) is not int or type(gpu["total_bytes"]) is not int
                    or gpu["free_bytes"] < 16 * GIB or gpu["free_bytes"] > gpu["total_bytes"]):
                raise Error("gpu_below_16gib_or_invalid")
        host, process = sample["host_kib"], sample["process_kib"]
        names = {"VmRSS", "VmSwap"} | ({"Rss", "Pss", "Swap"} if full else set())
        if set(process) != names or any(type(process[key]) is not int or process[key] < 0 for key in names):
            raise Error("missing_or_invalid_memory_measurement")
        if (any(type(host[key]) is not int or host[key] < 0 for key in
                ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"))
                or host["MemAvailable"] > host["MemTotal"] or host["SwapFree"] > host["SwapTotal"]
                or process["VmRSS"] <= 0):
            raise Error("missing_or_invalid_memory_measurement")
        if host["MemAvailable"] < 64 * GIB // 1024:
            raise Error("host_below_64gib_available")
        if full and not 0 < process["Pss"] <= process["Rss"]:
            raise Error("missing_or_invalid_memory_measurement")
        if process["VmSwap"] != 0 or full and process["Swap"] != 0:
            raise Error("target_process_swap_in_use")
        if type(sample["cgroup_swap_current_bytes"]) is not int or sample["cgroup_swap_current_bytes"] < 0:
            raise Error("missing_or_invalid_cgroup_swap")
        if sample["cgroup_swap_current_bytes"] != 0:
            raise Error("owned_cgroup_swap_in_use")
        if (type(sample["host_swap_used_kib"]) is not int
                or sample["host_swap_used_kib"] != host["SwapTotal"] - host["SwapFree"]):
            raise Error("missing_or_invalid_memory_measurement")
        if any(type(sample["vmstat"][key]) is not int or sample["vmstat"][key] < 0
               for key in ("pswpin", "pswpout", "oom_kill")):
            raise Error("missing_or_invalid_telemetry")
        if any(type(sample["vmstat_delta"][key]) is not int or not 0 <= sample["vmstat_delta"][key] <= sample["vmstat"][key]
               for key in ("pswpin", "pswpout", "oom_kill")):
            raise Error("missing_or_invalid_telemetry")
        if sample["vmstat_delta"]["oom_kill"] != 0:
            raise Error("oom_counter_increased")
        if any(type(sample["errors"][key]) is not int or sample["errors"][key] != 0 for key in ERROR_PATTERNS):
            raise Error("runtime_cuda_oom_storage_or_fusion_error")
        if sample["slot_count"] != 1 or sample["slot_context"] != sample["required_context"]:
            raise Error("actual_slot_context_mismatch")
        if sample["n_threads"] != 112:
            raise Error("actual_thread_count_mismatch")
        if sample["container"]["image_id"] != BASELINE_IMAGE or sample["required_context"] == NATIVE_CONTEXT:
            native = sample.get("native")
            if native is None:
                raise Error("NOT_TESTED_native_startup_diagnostic_required")
            required = {"n_ctx": sample["required_context"], "n_ctx_seq": sample["required_context"], "n_seq_max": 1,
                        "n_batch": 2048, "n_ubatch": 512, "flash_attn": 1, "fused_lid": 1,
                        "lid_nodes": 21, "fa_nodes": 78, "no_alloc": 0}
            if any(type(native[key]) is not int or native[key] != value for key, value in required.items()):
                raise Error("native_graph_selection_mismatch")
            for kind in ("compute_bytes", "cache_bytes"):
                if set(native[kind]) != {"CUDA0", "CUDA1"} or any(type(value) is not int or value <= 0 for value in native[kind].values()):
                    raise Error("NOT_TESTED_native_allocated_buffers_required")
    except (KeyError, TypeError, ValueError):
        raise Error("missing_or_invalid_telemetry") from None
    return sample


def _reviewed_args(args, image_id, context):
    # The protected manager emits these canonical long options. Reject any
    # unknown override, including RoPE, context shift, cache reuse or a key value.
    flags = {"--cpu-moe", "--jinja", "--no-webui"}
    options = {"--model", "--host", "--port", "--alias", "--api-key-file", "--ctx-size",
               "--parallel", "--n-gpu-layers", "--split-mode", "--tensor-split", "--load-mode",
               "--device", "--chat-template-kwargs", "--n-cpu-moe"}
    values = {}
    index = 0
    while index < len(args):
        name = args[index]
        if name in values or name not in flags | options:
            raise Error("unreviewed_or_duplicate_runtime_option")
        if name in flags:
            values[name] = True
            index += 1
        else:
            if index + 1 >= len(args):
                raise Error("incomplete_runtime_option")
            values[name] = args[index + 1]
            index += 2
    required = {"--host": "0.0.0.0", "--port": "30002", "--alias": "glm-5.3",
                "--ctx-size": str(context), "--parallel": "1", "--n-gpu-layers": "999",
                "--split-mode": "layer", "--tensor-split": "1,1", "--load-mode": "none",
                "--device": "CUDA0,CUDA1", "--jinja": True, "--no-webui": True}
    if any(values.get(key) != value for key, value in required.items()):
        raise Error("reviewed_runtime_option_mismatch")
    if json.loads(values.get("--chat-template-kwargs", "null")) != {"clear_thinking": True}:
        raise Error("reviewed_template_option_mismatch")
    if values.get("--model") != "/models/UD-Q4_K_XL/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf" or values.get("--api-key-file") != "/run/secrets/llm-api-key":
        raise Error("reviewed_model_or_key_file_option_mismatch")
    if image_id == BASELINE_IMAGE:
        if context != 32768 or values.get("--cpu-moe") is not True or "--n-cpu-moe" in values:
            raise Error("old_d1_is_32k_all_cpu_baseline_only")
        return "all_cpu"
    if values.get("--n-cpu-moe") != "76" or "--cpu-moe" in values:
        raise Error("only_reviewed_n76_candidate")
    return "n_cpu_moe_76"


def _run(argv, limit=65536):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10,
                            env=dict(os.environ, LC_ALL="C", TZ="UTC"))
    if result.returncode or len(result.stdout) > limit:
        raise Error("bounded_telemetry_command_failed")
    return result.stdout.decode("utf-8", errors="strict")


def _metrics(path, names, unit="kB"):
    raw = Path(path).read_bytes()
    if len(raw) > 131072:
        raise Error("proc_read_bound_exceeded")
    result = {}
    for line in raw.decode().splitlines():
        parts = line.replace(":", " ").split()
        if parts and parts[0] in names:
            if (parts[0] in result or len(parts) != (3 if unit else 2)
                    or not re.fullmatch(r"[0-9]+", parts[1]) or unit and parts[2] != unit):
                raise Error("required_proc_metric_malformed")
            result[parts[0]] = int(parts[1])
    if set(result) != set(names):
        raise Error("required_proc_metric_missing")
    return result


def _process_identity(pid):
    raw = Path("/proc/%d/stat" % pid).read_bytes()
    if len(raw) > 65536:
        raise Error("proc_read_bound_exceeded")
    prefix, sep, tail = raw.decode().rpartition(") ")
    fields = tail.split()
    if (not sep or not prefix.startswith(str(pid) + " (") or len(fields) < 20
            or fields[0] not in ("R", "S", "D", "I")
            or not re.fullmatch(r"[0-9]+", fields[19]) or int(fields[19]) <= 0):
        raise Error("process_identity_or_state_invalid")
    return int(fields[19]), fields[0]


def _owned_cgroup_path(pid, container_id):
    """Accept only canonical whole-host Docker v2 groups for the exact PID/ID."""
    if (type(pid) is not int or pid <= 0 or not isinstance(container_id, str)
            or not re.fullmatch(r"[0-9a-f]{64}", container_id)):
        raise Error("owned_cgroup_identity_invalid")
    try:
        raw = Path("/proc/%d/cgroup" % pid).read_bytes()
    except OSError:
        raise Error("owned_cgroup_unavailable_or_invalid") from None
    if len(raw) > 4096:
        raise Error("owned_cgroup_path_invalid")
    allowed = ("/system.slice/docker-" + container_id + ".scope", "/docker/" + container_id)
    for path in allowed:
        if raw in (("0::" + path + "\n").encode(), ("0::" + path).encode()):
            return path
    raise Error("owned_cgroup_path_invalid")


def _cgroup_swap(pid, container_id):
    """Read only the owned group's v2 byte counter through protected dir fds."""
    path = _owned_cgroup_path(pid, container_id)
    descriptors = []
    identities = []
    components = ["sys", "fs", "cgroup"] + path.lstrip("/").split("/")
    try:
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        descriptors.append(fd)
        metadata = os.fstat(fd)
        if metadata.st_uid != 0 or metadata.st_mode & 0o022:
            raise Error("cgroup_ancestry_unprotected")
        for component in components:
            parent = fd
            fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                         dir_fd=parent)
            descriptors.append(fd)
            metadata = os.fstat(fd)
            if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o022:
                raise Error("cgroup_ancestry_unprotected")
            identities.append((metadata.st_dev, metadata.st_ino))
        root_fd, leaf_fd = descriptors[3], descriptors[-1]
        raw = Path("/proc/self/mountinfo").read_bytes()
        if len(raw) > 131072:
            raise Error("cgroup_mount_identity_invalid")
        mounts = [line.split() for line in raw.decode().splitlines()]
        matches = [row for row in mounts if len(row) >= 10 and row[4] == "/sys/fs/cgroup"]
        if len(matches) != 1:
            raise Error("cgroup_mount_identity_invalid")
        mount = matches[0]
        separator = mount.index("-")
        if (separator < 6 or len(mount) < separator + 4
                or mount[3] != "/" or mount[separator + 1] != "cgroup2"
                or not re.fullmatch(r"[0-9]+", mount[0])):
            raise Error("cgroup_mount_identity_invalid")
        mount_id = int(mount[0])
        # fdinfo binds the opened directories to this exact whole-root v2 mount,
        # including refusal of bind-mounted descendants or a replaced root.
        for current in descriptors[3:]:
            if _metrics("/proc/self/fdinfo/%d" % current, {"mnt_id"}, unit=None)["mnt_id"] != mount_id:
                raise Error("cgroup_mount_identity_invalid")

        def read_owned(name):
            opened = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=leaf_fd)
            with os.fdopen(opened, "rb") as handle:
                metadata = os.fstat(handle.fileno())
                if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0
                        or metadata.st_mode & 0o022 or metadata.st_dev != os.fstat(root_fd).st_dev
                        or _metrics("/proc/self/fdinfo/%d" % handle.fileno(), {"mnt_id"}, unit=None)["mnt_id"] != mount_id):
                    raise Error("cgroup_file_identity_invalid")
                data = handle.read(65537)
                if len(data) > 65536:
                    raise Error("cgroup_read_bound_exceeded")
                return data

        def member():
            raw = read_owned("cgroup.procs")
            if not re.fullmatch(rb"(?:[1-9][0-9]*\n)+", raw) or str(pid).encode() not in raw.splitlines():
                raise Error("owned_pid_not_in_cgroup")

        member()
        raw = read_owned("memory.swap.current")
        if not re.fullmatch(rb"[0-9]+\n?", raw):
            raise Error("cgroup_swap_metric_invalid")
        value = int(raw)
        member()
        if _owned_cgroup_path(pid, container_id) != path:
            raise Error("owned_cgroup_changed")
        for index, component in enumerate(components):
            metadata = os.stat(component, dir_fd=descriptors[index], follow_symlinks=False)
            if (metadata.st_dev, metadata.st_ino) != identities[index]:
                raise Error("owned_cgroup_changed")
        return value, (path, mount_id, identities[2], identities[-1])
    except (OSError, ValueError, IndexError, UnicodeError):
        raise Error("owned_cgroup_unavailable_or_invalid") from None
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def _local_snapshot(container_id, image_id, context, state, full=True):
    """Runs fixed read-only telemetry in the ephemeral SSH Python process."""
    began = time.monotonic()
    container = json.loads(_run(["docker", "inspect", container_id], 262144))[0]
    if container["Id"] != container_id or container["Image"] != image_id:
        raise Error("container_or_image_identity_changed")
    placement = _reviewed_args(container["Args"], image_id, context)
    if container["NetworkSettings"]["Ports"] != {"30002/tcp": [{"HostIp": "127.0.0.1", "HostPort": "30002"}]}:
        raise Error("reviewed_loopback_publication_mismatch")
    status = container["State"]
    pid = status["Pid"]
    identity = (pid, status["StartedAt"], container["LogPath"])
    if "process_identity" in state and state["process_identity"] != identity:
        raise Error("container_process_restarted")
    state["process_identity"] = identity
    if not status["Running"] or status["OOMKilled"] or type(pid) is not int or pid <= 0:
        raise Error("container_not_safe_running")
    start_ticks, process_state = _process_identity(pid)
    if "process_start_ticks" in state and state["process_start_ticks"] != start_ticks:
        raise Error("process_identity_changed")
    state["process_start_ticks"] = start_ticks
    initial_swap, initial_cgroup = _cgroup_swap(pid, container_id)
    if initial_swap != 0:
        raise Error("owned_cgroup_swap_in_use")
    if "cgroup_identity" in state and state["cgroup_identity"] != initial_cgroup:
        raise Error("owned_cgroup_changed")
    state["cgroup_identity"] = initial_cgroup
    mounts = {}
    for target, uuid in MOUNTS.items():
        entry = json.loads(_run(["findmnt", "-J", "-o", "TARGET,UUID,FSTYPE", "--target", target]))["filesystems"][0]
        if entry != {"target": target, "uuid": uuid, "fstype": "ext4"}:
            raise Error("exact_mount_identity_failed")
        mounts[target] = entry["uuid"]
    log = Path(container["LogPath"])
    if not str(log).startswith("/data/docker/containers/" + container_id + "/"):
        raise Error("container_log_outside_data")
    st = log.stat()
    if "log_inode" in state and state["log_inode"] != (st.st_dev, st.st_ino):
        raise Error("log_rotated_monitoring_gap")
    state["log_inode"] = (st.st_dev, st.st_ino)
    offset = state.get("log_offset", 0)
    if st.st_size < offset or st.st_size - offset > (524288 if offset == 0 else 65536):
        raise Error("log_read_bound_or_gap")
    with log.open("rb") as handle:
        handle.seek(offset)
        data = handle.read(st.st_size - offset)
    state["log_offset"] = st.st_size
    state["log_hash"].update(data)
    pending = state.get("log_pending", b"") + data
    lines = pending.split(b"\n")
    state["log_pending"] = lines.pop()
    for raw in lines:
        parse_log_line(json.loads(raw)["log"], state)
    kernel = _run(["dmesg", "--level", "err,crit,alert,emerg", "--since", status["StartedAt"][:19].replace("T", " ")])
    kernel_errors = {name: len(re.findall(pattern, kernel, re.I)) for name, pattern in ERROR_PATTERNS.items()}
    host = _metrics("/proc/meminfo", {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"})
    process = _metrics("/proc/%d/status" % pid, {"VmRSS", "VmSwap"})
    if full:
        process.update(_metrics("/proc/%d/smaps_rollup" % pid, {"Rss", "Pss", "Swap"}))
    vmstat = _metrics("/proc/vmstat", {"pswpin", "pswpout", "oom_kill"}, unit=None)
    if "vmstat_start" not in state:
        state["vmstat_start"] = vmstat.copy()
    gpu_raw = _run(["nvidia-smi", "--query-gpu=index,uuid,memory.total,memory.free", "--format=csv,noheader,nounits"])
    gpus = []
    for line in gpu_raw.splitlines():
        index, uuid, total, free = [part.strip() for part in line.split(",")]
        gpus.append({"index": int(index), "uuid": uuid, "total_bytes": int(total) * 1024 ** 2,
                     "free_bytes": int(free) * 1024 ** 2})
    gpu_ids = tuple((gpu["index"], gpu["uuid"]) for gpu in gpus)
    if "gpu_ids" in state and state["gpu_ids"] != gpu_ids:
        raise Error("gpu_identity_changed")
    state["gpu_ids"] = gpu_ids
    root = os.statvfs("/")
    cgroup_swap, cgroup_identity = _cgroup_swap(pid, container_id)
    if cgroup_identity != initial_cgroup:
        raise Error("owned_cgroup_changed")
    after = json.loads(_run(["docker", "inspect", container_id], 262144))[0]
    if (any(after[key] != container[key] for key in ("Id", "Image", "Args", "LogPath", "RestartCount"))
            or any(after["State"][key] != status[key] for key in
                   ("Pid", "StartedAt", "Running", "OOMKilled", "Paused", "Restarting", "Dead"))
            or after["NetworkSettings"]["Ports"] != container["NetworkSettings"]["Ports"]):
        raise Error("container_identity_changed_during_sample")
    final_ticks, process_state = _process_identity(pid)
    if final_ticks != start_ticks or _owned_cgroup_path(pid, container_id) != cgroup_identity[0]:
        raise Error("process_or_cgroup_changed_during_sample")
    result = {"schema_version": 2, "sample_kind": "full" if full else "cheap",
              "timestamp": time.time(), "sample_elapsed_seconds": time.monotonic() - began,
              "process_start_ticks": start_ticks, "process_state": process_state,
              "sampled_only": True, "required_context": context,
              "container": {"id": container_id, "image_id": image_id, "pid": pid,
                            "started_at": status["StartedAt"], "running": status["Running"],
                            "oom_killed": status["OOMKilled"], "paused": status["Paused"],
                            "restarting": status["Restarting"], "dead": status["Dead"],
                            "restart_count": container["RestartCount"]},
              "mounts": mounts, "root_available_bytes": root.f_bavail * root.f_frsize,
              "host_kib": host, "process_kib": process, "vmstat": vmstat,
              "cgroup_swap_current_bytes": cgroup_swap,
              "host_swap_used_kib": host["SwapTotal"] - host["SwapFree"],
              "vmstat_delta": {key: vmstat[key] - state["vmstat_start"][key] for key in vmstat},
              "gpus": gpus, "errors": {key: state["errors"][key] + kernel_errors[key] for key in ERROR_PATTERNS},
              "slot_count": state.get("slot_count"), "slot_context": state.get("slot_context"),
              "n_threads": state.get("n_threads"), "placement": placement,
              "log": {"path": str(log), "read_bytes": state["log_offset"], "sha256": state["log_hash"].hexdigest()},
              "native": state.get("native")}
    return result


def _remote_main(container_id, image_id, context, cap_seconds):
    state = {"log_lines": 0, "errors": {key: 0 for key in ERROR_PATTERNS}, "log_hash": hashlib.sha256()}
    start = time.monotonic()
    full, terminal = True, cap_seconds == 0
    while True:
        try:
            sample = _local_snapshot(container_id, image_id, context, state, full=full)
            try:
                validate_snapshot(sample)
                sample["status"] = "PASS"
            except Error as exc:
                sample.update({"status": "STOP", "error": str(exc)})
            print(json.dumps(sample, separators=(",", ":")), flush=True)
            if sample["status"] == "STOP" or terminal:
                return
        except Exception:
            print(json.dumps({"status": "STOP", "error": "telemetry_collection_failed"}), flush=True)
            return
        # Full PSS is deliberately outside the periodic cadence. Start a fresh
        # one-second interval after the initial checkpoint; never catch up with
        # expensive repeated rollup reads.
        next_sample = time.monotonic() + max(0, 1.0 - (0 if full else sample["sample_elapsed_seconds"]))
        full = False
        delay = min(next_sample, start + cap_seconds) - time.monotonic()
        if delay <= 0 and time.monotonic() >= start + cap_seconds:
            return
        # One fixed command requests a terminal full checkpoint. EOF/anything
        # else closes this exact sampler; it cannot dispatch an API request.
        if select.select([sys.stdin], [], [], max(0, delay))[0]:
            if sys.stdin.readline() != "full\n":
                return
            full, terminal = True, True
        if time.monotonic() >= start + cap_seconds:
            return


def _source(container_id, image_id, context, cap_seconds):
    if not re.fullmatch(r"[0-9a-f]{64}", container_id) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise Error("full_container_and_image_ids_required")
    if type(context) is not int or context not in (32768, NATIVE_CONTEXT):
        raise Error("only_reviewed_32k_or_native_capacity")
    if type(cap_seconds) is not int or not 0 <= cap_seconds <= 86400:
        raise Error("bounded_sampler_cap_required")
    imports = "import hashlib,json,os,re,select,stat,subprocess,sys,time\nfrom pathlib import Path\nAgentError=RuntimeError\n"
    constants = "GIB=%r\nNATIVE_CONTEXT=%r\nBASELINE_IMAGE=%r\nMOUNTS=%r\nERROR_PATTERNS=%r\n" % (GIB, NATIVE_CONTEXT, BASELINE_IMAGE, MOUNTS, ERROR_PATTERNS)
    helpers = (Error, parse_log_line, validate_snapshot, _reviewed_args, _run, _metrics,
               _process_identity, _owned_cgroup_path, _cgroup_swap, _local_snapshot, _remote_main)
    return imports + constants + "\n".join(inspect.getsource(helper) for helper in helpers) + "\n_remote_main(%r,%r,%r,%r)\n" % (container_id, image_id, context, cap_seconds)


def start_sampler(container_id, image_id, context, cap_seconds):
    """Start one bounded SSH sampler: initial full, then cheap 1 Hz JSON rows.

    The caller drains stdout promptly and checks freshness/gaps <=2 seconds.
    Send full + newline for a terminal checkpoint; close stdin to stop without
    another read. No remote persistent files/PIDs.
    cap_seconds=0 is reserved for collect()'s single read-only observation.
    """
    source = _source(container_id, image_id, context, cap_seconds)
    command = ["ssh", "-T", "-S", "none", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
               "-o", "ClearAllForwardings=yes", "ai-vm",
               "sudo -n python3 -B -u -c 'import json,sys;exec(json.loads(sys.stdin.readline()))'"]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True, bufsize=1)
    try:
        process.stdin.write(json.dumps(source) + "\n")
        process.stdin.flush()
    except Exception:
        stop_sampler(process)
        raise Error("sampler_start_failed") from None
    return process


def stop_sampler(process):
    """Close/reap only the exact Popen SSH transport returned by start_sampler."""
    if process.stdin is not None and not process.stdin.closed:
        process.stdin.close()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    if process.stdout is not None:
        process.stdout.close()


def collect(container_id, image_id, context):
    """One bounded actual telemetry read; returns measurements even on STOP."""
    sampler = Sampler(container_id, image_id, context, 0)
    try:
        result = sampler.next(timeout=30)
        if result.get("status") == "STOP":
            return result  # Preserve missing-checkpoint evidence; bind still refuses.
        if result.get("container", {}).get("id") != container_id or result.get("container", {}).get("image_id") != image_id:
            raise Error("snapshot_identity_unavailable_or_changed")
        return result
    finally:
        sampler.close()


def stable_identity(sample):
    """Actual immutable runtime identity; usable across paused client stages."""
    try:
        container = sample["container"]
        return (container["id"], container["image_id"], container["pid"], container["started_at"],
                sample["process_start_ticks"], container["restart_count"],
                sample["required_context"], sample["slot_context"], sample["placement"],
                tuple((gpu["index"], gpu["uuid"]) for gpu in sample["gpus"]))
    except (KeyError, TypeError):
        raise Error("runtime_identity_missing") from None


def check_snapshot(sample, native=False, previous=None, require_full=False, checkpoint=False):
    validate_snapshot(sample)
    if (require_full or checkpoint) and sample["sample_kind"] != "full":
        raise Error("full_memory_checkpoint_required")
    if native and sample["required_context"] != NATIVE_CONTEXT:
        raise Error("native_capacity_required")
    timestamp = sample.get("timestamp")
    # Worker/VM clocks measured ~24ms apart on this VM; tolerate at most 250ms
    # future skew while retaining the strict two-second stale-sample stop.
    if type(timestamp) not in (float, int) or not -0.25 <= time.time() - timestamp <= 2:
        raise Error("snapshot_stale_or_future")
    if previous is not None:
        if stable_identity(sample) != stable_identity(previous):
            raise Error("runtime_changed_during_request")
        gap = timestamp - previous["timestamp"]
        if gap <= 0 or not checkpoint and gap > 2:
            raise Error("sample_gap_or_replay")
        if sample["vmstat"]["oom_kill"] != previous["vmstat"]["oom_kill"]:
            raise Error("oom_counter_changed")
        if any(sample["vmstat"][key] < previous["vmstat"][key] for key in ("pswpin", "pswpout")):
            raise Error("host_swap_counter_regressed")
        if sample.get("native") != previous.get("native"):
            raise Error("native_diagnostic_changed")
    return sample


class Sampler:
    """Task-specific reader for its one exact ephemeral SSH sampler process."""
    def __init__(self, container_id, image_id, context, cap_seconds):
        self.process = start_sampler(container_id, image_id, context, cap_seconds)
        self.pending = b""
        self.full_requested = False

    def request_full_checkpoint(self):
        """Request exactly one terminal full read; next() still drains cheap rows."""
        if self.full_requested:
            raise Error("full_checkpoint_already_requested")
        self.full_requested = True
        try:
            self.process.stdin.write("full\n")
            self.process.stdin.flush()
        except Exception:
            raise Error("full_checkpoint_request_failed") from None

    def next(self, timeout=3):
        if not 0 < timeout <= 30:
            raise Error("bounded_snapshot_read_timeout_required")
        deadline = time.monotonic() + timeout
        while b"\n" not in self.pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                raise Error("snapshot_timeout")
            data = os.read(self.process.stdout.fileno(), 65537)
            if not data:
                raise Error("snapshot_transport_closed")
            self.pending += data
            if len(self.pending) > 65536:
                raise Error("snapshot_transport_bound_exceeded")
        line, self.pending = self.pending.split(b"\n", 1)
        try:
            return json.loads(line)
        except (ValueError, UnicodeDecodeError):
            raise Error("invalid_snapshot_json") from None

    def close(self):
        stop_sampler(self.process)
