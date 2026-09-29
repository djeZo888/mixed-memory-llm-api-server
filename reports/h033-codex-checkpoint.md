# H033 — Codex integration checkpoint

Execution window: September 29, 2026, 14:22:49–16:22:49 UTC.
Closed within the authorized window. Live deployment finished at 16:04:53 UTC;
the final paid worker CLI exited successfully at 16:07:28 UTC. **The window is
complete; full Codex integration remains incomplete.**

## Result so far

**MiMo delegation works through both Codex and MiniMax.** Each engine delegated
a short task to MiMo, which executed Python, consumed its result, completed its
child answer and returned that answer to its parent. Both parents completed and
native work settled. Results were `437` and `667`. Ordinary Codex frontier access
is now enabled by a protected, reviewed qualification record.

**Codex image integration remains incomplete.** One independent child request
produced a real Full HD PNG and its parent returned it in a correctly associated
final answer. The model recovered from six tool/resource errors. This proves a
working path, not reliable image operation: the original regression repeated invalid capability-tool arguments. Guarded
editing also failed its bounded acceptance. The general Codex image gate
remains closed.

Public chat remains in maintenance (HTTP 503); status remains available (HTTP
200). MiniMax remains the default engine. This is not a complete release.

## Corrections made

- **Fresh instructions now reach native Codex.** The launcher validated an updated
  host model catalog but did not mount it, so the container used an older baked
  catalog. An explicit read-only mount fixes this. The new native and normalized
  provider requests actually contain the corrected instructions; this was checked
  from captured requests, not inferred from host files.
- **Final answers and artifacts are associated correctly.** Successful native
  terminal summaries now identify the authoritative final message without
  classifying prose by its meaning. A real child-image workflow passed final
  message and artifact association; original stored history is preserved.
- **Download rendering handles a real model response.** When the model returns
  an exact reply-owned download URL inside inline code, the UI presents a
  clickable download using the artifact filename. Unknown/cross-run URLs,
  ordinary code and fenced examples remain unchanged. Forty-one focused tests
  and the web build passed; the deployed assets match that reviewed build.
- **Token counting performs fewer expensive checks.** One fresh before/after
  verification bracket reduces control reads from four to two. Restart, changed
  identity, stale state and cancellation still reject. There is no health cache.
  Forty focused tests passed. A live before/after comparison was skipped, so no
  measured speedup is claimed.
- **Frontier evidence is reused transparently.** Successful MiMo workflows used
  the previous instruction digest. A separately reviewed, exact compatibility
  record retains their actual tested source and policy, and the target policy.
  It does not relabel old execution as a new live test. Other model/runtime pins
  must still match, and image evidence cannot use this exception. Seventy-nine
  affected checks passed, including the new compatibility cases.

Test suite counts describe separate suites, not a sum of unique checks.

## MiMo timing observations

These are the first requests from the short acceptance workflows, not new model
capacity benchmarks. Tool turns, parent inference and queueing add to total task
time.

| Engine | Input tokens | Prefill | Input tokens/s | Output tokens | Decode | Output tokens/s |
|---|---:|---:|---:|---:|---:|---:|
| MiniMax | 11,620 | 305.915 s | 38.0 | 42 | 4.889 s | 8.6 |
| Codex | 13,133 | 358.591 s | 36.6 | 138 | 15.192 s | 9.1 |

Slow prefill and shared queueing explain substantial waiting in these tasks.
The Codex request omitted reasoning effort; it was not measured as an explicit
medium-effort request. MiniMax requested medium. Both used the existing native
thinking-enabled, nonparallel-tool profile.

## Image evidence and limits

The independent child produced one opaque 1920×1080 PNG: a red sailboat on a
calm lake with distant green hills at sunrise. Root and worker viewed the actual
image; downloaded bytes matched saved metadata. Parent final text includes its
real inline preview URL and correct download path. Image job
`0aae2635-c9c7-4aa5-ad6e-d8b5a9aefffd` belongs to run
`ec762194-446f-4938-b0ca-e94b50ab95fe` and its final message. Parent/child ownership,
provider requests and image job settled.

