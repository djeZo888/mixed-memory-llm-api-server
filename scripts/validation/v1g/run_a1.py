#!/usr/bin/env python3
"""Run the unchanged A1 CLI once with private evidence and an external failure guard.

Verification: python3 -B scripts/validation/v1g/run_a1.py --help
Source pin and all requested limits are checked before live requests. The trace
observer only saves completed probe evidence and halts on FAIL; it never edits
requests, responses, fixtures, acceptance criteria, or successful outcomes.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import sys
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--private-dir', type=Path, required=True)
    p.add_argument('--base-url', required=True)
    p.add_argument('--mode', choices=['nonstream', 'stream-tools'], required=True)
    p.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = p.parse_args()
    os.umask(0o077)
    repo = Path(__file__).resolve().parents[3]
    private = args.private_dir.resolve(strict=True)
    if private.is_relative_to(repo) or private.stat().st_mode & 0o077:
        p.error('private directory must be outside checkout with mode 0700')
    mode = private / args.mode
    report = mode / 'report.json'
    command = [sys.executable, '-B', str(repo / 'scripts/agent/acceptance.py'),
               '--base-url', args.base_url, '--model', 'glm-5.3',
               '--api-key-file', str(private / 'llm-api-key'), '--auth', 'enabled',
               '--reasoning-effort', 'low', '--request-timeout', '300',
               '--overall-timeout', '1800', '--max-tokens', '2048',
               '--max-rounds', '12', '--max-tool-calls', '32',
               '--test-timeout', '10', '--workspace-parent', str(mode),
               '--report', str(report)]
    if args.mode == 'stream-tools':
        command.append('--stream-tools')
    if args.child:
        import hashlib
        acceptance = repo / 'scripts/agent/acceptance.py'
        source_hash = hashlib.sha256(acceptance.read_bytes()).hexdigest()
        expected = json.loads((mode / 'execution.json').read_text())['acceptance_sha256']
        if source_hash != expected:
            raise SystemExit('A1 source changed before execution')
        sys.path.insert(0, str(acceptance.parent))
        import protocol
        import acceptance as module
        started = time.monotonic()
        def observe(frame, event, arg):
            if event == 'return' and frame.f_code.co_filename == str(acceptance) and frame.f_code.co_name == 'check':
                current = frame.f_locals['report']
                client = frame.f_locals['client']
                name = frame.f_locals['name']
                snapshot = dict(current, requests=client.requests,
                                elapsed_seconds=round(time.monotonic() - started, 6))
                safe = module.redact_report(snapshot, client.api_key)
                (mode / 'partial-report.json').write_text(json.dumps(safe, indent=2) + '\n')
                if current['checks'][name]['status'] == 'FAIL':
                    safe['status'] = 'FAIL'
                    safe['v1g_external_stop_guard'] = {'failed_check': name, 'dependent_requests_stopped': True}
                    report.write_text(json.dumps(safe, indent=2) + '\n')
                    raise SystemExit(1)
            return observe
        sys.argv = command[2:]
        sys.settrace(observe)
        try:
            runpy.run_path(str(acceptance), run_name='__main__')
        finally:
            sys.settrace(None)
        return 0
    import hashlib
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    if head != '66ef3d45f2225b3187e3d246637f6aaa3cf32514':
        p.error('A1 initial run requires exact reviewed A2A commit')
    mode.mkdir(mode=0o700)
    metadata = {'source_commit': head, 'command': command,
                'acceptance_sha256': hashlib.sha256((repo/'scripts/agent/acceptance.py').read_bytes()).hexdigest(),
                'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'external_timeout_seconds': 1800, 'mode': args.mode}
    (mode / 'execution.json').write_text(json.dumps(metadata, indent=2) + '\n')
    child = [sys.executable, '-B', str(Path(__file__).resolve()), '--child',
             '--private-dir', str(private), '--base-url', args.base_url, '--mode', args.mode]
    started = time.monotonic()
    with (mode/'stdout.log').open('xb') as out, (mode/'stderr.log').open('xb') as err:
        proc = subprocess.Popen(child, stdout=out, stderr=err, start_new_session=True)
        metadata['pid'] = proc.pid
        (mode/'execution.json').write_text(json.dumps(metadata, indent=2)+'\n')
        timed_out = False
        try:
            rc = proc.wait(timeout=1800)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)
            rc = 124
        finally:
            # The group belongs solely to this run. Remove any surviving child.
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    metadata.update(exit_code=rc, timed_out=timed_out,
                    elapsed_seconds=round(time.monotonic()-started,6),
                    ended_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    (mode/'execution.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps({k:metadata[k] for k in ['mode','exit_code','timed_out','elapsed_seconds']}))
    return rc

if __name__ == '__main__':
    raise SystemExit(main())
