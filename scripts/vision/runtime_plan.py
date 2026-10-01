#!/usr/bin/env python3
"""Describe isolated vision candidate argv. This program never executes it."""
import argparse
import json
from pathlib import Path
import re


def plan(config, profile="16k"):
    if config.get("activation") != "DISABLED_SOURCE_PREPARATION":
        raise ValueError("source_preparation_gate_required")
    if profile not in ("16k", "32k"):
        raise ValueError("unknown_profile")
    image = config["container"]["image"]
    if not re.fullmatch(r"vllm/vllm-openai@sha256:[0-9a-f]{64}", image):
        raise ValueError("immutable_runtime_image_required")
    caps = config["profiles"][profile]
    if not (16384 <= caps["qwenTotalTokens"] <= 32768):
        raise ValueError("bounded_context_required")
    if sum(m["gpuMemoryUtilization"] for m in config["models"]) > .93 + 1e-9:
        raise ValueError("combined_vram_reserve_required")
    servers = []
    for model in config["models"]:
        argv = ["vllm", "serve", model["candidateModelPath"], "--served-model-name", model["repo"],
                "--dtype", "bfloat16", "--tensor-parallel-size", "1", "--host", "127.0.0.1",
                "--port", str(model["candidatePort"]), "--max-num-seqs", "1",
                "--gpu-memory-utilization", str(model["gpuMemoryUtilization"]),
                "--max-model-len", str(caps["qwenTotalTokens"] if model["role"] == "interpretation" else caps["ocrTotalTokens"]),
                "--max-num-batched-tokens", "4096", "--mm-processor-cache-gb", "0",
                "--limit-mm-per-prompt", '{"image":1,"video":0}']
        if model["role"] == "interpretation":
            argv += ["--reasoning-parser", "qwen3"]
        else:
            argv += ["--no-enable-prefix-caching"]
        servers.append({"repo": model["repo"], "revision": model["revision"], "argv": argv,
                        "execute": False, "remoteCodeExecution": False})
    return {"activation": config["activation"], "profile": profile, "execute": False,
            "gpuUuidProposed": config["placement"]["proposedGpuUuid"], "servers": servers,
            "gates": config["gates"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("/opt/vision/candidate.json"))
    parser.add_argument("--profile", choices=("16k", "32k"), default="16k")
    args = parser.parse_args()
    print(json.dumps(plan(json.loads(args.config.read_text()), args.profile), indent=2))


if __name__ == "__main__":
    main()
