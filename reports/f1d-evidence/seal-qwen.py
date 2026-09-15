#!/usr/bin/env python3
"""Seal only completed F1A Qwen payloads using M1 stat-anchored hash evidence.

Run as root on ai-vm, after separately provisioning protected acquisition ancestry.
--dry-run writes storage-guard reports only; it does not change ownership/modes or
publish backup, seal evidence, or completion. All output directories must exist.
No full weight reread, model/service launch, downloads, key access, or source edits.
"""
import argparse
import base64
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys

TASK = Path('/data/build/f1d-qwen-20260915')
MODEL = Path('/data/models-large/qwen3-coder-next-fp8')
GLM = Path('/data/models-large/glm-5.3-ud-q4-k-xl')
ACQ = Path('/data/services/llm-manager/acquisition')
STATUS = Path('/data/build/f1a-qwen-20260915/evidence/acquisition-status.json')
MANIFEST = Path('/data/build/f1a-qwen-20260915/metadata/f1a-qwen-manifest.json')
PROOF = TASK / 'inputs/qwen-completion-proof.json'
BACKUP = TASK / 'backups/qwen-metadata-pre.json'
SEAL = ACQ / 'f1d-qwen-seal-evidence.json'
COMPLETE = ACQ / 'qwen3-coder-next-fp8.complete.json'
LOCK = MODEL / '.f1a-acquisition.lock'
REV = 'da6e2ed27304dd39abadd9c82ef50e8de67bdd4c'
PINS = {
    'manifest': '022674d4daf63fa57c2798a30fea80c6dde7b1b2e73630ae3c3aa94e45debb9e',
    'status': '37cec46972a9073aea39d225c4275236231791294ebc4f81f79cab191f6b310c',
    'proof': '904580fe0b70e22f96a1732695e8bc2024383e7e1180d3f9b464ad8d15fd07aa',
    'scripts/f1a/acquire.py': 'b2a19c96034c1bc48bad39c516b67365af885a701532670a72f310fb18a505bb',
    'scripts/d1/acquire.py': '950334895648a53db8ffef32171f2e97a64bdf6b0c07eed56424a4649a76fcf4',
    'scripts/common/require-data-mounted.sh': '5bd86b1e3f84fe5ca76922ca896289edb723b09bc03b99044b7d1ec320215c4f',
    'scripts/common/root-disk-guard.sh': '9945b21e13568caa77e1e19d56ac05f30adc692d40a94a6c1dbe1b23ed4e7eb2',
}
WEIGHTS = {f'model-{i:05d}-of-00040.safetensors' for i in range(1, 41)}
SMALL = {'model.safetensors.index.json', 'chat_template.jinja', 'config.json',
         'generation_config.json', 'merges.txt', 'tokenizer.json', 'tokenizer_config.json', 'vocab.json'}
IDENTITY = ('device', 'inode', 'mode', 'nlink', 'uid', 'gid', 'size_bytes',
            'mtime_ns', 'ctime_ns', 'regular', 'symlink')


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def metadata(st):
    return dict(device=st.st_dev, inode=st.st_ino, mode=oct(stat.S_IMODE(st.st_mode)),
                nlink=st.st_nlink, uid=st.st_uid, gid=st.st_gid, size_bytes=st.st_size,
                mtime_ns=st.st_mtime_ns, ctime_ns=st.st_ctime_ns,
                regular=stat.S_ISREG(st.st_mode), symlink=stat.S_ISLNK(st.st_mode))


def same(a, b, fields=IDENTITY):
    return all(a[k] == b[k] for k in fields)


def safe_path(path):
    require(path.is_absolute() and '..' not in path.parts, f'unsafe absolute path: {path}')
    for part in reversed((path, *path.parents)):
        st = part.lstat()
        require(not stat.S_ISLNK(st.st_mode), f'symlink refused: {part}')
        if part != path:
            require(stat.S_ISDIR(st.st_mode), f'non-directory ancestor: {part}')
    require(path.resolve(strict=True) == path, f'noncanonical path: {path}')


