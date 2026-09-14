"""Static boot contract tests; live Linux systemd/reboot remains NOT_TESTED."""

import json
from pathlib import Path
import shlex
import unittest

ROOT = Path(__file__).resolve().parents[2]
UNIT = ROOT / "scripts/lifecycle/llmctl-boot.service"


def parse_unit():
    """Keep repeated directives such as After and mount conditions intact."""
    sections = {}
    section = None
    for line in UNIT.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = sections.setdefault(line[1:-1], {})
        else:
            key, value = line.split("=", 1)
            section.setdefault(key, []).append(value)
    return sections


def seconds(value):
    for suffix, multiplier in (("min", 60), ("h", 3600), ("s", 1)):
        if value.endswith(suffix):
            return int(value[:-len(suffix)]) * multiplier
    return int(value)


class BootSourceTests(unittest.TestCase):
    def setUp(self):
        self.unit = parse_unit()

    def test_both_mounts_order_and_stop_the_boot_owner(self):
        unit = self.unit["Unit"]
        self.assertEqual(set(unit["RequiresMountsFor"][0].split()), {"/data", "/data/models-large"})
        self.assertEqual(set(unit["ConditionPathIsMountPoint"]), {"/data", "/data/models-large"})
        mount_units = {"data.mount", r"data-models\x2dlarge.mount"}
        self.assertTrue(mount_units <= set(" ".join(unit["After"]).split()))
        self.assertTrue(mount_units <= set(" ".join(unit["BindsTo"]).split()))
        self.assertIn("docker.service", " ".join(unit["Requires"]).split())

    def test_single_owner_replays_intent_through_the_same_manager(self):
        service = self.unit["Service"]
        self.assertEqual(service["Type"], ["oneshot"])
        self.assertEqual(service["RemainAfterExit"], ["yes"])
        self.assertNotIn("Restart", service)
        for directive, action in (("ExecStart", "boot-start"), ("ExecStop", "boot-stop")):
            self.assertEqual(len(service[directive]), 1)
            argv = shlex.split(service[directive][0])
            self.assertEqual(argv[:3], ["/usr/bin/python3",
                                         "/data/services/mixed-memory-llm-api-server/scripts/llmctl", action])
            self.assertIn("--yes", argv)
            self.assertEqual(argv[argv.index("--instance") + 1],
                             "/data/services/llm-manager/deployment-instance.json")
        self.assertNotIn("docker", " ".join(service["ExecStart"] + service["ExecStop"]))
        self.assertNotIn("git checkout", UNIT.read_text())

    def test_conservative_start_and_bounded_stop_timeouts(self):
        service = self.unit["Service"]
        deployment_timeouts = [json.loads(path.read_text())["launch"]["timeout_seconds"]
                               for path in (ROOT / "configs/deployments").glob("*.json")]
        self.assertGreater(seconds(service["TimeoutStartSec"][0]), max(deployment_timeouts))
        self.assertGreaterEqual(seconds(service["TimeoutStopSec"][0]), 150)
        self.assertLessEqual(seconds(service["TimeoutStopSec"][0]), 600)

    def test_service_output_does_not_spill_to_root_journal(self):
        service = self.unit["Service"]
        self.assertEqual(service["StandardOutput"], ["null"])
        self.assertEqual(service["StandardError"], ["null"])
        self.assertEqual(service["UMask"], ["0077"])
        self.assertTrue(service["WorkingDirectory"][0].startswith("/data/services/"))
        for path in (ROOT / "configs/deployments").glob("*.json"):
            deployment = json.loads(path.read_text())
            self.assertEqual(deployment["docker_restart_policy"], "no")
            self.assertEqual(deployment["logs"], {"driver": "json-file", "max_size": "20m", "max_file": 3})


if __name__ == "__main__":
    unittest.main()
