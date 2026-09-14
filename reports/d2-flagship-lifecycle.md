# D2 — flagship lifecycle source

- Date: 2026-09-15; worker: Mac-Worker2, Python 3.14.7.
- Branch: `milestone/d2-flagship-lifecycle`.
- Reviewed integration base: `051c663143326d2e4a15614454a4c3b2ad98bf46`.
- Result: source implementation and deterministic worker verification; live deployment remains D3.
- Exact D3 commands, instance/key contract, boot replacement, rollback and limitations:
  [D2 handoff](../docs/lifecycle/d2-handoff.md).
- Final commit and bundle identity are recorded in the external task `progress.md`
  and final delivery summary, avoiding a self-referential commit hash in this file.

## What changed

Replaced the old unlocked SGLang-only lifecycle section of `scripts/llmctl` with
separately owned `scripts/lifecycle/` source. Existing model/runtime planning,
validation and download-plan commands remain. Declarative GLM8K/32K profiles
consume the exact model/runtime contract; none downloads weights or builds images.

Complete mutations hold one process mutex and re-read state under lock. Atomic
schema2 state separates selected deployment, desired running/stopped intent,
observed readiness and immutable container identity. Missing selection never
chooses smoke; deactivation leaves a tombstone. Historical Qwen30B/smoke identity
migrates with stopped/manual intent, never automatic resume.

Start checks exact mount targets/UUIDs/devices before artifact stats or Docker,
all eleven file sizes, D1 evidence, key metadata, storage policy, owned conflicts,
loopback publication, image/command/mount/GPU/log contracts and bounded
authenticated readiness for the exact alias. Stop remains identity-checked and
available when start guards or either journal write fail. A failed start retains
honest running/unknown state and a deterministic stop path.

The supplied one-shot systemd unit is the sole proposed boot intent owner;
Docker restart is disabled. D3 must remove the R1 old M6B branch-changing boot
writer before installation. Nothing was installed or changed on a server by D2.

## Source and artifact contracts

| Item | Exact selection |
| --- | --- |
| Model profile | `glm-5.3-ud-q4-k-xl` |
| Deployment profiles | `glm-5.3-ud-q4-k-xl-8k`, `glm-5.3-ud-q4-k-xl-32k` |
| Served model / endpoint | `glm-5.3`, `http://127.0.0.1:30002/v1` |
| Artifact revision | `346b3591c7f28d1a23716f97a065ecf12ec14771` |
| Artifact inventory | 11 shards, 467289116837 bytes; `UD-Q4_K_XL` directory retained |
| Runtime profile | `llama-cpp-v0.4.1-d1` |
| Runtime source | `v0.4.1`, `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4` |
| Actual binary version | `0.4.1-dev (build 62, commit b29c606)` |
| Image tag | `local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d1` |
| Local image ID | `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62` |
| Launch | CUDA0/CUDA1, CPU MoE, layer split 1:1, load-mode none, Jinja, no WebUI, one slot |
| Template candidate | `clear_thinking=true`; live model behavior NOT_TESTED |
| Key | `/data/services/secrets/llm-api-key`, regular0600, exact token bytes without newline |

[D1 runtime proof](d2-contract-evidence/d1-runtime-proof.json),
[pinned CLI help](d2-contract-evidence/d1-cli-selected.txt), and
[D1b contract](d2-contract-evidence/d1b-runtime-contract.md) were supplied as local
inputs. D2 did not run their recorded VM commands. D1 BUILD/CUDA/CLI and D1b
identity/help PASS are external evidence, not D2 inference results. The verbatim
[D1 contract input](d2-contract-evidence/D1-CONTRACT.md) includes an earlier
provisional section superseded by its final update; current runtime profiles and
this report use the final image/CLI facts. The readable CLI `.txt` removes trailing
whitespace; [the verbatim JSON payload](d2-contract-evidence/d1-cli-verbatim.json)
preserves the exact supplied bytes and is checked against D1's SHA256. No source
facts or runtime proof hashes were changed.

Host UUIDs are confined to the explicit `ai-vm-d0b` instance. The generic template
has no UUID defaults. Runtime scratch stays on models-large; no duplicate
`/data/hf-cache` weights are assumed. Artifact integrity completion and obsolete
boot-owner removal are still false in the example instance, so activation fails
closed until D3 fills the remaining reviewed evidence.

## Verification

| Check | Result / scope |
| --- | --- |
| `python3 -m unittest discover -s tests/lifecycle -q` | **PASS: 116 tests**, Mac worker, 5.843s; includes8 independent offline verifier tests |
| `test-llmctl-static.sh`, `test-llmctl-fixtures.sh` | PASS: retained planning regressions |
| `test-llmctl-lifecycle-static.sh`, `test-llmctl-lifecycle-fixtures.sh` | PASS: help, refusal, explicit selections and CLI safety |
| `test-sglang-smoke-static.sh` | PASS: actual functional offline verifier execution and template checks |
| `test-sglang-real-fast-static.sh`, `test-large-model-plan-static.sh` | PASS: retained source/planning regressions |
| `verify-sglang-smoke-plan.sh --instance /nonexistent-d2-instance.json` | PASS: offline contract; live host/readiness explicitly NOT_TESTED |
| `python3 -m py_compile scripts/llmctl scripts/lifecycle/*.py` | PASS |
| `bash -n` changed shell sources/tests | PASS |
| D2 local Markdown links, `git diff --check` | PASS |
| Local author and committer, reviewed base and feature branch | PASS: CodexAIagent attribution, exact authorized branch/base |
| `git remote -v` credential check | PASS: credential-free HTTPS GitHub remote |
| Final grep-based changed-source secret/forbidden-file scan | PASS before feature push; filenames only on detection |
| GitHub-hosted CI execution | NOT_TESTED; supplied workflow runs locally passing suites |
| Live Linux/CUDA/GLM/API/controlled service restart/boot | **NOT_TESTED by D2** |

