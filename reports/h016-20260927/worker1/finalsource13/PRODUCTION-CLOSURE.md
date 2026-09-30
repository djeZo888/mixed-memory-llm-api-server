# H016 FINAL-SOURCE-13 ordinary production closure

Source review and focused patches at 2026-09-27T16:36:02Z. SOURCE ONLY: no SSH, deployment,
inference, selection change, qualification claim or container adoption.

## Exact reviewed source and focused checks

| Source | SHA256 |
| --- | --- |
| `scripts/runtime/mimo/private_proxy.py` | `ad7fea4cbf9fd2b6583c87530325136c858d94c1e28318b71bed682965972a56` |
| `scripts/runtime/mimo/owner.py` | `c7b4b109138de2ab566d7403f79b24f0203ac3f2bc6080e07d7604f30803221a` |
| `scripts/runtime/mimo/launch.json` | `c20b46fa1786dad3a358a0c3c29ecbba4a3d76afb3d4ea36f3ff823da6538241` |
| `scripts/control/node.py` | `d67384fed158b8977d5e968f46bada976df5053fc31264995001765e926ed571` |
| `scripts/control/node_observation.py` | `da330ab85bd2beb44ab71e5996743b4519ff2958c3ac7ad8ebb0f309e4b04ee2` |
| `scripts/control/node_collectors.py` | `347b4667146bd2fa6fe0e95035f59817c860528ee50575fa2d278c439ac207dd` |
| `scripts/control/passive.py` | `f535b9a0e8c8869566a40209d78704de428e14518d1b6eebf0540589e26817a3` |
| `tests/test_mimo_owner.py` | `f8a957f3f5589d76283702adb0d7f843b22e922418387292412386d9cfc4f8c3` |

Executed locally on this source:

- `python3 -m unittest discover -s tests -p test_mimo_proxy_deadline.py -v`: **4 PASS**. Fixed eight-hour stream deadline, full HTTP drain, ambiguous deadline hold without replay, required current protected proxy hash.
- `python3 -m unittest discover -s tests -p test_mimo_owner.py -v`: **16 PASS** (original13 plus2 focused capacity cases and1 memory-component case). Exact owner/selection/source/guard/settlement behavior, actual allocator rounding, refusal of stale/mixed requests, incremental zero startup allowance, and negative/over-budget refusal with mocked dependencies.
- `git diff --check`: PASS.

These checks do not establish native loading, production Linux lifecycle,
application behavior, actual throughput or current host readiness.

## Configuration decisions still awaiting actual evidence

`launch.json` now contains root-selected requested1000000 and8spread, decode mask0x10101010101010001, with GGMLnuma omitted. Root selected the tested whole profile at9.209882712outputtokens/s; the aggregate affinity classifier remains INCONCLUSIVE, with bounded later steady samples preserved separately. Preserve batch threads64,
native F16 K/V, model/image/native precision, explicit load `none`, `--no-host`,
GOMP_SPINCOUNT=0, outer interleave0-7 and all current registered guards.

Requested final usable context is1000000; accepted actual usable capacity is
1000000 or1000192 with actual props/slots and reviewed allocator semantics.
Physical pool is a separate quantity. The minimal ordinary owner patch
preserves both launch-source request values at1000000 when actual
`manifest.context` is1000000 or1000192; it rejects stale or mixed request
values. The entire resulting argv must still exactly equal the reviewed
`manifest.native_argv`. Owner and node continue to require actual props and
slots equal the manifest's actual capacity. Other capacities retain the
existing manifest-to-argv substitution behavior. No schema was added.
The launch source records the actual root-selected profile; the qualified manifest still awaits actual final native/ordinary production proof. Do not fabricate
equality or reload a proved allocation merely to remove rounding. 917504
requires actual workspace/reserve invalidity and root review; this report does
not select it.

`reports/h016-production-owner-20260927/REVIEW-MANIFEST.template.json` remains
`qualified:false` with incomplete memory/argv/artifact/qualification fields.
Its old source hashes are placeholders and differ from the table above.
Preserve that false status until actual final native qualification exists;
refresh the complete installed source closure and qualification pins from the
exact final bytes. Measured cgroup peak includes charged file cache. startup_cache_bytes is only separately justified incremental startup allowance and may be zero; peak+incremental must fit704GiB and actual15%host reserve. Required closure already includes owner, private proxy,
launch and node/control sources. Do not deploy the historical template as-is.