def protected_directory(path):
    safe_path(path)
    for part in (path, *path.parents):
        st = part.lstat()
        require(stat.S_ISDIR(st.st_mode) and st.st_uid == 0 and not st.st_mode & 0o022,
                f'protected acquisition ancestry not provisioned: {part}')


def open_regular(path):
    safe_path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        os.close(fd)
        raise RuntimeError(f'nonregular/multiply-linked file: {path}')
    if not same(metadata(st), metadata(path.lstat())):
        os.close(fd)
        raise RuntimeError(f'open race: {path}')
    return fd


def read_small(path, expected=None, limit=32 * 1024**2):
    fd = open_regular(path)
    try:
        before = metadata(os.fstat(fd))
        require(0 < before['size_bytes'] <= limit, f'small evidence size invalid: {path}')
        pieces, total = [], 0
        while True:
            block = os.read(fd, min(1024 * 1024, limit + 1 - total))
            if not block:
                break
            pieces.append(block)
            total += len(block)
            require(total <= limit, f'evidence grew: {path}')
        raw = b''.join(pieces)
        after = metadata(os.fstat(fd))
        require(same(before, after) and same(after, metadata(path.lstat()))
                and len(raw) == after['size_bytes'], f'evidence changed while read: {path}')
        digest = hashlib.sha256(raw).hexdigest()
        require(expected is None or digest == expected, f'content pin mismatch: {path}')
        return raw, dict(path=str(path), identity=after, sha256=digest)
    finally:
        os.close(fd)


def run(command, **kwargs):
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False, **kwargs)
    require(result.returncode == 0, f'command failed ({result.returncode}): {command[0]}')
    return result.stdout


def mounts():
    result = {}
    for path, uuid in [(Path('/data'), '8daf56f1-5649-4163-9d87-919c2d271875'),
                       (Path('/data/models-large'), 'a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a')]:
        safe_path(path)
        data = json.loads(run(['findmnt', '--json', '--target', str(path),
                              '--output', 'TARGET,SOURCE,UUID,FSTYPE,OPTIONS']))['filesystems']
        require(len(data) == 1 and data[0]['target'] == str(path)
                and data[0]['uuid'] == uuid and data[0]['fstype'] == 'ext4'
                and 'rw' in data[0]['options'].split(','), f'actual mount mismatch: {path}')
        result[str(path)] = data[0]
    require(len({os.stat(p).st_dev for p in ('/', '/data', '/data/models-large')}) == 3,
            'root/data/model devices must differ')
    fs = os.statvfs('/')
    free = fs.f_bavail * fs.f_frsize
    require(free >= 4 * 1024**3, 'root available space below exact 4 GiB threshold')
    result['root_available_bytes'] = free
    result['root_warning_below_6_gib'] = free < 6 * 1024**3
    return result


def guards(repo, phase, dry_run):
    identity = mounts()
    suffix = ('dryrun-' if dry_run else '') + phase + '-' + str(os.getpid())
    report = TASK / ('evidence/root-qwen-seal-' + suffix + '.md')
    require(not report.exists() and not report.is_symlink(), f'guard report already exists: {report}')
    env = dict(os.environ, TMPDIR=str(TASK / 'tmp'), PYTHONDONTWRITEBYTECODE='1')
    run([str(repo / 'scripts/common/require-data-mounted.sh')], cwd=repo, env=env)
    run([str(repo / 'scripts/common/root-disk-guard.sh'), '--no-sudo', '--report', str(report)],
        cwd=repo, env=env)
    return dict(mounts=identity, report=str(report), sha256=read_small(report)[1]['sha256'])


