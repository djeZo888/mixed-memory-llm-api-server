#!/usr/bin/env python3
"""Dedicated ordinary32B creation control; never rotates/adopts native evidence.

UNEXECUTED operational helper. A separate fresh root GO, exact inventory,
current application and all three model owners, protected ancestor/inode joins,
and an absent target are mandatory. Existing keys are never overwritten. The
only entropy call occurs after the durable once-only claim in execute(). No key
bytes or derived key digest enter receipts, exceptions, stdout or stderr.
"""
import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

from key_inventory import (SOURCE_PATHS, InventoryError, absolute, ancestry, bounded_read,
                           canonical, file_metadata, identity, need,
                           observe_process, observe_remote_owners)

FIELDS = {'schema', 'status', 'approvedBy', 'authority', 'goId', 'issuedUtc',
          'notBeforeUtc', 'dispatchCutoffUtc', 'expiresUtc', 'invocations',
          'retries', 'counts', 'sourceCommit', 'helper', 'helperFiles',
          'sourceFiles', 'keyInventory', 'application', 'generalOwners', 'remoteOwnerObservation',
          'protectedFiles', 'ordinaryAbsenceReview', 'target', 'claim'}
SCHEMA = 'h046-ordinary-key-create-go-v1'


def strict_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            need(key not in value, 'duplicate JSON key')
            value[key] = item
        return value
    return json.loads(raw.decode('utf-8', errors='strict'), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(InventoryError('nonfinite JSON')))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def timestamp(value):
    need(isinstance(value, str), 'GO time must be UTC text')
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    need(parsed.utcoffset() == dt.timedelta(0), 'GO time must use UTC')
    return parsed.timestamp()


def private(path, uid, exact_size=None, cap=1048576):
    p = absolute(str(path)); ancestry(p.parent, (0, uid))
    parent = identity(p.parent)
    need(parent['uid'] == uid and parent['mode'] == 0o700, 'private input requires exact owned private700 parent')
    before = identity(p)
    need(before['uid'] == uid and before['mode'] == 0o600 and before['nlink'] == 1,
         'root GO/key/inventory requires private600 owner and single inode')
    raw = bounded_read(p, cap)
    need(identity(p) == before and (exact_size is None or len(raw) == exact_size),
         'private input size/inode changed')
    return raw


def reference(ref):
    need(isinstance(ref, dict) and set(ref) == {'path', 'sha256', 'uid', 'identity'},
         'exact file reference fields required')
    need(type(ref['uid']) is int and ref['uid'] >= 0 and
         re.fullmatch('[a-f0-9]{64}', ref['sha256'] or '') is not None,
         'invalid file owner/digest')
    p = absolute(ref['path']); ancestry(p.parent, (0, ref['uid']))
    need(identity(p) == ref['identity'] and ref['identity']['uid'] == ref['uid'] and
         not ref['identity']['mode'] & 0o022, 'source/config/inventory identity mismatch')
    raw = bounded_read(p)
    need(digest(raw) == ref['sha256'] and identity(p) == ref['identity'],
         'source/config/inventory bytes changed')
    return raw


def validate_go(envelope, key, now, helper_path, helper_sha):
    need(isinstance(envelope, dict) and set(envelope) == {'body', 'seal'} and
         isinstance(envelope['seal'], str) and
         re.fullmatch('[a-f0-9]{64}', envelope['seal']) is not None,
         'exact HMAC envelope required')
    need(len(key) == 32 and hmac.compare_digest(envelope['seal'],
         hmac.new(key, canonical(envelope['body']), hashlib.sha256).hexdigest()),
         'root32B HMAC mismatch')
    return validate_body(envelope['body'], now, helper_path, helper_sha)


