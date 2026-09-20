# Sealed REAL72 follow-up batch

Source-only preparation at b88a3582 adds mode `sealed_batch`, campaign `benchrun-p72b-20260920`, within the existing `postrestart72-480k` runner. It authorizes exactly two480000 loads, the existing two discarded32-output warmups, then five measured requests:

1. Barrier-start G~4K retrieval256 and Qnear479487 retrieval256.
2. Exact `decode_diag.long_body()` scientific request4096; Qwen resident idle.
3. Barrier-start G65008 retrieval256 and Qnear479487 retrieval256.

Retrieval logical fixtures, native schema/sampling and unique leading prefixes are preserved. Scientific bytes have SHA256 `adfc0b6c1225ac5dc1f7e8ddb5c8022911c9a4551e48fd201d2228bc3abe86fe`, with no nonce, schema or EOS suppression. Actual outputs, including reasoning, remain outcomes. No180-second gate, speed cancellation, correctness retry, filler or additional follow-up is enabled.

The existing host registers native count routes, two warmups and a source/session/body/count/manifest-bound batch; cases advance only after owned drain and fresh proof. Preparation has its separate7200-second bound. Measurement admission lasts6hours from first admission. Expiry refuses new HTTP dispatch without clipping any admitted7200-second request. A scientific absolute deadline preserves partial evidence; socket closure plus bounded native singleton-slot idle and current pair safety proof are required before TIMEOUT can advance. Generic uncertainty remains registered for canonical recovery.

The existing1second collectors provide CPU phase mean/time-weightedp95, PSI/steal/throttling, thread counts and resource coverage. Native aggregate decode uses(n−1); rolling native counters remain distinct from event rates. `samples.jsonl` records preliminary transport capture; per-request results and `batch_request_terminal` record owner-verified terminal classification.

Future execution requires explicit root GO: canonical release of the old keeper, verified STOPPED/manual and free canonical lease, then one fresh detached RUN. No adoption/hotpatch. The new keeper remains in guarded warm hold after complete or safely drained quality/partial outcomes and after native CLI exit. Existing danger/recovery rules remain. Old modes and model/runtime/resource profiles are unchanged; this batch is one-use and admits no later mailbox follow-up.

Focused offline checks are `tests/test_postrestart72_batch_{contract,host,run,evidence}.py` plus existing clock/hold/follow-up/diagnostic contracts. Source checks prove no live allocation, inference, timeout cancellation or warm retention.
