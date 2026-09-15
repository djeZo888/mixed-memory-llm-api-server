"""Worker-only controls for Q38B's actual-image probe; native image NOT_TESTED."""
from contextlib import contextmanager, ExitStack, redirect_stdout
import copy
import importlib.util
import io
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "tests/lifecycle/sglang38_fixture/cache_probe.py"
spec = importlib.util.spec_from_file_location("q38b_cache_probe_controls", PATH)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def mountinfo():
    return "\n".join([
        "1 0 0:1 / / ro,relatime - overlay overlay ro",
        "2 1 0:2 / /cache rw,nosuid,nodev - tmpfs tmpfs rw",
        "3 1 0:3 / /models rw,nosuid,nodev,noexec - tmpfs tmpfs rw",
        "4 1 0:4 / /run/secrets rw,nosuid,nodev,noexec - tmpfs tmpfs rw",
    ])


def record():
    return copy.deepcopy(probe.result_record(dict(probe.EXPECTED_PATHS), ["/dev/nvidiactl"]))


def runtime_environment(visible="none"):
    return {"NVIDIA_VISIBLE_DEVICES": visible,
            "NVIDIA_DRIVER_CAPABILITIES": "compute,utility", "CUDA_VISIBLE_DEVICES": ""}


@contextmanager
def synthetic_isolation(*, mounts=None, metadata=None, contents=None, devices=()):
    """Supply OS facts only; exercise the real predicate and isolation checks."""
    metadata, contents = metadata or {}, contents or {}

    def read_text(path):
        assert path == Path("/proc/self/mountinfo")
        return mountinfo() if mounts is None else mounts

    def lstat(path):
        if str(path) in probe.CONTROL_NODES:
            observed = {"/dev/nvidia-modeset": (195, 254), "/dev/nvidiactl": (195, 255),
                        "/dev/nvidia-uvm": (511, 0), "/dev/nvidia-uvm-tools": (511, 1)}
            major, minor = observed[str(path)]
            return metadata.get(str(path), SimpleNamespace(st_mode=stat.S_IFCHR | 0o666,
                                                           st_rdev=(major, minor)))
        assert str(path) in ("/cache", "/models", "/run/secrets")
        return metadata.get(str(path), SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=1000))

    def iterdir(path):
        if path == Path("/dev"):
            return iter(sorted({Path("/dev") / Path(name).relative_to("/dev").parts[0]
                                for name in devices}))
        assert str(path) in ("/models", "/run/secrets")
        return iter(contents.get(str(path), ()))

    def glob(path, pattern):
        assert (str(path), pattern) in (("/dev", "nvidia*"), ("/dev/dri", "*"))
        return [Path(name) for name in devices if Path(name).parent == path
                and (pattern == "*" or Path(name).name.startswith("nvidia"))]

    def exists(path):
        assert str(path) in ("/dev/kfd", "/dev/dxg")
        return str(path) in devices

    with ExitStack() as stack:
        stack.enter_context(patch.object(probe.sys, "platform", "linux"))
        stack.enter_context(patch.object(probe.os, "geteuid", return_value=1000))
        # Linux dev_t observations, independent of the macOS host encoding.
        stack.enter_context(patch.object(probe.os, "major", side_effect=lambda value: value[0]))
        stack.enter_context(patch.object(probe.os, "minor", side_effect=lambda value: value[1]))
        for name, implementation in (("read_text", read_text), ("lstat", lstat),
                                     ("iterdir", iterdir), ("glob", glob), ("exists", exists)):
            stack.enter_context(patch.object(probe.Path, name, autospec=True, side_effect=implementation))
        yield


