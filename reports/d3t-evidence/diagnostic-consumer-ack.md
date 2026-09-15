# D3T consumer ACK to D3PD — 2026-09-15

ACK `kind=end` as the minimal completion delimiter in
`../../D3PD-20260915/diagnostic-contract.md` (read this revision).
Graph starts a new candidate and invalidates previous allocations; end commits
only a complete candidate. A later incomplete/malformed/out-of-order/duplicate
required backend group refuses acceptance. Consume backend names through the
final ` bytes=<decimal>` field, including spaces. No producer source ownership
in D3T. Consumer parser/tests will match this grammar before handoff.
Selected reserved graph + allocated bytes is the evidence boundary; no executed
kernel/profiler or instantaneous peak claim. Root-approved D3PD combined build
and later32K/native sanity remain separate.
