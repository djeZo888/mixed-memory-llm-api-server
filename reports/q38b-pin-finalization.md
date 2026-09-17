# Q38B original provenance finalization trace

**Confirmed source defect, corrected in `6c10334031f9b6d756231df27ec420b0a0b6d5e0`.**
The original Q38S `622d1262f6489cdb0c9c8acbe9eee92b737868e3` and reviewed
`6cffccbf1927ff610c21cfc6a0bea3b2f14bd85a` both store fixture provenance SHA256
`e82d8e9e83972599594aacc35193290d5ffad096641c6e6c35878fd140ba3910`.
Their adapter instead expects
`1210f1006a557aba43bf20117b56246ef01c64b89ff4ddc597c40ff1c6d26d2d`.
The original happy-path receipt test fails with
`qwen38_source_profile_pin_mismatch` on those final committed bytes.

## Exact cause, UTC on 2026-09-15

1. Q38S root session `01a0a280-009e-79d1-8520-f45a738f6a49` refreshed
   `PROFILE_HASHES` and reported 81 focused passes at **00:52:09.119**;
   its 282 lifecycle passes completed at **00:52:24.762**.
2. Fixture subagent session `01a0a280-a2bd-7d63-a750-73993d356686`
   then added a second `validate_output_path(output)` immediately before
   `unchanged()` in `write_receipt`, at **00:52:33.266**. The extra check is a
   legitimate final safety correction and is retained.
3. At **00:52:33.461**, that subagent rehashed the fixture manifest and ran
   only `test_qwen38_image_fixture.py`: **17 PASS**. It did not update the
   parent adapter's pin or rerun its receipt happy path. The parent later
   committed the changed provenance with its stale adapter pin.
4. Exact reconstruction proves the relationship: removing only that inserted
   line from the original committed runner gives runner SHA256
   `37328cc33b81414cbd058d730f4428c47d45798d8e1a0fb17170055485f0ee1d`.
   Substituting only this runner hash into the original sorted/indented
   provenance produces **exactly** `1210f100...`. The final runner is
   `84d016aafa3c6544d879afc30abd67bfa68419fac334712c91cc39f43d76894b`,
   whose final provenance is **exactly** `e82d8e9e...`.

Evidence was read from original taskroot `Q38S/events.jsonl` (completed items
61, 63, 74, 82, 87), the two original session records above (root records
315/329; fixture records 285/287), and original Git blobs. Historical reports
are preserved as historical claims: the 81/282 passes were real earlier-tree
results, **not final committed-source verification**.

## Correction and lasting check

The first correction intentionally changed only the adapter's provenance pin
to the reviewed final `e82d8e9e...`; it did not rewrite provenance or regenerate
unrelated hashes. It passed both the receipt happy path and an actual-byte
provenance drift rejection from an exported Git archive at commit `6c103340`.

Subsequent Q38B fixture/cache/OCI changes necessarily require their explicitly
reviewed downstream pins to change again. The dependency direction is fixture
and launcher/support sources -> provenance -> adapter pin. Provenance never
hashes itself or the adapter. No cycle or runtime pin regeneration is allowed.

Run after the final source commit and again on the bundle-imported final head:

```sh
python3 tests/lifecycle/verify_qwen38_git_source.py --commit HEAD
```

This exports committed bytes with `git archive`, exercises the real receipt
happy path and appends a byte to a temporary provenance copy to require
rejection. It neither mocks the expected pin nor writes a production receipt.
Actual image and live execution remain **NOT_TESTED**.
