"""Exercise real source bytes; no hash override or generated PASS receipt file."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.lifecycle.test_qwen38 import ROOT, bound, auth_receipt, q, LifecycleError


class FinalSource(unittest.TestCase):
    def test_actual_fixture_and_support_source_drift_rejects(self):
        d = bound(); proof, _ = auth_receipt(d)
        identity = {name: proof[name] for name in ('image_id', 'image_reference', 'source_revision', 'launcher_sha256')}
        for relative, code in (
                ('tests/lifecycle/sglang38_fixture/run_fixture.py', 'qwen38_auth_fixture_changed'),
                ('tests/lifecycle/sglang38_fixture/run_pinned_image.py', 'qwen38_auth_fixture_changed'),
                ('tests/lifecycle/sglang38_fixture/cache_probe.py', 'qwen38_auth_fixture_changed'),
                ('scripts/runtime/qwen38_oci.py', 'qwen38_support_source_changed')):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for source in ('scripts/runtime', 'tests/lifecycle/sglang38_fixture'):
                    shutil.copytree(ROOT / source, root / source)
                target = root / relative
                target.write_bytes(target.read_bytes() + b'\n')
                with patch.object(q, 'ROOT', root), self.assertRaisesRegex(LifecycleError, '^' + code + '$'):
                    q._validate_auth_proof(proof, identity)

    def test_final_source_happy_path_and_provenance_drift_rejection(self):
        d = bound()
        _, instance = auth_receipt(d)
        self.assertTrue(q.evidence(d, instance)['auth_gate_passed'])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in q.PROFILE_HASHES:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            target = root / 'tests/lifecycle/sglang38_fixture/provenance.json'
            target.write_bytes(target.read_bytes() + b'\n')
            with patch.object(q, 'ROOT', root), self.assertRaisesRegex(
                    LifecycleError, '^qwen38_source_profile_pin_mismatch$'):
                q._pinned_json('tests/lifecycle/sglang38_fixture/provenance.json')


if __name__ == '__main__':
    unittest.main()