def validate_body(b, now, helper_path, helper_sha):
    need(isinstance(b, dict) and set(b) == FIELDS and b['schema'] == SCHEMA and
         b['status'] == 'APPROVED' and b['approvedBy'] == 'root' and b['authority'] == 'H046',
         'fresh exact H046 ordinary-key GO required')
    need(isinstance(b['goId'], str) and re.fullmatch('[a-f0-9]{64}', b['goId']), 'fresh GO ID required')
    issued, start, cutoff, expiry = [timestamp(b[k]) for k in
        ('issuedUtc', 'notBeforeUtc', 'dispatchCutoffUtc', 'expiresUtc')]
    need(issued <= start <= now < cutoff <= expiry - 45 and 60 <= expiry - issued <= 600,
         'GO stale/future/expired or cleanup reserve missing')
    need(expiry <= timestamp('2026-10-02T16:59:03+00:00'), 'GO exceeds H046 closure reserve')
    need(type(b['invocations']) is int and b['invocations'] == 1 and
         type(b['retries']) is int and b['retries'] == 0 and
         b['counts'] == {'createOrdinaryKey': 1, 'overwrite': 0, 'rotate': 0} and
         all(type(v) is int for v in b['counts'].values()), 'finite one-shot counts required')
    need(isinstance(b['sourceCommit'], str) and re.fullmatch('[a-f0-9]{40}', b['sourceCommit']),
         'sealed source commit missing')
    need(b['helper']['path'] == str(helper_path) and b['helper']['sha256'] == helper_sha and
         b['helper']['uid'] == 0, 'executed root helper mismatch')
    need(set(b['generalOwners']) == {'qwen1', 'qwen2', 'mimo'}, 'all three current general owners required')
    need(set(b['application']) == {'unit', 'unitFile', 'unitSha256', 'owner'} and
         b['application']['unit'] == 'ai-harness.service' and
         b['application']['unitFile'] == '/home/user/.config/systemd/user/ai-harness.service',
         'exact current ordinary service unit required')
    need(set(b['target']) == {'path', 'parentIdentity', 'uid', 'gid'} and
         b['target']['uid'] == b['application']['owner']['uid'] and
         b['target']['gid'] == b['application']['owner']['gid'] and b['target']['uid'] == b['target']['gid'] == 1000,
         'ordinary service target owner required')
    need(set(b['claim']) == {'path', 'parentIdentity'} and
         Path(b['claim']['path']).name == b['goId'] + '.ordinary-key-create.claim.json',
         'exact one-shot claim filename required')
    need(set(b['ordinaryAbsenceReview']) == {'reviewedBy', 'status', 'recognizedPaths'} and
         b['ordinaryAbsenceReview']['reviewedBy'] == 'root' and
         b['ordinaryAbsenceReview']['status'] == 'WHOLLY_ABSENT_AT_EXACT_PATHS' and
         isinstance(b['ordinaryAbsenceReview']['recognizedPaths'], list) and
         len(b['ordinaryAbsenceReview']['recognizedPaths']) <= 32,
         'root exact recognized-path absence review required')
    return b


def observe_owner(expected):
    need(isinstance(expected, dict), 'current exact owner object required')
    observed = observe_process(expected['pid'])
    # No caller JSON can attest a current owner: compare every supplied field to
    # a fresh kernel observation. Carrier metadata may use cgroupPath spelling.
    joined = dict(observed)
    joined['cgroupPath'] = observed['cgroup'].removeprefix('0::')
    need(set(expected) <= set(joined) and
         {'bootId', 'uid', 'pid', 'startTicks', 'pgid', 'cgroupPath'} <= set(expected) and
         all(joined[k] == v for k, v in expected.items()), 'fresh current owner changed')
    return observed


def check_parent(path, expected, owner):
    p = absolute(str(path)); ancestry(p.parent, (0, owner))
    observed = identity(p.parent)
    need(observed == expected and observed['uid'] == owner and observed['mode'] == 0o700,
         'protected700 parent/inode changed')
    return p


