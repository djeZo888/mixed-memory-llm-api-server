# H024 Worker2 first bounded source wave

Native session `01a0e8f2-162f-73e0-a6ca-6ab9ca62a9ec`, started
2026-09-28T16:56:14Z, hard deadline17:41:14Z. Base
`4b631d0b44ef1c471d39129b273f1753b373298b`. Offline source/native mocks only.

## Candidate

- Bounded Responses diagnostics distinguish observed provider finish from actual
  canonical terminal, retain safe text/argument/reasoning fingerprints and tool
  identities, and isolate observer failures. W1 owns the gateway capture wiring.
- Per-provider Responses translation preserves verified MiMo plaintext reasoning
  as pinned `reasoning_text`, exact tool IDs/results/custom input, separate
  capacities, and explicit requested/effective serial policy. Qwen unchanged.
  Actual pinned native MiMo mock continuation through the exact adapter passes.
- Trusted runtime passes explicit qualified child models; default is Qwen only.
- Owned typed Codex compaction uses the existing serialized broker/settlement
  path and original native thread. Durable action IDs survive completion/restart;
  browser unresolved IDs survive refresh, lost acknowledgements and subsequent
  rejected retries. Original messages/files remain intact.
- Unknown completed response labels are neutral `Assistant response`; stored
  content/phases/native IDs are preserved.

## Outcomes and limits

| Boundary | Result |
|---|---|
| Final affected server/native fixture pass | PASS72/72, no failures/skips |
| Server build; final web build | PASS |
| Additional affected app lifecycle checks | PASS33 |
| Web phase/compaction/queue checks | PASS76, then final changed compaction11 |
| Native image malformed args/schema/continuation | PASS offline preservation; no argument repair |
| Pinned native MiMo reasoning/tool continuation | PASS local mock; live NOT_TESTED |
| Pinned manual compact/fresh resume/history preservation | PASS local mock; model recall NOT_TESTED |
| Original image and PDF complete workflows | FAIL retained; historical raw provider origin/reason missing |
| VM/model inference/deployment in this wave | NOT_TESTED; none performed |

No deterministic image-argument insertion or PDF-content-loss defect was proven.
Native/app PDF text matches exactly; raw historical upstream finish_reason and
next Chat body are missing. No key stripping, synthetic replacement argument,
schema weakening, hidden retry or acceptance prompt rescue was added. Operational
image and native-vision gates remain false. MiMo950K remains configured capacity.

## Integration and deliverables

Commit order after the base:

1. `c74eed22a90eb4f91ff209f8da6de89fdc444068` diagnostics/PDF trace. Root already
   cherry-picked this as `b0b2620`; do not apply it twice.
2. `f7ceeb9769e7eba866f685c9150133b03f796bd2` provider reasoning contract and
   runtime child policy. Requires matching W1 provider/children files.
3. `bd2458a26c917bea52db71c21bf14c5e42b0f2e2` explicit root-reviewed serial
   adaptation and exact pinned native fixtures. This supersedes the initial
   parallel-flag blocker; integrate with item2 before deployment.
4. `85d74fc3be9923074acd326239f823295eb50a4a` owned compaction/UI including the
   final lost-ack/rejected-retry safeguard.

The final report-only commit follows those source commits. `VALIDATION.json`
contains every changed owned source hash, exact W1 compile-support hashes,
private evidence digests and web manifest. W1 files `codex-provider.ts` and
`codex-children.ts` were copied unchanged solely for local checks; they are
excluded from W2 commits/bundle. Root must integrate the matching W1 implementation.
No gateway/main/host/catalog/MCP image production files were edited by W2.

Task sibling `report/` contains final candidate bundle, diff and hashes,
matching `WEB-DIST.tar.gz` plus manifest, focused test log and handoff metadata.
Raw native/provider captures remain only in the task's private directory. No
image MCP layer or heavy native runtime rebuild is required by W2 changes.
The exact combined server/thin policy build and sole deployment remain for the
next fresh Worker2 session after root review/GO. App/status remain paused here.

See `NEXT-ACCEPTANCE.md` for one short owned compact/recall case and the required
conditional MiMo continuation. No unchanged live image/PDF retry is scheduled.
Wrapper writes the exit receipt after this CLI exits; no premature exit PASS is
claimed. Models/fans/holds/quarantines/default engine were not touched.
