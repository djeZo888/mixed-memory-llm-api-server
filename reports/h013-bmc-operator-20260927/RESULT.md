# H013 BMC Operator discovery — read access proved, channel control not yet qualified

Native task `01a0e13b-4708-7ae2-ac5d-959157e52c8d` on mac-worker2. Base
`8ef96c7482ac1af1685f31be20fe35bdc918dcf1`, isolated branch
`worker2/h013-bmc-operator`. Launch **2026-09-27 04:59:13 UTC**; original
absolute deadline **05:19:13 UTC**, root requested finish by05:18. Early evidence
was written before05:03, within five minutes. Last private connection ended
at approximately05:11:01. No monitoring/background loop or paid waiting.

## Findings

| Item | Actual evidence |
|---|---|
| Endpoint | All BMC connections originated on ai-harness, exact10.156.100.40:443 |
| Interface | AMI Redfish1.11.0, RTP13.03; Managers/Self firmware2.01.38, model449963100 |
| Board identity | Chassis manufacturer/model are generic/blank; specific board identity not independently proved by this API |
| Dedicated login | Protected credential username is sova; Basic-auth Thermal GET200 versus unauthenticated GET401 proves authenticated read access |
| Exact fan | `/redfish/v1/Chassis/Self/Thermal#/Fans/4`, NameCHA_FAN3, MemberId4, SensorNumber54, OwnerLUN0 |
| Fresh reading | At05:10:32, raw Reading14640, HealthOK, StateEnabled |
| RPM | **Unverified**: firmware omits ReadingUnits. DMTF permits RPM or Percent and supplies no default; magnitude alone is not unit proof |
| Current mode | Thermal.Oem.Mode=`Manual` at05:10:32 |
| Configured curves | Eight Oem.PWM records retained completely, including Index, Source, all five temperature/duty points |
| Actual duty | Not exposed/proved; curve duty points are configuration, not measured instantaneous duty or RPM ramp |
| CHA_FAN3 control binding | **Not proved**: PWMName, PWMNum and display-index tuple require successful UI API readback |

Thermal array entry3 is **CHA_FAN2**, not CHA_FAN3. PWM records3 and6 each have
all five configured duties100, but neither is proved bound to CHA_FAN3.
The user's full-speed setting was left unchanged; this session cannot certify
its instantaneous duty from the available interface. Sensor collection has no
advertised54_0 resource, so no such URI was guessed.

## Permissions and authentication limits

| Method/path | Result | What it establishes |
|---|---|---|
| GET `/redfish/v1/Chassis/Self/Thermal` | 200 with Basic auth; AllowGET,PATCH | Read authorization and advertised methods only |
| Same GET without authentication | 401 | Successful authenticated read is meaningful |
| GET `/redfish/v1/AccountService` | 403, Security.1.0.InsufficientPrivilege | Cannot inspect AccountService with this credential |
| GET advertised privilege registry | 200 | Thermal PATCH requires ConfigureManager; AccountService GET requires ConfigureUsers **or** ConfigureManager |
| GET `/api/fanctrl/mode` with Basic auth | 401, Invalid Authentication | Redfish Basic auth does not establish this UI API session |
| POST `/api/session`, first documented form request | 401 | Failed login; first filter retained status and response key names, not numeric error value |
| One protocol-corrected POST `/api/session` | 401, code1009, `Could not login` | Still unable to establish UI session; no further attempts |

The second and final login added the installed jQuery `X-Requested-With:
XMLHttpRequest` header and same-origin Origin/Referer. Credentials were unchanged.
No successful session, cookie or CSRF token was exposed in output or saved;
no session logout was attempted because neither login was accepted. This does
not establish whether web access, account policy, session policy or another
condition caused1009. No password/role/account change was attempted.

The account's Operator designation is user-supplied; an actual current-account
RoleId readback was unavailable. No other account collection was requested.
AccountService403 is not grounds to request Administrator. Installed UI gates
global mode/source controls at Administrator; ManualView gates per-PWM controls
below Operator. Client UI gates are distinct from actual backend authorization.
**No fan write, including a no-op permission probe, was made.**

## Exact installed control contract and remaining gap

`UI-SOURCE.json` identifies the installed AutoView, ManualView, ManualItemView and
SourceView with source hashes. Vendor implementation text remains in private
evidence; the public record describes the observed API contract. The UI advertises these exact read endpoints:
`GET /api/fanctrl/PWM`, `/api/fanctrl/last_source`, `/api/fanctrl/source` and
`/api/fanctrl/mode`.

