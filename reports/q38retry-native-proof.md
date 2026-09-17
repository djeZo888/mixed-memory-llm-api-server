# Q38RETRY actionable warmup child diagnostic

Observed2026-09-17T04:29:00.354966Z in one authorized targeted noGPU observation at original integration357358ab; task-only runner/provenance diagnostic overlay, unchanged product launcher/containment/capture/device policy. Original exact-source128K FAIL remains unchanged. No256K, extension, auth receipt, publication, model load, inference or accepted context.

| Scenario | Exit | stdout | Marker count | stderr | Three clauses |
|---|---:|---|---:|---:|---|
| warmup-auth-failure | 1 | exact40-byte fault marker | 1 | 0B | true / true / true |
| warmup-timeout | 2 | 331-byte closed FAIL JSON | 0 | 0B | false / false / true |

The timeout child fails in its ORIGINAL cache/device preflight: `cache_probe.py:198`, `require(relevant <= CONTROL_NODES, "gpu_device_node_present")`, propagated as `cache_probe_child_failed` (original runner:669; diagnostic overlay:672). The closed child failure records ProbeError at198. Timeout-child phases are empty and startup deadline is null: it never entered `make_warmup` and never created/armed the startup watchdog. Thus the observed failure is NOT the hypothesized0.4-second pre-marker watchdog race. Child180s / request600s / watchdog0.4s remain unchanged; auth-failure watchdog7200s remains unchanged.

The auth-failure child did enter native engine setup, Uvicorn capture, synthetic HTTP binding and authenticated warmup; it wrote exactly one marker and exited1 on the main thread after the intended401 rejection. This is diagnostic partial evidence, never whole auth acceptance.

Exact device predicate: relevant names are /dev/nvidia* or /dev/dri/* plus exact /dev/dri,/dev/kfd,/dev/dxg; all must belong to CONTROL_NODES. The false subset relation proves at least one disallowed relevant name existed in this observation. Its exact name/type/creation origin was NOT captured by the original probe and is UNKNOWN. No device/cache gate was bypassed or relaxed; no additional native observation is authorized by this report. Worker2 can review sequential-child device-state contamination and native imports from the pinned sources; a further specific device-name observation requires root coordination in this same session if needed.

Observation boundary: targeted parent skipped the already-completed positive scenario; child order and reject policy were preserved. Original parent retained no child operands, so this identifies the targeted observation's exact cause and a concrete explanation for the same compound failure, not retrospective proof of the original child's scenario/value.

Original exact-source container878e8cd6aee80dc5d3968395311f68d7b8b0536553c63f8d7b8595ef37e72eae removed and independently absent. Diagnostic container9bfa6cfc7be3c0a7b987823f9348ec8301d0317ece024caf3630a818e7ed1f78 / q38b-fixture-9bea1568b717d6216605de90138e840b removed normally, independent ID/name absencePASS. Final postguardsPASS, all backends stopped, no new/changed Apport. Canonical lease released04:29:00.915998Z; SSH exited0 and worker request context released. Session remains available for coordination; no further VM operation planned.

Raw child/native streams remain private under worker-private-warmup-observation, outside Git. All safe clause/timing facts are in warmup-child-operands.json. VM stage/evidence: /data/build/q38retry-20260917/warmup-observation/source and /data/logs/q38retry-20260917/warmup-observation. No healthy backend was stopped by reporting.

Precision from pinned source review: this is a names-only refusal before that call's lstat/type/device-number checks; it does not establish actual GPU exposure. Allowed names are exactly /dev/nvidia-modeset, /dev/nvidiactl, /dev/nvidia-uvm and /dev/nvidia-uvm-tools. A disallowed directory, symlink, regular file or device all trigger the same code. The probe invokes verify_isolation both before and after its own native imports/resolver work, and the shared line198 does not identify which invocation failed. Exact offending name/type, entry-versus-exit probe boundary and creator remain UNKNOWN. No allowlist relaxation is justified.

## Exact-source baseline and continuation

Approved source357358ab native128K ran once04:20:50.624424–04:21:17.611836Z. It failed the compound negative-child predicate at original runner933; original first cause does not identify which child. Original native stdout163B SHA2561242a34e635aec9ec0bd4c356b5a2fee097203a0a53079276d66970924739828; stderr0B. Fresh task staging verified all9 exact committed files; no source edits were made in this checkout. Current guard identity/mode root0755 and dependency root0644, registered mounts, cached OCI image and NETPATCH helper/receipt passed. Root available after pair5,562,449,920B, below6GiB warning but above unchanged4GiB stop. No broad inventories, full weight hashes, tests, download, host policy or service changes.

The one additional diagnostic was explicitly authorized via task-root coordination in the same session. Only its private fixture runner/provenance differed; production launcher, driver, auth/cache/device checks and reject predicate stayed unchanged. That observer is not exact-source fixture acceptance. Exact safe source/terminal/operand evidence is in [q38retry-evidence](q38retry-evidence/result.json).

No production256K or1M context/allocation/memory/pool/headroom, inference requests, speed or tool behavior was tested. Preserved selected stopped GLM native1M is prior/current handoff state, not a GLM trial here. Worker2 owns any source correction; root owns next reviewed exact-source authorization. No retry, profile change or device-policy relaxation was made. This report-only checkout is retained on milestone/q38retry with exact CodexAIagent author/committer; no push. Final task-root result records the report bundle ref/SHA.
