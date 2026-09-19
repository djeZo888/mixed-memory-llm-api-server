"""Bounded G1 schema ladder: two loads, two discarded warmups, three measurements.

No network at import/prepare. Run requires the source/session-bound root receipt.
All VM lifecycle, storage, native proof, transport and restoration remain shared.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import socket
import stat
import time

from agent import protocol
from . import client, fixtures, glmrepair, profiles, runner, worker_verify
from .warmup import prefill_proof

BASE = "327714f6cf1b3a2e834c7f79571ca322fb62f504"
MODEL = "bench-glm-5.3"
SEED = "g1-ladder-fixture-1729"
SCHEMA = {"type": "json_schema", "json_schema": {"name": "retrieval", "strict": True,
    "schema": {"type": "object", "properties": {k: {"type": "string"} for k in fixtures.MARKERS},
               "required": list(fixtures.MARKERS), "additionalProperties": False}}}


def body_bytes(sample, output_cap=256):
    if output_cap not in (32, 256):
        raise ValueError("ladder_output_cap")
    body = protocol.strict_json_loads(fixtures.serialize_validate(sample))
    if body["model"] != MODEL or sample["kind"] != "retrieval":
        raise ValueError("ladder_retrieval_only")
    body.update(temperature=1.0, seed=1729, response_format=copy.deepcopy(SCHEMA), max_tokens=output_cap)
    return fixtures.canonical(body)


def fit(capacity, nonce, counter, *, warmup=False, matched=None, synthetic=False):
    """Count FINAL bytes at every bracket; never estimate characters or refit repeat."""
    if capacity not in (16384, 65536) or (warmup and matched is not None):
        raise ValueError("ladder_capacity_or_matching")
    cap, ceiling = (32, 2432) if warmup else (256, capacity - 512)
    seed = "warmup-only-seed" if warmup else SEED
    low, high, records, bracketed, best = 12, capacity, 12, False, None
    if matched is not None:
        fixtures.serialize_validate(matched)
        if nonce == matched["nonce"] or matched["seed"] != seed:
            raise ValueError("fresh_matched_prefix_required")
        records = matched["records"]
    for attempt in range(1 if matched is not None else 32):
        sample = fixtures.build_sample(MODEL, records, seed, nonce)
        raw = body_bytes(sample, cap)
        counted = fixtures.validate_count(counter(raw), raw, capacity, synthetic=synthetic)
        actual = counted["input_tokens"]
        if matched is not None:
            if (sample["fixture_sha256"] != matched["fixture_sha256"] or sample["scorer"] != matched["scorer"]
                    or not ceiling - 128 <= actual <= ceiling):
                raise ValueError("matched_fixture_or_count_changed_no_refit")
            best = sample, raw, counted
            break
        if actual <= ceiling:
            best = sample, raw, counted
            if ceiling - actual <= 128:
                break
            low = records + 1
            if not bracketed:
                records = min(high, records * 2)
                continue
        else:
            high, bracketed = records - 1, True
        if low > high:
            break
        records = (low + high) // 2
    if best is None or not ceiling - 128 <= best[2]["input_tokens"] <= ceiling:
        raise ValueError("native_fit_outside_bounded_target")
    sample, raw, counted = best
    return sample, raw, {**counted, "input_ceiling_tokens": ceiling, "output_cap": cap,
        "margin_tokens": capacity - ceiling - cap, "fit_calls": attempt + 1,
        "fixture_sha256": sample["fixture_sha256"], "records": sample["records"],
        "matched_fixture_sha256": matched["fixture_sha256"] if matched else None}


def stage_clock(task):
    clock = json.loads((task / "stage-clock.json").read_bytes())
    start, deadline = clock.get("start_epoch"), clock.get("deadline_epoch")
    if (type(start) not in (int, float) or type(deadline) not in (int, float)
            or not math.isfinite(start) or not math.isfinite(deadline) or start <= 0
            or deadline != start + 10800 or clock.get("budget_seconds") != 10800
            or clock.get("restoration_outside_budget") is not True
            or clock.get("clock_includes_preparation") is not True):
        raise ValueError("fresh_absolute_3hour_clock_required")
    return clock


def checkpoint(task):
    glmrepair.checkpoint(task)
    # Routine notes are observations. Only explicit standalone directives stop.
    lines = (task / "incoming-latest.md").read_text().splitlines()
    if any(line.strip().upper() in {"STOP", "PAUSE", "ACTION: STOP", "ACTION: PAUSE"} for line in lines):
        raise RuntimeError("ROOT_EXPLICIT_STOP_OR_PAUSE")


class Ladder(glmrepair.Diagnostic):
    def boundary(self, cid, point):
        checkpoint(self.state)
        self.collect()
        if cid in self.safety:
            raise RuntimeError(self.safety[cid])
        self.record(point)

    def request(self, cid, raw, identifier, *, timed=True):
        if protocol.strict_json_loads(raw)["max_tokens"] == 256:
            return super().request(cid, raw, identifier, timed=timed)
        timeout = self.admission(cid)
        try:
            transport = self.transport_factory("http://127.0.0.1:31002", self.key,
                cancel_event=self.active[cid]["cancel_event"])
            result = client._capture_request(raw, transport, sample_id=identifier, private_dir=self.private,
                summary_path=self.state / "warmups.jsonl", timeout=timeout, clock=self.clock)
            if self.active[cid].get("abort_reason"):
                raise RuntimeError(self.active[cid]["abort_reason"])
            return self.persistence_check(result)
        finally:
            self.host.call("request_end", id=cid)

    def warm(self, cid, manifest, proof):
        capacity = manifest["configured_capacity"]
        identifier = "G1-" + str(capacity) + "-warmup"
        self.emit({"type": "native_allocation", "capacity": capacity, "container": cid,
            "manifest_sha256": fixtures.digest(fixtures.canonical(manifest)), "proof": proof})
        self.boundary(cid, "FITTING_" + identifier)
        sample, raw, counted = fit(capacity, "warmup-" + str(time.time_ns()), self.counter(cid), warmup=True)
        runner.save(self.private / (identifier + "-fixture.json"), sample)
        runner.save(self.private / (identifier + "-count.json"), counted)
        self.record("WARMING_" + str(capacity))
        result = self.request(cid, raw, identifier, timed=False)
        counters = result["summary"].get("counters", {})
        accepted = (result.get("parsed") and result["summary"]["status"] in {"COMPLETE", "OUTPUT_LIMIT"}
                    and counters.get("prompt_tokens") == counted["input_tokens"] and counters.get("cached_tokens") == 0)
        evidence = prefill_proof(counters, manifest, proof) if accepted else None
        self.emit({"type": "warmup", "id": identifier, "capacity": capacity, "count": counted,
            "summary": result["summary"], "prefill_proof": evidence, "timings": "DISCARDED",
            "checkpoint": self.host.call("quiescent", id=cid, point="warm_idle")})
        if not accepted:
            raise RuntimeError("STOP_WARMUP_NATIVE_OR_UNCACHED_PROOF")
        self.boundary(cid, "WARMED_" + str(capacity))

    def measure(self, cid, identifier, *, matched=None):
        capacity = self.active[cid]["manifest"]["configured_capacity"]
        self.boundary(cid, "FITTING_" + identifier)
        started = self.clock()
        sample, raw, counted = fit(capacity, "trial-" + str(time.time_ns()), self.counter(cid), matched=matched)
        preparation = self.clock() - started
        runner.save(self.private / (identifier + "-fixture.json"), sample)
        runner.save(self.private / (identifier + "-count.json"), counted)
        self.emit({"type": "fixture_prepared", "id": identifier, "count": counted,
            "seconds": preparation, "body_sha256": fixtures.digest(raw)})
        self.boundary(cid, "BEFORE_" + identifier)
        self.progress["inflight"][identifier] = {"container": cid, "capacity": capacity}
        self.record("MEASURING_" + identifier)
        result = self.request(cid, raw, identifier)
        summary, parsed = result["summary"], result.get("parsed")
        counters = summary.get("counters", {})
        score = (fixtures.score_retrieval(sample, parsed["message"]) if parsed else
                 {"status": "HARNESS_FAILURE", "reason": "native_response_unparsed"})
        native_ok = (summary["status"] == "COMPLETE" and counters.get("cached_tokens") == 0
            and counters.get("prompt_tokens") == counted["input_tokens"]
            and counters.get("evaluated_prompt_tokens") == counted["input_tokens"])
        n, ms = counters.get("decode_tokens"), counters.get("decode_ms")
        row = {"type": "trial", "id": identifier, "capacity": capacity, "placement": "G1",
            "status": "PASS" if native_ok and score["status"] == "PASS" else "STOP_REQUEST_GATE",
            "score": score, "strict_native_uncached_gate": bool(native_ok), "count": counted,
            "summary": summary, "fixture_sha256": sample["fixture_sha256"], "records": sample["records"],
            "native_n_minus_1_decode_tokens_per_second": (n - 1) * 1000 / ms if type(n) is int and n > 1 and type(ms) in (int, float) and ms > 0 else None,
            "occupied_window_tokens": (counters.get("prompt_tokens") or 0) + (counters.get("completion_tokens") or 0),
            "output_composition": glmrepair.format_outcome(result, sample),
            "finish_reason": parsed.get("finish_reason") if parsed else None,
            "fixture_preparation_seconds": preparation, "output_modified": False,
            "limitations": ["short_output_counts_vary", "sampled_memory_peaks_not_absolute"],
            "telemetry": self.telemetry_window(cid, summary.get("request_started_monotonic_s"),
                summary.get("request_ended_monotonic_s"), "inference_transport_dispatch_to_drain")}
        self.emit(row)
        runner.save(self.state / (identifier + "-result.json"), row)
        self.progress["completed"][identifier] = row
        del self.progress["inflight"][identifier]
        self.record("COMPLETED_" + identifier)
        self.boundary(cid, "AFTER_" + identifier)
        if row["status"] != "PASS":
            raise RuntimeError("STOP_REQUEST_GATE")
        return sample

    def sequence(self):
        checkpoint(self.state)
        self.host.call("begin")
        for manifest in self.armed["manifests"]:
            capacity = manifest["configured_capacity"]
            self.record("LOADING_" + str(capacity))
            cid = self.loaded(manifest)
            sample = self.measure(cid, "G1-" + str(capacity) + "-primary")
            if capacity == 16384:
                self.measure(cid, "G1-16384-repeat", matched=sample)
            self.retire_all()
        self.record("MEASUREMENTS_COMPLETE")


def prepare(task, session_id):
    if (task / "arm.json").exists() or glmrepair.git("status", "--porcelain"):
        raise ValueError("clean_new_candidate_required")
    previous = task.parent / "GLMREPAIR-G1FIX-20260919"
    receipt = json.loads((previous / "final-restoration-receipt.json").read_bytes())
    if receipt.get("status") != "PASS" or receipt.get("host_session_closed") is not True:
        raise ValueError("predecessor_restoration_required")
    accepted = json.loads(glmrepair.schema_body(previous))
    if {k: v for k, v in accepted.items() if k != "messages"} != {k: v for k, v in json.loads(
            body_bytes(fixtures.build_sample(MODEL, 12, SEED, "comparison-prefix"))).items() if k != "messages"}:
        raise ValueError("successful_D_schema_sampling_contract_changed")
    files = runner.source_files()
    armed = {"schema": 1, "scope": "g1-ladder", "campaign": profiles.G1_LADDER_CAMPAIGN,
        "session_id": session_id, "source_commit": glmrepair.git("rev-parse", "HEAD"), "base_commit": BASE,
        "runtime": stage_clock(task), "manifests": [profiles.g1_ladder_manifest(n) for n in (16384, 65536)],
        "trial_plan": profiles.trial_order("g1-ladder"), "accepted_schema_source_sha256": glmrepair.SCHEMA_SHA256,
        "source_files": {p: hashlib.sha256(b).hexdigest() for p, b in files.items()}}
    profiles.validate_arm_scope(armed)
    runner.save(task / "arm.json", armed)
    runner.save(task / "progress.json", {"phase": "AWAITING_ROOT_REVIEW", "completed": {}, "inflight": {}, "errors": []})
    runner.save(task / "status.json", {"phase": "AWAITING_ROOT_REVIEW", "source_commit": armed["source_commit"],
        "session_id": session_id, "clock": armed["runtime"], "live_inference_authorized": False})
    runner.save(task / "arm-receipt.json", {"source_commit": armed["source_commit"], "session_id": session_id,
        "campaign": armed["campaign"], "arm_sha256": fixtures.digest((task / "arm.json").read_bytes())})


def run(task, go_path, session_id, *, restore_only=False):
    armed = json.loads((task / "arm.json").read_bytes())
    go = json.loads(go_path.read_bytes())
    expected = json.loads((task / "arm-receipt.json").read_bytes())
    if (go.get("decision") != "GO" or any(go.get(k) != v for k, v in expected.items())
            or expected["arm_sha256"] != fixtures.digest((task / "arm.json").read_bytes())
            or session_id != armed["session_id"] or glmrepair.git("rev-parse", "HEAD") != armed["source_commit"]
            or glmrepair.git("status", "--porcelain") or os.geteuid() == 0):
        raise ValueError("root_source_session_GO_required")
    profiles.validate_arm_scope(armed)
    if {p: hashlib.sha256(b).hexdigest() for p, b in runner.source_files().items()} != armed["source_files"]:
        raise ValueError("reviewed_source_changed")
    clock = stage_clock(task)
    if clock != armed["runtime"]:
        raise ValueError("immutable_clock_changed")
    if not restore_only and ((task / "execution.json").exists() or time.time() >= clock["deadline_epoch"]):
        raise ValueError("no_rerun_or_budget_reset")
    from runtime.sglang38_file_auth import read_key
    credentials = task.parent / "BENCHRUN-20260919/private-credentials"
    metadata = credentials.lstat()
    if credentials.is_symlink() or not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
        raise ValueError("protected_credential_directory_required")
    key, control_key = read_key(credentials / "inference-key"), read_key(credentials / "control-key")
    if not restore_only:
        checkpoint(task)
        runner.save(task / "execution.json", clock)
    host = glmrepair.DiagnosticSSHHost(armed, stage=not restore_only)
    def transport(url, credential, **kwargs):
        return client.http_transport(url, credential, deadline_epoch=clock["deadline_epoch"], **kwargs)
    job = Ladder(task, armed, host, key, transport_factory=transport)
    error = None
    try:
        try:
            host.call("recover") if restore_only else job.execute()
        except BaseException as exc:
            error = type(exc).__name__
            job.progress["errors"].append({"error_class": error,
                "code": str(exc) if str(exc).startswith(("STOP_", "ROOT_", "SKIP_")) else "HARNESS_FAILURE"})
            job.record()
        status = host.call("status")
        if status["phase"] == "POST_RELEASE_LAN_VERIFICATION_PENDING":
            result = host.call("verify_restoration", receipt=worker_verify.verify(status, key, control_key))
            job.emit({"type": "worker_restoration_verified", "result": result})
            job.record("RESTORED")
        elif status["phase"] != "RESTORED":
            job.record("RECOVERY_REQUIRED")
            raise RuntimeError("restoration_not_verified_preserve_ledger")
    finally:
        terminal = host.call("status")["phase"]
        if terminal in {"RESTORED", "NEW", "FAILED_BEFORE_OWNERSHIP", "FAILED_BEFORE_MUTATION"}:
            host.close()  # stdin close and process wait, then verify local tunnel removal
            ports = {}
            for port in (31002, 31004):
                with socket.socket() as connection:
                    connection.settimeout(1)
                    ports[str(port)] = "CLOSED" if connection.connect_ex(("127.0.0.1", port)) != 0 else "OPEN"
            final = json.loads((task / "status.json").read_bytes())
            runner.save(task / "status.json", {**final, "host_session_closed": True, "local_tunnel_ports": ports})
            if terminal == "RESTORED":
                runner.save(task / "final-restoration-receipt.json", {"phase": terminal,
                    "status": "PASS" if set(ports.values()) == {"CLOSED"} else "FAIL", "epoch": time.time(),
                    "source_commit": armed["source_commit"], "session_id": session_id, "host_session_closed": True,
                    "local_tunnel_ports": ports, "restoration_outside_budget": True,
                    "verification": "canonical finalize plus authenticated worker LAN control/inference"})
    return 1 if error else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "restore"))
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--go", type=Path)
    args = parser.parse_args(argv)
    task = args.task_dir.resolve()
    if args.action == "prepare":
        prepare(task, args.session_id)
        return 0
    if args.go is None:
        parser.error("run/restore requires concrete root --go receipt")
    def terminate(signum, frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, terminate)
    return run(task, args.go, args.session_id, restore_only=args.action == "restore")


if __name__ == "__main__":
    raise SystemExit(main())
