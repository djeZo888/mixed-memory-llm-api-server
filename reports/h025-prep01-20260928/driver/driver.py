#!/usr/bin/env python3
"""H025 local contract validation only. Fixed W1-only adapter; default is local validation and no dispatch."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parent))
from contract import Refusal, digest, validate_manifest, validate_go

SOURCE_FILES = ('contract.py', 'primitives.py', 'telemetry.py', 'controller.py', 'runner.py', 'native.py', 'fans.py', 'fan_status.py', 'bridge.py', 'driver.py')

def package():
    here = Path(__file__).resolve().parent
    files = {name: hashlib.sha256((here/name).read_bytes()).hexdigest() for name in SOURCE_FILES}
    return {'files': files, 'package_sha256': digest(files)}

def failure_receipt(exc, phase=None, run_entered=False):
    # The exact journal path and owned receipts survive a top-level exception.
    # Never turn a submitted/uncertain request into a no-dispatch replay permit.
    submitted = phase is not None and any(phase.requests.values())
    return {'status': 'POSSIBLY_SUBMITTED_UNKNOWN_OWNED' if submitted or run_entered else 'REFUSED_NO_DISPATCH',
            'reason_type': type(exc).__name__, 'automatic_retry': False,
            'journal': str(phase.journal.path) if phase else None,
            'active': {l:{k:r[k] for k in ('request_id','state')} for l,r in phase.active.items()} if phase else {},
            'request_counts': {l:len(rows) for l,rows in phase.requests.items()} if phase else {},
            'first_failure': phase.first_failure if phase else None,
            'stop_intents': phase.stop_intents if phase else {},
            'reason': str(exc) if isinstance(exc, Refusal) else 'top-level execution failure; inspect exact owned receipts'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--go', type=Path)
    parser.add_argument('--phase', choices=('B',))
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--journal',type=Path)
    args = parser.parse_args()
    result = {'status': 'NO_DISPATCH', **package(), 'live': 'NOT_TESTED_REQUIRES_W1_CURRENT_VALUES_AND_ROOT_REVIEW'}
    if args.manifest:
        m = json.loads(args.manifest.read_text())
        validate_manifest(m)
        result.update(manifest='VALID_SHAPE_NOT_LIVE_PROOF', deployment_sha256=digest(m))
        if args.go:
            validate_go(json.loads(args.go.read_text()), m, args.phase, result['package_sha256'], datetime.now(timezone.utc).isoformat())
            result['go'] = 'VALID_SHAPE_NOT_CONSUMED_NO_DISPATCH'
    elif args.go:
        raise Refusal('manifest required with GO')
    if args.run:
        if not (args.manifest and args.go and args.phase and args.journal):raise Refusal('exact manifest GO phase deadline and journal required')
        from native import NativeAdapter,clock,protected
        from controller import Phase
        from runner import Runner
        m=json.loads(protected(args.manifest));g=json.loads(protected(args.go))
        validate_go(g,m,args.phase,result['package_sha256'],clock()['utc'])
        adapter=NativeAdapter(m,g,args.journal)
        phase=None;entered=False
        try:
            phase=Phase(m,g,args.phase,result['package_sha256'],args.journal,clock,
                        storage_guard=adapter.guard,anchored_root=adapter.root_cls)
            adapter.journal=phase.journal
            entered=True
            result=Runner(phase,adapter).run()
        except Exception as exc:
            result=failure_receipt(exc,phase,entered)
            if phase:
                try:phase.journal.write('TOP-ERROR',result)
                except Exception:result['error_receipt_persistence']='FAILED_RETAIN_ORIGINAL_JOURNAL'
        finally:
            for close in (adapter.fans.close,adapter.guard.close):
                try:close()
                except Exception as exc:
                    result=failure_receipt(exc,phase,entered)
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    try:
        main()
    except (Refusal, KeyError, TypeError, ValueError, OSError) as exc:
        print(json.dumps(failure_receipt(exc)))
        sys.exit(2)
