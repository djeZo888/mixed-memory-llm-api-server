# Shared fixtures

Exact copies of Worker1-owned `tests/fixtures/service_resilience/` v1 fixtures,
delivered by root in H005 task parent `contract-fixtures/` on 2026-09-25.
Root-frozen amendments and the current task inbox govern; node endpoint uses
private port **30008**, superseding the early proposal's 30000. Do not fork
these fixtures to conceal a producer/consumer mismatch.

Root-delivered additive `disk-volumes-v1.json` is copied exactly, SHA256
`723de2ecfde1d62d1c2a7b95277302ba2b9c81a0736caa19b0c76d9a222c1e4a`.
The adjacent original `CONTRACT-AMENDMENT.md` records disk entry semantics and
the authoritative `hardware_latched_boot_id` field. The current root-delivered
Worker1 fixtures replace the original startup snapshot with the producer amendment.
`LATCH-SEMANTICS.md` and `service-resilience-contract.md` are exact delivered
source-contract copies. Fresh `hardware_latched:false` proves current-boot
validation of every exact required UUID independently of global inventory.
Consumers retain same-boot latches and missing-provenance protection; clearing an
inherited latch additionally requires unchanged UUID requirements and durable
ledger commit. These contracts remain source-only pending root activation review.

Canonical stop/restart settlement source proof: `CANONICAL-SUCCESS.md`, copied
byte-for-byte from parent contract-fixtures; Worker1 commit `109d3b4`, 459 focused
offline tests as recorded there. Root combined exact-source review remains pending;
this is no deployment/live acceptance claim and changes no NodeOperation wire.
