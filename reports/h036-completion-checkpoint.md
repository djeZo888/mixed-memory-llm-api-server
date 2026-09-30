# H036 completion checkpoint — release pending

**September 30 update:** the host reboot and subsequent VM recovery have now
been inspected. ai-vm was then shut down at the user's request for a cable trial.
See the [reboot recovery checkpoint](h036-reboot-recovery.md) for current state,
source repairs and remaining gates. The evidence below retains its original
September 29 timing and limitations.

This documentation checkpoint uses exact source base
`92325effe103b638f64a944e751e31f28edf9ad0`, supplied acceptance snapshots and root's
September 29 root final-review INBOX updates. **MiniMax remains default; Codex
remains a per-chat preview. Ordinary release and the default-branch merge are pending.**
Root reported ai-harness HTTP/SSH unreachable around 23:32 UTC without a
corresponding app deployment/restart. W2 owns diagnosis; current follow-up,
reconnect and settlement are unknown. W2 also reports the ai-vm endpoint
unreachable and BMC healthy. The user reports Proxmox reachable with no changes;
no host, kernel, hypervisor or power cause is proven. W2 CLI exited at
23:40:42 UTC; worker-process exit does not establish guest-job settlement.
A later explicit root exception authorized
one TCP connect per endpoint from Mac1: both harness ports and the ai-vm SSH
port timed out at 23:41:47–23:41:56 UTC. There were no protocol requests, logins or
retries. TCP failure does not establish machine power, service health or settlement.
Exact results are in task output `MAC1-TCP-ONCE.json`.

The last supplied server activation was `74507f64` at 23:03:28 UTC; the separate
web UUID fix `79f011b3` activated at 23:17:40 UTC without a server restart and is
imported as `fcddd40` in this source base. The source base is not a claim that
that entire commit was deployed. [Compact results](h036-completion-results.json)
record exact identities, safe private-evidence names/hashes and pending gates.

## Completed cases and limits

Guarded child editing passed normal resize approval and root visual review;
job `8c9a96f6` preserved the original. Follow-up run `09b78031` in session
`96e8adbb` retrieved that same job, rendered inline/download links and survived
reload without another creative submission. Actual browser image download
passed (1,630,079 bytes; SHA256 `0eab57b0b67ea008b363858c386cb53952e61d7f7526bf77d5229e64fe234bc9`).
Fresh generation `af1324fe` / artifact `5225362b` also passed native settlement
and root visual review. These cases do not rewrite earlier failures or assert
that global qualification gates have been promoted.

Coding plus follow-up (`e5153e49`) passed actual checks and correct 0.825 W / 0.5 W
results. PDF extraction/citation and later Tesseract OCR (`acc1d636`) passed;
H035 PDF output and honest error/recovery evidence remain separate. ZIP HTTP
response/CRC passed for 2 uploads + 2 outputs, and the button was visible; browser
ZIP completion is **NOT_CONFIRMED** because only a 1,038-byte partial file was
observed. MiniMax native image transport works, but recognition is **PARTIAL**
(the lower-half-empty claim was incorrect). Codex native vision is
**UNSUPPORTED**. PDF/OCR and pixel sampling are distinct from native vision.

The secure plain-HTTP UUID fallback passed 23 focused unit and 2 actual Chromium
tests; root's normal browser Send accepted the 395,631-byte paste and completed
its first response using 407,499 input tokens. Initial paste run `d17d4942`
completed. Root reviewed `COMPACTION-INITIAL-AUDIT.json`: native compaction
completed at 23:28:57 UTC with 402,104 input / 237 output tokens, retaining all
four facts; the next complete request contained 92,320 input tokens. The browser
showed Compaction → Running and estimated context 92,544 before reload failed.
**Automatic triggering is an inference** from the ordinary UI trigger and native
source path; RAW_AUTO metadata is absent. Compaction/follow-up owner is
`346c89f0-a3f6-4668-b3ed-e6230111cf8f` in session `f006fc27`. Its final parent/tool
result and settlement are UNKNOWN. Final continuation, reconnect/history and
settlement receipts remain pending; completed compaction alone is not a full PASS.

