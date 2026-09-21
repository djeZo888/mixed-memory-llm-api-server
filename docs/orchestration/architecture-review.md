# Completion architecture review

Reviewed repository snapshot `7171167` on Mac-Orchestrator, read-only. No runtime commands, builds, tests, or SSH were performed. Evidence below is source inspection, not live verification. The current user request authorizes completion and supersedes old planning-only milestone gates; localhost exposure, storage isolation, attribution, and secret protections still apply.

## Minimum completed outcome

1. One selected flagship model actually serves OpenAI-compatible inference with a recorded model revision, artifact/quantization identity, runtime revision/image digest, context limit, memory use, and measured latency. Retain the existing fast model as an explicitly selectable fallback.
2. A client on a worker reaches the localhost-only VM endpoint through SSH forwarding. Document one usable command sequence and model ID. A chat-only endpoint does not establish compatibility with every agent client; prove the exact chosen client.
3. Native tool calling is demonstrated with valid structured arguments and call IDs, tool results are returned to the model, and a bounded agent reads a disposable repository, edits code, runs its tests, and reports the real outcome. The inference VM remains API-only; tool execution stays on the client worker.
4. The selected deployment has a truthful lifecycle status, bounded startup/recovery, explicit boot policy, bounded logs, storage guards, and a reproducible stop/start/rollback procedure.
5. Repository state, deployment identity, worker sessions, test evidence, and remaining limitations are synchronized into committed project documentation. A download or a generated patch alone is not completion.

## Independent task partition

### A1 — Worker2: client/protocol acceptance (start alongside flagship deployment)

Own new `scripts/agent/`, `tests/agent/`, agent usage documentation, and a milestone report; avoid changing `scripts/llmctl`, runtime/model profiles, or live services while Worker1 owns them.

- Implement a small backend-agnostic Chat Completions acceptance runner with explicit base URL/model options, request/overall timeouts, bounded turns, bounded output, and redacted evidence. Probe non-streaming chat, `/v1/models`, unknown model error, streaming completion termination, and native function calls followed by a tool-result continuation.
- Implement or integrate a real tool-executing client. Its tools may inspect/edit files and run an allowlisted test command only inside a freshly created disposable workspace. Reject absolute paths, traversal, symlink escapes, unknown tools, invalid JSON/schema, oversized output, and calls beyond its budget. Never allow model-supplied shell text.
- A meaningful acceptance fixture starts with a failing test and a simple bug. The model must read relevant files, modify the implementation through tool calls, run the tests through a tool, and produce a final answer. Record the initial failure, executed calls, actual diff, final test exit status, model identity, timings, and API usage where supplied. Do not mark a fabricated assistant claim as a test result.
- Fixture tests use a deterministic mock HTTP backend for orchestration/protocol failure cases; live completion evidence is recorded separately once the flagship is ready. Do not claim stock Codex CLI support until its actual wire protocol and a live run have been validated.
- Keep all live VM operations read-only during this task; run through an SSH tunnel opened from the worker. Coordinate even load tests with Worker1's one-active-model deployment lock.

### D1 — Worker1: flagship model/runtime proof

Own model/runtime/deployment profiles, downloads/builds under `/data`, actual backend startup, and performance/resource evidence. Confirm native tool-parser/chat-template support for the selected model and runtime. Publish the exact API model ID, endpoint, context length, parser flags, reasoning options, startup duration, and server limits to A1. Keep a recoverable prior deployment snapshot. Do not install a second independent boot owner.

### L1 — fresh worker session after D1: lifecycle and restart completion

Bring the chosen deployment into the manager, make operations serialized, validate fail-closed network and storage policy, remove implicit smoke fallback, define desired versus observed state, and add bounded startup/recovery. Configure one boot owner with `/data` mount dependencies and preserve intentional stopped state. Verify controlled service restart rather than rebooting the VM solely for this review; label a full boot test NOT_TESTED if not executed.

### V1 — fresh opposite-worker session: integrated acceptance and review

