# I1b bounded stage interfaces

Source-only integration from I1 `722050fdcb6de4a9f56a5488b705998a1d82ce85`.
No live installation, download, service restart or model activation is authorized
by this handoff. Full installer remains incomplete until I1c passes.

## Dispatcher and ownership

Public `install.sh plan|apply|resume|status|verify` retains I1 configuration,
registered storage and protected state identities. Additional explicit boundaries
are `--through container`, `--through runtime`, and `--through acquisition`
(`models` is an alias). `runtime` includes actual GPU-container gate; acquisition
includes every selected GLM/Qwen artifact. Full apply/resume remains exit 78.
`ready` remains false even after bounded stage verification.

Current package execution also remains exit78 pending reviewed I1R/L1 source,
authorized same-lease export and transaction admission. No raw descriptor bypass
or method-name check enables it. Runtime supervision must retain ownership across
installer SIGKILL. The coordinator's developing handshakes are not installed
contracts; the public source checkpoint is intentional until reviewed integration.

One uninterrupted `/run/llmctl/lifecycle.lock` context encloses all stages. L1
owns canonical `LifecycleLease` and Manager borrowing; it is not present in this
checkout. I1c must replace the existing context with that reviewed API without
release/reacquire or a second lock. I1b does not call Manager or create lifecycle
code. A per-acquisition-file FD flock additionally rejects accidental duplicate
engine invocations; it does not replace the global installer lease.

## Python stage API

- `ContainerStage(config, runner, guard, ...)`: `check()/apply()` and
  `check_gpu()/apply_gpu()`; container package/config postconditions and separately
  identified real GPU container evidence.
- `RuntimeStage(config, runner, guard, ...)`: `check()/apply()`; selected immutable
  runtime artifacts, inspected image IDs and protected source/build/CLI evidence.
- `AcquisitionStage(config, runner, guard, ...)`: `check()/apply()`; immutable
  selected manifests, aggregate concurrency/reservation, computed file hashes.
- `guard()` returns I1 schema1 registration and revalidates mounted identity.
  `scripts/install/storage_io.py` owns directory-FD anchored I/O independently
  of L1 lifecycle/common modules. Its final API is documented in that module.

Checks are observations, never a successful stage marker alone. Rechecking model
completion computes every expected file SHA256; it may be slow for 547.7 GB.
Stage evidence records synthetic test provenance separately from actual command
execution. No synthetic evidence satisfies a production GPU gate.

## Acquisition completion contract (schema 1)

Protected `<roots.state>/acquisition/<selection>.complete.json` contains selected
manifest SHA256, repo/revision, registered destination and storage identity,
exact artifact paths/sizes/computed SHA256, total verified bytes and completion
time. Expected source manifests are never rewritten. This proves acquisition
only; it asserts no auth, model load, health, generation or tool support. I1c/L1
must explicitly consume/validate this contract through their reviewed interface.

## I1c remaining interfaces

Fresh I1S owns opt-in blank-disk mutation from the reviewed identity plan (see
`docs/orchestration/i1s-storage-handoff.md`); I1b leaves storage.py untouched. I1c owns protected
installed source/release and identity migration; L1 lease borrowing, key/instance
and boot lifecycle; F1S native pinned-image sentinel auth proof; U1 authenticated
catalog/switch service over existing Manager; V0 ordinary-user staged OpenCode
bootstrap; chosen-role real health, generation, streaming, tool continuation and
client edit/test acceptance. No browser UI or agent tools belong on the API VM.
