# H040 A protocol and supervisor receipts — source preparation

The source candidate implements a bounded optional native `item/tool/call` seam,
an immutable host-authored `read_original` scope, and host-only launch/cleanup
receipts from the existing exact-random-container supervisor. Ordinary chats
retain their existing transport/settings and do not register dynamic tools.
**Probe admission is disabled. Linux transport and model-facing scope remain
NOT_TESTED.** Physical container evidence cannot qualify B's empty-root/no-tool
contract. No VM access, deployment, inference, GPU/fan transition or native binary
test occurred in this phase.

Base: `a0bfe59f5dfd83a7436061b46e25d8626feb9102`. Adopted native session:
`01a0f4d8-9d87-78d0-94cc-5a73d9056be2`. Its selected local session metadata confirms
`gpt-6.1-sol`, effort `ultra`, and this isolated checkout. Final commit/bundle and
actual outer exit belong to private `../output/RESULTS.json` / root receipts.
The earlier Qwen start label “fast” was inaccurate: UUID93 is slow Gen3 x4.
Actual old receipts were retained; no current VM inventory is claimed here.

The pinned native source is Codex 0.158.0,
`064c6b8c737f5b41d171fdda80bd9ef10ad06eb3`, reused from the private H039 cache.
These compact pointers support the implementation; upstream main was not used:

| Pinned file under codex-rs | Lines | Consequence |
| --- | --- | --- |
| app-server-protocol/src/protocol/common.rs | 1795–1799 | Native server method is `item/tool/call`. |
| app-server-protocol/src/protocol/v2/item.rs | 1654–1685 | Thread/turn/call/tool/arguments identity; namespace optional; text content items and success response. |
| app-server-protocol/src/protocol/v2/thread.rs | 99–106, 145–151 | Host base instructions and experimental dynamic tool registration. |
| app-server-protocol/src/protocol/v2/thread.rs | 184–218 | Actual thread/start response exposes sandbox policy separately from config/tool registration. |
| app-server/src/message_processor.rs | 975–978 | Experimental API capability gate. |
| app-server/src/request_processors/thread_processor.rs | 1448–1452, 1494–1507 | Dynamic tool validation and forwarding. |
| app-server/src/bespoke_event_handling.rs | 1084–1115, 1206 | Canonical item start precedes the server request; pending request abort is separate. |
| app-server/src/dynamic_tools.rs | 18–55, 59–111 | Response decode/submission and fallback handling. |
| core/src/tools/handlers/dynamic.rs | 174–250 | Native pending response wait and completed/failed item; no proven semantic precommit veto. |
| app-server/src/outgoing_message.rs | 215–229, 598–631 | Thread-owned pending request cancellation; no host replay. |
| core/src/session/mod.rs | 745–749 | Saved dynamic tools may restore; this seam only admits a fresh ephemeral probe. |
| protocol/src/permissions.rs | 598–615 | Native read-only includes reading root; it does not prove `readRoots:[]`. |

`codex-probe.ts` exports `createCodexReadOriginalProbe({sessionId,runId,checkpointId,
baseInstructions,originals:[{reference,bytes:Uint8Array}]})`. E supplies its safe
frozen capture. Bytes are copied into a private one-shot scope; public references
carry lengths and SHA256 only. The reader accepts exact reference/byte-offset/
limit arguments, no paths, URLs or oracle handles. Limits are 32 references,
64 MiB originals, 64 KiB host instructions, 8192 bytes per read, 16 reads and
64 KiB total returned text per probe. Invalid UTF8 byte splits return a bounded
failure. Cancellation suppresses late responses.

Connection inbound IDs occupy a separate bounded space (64 total, four pending,
128-character string IDs). Identical requests do not repeat reads/writes;
conflicting duplicates, malformed IDs/results, unsupported calls and timeouts
fail closed. Native stdio cannot forge reserved host serialization observations.
Engine ownership binds the real canonical thread/turn/item/call and arguments.
Namespace omission/null is accepted; conflicting namespaces and changed repeated
start frames are rejected. Success requires an actual read. Serialization alone
does not call `onOriginalReadSettled`; the matching native completed item must
consume the exact response. Turn completion cannot substitute for an unfinished
call. Missing usage stays unknown and does not reject a settled completion.

