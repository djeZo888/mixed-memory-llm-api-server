# Shared fixtures

Exact copies of Worker1-owned `tests/fixtures/service_resilience/` v1 fixtures,
delivered by root in H005 task parent `contract-fixtures/` on 2026-09-25.
Root-frozen amendments and the current task inbox govern; node endpoint uses
private port **30008**, superseding the early proposal's 30000. Do not fork
these fixtures to conceal a producer/consumer mismatch.

Root-delivered additive `disk-volumes-v1.json` is copied exactly, SHA256
`723de2ecfde1d62d1c2a7b95277302ba2b9c81a0736caa19b0c76d9a222c1e4a`.
The adjacent original `CONTRACT-AMENDMENT.md` records disk entry semantics and
the authoritative `hardware_latched_boot_id` field; the original startup fixture
was not amended by Worker1, so no local edit is made to that historical fixture.
