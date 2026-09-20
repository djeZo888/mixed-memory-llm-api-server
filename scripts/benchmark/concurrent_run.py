"""Closed two-round G1/Q1 experiment; preparation is offline, RUN needs fresh GO.

Reuse the benchmark owner, guarded staging, native counters and drain-first client.
No production installation, model tuning, old campaign resume or profiling.
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
import threading
import time

from agent import protocol
from . import accounting, client, fixtures, g1_ladder, glmrepair, profiles, runner, worker_verify
from .warmup import prefill_proof

SCOPE = "concurrent-g1q1"
POLICY = {"budget_seconds": 5400, "request_max_seconds": 7200,
          "clock_includes_preparation": True, "clock_starts": "RUN_DISPATCH",
          "restoration_outside_budget": True, "includes_load_warmup_fitting": True, "excludes_source_prep": True}
SUCCESS = {"PASS", "TIMING_ONLY"}


def bind_runtime(armed, go, session_id, now):
    """Root stamps a fresh RUN clock; PREP never invents an execution epoch."""
    value = go.get("runtime", {})
    start, end = value.get("start_epoch"), value.get("deadline_epoch")
    if (armed.get("runtime_policy") != POLICY or any(value.get(k) != v for k, v in POLICY.items())
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end))
            or not 0 < start <= now < end or end != start + 5400
            or go.get("run_session_id") != session_id or not session_id
            or session_id == armed.get("session_id")):
        raise ValueError("fresh_RUN_dispatch_clock_and_session_required")
    return copy.deepcopy(value)


class PeerFinished(Exception):
    """A queued Qwen filler was not admitted after GLM drained."""


def drain_threads(threads):
    """A supervisor exception is re-raised only after every started lane exits."""
    interrupted = None
    for thread in threads:
        while thread.is_alive():
            try:
                thread.join()
            except BaseException as exc:
                if interrupted is None:
                    interrupted = exc
    if interrupted is not None:
        raise interrupted


def execute_round(glm_job, qwen_jobs, invoke, *, clock=time.monotonic, stop_event=None):
    """One barrier-started GLM lane and a bounded serial Qwen lane; drain both."""
    if len(qwen_jobs) not in (3, 8):
        raise ValueError("closed_round_job_count")
    barrier, done, failed = threading.Barrier(2), threading.Event(), threading.Event()
    result = {"glm": None, "qwen": [], "errors": [], "started_monotonic_s": clock()}
    mutex = threading.Lock()
    def call(job):
        try:
            row = invoke(job)
            if row.get("status") not in SUCCESS:
                failed.set()
            return row
        except PeerFinished:
            return {"status": "NOT_ADMITTED", "id": job.get("id")}
        except BaseException as exc:
            failed.set()
            with mutex:
                result["errors"].append({"error_class": type(exc).__name__})
            return {"status": "HARNESS_FAILURE", "id": job.get("id")}
    def glm_lane():
        barrier.wait()
        try:
            result["glm"] = call({**glm_job, "drained_event": done})
        finally:
            done.set()
    def qwen_lane():
        barrier.wait()
        for index, job in enumerate(qwen_jobs):
            # The first pair is mandatory even if the peer finishes immediately.
            if index and (done.is_set() or failed.is_set() or (stop_event is not None and stop_event.is_set())):
                break
            row = call({**job, "stop_admission": done} if index else job)
            if row.get("status") == "NOT_ADMITTED":
                break
            result["qwen"].append(row)
    threads = [threading.Thread(target=glm_lane), threading.Thread(target=qwen_lane)]
    try:
        for thread in threads:
            thread.start()
    except BaseException:
        barrier.abort()
        drain_threads(threads)
        raise
    drain_threads(threads)
    result.update(status="FAILED" if failed.is_set() else "COMPLETE", ended_monotonic_s=clock())
    result["overlap"] = summarize_overlap(result["glm"], result["qwen"])
    return result


def _interval(row, phase):
    sample = (row or {}).get("sample", {})
    start, end = sample.get("request_started_monotonic_s"), sample.get("request_ended_monotonic_s")
    if not all(type(v) in (int, float) and math.isfinite(v) for v in (start, end)) or end < start:
        return None
    if phase == "request":
        return start, end
    timing = sample.get("client_timing", {})
    first, last = timing.get("ttft_any_output_seconds"), timing.get("last_output_seconds")
    if not all(type(v) in (int, float) and math.isfinite(v) for v in (first, last)) or not 0 <= first <= last <= end-start:
        return None
    return (start, start+first) if phase == "prefill_proxy" else (start+first, start+last)


def summarize_overlap(glm_row, qwen_rows):
    result = {"basis": "worker client dispatch/drain and actual output-event arrivals; prefill proxy is not native phase timing", "pairs": []}
    for q in qwen_rows:
        row = {"qwen_id": q.get("id")}
        for gp, qp in (("request", "request"), ("prefill_proxy", "prefill_proxy"),
                       ("prefill_proxy", "decode"), ("decode", "prefill_proxy"), ("decode", "decode")):
            g, other = _interval(glm_row, gp), _interval(q, qp)
            row[gp + "_" + qp + "_seconds"] = max(0, min(g[1], other[1])-max(g[0], other[0])) if g and other else None
        g, other = _interval(glm_row, "request"), _interval(q, "request")
        row["qwen_tail_after_glm_seconds"] = max(0, other[1]-g[1]) if g and other else None
        result["pairs"].append(row)
    return result


def execute_decode_pair(glm_job, qwen_job, invoke):
    """Optional single pair; Q starts only after actual GLM output, not a timer."""
    first, finished = threading.Event(), threading.Event()
    result = {"glm": None, "qwen": [], "errors": []}
    def glm_lane():
        try:
            result["glm"] = invoke(glm_job, first_output=first)
        except BaseException as exc:
            result["errors"].append({"error_class": type(exc).__name__})
        finally:
            finished.set()
    thread = threading.Thread(target=glm_lane)
    try:
        thread.start()
        while not first.wait(.05) and not finished.is_set():
            pass
        if first.is_set():
            try:
                result["qwen"].append(invoke(qwen_job))
            except BaseException as exc:
                result["errors"].append({"error_class": type(exc).__name__})
    finally:
        drain_threads([thread])
    result["overlap"] = summarize_overlap(result["glm"], result["qwen"])
    rows = [r for r in [result["glm"], *result["qwen"]] if r is not None]
    result["status"] = ("FAILED" if result["errors"] or any(r.get("status") not in SUCCESS for r in rows)
                        else "COMPLETE" if result["glm"] and result["qwen"] else "UNAVAILABLE")
    return result


def restore_and_finalize(host, key, control_key, *, verify=worker_verify.verify):
    """Explicit canonical stages; a failed stage remains a failure, with its ledger."""
    status = host.call("status")
    if status["phase"] == "NEW":
        host.call("recover")  # restore-only caller, existing execution/ledger required
    elif status["phase"] not in {"RESTORED", "POST_RELEASE_LAN_VERIFICATION_PENDING"}:
        host.call("restore")
    status = host.call("status")
    if status["phase"] == "POST_RELEASE_LAN_VERIFICATION_PENDING":
        host.call("verify_restoration", receipt=verify(status, key, control_key))
    final = host.call("status")
    if final["phase"] != "RESTORED":
        raise RuntimeError("canonical_restoration_not_verified_preserve_ledger")
    return final


class ConcurrentRun(runner.Campaign):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.interrupted = threading.Event()

    def retire_all(self):
        with self.lock:
            super().retire_all()
            self.safety.clear()

    def admission(self, cid, maximum=7200):
        if self.interrupted.is_set():
            raise RuntimeError("ROOT_INTERRUPTED_DRAIN_AND_RESTORE")
        return super().admission(cid, maximum)

    def record(self, phase=None):
        with self.lock:
            super().record(phase)
            runner.save(self.state / "status.json", {"phase": self.progress["phase"], "task": self.state.name,
                "session_id": self.armed["session_id"], "source_commit": self.armed["source_commit"],
                "clock": self.armed["runtime"], "completed": list(self.progress["completed"]),
                "inflight": self.progress["inflight"], "errors": self.progress["errors"], "updated_epoch": time.time()})

    def collect(self):
        with self.lock:
            result = super().collect()
            # Proven resource danger is shared. Missing observations stop new
            # admission without cancelling a healthy already-admitted peer.
            reasons = [v.get("abort_reason") for v in self.active.values() if v.get("abort_reason")]
            if reasons:
                for entry in self.active.values():
                    entry.setdefault("abort_reason", reasons[0]);entry["cancel_event"].set()
            return result

    def boundary(self):
        if self.interrupted.is_set():
            raise RuntimeError("ROOT_INTERRUPTED_DRAIN_AND_RESTORE")
        g1_ladder.checkpoint(self.state)
        self.collect()
        if self.safety:
            raise RuntimeError(next(iter(self.safety.values())))

    def request(self, cid, raw, identifier, *, timed=True, first_output=None, drained_event=None, stop_admission=None):
        if stop_admission is not None and stop_admission.is_set():
            raise PeerFinished()
        timeout = self.admission(cid)
        if not 0 < timeout <= 7200:
            raise RuntimeError("STOP_BUDGET")
        manifest = self.active[cid]["manifest"]
        class Observer(client.StreamObserver):
            def feed(self, chunk, arrived):
                super().feed(chunk, arrived)
                if first_output is not None and not self.error and self.first_any is not None:
                    first_output.set()
        try:
            if stop_admission is not None and stop_admission.is_set():
                raise PeerFinished()
            body = protocol.strict_json_loads(raw)
            if body.get("max_tokens") not in (32, 256, 512) or body.get("stream") is not True:
                raise ValueError("closed_request_output_policy")
            transport = self.transport_factory("http://127.0.0.1:" + str(manifest["transport"]["port"]), self.key,
                cancel_event=self.active[cid]["cancel_event"], deadline_epoch=self.armed["runtime"]["deadline_epoch"])
            def observed_transport(body, seconds):
                try:
                    yield from transport(body, seconds)
                finally:
                    if drained_event is not None:
                        drained_event.set()
            result = client._capture_request(raw, observed_transport, sample_id=identifier, private_dir=self.private,
                summary_path=self.state / ("samples.jsonl" if timed else "warmups.jsonl"), timeout=timeout,
                clock=self.clock, observer_factory=Observer)
            if self.active[cid].get("abort_reason"):
                self.emit({"type": "resource_cancel", "id": identifier, "sample": result["summary"]})
                raise RuntimeError(self.active[cid]["abort_reason"])
            return glmrepair.Diagnostic.persistence_check(result)
        finally:
            self.host.call("request_end", id=cid)

    def warm(self, cid, manifest, proof):
        identifier = manifest["placement"] + "-" + str(manifest["configured_capacity"]) + "-warmup"
        capacity = manifest["configured_capacity"]
        if manifest["placement"] == "G1":
            sample, raw, count = g1_ladder.fit(capacity, "warmup-" + str(time.time_ns()), self.counter(cid), warmup=True)
        else:
            sample, count = fixtures.warmup_sample("bench-qwen3.8-27b", capacity,
                "warmup-" + str(time.time_ns()), self.counter(cid), scope=SCOPE)
            raw = fixtures.serialize_validate(sample)
        response = self.request(cid, raw, identifier, timed=False)
        counters = response["summary"].get("counters", {})
        if not response.get("parsed") or response["summary"]["status"] not in {"COMPLETE", "OUTPUT_LIMIT"} or counters.get("prompt_tokens") != count["input_tokens"]:
            raise RuntimeError("STOP_WARMUP_NATIVE_COUNT")
        evidence = prefill_proof(counters, manifest, proof)
        self.emit({"type": "warmup", "id": identifier, "count": count, "prefill_proof": evidence,
            "timings": "DISCARDED", "sample": response["summary"],
            "checkpoint": self.host.call("quiescent", id=cid, point="warm_idle")})
        self.boundary()

    def prepare_job(self, cid, identifier, *, target=None, matched=None, generation=False):
        self.boundary()
        start = self.clock()
        m = self.active[cid]["manifest"];capacity = m["configured_capacity"]
        nonce = "fresh-" + str(time.time_ns())
        if generation:
            # Reuse the saved short scientific/tutorial question. Output length
            # is observed, with no scientific-quality or natural-completion claim.
            from .decode_diag import QUESTION
            glm = m["placement"] == "G1"
            body = {"model": "bench-glm-5.3" if glm else "bench-qwen3.8-27b",
                "messages": [{"role": "user", "content": nonce + "\n" + QUESTION}],
                "max_tokens": 512, "temperature": 1.0 if glm else 0,
                "reasoning_effort": "low" if glm else "none", "stream": True,
                "stream_options": {"include_usage": True}}
            if glm:
                body["seed"] = 1729
            raw = fixtures.canonical(body)
            sample = {"kind": "generation", "fixture_sha256": fixtures.digest(QUESTION.encode()),
                      "body": body, "source": "decode_diag.QUESTION", "output_cap": 512}
            count = fixtures.validate_count(self.counter(cid)(raw), raw, capacity)
        elif m["placement"] == "G1":
            frozen = json.loads((self.private / ("G1-" + str(capacity) + "-saved-fixture.json")).read_bytes())
            sample, raw, count = g1_ladder.fit(capacity, nonce, self.counter(cid), matched=frozen)
        else:
            if matched:
                sample, count = fixtures.matched_sample(matched, nonce, self.counter(cid), capacity, scope=SCOPE, target_capacity=target)
            else:
                sample, count = fixtures.fit_sample("bench-qwen3.8-27b", capacity, "concurrent-qwen-fixture-1729", nonce,
                    self.counter(cid), scope=SCOPE, target_capacity=target)
            raw = fixtures.serialize_validate(sample)
        if count["input_tokens"] + (512 if generation else 256) > capacity:
            raise RuntimeError("STOP_NATIVE_CAPACITY")
        runner.save(self.private / (identifier + "-fixture.json"), sample)
        runner.save(self.private / (identifier + "-count.json"), count)
        return {"id": identifier, "cid": cid, "sample": sample, "raw": raw, "count": count,
            "manifest_sha256": fixtures.digest(fixtures.canonical(m)), "generation": generation,
            "preparation_seconds": self.clock()-start}

    def measure(self, job, *, first_output=None):
        cid, identifier = job["cid"], job["id"]
        if fixtures.digest(job["raw"]) != job["count"]["body_sha256"] or fixtures.digest(fixtures.canonical(self.active[cid]["manifest"])) != job["manifest_sha256"]:
            raise RuntimeError("STOP_PREPARED_IDENTITY_CHANGED")
        with self.lock:
            if identifier in self.progress["inflight"] or identifier in self.progress["completed"]:
                raise RuntimeError("no_measurement_retry")
            self.progress["inflight"][identifier] = {"container": cid};self.record()
        try:
            response = self.request(cid, job["raw"], identifier, first_output=first_output,
                drained_event=job.get("drained_event"), stop_admission=job.get("stop_admission"))
        except PeerFinished:
            with self.lock:
                del self.progress["inflight"][identifier]
                self.record()
            raise
        summary, parsed = response["summary"], response.get("parsed")
        counters = summary.get("counters", {})
        cap = self.active[cid]["manifest"]["configured_capacity"]
        native = bool(parsed and type(counters.get("completion_tokens")) is int and counters["completion_tokens"] > 0
            and counters.get("prompt_tokens") == job["count"]["input_tokens"]
            and counters["prompt_tokens"]+counters["completion_tokens"] <= cap
            and counters["completion_tokens"] <= protocol.strict_json_loads(job["raw"])["max_tokens"]
            and (counters.get("cached_tokens") == 0
                 and counters.get("evaluated_prompt_tokens") == counters["prompt_tokens"]
                 and counters.get("decode_tokens") == counters["completion_tokens"]
                 if self.active[cid]["manifest"]["placement"] == "G1"
                 else counters.get("cached_tokens") in (None, 0)))
        strict = fixtures.score_retrieval(job["sample"], parsed["message"]) if native and not job["generation"] else {"status": "UNSCORED"}
        semantic = fixtures.score_retrieval_semantic(job["sample"], parsed["message"]) if native and not job["generation"] else {"status": "UNSCORED"}
        status = ("STOP_NATIVE_OR_TRANSPORT" if not native or summary["status"] not in {"COMPLETE", "OUTPUT_LIMIT"}
                  else "TIMING_ONLY" if job["generation"] else "OUTPUT_LIMIT" if parsed["status"] == "OUTPUT_LIMIT"
                  else "PASS" if semantic["status"] == "PASS" else semantic["status"])
        n, ms = counters.get("decode_tokens"), counters.get("decode_ms")
        row = {"id": identifier, "status": status, "strict": strict, "semantic": semantic, "sample": summary,
            "native_count_valid": native, "count": job["count"], "configured_capacity": cap,
            "occupied_tokens": counters.get("prompt_tokens", 0)+counters.get("completion_tokens", 0) if native else None,
            "fixture_sha256": job["sample"]["fixture_sha256"], "fixture_preparation_seconds": job["preparation_seconds"],
            "native_n_minus_one_decode_tps": (n-1)*1000/ms if type(n) is int and n>1 and type(ms) in (int,float) and ms>0 else None,
            "telemetry": self.telemetry_window(cid, summary.get("request_started_monotonic_s"), summary.get("request_ended_monotonic_s"), "inference_dispatch_to_drain"),
            "limitations": ["output_cap_is_not_output_count", "short_decode_sample", "GLM_intermittent_variability", "no_speed_stop", "sampled_peaks_not_absolute"]}
        if self.active[cid]["manifest"]["placement"] == "G1" and row["native_n_minus_one_decode_tps"] is not None and row["native_n_minus_one_decode_tps"] < 1:
            self.emit({"type": "glm_low_decode_observation", "id": identifier,
                "native_n_minus_one_decode_tps": row["native_n_minus_one_decode_tps"],
                "root_notification": "observed_below_1_token_per_second", "stop_condition": False})
        with self.lock:
            self.progress["completed"][identifier] = row;del self.progress["inflight"][identifier]
            runner.save(self.state / (identifier + "-result.json"), row);self.emit({"type": "trial", **row});self.record()
        return row

    def sequence(self):
        self.host.call("begin")
        for round_name, gc, qc, maximum in (("short",16384,262144,3),("long",65536,700160,8)):
            self.boundary();self.record("PREPARING_" + round_name)
            admission = self.host.call("admit_concurrent", round=round_name)
            ids = {m["placement"]: self.loaded(m) for m in admission["manifests"]}
            g = self.prepare_job(ids["G1"], round_name + "-G1")
            first = self.prepare_job(ids["Q1"], round_name + "-Q1-0", target=qc)
            q = [first];filler = None
            for index in range(1,maximum):
                prepared = self.prepare_job(ids["Q1"], round_name + "-Q1-" + str(index), target=262144,
                    matched=first["sample"] if round_name == "short" else filler)
                filler = prepared["sample"];q.append(prepared)
            self.boundary();self.record("DISPATCHING_" + round_name)
            result = execute_round(g,q,self.measure,clock=self.clock,stop_event=self.interrupted)
            self.emit({"type": "concurrent_round", "round": round_name, **result})
            runner.save(self.state / (round_name + "-round.json"), result)
            if result["status"] != "COMPLETE":
                raise RuntimeError("STOP_ROUND_GATE")
            if round_name == "short":
                self.retire_all()
            else:
                self.boundary()
                baseline = self.prepare_job(ids["Q1"], "large-Q1-resident-idle-reference", target=qc, matched=first["sample"])
                if self.measure(baseline)["status"] != "PASS":
                    raise RuntimeError("STOP_REFERENCE_GATE")
                decode_overlap = any((r.get("decode_decode_seconds") or 0)>0 for r in result["overlap"]["pairs"])
                if not decode_overlap and self.armed["optional_decode_pair"]:
                    self.boundary()
                    g = self.prepare_job(ids["G1"], "decode-G1", generation=True)
                    q = self.prepare_job(ids["Q1"], "decode-Q1", generation=True)
                    pair = execute_decode_pair(g,q,self.measure)
                    self.emit({"type": "optional_decode_pair", **pair});runner.save(self.state / "decode-pair.json",pair)
                    if pair["status"] == "FAILED":
                        raise RuntimeError("STOP_OPTIONAL_DECODE_GATE")
                self.boundary()
                self.record("MEASUREMENTS_COMPLETE")

    def execute(self):
        monitor = threading.Thread(target=self.monitor, daemon=True);monitor.start()
        try:
            self.sequence()
        finally:
            self.stop.set();monitor.join()  # every HTTP lane already drained


def prepare(task, session_id):
    task = Path(task).resolve()
    if (task / "arm.json").exists():
        raise ValueError("arm_exists_preserve_review")
    from .host import concurrent_capacity_policy
    private = task / "private";private.mkdir(mode=0o700,exist_ok=True)
    frozen = {}
    for capacity in (16384,65536):
        source = task.parent / "GLM-G1-LADDER-20260920/private" / ("G1-"+str(capacity)+"-primary-fixture.json")
        value = json.loads(source.read_bytes());fixtures.serialize_validate(value)
        target = private / ("G1-"+str(capacity)+"-saved-fixture.json");runner.save(target,value)
        frozen[str(target.relative_to(task))] = fixtures.digest(target.read_bytes())
    value = {"schema":1,"scope":SCOPE,"campaign":profiles.CONCURRENT_CAMPAIGN,"session_id":session_id,
        "source_commit":glmrepair.git("rev-parse","HEAD"), "runtime_policy":POLICY,
        "manifests":profiles.concurrent_manifests(),"trial_plan":profiles.trial_order(SCOPE),
        "concurrent_capacity_policy":concurrent_capacity_policy(),"frozen_inputs":frozen,
        "optional_decode_pair":True,"source_files":{p:fixtures.digest(b) for p,b in runner.source_files().items()}}
    profiles.validate_arm_scope(value)
    runner.save(task/"arm.json",value)
    runner.save(task/"arm-receipt.json",{"source_commit":value["source_commit"],"preparation_session_id":session_id,
        "campaign":value["campaign"],"arm_sha256":fixtures.digest((task/"arm.json").read_bytes())})
    runner.save(task/"progress.json",{"phase":"SOURCE_READY_FOR_ROOT_REVIEW","completed":{},"inflight":{},"errors":[]})
    return value


def run(task, go_path, session_id, *, restore_only=False):
    task = Path(task).resolve()
    armed = json.loads((task/"arm.json").read_bytes());go=json.loads(go_path.read_bytes())
    receipt=json.loads((task/"arm-receipt.json").read_bytes())
    if (go.get("decision")!="GO" or go.get("vm_writer_handoff") is not True
            or any(go.get(k)!=v for k,v in receipt.items())
            or receipt["arm_sha256"]!=fixtures.digest((task/"arm.json").read_bytes()) or os.geteuid()==0
            or {p:fixtures.digest(b) for p,b in runner.source_files().items()}!=armed["source_files"]):
        raise ValueError("root_source_arm_GO_required")
    for name,sha in armed["frozen_inputs"].items():
        if fixtures.digest((task/name).read_bytes())!=sha:raise ValueError("frozen_input_changed")
    execution=task/"execution-arm.json"
    if restore_only:
        executed=json.loads(execution.read_bytes())
        if executed.get("preparation_arm_sha256")!=receipt["arm_sha256"]:raise ValueError("recovery_arm_changed")
    else:
        if execution.exists():raise ValueError("no_rerun_or_clock_reset")
        executed={**armed,"runtime":bind_runtime(armed,go,session_id,time.time()),"session_id":session_id,
                  "preparation_arm_sha256":receipt["arm_sha256"]}
        runner.save(execution,executed)
    from runtime.sglang38_file_auth import read_key
    credentials=task.parent/"BENCHRUN-20260919/private-credentials"
    s=credentials.lstat()
    if credentials.is_symlink() or s.st_uid!=os.geteuid() or stat.S_IMODE(s.st_mode)!=0o700:raise ValueError("protected_credentials_required")
    key,control_key=read_key(credentials/"inference-key"),read_key(credentials/"control-key")
    runner.run_preflight(SCOPE)
    host=glmrepair.DiagnosticSSHHost(executed,stage=not restore_only)
    job = ConcurrentRun(task, executed, host, key)
    failed, restored, restoration_error = False, False, None
    errors = []
    def save_safe(path, value):
        # Worker evidence failure must never bypass ownership restoration.
        try:
            runner.save(path, value)
        except BaseException as exc:
            errors.append({"phase": "local_evidence_write", "error_class": type(exc).__name__})
    def record_safe(phase):
        try:
            job.record(phase)
        except BaseException as exc:
            errors.append({"phase": "local_status_write", "error_class": type(exc).__name__})
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    for sig in previous:
        signal.signal(sig, lambda signum, frame: job.interrupted.set())
    try:
        if not restore_only:
            try:
                job.execute()
            except BaseException as exc:
                failed = True
                # Preserve the original class before any fallible local writes.
                from .host import rpc_diagnostic
                diagnostic = rpc_diagnostic("measurement", exc)
                errors.append({"phase": "measurement", "error_class": type(exc).__name__,
                               "frames": diagnostic["frames"], "require_code": diagnostic["require_code"]})
                job.progress["errors"].append(dict(errors[-1]))
                record_safe("RESTORING_AFTER_FAILURE")
        try:
            phase = host.call("status")["phase"]
            if not restore_only and phase in {"NEW", "FAILED_BEFORE_OWNERSHIP", "FAILED_BEFORE_MUTATION"}:
                failed = True
                record_safe("FAILED_BEFORE_OWNED_MUTATION")
            else:
                restore_and_finalize(host, key, control_key)
                restored = True
                record_safe("RESTORED")
        except BaseException as exc:
            restoration_error = exc
            from .host import rpc_diagnostic
            original = rpc_diagnostic("restoration", exc)
            errors.append({"phase": "restoration", "error_class": type(exc).__name__,
                           "frames": original["frames"], "require_code": original["require_code"]})
            try:
                diagnostic = host.call("rpc_diagnostics")
            except BaseException as diag_error:
                diagnostic = {"status": "UNAVAILABLE", "error_class": type(diag_error).__name__}
            save_safe(task / "restoration-rpc-diagnostics.json", diagnostic)
            record_safe("RECOVERY_REQUIRED")
    finally:
        try:
            terminal = "RESTORED" if restored else host.call("status")["phase"]
            if terminal in {"RESTORED", "NEW", "FAILED_BEFORE_OWNERSHIP", "FAILED_BEFORE_MUTATION"}:
                host.close()
                ports = {}
                for port in (31002, 31004):
                    with socket.socket() as sock:
                        sock.settimeout(1)
                        ports[str(port)] = "CLOSED" if sock.connect_ex(("127.0.0.1", port)) else "OPEN"
                if set(ports.values()) != {"CLOSED"}:
                    failed = True
                    record_safe("TUNNEL_CLOSURE_FAILED")
                save_safe(task / "final-restoration-receipt.json", {
                    "status": "PASS" if restored and set(ports.values()) == {"CLOSED"} else "FAIL",
                    "phase": "RESTORED" if restored else "NOT_APPLICABLE", "host_session_closed": True,
                    "local_tunnel_ports": ports, "authenticated_worker_LAN": restored, "epoch": time.time()})
        except BaseException as exc:
            failed = True
            errors.append({"phase": "host_session_close", "error_class": type(exc).__name__})
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
    save_safe(task / "run-outcome.json", {"measurement_failed": failed, "restored": restored, "errors": errors})
    if restoration_error is not None:
        raise RuntimeError("canonical_restoration_failed_preserve_ledger_and_safe_diagnostics") from None
    return 1 if failed or errors else 0


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=("prepare","run","restore"));p.add_argument("--task-dir",type=Path,required=True)
    p.add_argument("--session-id",required=True);p.add_argument("--go",type=Path)
    args=p.parse_args(argv)
    if args.action=="prepare":prepare(args.task_dir,args.session_id);return 0
    if args.go is None:p.error("--go is required for live or recovery work")
    return run(args.task_dir,args.go,args.session_id,restore_only=args.action=="restore")

if __name__=="__main__":
    raise SystemExit(main())
