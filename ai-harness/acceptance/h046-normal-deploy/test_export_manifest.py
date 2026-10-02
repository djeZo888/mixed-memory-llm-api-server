#!/usr/bin/env python3
"""Local source/graph/archive regression tests; no native or live qualification."""
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("h046_export_manifest", Path(__file__).with_name("export_manifest.py"))
E = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(E)
REPO = Path(__file__).resolve().parents[3]


class GraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names = ("technical-vision-qualification.ts", "codex-receipts.ts", "codex-specialist-qualification.ts")
        cls.source = {"ai-harness/server/src/" + name: (REPO / "ai-harness/server/src" / name).read_bytes() for name in names}
        cls.vision, cls.profiles, cls.generation, cls.frontier = E.authoritative_graphs(cls.source)

    def fixture(self):
        files = dict(self.source)
        for name in set(self.vision):
            files["ai-harness/server/dist/" + name + ".js"] = b"export const n = 1;\n"
            files["ai-harness/server/src/" + name + ".ts"] = b"export const n = 1;\n"
        files.update(self.source)
        files["ai-harness/server/dist/main.js"] = b'import "./nested.js";\n'
        files["ai-harness/server/dist/nested.js"] = b'import("./nested-two.js");\n'
        files["ai-harness/server/src/nested.ts"] = b"export {};\n"
        files["ai-harness/server/dist/nested-two.js"] = b"export {};\n"
        files["ai-harness/server/src/nested-two.ts"] = b"export {};\n"
        files["ai-harness/server/dist/codex-preview-main.js"] = b'import {n} from "./main.js";\n'
        files["ai-harness/server/src/codex-preview-main.ts"] = b"export {};\n"
        files["ai-harness/server/package-lock.json"] = b"{}\n"
        for paths in self.profiles.values():
            for name in paths:
                files[E.os.path.normpath("ai-harness/deploy/" + name)] = b"fixture\n"
        files["ai-harness/deploy/engine/validate-image-overlays.py"] = b"fixture\n"
        for name in self.generation + self.frontier:
            files.setdefault(name, b"fixture\n")
        return files

    def test_current_authoritative_shapes_and_order(self):
        self.assertEqual(len(self.vision), 18)
        self.assertEqual(self.vision[:4], ["main", "app", "broker", "gateway"])
        self.assertEqual(self.vision[-3:], ["contracts", "store", "files"])
        self.assertEqual(len(self.generation), 30)
        self.assertEqual(len(self.frontier), 14)
        self.assertEqual([len(self.profiles[p]) for p in E.PROFILES], [8, 10, 12, 14])

    def test_ordinary_exact_recursive_closure_excludes_unimported_helper(self):
        files = self.fixture()
        files["ai-harness/deploy/run-server.sh"] = b"unimported launcher\n"
        files["ai-harness/server/dist/unimported.js"] = b"unimported app byte\n"
        graph = E.ordinary_files(files, self.profiles["technical-generation"])
        self.assertIn("ai-harness/server/dist/nested-two.js", graph)
        self.assertIn("ai-harness/server/src/nested-two.ts", graph)
        self.assertIn("ai-harness/deploy/engine/validate-image-overlays.py", graph)
        self.assertNotIn("ai-harness/deploy/run-server.sh", graph)
        self.assertNotIn("ai-harness/server/dist/unimported.js", graph)
        self.assertIn("ai-harness/tools/technical-vision/technical-vision.mjs", graph)
        self.assertIn("ai-harness/tools/image/image.mjs", graph)

    def test_ordinary_missing_pair_and_escape_refused(self):
        files = self.fixture()
        del files["ai-harness/server/src/nested-two.ts"]
        with self.assertRaises(E.Refused):
            E.ordinary_files(files, self.profiles["ordinary"])
        files = self.fixture()
        files["ai-harness/server/dist/main.js"] = b'import "../../outside.js";\n'
        with self.assertRaisesRegex(E.Refused, "escapes"):
            E.ordinary_files(files, self.profiles["ordinary"])

    def test_vision_digest_is_javascript_insertion_order(self):
        files = self.fixture()
        source = {n: b for n, b in files.items() if "/dist/" not in n}
        compiled = {n: b for n, b in files.items() if "/dist/" in n}
        vision, generation, frontier, ordinary = E.make_graphs(source, compiled, PurePosixPath("/opt/release"), "a" * 40)
        ordered = json.dumps(vision["sourceBindings"], separators=(",", ":")).encode()
        self.assertEqual(vision["sourceGraphSha256"], hashlib.sha256(ordered).hexdigest())
        self.assertNotEqual(vision["sourceGraphSha256"], E.sha(E.canonical(vision["sourceBindings"])))
        self.assertEqual(generation["requiredCount"], 30)
        self.assertEqual(len(generation["sourceClosure"]), 30)
        self.assertEqual(list(ordinary["profiles"]), list(E.PROFILES))

    def test_authoritative_schema_drift_refused(self):
        changed = dict(self.source)
        key = "ai-harness/server/src/technical-vision-qualification.ts"
        changed[key] = changed[key].replace(b'"store", "files"]', b'"store"]')
        with self.assertRaisesRegex(E.Refused, "exact18"):
            E.authoritative_graphs(changed)


