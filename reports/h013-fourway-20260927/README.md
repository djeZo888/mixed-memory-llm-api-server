# H013 four-way benchmark source archive

These are the unchanged, reviewed Worker1 sources used for Warm02 and the
conditional four-way trial on27September2026. Root synchronized them from the
worker delivery after verifying every entry in `SOURCE-SHA256.json`. The
recorded19 driver/warm checks and5 controller checks passed on the worker;
publication did not change or rerun their implementation.

The actual result is [thermal cutoff, with all owned work settled](../h013-ecc-off-comparison-20260927/README.md).
Warm02 passed; main stopped at the server Blackwell85C limit. No further stress
test is authorized by this archive. The original GLM1M result is separate.

This is task-specific benchmark evidence, not a general installer or service
launcher. It requires the original isolated task layout, guarded storage,
current protected parameters, retained private fixtures and a fresh scoped GO.
Old GO/dispatch intent must never be reused. Long-lived worker control used
the active macOS GUI launchd domain with an explicit resolved Python path;
VM benchmark and settlement jobs used independent bounded systemd units.

Driver package SHA256:
`ff31aca7a201b29226a844c0047545f8fe79aa240b7ad915802dcf59c1bcebee`.
Controller SHA256:
`6fecc33efa6d163b4d550571b8402adfad0fed9912970a57ee681cd451002472`.
Bulky fixtures, generated media, raw traces, credentials and private state stay
outside Git. The result report identifies their retained evidence archive.