All listed shell tests are under `tests/shell/`. Packaging uses fail-fast
`set -euo pipefail`; no failing check can fall through into commit or push.
The final feature ref and bundle are verified after committing and recorded in
the external delivery manifest.

Worker checks exercise real Python state/locking code and real loopback HTTP test
servers against tiny synthetic inputs. Docker, mount metadata and model artifacts
are injected deterministic fixtures. The process tests use separate processes,
not only threads. No synthetic assertion is described as a live VM result.

Coverage includes full-transition concurrency and state re-reading; missing,
invalid, migrated and stale state; UUID/unmounted/wrong-device rejection; exact
11-file size checks without payload hashing; other-port conflicts; every effective
published bind and network escape; wrong model/auth/health/timeout; truthful failed
state; corrupted/missing journals; safe stop when guards or writes fail; legacy and
flagship start/stop/restart; manual/resume boot intent; image/launch/mount/GPU/log
reuse mismatches; secret-safe error/environment handling; exact key bytes.

### Retained smoke planning verifier correction

The original `verify-sglang-smoke-plan.sh` called `llmctl active`, assumed the old
`active: none`/key-value text format and a smoke-only selection, then tried `sudo
docker ps`. The first D2 run failed before that Docker probe because new live
status without an instance exits nonzero with explicit observation-unavailable
JSON. A syntax-only replacement of this functional check was rejected in root
review and is **not** the delivered correction.

The retained verifier now performs its template/path/image checks and consumes
`llmctl status --offline` schema2. Offline status reports saved intent separately
from actual observation (`observed:null`, `container_running:null`,
`observation:not_performed_offline`). No installed Docker, GPU, key, mounted data,
API or running smoke model is required. Any existing selected deployment is
permitted for planning; it is not called healthy. Independent mock executables
exercise absent/stopped/ready-recorded/other-model status, bad or legacy responses,
command failure and a Docker sentinel. The shell smoke test executes the actual
verifier and asserts functional PASS plus explicit NOT_TESTED live scope.

## Warnings and limitations

- Live GLM load, authentication behavior, inference, tools, 8K/32K fit/latency, GPU
  execution, Linux systemd verification, controlled service restart and full boot:
  **NOT_TESTED by D2**. D3/V1 own them.
- Root guard remains WARN below6GiB / HALT below4GiB. Its historical shared UUID,
  layout and environment assumptions remain unchanged; I1/I2 must parameterize
  those guards for a different fresh host using the instance contract.
- This is one-shot boot intent replay, not a new crash restart supervisor.
- If `/data` is unavailable, stop can use volatile `/run` recovery, but D3 must
  restore `/data` and repeat stop before reboot to persist intentionally stopped
  intent. Missing all trusted identity evidence requires reviewed manual recovery.
- Legacy support retains the two existing SGLang containers, not arbitrary new
  SGLang models or recreation of absent legacy deployments. Manager raw log relay
  is refused; D3 must use reviewed redaction for diagnostic excerpts.
- F1S must supply a separate Qwen3-Coder-Next FP8 profile and SGLang-specific
  validation/launch/reuse/auth adapter. The current `validate_deployment`,
  `create_args`, `launch_command`, `validate_reused_contract` are llama.cpp-specific.
  It must not disguise the future model as legacy Qwen30B. See the handoff boundary.
- D2 is not the requested whole fresh-Linux installer; I1/I2 own it. No new model,
  quantization, exposed LAN endpoint, browser/UI or VM-side agent execution was added.

## Files changed

- `scripts/llmctl`; `scripts/lifecycle/{__init__.py,manager.py,runtime_io.py,llmctl-boot.service}`.
- GLM model/runtime JSON; 8K/32K deployment JSON; explicit instance and generic template.
- `scripts/sglang/verify-sglang-smoke-plan.sh` (specific root-authorized offline correction).
- `tests/lifecycle/`; the two llmctl lifecycle shell tests and retained smoke static test.
- `.github/workflows/d2-lifecycle.yml` (separate workflow to avoid A1 workflow collision).
- This report, copied D1 input evidence and `docs/lifecycle/d2-handoff.md`.

D1 acquisition/build helpers, `containers/llama-cpp/Dockerfile`, A1 clients,
`scripts/agent/`, shared README/current-state and original boot unit were not edited.

## Next action

Root reviews/merges the checked feature branch/bundle. D3 fills remaining artifact
and boot-removal evidence, executes the documented sequence, proves 8K first,
then measures32K and worker-side OpenCode/tool headroom. F1S and I1/I2 follow their
separate adapter/installer scopes.
