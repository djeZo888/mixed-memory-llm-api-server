# H021 ACCEPT03 W2 checkpoint

Implemented the reviewed deny-all browser WebSocket guard and a bounded matched
Sova API batch runner. Actual rootless Linux public browser navigation/render,
SearXNG search and PDF helper extract/render/create/re-extract/re-render passed.
Public PDF download initially failed after20.258s. A narrow repair passes four
offline checks and one actual Mac download; Linux repair acceptance is pending. No model
requests, preview activation, deployment or production data changes were made.

Native executor session `01a0e6b3-3461-7e13-9302-d3d09d8f73cb` started
2026-09-28T06:28:18.612374Z; hard cap07:08:18.612374Z. Initial exact base
`9ee552dcc8fd5086c97d47eea33828c8e0cf15c5`; root-provided namespace repair
fast-forwarded to `dd0535e80df3665ebe39946033f2e175b15253e7`. Implementation
commits: `2f2e478` browser guard, `747c8be` batch runner, `fd116f1` input hashes,
`d27200c` inline download repair and `3a69a37` explicit zero retries.
No push or subagents. Wrapper records actual exit after this terminal checkpoint.

| Check | Result | Qualification |
|---|---|---|
| Browser WebSocket guard | PASS | Actual Mac Playwright1.63.0/Chrome153.0.8010.37; control1 handshake, guarded2 attempts/0 handshakes |
| Batch runner | PASS10/10 | Offline contract tests, including uncertain dispatch/no replay, missing/false host settlement, automatic sequential handoff, input integrity |
| Rootless browser public navigation/screenshot | PASS | Actual MCP browser_open, https://example.com/, screenshot inspected |
| Browser private destination rejection | PASS | Actual MCP rejected127.0.0.1 before browser launch |
| Browser public PDF download | FAIL | W3 dummy.pdf URL;20.258s generic failure, no artifact; no repeat or alternate service |
| Inline download repair | PASS locally / NOT_TESTED Linux | Four redirect/body checks; actual Mac context GET downloads valid13264-byte one-page PDF |
| Local search | PASS | Actual SearXNG MCP returns primary Python bisect URL; selected source page not opened in this fixture |
| Linux PDF helper operations | PASS | Extract source, render source, create summary, extract/render summary; actual page PNGs visually inspected |
| Mac PDF extraction | PASS | Cached pinned pypdf/pdfplumber; source PDFium render visually inspected |
| Mac PDF creation | FAIL |60s timeout, retained; downstream missing summary failure retained |
| Exact Linux container cleanup/app preservation | PASS | Supervisor exit0; exact container absent; no new containers; original app inactive/PID0/unit hash-mode-owner unchanged |
| Linux full-profile skill advertisement review | PASS | Actual W1 supplied5 requests advertise Sova skill and browser/search/image-capabilities namespaces |
| Skill invocation / model tool selection | NOT_TESTED | Captures never read SKILL.md and use direct shell tools, not reviewed PDF helper/browser MCP |
| Matched model tasks / actual deployed UI / Stop / rollback | NOT_TESTED | No application/model batch GO; existing host settlement adapter path pending W1 |
| MiMo Codex / image job / model capacity | NOT_TESTED | MiMo deferred byH019; image remains W1-owned; no capacity test |

Rootless run used cached image
`a8b7d8bdb8a2f56f4c4fb8e8592f80e2664549c61bb5476b400dea9ad599b35f`, plus
explicitly authorized browser source SHA256
`988455cfcd0b39ed913612c1c923295912120811882e2a268889df09e6802588`.
This was an override script in an isolated workspace, not a rebuilt/deployed
Codex profile. Container
`af3a0ee9c36319bb5c9cbd3f33842ab65cbd9c76bd554a6db9905fd10e763393` ran under
existing root-attested task egress and the reviewed rootless/seccomp envelope.
Node24.21.0, Chromium153.0.8010.52, Python3.12.14, pypdf6.19.0 and
pdfplumber0.11.10 were read from the actual runtime. No model keys entered it;
MCP search used the existing local service. The fake supervisor token was not
passed into the container. Window released after exact cleanup; W2 performs no
further host actions without coordinator scope.

The direct source PDF and created summary are legible, single-page fixtures with
3.3V and250mA=0.25A. This proves basic helper behavior, not engineering datasheet
accuracy or model answer correctness. Local diagnosis confirmed the download failure mechanism: W3 responds200 with
application/pdf and Chromium renders inline without a download event. The approved
repair uses a browser-context GET with at most5 manually validated redirects,
a20s GET deadline, explicit maxRetries0, HTTP/body-size rejection and response disposal. The
20MiB limit is honestly an accepted-artifact limit after buffering. Actual Mac
repair download is13264 bytes, SHA256
`3df79d34abbca99308e79cb94461c1893582604d68329a41fd4bec1885e6adb4`, and
pypdf reads one page containing Dummy PDF file. Linux MCP repeat remains pending
a new exact window; the original failure is preserved. Final browser source
SHA256 is `c874973d6bd48df542f0956dad16fe93c21c7448097dcc3956abd011040d0769`.
W1 must incorporate it into its owned policy/image hashes before deployment.

The actual W1 Linux captures confirm the seven-word fixture instruction override
in all5 requests. Upstream models-manager/src/model_info.rs uses BASE_INSTRUCTIONS
from models-manager/prompt.md. W1 owns production prompt correction. Bundled
.system skill advertisement is confirmed by codex-rs/skills/src/lib.rs; it is not
ambient credential leakage. A Sova skill catalog entry alone does not prove its
guidance was read. No fabricated reasoning/usage claims were added.

The batch runner stages only original buggy sources/tests plus the supplied PDF,
keeps answer keys outside model context, requires one bounded batch GO, uses Sova
HTTP only, preserves dispatch intent before POST, never replays uncertainty and
requires W1's existing authoritative native/gateway/children/image settlement
hook between cases. It does not execute downloaded model code on the Mac. Terminal
runs remain pending independent correctness checks. Missing token usage is null.
See ACCEPTANCE.md for exact procedure and real UI/lifecycle checklist.

Reuse prior ADAPTER02 broad server/web/native/lifecycle PASS; none was regenerated.
Pre-H021 rollback is unsafe for Codex IDs: disable preview in an engine-aware
release, retain Codex read-only histories/files and functioning MiniMax. H020
status/current MiMo selection were untouched. Independent MiniMax/MiMo HTTP400
remains unresolved. No ai-vm/H019 polling, inference/runtime/control changes,
GLM restoration, hardware/GPU work, dependency downloads or paid fallback.

Raw logs, captures, screenshots, input/oracle and PDF artifacts remain private
under task `../evidence` (and supplied `../input`); MANIFEST.json records hashes.
Only compact reports/manifests and necessary focused source/tests are committed.
