"""Focused approved repair checks; no inference or host mutations."""
import copy
import hashlib
import json
import pathlib
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import native_identity as identity
import candidate_owner as owner
import benchmark
import private_proxy
import verify_retained


class RepairTests(unittest.TestCase):
    def test_raw_and_pinned_lexer_effective_are_distinct_exact_pins(self):
        raw = (pathlib.Path(__file__).resolve().parents[3] / 'reports/h014-mimo-selection-20260927/sources/pro-chat_template.jinja').read_bytes()
        self.assertEqual(len(raw), 3867)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), identity.RAW_TEMPLATE_SHA256)
        effective = identity.pinned_lexer_source(raw.decode()).encode()
        self.assertEqual(len(effective), 3866)
        self.assertEqual(hashlib.sha256(effective).hexdigest(), identity.EFFECTIVE_TEMPLATE_SHA256)
        self.assertEqual(identity.pinned_lexer_source('x\n\n'), 'x\n')
        self.assertEqual(identity.pinned_lexer_source('x \t'), 'x \t')
        props = {'model_alias': 'mimo-v2.6-pro-rl', 'build_info': 'b1-7ac59a6', 'model_path': identity.MODEL_PATH, 'default_generation_settings': {'n_ctx': 131072}, 'total_slots': 1, 'is_sleeping': False, 'chat_template': effective.decode()}
        identity.validate_identity(identity.compact_identity(props))
        for field,value,reason in [('chat_template',raw.decode(),'loaded_effective_template_mismatch'),('build_info','wrong','loaded_build_mismatch'),('model_path','wrong','loaded_model_path_mismatch')]:
            with self.assertRaisesRegex(RuntimeError, reason):
                identity.validate_identity(identity.compact_identity({**props,field:value}))

    def test_fresh_namespace_keeps_original_verification(self):
        self.assertEqual(owner.LOG, verify_retained.LOG)
        self.assertEqual(benchmark.LOG, owner.LOG)
        self.assertTrue(owner.BASE.endswith('/worker1-r3'))
        self.assertTrue(owner.LOG.endswith('/worker1-r3'))
        self.assertEqual(owner.NAME, 'llm-h016-mimo-pro-r3')
        source = pathlib.Path(owner.__file__).read_text()
        self.assertIn("P('/data/logs/H016-20260927/worker1', 'VERIFICATION-STATUS.json')", source)
        self.assertNotIn('/data/logs/H016-20260927/worker1/OWNER.json', pathlib.Path(benchmark.__file__).read_text())
        self.assertLess(source.index("save(h, 'NATIVE-OBSERVED.json'"), source.index('validate_identity(observed)'))

    def test_private_production17_is_exact_and_unchanged(self):
        path = pathlib.Path(__file__).resolve().parents[4] / 'private/mimo-production-fixture-65536.json'
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), '2fb03cef2e700b304f8eea538a5ef8df300afc53bb0a94241bc754c17679ef78')
        body = json.loads(raw)['canonicalBody']; before = copy.deepcopy(body)
        private_proxy.normalize(body)
        self.assertEqual(body, before)
        self.assertEqual(len(body['tools']), 17)
        self.assertEqual(body['max_tokens'], 65536)
        self.assertEqual(hashlib.sha256(json.dumps(body,separators=(',', ':'),ensure_ascii=False).encode()).hexdigest(), 'c85d504741f038c1a0f150fdb59657a661ed38330958daab2b3f93f293e1e41b')
        self.assertEqual(hashlib.sha256(json.dumps(body['tools'],separators=(',', ':'),ensure_ascii=False).encode()).hexdigest(), '80e7a1e12e073ac57638e86638cf571158711ff821c96605135627777ce44e8c')


if __name__ == '__main__':
    unittest.main()
