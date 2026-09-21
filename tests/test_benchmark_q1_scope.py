"""Bounded Q1 continuation regression; all host/runtime I/O is synthetic."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tests import test_benchmark_runner as integrated
from tests import test_benchmark_host as host_tests

runner, profiles, fixtures = integrated.runner, integrated.profiles, integrated.fixtures

EPOCH = 1789826207.34127
DEADLINE = 1789847807.34127
EXECUTION = {"clock": "UTC_wall_seconds_first_staging_maintenance", "start_epoch": EPOCH}
CASES = ["Q1-4096-retrieval", "Q1-16384-retrieval", "Q1-16384-anchor",
         "Q1-16384-generation", "Q1-65536-retrieval"]


def saved_fixtures():
    """Synthetic saved Q2 fixtures, using the existing mock native counter."""
    saved = {}
    for capacity, kind, cap in [(4096, "retrieval", 256), (16384, "retrieval", 256), (16384, "generation", 512)]:
        key = f"bench-qwen3.8-27b-{capacity}-{kind}"
        saved[key] = fixtures.build_sample("bench-qwen3.8-27b", (capacity-cap-256-80)//15,
            hashlib.sha256(key.encode()).hexdigest()[:24], "saved-Q2-prefix", kind=kind, output_cap=cap)
    return saved


class Q1Scope(unittest.TestCase):
    def setup_case(self, path):
        runner.save(path / "execution.json", EXECUTION)
        runner.save(path / "private/fixtures.json", saved_fixtures())
        sha = runner.arm(path, "benchrun-20260919", "q1-only")
        armed = runner.load_arm(path, sha)
        campaign, host, requests = integrated.IntegratedRunner().setup_case(path, armed["manifests"])
        campaign.armed = armed
        host.budget.clock = lambda: EPOCH
        host.budget.start("maintenance")
        host.budget.clock = lambda: EPOCH + 600
        return campaign, host, requests, sha

    def test_q1_loop_exact_cases_warmups_frozen_recount_and_no_excluded_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            c, host, requests, _ = self.setup_case(path)
            original_epoch = (path / "execution.json").read_bytes()
            frozen = copy.deepcopy(c.fixture_cache)
            with patch.object(c, "mixed", side_effect=AssertionError("mixed forbidden")), \
                    patch.object(fixtures, "matched_sample", wraps=fixtures.matched_sample) as matched, \
                    patch.object(fixtures, "fit_sample", wraps=fixtures.fit_sample) as fit:
                c.run(resume=True)
            self.assertEqual(list(c.progress["completed"]), CASES)
            self.assertTrue(all(row["status"] == "PASS" for row in c.progress["completed"].values()))
            self.assertEqual(c.progress["phase"], "RESTORED_PENDING_WORKER_VERIFICATION")
            loads = [host.manifests[args["manifest_sha256"]] for op, args in host.events if op == "load"]
            self.assertEqual([(m["placement"], m["configured_capacity"]) for m in loads],
                             [("Q1", 4096), ("Q1", 16384), ("Q1", 65536)])
            self.assertTrue(all(m["guest_cpuset"] == "96-111" and m["guest_cpu_count"] == 16
                                and len(m["gpu_uuids"]) == 1 and not m["mixed"] for m in loads))
            self.assertEqual(len(requests), 8)  # Three discarded warmups plus five measurements.
            self.assertEqual(sum("warmup-prefix-" in r["messages"][0]["content"] for r in requests), 3)
            self.assertEqual(sum(r["max_tokens"] == 512 for r in requests), 1)
            self.assertTrue(all(r["model"] == "bench-qwen3.8-27b" and not r.get("tools") for r in requests))
            self.assertNotIn("admit_mixed", [op for op, _ in host.events])
            self.assertEqual(matched.call_count, 4)
            measured_fits = [call for call in fit.call_args_list if call.args[2] != "warmup-only-seed"]
            self.assertEqual(len(measured_fits), 1)
            self.assertEqual(measured_fits[0].args[1], 65536)
            nonces = [call.args[1] for call in matched.call_args_list]
            self.assertEqual(len(set(nonces)), 4)
            self.assertNotIn("saved-Q2-prefix", nonces)
            for identity in CASES[:4]:
                row = c.progress["completed"][identity]
                self.assertEqual(row["fixture_sha256"], row["count"]["matched_fixture_sha256"])
                self.assertGreater(row["count"]["input_tokens"], 0)
            after = json.loads((path / "private/fixtures.json").read_bytes())
            self.assertEqual({k: after[k] for k in frozen}, frozen)
            self.assertEqual(len(after), 4)  # Only 64K is newly fitted/frozen.
            self.assertEqual((path / "execution.json").read_bytes(), original_epoch)
            self.assertEqual(host.budget.data["started_at"], EPOCH)
            self.assertEqual(host.budget.data["started_at"] + host.budget.data["budget_seconds"], DEADLINE)

    def test_scope_and_exact_plan_rejected_before_host_work(self):
        with tempfile.TemporaryDirectory() as directory:
            c, host, _, _ = self.setup_case(Path(directory))
            original = copy.deepcopy(c.armed)
            bad_arms = []
            for placement, capacity in [("Q2", 4096), ("G1", 4096), ("Q1", 16384)]:
                bad = copy.deepcopy(original)
                bad["manifests"].append(profiles.command_manifest(placement, capacity))
                bad_arms.append(bad)
            for field, value in [("scope", "unknown"), ("trial_plan", profiles.trial_order())]:
                bad_arms.append({**original, field: value})
            for bad in bad_arms:
                c.armed = bad
                with self.assertRaises(ValueError):
                    c.run(resume=True)
            self.assertEqual(host.events, [])

    def test_new_failures_still_stop_restore_and_do_not_skip_forward(self):
        for verdict in ("MODEL_INCORRECT", "STOP_OOM", "HARNESS_FAILURE"):
            with self.subTest(verdict=verdict), tempfile.TemporaryDirectory() as directory:
                c, host, _, _ = self.setup_case(Path(directory))
                with patch.object(c, "trial", return_value={"status": verdict}):
                    with self.assertRaisesRegex(RuntimeError, "stopped_for_review"):
                        c.run(resume=True)
                self.assertEqual(len([op for op, _ in host.events if op == "load"]), 1)
                self.assertEqual(host.events[-1][0], "restore")
                self.assertEqual(c.progress["skipped_after_stop"], CASES)
                stop = next(json.loads(s) for s in (Path(directory) / "results.jsonl").read_text().splitlines()
                            if json.loads(s)["type"] == "stop")
                self.assertEqual(stop["mixed_pending"], [])
                c.progress["completed"] = {CASES[0]: {"status": verdict}}
                host.events.clear()
                with self.assertRaisesRegex(RuntimeError, "failed_measurement"):
                    c.run(resume=True)
                self.assertEqual(host.events, [])

    def test_q1_requires_saved_fixture_no_refitting(self):
        with tempfile.TemporaryDirectory() as directory:
            c, host, _, _ = self.setup_case(Path(directory))
            cid = c.loaded(c.armed["manifests"][0])
            c.fixture_cache.clear()
            with patch.object(fixtures, "fit_sample") as fit:
                with self.assertRaisesRegex(RuntimeError, "saved_matched_fixture"):
                    c.prepare_trial(cid, CASES[0])
            fit.assert_not_called()

    def test_epoch_and_resume_required_before_keys_staging_and_main_retains_epoch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            _, _, _, sha = self.setup_case(path)
            argv = ["run", "--state", directory, "--reviewed-arm-sha256", sha,
                    "--inference-key-file", "synthetic", "--control-key-file", "synthetic"]
            epoch_bytes = (path / "execution.json").read_bytes()
            with patch("runtime.sglang38_file_auth.read_key") as key, patch.object(runner, "SSHHost") as ssh:
                with self.assertRaises(SystemExit):
                    runner.main(argv)
                key.assert_not_called(); ssh.assert_not_called()
                runner.save(path / "execution.json", {**EXECUTION, "start_epoch": EPOCH + 1})
                with self.assertRaisesRegex(ValueError, "epoch_changed"):
                    runner.main([*argv, "--resume"])
                key.assert_not_called(); ssh.assert_not_called()
                (path / "execution.json").unlink()
                with self.assertRaises(FileNotFoundError):
                    runner.main([*argv, "--resume"])
                self.assertFalse((path / "execution.json").exists())
            (path / "execution.json").write_bytes(epoch_bytes)
            fake_host = Mock()
            with patch("runtime.sglang38_file_auth.read_key", return_value="synthetic"), \
                    patch.object(runner.os, "geteuid", return_value=501), \
                    patch.object(runner, "SSHHost", return_value=fake_host) as ssh, \
                    patch.object(runner, "Campaign") as campaign, \
                    patch("benchmark.worker_verify.verify", return_value={}):
                self.assertEqual(runner.main([*argv, "--resume"]), 0)
                self.assertEqual(ssh.call_args.args[0]["runtime"], EXECUTION)
                campaign.return_value.run.assert_called_once_with(resume=True)
            self.assertEqual((path / "execution.json").read_bytes(), epoch_bytes)

    def test_host_q1_helper_only_and_mixed_refused(self):
        host = host_tests.HostTests().bare()
        host.scope = "q1-only"
        host.mapping_helpers_verified = False
        manifest = profiles.command_manifest("Q1", 4096)
        host.manifests = {"reviewed": manifest}
        host.guards = Mock()
        resource = {"id": "1" * 64, "name": host.campaign + "-mapping-helper-q",
                    "image_id": manifest["expected_image_ids"][0]}
        host.docker_inspect = Mock(side_effect=[{}, None])
        host.owner._resource = lambda x: resource
        host.owner._save = Mock()
        host.resource = Mock()
        host._exact = Mock(return_value={"State": {"Running": False, "ExitCode": 0}})
        with patch("benchmark.host.command", side_effect=[SimpleNamespace(stdout=b"1" * 64),
                SimpleNamespace(stdout=b"", stderr=b""), SimpleNamespace(stdout=b"")]) as command:
            host.verify_mapping_helpers(host.owner.lease)
        creates = [c.args[0] for c in command.call_args_list if "create" in c.args[0]]
        self.assertEqual(len(creates), 1)
        self.assertIn(manifest["image"], creates[0])
        self.assertIn(host.campaign + "-mapping-helper-q", creates[0])
        with self.assertRaisesRegex(ValueError, "mixed_excluded"):
            host.dispatch({"op": "admit_mixed"})

    def test_exact_reviewed_generation_disposition_skips_all_completed_and_runs_only_64k(self):
        with tempfile.TemporaryDirectory() as directory:
            c, host, requests, _ = self.setup_case(Path(directory))
            completed = {identity: {"status":"PASS"} for identity in CASES[:3]}
            completed[CASES[3]] = {"status":"HARNESS_FAILURE", "synthetic":"saved framing failure"}
            c.progress["completed"] = copy.deepcopy(completed)
            # Synthetic row pin replaces only the immutable real-row pin in this offline test.
            approved = {**runner.Q1_GENERATION_FRAMING,
                "failed_row_sha256":fixtures.digest(fixtures.canonical(completed[CASES[3]]))}
            c.armed["q1_generation_framing"] = approved
            with patch.object(runner, "Q1_GENERATION_FRAMING", approved):
                c.run(resume=True)
            self.assertEqual({k:c.progress["completed"][k] for k in completed}, completed)
            self.assertEqual(c.progress["completed"][CASES[4]]["status"], "PASS")
            loads = [host.manifests[a["manifest_sha256"]] for op,a in host.events if op == "load"]
            self.assertEqual([(m["placement"],m["configured_capacity"]) for m in loads], [("Q1",65536)])
            self.assertEqual(len(requests), 2)  # One discarded warmup and one retrieval; no generation retry.

    def test_generation_disposition_missing_or_hash_mismatch_refuses_before_host(self):
        with tempfile.TemporaryDirectory() as directory:
            c, host, _, _ = self.setup_case(Path(directory))
            c.progress["completed"] = {CASES[3]:{"status":"HARNESS_FAILURE"}}
            for disposition in (None, runner.Q1_GENERATION_FRAMING,
                    {**runner.Q1_GENERATION_FRAMING,"semantic_disposition_sha256":"0"*64}):
                c.armed["q1_generation_framing"] = disposition
                with self.assertRaisesRegex(RuntimeError, "failed_measurement"):
                    c.run(resume=True)
            self.assertEqual(host.events, [])


if __name__ == "__main__":
    unittest.main()
