# H010 optional smoke — Worker2 PASS; four-instance overlap NOT_TESTED

Fresh native02 session `01a0e013-879f-7d33-83ce-06997cdbd56d` began
2026-09-26T23:36:11Z. Root delivered the actual settled primary 64K handback and
agreed 23:44:00Z with Worker1. Worker2 armed host PID 211845 at 23:42:51.019Z.
It exited 0 after all three requests settled at 23:44:13.318Z.

| Instance | Actual client request interval UTC | Native tokens in/out | Result |
|---|---|---:|---|
| Qwen GPU0 | 23:44:00.016–23:44:00.227 | 32 / 4 | Exact `323`; HTTP 200; stop |
| Qwen GPU1 | 23:44:00.018–23:44:04.514 | 39 / 6 | Exact `2,5,9`; HTTP 200; stop |
| Image | 23:44:00.009–23:44:13.183 | Not provided | Opaque 1024x576 PNG; HTTP 200; visual PASS |

The three Worker2 request intervals overlap for 0.209s. These are instrumented
client HTTP intervals, including transport/callback overhead. Nonstreaming first
response/body timestamps are retained; they are not token TTFT or native decode
windows. This is a bounded functionality smoke, not a performance benchmark.
No timing is blended with Worker1's uncontended 64K result.

Root subsequently reported that Worker1's first timer refused before any Flash
inference. Thus **four-instance request overlap is NOT_TESTED**. Root proposed a
corrected launch, then cancelled it after the explicit one-attempt scope conflict
and unmet mutual armed cutoff. Worker2 did not arm or send any second requests.
GPU-kernel simultaneity is NOT_TESTED, and no atomic native drain is claimed.

The unchanged installed `createGateway` dispatched one request to each of its
fixed Qwen endpoints. `ImageUpstream` fetched current capabilities and selected
the exact existing generation/1024x576/zero-reference/opaque profile. Both text
requests had max_tokens 128. The one image used seed 20260927, with no retry,
resize, edit, alternate profile or fallback. `NodeAvailability` used service ID
`image`. Host credentials were loaded only by the installed protected loader;
no values entered argv, env, source, reports or logs. No Sova session was created.

At settlement both gateway lanes were idle, all three responses were complete,
and image readiness was ready/idle. All four canonical service identities were
available. A visual inspection confirmed the requested centered red mug on pale
blue background. Image 298690 bytes, SHA256
`f1cd327f901ca7d5b79049f5b4d85525668e191d4e3e4f3adf9fdb5042b9a5eb`.
Original image and receipts remain at
`/home/user/ai-harness-build/H010-WORKER2-20260927/overlap-02/` and the matching
mac task `overlap-02/` directory; image bytes are outside Git.

`SMOKE-RAW-02.json` and `SMOKE-OWNERSHIP-02.jsonl` retain the original evidence.
`SMOKE-RESULT-02.json` adds visual review and explicit overlap limits without
rewriting raw receipts. The source hash at dispatch was
`34e8392a58bb24365bf30e364f4819d37973e39afa6a1ea926397c437cecc124`.
Validation before arming: syntax, installed module import, offline `--prepare`,
exact installed-client hashes and current app/history/owner metadata all passed.
