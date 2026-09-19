"""One reviewed G2 4K diagnostic run; no ladder, fix, resume or automatic retry.

Worker-local entry point: python3 -m benchmark.glmrepair --help (PYTHONPATH=scripts).
Only explicit run plus a source/session-bound root GO permits network or staging.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import signal
import stat
import threading
import time

from agent import protocol
from . import client, fixtures, profiles, runner, worker_verify
from .warmup import prefill_proof

TASK = "GLMREPAIR-RUN-20260919"
CAMPAIGN = "benchrun-glmrepair-20260919"
BASE = "48f0f38fcd42b081c2deca351cdfb7a943465449"
MODEL = "bench-glm-5.3"
FIXTURE_KEY = MODEL + "-4096-retrieval"
PROBE_TEXT = 'Return exactly one JSON object {"ok":true} as your final answer. No other final-answer text.'


def git(*args):
    return subprocess.check_output(["git", *args], cwd=profiles.ROOT, text=True).strip()


def checkpoint(task):
    """Record incoming root steering at boundaries, never during healthy requests."""
    path = task / "incoming-latest.md"
    if path.exists():
        raw = path.read_bytes()
        runner.save(task / "incoming-observed.json", {"sha256": fixtures.digest(raw), "observed_epoch": time.time()})
        # A new instruction requires the owning Codex session to inspect it;
        # pause only at a quiescent boundary, with restoration in the outer finally.
        approved = task / "incoming-reviewed.sha256"
        if not approved.exists() or approved.read_text().strip() != fixtures.digest(raw):
            raise RuntimeError("ROOT_STEERING_REVIEW_REQUIRED")


def probe_body(stream):
    body = {"model": MODEL, "temperature": 0, "reasoning_effort": "low", "stream": stream,
            "messages": [{"role": "user", "content": PROBE_TEXT}], "max_tokens": 128}
    if stream:
        body["stream_options"] = {"include_usage": True}
    return body


def format_outcome(response, sample=None):
    parsed = response.get("parsed")
    if not parsed:
        return {"status": "UNSCORED", "reason": "native_response_unparsed"}
    message = parsed["message"]
    content = message.get("content") or ""
    result = {"completion": "LENGTH" if parsed["finish_reason"] == "length" else "COMPLETE",
              "finish_reason": parsed["finish_reason"], "content_sha256": fixtures.digest(content.encode()),
              "literal_think_close_count": content.count("</think>"), "content_characters": len(content),
              "output_modified": False}
    if sample is not None:
        strict = fixtures.score_retrieval(sample, message)
    else:
        try:
            value = protocol.strict_json_loads(content)
            passed = isinstance(value, dict) and set(value) == {"ok"} and value["ok"] is True
            strict = {"status": "PASS" if passed and not message.get("tool_calls") else "MODEL_INCORRECT"}
        except (protocol.AgentError, TypeError):
            strict = {"status": "HARNESS_FAILURE", "reason": "invalid_answer_json_unscored"}
    result["strict_output_contract"] = strict
    result["status"] = "OUTPUT_LIMIT" if result["completion"] == "LENGTH" else strict["status"]
    return result


def load_frozen(task, profile):
    fixed = profile["fixed_fixture"]
    sample = json.loads(Path(fixed["path"]).read_bytes())[fixed["key"]]
    fixtures.serialize_validate(sample)
    for key in ("seed", "records", "kind", "fixture_sha256"):
        if sample[key] != fixed[key]:
            raise ValueError("frozen_G1_fixture_changed")
    runner.save(task / "private" / "fixtures.json", {FIXTURE_KEY: sample})
    return sample


class DiagnosticSSHHost(runner.SSHHost):
    """Defer main-thread interrupts until the one outstanding RPC reply drains."""
    def call(self, op, **args):
        if threading.current_thread() is not threading.main_thread():
            return super().call(op, **args)
        pending = []
        previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
        for sig in previous:
            signal.signal(sig, lambda signum, frame: pending.append(signum))
        try:
            result = super().call(op, **args)
            if pending and op == "request_begin":
                # No HTTP request has been dispatched; undo successful admission
                # before propagating cancellation into the restoration finally.
                super().call("request_end", id=args["id"])
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
        if pending:
            raise KeyboardInterrupt()
        return result


class Diagnostic(runner.Campaign):
    """Reuse owner admission, native recount, monitoring, placement and restore."""
    def record(self, phase=None):
        super().record(phase)
        runner.save(self.state / "status.json", {"schema_version": 1, "task": TASK,
            "session_id": self.armed["session_id"], "source_commit": self.armed["source_commit"],
            "phase": self.progress["phase"], "campaign": CAMPAIGN,
            "clock": self.armed.get("runtime"), "completed": list(self.progress["completed"]),
            "inflight": self.progress["inflight"], "errors": self.progress["errors"],
            "updated_epoch": time.time(), "live_inference_authorized": True})

    def boundary(self, cid, point):
        checkpoint(self.state)
        self.collect()
        if cid in self.safety:
            raise RuntimeError(self.safety[cid])
        self.emit({"type": "diagnostic_snapshot", "point": point,
                   "receipt": self.host.call("diagnostic_snapshot", id=cid, point=point)})

    def admission(self, cid, maximum=7200):
        timeout = super().admission(cid, maximum)
        deadline = self.armed.get("runtime", {}).get("deadline_epoch")
        if deadline is not None:
            timeout = min(timeout, deadline - time.time())
            if timeout <= 0:
                self.host.call("request_end", id=cid)
                raise RuntimeError("STOP_BUDGET")
        return timeout

    @staticmethod
    def persistence_check(result):
        if any(code in result["summary"].get("report_errors", []) for code in
               ("private_response_write_failed", "summary_write_failed")):
            raise RuntimeError("raw_evidence_persistence_failed")
        return result

    def request(self, cid, raw, identifier, *, timed=True):
        body = protocol.strict_json_loads(raw)
        if body["max_tokens"] == 256:
            return self.persistence_check(super().request(cid, raw, identifier, timed=timed))
        timeout = self.admission(cid)
        try:
            transport = self.transport_factory("http://127.0.0.1:31002", self.key,
                cancel_event=self.active[cid]["cancel_event"], stream=body["stream"])
            result = client.run_diagnostic_request(raw, transport, sample_id=identifier,
                private_dir=self.private, summary_path=self.state / ("samples.jsonl" if timed else "warmups.jsonl"),
                timeout=timeout, clock=self.clock)
            if self.active[cid].get("abort_reason"):
                raise RuntimeError(self.active[cid]["abort_reason"])
            return self.persistence_check(result)
        finally:
            self.host.call("request_end", id=cid)

    def warm(self, cid, manifest, proof):
        self.record("WARMUP")
        self.boundary(cid, "before_warmup")
        counter = self.counter(cid)
        # Reuse the historical warmup fitter, then recount the ACTUAL 32-cap body.
        # The frozen benchmark fixture serializer/output policy is unchanged.
        sample, _ = fixtures.warmup_sample(MODEL, 4096, "warmup-" + str(time.time_ns()), counter)
        body = copy.deepcopy(sample["body"])
        body["max_tokens"] = 32
        raw = fixtures.canonical(body)
        counted = fixtures.validate_count(counter(raw), raw, 4096)
        if not 2304 <= counted["input_tokens"] <= 2432:
            raise RuntimeError("warmup_actual_input_outside_full_batch_range")
        runner.save(self.private / "warmup-count.json", counted)
        result = self.request(cid, raw, "warmup", timed=False)
        self.emit({"type": "warmup_response", "summary": result["summary"], "timings": "DISCARDED"})
        if not result["parsed"] or result["summary"]["status"] not in {"COMPLETE", "OUTPUT_LIMIT"}:
            raise RuntimeError("warmup_transport_or_native_counters_unavailable")
        prefill = prefill_proof(result["parsed"]["counters"], manifest, proof)
        self.emit({"type": "warmup", "count": counted, "max_tokens": 32,
                   "prefill_proof": prefill, "timings": "DISCARDED",
                   "format": format_outcome(result),
                   "checkpoint": self.host.call("quiescent", id=cid, point="warm_idle")})
        self.boundary(cid, "after_warmup")

    def sequence(self):
        self.host.call("begin")
        cid = self.loaded(self.armed["manifests"][0])  # exactly one load + warmup
        for stream, name in ((True, "stream"), (False, "nonstream")):
            self.record("PROBE_" + name.upper())
            self.boundary(cid, "before_" + name)
            self.progress["inflight"][name] = {"container": cid}
            self.record()
            result = self.request(cid, fixtures.canonical(probe_body(stream)), name)
            outcome = {"summary": result["summary"], "format": format_outcome(result)}
            self.emit({"type": "plain_probe", "id": name, **outcome})
            self.progress["completed"][name] = outcome
            del self.progress["inflight"][name]
            self.record()
            self.boundary(cid, "after_" + name)
            if result["summary"]["status"] == "TRANSPORT_FAILURE":
                raise RuntimeError("native_transport_failure")
            # COMPLETE/LENGTH/invalid JSON are diagnostic outcomes, never a
            # baseline correctness gate. Safety remains independently mandatory.
        self.record("BASELINE")
        prepared = self.prepare_trial(cid, "matched-4096-retrieval", fixture_key=FIXTURE_KEY)
        runner.save(self.private / "baseline-fixture.json", prepared["sample"])
        runner.save(self.private / "baseline-count.json", prepared["count"])
        self.boundary(cid, "before_baseline")
        result = self.trial(cid, "matched-4096-retrieval", prepared=prepared)
        self.boundary(cid, "after_baseline")
        counters = result.get("sample", {}).get("counters", {})
        n, ms = counters.get("decode_tokens"), counters.get("decode_ms")
        rates = ({"n_minus_one_per_second": (n - 1) * 1000 / ms,
                  "n_per_second": n * 1000 / ms, "basis": "native predicted_n and predicted_ms"}
                 if type(n) is int and n > 0 and type(ms) in (int, float) and ms > 0 else {"status": "UNAVAILABLE"})
        self.emit({"type": "baseline_disposition", "strict_status": result["status"],
                   "performance_independent_of_format": True, "output_modified": False,
                   "native_counters": counters, "derived_decode_rates": rates})
        self.record("MEASUREMENT_COMPLETE")

    def execute(self):
        monitor = threading.Thread(target=self.monitor, daemon=True)
        monitor.start()
        try:
            self.sequence()
        finally:
            self.stop.set()
            monitor.join(timeout=30)
            if monitor.is_alive():
                self.record("RESTORING_WAIT_MONITOR")
                monitor.join()  # retain owner; never skip restoration for slow telemetry
            # Drain-first request wrappers unregister before this finally. The
            # canonical owner independently refuses to retire a healthy request.
            state = self.host.call("status")
            if state["phase"] not in {"NEW", "FAILED_BEFORE_OWNERSHIP", "FAILED_BEFORE_MUTATION",
                                       "POST_RELEASE_LAN_VERIFICATION_PENDING", "RESTORED"}:
                self.record("RESTORING")
                self.restore()


def prepare(task, session_id):
    if (task / "arm.json").exists():
        raise ValueError("preparation_exists_preserve_it")
    if git("status", "--porcelain"):
        raise ValueError("commit_reviewed_source_before_preparing")
    profile = json.loads((task / "accepted-profile.json").read_bytes())
    if profile["manifest"] != profiles.glmrepair_manifest():
        raise ValueError("accepted_profile_differs")
    task.joinpath("private").mkdir(mode=0o700, exist_ok=True)
    load_frozen(task, profile)
    files = runner.source_files()
    armed = {"schema": 1, "campaign": CAMPAIGN, "scope": "glmrepair", "session_id": session_id,
             "source_commit": git("rev-parse", "HEAD"), "manifests": [profile["manifest"]],
             "trial_plan": profiles.trial_order("glmrepair"),
             "source_files": {p: hashlib.sha256(b).hexdigest() for p, b in files.items()}}
    profiles.validate_arm_scope(armed)
    runner.save(task / "arm.json", armed)
    runner.save(task / "progress.json", {"phase": "CODE_READY", "completed": {}, "inflight": {}, "errors": []})
    runner.save(task / "status.json", {"schema_version": 1, "task": TASK, "phase": "CODE_READY",
        "session_id": session_id, "source_commit": armed["source_commit"], "base_commit": BASE,
        "campaign": CAMPAIGN, "live_inference_authorized": False, "clock": None,
        "next_action": "Root CODE REVIEW/GO; same RUN session executes"})


def run(task, go_path, session_id, *, restore_only=False):
    armed = json.loads((task / "arm.json").read_bytes())
    go = json.loads(go_path.read_bytes())
    if (go.get("decision") != "GO" or go.get("source_commit") != armed["source_commit"]
            or go.get("session_id") != session_id or armed["session_id"] != session_id
            or go.get("campaign") != CAMPAIGN or git("rev-parse", "HEAD") != armed["source_commit"]
            or git("status", "--porcelain")):
        raise ValueError("root_source_session_GO_required")
    if os.geteuid() == 0:
        raise ValueError("ordinary_worker_user_required")
    current = {p: hashlib.sha256(b).hexdigest() for p, b in runner.source_files().items()}
    if current != armed["source_files"]:
        raise ValueError("reviewed_source_changed")
    if (task / "execution.json").exists() and not restore_only:
        raise ValueError("no_rerun_or_clock_reset_use_reviewed_restoration_only")
    if not restore_only:
        checkpoint(task)
    from runtime.sglang38_file_auth import read_key
    credentials = task.parent / "BENCHRUN-20260919/private-credentials"
    metadata = credentials.lstat()
    if credentials.is_symlink() or not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
        raise ValueError("protected_credential_directory_required")
    key = read_key(credentials / "inference-key")
    control_key = read_key(credentials / "control-key")
    if restore_only:
        execution = json.loads((task / "execution.json").read_bytes())
    else:
        now = time.time()
        execution = {"start_epoch": now, "deadline_epoch": now + 3600, "budget_seconds": 3600,
                     "clock": "UTC_wall_seconds_first_staging_maintenance", "restoration_outside_budget": True}
        runner.save(task / "execution.json", execution)
    armed = {**armed, "runtime": execution}
    host = DiagnosticSSHHost(armed, stage=not restore_only)
    def transport(url, credential, **kwargs):
        return client.http_transport(url, credential, deadline_epoch=execution["deadline_epoch"], **kwargs)
    diagnostic = Diagnostic(task, armed, host, key, transport_factory=transport)
    error = None
    try:
        try:
            if restore_only:
                host.call("recover")
            else:
                diagnostic.execute()
        except BaseException as exc:
            error = type(exc).__name__
            diagnostic.progress["errors"].append({"error_class": error})
            diagnostic.record()
        status = host.call("status")
        if status["phase"] == "POST_RELEASE_LAN_VERIFICATION_PENDING":
            receipt = worker_verify.verify(status, key, control_key)
            result = host.call("verify_restoration", receipt=receipt)
            diagnostic.emit({"type": "worker_restoration_verified", "result": result})
            diagnostic.record("RESTORED")
        elif status["phase"] != "RESTORED":
            diagnostic.record("RECOVERY_REQUIRED")
            raise RuntimeError("restoration_not_verified_preserve_ledger")
    finally:
        # A failed supervisor preserves the durable owner ledger for the explicit
        # restoration-only entry point; it never claims a live capability survives exit.
        terminal = host.call("status")["phase"]
        if terminal == "RESTORED":
            diagnostic.record("RESTORED")
        if terminal in {"RESTORED", "NEW", "FAILED_BEFORE_OWNERSHIP", "FAILED_BEFORE_MUTATION"}:
            host.close()
            status_path = task / "status.json"
            final_status = json.loads(status_path.read_bytes())
            runner.save(status_path, {**final_status, "host_session_closed": True})
    return 1 if error else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "restore"))
    parser.add_argument("--task-dir", required=True, type=Path)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--go", type=Path)
    args = parser.parse_args(argv)
    task = args.task_dir.resolve()
    if args.action == "prepare":
        prepare(task, args.session_id)
        return 0
    if args.go is None:
        parser.error("run requires concrete root --go receipt")
    def terminate(signum, frame):
        raise KeyboardInterrupt()  # capture partial bytes, then canonical restoration
    signal.signal(signal.SIGTERM, terminate)
    return run(task, args.go, args.session_id, restore_only=args.action == "restore")


if __name__ == "__main__":
    raise SystemExit(main())
