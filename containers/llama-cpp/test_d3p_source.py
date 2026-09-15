#!/usr/bin/env python3
"""Focused fail-closed recipe tests; no network, Docker, models or host changes.

Run: PYTHONDONTWRITEBYTECODE=1 python3 containers/llama-cpp/test_d3p_source.py
Fixture tests patch module constants in-process; production CLI has no override.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

RECIPE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("d3p_source", RECIPE / "prepare-d3p-source.py")
source_helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source_helper)


class SourceTests(unittest.TestCase):
    def git(self, *args):
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update({"GIT_AUTHOR_NAME": "Fixture", "GIT_COMMITTER_NAME": "Fixture",
                    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
                    "GIT_COMMITTER_EMAIL": "fixture@example.invalid"})
        return subprocess.check_output(["git", "-C", str(self.source), *args],
                                       env=env, stderr=subprocess.PIPE)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="d3p-test-")
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.source = root / "source"
        self.recipe = root / "recipe"
        self.source.mkdir()
        self.recipe.mkdir()
        self.git("init", "-q")
        (self.source / ".gitignore").write_text("ignored-output\n")
        (self.source / "sample.txt").write_text("original\n")
        self.git("add", ".")
        self.git("commit", "-qm", "ancestor")
        self.ancestor = self.git("rev-parse", "HEAD").decode().strip()
        (self.source / "second.txt").write_text("base\n")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD").decode().strip()
        self.tree = self.git("rev-parse", "HEAD^{tree}").decode().strip()
        (self.source / "sample.txt").write_text("patched\n")
        (self.source / "guard.h").write_text("native guard fixture\n")
        self.git("add", ".")
        self.derived = self.git("write-tree").decode().strip()
        patch = self.git("diff", "--cached", "--binary", "--full-index", "HEAD")
        (self.recipe / source_helper.PATCH_FILE).write_bytes(patch)
        self.git("reset", "--hard", "-q", self.base)
        self.manifest = {
            "schema_version": 1,
            "upstream_repository": source_helper.UPSTREAM_REPOSITORY,
            "upstream_commit": self.base,
            "upstream_tree": self.tree,
            "jinja_fix_ancestor": self.ancestor,
            "patch_file": source_helper.PATCH_FILE,
            "patch_sha256": hashlib.sha256(patch).hexdigest(),
            "derived_tree": self.derived,
        }
        self.save_manifest()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(source_helper, "UPSTREAM_COMMIT", self.base).start()
        mock.patch.object(source_helper, "JINJA_FIX_ANCESTOR", self.ancestor).start()

    def save_manifest(self):
        (self.recipe / source_helper.MANIFEST_FILE).write_text(json.dumps(self.manifest))

    def prepare(self, check_only=False):
        return source_helper.prepare(self.source, self.recipe, check_only)

    def snapshot(self):
        # Include every Git index/object and worktree file's bytes and mode.
        return {str(path.relative_to(self.source)):
                (path.lstat().st_mode,
                 os.readlink(path) if path.is_symlink() else
                 path.read_bytes() if path.is_file() else None)
                for path in self.source.rglob("*")}

    def copy_checkout(self):
        original = self.source
        self.source = original.parent / "copied-source"
        shutil.copytree(original, self.source, copy_function=shutil.copy2)
        self.assertEqual((original / ".git/index").read_bytes(),
                         (self.source / ".git/index").read_bytes())
        self.assertNotEqual((original / "sample.txt").stat().st_ino,
                            (self.source / "sample.txt").stat().st_ino)

    def test_check_only_preserves_every_checkout_and_git_file(self):
        before = self.snapshot()
        result = self.prepare(check_only=True)
        self.assertEqual(result["derived_tree"], self.derived)
        self.assertEqual(result["source_state"], "verified-upstream")
        self.assertEqual(self.snapshot(), before)

    def assert_original_index_failure_then_corrected_apply(self):
        before = self.snapshot()
        self.assertEqual(self.prepare(check_only=True)["source_state"], "verified-upstream")
        self.assertEqual(self.snapshot(), before)
        # This is the original helper's exact first APPLY subprocess. It fails
        # on the real stale index; no Git result or failure is mocked here.
        with self.assertRaisesRegex(RuntimeError, "sample.txt: does not match index"):
            source_helper.git(self.source, "apply", "--check", "--index",
                              "--whitespace=error-all",
                              str(self.recipe / source_helper.PATCH_FILE))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.prepare()["source_state"], "verified-patched")
        self.assertEqual(self.git("write-tree").decode().strip(), self.derived)
        self.assertEqual(self.git("rev-parse", "HEAD").decode().strip(), self.base)

    def test_copied_checkout_reproduces_original_index_failure_then_applies(self):
        self.copy_checkout()
        self.assert_original_index_failure_then_corrected_apply()

    def test_stat_invalidated_checkout_reproduces_original_index_failure_then_applies(self):
        path = self.source / "sample.txt"
        previous = path.stat()
        # Deliberately invalidate only cached stat data, retaining bytes/mode.
        os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns - 2_000_000_000))
        self.assert_original_index_failure_then_corrected_apply()

    def assert_refused_before_refresh(self, pattern):
        before = self.snapshot()
        with mock.patch.object(source_helper, "git", wraps=source_helper.git) as calls:
            with self.assertRaisesRegex(RuntimeError, pattern):
                self.prepare()
        self.assertFalse(any(call.args[1:3] == ("update-index", "--refresh")
                             for call in calls.call_args_list))
        self.assertEqual(self.snapshot(), before)

    def test_copied_same_size_raw_tampering_refused_before_refresh(self):
        self.copy_checkout()
        # Make status trust size/mtime, then preserve both while changing bytes.
        # The helper's independent raw-blob check must still reject this source.
        self.git("config", "core.trustctime", "false")
        self.git("config", "core.checkStat", "minimal")
        path = self.source / "sample.txt"
        timestamp = 1_700_000_000_000_000_000
        os.utime(path, ns=(timestamp, timestamp))
        self.git("update-index", "--refresh")
        previous = path.stat()
        path.write_bytes(b"tampered\n")
        os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
        self.assertEqual(path.stat().st_size, previous.st_size)
        self.assertEqual(source_helper.git(self.source, "status", "--porcelain=v1"), b"")
        self.assert_refused_before_refresh("tracked content differs from pinned Git blob")

    def test_copied_mode_tampering_refused_before_refresh(self):
        self.copy_checkout()
        self.git("config", "core.filemode", "false")
        (self.source / "sample.txt").chmod(0o755)
        self.assert_refused_before_refresh("tracked executable mode changed")

    def test_copied_index_tampering_refused_before_refresh(self):
        self.copy_checkout()
        other_blob = self.git("rev-parse", "HEAD:second.txt").decode().strip()
        self.git("update-index", "--cacheinfo", "100644", other_blob, "sample.txt")
        self.assert_refused_before_refresh("dirty")

    def test_copied_same_size_patch_tampering_refused_before_refresh(self):
        self.copy_checkout()
        patch = self.recipe / source_helper.PATCH_FILE
        previous = patch.read_bytes()
        changed = previous.replace(b"+patched\n", b"+altered\n")
        self.assertNotEqual(changed, previous)
        self.assertEqual(len(changed), len(previous))
        patch.write_bytes(changed)
        self.assert_refused_before_refresh("patch SHA256 mismatch")

    def test_exact_apply_records_tree_without_fabricating_commit(self):
        result = self.prepare()
        self.assertEqual(self.git("write-tree").decode().strip(), self.derived)
        self.assertEqual(self.git("rev-parse", "HEAD").decode().strip(), self.base)
        self.assertEqual((self.source / "sample.txt").read_text(), "patched\n")
        self.assertEqual(result["source_state"], "verified-patched")
        self.assertIsNone(result["derived_commit"])
        with self.assertRaisesRegex(RuntimeError, "dirty"):
            self.prepare()

    def test_fixed_manifest_identities_cannot_retarget(self):
        for field, value in (("upstream_repository", "https://example.invalid/other"),
                             ("upstream_commit", "0" * 40),
                             ("jinja_fix_ancestor", "1" * 40),
                             ("patch_file", "../other.patch")):
            original = self.manifest[field]
            self.manifest[field] = value
            self.save_manifest()
            with self.subTest(field=field), self.assertRaisesRegex(RuntimeError, "unapproved"):
                self.prepare()
            self.manifest[field] = original

    def test_manifest_schema_and_digest_shapes(self):
        for field, value in (("schema_version", True), ("schema_version", 2),
                             ("patch_sha256", "bad"), ("derived_tree", "A" * 40),
                             ("upstream_tree", None)):
            original = self.manifest[field]
            self.manifest[field] = value
            self.save_manifest()
            with self.subTest(field=field, value=value), self.assertRaises(RuntimeError):
                self.prepare()
            self.manifest[field] = original
        self.manifest["extra"] = "ignored?"
        self.save_manifest()
        with self.assertRaisesRegex(RuntimeError, "fields"):
            self.prepare()

    def test_patch_digest_tampering(self):
        with (self.recipe / source_helper.PATCH_FILE).open("ab") as stream:
            stream.write(b"\n")
        with self.assertRaisesRegex(RuntimeError, "SHA256"):
            self.prepare()

    def test_wrong_base_commit(self):
        self.git("checkout", "--detach", self.ancestor)
        with self.assertRaisesRegex(RuntimeError, "commit mismatch"):
            self.prepare()

    def test_wrong_upstream_tree(self):
        self.manifest["upstream_tree"] = "0" * 40
        self.save_manifest()
        with self.assertRaisesRegex(RuntimeError, "upstream tree mismatch"):
            self.prepare()

    def test_wrong_derived_tree_fails_before_source_changes(self):
        self.copy_checkout()
        self.manifest["derived_tree"] = "0" * 40
        self.save_manifest()
        self.assert_refused_before_refresh("derived tree mismatch")
        self.assertFalse(self.git("status", "--porcelain"))
        self.assertEqual((self.source / "sample.txt").read_text(), "original\n")

    def test_nonancestor_jinja_is_rejected(self):
        unrelated = self.git("commit-tree", self.tree, "-m", "unrelated").decode().strip()
        with mock.patch.object(source_helper, "JINJA_FIX_ANCESTOR", unrelated):
            self.manifest["jinja_fix_ancestor"] = unrelated
            self.save_manifest()
            with self.assertRaisesRegex(RuntimeError, "merge-base"):
                self.prepare()

    def test_tracked_worktree_and_index_dirt(self):
        (self.source / "sample.txt").write_text("dirty\n")
        with self.assertRaisesRegex(RuntimeError, "dirty"):
            self.prepare()
        self.git("add", "sample.txt")
        with self.assertRaisesRegex(RuntimeError, "dirty"):
            self.prepare()

    def test_untracked_and_ignored_files_are_rejected(self):
        for name in ("untracked-output", "ignored-output"):
            path = self.source / name
            path.write_text("unexpected\n")
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, "dirty"):
                self.prepare()
            path.unlink()

    def test_index_flags_cannot_hide_changes(self):
        self.copy_checkout()
        for flag in ("assume-unchanged", "skip-worktree"):
            self.git("update-index", "--" + flag, "sample.txt")
            with self.subTest(flag=flag):
                self.assert_refused_before_refresh("hidden")
            self.git("update-index", "--no-" + flag, "sample.txt")

    def test_filemode_config_cannot_hide_executable_change(self):
        self.git("config", "core.filemode", "false")
        (self.source / "sample.txt").chmod(0o755)
        with self.assertRaisesRegex(RuntimeError, "executable mode"):
            self.prepare()

    def test_ambient_git_environment_cannot_redirect_source_or_index(self):
        with mock.patch.dict(os.environ, {"GIT_DIR": "/nonexistent", "GIT_WORK_TREE": "/",
                                         "GIT_INDEX_FILE": "/nonexistent/index",
                                         "GIT_OBJECT_DIRECTORY": "/nonexistent/objects"}):
            self.assertEqual(self.prepare(check_only=True)["derived_tree"], self.derived)

    def test_source_and_recipe_symlinks_rejected(self):
        alias = self.source.parent / "alias"
        alias.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "ordinary checkout"):
            source_helper.prepare(alias, self.recipe)
        patch = self.recipe / source_helper.PATCH_FILE
        moved = self.recipe / "moved.patch"
        patch.rename(moved)
        patch.symlink_to(moved)
        with self.assertRaisesRegex(RuntimeError, "ordinary adjacent"):
            self.prepare()

    def test_external_git_object_store_rejected(self):
        alternates = self.source / ".git/objects/info/alternates"
        alternates.write_text("/nonexistent\n")
        with self.assertRaisesRegex(RuntimeError, "external Git object store"):
            self.prepare()

    def test_unapplicable_patch_does_not_modify_checkout(self):
        patch = self.recipe / source_helper.PATCH_FILE
        patch.write_text(patch.read_text().replace("-original", "-not-the-source"))
        self.manifest["patch_sha256"] = hashlib.sha256(patch.read_bytes()).hexdigest()
        self.save_manifest()
        with self.assertRaisesRegex(RuntimeError, "apply"):
            self.prepare()
        self.assertFalse(self.git("status", "--porcelain"))


class CheckedInRecipeTests(unittest.TestCase):
    def test_checked_in_manifest_and_patch(self):
        manifest, patch = source_helper.load_manifest(RECIPE)
        self.assertEqual(manifest["upstream_commit"], source_helper.UPSTREAM_COMMIT)
        self.assertEqual(patch.name, source_helper.PATCH_FILE)

    def test_d1_pins_and_package_layer_are_preserved(self):
        d1 = (RECIPE / "Dockerfile").read_text()
        d3p = (RECIPE / "Dockerfile.d3p").read_text()
        for line in d1.splitlines():
            if line.startswith(("ARG CUDA_", "ARG UBUNTU_SNAPSHOT", "ARG BUILD_JOBS", "ENV CC=")):
                self.assertIn(line, d3p)
            if "-D" in line and ("cmake -S" in line or line.lstrip().startswith("-D")):
                self.assertIn(line, d3p)
        package_layer = d1[d1.index("RUN rm -f"):d1.index("ARG LLAMA_COMMIT")]
        self.assertIn(package_layer, d3p)
        self.assertLess(d3p.index("prepare-d3p-source.py /src"), d3p.index("cmake -S"))
        self.assertNotIn("ARG LLAMA_COMMIT", d3p)
        self.assertIn('local.d3p.source.revision-kind="git-tree"', d3p)

    def test_cli_help_and_shell_syntax_without_host_actions(self):
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        for command in (["python3", str(RECIPE / "prepare-d3p-source.py"), "--help"],
                        ["bash", str(RECIPE / "build-d3p-runtime.sh"), "--help"],
                        ["bash", "-n", str(RECIPE / "build-d3p-runtime.sh")]):
            subprocess.run(command, env=env, check=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
