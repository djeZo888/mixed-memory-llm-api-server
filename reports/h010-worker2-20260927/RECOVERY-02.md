# H010 native02 recovery — PASS

Verified 2026-09-26T23:52:47.219841Z. Ordinary `systemctl --user start ai-harness.service`
ran once at 23:50:46.864561Z after actual Worker1 final release/cancel settlement.
App is enabled/active, PID 213346. Search PID 190181, status PID 187415 and admin
PID 66185 stayed active and unchanged; no unnecessary restarts.

Private `/api/health`, `/status` and `/api/status/v1/system` returned HTTP 200.
The installed canonical NodeAvailability client reported Flash, both Qwens and
service ID `image` available/allow, fresh and hardware-unlatched at 23:52:10.231Z.
Production Flash remains qualified 480000 context / 65536 output with exact pinned
frontier config, native image c328dac0 and release 296ae49. Unit/config/launcher
hashes and protected credential metadata match the quiet receipt.

All 26 sessions, 133 messages, 62 file records,48 terminal runs,19 terminal image jobs,
25,359 events and the historical quarantined workspace retained their exact table
hashes. All 17,597 included regular files retained hash
`1e262519cde8059973b23a2fc2a2838e2a15cb4429269fe18e57cc4adb906f51`.
Transient SQLite/WAL/SHM counts were excluded from equality. Existing consistent
DB backup remains untouched. No old DB restore or manual quarantine clear occurred.
Normal image reconciliation changed the shutdown lane from quarantined to idle;
ownership uncertain remained 0. Text lanes remain idle; no active native owners.

One Worker2 smoke completed: both bounded Qwen answers and one 1024x576 opaque
image PASS, three-client HTTP interval overlap 0.209 s. **Four-instance overlap
NOT_TESTED** because Worker1's original timer refused before Flash inference.
The proposed corrected launch was cancelled; Worker2 made no second requests.
Worker1's actual cancel receipt records zero Flash requests, inactive / MainPID 0
owned timer and untouched model units. See SMOKE-RESULT-02.md/json.

Initial recovery recorder FAILED after successful start: it attempted JSON
parsing on the HTML `/status` page, leaving its status field unset. The original
failed receipt and log are preserved. Read-only finalization corrected media-type
handling, verified HTTP 200 and unchanged owners/data, and passed. No second
service start was performed. The committed helper includes the parsing fix;
RECOVERY-02.json records the exact originally executed helper hash.

No ai-vm SSH/mutations, builds/downloads, runtime/cache/ECC changes, CPU trial,
native delegation repeat, subagents, production chats, pushes or product changes.
CPU-only feasibility stays accepted/unchanged. This smoke is not a new benchmark;
client timing is not native decode or GPU-kernel simultaneity. No atomic drain
claim. Fresh session 01a0e013-879f-7d33-83ce-06997cdbd56d; started 23:36:11Z,
deadline 00:06:11Z. Hosttask `/home/user/ai-harness-build/H010-WORKER2-20260927`;
original smoke PID 211845 exited 0; recovery/finalization PIDs are in the receipts.
