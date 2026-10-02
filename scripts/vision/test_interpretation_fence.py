"""Source-only interpretation fence regressions; HTTP and image models mocked."""
import copy
import json
from pathlib import Path
import sys
import threading
import time
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'tests'))
from backend import interpretation_json, PADDLE
from service import Reject, BackendFailure, digest
from test_backend import VendorResponseTests, vendor_response
from test_service import fixture


class InterpretationFenceTests(unittest.TestCase):
    literal = '{"description":"fixture","uncertainties":[],"derivedConclusions":[]}'

    def test_unfenced_and_complete_fences(self):
        for raw in (self.literal, ' \n' + self.literal + '\t',
                    '```json\n' + self.literal + '\n```',
                    '\n\n```json\n' + self.literal + '\n```\n',
                    '```json\r\n' + self.literal + '\r\n```'):
            with self.subTest(raw=raw):
                self.assertEqual(interpretation_json(raw), json.loads(self.literal))

    def test_prose_wrong_truncated_malformed_and_duplicate_rejected(self):
        valid = '```json\n' + self.literal + '\n```'
        invalid = ['Here is JSON:\n' + valid, valid + '\nDone',
                   '```JSON\n' + self.literal + '\n```',
                   '```\n' + self.literal + '\n```',
                   '```javascript\n' + self.literal + '\n```',
                   '```json\n' + self.literal, valid[:-1],
                   '```json ' + self.literal + '\n```',
                   '```json\n{"description":}\n```',
                   '```json\n{"description":"x"',
                   '```json\n' + self.literal + self.literal + '\n```',
                   '{"description":"a","description":"b"}',
                   '```json\n{"description":"a","description":"b"}\n```',
                   valid + '\n' + valid]
        for raw in invalid:
            with self.subTest(raw=raw):
                with self.assertRaises(Reject): interpretation_json(raw)

    def test_original_literal_size_limit_includes_wrapper(self):
        literal = '"' + 'x' * 65534 + '"'
        self.assertEqual(len(interpretation_json(literal)), 65534)
        for raw in (literal + ' ', '```json\n' + literal + '\n```'):
            with self.assertRaises(Reject): interpretation_json(raw)


class FenceProvenanceTests(unittest.TestCase):
    def setUp(self):
        # Reuse the exact mocked transport and response-byte recorder.
        VendorResponseTests.setUp(self)

    def test_fenced_interpretation_keeps_original_provenance_and_ocr_literal(self):
        original = '\n\n```json\n' + self.payload['choices'][0]['message']['content'] + '\n```'
        self.payload['choices'][0]['message']['content'] = original
        interpretation = copy.deepcopy(self.payload)
        ocr_literal = '```json\n{"literal":"OCR stays fenced"}\n```'
        ocr = vendor_response(PADDLE, ocr_literal)
        self.responses = [interpretation, ocr]
        m, p = fixture()
        outcome = self.backend.execute(m, {1: p['page-1'][1]}, threading.Event(),
                                       time.monotonic() + 2, self.evidence.append)
        self.assertEqual(outcome.result['description'], 'Fixture')
        self.assertEqual(outcome.result['extraction']['text'][0]['exactText'], ocr_literal)
        checkpoints = [x for x in self.evidence if x['kind'] == 'model_response']
        self.assertEqual(checkpoints[0]['literalText'], original)
        self.assertEqual(checkpoints[0]['response'], interpretation)
        self.assertEqual(checkpoints[0]['responseSha256'], digest(self.raws[0]))

    def test_fence_does_not_relax_interpretation_schema_or_start_ocr(self):
        for body in ('{"description":"fixture","unexpected":1}',
                     '{"description":false,"uncertainties":[],"derivedConclusions":[]}',
                     '{"description":"fixture","uncertainties":{},"derivedConclusions":[]}'):
            self.payload['choices'][0]['message']['content'] = '```json\n' + body + '\n```'
            before = self.transport.call_count
            m, p = fixture()
            with self.assertRaises(BackendFailure) as error:
                self.backend.execute(m, {1: p['page-1'][1]}, threading.Event(),
                                     time.monotonic() + 2, self.evidence.append)
            self.assertTrue(error.exception.settled)
            self.assertEqual(self.transport.call_count, before + 1)


if __name__ == '__main__': unittest.main()
