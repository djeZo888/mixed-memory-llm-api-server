# L2 frozen runtime/control handshake

Scope: source only; installer STOPPED. No host access, downloads/builds/runtime,
service, network or disk mutations. Base 6ffd620 plus frozen Q38B
3a470d2b8c90398be0bffe78bccd13fe1c3a0f2e composed before L2 edits.

## Control advertisement API (frozen)

Protected `/etc/llm-server/control.json` stays schema_version 1, optionally adds
`"advertised_endpoint_policy":"private_network"`. No other value, host, URL,
port, path or request override. Absence retains existing loopback/tunnel DTO.
`control.private_network.load_policy()` is called with NO arguments; only its
validated protected fixed policy can provide host/role ports. Catch only
`PrivateNetworkError`; missing/invalid policy falls back to tunnel DTO and MUST
NOT prevent authenticated local startup/status/trusted stop/recovery.
Module source remains root-resident; policy file is NOT a recovery dependency.
Existing validate_installation() credential-byte return remains compatible;
read_advertised_policy() separately resolves the optional protected setting.
`production_application(..., advertised_policy=None)` forwards trusted policy
only to Application public catalog/status serialization. Internal listeners,
Manager endpoints, launch arguments, network checks and mutation semantics stay
unchanged. GLM model identity unsloth/GLM-5.3-GGUF maps to glm; Qwen identity
Qwen/Qwen3.8-27B-FP8 maps to qwen38. Advertisement requires the deployed profile
port equal the policy role port; alias/port come from that validated profile.
No advertised readiness or occupied-context claim follows from configuration.

## Parallel ownership

Storage agent extracts only read-role/whole-volume validation in storage.py.
Snapshot agent publishes exact two-model selection and receipt input handoff.
Control verification agent exercises actual imports and focused regressions.
L2 root owns endpoint/config glue and exact closure; N1S owns private_network.py
and network assets; D3T owns all llama validation/argv and final GLM profile.

## Protected profile and receipt inputs (frozen)

`configs/control/ai-vm-live-snapshot.json` is an operator source allowlist, not a
new runtime loader. Copy its five exact fixed profiles plus the separately
reviewed D3PD/D3T final GLM runtime, deployment, measured patched-image proof and
recipe/import dependency closure into the same relative paths below the fixed
root source closure. Do not recursively copy configs/deployments: discovery
enumerates every installed JSON there. Exactly GLM5.3 and Qwen3.8-27B FP8 are
offered model identities; Q38 has 128K and 256K declared context variants. GLM
runtime/deployment source/hash, measured image ID and patched proof/recipe closure
remain explicit null pending owner-approved composition. Old D1 runtime/image is
baseline/rollback only, excluded from the fixed selection. The 32K source profile
remains a test reference, not a final product limit. No fabricated image ID or
placeholder deployment enables publication before those owner inputs arrive.

L2VM supplies protected fixed `/etc/local-ai-server/storage.json` schema1 with
whole data/models path/mount/UUID/fstype identity and exact derived roots. No
source fixture or historical instance template establishes the live registry.
Normal Manager reads `{data}/services/llm-manager/deployment-instance.json`
root0600, whose storage_identity equals that whole registry stable identity.
Each model needs a protected generic complete artifact receipt at
`{data}/services/llm-manager/acquisition/{model_id}.complete.json`, linked by
instance model_integrity with verified/revision/evidence/completion_manifest;
Q38 additionally requires the pinned acquisition manifest SHA256 in both.
Model_root must equal `{models}/{model_id}` and all pinned artifact tuples must
match. Q38 runtime_evidence also links the actual reviewed image-auth receipt
at `{data}/services/llm-manager/evidence/sglang-qwen38-0.5.19.auth.json`, with
exact Q38B OCI domain relationship, launcher/source/fixture hashes and checks.
No source-only test can supply production completion or runtime receipts.
Detailed contract and focused verification: `docs/l2-live-snapshot.md`.
