# Q38B OCI identity handshake

Status: source checks only. Actual image, native auth, model loading, live
inference and occupied-context acceptance remain **NOT_TESTED**. The host
fixture must complete before real keys or models are exposed to this runtime.

## Exact reviewed relationship

| Domain | Exact value |
| --- | --- |
| Repository reference | `lmsysorg/sglang@sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262` |
| Platform manifest | `sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262` |
| Config image ID | `sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813` |
| Platform | `linux/amd64` |
| SGLang source revision | `0bcd822377da7b5718e674eaf9c870d349424dd1` |
| Image default entrypoint / workdir | `["/opt/nvidia/nvidia_entrypoint.sh"]` / `/sgl-workspace/sglang` |
| Reviewed runtime entrypoint | `["python3"]` with the separately hashed Q38 launcher |

On 2026-09-15 Q38B fetched only the small public [pinned manifest](https://registry-1.docker.io/v2/lmsysorg/sglang/manifests/sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262)
and [config blob](https://registry-1.docker.io/v2/lmsysorg/sglang/blobs/sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813).
Their raw SHA256 values matched the table: manifest 13,686 bytes; config 65,818
bytes. The OCI manifest's config descriptor contains that exact config digest,
byte count and `application/vnd.oci.image.config.v1+json` media type. The manifest
uses `application/vnd.oci.image.manifest.v1+json`; it is a platform manifest,
not an image index. Config metadata confirms the table, null default command,
and source repository `https://github.com/sgl-project/sglang`. No layers were
downloaded. Existing Q38S provenance records the same public relationship.

The [OCI manifest specification](https://github.com/opencontainers/image-spec/blob/v1.1.1/manifest.md)
defines the manifest-to-config descriptor relationship. Docker's classic
[image inspect implementation](https://github.com/moby/moby/blob/v28.4.0/daemon/images/image_inspect.go)
reports the image-store ID. Its [containerd implementation](https://github.com/moby/moby/blob/v28.4.0/daemon/containerd/image_inspect.go)
reports the target descriptor digest and includes that descriptor. These are
implementation evidence for distinct domains, not a claim that Worker1's
installed daemon was executed. The installer pins Docker 29.6.1; the same
v29.6.1 source URLs returned 404 during this research. Worker1 must observe
its actual inspect representation. An unsupported representation fails closed.

## Historical installer policy and current L2 receipt contract

The reviewed checkout's `scripts/install/runtime.py::_image_valid` already
accepts the historical Qwen runtime's config and platform-manifest identities
from verified registry artifacts only when their reference and platform match
the selected pin. `_record` / `check` preserve the actual observed `image_id`
and demand it again on inspection. Its selection registry is currently
`glm`/`qwen`. Installer work is now stopped; L2 owns the live runtime binding
and approved two-model publication. This Q38B change does not edit the installer
or `versions.lock.json`.

For Q38, `runtime.qwen38_oci` freezes precisely the relationship above.
`verify_image(image)` requires the exact immutable repository reference,
platform, source labels, original entrypoint/workdir/default command and one
of exactly two IDs. A platform-manifest ID additionally requires a matching
Docker `Descriptor` (digest, media type and byte size); a conflicting descriptor
is also refused on the config-ID path. Tags, image indexes, unrelated IDs,
missing or duplicate repository digests, cross-platform/source substitution
and relabeling a digest as the other domain are rejected.

The profile and outer receipt `image_id` retain their original meaning: the
reviewed config digest. The nested `docker_inspect.image_id` is the actual
observed ID, paired with `image_id_domain` (`oci_config` or
`oci_platform_manifest`) and the complete fixed relationship. L2 runtime binding must preserve
this block into protected lifecycle evidence. `validate_evidence` checks the
entire block with type-sensitive equality. The actual host gate and runtime
must compare the receipt block to fresh `verify_image` output; neither may
replace the observed ID with its preferred domain. A created/reused container's
`Image` must equal the observed image ID and `Config.Image` the pinned reference;
`validate_container_image` enforces this. An engine/store change requires a
fresh full gate. Unknown behavior is refused before using real keys or models.

The enclosing auth receipt must still bind launcher SHA256, this support
module's source SHA256, fixture/source hashes, both native context results,
runtime isolation/cache proof and all required auth checks. This identity
module does not manufacture that receipt, verify storage, relax the native
auth gate, select a model, or establish occupied-context/runtime acceptance.

## Source verification

Run `python3 -m unittest tests.lifecycle.test_qwen38_oci -v`. Tests cover both
reviewed observed domains, unrelated IDs/tag references, source/default-process
drift, missing/conflicting descriptors, domain substitution in receipts and
containers, and attempts to synthesize public metadata. The profile and Q38S
public provenance must retain their exact domain mapping.

`verify_registry_bytes(manifest_bytes, config_bytes)` is callable for supplied
public metadata and first checks both exact raw hashes and lengths before
interpreting the descriptor. Its result remains `actual_image: NOT_TESTED`.
It has no network, container, model, key, service or host mutation capability.
