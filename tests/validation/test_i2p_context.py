import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[2] / "scripts/validation/i2p/run.py"
SPEC = importlib.util.spec_from_file_location("i2p_run", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ContextSafety(unittest.TestCase):
    def context(self):
        return {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
                "GITHUB_REPOSITORY": "djeZo888/mixed-memory-llm-api-server",
                "I2P_DISPOSABLE_ACK": "github-hosted-ubuntu-24.04",
                "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
                "GITHUB_SHA": "a" * 40}

    def test_explicit_context(self):
        MODULE.validate_context(self.context())

    def test_each_missing_context_value_refused(self):
        for key in self.context():
            with self.subTest(key=key):
                context = self.context()
                del context[key]
                with self.assertRaises(RuntimeError):
                    MODULE.validate_context(context)

    def test_self_hosted_or_wrong_repository_refused(self):
        for key, value in (("RUNNER_ENVIRONMENT", "self-hosted"),
                           ("GITHUB_REPOSITORY", "other/repo"),
                           ("GITHUB_RUN_ID", "-123"),
                           ("GITHUB_SHA", "refs/heads/main")):
            with self.subTest(key=key):
                context = self.context()
                context[key] = value
                with self.assertRaises(RuntimeError):
                    MODULE.validate_context(context)


if __name__ == "__main__":
    unittest.main()
