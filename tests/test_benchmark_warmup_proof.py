"""Synthetic/offline pinned-null-usage replay through the integrated load warmup."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import test_benchmark_runner as integrated
from benchmark import client, fixtures, profiles, warmup
from benchmark.host import LinuxHost


class WarmupProof(unittest.TestCase):
    def setup_case(self, directory, *, disable=True, observed=True, prompt=2380, completion=52):
        path = Path(directory)
        manifest = profiles.command_manifest("Q1", 4096)
        c, host, requests = integrated.IntegratedRunner().setup_case(path, [manifest])
        original_call = host.call
        def call(op, **args):
            value = original_call(op, **args)
            if op == "readiness":
                value["server_facts"] = {"disable_radix_cache": disable}
                value["observed"] = {"native_argv": manifest["native_argv"] if observed else []}
            return value
        host.call = call
        original_transport = c.transport_factory
        def transport(url, key):
            def send(raw, timeout):
                for chunk in original_transport(url, key)(raw, timeout):
                    if b'"usage"' in chunk:
                        value = json.loads(chunk.removeprefix(b"data: "))
                        value.pop("timings", None)
                        value["usage"] = {"prompt_tokens": prompt, "completion_tokens": completion,
                                          "total_tokens": prompt + completion, "prompt_tokens_details": None}
                        chunk = b"data: " + fixtures.canonical(value) + b"\n\n"
                    yield chunk
            return send
        c.transport_factory = transport
        host.call("begin")
        return c, host, requests, manifest

    def test_integrated_null_details_uses_validated_policy_without_native_counter_invention(self):
        with tempfile.TemporaryDirectory() as directory:
            c, host, requests, manifest = self.setup_case(directory)
            cid = c.loaded(manifest)
            records = [json.loads(line) for line in (Path(directory) / "results.jsonl").read_text().splitlines()]
            warm = next(row for row in records if row["type"] == "warm_idle")
            proof = warm["prefill_proof"]
            self.assertEqual(proof["source"], "derived_cache_disabled_prompt_tokens")
            self.assertEqual(proof["prefill_tokens"], 2380)
            self.assertIsNone(proof["native_evaluated_prompt_tokens"])
            self.assertIsNone(proof["native_cached_tokens"])
            self.assertIsNone(warm["evaluated_prompt_tokens"])
            self.assertTrue(proof["cache_policy"]["disable_radix_cache"])
            summary = json.loads((Path(directory) / "warmups.jsonl").read_text())
            self.assertIsNone(summary["counters"]["cached_tokens"])
            self.assertIsNone(summary["counters"]["evaluated_prompt_tokens"])
            self.assertEqual(summary["counters"]["prompt_tokens"], 2380)
            self.assertEqual(summary["counters"]["completion_tokens"], 52)
            self.assertEqual(warm["warmup_timing"], "discarded")
            self.assertIn("warmup-prefix-", requests[0]["messages"][0]["content"])
            self.assertIn(cid, c.active)

    def test_integrated_null_details_refuses_unvalidated_cache_policy_or_insufficient_prefill(self):
        for changes in ({"disable": False}, {"disable": None}, {"disable": "true"},
                        {"observed": False}, {"prompt": 2047}, {"completion": 0}):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory:
                c, host, _, manifest = self.setup_case(directory, **changes)
                with self.assertRaisesRegex(RuntimeError, "WARMUP_PREFILL_UNPROVED"):
                    c.loaded(manifest)
                self.assertFalse(any(op == "retire" for op, _ in host.events), "proof failure must not kill inference")
                self.assertEqual(host.events[-1][0], "request_end", "response drains and admission is released")

    def test_native_counter_provenance_is_distinct_from_derived_proof(self):
        manifest = profiles.command_manifest("Q1", 4096)
        counters = {"prompt_tokens": 3000, "cached_tokens": 10, "evaluated_prompt_tokens": None,
                    "completion_tokens": 52}
        proof = warmup.prefill_proof(counters, manifest, {})
        self.assertEqual(proof["prefill_tokens"], 2990)
        self.assertEqual(proof["source"], "derived_native_prompt_minus_cached")
        self.assertIsNone(counters["evaluated_prompt_tokens"])
        counters["evaluated_prompt_tokens"] = 2800
        self.assertEqual(warmup.prefill_proof(counters, manifest, {})["source"], "native_evaluated_prompt_tokens")

    def test_actual_host_allocation_exposes_observed_cache_policy_without_boolean_coercion(self):
        manifest = profiles.command_manifest("Q1", 4096)
        path = next(part.split("source=", 1)[1].split(",", 1)[0] for part in manifest["create_argv"]
                    if isinstance(part, str) and "target=/models" in part)
        cid = "a" * 64
        host = LinuxHost.__new__(LinuxHost)
        host.assert_idle = Mock()
        host.identity = Mock(return_value=({"Config": {"Image": manifest["image"]},
            "HostConfig": {"DeviceRequests": [{"DeviceIDs": manifest["gpu_uuids"]}]},
            "Mounts": [{"Source": path, "Destination": "/models", "RW": False}]}, None, []))
        host.load_manifests = {cid: manifest}
        host.write_bytes, host.write_json = Mock(), Mock()
        host.cuda_mapping = Mock(return_value=manifest["gpu_uuids"])
        host.telemetry = Mock(return_value={"gpus": [{"uuid": u, "free_bytes": 40 * 1024**3} for u in manifest["gpu_uuids"]]})
        host.manager, host.allocation_proofs, host.log_root = Mock(), {}, "/data/logs/synthetic-offline"
        raw = b"BENCHMARK_NATIVE_ARGV " + fixtures.canonical({"argv": manifest["native_argv"]}) + b"\n"
        for value in (True, False, None):
            with self.subTest(value=value), patch("benchmark.host.command", return_value=SimpleNamespace(stdout=raw, stderr=b"")), \
                 patch("benchmark.host.http_json", return_value={"server_args": {"disable_radix_cache": value}}), \
                 patch("benchmark.host.parse_qwen_log", return_value={}), \
                 patch("benchmark.host.allocation_gate", return_value={"status": "ALLOCATION_PROOF_ACCEPTED"}):
                result = host.allocation(cid)
            self.assertIs(result["server_facts"]["disable_radix_cache"], value)
            self.assertEqual(result["observed"]["native_argv"], manifest["native_argv"])

    def test_actual_reported_usage_shape_replay_keeps_unavailable_counters_null(self):
        # Exact user-reported counter values, replayed OFFLINE; no new live inference.
        usage = {"prompt_tokens": 74987, "completion_tokens": 52, "total_tokens": 75039,
                 "prompt_tokens_details": None}
        sample = fixtures.build_sample("bench-qwen3.8-27b", 32, "null-details-replay", "fresh-prefix")
        events = [{"model": "bench-qwen3.8-27b", "choices": [{"index": 0, "delta": {"content": "ok"}, "finish_reason": None}]},
                  {"model": "bench-qwen3.8-27b", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
                  {"model": "bench-qwen3.8-27b", "choices": [], "usage": usage}]
        def transport(raw, timeout):
            for event in events:
                yield b"data: " + fixtures.canonical(event) + b"\n\n"
            yield b"data: [DONE]\n\n"
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "private").mkdir(mode=0o700)
            response = client.run_request(fixtures.serialize_validate(sample), transport, sample_id="null-details",
                                          private_dir=Path(directory) / "private", summary_path=Path(directory) / "samples.jsonl")
        self.assertEqual(response["parsed"]["status"], "COMPLETE")
        counters = response["parsed"]["counters"]
        self.assertEqual(counters["prompt_tokens"], 74987)
        self.assertEqual(counters["completion_tokens"], 52)
        self.assertIsNone(counters["cached_tokens"])
        self.assertIsNone(counters["evaluated_prompt_tokens"])


if __name__ == "__main__":
    unittest.main()
