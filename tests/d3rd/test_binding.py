"""Mutate actual chosen D3BR evidence/source; never manufacture a PASS image."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from d3rd import verify_binding as binder
from d3t.profiles import SOURCE_PINS


class ActualProofBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="d3rd-proof-negative-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        proof = binder.document(ROOT, binder.PROOF)
        paths = set(proof["evidence_sha256"]) | set(proof["build_recipe_sha256"])
        paths |= set(SOURCE_PINS) | set(binder.DEPLOYMENTS) | {
            binder.PROOF, f"configs/runtimes/{binder.RUNTIME}.json",
            "reports/d3br-evidence/provenance.json", "scripts/d3t/profiles.py",
        }
        for relative in paths:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)

    def edit_json(self, relative, mutation, *, rehash_evidence=False):
        value = binder.document(self.root, relative)
        mutation(value)
        (self.root / relative).write_text(json.dumps(value, indent=2) + "\n")
        if rehash_evidence:
            self.rehash(relative)

    def rehash(self, relative):
        # Simulate internally rehashed tampering. Other actual measurements and
        # reviewed recipe/source identities must still reject changed content.
        self.edit_json(binder.PROOF, lambda p: p["evidence_sha256"].update({
            relative: binder.digest(self.root, relative)}))

    def check(self):
        return binder.verify(self.root, inventory=False)

    def test_actual_delivered_image_proof_and_two_profiles_pass(self):
        self.assertEqual(self.check()["status"], "PASS_SOURCE_BINDING_ONLY")
        self.assertEqual(self.check()["image_id"], binder.document(ROOT, binder.PROOF)["image_id"])

    def test_wrong_image_and_d1_image_are_refused(self):
        original = (self.root / binder.PROOF).read_bytes()
        real = binder.document(self.root, binder.PROOF)["image_id"]
        wrong = real[:-1] + ("0" if real[-1] != "0" else "1")
        d1 = binder.document(self.root, binder.D1)["validation"]["image_id"]
        for identity in (wrong, d1):
            with self.subTest(image=identity):
                self.edit_json(binder.PROOF, lambda p: p.update(image_id=identity))
                with self.assertRaises(binder.BindingError):
                    self.check()
                (self.root / binder.PROOF).write_bytes(original)

    def test_missing_n_cpu_moe_in_runtime_is_refused(self):
        self.edit_json(f"configs/runtimes/{binder.RUNTIME}.json",
                       lambda r: r["required_cli_flags"].remove("--n-cpu-moe"))
        with self.assertRaises(binder.BindingError):
            self.check()

    def test_rehashed_help_without_n_cpu_moe_is_refused(self):
        relative = binder.EVIDENCE + "llama-server-help.txt"
        path = self.root / relative
        self.assertIn(b"--n-cpu-moe", path.read_bytes())
        path.write_bytes(path.read_bytes().replace(b"--n-cpu-moe", b"--removed-flag"))
        self.rehash(relative)
        with self.assertRaises(binder.BindingError):
            self.check()

    def test_wrong_runtime_tag_is_refused(self):
        self.edit_json(f"configs/runtimes/{binder.RUNTIME}.json",
                       lambda r: r.update(image_tag=r["image_tag"] + "-unreviewed"))
        with self.assertRaises(binder.BindingError):
            self.check()

    def test_wrong_runtime_entrypoint_is_refused(self):
        self.edit_json(f"configs/runtimes/{binder.RUNTIME}.json",
                       lambda r: r.update(entrypoint=["/unreviewed/server"]))
        with self.assertRaises(binder.BindingError):
            self.check()

    def test_each_of_six_actual_recipe_files_rejects_byte_drift(self):
        for relative in binder.document(self.root, binder.PROOF)["build_recipe_sha256"]:
            with self.subTest(recipe=relative):
                path = self.root / relative
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                with self.assertRaises(binder.BindingError):
                    self.check()
                path.write_bytes(original)

    def test_rehashed_image_recipe_patch_digest_drift_is_refused(self):
        relative = binder.EVIDENCE + "build-recipe-sha256.txt"
        path = self.root / relative
        lines = path.read_text().splitlines()
        index = next(i for i, line in enumerate(lines) if line.endswith("strict-model-chat.patch"))
        lines[index] = ("0" if lines[index][0] != "0" else "1") + lines[index][1:]
        path.write_text("\n".join(lines) + "\n")
        self.rehash(relative)
        with self.assertRaises(binder.BindingError):
            self.check()

    def test_rehashed_derived_tree_drift_is_refused(self):
        relative = binder.EVIDENCE + "source-tree.txt"
        path = self.root / relative
        original = path.read_text()
        path.write_text(("0" if original[0] != "0" else "1") + original[1:])
        self.rehash(relative)
        with self.assertRaises(binder.BindingError):
            self.check()

    def test_rehashed_provenance_patch_or_tree_or_commit_drift_is_refused(self):
        relative = binder.EVIDENCE + "source-provenance.json"
        original = (self.root / relative).read_bytes()
        for key in ("patch_sha256", "derived_tree", "derived_commit"):
            with self.subTest(field=key):
                self.edit_json(relative, lambda p: p.update({key: "unreviewed"}), rehash_evidence=True)
                with self.assertRaises(binder.BindingError):
                    self.check()
                (self.root / relative).write_bytes(original)
                self.rehash(relative)

    def test_version_is_verbatim_and_patched_source_is_never_clean(self):
        self.edit_json(binder.PROOF, lambda p: p.update(version_stdout="v0.4.1\n"))
        with self.assertRaises(binder.BindingError):
            self.check()
        shutil.copyfile(ROOT / binder.PROOF, self.root / binder.PROOF)
        self.edit_json(binder.PROOF, lambda p: p.update(source_clean=True))
        with self.assertRaises(binder.BindingError):
            self.check()

    def test_profile_budget_or_launch_drift_is_refused(self):
        self.edit_json(binder.DEPLOYMENTS[0], lambda d: d["launch"].update(parallel=2))
        with self.assertRaises(binder.BindingError):
            self.check()

    def test_final_exact_inventory_has_no_extra_publication_dependencies(self):
        binder.verify(ROOT)
        inventory = binder.document(ROOT, "reports/l2-source-closure-sha256.json")
        closure = binder.document(ROOT, "scripts/control/source-closure.json")
        proof = binder.document(ROOT, binder.PROOF)
        expected = set(closure["normal_files"]) | set(closure["recovery_files"])
        expected |= set(proof["evidence_sha256"]) | set(proof["build_recipe_sha256"])
        expected |= {binder.PROOF, f"configs/runtimes/{binder.RUNTIME}.json",
                     *binder.DEPLOYMENTS, "reports/d3br-evidence/provenance.json"}
        self.assertEqual(set(inventory["files"]), expected)


if __name__ == "__main__":
    unittest.main()
