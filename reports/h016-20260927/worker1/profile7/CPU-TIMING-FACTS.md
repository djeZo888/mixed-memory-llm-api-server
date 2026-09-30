# CPU backend and retained timing facts

At13:36:34 UTC exact R5 PID2782009 mapped `/opt/llama/libggml-cpu-zen4.so` (SHA2560899d6e438b3773955be3f930d3c095c92a896e63bf8b6707f1d9164ae7888f2). The retained CMakeCache confirms GGML_NATIVE=OFF, BACKEND_DL=ON, CPU_ALL_VARIANTS=ON, Release, SM120a-real. Source HEAD7ac59a6e3ad851cd41af00f678effab0598ba9a8. Source ggml/src/CMakeLists.txt512 includes AVX2 plus AVX512/VBMI/VNNI/BF16 in zen4. This proves the loaded backend variant, not a sampled execution kernel.

The complete emitted native log contains no tensor buffer assignment or backend selection lines at verbosity3. **CPU_REPACK versus ordinary CPU buffer/kernel assignment remains UNAVAILABLE.** No-host skips CUDA_Host; it does not establish that CPU-MoE extra buffers cannot select CPU_REPACK. The generic CPU traits at ggml-cpu.c287–292 assign MXFP4 vec_dot to ggml_vec_dot_mxfp4_q8_0 with Q8_0 activation operand. x86/quants.c918–1002 has AVX2/AVX branches and scalar tail. Native MXFP4 expert weight precision and Q8_0 dot operand are different facts. W2's CPU_REPACK branch evidence must remain a live alternative until sampled symbols or buffer readback distinguish it.

R5 final printed native timing lines independently match retained parsed SSE timing objects (native log is rounded to0.01ms). The existing request capturer directly assigned event.timings and did not compute or normalize its values. Distinct response IDs, prompt hashes and taskIDs134/182/249 are retained.

| Input | Native predicted_ms | predicted_n | Native interval denominator | ms/interval | HTTP wall−TTFT−native decode |
|---:|---:|---:|---:|---:|---:|
|4096|43776.971|41|40|1094.424275|+0.000435616s|
|16384|59139.755|55|54|1095.180648148|+0.000231122s|
|65536|48187.979|45|44|1095.181340909|+0.000733859s|

Exact formulas: `predicted_per_token_ms = predicted_ms / (predicted_n − 1)`; `predicted_per_second = 1000 × (predicted_n − 1) / predicted_ms`. First predicted token is accounted in prompt completion; do not divide by predicted_n when comparing native rate. Retained timing source uses ggml_time_us and t_max_predict_ms as termination, not rate limiting. The actual argv has sleep-idle-seconds=-1, poll=0 and poll-batch=0; no configured per-token rate/sleep limit was found. This is source/configuration evidence, not proof of why native intervals are so close.

Original raw SSE chunks and first/last-output monotonic timestamps were NOT retained. TTFT and full-drain wall were retained; their difference follows native decode to sub-millisecond precision. No causal claim follows. R6 will retain raw base64 chunks and monotonic receive/first-output/last-output/full-drain timestamps in private receipts, with the full unfiltered native log.
