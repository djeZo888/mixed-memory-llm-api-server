# H031 SOURCE05 — initial-absent canonical lock correction

SOURCE-ONLY FIXTURE PASS. Supersedes REVIEWED-BUT-BLOCKED SOURCE04 owner pin
`2875de12f543ba06de36d57d06f4a8d87553765f74cd4cb69e0d7c76942a698c`
with exact owner SHA256 `8bd2a30afb25c6b7cf26904efa2fa2be9e4a2870962cf2b0ebd78b7e25a82f12`.
Base: `ce32e7a64612f68b64c4b830fe4d12df2b2668bb`.
The original SOURCE04 report is retained unchanged; its initial-absent omission
is corrected by this report. No deployment or live qualification is claimed.

Only startup_lease and its fixture changed. Missing canonical lock is allowed
only before first observation; acquire_lease alone creates it. The first observed
canonical device/inode is pinned, including immediately after refused entry.
Disappearance/replacement after observation refuses admission. Boot and deadline
checks remain. Entry-only two-second wait, single acquired body, full current
source/manifest/state/supervisor/selection/recovery revalidation and existing
five-second active guard remain unchanged. Body exceptions are never retried.

Validation: 62 focused cases PASS: exact 61 cases listed in SOURCE04 TESTS.log
and COMPATIBILITY-TESTS.log plus one initially absent startup case. The new fixture
does not initialize the lock or its parent directories: actual canonical acquire
creates them, actual supervise reaches the first ownership write boundary once,
and predecessor/recovery evidence remains unconsumed. It independently passes
in INITIAL-ABSENT.log. The exact SOURCE04 startup_lease fails that same fixture
with FileNotFoundError (BASELINE-FAIL.log). First invocation without PYTHONPATH
failed import; all retained test runs use PYTHONPATH=scripts. Read-only independent
review confirmed the narrow correction and fixture design.

Historical competing holder/throw site and separately pinned deployed PREP bytes
remain unverified. Source fixtures mock installed storage/systemd/GPU/Docker
boundaries and do not establish live behavior. No VM, harness, SSH, model/image,
deployment, configuration or capability operation occurred. Root review and
separate activation authorization remain necessary. Bundle includes SOURCE04
ancestry plus this correction, with prerequisite
`711b24e283c16b61067621de39b796a8657ee309`.
