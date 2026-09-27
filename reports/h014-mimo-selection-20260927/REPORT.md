# H014 source-only selection evidence — 27 September 2026

**Decision remains pending: Pro-first versus full-quality Flash-first. Root selects.**
No production contact, weights, builds, inference, deployment, or push occurred.
Both Qwen480K instances and the image service must be preserved; the arithmetic
assumes GLM unloaded, with its rollback retained. No fit or throughput is claimed.
Read AGENTS.md, the H014 plan, local H013 STATUS files and current H013 status;
this user assignment supersedes the plan's earlier Flash-only selection.

## Findings that change the selection brief

1. **The existing ~155.9 GiB Flash candidate is not BF16 for all other matrices.**
   Its own conversion log shows native MXFP4 experts retained, followed by
   BF16 attention matrices converted to Q8_0. The matching full-quality candidate
   examined here is **AesSedai Flash MXFP4/BF16, 162.896 GiB / five shards**.
   The size difference also includes packaging/MTP differences; do not attribute
   all of it to quantization. [F-GGUF conversion log, L2621, L2676–2678,
   L3138–3149](https://huggingface.co/ggml-org/MiMo-V2.6-Flash-RL-GGUF/blob/a5d1269fdcf9c3346934411f700038e9cd9d5102/convert.log#L3138),
   [F-FULL author card](https://huggingface.co/AesSedai/MiMo-V2.6-Flash-RL-GGUF/blob/05c13439c18ba7183cb6afe294924c75ba7aa7b4/README.md).
2. **Pro has a concrete llama.cpp-format native-expert candidate**, AesSedai
   MXFP4/BF16: **577,669,438,240 bytes = 537.996588 GiB / 13 shards**.
   The card says 537.99 GiB. Its quality log reports 207 MXFP4, 163 BF16 and
   357 F32 tensors; BF16/MXFP4 is shorthand, not literally every tensor's type.
   This is author evidence, not local validation. [P-GGUF card](https://huggingface.co/AesSedai/MiMo-V2.6-Pro-RL-GGUF/blob/ba4eabb78b6c51ffd873ec73b9e12b0f64aced5d/README.md),
   [P-QA L75–80](https://huggingface.co/AesSedai/MiMo-V2.6-Pro-RL-GGUF/blob/ba4eabb78b6c51ffd873ec73b9e12b0f64aced5d/kld_data/wiki-test-raw/aes_sedai/MiMo-V2.6-Pro-RL-MXFP4.md#L75).
3. **Source support exists, but this exact CPU-expert/SM120 deployment is unqualified.**
   Pin examined upstream master to `7ac59a6e3ad851cd41af00f678effab0598ba9a8` (R).
   No unmerged Pro branch was required by the inspected source path. This is a
   research pin, not approval to replace the installed runtime or D1 rollback.

## Native quantization and provenance

F = official [Flash config](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Flash-RL/blob/5711b268169967567844e1e560e8a3966da959b1/config.json),
revision `5711b268169967567844e1e560e8a3966da959b1`, SHA256
`61bea4a0f7a0dd8969f8cae528761e26b697dd12ff63e98804c3f0945492e621`.
L286–292 specify block size 32 and `store_dtype: mxfp4`, despite the broader
`quant_method: fp8` label. P = official [Pro config](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Pro-RL/blob/73875d00b30a89ef8cc353a0b60b0e9f9561952d/config.json),
revision `73875d00b30a89ef8cc353a0b60b0e9f9561952d`, SHA256
`a9dc00e2a0c2c172efd198f42e81e41c95472021b57c65366c06587d44038b62`;
L351–357 carry the same quantization contract. The official Pro card's
1.02T total / 42B active / 1M claims are published specifications, not local
performance or quality conclusions. [P card L80–81](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Pro-RL/blob/73875d00b30a89ef8cc353a0b60b0e9f9561952d/README.md#L80).

R's [conversion/mimo.py L177–252](https://github.com/ggml-org/llama.cpp/blob/7ac59a6e3ad851cd41af00f678effab0598ba9a8/conversion/mimo.py#L177)
recognizes that storage contract, requires 32-element blocks, validates expert
presence/scales, and writes routed gate/up/down tensors as raw MXFP4. Its
[base.py L758–792](https://github.com/ggml-org/llama.cpp/blob/7ac59a6e3ad851cd41af00f678effab0598ba9a8/conversion/base.py#L758)
reorders nibbles and retains the E8M0 scale byte: no new expert quantization.
Nonexpert FP8 projections are dequantized, including TP-aware fused QKV handling
(mimo.py L35–140); BF16 output retains those matrices at BF16, with F32 routing/
small-tensor exceptions (base.py L1075–1149). Thus native expert MXFP4 is distinct
from further Q2/Q3/BPW reduction, and from Q8 nonexpert conversion.

F-FULL revision `05c13439c18ba7183cb6afe294924c75ba7aa7b4` has five
`MXFP4/MiMo-V2.6-Flash-RL-MXFP4-0000N-of-00005.gguf` shards. Its author's
quality log reports 141 MXFP4, 119 BF16 and 248 F32 tensors (L75–77).
Both full-quality artifacts match the intended representation at the
publisher/config/converter level. Exact author conversion commit and exact
upstream checkpoint revision used by AesSedai remain **unverified**; no binary
bit-equivalence check was possible without weights. Public LFS hashes are
recorded in ARTIFACT-MANIFEST.json, not represented as locally verified hashes.

P-QA uses wiki.test.raw, 584 chunks at 512 tokens, 16 sequences and eight RTX
PRO 6000 Blackwell Max-Q GPUs. It reports PPL 3.172064 versus base 3.170872 and
mean KLD rounded to -0.000000. The raw ratio is 1.000376: the card's positive
percentage should not be read as improvement under its `1-ratio` column heading.
This does not qualify mixed CPU/GPU execution, tools, engineering tasks or 1M.
The exact runtime build used by that author was not established. [P-QA L4–17,
L288, L877–888](https://huggingface.co/AesSedai/MiMo-V2.6-Pro-RL-GGUF/blob/ba4eabb78b6c51ffd873ec73b9e12b0f64aced5d/kld_data/wiki-test-raw/aes_sedai/MiMo-V2.6-Pro-RL-MXFP4.md#L877).

K = [kernelpool card](https://huggingface.co/kernelpool/MiMo-V2.6-Pro-RL-MXFP4-GGUF/blob/c3d772ed7225b75c00c69c1da96429c9f630e3fe/README.md),
revision `c3d772ed7225b75c00c69c1da96429c9f630e3fe`: a distinct DwarfStar/DS4
`mimo-v26` Metal-only two-Mac conversion, with Q8_0 attention/dense/output,
BF16 embeddings, native experts and MTP. It identifies upstream
`54b10491b1811c76aa9681a9d0ff872396a4064c`. Its format label and author quality
claims do not establish llama.cpp CUDA compatibility; it is not the BF16-other
candidate above.

## Pinned runtime evidence and critical risks

All R paths below have exact original SHA256 and numbered excerpts in
SOURCE-MANIFEST.json / SOURCE-EXCERPTS.txt. Links use the immutable R revision.

| Concern | Source evidence and remaining boundary |
|---|---|
| Pro architecture/conversion | `conversion/mimo.py:16–32,146–173`; registers official `MiMoV2ForCausalLM` as `mimo2`, reads dimensions and hybrid pattern; hardcodes three MTP layers unless disabled. `src/models/mimo2.cpp:3–72` loads these arrays and tensors. Pro's 70 layers fall through the cosmetic model-size classification to UNKNOWN; the graph is dimension-driven. Verify 70 trunk + 3 MTP metadata/array agreement, correct TP QKV scales, RoPE, sinks and value scale 0.612. |
| CPU experts | `common/arg.cpp:2755–2773` exposes `--cpu-moe` and `--n-cpu-moe`; CPU type table `ggml/src/ggml-cpu/ggml-cpu.c:287–292` uses MXFP4 × Q8_0 dot, x86 `arch/x86/quants.c:918–939` has AVX2 implementation. Presence is not a throughput result; verify actual routed expert placement, CPU ISA, NUMA bandwidth and prefill GEMM behavior. |
| CUDA SM120 experts | `ggml/src/ggml-cuda/CMakeLists.txt:38–56,75–96` handles CUDA >=12.8 and 120a-real/12Xa; plain generic Blackwell claims are insufficient. `ggml-cuda.cu:5206–5264` allows MXFP4 MUL_MAT_ID with layout/precision restrictions; `mmq.cu:115–141` handles expert IDs. Pin toolkit/CMake/build flags and test actual shapes, no driver change assumed. |
| Additional compute quantization | `mmq.cu:115–133` defaults eligible Blackwell MXFP4 MMQ to **Q4 activations**, otherwise Q8, with an override. Native weight preservation does not imply BF16 activation computation or identical quality. Record and qualify activation precision; CPU/GPU paths differ. |
| Attention and KV | `fattn.cu:317–333,589–598` explicitly supports K=192,V=128 under GQA/mask constraints; Pro Q/KV ratio=128/8=16 matches the branch. Verify the actual F16 Flash Attention path, sinks/value scale, cache allocation and no large fallback workspace. |
| Chat/tools | Official Pro template hash matches the template exposed by AesSedai repository metadata. `common/chat.cpp:1211–1225` deliberately excludes its no-newline XML tags from the Qwen3-Coder specialized parser; `1332–1369` uses the differential autoparser. `chat-auto-parser-generator.cpp:180–250` constructs tool parsing. Template presence is not a tool pass: test reasoning on/off, streamed partial calls, typed/nested arguments, tool result continuation, stop/EOS and Sova delegation. |
| Scope/extensions | Start with plain text, no MTP/DFlash or multimodal sidecars. Loader skips MTP weights when disabled (`mimo2.cpp:34–35`), and normal KV filter excludes MTP (`llama-model.cpp:2739–2750`). Recheck selected artifact metadata; the Qwen image service remains separate and preserved. |

## Component memory, not a fit verdict

Historical physical MemTotal is 946,820,972,544 bytes = **881.795746 GiB**.
15% reserve = **132.269362 GiB**; aggregate used ceiling = **749.526384 GiB**.
This is neither current free RAM nor a candidate cgroup limit. **650 GiB was
GLM-specific and is not Pro approval.** Complete formulas/results are in MATH.json.

| Component | Full-quality Flash | Pro | Qualification assumption |
|---|---:|---:|---|
| GGUF file bytes / GiB | 162.896006 | 537.996588 | File storage, not resident RAM; includes artifact extras |
| Routed expert payload | 149.812500 GiB | 494.859375 GiB | MoE layers × experts × 3 × hidden × FFN × 17/32 bytes |
| File less expert payload | 13.083506 GiB | 43.137213 GiB | Includes nonexperts, MTP/metadata/alignment; not automatically GPU allocation |
| Trunk attention matrices at BF16 | 8.349609 GiB | 34.863281 GiB | Separate GPU/CPU placement required |
| Embedding + output at BF16 | 2.328125 GiB | 3.492188 GiB | May split CPU/GPU |
| Dense FFN + F32 router matrices | 0.558594 GiB | 1.168945 GiB | Norms/sinks and allocation padding additional |
| Global F16 KV at 1,048,576 | 22.5 GiB | **50 GiB** | One sequence, no MTP, actual per-layer dimensions |
| Compact sliding F16 KV, ubatch=512 | 0.142822 GiB | 0.219727 GiB | 768 cells after padding; 39/60 sliding layers |
| Full-size sliding F16 KV | 195 GiB | **300 GiB** | If full sliding allocation enabled; additional to global KV |

Pro's verified dimension formula is
`10 * 8 * (192 + 128) * 2 * 1048576 = 53,687,091,200 bytes = 50 GiB`.
F config has 9 global /39 sliding layers; P has 10/60. R's ISWA allocator
uses `pad256(min(context, 128*(unified ? n_seq_max : 1) + n_ubatch))` compact
cells (`llama-kv-cache-iswa.cpp:69–80`), then allocates per-layer K/V with
`n_stream = unified ? 1 : n_seq_max` (`llama-kv-cache.cpp:84,209–235`).
For one sequence, Pro sliding cache is 0.659180 GiB at ubatch2048 and
2.416992 GiB at8192. **CLI/common default `swa_full=false`, but raw C API
context default is true** (`common.h:573`, `common.cpp:1701`,
`llama-context.cpp:3741`). A wrapper must explicitly establish which applies.

Use a disjoint accounting ledger:
`host = resident CPU weights + resident duplicate pages backing GPU weights + host KV
+ CPU/pinned/scratch/runtime + preserved Qwen/image host memory + OS/other`;
`GPU = GPU weights + GPU KV + GPU scratch/graphs/driver/other`.
Virtual mmap length is not RSS. CPU mapped pages and the same file's page cache
must not be added twice; a retained host copy of GPU weights is a real additional
physical copy. File-minus-experts and detailed nonexpert rows are alternative
breakdowns, not additive categories. MTP loaded/skipped and reclaimable pages
must be measured. Model loading can peak above steady-state allocation.

A conservative all-file-resident, all-KV-on-host Pro scenario at ubatch512 is
588.216315 GiB, leaving 161.310069 GiB under the historical aggregate ceiling
**before every other host consumer and runtime overhead**. GPU placement moves
components between ledgers; do not subtract offloaded bytes unless host pages
are actually released. A hypothetical 96 GiB frontier has only89.28 GiB under
7% reserve: Pro's ~39.524414 GiB trunk matrix subtotal plus50 GiB global KV
already crowds that envelope before scratch. This flags placement review,
not proof of fit or non-fit on the real machine. Preserve16 GiB per Qwen,
5% Ada reserve, their existing GPU allocations and their unknown host buffers.

## First qualification boundaries for root review

After the user chooses, the separately authorized owner should verify current
registered storage/installed guards, live host baseline with both Qwen480K and
image preserved, frontier identity/health and GLM rollback. Review exact shard
hashes, converter lineage, tokenizer/template, R/toolchain, tensor placement,
activation precision, compact/full SWA choice, KV precision and all reserves.
Then a separately authorized isolated load and short text/tool check can qualify
allocation/graph behavior. Only after that: warmed serial4K/16K/64K tests with
separate prefill/decode/TTFT, peaks, tool correctness and small technical tasks.
Full1M occupied inference requires root review of those results and actual
allocation/time bounds. Keep85C or lower cutoff, no owned swap/OOM and no
thermal retry. GLM co-residency is optional later; no current choice or deployment.
