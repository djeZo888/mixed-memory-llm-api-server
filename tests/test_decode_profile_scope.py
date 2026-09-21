"""Exact profile-only arm and bounded clock; offline, no host/model operations."""
import copy
import json
from pathlib import Path
import shlex
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark import profiles
from benchmark.host import HostBudget, LinuxHost


class DecodeProfileScope(unittest.TestCase):
    def arm(self):
        campaign = profiles.GLM_DECODE_PROFILE_CAMPAIGN
        return {"scope": "glm-decode-diag", "mode": "cpu-profile-only", "campaign": campaign,
                "manifests": [profiles.glm_decode_diag_manifest(65536, campaign)],
                "trial_plan": profiles.trial_order("glm-decode-diag", campaign=campaign),
                "capture": {"cpu": True, "cuda": False, "cpu_maximum_seconds": 5,
                            "cpu_sampling_seconds": 4, "cpu_file_limit_bytes": 1024**3}}

    def clock(self):
        original = {"stage": "GLM-DECODE-DIAG-20260920", "start_epoch": 1000,
                    "deadline_epoch": 15400, "budget_seconds": 14400,
                    "request_max_seconds": 7200, "clock_includes_preparation": True,
                    "restoration_outside_budget": True}
        return {"stage": "GLM-DECODE-PROFILE-20260920", "start_epoch": 10000,
                "deadline_epoch": 11200, "budget_seconds": 1200,
                "includes_preparation": True, "clock_includes_preparation": True,
                "request_max_seconds": 1200, "restoration_outside_budget": True,
                "original_clock": original}

    def test_only_campaign_identity_changes_from_old_64k(self):
        old = profiles.glm_decode_diag_manifest(65536)
        new = profiles.glm_decode_diag_manifest(65536, profiles.GLM_DECODE_PROFILE_CAMPAIGN)
        restored = json.loads(json.dumps(new).replace(profiles.GLM_DECODE_PROFILE_CAMPAIGN,
                                                      profiles.GLM_DECODE_DIAG_CAMPAIGN))
        self.assertEqual(old, restored)
        self.assertEqual(new["create_shell"], shlex.join(new["create_argv"]))
        for capacity in (True, 1024, 32768, 65536.0, 131072):
            with self.assertRaisesRegex(ValueError, "outside_scope"):
                profiles.glm_decode_diag_manifest(capacity, profiles.GLM_DECODE_PROFILE_CAMPAIGN)

    def test_arm_has_only_warmup32_cpu256_no_other_cases(self):
        arm = self.arm()
        self.assertEqual(profiles.validate_arm_scope(arm), "glm-decode-diag")
        plan = arm["trial_plan"]
        self.assertEqual([(r["capacity"], r["case"], r["output_cap"]) for r in plan["trials"]],
                         [(65536, "load_warmup", 32), (65536, "cpu_diagnostic", 256)])
        self.assertEqual(plan["measurement_budget_seconds"], 1200)
        self.assertEqual(plan["maximum_request_seconds"], 1200)
        variants = []
        for field, value in (("campaign", profiles.GLM_DECODE_DIAG_CAMPAIGN),
                             ("manifests", [profiles.glm_decode_diag_manifest(n) for n in (1024, 32768, 65536)]),
                             ("trial_plan", profiles.trial_order("glm-decode-diag"))):
            bad = copy.deepcopy(arm); bad[field] = value; variants.append(bad)
        for key in ("cpu", "cuda"):
            bad = copy.deepcopy(arm); bad["capture"][key] = not bad["capture"][key]; variants.append(bad)
        bad = copy.deepcopy(arm); bad["mode"] = "unreviewed"; variants.append(bad)
        bad = copy.deepcopy(arm); bad.pop("mode"); variants.append(bad)
        for bad in variants:
            with self.assertRaises(ValueError):
                profiles.validate_arm_scope(bad)

    def test_old_normal_arm_stays_three_loads_eight_steps(self):
        arm = {"scope": "glm-decode-diag", "campaign": profiles.GLM_DECODE_DIAG_CAMPAIGN,
               "manifests": [profiles.glm_decode_diag_manifest(n) for n in (1024, 32768, 65536)],
               "trial_plan": profiles.trial_order("glm-decode-diag")}
        self.assertEqual(profiles.validate_arm_scope(arm), "glm-decode-diag")
        self.assertEqual(len(arm["trial_plan"]["trials"]), 8)
        self.assertEqual(arm["trial_plan"]["measurement_budget_seconds"], 14400)

    def test_host_profile_clock_bounds_and_restoration(self):
        armed = {**self.arm(), "runtime": self.clock()}
        self.assertEqual(LinuxHost.decode_clock(armed), (10000, 11200))
        for field, value in (("deadline_epoch", 11201), ("budget_seconds", 14400),
                             ("request_max_seconds", 7200), ("includes_preparation", False)):
            bad = copy.deepcopy(armed); bad["runtime"][field] = value
            with self.assertRaises(ValueError):
                LinuxHost.decode_clock(bad)
        bad = copy.deepcopy(armed)
        bad["runtime"].update(start_epoch=15000, deadline_epoch=16200)
        with self.assertRaises(ValueError):
            LinuxHost.decode_clock(bad)
        host = SimpleNamespace(scope="glm-decode-diag", mode="cpu-profile-only", log_root="/data/logs/offline",
                               start_epoch=10000, deadline_epoch=11200, read_json=Mock(return_value=None), write_json=Mock())
        with patch("benchmark.host.time.time", return_value=10010):
            budget = HostBudget(host); budget.start("maintenance")
        budget.clock = lambda: 11199
        self.assertEqual(budget.request_timeout(7200), 1)
        budget.clock = lambda: 11200
        with self.assertRaises(ValueError):
            budget.request_timeout(7200)
        budget.begin_restoration(); budget.finish_restoration(True)
        self.assertEqual(budget.data["deadline_epoch"], 11200)

    def test_profile_retains_allocation_memory_cpuset_and_reserve_gates(self):
        from benchmark import allocation
        from tests.test_decode_diag_profiles import DecodeDiagProfiles
        _, parsed, observed = DecodeDiagProfiles().proof(65536)
        manifest = self.arm()['manifests'][0]
        observed['native_argv'] = manifest['native_argv']
        self.assertEqual(allocation.allocation_gate(manifest, parsed, observed)['status'], 'ALLOCATION_PROOF_ACCEPTED')
        for section, key, value in (
                ('container_memory_limits', 'cgroup_memory_swap_max', '1'),
                ('container_cpu_limits', 'cgroup_cpuset_cpus_effective', '0-111'),
                ('gpu_free_bytes', manifest['gpu_uuids'][0], 16 * allocation.GIB - 1)):
            bad = copy.deepcopy(observed); bad[section][key] = value
            self.assertEqual(allocation.allocation_gate(manifest, parsed, bad)['status'], 'STOP_ALLOCATION_PROOF')


if __name__ == "__main__":
    unittest.main()
