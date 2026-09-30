Update13:29:58:64K completed PASS at13:28:56.526621UTC,65536input/45output. Below is the preserved earlier snapshot analysis; see BENCH65536.json and64K-COUNTERS for terminal evidence. Allocation remains131072; no larger capacity validation.

# MiMo R5 maximum-context component estimate

Estimate only, based on the retained snapshot ending 2026-09-27T13:17:49.447621+00:00. Actual slot allocation is **131,072**; passed occupied inputs are **4,096 and 16,384**. The independent 65,536-input request was pending at this snapshot. Full17 is NOT_TESTED. No larger allocation or speed extrapolation was performed.

The exact retained runtime is `7ac59a6e3ad851cd41af00f678effab0598ba9a8`, image `cdb6efd75f53a8b453f866f30511b0f5c8d19440d3adaaf419e97bde1c2bf21e`. GGUF has 73 blocks, 3 inactive NextN blocks, 10 global trunk layers (0,7,15,23,31,39,47,55,62,69), 60 SWA trunk layers, 8 KV heads, key width192 and value width128. F16 global KV is `10 × 8 × (192+128) × 2 × C = 51,200 × C bytes`: **6.25 GiB at131,072; 50 GiB at1,048,576**.

Compact SWA uses `PAD(min(C,128 × 1 + 512),256)=768` cells with the retained one-sequence/ubatch512 settings. The 60 active trunk layers imply225 MiB of SWA KV, fixed as C increases under these same settings. This is a component calculation; actual per-buffer startup sizes were not retained in the available log output. No MTP is active.

Observed frontier readback is total97,887 / used46,482 / free50,769 MiB. Its arithmetic residual is636 MiB; the separate `memory.reserved` query reported638 MiB. Preserve that2 MiB discrepancy rather than treating the fields as exact interchangeable accounting. The7% free reserve is6,852.09 MiB.

Holding all non-global-KV use fixed gives `used(C)=46,482+[51,200×C/1,048,576−6,400] MiB`. The baseline already includes model, SWA, compute and other overhead; it does not separately identify their allocations.

| Context tokens | Global KV MiB | Estimated used MiB | Estimated free MiB | Margin above7% MiB |
|---:|---:|---:|---:|---:|
| 131,072 | 6,400.00 | 46,482.00 | 50,769.00 | 43,916.91 |
| 943,718 | 46,079.98 | 86,161.98 | 11,089.02 | 4,236.93 |
| 1,000,000 | 48,828.12 | 88,910.12 | 8,340.88 | 1,488.78 |
| 1,048,576 | 51,200.00 | 91,282.00 | 5,969.00 | -883.09 |

At1,048,576 the estimated use is89.14 GiB before any extra workspace; estimated free5,969 MiB misses the7% reserve by883.09 MiB. The algebraic zero-growth reserve ceiling is about1,030,490 tokens, **not a qualified capacity**. Roughly0.9–1.0 million tokens is only a future candidate range; additional workspace, host growth and actual guard behavior can lower it. Even the decimal1,000,000 row leaves only1,488.78 MiB for extra GPU allocation. Preserve15% host reserve, no owned swap and the85C-or-lower cutoff as separate gates.

Actual CPU model-buffer name/size and selected optimized ISA are **UNAVAILABLE** in the full retained Docker log filter. The launch proves `--no-host`, CPU-MoE64threads, exact NUMA binding, F16 KV and compact SWA intent. It does not prove CPU_REPACK, AMX or any optimized CPU backend was selected. Available symbols are not selection evidence.

Exact source evidence (line-numbered excerpts and SHA256 also embedded in the companion JSON):

- `src/llama-kv-cache.cpp` SHA256 `c83046da70d2806bce76e2396953dafc805c3c413ab9e80df3d82c940f9da7b1`.

```cpp
84:     n_seq_max(n_seq_max), n_stream(unified ? 1 : n_seq_max), n_pad(n_pad), n_swa(n_swa), swa_type(swa_type),
```


```cpp
209:         const uint32_t n_embd_k_gqa =            hparams.n_embd_k_gqa(il);
210:         const uint32_t n_embd_v_gqa = !v_trans ? hparams.n_embd_v_gqa(il) : hparams.n_embd_v_gqa_max();
```


```cpp
230:         const bool has_k = true;
231:         const bool has_v = !is_mla;
232:
233:         ggml_tensor * k = has_k ? ggml_new_tensor_3d(ctx, type_k, n_embd_k_gqa, kv_size, n_stream) : nullptr;
234:         ggml_tensor * v = has_v ? ggml_new_tensor_3d(ctx, type_v, n_embd_v_gqa, kv_size, n_stream) : nullptr;
```

- `src/llama-kv-cache-iswa.cpp` SHA256 `567fe836543e1dd9cdd5b7cb3a91afd049c17c7010f0bddf9fe149b02b5243cb`.

```cpp
58:         return !model.hparams.is_swa(il);
66:         return  model.hparams.is_swa(il);
69:     const uint32_t size_base = kv_size;
73:     uint32_t size_swa = GGML_PAD(std::min(size_base, hparams.n_swa*(unified ? n_seq_max : 1) + n_ubatch), 256);
```


```cpp
95:     kv_base = std::make_unique<llama_kv_cache>(
97:             v_trans, offload, unified, size_base, n_seq_max, n_pad,
98:             0, LLAMA_SWA_TYPE_NONE, mem_other_base, filter_base, reuse, share);
102:     kv_swa = std::make_unique<llama_kv_cache>(
104:             v_trans, offload, unified, size_swa, n_seq_max, n_pad,
105:             hparams.n_swa, hparams.swa_type, mem_other_swa, filter_swa, reuse, share);
```

- `src/llama-hparams.cpp` SHA256 `ab9acb8ffd22ce6d374b9db05103871a648db6f8e2a3b00321aa1a8f57d71556`.

```cpp
156: uint32_t llama_hparams::n_embd_k_gqa(uint32_t il) const {
157:     const uint32_t n_head_kv = this->n_head_kv(il);
158:
159:     return n_embd_head_k(il) * n_head_kv;
160: }
161:
162: uint32_t llama_hparams::n_embd_v_gqa(uint32_t il) const {
163:     const uint32_t n_head_kv = this->n_head_kv(il);
164:
165:     return n_embd_head_v(il) * n_head_kv;
```


```cpp
348: uint32_t llama_hparams::n_layer() const {
349:     return n_layer_all - n_layer_nextn;
350: }
```

- `src/models/mimo2.cpp` SHA256 `2aa58a9bdc648ac83aec0decb0d9e4075cce2bd152da0b69b0ace4f0446224d0`.

```cpp
6:     hparams.swa_type = LLAMA_SWA_TYPE_STANDARD;
7:
8:     ml.get_key_or_arr(LLM_KV_EXPERT_FEED_FORWARD_LENGTH, hparams.n_ff_exp_arr, hparams.n_layer_all);
9:     ml.get_key(LLM_KV_ATTENTION_SLIDING_WINDOW,   hparams.n_swa);
10:     ml.get_key(LLM_KV_ROPE_FREQ_BASE_SWA,         hparams.rope_freq_base_train_swa, false);
11:
12:     ml.get_arr(LLM_KV_ATTENTION_SLIDING_WINDOW_PATTERN, hparams.is_swa_impl);
```

Private snapshot SHA256 `c0d11830bc463122046c23b04b44c46c2524404cb586841098a9b74e6acaa157`; GGUF inventory SHA256 `a53a1db6e53c8a0f2a8f8381c40894643e18edad28f62d97b9925bd7d53bf0ae`. Raw private evidence remains outside Git.
