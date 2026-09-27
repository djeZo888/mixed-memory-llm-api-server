# BUSY16 early source review — dispatch BLOCKED pending W1 fix

Frozen input hashes match SHA256.json (all five files), including client
73869aaa2e737c44e3381e35f94f13463b15e828ef32fc2255a69b9d165d17c5 and proxy
ad7fea4cbf9fd2b6583c87530325136c858d94c1e28318b71bed682965972a56.

Exact local contention response (proxy lines127,132–136,173–180):
`HTTP/1.0 429 Too Many Requests`, `Content-Length: 0`, empty body, connection
closed; BaseHTTPRequestHandler adds Server and Date. No Content-Type,
Connection header, or explicit origin marker. It occurs after private subnet,
exact one Bearer authorization, exact route, and body validation, but BEFORE
Disposition.begin, native input-token count, or generation. Lock acquisition is
nonblocking; rejection never owns/releases the other request's lock.

Upstream response forwarding (191–196) emits its status, Content-Type (default
application/json), and Connection: close; it does NOT forward Content-Length or
arbitrary upstream headers. Thus the pinned source has distinguishable header
shapes, but 429 alone is NOT provenance and the frozen client has NO validated
local-BUSY classifier. No live deployed contract has been established here.
Smallest explicit W1 delta: emit one fixed header only at failed chat-lock
acquisition, e.g. X-H016-Admission: rejected-local-busy-before-native-v1, retain
429/Content-Length:0/empty body, and keep it stripped from ALL upstream replies.
Client must validate exact private host/port + POST /v1/chat/completions, complete
HTTP status/headers/body, exactly one marker and Content-Length:0, no transfer
encoding, Content-Type or conflicting header shape before clearing only its own
request_may_be_active. A missing/duplicate/wrong marker is NOT safe BUSY. This is
a proposed contract, not a claim that the frozen proxy already emits it.

Lock order: authenticate/validate body -> acquire(False) -> durable begin ->
count -> native generation -> read1 loop through EOF -> close native connection
-> finish disposition -> release (176–245). Broken downstream pipe/reset/timeout
switches to detached draining, never early lock release or replay; after drain,
detachment/nonterminal data quarantines. No global Sova pause is needed for this
single chat lane. Qwen/Sova UI/image should stay up for LAST. The separate held
foreground app-acceptance exact-app-owner stop remains its own requirement.

Critical client issue: lines270–275 persist may-active BEFORE reader.request;
294–300 retain it for every exception; settle lines187–214 stops the exact
production owner. Owner identity alone does not prove that active request is
OURS. A local lock rejection can therefore stop unrelated Sova work. W1 must
classify validated local BUSY at the HTTP boundary, persist BUSY_NOT_SUBMITTED
with may-active=false, stop this attempt without retry or next rung, and make
ExecStopPost a no-op for that state. Preserve identity checks and uncertain
settlement for all upstream429, other status, reset, timeout, malformed HTTP,
ambiguous EOF and incomplete response cases; none proves native settlement.
No new GO/queue/admin framework. No frozen input or runtime file modified.

Focused mocked proof and retimed held PREP15 packet follow. Final image remains
held for authentic completed qualification and clean production pins. No host
contact or inference was performed.

Additional completion-race finding (full review item5): client277–292 validates
its own terminal/drain/slot-idle proof but waits for shared global lane idle before
persisting may-active=false. A later Sova request can fail that check and leave
our flag true. W1 must durably retain authentic own settlement before a subsequent
shared availability check can fail; no global idle snapshot clears UNKNOWN.
The selected R9 reader is not included in frozen input; actual reader-boundary
and ExecStopPost regression are still required from W1, not proved by our mocks.
