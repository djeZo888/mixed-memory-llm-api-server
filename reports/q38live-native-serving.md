# Q38LIVE — first native fixture failed; no serving acceptance

At exact approved source `636f847fa2729238db9974c0a7b570960e6974d5`, the one authorized pair invocation stopped after **actual 131072 failed with exit 2**. Actual 262144 did not run. No native auth receipt, production source publication, Qwen load, inference or context-capacity acceptance followed. No retry or source change was made.

## First cause and precise boundary

The first retained native cause is `server_mode_unsupported` in `scripts/runtime/sglang38_file_auth.py:241`, reached through lines 404 and 258. The clause at 240 rejects any missing or truthy field in its 39-field disabled-mode list. Raw argument validation completed; validation of `resolving_view(args)` failed. The exact offending field and whether it was missing or truthy remain **UNKNOWN**, because the retained diagnostics do not expose those operands.

Launch operands: `result=1`, `captured=0`, `engine_calls=0`; exception `LaunchError`. Safe public origin: `run_pinned_image.py:163`, `FixtureFailure`; public code `actual_image_fixture_failed`. This failure precedes launcher key read at 405, auth installation, Engine and Uvicorn startup. It differs from the earlier environment-validation failure; it does not establish every later environment/auth/cache/parser clause.

Root can inspect the pinned resolver/argument-group behavior against this exact disabled-mode predicate. Existing synthetic tests do not establish installed resolved defaults. Production validation, all profiles, timeouts and memory limits remain unchanged. Root transferred one native resolved-field observation to fresh Q38MODE after accepting Q38LIVE release; Worker2 Q38MAX owns the source correction. Q38LIVE did not reacquire ownership or execute that diagnostic.

## Actual execution and cleanup

- Started `2026-09-17T03:57:13.088377+00:00`; native terminal `2026-09-17T03:57:41.891519+00:00`.
- Sole container `98ba9c05a41236787a70be8ca8383db51aeb754ce58ab342ae7ae570f1250d11`, name `q38b-fixture-3a6a926fb4944b3d2184ec56a37dbcf3`.
- Shipped exact-owner cleanup: `QUIESCENT_REMOVAL_VERIFIED`; independent immutable ID/name absence PASS at terminal and final audit.
- Native stdout 270 B SHA256 `c04678baecd75d2a07b62f6074c066fe140e3ff12108a0c78c5bb300bee2ba08`; stderr 699 B SHA256 `45aaf05980d87169d8f9e7ae98bb0401f2e319efb9c40ccc68e9c493ec6c15b6`.
- Raw streams were privately retained **before** postguards, outside Git in `tasks/Q38LIVE-20260917/worker-private-attempt-1/`. First-cause and terminal events were published immediately, before packaging.
- Full registered/root postguards PASS; no new/changed Apport files. Final root free 5,562,400,768 B; below 6 GiB warning remains, unchanged 4 GiB stop threshold preserved.

The existing shipped fixture retained its exact OCI/source/auth/device/cache/parser and unique ownership gates. Host runtime inspection passed: no GPU requests/maps, literal NVIDIA visibility `none`, `compute,utility`, network `none`, read-only source/root, empty private model/key tmpfs, memory 8 GiB, PID 128 and core 1:1. This is partial fixture evidence; no complete native-auth acceptance or production core inspection exists.

## Current host and source identities

Current refresh and final audit passed kernel 6.8.0-139/NVIDIA 595.84 with both GPUs healthy, protected registered ext4 mounts and Docker root `/data/docker`. GLM selected `glm-5.3-ud-q4-k-xl-n76-native1m` remains stopped, as root instructed after HOSTRECOVER. Its native 1M historical readiness is separate from this task; Q38LIVE performed no GLM start, stop or request.

Image reference remains `lmsysorg/sglang@sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262`; config digest `sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813`. This Docker store uses the platform-manifest ID domain, verified by the existing OCI relationship gate. An initial task-only preflight incorrectly compared `.Id` directly to the config digest; it was corrected to use that existing gate before any fixture/container attempt. No image drift or gate relaxation occurred.

Eight exact committed files were newly staged under `/data/build/q38live-20260917/attempt-1/source`; protected records remain under `/data/logs/q38live-20260917/attempt-1`. Production source 77, registry, selected GLM/rollback and protected keys were preserved. Installed control manifest SHA256 `8fe8b5c32da9e212cae7e1d50751deec0d91c8aa1405a10e343fe21b33e712e0`; manifest source commit remains `e8d8bbad3f2f6345295d440b25f084fed83dc734`. Registered guard remains root 0755; dependency root 0644.

NETPATCH helper SHA256 `9ca8ca4b86dbf04988bfe2f8f0a7b3748bbe5d1922c0543f081616f37ec1a6af` and protected receipt SHA256 `f17b33637bbc88c3fcb65d2016a73aa1c071fd383571e1452c01cef677c01eeb` matched current authority. No normal/control/boot source publication or activation occurred. No weight payload was rehashed or downloaded.

## Ownership and untested outcomes

Final read-only audit PASS at `2026-09-17T03:59:46.189632+00:00`. Canonical lease released at `2026-09-17T03:59:46.190198+00:00`; worker request lock subsequently acquired nonblocking and released. Zero owned containers, API requests, samplers, tunnels or backend operations. **Q38LIVE released VM ownership; no further VM operations.** Report serialization is outside model lifecycle handling and cannot trigger a stop/reload.

Production 128K/256K actual pool/context, GPU/memory/dtype/headroom, missing/bad/valid key requests, generation, SSE termination, tool continuation and prompt/decode timings are all **NOT_TESTED**. Occupied long-context quality is NOT_TESTED. Frontend, installer, extra models, co-residency, GLM placement and extended context work did not run.

## Evidence and continuation

[Result](q38live-evidence/result.json), [first cause](q38live-evidence/first-cause.json), [native context terminal](q38live-evidence/context-131072.json), [pair terminal](q38live-evidence/pair-terminal.json), [exact staged source manifest](q38live-evidence/source-manifest.json), [final audit](q38live-evidence/final-audit.json).

Input bundle SHA256 `53144606d2d9b15b8613db5bf2c3e969e4bc11a8237486397f18194f363fd41a`, advertised `refs/heads/milestone/server-completion-20260915`. Worker session `01a0ad7f-2315-7d63-bacb-d20a13d1d6ad`; task scripts, session/events, first cause, live status, publication plan, private streams and result retained outside Git beside this checkout. VM operator SHA256 is recorded in result. Final report bundle metadata follows in task-root result; no push.

Report-only validation: exact source/evidence/hash reconciliation, scope/diff/whitespace, safe-content scan and commit metadata. No broad or installer tests rerun. The earlier reviewed 144 source checks remain source-only evidence.
