# H024 — Codex integration checkpoint

September 28, 2026. Authorized window: **16:52–18:52 UTC**. Root coordinated and
reviewed; fresh bounded native sessions on both Macs performed implementation,
builds, tests and VM work. MiniMax remains the default. **Full Codex qualification
is incomplete.** No large-context or new thermal benchmark ran in this window.

## Deployed changes

The final combined application was activated at **18:22:15 UTC**, source
`e2e0a946cd4057ee33657a4714da473cf16ab5ca`. Root compared the deployed
implementation with its reviewed integration before adding these documentation
updates. The app and status service
were active; existing application rows, events, files and historical uncertain
ownership were preserved. Status stays on the preceding compatible release.

- Model-specific context, output and compression budgets for Qwen and MiMo.
- MiMo Responses reasoning/tool continuation support and strict serial tools.
- The actual MiniMax `reasoning_effort: medium` request now maps explicitly to
  MiMo thinking enabled. Unsupported or contradictory settings still fail.
- An owned manual compaction action with durable retry identity; original chat
  history and files remain visible. Live recall qualification is separate.
- Private diagnostics bound to one session and actual running request, including
  image-reference staging before run binding. Ordinary capability gates stay
  closed until complete workflows pass.
- Clearer assistant-response labels and capability explanations.

The pinned Codex binary remains **0.158.0**. The thin image is
`d8841743002e16de1f9269a850a2f06a73055688befec4c309778ca8a4c11aad`, with policy
`dd0ff12a651db4cc8521cddb8e5094c5a197ca87cef6b7ec797343da67d9f1ec`.
No model weights, inference runtime, GPU assignment or provider context changed.

## What validation establishes

Worker suites passed affected provider, admission, ownership, compaction,
continuation and UI checks, plus TypeScript/web builds. These suites overlap;
their counts are not added into a misleading total. The last MiMo effort change
passed 24 focused tests and the retained real request offline, preserving all
17 tools, messages and the 65,536-token output ceiling. This is **not** live MiMo
acceptance. Earlier H021 coding, browsing and lifecycle passes remain dated
evidence; they were not needlessly repeated.

| Check | Evidence / outcome |
|---|---|
| App deployment and preservation | PASS at 18:22; readiness metadata is not an inference test |
| Both Qwen native profiles | Ready at 480,000 configured tokens at 18:20 |
| First H024 Codex PDF request | FAIL before generation: `codex_qwen_identity_unqualified`; work settled |
| Exact unchanged Qwen0 verifier | PASS at 18:06; original rejected predicate remains unknown |
| Final serial pre-submit verifiers | Both PASS; serial checks differ from parallel gateway admission |
| Unchanged final PDF attempt | FAIL before generation: HTTP503 `No currently qualified Qwen lane`; settled |
| Later standalone parallel verification | Both PASS at 18:37; did not reproduce the in-app failure |
| MiniMax → MiMo child | FAIL before native inference: candidate flags disabled; parent and requests settled |
| Codex → MiMo | NOT_TESTED; current native MiMo outage blocks it |
| Ordinary Codex images/frontier | Remain disabled pending complete live qualification |
| New image/compaction checks | NOT_TESTED; further submissions stopped after shared admission failure |

## MiMo availability and demonstrated control defect

MiMo stopped at **18:04:30 UTC** after its hardware guard spent five seconds
waiting for the common lifecycle lock: 54 contentions, no refresh obtained.
The last valid sample was 34°C, with no recorded owned OOM or swap. The native
process, GPU compute allocation and cgroup subsequently settled; port 30012
refused connections. A static qualification receipt cannot override this state.
No blind restart or replacement with GLM was performed.

A later read-only reproduction measured `llm-control.service` holding that same
lock for about **9.03 seconds** during a status request; the HTTP call took
17.93 seconds. This exceeds the five-second guard budget and establishes a
current starvation mechanism. **The historical holder at 18:04 is unproved.**
This is not evidence that 950K exceeded model capacity.

The next repair must collect slow status observations outside the mutation lock,
then publish only after bounded identity/generation revalidation. Keep lifecycle
serialization and hardware checks. Increasing guard timeouts or treating unknown
hardware as healthy would hide the defect. See the
[evidence](h024-acceptance02-20260928/RESULTS.md) and
[specific repair with required race tests](h024-acceptance02-20260928/CONTROL-REFRESH-FUTURE-FIX.md).
The existing near-950K failure stays preserved and is not rerun here.

## Fan outcome

The user removed CPU temperature as CHA_FAN3's control source and physically
confirmed that the repeated speed changes stopped. Worker readback confirmed
the source change. **Worker1 made zero BMC writes.** Preserve the working setting.
The requested GPU-driven **40% below 70°C / 80% at or above 70°C** controller is
not implemented or qualified. Integrated GPU fan boost remains separate.

H023's short third-GPU cooling test passed, but its four-way PSU/thermal test
remains **partial** because monitoring failed during the run. All submitted
requests settled; that does not turn incomplete telemetry into a full pass.
See [H023 results](h023-thermal-20260928/README.md).

## Remaining work, in order

1. Repair and measure the control-lock critical section; preserve identity and
   lifecycle race protection. Recover the same MiMo profile only afterward.
2. Capture the exact predicate inside the failing Qwen admission path; don't
   weaken or bypass it. Both serial and later parallel standalone verification
   passed, so concurrency alone is not established as the cause. The gateway
   currently discards verifier rejection details. Complete remaining ordinary
   Codex workflows after this intermittent admission failure is repaired.
3. Qualify MiMo tool continuation and delegation through MiniMax and Codex with
   short tasks. Keep 950K as configured capacity until separately tested.
4. Complete PDF, guarded image generation/editing, compaction recall and remaining
   child/lifecycle cases before changing the default engine or capability flags.
   Cross-engine handoff and durable retry IDs for ordinary user submissions also
   remain on the completion plan; compaction-action retry protection does not
   establish either feature.
5. Implement the requested GPU-driven CHA_FAN3 policy separately, preserving the
   user-resolved source setting and avoiding competing controllers.

The main time costs were current-generation readiness after reboot, exact request
diagnostics, deployment/preservation and the independent MiMo watchdog failure.
This window made concrete source changes but did not complete all live acceptance.
The next work should address the demonstrated control bottleneck first rather
than repeat broad benchmarks or long model loads.

## Final acceptance and settlement

Worker1 exited cleanly at 18:26:45 UTC, with no owned requests, tickets or holds.
Worker2's final health read at 18:37:56 records no active runs, pending gateway work,
owned native work, holds or temporary tickets. App/status are active; both Qwen
instances and the image service report available. Historical two uncertain
owners and three quarantines remain preserved. These healthy aggregate status
values do not override the failed Codex admission.

One read-only parallel verifier check passed at 18:37:33; the exact predicate in
the preceding in-app failure remains **unproved**. Image and compaction cases
were not submitted. Worker2 exited cleanly at **18:38:41 UTC**. Both paid native
workers are closed and no task-owned requests remain. The two-hour window was
not extended. See [machine-readable results](h024-codex-results.json).
