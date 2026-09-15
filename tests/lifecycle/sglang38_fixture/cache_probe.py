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
CONTROL_NODES = frozenset({"/dev/nvidiactl", "/dev/nvidia-uvm", "/dev/nvidia-uvm-tools"})


class ProbeError(Exception):
    """Only fixed codes may leave this probe."""


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
                or name in ("/dev/kfd", "/dev/dxg")}
    require(relevant <= CONTROL_NODES, "gpu_device_node_present")
    return sorted(relevant)


def verify_isolation():
    require(sys.platform == "linux", "linux_pinned_image_required")
    require(all(os.environ.get(name) == value for name, value in RUNTIME_ENVIRONMENT.items()),
            "no_gpu_runtime_environment_required")
    check_mounts(Path("/proc/self/mountinfo").read_text())
    for target in (Path("/cache"), Path("/models"), Path("/run/secrets")):
        meta = target.lstat()
        require(stat.S_ISDIR(meta.st_mode) and meta.st_uid == os.geteuid()
                and stat.S_IMODE(meta.st_mode) == 0o700, "private_directory_required")
        if target != Path("/cache"):
            require(not any(target.iterdir()), "empty_model_and_secret_tmpfs_required")
    names = [str(path) for path in Path("/dev").glob("nvidia*")]
    names += [str(path) for path in Path("/dev/dri").glob("*")]
    names += [str(path) for path in (Path("/dev/kfd"), Path("/dev/dxg")) if path.exists()]
    return check_device_names(names)


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
    except Exception:
        print(json.dumps({"status": "FAIL", "code": "q38b_cache_probe_failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
