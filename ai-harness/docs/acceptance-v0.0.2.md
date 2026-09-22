# ai-harness 0.0.2 — source/fixture candidate acceptance

**Five original browser fixture scenarios pass; the status finding is corrected
and verified by one focused follow-up. This is not deployed/live acceptance.**
Authorized 2026-09-22; see the [plan](../PLAN-v0.0.2.md) and
[machine-readable receipt](acceptance-v0.0.2.json). The
[0.0.1 acceptance](acceptance-v0.0.1.md) is preserved as historical evidence.

## Identities and boundary

- Candidate UI source: `eb8387c9431b83a50d3c782b45ab7468f8f5a173`.
- Native Codex session: `01a0c7b6-5206-7cf1-9cc5-1df1643f1e61`.
- Existing utility image: `sha256:84ea979312f7743d9ab789465aae7adde92f97d6169744ec7b63776a9482b227`.
- Utility versions: Node `24.21.0`, Chromium `153.0.8010.52`, Playwright `1.63.0`.
- Approved seccomp SHA256: `0474c063b32acee85a1eb5ccfc35f7b1f66278af8da722c45b1d25eb2ae1cfbb`.

The browser served freshly built candidate assets, not the image's old web.
The local build/typecheck passed. H002-WEB dependencies were copied only after
matching package-lock SHA256
`c37680f13608e51a146425b897aca0b781b299d30f626c051139d8e2f284cf09`.
No dependency installation, image rebuild/retag, production app/API, gateway,
inference, credentials, shared-service change or ai-vm contact occurred.
The image is a browser utility identity, not accepted 0.0.2 production runtime.

Rootless Podman used network `none`, no host ports, internal `127.0.0.1:4193`,
keep-id UID, read-only root, cap-drop ALL, no-new-privileges, approved seccomp,
catatonit init, 2 CPUs, 2 GiB memory, 512 PIDs and 512 MiB shared memory. Mounts
were only owned payload (read-only) and evidence. Chromium launched with
`chromiumSandbox:true`; process receipts show seccomp, no-new-privileges and
nested sandbox namespaces, without `--no-sandbox` or privileged mode.

## Observed checks

| Check | Evidence result |
| --- | --- |
| Emitted progress and final | Synthetic SSE intermediate update visible while working; completed classified final collapses progress; reopening retains text; final visually distinct. |
| Lifecycle and children | Same tool identity stays one item through pending/running/completed, with command, URL, 4.0 s duration and detail. Simulated authoritative counts 2 and 0 display; zero retains running status/spinner. |
| Reply ownership and queue | Follow-up queues during active run; late final/file stay with original run. Explicit fixture events start/settle the queued run; two replies keep separate activities/files. Refresh preserves messages/grouping and makes no extra send. |
| Shared/no-message files | Proven shared membership appears in both replies; a no-message run renders its activity/files without an invented final. Two synthetic SVGs decode as image previews. Individual download and distinct per-run ZIP routes work; single-file replies omit ZIP. |
| Attachments and errors | File-input and DataTransfer drop traverse actual browser handlers and multipart requests. Submitted user message retains both names/download links. Unsupported type and disabled image capability show errors. Synthetic HTTP 503 retains draft. |
| Keyboard and context | Enter adds newline; Ctrl+Enter submits; hint visible. Untouched chat shows zero, unknown/stale stays unknown, and first prompt removes zero even when fixture context metadata remains empty. |
| Locale/version/layout | DOM version 0.0.2; explicit Europe/Ljubljana converts 10:24 UTC to 12:24 summer / 11:24 winter with browser timezone UTC. Desktop 1440×1080 and mobile 390×844; sidebar Escape restores focus; asserted states have no horizontal overflow. |

Two focused unit files pass **13 tests**, including composition guards and
shared/no-message grouping. This is synthetic DOM proof, not platform IME
acceptance. No broad v0.0.1, GPU, context/output or installer suite was repeated.

All 17 actual screenshots were visually inspected and labeled
**FIXTURE / NOT LIVE INFERENCE**. Progress, final, galleries, errors, composer and
status are readable. The initial mobile sidebar shot caught its transition;
`browser/supplement/mobile-sidebar-settled.png` supplies the settled view.
The conversation scrolls internally, so one full-page screenshot does not show
all history. Normal scroll clipping is not a missing-content finding.

## Status finding and focused correction

**H002-UI-001 (corrected, fixture verified):** pre-fix `eb8387c` showed idle in
header/sidebar while the run strip correctly showed Queued; retained evidence:
`ROOT-DEFECTS.md` and `browser/results/desktop-final-original-run.png`.
The authorized follow-up to docs commit `ac25d510` reuses the existing idle-only
cancelling > running > queued rule across all three surfaces. Other aggregate
states remain authoritative; only the current loaded thread supplies typed runs,
and every unselected chat retains its list aggregate. Build and 12 focused regressions
pass. One isolated Chromium scenario confirms consistent queued labels after
refresh/chat switching; `status-correction/results/receipt.json` and visually
reviewed `status-correction/results/desktop-status-corrected.png` record it.
The original five scenarios were not repeated. Production remains NOT_TESTED.

## Explicit fixture adaptations and limits

The evidence copy of current `web/tests/fixture-server.mjs` adds only a second
named SVG preview, derived from its original synthetic SVG. The driver injects
contract events for progress, tools, child summaries, queue settlement, late
files, shared membership and a no-message run. One fixture-origin POST is
fulfilled with HTTP 503. Browser DataTransfer objects exercise drop handlers;
this is not operating-system drag automation. Frozen fixture timestamps test
conversion, not the current clock. The full delta is retained outside Git.

The fixture upload endpoint records multipart metadata; attachment downloads
return fixed synthetic text. The ZIP is an **empty archive used only for route
verification**. Added artifact download routes are specimens, not validation
of filename/byte fidelity. Supplemental completion intentionally leaves the
fixture's auto-created activity unchanged; its displayed in-progress status is
fixture data, not a native cleanup finding.

**NOT_TESTED:** all live engine/server behavior, real ZIP contents, native child
counts, user-history migration, production rendering, original attachment byte
equality, live clock/engine locale, platform IME, Cmd+Enter, PNG/JPEG variants
and hostile SVG execution/security. No synthetic event, screenshot or unit test
is promoted to these acceptance claims.

## Evidence and handoff

Local evidence root:
`/Users/agent/CodexProjects/llm-orchestration/tasks/H002-UI-FIXTURES-20260922/evidence`.
Retained remote task root:
`/home/user/ai-harness-build/H002-UI-FIXTURES-20260922`.

Primary records: `browser/results/receipt.json`,
`browser/supplement/receipt.json`, `source-build-receipt.json`, `build.log`,
`focused-unit.log`, `visual-review.json`, `ROOT-DEFECTS.md`,
`browser/cleanup-final.json`, and the two owned launch scripts. The JSON report
lists all screenshot paths. Both owned containers and their fixture Node
processes are absent; uploaded task payload/evidence remain outside Git.

`later-live/CHECKLIST.md` and `driver-skeleton.mjs` prepare the later campaign.
The skeleton defaults to **NO_LIVE_GATE**; `--run` exits 2 before any browser or
network access. Root must review final combined source/runtime and separately
assign actual-live acceptance. This task ends without awaiting that gate.
No push or deployment is part of this release-document candidate.
