# Adaptive idle source checkpoint

H005 contains an inactive candidate policy and text `IdleSleeper` patch. **Native
text/image scheduler integration is incomplete; this is not a deployable overlay
or live idle acceptance.** Existing runtime profiles, launchers, source pins,
capacity receipts, model/context settings and runtime images are unchanged.

`scripts/runtime/adaptive_idle.py` implements one independent monotonic 600-second
grace per scheduler. Startup begins grace. Real request admission, warmup and
final work completion renew it; positive active/queued/streaming/pending-asynchronous
counters prevent blocking. Unknown counters also prevent blocking. Status reads,
metrics and bare wake events do not renew grace. After 600 seconds and all four
counters are known zero, the policy enters an indefinite level-triggered event
wait. A native binding must cover every ingress/completion event and preserve
readability through the check/wait boundary; no event may be cleared there.

The candidate text patch under `scripts/runtime/patches/` uses a required activity
provider. Applying it alone cannot silently reuse the old caller: construction
without the provider fails. It replaces periodic `poll(1000)` and allocator
cache-emptying in the ZMQ `IdleSleeper` with the policy and an indefinite poll.
The policy module must eventually be copied beside that class inside the reviewed
derived source package. The unsupported Rust sleeper is unchanged and outside
this candidate. No `--sleep-on-idle` default is changed, and no lifecycle owner,
timer thread, fixed busy sleep, weight unload or cache-emptying hook is added.

## Retained source boundary

The bounded search found full `IdleSleeper` text, but only scheduler/receiver
snippets, in H004 `final-observation.json`. That task's `initial.py` helper uses
`Path.read_text().strip()` before hashing. Its reported hashes therefore identify
normalized decoded text, **not original raw file bytes**. The 68-line reconstructed
fixture matches that normalized hash; its final newline is a fixture choice.
`adaptive_idle_sources.json` preserves the observed text/image revisions and this
limitation. `adaptive_idle_source_gate.py` checks those normalized identities and
reports raw hashes separately; it never installs files or accepts a runtime.

No full pinned text scheduler/receiver or image scheduler source was available
in the retained task copies checked. No VM contact or network retrieval was
performed. An image scheduling patch would require inspecting the full synchronous
and asynchronous execution/result paths; the retained empty-queue snippet cannot
prove that blocking is safe. The shared policy is prepared for that binding,
but this checkpoint contains no image patch or unproved queue-state guesses.

## Required next bounded task

1. Obtain full retained source for text revision
   `0bcd822377da7b5718e674eaf9c870d349424dd1` and image revision
   `0cd8be351d0825488f4b81c8931167bbab618eca`; bind raw bytes to official blobs and
   installed runtime receipts. Preserve the image's existing NVML UUID repair.
2. Bind real admission/final completion and all four activity states for the
   pinned text normal loop (overlap is disabled in the current profile) and image
   monolithic loop. Prove pending asynchronous work and all event sources before
   permitting the indefinite poll. Unknown activity must remain nonblocking.
3. Apply the candidate against the raw pinned tree, generate derived source/hash
   attestations and run full native-source fixtures. Root reviews the exact new
   runtime identity and a minimal acceptance transition. Existing 480000-token
   context and occupied-context measurements remain historical evidence from
   their original runtime; do not relabel those receipts as overlay acceptance.
4. After separately authorized activation, collect the planned baseline and
   at-least-11-minute idle observation, per-scheduler CPU and short warm work/wake
   checks. This task does not establish any of those live outcomes.

Offline verification:

```sh
python3 -B -m unittest discover -s tests -p test_adaptive_idle.py -v
python3 -B scripts/runtime/adaptive_idle_source_gate.py --help
```

The fixtures exercise 600-second boundaries, final completion, warmup/startup
grace, independent schedulers, status/spurious wakes, actual event block/resume,
the check/wait arrival boundary, all activity exclusions, and cache preservation
while executing the patched class. The patch applies to the reconstructed fixture;
that does not establish applicability to exact raw native source or real GPU work.
