"""Offline actual caller seams for diagnostic capture; no network acceptance."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark import client, decode_diag as diag, decode_request as request, fixtures


def event(content=None, finish=None, **extra):
    return {"model": "bench-glm-5.3", "choices": [{"index": 0,
            "delta": {"content": content} if content else {}, "finish_reason": finish}], **extra}


def sse(events, done=True):
    return b"".join(b"data: " + fixtures.canonical(row) + b"\n\n" for row in events) + (b"data: [DONE]\n\n" if done else b"")


def counted(raw, capacity):
    return {"source": "synthetic_offline", "input_tokens": 650,
            "body_sha256": fixtures.digest(raw), "configured_context": capacity,
            "template_sha256": "a" * 64, "token_ids_sha256": "b" * 64}


class Clock:
    def __init__(self): self.value = 10
    def __call__(self): self.value += .25; return self.value


class DecodeRequestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sample = fixtures.build_sample("bench-glm-5.3", 18, "decode-short-1729", "fresh-00001", kind="generation")

    def run_capture(self, response, *, cap=128, capacity=1024, sample_id="sample", **kwargs):
        raw = diag.long_body() if cap == 4096 else diag.short_body(self.sample, cap)
        def transport(body, timeout):
            self.assertEqual(body, raw)
            self.assertEqual(timeout, 17)
            yield response
        return request.run_decode_request(raw, kwargs.pop("transport", transport),
            sample_id=sample_id, private_dir=self.root, summary_path=self.root / "public.jsonl",
            count=counted(raw, capacity), configured_context=capacity,
            sample=None if cap == 4096 else self.sample, timeout=17, clock=Clock(), synthetic=True, **kwargs)

    def response(self, finish="stop", n=5):
        return sse([event("PRIVATE_FINAL_ANSWER", finish,
            usage={"prompt_tokens": 650, "completion_tokens": n, "total_tokens": 650+n},
            timings={"cache_n": 0, "prompt_n": 650, "prompt_ms": 100,
                     "predicted_n": n, "predicted_ms": 250})])

    def test_normal_cap_actual_counts_bound_body_count_and_unique_artifacts(self):
        for cap, finish, n in [(32, "stop", 4), (128, "length", 128), (256, "stop", 7)]:
            result = self.run_capture(self.response(finish, n), cap=cap)
            row = result["summary"]
            self.assertEqual(row["status"], "OUTPUT_LIMIT" if finish == "length" else "COMPLETE")
            self.assertEqual((row["finish_reason"], row["counters"]["decode_tokens"]), (finish, n))
            self.assertEqual(row["counter_status"], "AVAILABLE")
            self.assertEqual(row["request_sha256"], row["count_binding"]["body_sha256"])
            self.assertEqual(row["count_sha256"], fixtures.digest(Path(result["private_count_path"]).read_bytes()))
            self.assertEqual(Path(result["private_response_path"]).stat().st_mode & 0o777, 0o600)
        public = (self.root / "public.jsonl").read_text()
        rows = [json.loads(line) for line in public.splitlines()]
        self.assertEqual(len({r["artifact_id"] for r in rows}), 3)
        self.assertNotIn("PRIVATE_FINAL_ANSWER", public)
        self.assertNotIn("trial-prefix", public)
        self.assertTrue(all(r["retry_attempts"] == r["lifecycle_actions"] == 0 for r in rows))

    def test_exact_natural_long_fields_recount_and_no_forced_eos(self):
        result = self.run_capture(self.response(n=27), cap=4096, capacity=65536)
        raw = Path(result["private_request_path"]).read_bytes()
        self.assertEqual(raw, diag.long_body())
        body = json.loads(raw)
        self.assertEqual((body["temperature"], body["seed"], body["reasoning_effort"], body["timings_per_token"]),
                         (1, 1729, "low", True))
        self.assertEqual(result["summary"]["counters"]["completion_tokens"], 27)
        self.assertFalse(diag.natural_outcome(result)["is_4096_token_throughput_sample"])
        for key, value in [("ignore_eos", True), ("temperature", 0), ("seed", 1), ("timings_per_token", False)]:
            changed = fixtures.canonical({**body, key: value})
            with self.assertRaises(fixtures.HarnessError):
                request.validate_request(changed, counted(changed, 65536), 65536, synthetic=True)
        stale = counted(raw, 65536); stale["body_sha256"] = "c" * 64
        with self.assertRaises(fixtures.HarnessError):
            request.validate_request(raw, stale, 65536, synthetic=True)
        with self.assertRaises(fixtures.HarnessError):
            request.validate_request(raw, counted(raw, 1024), 1024, synthetic=True)

    def test_timeout_preserves_partial_native_progress_private_bytes_and_row(self):
        partial = sse([event("PRIVATE_PARTIAL", timings={"predicted_n": 3, "predicted_ms": 123})], False)
        def timeout(body, limit):
            yield partial
            raise TimeoutError("private endpoint detail")
        result = self.run_capture(b"", transport=timeout)
        row = result["summary"]
        self.assertEqual(row["status"], "TRANSPORT_FAILURE")
        self.assertEqual(row["counter_status"], "UNAVAILABLE")
        self.assertIsNone(row["counters"]["decode_tokens"])
        self.assertEqual(row["client_timing"]["native_progress_last"]["predicted_n"], 3)
        self.assertEqual(Path(result["private_response_path"]).read_bytes(), partial)
        public = (self.root / "public.jsonl").read_text()
        self.assertNotIn("PRIVATE_PARTIAL", public)
        self.assertNotIn("private endpoint", public)

    def test_scope_rejects_other_model_stale_short_count_and_extra_fields(self):
        wrong = fixtures.build_sample("bench-qwen3.8-27b", 18, "decode-short-1729", "fresh-00001", kind="generation")
        raw = diag.short_body(wrong)
        with self.assertRaises(fixtures.HarnessError):
            request.validate_request(raw, counted(raw, 1024), 1024, sample=wrong, synthetic=True)
        raw = diag.short_body(self.sample)
        stale = counted(raw, 1024); stale["body_sha256"] = "d" * 64
        with self.assertRaises(fixtures.HarnessError):
            request.validate_request(raw, stale, 1024, sample=self.sample, synthetic=True)
        changed = fixtures.canonical({**json.loads(raw), "ignore_eos": True})
        with self.assertRaises(fixtures.HarnessError):
            request.validate_request(changed, counted(changed, 1024), 1024, sample=self.sample, synthetic=True)

    def test_native_count_normalization_keeps_long_sampling_fields(self):
        raw = diag.long_body(); body = json.loads(raw)
        count_body = {k: v for k, v in body.items() if k not in ("stream", "stream_options")}
        native = {**counted(raw, 65536), "source": "native_apply_template_tokenize",
                  "count_body_sha256": fixtures.digest(fixtures.canonical(count_body)),
                  "count_transport_normalization": {"removed_fields": ["stream", "stream_options"]}}
        _, proof = request.validate_request(raw, native, 65536)
        self.assertEqual(proof["count_body_sha256"], native["count_body_sha256"])
        # A count made before adding timings_per_token is stale even if its
        # claimed outgoing body hash was subsequently replaced.
        count_body.pop("timings_per_token")
        native["count_body_sha256"] = fixtures.digest(fixtures.canonical(count_body))
        with self.assertRaises(fixtures.HarnessError): request.validate_request(raw, native, 65536)

    def test_schema_warmup_and_replay_exact_bodies(self):
        sample = fixtures.build_sample("bench-glm-5.3", 18, "warmup-only-seed", "fresh-00001")
        for cap in (32, 256):
            raw = diag.schema_body(sample, cap)
            result = request.run_decode_request(raw, lambda body, timeout: [self.response()],
                sample_id="schema", private_dir=self.root, summary_path=self.root / "public.jsonl",
                count=counted(raw, 65536), configured_context=65536, sample=sample, synthetic=True)
            self.assertEqual(result["summary"]["status"], "COMPLETE")
            self.assertEqual(Path(result["private_request_path"]).read_bytes(), raw)

    def test_missing_counters_and_parser_failure_keep_completed_and_failed_rows(self):
        missing = sse([event("PRIVATE_ANSWER", "stop")])
        result = self.run_capture(missing)
        self.assertEqual(result["summary"]["status"], "COMPLETE")
        self.assertEqual(result["summary"]["counter_status"], "UNAVAILABLE")
        self.assertTrue(all(v is None for v in result["summary"]["counters"].values()))
        with patch.object(client, "parse_response", side_effect=fixtures.HarnessError("native counters missing")):
            result = self.run_capture(missing)
        self.assertEqual(result["summary"]["status"], "HARNESS_FAILURE")
        self.assertEqual(result["summary"]["counter_status"], "UNAVAILABLE")
        self.assertEqual(Path(result["private_response_path"]).read_bytes(), missing)
        self.assertEqual(len((self.root / "public.jsonl").read_text().splitlines()), 2)

    def test_tail_survives_one_coalesced_chunk_without_token_inference(self):
        callback = []
        rows = [event("private-" + str(n), timings={"predicted_n": n * 3, "predicted_ms": n * 100}) for n in range(1, 11)]
        rows.append(event(finish="stop"))
        with patch.object(client, "MAX_EVENT_ARRIVALS", 4):
            observer = request.DiagnosticObserver(1, progress_callback=callback.append)
            observer.feed(sse(rows), 3)
        summary = observer.summary(); receipt = summary["event_arrivals"]
        self.assertEqual([r["ordinal"] for r in receipt["rows"]], [1, 2, 10, 11])
        self.assertEqual(receipt["dropped_events"], 7)
        self.assertFalse(receipt["complete"])
        self.assertEqual(callback[-1]["native_predicted_n"], 30)
        self.assertEqual(callback[-1]["output_event_count"], 10)
        self.assertEqual(callback[-1]["last_output_monotonic_s"], 3)
        self.assertNotIn("private-", json.dumps(summary))

    def test_fragmented_frames_callback_failure_drains_and_regression_unavailable(self):
        observer = request.DiagnosticObserver(1)
        raw = sse([event("private", timings={"predicted_n": 3, "predicted_ms": 4}),
                   event("later", "stop", timings={"predicted_n": 2, "predicted_ms": 5})])
        for byte in raw: observer.feed(bytes([byte]), 2)
        self.assertTrue(observer.done)
        self.assertIsNone(observer.progress(2)["native_predicted_n"])
        self.assertTrue(observer.summary()["native_progress_last"]["counter_regression"])
        def broken(_): raise RuntimeError("private error")
        result = self.run_capture(self.response(), progress_callback=broken)
        self.assertEqual(result["summary"]["status"], "HARNESS_FAILURE")
        self.assertTrue(Path(result["private_response_path"]).is_file())

    def test_interrupt_publishes_saved_failed_row_once_then_propagates(self):
        def interrupt(body, limit):
            yield sse([event("partial")], False)
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt): self.run_capture(b"", transport=interrupt)
        rows = (self.root / "public.jsonl").read_text().splitlines()
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0])["status"], "TRANSPORT_FAILURE")


if __name__ == "__main__": unittest.main()
