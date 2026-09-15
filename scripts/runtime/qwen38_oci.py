"""Exact Q38 OCI identity relationship; pure checks, no Docker/network execution.

The profile's image_id remains the config digest. Docker's observed Id is a
separate, explicitly named domain. Neither a tag nor an arbitrary digest can
supply the relationship. See docs/q38b-oci-contract.md for source verification.
"""
from __future__ import annotations

import hashlib
import json


MANIFEST_DIGEST = "sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262"
CONFIG_DIGEST = "sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813"
IMAGE_REFERENCE = "lmsysorg/sglang@" + MANIFEST_DIGEST
SOURCE_REVISION = "0bcd822377da7b5718e674eaf9c870d349424dd1"
SOURCE_REPOSITORY = "https://github.com/sgl-project/sglang"
MANIFEST_MEDIA_TYPE = "application/vnd.oci.image.manifest.v1+json"
CONFIG_MEDIA_TYPE = "application/vnd.oci.image.config.v1+json"
MANIFEST_BYTES = 13686
CONFIG_BYTES = 65818
IMAGE_ENTRYPOINT = ("/opt/nvidia/nvidia_entrypoint.sh",)
IMAGE_WORKDIR = "/sgl-workspace/sglang"


class Qwen38OCIError(ValueError):
    """A fixed error code, never untrusted inspect/config content."""


def require(condition, code):
    if not condition:
        raise Qwen38OCIError(code)


def same(actual, expected):
    try:
        return json.dumps(actual, sort_keys=True, allow_nan=False) == json.dumps(
            expected, sort_keys=True, allow_nan=False)
    except (ValueError, TypeError):
        return False


def id_domain(observed_id):
    """Admit only the two reviewed immutable descriptors of this exact image."""
    if observed_id == CONFIG_DIGEST:
        return "oci_config"
    if observed_id == MANIFEST_DIGEST:
        return "oci_platform_manifest"
    raise Qwen38OCIError("qwen38_oci_image_id_unreviewed")


def expected_evidence(observed_id):
    """Schema constructor; calling it is not actual-image verification."""
    return {
        "image_id": observed_id,
        "image_id_domain": id_domain(observed_id),
        "image_reference": IMAGE_REFERENCE,
        "platform_manifest_digest": MANIFEST_DIGEST,
        "config_digest": CONFIG_DIGEST,
        "source_revision": SOURCE_REVISION,
        "source_repository": SOURCE_REPOSITORY,
        "os": "linux",
        "architecture": "amd64",
        "image_default_entrypoint": list(IMAGE_ENTRYPOINT),
        "image_default_workdir": IMAGE_WORKDIR,
    }


def validate_evidence(evidence):
    """Validate the entire typed receipt block; never relabel a digest domain."""
    require(isinstance(evidence, dict), "qwen38_oci_evidence_invalid")
    expected = expected_evidence(evidence.get("image_id"))
    require(same(evidence, expected), "qwen38_oci_evidence_mismatch")
    return expected


def _config(config):
    require(isinstance(config, dict), "qwen38_oci_config_invalid")
    labels = config.get("Labels")
    require(isinstance(labels, dict)
            and labels.get("org.opencontainers.image.revision") == SOURCE_REVISION
            and labels.get("org.opencontainers.image.source") == SOURCE_REPOSITORY,
            "qwen38_oci_source_mismatch")
    require(same(config.get("Entrypoint"), list(IMAGE_ENTRYPOINT))
            and config.get("Cmd") is None and config.get("WorkingDir") == IMAGE_WORKDIR,
            "qwen38_oci_image_defaults_mismatch")


def verify_image(image):
    """Check an actual Docker image-inspect object before generating evidence.

    Platform-manifest Id requires the matching Docker Descriptor as observed
    in containerd image inspect. Unsupported/ambiguous representations fail
    here, before a native fixture, launcher, model, or real key can be used.
    Callers additionally check full image environment and runtime command.
    """
    require(isinstance(image, dict), "qwen38_oci_image_inspect_invalid")
    expected = expected_evidence(image.get("Id"))
    digests = image.get("RepoDigests")
    require(isinstance(digests, list) and all(isinstance(d, str) for d in digests)
            and len(digests) == len(set(digests)) and IMAGE_REFERENCE in digests,
            "qwen38_oci_repository_digest_mismatch")
    require(image.get("Os") == "linux" and image.get("Architecture") == "amd64",
            "qwen38_oci_platform_mismatch")
    descriptor = image.get("Descriptor")
    if expected["image_id_domain"] == "oci_platform_manifest" or descriptor is not None:
        require(isinstance(descriptor, dict)
                and descriptor.get("digest") == MANIFEST_DIGEST
                and descriptor.get("mediaType") == MANIFEST_MEDIA_TYPE
                and type(descriptor.get("size")) is int
                and descriptor["size"] == MANIFEST_BYTES,
                "qwen38_oci_manifest_descriptor_mismatch")
    _config(image.get("Config"))
    return expected


def validate_container_image(container, inspected_evidence):
    """Bind a container to the exact image-store domain observed by this host.

    A config/manifest-domain change mid-gate is refused, even though both are
    independently valid image identities. Re-run the complete actual gate to
    establish evidence on a different store; never rewrite an old receipt.
    """
    expected = validate_evidence(inspected_evidence)
    require(isinstance(container, dict) and isinstance(container.get("Config"), dict)
            and container.get("Image") == expected["image_id"]
            and container["Config"].get("Image") == IMAGE_REFERENCE,
            "qwen38_oci_container_image_mismatch")


def verify_registry_bytes(manifest_bytes, config_bytes):
    """Verify supplied small public metadata bytes only; never fetch layers.

    Exact hashes authenticate the reviewed manifest-to-config relationship.
    This is source/metadata evidence, not installed-image or execution proof.
    """
    for raw, size, digest in ((manifest_bytes, MANIFEST_BYTES, MANIFEST_DIGEST),
                              (config_bytes, CONFIG_BYTES, CONFIG_DIGEST)):
        require(isinstance(raw, bytes) and len(raw) == size
                and "sha256:" + hashlib.sha256(raw).hexdigest() == digest,
                "qwen38_oci_registry_bytes_mismatch")
    try:
        manifest, config = json.loads(manifest_bytes), json.loads(config_bytes)
    except (ValueError, TypeError):
        raise Qwen38OCIError("qwen38_oci_registry_json_invalid") from None
    require(isinstance(manifest, dict) and type(manifest.get("schemaVersion")) is int
            and manifest["schemaVersion"] == 2 and manifest.get("mediaType") == MANIFEST_MEDIA_TYPE
            and same(manifest.get("config"), {"mediaType": CONFIG_MEDIA_TYPE,
                     "digest": CONFIG_DIGEST, "size": CONFIG_BYTES}),
            "qwen38_oci_registry_relationship_mismatch")
    require(isinstance(config, dict) and config.get("os") == "linux"
            and config.get("architecture") == "amd64", "qwen38_oci_platform_mismatch")
    _config(config.get("config"))
    return {"platform_manifest_digest": MANIFEST_DIGEST, "config_digest": CONFIG_DIGEST,
            "image_reference": IMAGE_REFERENCE, "platform": "linux/amd64",
            "status": "VERIFIED_PRIMARY_REGISTRY_MANIFEST", "actual_image": "NOT_TESTED"}
