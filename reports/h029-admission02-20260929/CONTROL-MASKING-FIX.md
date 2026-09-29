# Separately authorized targeted-error correction — source only

Root INBOX 02:36 UTC authorized this correction after TypeScript commit
`7f433726b12987cea96ee290d07b6f11040d1fe2` and its bundle were exported.

Six lines in `scripts/control/core.py`: if a targeted observation fails and
recovery cannot provide a snapshot, raise the original safely projected
ControlError before constructing a singleton fallback. Existing router status
normalization remains. A refresh `stale_state`/`lifecycle_busy`409 or
`deadline_exceeded`503 therefore reaches its caller unchanged. Unknown exception
text becomes `observation_unavailable`; neither text nor arbitrary codes escape.

Whole-status fallback, successful recovery, valid single-owner409
`target_unavailable` and unknown-route404 remain unchanged. No guard, identity,
lease/CAS, TTL/freshness, readiness, capacity, ownership, retry or timeout changes.
This repairs the separately demonstrated masking defect; historical Codex
transport cause is still UNKNOWN. Original evidence stays preserved.

PASS24 focused tests: `PYTHONPATH=tests:scripts python3 -m unittest
 test_control_targeted_errors test_control_refresh test_control_slots`.
Four new cases cover targeted error preservation/no publication/no retry,
whole-status fallback, untrusted error/status projection and genuine route
errors. Independent read-only source review PASS; no blocker.

Not deployed; no live control call/restart was performed for this correction.
Core SHA256 becomes `5a2fef84e4dd77c9c6101a183ef1904b2a47dca244d24a7794938e334ca4150c`.
A future ai-vm deployment requires root's reviewed protected source-closure and
receipt-successor procedure across installed roots, plus an explicit lifecycle
gap. No source receipt/policy/adapter pin was changed here; preserve all existing
receipt predecessors. This Python patch is independent of W2's harness-only
TypeScript release. Worker1 must not restart control while W2 owns acceptance.
