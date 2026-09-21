"""Source/session-armed GLM decode RUN adapter; imports and prepare are offline.

Reuses the existing Diagnostic owner, loading/allocation, monitor, cancellation,
drain and restoration. No tuning variants or CUDA launch policy are introduced.
"""
from __future__ import annotations

import argparse
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

from . import client, decode_diag as diag, decode_request, fixtures, g1_ladder, glmrepair, profiles, runner, worker_verify
from .warmup import prefill_proof

PREP_HEAD = "c1188ecc4bb9172f66aa49a0a0e6832df5900c0c"
PREP_SESSION = "01a0bce0-04e7-7343-8a17-5a0dee734818"
LONG_SHA = "adfc0b6c1225ac5dc1f7e8ddb5c8022911c9a4551e48fd201d2228bc3abe86fe"
PROFILE_BASE = "20c2b4fd8e01e2b5710c197de4dd2957f2898842"
CPU_BODY_SHA = "0c0d362183289d17b5bccf0b9206ee169deb714eff1d9586e3c5b6a36e656215"
PROFILE_MODE = "cpu-profile-only"


def profile_inputs(task):
    """Bind the exact completed campaign CPU request; never regenerate its prefix."""
    prior = task.parent / "GLM-DECODE-DIAG-RUN-20260920"
    paths = list((prior / "private").glob("G1-65536-cpu-*/G1-65536-cpu.request.json"))
    if len(paths) != 1:
        raise ValueError("exact_saved_cpu_request_required")
    paths += [prior / "private/G1-65536-cpu-fixture.json", prior / "private/G1-65536-cpu-count.json",
              prior / "G1-65536-cpu-result.json", prior / "final-restoration-receipt.json"]
    raw, sample_raw, count_raw, result_raw, receipt_raw = [p.read_bytes() for p in paths]
    sample, counted, result, receipt = map(json.loads, (sample_raw, count_raw, result_raw, receipt_raw))
    decode_request.validate_request(raw, counted, 65536, sample=sample)
    if (fixtures.digest(raw) != CPU_BODY_SHA or counted['input_tokens'] != 618
            or json.loads(raw)['max_tokens'] != 256 or result.get('status') != 'PASS'
            or result.get('body_sha256') != CPU_BODY_SHA or result.get('strict_native_uncached_gate') is not True
            or receipt.get('status') != 'PASS' or receipt.get('phase') != 'RESTORED'
            or receipt.get('source_commit') != PROFILE_BASE or receipt.get('host_session_closed') is not True
            or receipt.get('local_tunnel_ports') != {'31002': 'CLOSED', '31004': 'CLOSED'}):
        raise ValueError('saved_cpu_and_completed_main_restoration_required')
    identity = {'files': {str(p): fixtures.digest(p.read_bytes()) for p in paths},
                'cpu_rawbody_sha256': CPU_BODY_SHA, 'native_input_tokens': 618, 'output_cap': 256,
                'prior_count': counted, 'prior_session_id': receipt['session_id']}
    return sample, raw, identity


def frozen_inputs(task):
    """Check immutable PREP artifacts without touching any host or credentials."""
    long_raw = fixtures.canonical(json.loads((task / "long-request.json").read_bytes()))
    if long_raw != diag.long_body() or fixtures.digest(long_raw) != LONG_SHA:
        raise ValueError("frozen_long_question_changed")
    identity = json.loads((task / "prior-replay-identity.json").read_bytes())
    path = Path(identity["prior_fixture_path"])
    raw = path.read_bytes()
    sample = json.loads(raw)
    fixtures.serialize_validate(sample)
    if (fixtures.digest(raw) != identity["prior_fixture_file_sha256"]
            or any(sample.get(k) != identity.get(k) for k in ("fixture_sha256", "records", "seed", "kind"))
            or sample["records"] != 2028 or sample["seed"] != g1_ladder.SEED or sample["kind"] != "retrieval"):
        raise ValueError("frozen_replay_identity_changed")
    return sample, {"long_body_sha256": LONG_SHA,
                    "replay_identity_sha256": fixtures.digest((task / "prior-replay-identity.json").read_bytes()),
                    "prior_fixture_file_sha256": fixtures.digest(raw)}


