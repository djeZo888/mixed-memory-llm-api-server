# IMAGE21-QUALIFY-20260923 — completed bounded qualification

Highest passing generation: **1920x1088**. Editing remains **unsupported after failed fidelity**.

Stop reason: `ROOT_DIRECTED_STOP_AFTER_SINGLE_REFINEMENT`. Unmeasured rungs: 2112x1184, 2528x1408, 3040x1696, 3648x2048, 3840x2160.

| Case | Delivered | Native | Status | Request s | Native s | Device peak MiB | Min free MiB | Min free % |
|---|---|---|---|---:|---:|---:|---:|---:|
| api-baseline-1024x1024 | 1024x1024 | 1024x1024 | PASS | 24.183 | 23.830 | 39050.312 | 10089.688 | 20.533 |
| r01-1024x576 | 1024x576 | 1024x576 | PASS | 13.587 | 13.473 | 36104.312 | 13035.688 | 26.528 |
| r02-1216x704 | 1216x704 | 1216x704 | PASS | 19.407 | 19.255 | 38086.312 | 11053.688 | 22.494 |
| r03-1472x832 | 1472x832 | 1472x832 | PASS | 28.603 | 28.410 | 40034.312 | 9105.688 | 18.530 |
| r04-1760x992 | 1760x992 | 1760x992 | PASS | 45.214 | 44.943 | 42810.312 | 6329.688 | 12.881 |
| r05-2112x1184 | 2112x1184 | 2112x1184 | NOT_TESTED | N/A | N/A | N/A | N/A | N/A |
| r06-2528x1408 | 2528x1408 | 2528x1408 | NOT_TESTED | N/A | N/A | N/A | N/A | N/A |
| r07-3040x1696 | 3040x1696 | 3040x1696 | NOT_TESTED | N/A | N/A | N/A | N/A | N/A |
| r08-3648x2048 | 3648x2048 | 3648x2048 | NOT_TESTED | N/A | N/A | N/A | N/A | N/A |
| r09-3840x2160 | 3840x2160 | 3840x2176 | NOT_TESTED | N/A | N/A | N/A | N/A | N/A |
| refinement-1920x1088 | 1920x1088 | 1920x1088 | PASS | 53.336 | 53.016 | 44776.312 | 4363.688 | 8.880 |

Dimensions on NOT_TESTED rows are frozen targets, not decoded outputs. MiB = 2²⁰ bytes; GiB = 2³⁰ bytes.

Next-rung forecast for 2112x1184 (native 2112x1184): **47.543 GiB** device use versus **45.589 GiB** allowed; `STOP_UNSAFE_FORECAST`. This is a forecast, not measured support.

Installed and root-accepted sizes: 1024x1024, 1024x576, 1216x704, 1472x832, 1760x992, 1920x1088.

Source `f188e6de8d151a7e571c7e3b5ecb59ef63d32bb7`; runtime `0cd8be351d0825488f4b81c8931167bbab618eca`; image `sha256:dafbccb763cff6a6aa3777c7c0a8cc185d838bd4b9f61bec8007f57f2c7233f8`; checkpoint `790c92633540aa0cb11d9abf19eb46d861714758`.

The Worker2 square API baseline is separate from the native ladder. Required deployment recoveries are recorded separately and excluded from benchmark case counts. Device samples are physical-device totals; native allocated and reserved peaks are separate, with lifetime limits retained. Final restored readiness is established by retained recovery output and Worker2 final GETs; future boot checks are not implied.

Worker2 used its reviewed studio-teapot prompt and seed 20260923; the ladder and deployment warm use seed 42. Baseline native time 23.83 s and reserved peak 37406 MiB come from a rounded backend log; allocated peak is unavailable. This is not a same-recipe benchmark comparison.

API: `http://10.156.100.60:30006`; authenticated `POST /v1/images/generations` and `GET /v1/image-capabilities`. Clients read the existing protected key through the approved loader, keeping its value out of argv/environment/logs. Exact client and acceptance evidence: [worker2-client/client.py](worker2-client/client.py), [worker2-client/README.md](worker2-client/README.md); API contract: [image API](../../docs/image-api.md). Valid edits are refused as unqualified; no edit or transparency profile is enabled.

Exact criteria, hashes, host/cgroup/swap evidence, forecasts, root review, native/delivered dimensions and remaining work: [resolution-results.json](resolution-results.json). Rejected editing findings: [reference/README.md](reference/README.md).

The separate 1920×1088 case is the single root-authorized refinement beyond the frozen ladder. It does not replace planned r05 (2112×1184); all tests stop after this bounded refinement, regardless of outcome.

Final state: the normal API recovery/warm completed at approximately 04:26 UTC and released the canonical lease. Worker2 then completed exactly four authenticated GETs at 04:31:40 UTC: all HTTP 200, ready=true, admitting=true, busy=false, with these six profiles and no edits. See [final receipt](FINAL-DEPLOYMENT-RECEIPT.json), [final projection](FINAL-WORKER2-PROJECTION.json) and [independent final results](worker2-final/FINAL-GET-RESULT.json). The post-recovery container ID was not reobserved; the original [deployment receipt](DEPLOYMENT-RECEIPT.json) remains byte-exact historical evidence.

Worker2 accepted exactly one generation and zero edits: its RGB PNG SHA256 is `876ad24718d40d31090a214ef7028a26b2e966cc14fe0f3894c20e91fe56467b`. Authentication, invalid-request and busy-429 behavior passed; both tiny text replies completed during that generation. A valid edit returned HTTP 400 `unqualified_profile`. This baseline is counted once.

All three models remain warm/resident according to the retained final state; both original Blackwell Qwen containers and 480000-context profiles are preserved. The dedicated Ada policy retains 5% observed device-free and 15% host margin, with no offload, swap or quantization. This closeout performed no VM contact, mutations, inference or repeated tests. The API implementation remains `f188e6d`; this documentation/evidence commit needs no redeployment. Root owns review, import and publication.

[Measurement receipts](measurement-receipts/) and [qualified cases](qualified-cases/) are immutable copies. [artifact-manifest.json](artifact-manifest.json) retains task-relative SHA/path references for large PNGs, raw telemetry and authority notes, which are outside this repository package. [PACKAGE-FILES.sha256](PACKAGE-FILES.sha256) identifies the final compact package. Source material under measurement-source/ and reference/source/ is retained provenance, not a newly executed campaign.
