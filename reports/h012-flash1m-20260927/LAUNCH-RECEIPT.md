# H012 — Flash 1M launch

**RUNNING_PREFILL_CONFIRMED**, observed 27 September 2026 at 02:37:00 UTC.
This is a launch check, not a completed 1M correctness or performance result.

- Main request sent at **02:36:10 UTC / 04:36:10 CEST**.
- Exact native input: **1,000,000 tokens**; configured capacity: **1,048,576**.
- Output ceiling: **1,024 tokens**. Main deadline: **04:36:10 UTC / 06:36:10 CEST**.
- Five successive native 2,048-token prefill batches were recorded from 02:36:23
  through 02:36:54. This establishes actual input processing.
- At 02:36:50 Flash was 47°C, using 35,650 MiB GPU memory with 61,600 MiB free.
  Host available memory was 606,780,485,632 bytes. Owned swap and OOM counters
  were zero. These are early samples, not whole-run peaks.
- Unit `h012-manual1m-02.service` remains independent of SSH and the paid CLI.
  Its candidate is `llm-frontier-flash-h012-manual1m-02` on loopback port 30011.
- Sova stays paused and the other three models stay loaded and idle.

## Launch repairs and evidence boundaries

The first start failed before dispatch because receipt writing reacquired its
own lifecycle lock. The correction borrows the outer lease and releases that
reference in `finally`; four real-lock regression checks passed.

The first dispatched candidate passed 1M allocation, its short request and exact
native token counting, but a pre-main guard treated Docker's reordered mount
list as an identity change. Complete mount contents were unchanged. Canonical
ordering preserves every field and rejects duplicate destinations; seven focused
checks passed. The first attempt naturally restored the original 480K service
and exited. No TERM or KILL was sent. Its source, stopped container and receipts
are preserved. The fresh attempt uses separate identities. Pre-dispatch lock
refusals were retained; the successful start followed an observed free lease.

Only the fresh attempt sent the long request. The canonical source contains both
fixes; the fresh staged variant changes five job identity constants as documented
in `MOUNT-ORDER-FIX-AND-FRESH-IDENTITIES.patch` and `REVIEW02.json`. Runtime, weights,
GPU placement, memory/temperature guards and the 300-second native forward-
progress watchdog remain unchanged. The main request has its own two-hour limit.

## Next check

The user will return after about one hour. No automatic wakeup or paid worker
session is waiting. Read the actual fresh job, not the retained first-attempt
receipt or an older mixed progress summary:

```bash
sudo python3 -I -B /data/services/h012-manual1m-02-20260927/manual.py status
sudo python3 -I -B /data/services/h012-manual1m-02-20260927/manual.py result
```

On verified success the candidate stays warm at 1M pending production promotion
and Sova configuration review. On failure, exact candidate shutdown precedes
480K recovery. Never replay or delete ownership records to force a retry.

Machine-readable launch evidence: [LAUNCH-RECEIPT.json](LAUNCH-RECEIPT.json).
The durable VM receipts use `/data/logs/flash-h008-20260926/H012-MANUAL1M-02`.