class DecodeRun(g1_ladder.Ladder):
    @staticmethod
    def persistence_check(result):
        if "diagnostic_summary_write_failed" in result["summary"].get("report_errors", []):
            raise RuntimeError("diagnostic_evidence_persistence_failed")
        return glmrepair.Diagnostic.persistence_check(result)

    def request(self, cid, raw, identifier, *, counted, sample=None, timed=True, cpu=False):
        capacity = self.active[cid]["manifest"]["configured_capacity"]
        # Reject a stale body/count before taking native request ownership.
        fixtures.validate_count(counted, raw, capacity)
        timeout = self.admission(cid)
        progress, lock, finished = {}, threading.Lock(), threading.Event()
        capture = {}

        def observe(value):
            with lock:
                progress.clear()
                progress.update(value)

        def snapshot():
            with lock:
                return dict(progress)

        def profile():
            try:
                while not finished.wait(.1):
                    before = snapshot()
                    if (before.get("first_output_monotonic_s") is not None
                            and before.get("done") is False
                            and type(before.get("native_predicted_n")) is int
                            and before["native_predicted_n"] > 0):
                        break
                else:
                    capture.update(status="UNAVAILABLE", reason="no_positive_native_decode_trigger")
                    return
                rpc_before = self.clock()
                capture.update(self.host.call("decode_cpu_capture_start", id=cid, client_before=before))
                capture_id = capture.get("capture_id")
                if not capture_id:
                    return
                # Status reads never poll /slots. The host brackets only once
                # before and once after its bounded profiler interval.
                for _ in range(30):
                    receipt = self.host.call("decode_cpu_capture_status", id=cid,
                        capture_id=capture_id, client_after=snapshot())
                    capture.update(receipt)
                    if receipt.get("safety_stop_required"):
                        self.active[cid].setdefault("abort_reason", "STOP_CAPTURE_SAFETY")
                        self.active[cid]["cancel_event"].set()
                    if receipt.get("capture_complete"):
                        break
                    finished.wait(1) if not finished.is_set() else self.sleep(1)
                # Cross-host clocks cannot be compared. Record a worker-side
                # post-stop observation, then require a later output arrival.
                observed_stop = self.clock()
                capture["worker_observed_capture_stop_monotonic_s"] = observed_stop
                while capture.get("capture_complete") and not finished.wait(.1):
                    after = snapshot()
                    if (after.get("last_output_monotonic_s") or 0) > observed_stop:
                        after.update(capture_start_rpc_before_monotonic_s=rpc_before,
                                     capture_complete_rpc_after_monotonic_s=observed_stop)
                        capture.update(self.host.call("decode_cpu_capture_status", id=cid,
                            capture_id=capture_id, client_after=after))
                        break
            except Exception as exc:
                capture.update(status="UNAVAILABLE", error_class=type(exc).__name__,
                               reason="optional_cpu_profiler_failed")

        worker = threading.Thread(target=profile, daemon=True) if cpu else None
        try:
            transport = self.transport_factory("http://127.0.0.1:31002", self.key,
                cancel_event=self.active[cid]["cancel_event"])
            if worker:
                worker.start()
            result = decode_request.run_decode_request(raw, transport, sample_id=identifier,
                private_dir=self.private, summary_path=self.state / ("samples.jsonl" if timed else "warmups.jsonl"),
                count=counted, configured_context=capacity, sample=sample, timeout=timeout,
                clock=self.clock, progress_callback=observe if cpu else None)
            return self.persistence_check(result)
        finally:
            finished.set()
            try:
                if worker and worker.ident is not None:
                    worker.join()  # bounded host capture; no request_end while capture is outstanding
                    self.last_cpu_capture = dict(capture)
                    self.emit({"type": "cpu_capture", "id": identifier, "receipt": capture,
                               "benchmark_timing": False})
            finally:
                self.host.call("request_end", id=cid)

    def prepared(self, cid, identifier, sample, raw, counted, *, kind, timed=True, cpu=False):
        capacity = self.active[cid]["manifest"]["configured_capacity"]
        if identifier in self.progress["completed"] or identifier in self.progress["inflight"]:
            raise RuntimeError("STOP_DUPLICATE_REQUEST")
        if sample is not None:
            runner.save(self.private / (identifier + "-fixture.json"), sample)
        runner.save(self.private / (identifier + "-count.json"), counted)
        self.boundary(cid, "BEFORE_" + identifier)
        self.progress["inflight"][identifier] = {"container": cid, "capacity": capacity, "kind": kind}
        self.record("REQUEST_" + identifier)
        row = {"type": "trial" if timed else "warmup", "id": identifier, "capacity": capacity,
               "kind": kind, "count": counted, "body_sha256": fixtures.digest(raw),
               "count_sha256": fixtures.digest(fixtures.canonical(counted)),
               "instrumented": cpu, "timing_disposition": "diagnostic_only" if cpu else "measured" if timed else "discarded"}
        result = None
        try:
            result = self.request(cid, raw, identifier, counted=counted, sample=sample, timed=timed, cpu=cpu)
            summary, parsed = result["summary"], result.get("parsed") or {}
            counters = summary.get("counters") or {}
            native_ok = (summary.get("status") in {"COMPLETE", "OUTPUT_LIMIT"}
                and counters.get("cached_tokens") == 0
                and counters.get("prompt_tokens") == counted["input_tokens"]
                and counters.get("evaluated_prompt_tokens") == counted["input_tokens"]
                and type(counters.get("completion_tokens")) is int and counters["completion_tokens"] > 0)
            arrivals = summary.get("client_timing", {}).get("event_arrivals", {})
            n, ms = counters.get("decode_tokens"), counters.get("decode_ms")
            timing_ok = (type(n) is int and n > 0 and n == counters.get("completion_tokens")
                and all(type(counters.get(k)) in (int, float) and math.isfinite(counters[k])
                        and counters[k] > 0 for k in ("decode_ms", "prompt_ms")))
            row.update(summary=summary, finish_reason=parsed.get("finish_reason"),
                status="STOP_REQUEST_GATE" if not native_ok else "PASS" if timing_ok or not timed else "STOP_NATIVE_TIMING_UNAVAILABLE",
                strict_native_uncached_gate=native_ok,
                native_timing_status="AVAILABLE" if timing_ok else "UNAVAILABLE",
                timing_acceptance_requires="positive native prompt_ms/decode_ms and matching positive decode/completion counts",
                actual_completion_tokens=counters.get("completion_tokens"),
                requested_output_cap=json.loads(raw)["max_tokens"],
                length_matched_128=(kind == "short_control" and counters.get("completion_tokens") == 128),
                native_tokens_per_second=n * 1000 / ms if timing_ok else None,
                decode_windows=diag.decode_windows(arrivals.get("rows", []), counters,
                    dropped_events=arrivals.get("dropped_events", 0)),
                telemetry=self.telemetry_window(cid, summary.get("request_started_monotonic_s"),
                    summary.get("request_ended_monotonic_s"), "transport_dispatch_to_drain"))
            timing = summary.get("client_timing", {})
            start = summary.get("request_started_monotonic_s")
            first, last = timing.get("ttft_any_output_seconds"), timing.get("last_output_seconds")
            if type(start) in (int, float) and type(first) in (int, float) and type(last) in (int, float):
                row["output_arrival_phase_telemetry"] = self.telemetry_window(cid, start + first, start + last,
                    "first_to_last_output_arrival; not native decode duration")
            if kind == "near_full_replay":
                row["score"] = fixtures.score_retrieval(sample, parsed.get("message", {})) if parsed else {"status": "HARNESS_FAILURE"}
                if summary.get("status") != "COMPLETE" or row["score"]["status"] != "PASS":
                    row["status"] = "STOP_REQUEST_GATE"
            if kind == "long_answer":
                row["natural_outcome"] = diag.natural_outcome(result)
            if self.active[cid].get("abort_reason"):
                row["status"] = self.active[cid]["abort_reason"]
        except BaseException as exc:
            row.update(status=self.active[cid].get("abort_reason", "HARNESS_FAILURE"), error_class=type(exc).__name__)
            raise
        finally:
            self.emit(row)
            runner.save(self.state / (identifier + "-result.json"), row)
            self.progress["completed"][identifier] = row
            self.progress["inflight"].pop(identifier, None)
            self.record("COMPLETED_" + identifier)
        if row["status"] != "PASS":
            raise RuntimeError(row["status"])
        self.boundary(cid, "AFTER_" + identifier)
        return result

    def warm(self, cid, manifest, proof):
        capacity = manifest["configured_capacity"]
        sample, raw, counted = diag.fit_warmup(capacity, "warmup-" + str(time.time_ns()), self.counter(cid))
        result = self.prepared(cid, "G1-" + str(capacity) + "-warmup", sample, raw, counted,
                               kind="load_warmup", timed=False)
        evidence = prefill_proof(result["summary"]["counters"], manifest, proof,
                                 minimum_tokens=512 if capacity == 1024 else 2048)
        self.emit({"type": "warmup_proof", "capacity": capacity, "prefill_proof": evidence,
                   "checkpoint": self.host.call("quiescent", id=cid, point="warm_idle")})

    def long_decision(self):
        self.record("AWAITING_ROOT_DIAGNOSTIC_DECISION")
        runner.save(self.state / "decision-boundary.json", {"phase": self.progress["phase"],
            "source_commit": self.armed["source_commit"], "session_id": self.armed["session_id"],
            "allowed_decisions": ["LONG_BASELINE", "STOP_AND_RESTORE"],
            "AB": "requires separately reviewed source/protocol; no preset variant",
            "cuda": "UNAVAILABLE: container launch/injection contract not validated; trace-none survival is insufficient"})
        path = self.state / "long-decision.json"
        while not path.exists():
            g1_ladder.checkpoint(self.state)
            diag.request_timeout(self.armed["runtime"], time.time())
            self.sleep(1)
        value = json.loads(path.read_bytes())
        expected = json.loads((self.state / "arm-receipt.json").read_bytes())
        if any(value.get(k) != v for k, v in expected.items()) or value.get("decision") not in {"LONG_BASELINE", "STOP_AND_RESTORE"}:
            raise RuntimeError("ROOT_DIAGNOSTIC_DECISION_INVALID")
        return value["decision"]

    def sequence(self):
        g1_ladder.checkpoint(self.state)
        if self.armed.get('mode') == PROFILE_MODE:
            sample, raw, identity = profile_inputs(self.state)
            if identity != self.armed['frozen_inputs']:
                raise RuntimeError('ROOT_FROZEN_INPUTS_CHANGED')
            self.host.call('begin')
            manifest, = self.armed['manifests']
            self.record('LOADING_65536')
            cid = self.loaded(manifest)  # Existing warm() discards one 32-token warmup.
            counted = fixtures.validate_count(self.counter(cid)(raw), raw, 65536)
            prior_count = identity['prior_count']
            if any(counted.get(k) != prior_count.get(k) for k in (
                    'input_tokens', 'body_sha256', 'count_body_sha256', 'template_sha256', 'token_ids_sha256')):
                raise RuntimeError('STOP_SAVED_CPU_NATIVE_RECOUNT_CHANGED')
            self.prepared(cid, 'G1-65536-cpu', sample, raw, counted, kind='cpu_diagnostic', cpu=True)
            receipt = getattr(self, 'last_cpu_capture', {})
            usable = receipt.get('profile_usable') is True
            self.emit({'type': 'profile_outcome', 'status': 'AVAILABLE' if usable else 'UNAVAILABLE',
                       'benchmark_timing': False, 'receipt': receipt})
            if not usable:
                raise RuntimeError('STOP_PROFILE_UNAVAILABLE')
            self.record('PROFILE_COMPLETE')
            return
        prior, identity = frozen_inputs(self.state)
        if identity != self.armed["frozen_inputs"]:
            raise RuntimeError("ROOT_FROZEN_INPUTS_CHANGED")
        self.host.call("begin")
        matched = None
        for manifest in self.armed["manifests"]:
            capacity = manifest["configured_capacity"]
            self.record("LOADING_" + str(capacity))
            cid = self.loaded(manifest)
            sample, raw, counted = diag.fit_short(capacity, "short-" + str(time.time_ns()), self.counter(cid), matched=matched)
            self.prepared(cid, "G1-" + str(capacity) + "-short", sample, raw, counted, kind="short_control")
            matched = matched or sample
            if capacity != 65536:
                self.retire_all()
        sample, raw, counted = diag.fit_replay("replay-" + str(time.time_ns()), self.counter(cid), prior)
        self.prepared(cid, "G1-65536-replay", sample, raw, counted, kind="near_full_replay")
        if self.armed["capture"]["cpu"]:
            sample, _, _ = diag.fit_short(65536, "cpu-" + str(time.time_ns()), self.counter(cid), matched=matched)
            raw = diag.short_body(sample, 256)
            counted = fixtures.validate_count(self.counter(cid)(raw), raw, 65536)
            self.prepared(cid, "G1-65536-cpu", sample, raw, counted, kind="cpu_diagnostic", cpu=True)
        self.emit({"type": "cuda_capture", "status": "UNAVAILABLE",
                   "reason": "container_cuda_launch_injection_and_target_preserving_interactive_stop_not_validated"})
        if self.long_decision() == "LONG_BASELINE":
            raw = diag.long_body()
            counted = fixtures.validate_count(self.counter(cid)(raw), raw, 65536)
            if counted["input_tokens"] + 4096 > 65536:
                raise RuntimeError("STOP_LONG_BODY_CAPACITY")
            self.prepared(cid, "G1-65536-natural4096", None, raw, counted, kind="long_answer")
        self.record("DIAGNOSTIC_DECISION_COMPLETE")


