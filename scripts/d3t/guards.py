"""Concrete ai-vm D3T telemetry: read-only SSH, bounded logs, 1 Hz samples.

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
        if not sample["container"]["running"] or sample["container"]["oom_killed"]:
            raise Error("container_not_safe_running")
        if sample["root_available_bytes"] < 4 * GIB:
            raise Error("root_below_4gib")
        if sample["mounts"] != MOUNTS:
            raise Error("mount_uuid_mismatch")
        if len(sample["gpus"]) != 2 or {g["index"] for g in sample["gpus"]} != {0, 1}:
            raise Error("requires_two_exact_gpus")
        for gpu in sample["gpus"]:
            if gpu["free_bytes"] < 16 * GIB or gpu["free_bytes"] > gpu["total_bytes"]:
                raise Error("gpu_below_16gib_or_invalid")
        host, process = sample["host_kib"], sample["process_kib"]
        if host["MemAvailable"] <= 0 or process["Rss"] <= 0 or not 0 < process["Pss"] <= process["Rss"]:
            raise Error("missing_or_invalid_memory_measurement")
        if process["Swap"] != 0 or process["VmSwap"] != 0:
            raise Error("target_process_swap_in_use")
        if any(sample["vmstat_delta"][key] != 0 for key in ("pswpin", "pswpout", "oom_kill")):
            raise Error("swap_or_oom_counter_increased")
        if any(sample["errors"][key] != 0 for key in ERROR_PATTERNS):
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
            if any(native[key] != value for key, value in required.items()):
                raise Error("native_graph_selection_mismatch")
            for kind in ("compute_bytes", "cache_bytes"):
                if set(native[kind]) != {"CUDA0", "CUDA1"} or any(value <= 0 for value in native[kind].values()):
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


def _metrics(path, names):
    raw = Path(path).read_bytes()
    if len(raw) > 131072:
        raise Error("proc_read_bound_exceeded")
    result = {}
    for line in raw.decode().splitlines():
        parts = line.replace(":", " ").split()
        if parts and parts[0] in names:
            result[parts[0]] = int(parts[1])
    if set(result) != set(names):
        raise Error("required_proc_metric_missing")
    return result


def _local_snapshot(container_id, image_id, context, state):
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
    if not status["Running"] or status["OOMKilled"] or not isinstance(pid, int) or pid <= 0:
        raise Error("container_not_safe_running")
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
    process = _metrics("/proc/%d/smaps_rollup" % pid, {"Rss", "Pss", "Swap"})
    process.update(_metrics("/proc/%d/status" % pid, {"VmSwap"}))
    vmstat = _metrics("/proc/vmstat", {"pswpin", "pswpout", "oom_kill"})
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
    result = {"timestamp": time.time(), "sample_elapsed_seconds": time.monotonic() - began,
              "sampled_only": True, "required_context": context,
              "container": {"id": container_id, "image_id": image_id, "pid": pid,
                            "started_at": status["StartedAt"], "running": status["Running"],
                            "oom_killed": status["OOMKilled"]},
              "mounts": mounts, "root_available_bytes": root.f_bavail * root.f_frsize,
              "host_kib": host, "process_kib": process, "vmstat": vmstat,
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
    next_sample = start
    while True:
        try:
            sample = _local_snapshot(container_id, image_id, context, state)
            try:
                validate_snapshot(sample)
                sample["status"] = "PASS"
            except Error as exc:
                sample.update({"status": "STOP", "error": str(exc)})
            print(json.dumps(sample, separators=(",", ":")), flush=True)
            if sample["status"] == "STOP" or cap_seconds == 0:
                return
        except Exception:
            print(json.dumps({"status": "STOP", "error": "telemetry_collection_failed"}), flush=True)
            return
        next_sample += 1.0
        delay = min(next_sample, start + cap_seconds) - time.monotonic()
        if delay <= 0 and time.monotonic() >= start + cap_seconds:
            return
        # Closing this exact SSH process's stdin ends only its ephemeral sampler.
        if select.select([sys.stdin], [], [], max(0, delay))[0]:
            return
        if time.monotonic() >= start + cap_seconds:
            return


def _source(container_id, image_id, context, cap_seconds):
    if not re.fullmatch(r"[0-9a-f]{64}", container_id) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise Error("full_container_and_image_ids_required")
    if type(context) is not int or context not in (32768, NATIVE_CONTEXT):
        raise Error("only_reviewed_32k_or_native_capacity")
    if type(cap_seconds) is not int or not 0 <= cap_seconds <= 86400:
        raise Error("bounded_sampler_cap_required")
    imports = "import hashlib,json,os,re,select,subprocess,sys,time\nfrom pathlib import Path\nAgentError=RuntimeError\n"
    constants = "GIB=%r\nNATIVE_CONTEXT=%r\nBASELINE_IMAGE=%r\nMOUNTS=%r\nERROR_PATTERNS=%r\n" % (GIB, NATIVE_CONTEXT, BASELINE_IMAGE, MOUNTS, ERROR_PATTERNS)
    helpers = (Error, parse_log_line, validate_snapshot, _reviewed_args, _run, _metrics, _local_snapshot, _remote_main)
    return imports + constants + "\n".join(inspect.getsource(helper) for helper in helpers) + "\n_remote_main(%r,%r,%r,%r)\n" % (container_id, image_id, context, cap_seconds)


def start_sampler(container_id, image_id, context, cap_seconds):
    """Start one bounded SSH sampler; stdout is compact JSON lines at 1 Hz.

    The caller drains stdout promptly and checks freshness/gaps <=2 seconds.
    Close stdin then wait to stop this sampler; no remote persistent files/PIDs.
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
                sample["required_context"], sample["slot_context"], sample["placement"],
                tuple((gpu["index"], gpu["uuid"]) for gpu in sample["gpus"]))
    except (KeyError, TypeError):
        raise Error("runtime_identity_missing") from None


def check_snapshot(sample, native=False, previous=None):
    validate_snapshot(sample)
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
        if not 0 < timestamp - previous["timestamp"] <= 2:
            raise Error("sample_gap_or_replay")
        if any(sample["vmstat"][key] != previous["vmstat"][key] for key in ("pswpin", "pswpout", "oom_kill")):
            raise Error("swap_or_oom_counter_changed")
    return sample


class Sampler:
    """Task-specific reader for its one exact ephemeral SSH sampler process."""
    def __init__(self, container_id, image_id, context, cap_seconds):
        self.process = start_sampler(container_id, image_id, context, cap_seconds)
        self.pending = b""

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
