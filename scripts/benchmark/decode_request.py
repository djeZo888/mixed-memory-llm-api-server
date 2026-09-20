"""Exact-body request seam for the bounded GLM decode diagnostic only.

This adapter supplies no credentials, transport, lifecycle, retries or admission.
The existing campaign owns those gates. Historical public client entry points
retain their original contracts. Raw requests/responses and count receipts stay
in a unique private directory; the public row contains only allowlisted metrics.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import re
import tempfile
import time

from agent import protocol
from . import client, decode_diag, fixtures


COUNTERS = ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens",
            "evaluated_prompt_tokens", "decode_tokens", "prompt_ms", "decode_ms")
NATIVE_REQUIRED = ("cached_tokens", "evaluated_prompt_tokens", "decode_tokens",
                   "prompt_ms", "decode_ms")
COUNT_FIELDS = ("source", "input_tokens", "body_sha256", "configured_context",
                "template_sha256", "token_ids_sha256")


class DiagnosticObserver(client.StreamObserver):
    """Retain bounded head/tail metadata, with an optional nonblocking callback.

    The callback receives sanitized worker-monotonic arrival/progress evidence;
    its event count proves output arrival only, never native token throughput.
    Splitting complete SSE frames before delegating preserves the tail even when
    one network read contains more events than the metadata limit.
    """
    def __init__(self, started, *, capture_events=True, progress_callback=None):
        super().__init__(started, capture_events=capture_events)
        self.progress_callback = progress_callback
        self._framing_pending = b""
        self._evicted = 0
        self.output_event_count = 0
        self.native_predicted_n = self.native_predicted_ms = None
        self.native_progress_valid = True

    def feed(self, chunk, arrived):
        if self.error:
            return
        try:
            self._framing_pending += chunk
            trailing = b"\r" if self._framing_pending.endswith(b"\r") else b""
            source = self._framing_pending[:-1] if trailing else self._framing_pending
            parts = source.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n\n")
            self._framing_pending = parts[-1] + trailing
            if len(self._framing_pending) > client.MAX_RESPONSE:
                raise fixtures.HarnessError("oversized diagnostic event")
            for part in parts[:-1]:
                data = b"\n".join(line[5:].lstrip(b" ") for line in part.split(b"\n")
                                    if line.startswith(b"data:"))
                is_event = bool(data and data != b"[DONE]")
                if self.capture_events and is_event and len(self.event_arrivals) >= client.MAX_EVENT_ARRIVALS:
                    # Preserve the first half plus the newest second half.
                    self.event_arrivals.pop(client.MAX_EVENT_ARRIVALS // 2)
                    self._evicted += 1
                previous_events = self.events
                super().feed(part + b"\n\n", arrived)
                if self.error:
                    break
                if self.events > previous_events and self.capture_events:
                    row = self.event_arrivals[-1]
                    if any(row.get("has_" + kind) for kind in ("content", "reasoning", "tool")):
                        self.output_event_count += 1
                    native = row.get("native_timings") or {}
                    n, ms = native.get("predicted_n"), native.get("predicted_ms")
                    if type(n) is int and n > 0 and type(ms) in (int, float) and math.isfinite(ms) and ms >= 0:
                        if (self.native_predicted_n is not None and
                                (n < self.native_predicted_n or ms < self.native_predicted_ms
                                 or n == self.native_predicted_n and ms != self.native_predicted_ms)):
                            self.native_progress_valid = False
                        self.native_predicted_n, self.native_predicted_ms = n, ms
            if self.progress_callback is not None:
                self.progress_callback(self.progress(arrived))
        except Exception:
            # A callback/reporting bug must not abort transport drain.
            self.error = True

    def progress(self, arrived):
        return {"monotonic_s": arrived, "request_started_monotonic_s": self.started,
                "first_output_monotonic_s": self.started + self.first_any if self.first_any is not None else None,
                "last_output_monotonic_s": self.started + self.last_any if self.last_any is not None else None,
                "output_event_count": self.output_event_count,
                "output_event_count_unit": "output-bearing SSE events, not native tokens",
                "native_predicted_n": self.native_predicted_n if self.native_progress_valid else None,
                "native_predicted_ms": self.native_predicted_ms if self.native_progress_valid else None,
                "done": self.done, "observer_status": "HARNESS_FAILURE" if self.error else "OK"}

    def summary(self):
        result = super().summary()
        result["native_progress_last"] = {
            "predicted_n": self.native_predicted_n if self.native_progress_valid else None,
            "predicted_ms": self.native_predicted_ms if self.native_progress_valid else None,
            "source": "native_cumulative_per_token_fields",
            "counter_regression": not self.native_progress_valid,
            "final_aggregate": False}
        if self.capture_events:
            receipt = result["event_arrivals"]
            receipt["dropped_events"] += self._evicted
            receipt["complete"] = receipt["complete"] and self._evicted == 0
            receipt["retention"] = "bounded_head_and_tail"
        return result


def validate_request(raw_body, count, configured_context, *, sample=None, synthetic=False):
    """Admit only exact PREP constructors and their final native count receipt."""
    if (not isinstance(raw_body, bytes) or type(configured_context) is not int
            or configured_context not in decode_diag.CAPACITIES):
        raise fixtures.HarnessError("invalid diagnostic body or configured capacity")
    body = protocol.strict_json_loads(raw_body)
    if (not isinstance(body, dict) or type(body.get("max_tokens")) is not int
            or body.get("model") != "bench-glm-5.3"):
        raise fixtures.HarnessError("invalid diagnostic body")
    cap = body["max_tokens"]
    if cap == 4096:
        if sample is not None or configured_context not in (32768, 65536) or raw_body != decode_diag.long_body():
            raise fixtures.HarnessError("natural4096 must equal the frozen PREP body")
    else:
        if cap not in (32, 128, 256) or not isinstance(sample, dict):
            raise fixtures.HarnessError("bounded diagnostic fixture required")
        try:
            expected = (decode_diag.short_body(sample, cap) if sample.get("kind") == "generation"
                        else decode_diag.schema_body(sample, cap))
        except (ValueError, KeyError, TypeError) as exc:
            raise fixtures.HarnessError("invalid diagnostic fixture") from exc
        if raw_body != expected:
            raise fixtures.HarnessError("diagnostic body differs from frozen constructor")
    checked = fixtures.validate_count(count, raw_body, configured_context, synthetic=synthetic)
    if checked["input_tokens"] + cap > configured_context:
        raise fixtures.HarnessError("diagnostic input plus output cap exceeds configured context")
    proof = {field: checked[field] for field in COUNT_FIELDS}
    if "count_body_sha256" in checked or not synthetic:
        count_body = {key: value for key, value in body.items() if key not in ("stream", "stream_options")}
        normalization = {"removed_fields": [key for key in ("stream", "stream_options") if key in body]}
        if (checked.get("count_body_sha256") != fixtures.digest(fixtures.canonical(count_body))
                or checked.get("count_transport_normalization") != normalization):
            raise fixtures.HarnessError("count transport differs from final body normalization")
        proof.update(count_body_sha256=checked["count_body_sha256"], count_transport_normalization=normalization)
    return body, proof


def _append_summary(path, row):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "ab") as handle:
        handle.write(fixtures.canonical(row) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def run_decode_request(raw_body, transport, *, sample_id, private_dir, summary_path,
                       count, configured_context, sample=None, timeout=7200,
                       clock=time.monotonic, redact=None, capture_events=True,
                       observer_factory=DiagnosticObserver, progress_callback=None,
                       synthetic=False):
    """One counted, admitted request through the existing drain-first capture.

    The caller bounds timeout to the immutable stage remainder and owns all live
    gates. This function preserves failures and partial rows. Missing counters
    stay unavailable; native cumulative progress is reported separately from
    final aggregate counters and never inferred from SSE event counts.
    """
    body, proof = validate_request(raw_body, count, configured_context,
                                   sample=sample, synthetic=synthetic)
    if (not isinstance(sample_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", sample_id)
            or type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 7200
            or type(capture_events) is not bool or (progress_callback is not None and not capture_events)):
        raise fixtures.HarnessError("invalid diagnostic request identity, timeout or capture")
    root = Path(private_dir)
    if not root.is_dir() or root.is_symlink() or root.stat().st_mode & 0o077:
        raise fixtures.HarnessError("private artifact directory must exist with mode 0700")
    artifact = Path(tempfile.mkdtemp(prefix=sample_id + "-", dir=root))
    count_raw = fixtures.canonical(count)
    client._write_private(artifact / "count.json", count_raw)
    capture_path = artifact / "capture-summary.jsonl"

    def observe(started, **kwargs):
        if progress_callback is not None:
            kwargs["progress_callback"] = progress_callback
        return observer_factory(started, **kwargs)

    interrupted = None
    try:
        result = client._capture_request(raw_body, transport, sample_id=sample_id,
            private_dir=artifact, summary_path=capture_path, timeout=timeout, clock=clock,
            redact=redact, observer_factory=observe, capture_events=capture_events)
    except BaseException as error:
        # _capture_request saves a row before propagating process interruption.
        # Publish that row as well, then preserve the original interruption.
        if not capture_path.is_file():
            raise
        row = protocol.strict_json_loads(capture_path.read_bytes().splitlines()[-1])
        result = {"summary": row, "parsed": None,
                  "private_request_path": str(artifact / (sample_id + ".request.json")),
                  "private_response_path": str(artifact / (sample_id + ".response.sse"))}
        interrupted = error
    row = result["summary"]
    counters = row.get("counters") or {}
    row["counters"] = {field: counters.get(field) for field in COUNTERS}
    missing = [field for field in NATIVE_REQUIRED if row["counters"][field] is None]
    row.update({"diagnostic_scope": "GLM-DECODE-DIAG-20260920",
                "artifact_id": artifact.name, "count_sha256": fixtures.digest(count_raw),
                "count_binding": proof, "requested_output_cap": body["max_tokens"],
                "configured_context": configured_context,
                "finish_reason": (result.get("parsed") or {}).get("finish_reason"),
                "counter_status": ("AVAILABLE" if not missing else "PARTIAL"
                                   if any(value is not None for value in row["counters"].values()) else "UNAVAILABLE"),
                "missing_native_counters": missing,
                "tokens_from_event_count": False})
    try:
        _append_summary(summary_path, row)
    except Exception:
        row["report_errors"].append("diagnostic_summary_write_failed")
    result["private_count_path"] = str(artifact / "count.json")
    if interrupted is not None:
        raise interrupted
    return result
