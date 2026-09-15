"""Immutable V1G2 fixture tests; run with python3 -I -B test_text_utils.py."""

import importlib.util
from pathlib import Path
import unittest


SOURCE_PATH = Path(__file__).resolve().with_name("text_utils.py")
SPEC = importlib.util.spec_from_file_location("v1g2_text_utils", SOURCE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load sibling text_utils.py")
TEXT_UTILS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TEXT_UTILS)


class WordCountTests(unittest.TestCase):
    def test_ordinary_two_words(self):
        self.assertEqual(TEXT_UTILS.word_count("hello world"), 2)

    def test_arbitrary_whitespace(self):
        for text in ("  hello world  ", "hello\tworld", "hello\nworld", " \thello\nworld\t "):
            with self.subTest(text=text):
                self.assertEqual(TEXT_UTILS.word_count(text), 2)

    def test_empty_string(self):
        self.assertEqual(TEXT_UTILS.word_count(""), 0)


if __name__ == "__main__":
    unittest.main()