class CacheProbeTests(unittest.TestCase):
    def test_help_is_available_without_native_import(self):
        with patch.object(probe.importlib, "import_module", side_effect=AssertionError), \
                redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
            probe.main(["--help"])
        self.assertEqual(raised.exception.code, 0)

    def test_non_linux_refuses_before_mount_or_library_access(self):
        with patch.object(probe.sys, "platform", "darwin"), patch.object(probe.Path, "read_text") as read:
            with self.assertRaisesRegex(probe.ProbeError, "linux_pinned_image_required"):
                probe.verify_isolation()
        read.assert_not_called()

    def test_measured_inner_none_and_void_pass_real_isolation_without_environment_rewrite(self):
        for visible in ("none", "void"):
            env = runtime_environment(visible) | {"UNRELATED_ENVIRONMENT": "retained"}
            with self.subTest(visible=visible), patch.dict(os.environ, env, clear=True), \
                    synthetic_isolation(devices=probe.CONTROL_NODES):
                self.assertEqual(probe.verify_isolation(), sorted(probe.CONTROL_NODES))
                self.assertEqual(dict(os.environ), env)

    def test_other_inner_visible_devices_are_refused_before_filesystem_access(self):
        invalid = (None, "", "all", "0", "1", "GPU-01234567-89ab-cdef-0123-456789abcdef",
                   " ", "\t", " none", "none ", "void\n", "NONE", "VOID", "none,void", "unreviewed")
        for value in invalid:
            env = runtime_environment()
            if value is None:
                del env["NVIDIA_VISIBLE_DEVICES"]
            else:
                env["NVIDIA_VISIBLE_DEVICES"] = value
            with self.subTest(value=value), patch.dict(os.environ, env, clear=True), \
                    patch.object(probe.sys, "platform", "linux"), patch.object(probe.Path, "read_text") as read:
                with self.assertRaisesRegex(probe.ProbeError, "no_gpu_runtime_environment_required"):
                    probe.verify_isolation()
                self.assertEqual(dict(os.environ), env)
                read.assert_not_called()

    def test_caps_and_cuda_remain_exact_for_both_allowed_inner_visible_values(self):
        invalid = {
            "NVIDIA_DRIVER_CAPABILITIES": (None, "", "all", "compute", "utility", "utility,compute",
                                           "compute,utility ", " compute,utility", "compute,utility,graphics",
                                           "COMPUTE,UTILITY", "none", "void", "unreviewed"),
            "CUDA_VISIBLE_DEVICES": (None, "none", "void", "all", "0", "1", " ", "\t", "\n",
                                     "GPU-01234567-89ab-cdef-0123-456789abcdef", "unreviewed"),
        }
        for visible in ("none", "void"):
            for name, values in invalid.items():
                for value in values:
                    env = runtime_environment(visible)
                    if value is None:
                        del env[name]
                    else:
                        env[name] = value
                    with self.subTest(visible=visible, name=name, value=value), \
                            patch.dict(os.environ, env, clear=True), patch.object(probe.sys, "platform", "linux"), \
                            patch.object(probe.Path, "read_text") as read:
                        with self.assertRaisesRegex(probe.ProbeError, "no_gpu_runtime_environment_required"):
                            probe.verify_isolation()
                        self.assertEqual(dict(os.environ), env)
                        read.assert_not_called()

    def test_both_allowed_inner_values_preserve_independent_isolation_refusals(self):
        cases = [
            ({"mounts": mountinfo().replace("/ / ro,", "/ / rw,")}, "readonly_container_root_required"),
            ({"mounts": mountinfo().replace("- tmpfs tmpfs", "- ext4 /dev/other", 1)}, "private_tmpfs_required"),
        ]
        for target in ("/cache", "/models", "/run/secrets"):
            for mode, uid in ((stat.S_IFREG | 0o700, 1000), (stat.S_IFLNK | 0o700, 1000),
                              (stat.S_IFDIR | 0o755, 1000), (stat.S_IFDIR | 0o700, 1001)):
                cases.append(({"metadata": {target: SimpleNamespace(st_mode=mode, st_uid=uid)}},
                              "private_directory_required"))
        for target in ("/models", "/run/secrets"):
            cases.append(({"contents": {target: [Path(target) / "unexpected"]}},
                          "empty_model_and_secret_tmpfs_required"))
        for device in ("/dev/nvidia0", "/dev/nvidia1", "/dev/nvidia-caps", "/dev/nvidia-caps/child",
                       "/dev/dri/renderD128", "/dev/dri/card0", "/dev/kfd", "/dev/dxg"):
            cases.append(({"devices": [device]}, "gpu_device_node_present"))
        for visible in ("none", "void"):
            for filesystem, code in cases:
                env = runtime_environment(visible)
                with self.subTest(visible=visible, filesystem=filesystem, code=code), \
                        patch.dict(os.environ, env, clear=True), synthetic_isolation(**filesystem):
                    with self.assertRaisesRegex(probe.ProbeError, code):
                        probe.verify_isolation()
                    self.assertEqual(dict(os.environ), env)

    def test_readonly_root_and_exact_private_tmpfs_required(self):
        probe.check_mounts(mountinfo())
        bad = [mountinfo().replace("/ / ro,", "/ / rw,"),
               mountinfo().replace("- tmpfs tmpfs", "- ext4 /dev/other", 1),
               mountinfo() + "\n" + mountinfo().splitlines()[1],
               "\n".join(mountinfo().splitlines()[:-1])]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(probe.ProbeError):
                probe.check_mounts(value)

    def test_only_bounded_control_nodes_allowed_and_gpu_nodes_rejected(self):
        self.assertEqual(probe.check_device_names(["/dev/null", *probe.CONTROL_NODES]),
                         sorted(probe.CONTROL_NODES))
        for device in ("/dev/nvidia0", "/dev/nvidia1", "/dev/nvidia-caps", "/dev/nvidia-modeset/child",
                       "/dev/dri/renderD128", "/dev/dri/card0", "/dev/kfd", "/dev/dxg"):
            with self.subTest(device=device), self.assertRaisesRegex(probe.ProbeError, "gpu_device_node_present"):
                probe.check_device_names([device])

    def test_observed_control_metadata_passes_without_opening_nodes(self):
        observed = {"/dev/nvidia-modeset": (195, 254), "/dev/nvidiactl": (195, 255),
                    "/dev/nvidia-uvm": (511, 0), "/dev/nvidia-uvm-tools": (511, 1)}
        metadata = {name: SimpleNamespace(st_mode=stat.S_IFCHR | 0o666,
                                         st_rdev=numbers)
                    for name, numbers in observed.items()}
        with patch.dict(os.environ, runtime_environment("void"), clear=True), \
                synthetic_isolation(devices=observed, metadata=metadata), \
                patch.object(probe.os, "open", side_effect=AssertionError("device opened")):
            self.assertEqual(probe.verify_isolation(), sorted(observed))

    def test_control_names_cannot_hide_gpu_numbers_symlinks_or_directories(self):
        for name in probe.CONTROL_NODES:
            for mode, device in ((stat.S_IFCHR, (195, 0)), (stat.S_IFCHR, (195, 1)),
                                 (stat.S_IFCHR, (226, 0)), (stat.S_IFCHR, (226, 128)),
                                 (stat.S_IFLNK, (0, 0)), (stat.S_IFDIR, (0, 0)),
                                 (stat.S_IFREG, (0, 0)), (stat.S_IFBLK, (195, 254))):
                meta = SimpleNamespace(st_mode=mode | 0o666, st_rdev=device)
                with self.subTest(name=name, mode=mode, device=device), \
                        patch.dict(os.environ, runtime_environment(), clear=True), \
                        synthetic_isolation(devices=[name], metadata={name: meta}), \
                        self.assertRaisesRegex(probe.ProbeError, "cache_control_nodes_invalid"):
                    probe.verify_isolation()

    def test_uvm_character_nodes_allow_dynamic_majors(self):
        for major in (234, 510, 511):
            metadata = {name: SimpleNamespace(st_mode=stat.S_IFCHR | 0o666,
                                             st_rdev=(major, minor))
                        for name, minor in (("/dev/nvidia-uvm", 0), ("/dev/nvidia-uvm-tools", 1))}
            with self.subTest(major=major), patch.dict(os.environ, runtime_environment(), clear=True), \
                    synthetic_isolation(devices=probe.CONTROL_NODES, metadata=metadata):
                self.assertEqual(probe.verify_isolation(), sorted(probe.CONTROL_NODES))

    def test_accelerator_roots_rejected_without_traversal_or_symlink_following(self):
        for name in ("/dev/dri", "/dev/nvidia-caps", "/dev/kfd", "/dev/dxg"):
            with self.subTest(name=name), patch.dict(os.environ, runtime_environment(), clear=True), \
                    synthetic_isolation(devices=[name]), \
                    self.assertRaisesRegex(probe.ProbeError, "gpu_device_node_present"):
                probe.verify_isolation()

    def test_exact_paths_reject_drift_before_any_writes(self):
        probe.check_paths(probe.EXPECTED_PATHS)
        for name in probe.EXPECTED_PATHS:
            bad = dict(probe.EXPECTED_PATHS)
            bad[name] = "/root/.cache/escape"
            with self.subTest(name=name), self.assertRaisesRegex(probe.ProbeError, "cache_resolved_path_mismatch"):
                probe.check_paths(bad)
        with self.assertRaises(probe.ProbeError):
            probe.check_paths({})

    def test_writability_check_writes_and_removes_only_own_probe(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "sglang/jit"
            target.mkdir(parents=True)
            sentinel = target / "unrelated"
            sentinel.write_text("retain")
            probe.prove_writable({"one": str(target), "duplicate": str(target)}, root)
            self.assertEqual(sorted(path.name for path in target.iterdir()), ["unrelated"])
            self.assertEqual(sentinel.read_text(), "retain")

    def test_writability_check_refuses_symlink_and_escape(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as other:
            root = Path(temp)
            (root / "escape").symlink_to(other, target_is_directory=True)
            with self.assertRaises(OSError):
                probe.prove_writable({"bad": str(root / "escape/child")}, root)
            self.assertEqual(list(Path(other).iterdir()), [])
            for target in (str(root / "../escaped"), str(root)):
                with self.subTest(target=target), self.assertRaises(probe.ProbeError):
                    probe.prove_writable({"bad": target}, root)

    def test_failed_write_still_removes_private_probe(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(probe.os, "write", return_value=0), self.assertRaisesRegex(probe.ProbeError, "cache_write_failed"):
                probe.prove_writable({"cache": str(root / "sglang")}, root)
            self.assertEqual(list((root / "sglang").iterdir()), [])

    def test_receipt_validator_is_pure_and_exact(self):
        with patch.object(probe.importlib, "import_module", side_effect=AssertionError), \
                patch.object(probe.Path, "resolve", side_effect=AssertionError), \
                patch.object(probe.ctypes, "CDLL", side_effect=AssertionError):
            probe.validate_result(record())
        for name in record():
            bad = record()
            bad[name] = "unreviewed"
            with self.subTest(name=name), self.assertRaises(probe.ProbeError):
                probe.validate_result(bad)
        bad = record()
        bad["unreviewed"] = "PASS"
        with self.assertRaises(probe.ProbeError):
            probe.validate_result(bad)

    def test_receipt_rejects_boolean_integer_aliases_and_control_node_drift(self):
        for name, value in (("schema_version", True), ("native_torch_device_count", False),
                            ("native_torch_cuda_available", 0),
                            ("global_driver_control_nodes", ["/dev/nvidia0"]),
                            ("global_driver_control_nodes", ["/dev/nvidiactl"] * 2)):
            bad = record()
            bad[name] = value
            with self.subTest(name=name, value=value), self.assertRaises(probe.ProbeError):
                probe.validate_result(bad)

    def test_run_orders_isolation_and_source_before_native_resolvers(self):
        events = []
        torch = SimpleNamespace(cuda=SimpleNamespace(device_count=lambda: 0, is_available=lambda: False))
        with ExitStack() as stack:
            stack.enter_context(patch.object(probe, "verify_isolation", side_effect=lambda: events.append("isolation") or []))
            stack.enter_context(patch.object(probe, "verify_sources", side_effect=lambda repo: events.append("sources")))
            stack.enter_context(patch.object(probe.ctypes, "CDLL", side_effect=lambda lib: events.append(lib)))
            stack.enter_context(patch.object(probe.importlib, "import_module", side_effect=lambda name: events.append(name) or torch))
            stack.enter_context(patch.object(probe, "resolve_paths", side_effect=lambda: events.append("resolvers") or dict(probe.EXPECTED_PATHS)))
            stack.enter_context(patch.object(probe, "prove_writable", side_effect=lambda paths: events.append("write")))
            result = probe.run(Path("/fixture"))
        probe.validate_result(result)
        self.assertEqual(events, ["isolation", "sources", "libcuda.so.1", "libnvidia-ml.so.1",
                                  "torch", "resolvers", "write", "isolation"])

    def test_visible_gpu_refuses_before_resolving_or_writing(self):
        torch = SimpleNamespace(cuda=SimpleNamespace(device_count=lambda: 1, is_available=lambda: True))
        with patch.object(probe, "verify_isolation", return_value=[]), patch.object(probe, "verify_sources"), \
                patch.object(probe.ctypes, "CDLL"), patch.object(probe.importlib, "import_module", return_value=torch), \
                patch.object(probe, "resolve_paths") as resolve, self.assertRaisesRegex(probe.ProbeError, "gpu_visible"):
            probe.run(Path("/fixture"))
        resolve.assert_not_called()

    def test_missing_driver_library_stops_before_native_import(self):
        with patch.object(probe, "verify_isolation", return_value=[]), patch.object(probe, "verify_sources"), \
                patch.object(probe.ctypes, "CDLL", side_effect=OSError("driver-library-missing")), \
                patch.object(probe.importlib, "import_module") as imported, self.assertRaises(OSError):
            probe.run(Path("/fixture"))
        imported.assert_not_called()

    def test_receipt_builder_does_not_share_mutable_source_pins(self):
        result = probe.result_record(dict(probe.EXPECTED_PATHS), [])
        result["source_hashes"]["sglang"]["__init__.py"] = "drift"
        self.assertNotEqual(probe.SOURCE_PINS["sglang"]["__init__.py"], "drift")
        with self.assertRaises(probe.ProbeError):
            probe.validate_result(result)

    def test_native_import_or_library_failure_has_no_fallback_and_no_exception_disclosure(self):
        output = io.StringIO()
        with patch.object(probe, "run", side_effect=OSError("protected-diagnostic-sentinel")), redirect_stdout(output):
            self.assertEqual(probe.main(["--actual-image", "--repo", "/fixture"]), 1)
        self.assertNotIn("protected-diagnostic-sentinel", output.getvalue())
        self.assertIn("q38b_cache_probe_failed", output.getvalue())

    def test_launch_cache_overrides_are_only_two_reviewed_additions(self):
        launcher_spec = importlib.util.spec_from_file_location("q38b_cache_launcher_test", ROOT / "scripts/runtime/sglang38_file_auth.py")
        launcher = importlib.util.module_from_spec(launcher_spec)
        launcher_spec.loader.exec_module(launcher)
        env = launcher.CACHE_ENVIRONMENT
        self.assertEqual({key: value for key, value in env.items() if key.startswith("SGLANG_")},
                         {"SGLANG_CACHE_DIR": "/cache/sglang", "SGLANG_JIT_CACHE_DIR": "/cache/sglang/jit"})
        self.assertNotIn("HOME", env)


if __name__ == "__main__":
    unittest.main()