def write_exclusive(path, parent_identity, raw, uid, gid):
    """Small primitive; CLI only reaches it after full GO/source/current checks."""
    p = Path(path)
    directory = os.open(p.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        ds = os.fstat(directory)
        need((ds.st_dev, ds.st_ino) == (parent_identity['dev'], parent_identity['ino']) and
             stat.S_IMODE(ds.st_mode) == 0o700, 'opened parent inode changed')
        fd = os.open(p.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        try:
            os.fchmod(fd, 0o600)
            if os.geteuid() == 0:
                os.fchown(fd, uid, gid)
            else:
                need((os.fstat(fd).st_uid, os.fstat(fd).st_gid) == (uid, gid),
                     'fixture primitive cannot change owners')
            offset = 0
            while offset < len(raw):
                written = os.write(fd, raw[offset:]); need(written > 0, 'private write failed')
                offset += written
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(directory)
        need((p.parent.lstat().st_dev, p.parent.lstat().st_ino) == (ds.st_dev, ds.st_ino),
             'parent moved during private write')
    finally:
        os.close(directory)


def execute(body, now=None):
    need(os.geteuid() == 0 and sys.platform == 'linux', 'ordinary creation requires root on actual Linux')
    now = time.time() if now is None else now
    need(now < timestamp(body['dispatchCutoffUtc']), 'key creation dispatch cutoff passed')
    helper = absolute(__file__)
    need(set(x['path'] for x in body['helperFiles']) ==
         {str(helper), str(helper.with_name('key_inventory.py'))}, 'complete key-helper import closure required')
    need(body['helper'] in body['helperFiles'], 'executed helper absent from exact import closure')
    for ref in body['helperFiles'] + body['sourceFiles']:
        reference(ref)
    packet_raw = private(body['keyInventory']['path'], 0)
    need(digest(packet_raw) == body['keyInventory']['sha256'] and
         identity(body['keyInventory']['path']) == body['keyInventory']['identity'],
         'exact inventory original changed')
    packet = strict_json(packet_raw)
    need(packet['schema'] == 'h046-exact-key-inventory-v1' and packet['keyBytesRead'] is False,
         'required precise metadata inventory missing')
    expected_sources = {str(absolute(packet['sourceRoot']) / p): packet['sourceFiles'][p]
                        for p in SOURCE_PATHS}
    need(len(body['sourceFiles']) == len(expected_sources) and
         {x['path']: x['sha256'] for x in body['sourceFiles']} == expected_sources and
         digest(canonical(packet['sourceFiles'])) == packet['sourceGraphSha256'],
         'exact app/launcher/receipt source inventory joins changed')
    need(packet['unit']['path'] == body['application']['unitFile'] and
         packet['unit']['sha256'] == body['application']['unitSha256'] and
         identity(body['application']['unitFile']) == packet['unit']['identity'] and
         digest(reference({'path': packet['unit']['path'], 'sha256': packet['unit']['sha256'],
                           'uid': packet['unit']['identity']['uid'], 'identity': packet['unit']['identity']}))
           == body['application']['unitSha256'],
         'current service unit changed')
    owner = observe_owner(body['application']['owner'])
    need(owner['bootId'] == packet['owner']['bootId'] and owner == packet['owner'],
         'current owner differs from original inventory')
    policy = body['remoteOwnerObservation']
    need(policy['purpose'] == 'ordinary-key-create' and policy['sourceCommit'] == body['sourceCommit'] and
         policy['bindingId'] == body['goId'] and policy['afterAnchor'] == body['target']['path'],
         'remote root original policy differs from key creation GO')
    observe_remote_owners(body['generalOwners'], policy, 'before')
    protected = body['protectedFiles']
    need(isinstance(protected, list) and all(set(x) == {'path', 'identity'} for x in protected),
         'exact original protected-file inode packet required')
    for ref in protected:
        need(identity(absolute(ref['path'])) == ref['identity'], 'original protected file inode changed')
    native = packet['nativeEvidenceKey']
    need(native['state'] in ('PRESENT', 'ABSENT') and
         file_metadata(native['path'], owner['uid']) == native,
         'native evidence exact metadata changed')
    if native['state'] == 'PRESENT':
        need(native['protected32B'] is True and
             any(x['path'] == native['path'] and x['identity'] == native['identity'] for x in protected),
             'native evidence inode absent from protected originals')
    target = body['target']; target_path = check_parent(target['path'], target['parentIdentity'], target['uid'])
    forbidden = {x['path'] for x in protected} | set(packet['protectedCredentialPaths']) | {native['path']}
    need(str(target_path) not in forbidden, 'ordinary target aliases existing protected secret')
    paths = body['ordinaryAbsenceReview']['recognizedPaths']
    need(len(paths) == len(set(paths)) and str(target_path) in paths and
         {x['path'] for x in packet['ordinaryApprovalKeys']} <= set(paths),
         'target/current recognized ordinary paths omitted from root absence review')
    for p in paths:
        need(file_metadata(p, target['uid'])['state'] == 'ABSENT',
             'existing recognized ordinary key must be adopted; generation denied')
    claim = check_parent(body['claim']['path'], body['claim']['parentIdentity'], 0)
    need(str(claim) != str(target_path) and not claim.exists(), 'spent GO claim denied')
    need(time.time() < timestamp(body['dispatchCutoffUtc']), 'dispatch elapsed during review')
    # Claim is durable and remains spent even on failed entropy/write/teardown.
    write_exclusive(claim, body['claim']['parentIdentity'], canonical({
        'schema': 'h046-ordinary-key-once-claim-v1', 'goId': body['goId'],
        'sourceCommit': body['sourceCommit'], 'targetPath': str(target_path),
        'claimedAtUtc': dt.datetime.now(dt.timezone.utc).isoformat()}), 0, 0)
    need(time.time() < timestamp(body['dispatchCutoffUtc']), 'dispatch elapsed after once-only claim')
    observe_owner(body['application']['owner'])
    observe_remote_owners(body['generalOwners'], policy, 'before')
    for ref in body['helperFiles'] + body['sourceFiles']:
        reference(ref)
    need(identity(body['application']['unitFile']) == packet['unit']['identity'],
         'unit inode changed after once-only claim')
    for p in paths:
        need(file_metadata(p, target['uid'])['state'] == 'ABSENT',
             'recognized ordinary key appeared after once-only claim')
    need(file_metadata(native['path'], owner['uid']) == native,
         'native evidence presence/inode changed before creation')
    # No ambient key, rotation, duplicate generation or public key hash export.
    write_exclusive(target_path, target['parentIdentity'], os.urandom(32), target['uid'], target['gid'])
    created = file_metadata(target_path, target['uid'])
    need(created.get('protected32B') is True, 'new ordinary key private metadata failed')
    need(file_metadata(native['path'], owner['uid']) == native,
         'native evidence presence/inode changed after creation')
    for ref in protected:
        need(identity(ref['path']) == ref['identity'], 'protected original changed during creation')
    observe_owner(body['application']['owner'])
    observe_remote_owners(body['generalOwners'], policy, 'after')
    return {'schema': 'h046-ordinary-key-create-receipt-v1', 'status': 'CREATED',
            'goId': body['goId'], 'sourceCommit': body['sourceCommit'],
            'ordinaryKey': created, 'nativeEvidenceKey': native,
            'oneShotClaim': str(claim), 'keyBytesExported': False, 'keyShaExported': False,
            'nativeAcceptance': 'NOT_TESTED', 'nativeStarts': 0, 'providerDispatches': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--go', help='HMAC envelope using a genuinely existing independent root32B key')
    mode.add_argument('--root-private-go', help='Dedicated raw root-private finite creation GO; no auth key generated')
    parser.add_argument('--go-key')
    parser.add_argument('--trusted-go-key-sha256')
    parser.add_argument('--trusted-go-sha256')
    args = parser.parse_args()
    need(os.geteuid() == 0 and sys.platform == 'linux', 'root actual Linux required; no source-only approval')
    helper = absolute(__file__); helper_raw = bounded_read(helper)
    if args.root_private_go:
        need(args.go_key is None and args.trusted_go_key_sha256 is None and
             isinstance(args.trusted_go_sha256, str) and
             re.fullmatch('[a-f0-9]{64}', args.trusted_go_sha256),
             'raw root-private mode requires only independently pinned exact GO SHA256')
        go_path = absolute(args.root_private_go)
        ancestry(go_path.parent, (0,))
        need(identity(go_path.parent)['uid'] == 0 and identity(go_path.parent)['mode'] == 0o700,
             'root-private GO requires root-owned private700 parent')
        go_before = identity(go_path)
        raw = private(go_path, 0)
        need(digest(raw) == args.trusted_go_sha256 and identity(go_path) == go_before,
             'out-of-band exact root-private GO bytes/inode changed')
        body = validate_body(strict_json(raw), time.time(), helper, digest(helper_raw))
        # Bind the original GO inode in the trusted invocation, rather than
        # embedding its own mtime/size inside itself (a circular byte binding).
        need(str(go_path) != body['target']['path'], 'GO cannot be an ordinary key target')
        authorization = {'mechanism': 'ROOT_PRIVATE_FILE_EFFECTIVE_UID0_AND_OUT_OF_BAND_GO_SHA256',
                         'goPath': str(go_path), 'goSha256': digest(raw), 'goIdentity': go_before,
                         'hmacKeyGenerated': False}
    else:
        need(args.go_key and args.trusted_go_sha256 is None and
             isinstance(args.trusted_go_key_sha256, str) and
             re.fullmatch('[a-f0-9]{64}', args.trusted_go_key_sha256),
             'HMAC mode requires independent existing32B key SHA256 anchor')
        key_before = identity(absolute(args.go_key))
        key = private(args.go_key, 0, 32, 32)
        need(digest(key) == args.trusted_go_key_sha256 and identity(args.go_key) == key_before,
             'independent existing GO key anchor/inode mismatch')
        body = validate_go(strict_json(private(args.go, 0)), key, time.time(), helper, digest(helper_raw))
        need(args.go_key != body['target']['path'] and
             any(x['path'] == args.go_key and x['identity'] == key_before for x in body['protectedFiles']),
             'existing independent root GO key inode must be bound/preserved')
        authorization = {'mechanism': 'EXISTING_ROOT32B_HMAC_WITH_OUT_OF_BAND_KEY_ANCHOR',
                         'goPath': args.go, 'goKeyIdentity': key_before, 'hmacKeyGenerated': False}
    result = execute(body)
    if args.root_private_go:
        need(identity(go_path) == go_before, 'original root-private GO inode changed during creation')
    result['authorization'] = authorization
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Exceptions describe guard seams/path metadata, never secret bytes.
        print(json.dumps({'status': 'DENIED_OR_FAILED', 'reason': str(error),
                          'keyBytesExported': False}), file=sys.stderr)
        raise SystemExit(1)
