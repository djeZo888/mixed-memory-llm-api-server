#!/usr/bin/env python3
"""Validate only the H035 reviewed image and skill overlays; never select an image or policy."""
import hashlib
import os
from pathlib import Path
import stat
import sys


COMMON = {
    "tools/image/image-mcp.mjs": "6f4347bc3b3192fcd057883bc5425fd30c8a096bdf6ee6785d0673a4f6b4d2b7",
    "tools/image/image.mjs": "7cba531025eb598f1df36e9fed14c07b1ee59c0d091373ee03ad419443de7407",
}
ENGINE = {
    "skills/pdf/SKILL.md": "f1e77bf04846cde401c900f0a817a6fc14685df438c050f7f6aad75d6a670211",
    "skills/image/SKILL.md": "98db7d4da3cf4f27f3b4b3f2ec5b271ada2b8bf59cab89ae6fb2c23cd85e294e",
    "deploy/engine/configure-profile.mjs": "81a4ce401f01a67439c7db278c29f69498c7ec87ae27c415b9b231291e242896",
}


def protected(metadata):
    return metadata.st_uid in (0, os.getuid()) and not metadata.st_mode & 0o022


def validate(launcher, engine, profile, workspace):
    if engine not in ("engine", "codex"):
        raise ValueError("unknown launcher")
    root = Path(launcher).parent
    if not root.is_absolute() or root.resolve(strict=True) != root:
        raise ValueError("noncanonical source root")
    if any(character in str(root) for character in ":,") or any(ord(c) < 32 or ord(c) == 127 for c in str(root)):
        raise ValueError("unsupported source path")
    for writable in (Path(profile), Path(workspace)):
        if root == writable or root in writable.parents or writable in root.parents:
            raise ValueError("source overlaps writable task state")
    for directory in (root, *root.parents):
        metadata = directory.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or not protected(metadata):
            raise ValueError("unsafe source directory")
    pins = {**COMMON, **(ENGINE if engine == "engine" else {})}
    for relative, expected in pins.items():
        source = root / relative
        directory = source.parent
        while directory != root:
            metadata = directory.lstat()
            if not stat.S_ISDIR(metadata.st_mode) or not protected(metadata):
                raise ValueError("unsafe source directory")
            directory = directory.parent
        if source.resolve(strict=True) != source:
            raise ValueError("noncanonical source file")
        if not stat.S_ISREG(source.lstat().st_mode):
            raise ValueError("nonregular source file")
        descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or not protected(metadata):
                raise ValueError("unsafe source file")
            if hashlib.sha256(stream.read()).hexdigest() != expected:
                raise ValueError("source checksum mismatch")
            after = source.lstat()
            fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
            if any(getattr(after, field) != getattr(metadata, field) for field in fields):
                raise ValueError("source changed during validation")


if __name__ == "__main__":
    try:
        if len(sys.argv) != 5:
            raise ValueError("expected launcher, engine and task directories")
        validate(*sys.argv[1:])
    except (OSError, ValueError):
        # Do not disclose paths, task identity or environment values on ACP stdout.
        print("Reviewed image delivery overlay validation failed.", file=sys.stderr)
        sys.exit(1)
