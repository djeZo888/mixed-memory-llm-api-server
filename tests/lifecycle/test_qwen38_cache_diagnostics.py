"""Cache failure serialization controls; fake children/Docker, native NOT_TESTED."""
import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
from types import FunctionType
import unittest
from unittest.mock import patch

from tests.lifecycle.test_qwen38_cache_probe import (
    probe, record as cache_result, synthetic_isolation, runtime_environment,
)
from tests.lifecycle.test_qwen38_fixture_lifetime import (
    DockerDaemon, OWN_ID, SENTINEL_ID, host, response,
)
from tests.lifecycle.test_qwen38_image_fixture import ROOT, inner, inspected


# Intentionally combines credential shape, quotes, backslash and braces. Fake only.
SENTINEL = 'Bearer Q38VC_SYNTHETIC_"\\}{api_key=fixture-only}'
GENERIC = "q38b_cache_probe_failed"


def safe_record(**changes):
    value = {"status": "FAIL", "code": "private_tmpfs_required", "failure_origin": {
        "filename": "cache_probe.py", "line": 147, "exception_class": "ProbeError"}}
    value.update(changes)
    return value


class CacheFailureDiagnosticTests(unittest.TestCase):
    def assert_secret_absent(self, value):
        rendered = value if type(value) is str else json.dumps(value, sort_keys=True)
        escaped = SENTINEL
        for _ in range(3):
            self.assertNotIn(escaped, rendered, "synthetic diagnostic content disclosed")
            escaped = json.dumps(escaped)[1:-1]

    def probe_output(self, action):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(probe, "run", side_effect=action), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = probe.main(["--actual-image", "--repo", str(ROOT)])
        self.assertEqual(code, 1)
        self.assertEqual(stderr.getvalue(), "")
        self.assert_secret_absent(stdout.getvalue())
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["status"], "FAIL")
        self.assertIn(set(result), ({"status", "code", "failure_origin"},
                                    {"status", "code", "failure_origin", "device_failure"}))
        return response([], code, stdout.getvalue().encode(), stderr.getvalue().encode())

    def inner_output(self, child):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(inner.os.environ, runtime_environment(), clear=True), \
                patch.object(inner, "verify_sources", return_value=ROOT / "unused.py"), \
                patch.object(inner.subprocess, "run", return_value=child) as process, \
                patch.object(inner.os, "write") as private_stderr, \
                patch.object(inner, "run_failure_children") as later, \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = inner.main(["--actual-image", "--repo", str(ROOT), "--context", "131072"])
        self.assertEqual(code, 2)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(process.call_count, 1)
        command = process.call_args.args[0]
        self.assertEqual(command[1:4], ["-X", "faulthandler", "-B"])
        self.assertEqual(Path(command[4]).name, "cache_probe.py")
        self.assertEqual(process.call_args.kwargs["timeout"], 120)
        later.assert_not_called()
        self.assert_secret_absent(stdout.getvalue())
        value = json.loads(stdout.getvalue())
        self.assertEqual(value["status"], "FAIL")
        self.assertEqual(value["code"], "actual_image_fixture_failed")
        self.assertEqual(value["failure_origin"]["filename"], "run_pinned_image.py")
        return response([], code, stdout.getvalue().encode()), value

    def host_output(self, child):
        """Run real host main/run/lifetime; replace only external I/O collaborators."""
        daemon = DockerDaemon()

        def docker(command, *, timeout):
            if command[1:3] != ["container", "start"]:
                return daemon(command, timeout=timeout)
            daemon.calls.append((command, timeout))
            daemon.attached = True
            daemon.objects[OWN_ID]["State"].update(
                Running=False, Pid=0, Status="exited", ExitCode=child.returncode)
            return response(command, child.returncode, child.stdout, child.stderr)

        stdout, stderr = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "receipt.json"
            with patch.object(host, "validate_output_path"), \
                    patch.object(host, "read_provenance", return_value=({}, {})), \
                    patch.object(host.subprocess, "run", return_value=response(
                        [], stdout=json.dumps(inspected()).encode())) as image_inspect, \
                    patch.object(host, "docker_call", side_effect=docker), \
                    patch.object(host, "check_native_result") as accept, \
                    patch.object(host, "write_receipt") as publish, \
                    redirect_stdout(stdout), redirect_stderr(stderr):
                code = host.main(["--repo", str(ROOT), "--output", str(output)])
            self.assertEqual(code, 1)
            self.assertEqual(stderr.getvalue(), "")
            self.assertFalse(output.exists())
            accept.assert_not_called()
            publish.assert_not_called()
            self.assertEqual(image_inspect.call_count, 1)
            self.assertEqual(image_inspect.call_args.args[0][:3], ["docker", "image", "inspect"])
        emitted = json.loads(stdout.getvalue())
        self.assert_secret_absent(stdout.getvalue())
        self.assertEqual(emitted["status"], "FAIL")
        lifetime = emitted["lifetime"]
        self.assertEqual(lifetime["outcome"], "ATTACH_FAILED")
        self.assertEqual(lifetime["cleanup"], "QUIESCENT_REMOVAL_VERIFIED")
        self.assertEqual(lifetime["container_id"], OWN_ID)
        self.assertNotIn(OWN_ID, daemon.objects)
        self.assertEqual(daemon.objects[SENTINEL_ID], daemon.sentinel)
        creates = [cmd for cmd, _ in daemon.calls if cmd[1] == "create"]
        self.assertEqual(len(creates), 1)
        self.assertEqual(creates[0][-2:], ["--context", "131072"])
        mutations = [cmd for cmd, _ in daemon.calls
                     if cmd[1:3] in (["container", "stop"], ["container", "rm"])]
        self.assertEqual(len(mutations), 1)
        self.assertEqual(mutations[0][1:3], ["container", "rm"])
        self.assertEqual(mutations[0][-1], OWN_ID)
        self.assertNotIn("--force", mutations[0])
        diagnostic = lifetime["attach_diagnostic"]
        self.assertEqual(diagnostic["cli_returncode"], 2)
        self.assertEqual(diagnostic["failure_kind"], "CLI_NONZERO_EXIT")
        self.assertEqual(diagnostic["container_before_cleanup_stop"], {
            "status": "EXITED", "exit_code": 2, "signal": None})
        self.assertEqual(diagnostic["stdout"]["captured_bytes"], len(child.stdout))
        return diagnostic["failure_metadata"]

    def pipeline(self, child):
        inner_child, emitted = self.inner_output(child)
        return emitted, self.host_output(inner_child)

    def test_known_real_probe_callsite_survives_every_failure_boundary(self):
        child = self.probe_output(lambda _repo: probe.check_mounts(""))
        record = json.loads(child.stdout)
        self.assertEqual(record["code"], "private_tmpfs_required")
        origin = record["failure_origin"]
        self.assertEqual(origin["filename"], "cache_probe.py")
        self.assertEqual(origin["exception_class"], "ProbeError")
        self.assertIs(type(origin["line"]), int)
        self.assertIn(origin["line"], range(probe.check_mounts.__code__.co_firstlineno,
                                           probe.check_device_names.__code__.co_firstlineno))
        with patch.object(inner.subprocess, "run", return_value=child):
            with self.assertRaisesRegex(inner.FixtureFailure, "^cache_probe_child_failed$") as caught:
                inner.run_cache_probe(ROOT)
        self.assertEqual(caught.exception.cache_failure, record)
        emitted, metadata = self.pipeline(child)
        self.assertEqual(emitted["cache_failure"], record)
        self.assertEqual(metadata["cache_failure"], record)
        self.assertEqual(metadata["status"], "SAFE_ORIGIN")
        self.assertEqual(metadata["origin"], emitted["failure_origin"])

    def test_caps_failure_safe_facts_survive_existing_boundaries_without_child_names(self):
        with patch.dict(os.environ, runtime_environment(), clear=True), \
                synthetic_isolation(devices=[probe.CAPS_DIRECTORY],
                    contents={probe.CAPS_DIRECTORY: [SENTINEL]}):
            child = self.probe_output(lambda _repo: probe.verify_isolation())
        record = json.loads(child.stdout)
        self.assertEqual(record["code"], "gpu_device_node_present")
        self.assertEqual(record["device_failure"], {
            "path": "/dev/nvidia-caps", "type": "DIRECTORY", "uid_root": True,
            "gid_root": True, "mode_0755": True, "has_entries": True})
        emitted, metadata = self.pipeline(child)
        self.assertEqual(emitted["cache_failure"], record)
        self.assertEqual(metadata["cache_failure"], record)
        self.assertEqual(metadata["status"], "SAFE_ORIGIN")

    def test_device_diagnostics_mask_unknown_names_and_never_follow_descendants(self):
        for name, expected in (("/dev/nvidia0", "/dev/nvidia0"),
                               ("/dev/dri/renderD128", "/dev/dri/renderD128"),
                               ("/dev/nvidia-" + SENTINEL, "OTHER_ACCELERATOR_PATH"),
                               ("/dev/nvidia-caps/" + SENTINEL, "OTHER_ACCELERATOR_PATH")):
            with self.subTest(expected=expected), patch.object(probe.Path, "lstat",
                    side_effect=FileNotFoundError()) as checked:
                child = self.probe_output(lambda _repo: probe.check_device_names([name]))
                if Path(name).parent != Path("/dev"):
                    checked.assert_not_called()
            record = json.loads(child.stdout)
            self.assertEqual(record["device_failure"]["path"], expected)
            self.assertEqual(record["device_failure"]["type"], "UNAVAILABLE")
            self.assertIsNone(record["device_failure"]["has_entries"])
            self.assert_secret_absent(record)

    def test_device_failure_parser_refuses_extra_paths_types_counts_or_success_claims(self):
        facts = {"path": "/dev/nvidia-caps", "type": "DIRECTORY", "uid_root": True,
                 "gid_root": True, "mode_0755": True, "has_entries": True}
        valid = safe_record(code="gpu_device_node_present", device_failure=facts)
        accepted = probe.validate_failure(valid)
        self.assertEqual(accepted, valid)
        self.assertIsNot(accepted["device_failure"], facts)
        self.assertEqual(probe.failure_metadata(json.dumps(valid).encode()), valid)
        invalid = [safe_record(device_failure=facts),
                   safe_record(code="gpu_device_node_present", status="PASS", device_failure=facts)]
        for field, values in {
            "path": (SENTINEL, "/dev/nvidia-caps/child", "/dev/nvidia" + "1" * 64,
                     "/dev/dri/../secret", True, None),
            "type": (SENTINEL, "EMPTY", "PASS", True, None),
            "uid_root": (0, 1, "true", [], {}),
            "gid_root": (0, 1, "true", [], {}),
            "mode_0755": (755, "0755", 1),
            "has_entries": (0, 1, "empty", [], {}, SENTINEL),
        }.items():
            for value in values:
                bad = copy.deepcopy(valid)
                bad["device_failure"][field] = value
                invalid.append(bad)
        bad = copy.deepcopy(valid)
        bad["device_failure"]["filename"] = SENTINEL
        invalid.append(bad)
        for index, value in enumerate(invalid):
            with self.subTest(index=index):
                self.assertIsNone(probe.validate_failure(value))
                self.assertIsNone(probe.failure_metadata(json.dumps(value).encode()))
        raw = json.dumps(valid).encode()
        self.assertIsNone(probe.failure_metadata(raw.replace(b'"has_entries": true',
            b'"has_entries": true, "has_entries": true')))
        self.assertIsNone(probe.failure_metadata(raw + b" " * 2048))
        self.assertNotIn("device_failure", cache_result())

    def test_unknown_error_and_hostile_text_class_or_code_remain_generic_failures(self):
        errors = [RuntimeError(SENTINEL), probe.ProbeError(SENTINEL),
                  probe.ProbeError("private_tmpfs_required", SENTINEL),
                  probe.ProbeError([SENTINEL]),
                  type(SENTINEL, (RuntimeError,), {})(SENTINEL),
                  type("ProbeError", (probe.ProbeError,), {})("private_tmpfs_required"),
                  type("ValueError", (ValueError,), {})(SENTINEL)]
        for index, error in enumerate(errors):
            with self.subTest(case=index):
                child = self.probe_output(error)
                record = json.loads(child.stdout)
                self.assertEqual(record["code"], GENERIC)
                expected_class = "RuntimeError" if type(error) is RuntimeError else (
                    "ProbeError" if type(error) is probe.ProbeError else "OTHER")
                self.assertEqual(record["failure_origin"]["exception_class"], expected_class)
                emitted, metadata = self.pipeline(child)
                self.assertEqual(emitted["cache_failure"], record)
                self.assertEqual(metadata["cache_failure"], record)

    def test_hostile_external_path_is_never_an_approved_origin(self):
        path = "/untrusted/" + SENTINEL + "/cache_probe.py"
        namespace = {"error": ValueError(SENTINEL)}
        exec(compile("def fail():\n    raise error\n", path, "exec"), namespace)
        try:
            namespace["fail"]()
        except ValueError as error:
            record = probe.failure_record(error)
        self.assertIsNone(record["failure_origin"])
        self.assertEqual(record["code"], GENERIC)
        child = self.probe_output(lambda _repo: namespace["fail"]())
        self.assertEqual(json.loads(child.stdout)["failure_origin"]["filename"], "cache_probe.py")
        emitted, metadata = self.pipeline(child)
        self.assert_secret_absent(record)
        self.assert_secret_absent(emitted)
        self.assert_secret_absent(metadata)
        self.assertNotIn(path, json.dumps(metadata))

    def test_matching_path_or_code_alone_cannot_claim_approved_origin(self):
        namespace = {}
        exec(compile("def fail():\n    raise ValueError()\n", probe.__file__, "exec"), namespace)
        same_path_and_globals = FunctionType(namespace["fail"].__code__, probe.__dict__)
        real_code_foreign_globals = FunctionType(probe.check_mounts.__code__, dict(probe.__dict__))
        for call in (same_path_and_globals, lambda: real_code_foreign_globals("")):
            with self.subTest(call=call.__name__):
                try:
                    call()
                except Exception as error:
                    record = probe.failure_record(error)
                else:
                    self.fail("synthetic exception did not occur")
                self.assertIsNone(record["failure_origin"])
                self.assert_secret_absent(record)

    def test_traceback_overflow_discards_structural_detail_and_preserves_failure(self):
        def deep(depth):
            if depth:
                return deep(depth - 1)
            raise ValueError(SENTINEL)

        child = self.probe_output(lambda _repo: deep(70))
        record = json.loads(child.stdout)
        self.assertEqual(record, {"status": "FAIL", "code": GENERIC, "failure_origin": None})
        emitted, metadata = self.pipeline(child)
        self.assertEqual(emitted["cache_failure"], record)
        self.assertEqual(metadata["cache_failure"], record)

    def test_failure_validator_makes_fresh_exact_records_with_strict_types(self):
        for line in (1, 100000):
            source = safe_record()
            source["failure_origin"]["line"] = line
            clean = probe.validate_failure(source)
            self.assertEqual(clean, source)
            self.assertIsNot(clean, source)
            self.assertIsNot(clean["failure_origin"], source["failure_origin"])
            source["failure_origin"]["filename"] = SENTINEL
            self.assertEqual(clean["failure_origin"]["filename"], "cache_probe.py")
        self.assertEqual(probe.validate_failure(safe_record(failure_origin=None)),
                         safe_record(failure_origin=None))
        invalid = [None, [], (), True, "FAIL", {"status": "FAIL", "code": GENERIC}]
        for field in ("status", "code", "failure_origin"):
            for value in (True, 0, [], {}, SENTINEL):
                invalid.append(safe_record(**{field: value}))
        for field in ("filename", "exception_class"):
            for value in (True, 0, [], {}, SENTINEL):
                record = safe_record()
                record["failure_origin"][field] = value
                invalid.append(record)
        for line in (True, False, 0, -1, 100001, 1.5, "1", None, [], {}):
            record = safe_record()
            record["failure_origin"]["line"] = line
            invalid.append(record)
        invalid += [safe_record(extra=SENTINEL), safe_record(status="PASS")]
        extra_origin = safe_record()
        extra_origin["failure_origin"]["text"] = SENTINEL
        invalid.append(extra_origin)
        for index, value in enumerate(invalid):
            with self.subTest(case=index):
                self.assertIsNone(probe.validate_failure(value))

    def test_child_parser_is_whole_strict_unique_bounded_json(self):
        raw = json.dumps(safe_record()).encode()
        self.assertEqual(probe.failure_metadata(raw), safe_record())
        self.assertEqual(probe.failure_metadata(raw + b" " * (2048 - len(raw))), safe_record())
        invalid = [b"", b"\xff", raw[:-1], raw + raw, b"log\n" + raw, b"[]", b"null",
                   raw.decode(), bytearray(raw), raw + b" " * (2049 - len(raw)),
                   b"[" * 1000 + b"]" * 1000,
                   raw.replace(b'"status": "FAIL"', b'"status": "FAIL", "status": "FAIL"'),
                   raw.replace(b'"line": 147', b'"line": 147, "line": 147')]
        for literal in (b"NaN", b"Infinity", b"-Infinity", b"true", b"1e999"):
            invalid.append(raw.replace(b'"line": 147', b'"line": ' + literal))
        for index, value in enumerate(invalid):
            with self.subTest(case=index):
                self.assertIsNone(probe.failure_metadata(value))

    def test_hostile_payload_fields_and_oversize_are_dropped_across_real_boundaries(self):
        records = [safe_record(code=SENTINEL), safe_record(extra=SENTINEL),
                   safe_record(failure_origin={"filename": SENTINEL, "line": 1,
                                               "exception_class": "ProbeError"}),
                   safe_record(failure_origin={"filename": "cache_probe.py", "line": 1,
                                               "exception_class": SENTINEL}),
                   safe_record(failure_origin={"filename": "cache_probe.py", "line": 1,
                                               "exception_class": "ProbeError", "text": SENTINEL})]
        payloads = [json.dumps(value).encode() for value in records]
        payloads += [(SENTINEL + "\n").encode(),
                     json.dumps(safe_record()).encode() + b" " * 2048,
                     json.dumps(safe_record()).encode() + b" " * 131073]
        for index, payload in enumerate(payloads):
            with self.subTest(case=index):
                emitted, metadata = self.pipeline(response([], 1, payload))
                self.assertNotIn("cache_failure", emitted)
                self.assertNotIn("cache_failure", metadata)
                self.assertEqual(metadata["status"], "SAFE_ORIGIN")

    def test_outer_parser_revalidates_child_record_and_rejects_nested_extra_or_duplicates(self):
        value = {"status": "FAIL", "code": "actual_image_fixture_failed",
                 "failure_origin": {"filename": "run_pinned_image.py", "line": 580,
                                    "exception_class": "FixtureFailure"},
                 "cache_failure": safe_record()}
        self.assertEqual(host.failure_metadata(json.dumps(value).encode())["cache_failure"], safe_record())
        fixed = copy.deepcopy(value)
        fixed["failure_origin"] = None
        metadata = host.failure_metadata(json.dumps(fixed).encode())
        self.assertEqual(metadata["status"], "FIXED_FAILURE_ONLY")
        self.assertEqual(metadata["cache_failure"], safe_record())
        invalid = []
        for key, item in (("code", SENTINEL), ("extra", SENTINEL), ("failure_origin", None)):
            bad = copy.deepcopy(value)
            bad["cache_failure"][key] = item
            if key == "failure_origin":
                bad["cache_failure"]["failure_origin"] = {"filename": SENTINEL}
            invalid.append(json.dumps(bad).encode())
        raw = json.dumps(value).encode()
        invalid += [raw.replace(b'"line": 147', b'"line": 147, "line": 147'),
                    raw.replace(b'"line": 147', b'"line": true'),
                    raw.replace(b'"line": 147', b'"line": NaN'),
                    raw + b" " * 4096]
        for index, payload in enumerate(invalid):
            with self.subTest(case=index):
                metadata = host.failure_metadata(payload)
                self.assertEqual(metadata, {"status": "REJECTED_OR_UNAVAILABLE"})
                self.assert_secret_absent(metadata)

    def test_existing_nonzero_stderr_size_and_success_validation_gates_still_fail(self):
        known = json.dumps(safe_record()).encode()
        cases = [response([], 1, json.dumps(cache_result()).encode()),
                 response([], 1, known, SENTINEL.encode()),
                 response([], 0, known, SENTINEL.encode()),
                 response([], 0, known + b" " * 131073),
                 response([], 1, known + b" " * 131073),
                 response([], 0, known)]
        for index, child in enumerate(cases):
            with self.subTest(case=index):
                emitted, metadata = self.pipeline(child)
                self.assertNotIn("cache_failure", emitted)
                self.assertNotIn("cache_failure", metadata)

    def test_failure_diagnostics_cannot_enter_existing_pass_receipts(self):
        result = cache_result()
        result["cache_failure"] = safe_record()
        with self.assertRaises(probe.ProbeError):
            probe.validate_result(result)
        from tests.lifecycle.test_qwen38 import bound, auth_receipt, q, LifecycleError
        proof, _ = auth_receipt(bound())
        identity = {name: proof[name] for name in (
            "image_id", "image_reference", "source_revision", "launcher_sha256")}
        q._validate_auth_proof(proof, identity)
        proof["container_lifetimes"][0]["attach_diagnostic"] = {"cache_failure": safe_record()}
        with self.assertRaises(LifecycleError):
            q._validate_auth_proof(proof, identity)


if __name__ == "__main__":
    unittest.main()
