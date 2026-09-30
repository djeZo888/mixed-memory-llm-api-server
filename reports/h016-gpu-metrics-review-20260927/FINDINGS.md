# H016 GPU DRAM metrics — early finding

Current authorized toolchain cannot establish actual VRAM DRAM read/write bytes/s
during existing R6 decode without restart, injection or replay. No collector is ready.

- Nsight Systems is absent according to the supplied W1 host inventory. Its
  documented DRAM/VRAM read and write bandwidth metrics are percentages of
  elapsed interface cycles / peak sustained throughput, not measured bytes/s.
  Obtaining it alone would not satisfy the requested measurement.
- The actual retained `GPU-TOOL-PREFLIGHT.json` was read. Existing image
  `sha256:a85c9f5af049f0ab679c1669ae6fa8393022886739af7361e85bb96878e8cdd4`
  contains `ncu` 2025.3.1.0 build 36398880 and lists `gb202`. This is filesystem,
  version and chip-name evidence only; no GPU counter or attachment was tested.
- Nsight Compute's attach workflow requires a target prepared by its launch
  instrumentation. It is not evidence of arbitrary attachment to the already
  running, uninstrumented llama process. One-pass metric selection does not prove
  absence of serialization, cache flushing or clock control.

Official sources: [Nsight Systems GPU metrics](https://docs.nvidia.com/nsight-systems/UserGuide/index.html#gpu-metrics)
and [Nsight Compute CLI modes](https://docs.nvidia.com/nsight-compute/2025.3.1/NsightComputeCli/index.html).
Version-specific details and retained receipt SHA follow in REPORT.md and
SOURCE-MANIFEST.json. No host contact, GPU action, installation, inference,
subagent or push. R6 remains W1-owned; Sova recovery remains HOLD.
