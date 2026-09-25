# H005 protected source and runtime transition proposal

Status: **source proposal; activation binding incomplete**. This document does
not authorize deployment, publish acceptance, change a pin, or establish a live
result. The owner task starts at
`deba8af306cb0b3f87ddf8a2ed669d2eae1ac076`; the parallel runtime task owns the exact
scheduler overlays and text readiness launcher. Root must review their combined
immutable candidate before assigning a fresh activation session.

## Existing checks remain authoritative

`concurrent_profiles.check_acceptance()` requires the protected schema-2
`root-reviewed-dualq-480k` receipt at the registered data suffix
`services/llm-manager/evidence/dualq-480k.accepted.json`. The instance reference
contains exactly `path`, canonical JSON `sha256`, and `reviewed_source_commit`.
The receipt binds the complete current `source_identity()`, both modes and all
slot proofs. Changes to `manager.py`, `concurrent_profiles.py`, control source or
pinned launcher bytes invalidate the prior exact source acceptance. Source
checks and regenerated fixture receipts do not replace that acceptance.

The image `Runtime` independently reads protected registered `config.json`,
checks checkpoint revision/size/count/receipt digest, and verifies every
`source_sha256` entry against protected installed runtime files. The control,
image API and node installation checks protect their own import closures.
Protected ownership is not an exact-source digest: root's combined delivery
manifest must also cover those files, units, fixed adapters and policy source.

This proposal changes none of these checks. An incomplete/mixed source,
receipt, instance, image config, overlay or import closure must stay closed.
An old receipt is retained as historical evidence, never relabeled as proof
that the revised scheduler, launcher or owner ran successfully.

## Exact candidate record required before activation

Root's frozen source review must have a machine-readable manifest with all of:

- Owner and runtime source commits, exact base commits, verified bundle hashes,
  and an integrated candidate commit. No dirty tree may stand in for that commit.
- Every current `concurrent_profiles.source_identity()` path and SHA256, plus
  the complete control recovery/normal and node source closures and image
  owner/API/runtime source, units, fixed recovery helper and network policy.
  Include newly imported `hardware_policy.py` and `hardware_latch.py` explicitly;
  a changed caller hash alone does not bind a dependency's bytes. The final
  reviewed `source_identity()` and closure declarations must include every new
  dependency they are intended to enforce. Do not omit a mismatching path.
- An old/new digest row for every changed critical path, with its owner and
  reason. Compare against protected *installed bytes*, not only a Git ancestor.
  Record full bytes' SHA256, never stripped/normalized scheduler hashes.
- Parallel runtime's exact overlay artifact hashes, original/target in-container
  paths, exact original and patched file SHA256, upstream commit and dependency
  image identity, patch order, and a closed expected file set. Patch application
  must reject missing, extra, partial, already modified or wrong-base source.
  Include both text launcher readiness bytes and image launcher bytes.
- Guarded build receipts and the new immutable derived runtime-image identities,
  with unchanged parent manifest/config identity lineage. Reverify the baked
  overlay receipt, verifier and every final in-container native file before
  admission. No derived image exists at this source checkpoint; parent-only
  historical image identity cannot stand in for a changed executable image.
- Raw and canonical hashes of the retained old text receipt/instance, raw
  hashes of image runtime/API configs and checkpoint receipt, original source
  manifests, installed storage guard identities, and root's review reference.
  Credentials themselves never enter this record.

A source-only review manifest may use
`status: SOURCE_REVIEW_ONLY`, `activation_binding: INCOMPLETE` and
`runtime_overlay_proof: null` while the other task is still working. Those
values are explicit blockers, not values any production acceptance verifier
may accept. The final manifest must be regenerated **after** both workers stop
editing and must match the exact reviewed delivery. Its SHA256 belongs in the
root review, task result and later protected transition evidence.

The retained extraction's text image identity has two distinct meanings:
manifest digest `sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262`
and OCI config digest
`sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813`.
The parallel task's `TEXT-IMAGE-DIGEST-PROVENANCE.json` binds that relationship.
A Docker `.Image` observation is not permission to exchange those meanings or
to rewrite existing runtime pins. Record each field with its original meaning
and verify against the exact extraction. Runtime `RUNTIME-INTERFACE.md` and the
final overlay proof remain required inputs; this proposal does not manufacture
them from the extraction inventory.

The runtime handoff observed during this owner checkpoint lists candidate
`4eead577a45abbb7c1cf9134e20caf1114a5e3d3` but explicitly marks it
**SUPERSEDED — do not build**, pending cancellation/error drain corrections.
Its hashes are provenance for that superseded candidate only. This owner
checkpoint therefore does not copy its launcher bytes, update critical pins,
or bind it as the runtime overlay proof. The replacement exact commit, closed
file/hash inventory and verified bundle remain required before integration.

## Preserve measurements and bind changed executable behavior

Keep original weights/revisions and checkpoint receipts, runtime base images,
FP8 weights/BF16 KV, both configured 480000-token Qwens, shared CPU masks,
no-swap memory caps, 72 guest vCPUs, the 15% sampled required-working-set margin,
UUID placement, text reserve policy, Ada generation/editing profiles and Full HD
crop semantics. The added server GPU remains unassigned. No capacity, memory,
context, geometry, concurrency or new-model expansion is part of this change.

