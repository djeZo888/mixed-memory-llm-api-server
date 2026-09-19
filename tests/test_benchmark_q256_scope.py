"""Q1 262144 continuation: synthetic offline execution, no host contact."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from tests import test_benchmark_q1_scope as q1
from tests import test_benchmark_qwen_adapter as adapter
from tests import test_benchmark_allocation as alloc
from benchmark import accounting, allocation, qwen_launcher

runner, profiles, fixtures = q1.runner, q1.profiles, q1.fixtures
CASE = "Q1-262144-retrieval"


class Q256Scope(unittest.TestCase):
    def setup_case(self, path):
        runner.save(path / "execution.json", q1.EXECUTION)
        frozen = q1.saved_fixtures()
        key = "bench-qwen3.8-27b-65536-retrieval"
        frozen[key] = fixtures.build_sample("bench-qwen3.8-27b", 4330, "old64-seed", "old64-prefix")
        runner.save(path / "private/fixtures.json", frozen)
        sha = runner.arm(path, "benchrun-20260919", "q1-256k")
        armed = runner.load_arm(path, sha)
        campaign, host, requests = q1.integrated.IntegratedRunner().setup_case(path, armed["manifests"])
        campaign.armed = armed
        host.budget.clock = lambda: q1.EPOCH
        host.budget.start("maintenance")
        host.budget.clock = lambda: q1.EPOCH + 600
        return campaign, host, requests, sha

    def test_exact_manifest_native_settings_and_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            c, _, _, _ = self.setup_case(Path(directory))
            self.assertEqual(len(c.armed["manifests"]), 1)
            manifest = c.armed["manifests"][0]
            self.assertEqual((manifest["placement"], manifest["configured_capacity"], manifest["mixed"]), ("Q1", 262144, False))
            self.assertEqual((manifest["guest_cpuset"], manifest["guest_cpu_count"]), ("96-111", 16))
            self.assertEqual(manifest["gpu_uuids"], [profiles.read_config()["gpu_uuids"][1]])
            old = profiles.command_manifest("Q1", 65536)
            for field in ("model", "image", "expected_image_ids"):
                self.assertEqual(manifest[field], old[field])
            self.assertEqual(manifest["native_argv"], ["262144" if x == "65536" else x for x in old["native_argv"]])
            argv = manifest["native_argv"]
            for flag, value in (("--context-length", "262144"), ("--max-total-tokens", "262144"),
                                ("--tp-size", "1"), ("--mem-fraction-static", "0.80"),
                                ("--kv-cache-dtype", "bfloat16"), ("--quantization", "fp8")):
                self.assertEqual(argv[argv.index(flag) + 1], value)
            self.assertEqual(c.armed["trial_plan"]["trials"], [
                {"placement":"Q1", "capacity":262144, "case":"load_warmup", "timing":"discard"},
                {"placement":"Q1", "capacity":262144, "case":"retrieval", "output_cap":256}])
            self.assertEqual(c.armed["trial_plan"]["then"], [])
            self.assertEqual(c.armed["trial_plan"]["mixed_jobs"], [])
            self.assertEqual(c.armed["continuation_execution"], q1.EXECUTION)
            self.assertNotIn("q1_generation_framing", c.armed)

    def test_one_discarded_warmup_one_retrieval_only_new_fixture_and_retained_epoch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            c, host, requests, _ = self.setup_case(path)
            epoch_bytes = (path / "execution.json").read_bytes()
            frozen = copy.deepcopy(c.fixture_cache)
            with patch.object(c, "mixed", side_effect=AssertionError("mixed forbidden")), \
                    patch.object(fixtures, "fit_sample", wraps=fixtures.fit_sample) as fit:
                c.run(resume=True)
            self.assertEqual(list(c.progress["completed"]), [CASE])
            self.assertEqual(c.progress["completed"][CASE]["status"], "PASS")
            self.assertEqual(c.progress["phase"], "RESTORED_PENDING_WORKER_VERIFICATION")
            self.assertEqual(len([op for op, _ in host.events if op == "load"]), 1)
            self.assertEqual(len(requests), 2)
            self.assertEqual(sum("warmup-prefix-" in r["messages"][0]["content"] for r in requests), 1)
            self.assertTrue(all(r["max_tokens"] == 256 and r["model"] == "bench-qwen3.8-27b" and not r.get("tools") for r in requests))
            self.assertNotEqual(requests[0]["messages"][0]["content"], requests[1]["messages"][0]["content"])
            measured = [call for call in fit.call_args_list if call.args[2] != "warmup-only-seed"]
            self.assertEqual(len(measured), 1)
            self.assertEqual(measured[0].args[1], 262144)
            count = c.progress["completed"][CASE]["count"]
            self.assertLessEqual(count["input_tokens"], 262144 - 512)
            self.assertGreaterEqual(count["input_tokens"], 262144 - 512 - 128)
            self.assertEqual(count["configured_context"], 262144)
            after = json.loads((path / "private/fixtures.json").read_bytes())
            self.assertEqual({k: after[k] for k in frozen}, frozen)
            self.assertEqual(set(after) - set(frozen), {"bench-qwen3.8-27b-262144-retrieval"})
            self.assertEqual((path / "execution.json").read_bytes(), epoch_bytes)
            self.assertEqual(host.budget.data["started_at"] + host.budget.data["budget_seconds"], q1.DEADLINE)
            self.assertEqual(host.events[-1][0], "restore")

    def test_exact_scope_exclusions_fail_before_host(self):
        with tempfile.TemporaryDirectory() as directory:
            c, host, _, _ = self.setup_case(Path(directory))
            original = copy.deepcopy(c.armed)
            bad_arms = []
            for p, n in (("Q1",4096), ("Q1",65536), ("Q2",16384), ("G1",16384)):
                bad = copy.deepcopy(original)
                bad["manifests"].append(profiles.command_manifest(p,n))
                bad_arms.append(bad)
            for field, value in (("scope","unknown"), ("trial_plan",profiles.trial_order("q1-only"))):
                bad_arms.append({**original,field:value})
            for bad in bad_arms:
                c.armed = bad
                with self.assertRaises(ValueError): c.run(resume=True)
            self.assertEqual(host.events, [])
            host = q1.host_tests.HostTests().bare()
            host.scope = "q1-256k"
            with self.assertRaisesRegex(ValueError,"mixed_excluded"):
                host.dispatch({"op":"admit_mixed"})

    def test_unapproved_capacity_placement_and_fixture_tuples_refused(self):
        for p, n, options in (("Q2",262144,{}),("G1",262144,{}),("G2",262144,{}),
                              ("Q1",524288,{}),("Q1",131072,{}),("Q1",262144,{"mixed":True,"ram_cap":1})):
            with self.assertRaises(ValueError): profiles.command_manifest(p,n,**options)
        base = qwen_launcher.pinned_base(profiles.ROOT / "scripts/runtime/sglang38_file_auth.py")
        for n, tp in ((262144,2),(524288,1),(131072,1)):
            with self.assertRaises(ValueError): qwen_launcher.variant(base,n,tp)
        with self.assertRaises(fixtures.HarnessError):
            accounting.native_counter("bench-glm-5.3",262144,Mock())
        for model, kind, cap in (("bench-glm-5.3","retrieval",256),("bench-qwen3.8-27b","generation",512),("bench-qwen3.8-27b","tool",256)):
            counter = Mock()
            with self.assertRaises(fixtures.HarnessError):
                fixtures.fit_sample(model,262144,"seed","prefix",counter,kind=kind,output_cap=cap)
            counter.assert_not_called()

    def test_epoch_and_resume_required_before_keys_or_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            c, host, _, sha=self.setup_case(path)
            with self.assertRaisesRegex(RuntimeError,"explicit_resume"): c.run()
            self.assertEqual(host.events, [])
            argv=["run","--state",directory,"--reviewed-arm-sha256",sha,
                  "--inference-key-file","synthetic","--control-key-file","synthetic"]
            epoch_bytes=(path / "execution.json").read_bytes()
            with patch("runtime.sglang38_file_auth.read_key") as key, patch.object(runner,"SSHHost") as ssh:
                with self.assertRaises(SystemExit): runner.main(argv)
                runner.save(path / "execution.json", {**q1.EXECUTION,"start_epoch":q1.EPOCH+1})
                with self.assertRaisesRegex(ValueError,"epoch_changed"): runner.main([*argv,"--resume"])
                (path / "execution.json").unlink()
                with self.assertRaises(FileNotFoundError): runner.main([*argv,"--resume"])
                key.assert_not_called(); ssh.assert_not_called()
            (path / "execution.json").write_bytes(epoch_bytes)
            with patch("runtime.sglang38_file_auth.read_key",return_value="synthetic"), \
                    patch.object(runner.os,"geteuid",return_value=501), \
                    patch.object(runner,"SSHHost") as ssh, patch.object(runner,"Campaign") as campaign, \
                    patch("benchmark.worker_verify.verify",return_value={}):
                self.assertEqual(runner.main([*argv,"--resume"]),0)
                self.assertEqual(ssh.call_args.args[0]["runtime"],q1.EXECUTION)
                campaign.return_value.run.assert_called_once_with(resume=True)
            self.assertEqual((path / "execution.json").read_bytes(),epoch_bytes)

    def test_failure_restores_without_retry_or_imported_disposition(self):
        with tempfile.TemporaryDirectory() as directory:
            c, host, _, _=self.setup_case(Path(directory))
            with patch.object(c,"trial",return_value={"status":"HARNESS_FAILURE"}):
                with self.assertRaisesRegex(RuntimeError,"stopped_for_review"): c.run(resume=True)
            self.assertEqual(host.events[-1][0],"restore")
            self.assertEqual(c.progress["skipped_after_stop"],[CASE])
            c.progress["completed"]={CASE:{"status":"HARNESS_FAILURE"}}
            host.events.clear()
            with self.assertRaisesRegex(RuntimeError,"failed_measurement"): c.run(resume=True)
            self.assertEqual(host.events,[])

    def test_262144_actual_launcher_main_auth_and_pool_drift(self):
        test=adapter.AdapterIntegrationTests()
        test.exercise(262144,1)
        test.exercise(262144,1,bad_pool=True)

    def test_actual_allocation_requires_exact_native_pool(self):
        m=profiles.command_manifest("Q1",262144)
        fixture=alloc.Allocation()
        events,facts=fixture.qwen(1)
        facts.update(context_length=262144,max_total_tokens=262144,max_total_num_tokens=262144)
        events[0]["memory_usage_gb_log_label"]=28.72
        events[1].update(cache_tokens=262144,k_size_gb_log_label=8.0,v_size_gb_log_label=8.0)
        observed=fixture.observed(m)
        self.assertEqual(allocation.allocation_gate(m,allocation.parse_qwen_log_facts(events,facts),observed)["status"],"ALLOCATION_PROOF_ACCEPTED")
        for bad in (None,65536,262143):
            drift={**facts,"max_total_num_tokens":bad}
            self.assertEqual(allocation.allocation_gate(m,allocation.parse_qwen_log_facts(events,drift),observed)["status"],"STOP_ALLOCATION_PROOF")


if __name__ == "__main__":
    unittest.main()