MiMo native 480,000 readiness passed once at 23:07:48 UTC: properties and one idle
slot 480K, selection 13, exact owner/target guard and unchanged peers. About
33,503 MiB GPU allocation does not qualify occupied 480K. W2 reports the tiny native
first-turn read passed and the second tool-result turn was sent at 23:28:20 UTC;
complete continuation/settlement are **UNKNOWN**. Fresh both-engine delegation
remains **PENDING**. Profile correction `47d386` (root import `4d927fee`) is reviewed
and source-ready but **UNDEPLOYED**; it supplies protected active-frontier JSON
read-only instead of stale baked 950K. Focused source tests passed: overlay 19,
engineLauncher 21, codexLauncher 19, configure 18 / 1 existing skip, engine 86. These
are root/W2 updates, not final raw live receipts reviewed here. H033 950K workflow
receipts remain historical. No 1M/950K/full occupied 480K benchmark was repeated.

## Root finalization

- Resolve connectivity and first verify maintenance and actual owned jobs; do
  not replay uncertain work. The last browser acceptance window was OPEN; do not
  assume the scheduled 23:59:10 watcher ran through a possible reboot. Confirm the
  `f006fc27` / `346c89f0` final continuation and reload; `d17d4942` is the
  separately completed initial paste run.
- Collect exact 480K native tool/count, protected MiniMax profile delivery and
  both-engine parent/child completion receipts from W2.
- Confirm browser ZIP completion separately from the passed HTTP/CRC case.
- Review final capability descriptors, public readiness/maintenance disposition
  and default-branch merge. Global gates remain closed pending proof. Root verified
  all eight GitHub checks at `92325eff` SUCCESS and subsequently all eight at
  root candidate `4d927fee` SUCCESS (push and PR: repository-sanity,
  client-regressions, installer-fixtures, deterministic-worker-tests). The profile
  fix remains UNDEPLOYED. These are root-supplied current receipts, not checks
  for this documentation commit or any later candidate. Merge remains HELD
  for live reachability/settlement; no release or default switch is announced.

Supplied prior local verification passed 888 lifecycle tests with 2 existing skips,
5 shell suites and whitespace checks. Fixture repair `a226c5a` and exact historical
whitespace handling `92325ef` are in this base. Those checks were not rerun here;
no later GitHub outcome is inferred from that source-base result. The current snapshot
also records server 846 PASS / 4 existing skips and web 250 PASS at `74507f64`.

## Documentation handoff and preservation

FINAL-DOCS03 has a 25-minute native-task limit ending
2026-09-29T23:58:46.460854Z; this is not an H036 campaign deadline. This task
updates only current READMEs, TODO, AGENTS and these two new reports. It ran no
build, app/model/CI suite, install, inference, VM login, deployment or GitHub push.
Only documentation checks and the separately authorized one-shot TCP checks ran.
Architecture, MIT first-party versus upstream/model licenses, organizations,
scaling and update-policy TODOs are retained. Historical reports remain
byte-for-byte unchanged, including H035 promise-only failures, H036 IMAGE-FLOW02,
the original image-follow-up render failure, HTTP Send failure, stopped-timeout
migration failure and failed 950K evidence. Raw captures and prompts stay private.

Documentation checks passed: 98 local Markdown links, strict JSON, whitespace
and all 3,113 historical report files unchanged. No app/model/CI suite was run.

Task-local output contains the local commit export, SOURCE.bundle requiring
exact 92325, DOCS.patch, hashes and actual documentation-check/command receipts.
Native session `01a0ef84-66f5-7b70-980c-2261714dab62` is still running when this
report is written. Its actual exit must come from the outer wrapper's later
`WRAPPER-TERMINAL.json`; this report does not predict success or settlement.

## Root review and actual worker closure

Root reviewed and imported the profile correction as `4d927fee`, then the
current documentation as `9ce5b2f`. All eight push/PR checks for the code candidate
passed. The actual outer wrappers confirm Worker2 exited 0 at 23:40:42.346617 UTC
and Worker1 exited 0 at 23:52:33.020657 UTC. Both bounded native sessions are
closed; no paid worker is waiting for networking. These CLI exits do not establish
settlement of the disconnected VM requests. Exact receipt hashes are in the
machine-readable results.

The reviewed code and checkpoint are ready for feature-branch publication.
Default-branch merge and ordinary release remain held. The next input is the
requested Proxmox VM status, bridge and guest-agent network output. No host/VM
restart, uncertain request replay or additional model benchmark was performed.
