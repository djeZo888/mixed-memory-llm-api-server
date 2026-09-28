# H019 HARNESS PREP01 handoff

Prepared for root review; **no deployment, image build, model request or app
acceptance**. The original Sova pair is normally paused. Native 950K/full17
qualification remains a future W1 action. Only ai-harness was contacted.

## Actual preservation

The ordinary app stop returned at 02:17:56 UTC on September 28. Release
`7143c17d73173db9364b77956679c86d7026a4ae` and image
`9ef88598cf54a03aa259c5aa2d2878b34b7473cfcec7c8c07cee6ba462c39f1c`
remain installed unchanged; MainPID 0, inactive/dead, enabled. Search, status
and admin retain their prior PIDs and active states. No owned engine container,
active run, frontier request or image job remained; image uncertainty is zero.
This is app-side ownership evidence, not an atomic native GPU-idle claim.

Protected histories match the recovered baseline:26 sessions, 133 messages,
62 file records, 48 terminal runs, 25,359 events, 19 terminal image jobs and 1 workspace
quarantine. The normal pause changed only the image-lane state from idle to
quarantined; no quarantine was manually cleared. All 17,597 non-DB files had
unchanged metadata across the pause and no mtime/ctime newer than the prior
full hash pass, whose digest remains `1e262519cde8059973b23a2fc2a2838e2a15cb4429269fe18e57cc4adb906f51`.
No redundant full content rehash was performed. Raw per-file metadata and
before/after receipts stay in the VM task's private directory; sanitized
evidence is in QUIET.json. Credentials were stat-checked, never read, and
owner.sqlite was never opened. All old receipts remain unchanged.

## Prepared source and clients

Source commit `34959c67baea0d8a357cbea4cefac1658f3553f0` is staged at
`/home/user/ai-harness-build/H019-HARNESS-PREP01-20260928`. The 513-entry
source manifest is SHA256 `c0b0bd6f4dee02b7c54f96eac2706d1af58dfd3eea595e80ecfa8fd180a632ba`.
It reuses 446 source entries from H018 source 3760c615 plus the explicit 5b6f933
clock overlay, with 33 H019 overlay files and their source mirrors. All 445 code
and other retained entries match the current checkout; the only different
entry is an older historical H018 report, retained with its original digest.
The old 479-entry stage and manifest ad0a8b84 remain untouched.

The 20 acceptance/build helper copies include 11 byte-identical files and 9 narrow
task/release/clock/context adaptations. The existing actual Qwen-parent ->
MiMo-child tool/result -> Qwen-verification driver, full17 roster and guarded
settlement remain unchanged. H019 accepts only 950000 usable context; historical
1M proof and 950016 physical padding cannot satisfy it. Main Qwen 480K,
maxgeneration 65536, separate queues and the retained 511-minute transport
budget remain intact. Parent-wait behavior is retained, not newly qualified.

Five clock fixtures, three capacity/admission/owner-refusal fixtures and 18
helper syntax checks passed. Preservation/staging Python AST checks also
passed. No broad historical tests, package fixture, native/dependency build,
download or runtime tuning was repeated. A shortened source ID was initially
refused before stage mutation; the exact 40-character commit then staged once.

## Fresh-session continuation

The build procedure reuses image 46feffff, host 6c4b5869 and the 44-file compiled
payload 0d34ca65. It will make only the two-file image layer and three-file host
overlay after current authentic qualification and root review. No new image
ID, paired deployment or protected qualification was produced in PREP01.

Keep SOURCE-COMMIT 34959c67 as the staged artifact identity when calling the
existing build/activate helpers; later report-only commits do not alter those
bytes. Exact receipt/image/unit/driver hashes must agree before the existing
acceptance launcher can run. Use a fresh bounded native session after root GO;
do not reopen or replay an ambiguous acceptance attempt.

Application stop is 03:49:30 UTC and hard settlement 03:50:00 UTC. The theoretical
post-preflight admission limit is 03:34:30; both actual preflights consume that
budget. Bounds remain 720 s minimum work, 1200 s maximum work, 180 s cleanup,
1380 s supervisor and 30 s stop grace. Aim for app result 03:40. Latest root steering
allows W1's direct near950K/eight-hour background test after native17/production
acceptance even if an app-only issue leaves Sova paused. Skip 64K. Automation
stays paused; keep MiMo selected at the overall 04:10:29 deadline and do not
automatically restore GLM. Hardware/resource faults still require safe stop.

Native session `01a0e5cb-2069-7661-b178-7c7ac500a191` has effective deadline
02:39:49.099570 UTC. Root EARLY/PROGRESS/QUIET/READY and BACKEND-REVIEW receipts
are outside the checkout. The wrapper records actual native exit after this
handoff. No push was made; root reviews/synchronizes/publishes.

## Backend review disposition

Exact early owner `57ace7da` passes the new nested-lease source review: 11
supplied latch tests and 3 independent delta fixtures pass. It borrows and
validates the existing canonical lease without reacquiring/replacing it;
positive-fault retention, freshness and five-second failure guards remain.
The previously reviewed cf558 periodic hardware-policy fix was not retested.
See backend-review/REVIEW.json for complete pins and focused evidence.

The early final950K adapter still requires Sova PASS and must be corrected to
match the latest native17+production authority before dispatch. The separate
periodic owner/short-client writer delta and final imported/deployment closure
were not supplied for completed review. Root directed closing this first
session without waiting; a fresh session will review those exact later bytes.
Owner-source PASS does not approve those pending artifacts or a live load.
