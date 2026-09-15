#!/usr/bin/env python3
"""Pinned Qwen acquisition only; no model load, cache copy, or GLM mutation.

Read-only reuse of reviewed D1b transfer/atomic-status/concurrency primitives.
The privately loaded Python module belongs to this process, not the GLM job.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import sys
import time
from types import SimpleNamespace
import urllib.request

D1 = Path(__file__).resolve().parents[1] / 'd1'
sys.path.insert(0, str(D1))
spec = importlib.util.spec_from_file_location('_f1a_reviewed_d1', D1 / 'acquire.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
sys.path.pop(0)

REPO_ID = 'Qwen/Qwen3-Coder-Next-FP8'
REV = 'da6e2ed27304dd39abadd9c82ef50e8de67bdd4c'
MODEL_UUID = 'a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a'
DEST = Path('/data/models-large/qwen3-coder-next-fp8')
GLM_DEST = Path('/data/models-large/glm-5.3-ud-q4-k-xl')
RUN = Path('/data/build/f1a-qwen-20260915')
WEIGHT_BYTES = 80381394600
WEIGHTS = {f'model-{i:05d}-of-00040.safetensors' for i in range(1, 41)}
SMALL = {'model.safetensors.index.json', 'chat_template.jinja', 'config.json',
         'generation_config.json', 'merges.txt', 'tokenizer.json',
         'tokenizer_config.json', 'vocab.json'}
RESERVE = 20 * 1024**3
IntegrityError, Cancelled = base.IntegrityError, base.Cancelled
digest, no_symlinks, check, common = base.digest, base.no_symlinks, base.check, base.common
GLM_REPO, GLM_REV, GLM_TOTAL = base.REPO_ID, base.REV, base.TOTAL
# Only this private module instance is configured. No shared source is changed.
base.REPO_ID, base.REV, base.DEST = REPO_ID, REV, DEST


def validate_manifest(m):
    if (m.get('schema_version'), m.get('repo_id'), m.get('revision'),
            m.get('architecture'), m.get('quantization'), m.get('license')) != (
            1, REPO_ID, REV, 'Qwen3NextForCausalLM', 'fp8', 'apache-2.0'):
        raise IntegrityError('manifest identity mismatch')
    rows = m['artifacts']
    if (len(rows) != 48 or m.get('artifact_count') != 48 or
            {a['path'] for a in rows} != WEIGHTS | SMALL):
        raise IntegrityError('manifest exact artifact set mismatch')
    for a in rows:
        if (type(a['size_bytes']) is not int or a['size_bytes'] <= 0 or
                not re.fullmatch('[0-9a-f]{64}', a['sha256']) or not a.get('role')):
            raise IntegrityError('invalid artifact size/hash/role')
        if a['path'] in WEIGHTS or a['path'] == 'model.safetensors.index.json':
            if a.get('lfs_sha256') != a['sha256'] or a.get('git_blob_sha1'):
                raise IntegrityError('LFS SHA256 identity missing or ambiguous')
        elif (not re.fullmatch('[0-9a-f]{40}', a.get('git_blob_sha1', '')) or
                a.get('lfs_sha256') or a['size_bytes'] > 32 * 1024**2):
            raise IntegrityError('small Git asset identity/size mismatch')
    weight_bytes = sum(a['size_bytes'] for a in rows if a['path'] in WEIGHTS)
    if (weight_bytes != WEIGHT_BYTES or m.get('weight_count') != 40 or
            m.get('weight_bytes') != WEIGHT_BYTES or
            sum(a['size_bytes'] for a in rows) != m.get('total_bytes')):
        raise IntegrityError('manifest byte totals mismatch')
    return rows


def compare_metadata(artifacts, metadata):
    if metadata.get('sha') != REV or metadata.get('id') != REPO_ID:
        raise IntegrityError('pinned repository/revision metadata mismatch')
    siblings = metadata['siblings']
    paths = [r['rfilename'] for r in siblings]
    if len(paths) != len(set(paths)):
        raise IntegrityError('duplicate pinned metadata paths')
    actual = {r['rfilename']: r for r in siblings}
    for a in artifacts:
        r = actual.get(a['path'], {})
        if r.get('size') != a['size_bytes']:
            raise IntegrityError('pinned artifact size mismatch')
        if 'lfs_sha256' in a:
            lfs = r.get('lfs', {})
            if (lfs.get('sha256'), lfs.get('size')) != (a['sha256'], a['size_bytes']):
                raise IntegrityError('pinned LFS metadata mismatch')
        elif r.get('lfs') or r.get('blobId') != a['git_blob_sha1']:
            raise IntegrityError('pinned Git blob metadata mismatch')


def git_blob(path):
    h = hashlib.sha1()
    h.update(f'blob {path.stat().st_size}\0'.encode())
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(base.CHUNK), b''):
            h.update(block)
    return h.hexdigest()


def validate_glm_manifest(m):
    expected = {f'UD-Q4_K_XL/GLM-5.3-UD-Q4_K_XL-{i:05d}-of-00011.gguf' for i in range(1, 12)}
    rows = m['artifacts']
    if ((m.get('repo_id'), m.get('revision'), m.get('quantization'), m.get('artifact_count'),
            m.get('total_bytes')) != (GLM_REPO, GLM_REV, 'UD-Q4_K_XL', 11, GLM_TOTAL) or
            len(rows) != 11 or {a['path'] for a in rows} != expected or
            sum(a['size_bytes'] for a in rows) != GLM_TOTAL or
            any(a['size_bytes'] <= 0 or not re.fullmatch('[0-9a-f]{64}', a['sha256']) for a in rows)):
        raise IntegrityError('GLM reservation manifest identity mismatch')
    return rows


def remaining_bytes(destination, artifacts, device):
    """Read actual sizes only; a simultaneous GLM rename is conservatively absent."""
    remaining = 0
    for a in artifacts:
        final = destination / a['path']
        partial = final.with_name(final.name + '.partial')
        found = []
        for path in (final, partial):
            no_symlinks(path.parent)
            try:
                st = path.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(st.st_mode) or st.st_dev != device or st.st_size > a['size_bytes']:
                raise IntegrityError('unsafe/oversize existing artifact')
            found.append(st.st_size)
        if len(found) > 1:
            raise IntegrityError('ambiguous final plus partial')
        remaining += a['size_bytes'] - (found[0] if found else 0)
    return remaining


class Acquisition(base.Acquisition):
    def __init__(self, args):
        no_symlinks(args.run_dir)
        if args.run_dir != RUN or '..' in args.run_dir.parts:
            raise IntegrityError('exact normalized isolated run path required')
        # Base constructor accepts 1/3/4; this task intentionally defaults to 2.
        super().__init__(SimpleNamespace(**{**vars(args), 'workers': 1}))
        self.args = args
        self.workers = args.workers
        if self.workers not in (1, 2, 3, 4):
            raise IntegrityError('workers must be 1 through 4')
        if args.model_uuid != MODEL_UUID:
            raise IntegrityError('exact model UUID required')
        for path in (args.manifest, args.glm_manifest):
            no_symlinks(path)
        if (digest(args.manifest) != args.manifest_sha256 or
                digest(args.glm_manifest) != args.glm_manifest_sha256):
            raise IntegrityError('immutable manifest SHA256 mismatch')
        self.manifest = json.loads(args.manifest.read_text())
        self.artifacts = validate_manifest(self.manifest)
        self.glm_artifacts = validate_glm_manifest(json.loads(args.glm_manifest.read_text()))
        self.state.update(repo_id=REPO_ID, revision=REV, destination=str(DEST),
                          total_bytes=self.manifest['total_bytes'], workers=self.workers,
                          helper_sha256=digest(Path(__file__)),
                          reused_transfer_sha256=digest(D1 / 'acquire.py'),
                          manifest_sha256=args.manifest_sha256,
                          glm_manifest_sha256=args.glm_manifest_sha256,
                          model_inference='NOT_TESTED', tool_calls='NOT_TESTED')
        self.state.pop('glm_inference', None)
        self.by_path = {a['path']: a for a in self.artifacts}
        # Extend the private D1b SHA gate: Git assets must pass both identities
        # inside digest(), before inherited one() can rename a partial to final.
        base.digest = self.artifact_digest

    def require_capacity(self, remaining=0):
        device = self.model_device()
        qwen_remaining = remaining_bytes(DEST, self.artifacts, device)
        glm_remaining = remaining_bytes(GLM_DEST, self.glm_artifacts, device)
        free = shutil.disk_usage('/data/models-large').free
        if free < qwen_remaining + glm_remaining + RESERVE + remaining:
            raise IntegrityError('insufficient space for both remaining models plus 20 GiB reserve')
        self.state['capacity'] = dict(model_free_bytes=free,
            qwen_remaining_bytes=qwen_remaining, glm_remaining_bytes=glm_remaining,
            reserve_bytes=RESERVE, write_buffer_bytes=remaining)

    def guard(self):
        identity = check(MODEL_UUID)
        for path, mount in ((self.run, '/data'), (self.run / 'evidence', '/data'),
                            (self.run / 'tmp', '/data'), (DEST, '/data/models-large'),
                            (GLM_DEST, '/data/models-large')):
            no_symlinks(path)
            if path.exists() and path.stat().st_dev != os.stat(mount).st_dev:
                raise IntegrityError('nested mount redirects task/artifact path')
        self.require_capacity(self.workers * base.CHUNK)
        return identity

    def status(self, force=False, failure=False):
        with self.mutex:
            now = time.monotonic()
            if not force and now - self.last_status < 15:
                return
            rows = self.state['files']
            self.state.update(updated_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                session_bytes_downloaded=self.transferred,
                session_average_bytes_per_second=int(self.transferred / max(now - self.start, 1)),
                bytes_present=sum(f.get('bytes_present', 0) for f in rows.values()),
                sha256_verified_bytes=sum(f['bytes_present'] for f in rows.values() if f.get('sha256_verified')),
                active_artifacts=[p for p, f in rows.items() if f.get('status') in ('DOWNLOADING', 'HASHING')])
            self.state['download_complete_artifacts'] = sum(
                f.get('bytes_present') == a['size_bytes']
                for a in self.artifacts for f in [rows.get(a['path'], {})])
            self.state['sha256_verified_artifacts'] = sum(bool(f.get('sha256_verified')) for f in rows.values())
            self.state['verified_weight_shards'] = sum(bool(rows.get(p, {}).get('artifact_verified')) for p in WEIGHTS)
            self.state['fully_verified_artifacts'] = sum(bool(f.get('artifact_verified')) for f in rows.values())
            self.state['fully_verified_bytes'] = sum(f['bytes_present'] for f in rows.values() if f.get('artifact_verified'))
            self.atomic_json('acquisition-status.json', self.state, failure=failure)
            self.last_status = now

    @contextmanager
    def owner(self):
        lock = DEST / '.f1a-acquisition.lock'
        no_symlinks(lock)
        self.guard()
        with lock.open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.owns_lock = True
            try:
                yield
            except BaseException as exc:
                self.cancel.set()
                with self.mutex:
                    self.state.update(status='CANCELLED' if isinstance(exc, Cancelled) else 'STOP',
                                      error_type=type(exc).__name__)
                    for row in self.state['files'].values():
                        if row.get('status') in ('PENDING', 'DOWNLOADING', 'HASHING'):
                            row['status'] = 'CANCELLED'
                try:
                    self.status(True, failure=True)
                    common(self.run / 'evidence/root-acquisition-stopped.md')
                except Exception:
                    print('STOP: final status unavailable; prior JSON may be stale', file=sys.stderr)
                raise
            finally:
                self.owns_lock = False
                fcntl.flock(stream, fcntl.LOCK_UN)

    def artifact_digest(self, path, cancel=None):
        value = digest(path, cancel)
        name = path.name.removesuffix('.partial')
        artifact = self.by_path.get(name) if path.parent == DEST else None
        if artifact and 'git_blob_sha1' in artifact and value == artifact['sha256']:
            self.cancelled()
            self.guard()
            git_value = git_blob(path)
            if git_value != artifact['git_blob_sha1']:
                raise IntegrityError('computed Git blob identity mismatch: artifact preserved')
            with self.mutex:
                self.state['files'][name].update(
                    git_blob_sha1_verified=True, computed_git_blob_sha1=git_value)
        return value

    def one(self, artifact):
        # SHA256/Git identity gate and adjacent resume/fsync/rename use D1b code.
        super().one(artifact)
        row = self.state['files'][artifact['path']]
        if 'git_blob_sha1' in artifact and not row.get('git_blob_sha1_verified'):
            raise IntegrityError('small artifact Git gate missing')
        with self.mutex:
            row['artifact_verified'] = True
            self.status(True)

    def asset_contract(self):
        index = json.loads((DEST / 'model.safetensors.index.json').read_text())
        weight_map = index.get('weight_map')
        if not isinstance(weight_map, dict) or not weight_map or set(weight_map.values()) != WEIGHTS:
            raise IntegrityError('exact complete index referenced shard set mismatch')
        config = json.loads((DEST / 'config.json').read_text())
        if (config.get('architectures') != ['Qwen3NextForCausalLM'] or
                config.get('quantization_config', {}).get('quant_method') != 'fp8'):
            raise IntegrityError('pinned config architecture/quantization mismatch')
        if config.get('auto_map'):
            raise IntegrityError('unexpected remote-code mapping; review required')
        for name in SMALL:
            if not self.state['files'][name].get('artifact_verified'):
                raise IntegrityError('required runtime asset not verified')
        self.state['index_referenced_shards'] = 40
        self.state['runtime_asset_contract'] = 'PASS_NATIVE_NO_TRUST_REMOTE_CODE'

    def acquire(self):
        if self.run != RUN:
            raise IntegrityError('exact isolated run path required')
        identity = self.guard()
        self.state['mounts'] = identity
        DEST.mkdir(exist_ok=True)
        self.guard()
        with self.owner():
            common(self.run / 'evidence/root-acquisition-before.md')
            self.guard()
            url = f'https://huggingface.co/api/models/{REPO_ID}/revision/{REV}?blobs=true'
            with urllib.request.urlopen(url, timeout=60) as response:
                metadata = json.load(response)
            compare_metadata(self.artifacts, metadata)
            # Store selected immutable metadata only, never signed redirect URLs.
            self.atomic_json('hf-pinned-metadata.json', {
                'id': metadata['id'], 'sha': metadata['sha'],
                'siblings': [r for r in metadata['siblings'] if r['rfilename'] in WEIGHTS | SMALL]})
            allowed = {a['path'] + suffix for a in self.artifacts for suffix in ('', '.partial')}
            allowed.add('.f1a-acquisition.lock')
            if {p.name for p in DEST.iterdir()} - allowed:
                raise IntegrityError('unexpected destination artifact')
            for a in self.artifacts:
                missing = remaining_bytes(DEST, [a], self.model_device())
                self.state['files'][a['path']] = dict(
                    bytes_present=a['size_bytes'] - missing, initial_bytes=a['size_bytes'] - missing,
                    sha256_verified=False, artifact_verified=False, status='PENDING')
            self.state['status'] = 'DOWNLOADING_RUNTIME_ASSETS'
            self.status(True)
            self.run_workers([a for a in self.artifacts if a['path'] in SMALL])
            self.asset_contract()
            self.state['status'] = 'DOWNLOADING_WEIGHTS'
            self.status(True)
            self.run_workers([a for a in self.artifacts if a['path'] in WEIGHTS])
            self.asset_contract()
            if ({p.name for p in DEST.iterdir()} != WEIGHTS | SMALL | {'.f1a-acquisition.lock'} or
                    any((DEST / a['path']).stat().st_size != a['size_bytes'] for a in self.artifacts) or
                    not all(r.get('artifact_verified') for r in self.state['files'].values())):
                raise IntegrityError('final exact artifact/hash set mismatch')
            self.guard()
            common(self.run / 'evidence/root-acquisition-after.md')
            self.cancelled()
            self.state['status'] = 'PASS_ALL_48_VERIFIED'
            self.status(True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', required=True, type=Path)
    p.add_argument('--manifest-sha256', required=True)
    p.add_argument('--glm-manifest', required=True, type=Path)
    p.add_argument('--glm-manifest-sha256', required=True)
    p.add_argument('--run-dir', required=True, type=Path)
    p.add_argument('--model-uuid', default=MODEL_UUID)
    p.add_argument('--workers', type=int, choices=(1, 2, 3, 4), default=2)
    args = p.parse_args()
    try:
        job = Acquisition(args)
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda signum, frame: job.cancel.set())
        job.acquire()
    except Exception as exc:
        print('STOP acquisition: ' + type(exc).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
