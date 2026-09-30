# H032 ACTIVATE01 — activation handoff

Observed 2026-09-29T11:54:16.423844+00:00. Native worker `01a0ecfd-8a08-7c10-acfc-7193a7dfe8e0` on mac-worker1. **No more lifecycle writes.**

MiMo was admitted after the exact reviewed source-owner amendment and is **LOADING** under independent systemd ownership. Image exact cleanup settled, but activation **FAILED CLOSED** after source/config promotion. API remains stopped. This is not a readiness or release claim.

## MiMo

- Protected package readback, original raw pins, PREP03c0933 and current-boot checks passed. W1 held a no-start interval from prepare through exact install and activation. Immediate preinstall recheck confirmed stopped/empty unit, unchanged source/state/selection and unconsumed original receipt.
- Prepare command 11:49:59.034–11:50:00.142 UTC, exit0. Immutable predecessor source/manifest backed up. Exact owner2406d9a0 and manifest059d289e installed11:50:15 UTC; activation and one normal start completed11:50:16 UTC, exit0.
- Amendment SHA256 `1e8beefbaa7ae97ebc7aee156ea0903cd3b4d23a77ab1c0095b7bcf76cc6ab22`. Original consumed filename and its complete identity are in RESULT.json; consumed SHA256 `9b01b664b04a40fe156e7a90d86e4333b0755e76691b61a19b02603f60aa1d91`.
- Owner PID531588 / invocation57777f7b609144678201b2171020b513. Successor launch `e5984f1e7e08434c89a7367a07b048fa`, native `c1254995061955ceb7bf0474602c1854a3645f42a67f22a912094f6fa6fbe162`, PID533410, native started11:50:19.046377739 UTC. LOADING observed11:54:16 UTC. No second stop/start and no inference.
- Earliest useful later readiness observation: approximately **12:02 UTC**, based on the supplied ~11-minute load estimate; not a readiness guarantee. This session does not wait for it.

## Image failed boundary

- Exact final GO tuple verified against 13 package entries, source hashes and INBOX. API fresh closed/not busy/not admitting, full source maps matched, owned unit jobs absent. Normal stop of API only11:52:23 UTC, exit0; API/backend unit PID, cgroup and jobs empty, old owner PIDs absent.
- Four exclusive reviewed leaves staged11:52:36 UTC. Helper invoked exactly once11:52:50.736–11:53:01.816 UTC, exit1. No backend or API successor start occurred.
- Immutable archive includes old records/source/config, native inspect/generation, actual bind-mounted backend log, generation request/response/summary/perf/PNG, telemetry, original failure receipts and journals. Docker log policy none preserved; no Docker log stream used.
- Cleanup intent consumed, exact old native stopped/removed once. Immutable physical settlement SHA256 `49b43a55cf83539dc19137a4d22b39219d2ebb997b46695123a1c04321d0843c`. Final proof: fixed old ID/name absent, PID/cgroup absent, target image GPU compute empty, port30007 empty. Existing public socket proxy on30006 remains; API unit is inactive/dead with empty cgroup.
- Both exact new service6b7ac0a1 and configa3ca37b0 bytes are installed. Their mtimes are recorded in RESULT.json. **Both mode0400, uid0/gid1001**. Full content source maps match.
- Attempt `32a3ea39cefa48a598ca64c2ef2e6427` failed `registered_storage_refused` at `reconcile_install`, detail `unsafe_storage_json`. Source cause independently confirmed: helper immutable() creates0400; install promotes it using replace; registered JSON reader requires exact0600. No source fix or metadata change was attempted here.
- Recovery remains ACTIVE, phase `settled_awaiting_reviewed_activation`, cleanup token6b0b598ef83b4a39977cb1d508c7cbda, old config digest retained. Helper PID586481 is absent. Handoff and consumed handoff are absent. Historical original failures remain archived. No retry, clearing, rollback or API restart.
- Further work requires review of this exact partial activation and a separately authorized continuation; do not replay helper or old warm.

## Evidence and bounds

27 total input SHA256SUMS entries and all final source leaves matched. Three Qwen container identities mechanically match the supplied immutable baseline. Nine historic MiMo files still match original pins. No runtime/weights/context/profile/hardware/fan/power/ECC or app/capability changes were performed.

Raw evidence stays in private task output. Exact exported VM archive contains57 files, SHA256 `34585550975d550d68595548974f6ca5157a4b71acc406af6a132649336f7ac3`. Each VM command has a UTC/exit/hash receipt. Failed readback scripts06/07 used an incorrect image-config key and made no mutations; corrected readback08 passed. A local stage metadata assertion expected gid0/0700 but observed inherited gid1001/setgid2700; root ownership/no group or other write permissions and all staged hashes met the helper protection contract. The shell proceeded to the sole authorized helper invocation after that local assertion; no duplicate invocation occurred. This local check defect is retained in the execution trace.

All SSH commands returned; no worker-owned background command remains. Native CLI wrapper exit is recorded by the coordinator after this final return. Public maintenance and specialist/candidate gates remain unchanged. No tests beyond mechanical validation, no readiness wait and no GitHub push.
