# H036 MIMO-480K01 source/current readback

The exact950000->480000 native profile reduction now has explicit preparation and
reconciliation commands, separate receipt names/status, an explicit owner-only
source delta, and the existing guarded one-time start path. launch.json and all
non-context profile/runtime/GPU flags remain unchanged. The reviewed stopped-only
install helper preserves old bytes before its first write and refuses partial
replay. Activation remains subject to separate root GO.

The one authorized pure-read SSH observation at21:53:15UTC found RUNNING950000,
props/slot950000, idle proxy0, hardware_latched=false, exact owner2406d9a0 and no
manifest source-closure discrepancies. PREP matched03c0933c. Three Qwen and image
native identities were captured; raw source/profile/captures are private offGit.
No VM writes, lifecycle or model actions occurred in this task.

Focused offline tests:91 collected,89 passed,2 skipped (existing optional private
historical-capture fixtures not supplied). Thirteen context-specific cases passed,
covering prepare/settlement/install/normal-supervise consumption, exact old/new
native manifest validation, failure/history preservation, changed flags/runtime/
GPU/increase refusal, absent physical release or changed boot/source/selection,
current guard/admission checks, archive integrity and partial mutation refusal.
The existing real temporary-lock startup tests and source/timeout successor tests
passed. No new test framework or broad suite was used.

Retained failures: the first context run had4 assertions after its physical-proof
stub allowed a HELD fixture; reconciliation now explicitly checks SETTLED launch
admission before physical proof. The first combined test invocation used tests/
as cwd and one existing package import failed; rerunning from repo root resolved
it. A local exact-capture validation mock compared str to Path; normalization fixed
that fixture. All original logs/receipts remain in task output. None was a VM test.

Actual current480K allocation/readiness/tool/occupied-context proof remains false.
Existing950K evidence and qualified manifest inputs are preserved as historical
source-admission evidence, never rewritten as a480K live pass. See the concrete
ACTIVATION-PROPOSAL and hash-bound pins for the later one-stop/one-start sequence.

Native session01a0ef26-797d-7ab2-b6ce-183090daf948 started21:51:10UTC. This report is
written before native exit; the outer wrapper must supply the actual exit receipt.
No clean-exit claim is made here. No GitHub push, subagent or model override used.
