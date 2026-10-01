"""Synthetic source fixtures only: no SSH, GPU, service, credentials or models."""
import ast
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import time
import unittest
from unittest import mock

MODULE = Path(__file__).with_name("image_workflow_probe.py")
spec = importlib.util.spec_from_file_location("image_workflow_probe", MODULE)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
ROOT = MODULE.parents[2]


def container():
    return {"id": "a" * 64, "name": "/llm-image-backend", "image": p.CONFIG, "configImage": p.PLATFORM,
            "created": "2026-10-01T00:00:00Z", "pid": 123, "status": "running", "running": True,
            "oomKilled": False, "exitCode": 0, "startedAt": "2026-10-01T00:00:00Z",
            "finishedAt": "0001-01-01T00:00:00Z", "owner": p.OWNER, "invocation": "b" * 32,
            "gpu": p.GPU, "memory": 96 * 1024**3, "memorySwap": 96 * 1024**3,
            "cpuset": "8-15", "mems": "0", "privileged": False, "readonly": True, "restart": "no",
            "devices": [{"driver": "nvidia", "count": 0, "ids": [p.GPU], "capabilities": [["gpu"]]}],
            "mounts": [{"type": "bind", "source": p.MODEL, "destination": "/models", "rw": False}]}


def observation():
    config = {"owner": p.OWNER, "gpu_uuid": p.GPU, "image_id": p.PLATFORM,
              "source_sha256_keys_exact": True, "release_source_sha256_keys_exact": True,
              "source_sha256": {}, "release_source_sha256": {}}
    graph = []
    for field, paths in (("source_sha256", p.RUNTIME_FILES), ("release_source_sha256", p.RELEASE_FILES)):
        for path in paths:
            config[field][path] = "c" * 64
            graph.append({"scope": field, "key": path, "receipt": {"outcome": "READBACK", "sha256": "c" * 64}})
    value = {"schema": p.SCHEMA, "host": p.HOST, "origin": "LIVE_PASSIVE_READBACK", "bootStable": True,
             "selected": {"gpu_inventory": [{"uuid": p.GPU}, {"uuid": p.VISION_GPU}], "systemd_owner": {"MainPID": "123"},
                          "native_container": container(), "native_image": {"id": p.CONFIG}},
             "records": {"config": {"fields": config}, "state": {"fields": {"owner": p.OWNER, "run_id": "b" * 32, "container": {"id": "a" * 64}}}},
             "sourceGraph": graph, "workflowAcceptance": {"generation": "NOT_TESTED", "followup_edit": "NOT_TESTED", "child": "NOT_TESTED"},
             "commands": [{"name": name, "argv": list(item[0]), "exitCode": 0} for name, item in p.COMMANDS.items()],
             "observationResult": "READBACK"}
    value["layers"] = p.assess(value)
    return value


