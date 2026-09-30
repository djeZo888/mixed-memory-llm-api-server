# H008 Flash phase3 handoff — 2026-09-26

Partial qualification: Flash is warm and native-ready with an allocated 480000-token FP8 pool. Forced weather-tool semantics FAILED. Discarded 4K warm ended incomplete at the 300-second request cap; measured 4K/16K remain NOT_TESTED. No further worker1 inference is planned.

Worker1 released its benchmark lane to root at 18:59:29 UTC. All qualification units are inactive; final owned connection was closed and readback found no established TCP30010 connections. Native active-request counters are unavailable, so this is not an atomic-drain claim. Root owns worker2 lane release and acceptance. See LANE-RELEASE.json and ROOT-NOTICE-LANE-RELEASE.md. Default-auto tool acceptance is deferred to root-coordinated worker2.

## Exact deployed state

- Deployed source: f91453c6a98a788f624110c0823eaad90e540f55. R3 route replacement 5ab9f465ff7921219c1bf54a8872e4e78bb828b0; R4 missing KT weight path 45aca6c732e5eeafbe6ba5d9cdd3fc8b5248f856; R5 registered TVM cache path f91453c6a98a788f624110c0823eaad90e540f55. Exact ROOT-GO-FLASH-R3/R4/R5 files and corresponding review/patch/script/bundle files are preserved in this task directory.
- Manifest SHA256: fe79c4bbd6cd8da27b45676379089069b1672f6c92e8c147b5a7505231bc427f; config b704ed5985d5437930fc06187fb301e98a5f39478362f4dc43c426b27c8680e3; launcher 0361f8689fe4c24c28f072a1d6d31fd3a483136d59dc5311fa0346a3c2d9d18a.
- Same retained llm-frontier-flash container 3c9501c8937ee2319eedd26b0b12dfb4dd11ec1d05b09543abc6f1187957e1a2; current boot started 18:38:38.431861217Z. Immutable image sha256:51791e17c0149019e2ddc032d8c1b2f60b86c3a6c293daff639e20053baa858a; original model revision eb9eb208eb0d988989d07a6a12d0fdeb5f52574a unchanged.
- Source/state /data/services/flash-h008-20260926; logs /data/logs/flash-h008-20260926. Immutable releases /data/services/releases/h008-flash-route-r3-20260926, h008-flash-kt-r4-20260926 and h008-flash-cache-r5-20260926; matching /data/backups/ directories retain exact replaced bytes/configs. Rollback requires root coordination and normal canonical lease/storage guards; do not blindly replay failed starts.
- llm-frontier-flash owner remains active with running intent; Docker stays warm. Qualification jobs and their task-local samplers have ended. No persistent whole-container idle-monitor acceptance is claimed. Both Qwens native200, unchanged container IDs, image fresh available, control/node active at 18:58:32 readback. No Qwen reload/inference, no new image request, no other host contacted.

## Live evidence and limits

FLASH_NATIVE_ALLOCATION: configured context480000, actual pool480000, max_req_len479999, max_req_input_len479994, resolved torch.float8_e4m3fn, SM120 execution PASS. Source adapter bounds input<=479993 and total<=479998; no live near-boundary occupied-context proof. Largest completed native usage is213 tokens (tools_history212 input plus1 output); stale job scalar173 excluded from final claim. The 4K request passed exact native-tokenizer fixture construction but incomplete-stream code did not persist partial native output usage; its throughput/output count are unavailable.

Live auth correct200/wrong401/absent401; tokenizer-to-inference usage36/42/212 full pins; text arrays without separator and developer→system on both routes; invalid media and unknown block400 on both routes PASS. Coherent answer 7+5=12 completed29 input/10 output, TTFT7.176s, effective input4.041 tok/s, short decode0.737 tok/s. This short sample is not sustained-speed proof.

Forced tool request completed170 input/3 output in12.417s, but emitted null function name and empty arguments; semanticFAIL. Original assembly TypeError is retained separately. The raw single-delta34013 tok/s figure is invalid throughput and is nulled in the authoritative forced-tool summary. Original immediate-post-SSE HTTP429 body was NOT_CAPTURED; following request admitted without reload, so a persistent admission latch was not demonstrated.

R5 load/request-attempt samples: peak32174MiB target GPU, min free65076MiB, peak47C; cgroup peak428669755392 bytes; minimum host MemAvailable601575821312 bytes; swap0 in recorded snapshots. JSON includes after-load and sampled-peak anon/file/cache/RSS distinctions; after-warm unavailable. CPU temperature unavailable. Configured64 expert threads/two pools and observed64 named threads including masters; masks0-15 and16-23 preserved by root instruction, no affinity optimization. Prior R3 all-GPU OOM violated reserve and is NOT covered by later successful-load margins.

Measured4K/16K, sustained2048 output, default-auto tool, 600-second quiet/blocking/wake, full480K occupied context: NOT_TESTED. No optimal-speed or full qualification claim.

## Independent jobs and receipts

All ended, no restart needed:

| Unit suffix | Invocation ID | Script SHA256 | Result |
|---|---|---|---|
| r5 | 14dc16497c694e28ac05d4216947944f | 24663e160e1e6d6b249aee8d27f9c39e4e1f9ae9c52c37d752b5ea6e92d62558 | Live fixtures/coherent PASS; immediate tool429 |
| r5-cont1 | cdf9cb89236746d695984627e6aea671 | 4ffc8c3afb39afea6c3e89185b65aa587656ec22f89bf3319815976390c0f49e | Forced-tool semantics FAIL; assembly TypeError |
| r5-cont2 | ffedd63d0aad407188d9f798b7b53246 | 09056fd01765cc500b7eecbea4aa845e5f8b69908879d386d5ab32317148d85d | Warm4K incomplete at300s; ended18:56:44Z |

Unit names have prefix h008-flash-qualification- and suffix .service. CONT1 timing mismatch360/450 vs root300/330 was reported and not repeated; CONT2 used exact300/330 with output budgets32warm/64measured. No completed requests repeated. R3 invocation8f96057065d24828ad35b6bd498d6b42, R4 854483e62dfa4fb9879f8910835d7221 also inactive.

VM durable QUALIFICATION-R3/R4/R5/R5-CONT1/R5-CONT2.json, their OWNER receipts, telemetry JSONL and publication records remain under registered log root. Local evidence/FINAL-DURABLE-RECEIPTS.json contains receipts, telemetry hashes, final unit states and TCP observation. evidence/LIVE-READBACK-R5.json is the actual fresh node DTO and passive native status, source/config hashes and expert affinity. NATIVE-READY-RECEIPT.json, FORCED-TOOL-RESULT.json, FLASH-RESULT.json/md and startup failure receipts preserve boundaries. Historical phase2 publication-size-limit and R2 unsupported-flag/route failures remain in phase2; R3 CUDA OOM and R4 cache EROFS remain separate here.

## Next ownership

Root may coordinate worker2 native acceptance against this warm baseline. Forced-tool behavior and incomplete 4K warm are concrete unresolved runtime failures; any source/runtime correction needs fresh bounded review/GO. No automatic benchmark retry, model reload, CPU tuning, or idle wait. Keep accepted models and rollback files. No Git push was made. Report-only final commit/bundle IDs are in SOURCE-FINAL.json; deployed source remains f91453c6a98a788f624110c0823eaad90e540f55.
