#!/usr/bin/env python3
"""Validate only the H034 reviewed file overlays; never select an image or policy."""
import hashlib
import os
from pathlib import Path
import stat
import sys


COMMON = {
    "tools/image/image-mcp.mjs": "d23616513961b053d7da4e61b9f5ca29025b48cce6290d52e871a8e82fb51a66",
    "tools/image/image.mjs": "fb15f15951448169a6d3e1ca97805ce1075aa668b495e6e032069437ef8f6f6b",
}
ENGINE = {
    "skills/image/SKILL.md": "824aba75ad5e27b2388c3c2264d8dd5fd8fd39cd86e4b1f6134b6e3a4a4c1dbc",
    "deploy/engine/configure-profile.mjs": "e4042d2a544d1422e840f084e7c77caa84b67668da428d462e84f563358fdcfc",
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
