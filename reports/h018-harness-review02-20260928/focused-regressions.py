#!/usr/bin/env python3
"""Offline review probes only; no runtime calls or model qualification.

Run from repo root: python3 -B reports/h018-harness-review02-20260928/focused-regressions.py ../input/owner.py
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
from unittest.mock import patch

source = Path(sys.argv[1]).resolve()
raw = source.read_bytes()
pin = 'dbb54dd908a5f9d1e833d34f9cf5d72fce27583fea089c35071b46e0b91f4e05'
assert hashlib.sha256(raw).hexdigest() == pin
o = types.ModuleType('frozen_owner')
o.__file__ = str(source)
exec(compile(raw, str(source), 'exec'), o.__dict__)
m = {'memory': {'limit_bytes': 755914244096}}
host = dict(MemTotal=1000, MemAvailable=900, SwapTotal=100, SwapFree=100)
passed = []


def refused(call, code='native_memory_policy_changed'):
    try:
        call()
    except o.OwnerRefusal as exc:
        assert str(exc) == code
        return exc
    raise AssertionError('expected refusal')


with tempfile.TemporaryDirectory(prefix='h018-review02-') as td:
    parent = Path(td) / 'llmmimo.slice'
    parent.mkdir()
    unit = ('[Unit]\nDescription=MiMo dedicated zero-swap boundary\n'
            '[Slice]\nMemoryAccounting=yes\nMemoryMax=755914244096\nMemorySwapMax=0\n').encode()
    policy = {'memory.max': '755914244096', 'memory.swap.max': '0', 'memory.swap.current': '0'}
    for name, value in {**policy, 'cgroup.procs': ''}.items():
        (parent / name).write_text(value)
    native = {'pid': 123, 'container_id': 'a' * 64}
    child = parent / ('docker-' + native['container_id'] + '.scope')
    with patch.object(o, 'MEMORY_SLICE_PATH', parent), patch.object(o, 'protected', return_value=unit):
        assert o.memory_policy(m) == policy
        child.mkdir()
        assert o.memory_policy(m, native) == policy
        refused(lambda: o.memory_policy(m))
        foreign = parent / 'foreign.scope'
        foreign.mkdir()
        refused(lambda: o.memory_policy(m, native))
        foreign.rmdir()
        (parent / 'cgroup.procs').write_text('321\n')
        refused(lambda: o.memory_policy(m, native))
        (parent / 'cgroup.procs').write_text('')
        child.rmdir()
        refused(lambda: o.memory_policy(m, native))
        foreign.mkdir()
        refused(lambda: o.memory_policy(m, native))
        foreign.rmdir()
        child.mkdir()
        passed.append('parent topology: empty pre-create / sole exact child accepted; extra, foreign, missing child and direct parent process refused')
        for name, value in {'memory.current': '790', 'memory.max': '755914244096',
                            'memory.swap.current': '0', 'memory.swap.max': 'max',
                            'memory.events': 'oom 0\noom_kill 0\noom_group_kill 0\n'}.items():
            (child / name).write_text(value)
        with patch.object(o, 'run', return_value=o.GPU + ', 100, 7, 69'), patch.object(o, 'memory', return_value=host):
            with patch.object(o, 'cgpath', return_value=child):
                assert o.sample_guard(m, host, 85, native)['cgroup']['memory.swap.max'] == 'max'
            with patch.object(o, 'cgpath', return_value=Path(td) / child.name), patch.object(o, 'memory_policy') as checker:
                refused(lambda: o.sample_guard(m, host, 85, native))
                checker.assert_not_called()
            passed.append('sample_guard accepts literal max only through exact proven parent; wrong native ancestry refused before policy sampling')
            with patch.object(o, 'cgpath', return_value=child):
                for value, expected in [('max', {'class': 'max', 'raw': 'max'}),
                                        ('PRIVATE_INVALID', {'class': 'invalid'})]:
                    (parent / 'memory.swap.max').write_text(value)
                    exc = refused(lambda: o.sample_guard(m, host, 85, native))
                    receipt = o.failure(exc, 'RUNNING', 'cgroup_memory')
                    assert receipt['resource_memory']['memory_policy']['memory.swap.max'] == expected
                    assert 'PRIVATE_INVALID' not in json.dumps(receipt)
                (parent / 'memory.swap.max').write_text('0')
            passed.append('parent refusal evidence survives sample_guard before resource_validate catch; arbitrary invalid text omitted')

required = {str(o.BASE / 'source' / n) for n in ('owner.py', 'private_proxy.py', 'launch.json')}
required |= {'/usr/local/lib/llm-server/node-api/scripts/control/' + n
             for n in ('node.py', 'node_observation.py', 'node_collectors.py', 'passive.py')}
units = {str(o.MEMORY_SLICE_UNIT), '/etc/systemd/system/' + o.UNIT}
with patch.object(o, 'validate_manifest'):
    for omitted in units:
        manifest = {'source_sha256': dict.fromkeys(required | (units - {omitted}), '0' * 64)}
        refused(lambda: o.source_preflight(None, manifest), 'deployed_source_closure_required')
passed.append('source_preflight refuses omission of either slice or owner service pin before storage/runtime work')
print(json.dumps({'status': 'PASS', 'owner_sha256': pin, 'focused_groups': len(passed),
                  'checks': passed, 'live_operations': False, 'w1_suites_rerun': False}, indent=2))
