#!/usr/bin/env python3
"""Read saved Worker1 evidence only; emit an allowlisted verification JSON.

Usage: python3 scripts/bench/verify-q1-saved.py --tasks TASKS --output FILE
No network, inference, lifecycle calls, raw responses, or credentials in output.
"""
import argparse
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from benchmark.fixtures import build_sample, serialize_validate  # offline only


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def check(condition, label):
    if not condition:
        raise ValueError(label)  # never include private values


def sse(path):
    raw = path.read_bytes()
    check(raw.rstrip().endswith(b"data: [DONE]"), "incomplete stream")
    events = [json.loads(line[6:]) for line in raw.splitlines()
              if line.startswith(b"data: ") and line != b"data: [DONE]"]
    content = "".join(c.get("delta", {}).get("content") or ""
                      for e in events for c in e.get("choices", []))
    usage = next(e["usage"] for e in reversed(events) if e.get("usage"))
    finish = [c["finish_reason"] for e in events for c in e.get("choices", [])
              if c.get("finish_reason")]
    return content, usage, finish


def coverage(samples, start, end):
    samples = sorted((s for s in samples if start <= s["timestamp_monotonic_s"] <= end),
                     key=lambda s: s["timestamp_monotonic_s"])
    times = [s["timestamp_monotonic_s"] for s in samples]
    covered, right = 0, start
    for t in times:
        left, stop = max(start, t - .5), min(end, t + .5)
        covered += max(0, stop - max(left, right))
        right = max(right, stop)
    return samples, {"sample_count": len(samples),
        "coverage_fraction_estimate": covered / (end - start),
        "maximum_sample_gap_s": max((b-a for a, b in zip(times, times[1:])), default=None),
        "leading_gap_s": times[0]-start if times else end-start,
        "trailing_gap_s": end-times[-1] if times else end-start,
        "collection_overhead_fraction": sum(s["collection_duration_s"] for s in samples)/(end-start)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    q1, q2 = [args.tasks / x for x in ("BENCHQ1-20260919", "BENCHRUN-20260919")]
    q256 = args.tasks / "BENCHQ256-20260919"
    evidence = {}

    def evidence_file(path, expected=None):
        raw = path.read_bytes()
        digest = sha(raw)
        if expected:
            check(digest == expected, "saved file digest mismatch: " + path.name)
        evidence[str(path.relative_to(args.tasks))] = {"sha256": digest, "bytes": len(raw)}
        return read(path) if path.suffix == ".json" else None

    status = evidence_file(q1 / "status.json")
    outcome = evidence_file(q1 / "completion/outcome.json")
    check(status["phase"] == "RESTORED" and not status["campaign_alive"], "Q1 not terminal")
    check(outcome["restoration_finalization_exit"]["exit_code"] == 0, "Q1 not restored")
    index = evidence_file(q1 / "completion/artifact-index.json")
    for item in index.values():
        evidence_file(Path(item["path"]), item["raw_file_sha256"])
    numeric = read(q1 / "completion/numeric-receipts.json")
    host = read(q1 / "completion/private/host-receipts.json")
    for item in list(host["receipts"].values()) + [a[k] for a in host["allocations"] for k in ("load", "allocation")]:
        encoded = (json.dumps(item["value"], sort_keys=True, indent=2) + "\n").encode()
        check(sha(encoded) == item["sha256"], "embedded formal receipt hash mismatch")
    owner = host["receipts"]["owner.json"]["value"]
    lan = host["receipts"]["worker-restoration-verification.json"]["value"]
    challenge = host["receipts"]["restoration-challenge.json"]["value"]
    check(owner["phase"] == "RESTORED" and all(r["state"] == "REMOVED" for r in owner["resources"]), "owner not restored")
    check(lan["nonce"] == challenge["nonce"] and lan["original_sha256"] == sha(canonical(owner["original"])), "LAN challenge binding")
    # Challenge snapshot hashes the fresh restored capture, not original capture.
    check(challenge["selected"] == owner["original"]["manager"]["selected"], "restored selection binding")
    check(lan["checks"]["worker_lan_control_authenticated"] and lan["checks"]["worker_lan_inference_authenticated"], "LAN not authenticated")
    check(all(host[k] for k in ("no_owned_containers", "no_campaign_host", "no_benchmark_listeners")) and not host["canonical_lease_held"], "resources not released")
    checks = evidence_file(q1 / "completion/private/restoration-readonly-checks.json")
    current, original = checks["current_capture"]["value"], owner["original"]
    equal_fields = ["manager", "source", "guards", "storage", "credentials"]
    check(all(current[k] == original[k] for k in equal_fields), "restoration identity mismatch")
    check(all(checks[k]["status"] == "PASS" for k in checks), "restoration checks failed")
    for name, service in original["services"].items():
        for old, new in (("active", "ActiveState"), ("substate", "SubState"), ("enabled", "UnitFileState")):
            check(service[old] == host["services"][name][new], "service state differs")
        check(current["services"][name]["unit_sha256"] == service["unit_sha256"], "service unit changed")
    for name in ("completion/restoration-diagnosis.json", "completion/private/restoration-fresh-process-diagnosis.json", "startup-repair/diagnosis.json", "campaign-q1-exit.json", "campaign-q1-64k-exit.json", "campaign-q1-restore-exit.json", "campaign-q1-finalization-exit.json"):
        evidence_file(q1 / name)
    failed_log = q1 / "final/private/q1-4096-allocation.log"
    failed_log_raw = failed_log.read_bytes()
    check(sha(failed_log_raw) == read(q1 / "startup-repair/diagnosis.json")["log_sha256"], "failed startup log digest")
    check(b"#tokens: 4096, K size: 0.13 GB, V size: 0.13 GB" in failed_log_raw, "failed startup native log")
    evidence[str(failed_log.relative_to(args.tasks))] = {"sha256":sha(failed_log_raw), "bytes":len(failed_log_raw)}
    prior = evidence_file(q1 / "prior-evidence.json")
    for item in prior["paths"].values():
        path = Path(item["path"])
        check(path.stat().st_size == item["bytes"], "prior evidence size changed")
        raw = path.read_bytes()
        check(sha(raw) == item["sha256"], "prior evidence changed")
        evidence[str(path.relative_to(args.tasks))] = {"sha256": sha(raw), "bytes": len(raw)}
    status256 = evidence_file(q256 / "status.json")
    outcome256 = evidence_file(q256 / "completion/outcome.json")
    check(status256["phase"] == "RESTORED" and status256["restoration_state"] == "VERIFIED"
          and not status256["campaign_alive"] and status256["task_complete"], "Q256 not terminal/restored")
    evidence_file(q256 / "exit-code")
    check((q256 / "exit-code").read_text().strip() == "0", "Q256 CLI not terminal success")
    check(outcome256["measurement_process_exit"]["phase"] == "RESTORED"
          and outcome256["measurement_process_exit"]["exit_code"] == 1, "Q256 immutable measurement exit changed")
    for item in evidence_file(q256 / "completion/artifact-index.json").values():
        evidence_file(Path(item["path"]), item["raw_file_sha256"])
    evidence_file(q256 / "completion/replay-semantic.py")
    host256, numeric256 = [read(q256 / "completion" / name) for name in ("private/host-receipts.json", "numeric-receipts.json")]
    for item in list(host256["receipts"].values()) + [a[k] for a in host256["allocations"] for k in ("load", "allocation")]:
        check(sha((json.dumps(item["value"], sort_keys=True, indent=2) + "\n").encode()) == item["sha256"], "Q256 embedded receipt hash")
    owner256 = host256["receipts"]["owner.json"]["value"]
    lan256 = host256["receipts"]["worker-restoration-verification.json"]["value"]
    challenge256 = host256["receipts"]["restoration-challenge.json"]["value"]
    check(owner256["phase"] == "RESTORED" and not owner256["errors"]
          and all(r["state"] == "REMOVED" for r in owner256["resources"]), "Q256 owner not restored")
    check(lan256["nonce"] == challenge256["nonce"] and lan256["original_sha256"] == sha(canonical(owner256["original"])), "Q256 LAN binding")
    check(lan256["checks"]["worker_lan_control_authenticated"] and lan256["checks"]["worker_lan_inference_authenticated"], "Q256 LAN authentication")
    check(host256["receipts"]["owner.json"]["sha256"] == outcome256["owner_receipt_sha256"]
          and host256["receipts"]["worker-restoration-verification.json"]["sha256"] == outcome256["authenticated_worker_lan_receipt"]["sha256"], "Q256 outcome receipts")
    check(all(host256[k] for k in ("no_owned_containers", "no_campaign_host", "no_benchmark_listeners")) and not host256["canonical_lease_held"], "Q256 resources not released")
    for key in ("selected", "desired", "boot_policy"):
        check(owner256["original"]["manager"][key] == original["manager"][key], "Q256 original intent differs")
    for name, service in owner256["original"]["services"].items():
        for old, new in (("active", "ActiveState"), ("substate", "SubState"), ("enabled", "UnitFileState")):
            check(service[old] == host256["services"][name][new], "Q256 service state differs")
    for item in evidence_file(q256 / "prior-evidence.json")["paths"].values():
        path = Path(item["path"])
        evidence_file(path, item["sha256"])
        check(path.stat().st_size == item["bytes"], "Q256 prior evidence size")
    check(outcome256["first_epoch"] == outcome["first_epoch"] and outcome256["deadline"] == outcome["deadline"], "Q256 budget reset")
    check((q256/"campaign-arm/execution.json").read_bytes() == (q1/"campaign-arm/execution.json").read_bytes(), "Q256 execution changed")
    arms = {label: evidence_file(task / "campaign-arm/arm.json") for label, task in (("Q1", q1), ("Q2", q2), ("Q256", q256))}
    arm_hashes = {k: sha(canonical(v)) for k, v in arms.items()}
    check(arm_hashes["Q1"] == outcome["canonical_arm_sha256"], "Q1 arm changed")
    check(arm_hashes["Q256"] == outcome256["canonical_arm_sha256"] == "328830179bfcd4488a1f7ecf23083126b472ef41d7f883a1174f177f65497af1", "Q256 arm differs")
    check(outcome256["source_head"] == "b750bb37dd3107cf5b1e7aaabe6237ebc435085c", "Q256 source differs")
    for name, expected in arms["Q256"]["source_files"].items():
        check(sha((q256/"repo"/name).read_bytes()) == expected, "Q256 accepted source bytes differ")
    manifest64, manifest256 = arms["Q1"]["manifests"][-1], arms["Q256"]["manifests"][0]
    for key in ("model", "image", "gpu_uuids", "guest_cpu_count", "guest_cpuset"):
        check(manifest64[key] == manifest256[key], "Q256 placement/model policy changed")
    check(["262144" if x == "65536" else x for x in manifest64["native_argv"]] == manifest256["native_argv"], "Q256 native policy changed beyond capacity")
    for name, expected in arms["Q1"]["source_files"].items():
        check(sha((q1/"repo"/name).read_bytes()) == expected, "historical Q1 source differs: " + name)
    go = evidence_file(q1 / "GO.json")
    review = evidence_file(q1 / "q1-64k-continuation/review.json")
    package = evidence_file(q1 / "q1-64k-continuation/update-package.json", outcome["update_package_sha256"])
    for name, expected in package.items():
        evidence_file(q1 / "q1-64k-continuation" / name, expected) if name.endswith(".json") else check(sha((q1 / "q1-64k-continuation" / name).read_bytes()) == expected, "update bytes differ")
    check(go["authorized"] and go["source_head"] == review["source_head"] == outcome["source_head"], "continuation source binding")
    check(go["arm_sha256"] == review["candidate_arm_sha256"] == arm_hashes["Q1"], "continuation arm binding")
    check(go["first_epoch"] == prior["first_epoch"] == outcome["first_epoch"] and go["deadline"] == prior["deadline"] == outcome["deadline"], "continuation budget binding")
    execution = evidence_file(q1 / "campaign-arm/execution.json")
    for name in ("samples.jsonl", "warmups.jsonl"):
        raw = (q1 / "campaign-arm" / name).read_bytes()
        evidence[f"BENCHQ1-20260919/campaign-arm/{name}"] = {"sha256": sha(raw), "bytes": len(raw)}
    check((q1/"campaign-arm/execution.json").read_bytes() == (q2/"campaign-arm/execution.json").read_bytes(), "budget reset")
    check(outcome["deadline"] - outcome["first_epoch"] == 21600, "budget differs")
    for name, receipt in outcome["journal_prefix_proof"].items():
        check(sha((q1/name).read_bytes()[:receipt["preserved_bytes"]]) == receipt["sha256"], "journal prefix changed")

    all_rows, fixtures, trials, parsed = {}, {}, [], {}
    for label, task in (("Q1", q1), ("Q2", q2), ("Q256", q256)):
        path = task / "campaign-arm/results.jsonl"
        raw = path.read_bytes()
        evidence[str(path.relative_to(args.tasks))] = {"sha256": sha(raw), "bytes": len(raw)}
        rows = [json.loads(s) for s in raw.splitlines()]
        if label == "Q256":
            check(sum(r["type"] == "trial" for r in rows) == 1 and sum(r["type"] == "warm_idle" for r in rows) == 1, "Q256 repeated case/warmup")
        all_rows[label] = rows
        fixtures[label] = evidence_file(task / "campaign-arm/private/fixtures.json")
        for fixture in fixtures[label].values():
            serialize_validate(fixture)
        telemetry = [r["sample"] for r in rows if r["type"] == "telemetry"]
        for r in (r for r in rows if r["type"] == "trial"):
            if r["kind"] == "tool":
                continue  # separately verify immutable diagnosis below; never execute a tool
            count, sample = r["count"], r["sample"]
            check(sample["response_retained_complete"] and sample["retry_attempts"] == 0, "incomplete or retried measurement")
            raw_request = (task / "campaign-arm/private" / (r["id"] + ".request.json")).read_bytes()
            response = task / "campaign-arm/private" / (r["id"] + ".response.sse")
            check(sha(raw_request) == sample["request_sha256"] == count["body_sha256"], "request hash")
            check(sha(response.read_bytes()) == sample["response_sha256"], "response hash")
            body = json.loads(raw_request)
            frozen = fixtures[label][f'bench-qwen3.8-27b-{r["capacity"]}-{r["kind"]}']
            nonce = body["messages"][0]["content"].splitlines()[0].removeprefix("trial-prefix=")
            regenerated = build_sample(body["model"], frozen["records"], frozen["seed"], nonce, kind=r["kind"], output_cap=count["output_cap"])
            check(serialize_validate(regenerated) == raw_request, "frozen fixture request differs")
            check(regenerated["fixture_sha256"] == r["fixture_sha256"] == frozen["fixture_sha256"], "fixture hash")
            content, usage, finish = sse(response)
            parsed[r["id"]] = content
            check(usage["prompt_tokens"] == count["input_tokens"] == sample["counters"]["prompt_tokens"], "prompt usage")
            check(usage["completion_tokens"] == sample["counters"]["completion_tokens"] and finish == ["stop"], "output usage/finish")
            if r["status"] == "PASS":
                answer = json.loads(content)
                if r["kind"] == "generation":
                    check(bool(answer.pop("commentary")), "empty commentary")
                check(answer == frozen["scorer"]["retrieval"], "saved PASS answer differs")
            t = sample["client_timing"]
            first, last = t["ttft_any_output_seconds"], t["last_output_seconds"]
            start, end = sample["request_started_monotonic_s"], sample["request_ended_monotonic_s"]
            window, cov = coverage(telemetry, start, end)
            for key, value in cov.items():
                check(value == r["telemetry"][key] if value is None else math.isclose(value, r["telemetry"][key], abs_tol=1e-8), "coverage recalculation")
            gpu = {}
            for uuid in {g["uuid"] for s in window for g in s["gpus"]}:
                gs = [g for s in window for g in s["gpus"] if g["uuid"] == uuid]
                gpu[uuid] = {"sampled_peak_used_bytes": max(g["used_bytes"] for g in gs), "sampled_min_free_bytes": min(g["free_bytes"] for g in gs)}
            request_groups = {cid: {k: max(s["cgroups"][cid][k] for s in window if cid in s["cgroups"])
                for k in ("current_bytes", "anon_bytes", "file_bytes", "kernel_bytes", "swap_bytes")}
                for cid in {cid for s in window for cid in s["cgroups"]}}
            trials.append({"id": r["id"], "status": r["status"], "configured_capacity": r["capacity"],
                "input_tokens": count["input_tokens"], "completion_tokens": usage["completion_tokens"], "output_cap": count["output_cap"],
                "ttft_s": first, "last_output_s": last, "output_delivery_tokens_s": (usage["completion_tokens"]-1)/(last-first),
                "effective_input_tokens_per_client_ttft_s": count["input_tokens"]/first,
                "request_latency_s": end-start, "trial_orchestration_s": r["client_total_seconds"],
                "finish_reason": finish[0], "fixture_sha256": r["fixture_sha256"], "records": frozen["records"],
                "template_sha256": count["template_sha256"], "token_ids_sha256": count["token_ids_sha256"],
                "row_canonical_sha256": sha(canonical(r)), "request_sha256": sample["request_sha256"], "response_sha256": sample["response_sha256"],
                "telemetry": cov, "request_gpu": gpu, "request_cgroup_sampled_peaks": request_groups,
                "request_min_host_available_bytes": min(s["host"]["available_bytes"] for s in window),
                "native_prefill_decode_cached_evaluated_counters": None})
    check(sha((q1/"campaign-arm/results.jsonl").read_bytes()) == numeric["provenance"]["results_file_sha256"], "numeric results binding")
    check(all(fixtures["Q1"][k] == v for k,v in fixtures["Q2"].items()), "original frozen entries changed")
    check(all(fixtures["Q256"][k] == v for k,v in fixtures["Q1"].items()), "Q256 changed prior frozen entries")
    check(sha((q256/"campaign-arm/results.jsonl").read_bytes()) == numeric256["provenance"]["results_file_sha256"], "Q256 numeric results binding")
    semantic = evidence_file(q1 / "generation-failure/semantic-disposition.json", outcome["semantic_disposition_file_sha256"])
    gen = next(r for r in trials if r["id"] == "Q1-16384-generation")
    check(gen["status"] == "HARNESS_FAILURE" and gen["row_canonical_sha256"] == semantic["original_row_canonical_sha256"], "generation row relabeled")
    content = parsed[gen["id"]]
    check(content.startswith("```json\n") and content.endswith("\n```"), "expected one JSON fence")
    normalized = content[len("```json\n"):-len("\n```")]
    check(content == semantic["original_content"] and normalized == semantic["normalized_content"], "semantic normalization differs")
    for key, value in (("raw_response_sha256", gen["response_sha256"]), ("original_content_sha256", sha(content.encode())), ("normalized_content_sha256", sha(normalized.encode()))):
        check(semantic[key] == value, "semantic hash differs")
    answer = json.loads(normalized)
    check(bool(answer.pop("commentary")) and answer == fixtures["Q1"]["bench-qwen3.8-27b-16384-generation"]["scorer"]["retrieval"], "semantic answer differs")
    check(arms["Q1"]["q1_generation_framing"]["failed_row_sha256"] == gen["row_canonical_sha256"] and arms["Q1"]["q1_generation_framing"]["semantic_disposition_sha256"] == outcome["semantic_disposition_file_sha256"], "arm semantic binding")
    semantic256 = evidence_file(q256 / "completion/semantic-disposition.json", "f5d247b7ea6b7150cfa2ca8acbbc8849a2abee030f7b4e170b7f2a5b5a6ccd31")
    trial256 = next(r for r in trials if r["id"] == "Q1-262144-retrieval")
    check(trial256["status"] == "HARNESS_FAILURE" and trial256["row_canonical_sha256"] == semantic256["original_row_canonical_sha256"] == "0e28306969447642459452e17fcb7395dbdd1c0f8387d6ce25d66e49b176664f", "Q256 strict row changed")
    check(trial256["response_sha256"] == semantic256["raw_response_sha256"] == "c58d5e6db1e05f1fc3f9d0ef25a937a7054d18f9c8bfcbf2da196fa54b55c61d", "Q256 response changed")
    content256 = parsed[trial256["id"]]
    check(content256.startswith("```json\n") and content256.endswith("\n```"), "Q256 one enclosing fence")
    normalized256 = content256[len("```json\n"):-len("\n```")]
    check("```" not in normalized256 and content256 == semantic256["original_content"] and normalized256 == semantic256["normalized_content"], "Q256 normalization differs")
    check(json.loads(normalized256) == fixtures["Q256"]["bench-qwen3.8-27b-262144-retrieval"]["scorer"]["retrieval"], "Q256 exact semantic answer")
    check(sha(content256.encode()) == semantic256["original_content_sha256"] and sha(normalized256.encode()) == semantic256["normalized_content_sha256"], "Q256 content hashes")
    check(semantic256["normalized_score"]["status"] == "PASS" and semantic256["original_score"]["status"] == "HARNESS_FAILURE", "Q256 disposition status")
    evidence_file(q256 / "completion/semantic-authority.md", semantic256["authority_sha256"])
    for name, expected in semantic256["immutable_state_sha256"].items():
        evidence_file(q256 / "campaign-arm" / name, expected)
    diag = read(q2 / "tool-failure/diagnosis.json")
    for group in (diag["failed_tool_evidence"], *[x["raw"] for x in diag["successful_cases_preserved"].values()]):
        for name, pin in group.items():
            check(sha((q2/name).read_bytes()) == pin["sha256"], "Q2 evidence differs")
    tool_row = next(r for r in all_rows["Q2"] if r.get("id") == "Q2-16384-tool" and r["type"] == "trial")
    check(sha(canonical(tool_row)) == diag["failed_record_sha256"] and tool_row["status"] == "HARNESS_FAILURE", "Q2 tool row changed")
    tool_content, _, _ = sse(q2/"campaign-arm/private/Q2-16384-tool-continuation.response.sse")
    check("<function=write_file>" in tool_content and all(k not in tool_content for k in ("START", "MIDDLE", "END")), "Q2 diagnosed contract differs")
    for row in (r for r in trials if r["id"].startswith("Q2")):
        check(row["row_canonical_sha256"] == diag["successful_cases_preserved"][row["id"]]["trial_record_sha256"], "Q2 PASS row changed")

    memory = []
    used_uuid = arms["Q1"]["manifests"][0]["gpu_uuids"][0]
    q1samples = [r for label in ("Q1", "Q256") for r in all_rows[label] if r["type"] == "telemetry"]
    allocation_sets = [(a, n, "Q1") for a, n in zip(host["allocations"], numeric["allocations"])]
    allocation_sets += [(a, n, "Q256") for a, n in zip(host256["allocations"], numeric256["allocations"])]
    for allocation, saved, label in allocation_sets:
        cap, cid = allocation["capacity"], allocation["container_id"]
        value = allocation["allocation"]["value"]
        manifest = allocation["load"]["value"]["manifest"]
        check(value["observed"]["native_argv"] == manifest["native_argv"], "observed native argv differs")
        check(value["observed"]["model"] == manifest["model"] and value["observed"]["image_ref"] == manifest["image"], "observed model/runtime differs")
        check(value["observed"]["cuda_uuid_order"] == value["observed"]["device_request_uuids"] == manifest["gpu_uuids"], "GPU placement differs")
        check(value["parsed"] == saved["native_allocation"], "numeric allocation differs")
        check(all(value["parsed"][k] == cap for k in ("actual_pool_tokens", "configured_context", "configured_pool_tokens")), "pool differs")
        samples = [r["sample"] for r in q1samples if r["container"] == cid]
        gs = [g for s in samples for g in s["gpus"] if g["uuid"] == used_uuid]
        peak, free = max(g["used_bytes"] for g in gs), min(g["free_bytes"] for g in gs)
        check(peak == saved["lifecycle_gpu_sampled_peaks"][used_uuid]["sampled_peak_used_bytes"], "numeric GPU peak")
        load = next(r for r in all_rows[label] if r["type"] == "load" and r["capacity"] == cap)
        warm = next(r for r in all_rows[label] if r["type"] == "warm_idle" and r["container"] == cid)
        check(load["allocation"]["status"] == "ALLOCATION_PROOF_ACCEPTED" and warm["warmup_timing"] == "discarded"
              and warm["prefill_proof"]["prefill_tokens"] >= 2048, "allocation/warmup proof failed")
        load_samples = [s for s in samples if s["host_timestamp_monotonic_s"] <= load["readiness"]["telemetry"]["timestamp_monotonic_s"]]
        for key, point in (("readiness", load["readiness"]), ("warm_idle", warm["checkpoint"])):
            check(point["pss_bytes"] == saved["checkpoints"][key]["quiescent_process_tree_pss_bytes"], "numeric PSS")
        def group_peaks(series):
            return {k: max((s["cgroups"][cid][k] for s in series if s["cgroups"][cid].get(k) is not None), default=None)
                    for k in ("current_bytes", "peak_since_cgroup_creation_bytes", "anon_bytes", "file_bytes", "kernel_bytes", "swap_bytes")}
        warm_g = next(g for g in warm["checkpoint"]["telemetry"]["gpus"] if g["uuid"] == used_uuid)
        memory.append({"capacity": cap, "container_id": cid, "allocation_receipt_sha256": allocation["allocation"]["sha256"],
            "upstream_raw_log_sha256": allocation["raw_log_sha256"], "raw_successful_load_log_locally_available": False,
            "native_allocation": value["parsed"], "observed_native_argv_sha256": sha(canonical(value["observed"]["native_argv"])),
            "sample_count": len(samples), "sample_span_s": samples[-1]["timestamp_monotonic_s"]-samples[0]["timestamp_monotonic_s"],
            "load_before_readiness_sample_count": len(load_samples),
            "load_before_readiness_gpu_sampled_peak_used_bytes": max(g["used_bytes"] for s in load_samples for g in s["gpus"] if g["uuid"] == used_uuid),
            "gpu_sampled_peak_used_bytes": peak, "gpu_sampled_min_free_bytes": free,
            "gpu_warm_used_bytes": warm_g["used_bytes"], "gpu_warm_free_bytes": warm_g["free_bytes"], "gpu_readiness_used_bytes": next(g["used_bytes"] for g in load["readiness"]["telemetry"]["gpus"] if g["uuid"] == used_uuid),
            "fixed_used_minus_hypothesized_kv_bytes": peak-cap*65536, "load_client_s": load["client_load_seconds"],
            "readiness_pss_bytes": load["readiness"]["pss_bytes"], "warm_pss_bytes": warm["checkpoint"]["pss_bytes"],
            "warm_cgroup": warm["checkpoint"]["telemetry"]["cgroups"][cid], "lifecycle_cgroup_peaks": group_peaks(samples),
            "load_cgroup_sampled_peaks": group_peaks(load_samples),
            "warm_required_host_demand_bytes": warm["checkpoint"]["telemetry"]["required_host_demand"].get("required_bytes"),
            "warmup_native_input_tokens": warm["count"]["input_tokens"], "warmup_prefill_proof": warm["prefill_proof"]["source"]})
    q2memory = []
    for warm in (r for r in all_rows["Q2"] if r["type"] == "warm_idle"):
        cid, point = warm["container"], warm["checkpoint"]
        samples = [r["sample"] for r in all_rows["Q2"] if r["type"] == "telemetry" and r["container"] == cid]
        load = next(r for r in all_rows["Q2"] if r["type"] == "load" and r["readiness"]["container_id"] == cid)
        q2memory.append({"capacity": warm["count"]["configured_capacity"], "container_id": cid,
            "load_client_s": load["client_load_seconds"], "sample_count": len(samples),
            "warm_pss_bytes": point["pss_bytes"], "warm_cgroup_current_bytes": point["telemetry"]["cgroups"][cid]["current_bytes"],
            "gpus": {g["uuid"]:{"warm_used_bytes":g["used_bytes"],
                "sampled_peak_used_bytes":max(v["used_bytes"] for s in samples for v in s["gpus"] if v["uuid"] == g["uuid"]),
                "sampled_min_free_bytes":min(v["free_bytes"] for s in samples for v in s["gpus"] if v["uuid"] == g["uuid"])} for g in point["telemetry"]["gpus"]},
            "native_numeric_pool_K_V_and_required_demand":None})
    demands = [r for r in q1samples if isinstance(r["sample"]["required_host_demand"].get("required_bytes"), int)]
    for r in demands:
        d = r["sample"]["required_host_demand"]
        check(d["required_bytes"] == sum(d[k] for k in ("anon_bytes", "kernel_bytes", "required_file_backed_bytes", "workspace_extra_bytes")), "host demand sum")
    peak_row = max(demands, key=lambda r: r["sample"]["required_host_demand"]["required_bytes"])
    peak_demand = peak_row["sample"]["required_host_demand"]
    at64, last = memory[-2:]
    totals = {g["total_bytes"] for r in q1samples for g in r["sample"]["gpus"] if g["uuid"] == used_uuid}
    check(totals == {102641958912} and at64["gpu_sampled_peak_used_bytes"] == 37476106240 and at64["gpu_sampled_min_free_bytes"] == 64497909760, "64K memory values differ")
    total = totals.pop()
    used, free = [trial256["request_gpu"][used_uuid][k] for k in ("sampled_peak_used_bytes", "sampled_min_free_bytes")]
    check(any((g["total_bytes"],g["used_bytes"],g["free_bytes"]) == (total,used,free)
              for r in q1samples if r["container"] == last["container_id"]
              for g in r["sample"]["gpus"] if g["uuid"] == used_uuid), "256K values must share a saved sample")
    check((used, free) == (50400854016, 51573161984), "256K request memory differs")
    gap, kv, base, reserve = total-used-free, 65536, 262144, Fraction(total, 10)
    observed_slope = Fraction(last["gpu_warm_used_bytes"]-at64["gpu_warm_used_bytes"], base-at64["capacity"])
    overhead_growth = last["gpu_warm_used_bytes"]-at64["gpu_warm_used_bytes"]-(base-at64["capacity"])*kv
    projections = []
    anchors = {"request_peak":(used,free), "warm":(last["gpu_warm_used_bytes"],last["gpu_warm_free_bytes"]),
               "lifecycle_peak":(last["gpu_sampled_peak_used_bytes"],last["gpu_sampled_min_free_bytes"])}
    for anchor, (u,f) in anchors.items():
        for basis, slope in (("observed_64K_to_256K", observed_slope), ("cache_only", Fraction(kv))):
            check(total-u-f == gap == 667942912, "device gap differs across anchors")
            projections.append({"anchor":anchor,"slope_basis":basis,"anchor_used_bytes":u,"anchor_free_bytes":f,
                "slope_bytes_per_token":float(slope),"projected_512K_used_bytes":float(u+base*slope),
                "projected_512K_free_bytes":float(f-base*slope),"physical_max_tokens":base+math.floor((f-reserve)/slope),
                "physical_max_with_extra_4GiB_workspace_tokens":base+math.floor((f-reserve-4*2**30)/slope),
                "policy_0_8_occupancy_proxy_max_tokens":base+math.floor((f-Fraction(total,5))/slope),"tested":False})
    native_projection = numeric256["physical_memory_projection"]
    warm_observed = next(p for p in projections if p["anchor"] == "warm" and p["slope_basis"] == "observed_64K_to_256K")
    check(warm_observed["physical_max_tokens"] == native_projection["approximate_physical_maximum_tokens"]
          and math.isclose(warm_observed["projected_512K_used_bytes"],native_projection["projected_524288_warm_used_bytes"]), "native handoff slope reconciliation")
    pairs, variability = [], {}
    byid = {r["id"]: r for r in trials}
    for suffix in ("4096-retrieval", "16384-retrieval", "16384-anchor", "16384-generation"):
        a,b = byid["Q1-"+suffix], byid["Q2-"+suffix]
        check(a["fixture_sha256"] == b["fixture_sha256"] and a["template_sha256"] == b["template_sha256"], "unmatched fixture/template")
        pairs.append({"case": suffix, "fixture_sha256": a["fixture_sha256"], "records": a["records"],
            "Q1_vs_Q2_ttft_ratio": a["ttft_s"]/b["ttft_s"], "Q1_vs_Q2_output_delivery_ratio": a["output_delivery_tokens_s"]/b["output_delivery_tokens_s"],
            "Q1_minus_Q2_output_tokens": a["completion_tokens"]-b["completion_tokens"]})
    for label in ("Q1", "Q2"):
        a,b = byid[label+"-16384-retrieval"],byid[label+"-16384-anchor"]
        variability[label] = {k:{"min": min(a[k],b[k]), "max": max(a[k],b[k]), "range_over_mean_percent": 100*abs(a[k]-b[k])/((a[k]+b[k])/2)} for k in ("ttft_s", "output_delivery_tokens_s", "request_latency_s")}
    runtime = read(ROOT/"configs/runtimes/sglang-qwen38-0.5.19.json")
    identities = {label:{"arm_canonical_sha256": arm_hashes[label], **{k:m[k] for k in ("model", "image", "expected_image_ids", "gpu_uuids", "guest_cpu_count", "guest_cpuset")}}
                  for label in ("Q1","Q2","Q256") for m in [next(x for x in arms[label]["manifests"] if x["placement"] == ("Q1" if label == "Q256" else label))]}
    result = {"schema": 1, "task": "BENCHQ1VERIFY", "session_id": (ROOT.parent/"session-id").read_text().strip(),
        "scope": "Worker1 saved evidence only; no VM contact or new measurements",
        "reviewed_source_head": outcome["source_head"], "Q1_initial_successful_source_head": review["base_source_head"], "Q2_source_head": prior["source_head"],
        "Q256_accepted_source_head":outcome256["source_head"], "interim_report_commit":"80e50f0535428c4be99951ad887b59079adb5ae3",
        "report_publication_base":"b750bb37dd3107cf5b1e7aaabe6237ebc435085c",
        "identities": identities, "runtime": {k:runtime[k] for k in ("id","source_commit","image_ref","image_id")},
        "common_policy": {"weights":"FP8", "KV":"BF16", "radix_cache":False, "mem_fraction_static":0.8, "yarn_factor":4, "native_context":262144},
        "restoration":{"status":"VERIFIED_FROM_SAVED_RECEIPTS","task":"BENCHQ256","restored_measurement_end_utc":outcome256["measurement_process_exit"]["ended_utc"],
            "CLI_exit":0,"measurement_process_exit":1,"automatic_restoration_passed":True,"recovery_retry":False,
            "selected":owner256["original"]["manager"]["selected"],"desired":owner256["original"]["manager"]["desired"],"boot_policy":owner256["original"]["manager"]["boot_policy"],
            "services":host256["services"],"canonical_lease_held":False,"owned_resources_absent":True,
            "proof_scope":"formal RESTORED owner plus original-snapshot and nonce-bound authenticated Worker1 LAN receipt; no new live check",
            "owner_sha256":outcome256["owner_receipt_sha256"],"LAN_receipt_sha256":outcome256["authenticated_worker_lan_receipt"]["sha256"]},
        "prior_Q1_restoration": {"status":"VERIFIED_FROM_SAVED_RECEIPTS", "terminal_time_utc": outcome["restoration_finalization_exit"]["ended_utc"],
            "automatic_restore_exit":1, "fresh_process_restore_exit":1, "finalization_exit":0, "production_restart_during_finalization":False,
            "selected":original["manager"]["selected"], "desired":original["manager"]["desired"], "boot_policy":original["manager"]["boot_policy"],
            "unchanged_fields":equal_fields, "services":host["services"], "canonical_lease_held":False, "owned_resources_absent":True,
            "owner_sha256":host["receipts"]["owner.json"]["sha256"], "LAN_receipt_sha256":host["receipts"]["worker-restoration-verification.json"]["sha256"]},
        "budget":{"first_epoch":outcome["first_epoch"],"deadline":outcome["deadline"],"seconds":21600,"execution_unchanged":True},
        "formulas":{"output_delivery_tokens_s":"(completion_tokens-1)/(last_output_s-ttft_s)","effective_input_tokens_per_client_ttft_s":"input_tokens/ttft_s; NOT native prefill", "request_latency_s":"transport drain minus dispatch; separate from trial orchestration", "GPU_used_projection":"anchor_used+(context-262144)*specified_slope", "GPU_free_projection":"anchor_direct_free-(context-262144)*specified_slope", "physical_max":"262144+floor((anchor_direct_free-0.1*actual_total-extra_workspace)/specified_slope)", "policy_occupancy_proxy":"262144+floor((anchor_direct_free-0.2*actual_total)/specified_slope); not verified SGLang allocator formula", "host_required":"anon+kernel+retained_file+workspace_extra; no PSS/RSS addition", "GiB":"bytes/1073741824", "GB":"bytes/1000000000"},
        "trials":trials,"matched_pairs":pairs,"anchor_variability_two_samples_only":variability,
        "generation_disposition":{k:semantic[k] for k in ("case","recorded_status","normalization","semantic_status","original_row_canonical_sha256","raw_response_sha256","original_content_sha256","normalized_content_sha256")},
        "Q256_disposition":{k:semantic256[k] for k in ("case","recorded_status","normalization","semantic_status","original_row_canonical_sha256","raw_response_sha256","original_content_sha256","normalized_content_sha256","authority_sha256")},
        "Q2_tool":{"immutable_status":"HARNESS_FAILURE","diagnosis":"genuine output-contract failure: literal write_file markup after read_file, not a structured API tool call; missing retrieval answers", "write_file_executed":False,"row_canonical_sha256":diag["failed_record_sha256"], "continuation_response_sha256":diag["failed_tool_evidence"]["campaign-arm/private/Q2-16384-tool-continuation.response.sse"]["sha256"], "retested":False},
        "memory":memory, "Q2_memory":q2memory,
        "observed_GPU_used_slopes_bytes_per_token":[{"from":a["capacity"],"to":b["capacity"],"scope":"lifecycle_peak","slope":(b["gpu_sampled_peak_used_bytes"]-a["gpu_sampled_peak_used_bytes"])/(b["capacity"]-a["capacity"])} for a,b in zip(memory[:3],memory[1:3])],
        "observed_GPU_warm_slopes_bytes_per_token":[{"from":a["capacity"],"to":b["capacity"],"slope":(b["gpu_warm_used_bytes"]-a["gpu_warm_used_bytes"])/(b["capacity"]-a["capacity"])} for a,b in zip(memory,memory[1:])],
        "host_load_peak":{"container_id":peak_row["container"],"row_canonical_sha256":sha(canonical(peak_row)),"belongs_to_failed_initial_4K_startup":True, **{k:peak_demand[k] for k in ("required_bytes","anon_bytes","kernel_bytes","required_file_backed_bytes","reclaimable_file_bytes","load_phase_sample_count","load_phase_observed_span_s")}},
        "GPU_projection":{"primary_anchor":"request_peak","total_bytes":total,"request_used_at_256K_bytes":used,"request_free_at_256K_bytes":free,"unavailable_reserved_gap_bytes":gap,"BF16_KV_hypothesis_bytes_per_token":kv,"observed_64K_to_256K_slope_bytes_per_token":float(observed_slope),"64K_to_256K_growth_beyond_cache_only_bytes":overhead_growth,"reserve_fraction":0.1,"reserve_bytes":float(reserve),"historical_live_gate_reserve_bytes":16*2**30,"policy_proxy":"0.8*total occupancy including device gap; NOT a verified SGLang allocator formula or accepted maximum", "estimates":projections},
        "limitations":["No tested Q1 capacity above 262144; actual 261525 input/89 output; strict HARNESS_FAILURE plus separate root-approved semantic PASS", "Q2 64K/256K absent; no code-analysis coverage; no Q1 tool retest", "Single GPU benchmarked, not deployed; original Qwen 1M TP2 production restored; no simultaneous GLM/Qwen feasibility", "Native prefill/decode timing, evaluated/cached counters and standalone workspace are unavailable", "Successful-load raw native logs remain remote hash references; local numeric receipts rehashed, not raw-log reparsed", "Native GB labels retained without exact byte conversion", "13.288GB sampled load peak belongs to failed initial container; cold-load and whole-VM RAM requirement unknown", "16K/64K/256K required-host-demand unavailable; reclaimable file cache and shared process RSS are not unique required RAM", "Telemetry is sampled, with gaps; lifetime cgroup peaks are not request peaks; client event timing includes transport/chunk overhead", "CPU allocation and source revisions differ; no causal GPU-only speed claim", "512K and all maximum projections untested for allocation/speed/quality; observed slope, cache-only slope and policy proxy are separate"],
        "evidence_files":evidence}
    args.output.write_text(json.dumps(result,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n")
    print(json.dumps({"verification":"PASS", "rows":len(trials), "evidence_files":len(evidence), "output":str(args.output)}))


if __name__ == "__main__":
    main()
