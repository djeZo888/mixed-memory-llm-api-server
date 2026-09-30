# H021 acceptance contract

This matrix qualifies an optional local Codex preview. It does not qualify model quality, repeat capacity measurements, or establish MiMo live compatibility while H019 owns that runtime. Use the exact CLI/source/schema pin and exact candidate source for each result.

## Protocol and ownership gate

- Capture a sanitized real pinned Codex request against a protocol fixture. Inventory all emitted tool types, history types, instructions, reasoning, context and output settings. Preserve a compact fixture; never persist credentials or unbounded model output in Git.
- Complete a short Qwen tool call, tool result and final continuation using shared admission. Include two calls with distinct IDs in protocol fixtures. Tool schemas that cannot be represented faithfully must fail explicitly.
- Verify stream delta/order/terminal usage, partial disconnect, queued cancellation, accepted-request draining and uncertain ownership. No upstream retry after uncertain dispatch. Parent/child/compaction use the same request slots.
- Preserve provider context limits and 65,536 output ceiling. Count actual input plus output reservation; a tiny request can verify capacity configuration without generating 64K output.
- Reject unsupported response-history IDs, encrypted reasoning state and media rather than silently discarding them.

## Engine and persistence gate

- Existing session migration retains MiniMax native IDs, messages, event ordering, files and workspace ownership.
- New Codex sessions persist engine/version/thread/turn identity; engine choice is fixed on follow-up. MiniMax stays default.
- Browser reconnect does not re-execute a prompt. Process/service restart marks unfinished tasks interrupted without replay.
- Stop covers native turn/children/terminals and inference queue ownership. Client disconnection alone never proves GPU settlement.
- Tool/commentary/final events use supplied native metadata; absence remains explicit. Context is occupied tokens, not lifetime use. Original chat history survives reduced-threshold compaction.
- No arbitrary browser-to-App-Server RPC forwarding. Rootless container and scoped credential boundaries remain effective.

## Matched short tasks

Run each supported case on both engines against the same Qwen configuration and bounded output/tool limits. Record correctness, elapsed time, input/output tokens if available, retries, tool errors and intervention. Reuse existing tools and fixtures where possible.

| Case | Meaningful acceptance |
|---|---|
| Python | Fix an intentional boundary-condition bug in a small supplied function and pass a prewritten independent test. |
| C/C++ | Correct a small bounds/logic defect, build with warnings and run the supplied regression. |
| Node.js | Correct a small asynchronous/validation defect and run the supplied test. |
| Public research | Query local search and open one public primary-source page; final answer links the page actually read. |
| PDF/datasheet | Read a supplied small PDF and answer one verifiable numeric/unit question; create a simple PDF artifact where supported. |
| Image | Call existing image capabilities and one bounded generation/edit workflow using existing image ownership and approval rules. Generation must not bypass the specialist service. |

A failed meaningful task remains a failure even when the tool transport succeeds. Avoid open-ended retries or prompt tuning to claim a pass. One diagnosed repair and focused repeat is reasonable; retain the first failure.

## Delegation and offline checks

- A tiny delegated Qwen case verifies parent-slot release and independent child IDs. Short overlapping cases may exercise both Qwen instances after root-coordinated lane/thermal checks; no stress test.
- MiMo routing and request validation use fixtures only during H019. Live frontier continuation and full engine-to-frontier acceptance remain NOT_TESTED, with a clear UI/capability gate.
- No OpenAI model login, inference/search fallback, host credentials or administration sockets enter task containers. Local coding runs with external network unavailable; external research reports offline state accurately.

## Preview rollout

Only deploy exact reviewed source and pinned container after protocol and lifecycle gates pass. Preserve database/files and old releases; retain H020 status identity fix and live MiMo selector. Verify public UI, new-chat engine selection, old chat history, follow-up, stop and reconnect. Leave existing long MiMo process untouched. Publish PASS/FAIL/NOT_TESTED per row and rollback procedure; do not claim full acceptance from unit tests alone.
