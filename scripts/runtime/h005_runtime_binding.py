"""Closed H005 derived-image binding; pure verification, no build or activation.

The JSON is hashed here after completed build receipts are transcribed. This
module and that JSON are then hashed by the external critical-source manifest.
Historical parent OCI identities remain in qwen38_oci, never overwritten.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re

from runtime import qwen38_oci as parent

ROOT = Path(__file__).resolve().parents[2]
RELATIVE = 'configs/runtimes/h005-runtime-binding.json'
BINDING_SHA256 = '66c83c3487d6a9cae7b7c9c9dd5415a0a272c2fa1732f9e64b8eedbea3c40079'
Qwen38OCIError = parent.Qwen38OCIError
require, same = parent.require, parent.same


def load(*, require_complete=True, root=None):
    raw = ((root or ROOT) / RELATIVE).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == BINDING_SHA256, 'h005_binding_source_mismatch')
    value = json.loads(raw)
    require(value['schema_version'] == 1 and value['runtime_source_commit'] ==
            'f9d9b5191534581d854067507922af2b56790710', 'h005_runtime_source_mismatch')
    if require_complete:
        require(value['status'] == 'COMPLETE_VERIFIED_BUILD', 'h005_runtime_blocked_by_build')
        require(re.fullmatch(r'[0-9a-f]{64}', value.get('build_receipt_sha256') or ''),
                'h005_build_receipt_required')
        for target in ('text', 'image'):
            item = value[target]
            require(re.fullmatch(r'sha256:[0-9a-f]{64}', item.get('image_id') or '')
                    and re.fullmatch(r'sha256:[0-9a-f]{64}', item.get('image_config_digest') or '')
                    and item['image_id'] != item['parent_config_digest'], 'h005_derived_image_required')
            require(item['image_id_domain'] in ('oci_config', 'oci_platform_manifest'),
                    'h005_image_id_domain_required')
            key = 'image_config_digest' if item['image_id_domain'] == 'oci_config' else 'image_manifest_digest'
            require(item['image_id'] == item[key], 'h005_image_domain_mismatch')
    return value


def overlay_source_hashes(repo, provenance=None):
    """Closed full-byte map relative to the installed sglang package root."""
    return {name.removeprefix('python/sglang/'): digest for name, digest in
            load(require_complete=False, root=Path(repo))['text']['final_source_sha256'].items()}


def profile(base):
    """Preserve base environment/version; select only the fixed pair's image."""
    value = load(require_complete=False)
    result = copy.deepcopy(base)
    result['parent_image_id'] = base['image_id']
    result['parent_image_ref'] = base['image_ref']
    result['parent_image_manifest_digest'] = base['image_manifest_digest']
    result['image_id'] = value['text']['image_config_digest']
    result['image_ref'] = value['text']['image_id']
    result['image_manifest_digest'] = value['text']['image_manifest_digest']
    result['h005_binding_sha256'] = BINDING_SHA256
    result['validation'] = {'status': value['status'], 'actual_image': 'REQUIRES_NEW_PAIR_AUTH_RECEIPTS',
                            'inference': 'NOT_TESTED', 'service_activation': 'NOT_PERFORMED'}
    return result


class TextOCI:
    Qwen38OCIError = Qwen38OCIError

    def __init__(self):
        self.binding = load()
        self.item = self.binding['text']
        self.IMAGE_ID = self.item['image_config_digest']
        # Local derived image: exact observed immutable ID, never a mutable tag.
        self.IMAGE_REFERENCE = self.item['image_id']

    def expected_evidence(self, observed_id):
        require(observed_id == self.item['image_id'], 'h005_image_identity_mismatch')
        return {'image_id': observed_id, 'image_id_domain': self.item['image_id_domain'],
                'image_reference': self.IMAGE_REFERENCE,
                'platform_manifest_digest': self.item['image_manifest_digest'],
                'config_digest': self.item['image_config_digest'],
                'source_revision': parent.SOURCE_REVISION, 'source_repository': parent.SOURCE_REPOSITORY,
                'os': 'linux', 'architecture': 'amd64',
                'image_default_entrypoint': list(parent.IMAGE_ENTRYPOINT),
                'image_default_workdir': parent.IMAGE_WORKDIR,
                'parent_manifest_digest': parent.MANIFEST_DIGEST,
                'parent_config_digest': parent.CONFIG_DIGEST,
                'overlay_sha256': self.item['overlay_sha256'],
                'binding_sha256': BINDING_SHA256,
                'build_receipt_sha256': self.binding['build_receipt_sha256']}

    def validate_evidence(self, evidence):
        require(isinstance(evidence, dict), 'h005_image_evidence_invalid')
        expected = self.expected_evidence(evidence.get('image_id'))
        require(same(evidence, expected), 'h005_image_evidence_mismatch')
        return expected

    def verify_image(self, image):
        require(isinstance(image, dict), 'h005_image_inspect_invalid')
        result = self.expected_evidence(image.get('Id'))
        require(image.get('Os') == 'linux' and image.get('Architecture') == 'amd64',
                'h005_image_platform_mismatch')
        parent._config(image.get('Config'))
        require(image['Config'].get('Volumes') in (None, {}), 'h005_image_volumes_unreviewed')
        require(image['Config']['Labels'].get('io.llmctl.adaptive-idle.overlay-sha256') ==
                self.item['overlay_sha256'], 'h005_overlay_label_mismatch')
        descriptor = image.get('Descriptor')
        if self.item['image_id_domain'] == 'oci_platform_manifest':
            require(isinstance(descriptor, dict) and descriptor.get('digest') ==
                    self.item['image_manifest_digest'], 'h005_manifest_descriptor_mismatch')
        return result

    def validate_container_image(self, container, evidence):
        expected = self.validate_evidence(evidence)
        require(container.get('Image') == expected['image_id'] and
                container.get('Config', {}).get('Image') == self.IMAGE_REFERENCE,
                'h005_container_image_mismatch')


def text_oci():
    return TextOCI()
