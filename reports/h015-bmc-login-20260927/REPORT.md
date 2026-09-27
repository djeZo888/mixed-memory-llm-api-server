# H015 single BMC access check

**Login succeeded; fan configuration readback did not.** At 08:16:01–08:16:02 UTC
on 27 September 2026, the reviewed UI probe made exactly one form login from
ai-harness to `10.156.100.40:443`. The owned session was accepted and logged out.

| Operation | HTTP result |
|---|---:|
| POST `/api/session` | 200, accepted owned session |
| GET `/api/fanctrl/mode` | 500 |
| GET `/api/fanctrl/PWM` | 500 |
| GET `/api/fanctrl/source` | 500 |
| GET `/api/fanctrl/last_source` | 500 |
| DELETE `/api/session` | 200, own session only |

All six actual TLS sockets matched leaf DER SHA256
`0f1ee547edbdbca346ea2d884d3271a8f28351d57a16baa911c388198063f7ec`
before any credentials or session authentication were sent. No redirects,
retries, protocol variants, static JS retrieval or optional Thermal GET were made.

The reviewed probe recognizes ownership only after HTTP 200, its success marker
and an in-memory CSRF value; reaching the four GETs and owned logout establishes
that condition. Authentication response fields, cookies, tokens and headers are
omitted from the receipt. Fan GETs retained no whitelisted configuration fields
(`data: {}`); this means unavailable readback, not empty fan configuration. Error
response bodies were not retained by the reviewed fan filter, so no backend error
code or cause is claimed.

**The API result alone does not establish the required account change.** These
HTTP 500 responses do not establish a missing privilege. The later user-observed
Operator/Administrator comparison below supports a role-dependent restriction.
The user-reported screenshot settings (Enabled; channels 1/2/8 Operator; KVM and
VMedia off; SNMP ReadWrite/SHA256/AES) were not independently queried or changed.
No account, role, password, SNMP, global mode/source or fan setting was written.
External fans remain at the user's existing 100% setting without intervention;
this check did not independently measure instantaneous duty.

## Mapping and controller boundary

Current `PWMName == CHA_FAN3`, array/display index, `PWMNum`, full five-point
curve, mode and source values **could not be obtained** because all four reads
returned 500. Historical H013 mapping gaps and configuration snapshots are not
current proof. No numeric PWM binding or current configuration is inferred.
Fan-write authorization remains **UNQUALIFIED**; no write, including a no-op,
was attempted. Successful login does not establish fan GET or write authorization.

Remaining prerequisites for a future CHA_FAN3-only 50/100 controller, retained
from the reviewed H013 contract:

- Successful authorized reads must establish the exact `PWMName`/index/`PWMNum`
  tuple and preserve the complete original curve, mode and source values.
- Qualify backend write permission, `PWMSrc` preservation, persistence/endurance
  and ownership semantics for the exact channel; preserve every temperature
  breakpoint, other field and other fan. Root must review the concrete channel-only
  100% request and readback before a later explicitly authorized 50% test.
- Qualify actual duty/tachometer units and physical response separately from a
  configured flat curve. Flat 100% is not instantaneous-duty proof.
- Use authenticated fresh telemetry for the exact Server GPU identified in the
  reviewed H013 report: 100% at >=70 C, 50% below 70 C only when fresh and valid;
  missing/stale/offline input must not lower cooling. Retain the 85 C cutoff.
- Independently qualify fail-full behavior on controller/host/network failure
  before lowering cooling; a last attempted write is insufficient. If curve
  configuration is the supported interface, write only transitions or bounded
  corrections after persistence/endurance review, never every polling cycle.

These are future prerequisites, not authorization to make writes in this task.
No VM/model/build/download/benchmark work, subagents or push occurred.

## Execution and review evidence

`RECEIPT.json` contains sanitized current HTTP results, request/pin counts,
probe timestamps, exit code, exact source hashes and the sole deadline delta.
The protected host scripts matched the source-base copies byte-for-byte:
`probe.py` c07a4fc9958a50d611ad42c4a3eec547ddb9387ddce8d80ab14b31c49028ecd0;
`ui_probe.py` e13f59b3006e1ef0d10594b6f6397874112720d0d79f111211b77bcad04dcfa9.
Only `probe.DEADLINE` was refreshed in process memory, from epoch 1790486340
(05:19:00 UTC) to 1790497320 (08:22:00 UTC), delta +10,980 seconds. Original local
and protected remote source files are unchanged. The reviewed corrected jQuery,
Origin/Referer and form behavior is unchanged; no new auth implementation was made.
The output wrapper only removes auth metadata/key names before persistence.

`STATUS.json` records native session, wrapper start/deadline and probe exit.
No new tests were needed for documentation and a runtime deadline refresh; prior
probe tests were not replayed. New JSON was parsed, route/count/status evidence
checked, and new files inspected with whitespace and pattern-based secret scans.
The parent wrapper writes the actual native exit status/time after this session
ends. Bundle SHA and commit are recorded in the task-root `RESULT-DELIVERY.json`
and final handoff, outside the bundle to avoid a self-referential digest.

## Source-only continuation and actual exit

The original deadline was 08:22:50 UTC. Source-only packaging finished and the
native session exited successfully at 08:23:13, 23 seconds beyond that limit.
No BMC request occurred after 08:16:02. This overrun is not a deadline extension
or authorization for another task; the worker is stopped.

The latest **user-observed browser comparison** is that Fan Control fails or is
unavailable for sova Operator but works as Administrator. This is separate from
our four API HTTP 500 responses and supports a role restriction. It does not
identify the exact backend error or authorize an account/role change. The earlier
statement about no demonstrated required account change remains bounded to the
API evidence; the comparative browser evidence adds support for role dependence.

**The reviewed error cleaner dropped HTTP 500 error details.** Its fan-field
whitelist yielded `{}`; the original error bodies were not retained. Their exact
cause cannot be recovered from the sanitized receipt.

Readily available private local login/XHR excerpts were scanned without printing
or copying vendor code or authentication data. They show cookie API/session
storage usage, CSRF-header setup and the jQuery XHR marker. This limited marker
inspection establishes neither complete browser/probe cookie equivalence nor a
specific mismatch. No conclusive cookie/header mismatch was demonstrated.
`FOLLOWUP.json` records these source-only findings and distinct evidence origins.
No network request, login, write, test or probe was made in this continuation.

## Root review of the user's admin screenshot

The administrator screenshot labels the panel **Zone4(CHA_FAN3)** and shows a
flat 100% blue curve, with visible duty fields all at 100%. Its horizontal axis
is **CPU Package Temperature**, not the NVIDIA GPU temperature. This supports
the user's configured full-speed setting and establishes the displayed zone
name, but does not prove instantaneous duty or the API's zero-based index and
PWMNum. Do not turn the displayed zone number into a guessed API address.

The user reports that this page fails/is unavailable under sova Operator and
works as Administrator. The next controlled account change to test is sova
Administrator on its enabled channels, preserving its password and other
settings, followed by one fresh owned-session read. This is a proposed user-side
change, not an executed role elevation or proof that all setters will succeed.
No SNMP permission change is needed to test the existing HTTPS route.

Leave the current curve at 100%. A later controller must read the exact server
GPU temperature from ai-vm; setting a 70 C breakpoint on this CPU-temperature
curve would not implement the requested GPU policy. Existing channel mapping,
write semantics and failure behavior remain to be qualified before low duty.
