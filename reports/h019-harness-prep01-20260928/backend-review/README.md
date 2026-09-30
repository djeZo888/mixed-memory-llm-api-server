# Independent early backend review

Exact nested-lease owner source **PASS**. Direct950K adapter **changes required**.
Final deployment/import closure and the later periodic guard-writer delta are
pending. No host contact, deployment, inference, or implementation edit occurred.

Reviewed `candidate.patch` SHA-256
`cd3c89ef848793ab1aa55a739bc8ac04f14dee99e071145b99fe5f7c739d55a0`, applied
to an isolated archive of base `89cc931b69e39a4a2acd95270d3156396d0053d0`.
The resulting owner is
`57ace7da1f84e09cb7ed5f0a72ac18315a9875d4c8c00f87f768288bf1b2c5f8`;
test source is
`8962fe279707f1dd79c3633e7dadd1093cabd8910b9f998baf21fcd6b75abc39`.

The candidate borrows and validates the canonical parent capability, does not
reacquire or release it, and reuses the startup's same-boot hardware sample under
the existing five-second guard budget. No TTL, positive-fault clearing,
inference lock scope, replay, or settlement behavior was widened. The unchanged
cf558 periodic hardware-policy baseline remains covered by its historical
independent review; its 59 checks were not repeated.

Validation: all **11** supplied `LatchRefreshTests` pass; the earlier candidate
prose claimed 12, subsequently corrected by the coordinator. Three additional
focused checks pass: real supervisor startup reaches the model-create boundary
with one parent lease acquisition and one GPU sample; an asserted positive
fault remains retained without writes; a swallowed alarm still refuses the
borrowed refresh and leaves the parent's lease active. These are offline
fixtures, with all host boundaries mocked. `independent-tests.py` imports the
isolated candidate through `PYTHONPATH=<isolate>/scripts:<isolate>`.

The historical positive-latch test uses boot age100, below the120-second boot
grace, so its refusal alone does not prove a positive fixture. The added test
explicitly asserts a positive latch at age150. Initial review-fixture failures
(stale validation suppressing historical evidence, then boot grace) are retained
in the two `*-fixture-error.txt` logs. They are fixture corrections, not owner
failures. The startup fixture's synthetic `OWNER_FAILURE` is its deliberate
stop at `fixture-create`, before any model operation.

The early final adapter
`73cee9dffc47909e7b4e166f09cfb253dd2a267faf8af64bbcac6f9019555794`
still requires exact acceptance keys `final_native17`, `production`, `sova`;
the reused preflight requires PASS/PASSED for every key. Current native17 plus
production authority is reproduced as rejected with `actual_acceptance_required`.
This conflicts with the new ROOT-STEERING app-only exception. W1 must narrowly
correct this adapter and the matching service description before dispatch.
Do not fabricate Sova acceptance. Its direct plan is correctly one948975-input,
1024-output request in950000 capacity; no64K rung.

Candidate manifest
`d3525c3c4091848d8d4e058747446c7f148a020ff5a659beef6b778166a4eed6`
pins the exact reviewed owner, cf558 in control/node, and canonical lease483ba
in both. This is candidate-pin evidence only; actual import inventory and
affected release/config/deployment receipts remain outstanding.

Root separately identified existing recursive scans in periodic owner
`guard.json` writes and short-client `GUARD-PROGRESS` writes. The requested
measured, narrow periodic-writer delta has not been supplied and is not covered
by this approval. Closing now as directed by `CLOSE-FIRST-SESSION.md`; no paid
waiting for W1 packaging. Machine-readable disposition is `REVIEW.json` and the
matching task-level `../BACKEND-REVIEW.json`.
