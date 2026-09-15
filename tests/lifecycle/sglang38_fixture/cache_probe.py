#!/usr/bin/env python3
"""Pinned-image cache resolver and driver-library probe; no model/key/GPU work.

Invoke only in run_fixture.py's verified disposable container, before fixture
files or hardware stubs exist. This file imports genuine installed resolvers;
there is no source-extraction fallback and no build, download or GPU kernel.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import ctypes
import hashlib
import importlib
import importlib.metadata
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys

SOURCE_REVISION = "0bcd822377da7b5718e674eaf9c870d349424dd1"
RUNTIME_ENVIRONMENT = {
    "NVIDIA_VISIBLE_DEVICES": "none",
    "NVIDIA_DRIVER_CAPABILITIES": "compute,utility",
    "CUDA_VISIBLE_DEVICES": "",
}
# Exact public source files independently reviewed for resolver behavior.
SOURCE_PINS = {
    "sglang": {
        "__init__.py": "0c6bd1b5bc75da013d49d26f7799ca36d682779293405dce1adc193b97a0e6bd",
        "srt/environ.py": "a39ae8475f2bff6e5cea99f0675bcb6d6647c07540b4b5be65fa7b0b916327cd",
        "kernels/jit/utils/compile/cache.py": "45d4b3ae569886b2ea286b6feef93e618153386776c3d563a08e1fb0028f9157",
        "kernels/jit/utils/arch.py": "b24cdb3c2e0f8187b188253ca47f666725b521f911690f5a4246f528e8917290",
    },
    "flashinfer": {
        "jit/env.py": "c3955fd0b83154356942840c1217e7c64a3602766feddbd701f814bae25ff47e",
        "compilation_context.py": "65d3afe9c069f9d685a9f99a15e307f02d966a7112681e2d1d5ca70c054336cd",
    },
    "torch": {
        "_inductor/runtime/cache_dir_utils.py": "e009cb55b15513c48d84e02d1d3b498cce90f8b33cc000697dbbbc751d92e24b",
        "utils/cpp_extension.py": "1494e212b205f4485267c7a89017929dca30f748ae55aec792557d460a83447a",
    },
    "transformers": {
        "utils/hub.py": "757c6172bdf0f056eb53e32add7842b4fe57d2b1fd68a492cb3cc0b60fffac4c",
    },
}
VERSIONS = {"sglang": "0.5.19", "flashinfer-python": "0.6.18",
            "torch": "2.13.0", "transformers": "5.12.1"}
EXPECTED_PATHS = {
    "sglang": "/cache/sglang",
    "sglang_deep_gemm": "/cache/sglang/deep_gemm",
    "sglang_jit": "/cache/sglang/jit/sm00/q38b_resolver_probe/build-0000000000000000",
    "huggingface_home": "/cache/huggingface",
    "huggingface_hub": "/cache/huggingface/hub",
    "huggingface_assets": "/cache/huggingface/assets",
    "transformers_modules": "/cache/huggingface/modules",
    "triton": "/cache/triton/q38b_resolver_probe",
    "torchinductor": "/cache/torchinductor",
    "torch_extensions": "/cache/torch_extensions",
    "flashinfer_cache": "/cache/flashinfer/.cache/flashinfer",
    "flashinfer_workspace": "/cache/flashinfer/.cache/flashinfer/0.6.18",
    "flashinfer_jit": "/cache/flashinfer/.cache/flashinfer/0.6.18/cached_ops",
    "flashinfer_generated": "/cache/flashinfer/.cache/flashinfer/0.6.18/generated",
    "cuda_configured": "/cache/cuda",
}
# Q38DEV observed these exact character devices; NVIDIA toolkit 1.19.1's
# controlDeviceNodeDiscoverer lists all four as global controls, not per-GPU nodes.
CONTROL_DEVICES = {
    "/dev/nvidia-modeset": (195, 254), "/dev/nvidiactl": (195, 255),
    "/dev/nvidia-uvm": (511, 0), "/dev/nvidia-uvm-tools": (511, 1),
}
CONTROL_NODES = frozenset(CONTROL_DEVICES)


class ProbeError(Exception):
    """Only fixed codes may leave this probe."""


# Diagnostic enums are deliberately finite; never derive them from child text.
FAILURE_CODES = frozenset((
    "q38b_cache_probe_failed", "cache_control_nodes_invalid", "cache_path_escape",
    "cache_probe_hash_mismatch", "cache_resolved_path_mismatch",
    "cache_resolver_source_mismatch", "cache_result_invalid", "cache_result_mismatch",
    "cache_result_types_invalid", "cache_write_failed", "empty_model_and_secret_tmpfs_required",
    "fixture_repository_required", "gpu_device_node_present", "gpu_visible", "home_changed",
    "installed_package_missing", "installed_version_mismatch", "isolation_changed",
    "launcher_source_hash_mismatch", "linux_pinned_image_required",
    "no_gpu_runtime_environment_required", "private_directory_required", "private_tmpfs_required",
    "readonly_container_root_required", "repository_package_substitution_refused",
    "source_revision_mismatch",
))
FAILURE_TYPES = (
    ProbeError, AssertionError, AttributeError, ImportError, ModuleNotFoundError,
    TypeError, ValueError, KeyError, IndexError, RuntimeError, OSError,
    FileNotFoundError, PermissionError, TimeoutError, json.JSONDecodeError,
    MemoryError, RecursionError,
)
FAILURE_CLASSES = frozenset(kind.__name__ for kind in FAILURE_TYPES) | {"OTHER"}


def failure_record(error):
    """Emit only an exact code and a bounded, structurally owned callsite.

    Do not format exceptions/tracebacks or inspect locals, causes or contexts.
    Class identity prevents an unapproved class borrowing an approved name.
    """
    code = "q38b_cache_probe_failed"
    if (type(error) is ProbeError and len(error.args) == 1
            and type(error.args[0]) is str and error.args[0] in FAILURE_CODES):
        code = error.args[0]
    kind = next((known.__name__ for known in FAILURE_TYPES if type(error) is known), "OTHER")
    origin = None
    frame = BaseException.__traceback__.__get__(error)
    for _ in range(64):
        if frame is None:
            break
        frame_code = frame.tb_frame.f_code
        if (any(frame_code is known for known in FAILURE_ORIGIN_CODES)
                and frame.tb_frame.f_globals is globals() and frame_code.co_filename == __file__
                and type(frame.tb_lineno) is int and 1 <= frame.tb_lineno <= 100000):
            origin = {"filename": "cache_probe.py", "line": frame.tb_lineno,
                      "exception_class": kind}
        frame = frame.tb_next
    else:
        origin = None
    return {"status": "FAIL", "code": code, "failure_origin": origin}


def validate_failure(value):
    """Copy only the exact diagnostic schema; never an acceptance record."""
    if (type(value) is not dict or set(value) != {"status", "code", "failure_origin"}
            or type(value["status"]) is not str or value["status"] != "FAIL"
            or type(value["code"]) is not str or value["code"] not in FAILURE_CODES):
        return None
    origin = value["failure_origin"]
    if origin is not None:
        if (type(origin) is not dict or set(origin) != {"filename", "line", "exception_class"}
                or type(origin["filename"]) is not str or origin["filename"] != "cache_probe.py"
                or type(origin["line"]) is not int or not 1 <= origin["line"] <= 100000
                or type(origin["exception_class"]) is not str
                or origin["exception_class"] not in FAILURE_CLASSES):
            return None
        origin = {"filename": "cache_probe.py", "line": origin["line"],
                  "exception_class": origin["exception_class"]}
    return {"status": "FAIL", "code": value["code"], "failure_origin": origin}


def failure_metadata(stdout):
    """Parse one small whole FAIL document, with no duplicate or nonfinite JSON."""
    if type(stdout) is not bytes or not 0 < len(stdout) <= 2048:
        return None

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError()
            result[key] = value
        return result

    def reject_constant(_value):
        raise ValueError()

    try:
        return validate_failure(json.loads(stdout.decode("utf-8"),
            object_pairs_hook=unique_object, parse_constant=reject_constant))
    except (ValueError, TypeError, RecursionError):
        return None


def require(value, code):
    if not value:
        raise ProbeError(code)


def check_mounts(mountinfo):
    mounts = {}
    for row in mountinfo.splitlines():
        fields, filesystem = row.split(" - ", 1)
        fields = fields.split()
        mounts.setdefault(fields[4], []).append((fields[5].split(","), filesystem.split()[0]))
    for target in ("/cache", "/models", "/run/secrets"):
        rows = mounts.get(target, [])
        require(len(rows) == 1 and rows[0][1] == "tmpfs" and "rw" in rows[0][0],
                "private_tmpfs_required")
    root = mounts.get("/", [])
    require(len(root) == 1 and "ro" in root[0][0], "readonly_container_root_required")


def check_device_names(names):
    relevant = {name for name in names if name.startswith(("/dev/nvidia", "/dev/dri/"))
                or name in ("/dev/dri", "/dev/kfd", "/dev/dxg")}
    require(relevant <= CONTROL_NODES, "gpu_device_node_present")
    return sorted(relevant)


def verify_isolation():
    require(sys.platform == "linux", "linux_pinned_image_required")
    # Q38ENV measured inherited inner "void"; host create/inspect still require "none".
    require(os.environ.get("NVIDIA_VISIBLE_DEVICES") in ("none", "void")
            and os.environ.get("NVIDIA_DRIVER_CAPABILITIES") == "compute,utility"
            and os.environ.get("CUDA_VISIBLE_DEVICES") == "",
            "no_gpu_runtime_environment_required")
    check_mounts(Path("/proc/self/mountinfo").read_text())
    for target in (Path("/cache"), Path("/models"), Path("/run/secrets")):
        meta = target.lstat()
        require(stat.S_ISDIR(meta.st_mode) and meta.st_uid == os.geteuid()
                and stat.S_IMODE(meta.st_mode) == 0o700, "private_directory_required")
        if target != Path("/cache"):
            require(not any(target.iterdir()), "empty_model_and_secret_tmpfs_required")
    # Enumerate names without following symlinks. Refuse accelerator directories
    # outright, so neither descendants nor dangling symlinks can evade the gate.
    controls = check_device_names([str(path) for path in Path("/dev").iterdir()])
    for name in controls:
        meta = Path(name).lstat()
        require(stat.S_ISCHR(meta.st_mode)
                and (os.major(meta.st_rdev), os.minor(meta.st_rdev)) == CONTROL_DEVICES[name],
                "cache_control_nodes_invalid")
    return controls


def verify_sources(repo):
    require(repo == Path("/fixture") and repo.resolve() == repo, "fixture_repository_required")
    provenance = json.loads((repo / "tests/lifecycle/sglang38_fixture/provenance.json").read_text())
    require(provenance["source_revision"] == SOURCE_REVISION, "source_revision_mismatch")
    fixture_root = repo / "tests/lifecycle/sglang38_fixture"
    require(provenance["fixture_sha256"].get("cache_probe.py")
            == hashlib.sha256((fixture_root / "cache_probe.py").read_bytes()).hexdigest(),
            "cache_probe_hash_mismatch")
    launcher_path = repo / "scripts/runtime/sglang38_file_auth.py"
    require(hashlib.sha256(launcher_path.read_bytes()).hexdigest() == provenance["launcher_sha256"],
            "launcher_source_hash_mismatch")
    for distribution, version in VERSIONS.items():
        require(importlib.metadata.version(distribution).split("+", 1)[0] == version,
                "installed_version_mismatch")
    for package, files in SOURCE_PINS.items():
        spec = importlib.util.find_spec(package)
        require(spec is not None and spec.origin is not None, "installed_package_missing")
        root = Path(spec.origin).resolve().parent
        require(not root.is_relative_to(repo), "repository_package_substitution_refused")
        for relative, digest in files.items():
            require(hashlib.sha256((root / relative).read_bytes()).hexdigest() == digest,
                    "cache_resolver_source_mismatch")
    spec = importlib.util.spec_from_file_location("q38b_cache_launcher", launcher_path)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    launcher.validate_environment()


def resolve_paths():
    """Call native installed resolvers only; never execute a kernel/compiler."""
    environ = importlib.import_module("sglang.srt.environ")
    jit_cache = importlib.import_module("sglang.kernels.jit.utils.compile.cache")
    hub = importlib.import_module("huggingface_hub.constants")
    transformers = importlib.import_module("transformers.utils.hub")
    triton_cache = importlib.import_module("triton.runtime.cache")
    inductor = importlib.import_module("torch._inductor.runtime.cache_dir_utils")
    cpp = importlib.import_module("torch.utils.cpp_extension")
    flashinfer = importlib.import_module("flashinfer.jit.env")
    return {
        "sglang": environ.envs.SGLANG_CACHE_DIR.get(),
        "sglang_deep_gemm": environ.envs.SGLANG_DG_CACHE_DIR.get(),
        "sglang_jit": str(jit_cache.build_key_dir(module_name="q38b_resolver_probe", build_key="0" * 16)),
        "huggingface_home": hub.HF_HOME, "huggingface_hub": hub.HF_HUB_CACHE,
        "huggingface_assets": hub.HF_ASSETS_CACHE, "transformers_modules": transformers.HF_MODULES_CACHE,
        "triton": triton_cache.FileCacheManager("q38b_resolver_probe").cache_dir,
        "torchinductor": inductor.cache_dir(), "torch_extensions": cpp.get_default_build_root(),
        "flashinfer_cache": str(flashinfer.FLASHINFER_CACHE_DIR),
        "flashinfer_workspace": str(flashinfer.FLASHINFER_WORKSPACE_DIR),
        "flashinfer_jit": str(flashinfer.FLASHINFER_JIT_DIR),
        "flashinfer_generated": str(flashinfer.FLASHINFER_GEN_SRC_DIR),
        # Driver JIT cache has no Python resolver. This is a configuration check;
        # triggering actual CUDA JIT is outside this no-GPU/no-kernel fixture.
        "cuda_configured": os.environ["CUDA_CACHE_PATH"],
    }


def check_paths(paths):
    require(paths == EXPECTED_PATHS, "cache_resolved_path_mismatch")
    for value in paths.values():
        path = Path(value)
        require(path.is_absolute() and path.is_relative_to("/cache")
                and path.resolve().is_relative_to("/cache"), "cache_path_escape")


def prove_writable(paths, cache_root=Path("/cache")):
    """Use directory FDs to refuse symlink traversal, even for the root user."""
    for value in sorted(set(paths.values())):
        relative = Path(value).relative_to(cache_root)
        require(relative.parts and ".." not in relative.parts, "cache_path_escape")
        fd = os.open(cache_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for name in relative.parts:
                try:
                    os.mkdir(name, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            filename = "q38b-resolver-" + os.urandom(16).hex()
            probe = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                            0o600, dir_fd=fd)
            try:
                payload = b"q38b-cache-write-proof\n"
                require(os.write(probe, payload) == len(payload), "cache_write_failed")
                os.fsync(probe)
            finally:
                os.close(probe)
                os.unlink(filename, dir_fd=fd)
        finally:
            os.close(fd)


def run(repo):
    controls = verify_isolation()
    home_before = os.environ.get("HOME")
    verify_sources(repo)
    # Loading driver libraries is distinct from GPU enumeration or execution.
    for library in ("libcuda.so.1", "libnvidia-ml.so.1"):
        ctypes.CDLL(library)
    torch = importlib.import_module("torch")
    require(torch.cuda.device_count() == 0 and not torch.cuda.is_available(), "gpu_visible")
    paths = resolve_paths()
    check_paths(paths)
    prove_writable(paths)
    require(os.environ.get("HOME") == home_before, "home_changed")
    require(verify_isolation() == controls, "isolation_changed")
    result = result_record(paths, controls)
    validate_result(result)
    return result


def result_record(paths, controls):
    return {
        "schema_version": 1, "kind": "q38b_cache_resolvers",
        "status": "PASS_ACTUAL_CACHE_RESOLVERS", "source_revision": SOURCE_REVISION,
        "image_identity_verification": "HOST_DOCKER_INSPECT_REQUIRED",
        "source_hashes": {package: dict(files) for package, files in SOURCE_PINS.items()},
        "resolved_paths": dict(paths),
        "writable_paths": "PASS", "home_unchanged": "PASS",
        "driver_library_loading": {"libcuda.so.1": "PASS", "libnvidia-ml.so.1": "PASS"},
        "gpu_device_nodes": [], "global_driver_control_nodes": controls,
        "native_torch_device_count": 0, "native_torch_cuda_available": False,
        "native_resolvers": "UNMODIFIED", "sglang_jit_target": "NATIVE_NO_DEVICE_SM00",
        "dependency_source_scope": {
            "huggingface_hub": "IMAGE_BOUND_NATIVE_API_PATH_CHECK",
            "triton": "IMAGE_BOUND_NATIVE_API_PATH_CHECK",
        },
        "cuda_driver_cache": "CONFIG_ONLY_NO_KERNEL",
        "model_loading": "NOT_TESTED", "gpu_execution": "NOT_TESTED",
        "compilation": "NOT_TESTED", "real_key_access": "NONE",
    }


def validate_result(result):
    """Pure fail-closed receipt validation, safe in host/lifecycle processes.

    This validates evidence shape and the reviewed claims only. The host must
    independently bind the receipt to its verified immutable container/image.
    """
    require(type(result) is dict, "cache_result_invalid")
    controls = result.get("global_driver_control_nodes")
    require(type(controls) is list and all(type(name) is str for name in controls)
            and controls == sorted(set(controls)) and set(controls) <= CONTROL_NODES,
            "cache_control_nodes_invalid")
    require(type(result.get("schema_version")) is int
            and type(result.get("native_torch_device_count")) is int
            and type(result.get("native_torch_cuda_available")) is bool,
            "cache_result_types_invalid")
    require(result == result_record(dict(EXPECTED_PATHS), controls), "cache_result_mismatch")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--actual-image", action="store_true", required=True)
    parser.add_argument("--repo", type=Path, required=True)
    options = parser.parse_args(argv)
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = run(options.repo)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps(failure_record(error), sort_keys=True))
        return 1


# Freeze exact original function identities, excluding the generic require frame.
FAILURE_ORIGIN_CODES = tuple(function.__code__ for function in (
    check_mounts, check_device_names, verify_isolation, verify_sources,
    resolve_paths, check_paths, prove_writable, run, result_record, validate_result, main,
))


if __name__ == "__main__":
    raise SystemExit(main())
