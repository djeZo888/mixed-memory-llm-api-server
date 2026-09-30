# v0.0.3 bounded live acceptance — native worker path failed

On 2026-09-23, fresh native Worker2 task `H003-ACCEPT-20260923` independently
checked deployed source `b5717d03416252c8640c47d37baf892a0c4e532a` after root GO.
Worker1 retained production ownership. This report does **not** accept the
release: the worker generated its image through a Python HTTP gateway fallback,
with zero registered native image MCP calls. The cause is not proven; diagnosis
and repair belong to a fresh task.

| Area | Outcome |
|---|---|
| Deployment identity | PASS: activation source and engine image/digest match reviewed receipt; actual owned engine container independently matched immutable image. Live health reports 0.0.3. Legacy runtime tag 0.0.2 is not the immutable version proof. |
| Image model pins | PASS: live capabilities match retained Qwen-Image-2.1 model revision, runtime revision/digest and six qualified generation profiles. |
| Ordinary main generation | PASS: Worker1's existing Full HD image reused; independent persisted activity and retained native trace confirm one `skill`, one `mcp__image__image_capabilities`, one `mcp__image__image_generate`, and zero bash calls. |
| Ordinary worker delegation | PASS: exactly one native `task` selected `agent_name: worker`; actual parent/child identities retained. No role ceilings changed. |
| Worker native image MCP path | **FAIL:** child used 16 bash calls and a Python HTTP POST to internal `/v1/image-jobs`; zero registered image MCP calls. Native task results contain the resulting job/request IDs. Successful output does not qualify this fallback. |
| Browser image handling | PASS: real installed Chrome/Playwright showed reply-specific running state, same-job reload recovery, completed previews and downloads. SSE revisions 1–5 retain job/run identity. First live elapsed field showed `Unknown`; reload showed 2s, completion 24s. Automatic reconnect indicator was not observed during the bounded offline toggle. |
| Artifacts | PASS: both downloaded PNGs independently decode as opaque RGB; dimensions, byte sizes, MIME and SHA256 match job/artifact metadata. One artifact per run, no duplication after reload. |
| Concurrent text | PASS: existing two text requests completed entirely within main image broker interval 12:06:05.261–12:06:58.952 UTC, in 3.529s and 3.427s. This is not GPU-kernel timing evidence. |
| Approval-token isolation | PASS: actual owned engine-origin requests to server8080 with allowed Host/Origin and spoofed proxy/forwarding headers returned 403 `image_approval_forbidden`; host80 variants returned 403 without a token. Two initial origin-only denials were excluded from proxy-secret proof; eight corrected checks followed. No real proxy secret or session bearer was used by probes. |
| Queue cancellation | NOT_TESTED: no safe atomic queue-only admission guard; no extra submission risking a third image. |
| ZIP | NOT_TESTED: no naturally available multi-file reply; one artifact in each separate run. |
| Editing / resize approval | NOT_TESTED: disabled/unqualified in this task; disabled UI is not edit acceptance. Later edit authorization does not extend this campaign. |

The broker accepted **two** image jobs across workers: one reused Worker1 main
image and one Worker2 child fallback. Both completed. Native image-MCP acceptance
is **main 1, child 0**. There were no image retries, replacements, optional queued
submissions or edits. The failed-path image consumes the second image budget.

| Case | Dimensions | Seed | Model | Broker execution |
|---|---|---|---|---|
| Worker1 main | 1920×1080 | 23092301 | qwen-image-2.1 | 53.691s |
| Worker2 child fallback | 1024×1024 | 2026092302 | qwen-image-2.1 | 24.436s |

Root reports a separate strict no-swap gate **FAIL**: cumulative counters changed
from 0/0 to 305/5323, with attribution unresolved. Main-image memory samples were
after inference and do not establish peak reserve. No overall release acceptance,
no-swap success, intrinsic model repair, or editing qualification is claimed.
The main final prose also contained a host-path image link; the dedicated gallery
and artifact download passed, but that prose link is not accepted.

The inference/deployment window was returned to Worker1/root with the owned chat
idle, run completed, zero active children and one retained image. An owned Stop
was sent after detecting the fallback, but native completion preceded it; this
does not establish cancellation coverage. A later root grant allowed only retained
main-trace readback and this documentation commit/bundle. No generation was repeated.

Exact session/run/job/request/artifact IDs, model pins, output hashes and evidence
hashes are in [the compact summary](acceptance-v0.0.3-historical-worker-failure.json). Full sanitized native
traces, response/SSE metadata, genuine screenshots, downloads, scripts, wrapper,
events and actual exit are retained under task `H003-ACCEPT-20260923`, outside Git.
No implementation changes, builds, installations, broad tests, ai-vm contact,
production configuration changes, service restarts, cleanup, push or main merge
were performed by Worker2 acceptance. Source fixtures are not live acceptance.