class ProbeTests(unittest.TestCase):
    def test_exact_retained_closure(self):
        closure = json.loads((ROOT / "scripts/image_runtime/source-closure.json").read_text())
        self.assertEqual(tuple(closure["runtime_files"]), p.RUNTIME_FILES)
        self.assertEqual(tuple(closure["release_files"]), p.RELEASE_FILES)
        self.assertEqual(tuple(closure["image_api_files"]), p.API_FILES)
        binding = json.loads((ROOT / "configs/runtimes/h005-runtime-binding.json").read_text())["image"]
        self.assertEqual(binding["image_id"], p.PLATFORM)
        self.assertEqual(binding["image_config_digest"], p.CONFIG)
        self.assertLess(len(p.READ_PATHS), p.CAPS["fileCount"])

    def test_no_imported_runtime_or_shell(self):
        tree = ast.parse(MODULE.read_text())
        imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertNotIn("image_runtime", imports)
        for argv, seconds in p.COMMANDS.values():
            self.assertLessEqual(seconds, 5)
            self.assertNotIn("sudo", argv)
            self.assertNotIn("status", argv)
            self.assertNotIn("restart", argv)
            self.assertNotIn("start", argv)
            self.assertNotIn("stop", argv)
            self.assertNotIn(".Config.Env", " ".join(argv))
            self.assertNotIn(".Config.Cmd", " ".join(argv))
        self.assertEqual(p.SSH[-1], "--remote-observe")
        self.assertIn("BatchMode=yes", p.SSH)

    def test_public_cli_rejects_execution_and_arbitrary_inputs(self):
        for args in (["--execute"], ["--observe", "--host", "attacker"], ["--observe", "--path", "/etc/shadow"],
                     ["--proposal", "--observe"], ["--observe", "--command", "reboot"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                p.main(args)
            self.assertEqual(raised.exception.code, 2)

    def test_disabled_proposal_and_gaps(self):
        with mock.patch.object(p.subprocess, "Popen", side_effect=AssertionError("no commands")):
            value = p.proposal()
        self.assertFalse(value["enabled"])
        self.assertEqual(value["execution"], "DISABLED")
        self.assertIsNone(value["rootGo"])
        self.assertEqual(value["workflowResult"], "NOT_TESTED")
        self.assertEqual(value["identity"]["imageGpu"], p.GPU)
        self.assertEqual(value["identity"]["excludedVisionGpu"], p.VISION_GPU)
        self.assertEqual(len(value["genuineMissingImplementation"]), 3)
        stages = value["stages"]
        self.assertNotEqual(stages[1]["arguments"]["seed"], stages[2]["arguments"]["seed"])
        self.assertIsNone(stages[2]["arguments"]["references"][0]["fileId"])

    def test_json_caps_duplicates_nonfinite(self):
        for raw in (b'{"a":1,"a":2}', b'{"n":NaN}', b'[' * 20 + b'0' + b']' * 20,
                    json.dumps(list(range(129))).encode(), json.dumps("x" * 1025).encode(), b"x" * 65537):
            with self.assertRaises((ValueError, RecursionError)):
                p.strict_json(raw)

    def test_gpu_parser_exact_and_unknown(self):
        raw = (p.GPU + ", 00000000:01:00.0, 49140, 0, 49140, 34\n").encode()
        self.assertEqual(p.parse_command("gpu_inventory", raw)[0]["freeMiB"], 49140)
        with self.assertRaises(ValueError):
            p.parse_command("gpu_inventory", raw + raw)
        with self.assertRaises(ValueError):
            p.parse_command("gpu_inventory", raw.replace(p.GPU.encode(), b"GPU-" + b"-" * 36))
        with self.assertRaises(ValueError):
            p.parse_command("gpu_processes", (p.GPU + ", 0, 100\n").encode())
        link = p.parse_command("image_link", (p.GPU + ", N/A, 4, N/A, 16\n").encode())
        self.assertIsNone(link[0]["currentGen"])

    def test_docker_filtered_valid(self):
        self.assertEqual(p.parse_command("native_container", json.dumps(container()).encode())["gpu"], p.GPU)
        image = {"id": p.CONFIG, "repoDigests": ["repo@" + p.PLATFORM], "os": "linux", "architecture": "amd64", "created": "2026-10-01T00:00:00Z"}
        self.assertEqual(p.parse_command("native_image", json.dumps(image).encode())["id"], p.CONFIG)
        image["repoDigests"] = "not-a-list"
        with self.assertRaises(ValueError):
            p.parse_command("native_image", json.dumps(image).encode())

    def test_docker_untrusted_types_and_fields(self):
        changes = ({"pid": True}, {"memory": -1}, {"owner": None}, {"gpu": "GPU-" + "-" * 36},
                   {"mounts": [{}]}, {"devices": [{"driver": "nvidia", "count": 0, "ids": p.GPU, "capabilities": [["gpu"]]}]},
                   {"devices": [{"driver": "nvidia", "count": 0, "ids": [p.GPU], "capabilities": ["gpu"]}]},
                   {"Env": ["TOKEN=fixture"]})
        for change in changes:
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError, KeyError)):
                p.parse_command("native_container", json.dumps({**container(), **change}).encode())

    def test_projection_excludes_credentials_recovery_tokens_and_unknowns(self):
        value = {"schema_version": 1, "owner": p.OWNER, "phase": "warm", "container": None,
                 "token": "synthetic-secret", "environment": {"TOKEN": "synthetic-secret"}, "history": [{"prompt": "private"}]}
        result = p.project_record("state", value)
        self.assertNotIn("synthetic-secret", json.dumps(result))
        self.assertNotIn("history", result)
        self.assertEqual(p.project_record("recovery", {"token": "synthetic-secret", "status": "active"}), {"status": "active"})

    def test_api_config_model_identifier_and_profiles(self):
        value = {"model_id": "Qwen/Qwen-Image-2.1", "model_revision": p.REV,
                 "profiles": [{"operation": "edit", "size": "1536x864", "references": 1, "transparent": False, "evidence_sha256": "a" * 64}],
                 "credential": "synthetic-secret"}
        projected = p.project_record("api_config", value)
        self.assertEqual(projected["model_id"], "Qwen/Qwen-Image-2.1")
        self.assertEqual(projected["profiles"][0]["size"], "1536x864")
        self.assertNotIn("credential", projected)

    def test_allowlisted_files_refuse_before_open(self):
        f = p.Files(time.monotonic() + 1)
        with mock.patch.object(p.os, "open", side_effect=AssertionError("must not open")):
            raw, receipt = f.read("/etc/shadow")
        self.assertIsNone(raw)
        self.assertEqual(receipt["failure"], "file_not_allowlisted")
        self.assertEqual(receipt["outcome"], "FAILED")

    def test_file_deadline_and_permission_preserve_failure(self):
        f = p.Files(time.monotonic() - 1)
        self.assertEqual(f.read(p.BASE + "/config.json")[1]["outcome"], "FAILED")
        f = p.Files(time.monotonic() + 1)
        with mock.patch.object(p.os, "open", side_effect=PermissionError(13, "fixture-denied")):
            raw, receipt = f.read(p.BASE + "/config.json")
        self.assertIsNone(raw)
        self.assertEqual(receipt["errno"], 13)
        self.assertEqual(receipt["failure"], "file_read_refused")

    def test_proc_deadline_and_no_missing_owner_adoption(self):
        with mock.patch("builtins.open", side_effect=AssertionError("must not read")):
            self.assertEqual(p.proc_stamp(123, "synthetic-boot", time.monotonic() - 1)["outcome"], "NOT_TESTED")
            self.assertEqual(p.proc_stamp(True, "synthetic-boot", time.monotonic() + 1)["outcome"], "UNKNOWN")

    def test_layer_readback_never_pass_or_ready(self):
        value = observation()
        result = p.assess(value)
        self.assertTrue(result["installedSource"]["protectedClosureHashesMatch"])
        self.assertTrue(result["processRuntime"]["selectedOwnerIdentityMatches"])
        self.assertFalse(result["processRuntime"]["authenticOwnershipProven"])
        self.assertEqual(result["processRuntime"]["modelReadiness"], "NOT_TESTED")
        self.assertNotIn('"PASS"', json.dumps(result))
        self.assertEqual(p.assess({})["modelArtifact"]["result"], "UNKNOWN")

    def test_layer_mismatches_fail_identity(self):
        for location, field, v in (("config", "owner", "UNKNOWN"), ("config", "gpu_uuid", p.VISION_GPU),
                                  ("state", "owner", "UNKNOWN"), ("state", "run_id", "d" * 32)):
            value = observation()
            value["records"][location]["fields"][field] = v
            self.assertFalse(p.assess(value)["processRuntime"]["selectedOwnerIdentityMatches"])
        value = observation()
        value["bootStable"] = False
        self.assertFalse(p.assess(value)["processRuntime"]["selectedOwnerIdentityMatches"])

    def test_api_parent_only_identity_is_explicit(self):
        value = observation()
        value["records"]["api_config"] = {"fields": {"runtime_image_digest": p.PARENT}}
        layer = p.assess(value)["apiConfiguration"]
        self.assertTrue(layer["parentOnlyBinding"])
        self.assertFalse(layer["matchesRequiredPlatformManifest"])
        self.assertFalse(layer["staticProfilesAreLiveReadiness"])

    def test_runner_rejects_arbitrary_commands_and_caps(self):
        with self.assertRaises(ValueError):
            p.run_bounded(("reboot",), timeout=1, stdout_cap=10)
        with self.assertRaises(ValueError):
            p.run_bounded(p.SSH, timeout=10000, stdout_cap=10)

    def fixture_run(self, code, timeout=1, cap=1024):
        argv = (sys.executable, "-I", "-B", "-c", code)
        with mock.patch.dict(p.COMMANDS, {"fixture": (argv, 1)}):
            return p.run_bounded(argv, timeout=timeout, stdout_cap=cap, host="SYNTHETIC_LOCAL", cwd=str(ROOT))

    def test_bounded_child_receipt_real_int_exit_and_hashes(self):
        receipt, out, err = self.fixture_run("import sys; print('fixture'); sys.exit(7)")
        self.assertIs(type(receipt["exitCode"]), int)
        self.assertEqual(receipt["exitCode"], 7)
        self.assertEqual(receipt["outcome"], "FAILED")
        self.assertEqual(receipt["stdoutSha256"], p.sha(out))
        self.assertEqual(receipt["stderrSha256"], p.sha(err))
        self.assertTrue(receipt["capturedBytesComplete"])

    def test_bounded_child_byte_and_time_caps(self):
        receipt, out, _ = self.fixture_run("print('x'*100000)", cap=16)
        self.assertEqual(receipt["failure"], "stdout_byte_cap")
        self.assertEqual(len(out), 16)
        self.assertFalse(receipt["capturedBytesComplete"])
        receipt, _, _ = self.fixture_run("import time; time.sleep(5)", timeout=.05)
        self.assertEqual(receipt["failure"], "time_cap")
        self.assertIs(type(receipt["exitCode"]), int)

    def test_failed_command_preserves_original_hash_and_integer_exit(self):
        receipt = {"outcome": "FAILED", "exitCode": 1, "stdoutSha256": p.sha(b""), "stderrSha256": p.sha(b"permission denied\n")}
        with mock.patch.object(p, "run_bounded", return_value=(receipt, b"", b"permission denied\n")):
            result, value = p.command("native_container", time.monotonic() + 1)
        self.assertIsNone(value)
        self.assertEqual(result["stderrLog"], "permission denied\n")
        self.assertEqual(result["exitCode"], 1)
        self.assertEqual(result["stderrSha256"], p.sha(b"permission denied\n"))

    def test_observe_rejects_fake_pass_duplicate_bool_exit_and_malformed(self):
        good = observation()
        bad_pass = copy.deepcopy(good)
        bad_pass["workflowAcceptance"]["generation"] = "PASS"
        bad_exit = copy.deepcopy(good)
        bad_exit["commands"][0]["exitCode"] = False
        bad_layer = copy.deepcopy(good)
        bad_layer["layers"]["liveWorkflowAcceptance"]["result"] = "PASS"
        raws = (json.dumps(bad_pass).encode(), json.dumps(bad_exit).encode(), json.dumps(bad_layer).encode(), b'{"schema":"a","schema":"b"}', b"[" * 2000)
        for raw in raws:
            with mock.patch.object(p, "run_bounded", return_value=({"outcome": "READBACK", "exitCode": 0}, raw, b"")):
                value = p.observe()
            self.assertEqual(value["transportReceipt"]["failure"], "remote_report_invalid")
            self.assertIsNone(value["observation"])

    def test_valid_synthetic_envelope_stays_not_tested(self):
        good = observation()
        with mock.patch.object(p, "run_bounded", return_value=({"outcome": "READBACK", "exitCode": 0}, json.dumps(good).encode(), b"")):
            value = p.observe()
        self.assertEqual(value["workflowAcceptance"], "NOT_TESTED")
        self.assertEqual(value["observation"]["layers"]["liveWorkflowAcceptance"]["result"], "NOT_TESTED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