`OwnedCodexProcess` exposes optional `launchReceipt` and `settlementReceipt`
promises, preserving old fake-runtime compatibility without native qualification.
`CodexRuntime` exposes receipt requirements and trusted observation callbacks.
Private receipt types are deeply frozen and branded only by validators; copied
JSON is not a genuine receipt object. Launch validates exact source hashes,
nonce/run/session/timestamps, observed child ancestry/boot/start/cgroup identity,
actual image pin/rootless/user/caps/security/network and exact bind scope.
Inspected additional mounts are recorded; unexpected named volumes or oracle
mounts are rejected. Strict Podman inspection representations are unqualified
until actual Linux acceptance.

The optional channel is a fresh 0700 host-only directory under
`/run/user/UID/ai-harness-codex-receipts`, outside every container/model mount.
O_EXCL/O_NOFOLLOW 0600 JSON is bounded to 32 KiB and published with a one-shot
ready marker after fsync. Nonce/transport environment is host-only, never added
to native container environment. No stderr, model frame, token, config or log
body is used as attestation. Producer bytes and ancestors are checked. Inspection
capture has a real 1 MiB/three-second bound; launch inspection is bounded to ten
seconds. No second lifecycle manager or shared-container cleanup is introduced.

Settlement records raw engine exit separately from requested Stop, CLI reap,
`rm` exit0, exact `exists` exit1, and pipe joins. A nonzero engine exit is retained
even when cleanup succeeds; uncertain cleanup never passes. The shared Stop
deadline starts at cleanup, not launch age. Long-lived sessions retain their
receipt promise. Missing/rejected launch proof still awaits bounded actual
supervisor exit before returning uncertainty. Gateway settlement is independent.

`composeCodexHost` rejects any original-probe selection until separately observed
model-facing scope exists, even if a Linux transport policy is supplied. A fake
probe requests read-only and checks the returned sandbox type; this is plumbing,
not empty-root isolation. The mounted reviewed config still contains builtin,
MCP and agent capabilities. No audited native no-tools override is exposed.
Both global and per-session image acceptance are blocked for a probe.

Minimum cross-owner proposal: A observes canonical native thread policy and tool
registration; the gateway/responses owner observes and gates the **entire** actual
provider tools envelope for the same owned run/thread/window, retaining schema
hashes and rejecting extra tools. Summary may allow only the reviewed original
reader; recovery must meet B's no-tools contract. E joins those genuine
observations with physical receipts and B's scope requirements. Dedicated gateway
transport needs an explicit approved exception. Denial of parent/oracle/original
paths also requires reviewed fresh mount scope that does not expose them. A did
not edit gateway/responses/store or E/B files and does not manufacture this proof.
Canonical native turn metadata parsing remains a separately owned proposal.

Final source checks: **161 TypeScript fixtures, 12 new Python transport/supervisor
fixtures, six existing affected launcher regressions and three egress guard
regressions PASS**. Server build, strict new-fixture compile, shell syntax and diff
checks exit0. These are synthetic/fake-process tests, not Linux/systemd/Podman or
native semantic acceptance. Unchanged full server suites were not replayed;
root must validate the coherent A/E/B candidate. Private logs retain actual exits,
digests and earlier failures: five initial fixture teardown assertions were
corrected to explicitly close uncertain ownership; an intermediate build had
four TypeScript mount-type errors; one initial redirect failed before npm ran.

Native live retrieval/compaction/isolation/runtime placement remain NOT_TESTED.
Atomic rollback remains NOT_PROVEN. No suitable precommit semantic veto is claimed;
bounded staging/recovery and retained originals remain the proposal. Root next
reviews the source bundle, genuine object interfaces and disabled gates, qualifies
the exact Linux transport/deploy closure separately, resolves native/gateway scope,
then decides any later deployment/live GO. Root collects actual native/outer exits
after this session closes; no launch or intermediate test is reported as that exit.
