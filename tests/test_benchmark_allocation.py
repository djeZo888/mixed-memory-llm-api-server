"""Synthetic/offline allocation parser/admission tests. No models or GPU calls."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark import allocation as a
from benchmark import profiles


class Allocation(unittest.TestCase):
    def observed(self, manifest):
        return {"image_ref": manifest["image"], "model": manifest["model"],
                "native_argv": manifest["native_argv"], "device_request_uuids": manifest["gpu_uuids"],
                "cuda_uuid_order": manifest["gpu_uuids"], "raw_log_sha256": "a" * 64,
                "gpu_free_bytes": {u: 20 * a.GIB for u in manifest["gpu_uuids"]}}

    def glm_manifest(self, count=1):
        manifest = profiles.command_manifest("G" + str(count), 4096)
        return manifest

    def glm_log(self, count=1):
        lines = ["load_tensors: CPU model buffer size = 400000.00 MiB",
                 "load_tensors: offloaded 80/80 layers to GPU",
                 "srv initialize: initializing, n_slots = 1, n_ctx_slot = 4096",
                 "D3T_NATIVE_V1 kind=graph n_ctx=4096 n_ctx_seq=4096 n_seq_max=1 n_batch=2048 n_ubatch=512 flash_attn=1 fused_lid=1 lid_nodes=78 fa_nodes=78 no_alloc=0"]
        for i in range(count):
            lines.insert(1, f"load_tensors: CUDA{i} model buffer size = 20000.00 MiB")
            lines.append(f"D3T_NATIVE_V1 kind=compute backend=CUDA{i} bytes=1073741824")
        lines.append("D3T_NATIVE_V1 kind=compute backend=CUDA_Host bytes=2172727328")
        for i in range(count):
            lines.append(f"D3T_NATIVE_V1 kind=cache backend=CUDA{i} bytes=195035136")
        lines.append("D3T_NATIVE_V1 kind=end")
        return "\n".join(lines)

    def test_glm_exact_native_bytes_offload_and_one_two_gpu_admission(self):
        for count in (1, 2):
            parsed = a.parse_glm_log(self.glm_log(count))
            manifest = self.glm_manifest(count)
            self.assertEqual(parsed["native"]["cache_bytes"]["CUDA0"], 195035136)
            self.assertEqual(parsed["weights_mib_log_label"]["CPU"], 400000.0)
            self.assertEqual(parsed["offloaded_layers"], 80)
            self.assertEqual(parsed["host_compute_bytes"], {"CUDA_Host": 2172727328})
            self.assertEqual(parsed["host_workspace_bytes"], 2172727328)
            self.assertNotIn("CUDA_Host", parsed["native"]["compute_bytes"])
            self.assertEqual(a.allocation_gate(manifest, parsed, self.observed(manifest))["status"], "ALLOCATION_PROOF_ACCEPTED")

    def test_glm_exact_offload_counts_required_not_any_positive_count(self):
        parsed = a.parse_glm_log(self.glm_log())
        manifest = self.glm_manifest()
        bad = dict(parsed, offloaded_layers=1)
        self.assertIn("actual_gpu_offload_counts_mismatch", a.allocation_gate(manifest, bad, self.observed(manifest))["reasons"])
        bad = dict(parsed, total_layers=79)
        self.assertIn("actual_gpu_offload_counts_mismatch", a.allocation_gate(manifest, bad, self.observed(manifest))["reasons"])
        production = profiles.command_manifest("G1", 4096)
        self.assertEqual(production["glm_offload_expectation"]["evidence_status"], "REVIEWED_LOG_COUNT_SEMANTICS")
        self.assertEqual(production["glm_offload_expectation"]["offloaded_layers"], 80)
        production["glm_offload_expectation"] = {"offloaded_layers": None, "total_layers": None, "evidence_status": "HOLD_LOG_COUNT_SEMANTICS"}
        self.assertIn("reviewed_exact_offload_counts_missing", a.allocation_gate(production, parsed, self.observed(production))["reasons"])
        no_host = a.parse_glm_log(self.glm_log().replace("D3T_NATIVE_V1 kind=compute backend=CUDA_Host bytes=2172727328\n", ""))
        self.assertIsNone(no_host["host_workspace_bytes"])

    def test_glm_missing_or_malformed_proof_never_fabricates_zero(self):
        parsed = a.parse_glm_log("unrecognized log text")
        self.assertIsNone(parsed["native"])
        self.assertIsNone(parsed["offloaded_layers"])
        manifest = profiles.command_manifest("G1", 4096)
        self.assertEqual(a.allocation_gate(manifest, parsed, self.observed(manifest))["status"], "STOP_ALLOCATION_PROOF")
        self.assertEqual(a.parse_glm_log(self.glm_log().replace("kind=end", "kind=bad"))["parser_status"], "HARNESS_FAILURE")

    def qwen(self, tp=2):
        facts = {"tp_size": tp, "context_length": 16384, "max_total_tokens": 16384,
                 "max_total_num_tokens": 16384, "kv_cache_dtype": "bfloat16", "quantization": "fp8"}
        events = []
        for rank in range(tp):
            events += [{"phase": "weights_end", "tp_rank": rank, "memory_usage_gb_log_label": 14.66},
                       {"phase": "kv_allocated", "tp_rank": rank, "cache_tokens": 16384,
                        "k_size_gb_log_label": 0.25, "v_size_gb_log_label": 0.25}]
        return events, facts

    def test_qwen_rank_pool_semantics_and_log_units_preserved(self):
        for tp in (1, 2):
            parsed = a.parse_qwen_log_facts(*self.qwen(tp))
            manifest = profiles.command_manifest("Q" + str(tp), 16384)
            self.assertEqual(parsed["ranks"][0]["weights_gb_log_label"], 14.66)
            self.assertIsNone(parsed["ranks"][0]["workspace_bytes"])
            self.assertEqual(a.allocation_gate(manifest, parsed, self.observed(manifest))["status"], "ALLOCATION_PROOF_ACCEPTED")

    def test_qwen_missing_rank_or_pool_mismatch_refuses(self):
        events, facts = self.qwen()
        manifest = profiles.command_manifest("Q2", 16384)
        parsed = a.parse_qwen_log_facts(events[:-1], facts)
        self.assertEqual(a.allocation_gate(manifest, parsed, self.observed(manifest))["status"], "STOP_ALLOCATION_PROOF")
        facts["max_total_num_tokens"] = 4096
        parsed = a.parse_qwen_log_facts(events, facts)
        self.assertIn("actual_and_configured_pool_unproved", a.allocation_gate(manifest, parsed, self.observed(manifest))["reasons"])
        del events[0]["tp_rank"]
        self.assertEqual(a.parse_qwen_log_facts(events, facts)["parser_status"], "HARNESS_FAILURE")

    def test_qwen_raw_installed_source_phrases_rank_and_dtype(self):
        _, facts = self.qwen()
        lines = []
        for rank in range(2):
            lines += [f"[synthetic TP{rank}] Load weight end. elapsed=10.00 s, type=Qwen, avail mem=79.29 GB, mem usage=14.66 GB.",
                      f"[synthetic TP{rank}] KV Cache is allocated. dtype: torch.bfloat16, #tokens: 16384, K size: 0.25 GB, V size: 0.25 GB"]
        raw = "\n".join(lines)
        parsed = a.parse_qwen_log(raw, facts)
        manifest = profiles.command_manifest("Q2", 16384)
        self.assertEqual(a.allocation_gate(manifest, parsed, self.observed(manifest))["status"], "ALLOCATION_PROOF_ACCEPTED")
        self.assertEqual(a.parse_qwen_log(raw.replace("is allocated", "VA upper bound"), facts)["parser_status"], "HARNESS_FAILURE")
        self.assertEqual(a.parse_qwen_log(raw.replace("bfloat16", "float8"), facts)["parser_status"], "HARNESS_FAILURE")
        self.assertEqual(a.parse_qwen_log(raw.replace(" TP1", ""), facts)["parser_status"], "HARNESS_FAILURE")

    def test_uuid_mapping_and_reserve_must_be_measured(self):
        manifest = profiles.command_manifest("Q1", 16384)
        parsed = a.parse_qwen_log_facts(*self.qwen(1))
        observed = self.observed(manifest)
        observed["cuda_uuid_order"] = ["different-GPU"]
        observed["gpu_free_bytes"] = {manifest["gpu_uuids"][0]: 16 * a.GIB - 1}
        result = a.allocation_gate(manifest, parsed, observed)
        self.assertIn("cuda_ordinal_uuid_mapping_missing_or_mismatched", result["reasons"])
        self.assertTrue(any(reason.startswith("gpu_reserve_unproved") for reason in result["reasons"]))
        observed["gpu_free_bytes"] = {}
        self.assertEqual(a.allocation_gate(manifest, parsed, observed)["status"], "STOP_ALLOCATION_PROOF")


if __name__ == "__main__":
    unittest.main()