ManualView renders each returned record's `PWMName`, uses its array/display
index as `PWMIndex`, and takes `PWMNum` from the record. ManualItemView reads
`CurrentPWMdata` as **five `{Temp,Duty}` curve points**, and Save sends
`PUT /api/fanctrl/PWM` with fields `PWMIndex`, `PWMNum`, `PWMSrc` (hardcoded0 in
this UI) and `CurrentPWMdata` flattened as `[T1,D1,T2,D2,T3,D3,T4,D4,T5,D5]`.
Thus this is a **curve-configuration interface**, not a proved volatile direct
duty setter. Nonvolatile lifetime, write endurance, effect on mode and meaning
of PWMSrc remain undocumented here; treat it as persistent configuration until
vendor evidence says otherwise. No repeated write per poll is acceptable.

The global UI setter is `PUT /api/fanctrl/mode` with `{"FanMode":3}` for full
speed, with an Administrator client-side gate. It is recorded solely as source
evidence: it has no channel selector and is **not the proposed integration**.
Keep global FanMode, PWMSrc and every other fan unchanged.

**No executable CHA_FAN3-only100% invocation is qualified.** Supplying a numeric
PWMIndex/PWMNum now would guess the missing binding. Even the UI's hardcoded
PWMSrc0 cannot be assumed to preserve the existing source selector.

Next safe verification: resolve the code1009 web-session failure using the
installed login protocol and read-only inspection of this account's web-login
allowance, without changing its credential/role or dumping accounts. After a
successful owned session, make one GET of the four advertised endpoints above;
retain only fan data/current role metadata, identify exact PWMNameCHA_FAN3 and
its actual index/PWMNum, and save original CurrentPWMdata/source/mode. Obtain
vendor confirmation of PWMSrc and persistence/ownership if these are not in the
readback. Root then reviews one concrete header-only100% request and readback
before any subsequent cool50% test. If login remains unavailable, vendor
confirmation for installed firmware2.01.38 is the next safe route; do not guess
Redfish OEM PATCH fields or switch to IPMI raw commands.

## Future controller requirements retained for root

- Source temperature must be authenticated, fresh telemetry for exact Server
  GPU UUID `GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528`; no CPU/BMC substitute.
  This task did not contact ai-vm or sample that GPU.
- Requested policy:100% at >=70C;50% below70C only when valid/fresh/online;
  unknown/stale/GPU offline must stay100%. Independent85C load cutoff remains.
- If flat curves are the only supported route, change only the bound channel's
  five Duty values, preserve **every Temp breakpoint and other field**, and
  write only50↔100 transitions or bounded readback correction. Verify exact
  PWMSrc preservation first. No host/network daemon has been implemented.
- Readback must separate configured curve, actual duty (if available), tachometer
  unit and observed RPM ramp. A failed controller cannot be assumed to issue a
  final100% write; independently qualified failure ownership/watchdog behavior
  is required before lowering below100. ASUS's documented CPU/60% fallback
  fails the required fail-full policy.

## Security, counts and evidence

32 HTTP requests:30 GETs and2 authentication-only POSTs; zero fan/control POST,
PATCH, PUT, DELETE or OPTIONS. 34 successful actual-socket certificate pin checks
(32 request sockets plus2 certificate-only inspections); two additional normal
CA validation handshakes failed before any HTTP/credential send. Total36 TLS
connections. No changed pin, redirect following or reconnect was observed.

Every request pinned leaf DER SHA256
`0f1ee547edbdbca346ea2d884d3271a8f28351d57a16baa911c388198063f7ec`
before authentication. Reconnect code rechecks. CA error20 was `unable to get
local issuer certificate`; certificate expired1989 and its SAN lacks10.156.100.40.
Receipt16 initially treated OpenSSL's exit0 as IP match; receipt18 corrects that
local interpretation using its explicit `does NOT match certificate` output.
The flawed display field never governed trust: exact DER pin always did.

Credential and private parents were user-owned file0600/directories0700 with
protected ancestry; no symlink credential accepted. Secret unchanged at
`/home/user/.config/sova-private/bmc.json`. Probe scripts are in the protected
ai-harness task directory `/home/user/.config/sova-private/h013-bmc-operator-20260927`.
No host raw authenticated receipts were written. Secrets remained in host memory;
no credentials/session tokens/headers/cookies were copied to Mac/repo/argv/env.

`RECEIPTS.json` is the compact filtered record of every phase and request, with
SHA256 of original filtered phase files. Originals are preserved under task-root
`filtered-phase-receipts/` (directory0700/files0600), not lost by compaction.
`SOURCE-REVIEW.md` gives official source URLs and boundaries. Offline pin/auth,
reconnect, filtering, credential-permission and bounded-response tests passed (11 checks), together with3 offline UI-session
checks;
these are client safety checks, not fan-control acceptance.

No ai-vm/Proxmox contact, inference, fan-speed/mode write, raw IPMI, reset,
reboot/power/BIOS/firmware operation, service change, Worker1 message or GitHub
push occurred. No Sova/model settings were touched. Flash1M label/profile work,
ECC/integrated fans, root's later BMC write phase and all model work remain outside
this discovery task.
