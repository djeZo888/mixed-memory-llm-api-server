"""Offline checks of the configured client against reviewed source and npm cache.

This reads existing prefix state only. It never repairs a prefix, downloads a
package, trusts a caller-supplied pin, or executes installed code.
"""

import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tarfile
import time

from client_common import (ClientError, VERSION, endpoint, key_env_name, model_id,
                           native_package, reasoning_effort, runtime_dir, verify_install)


SOURCE = Path(__file__).resolve().parent
MAX_FILE = 512 * 1024 * 1024
MAX_TOTAL = 2 * 1024 * 1024 * 1024
MAX_MEMBERS = 60000
SECONDS = 30


def _require(condition):
    if not condition:
        raise ClientError("Client source, configuration, or cached package integrity check failed")


def _safe(path, root, directory=False):
    """Every descendant is owned, unwritable by others and has no link alias."""
    _require(path == root or root in path.parents)
    for relative in reversed(path.relative_to(root).parents):
        current = root / relative
        info = current.lstat()
        _require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                 and not info.st_mode & 0o022)
    info = path.lstat()
    _require(info.st_uid == os.getuid() and not info.st_mode & 0o022)
    if directory:
        _require(stat.S_ISDIR(info.st_mode))
    else:
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= MAX_FILE)
    return info


def _small_json(path, root):
    info = _safe(path, root)
    _require(info.st_size <= 1024 * 1024)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        _require(stat.S_ISREG(opened.st_mode) and opened.st_ino == info.st_ino
                 and opened.st_dev == info.st_dev and opened.st_size == info.st_size)
        data = stream.read(1024 * 1024 + 1)
    _require(len(data) <= 1024 * 1024)
    return json.loads(data)


def _digest_file(path, root, algorithm, budget):
    info = _safe(path, root)
    digest = hashlib.new(algorithm)
    def identity(value):
        return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
                value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        _require(identity(os.fstat(stream.fileno())) == identity(info))
        while chunk := stream.read(1024 * 1024):
            budget[0] += len(chunk)
            _require(budget[0] <= MAX_TOTAL and time.monotonic() <= budget[1])
            digest.update(chunk)
        _require(identity(os.fstat(stream.fileno())) == identity(info))
    _require(identity(path.lstat()) == identity(info))
    return digest.hexdigest()


def _settings(settings, lock):
    required = {"version", "base_url", "model", "auth", "context_tokens", "output_tokens", "lock_sha256"}
    _require(type(settings) is dict and set(settings) in (required, required | {"reasoning_effort"}))
    _require(settings["version"] == VERSION)
    _require(type(settings["base_url"]) is str and endpoint(settings["base_url"]) == settings["base_url"])
    _require(type(settings["model"]) is str and model_id(settings["model"]) == settings["model"])
    _require(type(settings["context_tokens"]) is int and type(settings["output_tokens"]) is int
             and 0 < settings["output_tokens"] < settings["context_tokens"])
    _require(settings["lock_sha256"] == hashlib.sha256(lock).hexdigest())
    if "reasoning_effort" in settings:
        reasoning_effort(settings["reasoning_effort"])
    auth = settings["auth"]
    _require(type(auth) is dict)
    if auth.get("kind") == "disabled":
        _require(set(auth) == {"kind"})
    else:
        _require(set(auth) == {"kind", "reference"} and type(auth["reference"]) is str)
        if auth["kind"] == "env":
            key_env_name(auth["reference"])
        else:
            _require(auth["kind"] == "file")
            path = Path(auth["reference"])
            _require(path.is_absolute() and ".." not in path.parts
                     and not any(ord(c) < 32 for c in str(path)))


