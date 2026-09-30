# IMAGE21-BW-20260923 — completed

Completed 2026-09-23T01:54:42.856232+00:00. Planning publication verified; all18 bandwidth cases have five retained native samples. No implementation/source delta.

Planning HEAD `9a0430c8e3eea56cc432821116cb448a58fbabc8` remains clean and unchanged. Normal push reported **Everything up-to-date**; independent remote SHA matched. Publication receipts were saved before VM work.

| GPU UUID prefix | Guest PCI bus | Idle / active copy-test link | 32 MiB H2D / D2H | 256 MiB H2D / D2H | 1024 MiB H2D / D2H |
|---|---|---|---|---|---|
| `88058d9d` | `01:00.0` | Gen1x16 / Gen5x16 | 56.92 / 56.46 | 57.01 / 56.49 | 57.01 / 56.51 |
| `69acfa26` | `02:00.0` | Gen1x16 / Gen5x16 | 56.92 / 56.46 | 57.01 / 56.50 | 57.01 / 56.51 |
| `5d895991` | `03:00.0` | Gen1x4 / Gen3x4 | 2.61 / 2.89 | 2.61 / 2.89 | 2.61 / 2.89 |

**Rates are median decimal GB/s**, from five verbose samples; ranges/full UUIDs/timestamps are in CSV/JSON. Blackwells each97887MiB; Ada49140MiB; driver595.84. Guest-reported maximum links: Blackwells Gen5x16; Ada Gen3x16, actual active widthx4. This is guest observation, not a physical-host topology diagnosis.

Official NVIDIA nvbandwidth v0.10.0, pin `82fc4e8c6afa0babb8687793678f615b3b8d793e`, built once unchanged in a new container from existing pinned CUDA13.0 image. No packages installed. Setup42s; measurement wall window **198.839s**, 01:46:30.700–01:49:49.539UTC. Binary SHA256 `6e72482d0ca7fa2c2aa74cc559ab10100e3dcca4f6bde4012123a794be2bf764`.

Each UUID/size had one excluded native warmup sample and five measured samples per direction. Native methodology retains four warmup copies before **each** sample and16 timed CE copies/sample, with pinned host memory and verification. CPU8–15/Mems0, no-swap12GiB container cap, native automatic affinity disabled throughout. Selection used full UUID; every tool PCI identity matched the fresh mapping. Telemetry interval200ms includes warmup/verification and is not CUDA-event synchronized.

**Timeout limitation:** the combined Ada1024 call hit its60s per-call cap after completing all five H2D samples. Only missing D2H was completed once with120s cap using the same exact container/tool/policy. No completed case or whole campaign rerun; unflushed partial D2H from the aborted call is excluded.

Current installed registered-storage/root guards passed before and after VM writes and at final shutdown. Existing warning: root has less than6GiB free (~5.405GB). Writes stayed in registered `/data/build/IMAGE21-BW-20260923` and container storage; evidence streamed to this Mac. All28 protected critical receipt files match both deployed roots at reviewed source `04143b18cca7aca724d9a4a4bcf943fe86c040db`; targeted guard/lease/admission bytes also match that Git commit.

Both original Qwen containers remain exited; boot remains failed/exit1. Canonical desired running/resume policy and inventory-mismatch failure are unchanged, as are instance/state/receipt hashes. Control remains active. Temporary task container is retained **exited**, restart=no; GPU process list empty; canonical lease released and observed free. No SSH keeper.

Worker2 findings: `scripts/lifecycle/concurrent_profiles.py:160–168` requires exactly two ordered GPU rows; `415–425` repeats the two-row requirement and indexes VRAM positionally. Use required UUID validation and UUID-based memory lookup while preserving two text slots. Source receipt amendment requires root review. Detailed functions/guard paths: `evidence/source-review-local.md`.

NOT_TESTED: optional pageable transfers, D2D/P2P, tuning, models/inference/image ladder, Qwen recovery, implementation fixtures/deployment, physical-host link diagnosis. No Proxmox or ai-harness work.

Next bounded action: Worker2 compatibility source/targeted fixtures → root exact review and source-receipt amendment → fresh Worker1 activation GO. Preserve future Ada5% GPU margin, existing Blackwell policies and15% host margin. No image work ran.
