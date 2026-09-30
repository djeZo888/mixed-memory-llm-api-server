#!/usr/bin/env python3
"""H036 reviewed stopped-owner install only. Never stops, starts, or retries.

Invoke only after root GO and one clean old-owner settlement. A partial install
leaves an exclusive attempt marker and requires review, never automatic replay.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path


def install(o, pins, candidate, expected_state_sha, expected_intent_sha):
    sha = lambda raw: hashlib.sha256(raw).hexdigest()
    o.require(all(isinstance(v, str) and o.HEX.fullmatch(v) for v in
                  (expected_state_sha, expected_intent_sha)), 'source_successor_invalid')
    candidate_raw = o.protected(candidate)
    o.require(sha(candidate_raw) == pins['ownerNewSha256'], 'source_successor_invalid')
    h = o.setup()
    with h.acquire_lease(blocking=False) as lease, h.MountedStorageGuard(h.s) as guard:
        o.storage_paths(h, guard)
        h.s.root_payload_guard()
        files = {n:o.protected(o.BASE/n).decode() for n in ('manifest.json', 'state.json',
            'selection.json', 'guard.json', 'proxy-state.json', 'source/owner.py',
            o.CONTEXT_DELTA, o.CONTEXT_MANIFEST)}
        old, state = json.loads(files['manifest.json']), json.loads(files['state.json'])
        boot = pins['bootId']
        o.require(o.BOOT.read_text().strip() == boot == state['boot_id']
                  and state['launch_id'] == pins['priorLaunchId']
                  and sha(files['manifest.json'].encode()) == pins['manifestOldRawSha256']
                  and o.digest(old) == pins['manifestOldSha256']
                  and sha(files['source/owner.py'].encode()) == pins['ownerOldSha256']
                  and sha(files['selection.json'].encode()) == pins['selectionOldRawSha256']
                  and sha(files['state.json'].encode()) == expected_state_sha
                  and sha(files[o.CONTEXT_DELTA].encode()) == pins['deltaRawSha256'],
                  'source_successor_invalid')
        intent_name = o.transition_stop_name(state, True)
        files[intent_name] = o.protected(o.BASE/intent_name).decode()
        o.require(sha(files[intent_name].encode()) == expected_intent_sha, 'source_successor_invalid')
        prepared = json.loads(files[intent_name])['files']
        for name in ('manifest.json','selection.json','source/owner.py',o.CONTEXT_DELTA,o.CONTEXT_MANIFEST):
            o.require(files[name] == prepared[name], 'source_successor_invalid')
        new = json.loads(files[o.CONTEXT_MANIFEST])
        o.require(o.digest(new) == pins['manifestNewSha256']
                  and new['source_sha256'][str(o.BASE/'source/owner.py')] == pins['ownerNewSha256'],
                  'source_successor_invalid')
        o.source_preflight(h, old)
        o.require_selected(old, state['selection'])
        o.assert_launch_admission(old, state['selection'], state)
        o.reviewed_context_reduction(old, new, json.loads(files[o.CONTEXT_DELTA]), preparing=True)
        o.intentional_source_stop(old, state, boot, files, pins['deltaRawSha256'], context_reduction=True)
        physical = o.settled_source_absence(old, state, boot, same_boot=True)
        hardware = o.source_hardware(h, boot, lease)
        o.require(all(o.protected(o.BASE/n).decode() == raw for n,raw in files.items())
                  and o.protected(candidate) == candidate_raw
                  and o.BOOT.read_text().strip() == boot, 'source_successor_invalid')
        lease.validate()
        marker = intent_name.replace('context-reduction-stop-', 'context-reduction-install-')
        o.exclusive_recovery_write(h, guard, marker, {'schema_version':1,
            'status':'CONTEXT_REDUCTION_INSTALL_ATTEMPT', 'files':files,
            'expected_state_sha256':expected_state_sha, 'expected_intent_sha256':expected_intent_sha,
            'pins':pins, 'physical_absence':physical, 'hardware_proof':hardware})
        # Exact old bytes are durable above before either installed file changes.
        # O_EXCL marker means a crash at ANY following point cannot be replayed.
        with h.AnchoredRoot(str(o.BASE), guard) as root:
            temporary = 'source/context-reduction-owner-' + state['launch_id'] + '.py'
            with root.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) as stream:
                stream.write(candidate_raw)
                stream.fsync()
            root.replace(temporary, 'source/owner.py')
        o.write(h, 'manifest.json', new)
        o.require(sha(o.protected(o.BASE/'source/owner.py')) == pins['ownerNewSha256']
                  and o.read(o.BASE/'manifest.json') == new
                  and o.protected(o.BASE/'state.json').decode() == files['state.json']
                  and o.protected(o.BASE/'selection.json').decode() == files['selection.json'],
                  'source_successor_invalid')
        lease.validate()
        return {'status':'CONTEXT_REDUCTION_INSTALLED_NOT_RECONCILED', 'attempt':marker,
                'manifest_sha256':o.digest(new), 'state_sha256':expected_state_sha}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate-owner', required=True)
    p.add_argument('--pins', required=True)
    p.add_argument('--expected-settled-state-sha256', required=True)
    p.add_argument('--expected-intent-sha256', required=True)
    a=p.parse_args()
    candidate=Path(a.candidate_owner)
    pins=json.loads(Path(a.pins).read_bytes())
    assert hashlib.sha256(candidate.read_bytes()).hexdigest() == pins['ownerNewSha256']
    spec=importlib.util.spec_from_file_location('h036_reviewed_owner',candidate)
    o=importlib.util.module_from_spec(spec);spec.loader.exec_module(o)
    print(json.dumps(install(o,pins,candidate,a.expected_settled_state_sha256,a.expected_intent_sha256)))


if __name__ == '__main__':
    main()
