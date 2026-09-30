# H008 Flash phase3 result

PARTIAL_NATIVE_READY_FORCED_TOOL_SEMANTICS_FAILED. Discarded 4K warm also failed at its 300-second cap; measured 4K/16K remain NOT_TESTED.

Deployed source `f91453c6a98a788f624110c0823eaad90e540f55`; runtime manifest `fe79c4bbd6cd8da27b45676379089069b1672f6c92e8c147b5a7505231bc427f`. R5 retains the exact model/image and original container. No push, drivers/packages/reboot or unrelated model reload.

Live native allocation:480000 configured and allocated pool; max_req_len479999, max_req_input_len479994. Source adapter bounds input<=479993 and input+output<=479998; no live near-boundary occupied test. Actual cache `torch.float8_e4m3fn`, SM120 allocation execution PASS. Configured output ceiling65536, one running request. Largest completed occupied context: 213 tokens. No near-full occupied-context proof.

Auth/three pinned36,42,212 fixtures/developer-to-system/pure-text arrays/no-separator and invalid media/unknown blocks PASS live. Coherent arithmetic answer PASS. Forced weather tool FAIL: null function name and `{}` arguments. The single buffered tool delta has no valid decode-rate measurement. Auto-tool status: NOT_TESTED.

| Case | Status | Input | Output | TTFT s | Effective input tok/s | Decode tok/s | Finish |
|---|---|---:|---:|---:|---:|---:|---|
| discarded_warm_4k | FAIL | - | - | - | - | - | - |
| measured_4k | NOT_TESTED | - | - | - | - | - | - |
| measured_16k | NOT_TESTED | - | - | - | - | - | - |
| coherent_short | PASS | 29 | 10 | 7.176 | 4.041 | 0.737 | stop |

Requested measured output budget64 and warm32; no completed4K/16K speed sample. Warm stream ended at its300-second client watchdog without a terminal finish reason; partial usage was not persisted, so warm output count/rate are unavailable. Coherent-short rates derive from native usage, with TTFT including request overhead, and its10 output tokens do not establish sustained decode.

R5 load/request-attempt sampled GPU peak:32174MiB; minimum free:65076MiB; peak core:47C. Cgroup memory peak:428669755392 bytes; minimum host MemAvailable:601575821312 bytes. After-load and sampled-peak anon/file/cache/process-RSS distinctions are in JSON; after-warm is unavailable because warm did not complete. CPU temperature unavailable.

64 named expert threads including pool masters, two pools; actual CPU masks span0-15 and16-23. This baseline was preserved without tuning. All inherited Qwen/image containers and passive readiness are retained; no new Qwen inference.

600-second quiet/blocking/wake and optional2048 output NOT_TESTED. Lane state:{"auto_tool": "NOT_TESTED_deferred_to_root_coordinated_worker2", "container_retained_warm": true, "established_frontier_connections": "", "forced_tool": "FAIL_NULL_NAME_EMPTY_ARGUMENTS", "job_end_utc": "2026-09-26T18:56:44.135876+00:00", "last_invocation_id": "ffedd63d0aad407188d9f798b7b53246", "last_job": "h008-flash-qualification-r5-cont2.service", "measured_16k": "NOT_TESTED", "measured_4k": "NOT_TESTED", "native_readiness": {"readiness": {"admitting": null, "model_alias": "glm-5.3-flash", "ready": true, "schema_version": 1, "state": "up"}, "status": 200}, "native_request_active_at_finalize": false, "qualification_units": {"h008-flash-qualification-r5": "inactive", "h008-flash-qualification-r5-cont1": "inactive", "h008-flash-qualification-r5-cont2": "inactive"}, "released": true, "root_must_coordinate_worker2": true, "settlement_basis": "Owned qualification jobs inactive; qualifier closed active connection, current TCP30010 established connections empty. Native active-request counter unavailable; no atomic drain claim. No additional worker1 inference will be sent.", "status": "WORKER1_BENCHMARK_LANE_RELEASED_TO_ROOT", "utc": "2026-09-26T18:59:29.239460+00:00", "warm_4k": "FAIL_native_stream_incomplete_at_300s_request_cap"}.

Rollback releases/backups: `/data/services/releases/h008-flash-{route-r3,kt-r4,cache-r5}-20260926` and matching `/data/backups/` paths. Immutable R2 predecessor also retained. Failed revisions and original publication/continuation records remain separate.

See FLASH-RESULT.json, NATIVE-READY-RECEIPT.json, FORCED-TOOL-RESULT.json, evidence/FINAL-DURABLE-RECEIPTS.json, and HANDOFF.md for exact receipt/job IDs and limits.
