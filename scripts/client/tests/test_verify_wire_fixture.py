"""Offline refusals for the real-client synthetic HTTP verifier fixture."""

import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import verify_wire_fixture as wire


class VerifierWireTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="verifier-wire-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        source = (wire.CLIENT / "verifier_fixture" / "text_utils.py").read_bytes()
        tests = (wire.CLIENT / "verifier_fixture" / "test_text_utils.py").read_bytes()
        (self.root / "text_utils.py").write_bytes(source)
        (self.root / "test_text_utils.py").write_bytes(tests)
        self.server = SimpleNamespace(model="glm-5.3", output_tokens=2048, workspace=self.root,
                                      source=source, test_sha256=hashlib.sha256(tests).hexdigest(),
                                      stage=0, records=[])

    def body(self, rounds=0):
        messages = [{"role": "user", "content": "Synthetic fixture request"}]
        for index in range(rounds):
            messages += [
                {"role": "assistant", "tool_calls": [{"id": wire.CALL_IDS[index], "type": "function",
                 "function": {"name": wire.CALL_NAMES[index],
                              "arguments": json.dumps(wire.arguments(self.root)[index])}}]},
                {"role": "tool", "tool_call_id": wire.CALL_IDS[index], "content": (
                    self.server.source.decode() if index == 0 else
                    "importlib.util\ndef test_empty_string" if index == 1 else
                    "Edit applied successfully." if index == 2 else "Ran 3 tests\n\nOK\n")},
            ]
        return {"model": "glm-5.3", "stream": True, "max_tokens": 2048, "reasoning_effort": "low",
                "tools": [{"type": "function", "function": {"name": name}}
                          for name in set(wire.CALL_NAMES)], "messages": messages}

    def test_first_response_requests_actual_implementation_read_and_no_disk_edit(self):
        before = (self.root / "text_utils.py").read_bytes()
        delta, finish = wire.model_reply(self.server, self.body())
        self.assertEqual(finish, "tool_calls")
        call = delta["tool_calls"][0]
        self.assertEqual(call["function"]["name"], "read")
        self.assertEqual(json.loads(call["function"]["arguments"]), wire.arguments(self.root)[0])
        self.assertEqual((self.root / "text_utils.py").read_bytes(), before)
        self.assertEqual(self.server.stage, 1)

    def test_real_implementation_content_must_be_replayed_before_requesting_tests_read(self):
        self.server.stage = 1
        delta, _ = wire.model_reply(self.server, self.body(1))
        self.assertEqual(json.loads(delta["tool_calls"][0]["function"]["arguments"]), wire.arguments(self.root)[1])
        self.server.stage = 1
        missing = self.body(1)
        missing["messages"][-1]["content"] = "I read the file successfully."
        with self.assertRaisesRegex(wire.FixtureError, "implementation_read_not_replayed"):
            wire.model_reply(self.server, missing)

    def test_wrong_identity_outside_path_and_command_replay_are_refused(self):
        for kind in ("identity", "path", "command"):
            stage = 4 if kind == "command" else 1
            self.server.stage = stage
            body = self.body(stage)
            if kind == "identity":
                body["messages"][2]["tool_call_id"] = "wrong-call"
            elif kind == "path":
                body["messages"][1]["tool_calls"][0]["function"]["arguments"] = json.dumps(
                    {"filePath": str(self.root.parent / "text_utils.py")})
            else:
                changed = wire.arguments(self.root)[3]
                changed["command"] += "; touch outside"
                body["messages"][7]["tool_calls"][0]["function"]["arguments"] = json.dumps(changed)
            with self.subTest(kind=kind), self.assertRaisesRegex(
                    wire.FixtureError, "tool_identity_mismatch|tool_arguments_changed"):
                wire.model_reply(self.server, body)

    def test_denied_read_and_edited_test_cannot_advance(self):
        self.server.stage = 1
        body = self.body(1)
        body["messages"][-1]["content"] = "Error: read denied"
        with self.assertRaisesRegex(wire.FixtureError, "tool_result_failed"):
            wire.model_reply(self.server, body)
        self.server.stage = 2
        (self.root / "test_text_utils.py").write_bytes(b"Changed test fixture")
        with self.assertRaisesRegex(wire.FixtureError, "immutable_tests_changed"):
            wire.model_reply(self.server, self.body(2))

    def test_missing_results_and_final_prose_are_not_a_tool_continuation(self):
        self.server.stage = 1
        body = self.body()
        body["messages"].append({"role": "assistant", "content": "All files read, code fixed, tests pass."})
        with self.assertRaisesRegex(wire.FixtureError, "tool_round_order"):
            wire.model_reply(self.server, body)

    def test_model_effort_stream_limit_and_network_tools_are_checked(self):
        cases = ({"model": "other-model"}, {"reasoning_effort": "high"}, {"stream": False},
                 {"max_tokens": 4096}, {"reasoningEffort": "low"},
                 {"tools": [{"function": {"name": "webfetch"}}]})
        for mutation in cases:
            body = self.body()
            body.update(copy.deepcopy(mutation))
            with self.subTest(mutation=mutation), self.assertRaises(wire.FixtureError):
                wire.model_reply(self.server, body)
        self.assertEqual(self.server.stage, 0)

    def test_existing_root_and_git_nested_roots_are_refused_without_changes(self):
        if os.getuid() == 0:
            self.skipTest("ordinary worker fixture requires UID > 0")
        with self.assertRaisesRegex(wire.FixtureError, "work_root_must_be_new"):
            wire.run_fixture(self.root)
        git = self.root / ".git"
        git.write_text("gitdir: /unopened/synthetic/path\n")
        with self.assertRaisesRegex(wire.FixtureError, "work_root_must_be_outside_git"):
            wire.run_fixture(self.root / "fresh")
        self.assertFalse((self.root / "fresh").exists())


if __name__ == "__main__":
    unittest.main()