def unit(name):
    result = subprocess.run(['systemctl', 'show', name, '--property=LoadState,ActiveState,SubState,MainPID,Result'],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    require(fields.get('LoadState') in ('loaded', 'not-found'), f'unit observation unavailable: {name}')
    return dict(unit=name, fields=fields, query_exit_code=result.returncode)


def no_acquisition_owner(status):
    qwen = unit('f1a-qwen-fast-acquire-20260915.service')
    fields = qwen['fields']
    require(fields.get('ActiveState') == 'inactive' and fields.get('SubState') == 'dead'
            and fields.get('MainPID') == '0', 'Qwen acquisition unit is not inactive/dead')
    pid = status.get('pid')
    require(type(pid) is int and pid > 1 and not Path(f'/proc/{pid}').exists(),
            'recorded Qwen acquisition PID exists; stop for explicit investigation')
    return qwen


def no_writable_descriptors(identities):
    # A previous writer with an already-open FD could write after chmod/chown.
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            for descriptor in (process / 'fd').iterdir():
                try:
                    st = descriptor.stat()
                    if (st.st_dev, st.st_ino) not in identities:
                        continue
                    info = (process / 'fdinfo' / descriptor.name).read_text()
                    rows = dict(line.split(':', 1) for line in info.splitlines() if ':' in line)
                    flags = int(rows['flags'].strip(), 8)
                    require(flags & os.O_ACCMODE == os.O_RDONLY,
                            f'Qwen writable descriptor exists: PID {process.name}, FD {descriptor.name}')
                except FileNotFoundError:
                    pass  # Process or FD closed during read-only scan.
        except FileNotFoundError:
            pass


def backup_row(path, fd):
    safe_path(path)
    require(same(metadata(os.fstat(fd)), metadata(path.lstat())), f'backup identity race: {path}')
    return dict(path=str(path), identity=metadata(os.fstat(fd)),
                xattrs={name: base64.b64encode(os.getxattr(fd, name)).decode('ascii')
                        for name in os.listxattr(fd)})


def publish_new(path, value, mode):
    # Hard-link publication gives no-overwrite atomic semantics on this ext4 filesystem.
    safe_path(path.parent)
    require(not path.exists() and not path.is_symlink(), f'output already exists: {path}')
    temp = path.with_name(path.name + '.tmp-' + str(os.getpid()))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    try:
        raw = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
        os.fchown(fd, 0, 0)
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
        os.link(temp, path, follow_symlinks=False)
        temp.unlink()
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return hashlib.sha256(raw).hexdigest()
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', required=True, type=Path, help='Reviewed release checkout; no Git mutation is performed')
    parser.add_argument('--dry-run', action='store_true', help='All checks; guard reports only, no seal/backup/completion mutation')
    args = parser.parse_args()
    require(os.geteuid() == 0 and sys.platform == 'linux', 'root on Linux ai-vm required')
    def interrupted(signum, frame):
        raise RuntimeError(f'interrupted by signal {signum}')
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, interrupted)
    os.umask(0o077)
    mounts()
    protected_directory(ACQ)
    for path in (TASK, TASK / 'inputs', TASK / 'backups', TASK / 'evidence', TASK / 'tmp'):
        safe_path(path)
        require(path.is_dir() and path.stat().st_dev == Path('/data').stat().st_dev,
                f'existing task directory on verified /data required: {path}')
    require(args.repo.is_absolute(), 'absolute reviewed repo path required')
    safe_path(args.repo)
    source_evidence = {}
    for relative, digest in PINS.items():
        if relative.startswith('scripts/'):
            source_evidence[relative] = read_small(args.repo / relative, digest)[1]
    for path in (BACKUP, SEAL, COMPLETE):
        require(not path.exists() and not path.is_symlink(), f'recovery/output already exists: {path}')
    before_guard = guards(args.repo, 'before', args.dry_run)
    proof_raw, proof_id = read_small(PROOF, PINS['proof'])
    proof = json.loads(proof_raw)
    require(proof.get('result') == 'PASS_ALIGNMENT_UNSEALED_HANDOFF'
            and len(proof.get('checks', {})) == 16 and all(proof['checks'].values()), 'M1 proof checks incomplete')
    status_raw, status_id = read_small(STATUS, PINS['status'])
    manifest_raw, manifest_id = read_small(MANIFEST, PINS['manifest'])
    status, manifest = json.loads(status_raw), json.loads(manifest_raw)
    require(same(status_id['identity'], proof['status_identity']['after'])
            and same(manifest_id['identity'], proof['immutable_manifest_identity']['after']), 'M1 evidence stat identity changed')
    require(manifest == proof['manifest'] and manifest_raw.decode() == proof['immutable_manifest_source_text'],
            'M1 manifest identity differs')
    artifacts = manifest['artifacts']
    require(len(artifacts) == 48 and {a['path'] for a in artifacts} == WEIGHTS | SMALL
            and sum(a['size_bytes'] for a in artifacts) == 80407722953, 'exact artifact set/total invalid')
    require(status.get('status') == 'PASS_ALL_48_VERIFIED' and status.get('repo_id') == manifest['repo_id']
            == 'Qwen/Qwen3-Coder-Next-FP8' and status.get('revision') == manifest['revision'] == REV
            and status.get('destination') == str(MODEL) and status.get('manifest_sha256') == PINS['manifest'],
            'acquisition terminal identity invalid')
    for field, expected in [('total_bytes', 80407722953), ('bytes_present', 80407722953),
                            ('sha256_verified_bytes', 80407722953), ('fully_verified_bytes', 80407722953),
                            ('download_complete_artifacts', 48), ('sha256_verified_artifacts', 48),
                            ('fully_verified_artifacts', 48), ('verified_weight_shards', 40), ('index_referenced_shards', 40)]:
        require(type(status.get(field)) is int and status[field] == expected, f'acquisition count mismatch: {field}')
    require(status.get('active_artifacts') == []
            and status.get('runtime_asset_contract') == 'PASS_NATIVE_NO_TRUST_REMOTE_CODE'
            and status.get('helper_sha256') == PINS['scripts/f1a/acquire.py']
            and status.get('reused_transfer_sha256') == PINS['scripts/d1/acquire.py'], 'acquisition proof/source mismatch')
    require(set(status['files']) == WEIGHTS | SMALL, 'status artifact set differs')
    qwen_unit = no_acquisition_owner(status)
    glm_before = dict(identity=metadata(GLM.lstat()), unit=unit('d1-glm53-acquire-20260915-d1b-p4.service'))
    safe_path(GLM)
    require(GLM.is_dir() and GLM.stat().st_dev == MODEL.parent.stat().st_dev, 'GLM child mount identity invalid')
    fds = {}
    try:
        fds[LOCK] = open_regular(LOCK)
        require(os.fstat(fds[LOCK]).st_size == 0, 'acquisition lock must be existing zero-byte file')
        fcntl.flock(fds[LOCK], fcntl.LOCK_EX | fcntl.LOCK_NB)
        no_acquisition_owner(status)
        require({p.name for p in MODEL.iterdir()} == WEIGHTS | SMALL | {LOCK.name}, 'unexpected/partial model entries')
        aligned = {a['path']: a for a in proof['alignment']}
        require(len(proof['alignment']) == 48 and set(aligned) == WEIGHTS | SMALL, 'M1 alignment set differs')
        small_evidence = []
        assets = {}
        for artifact in artifacts:
            name = artifact['path']
            row = status['files'][name]
            require(row.get('status') == 'VERIFIED' and row.get('sha256_verified') is True
                    and row.get('artifact_verified') is True and row.get('computed_sha256') == artifact['sha256']
                    and row.get('bytes_present') == artifact['size_bytes'], f'incomplete hash evidence: {name}')
            if 'git_blob_sha1' in artifact:
                require(row.get('git_blob_sha1_verified') is True
                        and row.get('computed_git_blob_sha1') == artifact['git_blob_sha1'], f'Git identity missing: {name}')
            path = MODEL / name
            fd = fds[path] = open_regular(path)
            current = metadata(os.fstat(fd))
            require(same(current, aligned[name]['filesystem_identity'])
                    and current['size_bytes'] == artifact['size_bytes']
                    and current['device'] == MODEL.parent.stat().st_dev, f'M1 payload stat mismatch: {name}')
            if name in SMALL:
                raw, identity = read_small(path, artifact['sha256'])
                if 'git_blob_sha1' in artifact:
                    require(hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest() == artifact['git_blob_sha1'],
                            f'independent small-asset Git mismatch: {name}')
                small_evidence.append(identity)
                if name in ('config.json', 'model.safetensors.index.json', 'tokenizer_config.json'):
                    assets[name] = json.loads(raw)
        config, index = assets['config.json'], assets['model.safetensors.index.json']
        tokenizer = assets['tokenizer_config.json']
        quant = config.get('quantization_config', {})
        require(config.get('architectures') == ['Qwen3NextForCausalLM']
                and config.get('model_type') == 'qwen3_next'
                and quant.get('quant_method') == 'fp8' and quant.get('weight_block_size') == [128, 128]
                and quant.get('activation_scheme') == 'dynamic' and not config.get('auto_map'),
                'config native architecture/FP8 contract mismatch')
        require(not tokenizer.get('auto_map') and tokenizer.get('tokenizer_class') == 'Qwen2Tokenizer',
                'tokenizer native class/no-remote-code contract mismatch')
        require(isinstance(index.get('weight_map'), dict) and index['weight_map']
                and set(index['weight_map'].values()) == WEIGHTS, 'index does not reference exact40 shards')
        for path in (MODEL.parent, MODEL):
            safe_path(path)
            fds[path] = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        targets = [MODEL.parent, MODEL, LOCK] + [MODEL / a['path'] for a in artifacts]
        snapshots = [backup_row(path, fds[path]) for path in targets]
        payload_ids = {(os.fstat(fd).st_dev, os.fstat(fd).st_ino) for p, fd in fds.items() if p.parent == MODEL}
        require(len(payload_ids) == 49, 'payload/lock inode aliases')
        no_writable_descriptors(payload_ids)
        # Recheck all original inputs immediately before the first deliberate mutation.
        read_small(STATUS, PINS['status'])
        read_small(MANIFEST, PINS['manifest'])
        for artifact in artifacts:
            require(same(metadata(os.fstat(fds[MODEL / artifact['path']])), aligned[artifact['path']]['filesystem_identity']),
                    f'payload changed during preflight: {artifact["path"]}')
        planned = [dict(path=row['path'], uid=0, gid=row['identity']['gid'],
                        mode=oct(int(row['identity']['mode'], 8) & ~0o022)) for row in snapshots]
        if args.dry_run:
            after_guard = guards(args.repo, 'after', True)
            print(json.dumps(dict(result='PASS_DRY_RUN', mutation_plan=planned, before_guard=before_guard,
                                  after_guard=after_guard, independently_reread_all_weight_bytes=False,
                                  independent_small_assets_hashed=8), indent=2))
            return
        backup = dict(schema_version=1, created_utc=now(), before=snapshots, planned=planned,
                      mounts=before_guard['mounts'], glm_before=glm_before,
                      restore='While holding acquisition lock and before any model use, restore only listed path ownership/modes/xattrs after confirming device/inode. Never recursive; ctime cannot be restored. Remove trusted completion before restoring write permissions.')
        backup_sha = publish_new(BACKUP, backup, 0o600)
        for row, plan in zip(snapshots, planned):
            path = Path(row['path'])
            fd = fds[path]
            require(same(metadata(os.fstat(fd)), row['identity'])
                    and same(metadata(path.lstat()), row['identity']), f'identity changed before seal: {path}')
            if os.fstat(fd).st_uid != 0:
                os.fchown(fd, 0, plan['gid'])
            if stat.S_IMODE(os.fstat(fd).st_mode) != int(plan['mode'], 8):
                os.fchmod(fd, int(plan['mode'], 8))
            os.fsync(fd)
        protected_directory(MODEL)
        after = [backup_row(path, fds[path]) for path in targets]
        for old, new in zip(snapshots, after):
            require(same(old['identity'], new['identity'], ('device', 'inode', 'nlink', 'size_bytes', 'mtime_ns', 'regular', 'symlink'))
                    and new['identity']['uid'] == 0 and not int(new['identity']['mode'], 8) & 0o022,
                    f'post-seal identity/protection mismatch: {old["path"]}')
        no_writable_descriptors(payload_ids)
        require(same(glm_before['identity'], metadata(GLM.lstat()), ('device', 'inode', 'mode', 'uid', 'gid')),
                'GLM child ownership/mode/identity changed')
        require({p.name for p in MODEL.iterdir()} == WEIGHTS | SMALL | {LOCK.name}, 'model entries changed during seal')
        require(same(read_small(STATUS, PINS['status'])[1]['identity'], proof['status_identity']['after'])
                and same(read_small(MANIFEST, PINS['manifest'])[1]['identity'], proof['immutable_manifest_identity']['after']),
                'original downloader evidence changed during seal')
        after_guard = guards(args.repo, 'after', False)
        evidence = dict(schema_version=1, result='PASS_ACQUISITION_HASH_STAT_SEAL', created_utc=now(),
                        evidence_class='acquisition_worker_computed_sha256_m1_and_current_stat_alignment_protected_payload',
                        independently_reread_all_weight_bytes=False, independently_hashed_small_assets=small_evidence,
                        source_evidence=source_evidence, proof=proof_id, status=status_id, manifest=manifest_id,
                        qwen_unit=qwen_unit, acquisition_lock_held=True, backup=str(BACKUP), backup_sha256=backup_sha,
                        before=snapshots, after=after, before_guard=before_guard, after_guard=after_guard,
                        glm_before=glm_before, glm_after=dict(identity=metadata(GLM.lstat()),
                            unit=unit('d1-glm53-acquire-20260915-d1b-p4.service')),
                        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        auth_gate_passed=False, model_inference='NOT_TESTED')
        protected_directory(ACQ)
        evidence_sha = publish_new(SEAL, evidence, 0o644)
        completion = dict(schema_version=1, complete=True, repo_id=manifest['repo_id'], revision=REV,
                          model_root=str(MODEL), manifest_sha256=PINS['manifest'], artifact_count=48,
                          total_bytes=80407722953, evidence=str(SEAL), evidence_sha256=evidence_sha,
                          independently_reread_all_weight_bytes=False,
                          artifacts=[dict(path=a['path'], size_bytes=a['size_bytes'], sha256=a['sha256'], verified=True)
                                     for a in artifacts])
        completion_sha = publish_new(COMPLETE, completion, 0o644)
        for path in (SEAL, COMPLETE):
            protected_directory(path.parent)
            st = path.lstat()
            require(st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o644 and st.st_nlink == 1,
                    f'published evidence metadata invalid: {path}')
        require(read_small(COMPLETE, completion_sha)[0] == (json.dumps(completion, indent=2, sort_keys=True) + '\n').encode(),
                'completion readback mismatch')
        # Final milestone storage guard follows even the small evidence writes.
        final_guard = guards(args.repo, 'final', False)
        print(json.dumps(dict(result='PASS_SEALED', completion_manifest=str(COMPLETE), completion_sha256=completion_sha,
                              seal_evidence=str(SEAL), seal_evidence_sha256=evidence_sha, backup=str(BACKUP),
                              final_guard=final_guard,
                              independently_reread_all_weight_bytes=False, auth_gate_passed=False,
                              inference='NOT_TESTED'), indent=2))
    finally:
        for fd in fds.values():
            os.close(fd)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print(f'STOP: {exc}; do not infer completion. Preserve any backup/partial protection for review.', file=sys.stderr)
        sys.exit(1)
