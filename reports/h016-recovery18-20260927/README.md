# RECOVERY18 — original GLM restoration

Original GLM 1M authenticated readiness passed at **18:17:36UTC**, before the18:23 native cutoff. The fresh canonical row reports available/ready and deployment glm-5.3-flash-1048576-fp8-kt; both Qwens and image remain ready. Native handback is complete for Root/Worker2 to restore original Sova.

Root's direct 18:07 authority and RECOVERY18 clarifications supersede MiMo promotion. No third MiMo load, adoption or inference was performed. The corrected failed container and historical first-attempt archive remain preserved. No deployed source, hardware policy or node service changed.

At18:11:31 the exact second MiMo container had already exited18:05:00 with PID0, OOMKilled=false, old native PID/cgroup absent and frontier GPU compute empty. MainPID0 alone was not used as settlement proof. Raw source/state/journal/logs were preserved under protected `/data/build/H016-20260927/worker1-deploy17/recovery18` before any state write.

Current canonical lease ownership was proven as llm-node.service PID3309508/FD31/inode1838. This identifies only the holder at observation time, not the18:04:45 failure holder. The existing API acquired the lease after a bounded wait; ordinary settle_state then succeeded18:12:57. No lock replacement, bypass, service restart or model signal was required.

The remaining sticky request_hold was reconciled18:14:46 under direct root authority. Evidence: exact physical release; proxy_started=false; no proxy-state receipt; last guard has no proxy or request disposition; retained native logs end while loading and contain no admission/completion evidence; installed source assigns request_hold=true on any settlement exception. The original HELD state was archived with SHA256 `2edcf2a65c50099dca43eb48e5179ceba2cb5f8577fe69432517812ea1183f8c`. An explicit reconciliation receipt records this narrow true→false transition; no unknown request state was silently discarded.

The existing rollback_glm function wrote real selection generation4 for glm-5.3-flash and then started the unchanged original ordinary unit. Original config SHA256 `4a5ea3904fba96480884b91414524617683b50e6f79fef96261e2b92183e6b71` and owner SHA256 `d4a628876b8643a01277039ab744e87a2218e3b87e2c6207e2d67816b570a4b1` passed. The retained GLM container started18:14:48.189468618, PID3836017, image51791e17. The other three containers retain their exact IDs, images, PIDs and StartedAt. No inference request was sent by recovery; ordinary runtime startup behavior is unchanged.

Actual authenticated readiness and canonical node status are separate from successful start. The first read18:16:25 found GLM still loading, with no HTTP listener yet, no owned swap/OOM, and node available. See final RESULT.json/HANDOFF.md for the latest read. No model cycle is authorized by a pending read.

Mechanical single bounded follow-up, if needed, outside the paid waiting period:

```
python3 /Users/agent/CodexProjects/llm-orchestration/tasks/H016-RECOVERY-18-20260927/READ-GLM-READY.py
```

The command preserves timestamped private raw JSON, writes ROOT-GLM-READY.json, and only sends authenticated read-only GETs. It performs no inference, lifecycle mutation, retries or polling loop. Root/Worker2 owns original Sova application restoration after actual GLM ready; Sova is not changed here. Native cap18:23/global18:33:08 remain unchanged.

All executed recovery script bodies and bulky raw receipts remain outside Git in the task's private directory. RESULT.json pins their hashes. The failure diagnosis is an offline proposal only; original primary loop cause remains UNKNOWN because finally settlement replaced its diagnostic. Docs-only packaging requires no new production or performance test.
