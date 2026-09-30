---
license: mit
base_model: XiaomiMiMo/MiMo-V2.6-Pro-RL
tags:
- gguf
- mimo
- metal
---

# MiMo-V2.6 Pro RL GGUF for DwarfStar

GGUF files for the MiMo-V2.6 Pro RL port in [DwarfStar (DS4)](https://github.com/antirez/ds4),
branch [`kernelpool/ds4:mimo-v26`](https://github.com/kernelpool/ds4/tree/mimo-v26)
(pull request: TODO link). Metal only. The model runs over tensor parallelism
between two 512 GB Macs.

## Files

The main GGUF is above the Hugging Face single-file limit, so it is stored in
two parts and joined after download, the same way the official DwarfStar Q4
release is.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `MiMo-V2.6-Pro-RL-MXFP4.gguf.part1` | 480,000,000,000 | `2c53578328dedbb3462f01422fa0548eccd5567ff8e2ab7254aebf74d0c3aea9` |
| `MiMo-V2.6-Pro-RL-MXFP4.gguf.part2` | 77,146,510,560 | `601b0ad28e8e36bf88adabb97e4994ffc9da281ec26488671350645850ed969e` |
| `MiMo-V2.6-Pro-RL-MXFP4.gguf` (joined) | 557,146,510,560 | `dac336f68cecf88b8ca04ab4ea2c75b831752e0323c7152a758082826f60bf21` |
| `MiMo-V2.6-Pro-RL-DFlash-Q8_0.gguf` | 2,941,587,648 | `3aec4c9819dacad46e5bca5ccd55b92e426e807616783f8140914854e76e4e91` |

The main file uses the `mimo2` layout: the checkpoint's own MXFP4 experts
repacked without requantization, Q8_0 attention, dense and output weights,
BF16 embeddings, and the three MTP blocks. The DFlash sidecar uses the
`dflash` layout plus the mask embedding and value scale DS4 needs.

```sh
hf download kernelpool/MiMo-V2.6-Pro-RL-MXFP4-GGUF --local-dir gguf
cd gguf
cat MiMo-V2.6-Pro-RL-MXFP4.gguf.part2 >> MiMo-V2.6-Pro-RL-MXFP4.gguf.part1
mv MiMo-V2.6-Pro-RL-MXFP4.gguf.part1 MiMo-V2.6-Pro-RL-MXFP4.gguf
rm MiMo-V2.6-Pro-RL-MXFP4.gguf.part2
openssl dgst -sha256 MiMo-V2.6-Pro-RL-MXFP4.gguf   # dac336f6...
```

Appending the second part to the first keeps the extra disk space to the size
of the second part.

## Run

Both Macs need the joined file locally. Each rank keeps half of the attention
heads, half of the routed experts and half of the vocabulary head, about
270 GiB resident, so each Mac needs 512 GB. The link setup is in
[docs/DISTRIBUTED.md](https://github.com/kernelpool/ds4/blob/mimo-v26/docs/DISTRIBUTED.md).
Start the worker first:

```sh
git clone -b mimo-v26 https://github.com/kernelpool/ds4 && cd ds4 && make
# Machine B (worker)
./ds4 -m gguf/MiMo-V2.6-Pro-RL-MXFP4.gguf --ctx 8192 --mtp \
  --tensor-parallel --role worker --coordinator 192.168.0.1 9911 --transport rdma
# Machine A (coordinator)
./ds4-server -m gguf/MiMo-V2.6-Pro-RL-MXFP4.gguf --ctx 8192 --mtp \
  --tensor-parallel --role coordinator --listen 192.168.0.1 9911 --transport rdma
```

`--mtp` drafts with the MTP blocks inside the main file; both ranks run the
draft and verify it together, so pass it to both or to neither. Greedy output
follows plain decoding.

The server exposes `mimo-v2.6-pro`, `mimo-v2.6-pro-chat` (thinking off) and
`mimo-v2.6-pro-reasoner` (thinking on).

DS4 does not run the DFlash sidecar or vision under tensor parallelism yet,
so the sidecar is not used for now and no vision encoder is included.
See [docs/MIMO_V26.md](https://github.com/kernelpool/ds4/blob/mimo-v26/docs/MIMO_V26.md).

## Conversion

Written by `gguf-tools/mimo26_quantize.py` from `XiaomiMiMo/MiMo-V2.6-Pro-RL`
at revision `54b10491b1811c76aa9681a9d0ff872396a4064c`. The converter
de-interleaves the tensor-parallel chunks of the fused QKV projection and
keeps the released MXFP4 expert blocks bit for bit; the source revision is
recorded in the GGUF metadata.

## Quality

Scored over two-Mac tensor parallelism on 100 official continuations from the
Xiaomi platform with the fixture in
`gguf-tools/quality-testing/mimo-v2.6-pro-20260923`; the reference scores are
in the repository's `QA_BEFORE_RELEASES.md`.

The original checkpoint is released by Xiaomi under the MIT license, which
applies to these files as well.
