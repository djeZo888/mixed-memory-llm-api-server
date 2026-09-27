# H011 exact1M manual candidate

**PREPARED_OFFLINE_NOT_EXECUTED — 1M LIVE NOT_TESTED, THERMAL BLOCK.**
Root canceled all staging/launch this turn after ServerQwen1 reached85–86C
during the corrected concurrent-load test. Keep Sova paused; no guard changes.
The commands below describe a future reviewed workflow, not a current launch.
Source and mock checks do not qualify1M.
Worker2 has made no ai-vm contact, allocation, profile activation or inference.
Root reviews the exact source; Worker1 alone stages it and a fresh authorized
Worker1 execution session owns any launch. Production remains480000 configured,
65536 occupied input qualified until actual new evidence exists.

The latest direct user message supersedes restoration-on-success: full PASS
retains the separate1M candidate, with Sova paused. Promotion is later work;
the current job never edits production source/config/container or harness config.

## Review and offline reproduction

From repo root (no network, GPU or service calls):

```
python3 -B reports/h011-worker2-20260927/manual/test_manual.py
python3 -B reports/h011-worker2-20260927/manual/test_lifecycle.py
python3 -B reports/h011-worker2-20260927/manual/test_stream.py
python3 -B reports/h011-worker2-20260927/manual/prepare.py --output /absolute/new/local/directory
python3 -B reports/h011-worker2-20260927/manual/manual.py plan
```

The materializer verifies all baseline hashes and applies explicit single-site
edits into a new directory; it refuses an existing output. `context-only.patch`
shows the three edited wrappers. `context_profile.py` allowlists only480000 and
1048576; default remains480000/port30010. Experimental selection is
`--profile manual1m`, fixed port30011. Native bounds derive from pinned source:
input<=context-7 and input+reserved output<=context-2. Actual native context/pool,
max input, cache dtype, threading, prefill and native SM120 assertion must match.
Unrecognized profiles or actual allocation mismatch fail closed.

The unchanged original owner, tool runtime, native-source manifest, NUMA policy,
H010 fixture constructor and stream implementation are hash-bound dependencies.
The generated request driver reuses selected H010 functions, changing only its
fixed port, telemetry sample bound and a timestamp immediately after request body send.
That timestamp proves the client sent bytes, not native admission or prefill. It drains promptly into bounded memory;
5s telemetry and15s buffered durable checkpoints run on separate threads.
No lifecycle acquisition, storage checks, writes or fsync occur per token.
Boundary/terminal records remain durable. Abrupt death can lose a checkpoint
interval of deltas; it cannot authorize request replay.

Worker1 stages the resulting files, **not this repo path**, into the protected
root-owned `/data/services/h011-manual1m-20260927` using the currently installed
registered-storage/anchored guards before and after writes. Files and manifest
must be root-owned0644 with protected ancestry. Compare every staged file with
`candidate-sha256.json`. Do not overwrite an existing staged tree or prior owner
receipt. No staging command is run by Worker2. The staged `manual.py` requires
that exact absolute path, the pinned installed owner and current production
source hashes. No production manifest is changed to make partial files pass. Credential raw-byte
checks match the pinned original file_auth.py: root-owned0600, ASCII33..126,
no whitespace normalization. Worker1 may verify a private boolean contract match
at staging; never print, rewrite or export the key.

## Future two-console workflow

First, on **ai-harness** as its ordinary user, verify no user/native/Flash/image
work or uncertain ownership. Use the normal current owner/data checks and stop
only the idle app:

```
systemctl --user stop ai-harness.service
```

Keep enablement/search/status/admin/data/credentials intact. Do not reuse H011's
old quiet receipt as proof for a later launch. The acknowledgement below means
CURRENT harness paused and ALL clients settled, including external benchmark
clients. Readiness and no observed TCP connection are supplemental observations;
they do not establish an atomic native drain. Unknown work must refuse launch.
No cross-VM keys/admin/auth plumbing is introduced.

Then, on **ai-vm**, after exact root review and staging:

```
sudo python3 -I -B /data/services/h011-manual1m-20260927/manual.py start --ack-harness-stopped-and-clients-settled
sudo python3 -I -B /data/services/h011-manual1m-20260927/manual.py status
sudo python3 -I -B /data/services/h011-manual1m-20260927/manual.py result
```

`plan` or `start --dry-run` prints the offline contract with no host operation.
Missing acknowledgement refuses before protected files/services are contacted.
Start reserves one durable owner and launches `h011-manual1m.service`; SSH
closure does not own its lifetime. An existing owner/result/claim/candidate,
unknown creation outcome or stale job cannot be replayed. Do not delete these
records to retry. `sudo systemctl stop h011-manual1m.service` asks this exact job
to abort and run its confirmed-stop failure cleanup; it can take the bounded
restoration period. SIGKILL/host failure instead requires owner review.