class SealedArchiveTests(unittest.TestCase):
    def test_immutable_release_path_requires_final_commit(self):
        commit = "a" * 40
        self.assertEqual(str(E.release_path("/opt/ai-harness/releases/" + commit + "-h046-normal05", commit)),
                         "/opt/ai-harness/releases/" + commit + "-h046-normal05")
        for path in ("relative", "/opt/ai-harness/releases/old", "/opt/../" + commit + "-x"):
            with self.assertRaises(E.Refused):
                E.release_path(path, commit)

    def test_archive_is_deterministic_regular_relative_and_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            files = {"ai-harness/server/src/z.ts": b"z\n", "ai-harness/deploy/run-server.sh": b"x\n"}
            a = E.write_archive(root / "first.tar.gz", files, {"ai-harness/deploy/run-server.sh": 0o755})
            b = E.write_archive(root / "second.tar.gz", files, {"ai-harness/deploy/run-server.sh": 0o755})
            self.assertEqual(a["sha256"], b["sha256"])
            with tarfile.open(root / "first.tar.gz") as tar:
                members = tar.getmembers()
                self.assertEqual([m.name for m in members], sorted(files))
                self.assertTrue(all(m.isfile() and not m.issym() and not m.islnk() for m in members))
                self.assertTrue(all(m.mtime == 0 and m.uid == 0 and m.gid == 0 for m in members))
                self.assertEqual(members[0].mode, 0o755)
                for member in members:
                    self.assertEqual(tar.extractfile(member).read(), files[member.name])

    def test_forbidden_archive_inputs(self):
        for path in ("../ai-harness/x", "/ai-harness/x", "ai-harness/node_modules/x.js",
                     "ai-harness/secrets/x.json", "ai-harness/auth.json", "ai-harness/.env",
                     "ai-harness/logs/x", "ai-harness/native.bin", "ai-harness/run.jsonl"):
            with self.subTest(path=path), self.assertRaises(E.Refused):
                E.safe_relative(path)

    def test_sealed_source_requires_clean_head_and_exact_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            p = repo / "ai-harness/server/src/main.ts"
            p.parent.mkdir(parents=True)
            p.write_text("export {};\n")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                            "commit", "-qm", "fixture"], check=True)
            commit, source, modes = E.sealed_source(repo)
            self.assertEqual(source["ai-harness/server/src/main.ts"], b"export {};\n")
            with self.assertRaises(E.Refused):
                E.sealed_source(repo, "b" * 40)
            p.write_text("export const changed = 1;\n")
            with self.assertRaisesRegex(E.Refused, "HEAD must be clean"):
                E.sealed_source(repo, commit)

    def test_symlink_and_hardlink_source_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp).resolve() / "file"
            p.write_text("fixture")
            alias = p.with_name("alias")
            alias.symlink_to(p)
            with self.assertRaises(E.Refused):
                E.read_regular(alias)
            alias.unlink()
            E.os.link(p, alias)
            with self.assertRaises(E.Refused):
                E.read_regular(p)


if __name__ == "__main__":
    unittest.main()
