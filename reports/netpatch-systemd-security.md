# NETPATCH source-ready handoff — 2026-09-17

Base: `9650512a25052dcd170ec0ac4fb27cb9e3cb4419`.
Ref: `refs/heads/milestone/netpatch-systemd-security`.

The installed helper accepts only canonical `255.4-1ubuntu8.N`, ASCII decimal
`N >= 16`, replacing the `.16` equality that Worker1 reported blocked startup
after an unattended update to `.17`. Full matching rejects whitespace, leading
zeros, downgrades, other upstream/distro/Ubuntu bases and extra suffixes.
The package query, fixed binary, six units, protected file reads, ownership
receipt and firewall checks are unchanged.

Focused worker checks ran once and passed:

- `python3 -B -m unittest discover -s tests -p 'test_private_network*.py' -v`:
  37 tests, including real `_installation()` fixtures for `.16`, `.17`, synthetic
  future patches through `.100`, and rejected versions/malformed strings.
- `python3 -B scripts/control/private_network.py source-check`: fixed policy
  and six exact units passed; systemd runtime NOT_TESTED.
- `python3 -B scripts/control/private_network.py --help`: exit 0.

New `scripts/control/private_network.py` SHA256 for final composition:
`9ca8ca4b86dbf04988bfe2f8f0a7b3748bbe5d1922c0543f081616f37ec1a6af`.
Q38FIN retains ownership of shared inventories, including
`reports/l2-source-closure-sha256.json`; NETPATCH did not edit them. Final
composition must refresh the helper digest and review the existing protected
ownership receipt without bypassing source-signature checks.

This is source acceptance of the requested security-update family. No Ubuntu
package, future patch, systemd runtime, private API or updated-host startup was
live-tested here. Worker1 host acceptance remains pending. No SSH, service
mutation, installer tests/work, frontend/model work or push was performed.
The incremental bundle and `result.json` beside the checkout record the final
commit, verification, digests and clean status.