The job holds the existing canonical lifecycle lease through the maintenance
window and lends it to the original owner and periodic checkpoint transactions.
Other model processes remain unchanged; competing lifecycle mutations are
blocked until this job releases the lease. Ordinary current-user work must be
quiet before launch. Production port30010 is unavailable while the experimental
port30011 is active, so stale Sova480K configuration cannot dispatch to the1M
candidate or advertise it as qualified production.

## Request and terminal contract

The job snapshots exact original source/config/state/container identity and the
other three model identities. Normal owner `halt` preserves desired=running.
It creates only `llm-frontier-flash-h011-manual1m` on loopback30011, restart=no,
with the same image, weights, GPU, cache/tmp paths, CPU placement, security and
650GiB no-swap cgroup. Candidate validation reuses all original owner containment
checks with explicit, checked differences only for name/label/runtime mount/Cmd.

After startup's existing native warmup, one short bounded32-output request checks
transport, native usage and actual allocation. A fresh UUID-seeded varied
technical dossier is constructed with three planted early/middle/end markers
and an arithmetic result. The local pinned native template/IDs must total exactly
**1,000,000 input tokens**, then the unchanged native chat processing path through
`/v1/tokenize` must return exactly that count and pinned revisions. The actual
serialized request must fit16MiB. The main output cap is1024 including reasoning;
it is neither a product output ceiling nor extra reserved input capacity.
The full1M character-tokenizer fixture test is only offline construction coverage;
actual native parity and actual native body size remain live gates.

Retain only if all gates pass: complete drained SSE/DONE, stop finish, exact
native input1000000 and output1..1024/consistent total, correct complete answer,
no resource cancellation, final identity/source/allocation/other-model checks,
7% GPU reserve,15% host reserve,650GiB cgroup and unchanged ECC. An answer capped
at length is unproven even if its visible JSON looks complete. Successful state:
`PASSED_RETAINED_PENDING_PRODUCTION_PROMOTION`. The exact candidate remains warm
when the job exits. No ExecStop/ExecStopPost removes it. Source/image/owner nonce,
container ID, final resources and reboot behavior are durable. Sova stays paused;
root's later user-return work promotes only after reviewing actual success.

On failure/timeout/abort the job validates and stops **only its exact owned ID**,
waits for Docker Running=false/PID0 and no captured cgroup processes, then uses
the unchanged production owner's `resume` and verifies480K plus other models.
It retains the stopped candidate and evidence, never deletes unrelated state.
Lost create outcome, changed identity, failed stop/restore or unproven settlement
leaves explicit quarantine. Socket closure is never treated as native settlement.
Late evidence-write uncertainty after all success gates cannot destroy a valid
retained success. Status marks a dead nonterminal job stale/uncertain, no replay.

On reboot the candidate does not auto-start; original desired=running resumes
480K. Retained success is not production promotion. Keep Sova paused during this
H011 handoff regardless of outcome. Any later app start follows current owner and
backend validation; never restore old DBs or manually clear quarantine.

## Budgets, measurements and remaining limits

| Phase | Maximum planned seconds |
|---|---:|
| Startup/allocation |1800|
| Explicit short qualification |300|
| Exact fixture construction/counting |600|
| Main HTTP request |7200|
| Failure restoration |1800|
| Normal supervisor budget |11700|
| Final systemd stop grace |1830|
| Absolute supervisor ceiling including final stop grace |13530|

Main HTTP cancellation is distinct from confirmed native stop: exact-owned
Docker stop has30s grace and45s command timeout, within cleanup. Guards and
control-call deadlines can cross a phase boundary; systemd's final ceiling is
independent. TimeoutStopSec provides bounded restoration after terminal SIGTERM;
if it expires, durable nonterminal ownership becomes honest quarantine. No retry
and no hidden second main request exist. Retained success intentionally outlives
these job budgets. Native watchdog stays at its unchanged300s forward-progress
limit, not a total request wall cap; see `../WATCHDOG-SOURCE-01.md`.

The64K measured TTFT246.468s gives only a linear planning reference:62.68minutes
for1,000,000 input and65.72minutes for1048576 positions. Nonlinear attention,
workspace, memory and quality at1M remain unmeasured. Native input/output usage
is authoritative; client TTFT/rate windows include transport/instrumentation and
must be labeled separately from native logs and full-request averages.
KPool's request-local tail is not restored from reused prefixes, so the pinned
runtime forces radix caching off; removing a flag would not qualify prefix reuse.
Native harness compaction notifications remain estimates, not exact input counts.
No harness agent/compaction or promotion behavior is tested by this runner.
GPU telemetry does not measure wall power or PSU transients. User wiring is Ada
on separate CoreX PSU; three Blackwells on2200W workstation. No power/ECC limits
are changed. Installer, downloads/builds, other models and production policies
remain outside these source changes.

Latest root steering at01:31: user fan adjustment is pending. A future repeat
four-way qualification and later1M launch may follow after fan-ready confirmation,
a passing repeat and root execution handoff. This preparation session does not
wait for that work; no staging/launch or app restart was performed.
