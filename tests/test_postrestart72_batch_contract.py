"""Focused offline REAL72 body, native-count and sealed arm contract checks."""
import ast
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark import cpu_budget_profiles as profile, decode_diag, decode_request, fixtures, g1_ladder, runner
from benchmark import postrestart72_batch as batch, postrestart72_followup as followup


class SealedBatchContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payloads = {}
        for identifier in batch.REQUEST_IDS:
            if identifier == batch.SCIENCE_ID:
                cls.payloads[identifier] = batch.science_sample(), decode_diag.long_body()
                continue
            preset = followup.PRESETS[batch.PRESETS[identifier]]
            model = "bench-glm-5.3" if batch.REQUEST_PLACEMENTS[identifier] == "G1" else "bench-qwen3.8-27b"
            sample = fixtures.build_sample(model, preset["records"], preset["seed"], "fresh-contract-" + identifier)
            raw = g1_ladder.body_bytes(sample) if model == "bench-glm-5.3" else fixtures.serialize_validate(sample)
            cls.payloads[identifier] = sample, raw

    @staticmethod
    def count(identifier, raw, input_tokens=None):
        body = json.loads(raw)
        count = {"source": "native_apply_template_tokenize", "body_sha256": fixtures.digest(raw),
                 "configured_context": 480000, "template_sha256": "c" * 64, "token_ids_sha256": "d" * 64,
                 "input_tokens": input_tokens if input_tokens is not None else
                     {"B1-G4K": 3546, "B1-Qnear480K": 479487, "B2-Gscience": 65,
                      "B3-G65008": 65008, "B3-Qnear480K": 479487}[identifier]}
        if identifier == batch.SCIENCE_ID:
            count.update(count_body_sha256=fixtures.digest(fixtures.canonical(
                {key: value for key, value in body.items() if key not in ("stream", "stream_options")})),
                count_transport_normalization={"removed_fields": ["stream", "stream_options"]})
        return count

    def jobs(self):
        jobs = []
        for identifier in batch.REQUEST_IDS:
            sample, raw = self.payloads[identifier]
            counter = Mock(return_value=self.count(identifier, raw))
            job = batch.prepare_job(identifier, raw, sample, "owned-" + batch.REQUEST_PLACEMENTS[identifier], counter,
                campaign=profile.POSTRESTART_BATCH_CAMPAIGN, templates={"G1": "c" * 64, "Q1": "c" * 64},
                session_id="fresh-batch-session")
            counter.assert_called_once_with(raw)
            self.assertEqual(job["raw"], raw)
            jobs.append(job)
        return jobs

    def test_exact_five_bodies_caps_and_case_order_no_extra_jobs(self):
        self.assertEqual(batch.CASES, (("B1-G4K", "B1-Qnear480K"), ("B2-Gscience",),
                                      ("B3-G65008", "B3-Qnear480K")))
        plan = profile.postrestart_trial_order(profile.POSTRESTART_BATCH_MODE)
        self.assertEqual([row["id"] for row in plan["trials"]], list(batch.REQUEST_IDS))
        self.assertEqual([row["output_cap"] for row in plan["trials"]], [256, 256, 4096, 256, 256])
        self.assertEqual([json.loads(raw)["max_tokens"] for _, raw in self.payloads.values()], [256, 256, 4096, 256, 256])
        self.assertEqual(plan["loads"], 2)
        self.assertEqual(plan["initial_measured_requests"], 5)
        self.assertEqual(plan["warmup"]["output_cap"], 32)
        self.assertFalse(plan["warmup"]["performance_gate"])
        self.assertNotIn("preliminary_gate", plan)
        self.assertEqual((plan["maximum_request_seconds"], plan["measurement_budget_seconds"]), (7200, 21600))
        self.assertFalse(plan["clock_includes_preparation"])
        self.assertEqual(batch.BATCH_PLAN_SHA256, fixtures.digest(fixtures.canonical(plan)))
        jobs = self.jobs()
        self.assertEqual(sum(job["generation"] for job in jobs), 1)
        for identifier, (sample, raw) in self.payloads.items():
            self.assertEqual(batch.validate_body(identifier, raw), sample)
            body = json.loads(raw)
            if identifier != batch.SCIENCE_ID:
                for bad_cap in (32, 64, 128, 512, 4096):
                    with self.subTest(identifier=identifier, cap=bad_cap), self.assertRaises(ValueError):
                        batch.validate_body(identifier, fixtures.canonical({**body, "max_tokens": bad_cap}), sample)
        with self.assertRaises(ValueError):
            batch.bind_jobs(jobs + jobs[:1], source_commit="a" * 40, session_id="fresh-batch-session")

    def test_scientific_exact_bytes_narrow_480000_count_legacy_validator_unchanged(self):
        sample, raw = self.payloads[batch.SCIENCE_ID]
        self.assertEqual(fixtures.digest(raw), batch.SCIENCE_BODY_SHA256)
        body = json.loads(raw)
        self.assertEqual(body["messages"], [{"role": "user", "content": decode_diag.QUESTION}])
        self.assertEqual(set(body), {"model", "messages", "max_tokens", "temperature", "seed",
                                    "reasoning_effort", "stream", "stream_options", "timings_per_token"})
        self.assertTrue(body["timings_per_token"])
        for altered in (raw + b"\n", fixtures.canonical({**body, "response_format": g1_ladder.SCHEMA}),
                        fixtures.canonical({**body, "ignore_eos": True}),
                        fixtures.canonical({**body, "max_tokens": 256})):
            with self.assertRaisesRegex(ValueError, "scientific"):
                batch.validate_body(batch.SCIENCE_ID, altered, sample)
        count = self.count(batch.SCIENCE_ID, raw)
        self.assertEqual(batch.validate_count(batch.SCIENCE_ID, raw, count, template_sha256="c" * 64), count)
        with self.assertRaisesRegex(fixtures.HarnessError, "configured capacity"):
            decode_request.validate_request(raw, count, 480000)
        for update in ({"input_tokens": 475905}, {"configured_context": 65536},
                       {"body_sha256": "f" * 64}, {"template_sha256": "e" * 64},
                       {"count_body_sha256": "e" * 64}, {"count_transport_normalization": {}},
                       {"source": "synthetic_offline"}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                batch.validate_count(batch.SCIENCE_ID, raw, {**count, **update}, template_sha256="c" * 64)

    def test_five_source_session_manifest_body_count_bindings_and_nonce_freshness(self):
        jobs = self.jobs()
        binding = batch.bind_jobs(jobs, source_commit="a" * 40, session_id="fresh-batch-session")
        self.assertEqual([row["request_id"] for row in binding["requests"]], list(batch.REQUEST_IDS))
        self.assertEqual([row["count_sha256"] for row in binding["requests"]],
                         [fixtures.digest(fixtures.canonical(job["count"])) for job in jobs])
        for mutate in (lambda v: v.update(campaign=profile.POSTRESTART_WARM_CAMPAIGN),
                       lambda v: v.update(source_commit="b" * 40), lambda v: v.update(session_id="other-session"),
                       lambda v: v.update(batch_plan_sha256="b" * 64), lambda v: v["requests"].reverse(),
                       lambda v: v["requests"].pop(),
                       lambda v: v["requests"][2].update(request_sha256="f" * 64),
                       lambda v: v["requests"][0].update(manifest_sha256="f" * 64)):
            bad = copy.deepcopy(binding); mutate(bad)
            with self.assertRaises(ValueError):
                batch.validate_binding(bad, source_commit="a" * 40, session_id="fresh-batch-session")
        # Reusing the first Q body for the second Q case is not fresh, even with
        # recomputed matching count and descriptor hashes.
        repeated = copy.deepcopy(jobs)
        repeated[4].update(raw=jobs[1]["raw"], sample=jobs[1]["sample"], count=jobs[1]["count"])
        with self.assertRaisesRegex(ValueError, "fresh_prefixes"):
            batch.bind_jobs(repeated, source_commit="a" * 40, session_id="fresh-batch-session")

    def test_fixed_campaign_actual_shared_stage_and_unchanged_legacy_modes(self):
        campaign = profile.postrestart_campaign(profile.POSTRESTART_BATCH_MODE)
        self.assertEqual(campaign, "benchrun-p72b-20260920")
        contract = [node for node in ast.walk(ast.parse(runner.STAGE)) if isinstance(node, ast.Assert)
                    and any(isinstance(part, ast.Name) and part.id == "campaign" for part in ast.walk(node))]
        self.assertEqual(len(contract), 1)
        exec(compile(ast.Module(body=contract, type_ignores=[]), "actual-STAGE", "exec"), {"campaign": campaign})
        arm = {"scope": profile.POSTRESTART_SCOPE, "campaign": campaign, "mode": profile.POSTRESTART_BATCH_MODE,
               "trial_plan": profile.postrestart_trial_order(profile.POSTRESTART_BATCH_MODE),
               "manifests": profile.postrestart_manifests(campaign)}
        profile.validate_postrestart_arm_scope(arm)
        for now, old in zip(arm["manifests"], profile.postrestart_manifests()):
            for field in ("image", "model", "gpu_uuids", "native_argv", "configured_capacity", "ram_cap_bytes",
                          "resource_policy", "guest_cpuset", "guest_mems_allowed"):
                self.assertEqual(now[field], old[field], field)
        measured = profile.postrestart_trial_order()
        warm = profile.postrestart_trial_order(profile.POSTRESTART_WARM_ONLY_MODE)
        self.assertEqual([row["id"] for row in measured["trials"]], ["P-G4K", "P-G65008", "P-Qnear480K"])
        self.assertEqual(measured["preliminary_gate"]["client_total_seconds_maximum"], 180)
        self.assertEqual(warm["trials"], [])
        self.assertEqual(warm["initial_measured_requests"], 0)
        for update in ({"mode": profile.POSTRESTART_MEASURED_MODE}, {"campaign": profile.POSTRESTART_WARM_CAMPAIGN},
                       {"trial_plan": measured}, {"manifests": profile.postrestart_manifests()}):
            bad = copy.deepcopy(arm); bad.update(update)
            with self.assertRaises(ValueError): profile.validate_postrestart_arm_scope(bad)


if __name__ == "__main__":
    unittest.main()
