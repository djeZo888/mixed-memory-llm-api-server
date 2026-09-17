"""Q38A read-only image contract check using exact reviewed Q38B source.

Verification command: ssh ai-vm 'sudo -n env TMPDIR=/data/build/q38a-20260915/tmp
python3 -I -B -' < this file. No container launch or native runtime imports.
"""
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess

source = Path('/data/services/q38a-20260915/q38b-reviewed/qwen38_oci.py')
expected_sha = 'f2059445f3a06b15e710bc7d65866bc8d821ca3a78ef900f3d94ce4866accc2f'
assert source.resolve() == source
for path in [source, *source.parents]:
    value = path.stat()
    assert value.st_uid == 0 and not value.st_mode & 0o022
assert source.stat().st_nlink == 1 and hashlib.sha256(source.read_bytes()).hexdigest() == expected_sha
spec = importlib.util.spec_from_file_location('q38b_reviewed_oci', source)
oci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oci)
image = json.loads(subprocess.check_output(['/usr/bin/docker', '--host', 'unix:///run/docker.sock',
                                         'image', 'inspect', oci.IMAGE_REFERENCE], timeout=30))
assert isinstance(image, list) and len(image) == 1
image = image[0]
observed = oci.verify_image(image)
oci.validate_evidence(observed)
payloads = []
for digest, size in ((oci.MANIFEST_DIGEST, oci.MANIFEST_BYTES), (oci.CONFIG_DIGEST, oci.CONFIG_BYTES)):
    raw = subprocess.check_output(['/usr/bin/ctr', '--address', '/run/containerd/containerd.sock',
                                   '--namespace', 'moby', 'content', 'get', digest], timeout=30)
    assert len(raw) == size
    payloads.append(raw)
public = oci.verify_registry_bytes(*payloads)
provenance = json.loads(Path('/data/services/q38a-20260915/repo/reports/q38s-provenance.json').read_text())
expected_env = provenance['runtime']['image_environment']
raw_env = image['Config']['Env']
assert isinstance(raw_env, list) and all(isinstance(value, str) and '=' in value for value in raw_env)
env = dict(value.split('=', 1) for value in raw_env)
assert len(env) == len(raw_env) and env == expected_env
result = {'schema_version': 1, 'status': 'PASS_REVIEWED_Q38B_IMAGE_IDENTITY',
          'checked_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'reviewed_commit': '3a470d2b8c90398be0bffe78bccd13fe1c3a0f2e',
          'reviewed_module_sha256': expected_sha,
          'image_id': oci.CONFIG_DIGEST, 'docker_inspect': observed,
          'descriptor': image.get('Descriptor'), 'docker_reported_size_bytes': image['Size'],
          'stored_public_registry_relationship': public,
          'full_public_environment_equal': True,
          'public_environment_sha256': hashlib.sha256(json.dumps(env, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
          'Q38B_actual_helper_auth': 'NOT_TESTED', 'inference': 'NOT_TESTED', 'model_load': 'NOT_TESTED'}
print(json.dumps(result, indent=2))
