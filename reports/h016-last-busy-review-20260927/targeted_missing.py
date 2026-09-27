"""Additional missing negatives; offline actual client/reader/settle, no sockets.
Usage: python3 -B targeted_missing.py PRIVATE_SOURCE_ROOT
"""
import importlib.util
import json
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
p = root / 'scripts/h016/final13_long/test_last_ownership.py'
spec = importlib.util.spec_from_file_location('w1_ownership_review_fixture', p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
fixture = m.OwnershipTests()
base = b'HTTP/1.0 429 Too Many Requests\r\n' + m.MARKER + b'Content-Length: 0\r\n\r\n'
cases = {
    'HTTP_0_9_must_remain_ambiguous': base.replace(b'HTTP/1.0', b'HTTP/0.9'),
    'HTTP_1_1_must_remain_ambiguous': base.replace(b'HTTP/1.0', b'HTTP/1.1'),
    'wrong_marker_must_remain_ambiguous': base.replace(b'rejected-local-busy-before-native-v1', b'wrong-marker'),
    'missing_marker_must_remain_ambiguous': base.replace(m.MARKER, b''),
    'timeout_must_remain_ambiguous': TimeoutError('offline synthetic timeout'),
    'duplicate_date_must_remain_ambiguous': base.replace(b'Content-Length:', b'Date: first\r\nDate: second\r\nContent-Length:'),
    'folded_marker_must_remain_ambiguous': base.replace(b'before-native-v1\r\n', b'before-native-v1\r\n continued\r\n'),
}
results = []
for name, wire in cases.items():
    got = fixture.exercise(wire)
    stops = [x for x in got['commands'] if x[:2] == ['systemctl', 'stop']]
    passed = (got['result']['request_may_be_active'] is True
              and got['result']['status'] != 'BUSY_NOT_SUBMITTED'
              and got['reader_row']['status'] == 'FAILED_QUARANTINE_NO_RETRY'
              and stops == [['systemctl', 'stop', 'production-fixture.service']]
              and len([x for x in got['requests'] if x[3] == '/v1/chat/completions']) == 1)
    results.append({'name': name, 'pass': passed, 'client_status': got['result']['status'],
                    'reader_status': got['reader_row']['status'],
                    'request_may_be_active': got['result']['request_may_be_active'],
                    'synthetic_owner_stop_count': len(stops),
                    'error_type': type(got['error']).__name__ if got['error'] else None})
print(json.dumps({'scope': 'offline actual run/reader/getresponse/settle; fake wire, no sockets or live services',
                  'results': results}, indent=2))
raise SystemExit(0 if all(x['pass'] for x in results) else 1)
