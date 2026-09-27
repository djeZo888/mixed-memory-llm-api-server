# H013 BMC power discovery: no qualified host/PSU measurement

Two authenticated GETs from **ai-harness** to the exact pinned BMC completed
at **2026-09-27 06:16:24 UTC**. Both returned HTTP 200. Discovery stopped because
the returned power semantics are unknown; **no sampler was created or started**.
This finding does not gate or expand H013 or H014/MiMo.

| Resource / field | Observed | Interpretation |
|---|---|---|
| `Power#/PowerControl/0`, `PowerConsumedWatts` | 20 W; Name `Chassis Power Control`; MemberId `0`; PhysicalContext `Intake` | Unknown coverage/acquisition. Does not prove actual system total, wall AC, PSU AC input, DC output, or CPU power. |
| Same entry, `PowerMetrics` | Average/Min/MaxConsumedWatts all 0; IntervalInMin 0 | No usable interval/summary established; not measured zero consumption. |
| `Power#/PowerSupplies/0` | Power Supply 1, `State: Absent`, Type AC, input-voltage type Unknown; input/output/last-output all 0 W | Absent telemetry resource; numeric zeros are unusable, not measured zero watts. |
| `Power#/PowerSupplies/1` | Power Supply 2, same status and values | Same limitation. |

`Power` above abbreviates `/redfish/v1/Chassis/Self/Power`. The power-control
entry provides no retained Status, OEM label, physical measurement timestamp,
or usable sampling interval. Its watt-valued property is not an energy counter;
instantaneous versus cached/averaged acquisition is unqualified. Capacity fields
also report zero and do not establish physical PSU capacity. The absent API
resources do not establish that physical power supplies are absent.

HTTP Date and the recorded client request/response times describe transport,
**not physical sensor acquisition**. BMC source age/cache freshness is unknown.
The 20 W field must not be used as wall AC or a validated comparison channel.
No CPU-specific power measurement was established. GPU board-power sums remain
separate, and chassis metadata does not establish coverage of Ada's separate PSU.

The retained prior Chassis inventory advertised `Power` but omitted its target
from the old filter. One fresh GET `/redfish/v1/Chassis/Self` recovered the exact
`Power.@odata.id`; the second GET followed it. No `PowerSubsystem` link appears
in the fresh chassis. `Sensors` is advertised but its collection was not crawled.
The result is bounded lack of qualification, not proof that all hardware power
telemetry is impossible. No endpoints were guessed.

`GET-EVIDENCE.json` retains allowlisted power values, status, transport times,
response byte counts and SHA256 hashes. Raw authenticated responses were kept
only in host memory, never copied. `discover.py` is this task's one-shot probe,
adapted from the prior tested host pattern with an explicit new deadline; it is
not a long-running sampler. Only its two GETs were executed. Every actual TLS
socket was leaf-DER SHA256 pinned before credentials were loaded or authorization
constructed; reconnect uses the same pin check. Changed pin stops before auth.
No redirect following, credential transfer, cookie/session login, other HTTP
method, VM contact, fan/service change, inference, subagent or push occurred.
The credential stayed in the protected ai-harness host store. Public files
contain API descriptions and hashes, no vendor implementation excerpts.

Task `H013-BMC-POWER-20260927`, parent project task `H013`, native session
`01a0e17f-eac5-7fa2-b574-6767cf2aedc1`, isolated mac-worker2 branch
`worker2/h013-bmc-power`, root base `cb4cdf87b692b3b81b124b54b7c848cfc225175a`.
Wrapper start **06:14:11 UTC**, hard deadline **06:24:11 UTC**, same date;
probe cutoff **06:23:00 UTC**, whole-request bound 10 s. Parent orchestrator
session ID was not supplied. Prior task/session IDs and hashes are in RESULT.json.

Validation: two live pinned HTTP 200 receipts; local source/staged-diff,
whitespace and secret-pattern review. No sampler means the conditional sampler
tests do not apply; no broad test suite or historic readiness replay was run.
The bundle is `../H013-BMC-POWER.bundle` relative to this task's repository,
with the exact root base above as prerequisite. Task-parent STATUS/HANDOFF
record the final commit, bundle verification/hash and completion time.
