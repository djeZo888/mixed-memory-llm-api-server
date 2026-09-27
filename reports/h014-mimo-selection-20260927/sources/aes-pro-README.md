---
base_model:
- XiaomiMiMo/MiMo-V2.6-Pro-RL
---

This repo contains specialized MoE-quants for XiaomiMiMo/MiMo-V2.6-Pro-RL. The idea being that given the huge size of the FFN tensors compared to the rest of the tensors in the model, it should be possible to achieve a better quality while keeping the overall size of the entire model smaller compared to a similar naive quantization. To that end, the quantization type default is kept in high quality and the FFN UP + FFN GATE tensors are quanted down along with the FFN DOWN tensors.

The MXFP4 quant is the "full quality" version, as the model has MXFP4 experts.

The BPW quants have been created targeting specific sizes, using [ed's bpw-size PR](https://github.com/ggml-org/llama.cpp/pull/15550). I've included the `imatrix-bpw.gguf` and `bpw-state.bin` files needed to produce other quants using his PR.

| Quant  | Size                  | Mixture       | PPL                 | 1-(Mean PPL(Q)/PPL(base)) | KLD                  |
| :----- | :-------------------- | :------------ | :------------------ | :------------------------ | :------------------- |
| MXFP4  | 537.99 GiB (4.52 BPW) | BF16 / MXFP4  | 3.172064 ± 0.015439 | +0.0376%                  | -0.000000 ± 0.000000 |
| BPW3.5 | 416.88 GiB (3.50 BPW) | Q8_0 / varies | 3.231880 ± 0.015640 | +1.9240%                  | 0.141151 ± 0.000823  |
| BPW3.0 | 357.32 GiB (3.00 BPW) | Q8_0 / varies | 3.383461 ± 0.016667 | +6.7044%                  | 0.183875 ± 0.001023  |
| BPW2.5 | 297.78 GiB (2.50 BPW) | Q6_K / varies | 3.682749 ± 0.018545 | +16.1431%                 | 0.255708 ± 0.001335  |
| BPW2.0 | 219.58 GiB (1.84 BPW) | Q6_K / varies | 5.113859 ± 0.027763 | +61.2761%                 | 0.542302 ± 0.002336  |


![kld_graph](kld_data/01_kld_vs_filesize.png "Chart showing Pareto KLD analysis of quants")
![ppl_graph](kld_data/02_ppl_vs_filesize.png "Chart showing Pareto PPL analysis of quants")