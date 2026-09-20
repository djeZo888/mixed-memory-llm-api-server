"""Offline arrival metadata: bounded observations, never native token timings."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark import client, fixtures


MODEL = "bench-glm-5.3"


def event(delta=None, finish=None, **extra):
    return {"model": MODEL, "choices": [{"index": 0, "delta": delta or {},
            "finish_reason": finish}], **extra}


def wire(*events, done=False):
    return b"".join(b"data: " + fixtures.canonical(row) + b"\r\n\r\n" for row in events) + (
        b"data: [DONE]\r\n\r\n" if done else b"")


class DecodeDiagnosticEvents(unittest.TestCase):
    def test_default_summary_is_unchanged(self):
        observer = client.StreamObserver(10)
        observer.feed(wire(event({"content": "ok"}), done=True), 13)
        self.assertEqual(observer.summary(), {
            "source": "client_event_arrival", "ttft_content_seconds": 3,
            "ttft_reasoning_seconds": None, "ttft_tool_seconds": None,
            "ttft_any_output_seconds": 3, "last_output_seconds": 3,
            "events": 1, "done_observed": True, "observer_status": "OK",
            "timing_limit": "event-arrival timestamps; chunk batching and client overhead included"})

    def test_coalesced_and_fragmented_events_keep_actual_arrivals_not_token_times(self):
        observer = client.StreamObserver(10, capture_events=True)
        observer.feed(wire(event({"role": "assistant"}), event({"reasoning_content": "ž"})), 11)
        last = wire(event({"content": "several words in one event"}), done=True)
        observer.feed(last[:20], 12)
        observer.feed(last[20:], 14)
        rows = observer.summary()["event_arrivals"]["rows"]
        self.assertEqual([row["ordinal"] for row in rows], [1, 2, 3])
        self.assertEqual([row["arrived_monotonic_s"] for row in rows], [11, 11, 14])
        self.assertEqual([row["elapsed_s"] for row in rows], [1, 1, 4])
        self.assertEqual(rows[0]["content_bytes"], 0)
        self.assertFalse(rows[0]["has_content"])
        self.assertTrue(rows[1]["has_reasoning"])
        self.assertEqual(rows[1]["reasoning_bytes"], 2)
        self.assertTrue(rows[2]["has_content"])
        self.assertEqual(rows[2]["content_bytes"], 26)
        self.assertEqual(observer.summary()["ttft_any_output_seconds"], 1)
        self.assertIn("not native tokens", observer.summary()["event_arrivals"]["unit"])

    def test_only_allowlisted_numeric_and_boolean_delta_metadata_is_retained(self):
        observer = client.StreamObserver(1, capture_events=True)
        observer.feed(wire(event({"content": "private-content-1826", "reasoning_content": "private-reason-1826",
            "tool_calls": [{"id": "private-tool-id-1826", "function": {
                "name": "private-tool-name-1826", "arguments": "private-tool-args-1826"}}]}), done=True), 2)
        details = observer.summary()["event_arrivals"]
        row = details["rows"][0]
        self.assertEqual(set(row), {"ordinal", "arrived_monotonic_s", "elapsed_s",
            "content_bytes", "reasoning_bytes", "tool_bytes", "has_content", "has_reasoning", "has_tool",
            "native_timings"})
        self.assertTrue(all(row[key] for key in ("has_content", "has_reasoning", "has_tool")))
        self.assertEqual(row["tool_bytes"], len("private-tool-name-1826private-tool-args-1826"))
        self.assertNotIn("1826", json.dumps(details))
        self.assertTrue(details["complete"])

    def test_native_timings_are_allowlisted_separate_and_invalid_values_stay_null(self):
        observer = client.StreamObserver(0, capture_events=True)
        observer.feed(wire(event({"content": "x"}, timings={"predicted_n": 25, "predicted_ms": 500.5,
            "prompt_n": 700, "prompt_ms": 1000, "private_extra": "secret-4842", "tokens": [4842]}),
            event({"content": "y"}, timings={"predicted_n": True, "predicted_ms": -1,
                "prompt_n": 7.5, "prompt_ms": "private-value-4842"}), done=True), 2)
        rows = observer.summary()["event_arrivals"]["rows"]
        self.assertEqual(rows[0]["native_timings"], {"predicted_n": 25, "predicted_ms": 500.5,
            "prompt_n": 700, "prompt_ms": 1000})
        self.assertEqual(rows[1]["native_timings"], {"predicted_n": None, "predicted_ms": None,
            "prompt_n": None, "prompt_ms": None})
        self.assertEqual(observer.summary()["events"], 2)
        self.assertNotIn("4842", json.dumps(rows))

    def test_bound_drops_metadata_without_stopping_stream_observation(self):
        self.assertEqual(client.MAX_EVENT_ARRIVALS, 16384)
        observer = client.StreamObserver(0, capture_events=True)
        count = client.MAX_EVENT_ARRIVALS + 3
        observer.feed(wire(*(event({"content": "x"}) for _ in range(count)), done=True), 7)
        result = observer.summary()
        self.assertEqual(result["events"], count)
        self.assertTrue(result["done_observed"])
        self.assertEqual(result["observer_status"], "OK")
        details = result["event_arrivals"]
        self.assertEqual(len(details["rows"]), client.MAX_EVENT_ARRIVALS)
        self.assertEqual(details["rows"][-1]["ordinal"], client.MAX_EVENT_ARRIVALS)
        self.assertEqual(details["dropped_events"], 3)
        self.assertFalse(details["complete"])

    def capture(self, directory, *, observer_factory=client.StreamObserver, enabled=True):
        body = fixtures.serialize_validate(fixtures.build_sample(MODEL, 12, "events-seed", "events-nonce"))
        chunks = [wire(event({"content": "private-answer-7754"})), wire(event(finish="length",
            usage={"prompt_tokens": 700, "completion_tokens": 128},
            timings={"cache_n": 0, "prompt_n": 700, "predicted_n": 128,
                     "prompt_ms": 100, "predicted_ms": 1000}), done=True)]
        seen = []
        def transport(*args):
            for chunk in chunks:
                seen.append(chunk)
                yield chunk
        times = iter((10.0, 11.0, 15.0, 16.0))
        result = client._capture_request(body, transport, sample_id="arrival-capture",
            private_dir=directory, summary_path=Path(directory) / "summary.jsonl",
            clock=lambda: next(times), capture_events=enabled, observer_factory=observer_factory)
        return result, seen, chunks

    def test_opt_in_capture_keeps_native_counts_separate_and_summary_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            result, seen, chunks = self.capture(directory)
            self.assertEqual(seen, chunks)
            summary = result["summary"]
            self.assertEqual(summary["status"], "OUTPUT_LIMIT")
            self.assertEqual(summary["counters"]["decode_tokens"], 128)
            self.assertEqual(summary["client_timing"]["events"], 2)
            self.assertEqual([row["arrived_monotonic_s"] for row in
                summary["client_timing"]["event_arrivals"]["rows"]], [11, 15])
            self.assertIsNone(summary["client_timing"]["event_arrivals"]["rows"][0]["native_timings"])
            self.assertEqual(summary["client_timing"]["event_arrivals"]["rows"][1]["native_timings"]["predicted_n"], 128)
            self.assertNotIn("7754", (Path(directory) / "summary.jsonl").read_text())
            self.assertEqual(Path(result["private_response_path"]).read_bytes(), b"".join(chunks))

    def test_opt_in_observer_failure_still_drains_and_preserves_native_result(self):
        class Broken(client.StreamObserver):
            def feed(self, *args):
                raise ValueError("private observer detail")
        with tempfile.TemporaryDirectory() as directory:
            result, seen, chunks = self.capture(directory, observer_factory=Broken)
            self.assertEqual(seen, chunks)
            self.assertEqual(result["parsed"]["counters"]["decode_tokens"], 128)
            self.assertTrue(result["summary"]["response_retained_complete"])
            self.assertIn("stream_timing_observer_failed", result["summary"]["report_errors"])
            self.assertFalse(result["summary"]["client_timing"]["event_arrivals"]["complete"])
            self.assertEqual(result["summary"]["lifecycle_actions"], 0)
            self.assertEqual(Path(result["private_response_path"]).read_bytes(), b"".join(chunks))

    def test_default_factory_signature_remains_compatible(self):
        with tempfile.TemporaryDirectory() as directory:
            result, _, _ = self.capture(directory, enabled=False,
                observer_factory=lambda started: client.StreamObserver(started))
            self.assertNotIn("event_arrivals", result["summary"]["client_timing"])


if __name__ == "__main__":
    unittest.main()