That successful request used the older baked catalog. Its evidence remains
labelled that way. The first original-regression attempt was cancelled by the
test operator after one invalid call, before possible correction; it is not
proof of an unrecoverable task failure. The fresh original after the catalog fix
was allowed normal recovery, made eleven failed capability calls across twelve
provider requests, and dispatched no image job. It was then stopped normally
and settled. The first ten errors were present in the next normalized request;
there is no evidence of dropped feedback. The eleventh lacked a completed
normalized capture before Stop. No arguments were silently stripped and no
alternative creative service was substituted.

The follow-up edit used the retained sailboat session. Its child inherited the
old parent instructions despite the new host catalog; the mounted current skill
was read, but this was not a fresh-catalog child test. The child completed with
intent only, after two invalid capability calls and no job. Its parent then made
further invalid calls and spawned a second child despite the one-child task
limit. The test was stopped for that scope violation. There was no edit job or
resize card, so geometry approval, edited artifact fidelity and edit downloads
were not exercised. Do not report this stop as the eight-identical-call threshold:
the parent had eight total faults, seven identical.

Actual browser interaction with the new image/download presentation is not yet
qualified. Renderer tests, API bytes and visual inspection are separate evidence.
Image generation does not establish native image recognition; Codex native
image/audio/video recognition stays unsupported.

## Deployment and preservation

Final app source `d55eb2b2eafd4e0d7df8ca2311277b797f3bad23` was ready at
16:04:53 UTC. Its frontier summary now agrees with the enabled protected
capability; image and native media remain disabled. The served web assets match
the reviewed download-rendering build. All current-window native/provider work
settled before activation, and acceptance tickets are zero. The final activation
preserved prior hashed assets and original application rows/events.

Original chats, files, failed cases, two historical uncertain owners and three
quarantines remain preserved. The native Codex image, model weights, inference
runtimes, GPU placement, fan/power/ECC settings and context capacities were not
changed. Three Qwen services remain configured at 480K, 480K and 200K. MiMo's
950,000 configured capacity is not a passed occupied-context result. No 950K or
other long model benchmark ran in this window.

## Evidence

- [Machine-readable results](h033-codex-results.json)
- [Final deployment](h033-image-flow02-20260929/DEPLOYMENT.json)
- [Bounded edit result](h033-image-flow02-20260929/EDIT-SUMMARY.json)
- [Repeated-error guard review](h033-image-flow02-evidence/RETRY-GUARD-REVIEW.md)
- [Independent review](h033-review-timing02-20260929/REVIEW.md)
- [Performance change](h033-perf01-20260929/REPORT.md)
- [Frontier compatibility review](h033-compat03-20260929/REPORT.md)
- [Artifact rendering](h033-artifact-ui04-20260929/REPORT.md)
- [Source and live workflow report](h033-flow-source01-20260929/REPORT.md)
- [Execution scope](h033-execution-plan.md)

Private native transcripts and raw captures remain under
`orchestration/tasks/H033-20260929`; compact receipts and all reviewed source are
published on `feature/glm53-flash` / draft PR10. All native worker CLI sessions
exited successfully, current-window owned work is settled and tickets are zero.
No model was unloaded to restore GLM or an old Sova baseline.

Most waiting came from actual local-model turns, including five-to-six-minute
MiMo prefills and repeated invalid image-tool calls. The latter did not reach
the image backend. Deployment also exposed and corrected script executable-mode
and inert build/staging assumptions; those failures are preserved. No complete
GPU benchmark or passed model recovery was repeated.

[Remaining work](h033-next-execution.md) covers image/tool compatibility, retained
chat instructions, PDF answer reliability and outstanding concurrency/restart/
browser/offline checks. Public maintenance stays enabled. This report does not
authorize another execution window.
