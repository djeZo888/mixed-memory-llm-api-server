#!/usr/bin/env python3
"""Deferred actual-image cache resolver/filesystem proof; no GPU/model proof.

Run only after root review in the exact pinned image, read-only root and
/fixture, no network/ports/GPU/key/models, empty private tmpfs /cache and /tmp.
Imports are real installed modules with version/source assertions, never AST
extractions or stubs. FlashInfer imports may create a workspace log in /cache.
This helper does not inject environment defaults or change HOME.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import secrets
import stat
import sys


IMAGE_ID = "sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3"
CACHE_ROOT = Path("/cache")
PROBE_BYTES = b"F1C bounded cache filesystem probe\n"


class CacheFailure(Exception):
    """Only fixed diagnostic codes are emitted."""


def require(condition, code):
    if not condition:
        raise CacheFailure(code)


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise CacheFailure("arguments_invalid")


def parse_options(argv):
    parser = Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--actual-image", action="store_true", required=True)
    parser.add_argument("--repo", type=Path, required=True)
    return parser.parse_args(argv)


def checked_path(value, *, root=CACHE_ROOT):
    """Reject lexical traversal, sibling prefixes and existing symlink escapes."""
    raw = os.fspath(value)
    path = Path(raw)
    require(path.is_absolute() and str(path) == raw and ".." not in path.parts
            and not any(ord(char) < 32 for char in raw), "cache_path_invalid")
    require(path.is_relative_to(root) and path.resolve() == path,
            "cache_path_escape")
    return path


def verify_isolation(repo):
    require(sys.platform == "linux" and sys.dont_write_bytecode,
            "linux_no_bytecode_required")
    require(repo == Path("/fixture") and repo.resolve() == repo,
            "repository_path_invalid")
    rows = [row.split() for row in Path("/proc/self/mountinfo").read_text().splitlines()]
    for target in ("/", "/fixture", "/cache", "/tmp"):
        matches = [row for row in rows if row[4] == target]
        require(len(matches) == 1, "isolated_mount_required")
        row = matches[0]
        options = set(row[5].split(","))
        if target in ("/", "/fixture"):
            require("ro" in options, "readonly_mount_required")
        else:
            require(row[row.index("-") + 1] == "tmpfs"
                    and {"rw", "nosuid", "nodev"} <= options,
                    "private_tmpfs_required")
            path = Path(target)
            meta = path.lstat()
            require(stat.S_ISDIR(meta.st_mode) and meta.st_uid == os.geteuid()
                    and not meta.st_mode & 0o077 and not any(path.iterdir()),
                    "empty_private_directory_required")
    require(not any(row[4].startswith(("/cache/", "/tmp/", "/models", "/run/secrets"))
                    for row in rows), "unexpected_fixture_mount")
    require(not list(Path("/dev").glob("nvidia*")), "gpu_device_refused")
    require(os.environ.get("TMPDIR") == "/tmp", "temporary_path_invalid")


def load_launcher(repo):
    provenance = json.loads((repo / "reports/f1s-contract-evidence/launcher-provenance.json").read_text())
    require(provenance["path"] == "scripts/lifecycle/sglang_file_auth.py"
            and provenance["image_id"] == IMAGE_ID, "launcher_provenance_invalid")
    path = repo / provenance["path"]
    require(hashlib.sha256(path.read_bytes()).hexdigest() == provenance["sha256"],
            "launcher_hash_mismatch")
    spec = importlib.util.spec_from_file_location("f1c_reviewed_launcher", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Real validator: never fill missing values in the actual fixture.
    module.validate_environment()
    runtime = json.loads((repo / "configs/runtimes/sglang-qwen-next-0.5.14.json").read_text())
    require(runtime["image_id"] == IMAGE_ID and all(
        os.environ.get(name) == value for name, value in runtime["environment"].items()),
        "runtime_environment_mismatch")
    for value in module.FIXED_CACHE_ENVIRONMENT.values():
        checked_path(value)
    return module


def verify_installed_sources(repo):
    evidence = json.loads((repo / "reports/f1c-cache-source-evidence.json").read_text())
    require(evidence["image_id"] == IMAGE_ID, "source_image_mismatch")
    for package, version in evidence["packages"].items():
        require(importlib.metadata.version(package) == version, "installed_version_mismatch")
    paths = {}
    for source in evidence["resolver_sources"]:
        module = source["module"]
        package, _, relative = source["relative_path"].partition("/")
        # Top-level find_spec avoids executing package parents before preflight.
        spec = importlib.util.find_spec(package)
        require(spec is not None and spec.origin is not None, "installed_module_missing")
        root = Path(spec.origin).resolve().parent
        path = root / relative
        require(path.resolve() == path and not path.is_relative_to(repo)
                and not path.is_relative_to(CACHE_ROOT)
                and not path.is_relative_to(Path("/tmp")), "installed_module_path_invalid")
        raw = path.read_bytes()
        require(len(raw) == source["bytes"]
                and hashlib.sha256(raw).hexdigest() == source["sha256"],
                "installed_source_mismatch")
        paths[module] = path
    return paths


def resolved_directories(launcher, sources):
    modules = {}
    for name in sources:
        module = importlib.import_module(name)
        require(module.__name__ == name and Path(module.__file__).resolve() == sources[name],
                "imported_module_mismatch")
        modules[name] = module
    envs = modules["sglang.srt.environ"].envs
    flash = modules["flashinfer.jit.env"]
    cpp = modules["torch.utils.cpp_extension"]
    require(flash.flashinfer_version == "0.6.12"
            and sys.modules["torch"].__version__ == "2.11.0+cu130"
            and sys.modules["sglang"].__version__ == "0.5.14",
            "imported_version_mismatch")
    paths = dict(launcher.FIXED_CACHE_ENVIRONMENT)
    for name in ("SGLANG_DG_CACHE_DIR", "SGLANG_CACHE_DIR"):
        paths[name] = getattr(envs, name).get()
        require(paths[name] == launcher.FIXED_CACHE_ENVIRONMENT[name], "sglang_resolver_mismatch")
    require(str(flash.FLASHINFER_BASE_DIR) == paths["FLASHINFER_WORKSPACE_BASE"],
            "flashinfer_resolver_mismatch")
    for field in ("FLASHINFER_CACHE_DIR", "FLASHINFER_WORKSPACE_DIR",
                  "FLASHINFER_JIT_DIR", "FLASHINFER_GEN_SRC_DIR"):
        paths[field] = str(getattr(flash, field))
    # cpp_extension creates this directory itself, so validate before calling.
    expected_extension = checked_path(paths["TORCH_EXTENSIONS_DIR"] + "/f1c_cache_probe")
    paths["TORCH_EXTENSION_BUILD"] = cpp._get_build_directory("f1c_cache_probe", False)
    require(Path(paths["TORCH_EXTENSION_BUILD"]) == expected_extension,
            "torch_resolver_mismatch")
    # CUDA_CACHE_PATH is documented driver input only; no CUDA call is made.
    # Existing HF/XDG/Triton/Inductor roots are checked configured paths here.
    return {name: checked_path(value) for name, value in paths.items()}


def probe_directory(path, *, root=CACHE_ROOT):
    """Write only one owned bounded file using no-follow directory descriptors."""
    path = checked_path(path, root=root)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory = os.open(root, flags)
    fd = None
    created = None
    filename = ".f1c-cache-probe-" + secrets.token_hex(8)
    try:
        for part in path.relative_to(root).parts:
            try:
                os.mkdir(part, 0o700, dir_fd=directory)
            except FileExistsError:
                pass
            child = os.open(part, flags, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(filename, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        meta = os.fstat(fd)
        created = (meta.st_dev, meta.st_ino)
        require(stat.S_ISREG(meta.st_mode), "probe_file_invalid")
        require(os.write(fd, PROBE_BYTES) == len(PROBE_BYTES), "probe_write_incomplete")
        os.fsync(fd)
        os.lseek(fd, 0, os.SEEK_SET)
        require(os.read(fd, len(PROBE_BYTES) + 1) == PROBE_BYTES, "probe_read_mismatch")
    finally:
        if fd is not None:
            os.close(fd)
        try:
            if created is not None:
                now = os.stat(filename, dir_fd=directory, follow_symlinks=False)
                require((now.st_dev, now.st_ino) == created, "probe_file_replaced")
                os.unlink(filename, dir_fd=directory)
        finally:
            os.close(directory)


def run_actual(repo):
    original_home = os.environ.get("HOME")
    verify_isolation(repo)
    launcher = load_launcher(repo)
    sources = verify_installed_sources(repo)
    paths = resolved_directories(launcher, sources)
    for path in sorted(set(paths.values())):
        probe_directory(path)
    require(os.environ.get("HOME") == original_home, "home_changed")
    return {"status": "PASS_RESOLVERS_AND_FILESYSTEM_ONLY", "expected_image_id": IMAGE_ID,
            "resolved_directories": {name: str(path) for name, path in paths.items()},
            "installed_source_hashes": {name: hashlib.sha256(path.read_bytes()).hexdigest()
                                        for name, path in sources.items()},
            "home_unchanged": True, "gpu_driver_jit_cache": "NOT_TESTED",
            "model_cache_behavior": "NOT_TESTED"}


def main(argv=None):
    try:
        options = parse_options(argv)
        # Native imports can log; never dump their exceptions/environment.
        with open(os.devnull, "w") as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
            result = run_actual(options.repo)
    except Exception:
        print(json.dumps({"status": "FAIL", "code": "actual_cache_fixture_failed"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
