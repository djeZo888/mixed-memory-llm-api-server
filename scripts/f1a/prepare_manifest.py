#!/usr/bin/env python3
"""Fetch pinned metadata and small assets only; never download model weights.

Verification: run --help, then --run-dir /data/build/f1a-qwen-20260915.
Every selected small asset is checked against the pinned Git blob or LFS hash.
The resulting manifest is input to the separately launched acquisition job.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'd1'))
from storage_guard import check, common

REPO = 'Qwen/Qwen3-Coder-Next-FP8'
REV = 'da6e2ed27304dd39abadd9c82ef50e8de67bdd4c'
UUID = 'a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a'
SMALL = {
    'chat_template.jinja': 'template', 'config.json': 'config',
    'generation_config.json': 'config', 'merges.txt': 'tokenizer',
    'model.safetensors.index.json': 'index', 'tokenizer.json': 'tokenizer',
    'tokenizer_config.json': 'tokenizer', 'vocab.json': 'tokenizer',
}


def fetch(url, limit=24 * 1024**2):
    with urllib.request.urlopen(url, timeout=90) as response:
        if response.status != 200:
            raise RuntimeError('unexpected metadata HTTP status')
        content = response.read(limit + 1)
        if len(content) > limit:
            raise RuntimeError('metadata/small asset size limit exceeded')
        return content


def verify_asset(row, content):
    if len(content) != row['size']:
        raise RuntimeError('small asset size mismatch: ' + row['rfilename'])
    sha = hashlib.sha256(content).hexdigest()
    if row.get('lfs'):
        if row['lfs']['size'] != len(content) or row['lfs']['sha256'] != sha:
            raise RuntimeError('small asset LFS hash mismatch')
    else:
        blob = hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
        if blob != row['blobId']:
            raise RuntimeError('small asset Git blob mismatch')
    return sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    args = parser.parse_args()
    run = args.run_dir
    if (not run.is_absolute() or run.parent != Path('/data/build')
            or not run.name.startswith('f1a-') or run != run.resolve(strict=False)):
        parser.error('run must be a normalized isolated /data/build/f1a- path')

    def guard():
        check(UUID)
        for path in (run.parent, run, run / 'metadata', run / 'evidence'):
            if any(p.is_symlink() for p in (path, *path.parents)):
                raise RuntimeError('symlinked task path')
            if path.exists() and (not path.is_dir() or os.stat(path).st_dev != os.stat('/data').st_dev):
                raise RuntimeError('task directory is not on verified /data')

    def save(path, content):
        guard()
        if path.is_symlink() or path.exists():
            raise RuntimeError('refusing to replace existing metadata evidence: ' + str(path))
        with path.open('xb') as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())

    guard()
    run.mkdir(exist_ok=True)
    for name in ('metadata', 'evidence'):
        guard()
        (run / name).mkdir(exist_ok=True)
    common(run / 'evidence/root-metadata-before.md')
    metadata_url = f'https://huggingface.co/api/models/{REPO}/revision/{REV}?blobs=true'
    raw = fetch(metadata_url)
    meta = json.loads(raw)
    if meta['id'] != REPO or meta['sha'] != REV or meta.get('gated') or meta.get('disabled'):
        raise RuntimeError('pinned repository identity/access mismatch')
    if meta['cardData']['license'] != 'apache-2.0':
        raise RuntimeError('license metadata mismatch')
    rows = {r['rfilename']: r for r in meta['siblings']}
    if len(rows) != len(meta['siblings']):
        raise RuntimeError('duplicate repository file rows')
    weights = {f'model-{i:05d}-of-00040.safetensors' for i in range(1, 41)}
    if {p for p in rows if p.endswith('.safetensors')} != weights:
        raise RuntimeError('unexpected weight set')
    contents, hashes = {}, {}
    for name in [*SMALL, 'README.md']:
        row = rows[name]
        content = fetch(f'https://huggingface.co/{REPO}/resolve/{REV}/{name}')
        hashes[name] = verify_asset(row, content)
        contents[name] = content
    index = json.loads(contents['model.safetensors.index.json'])
    if set(index['weight_map'].values()) != weights:
        raise RuntimeError('weight-index referenced shard set mismatch')
    config = json.loads(contents['config.json'])
    quant = config['quantization_config']
    if (config['architectures'] != ['Qwen3NextForCausalLM'] or config['model_type'] != 'qwen3_next'
            or quant['quant_method'] != 'fp8' or quant['weight_block_size'] != [128, 128]
            or quant['activation_scheme'] != 'dynamic' or config.get('auto_map')):
        raise RuntimeError('architecture/quantization/custom-code contract mismatch')
    tokenizer = json.loads(contents['tokenizer_config.json'])
    if tokenizer.get('auto_map'):
        raise RuntimeError('tokenizer custom-code contract requires review')
    artifacts = []
    for name in sorted(weights | set(SMALL)):
        row = rows[name]
        if type(row['size']) is not int or row['size'] <= 0:
            raise RuntimeError('invalid published artifact size')
        artifact = {'path': name, 'size_bytes': row['size'], 'role': 'weight' if name in weights else SMALL[name]}
        if row.get('lfs'):
            if (row['lfs']['size'] != row['size']
                    or not re.fullmatch(r'[0-9a-f]{64}', row['lfs']['sha256'])):
                raise RuntimeError('invalid LFS size/hash')
            artifact.update(sha256=row['lfs']['sha256'], lfs_sha256=row['lfs']['sha256'])
        else:
            artifact.update(sha256=hashes[name], git_blob_sha1=row['blobId'])
        artifacts.append(artifact)
    weight_bytes = sum(a['size_bytes'] for a in artifacts if a['role'] == 'weight')
    if weight_bytes != 80381394600:
        raise RuntimeError('approved weight size mismatch')
    manifest = dict(schema_version=1, repo_id=REPO, revision=REV, architecture='Qwen3NextForCausalLM',
                    quantization='fp8', license='apache-2.0', artifact_count=len(artifacts),
                    total_bytes=sum(a['size_bytes'] for a in artifacts), weight_count=40,
                    weight_bytes=weight_bytes, artifacts=artifacts)
    save(run / 'metadata/hf-pinned-metadata.json', raw)
    for name, content in contents.items():
        save(run / 'metadata' / name, content)
    encoded = (json.dumps(manifest, indent=2) + '\n').encode()
    save(run / 'metadata/f1a-qwen-manifest.json', encoded)
    proof = dict(metadata_url=metadata_url, manifest_sha256=hashlib.sha256(encoded).hexdigest(),
                 status='PASS_METADATA_AND_SMALL_ASSET_HASHES_ONLY', weight_downloaded=False,
                 small_computed_sha256=hashes, weight_index_entries=len(index['weight_map']),
                 index_tensor_bytes=index['metadata']['total_size'], tokenizer_class=tokenizer.get('tokenizer_class'),
                 config_auto_map=config.get('auto_map'), tokenizer_auto_map=tokenizer.get('auto_map'))
    save(run / 'evidence/metadata-proof.json', (json.dumps(proof, indent=2) + '\n').encode())
    guard()
    common(run / 'evidence/root-metadata-after.md')
    print(json.dumps({**proof, 'artifact_count': len(artifacts), 'total_bytes': manifest['total_bytes']}, indent=2))


if __name__ == '__main__':
    main()
