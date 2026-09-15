"""Read-only host facts and explicit capacity estimates; no fit claim from weights."""
from __future__ import annotations
import json
from pathlib import Path
import platform
import shutil
from .config import MODELS
from .core import InstallError

GIB = 1024 ** 3


def observe(runner):
    facts = {"system": platform.system(), "architecture": platform.machine(),
             "kernel": platform.release(), "os_id": None, "os_version": None,
             "root_available_bytes": shutil.disk_usage("/").free,
             "ram_bytes": None, "cpu_flags": [], "gpus": None, "dns": "unverified",
             "package_manager": "unverified", "listeners": "unverified"}
    if facts["system"] != "Linux":
        return facts
    try:
        release = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line)
        facts.update(os_id=release.get("ID", "").strip('"'), os_version=release.get("VERSION_ID", "").strip('"'))
        info = Path("/proc/meminfo").read_text()
        facts["ram_bytes"] = int(next(x.split()[1] for x in info.splitlines() if x.startswith("MemTotal:"))) * 1024
        cpu = Path("/proc/cpuinfo").read_text()
        facts["cpu_flags"] = next((x.split(":", 1)[1].split() for x in cpu.splitlines() if x.startswith("flags")), [])
    except (OSError, ValueError, StopIteration):
        facts["discovery"] = "incomplete"
    try:
        lines = runner.run(["nvidia-smi", "--query-gpu=index,name,memory.total,driver_version", "--format=csv,noheader,nounits"]).splitlines()
        facts["gpus"] = []
        for line in lines:
            index, name, memory, driver = [x.strip() for x in line.split(",")]
            facts["gpus"].append({"index": index, "name": name, "memory_mib": int(memory), "driver": driver})
    except (InstallError, ValueError):
        facts["gpu_discovery"] = "driver_absent_or_query_unavailable"
    for field, command in (("dns", ["getent", "ahosts", "snapshot.ubuntu.com"]),
                           ("package_manager", ["dpkg", "--print-architecture"]),
                           ("listeners", ["ss", "-H", "-ltn"])):
        try:
            output = runner.run(command, timeout=20)
            facts[field] = output.strip().splitlines()[:100]
        except InstallError:
            facts[field] = "unavailable"
    return facts


def supported(facts):
    return (facts.get("system") == "Linux" and facts.get("architecture") in {"amd64", "x86_64"}
            and facts.get("os_id") == "ubuntu" and facts.get("os_version") == "24.04")


def model_plan(config, repo):
    rows = []
    if config["role"] == "client":
        return rows
    for name in config["model_set"].split(","):
        source = Path(repo) / MODELS[name]
        manifest = json.loads(source.read_text())
        if sum(x["size_bytes"] for x in manifest["artifacts"]) != manifest["total_bytes"]:
            raise InstallError("manifest_size_mismatch")
        rows.append({"selection": name, "repo_id": manifest["repo_id"], "revision": manifest["revision"],
                     "artifact_count": manifest["artifact_count"], "download_bytes": manifest["total_bytes"],
                     "manifest": MODELS[name], "quantization": manifest["quantization"],
                     "capacity_status": "UNVERIFIED: readiness, generation and agent acceptance required",
                     "measured_ram_vram_minimum": None,
                     "candidate_hardware": "D1/F1A dual 96 GB GPUs; full-model fit/peak not measured",
                     "runtime_profile": "llama-cpp-v0.4.1-d1" if name == "glm" else "sglang-qwen-next-0.5.14"})
    return rows


def budget(config, models, storage):
    model_bytes = sum(x["download_bytes"] for x in models)
    # Conservative disk reservations only. Never interpret as RAM/VRAM minima.
    runtime_reserve = sum(100 if x["selection"] == "glm" else 40 for x in models) * GIB
    reserve = 20 * GIB
    capacity = storage.get("capacity", {})
    shared = capacity.get("shared_model_filesystem", True)
    data_required = runtime_reserve + reserve + (model_bytes if shared else 0)
    model_required = data_required if shared else model_bytes + reserve
    available = (capacity.get("data_available_bytes"), capacity.get("model_available_bytes"))
    return {"model_download_bytes": model_bytes, "runtime_build_reserve_bytes": runtime_reserve,
            "free_reserve_bytes": reserve, "shared_model_filesystem": shared,
            "data_required_bytes": data_required, "model_required_bytes": model_required,
            "space_status": "unverified" if any(x is None for x in available) else
                ("sufficient_for_full_artifact_reservation" if available[0] >= data_required and available[1] >= model_required else "insufficient"),
            "note": "Fresh full-download reservation; no duplicate weight cache. Acquisition remeasures remaining bytes under one owner and counts completed runtime storage in actual free space."}
