"""Exact diagnostic scope and 1K allocation seam; synthetic/offline only."""
import copy
import json
from pathlib import Path
import shlex
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark import accounting, allocation, profiles
from benchmark.fixtures import HarnessError, canonical
from tests import test_benchmark_allocation as allocation_fixtures
from tests import test_glmrepair_host as limit_fixtures


class DecodeDiagProfiles(unittest.TestCase):
    def arm(self):
        return {"scope": "glm-decode-diag", "campaign": profiles.GLM_DECODE_DIAG_CAMPAIGN,
                "manifests": [profiles.glm_decode_diag_manifest(n) for n in (1024, 32768, 65536)],
                "trial_plan": profiles.trial_order("glm-decode-diag")}

    def proof(self, capacity):
        fixture = allocation_fixtures.Allocation()
        manifest = profiles.glm_decode_diag_manifest(capacity)
        raw = fixture.glm_log().replace("4096", str(capacity)).replace("lid_nodes=78", "lid_nodes=21")
        raw = raw.replace("195035136", str(95232 * capacity))
        if capacity == 1024:
            raw = raw.replace("n_batch=2048", "n_batch=1024")
        parsed = allocation.parse_glm_log(raw)
        observed = fixture.observed(manifest)
        limits = limit_fixtures.GlmrepairHost()
        observed.update(container_memory_limits=limits.limits(), container_cpu_limits=limits.cpu_limits())
        return manifest, parsed, observed

    def test_only_context_and_campaign_identity_change_from_frozen_g1(self):
        frozen = profiles.glmrepair_manifest(profiles.GLMREPAIR_G1_CAMPAIGN)
        for capacity in (1024, 32768, 65536):
            manifest = profiles.glm_decode_diag_manifest(capacity)
            self.assertEqual(manifest["create_shell"], shlex.join(manifest["create_argv"]))
            restored = json.loads(json.dumps(manifest).replace(manifest["container_name"], frozen["container_name"])
                                  .replace(profiles.GLM_DECODE_DIAG_CAMPAIGN, profiles.GLMREPAIR_G1_CAMPAIGN))
            restored["configured_capacity"] = 4096
            for key in ("native_argv", "create_argv"):
                restored[key][restored[key].index("--ctx-size") + 1] = "4096"
            restored["create_shell"] = shlex.join(restored["create_argv"])
            self.assertEqual(restored, frozen)
            self.assertNotIn("--poll", manifest["native_argv"])  # Unchanged pinned default50.
        for capacity in (True, 1024.0, 4096, 16384, 131072, 524288, 1000000):
            with self.assertRaisesRegex(ValueError, "outside_scope"):
                profiles.glm_decode_diag_manifest(capacity)

    def test_scope_requires_exact_campaign_manifests_and_bounded_plan(self):
        arm = self.arm()
        self.assertEqual(profiles.validate_arm_scope(arm), "glm-decode-diag")
        trials = arm["trial_plan"]["trials"]
        self.assertEqual([(row["capacity"], row["case"], row["output_cap"]) for row in trials], [
            (1024, "load_warmup", 32), (1024, "short_control", 128),
            (32768, "load_warmup", 32), (32768, "short_control", 128),
            (65536, "load_warmup", 32), (65536, "short_control", 128),
            (65536, "near_full_replay", 256), (65536, "long_answer", 4096)])
        self.assertEqual(profiles.scope_placements("glm-decode-diag"), ("G1",))
        self.assertEqual(arm["trial_plan"]["measurement_budget_seconds"], 14400)
        self.assertEqual(arm["trial_plan"]["maximum_request_seconds"], 7200)
        variants = []
        for key, value in (("campaign", profiles.G1_LADDER_CAMPAIGN),
                           ("manifests", arm["manifests"][:-1]), ("manifests", arm["manifests"] * 2)):
            bad = copy.deepcopy(arm); bad[key] = value; variants.append(bad)
        bad = copy.deepcopy(arm); bad["manifests"][0]["native_argv"] += ["--poll", "0"]; variants.append(bad)
        bad = copy.deepcopy(arm); bad["trial_plan"]["trials"] += [trials[-1]]; variants.append(bad)
        bad = copy.deepcopy(arm); bad["trial_plan"]["trials"][-1]["output_cap"] = 8192; variants.append(bad)
        for bad in variants:
            with self.assertRaisesRegex(ValueError, "glm_decode_diag_exact_arm_scope_mismatch"):
                profiles.validate_arm_scope(bad)

    def test_native_count_opt_in_is_glm_only_and_does_not_expand_old_defaults(self):
        call = Mock()
        for capacity in (1024, 32768):
            with self.assertRaises(HarnessError):
                accounting.native_counter("bench-glm-5.3", capacity, call)
            self.assertTrue(callable(accounting.native_counter("bench-glm-5.3", capacity, call, scope="glm-decode-diag")))
            with self.assertRaises(HarnessError):
                accounting.native_counter("bench-qwen3.8-27b", capacity, call,
                                          scope="glm-decode-diag", qwen_template_sha256="a" * 64)
        for capacity in (4096, 16384, 131072, 262144):
            with self.assertRaises(HarnessError):
                accounting.native_counter("bench-glm-5.3", capacity, call, scope="glm-decode-diag")
        with self.assertRaises(HarnessError):
            accounting.native_counter("bench-glm-5.3", 65536, call, scope="unknown")
        call.assert_not_called()
        self.assertEqual(profiles.scope_capacities("g1-ladder"), (16384, 65536))
        self.assertEqual(profiles.scope_capacities("g1-only"), (4096, 16384, 65536))

    def test_short_native_count_requires_effective_capacity_and_exact_final_body(self):
        raw = canonical({"model": "bench-glm-5.3", "messages": [{"role": "user", "content": "Explain pressure."}],
                         "max_tokens": 128, "temperature": 1, "seed": 1729,
                         "reasoning_effort": "low", "stream": True, "stream_options": {"include_usage": True}})
        for capacity in (1024, 32768, 65536):
            props = {"model_alias": "bench-glm-5.3", "is_sleeping": False, "total_slots": 1,
                     "default_generation_settings": {"n_ctx": capacity}, "chat_template": "synthetic"}
            call = Mock(side_effect=[props, {"prompt": "synthetic rendered request"}, {"tokens": [1, 2, 3]}])
            result = accounting.native_counter("bench-glm-5.3", capacity, call, scope="glm-decode-diag")(raw)
            self.assertEqual(result["configured_context"], capacity)
            self.assertEqual(result["input_tokens"], 3)
            self.assertEqual(result["body_sha256"], accounting.digest(raw))
            rendered_body = call.call_args_list[1].args[1]
            self.assertEqual(rendered_body, {key: value for key, value in json.loads(raw).items()
                                             if key not in ("stream", "stream_options")})
            props["default_generation_settings"]["n_ctx"] = 4096
            with self.assertRaisesRegex(HarnessError, "properties differ"):
                accounting.native_counter("bench-glm-5.3", capacity, Mock(return_value=props), scope="glm-decode-diag")(raw)

    def test_native_batch_clamp_is_exact_manifest_only(self):
        for capacity in (1024, 32768, 65536):
            manifest, parsed, observed = self.proof(capacity)
            self.assertEqual(allocation.allocation_gate(manifest, parsed, observed)["status"], "ALLOCATION_PROOF_ACCEPTED")
            for field, value in (("n_batch", 2048 if capacity == 1024 else 1024),
                                 ("cache_bytes", {"CUDA0": 95232 * capacity - 1}), ("fa_nodes", 77), ("lid_nodes", 78)):
                bad = copy.deepcopy(parsed); bad["native"][field] = value
                self.assertEqual(allocation.allocation_gate(manifest, bad, observed)["status"], "STOP_ALLOCATION_PROOF")
        manifest, parsed, observed = self.proof(1024)
        for key, value in (("campaign", "benchrun-unreviewed"), ("guest_cpuset", "0-111")):
            bad = copy.deepcopy(manifest); bad[key] = value
            result = allocation.allocation_gate(bad, parsed, observed)
            self.assertIn("native_batch_mismatch", result["reasons"])
        bad = copy.deepcopy(manifest); bad["native_argv"] += ["--poll", "0"]
        self.assertIn("glm_decode_diag_exact_manifest_required", allocation.allocation_gate(bad, parsed, observed)["reasons"])

    def test_diag_requires_no_swap_cpu_limits_and_gpu_reserve_without_caller_flags(self):
        manifest, parsed, observed = self.proof(1024)
        for section, field, value in (("container_memory_limits", "cgroup_memory_swap_max", "1"),
                                       ("container_cpu_limits", "cgroup_cpuset_cpus_effective", "0-111"),
                                       ("container_cpu_limits", "cgroup_cpu_max", "9600000 100000"),
                                       ("gpu_free_bytes", manifest["gpu_uuids"][0], 16 * allocation.GIB - 1)):
            bad = copy.deepcopy(observed); bad[section][field] = value
            self.assertEqual(allocation.allocation_gate(manifest, parsed, bad)["status"], "STOP_ALLOCATION_PROOF")


if __name__ == "__main__":
    unittest.main()
