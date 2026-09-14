# F1A — exact Qwen acquisition and installed SGLang contract

**Metadata/capacity/helper/runtime-investigation gates PASS. Qwen acquisition RUNNING; full-model integrity PENDING. Live model inference, tool calling, authentication readiness and resource fit NOT_TESTED.** Stock SGLang API-key disclosure requires an F1S fix before F1D uses a real key.

Mac-Worker1, 2026-09-15 Europe/Ljubljana; VM evidence uses UTC September 14. Branch `milestone/f1a-qwen-fast-acquisition`, base `26653e949773894f435a0fb6482c687cef134499`. All VM actions used worker `ssh ai-vm`; no push.

## Exact source and storage — PASS

Approved official **`Qwen/Qwen3-Coder-Next-FP8@da6e2ed27304dd39abadd9c82ef50e8de67bdd4c`**. [Immutable manifest](f1a-qwen-manifest.json), SHA256 **`022674d4daf63fa57c2798a30fea80c6dde7b1b2e73630ae3c3aa94e45debb9e`**: **48 files / 80,407,722,953 bytes**, including **40 weight shards / 80,381,394,600 bytes** and **8 runtime assets / 26,328,353 bytes**.

The pinned [official metadata](https://huggingface.co/api/models/Qwen/Qwen3-Coder-Next-FP8/revision/da6e2ed27304dd39abadd9c82ef50e8de67bdd4c?blobs=true) matched exact repo/revision, all names, sizes and published LFS SHA256s. The index is also LFS; its computed hash `0ac9834aa1e30eb60d921d25e1755f97e92dfd47cf74ac2613e474243adcc4cf` matches, and its 148,383 tensor entries reference exactly all 40 selected shards. Index tensor bytes exclude safetensors headers and therefore differ from total file bytes. Seven non-LFS config/tokenizer/template assets have verified Git blob SHA1 plus recorded computed SHA256. [Metadata proof](f1a-metadata-proof.json) is explicitly a pre-weight-transfer snapshot.

Pinned config declares `Qwen3NextForCausalLM`, `qwen3_next`, FP8 dynamic activations and 128×128 block weights, bfloat16 residual dtype, maximum context 262144. Config and tokenizer have no `auto_map`; no `trust_remote_code` is enabled. Official pinned metadata/card declares Apache-2.0. The FP8 repository has no standalone LICENSE; its metadata links the official base model license. Pinned README is retained as provenance in task metadata only. The two repository Python parser files, `.gitattributes`, alternate revisions and other weights were excluded.

The concrete pre-transfer plan was published as task sibling `../acquisition-plan.md`, then copied before launch to `/data/build/f1a-qwen-20260915/evidence/acquisition-plan-before-transfer.md`. Normal exact metadata/capacity PASS was already authorized; no extra approval was requested.

At **23:16:34Z**, [capacity snapshot](f1a-capacity-plan.json) verified actual distinct ext4/rw mounts:

| Mount | Actual source | Exact UUID | Free bytes |
| --- | --- | --- | ---: |
| `/data` | `/dev/sdb1` | `8daf56f1-5649-4163-9d87-919c2d271875` | 1,394,115,362,816 |
| `/data/models-large` | `/dev/sdc1` | `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a` | 3,023,549,222,912 |

GLM remaining **321,359,976,608** + Qwen **80,407,722,953** + 20 GiB reserve **21,474,836,480** + two write buffers **33,554,432** = **423,276,090,473 bytes** required. Headroom after both acquisitions/reserve: **2,600,273,132,439 bytes**. Root had **5,197,049,856 bytes** free; accepted <6 GiB warning, exact <4 GiB stop retained. The helper recomputes both remaining acquisitions from actual finals/partials before writes; missing/wrong mounts or ambiguous paths stop without root fallback.

## Narrow implementation and verification — PASS

`scripts/f1a/prepare_manifest.py` downloads only metadata/small assets and checks their identities. `scripts/f1a/acquire.py` privately imports the unchanged reviewed D1b transfer primitives and adds the exact Qwen manifest, Git-blob-before-rename gate, own lock, native asset/index checks and combined GLM/Qwen reserve. It does not modify D1 source or its running process. Eight runtime assets finish before weight workers start. Two Qwen streams were selected beside four GLM streams based on D1b's measured 108,712,962 B/s over 150 seconds; aggregate network capacity and ETA are not guaranteed.

Exact HTTP status/Range/content-range/content-length, adjacent partial resume, atomic fsync/rename, SHA256 and Git identities, exclusive lock, cancellation/join, bounded retries and truthful downloaded/SHA/full verification counters gate acceptance. Existing finals are rehashed on resume; unexpected names, symlinks, nested devices, oversize/ambiguous files and corruption stop and preserve evidence. Concurrent companion-file renames are read conservatively without false corruption reports.

One common-guard change redirects its two diagnostic files to `${TMPDIR:-/tmp}`. F1A sets TMPDIR to verified task storage, including launcher preflight. This does not change the running GLM copy or historical deployment. Initial runtime checks using the unchanged common guard wrote its two existing tiny `/tmp` diagnostics; subsequent F1A guard outputs use `/data`. All F1A model/temp/cache/log/status/build outputs otherwise use verified data mounts.

Executed on ai-vm in isolated `/data/build/f1a-qwen-20260915/repo` with TMPDIR and F1A_TEST_TMPDIR set to the run's `tmp`, PYTHONDONTWRITEBYTECODE=1:

```bash
python3 scripts/f1a/test_prepare_manifest.py -v   # 8 PASS
python3 scripts/f1a/test_acquire.py -v            # 12 PASS
python3 scripts/d1/test_helpers.py -v             # 5 PASS
python3 scripts/d1/test_parallel.py -v            # 16 PASS
bash tests/shell/test-root-disk-guard-static.sh   # PASS
bash tests/shell/test-root-disk-guard-fixtures.sh # PASS
bash -n scripts/f1a/launch-acquisition.sh
scripts/f1a/launch-acquisition.sh --help
python3 scripts/f1a/acquire.py --help
```

**41 Python tests plus both common-guard suites PASS**. F1A tests include metadata/Git identity, path escape, wrong manifest/UUID, exact index set, real exclusive flock, resume inode/prefix/Range, both hash domains before rename, combined capacity boundary and concurrent rename. Reviewed D1b suites cover concurrent transfers/status, cancellation and guard/HTTP/hash failures. Independent review caught and resolved a GLM validator global collision and reservation rename race before launch. All **13 staged source/dependency/manifest hashes match local files**; [helper proof](f1a-helper-proof.json). Acquisition helper SHA256: **`b2a19c96034c1bc48bad39c516b67365af885a701532670a72f310fb18a505bb`**.

## Durable handoff — acquisition RUNNING

- Unit **`f1a-qwen-fast-acquire-20260915.service`**, PID **73182**, start **2026-09-14 23:22:28 UTC**, invocation **`490c652a660b4e258e5b13d34cc82ebb`**.
- Run/source/evidence: **`/data/build/f1a-qwen-20260915`**; log `acquisition.log`; authoritative status `evidence/acquisition-status.json`; PID is also recorded in that JSON. Model files: **`/data/models-large/qwen3-coder-next-fp8`**, lock `.f1a-acquisition.lock`.
- Two workers, MemoryMax 2 GiB, TasksMax128, nice10, timeout36h; transient job survives SSH exit but does not survive reboot. No automatic restart.
- At **23:23:42Z**, [bounded snapshot](f1a-acquisition-snapshot.json) confirms active/running, three tasks, second-process flock refusal, log228bytes. Actual file bytes **2,123,480,353**. JSON at23:23:39Z reports **2,039,594,273** bytes, **8/48 fully verified**, **26,328,353 verified bytes**, **0/40 weight shards verified**, state `DOWNLOADING_WEIGHTS`. Both distinct first weight partials are growing. Moving actual/JSON totals differ by write/status timing; neither is full integrity proof.
- Before/after metadata, runtime checks and launch, and final handoff strict/common guards PASS. Final root free **5,196,955,648 bytes**. Reports are under the run's `evidence/`; no root cleanup.
- GLM remains **`d1-glm53-acquire-20260915-d1b-p4.service`**, PID **49253**, original invocation unchanged. Its snapshot reports **189,348,575,237 bytes present**, **2/11 computed hashes**, **49,443,371,013 verified bytes**; source SHA256 remains `950334895648a53db8ffef32171f2e97a64bdf6b0c07eed56424a4649a76fcf4`. F1A never stopped, restarted, rewrote or loaded GLM.

End this bounded task with acquisition continuing. [Continuation](f1a-continuation.md) specifies fresh unit/status checks, resume and all 48-file/hash/final-guard gates. Task sibling `../acquisition-state.md` is the immediate orchestrator handoff.

## Installed SGLang and next action

[Full installed-source/auth/backend contract](f1a-sglang-contract.md), [exact evidence hashes](f1a-sglang-proof.json), immediate sibling `../sglang-contract.md`.

Exact R1/live image **`lmsysorg/sglang:v0.5.14-cu130`**, ID/digest **`sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3`**. Installed native architecture/parser and flags were inspected; synthetic `qwen3_coder` parsing and 15 pure auth decisions pass. Tiny actual Triton block-FP8 linear kernel executes correctly on both SM120 GPUs. This does not prove Qwen MoE/attention/GDN, TP collectives, memory fit, full-model inference or tool round trips.

**Auth finding:** native protected YAML `--config` supports `api-key` internally without key-bearing OS argv/env, but stock startup `ServerArgs` repr leaks the value. `/server_info` and `/get_server_info` include it through `dataclasses.asdict`. No native `--api-key-file` was found. F1S must prevent both logging and diagnostic disclosure, fixture-test the solution, retain single-tokenizer authentication and verify missing/wrong/correct-key behavior. Do not place real keys in Docker metadata, env, Git, logs or arguments. No real key was created/read/displayed here.

F1S owns the new SGLang declarative adapter and auth probes after D2. F1D owns reviewed merged-code activation, one-active-model enforcement, host loopback/SSH forwarding, actual auth/readiness, tool calls and measured resources. **No inference activation, llmctl/profile/lifecycle edits, public binds, host driver/toolkit/daemon/firewall/SSH changes, restart/reboot or disk changes occurred.** Historical deployment HEAD `e4907b96a555b9a7a1580f4dc932da51b5e2f3a9` and its three dirty report paths remain untouched.

Final packaging checks PASS: staged whitespace/diff review, value-shaped grep credential scan, remote URL credential check and exact local/effective Git author **and** committer `CodexAIagent <133749519+djeZo888@users.noreply.github.com>`. No secrets, weights, memory files or live environment files are staged. Orchestrator owns synchronization; no push.
