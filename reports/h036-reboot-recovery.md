# H036 reboot recovery — hardware maintenance checkpoint

Historical checkpoint at 02:48 UTC, September 30, 2026. The later [resumed recovery report](h036-resumed-recovery.md) supersedes the current-state and pending-work statements below. This record supplements the [earlier completion checkpoint](h036-completion-checkpoint.md) and retains its original test outcomes.

## Current hardware and service state

The supplied Proxmox records establish an unclean host restart. The first recorded SSH failure was September 30 at 01:31:38 Ljubljana time; the new host boot began at 01:41:48. The supplied logs do not establish why the host restarted. Corrected PCIe errors on the external Ada path are a separate observed fault, not a proven reboot cause.

Both VMs returned after the user started them. Worker1's bounded inventory found all five GPUs visible at 29–38 °C, three Qwen instances and the image runtime running. MiMo's old native container had exited, while its persistent owner still said RUNNING. Worker2 restored the existing public maintenance response and preserved the interrupted chats, files and request records.

For the user's USB4 cable comparison, Worker1 issued exactly one graceful ai-vm poweroff at **02:05:46 UTC / 04:05:46 Ljubljana**. It returned zero; two later bounded SSH checks timed out. Classification: **shutdown accepted, SSH unreachable**. Hypervisor `stopped` status requires the user's `qm status 120` confirmation. ai-harness was not shut down. No VM probes, deployment, model loads or inference are authorized during the cable trial until the user reports it complete.

The supplied Core X link reports 20 Gb/s per lane with two lanes in each direction: a negotiated 40 Gb/s link. The bridge's sampled PCIe 2.5 GT/s ×4 state may be an idle power state and is not a throughput measurement. Its 3,911 BadDLLP and four BadTLP counts are cumulative; the supplied last-five-minute journal query was empty. Compare new errors with the same port and comparable activity for each cable. Actual CPU/GPU transfer throughput remains untested in this recovery window.

## Reviewed source repairs — not deployed

| Change | Source validation | Limitation |
|---|---|---|
| SearXNG unit invokes its existing owned-container stop helper before startup | Nine synthetic Podman cases pass; shell syntax and whitespace pass | Real cold-start recovery is pending. Foreign containers and cleanup failures still block startup. No image rebuild is required for this unit change. |
| MiMo explicitly reconciles the supported interrupted owner from an older boot | Included in 303 passing focused/adjacent tests, with five existing skips | Requires fresh boot and physical-absence proof. Original request remains `FAILED_OR_UNKNOWN`; it is never replayed or marked successful. |
| Ada writes status atomically using existing protected storage | Same focused/adjacent validation includes stale temporary files, contention and finalization failures | Preserves the old `status.new`. Busy periodic telemetry is deferred; failed cleanup or terminal persistence produces a failure exit. |
| Protected offline recovery for one interrupted Codex chat | 148 TypeScript cases, 29 Python settlement cases and TypeScript build pass | Requires stopped application, protected physical-release evidence and an unchanged database snapshot. Full server suite and live execution remain pending. |

SearXNG source is imported as `54f35f756f0b08f2ffae3d68f03e695249bd46b6`; MiMo/Ada source as `7822ebf` from worker commit `2aeb870cf373c89e36d3acabfd8fbe83f00a7499`. These are source validation results, not live recovery evidence. Worker1's source session exited zero at 02:30:52 UTC, within its 35-minute cap. Its deployment proposal needs further review: the Ada observer pin is also in MiMo's source manifest, and delivery should avoid an unnecessary MiMo load/stop/reload solely to change that pin.

Interrupted-chat recovery is imported as `f1f3a98` from worker commit `391001241a7df16e5d7a485db72453a497cc6073`. Root reviewed the transaction, original-record preservation, exact request binding and final corrections for systemd's raw InvocationID and unresolved-only gateway loading. Worker2's native session exited zero at **02:43:13 UTC**, before its 02:58:23 deadline. No additional worker task was opened after it exited. The full server suite was requested after closure and remains explicitly **NOT_RUN** for this candidate; GitHub's existing checks do not substitute for that suite.

No live ownership record has been cleared. The two older uncertain owners and three older quarantines remain separate from the new interrupted compaction case. Both native worker sessions are closed. [Machine-readable recovery results](h036-reboot-recovery-results.json) retain source identities, test scope and actual exit receipts.

## Recovered acceptance evidence

- Qwen's original automatic compaction completed before the outage: 402,104 input tokens and a 237-token summary retaining all four facts. Automatic triggering remains inferred from the ordinary UI/source path; raw automatic-trigger metadata was not present.
- The subsequent Python tool completed and wrote the original 98-byte `retained-power.txt`, including the correct 0.825 W result. Its SHA256 is `4ab33d8f0b84d81ab152e8fe50172f66e9c3602595e2fe6b16b3d8beda754a11`.
- A later provider request was interrupted by the host outage. There is no final parent answer or normal artifact-registration proof for that original run. The file's existence does not establish that the whole turn completed.
- MiMo's first tiny 480K-profile tool turn completed; the tool-result continuation has no final receipt. Do not relabel the old 950K qualification as a new 480K result.
- Previously passed image generation/edit/follow-up, coding and PDF/OCR cases are retained. Browser ZIP completion, fresh 480K delegation and final reconnect/continuation remain pending. Codex native vision remains unsupported; MiniMax image recognition was partial.

## Next work after hardware returns

1. Obtain fresh VM/boot/GPU and maintenance evidence, then review one coherent cold-state deployment sequence. Preserve the original failed states and exact source pins.
2. Deploy reviewed recovery fixes and confirm actual native/container settlement. Do not infer settlement from a worker exit, expired ticket or missing SSH connection.
3. Perform a distinct short MiMo 480K qualification and deliver its protected profile to both harnesses. Do not repeat the large compaction paste or any 950K benchmark.
4. Reconcile only the selected interrupted chat with fresh physical proof, then submit a new distinct follow-up using its retained history/files. Preserve the original interrupted outcome.
5. Run the full server regression suite on the integrated candidate, complete browser ZIP/reconnect checks, review capability/readiness descriptions and exact-candidate CI, then publish the qualified release and merge to the actual default branch, `main`.

Credentials, prompts and bulky traces remain outside Git. This checkpoint does not authorize hardware changes, force cleanup, replay of uncertain work or deployment during the cable trial.
