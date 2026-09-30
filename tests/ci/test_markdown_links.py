"""Offline checks for literal examples and byte-bound archive provenance."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('markdown_links', ROOT / 'scripts/ci/check_markdown_links.py')
links = importlib.util.module_from_spec(spec)
spec.loader.exec_module(links)


class MarkdownLinksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_literals_titles_and_active_failure(self):
        self.write('real.png', '')
        self.write('a.md', '`![example](missing)`\n``![other](missing)``\n'
                   '```md\n[x](missing)\n```\n~~~\n[x](missing)\n~~~\n'
                   '![real](real.png "a title")\n[real](<real.png>)\n[bad](missing)')
        self.assertEqual(links.check(self.root), ['a.md: missing local link target: missing'])

    def test_archive_context_is_exact_and_hash_bound(self):
        self.write('target', '')
        md = self.write('archive/original.md', '[source](target)')
        digest = hashlib.sha256(md.read_bytes()).hexdigest()
        with patch.dict(links.ARCHIVE_CONTEXTS, {'archive/original.md': (digest, '.')}):
            self.assertEqual(links.check(self.root), [])
            md.write_text(md.read_text() + '\nchanged')
            self.assertIn('archive/original.md: archived evidence hash mismatch', links.check(self.root))
            self.assertIn('archive/original.md: missing local link target: target', links.check(self.root))

    def test_external_archive_exception_never_hides_other_links_or_escapes(self):
        md = self.write('a.md', '[original](external.png)\n[bad](missing)\n[escape](../outside)')
        digest = hashlib.sha256(md.read_bytes()).hexdigest()
        with patch.dict(links.EXTERNAL_ARCHIVES, {'a.md': (digest, {'external.png'})}):
            self.assertEqual(links.check(self.root), ['a.md: missing local link target: missing',
                                                    'a.md: link escapes repository: ../outside'])

    def test_repository_archive_hashes_are_exact(self):
        for name, (digest, _) in {**links.ARCHIVE_CONTEXTS, **links.EXTERNAL_ARCHIVES}.items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest, name)


if __name__ == '__main__':
    unittest.main()
