# H023 RECOVER02 — independent LOADING confirmed

At 2026-09-28T15:40:52.586695+00:00, normal `llm-frontier-mimo.service` owns a real successor in LOADING. No readiness, warmup, inference or thermal acceptance is claimed. The worker exits without waiting through model load; running services are retained.

Exact current identity:
- Boot `17ac5d50-a6a4-4df1-8f9e-7bfc3db5f125`; selection MiMo generation12.
- Manifest canonical `2141e174172acced9fc8e2d0fc9a90b0fb053f8862dba6160fa55e5cc44226db`; raw `3f724d9b1d405916e4727d58d90b078ad53decbe056c3bbafe13bf5236c79615`.
- Launch `3b42b8b128f945a188be6b1b439eacf9`; unit invocation `b9712462f5064a089cd06cdcee037284`; supervisor PID661048.
- Native container `02b4b51c95a5b3f80794214746c9914f300c242e48ac44a4d6e05984993c849b`; PID661585; start ticks `244391`; started `2026-09-28T15:40:44.091098717Z`. Exact native/container/cgroup bindings passed.
- Owner `27caaee3a1fc3d0010527ac5e3626ef294278e2ebd15b79e3c33e9ba6842bc5f` from reviewed commit `9ab4f3c088b2042e9c38b4f0460cf26b405ec961`. Root revised exact GO15:39:49 is retained in ROOT-JOB-FIX-GO.json.

One initial preflight refused before writes: live systemctl reports no queued job as `Job=`, while the reviewed source expected `Job=0`. All original six files rechecked unchanged and no backup/archive/receipt/consumption paths existed. Root authorized a narrow correction accepting only explicit empty/zero values. Missing, whitespace, malformed and nonzero values remain refused. Two focused tests passed across19 subcases; prior65 PASS evidence was retained, not broadly rerun. The original refusal, exact source delta, reviewed helper delta, commit bundle and test log are retained.

After revised GO: one successful guarded stage, one reconcile and one `systemctl start --no-block` outside the parent lease. Registered-storage atomic writes and canonical lease26:1829 protected staging. Only installed owner.py and its source_sha256 manifest entry changed. Full manifest semantic equality except that owner pin, prewrite CAS and source-closure readback passed. Context950000, output65536, memory704GiB, container swap allowance0, GPU, model/runtime/image/weights, qualification and generation12 remain unchanged.

Protected original inputs use exact actual-boot names `new-boot-prior-manifest-17ac5d50-a6a4-4df1-8f9e-7bfc3db5f125.json` and `new-boot-prior-owner-17ac5d50-a6a4-4df1-8f9e-7bfc3db5f125.py`. Archive/recovery/consumption use that same boot. Backups were exclusive0400 writes with byte/hash readback. History backup contains original service bytes, failed H019 client bytes and the12-file H019 authority/client/request/SSE/progress hash index; the original H019 namespace remains in place. Raw history and credentials remain private on ai-vm.

Reconcile archive `5536650d58dfa06b4f1da91a6f0e006c244cddbbd76b6ac98463070817d4a4cc`, recovery raw `ebe50383b9e42cacb31e2bb24e776c3cf0ebe7e3ccc5cd3d453ac14ec492c805`, consumption raw `c6f5065df2aef2c57c33924dbcece2a41b9f6438a4d086cc7f290e76681bd2a2`. Recovery/consumption/successor binding verified. Original historical HELD/request_hold, lifecycle_busy primary failure and command_timeout settlement failure were preserved unchanged in the archive. They are not a pass or settled request. Normal startup created separate successor ownership and renamed the stopped predecessor to `llm-frontier-mimo-production-prior-b23d112359424d909862207e30f0c9d7`; its original container ID/logs remain. No manual hold or quarantine clearing occurred.

W2 fresh identity is W2-RECOVERY-IDENTITY.json. Proxy had not started at the LOADING snapshot. Before any driver dispatch, obtain genuine ready+idle and fresh current proxy/guard bindings under root admission coordination. Use owned proxy10.156.100.60:30012; directnative127.0.0.1:30012 forbidden,30010 oldGLM. Proposed next workload is native-counted MiMo~16384 input/output<=128, Qwen4–16K fresh prefixes and image1920x1080 with unchanged configured capacities. App frontier hold, historical quarantines and ai-harness lifecycle remain untouched. No healthy Qwen/image stop, hardware/fan/TDP action or inference took place here.

General later unchanged-source reboot recovery and transient periodic lease contention remain unimplemented. Neither was expanded. Latest sequence remains hardware/fourway first, separate two-hour Codex work afterward, large MiMo later.

Session `01a0e8a5-ede3-7b22-af49-cf5563b86e83` on mac-worker1, SSH alias ai-vm. Hard deadline16:03:02.943079Z; initial start15:33:02.943079Z; final observation15:40:52.586695Z. Exact executable helpers and command/deadline records are included. No subagents, nested native CLI or GitHub push. Two same-start snapshots: first caught CREATING during startup, second confirmed LOADING; no second start or reconcile.
