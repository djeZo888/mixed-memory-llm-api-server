# H021 stage 3 — real Qwen and local tools

September 28, 2026. The real-model protocol gate passed; application deployment
and matched-task acceptance remain in progress.

## Real-model gate

The pinned Linux Codex 0.158.0 App Server completed a two-turn coding task on
Qwen0 through the shared gateway: read the source and test, edit the implementation
with native `apply_patch`, run the unchanged regression, then resume the native
thread and run the regression again. Six upstream generations completed with
exact input counting, a 1,024-token per-request acceptance budget and no automatic
request retry. Qwen retained its existing 480,000-token allocation.

Input counts ranged from 11,330 to 12,055 per request; outputs ranged from 61 to
101 tokens. These are functional-test observations, not throughput benchmarks.
Observed Qwen0 temperatures were 36–48 C. Native container removal, gateway
settlement and restoration of the original inactive Sova app unit all passed.
No new containers, unresolved request owners or port-8081 listener remained.

The earlier attempt completed two upstream requests before the native client
reported a response-body decoding error. Its converter exception was not
captured, so its cause remains **unproven**. The successful attempt used the full
pinned upstream general agent instructions plus Sova's deployment overlay and
private diagnostic capture. Success does not prove that the prompt caused or
repaired the earlier failure. Static converter diagnostics now make a recurrence
identifiable without logging model text by default.

Evidence retained privately:

- Result/cleanup receipt SHA-256:
  `63d6cce7c4f09efd792dcf21286af7c5f6fce0fe7003c019e6fcfa7289ba9699`.
- Linux image:
  `beb56186c9087d7a66ad7c527eefae2f004865d59852e6be55f5264a9b413d81`.
- Trusted policy:
  `fc58824904adfed55fed6ac1a181e64954fb432abdcfe9d2a8a08e5cb202ab71`.
- Unchanged regression SHA-256:
  `70393eb09215c675c3f562f3fd49974b482a8555a0e266c8c0fd28d725ef8e09`.

## Local tool checks

Worker2's rootless Linux tool fixture passed public-page rendering/screenshot,
private-address rejection, local SearXNG search, PDF extraction/rendering and PDF
creation followed by re-extraction/rendering. These checks exercised the tools
directly, without a model. Its exact container was removed and the app unit was
unchanged at handoff.

An inline public PDF did not emit a browser download event. The repair uses a
browser-context GET with explicit public-address validation at every bounded
redirect and no request retries. The installed Mac browser returned the genuine
PDF; Linux repetition in the final image remains pending. The 20 MiB limit bounds
accepted artifacts; Playwright buffers the response before that validation.
Browser WebSockets are now blocked before pages are created, closing a gap in
the existing HTTP-only request checks.

## Remaining acceptance

Deploy the optional preview using existing data and admission ownership; run
matched coding/research/PDF tasks, specialist-image and native-child checks, and
verify the actual chat UI and lifecycle. MiniMax remains the default. MiMo live
Codex acceptance remains deferred, and the independent 950K benchmark has not
been polled or modified by this work.
