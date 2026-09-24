# READY — source-only activation preparation

**Historical preparation checkpoint.** The separately authorized activation is
complete; see [LIVE-RESULT.md](LIVE-RESULT.md) and [WINDOW-RELEASE.json](WINDOW-RELEASE.json).
The preparation facts below describe commit `56bf2c7` before execution GO.

Native Worker1 session `01a0ce8e-681a-77b3-83b8-5a6faab3f62d` retained.
No ai-vm/ai-harness contact, deployment, restart, recovery, warmup or inference.
Capacity task still owns the window. Final capacity HANDOFF, measured/root-reviewed
manifest and separate root source/manifest/transaction GO have **not** arrived.
This checkpoint is reviewable preparation, not authorization or live readiness.

Base `6a56776f3c6699542fa119ca6ca46b7c94c3039f` includes combined source
`9de9ecf701bedd0bcb337d9dcb49a4aca1c3fa27`. All seven adapter files match
that source, reviewed `f6e69d290a3cbf58dafbcfa726f9474f083a7cfd`, the working
tree and locally retained capacity CANDIDATE metadata. Exact old/new SHA256s:
[SOURCE-PACKET.json](SOURCE-PACKET.json). Production adapter source was unchanged.
Only `app.py`, `protocol.py` and the final manifest need installed replacement.

21 focused offline tests passed: one omitted edit seed draw after validation,
accurate `data[0].seed`, explicit/default generation behavior, exact FHD geometry,
RGBA/tRNS/EXIF normalization and refusal boundaries. Reproduce from repo root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests/image_api \
  /Users/agent/CodexProjects/llm-orchestration/tasks/H003-EDIT-CAPACITY-20260923/.venv/bin/python \
  -m unittest -v test_edit_seed.EditSeed test_edit_geometry.EditGeometry test_corrections.FullHD
```

The helper also passed eight negative payload cases and two simulated install
failure/compensation cases. The tests substitute host/runtime operations; no
real protected filesystem, systemd or VM validation is claimed. Reproduce:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 \
  reports/h003-image-api-activate-20260923/deployment-tools/offline_check.py \
  --output ../artifacts/transaction-checks-repeat
```

[PROFILE-MATRIX.json](PROFILE-MATRIX.json) is an evidence snapshot, **not a manifest**:

| Operation | References | Public size | Retained result |
|---|---:|---|---|
| generation | 0 | 1024x1024, 1024x576, 1216x704, 1472x832, 1760x992, 1920x1080 | Six previously accepted exact records |
| edit C01 | 1 | 1024x1024 | Measured + root visual PASS; minimum Ada free 18.6365% |
| edit C02 | 1 | 1536x864 | Measured + root visual PASS; minimum Ada free 16.1457% |
| edit C03 | 1 | 1920x1080 | Settled reserve FAIL; minimum Ada free 4.3875%, below 5% |
| edit C04 | 2 | 1024x1024 | Not dispatched in retained ledger; final outcome pending |

The retained capacity HANDOFF and matrix predate its latest captured ledger;
neither is the final release. C03 cannot be enabled from this failed receipt.
No interpolated sizes, reference counts, forecasts or source geometry support
qualify a profile. Final approved records and exact manifest bytes remain pending.

Seed42 regression/fail42 remains preserved. Fresh seeds are an orchestration
workaround, with no intrinsic model repair or guaranteed ancestor-seed exclusion.
C02 is a guarded creative edit; incidental background detail is not pixel-exact.
Public maximum remains opaque 1920x1080, with native 1920x1088 bottom repeat8/crop8
only where the exact operation profile is actually approved.

Original SIGTERM receipt `6ff05a981433d782d3b918338a27f803c243707d892cbbd52119a6c124ae02b5`
remains **ASGI-cleanup-unproven**, code2/status15. Separate task-only no-inflight
evidence admitted capacity cases; this packet does not reclassify that receipt.

The [transaction and rollback](TRANSACTION.md) reuse installed guards, lease and
the existing startup owner. [Adapted helper](deployment-tools/install.py) is
prepared offline; no deployment path was executed. Full source/test/input snapshots
are private outside Git; [PROTECTED-EVIDENCE.json](PROTECTED-EVIDENCE.json) binds
their locations/hashes. No PNGs, raw telemetry, keys or chat data are committed.

Finish here without polling. After separately transported final GO and handoff,
Worker1 may activate once and explicitly return the sole deployment/inference
window for root-authorized Worker2 acceptance. No later action while Worker2 owns it.
