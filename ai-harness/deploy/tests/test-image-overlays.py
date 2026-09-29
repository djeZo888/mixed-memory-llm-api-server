#!/usr/bin/env python3
"""Immutable image delivery contract; isolated source copies and fake Podman only."""
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import unittest


spec = importlib.util.spec_from_file_location(
    "image_overlay_launcher_fixture", Path(__file__).with_name("test-run-engine.py"))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
SOURCE = base.LAUNCHER.parent.parent
ENGINE_PATCHSET = base.PATCHSET


class OverlayChecks:
    """Only the new seam is exercised; unrelated inherited tests are not rerun."""
    runtime = "engine"
    invoke = base.LauncherContract.invoke
    calls = base.LauncherContract.calls

    def setUp(self):
        base.LAUNCHER = SOURCE / "deploy" / f"run-{self.runtime}.sh"
        if self.runtime == "codex":
            base.REVISION = "064c6b8c737f5b41d171fdda80bd9ef10ad06eb3"
            base.IMAGE_ID = "sha256:d8841743002e16de1f9269a850a2f06a73055688befec4c309778ca8a4c11aad"
            base.PATCHSET = "dd0ff12a651db4cc8521cddb8e5094c5a197ca87cef6b7ec797343da67d9f1ec"
        else:
            base.REVISION = "ae65651df5f97ae1085ab4e19964f4b78c769a4e"
            base.IMAGE_ID = "sha256:" + "a" * 64
            base.PATCHSET = ENGINE_PATCHSET
        base.LauncherContract.setUp(self)
        self.source = self.root / "reviewed source with spaces" / "ai-harness"
        for relative in ("deploy", "tools/image", "skills/image", "skills/pdf"):
            shutil.copytree(SOURCE / relative, self.source / relative)
        base.LAUNCHER = self.source / "deploy" / f"run-{self.runtime}.sh"
        self.artifacts = [
            ("tools/image/image-mcp.mjs", "/opt/ai-harness/tools/image/image-mcp.mjs"),
            ("tools/image/image.mjs", "/opt/ai-harness/tools/image/image.mjs"),
        ]
        if self.runtime == "engine":
            self.artifacts += [
                ("skills/image/SKILL.md", "/opt/ai-harness/skills/image/SKILL.md"),
                ("skills/pdf/SKILL.md", "/opt/ai-harness/skills/pdf/SKILL.md"),
                ("deploy/engine/configure-profile.mjs", "/opt/ai-harness/engine/configure-profile.mjs"),
            ]

    def assert_refused_before_runtime(self, args=None):
        result = self.invoke(args=args)
        self.assertEqual(result.returncode, 64, result.stderr)
        self.assertIn("overlay", result.stderr.lower())
        self.assertFalse(self.calls(), "invalid source must fail before even Podman info")
        self.assertFalse((self.profile / "state").exists())
        self.assertFalse((self.profile / "codex-home").exists())

    def test_reviewed_sources_with_spaces_are_exact_readonly_binds(self):
        result = self.invoke(text='{"id":1}\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '{"id":1}\n')
        run = next(call["argv"] for call in self.calls() if "run" in call["argv"])
        mounts = [run[index + 1] for index, item in enumerate(run) if item == "--volume"]
        expected = [f"{self.profile}:{self.profile}:rw,rprivate",
                    f"{self.workspace}:{self.workspace}:rw,rprivate"]
        expected += [f"{self.source / relative}:{target}:ro,rprivate"
                     for relative, target in self.artifacts]
        if self.runtime == "codex":
            expected += [
                f"{self.source}/deploy/codex/config.toml:{self.profile}/codex-home/config.toml:ro,rprivate",
                f"{self.source}/deploy/codex/models.json:/opt/sova/codex/models.json:ro,rprivate",
                f"{self.source}/deploy/codex/skills/sova-local-tools:{self.profile}/codex-home/skills/sova-local-tools:ro,rprivate",
            ]
        self.assertEqual(mounts, expected)
        self.assertEqual(run[-1], base.IMAGE_ID)
        for flag in ("--read-only", "--pull=never", "no-new-privileges", "--cap-drop"):
            self.assertIn(flag, run)

    def test_each_changed_hash_fails_before_runtime_and_environment_cannot_override(self):
        for relative, _ in self.artifacts:
            with self.subTest(artifact=relative):
                source = self.source / relative
                original = source.read_bytes()
                changed = original + b"\n// unreviewed fixture change\n"
                source.write_bytes(changed)
                self.env.update(
                    AI_HARNESS_IMAGE_OVERLAY_SHA256=hashlib.sha256(changed).hexdigest(),
                    AI_HARNESS_IMAGE_MCP_SHA256=hashlib.sha256(changed).hexdigest(),
                    AI_HARNESS_IMAGE_OVERLAY_SKIP_VERIFY="1",
                )
                try:
                    self.assert_refused_before_runtime()
                finally:
                    source.write_bytes(original)

    def test_each_missing_source_fails_before_runtime(self):
        for relative, _ in self.artifacts:
            with self.subTest(artifact=relative):
                source = self.source / relative
                original = source.read_bytes()
                source.unlink()
                try:
                    self.assert_refused_before_runtime()
                finally:
                    source.write_bytes(original)

    def test_each_symlink_or_hardlink_source_is_refused(self):
        for relative, _ in self.artifacts:
            for link_kind in ("symlink", "hardlink"):
                with self.subTest(artifact=relative, link=link_kind):
                    source = self.source / relative
                    original = source.read_bytes()
                    external = self.root / "external-reviewed-bytes"
                    external.write_bytes(original)
                    source.unlink()
                    if link_kind == "symlink":
                        source.symlink_to(external)
                    else:
                        os.link(external, source)
                    try:
                        self.assert_refused_before_runtime()
                    finally:
                        source.unlink()
                        source.write_bytes(original)
                        external.unlink()

    def test_each_group_or_world_writable_source_is_refused(self):
        for relative, _ in self.artifacts:
            source = self.source / relative
            original_mode = source.stat().st_mode & 0o777
            for unsafe_bit in (0o020, 0o002):
                with self.subTest(artifact=relative, unsafe_bit=unsafe_bit):
                    source.chmod(original_mode | unsafe_bit)
                    try:
                        self.assert_refused_before_runtime()
                    finally:
                        source.chmod(original_mode)

    def test_symlinked_source_ancestor_is_refused(self):
        directories = {str(Path(relative).parent) for relative, _ in self.artifacts}
        for relative in sorted(directories):
            with self.subTest(directory=relative):
                parent = self.source / relative
                external = self.root / "external-reviewed-tree"
                parent.rename(external)
                parent.symlink_to(external, target_is_directory=True)
                try:
                    self.assert_refused_before_runtime()
                finally:
                    parent.unlink()
                    external.rename(parent)

    def test_writable_source_ancestors_including_root_are_refused(self):
        directories = {self.source, self.source.parent}
        for relative, _ in self.artifacts:
            parent = (self.source / relative).parent
            while parent != self.source:
                directories.add(parent)
                parent = parent.parent
        for directory in sorted(directories):
            with self.subTest(directory=directory):
                original_mode = directory.stat().st_mode & 0o777
                directory.chmod(original_mode | 0o020)
                try:
                    self.assert_refused_before_runtime()
                finally:
                    directory.chmod(original_mode)

    def test_source_tree_cannot_overlap_either_writable_mount(self):
        for role in ("profile", "workspace"):
            for path in (self.source, self.source / "tools", self.source.parent):
                with self.subTest(role=role, path=path):
                    profile = path if role == "profile" else self.profile
                    workspace = path if role == "workspace" else self.workspace
                    self.assert_refused_before_runtime(
                        ["--profile-dir", str(profile), "--workspace", str(workspace)])


@unittest.skipIf(os.geteuid() == 0, "launcher deliberately refuses root")
class EngineOverlayContract(OverlayChecks, unittest.TestCase):
    runtime = "engine"


@unittest.skipIf(os.geteuid() == 0, "launcher deliberately refuses root")
class CodexOverlayContract(OverlayChecks, unittest.TestCase):
    runtime = "codex"


if __name__ == "__main__":
    unittest.main(verbosity=2)
