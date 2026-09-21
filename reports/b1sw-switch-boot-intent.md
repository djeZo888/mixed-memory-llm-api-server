# B1SW — preserve boot intent during API switching

**PASS: bounded worker source/fixture checks. Live application and reboot NOT_TESTED.**

Base `0b5f6160c46bf8a79de9daf4ecf87cb33bccd921`, branch
`milestone/b1sw-switch-boot-intent`, Mac-Worker2. Approved plan and boundary
incoming notes followed; no rebase, ai-vm contact, installer/frontend work or
changes to other owners' runtime/profile/monitor sources.

## Change

`ManagerSession.select()` validates the existing borrowed canonical lease, reads
current trusted Manager state inside its bounded call, validates exact string
`manual`/`resume`, and explicitly forwards that policy to `Manager.dispatch`.
It does not use constructor state, a cached observation or a request field.
Existing failure handling refuses unreadable/invalid state. Preflight remains
before old-backend stop, and one canonical owner spans the entire transition.

Ordinary switching preserves either preference and deliberately starts the
chosen model. Explicit API stop persists stopped/resume independently; service
reopen and boot-start do not start it. CLI/default selection, deactivate,
boot-stop, recovery and volatile persistence behavior are unchanged.

Only the adapter entry in `l2-source-closure-sha256.json` was mechanically
refreshed. Historical live inventories and Q38FIX-owned hashes were preserved.
All pre-existing source modes remain unchanged.

## Focused verification

31 checks PASS, zero failures/errors/skips: all 22 `test_control_production`
checks and these nine existing `test_manager.ManagerTests` checks:

- `test_select_records_intentionally_stopped_manual_intent`
- `test_deactivate_keeps_stopped_tombstone_and_never_resurrects`
- `test_resume_selection_alone_does_not_boot_start`
- `test_manual_policy_does_not_resume_after_boot_stop`
- `test_resume_policy_replays_running_intent_after_boot_stop`
- `test_explicit_stop_disables_resume_even_with_resume_policy`
- `test_recover_stop_uses_trusted_identity_despite_corrupt_primary`
- `test_emergency_stop_journal_overrides_stale_running_intent`
- `test_stop_continues_when_both_state_journals_cannot_be_written`

Production tests exercise actual Manager/adapter, real worker HTTP/flock and
temporary anchored fixture storage with controlled Docker/probe/host effects.
The former intentional-manual switch assertion now verifies resume/running and
exactly one selected-container start across repeated boot-start. Added coverage
includes manual no-resume, durable stop/reopen/later switch, stale cached state
in both policy directions, invalid/unreadable state, wrong/stale leases, expired
deadline, and unchanged preflight/CAS/idempotency rejection intent. Existing
no-storage recovery and one-active-owner checks remain.

Exact runner, per-run logs/results, session, independent review, full bundle,
commit/import checks and final handoff are preserved outside Git in the B1SW
task directory. Final VM owner must independently review, compose disjoint
manifest entries, and stage matching protected control/normal/boot closures
later. No VM apply, unit enabling, real Docker/model execution or actual reboot
was performed or established by this source task.