Qualified cgroup peak already includes charged reclaimable file cache. Do not
add the same cache again as `startup_cache_bytes`. The minimal memory patch
requires positive integer limit/peak, nonnegative integer incremental startup
allowance (including an evidenced zero), and peak+incremental<=limit. Keep the
704GiB limit if actual complete peak and separately justified incremental
allowance fit, with the independent15%host reserve guard. No schema changes or
arbitrary replacement memory values are introduced.

## Occupied16K qualification feasibility, source only

The existing provider contract can truthfully represent occupiedTested16384
and actual allocated1000000/1000192 without a completed64K-input test, subject
to root approving that scope and every other qualification check being real.
`ai-harness/server/src/mimo-frontier.ts:94-97` requires the genuine17-tool,
strict nested-schema and serial-completion qualifications; it requires
1<=occupiedTested<allocated, with configured>=actualSlotContext and
allocated==actualSlotContext. It has no hidden64K occupied-input Boolean.
`mimo.ts:211-232` retains all artifact/native/allocation/reserve/template,
text-array, tool/reasoning, single-owner and admission-bound checks. Its65536
at line229 is an accepted requested OUTPUT ceiling; line230 allows the actual
largest completed output to be shorter. Existing integration fixture lines
93-114 illustrates occupied4096 and completed output10 with ceiling65536.
`active-frontier.ts:31-35` still pins the complete qualification file digest,
exact selected actual context and production identity contract.

A deferred64K-input rung must stay explicitly NOT_TESTED until its actual
PASS. This review does not implement or authorize that background rung or the
near1M run. A root-approved64K-before-near1M gate would need to enforce that
order without replay and retain its own receipts. Allocation is not occupied
context correctness, and source validation does not authenticate evidence.

## Ordinary clean-launch sequence for root review

1. Finish the independent pair and final native qualification under their
   existing owners. Retain all completed rung and genuine17-tool receipts.
   Require actual settlement of the experimental owner before production.
   Preserve original GLM config/source/release/desired state, selection history,
   other three owners and application histories/files.
2. Finalize ordinary launch and schema2 manifest from reviewed actual winner,
   props/slots usable capacity, allocation/reserve, measured peak/startup cache,
   all13 verified shard identities, exact source and qualification pins. Source
   preflight requires unchanged image/runtime/template, original GLM pins and
   registered storage. Protected placement and source installation remain a
   separately authorized root-reviewed action.
3. Under existing selection semantics, confirm GLM/experimental owners and
   frontier GPU are physically settled, then publish selected MiMo generation
   with the exact manifest digest. Start only `llm-frontier-mimo.service` for a
   fresh container/proxy child. The owner has no warm-adoption path.
4. Require exact supervisor invocation, container ID/PID/start ticks/image,
   proxy child identity/disposition, authenticated props/plain slots, fresh
   guard/latch, >=7% GPU free, >=15% host available, zero owned swap/OOM and
   temperature below min(85C, hardware cutoff). Readiness of both Qwens and the
   image owner needs independent current evidence; this source does not infer
   it from the MiMo guard.
5. Complete actual production and W2 Sova application checks on the exact
   production identities before calling production accepted. Final native17,
   production and Sova PASS are all prerequisites for the held near1M job.
   Missing work remains NOT_TESTED. Sova's shared frontier lane must be paused
   again and exclusive before any separately root-authorized long job.
6. On failure use the ordinary owner's exact settlement and hold semantics.
   Ambiguous requests remain held; there is no automatic retry or GLM start.
   Explicit GLM rollback requires proved native PID/cgroup/GPU release and
   unchanged GLM bytes, writes GLM selection, then starts its original owner.
   Do not clear hardware latches or issue an unowned restart.

## Deadline and lifecycle review findings

The ordinary owner does not hold the canonical lifecycle lease while waiting
on GLM `systemctl start`: `rollback_glm` releases it first. Production
supervision releases the lease after Docker create/start; guard/readiness and
inference do not retain it. Exact native stop acquires its own canonical
transaction. No equivalent of the corrected affinity nested-lock defect was
found in this reviewed ordinary path.

Ordinary loading currently has a finite **1800s** internal timeout, rather than
a promised12min bound. The current window ends17:48:08Z. Any production launch
within it needs a reviewed finite controller/client admission and ordinary
settlement allowance consistent with the remaining time; estimated12min load
plus8min application checks is not a deadline guarantee. Do not consume the
hard recovery reserve or save time by adopting the experimental container.

The production proxy's request deadline is eight hours. It marks request
ambiguity before count/generation, requires terminal stream and full HTTP
drain for clean disposition, and does not auto-replay. The long client's own
durable eight-hour active cap and exact owner/pins/exclusive-lane validation
remain required; this report is not a launch instruction.