Review the other worker's commit and run the actual client loop over the tunnel against the deployed flagship. Verify single backend, listen addresses, storage/log locations, endpoint/model identity, lifecycle behavior, and previous-model rollback procedure. Run substantive regression fixtures in CI. Synchronize reviewed commits through feature branches; record exact commits in every copy and deployed checkout.

## Source findings and dangerous pitfalls

- **Lifecycle is not yet generic.** `scripts/llmctl:541` accepts only two hard-coded deployments. Unknown model state cannot even be stopped through the manager. `restart --yes` explicitly rejects the current real model (`:1124`). New runtime/model profiles alone do not enable deployment control. Assign lifecycle ownership explicitly.
- **A deactivated model can be resurrected.** `state_for_start` (`:530`) silently selects the smoke deployment when `active.json` is absent. Boot automation must not use that fallback; no selected deployment should remain stopped.
- **No mutation lock exists.** `write_active_state` (`:943`) uses a fixed temporary filename and atomic replace, but concurrent lifecycle operations are not serialized. Two workers/start-stop paths can race. Hold a process lock for the complete deployment transition; re-read state under that lock.
- **Start failure leaves ambiguous state.** `cmd_start` updates state only after readiness; timeout can leave a live container while the selected record still says stopped. Conversely `--no-wait` writes active before ready. Persist desired state and transition/error details; derive observed readiness without presenting failure as success. Keep a safe cleanup/retry command.
- **Shutdown currently depends on preflight success.** Stop/deactivate call the same storage/bind validation path. A broken config or storage-pressure guard can impede shutdown of an unhealthy service. Preserve targeted, identity-checked emergency stop without destructive cleanup.
- **One-model enforcement is incomplete.** Port availability checks only the selected container/port (`:967`). A different backend on another port can retain GPU/RAM. Inventory owned deployments before activation; never stop unrelated containers.
- **Network validation is textual.** `ensure_localhost_compose_bind` (`:636`) looks for known strings and one localhost binding, not every effective mapping. Validate rendered structured Compose configuration, all published addresses, host-network use, and actual listeners; preserve localhost-only defaults.
- **Health is not generation proof.** Readiness checks `/v1/models`; this may remain responsive while generation fails. Keep liveness cheap, readiness bounded, and a separate explicit inference/tool acceptance probe. Startup deadlines must reflect measured large-model cold start. An unhealthy Docker health check does not itself restart a container.
- **No boot policy exists.** The real-model template has `restart: "no"`; operations documentation is mostly placeholders. Do not combine Docker automatic restart with a competing systemd supervisor. If systemd owns lifecycle, its mount/ordering and start timeout must accommodate the actual model; stopped intent must survive boot.
- **Current API checks are too weak.** `scripts/api/smoke-openai-chat.sh` only asserts nonempty assistant content; it has no tool loop or streaming/auth tests and no curl timeouts. CI only checks required files, secret-like filenames, and Markdown links. Put actual new fixture tests into CI and record live tests separately.
- **Docs contradict current code/state.** README still says M0 bootstrap, operations are future tense, and old milestone gates are interleaved with current results. Rewrite compact current-state/usage/operations around the completed deployment and explicit user authorization, without replaying old stages.

## Access and synchronization decisions

Default usable access should be `ssh -N -L 127.0.0.1:<client-port>:127.0.0.1:<backend-port> ai-vm`, with the client targeting `http://127.0.0.1:<client-port>/v1`. SSH supplies authentication/encryption without opening a LAN listener. Test this exact path from a worker. A stable localhost gateway is optional; if added, preserve streaming, errors, tool fields, and authentication without leaking keys. Non-local publishing requires the repository's authenticated exposure policy and is unnecessary for the requested agent loop.

Synchronize source by reviewed feature-branch commits (or bundles if push access is unavailable), not broad home-directory rsync. Preserve uncommitted work and exclude credentials, model/cache data, session logs, and `.codex`. Keep the worker SSH alias, isolated checkout path, branch/base/commit, fresh Codex session ID, task status, bounded result summary, and deployed revision in the orchestrator task ledger. Deploy from the reviewed commit and record subsequent configuration differences explicitly.
