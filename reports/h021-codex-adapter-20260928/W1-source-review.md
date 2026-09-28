# W2 focused cross-review of W1 supplied source — 05:37 UTC

Reviewed W1-codex-launcher-early.ts and W1-gateway-ownership-early.ts plus exact generated request schemas/LICENSE/NOTICE, without execution/VM/inference. Source/interface review only, not deployment acceptance.

PASS interface fit: createRootlessCodexLauncher returns stdin/stdout/exited/terminateAndConfirm matching W2RootlessCodexProcess. It invokes only trusted run-codex.sh, guards Linux/nonroot/modelpolicy/scopedhome/fixedgateway, passes clean explicit env and discards stderr. Native settlement remains separate from gateway settlement. Timeout/nonzero/spawnerror return false, not a false cleanup proof. W2 now retains attempted-launch uncertainty if callback rejects before returning its handle. Both W2gatewayURL and fixture use exact http://10.0.2.2:8081/v1.

PASS ownership design from early source: per-session records outlive token revocation, restart nonterminal records become uncertain, missing recoveryReady or failed durable write prevents proof, unrelated active sessions do not block each other. Existing database tables remain unchanged. Cannot qualify transition callsites without full gateway delta; W1 must verify accepted/draining records settle only on upstream terminal proof.

BLOCKING integration evidence: run-codex.sh and exact supervisor/image/config source must verify exit0 means all owned descendants/container removed, read-only provider config/catatalog and no OpenAI/auth/search fallback; early TypeScript contract alone is insufficient. Need final W1gateway/Responses source for independent focused review and host wiring of GatewayOwnershipLedger.options(), revokeSession and confirmSettlement. Callback source itself not invoked by W2. Default disabled persists.

Latest W2 API: CodexRuntime now has revokeGatewaySession(sessionId) mandatory, mapped directly to W1revokeSession before confirmGatewaySettlement. token onExit still revokes parent runner; broker removes runner after each turn and next turn issues fresh token. FollowuploopbackHTTP fixture PASS. Background processes/browser state intentionally do not persist across turns. Native child/delegation unavailable at this stage; any collab item fails explicitly, and unfinished tool items prevent successful parentcompletion.

No request to broaden authority or wait. Remaining supplied-source limitations reported as NOT_TESTED.
