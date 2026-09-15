#!/usr/bin/env python3
"""Synthetic regression for the as-run V1G early failure guard; no live inference.

Run: python3 -B scripts/validation/v1g/test_stop_guard.py -v
Help: python3 -B scripts/validation/v1g/test_stop_guard.py --help
The backend is the existing loopback-only HTTP fixture. Its credential and all
temporary reports are synthetic, private, outside the checkout, and disposable.
This exercises the runner's child path without changing the reviewed A1 source.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[3]
RUNNER = Path(__file__).with_name("run_a1.py")
ACCEPTANCE = REPO / "scripts" / "agent" / "acceptance.py"


def private_write(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)


class StopGuardTests(unittest.TestCase):
    def test_invalid_model_failure_stops_after_four_requests(self):
        spec = importlib.util.spec_from_file_location(
            "v1g_synthetic_acceptance_backend", REPO / "tests" / "test_agent_acceptance.py"
        )
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        original_completion = fixture.completion

        def glm_completion(content="Hello", calls=None, model="glm-5.3"):
            # Rebinding MODEL alone cannot change completion's bound default.
            return original_completion(content=content, calls=calls, model=model)

        acceptance_hash = hashlib.sha256(ACCEPTANCE.read_bytes()).hexdigest()
        runner_hash = hashlib.sha256(RUNNER.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory(prefix="v1g-synthetic-stop-") as directory:
            private = Path(directory).resolve()
            self.assertFalse(private.is_relative_to(REPO))
            private.chmod(0o700)
            private_write(private / "llm-api-key", fixture.SYNTHETIC_KEY.encode("ascii"))
            mode = private / "nonstream"
            mode.mkdir(mode=0o700)
            private_write(mode / "execution.json", json.dumps({
                "acceptance_sha256": acceptance_hash,
                "evidence_kind": "synthetic",
            }).encode("utf-8"))

            with mock.patch.object(fixture, "MODEL", "glm-5.3"), \
                    mock.patch.object(fixture, "completion", glm_completion), \
                    fixture.backend("accept_invalid_model", auth=True) as (url, records):
                result = subprocess.run(
                    [sys.executable, "-B", str(RUNNER), "--child",
                     "--private-dir", str(private), "--base-url", url,
                     "--mode", "nonstream"],
                    cwd=REPO, env={"PATH": os.defpath},
                    capture_output=True, text=True, timeout=20,
                )

            self.assertEqual(result.returncode, 1, result.stderr)
            report_text = (mode / "report.json").read_text(encoding="utf-8")
            report = json.loads(report_text)
            self.assertNotIn(fixture.SYNTHETIC_KEY, report_text)
            self.assertNotIn(fixture.SYNTHETIC_KEY,
                             (mode / "partial-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(list(report["checks"]),
                             ["models", "chat", "streaming_end", "invalid_model"])
            for name in ("models", "chat", "streaming_end"):
                self.assertEqual(report["checks"][name]["status"], "PASS")
            self.assertEqual(report["checks"]["invalid_model"]["status"], "FAIL")
            self.assertIn("Invalid model was accepted",
                          report["checks"]["invalid_model"]["error"])
            self.assertEqual(report["v1g_external_stop_guard"], {
                "failed_check": "invalid_model", "dependent_requests_stopped": True,
            })
            self.assertNotIn("agent", report)
            self.assertEqual(report["opencode_e2e"], "NOT_TESTED")
            self.assertEqual(report["clean_linux_install"], "NOT_TESTED")
            self.assertEqual(len(records), 4)
            self.assertEqual(len(report["requests"]), 4)
            self.assertEqual([entry["method"] for entry in records],
                             ["GET", "POST", "POST", "POST"])
            chats = [entry for entry in records if entry["method"] == "POST"]
            self.assertEqual([entry["body"]["stream"] for entry in chats],
                             [False, True, False])
            for entry in chats:
                self.assertEqual(entry["auth_kind"], "correct")
                self.assertEqual(entry["body"]["reasoning_effort"], "low")
                self.assertEqual(entry["body"]["max_tokens"], 2048)
                self.assertNotIn("tools", entry["body"])
            self.assertTrue(chats[-1]["body"]["model"].startswith("__a1_invalid_model_"))
            invalid_request = report["requests"][-1]
            self.assertEqual(invalid_request["status"], 200)
            self.assertEqual(invalid_request["model"], "glm-5.3")
            self.assertEqual(invalid_request["finish_reason"], "stop")
            self.assertEqual(invalid_request["usage"]["completion_tokens"], 5)
            self.assertGreaterEqual(report["elapsed_seconds"], 0)

        self.assertEqual(hashlib.sha256(ACCEPTANCE.read_bytes()).hexdigest(), acceptance_hash)
        self.assertEqual(hashlib.sha256(RUNNER.read_bytes()).hexdigest(), runner_hash)


if __name__ == "__main__":
    unittest.main()
