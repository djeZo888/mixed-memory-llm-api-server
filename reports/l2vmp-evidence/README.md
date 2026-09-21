# L2VMP report evidence

Report-only copies of task-root artifacts; no configuration/source installed or changed. Main report is `../l2vmp-existing-host-activation-plan.md`; its sibling artifact references resolve within this evidence directory in the bundle and at task root in the external deliverable. `proposed/` JSON/unit/diffs are review payloads, not installed state or executable apply authorization.

- `host-inventory.json`: sanitized one-session host snapshot; two focused followups complete selected immutable fields and current-source paths.
- `adoption-verification.json`: worker-only actual Manager identity/reuse validators plus a context-mismatch negative check. Excludes real storage, keys, network guard, readiness, final L2 integration.
- `worker-verification.json`: proposal JSON/stable identity/observed mount/manifest/unit consistency.
- `q38-receipt-mapping-verification.json`: all81 actual Q38A sealed digest tuples mapped on worker; source evidence hash fixed, no current live stat check or receipt publication.
- `control-source-baseline.json`: hashes of inspected base source, never a final L2 install manifest.
- `l2-handshake.md`, `transport-contract.md`, `VM-GUARDS.json`: exact latest consumed coordination contracts, source ownership preserved.

Reproduction on original worker task layout: `python3 -B ../verify-adoption.py` and `python3 -B ../verify-plan.py`. Text copies of those scripts and read-only inventory probes are retained here solely as audit evidence; no probes should be rerun on a VM without task authorization. No tests or script implementations were added to production paths. Proposed receipt verification additionally compares the Q38A committed `reports/q38a-sealed-evidence.json` SHA256 a9b1ee9c80ca7030b79387b64f63d494159d0db7966f6510737e20c568584cfe, all81 exact rows, root0444/single-link recorded stats and full expected manifest equality. This is source evidence validation, not a new payload hash.

No key bytes/hashes or full Docker environment were read or included. Raw state/instance originals remain on VM; evidence contains selected safe fields and nonsecret byte hashes. Future rollback must capture raw originals under the explicit approved transaction, not reconstruct them from projections.
