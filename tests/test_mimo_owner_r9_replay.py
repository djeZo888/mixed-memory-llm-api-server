"""Explicit replay of retained complete R9 HTTP evidence; raw stays private.

Set H017_R9_FIXTURE and H017_R9_MANIFEST to the paths in OFFLINE-R9-REPLAY.json.
No synthetic identity or network fallback is allowed. Initial baseline PASS is
archived; this optional regression is not automatically rerun on every suite.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('owner_r9_replay', ROOT / 'scripts/runtime/mimo/owner.py')
o = importlib.util.module_from_spec(spec)
spec.loader.exec_module(o)


class GenuineR9Tests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('H017_R9_FIXTURE') and os.environ.get('H017_R9_MANIFEST'),
                         'explicit private retained R9 paths required; baseline replay already archived')
    def test_complete_authentic_r9_props_slots_and_manifest(self):
        raw = Path(os.environ['H017_R9_FIXTURE']).read_bytes()
        manifest_raw = Path(os.environ['H017_R9_MANIFEST']).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'b7b3f33e8add3db97db43fa4e46f21c820719ad4004372c5772636267f57918f')
        self.assertEqual(hashlib.sha256(manifest_raw).hexdigest(),'906530a52cd95fc9af27b79abcf73c4304728fe135ec77b5edbbb4ce512f449c')
        evidence,manifest=json.loads(raw),json.loads(manifest_raw)
        o.validate_manifest(manifest)
        responses={path:(evidence[key]['http_status'],evidence[key]['value'])
                   for path,key in [('/props','actual_props'),('/slots','actual_slots')]}
        with patch.object(o,'get',side_effect=lambda path,key:responses[path]) as get:
            self.assertIs(o.native_ready(manifest,b'offline-fixture'),True)
        self.assertEqual([c.args[0] for c in get.call_args_list],['/props','/slots'])
        self.assertEqual(manifest['context'],1000000)

if __name__=='__main__':unittest.main()
