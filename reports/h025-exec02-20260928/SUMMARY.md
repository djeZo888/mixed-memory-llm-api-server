# H025 EXEC02 — closed with zero requests

The single authorized campaign unit refused before its barrier because the current
fan controller status was blocked. **No inference or tokenization request was sent;
the 300-second campaign and four-model overlap remain NOT_TESTED.** No retry is
authorized and the campaign/GO/bridge/journal namespace is consumed.

Native worker session `01a0e98c-1f3b-7721-af92-6bc19c654d93` began
2026-09-28 19:44:43 UTC, with hard deadline 20:15 UTC. This session used one native
CLI and no subagents. Actual guest operations used existing worker SSH.

## Authorization and execution

Root approved the exact manifest canonical hash
`3c33e52e08a69725ad8bca5d445ab1655f4ec0ec9d651bcd1fb1c34aa13010d3`
and exact GO raw hash
`f6110e47e41c79926e3a31ec687558300a65728cadcda8c5b62cc4995b788bbc`.
The revised grant was 19:51:00–19:57:30 admission, with settlement through
20:13:30, preserving 900 seconds per request plus 60 seconds for physical stop.
Obsolete proposals were not dispatched.

The ten already-staged source files, retained corpora, four native container
identities, Qwen owner generations, image run ID, capacities, and source pins
matched. No preparation replay, source repair, suite rerun, warmup, model load,
profile change, or permanent frontier-policy change occurred.

`h025-test01-overlap.service`, `Restart=no`, ran once with PID 1293976 and invocation
`d2ebc1a2699d4e5fb8e4691f378966ed`, observed at 19:52:26.566081 UTC.
Its first failure at 19:52:27.006331 was `fan node/UUID drift`. The controller's
blocked status contained null node/sample/readback fields. The unit produced a
durable `FINAL.json`, zero request records, no active or uncertain work, no stop
intents, and `INCOMPLETE_OR_FAILED`. Exit status 0 is not campaign success.

There was also an operator sequencing error: a multi-command shell continued to
`systemd-run` after the separate fan preflight exited nonzero. The driver's own
independent check refused before barrier release and prevented all inference.
Root authorized the local `launch_once_fail_closed.py` correction, which propagates
preflight failure with `check=True` and rejects a consumed namespace. It passed
Python syntax compilation only and was **not executed**. The reviewed guest
driver package remains unchanged.

## Fan failure evidence

W1's final normal-stop/restart/physical-tach PASS was genuine historical evidence
bound to PID 65410 and source `9293a17d…`; current readiness later failed.
The exact controller mismatch receipt at 19:52:10.065356 records:

| BMC response path | Baseline | Observed |
| --- | ---: | ---: |
| `//api/fanctrl/source/FanSourceList/1/Current` | 38904 | 36864 |
| `//api/fanctrl/source/PWM2_1` | 248 | 0 |
| `//api/fanctrl/source/PWM2_2` | 151 | 144 |

Protected status reports `bmc_invariant_changed:safe_high_unavailable`. At the
restoration check the fan service was **failed/enabled, MainPID 0**. Last known
duty 40 and tach 3600 are historical readings; current readback was null and tach
units remain unknown. W2 made no BMC/controller/thermal writes, latch clear, or
repair. Root/W1 owns diagnosis and recovery. Exact mismatch, blocker, and status
files are preserved privately with original byte hashes.

## Settlement, restoration, and limits

The exact Mac bridge PID 14142 was stopped only after durable final evidence and
proof of no owned work were captured. No physical model stop was needed.

At 19:53:41 UTC app PID 69392 and status PID 69413 were active/running/enabled;
public `/api/health` and `/api/status/v1/system` both returned HTTP 200. Search's
user service retained PID 1655 and its original invocation, active/running/enabled,
with HTTP 200. All four model identities remained unchanged and ready, image was
idle, and permanent MiMo selection remained generation 12. MiMo was not called,
restarted, repaired, or qualified. Known Codex limitations remain unchanged.

All 51 session/native-ID bindings match the fresh pre-stop snapshot. Messages 220,
files 109, runs 73, gateway records 118, image jobs 20, holds 0, and historical
workspace quarantines 3 retain their counts. Events increased 35114→35120 during
normal restart; the two historical uncertain Codex bindings remain. No manual DB
edits, replay, hold clear, or quarantine clear occurred. A broad historical hash
audit was not repeated; unchanged aggregate session hashes are not claimed.

Actual four-way HTTP intersection is zero because no request was sent. There is
no admitted campaign window, longest-gap qualification, accepted telemetry
summary, thermal crossing, or load qualification. A single rejected pre-barrier
sample is labeled as such in `RESULT.json`; its cgroups showed zero swap and OOM
counts, but it cannot establish a swap-growth trend or campaign PASS. Independent
idle snapshots before and after showed GPU temperatures 32/33/37/34°C, zero GPU
utilization, and unchanged VRAM use. No wall-power, PSU, or sustained full-load
claim is made; Ada has a separate PSU.

`SOURCE-PINS.json` and `RAW-HISTORY-MANIFEST.json` bind the compact report to the
unchanged reviewed package and private raw evidence. No raw history or credentials
are committed. Root integrates and publishes; this worker does not push.
