# H042 E-cleanup01 — source cleanup

Source checks **PASS** at `581fa4133fbdd2e5255e33482d058295a9cc3b0f` from exact base `b5b7b894a50481661ade7623ce23c94b86e02dcd`. This source-only mac-worker2 task does not qualify native startup, runtime, AUTO, inference, deployment or production; all remain **NOT_TESTED**. No SSH/Linux/model/fan/download/upstream/pin/push operation was performed.

The manual caller now forwards its AbortSignal into reviewed entry loading. Manual cleanup retains the original operation error even when the thrown value is falsy. The owned runner rechecks cancellation after the durable startup receipt and clears the deadline timer and abort listener when an IPC operation is abandoned. Admission, exact source/build qualification, manual policy and ownership guards are unchanged; entry.ts needed no change.

Patch adoption is verified without reapplying integrated source. The supplied gzip SHA-256 is `eeabe0c2e28cac9e7c56373ae3b895f25639de1043be6a9e272c1759cba7a8b4`; retained decompressed SHA-256 is `72b102c076dd53f69d1777b8aef2e289d2820e92a190b62bf60ca43c5499c7f3`. Full `git apply --check` actually exited **1**, expected because both hunks already exist. Exact `git apply --reverse --check` exited **0**. A private reverse/apply round trip returned both exact-base files byte-identically; no derived patch was needed. All originals, failed logs, command receipts and hashes are in `../output/adoption/`, `../output/logs/` and `../output/receipts/`.

| Source check | Actual exit | Tests passed |
| --- | ---: | ---: |
| New focused cleanup tests | 0 | 14 |
| H041 completion08 | 0 | 13 |
| H041 completion09 | 0 | 7 |
| H041 native adapter completion | 0 | 8 |
| Wider affected adapter tests | 0 | 43 |
| Server typecheck and build | 0 each | — |
| Adapter noEmit and build.tsconfig | 0 each | — |

The 14 focused tests cover acquired success, failure before open, manual cancellation, qualification failure/cancellation, pre-READY abort, READY mismatch, abort during real receipt fsync, cancelled/expired IPC timer cleanup, pre-aborted no-acquisition, already-exited close readback and original-plus-cleanup error identity. Eleven actual owned Node fixture processes exited with code0/signalnull; logs include PID and OS absence readback before any second shutdown could hide missing caller cleanup. Historical-clock source fixtures grant no operational GO.

There are 85 distinct source tests passed, no test failures or skips. The only nonzero retained check is the expected full patch apply-check. Every check in the JSON companion retains actual argv/cwd/start/end/integer exit/log SHA-256. Immutable dependency symlinks were only read; generated builds are in this isolated checkout or its output directory.

Source changes are sealed separately from this report. Final export provides bundle/diff/HEAD/RESULTS, changed-file and complete export hashes. The untracked preexisting server/node_modules symlink is excluded from commits and bundle. Root must collect original CLI/wrapper/outer terminal receipts after voluntary session exit and review before integration. No task blocker remains; native/runtime/deployment qualification is outstanding.

Fixed pins remain Sova0.158.0/upstream064c6b8c737f5b41d171fdda80bd9ef10ad06eb3, context480000/auto400000/output65536. Mac CLI0.159.2 is separate. An unresponsive child without captured OS identity remains quarantined/unconfirmed under the existing exact-identity guard.
