# H016 r3 independent local source review

Reviewed r3 against the reviewed r2 commit `782bd29`, its frozen source receipts,
`LOAD-CORRECTION.diff`, `STAGE.json`, and the completed local staging command.
No source blocker found. This review made no ai-vm connection and performed no
runtime mutation. It does not establish current VM readiness or inference success.

All eight r3 runtime/config files match the SHA-256 values in `STAGE.json`.
The following files remain byte-identical to the reviewed r2 source:

| File | SHA-256 |
| --- | --- |
| benchmark.py | `8cd27c4839328c5ba3187d58d270e7504cb7fecc75b3827b4ce8cd233325702b` |
| private_proxy.py | `82d88ed7e13de4a4a36b1a74a4186927e7e03a5380e109860e4e076f3baeb50c` |
| telemetry.py | `df2c572fba760c963886a80a4a534c12b3c817465efc4a54aa85e01a72c7f39f` |
| native_identity.py | `0ba1f5781585ba887bd639e950870976e0ecb159caa674cb72dfa41cc48d3518` |
| inspect_gguf.py | `bc76625dc1e370db29036fc8218eac82bea414e73dce6daa2b3bd43e650acba4` |

`LAUNCH.json` equals reviewed r2 after reversing the single `none` to `mmap`
change. The owner delta is limited to r3 namespace, exact dependency pins, two
readonly file mounts, the numactl interleave wrapper and the 1,200-second readiness
cap. `verify_retained.py` changes only its log namespace; its verification entry
point is not part of this launch. Image/native settings, security flags, canonical
lease, registered storage guards, GLM settlement/restoration, 13:25 admission
cutoff and 13:40 owner settlement are unchanged. Current adoption/proxy/node
drafts are excluded from the r3 runtime packet.

The completed staging command copied the two pinned dependencies through anchored
exclusive writes under root, after host-file protection and hash checks. It
explicitly applied mode `0755` to numactl and `0644` to libnuma and fsynced them.
This is review of recorded staging execution, not an independent remote stat.
The owner verifies their staged hashes before launch. Existing phase3 checks
report 12 tests: 11 PASS and one private legacy fixture SKIP; this reviewer did
not replay them.

Retained evidence limitations: the frozen placement helper totals resident NUMA
pages without separating anonymous/file pages or recording policy. The requested
interleave policy and anonymous pages per node require separate observed process
evidence. A benchmark `SUBMITTED` receipt precedes `c.request` and does not prove
`body_sent`; interrupted requests do not persist buffered partial response text.
Use retained native slots/logs for actual progress and report unknown values as
unknown. The production fixture counter checks capacity but does not itself
assert the expected 9,461-token pin; retain its observed result before claiming
that exact count.
