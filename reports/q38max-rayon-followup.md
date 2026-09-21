# Q38MAX Rayon fixture follow-up

Source-only mac-worker2 at exact root base
`aafbfdd5a3d318105506e5f0517866aac20d7755`. Docker creates each existing fixture
context with `RAYON_NUM_THREADS=1`; existing inspect validates it, and parent/cache
entry checks refuse missing or nonexact values before native imports. No host or
daemon environment is set. Production bytes, pids128, OpenBLAS1, deadlines,
markers, auth/GPU/key gates and private stderr captures remain unchanged.

Rayon tag v1.11.0 declares [rayon-core1.13.0](https://github.com/rayon-rs/rayon/blob/v1.11.0/rayon-core/Cargo.toml#L1-L3),
matching the reported error. Its [default thread-count resolution](https://github.com/rayon-rs/rayon/blob/v1.11.0/rayon-core/src/lib.rs#L433-L460)
uses positive `RAYON_NUM_THREADS` before CPU-count fallback; the
[global pool uses that default builder](https://github.com/rayon-rs/rayon/blob/v1.11.0/rayon-core/src/registry.rs#L193-L228).
This requests one Rayon worker while preserving genuine tokenizers, constructor,
template and auth operations; it does not disable tokenizers parallelism.

Inheritance/allowlists checked once: cache and auth/timeout subprocesses plus the
cleanup child inherit environment; spawn entry retains parent environment.
Q38FIN restores the original environment for failure children; checked launches
restore the validated snapshot. Extension cache isolation removes only its exact
SGLANG extension key. Fresh Docker contexts always receive the literal setting.
The production validator already permits this unrelated variable and is unchanged.

Observed native128 failure: auth child rc2/stdout154B/stderr386B/marker0;
OpenAIServingChat construction reported Rayon global-pool ThreadPoolBuildError,
WouldBlock errno11. Caps/cache passed; no model loaded, no retry, cleanup/release
PASS. PID usage/events/threadcounts were not captured: PID-cap exhaustion remains
a hypothesis. Native correction remains NOT_TESTED until the next actual check.

Eight impacted focused checks passed once. Required pins and the 68-file source
inventory verify once; previous reports and native NOT_TESTED are retained.