def prepare(task, session_id, *, cpu=True, profile_only=False):
    if (task / "arm.json").exists() or glmrepair.git("status", "--porcelain"):
        raise ValueError("clean_new_candidate_required")
    if session_id == PREP_SESSION:
        raise ValueError("fresh_RUN_session_required")
    if profile_only and not cpu:
        raise ValueError('profile_cpu_capture_required')
    frozen = profile_inputs(task)[2] if profile_only else frozen_inputs(task)[1]
    campaign = profiles.GLM_DECODE_PROFILE_CAMPAIGN if profile_only else profiles.GLM_DECODE_DIAG_CAMPAIGN
    armed = {"schema": 1, "scope": "glm-decode-diag", "campaign": profiles.GLM_DECODE_DIAG_CAMPAIGN,
        "session_id": session_id, "source_commit": glmrepair.git("rev-parse", "HEAD"), "base_commit": PREP_HEAD,
        "runtime": diag.stage_clock(task), "manifests": [profiles.glm_decode_diag_manifest(n) for n in diag.CAPACITIES],
        "trial_plan": profiles.trial_order("glm-decode-diag"), "frozen_inputs": frozen,
        "capture": {"cpu": cpu, "cuda": False, "cpu_maximum_seconds": 5,
                    "cpu_sampling_seconds": 4, "cpu_file_limit_bytes": 1024**3},
        "source_files": {p: hashlib.sha256(b).hexdigest() for p, b in runner.source_files().items()}}
    if profile_only:
        armed.update(mode=PROFILE_MODE, campaign=campaign, base_commit=PROFILE_BASE,
            runtime=diag.profile_stage_clock(task),
            manifests=[profiles.glm_decode_diag_manifest(65536, campaign=campaign)],
            trial_plan=profiles.trial_order('glm-decode-diag', campaign=campaign))
        if time.time() >= armed['runtime']['deadline_epoch'] or session_id == frozen['prior_session_id']:
            raise ValueError('fresh_unexpired_profile_session_required')
        # The supplied restoration receipt belongs to the immutable main campaign.
        # Keep its exact bytes separately before the new campaign writes its own.
        prior_receipt = task / 'prior-final-restoration-receipt.json'
        if not prior_receipt.exists():
            raw = (task / 'final-restoration-receipt.json').read_bytes()
            with prior_receipt.open('xb') as saved:
                saved.write(raw)
            prior_receipt.chmod(0o600)
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
    if (go.get("decision") != "GO" or go.get("vm_writer_handoff") is not True
            or any(go.get(k) != v for k, v in expected.items())
            or expected["arm_sha256"] != fixtures.digest((task / "arm.json").read_bytes())
            or session_id != armed["session_id"] or glmrepair.git("rev-parse", "HEAD") != armed["source_commit"]
            or glmrepair.git("status", "--porcelain") or os.geteuid() == 0):
        raise ValueError("root_source_session_GO_and_writer_handoff_required")
    profiles.validate_arm_scope(armed)
    if {p: hashlib.sha256(b).hexdigest() for p, b in runner.source_files().items()} != armed["source_files"]:
        raise ValueError("reviewed_source_changed")
    profile_only = armed.get('mode') == PROFILE_MODE
    clock = diag.profile_stage_clock(task) if profile_only else diag.stage_clock(task)
    frozen = profile_inputs(task)[2] if profile_only else frozen_inputs(task)[1]
    if clock != armed["runtime"] or frozen != armed["frozen_inputs"]:
        raise ValueError("immutable_inputs_changed")
    if not restore_only and ((task / "execution.json").exists() or time.time() >= clock["deadline_epoch"]):
        raise ValueError("no_rerun_or_budget_reset")
    from runtime.sglang38_file_auth import read_key
    credentials = task.parent / "BENCHRUN-20260919/private-credentials"
    metadata = credentials.lstat()
    if credentials.is_symlink() or not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
        raise ValueError("protected_credential_directory_required")
    key, control_key = read_key(credentials / "inference-key"), read_key(credentials / "control-key")
    if not restore_only:
        g1_ladder.checkpoint(task)
        runner.save(task / "execution.json", clock)
    host = glmrepair.DiagnosticSSHHost(armed, stage=not restore_only)
    def transport(url, credential, **kwargs):
        return client.http_transport(url, credential, deadline_epoch=clock["deadline_epoch"], **kwargs)
    job = DecodeRun(task, armed, host, key, transport_factory=transport)
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
            host.close()
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
                    "verification": "canonical finalize plus authenticated Worker1 LAN control/inference"})
    return 1 if error else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "restore"))
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--go", type=Path)
    parser.add_argument("--no-cpu-capture", action="store_true")
    parser.add_argument("--profile-only", action="store_true", help="prepare exact fresh 64K CPU-only campaign")
    args = parser.parse_args(argv)
    task = args.task_dir.resolve()
    if args.action == "prepare":
        prepare(task, args.session_id, cpu=not args.no_cpu_capture, profile_only=args.profile_only)
        return 0
    if args.go is None:
        parser.error("run/restore requires concrete root --go receipt")
    if args.no_cpu_capture or args.profile_only:
        parser.error("capture policy is immutable in the reviewed arm")
    def terminate(signum, frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, terminate)
    return run(task, args.go, args.session_id, restore_only=args.action == "restore")


if __name__ == "__main__":
    raise SystemExit(main())
