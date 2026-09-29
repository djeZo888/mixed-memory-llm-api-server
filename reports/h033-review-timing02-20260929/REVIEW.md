# H033 REVIEW-TIMING02

Independent source review: **PASS, no blocking finding**. No production changes,
test reruns, VM probes or generation were performed by this reviewer.

Native session: `01a0edaa-bcc0-7cb1-a08c-434c3a6d5430`.
Review base: `37f9aa581c3f860e2860a9c2324524daeb5cf437`.
W2 reviewed commit: `20108e59420ff482b425075c1071b23f88dc0c07`, compared with
`aec3d5964c4abd412872f496d03a397f8612dc57`; bundle objects imported without
changing the worktree. PERF01 `9aba9d30fbff27a87daba5bb18c66bcf91ed7419` is
already integrated; its 40 passed tests were reused, not rerun.

## Findings

- `codex-engine.ts:573–592,715–718` follows the pinned native contract: summary
  contains exactly the last completed nonempty eligible agent message. The
  completed ID, text and phase must match; explicit commentary cannot replace
  the candidate. Omitted-last, reordered, empty or mismatched summaries reject.
  Missing/non-summary views retain unclassified text rather than guessing.
- `codex-engine.ts:313–328,539–571` associates an absent-phase final only after
  successful owned root completion and native/gateway settlement. Failed,
  interrupted, cancelled, late-cancelled or unsettled cases cannot promote the
  fallback. Explicit native phases remain authoritative. Terminal errors and
  conflicting duplicates reject. `store.ts:617–621` derives finalMessageId from
  the run's final-phase message; deployed end-to-end display remains unverified.
- Independently inspected retained native source revision
  `064c6b8c737f5b41d171fdda80bd9ef10ad06eb3`: `thread_state.rs:197–211` and
  `bespoke_event_handling.rs:1321–1345,1498–1558` support the eligibility,
  singleton-summary and failure/interruption rules. Their hashes match the proof.
- The retained H032 final rollout's complete hash matches the live-failure
  fixture; message and task_complete payloads match actual lines 28 and 31.
  Original child failure is preserved. No content-based reasoning split or
  rewritten success is introduced.
- Skill, overlay and both model instruction templates consistently require
  `image_capabilities({})`, distinguish it from resource/skill lookup, and permit
  MiMo only when host-enabled. Native-media limitations, canvas approval,
  shared queue and separate image settlement remain. Non-instruction model
  fields are unchanged. Logical policy remains
  `sova-codex-0.158.0-qwen-text-v2`; independently recomputed separate tool digest
  `b71c0ab62310df062f9df2eba464ef1c0fffe1a108d07778b50d7f3ebb4653c5`
  matches launcher, shell verifier and Containerfile. Capability wording scopes
  H030 small compaction success and H032 PDF partial success accurately;
  specialist gates are unchanged.

## Evidence and limits

Supplied logs record 51 association/capability PASS, 41 guidance/contracts PASS,
one optional native SKIP, zero failures. These are inherited checks, not reviewer
executions; the totals are not asserted to be disjoint. Empty typecheck/build
logs alone do not prove exit status; the packet reports success.

The live H032 AppServer transcript was not retained. Its test projects real
rollout content into the protocol. The separate pinned-native fixture contains
actual AppServer events from a scripted provider, not a model qualification.
Its original raw capture was not located locally, so that capture provenance
remains packet-backed. Native source and live-rollout hashes were independently
verified. This review does not prove deployed behavior or enable any gate.

Exact SHA256 pins:

| Artifact | SHA256 |
|---|---|
| W2 bundle | `e9a1dce31a5e83b043493e341a75555c6e755b1c155330b4511c0f18adc24c7a` |
| W2 patch | `0aaf6de397bad0440aed1295932a35ecbc5f661cea9eeadc2564d0c57c78071f` |
| Association proof | `4ea241b5f1115a6284843d4852fd078e370475f70cb28f4bced310330d23ca90` |
| Association log | `f113141869e03b57307940e0286093ee6eb67499e1a84995a0b83728dd67adeb` |
| Guidance log | `a42c498bdfa2a264d0483624410017ea8448b67a2bc2cc06292591421d856863` |
| Retained native thread_state.rs | `a3f9d252d61c9a78c50db119c87796cec92a734971762c1ba013791af2556e33` |
| Retained native bespoke_event_handling.rs | `9749c6cd7938b9af6317a7fa01171d66559333b7cbb945565b8445b144bc846a` |
| Retained live final rollout | `70ef7e482311952e7e461ee8fcfe59205f771763df36e541ddad0abc6e16f923` |

## Minimal remaining actual gates

From H032 next-execution/checkpoint, refined by H030/H031 retained passes:

1. Complete MiMo child final, parent receipt and settlement through Codex and
   MiniMax. Current child shell/results PASS alone is insufficient; original
   H032 count failures remain failures. W2 owns current acceptance evidence.
2. Image actual generation, guarded edit and child use, including the retained
   and an ordinary request; source guidance is not image acceptance.
3. Deployed authoritative final association and honest tool-failure reporting.
   PDF numeric answer, page citation and readable artifact already passed.
4. Healthy-lane fallback, remaining shared gateway queue/child cancellation,
   fresh restart, browser reconnect/offline. Reuse H031 workspace-queued Stop,
   active continuation settlement and API cursor replay; those do not prove
   native process interruption or browser reload.
5. Bounded actual count comparison remains unmeasured pending W2's explicit
   idle/readiness/source grant. No broad workflow/benchmark is introduced.

Reuse H030 coding, follow-up, dedupe, small compaction/recall and H031 retained
continuation, handoff and both small 480K lane passes. Do not reopen lifecycle
recovery, optional Ada, long-context or benchmark work. See
`h032-next-execution.md:19–64`, `h031-codex-checkpoint.md:32–37`,
`h031-codex-results.json:20–28`, `h030-codex-checkpoint.md:13–16`.