def _package(package, entry, prefix, budget):
    integrity = entry["integrity"]
    _require(type(integrity) is str and integrity.startswith("sha512-"))
    expected = base64.b64decode(integrity[7:], validate=True)
    _require(len(expected) == 64)
    digest = expected.hex()
    archive = prefix / "npm/cache/_cacache/content-v2/sha512" / digest[:2] / digest[2:4] / digest[4:]
    _require(_digest_file(archive, prefix, "sha512", budget) == digest)
    files = set()
    directories = set()
    with tarfile.open(archive, mode="r|gz") as tar:
        for member in tar:
            budget[2] += 1
            _require(budget[2] <= MAX_MEMBERS and time.monotonic() <= budget[1])
            name = PurePosixPath(member.name)
            _require(not name.is_absolute() and ".." not in name.parts and name.parts[0] == "package")
            relative = Path(*name.parts[1:])
            if member.isdir():
                if relative != Path("."):
                    directories.add(relative)
                continue
            _require(member.isfile() and relative != Path(".") and relative not in files
                     and 0 <= member.size <= MAX_FILE)
            target = package / relative
            _require(_safe(target, prefix).st_size == member.size)
            original = tar.extractfile(member)
            _require(original is not None)
            digest = hashlib.sha256()
            with original:
                while chunk := original.read(1024 * 1024):
                    budget[0] += len(chunk)
                    _require(budget[0] <= MAX_TOTAL and time.monotonic() <= budget[1])
                    digest.update(chunk)
            _require(_digest_file(target, prefix, "sha256", budget) == digest.hexdigest())
            files.add(relative)
            directories.update(relative.parents[:-1])
    _require(files)
    expected_entries = {directory: set() for directory in {Path("."), *directories}}
    for relative in files | directories:
        expected_entries[relative.parent].add(relative.name)
    # Scan only archive-declared directories; reject the first unexpected entry
    # without recursively exploring or materializing an attacker-added tree.
    for relative, expected in expected_entries.items():
        actual = set()
        with os.scandir(package / relative) as entries:
            for entry in entries:
                _require(time.monotonic() <= budget[1] and entry.name in expected)
                child = relative / entry.name
                _safe(package / child, prefix, directory=child in directories)
                actual.add(entry.name)
        _require(actual == expected)
    return len(files)


def verify_client(prefix, *, timeout=None):
    """Return validated settings and numeric/hash evidence, with no credentials.

    A pruned npm cache is a refusal, not permission to skip installed-byte checks.
    Bounds cover all compressed, expanded, and installed content reads together.
    """
    try:
        timeout = SECONDS if timeout is None else timeout
        _require(type(timeout) in (int, float) and 0 < timeout <= SECONDS)
        prefix = Path(prefix)
        _require(prefix.is_absolute() and not prefix.is_symlink() and ".." not in prefix.parts)
        prefix = prefix.resolve()
        budget = [0, time.monotonic() + timeout, 0]
        lock = (SOURCE / "package-lock.json").read_bytes()
        settings = _small_json(prefix / "bootstrap.json", prefix)
        _settings(settings, lock)
        # Guard every JSON input before V0's existing config/version checks read it.
        for path in [prefix / "opencode.json", prefix / "models.json", *[
                runtime_dir(prefix) / "node_modules" / name / "package.json"
                for name in ("opencode-ai", "@opencode-ai/plugin", native_package())]]:
            _small_json(path, prefix)
        _require(verify_install(prefix) == settings)
        for target, origin in ((prefix / "bin/opencode-client", "launch.py"),
                               (prefix / "bin/client_common.py", "client_common.py"),
                               (runtime_dir(prefix) / "package.json", "package.json"),
                               (runtime_dir(prefix) / "package-lock.json", "package-lock.json")):
            _require(_digest_file(target, prefix, "sha256", budget)
                     == hashlib.sha256((SOURCE / origin).read_bytes()).hexdigest())
        packages = json.loads(lock)["packages"]
        modules = runtime_dir(prefix) / "node_modules"
        _safe(modules, prefix, directory=True)
        installed = set()
        for child in modules.iterdir():
            if child.name in (".bin", ".package-lock.json"):
                continue  # npm-generated metadata/links; never used as executable entry points here.
            _safe(child, prefix, directory=True)
            candidates = child.iterdir() if child.name.startswith("@") else [child]
            for item in candidates:
                _safe(item, prefix, directory=True)
                name = str(item.relative_to(runtime_dir(prefix)))
                _require(name in packages)
                installed.add(name)
        required = {name for name, item in packages.items() if name and not item.get("optional", False)}
        required.add("node_modules/" + native_package())
        _require(required <= installed)
        count = sum(_package(runtime_dir(prefix) / name, packages[name], prefix, budget)
                    for name in sorted(installed))
        native = modules / native_package() / "bin/opencode"
        return settings, {"status": "pass", "method": "reviewed-source-and-offline-npm-sri",
                          "lock_sha256": hashlib.sha256(lock).hexdigest(),
                          "packages_verified": len(installed), "files_verified": count,
                          "native_sha256": _digest_file(native, prefix, "sha256", budget)}
    except (OSError, ValueError, KeyError, TypeError, IndexError, tarfile.TarError):
        raise ClientError("Client source, configuration, or cached package integrity check failed") from None
