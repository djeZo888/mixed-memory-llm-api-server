# Q38S → I1c exact acquisition mapping

Source-only handoff. No installer edits, layer pull, model download, VM access or acquisition PASS here.

## Immutable registry entry

- Model ID `qwen38-27b-fp8`, model profile `configs/models/qwen38-27b-fp8.json`.
- Manifest `reports/q38s-acquisition-manifest.json`, SHA256 `726012378a40f648a104230d3f5ed5d6bc505cbd09b32918fc29aa81c0f075f2`.
- Repository `Qwen/Qwen3.8-27B-FP8`, revision `017b9c7af6b5689d5dd426a76e0bc077eb5ca20a`.
- Destination comes only from canonical L1 `binding.path('models', 'qwen38-27b-fp8')`.
- All 81 artifacts must remain: 66 weights, 30,890,049,597 total bytes; 30,866,866,928 weight bytes.
- Runtime ID `sglang-qwen38-0.5.19`; deployment IDs `qwen38-27b-128k` and `qwen38-27b-256k` share this acquisition. Add via declarative generic selection registry, not per-model installer branching.

## Hash provenance correction

The normalized manifest preserves every reviewed Q38R row losslessly. For ordinary Git payloads, `git_blob_sha1` retains the expected `SHA1("blob "+size+NUL+payload)`. For 67 LFS payloads (66 weights and tokenizer.json), the Git SHA identifies the LFS pointer, not the downloaded payload; it is preserved as `lfs_pointer_git_blob_sha1`. Their downloaded payload must match `sha256` and the identical `lfs_sha256`. Do not compute payload Git SHA against the pointer's hash. Source `metadata_identity`, verification status and revision remain present. Neither publisher metadata nor prior small-file verification is an acquisition receipt.

## Generic acquisition corrections required

Read-only current sibling `L1/repo/scripts/install/acquisition.py` has these bounded integration gaps:

1. `validate_manifest` requires an alphanumeric/underscore/hyphen first filename character and therefore rejects `.gitattributes`. Permit safe leading-dot names generically while retaining normalized path checks, no empty/dot/dotdot components, no collisions, and partial/rejected-name protections.
2. It rejects `size_bytes <= 0`; this model includes the publisher's empty `safetensors-md5sum.txt`. Permit exactly nonnegative integer size and validate exact empty-payload SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`. Preserve the zero-byte artifact. Generic acquisition must create/read/hash/promote an empty payload safely; no invalid HTTP Range request or dropped row.
3. Current `selected_manifests` selection enum is `glm/qwen`; I1c's approved declarative registry must supply the Q38 selection. No model-specific downloader or hardcoded paths.
4. Model-root path and manifest identity belong to the registered root and immutable registry. Small source-only flags do not authorize acquisition or activation.

## Exact protected lifecycle sealing transform

Current generic acquisition output is schema1:

```json
{
  "status": "COMPLETE_COMPUTED_SHA256",
  "selection": "<registry selection>",
  "manifest_sha256": "<pinned manifest SHA256>",
  "repo_id": "Qwen/Qwen3.8-27B-FP8",
  "revision": "017b9c7af6b5689d5dd426a76e0bc077eb5ca20a",
  "destination": "<registered model root>",
  "storage": "<registered identity>",
  "artifact_count": 81,
  "verified_bytes": 30890049597,
  "artifacts": [{"path": "<exact path>", "size_bytes": 0, "computed_sha256": "<actual computed digest>"}],
  "inference": "NOT_TESTED",
  "authentication": "NOT_TESTED",
  "tool_calls": "NOT_TESTED",
  "completed": "<timestamp>"
}
```

I1c must first validate exact manifest SHA, registered storage identity/destination, complete status, all 81 unique records, byte counts, each computed SHA256 against the immutable expected SHA256, and unchanged protected artifact file metadata. Under the same canonical lifecycle lease and anchored writer, publish a distinct root-owned, nonsymlink, single-link mode0600 lifecycle receipt at `binding.path('data', 'services/llm-manager/acquisition/qwen38-27b-fp8.complete.json')`:

```json
{
  "schema_version": 1,
  "complete": true,
  "repo_id": "Qwen/Qwen3.8-27B-FP8",
  "revision": "017b9c7af6b5689d5dd426a76e0bc077eb5ca20a",
  "model_root": "<registered model root>",
  "manifest_sha256": "726012378a40f648a104230d3f5ed5d6bc505cbd09b32918fc29aa81c0f075f2",
  "artifact_count": 81,
  "total_bytes": 30890049597,
  "artifacts": [{"path": "<exact path>", "size_bytes": 0, "sha256": "<verified computed digest>", "verified": true}]
}
```

`destination→model_root`, `verified_bytes→total_bytes`, and `computed_sha256→sha256`; each artifact gets `verified:true` only after the checks. Include every row, using its actual size; the displayed zero is illustrative, not a common size. The lifecycle receipt permits precisely these fields. Keep richer acquisition status/timestamp/storage evidence in the original acquisition report; do not discard it or copy unchecked PASS flags.

Protected instance `model_integrity.qwen38-27b-fp8` must contain `verified:true`, exact revision, exact manifest SHA, `completion_manifest` equal to the registered receipt path, and a nonempty evidence reference. Lifecycle independently checks the receipt and must stat all 81 artifact paths/sizes through canonical L1 before switching. This seal proves acquired-byte integrity only. Actual-image auth, model load, client continuation and occupied-context gates remain independent.