For each old mode/slot proof, preserve the exact original measured allocation,
working-set estimate, host peak, GPU total/free, largest occupied context and
measurement evidence references. Record their observation dates and source
identity as **inherited historical measurements**. Configured 480000 remains
separate from measured occupied context. Do not change an old measurement or
create a PASS field because an offline test passes.

There are two different amendment cases:

1. If only owner/control critical bytes change and all profile/runtime/launcher
   pins remain byte-identical, the existing schema-2 compatibility procedure in
   [the retained rollout handoff](qwen-image-2.1-compat-rollout.md) can preserve
   both mode proofs. Root explicitly reviews applicability, changes the reviewed
   source commit/current critical hashes, and appends the protected amendment
   evidence reference. The old receipt bytes and digest remain retained.
2. A changed runtime image must bind its actual derived immutable identity and
   build/overlay receipt as well as the changed source. A changed pair launcher additionally conflicts with
   `proof.pair_launcher_sha256 == PINS[pair_launcher]` and the existing native
   authentication checks. Merely replacing `source_sha256` cannot satisfy the
   production contract honestly. Root must review exact changed launcher pins
   only after the runtime worker supplies them, and obtain fresh actual-image
   authentication/readiness/alias proof for each Qwen slot/port tuple. Keep the
   original slot proofs as immutable historical evidence. The successor receipt
   may bind the newly reviewed launcher and its actual native-auth result only
   with a protected amendment explaining which execution facts were rerun and
   which capacity measurements are inherited. Do not copy old auth PASS values
   to changed launcher bytes. Both modes still require their complete existing
   proofs; an untouched GLM launcher retains its own original lineage.

The current schema can carry explicit amendment/evidence references while
retaining the existing capacity fields and guards; it needs no permissive
schema or alternate acceptance flag. Root must approve the successor receipt's
exact diff. If the runtime overlay changes assumptions underlying the retained
measurements, stop and return that conflict for review. This bounded task does
not authorize silently rerunning large context or memory benchmarks.

Image runtime config updates likewise need exact before/after source and
config hashes plus overlay proof. `source_commit` there identifies pinned
upstream SGLang, not this owner repository commit; do not overwrite it with the
H005 commit. Preserve checkpoint and runtime-image facts and the existing
qualification/capacity receipts. Record changed helper hashes separately from
prior generation/editing evidence. A new service source importing owner code
must point to the reviewed protected release containing that complete closure;
do not mutate an old immutable release or assume a historical `RELEASE` path
already contains new modules.

## Guarded publication and incomplete-write recovery

Only a fresh root-assigned Worker1 activation session may perform these steps.
Resolve current installed guard/source identities and capture actual ownership,
boot, intent, pending operations and direct-client impact first. Obtain the
already required interruption authorization and use the established maintenance
path. Harness dispatch freeze does not prove direct clients are idle.

Under the existing canonical lifecycle lease, revalidate registered storage and
protected operation paths before and after each write/change. Retain verified
exact old source/config/receipt/instance bytes and their hashes beneath protected
registered evidence roots. Keep prior recovery artifacts and journals.

Publish the reviewed release and complete closures through the existing
protected deployment path. Bind the exact runtime overlays/readiness launchers;
verify originals and resulting bytes against the reviewed manifest. Re-read the
old receipt/instance/config identities immediately before replacing them. Use
the existing Manager persistent/anchored JSON writer and image registered
anchored writer, preserving modes, single-link files, fsync/rename semantics and
current source/config guards. Publish the text successor receipt, then its exact
instance reference. Image source/config and standalone node/network policy are
separate reviewed steps.

The first installation also needs the once-only protected latch initialization
specified in [hardware policy](hardware-owner-policy.md), and the registered
node journal parent and canonical `/run/llmctl` provisioning. Ordinary starts
must never recreate a missing latch store. Render the node unit's registered
data root from current protected registration; no root-disk fallback is valid.

Individual file replacement is atomic. The source/overlay/receipt/instance/image
config collection is **not one atomic transaction**. An interrupted publication
stays in maintenance; no model start occurs on a partial combination. Re-read
all outputs and their complete digests, reload source consumers without mixed
old Python modules, then run existing acceptance for both modes/all three text
profiles and image configuration verification. Do not bypass a mismatching pin,
ignore an omitted closure dependency, weaken storage guards or run an old helper
to force a partial candidate to start.

Use existing model owners for the captured intended state. Hardware latches,
request quarantine, manual-recovery gates and current resource admission remain
in force. A source transition, daemon restart or GPU reset does not clear a
positive boot hardware latch.

Rollback restores a root-reviewed matched source/overlay/config/receipt/reference
set under the same owners/guards. Preserve failed candidate evidence. Do not
restore stale runtime state over current journals or claim that byte restoration
proves readiness. If the retained old set cannot admit current hardware or state,
stop for root's recovery decision; no topology change or guard bypass follows.

## Gates this source proposal cannot close

Final runtime file/hash handoff; combined source and closure review; exact
protected transition/receipt/config diff approval; current installation identity
and rollback capture; actual-image checks for revised launchers; separate node
port/network policy publication; serial live owner/action/reboot acceptance;
authenticated passive readiness; and the authorized at-least-11-minute idle/wake
measurement remain live/review gates. A reboot operation succeeds only when a
later observation proves a changed boot. No offline fixture here proves those
outcomes or a deployable release.
