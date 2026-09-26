"""Offline packaging boundaries; synthetic source is never native acceptance."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from runtime import build_adaptive_idle_overlay as builder
from runtime import verify_adaptive_idle_overlay as verifier


class OverlayPackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        self.name = "python/sglang/srt/scheduler.py"
        self.native = self.source / self.name
        self.native.parent.mkdir(parents=True)
        self.native.write_bytes(b"VALUE = 1\n")
        self.patch = self.runtime / "change.patch"
        self.patch.write_text("--- a/" + self.name + "\n+++ b/" + self.name + "\n@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n")
        (self.runtime / "policy.py").write_text("GRACE = 600\n")
        (self.runtime / "verify_adaptive_idle_overlay.py").write_bytes((ROOT / "scripts/runtime/verify_adaptive_idle_overlay.py").read_bytes())
        self.package = self.root / "installed"
        self.spec = {"upstream_revision": "fixture-only", "image_reference": "sha256:" + "1" * 64,
                     "native_package_root": str(self.package), "files": {self.name: hashlib.sha256(self.native.read_bytes()).hexdigest()},
                     "patches": ["change.patch"], "helpers": {"python/sglang/srt/policy.py": "policy.py"}, "installed_preconditions": {}}
        self.manifest = self.root / "manifest.json"
        self.save_manifest()

    def save_manifest(self):
        self.manifest.write_text(json.dumps({"text": self.spec}))

    def prepare(self, name="output"):
        return builder.prepare(self.source, "text", self.root / name, manifest_path=self.manifest, runtime=self.runtime)

    def test_exact_transformation_deterministic_receipt_and_readonly_guard(self):
        a, b = self.prepare(), self.prepare("second")
        self.assertEqual(a, b)
        self.assertEqual(self.native.read_bytes(), b"VALUE = 1\n")
        self.assertIsNone(a["new_image_identity"])
        self.assertFalse(a["image_built"])
        self.assertFalse(a["native_integration_accepted"])
        output = self.root / "output"
        self.assertEqual((output / "files" / self.name).read_bytes(), b"VALUE = 2\n")
        docker = (output / "Dockerfile").read_text()
        self.assertLess(docker.index("sha256sum -c"), docker.index("COPY"))
        for source in (output / "files/python/sglang").rglob("*.py"):
            dest = self.package / source.relative_to(output / "files/python/sglang")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(source.read_bytes())
        with patch.dict(verifier.PACKAGE_ROOTS, {"text": str(self.package)}):
            self.assertEqual(verifier.verify_installed(output / "provenance.json", a["overlay_sha256"], "text")["verified_files"], 2)
            (self.package / "srt/scheduler.py").write_text("VALUE = 3\n")
            with self.assertRaisesRegex(ValueError, "installed_source_mismatch"):
                verifier.verify_installed(output / "provenance.json", a["overlay_sha256"], "text")

    def test_newline_drift_rejects_before_output_and_preserves_source(self):
        self.native.write_bytes(b"VALUE = 1\r\n")
        with self.assertRaisesRegex(ValueError, "source_hash_mismatch"):
            self.prepare()
        self.assertFalse((self.root / "output").exists())
        self.assertEqual(self.native.read_bytes(), b"VALUE = 1\r\n")

    def test_image_legacy_recipe_repairs_restrictive_copy_without_touching_secrets(self):
        self.manifest.write_text(json.dumps({"image": self.spec}))
        previous_umask = os.umask(0o077)
        try:
            receipt = builder.prepare(self.source, "image", self.root / "image",
                                      manifest_path=self.manifest, runtime=self.runtime)
        finally:
            os.umask(previous_umask)
        context = self.root / "image"
        # Reproduce COPY preserving restrictive protected-transfer file modes.
        metadata = self.root / "opt/llmctl/adaptive-idle"
        metadata.mkdir(parents=True, mode=0o700)
        metadata.parent.chmod(0o700)
        copied = []
        for line in (context / "Dockerfile").read_text().splitlines():
            if line.startswith("COPY "):
                source, destination = json.loads(line[5:])
                destination = Path(destination.replace("/opt/llmctl", str(metadata.parent)))
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((context / source).read_bytes())
                destination.chmod(0o600)
                copied.append(destination)
        before = {str(p): builder.digest(p.read_bytes()) for p in copied}
        secret = self.root / "protected-host-secret"
        secret.write_bytes(b"synthetic-fixture-only")
        secret.chmod(0o600)
        old_secret = (secret.read_bytes(), secret.stat().st_mode)
        recipe = (context / "Dockerfile").read_text().splitlines()
        command = json.loads(recipe[-1][4:])
        self.assertEqual(command[:2], ["/bin/sh", "-ec"])
        self.assertNotIn("-R", command[2])
        self.assertNotIn("--chmod", "\n".join(recipe))
        command[2] = command[2].replace("/opt/llmctl", str(metadata.parent))
        subprocess.run(command, check=True)
        self.assertEqual(before, {str(p): builder.digest(p.read_bytes()) for p in copied})
        self.assertEqual(old_secret, (secret.read_bytes(), secret.stat().st_mode))
        for path in copied:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            # UID1000:GID1001 uses non-owner bits on root-owned COPY payload.
            self.assertTrue(path.stat().st_mode & stat.S_IROTH)
            self.assertFalse(path.stat().st_mode & (stat.S_IWGRP | stat.S_IWOTH))
        for path in (metadata, metadata.parent):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755)
        core = {key: receipt[key] for key in verifier.CORE_KEYS}
        self.assertEqual(builder.digest(builder.canonical(core)), receipt["overlay_sha256"])

    def test_unpinned_patch_target_rejected_before_output(self):
        self.patch.write_text(self.patch.read_text().replace("scheduler.py", "other.py"))
        with self.assertRaisesRegex(ValueError, "unpinned_patch_target"):
            self.prepare()
        self.assertFalse((self.root / "output").exists())

    def test_syntax_failure_no_partial_output(self):
        (self.runtime / "policy.py").write_text("broken syntax ?\n")
        with self.assertRaises(SyntaxError):
            self.prepare()
        self.assertFalse((self.root / "output").exists())

    def test_output_refused_without_overwriting(self):
        output = self.root / "output"
        output.mkdir()
        (output / "keep").write_text("prior evidence")
        with self.assertRaisesRegex(ValueError, "output_exists"):
            self.prepare()
        self.assertEqual((output / "keep").read_text(), "prior evidence")

    def test_source_symlink_and_parent_symlink_rejected(self):
        real = self.root / "real.py"
        self.native.rename(real)
        self.native.symlink_to(real)
        with self.assertRaisesRegex(ValueError, "source_missing"):
            self.prepare()
        self.native.unlink()
        self.native.write_bytes(real.read_bytes())
        directory = self.root / "redirected-source"
        self.native.parent.rename(directory)
        self.native.parent.symlink_to(directory, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "source_missing"):
            self.prepare()

    def test_receipt_cannot_choose_own_digest(self):
        receipt = self.prepare()
        with self.assertRaisesRegex(ValueError, "digest_mismatch"):
            verifier.verify_installed(self.root / "output/provenance.json", "0" * 64, "text")
        path = self.root / "output/provenance.json"
        data = json.loads(path.read_text())
        data["output_raw_sha256"][self.name] = "0" * 64
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "digest_mismatch"):
            verifier.verify_installed(path, receipt["overlay_sha256"], "text")


if __name__ == "__main__":
    unittest.main()
