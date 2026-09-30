# LAST-BUSY-REVIEW17 — source review BLOCKED

One remaining strict-classifier blocker in W1's supplied final source. The two
original ownership findings are otherwise addressed in the reviewed paths.
Live deployment and actual LAST remain NOT_TESTED. W1 owns implementation;
this commit contains review evidence only.

## Finding: exact HTTP version is not verified

**P1, required before source acceptance:** `scripts/h016/final13_long/client.py:40`
checks `response.version == 10`, but Python `HTTPResponse.begin` maps both raw
`HTTP/0.9` and `HTTP/1.0` to 10. `HeaderBoundary` at lines 151–165 observes only
header termination and does not retain the exact final status-line version.

A synthetic `HTTP/0.9 429 Too Many Requests` response with the exact admission
marker, one CL0, complete headers and empty EOF passes the actual
`PrivateConnection.getresponse` classifier (187–199). Actual `client.run`, actual
`reader.request` and actual `client.settle` then persist BUSY_NOT_SUBMITTED,
clear own may-active, and omit the production stop. This violates the required
exact HTTP/1.0 provenance contract: a nonmatching/malformed response must remain
uncertain. The pinned proxy normally emits HTTP/1.0; this is a demonstrated
negative-classifier defect, not evidence of an observed production failure.

Smallest W1 correction: retain and check the exact raw final HTTP version token
before positive classification, without broadening the allowed response or
changing any deadlines. Add HTTP/0.9 to the actual client/reader/settle negative
matrix. Do not fix by accepting more versions or by relying on normalized 10.

## Reviewed behavior and original findings

- Proxy `scripts/runtime/mimo/private_proxy.py:173–186` emits the marker only
  after failed nonblocking chat-lock acquisition, before durable begin/native
  connection/count/generation. The original source diff changes only this branch.
  Upstream responses at 199–202 forward Content-Type and Connection only, stripping
  the marker and upstream Content-Length. One lock spans begin/count/generation,
  full drain, close, disposition finish and release (176–251); detached draining
  retains the lock and quarantines. No new queue or administrative mechanism.
- Client `38–61,166–200` checks fixed private host/port and POST chat route,
  unique exact marker/CL0, duplicate headers, parser defects, allowed headers,
  complete header boundary and raw empty EOF. Body EOF check is bounded to five
  seconds. The version exception above is the remaining blocker. Count route is
  not positively classified; HTTPConnection has no redirect/environment-proxy path.
- Client `304–308,388–398` persists BUSY_NOT_SUBMITTED and clears only its own
  flag; typed propagation is retained by reader `274–285`. No retry/next rung.
  Unit ExecStopPost invokes `client.py settle`; `262–286` validates source and
  authority, then returns for false own may-active before any owner stop.
  Upstream429/reset/incomplete/malformed cases in W1 receipts retain uncertainty.
- Reader `237–254` requires finish enum, typed usage, DONE, no pending data and
  full framing/drain before its single completion-hook call. Client `309–316`
  writes own completion through existing guarded atomic_json before returning.
  Reader checks measurement/guard/global slots only at `255–268`; client's global
  active-request/identity checks are later at `374–380`. Global idle cannot clear
  an ambiguous request. A later Sova caller may fail availability/next admission
  but cannot reset completed own may-active to true. Final snapshot writes repeat
  persisted state, not the callback or per-token durability work. Cleanup can
  fail the result without reclassifying another caller as owned work.
- Reader `128–140,176–236` opens guarded files at boundaries, buffers writes at
  64KiB, caps raw stream bytes at 64MiB and pending line at 16MiB; no per-token
  lease, fsync, guard scan or receipt rewrite. Client `327–343` keeps lightweight
  deadline checks and separate five-second guard receipt consumption.
- Client `93–105,235–259,292–365` retains acceptance/native17/production/Sova,
  source/owner/reader/proxy pins, registered paths, actual capacity, reserve,
  identity, guard and independent systemd gates. Whole-Sova pause/other-three-idle
  authority is replaced by the existing ordinary single-chat-lock contract.
  Sova UI/Qwen/image may stay up; no source in this delta pauses them. Frozen R9
  and helper closure are byte-identical. No unrelated timing/profile change.
  The eight-hour serial 64K then conditional near1M chain remains final-only after
  accepted production and app; root must verify startup/logs/guards, close every
  paid worker and pause monitoring. This review neither dispatches nor qualifies it.

## Exact package and evidence

Base `970fcae8ebff771427754a7f7c6ac9c5cda804d0`; clean initial checkout.
Supplied `SOURCE.patch` applied cleanly to a private HEAD archive outside Git at
`../private-review`. Initial main checkout matched 16 of 24 final hashes; all
24 match after private reconstruction, including adjacent reader and unchanged
R9 closure. All three frozen originals and both W1 raw-test hashes verified.
No originals needed copying. No W1 patch was applied to or committed in this repo.

Supplied W1 bundle hash matches RESULT, but its prerequisite `1a5469b0aac42badab041b069c57c96cc30a4876`
is absent here, so the bundle was not imported. Patch reconstruction plus exact
final hashes establishes reviewed bytes independently. Canonical source manifest
SHA256: `fc906fc5ed73d68d48cc5e32bb577d0247d41b99d2c96c5be4da9f00c629944d`.
See HASH-CLOSURE.json and CHECKS.json for full hashes/provenance.

W1's 29 LAST and 8 proxy tests are reused, not rerun. Their inspected actual
reader/run/settle tests cover the two ownership races, positive BUSY, framing,
cleanup and lock behavior. Existing tests lacked HTTP-version negatives.
New `targeted_missing.py` exercises only seven missing negatives using W1's
actual source harness and in-memory HTTP wire parsing: **6 PASS, 1 FAIL**
(HTTP/0.9 above). HTTP/1.1, wrong/missing marker, timeout, duplicate Date and folded
marker preserve uncertainty and the mocked exact-owner settlement path. No
socket/server or actual systemctl is used. Reproduce with:

`python3 -B reports/h016-last-busy-review-20260927/targeted_missing.py ../private-review`

Native session `01a0e3dd-9332-7960-833b-022910d7c636`; wrapper start
17:15:44.211248UTC, cap480s, hard deadline17:23:44.211248UTC. SESSION.json records
report time, not invented process exit; wrapper owns actual exit later.
AGENTS and supplied current handoff/readme/prior review read. Historical H016 plan
read for context; designated local H016-20260927/STATUS.md is absent. No remote
contact, inference, service/data/credential action, build/download, subagent,
source implementation, push or paid waiting. Root handles publication.
