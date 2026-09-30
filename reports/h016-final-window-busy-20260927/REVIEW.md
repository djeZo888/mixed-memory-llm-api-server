# BUSY16 — held retiming PASS; LAST client deployment BLOCKED

Base `5e9ba691c94900a6b3b214a86f83a7cf46b4fbcf`. Source-only review of exact private
frozen inputs, all five hashes verified. EARLY-BUSY.md was delivered to task root
at16:54:04UTC, about79s after the wrapper start. No frozen input/runtime edit,
host/VM/BMC/model contact, inference, services/data/credentials, build/download,
subagents, push or paid waiting. H016 parent task STATUS.md was not present at
the supplied local tasks path; current held PREP15 HANDOFF/ACTIVATION/closure and
user instructions were read. Historical H016 plan does not override this scope.

## Source findings and smallest W1 delta

1. **Unsafe ownership inference:** `client.py:270–275,294–300` writes may-active
   before HTTP and preserves it on failure. `client.py:187–214` then stops the
   pinned production owner. The exact owner can be running someone else's Sova
   request after our local rejection. Process identity is not request identity.
   Frozen client has no safe local-BUSY path; deployment remains BLOCKED.
2. **Exact local response:** proxy `127,132–136,144–180` yields HTTP/1.0 status429
   Too Many Requests, Content-Length:0, empty body, close, plus standard Server
   and Date. Authentication (one Bearer), private subnet, exact route and body
   checks precede failed nonblocking lock acquisition. Native connection/count/
   generation and durable begin have not happened. No explicit provenance marker
   exists. Upstream429 at `191–196` instead has Content-Type and Connection:close,
   without forwarded Content-Length or arbitrary headers. This pinned source's
   shapes are disjoint; status429 alone is not. Deployed provenance is NOT_TESTED.
3. **Recommended explicit contract, not implemented:** at this one failed acquire
   branch emit `X-H016-Admission: rejected-local-busy-before-native-v1`, keeping
   status429, Content-Length:0 and empty body. Continue stripping that header on
   every upstream response. No lock-order or other error-status change needed.
   Validate one exact marker, one Content-Length:0, empty fully framed body, no
   Transfer-Encoding/Content-Type/Connection contradictions, and exact authenticated
   private HOST/PORT + POST chat route. Do not accept redirects, arbitrary origins,
   duplicate markers/lengths or parse/transport failures. The fixed HTTPConnection
   adapter (`client.py:108–130`) bypasses environment proxies and redirects; it
   currently does not classify responses. HTTP is private bearer-authenticated;
   the marker is source/route provenance, not a cryptographic server attestation.
4. At the actual HTTP boundary, retain the validated BUSY disposition across any
   reader error conversion. Persist `BUSY_NOT_SUBMITTED`, own may-active=false,
   native settlement NOT_APPLICABLE_TO_THIS_UNSUBMITTED_REQUEST; end without retry,
   next rung or owner stop. No claim that someone else's native work is idle.
   `settle` must no-op on that persisted disposition without weakening source/
   exact-owner protection. Upstream429, other statuses, reset, timeout, malformed
   HTTP, ambiguous EOF or incomplete reply retain UNKNOWN/possibly submitted and
   existing exact-owner settlement coordination. No silent replay or dummy proof.
   The selected R9 reader is not supplied in this input: W1 must show the typed
   disposition survives its actual reader, including ExecStopPost behavior.
5. **Shared-lane completion race:** `client.py:277–292` accepts own terminal/drain/
   slot-idle proof, then waits/checks global active_requests==0 before persisting
   may-active=false. A new Sova request in this gap can fail that global check and
   leave our flag true. W1 must preserve authentic per-request completion and clear
   our settled rung's flag durably before unrelated shared-lane availability can
   fail; never interpret another request becoming active as our unsettled work.
   A global idle snapshot alone must never clear an ambiguous request. Confirm this
   ordering against the actual reader proof; no new queue/admin framework.
6. **Lock proof:** proxy `173–245`: acquire(False) -> begin -> native count -> native
   request -> read1 through EOF -> connection.close -> disposition.finish -> release.
   Failed acquire does not release the existing holder. Downstream broken pipe,
   reset or timeout switches to detached draining, retains lock until upstream
   drain, then quarantines nonterminal/detached disposition. Upstream errors and
   malformed streams quarantine; they do not prove settlement. Thus LAST needs no
   global Sova pause. Remove its pause/exclusive-other-model-idle requirements in
   `client.py:62–63`, associated frozen README and tests; retain existing source,
   acceptance, capacity, guard and exact-owner checks. Parent Qwen/Sova UI/image
   stay up. Foreground app acceptance/paired promotion keeps its separately owned
   exact app-owner stop. W1 owns actual fix and deployment.

## Retimed active held packet

Explicit foreground extension45min: global18:33:08UTC; local hard settlement
18:30:00; calendar stop18:29:30+30s grace. Latest theoretical inference18:14:30
minus overhead, with launch earlier by measured preflight. No static full-envelope
cutoff. Minimum720s AFTER both measured preflights,180cleanup, work<=1200,
supervisor total<=1380, systemd runtime<=1470+30. Local termination remains distinct
from native UNKNOWN. Only held wrapper/preflight/supervisor, focused clocks and
procedure references changed. Profile045d, prompts, live assertions and all17
advertised schemas are byte-identical to base. Approved combined bash child
read/edit/check/continuation plus parent independent verification, markers and
native IDs remain required; neither all17 execution nor separate read/edit calls
was introduced. Existing qualification/capacity/source gates are unchanged.

This retiming supersedes PREP15 timing, not its original test record. CHECKS.json,
SESSION.json and their raw-test hashes remain unchanged; original source closure
is archived here. New raw test output is task-root busy-tests.txt, clock-tests.txt,
driver-tests.tap and syntax-holds.txt, with hashes in CHECKS.json here. Five clock,
four driver and five BUSY tests PASS. BUSY fixtures execute the actual hash-checked
Handler AST with mocked HTTP streams/lock/disposition; no socket/server or owner
module executes. They prove local rejection is before dispatch, upstream429 cannot
forward a marker, lock through clean/detached drain, quarantine on malformed SSE,
and the **proposed** marker predicate's positive/negative cases. They do not prove
an implemented client fix, actual native settlement or a deployed contract.

Required W1 regression at its real reader boundary: validated local BUSY clears
only own flag, persists once, no next request/no production stop; upstream429,
other errors and incomplete replies never enter that branch; verify marker stripping
and lock drain; simulate another Sova request starting after our authentic settled
rung to ensure failed global availability cannot stop it. Frozen input tests do
not cover these behaviors and were not rerun as substitute acceptance.

No dispatch/activation. Final image awaits authentic completed qualification and
clean production pins. Background LAST64K→near1M is only the final action AFTER
accepted production/app/native, then all paid workers close and user nudges later.
No new GO file, permission workflow or background job was created.
