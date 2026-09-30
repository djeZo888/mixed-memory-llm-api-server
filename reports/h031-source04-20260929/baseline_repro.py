"""Run from repo root with PYTHONPATH=scripts; local source fixture only."""
import ast
import linecache
import subprocess
import unittest
from tests import test_mimo_startup_admission as t
base = '711b24e283c16b61067621de39b796a8657ee309'
raw = subprocess.check_output(['git', 'show', base + ':scripts/runtime/mimo/owner.py'], text=True)
node = next(n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name == 'supervise')
filename = '<exact-base-supervise>'
linecache.cache[filename] = (len(raw), None, raw.splitlines(True), filename)
print('Exact base supervise AST; unchanged helper globals; real temporary flock fixture.', flush=True)
exec(compile(ast.Module(body=[node], type_ignores=[]), filename, 'exec'), t.o.__dict__)
result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
    t.StartupAdmissionTests('test_transient_real_holder_release_reaches_body_once')]))
assert len(result.errors) == 1 and 'LeaseBusy: lifecycle_busy' in result.errors[0][1] and not result.failures
print('EXPECTED ORIGINAL FAILURE VERIFIED; no historical replay or VM operation.')
