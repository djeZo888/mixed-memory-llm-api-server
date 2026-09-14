"""Functional offline smoke-plan verifier tests, with explicit CLI injection."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "scripts/sglang/verify-sglang-smoke-plan.sh"
SENTINEL = "synthetic-sensitive-response-must-not-be-relayed"


def offline_state(selected=None, *, configured=True, desired="stopped", recorded="stopped"):
    return {"schema_version": 2, "configured": configured, "selected": selected,
            "desired": desired, "boot_policy": "manual", "recorded_observed": recorded,
            "observed": None, "container_running": None,
            "observation": "not_performed_offline"}


class SmokePlanOfflineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.response = self.work / "response.txt"
        self.exit_code = self.work / "exit-code"
        self.args_log = self.work / "args.json"
        self.bin = self.work / "bin"
        self.bin.mkdir()
        self.mock = self.work / "mock-llmctl"
        self.mock.write_text("""#!/usr/bin/env python3
import json
from pathlib import Path
import sys
root = Path(__file__).parent
(root / 'args.json').write_text(json.dumps(sys.argv[1:]))
sys.stdout.write((root / 'response.txt').read_text())
sys.stderr.write('synthetic-sensitive-response-must-not-be-relayed')
raise SystemExit(int((root / 'exit-code').read_text()))
""")
        self.mock.chmod(0o755)
        # Neither direct Docker, sudo Docker, API clients nor mount checks belong
        # in this offline verifier. A PATH sentinel makes regressions explicit.
        self.called = self.work / "live-operation-called"
        for name in ("docker", "sudo", "curl", "findmnt"):
            sentinel = self.bin / name
            sentinel.write_text("#!/usr/bin/env python3\nfrom pathlib import Path\n"
                                f"Path({str(self.called)!r}).write_text('called')\nraise SystemExit(97)\n")
            sentinel.chmod(0o755)

    def invoke(self, value, *, code=0, instance=None, cwd=ROOT):
        self.response.write_text(value if isinstance(value, str) else json.dumps(value))
        self.exit_code.write_text(str(code))
        command = ["bash", str(VERIFIER), "--llmctl", str(self.mock)]
        if instance is not None:
            command += ["--instance", str(instance)]
        result = subprocess.run(command, cwd=cwd, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, timeout=20,
                                env={**os.environ, "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", "")})
        self.assertFalse(self.called.exists(), "offline verifier invoked a live operation")
        self.assertNotIn(SENTINEL, result.stdout + result.stderr)
        return result

    def assert_pass(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS: SGLang smoke plan verification passed", result.stdout)
        self.assertIn("live_host_checks: NOT_TESTED", result.stdout)
        self.assertIn("readiness: NOT_TESTED", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_no_instance_requires_no_docker_and_uses_offline(self):
        self.assert_pass(self.invoke(offline_state(configured=False, recorded=None)))
        self.assertEqual(json.loads(self.args_log.read_text()), ["status", "--offline"])

    def test_stopped_smoke_qwen_and_saved_ready_glm_are_unverified(self):
        for selected, desired, recorded in (("qwen3-0.6b-smoke", "stopped", "stopped"),
                                            ("qwen3-30b-a3b-instruct-2507", "stopped", "ready"),
                                            ("glm-5.3-ud-q4-k-xl-8k", "running", "ready"),
                                            ("glm-5.3-ud-q4-k-xl-32k", "running", "ready")):
            with self.subTest(selected=selected):
                result = self.invoke(offline_state(selected, desired=desired, recorded=recorded))
                self.assert_pass(result)
                self.assertNotIn(selected, result.stdout)
                self.assertNotIn('"ready"', result.stdout)

    def test_instance_argument_passed_literally(self):
        instance = self.work / "instance with spaces.json"
        self.assert_pass(self.invoke(offline_state(), instance=instance))
        self.assertEqual(json.loads(self.args_log.read_text()),
                         ["status", "--offline", "--instance", str(instance)])

    def test_malformed_json_old_text_and_old_shape_fail_without_echo(self):
        for response in ("{invalid" + SENTINEL, "active: none", "[]", "null",
                         {"schema_version": 1, "model_profile": "qwen3-0.6b-smoke"},
                         {"schema_version": 2, "selected": None}):
            with self.subTest(kind=type(response).__name__):
                result = self.invoke(response)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stderr.strip(), "FAIL: offline_status_schema_invalid")
                self.assertNotIn("PASS:", result.stdout)

    def test_live_claims_and_inconsistent_offline_shapes_fail(self):
        changes = ({"observed": "ready"}, {"container_running": True},
                   {"observation": "live"}, {"configured": "false"},
                   {"schema_version": 2.0}, {"selected": "unsafe/identifier"},
                   {"desired": "running"}, {"boot_policy": "always"},
                   {"recorded_observed": {"unsafe": SENTINEL}},
                   {"configured": False, "recorded_observed": "ready"})
        for change in changes:
            with self.subTest(change=next(iter(change))):
                result = self.invoke({**offline_state(), **change})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stderr.strip(), "FAIL: offline_status_schema_invalid")

    def test_nonzero_status_diagnostics_never_relayed(self):
        result = self.invoke(SENTINEL, code=17)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stderr.strip(), "FAIL: offline_status_command_failed")
        self.assertNotIn("PASS:", result.stdout)

    def test_extra_untrusted_fields_are_not_reported(self):
        self.assert_pass(self.invoke({**offline_state(), "arbitrary_field": SENTINEL}))

    def test_template_and_pin_checks_still_execute(self):
        fixture_root = self.work / "repository"
        files = ("configs/compose/compose.sglang-smoke.template.yml",
                 "configs/sglang/smoke.env.example", "reports/m8a-sglang-smoke-plan.md",
                 "reports/m8b-sglang-smoke-deploy.md", "docs/sglang-smoke-deployment.md",
                 "scripts/sglang/verify-sglang-smoke-plan.sh", "tests/shell/test-sglang-smoke-static.sh")
        for relative in files:
            target = fixture_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        (fixture_root / "scripts/api").mkdir(parents=True)
        self.assert_pass(self.invoke(offline_state(), cwd=fixture_root))
        compose = fixture_root / files[0]
        saved = compose.read_text()
        for replacement in (saved.replace("127.0.0.1:30000:30000", "0.0.0.0:30000:30000"),
                            saved.replace("image: ${SGLANG_IMAGE_TAG}", "image: lmsysorg/sglang:latest")):
            compose.write_text(replacement)
            result = self.invoke(offline_state(), cwd=fixture_root)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("PASS:", result.stdout)
        compose.write_text(saved)
        env = fixture_root / files[1]
        env.write_text(env.read_text().replace("\nSGLANG_IMAGE_TAG=\n",
                                              "\nSGLANG_IMAGE_TAG=lmsysorg/sglang:latest\n"))
        self.assertNotEqual(self.invoke(offline_state(), cwd=fixture_root).returncode, 0)


if __name__ == "__main__":
    unittest.main()
