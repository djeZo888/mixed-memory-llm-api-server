#!/usr/bin/env python3
"""Generate offline manifests and private serialized fixture samples. Never RUN."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from benchmark.fixtures import build_sample, canonical, serialize_validate
from benchmark.profiles import command_manifest, trial_order


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="worker task directory outside Git checkout")
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents:
        parser.error("private samples must be outside the Git checkout")
    output.mkdir(parents=True, exist_ok=True)
    private = output / "private-fixtures"
    private.mkdir(mode=0o700, exist_ok=True)
    if private.is_symlink() or private.stat().st_mode & 0o077:
        parser.error("private fixture directory must have mode 0700")
    manifests = [command_manifest(p, n) for p in ("G2", "G1", "Q2", "Q1") for n in (4096, 16384, 65536)]
    (output / "command-manifest.json").write_text(json.dumps({"evidence": "OFFLINE_GENERATED_NOT_EXECUTED",
        "commands": manifests, "mixed_commands": "Generate with measured split_resources caps after isolated G1/Q1 acceptance"}, indent=2) + "\n")
    (output / "trial-plan.json").write_text(json.dumps(trial_order(), indent=2) + "\n")
    summaries = []
    for model in ("bench-glm-5.3", "bench-qwen3.8-27b"):
        for kind in ("retrieval", "generation", "tool"):
            sample = build_sample(model, 32, "benchprep-source-v1", "offline-serialized-sample-0001", kind=kind,
                                  output_cap=512 if kind == "generation" else 256)
            raw = serialize_validate(sample)
            name = f"{model}-{kind}"
            for suffix, data in (("request.json", raw), ("scorer.json", canonical(sample["scorer"]))):
                path = private / f"{name}.{suffix}"
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
            summaries.append({"sample": name, "request_sha256": hashlib.sha256(raw).hexdigest(),
                              "fixture_sha256": sample["fixture_sha256"], "bytes": len(raw),
                              "serialization_validation": "PASS_OFFLINE", "actual_tokens": None,
                              "private_path": str(private / f"{name}.request.json")})
    (output / "fixture-manifest.json").write_text(json.dumps({"evidence": "SYNTHETIC_OFFLINE_FIXTURES",
        "capacity_fit": "NOT_TESTED_NATIVE_TOKENIZER", "samples": summaries}, indent=2) + "\n")
    print("PASS: 12 command manifests and 6 exact serialized private fixtures generated offline; no live operations")


if __name__ == "__main__":
    main()
