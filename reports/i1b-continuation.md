# Required I1b continuation — full installer incomplete

Historical I1 handoff. I1b's bounded source implementation is recorded in
[I1b report](i1b-runtime-acquisition.md). Current required continuation is the
[I1c checklist](i1c-installer-checklist.md), with blank-disk work assigned to I1S
and package execution pending reviewed I1R/L1 ownership integration. The original
I1 scope/evidence below is retained for provenance.

I1 deliberately finishes the preflight/storage/prerequisites/driver source
boundary. It is **not** the user's requested complete fresh-machine installer.
No READY summary is possible in this revision. Do not remove the full-apply
exit78 gate until every selected stage below exists and has tested postconditions.

## Continue from the committed I1 branch

Use `milestone/i1-fresh-linux-installer` plus coordinator-reviewed L1/F1S updates.
Review `docs/orchestration/installer-plan.md`, `docs/installation.md`, I1 report,
package lock/source evidence, and the coordinator's current integration handoffs.
No task sibling file or memory belongs in Git. Preserve author and committer
`CodexAIagent <133749519+djeZo888@users.noreply.github.com>`.

I1 source scope made no live host changes. Do not infer live install/adoption
permission from its partial command examples. Keep active downloads under their
existing acquisition owners; an I2 adoption must coordinate lifecycle ownership.

## Required remaining source stages

1. Finish full preflight: network/apt locks/service ownership, profile hardware
   support, actual pins and root/data shared budget before selected effects.
   Plan must report failures concretely, not hide missing prerequisites.
2. Add a shared directory-FD anchored open/write/rename primitive with fstat
   device verification, so a mount detach between check and write cannot cause
   root fallback. Repeated path-based checks in I1 detect observed loss but do
   not close that race. Complete opt-in blank-disk provisioning only from reviewed by-id plan and
   repeated non-use/identity/root/boot/LVM/RAID exclusions. Existing/mount paths
   are implemented; never adapt the old `/dev/sdb` script blindly.
3. Docker/containerd/toolkit: install exact locked packages, preserve compatible
   daemon configs/data, place persistent roots on data **before first start**,
   bounded logs, root/data guards and actual GPU-container gate. Docker/toolkit
   pins are in the lock; that is not their installation implementation.
4. Runtime: adapt the exact D1 Dockerfile/pinned source recipe to registered roots;
   local image ID is evidence, not a public registry reference. Pin and retrieve
   SGLang's actual registry digest. Preserve runtime/profile/parser settings.
5. Acquisition: generic roots and shared disk budgeting; exact approved manifest,
   resume HTTP Range safely, preserve partials, hash every file, atomically promote,
   generate protected completion evidence, no duplicate HF weight cache. D1/F1A
   helpers have current-host assumptions and must not be invoked blindly.
6. Service: L1 root-owned registered paths + one dedicated or distinct filesystem;
   consume same lifecycle lock lease without deadlock/gap; installed trusted source;
   generate/reuse newline-free private API key; consume F1S wrapper + actual
   pinned-image sentinel auth proof before real secrets; systemd exact mount
   ordering, bounded restarts/readiness deadline, stopped intent and rollback.
   Provision the separately reviewed U1 authenticated model catalog/switch API
   through the same lifecycle owner when integrated; no browser UI on the server.
7. Client/access: locked Linux Node/npm + V0 OpenCode lock, ordinary user ownership,
   explicit workspace, safe resumable staging/promotion for V0 partial prefixes,
   SSH tunnel helper and localhost provider with protected key reference.
8. Acceptance: distinguish live/ready, exact model, unauthenticated rejection,
   bounded generation/streaming/tool/result continuation, real bounded OpenCode
   edit/test loop on client. Server-only cannot execute coding tools. Record any
   required external client gate pending until real evidence is available.
9. Make default `apply --yes` execute all selected applicable stages, `resume`
   recover without undocumented manual steps except genuine reboot/firmware,
   verify actual postconditions, and print READY only after all required acceptance.
   Upgrade/migration must safely reconcile I1 config/source/lock hashes; do not
   remove identity guards to continue from modified source.

## External interfaces to reconcile

- **L1:** extend D2's hard-coded paths/two-mount validation to trusted registered
  roots. I1 registry schema1 has `data`/`models` records with `path`, exact `mount`,
  `uuid`, `fstype`; `source`, `device`, `parents` are observations, not immutable
  names across reboot. `roots` maps models/cache/build/logs/services/secrets/state.
  Acquire `/run/llmctl/lifecycle.lock` once across installer/lifecycle transition;
  a reviewed held-descriptor/in-process dispatch interface is required.
- **F1S:** installed wrapper SHA must equal reviewed source; completion manifest
  exact48 artifacts/revision/hash; `auth_gate_passed` needs actual pinned-image
  sentinel verification, never source mocks. Final profile flags come from the
  reviewed adapter, not copied early handoff constants.
- **V0:** current bootstrap refuses incomplete prefixes. Provide/review a safe
  immutable staging-prefix/promote protocol or upstream resume extension. Never
  delete partials or claim `--version` is the real coding-agent loop.
- **F1D/D3:** full-model context/fit/peak/auth/parser proof is separate; I1 disk
  sizes and synthetic hardware fixtures are not measured RAM/VRAM requirements.

## Required independent validation

Run I1 fixtures, add stage command-boundary/failure/resume/idempotency tests for
all new stages, run disposable Ubuntu package/client paths and disposable Linux
loopback disk paths where feasible, then coordinated non-destructive adoption.
Record every evidence class separately. Full fresh-host GPU installation/reboot
remains **NOT_TESTED** unless actually run on a disposable GPU host.
