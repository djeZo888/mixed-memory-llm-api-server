#!/usr/bin/env python3
"""Validate reviewed source overlays and protected frontier selection; never select an image."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys


COMMON = {
    "tools/image/image-mcp.mjs": "afd30444aa3285e324f72bc729c8769e946ab1ccf476fb05529b521a5cd26c1d",
    "tools/image/image.mjs": "bd2c2a4b734bc1a00831517119b90c78427edc88f32dd5ae265082c3d8c4a2c4",
}
ENGINE = {
    "skills/pdf/SKILL.md": "f1e77bf04846cde401c900f0a817a6fc14685df438c050f7f6aad75d6a670211",
    "skills/image/SKILL.md": "9e503c891570d2c91975348f0954015c5b27fe658dd4926c88919a1c6a43c96d",
    "deploy/engine/configure-profile.mjs": "9c3b8a309a1cbc65529b5180a9d268424907cace0de2f363dfd4050057e498b5",
    # Mutable host selection is bound to the protected native receipt below.
    "config/active-frontier.json": None,
}


def protected(metadata):
    return metadata.st_uid in (0, os.getuid()) and not metadata.st_mode & 0o022


def native_receipt():
    source = Path("/etc/sova-qualification/mimo.json")
    for directory in source.parents:
        metadata = directory.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o022:
            raise ValueError("unsafe native receipt ancestry")
    if source.resolve(strict=True) != source:
        raise ValueError("noncanonical native receipt")
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or before.st_nlink != 1 or before.st_mode & 0o022 or before.st_size > 65536:
            raise ValueError("unsafe native receipt")
        raw = stream.read(65537)
        after = source.lstat()
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(raw) > 65536 or any(getattr(before, key) != getattr(after, key) for key in fields):
            raise ValueError("native receipt changed")
        return raw


def validate_frontier_selection(raw):
    selection = json.loads(raw)
    fields = {"model", "mimoEnabled", "mimoQualificationSha256", "mimoContextWindow", "mimoMaxOutputTokens"}
    if not isinstance(selection, dict) or set(selection) != fields:
        raise ValueError("invalid frontier selection")
    if selection == dict(model="glm-5.3-flash", mimoEnabled=False, mimoQualificationSha256=None,
                         mimoContextWindow=None, mimoMaxOutputTokens=None):
        return
    context, output = selection["mimoContextWindow"], selection["mimoMaxOutputTokens"]
    if selection["model"] != "mimo-v2.6-pro-rl" or selection["mimoEnabled"] is not True or type(context) is not int or not 2 <= context <= 1048576 or type(output) is not int or not 1 <= output <= 65536 or output >= context:
        raise ValueError("invalid MiMo selection")
    receipt = native_receipt()
    if hashlib.sha256(receipt).hexdigest() != selection["mimoQualificationSha256"]:
        raise ValueError("native receipt checksum mismatch")
    record = json.loads(receipt)
    qualification = record.get("qualification") if isinstance(record, dict) else None
    identity = qualification.get("identity") if isinstance(qualification, dict) else None
    if not isinstance(identity, dict):
        raise ValueError("invalid native receipt")
    if qualification.get("qualified") is not True or identity.get("model") != selection["model"] or identity.get("actualSlotContext") != context or type(identity.get("maxOutputTokens")) is not int or min(65536, identity["maxOutputTokens"]) != output:
        raise ValueError("native receipt capacity mismatch")


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
            raw = stream.read(65537) if expected is None else stream.read()
            if expected is None:
                if len(raw) > 65536:
                    raise ValueError("oversized frontier selection")
                validate_frontier_selection(raw)
            elif hashlib.sha256(raw).hexdigest() != expected:
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
