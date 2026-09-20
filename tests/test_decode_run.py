"""Offline tests of the RUN caller, decision boundary and owner restoration.

All count/transport/host observations are injected synthetic fixtures. Native
source labels exercise validation only; these tests establish no live evidence.
"""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark import decode_diag as diag, decode_run as run, fixtures, runner


CID = "a" * 64


def count(raw, capacity, inputs=650):
    body = json.loads(raw)
    return {"source": "native_apply_template_tokenize", "input_tokens": inputs,
            "body_sha256": fixtures.digest(raw), "configured_context": capacity,
            "template_sha256": "a" * 64, "token_ids_sha256": "b" * 64,
            "count_body_sha256": fixtures.digest(fixtures.canonical({k: v for k, v in body.items()
                                                                    if k not in ("stream", "stream_options")})),
            "count_transport_normalization": {"removed_fields": [k for k in ("stream", "stream_options") if k in body]}}


def response(*, finish="stop", n=5, counters=True, done=True):
    event = {"model": "bench-glm-5.3", "choices": [{"index": 0,
        "delta": {"content": "PRIVATE_RESPONSE_TEXT"}, "finish_reason": finish}]}
    if counters:
        event.update(usage={"prompt_tokens": 650, "completion_tokens": n, "total_tokens": 650+n},
            timings={"cache_n": 0, "prompt_n": 650, "prompt_ms": 100,
                     "predicted_n": n, "predicted_ms": 250})
    return b"data: " + fixtures.canonical(event) + b"\n\n" + (b"data: [DONE]\n\n" if done else b"")


class FakeHost:
    def __init__(self):
        self.phase, self.calls = "NEW", []

    def call(self, op, **kwargs):
        self.calls.append((op, kwargs))
        if op == "begin": self.phase = "ACTIVE"
        if op == "restore": self.phase = "POST_RELEASE_LAN_VERIFICATION_PENDING"
        if op == "status": return {"phase": self.phase}
        if op == "request_begin": return {"timeout_s": 17}
        return {}


class DecodeRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        runner.save(self.state / "progress.json", {"phase": "OFFLINE", "completed": {}, "inflight": {}, "errors": []})
        self.host = FakeHost()
        self.armed = {"session_id": "offline-run-session", "source_commit": "a" * 40,
            "campaign": "offline-only", "scope": "glm-decode-diag", "runtime": {},
            "manifests": [{"configured_capacity": n} for n in diag.CAPACITIES],
            "frozen_inputs": {"offline_fixture": True}, "capture": {"cpu": True}}
        self.sample = fixtures.build_sample("bench-glm-5.3", 18, "decode-short-1729", "fresh-test-0001", kind="generation")
        self.raw = diag.short_body(self.sample)

    def job(self, transport=None):
        factory = Mock(return_value=transport or (lambda body, timeout: iter([response()])))
        job = run.DecodeRun(self.state, self.armed, self.host, "offline-key", transport_factory=factory)
        job.active[CID] = {"manifest": {"configured_capacity": 1024}, "cancel_event": threading.Event()}
        job.boundary = Mock()
        return job

    def test_actual_caller_normal_cap_timeout_missing_preserve_rows_and_end_once(self):
        variants = [("normal", response(), None, "COMPLETE"),
                    ("cap", response(finish="length", n=128), None, "OUTPUT_LIMIT"),
                    ("timeout", response(finish=None, done=False), TimeoutError(), "TRANSPORT_FAILURE"),
                    ("missing", response(counters=False), None, "COMPLETE")]
        for name, raw_reply, failure, expected in variants:
            with self.subTest(name=name):
                def transport(body, timeout):
                    self.assertEqual(body, self.raw)
                    self.assertEqual(timeout, 17)
                    yield raw_reply
                    if failure is not None: raise failure
                job = self.job(transport)
                first_call = len(self.host.calls)
                result = job.request(CID, self.raw, name, counted=count(self.raw, 1024), sample=self.sample)
                self.assertEqual(result["summary"]["status"], expected)
                self.assertEqual([op for op, _ in self.host.calls[first_call:]], ["request_begin", "request_end"])
                self.assertEqual(Path(result["private_response_path"]).read_bytes(), raw_reply)
                if name == "missing":
                    self.assertEqual(result["summary"]["counter_status"], "UNAVAILABLE")
                if name == "timeout":
                    self.assertFalse(result.get("parsed"))
        public = (self.state / "samples.jsonl").read_text()
        rows = [json.loads(line) for line in public.splitlines()]
        self.assertEqual(len(rows), 4)
        self.assertEqual(len({row["artifact_id"] for row in rows}), 4)
        self.assertNotIn("PRIVATE_RESPONSE_TEXT", public)

    def test_actual_caller_stale_count_rejected_before_admission(self):
        job = self.job()
        bad = {**count(self.raw, 1024), "body_sha256": "c" * 64}
        with self.assertRaises(fixtures.HarnessError):
            job.request(CID, self.raw, "stale", counted=bad, sample=self.sample)
        self.assertEqual(self.host.calls, [])
        job.transport_factory.assert_not_called()

    def test_actual_caller_transport_construction_and_interrupt_end_once(self):
        for fail in (RuntimeError("offline construction failure"), KeyboardInterrupt()):
            with self.subTest(failure=type(fail).__name__):
                job = self.job()
                job.transport_factory.side_effect = fail
                start = len(self.host.calls)
                with self.assertRaises(type(fail)):
                    job.request(CID, self.raw, "failed", counted=count(self.raw, 1024), sample=self.sample)
                self.assertEqual([op for op, _ in self.host.calls[start:]], ["request_begin", "request_end"])

    def test_prepared_missing_or_nonpositive_native_timing_cannot_pass(self):
        valid = {"prompt_tokens": 650, "evaluated_prompt_tokens": 650, "cached_tokens": 0,
                 "completion_tokens": 5, "decode_tokens": 5, "decode_ms": 250, "prompt_ms": 100}
        for key, value in (("decode_tokens", None), ("decode_ms", None), ("prompt_ms", None),
                           ("decode_ms", 0), ("prompt_ms", 0), ("decode_tokens", 4)):
            with self.subTest(key=key, value=value):
                job = self.job()
                identifier = key + "-" + str(value)
                job.request = Mock(return_value={"summary": {"status": "COMPLETE", "counters": {**valid, key: value}},
                                                "parsed": {"finish_reason": "stop"}})
                with self.assertRaisesRegex(RuntimeError, "STOP_NATIVE_TIMING_UNAVAILABLE"):
                    job.prepared(CID, identifier, self.sample, self.raw, count(self.raw, 1024), kind="short_control")
                row = json.loads((self.state / (identifier + "-result.json")).read_bytes())
                self.assertTrue(row["strict_native_uncached_gate"])
                self.assertEqual(row["native_timing_status"], "UNAVAILABLE")
                self.assertIsNone(row["native_tokens_per_second"])

    def test_diagnostic_summary_failure_is_not_accepted(self):
        with self.assertRaisesRegex(RuntimeError, "diagnostic_evidence_persistence_failed"):
            run.DecodeRun.persistence_check({"summary": {"report_errors": ["diagnostic_summary_write_failed"]}})

    def test_cpu_capture_forwards_exact_worker_witness_and_safety_cancels(self):
        for safety in (False, True):
            with self.subTest(safety=safety):
                job = self.job()
                complete, witnessed = threading.Event(), threading.Event()
                calls, after_rows = [], []
                def call(op, **kwargs):
                    calls.append(op)
                    if op == "request_begin": return {"timeout_s": 17}
                    if op == "decode_cpu_capture_start":
                        self.assertFalse(kwargs["client_before"]["done"])
                        self.assertGreater(kwargs["client_before"]["native_predicted_n"], 0)
                        return {"capture_id": "offline-capture"}
                    if op == "decode_cpu_capture_status":
                        after = kwargs["client_after"]
                        after_rows.append(after)
                        if "capture_start_rpc_before_monotonic_s" in after: witnessed.set()
                        complete.set()
                        return {"capture_complete": True, "safety_stop_required": safety}
                    return {}
                job.host.call = call
                def request(raw, transport, **kwargs):
                    observe = kwargs["progress_callback"]
                    observe({"first_output_monotonic_s": time.monotonic(),
                             "last_output_monotonic_s": time.monotonic(), "native_predicted_n": 1, "done": False})
                    self.assertTrue(complete.wait(2), "bounded CPU status was never received")
                    observe({"first_output_monotonic_s": time.monotonic() - 1,
                             "last_output_monotonic_s": time.monotonic() + 10,
                             "native_predicted_n": 2, "done": False})
                    self.assertTrue(witnessed.wait(2), "final witness RPC was never received")
                    return {"summary": {"report_errors": []}}
                with patch.object(run.decode_request, "run_decode_request", side_effect=request):
                    job.request(CID, self.raw, "cpu-witness", counted=count(self.raw, 1024), sample=self.sample, cpu=True)
                self.assertEqual(calls.count("request_begin"), 1)
                self.assertEqual(calls.count("request_end"), 1)
                self.assertEqual(calls[-1], "request_end")
                final = after_rows[-1]
                self.assertLess(final["capture_start_rpc_before_monotonic_s"], final["capture_complete_rpc_after_monotonic_s"])
                self.assertGreater(final["last_output_monotonic_s"], final["capture_complete_rpc_after_monotonic_s"])
                self.assertEqual(job.active[CID]["cancel_event"].is_set(), safety)
                self.assertEqual(job.active[CID].get("abort_reason"), "STOP_CAPTURE_SAFETY" if safety else None)

    def test_cpu_receipt_emit_failure_still_ends_request_once(self):
        job = self.job()
        job.emit = Mock(side_effect=RuntimeError("offline persistence failure"))
        with patch.object(run.decode_request, "run_decode_request", return_value={"summary": {"report_errors": []}}):
            with self.assertRaisesRegex(RuntimeError, "offline persistence failure"):
                job.request(CID, self.raw, "cpu-emit", counted=count(self.raw, 1024), sample=self.sample, cpu=True)
        self.assertEqual([op for op, _ in self.host.calls], ["request_begin", "request_end"])

    def test_prepared_partial_and_missing_counter_rows_persist_before_stop(self):
        for identifier, reply, failure in (("partial", response(finish=None, done=False), TimeoutError()),
                                           ("missing", response(counters=False), None)):
            with self.subTest(identifier=identifier):
                def transport(body, timeout):
                    yield reply
                    if failure is not None: raise failure
                job = self.job(transport)
                with self.assertRaisesRegex(RuntimeError, "STOP_REQUEST_GATE"):
                    job.prepared(CID, identifier, self.sample, self.raw, count(self.raw, 1024), kind="short_control")
                row = json.loads((self.state / (identifier + "-result.json")).read_bytes())
                self.assertEqual(row["status"], "STOP_REQUEST_GATE")
                self.assertIsNone(row["actual_completion_tokens"])
                self.assertEqual(row["decode_windows"]["status"], "UNAVAILABLE")
                self.assertIn(identifier, job.progress["completed"])
                self.assertNotIn(identifier, job.progress["inflight"])
                before = len(self.host.calls)
                with self.assertRaisesRegex(RuntimeError, "STOP_DUPLICATE_REQUEST"):
                    job.prepared(CID, identifier, self.sample, self.raw, count(self.raw, 1024), kind="short_control")
                self.assertEqual(len(self.host.calls), before)

    def exercise_sequence(self, *, cpu=True, decision="LONG_BASELINE", fail_kind=None):
        self.armed["capture"]["cpu"] = cpu
        job = self.job()
        job.active.clear()
        job.monitor = Mock()
        job.long_decision = Mock(return_value=decision)
        seen, loads = [], []
        def prepared(cid, identifier, sample, raw, counted, **kwargs):
            seen.append((identifier, kwargs, json.loads(raw)["max_tokens"]))
            if kwargs["kind"] == fail_kind: raise RuntimeError("STOP_TEST_REQUEST")
            return {"summary": {"counters": {"evaluated_prompt_tokens": counted["input_tokens"]}}}
        job.prepared = Mock(side_effect=prepared)
        def loaded(manifest):
            capacity = manifest["configured_capacity"]
            cid = str(capacity)
            loads.append(capacity)
            job.active[cid] = {"manifest": manifest}
            job.warm(cid, manifest, {})
            return cid
        job.loaded = Mock(side_effect=loaded)
        job.counter = lambda cid: lambda raw: count(raw, int(cid))
        def fitted(capacity, nonce, counter, **kwargs):
            raw = diag.short_body(self.sample, 32 if kwargs.get("warmup") else 128)
            return self.sample, raw, count(raw, capacity, 650 if capacity == 1024 else 2304)
        with patch.object(run, "frozen_inputs", return_value=({"prior": True}, self.armed["frozen_inputs"])), \
             patch.object(run.g1_ladder, "checkpoint"), \
             patch.object(diag, "fit_short", side_effect=fitted) as short, \
             patch.object(diag, "fit_warmup", side_effect=lambda *a, **k: fitted(*a, **k, warmup=True)), \
             patch.object(diag, "fit_replay", return_value=(self.sample, diag.short_body(self.sample, 256), count(diag.short_body(self.sample, 256), 65536))) as replay, \
             patch.object(run, "prefill_proof", return_value={"offline": True}) as prefill:
            if fail_kind:
                with self.assertRaisesRegex(RuntimeError, "STOP_TEST_REQUEST"): job.execute()
            else:
                job.execute()
        self.assertEqual([op for op, _ in self.host.calls].count("restore"), 1)
        self.assertEqual(self.host.phase, "POST_RELEASE_LAN_VERIFICATION_PENDING")
        return job, seen, loads, short, replay, prefill

    def test_sequence_three_fresh_warmups_matched_shorts_replay_cpu_decision_long_restore_once(self):
        job, seen, loads, short, replay, prefill = self.exercise_sequence()
        self.assertEqual(loads, [1024, 32768, 65536])
        self.assertEqual([row[1]["kind"] for row in seen],
            ["load_warmup", "short_control"] * 3 + ["near_full_replay", "cpu_diagnostic", "long_answer"])
        self.assertEqual([row[2] for row in seen], [32, 128] * 3 + [256, 256, 4096])
        self.assertEqual([call.kwargs["minimum_tokens"] for call in prefill.call_args_list], [512, 2048, 2048])
        self.assertIsNone(short.call_args_list[0].kwargs["matched"])
        self.assertTrue(all(call.kwargs["matched"] is self.sample for call in short.call_args_list[1:]))
        replay.assert_called_once()
        job.long_decision.assert_called_once()
        self.assertEqual([row[0] for row in seen].count("G1-65536-natural4096"), 1)
        self.assertTrue(next(row[1]["cpu"] for row in seen if row[1]["kind"] == "cpu_diagnostic"))

    def test_sequence_optional_cpu_off_and_root_stop_never_dispatch_long(self):
        _, seen, _, _, replay, _ = self.exercise_sequence(cpu=False, decision="STOP_AND_RESTORE")
        self.assertEqual([row[1]["kind"] for row in seen], ["load_warmup", "short_control"] * 3 + ["near_full_replay"])
        replay.assert_called_once()

    def test_sequence_request_failure_stops_without_retry_and_restores_once(self):
        job, seen, loads, _, replay, _ = self.exercise_sequence(fail_kind="short_control")
        self.assertEqual(loads, [1024])
        self.assertEqual([row[1]["kind"] for row in seen], ["load_warmup", "short_control"])
        job.long_decision.assert_not_called()
        replay.assert_not_called()

    def test_root_decision_is_bound_to_exact_arm(self):
        job = self.job()
        receipt = {"source_commit": "a" * 40, "session_id": "offline-run-session", "arm_sha256": "b" * 64}
        runner.save(self.state / "arm-receipt.json", receipt)
        for decision in ("LONG_BASELINE", "STOP_AND_RESTORE"):
            runner.save(self.state / "long-decision.json", {**receipt, "decision": decision})
            self.assertEqual(job.long_decision(), decision)
        runner.save(self.state / "long-decision.json", {**receipt, "source_commit": "c" * 40, "decision": "LONG_BASELINE"})
        with self.assertRaisesRegex(RuntimeError, "ROOT_DIAGNOSTIC_DECISION_INVALID"): job.long_decision()
        self.assertEqual(self.host.calls, [])

    def test_run_rejects_missing_writer_handoff_or_wrong_GO_before_host(self):
        runner.save(self.state / "arm.json", self.armed)
        receipt = {"source_commit": self.armed["source_commit"], "session_id": self.armed["session_id"],
            "campaign": self.armed["campaign"], "arm_sha256": fixtures.digest((self.state / "arm.json").read_bytes())}
        runner.save(self.state / "arm-receipt.json", receipt)
        for extra in ({"decision": "GO"}, {"decision": "WAIT", "vm_writer_handoff": True},
                      {"decision": "GO", "vm_writer_handoff": False}):
            with self.subTest(extra=extra), patch.object(run.glmrepair, "DiagnosticSSHHost") as host:
                runner.save(self.state / "GO.json", {**receipt, **extra})
                with self.assertRaisesRegex(ValueError, "root_source_session_GO_and_writer_handoff_required"):
                    run.run(self.state, self.state / "GO.json", self.armed["session_id"])
                host.assert_not_called()
        self.assertFalse((self.state / "execution.json").exists())

    def test_prepare_refuses_reusing_PREP_session_without_host(self):
        with patch.object(run.glmrepair, "git", return_value=""), \
             patch.object(run.glmrepair, "DiagnosticSSHHost") as host:
            with self.assertRaisesRegex(ValueError, "fresh_RUN_session_required"):
                run.prepare(self.state, run.PREP_SESSION)
            host.assert_not_called()
        self.assertFalse((self.state / "arm.json").exists())


if __name__ == "__main__": unittest.main()
