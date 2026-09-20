"""Focused offline REAL72 body, native-count and sealed arm contract checks."""
import ast
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark import cpu_budget_profiles as profile, decode_diag, fixtures, g1_ladder, runner
from benchmark import postrestart72_batch as batch, postrestart72_followup as followup


class SealedBatchContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payloads = {}
        for identifier in batch.REQUEST_IDS:
            preset = followup.PRESETS[batch.PRESETS[identifier]]
            model = "bench-glm-5.3" if batch.REQUEST_PLACEMENTS[identifier] == "G1" else "bench-qwen3.8-27b"
            sample = fixtures.build_sample(model, preset["records"], preset["seed"], "fresh-contract-" + identifier)
            raw = g1_ladder.body_bytes(sample) if model == "bench-glm-5.3" else fixtures.serialize_validate(sample)
            cls.payloads[identifier] = sample, raw

    @staticmethod
    def count(identifier, raw, input_tokens=None):
        return {"source": "native_apply_template_tokenize", "body_sha256": fixtures.digest(raw),
                 "configured_context": 480000, "template_sha256": "c" * 64, "token_ids_sha256": "d" * 64,
                 "input_tokens": input_tokens if input_tokens is not None else
                     {"B3-G65008": 65008, "B3-Qnear480K": 479487}[identifier]}

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

    def test_exact_B3_pair_caps_and_case_order_no_extra_jobs(self):
        self.assertEqual(batch.CASES, (("B3-G65008", "B3-Qnear480K"),))
        self.assertEqual(batch.REQUEST_PLACEMENTS, {"B3-G65008": "G1", "B3-Qnear480K": "Q1"})
        plan = profile.postrestart_trial_order(profile.POSTRESTART_BATCH_MODE)
        self.assertEqual([row["id"] for row in plan["trials"]], list(batch.REQUEST_IDS))
        self.assertEqual([row["output_cap"] for row in plan["trials"]], [256, 256])
        self.assertEqual([json.loads(raw)["max_tokens"] for _, raw in self.payloads.values()], [256, 256])
        self.assertEqual([row["id"] for row in plan["cases"]], ["B3"])
        self.assertEqual(plan["rounds"][0]["qwen_max_requests"], 1)
        self.assertEqual(plan["loads"], 2)
        self.assertEqual(plan["warmup"]["per_model_per_load"], 1)
        self.assertEqual(plan["initial_measured_requests"], 2)
        self.assertEqual(plan["warmup"]["output_cap"], 32)
        self.assertFalse(plan["warmup"]["performance_gate"])
        self.assertNotIn("preliminary_gate", plan)
        self.assertEqual((plan["maximum_request_seconds"], plan["measurement_budget_seconds"]), (7200, 21600))
        self.assertFalse(plan["clock_includes_preparation"])
        self.assertEqual(batch.BATCH_PLAN_SHA256, fixtures.digest(fixtures.canonical(plan)))
        jobs = self.jobs()
        self.assertEqual(sum(job["generation"] for job in jobs), 0)
        for identifier, (sample, raw) in self.payloads.items():
            self.assertEqual(batch.validate_body(identifier, raw), sample)
            body = json.loads(raw)
            for bad_cap in (32, 64, 128, 512, 4096):
                with self.subTest(identifier=identifier, cap=bad_cap), self.assertRaises(ValueError):
                    batch.validate_body(identifier, fixtures.canonical({**body, "max_tokens": bad_cap}), sample)
        with self.assertRaises(ValueError):
            batch.bind_jobs(jobs + jobs[:1], source_commit="a" * 40, session_id="fresh-batch-session")

    def test_B1_B2_bodies_jobs_and_binding_rows_are_rejected(self):
        jobs = self.jobs()
        binding = batch.bind_jobs(jobs, source_commit="a" * 40, session_id="fresh-batch-session")
        for identifier in ("B1-G4K", "B1-Qnear480K", "B2-Gscience"):
            raw = decode_diag.long_body() if identifier == "B2-Gscience" else jobs[0]["raw"]
            with self.subTest(identifier=identifier):
                with self.assertRaisesRegex(ValueError, "batch_exact_request_required"):
                    batch.validate_body(identifier, raw)
                bad_jobs = copy.deepcopy(jobs); bad_jobs[0]["id"] = identifier
                with self.assertRaises(ValueError):
                    batch.bind_jobs(bad_jobs, source_commit="a" * 40, session_id="fresh-batch-session")
                bad_binding = copy.deepcopy(binding); bad_binding["requests"][0]["request_id"] = identifier
                with self.assertRaises(ValueError):
                    batch.validate_binding(bad_binding, source_commit="a" * 40, session_id="fresh-batch-session")

    def test_native_count_remains_exact_capacity_template_body_and_fixed_range(self):
        for identifier, (_, raw) in self.payloads.items():
            count = self.count(identifier, raw)
            self.assertEqual(batch.validate_count(identifier, raw, count, template_sha256="c" * 64), count)
            for update in ({"input_tokens": 1}, {"input_tokens": 479489}, {"configured_context": 65536},
                           {"body_sha256": "f" * 64}, {"template_sha256": "e" * 64},
                           {"source": "synthetic_offline"}):
                with self.subTest(identifier=identifier, update=update), self.assertRaises(ValueError):
                    batch.validate_count(identifier, raw, {**count, **update}, template_sha256="c" * 64)

    def test_two_source_session_manifest_body_count_bindings_and_nonce_freshness(self):
        jobs = self.jobs()
        binding = batch.bind_jobs(jobs, source_commit="a" * 40, session_id="fresh-batch-session")
        self.assertEqual([row["request_id"] for row in binding["requests"]], list(batch.REQUEST_IDS))
        self.assertEqual([row["count_sha256"] for row in binding["requests"]],
                         [fixtures.digest(fixtures.canonical(job["count"])) for job in jobs])
        for mutate in (lambda v: v.update(campaign=profile.POSTRESTART_WARM_CAMPAIGN),
                       lambda v: v.update(source_commit="b" * 40), lambda v: v.update(session_id="other-session"),
                       lambda v: v.update(batch_plan_sha256="b" * 64), lambda v: v["requests"].reverse(),
                       lambda v: v["requests"].pop(),
                       lambda v: v["requests"][1].update(request_sha256=v["requests"][0]["request_sha256"]),
                       lambda v: v["requests"][0].update(manifest_sha256="f" * 64)):
            bad = copy.deepcopy(binding); mutate(bad)
            with self.assertRaises(ValueError):
                batch.validate_binding(bad, source_commit="a" * 40, session_id="fresh-batch-session")
        # Both logical fixtures must have different leading prefixes even if
        # each body and count is otherwise internally consistent.
        repeated = copy.deepcopy(jobs)
        preset = followup.PRESETS[batch.PRESETS["B3-Qnear480K"]]
        sample = fixtures.build_sample("bench-qwen3.8-27b", preset["records"], preset["seed"], jobs[0]["sample"]["nonce"])
        raw = fixtures.serialize_validate(sample)
        repeated[1].update(raw=raw, sample=sample, count=self.count("B3-Qnear480K", raw))
        with self.assertRaisesRegex(ValueError, "fresh_prefixes"):
            batch.bind_jobs(repeated, source_commit="a" * 40, session_id="fresh-batch-session")

    def test_fixed_campaign_actual_shared_stage_and_unchanged_legacy_modes(self):
        campaign = profile.postrestart_campaign(profile.POSTRESTART_BATCH_MODE)
        self.assertEqual(campaign, "benchrun-p72b3-20260920")
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
        self.assertEqual([row["guest_cpuset"] for row in arm["manifests"]], ["0-71", "0-7"])
        self.assertEqual([row["guest_mems_allowed"] for row in arm["manifests"]], ["0-7", "0-7"])
        self.assertEqual([row["ram_cap_bytes"] for row in arm["manifests"]], [640 * 1024**3, 32 * 1024**3])
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
