# D3BASE baseline status

Updated: 2026-09-15T03:51:16.864551+00:00

Phase: baseline bound; checkpoint READY; generation requests completed: 0.
Private persistent trial: `/Users/agent/CodexProjects/llm-orchestration/tasks/D3BASE-20260915/trial`; checkpoint: `/Users/agent/CodexProjects/llm-orchestration/tasks/D3BASE-20260915/trial/run` (0700).
Protected key path: `/Users/agent/CodexProjects/llm-orchestration/tasks/D3BASE-20260915/trial/api-key` (0600; preserved).
Endpoint: `http://127.0.0.1:54597/v1`; owned tunnel PID `31379`; isolated ControlPath `/tmp/d3base-ssh-_8l6gtwi/ctl`.
Elapsed since admission: 22.799 seconds; stage elapsed not started.

Immutable container `bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55`; image `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`.
Actual slots/context: 1/32768; placement `all_cpu`; threads 112.
Root available: 5208965120 bytes. Registered/canonical guards PASS; warning root below 6 GiB retained (STOP below 4 GiB).
Target Swap/VmSwap: 0/0 KiB.
GPU free bytes: {"0": 84300267520, "1": 88377131008}.
Host historical swap used: 14080 KiB; new swap/OOM deltas: {"oom_kill": 0, "pswpin": 0, "pswpout": 0}.

Sole generation lease retained. Installer STOPPED; control inactive/disabled.
Only four short baseline requests authorized (256/256/512/512, low reasoning, temperature 0).
`highest_proven_window=null`; no occupied32K/max-context proof or candidate/native phase.

## Prepared checkpoint — 2026-09-15T03:52:09.108429+00:00

Status PREPARED; baseline/cold; elapsed 52.137s.
Actual native input 1370 tokens, body SHA256 `6682c1aaae6491aaa900da3297c05e17a63bc35adbceaef310bc8ded47b1f89d`; output cap256; low reasoning; temperature0.
Initial prepare return briefly reported PREPARATION_UNKNOWN before its detached child acquired request.lock. Advancement paused; one shipped status observation then showed the original child completed PREPARED. Request lock is free, frozen bytes/accounting checked, no retry or checkpoint edit occurred. This reconciles the transient launch observation.

## Monitor

```json
{
  "utc": "2026-09-15T03:54:55.616673+00:00",
  "stage": "baseline",
  "step": "cold",
  "status": "PENDING_RECONCILIATION",
  "elapsed_since_dispatch": 165.4668550491333,
  "sample_count": 112,
  "latest_sample_age_seconds": 29.187882661819458,
  "latest_sample_status": "PASS",
  "failure_class": "cold_cache_NOT_TESTED"
}
```

## First result — stopped advancement

```json
{
  "observed_utc": "2026-09-15T03:55:34.914642+00:00",
  "status": "PENDING_RECONCILIATION",
  "failure_class": "cold_cache_NOT_TESTED",
  "dispatched_at": 1789444330.149903,
  "request_deadline": 1789444929.163336,
  "worker_elapsed_seconds": 137.05595999999787,
  "counters": {
    "cached_tokens": 50,
    "cached_tokens_source": "usage.prompt_tokens_details.cached_tokens",
    "completion_tokens": 64,
    "decode_ms": 112294.399,
    "decode_tokens": 64,
    "elapsed_seconds": 137.0549194579944,
    "evaluated_prompt_tokens": 1320,
    "prompt_ms": 22135.537,
    "prompt_tokens": 1370,
    "total_tokens": 1434
  },
  "finish_metadata": [
    {
      "index": 0,
      "finish_reason": "stop"
    }
  ],
  "raw_sha256": "6291a2bb8814c37018862ec0a580c0c078a7921e896d2db6519cacf1e1cca445",
  "accounting": {
    "body_sha256": "6682c1aaae6491aaa900da3297c05e17a63bc35adbceaef310bc8ded47b1f89d",
    "common_prefix_tokens": null,
    "input_tokens": 1370,
    "rendered_prompt_sha256": "9bcde19e00224e1f7d5892196e079ea3c4951f7c99760f52337f06a216742d5d",
    "tokens_sha256": "469dd72637c5825cf9cd3b936e7c7033ab0d99ed1dfb14ca94ce4db92bbe455c"
  },
  "sample_count": 112,
  "samples_all_pass": true,
  "sample_first": 1789444330.3083448,
  "sample_last": 1789444466.4288764,
  "request_lock_free": true,
  "owned_probe_pids": [],
  "highest_proven_window": null,
  "native_configured_capacity": null,
  "later_stages": "PENDING_NOT_TESTED",
  "successful_results": 0
}
```

No further prepare/start has been called. Checkpoint remains unchanged; lease retained pending completion/cleanup reconciliation.

## Final status — 2026-09-15T03:58:45.033307+00:00

**STOP after first cold request**: backend cached count50, required0; no later request dispatched.
Complete response, matching native/usage1370 prompt tokens, 64 completion tokens, worker elapsed137.055960s.
Backend prompt1320 evaluated tokens/22135.537ms; decode64 tokens/112294.399ms. Missing TTFT=null.
Sole request lease RELEASED; tunnel31379 absent and port54597 unbound. Private checkpoint/key retained.
Checkpoint remains PENDING_RECONCILIATION/cold_cache_NOT_TESTED; operational completion reconciled by complete response, native slot release, no API connections and zero owned children.
Baseline/candidate/occupied proof has not passed; highest_proven_window=null.

## Coordinator final acceptance

Root accepts the completed request as a **PARTIALLY CACHED baseline** (50 cached,1320 evaluated) for later candidate comparison using identical body hashes/native timings with cache difference disclosed. No zero-cache retry, duplicate harness or more requests. Lease already released and tunnel cleaned at03:58:45 UTC. Checkpoint remains unchanged PENDING_RECONCILIATION/cold_cache_NOT_TESTED; no STAGE_PASS is manufactured. Source candidate-gate reuse is a later-owner integration gap.
