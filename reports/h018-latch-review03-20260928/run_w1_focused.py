"""Run only the supplied LatchRefreshTests class against frozen sibling owner.

Usage: python3 -B reports/h018-latch-review03-20260928/run_w1_focused.py INPUT_DIR
AST class selection avoids the delivered test file's repository-relative owner
import; no W1 bytes are changed and no unrelated tests are run.
"""
import ast
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
input_dir = Path(sys.argv[1]).resolve()
owner_path, test_path = input_dir / 'owner.py', input_dir / 'test_mimo_owner.py'
spec = importlib.util.spec_from_file_location('w1_frozen_owner', owner_path)
o = importlib.util.module_from_spec(spec)
spec.loader.exec_module(o)
node = next(n for n in ast.parse(test_path.read_text()).body
            if isinstance(n, ast.ClassDef) and n.name == 'LatchRefreshTests')
namespace = globals().copy()
exec(compile(ast.Module(body=[node], type_ignores=[]), str(test_path), 'exec'), namespace)
stream = io.StringIO()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(namespace['LatchRefreshTests'])
result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
report_dir = Path(__file__).resolve().parent
(report_dir / 'W1-FOCUSED-TESTS.txt').write_text(stream.getvalue())
metadata = {
    'owner_sha256': hashlib.sha256(owner_path.read_bytes()).hexdigest(),
    'test_sha256': hashlib.sha256(test_path.read_bytes()).hexdigest(),
    'execution': 'Only supplied LatchRefreshTests AST; supplied owner injected. '
                 'Existing policy and temporary canonical lease real; no VM/GPU/network or broad suite.',
    'tests_run': result.testsRun, 'failures': len(result.failures),
    'errors': len(result.errors), 'successful': result.wasSuccessful(),
    'review_harness_note': 'Initial ad hoc runner omitted json from its class globals; corrected here. '
                           'Those NameErrors were reviewer harness errors, not W1 failures.'}
(report_dir / 'W1-FOCUSED-RESULT.json').write_text(json.dumps(metadata, indent=2) + '\n')
print(json.dumps(metadata))
print(stream.getvalue())
sys.exit(0 if result.wasSuccessful() else 1)
