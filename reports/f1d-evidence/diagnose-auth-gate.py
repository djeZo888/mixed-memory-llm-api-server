#!/usr/bin/env python3
"""Sentinel-only traceback locations; no values, logs, keys or source changes."""
import json
import runpy
import sys

events = []
def trace(frame, event, arg):
    path = frame.f_code.co_filename
    if event == 'exception' and (path.endswith('/run_pinned_image.py') or path.endswith('/sglang_file_auth.py')):
        kind, value, tb = arg
        frames = []
        while tb is not None:
            frames.append({'file': tb.tb_frame.f_code.co_filename, 'line': tb.tb_lineno,
                           'function': tb.tb_frame.f_code.co_name})
            tb = tb.tb_next
        # Exception type and frame locations only, never message/local variables.
        events.append({'type': kind.__name__, 'frames': frames})
    return trace

sys.argv = ['/fixture/tests/lifecycle/sglang_fixture/run_pinned_image.py', '--actual-image', '--repo', '/fixture']
sys.settrace(trace)
try:
    runpy.run_path(sys.argv[0], run_name='__main__')
finally:
    sys.settrace(None)
    sys.__stdout__.write(json.dumps({'evidence_class': 'SENTINEL_ONLY_DIAGNOSTIC_NOT_GATE',
                                   'exception_locations': events[-12:]}, sort_keys=True) + '\n')
