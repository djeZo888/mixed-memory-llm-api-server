# H037 — Codex default and internal Ada image placement

30 September 2026. Execution window10:37:52–13:37:52 UTC.
**Partial checkpoint:** source/config changes are installed; new model starts were
dispatched at13:25:26 UTC. Fresh image/frontier workflows did not fit the window.
Their harness tool gates remain closed. The status collector remains paused, so
the status page is temporarily unavailable. The image binding pin is installed
on disk but has not been reloaded. This is not full production acceptance.

## Delivered changes

- New chats default to pinned Codex0.158.0 using local Qwen. MiniMax remains
  selectable; existing chat engine identities, messages and files are preserved.
- Keep480,000 context /400,000 compaction /65,536 output. The ten relevant
  policy/provider/catalog files are byte-identical to the reviewed main baseline.
  Nominal output headroom is14,464 tokens; no adaptive-output feature was added.
- Central registry plus actual runtime observations determine model/hardware
  identity, capacity and availability. Unknown image placement or missing
  qualification closes that capability without disabling text chats.
- Image selection is protected `gpu_uuid`, bound to the internal Ada.
  Retained200K-Qwen history/weights are separated from active service availability.
- Worker1's stale Mac CLI launcher was repaired; terminal and an actual desktop
  connected event passed. Direct inspection of the Settings UI was unavailable.

## Intended active placement

| Service | Hardware | Capacity |
|---|---|---|
| MiMo V2.6 Pro-RL | System RAM + fast Blackwell, Gen5x16 |480,000 context |
| Qwen instance1 | Fast Blackwell, Gen5x16 |480,000 context |
| Qwen instance2 | Server Blackwell, Gen3x4 |480,000 context |
| Qwen-Image-2.1 | Internal Ada, Gen4x16 | FullHD generation; guarded edits |

The external CoreX Ada is deliberately absent. The internal Ada's200K Qwen
is retired with its private transport. GLM remains dormant; no fallback was
silently substituted. Fresh runtime evidence must establish the final table.

## Verification

Reviewed source: backend6365ca30, harness2f21f831. Backend51 focused tests,
harness38 default/status/registry and55 policy/qualification tests,24 web
checks and both builds passed. All eight source-CI checks passed at12:24 UTC.
The documentation update has a separate pending CI result.

Source/config activation at12:42:45 preserved344 messages,124 runs,151 file
rows and all80 stored engine identities. Two already-uncertain sessions received
ordinary startup status/context metadata and a mutable owner journal changed;
original failures were not relabeled. The remaining28,816 original files were
byte-identical. This is preservation evidence at that bounded checkpoint.

Exact source/config placement and supported MiMo source reconciliation passed.
MiMo and image starts were dispatched normally at13:25:26 UTC; start dispatch does
not establish native readiness. Fresh image output/peak memory, default chat/follow-up,
MiMo child tool/result continuation and final status-page acceptance are NOT_TESTED.
No occupied480K/950K test or long compaction paste was repeated. Native Codex
vision remains unsupported; MiniMax recognition is partial. PDF/OCR and creative
image tools are separate capabilities.

## Upstream Codex

Upgrade held as requested for a substantial delta: pinned release versus audited
main changes1,281 files, including app-server protocol/provider/runtime paths.
Sova uses an official binary and external adapters, not a local Rust fork.
The Mac CLI update to0.159.2 is separate. See the upstream audit for exact
revisions and the proposed bounded compatibility upgrade.

## Delays and retained outcomes

A source-fixture session reached its bound after exporting the reviewed code and
51 passed checks; its termination remains recorded. Delivery04 refused before
VM writes because prose said32 files while the authoritative image map held33.
That count was corrected. Delivery05 preserved its partial result: the native
Ada Qwen stopped, but its independently owned private socket still listened.
Continuation06 retired that socket normally. Its promotion refused a physically
settled MiMo unit still marked failed255 by systemd. After preserving that outcome,
Continuation07 used normal reset-failed, promoted the exact staging and reconciled
the source successfully. A transient lifecycle-lock refusal was retained. The late
launch receipt proved successful normal dispatch; Continuation08 avoided replaying it. Status polling was temporarily paused to
reduce lifecycle lock contention. No guard was waived and no model/benchmark
was redownloaded or repeated.

## Publication

Reviewed source and dated documentation are on the H037 review branch, PR11.
PR11 remains draft and unmerged. The next bounded task must verify the existing
model starts, finish current owner/config/status readback, run short scoped
Qwen/image/MiMo workflows and review optional-tool promotion. No fresh long-context
test, upstream upgrade or model reload is required merely to collect this checkpoint. Credentials, private transcripts and bulky traces stay
outside the repository.

All paid worker sessions are closed. Final sessions reached their deadlines;
actual native−15/outer143 outcomes are retained. No later VM probes or operations
were performed. Restore the collector and reload the on-disk pin in the next window.
