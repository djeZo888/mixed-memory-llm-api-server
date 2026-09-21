# Q38MAX caps fixture follow-up

Source-only Worker2 follow-up atop root-reviewed
`609a32d494812bcace8af869f13ad428418a3284`; no ai-vm or API operations.
Production launcher, profiles/model/runtime/deployments and APISELECT snapshot/docs
remain byte-identical. Existing deadlines and the exact FAULT_MARKER are retained.

At each existing isolation boundary, exact `/dev/nvidia-caps` is allowed only
when absent or an ordinary nonsymlink root:root0755 directory proven empty through
a nofollow directory descriptor and stable metadata. Every entry is refused
without following it or retaining its name. Caps stays outside CONTROL_NODES and
control-device result identity; per-GPU/DRI and character-control checks remain.

Failure-only diagnostics add finite device facts and warmup child scenario,
returncode, stdout/stderr lengths, marker equality/count and closed parsed failure
metadata. Original success predicates and the two established bounded worker-private
stderr captures remain intact. New failure JSON excludes raw streams. No recursive
diagnostic schema or success-schema change is introduced.

The observed timeout-scenario child failed ENTRY device-name preflight before
imports/warmup/watchdog. Directory contents and creator were not captured; these
facts establish neither emptiness nor GPU access. The watchdog-race hypothesis
is not the cause and no timing adjustment is made.

All 90 tests in the four impacted cache/fixture diagnostic suites passed once.
Fixture/provenance pins and the 68-file source inventory verify; snapshot hash
refresh is mechanical. Source tests use synthetic collaborators; the next authorized
native check must prove caps emptiness or fail. No native acceptance, model load or
context claim is made.
