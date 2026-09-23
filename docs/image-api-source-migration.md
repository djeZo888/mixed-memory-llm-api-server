# IMAGE21 source/receipt migration proposal

This is a root-review handoff, not a production receipt or activation command.
Base `b39781d83404799c6fa9262fd94adb09b0995ec8`; final source commit and complete
hash maps are in the taskroot RESULT.md / SOURCE-MIGRATION.json package.

## Exact changed closure

| Control recovery file | Base SHA256 | Proposed SHA256 |
|---|---|---|
| `scripts/control/private_network.py` | `9ca8ca4b86dbf04988bfe2f8f0a7b3748bbe5d1922c0543f081616f37ec1a6af` | `d7b82c296fb94846ea9825c1f38d1892b67a8b853279f7e01f807668ea2e9b33` |

`source-closure.json` and `control/installation.py` stay unchanged; their exact
protection lists still cover the changed helper. No adapter module is imported
by control. The same helper is installed separately at
`/usr/local/lib/llm-server/private-network/private_network.py` and in the control
source tree `/usr/local/lib/llm-server/control-api/scripts/control/private_network.py`.
Both copies must match reviewed new bytes. No fallback, missing-hash tolerance,
receipt rewrite or historical evidence edit is introduced.

The fixed network policy changes only by adding image:30006. Its SHA256 changes
from `095bbf0ea64c792efa49ddf16a78383ec74528abe605c86b54ba8ac01563cb60`
to `eb04d179cd6c9af896dfc1809e7804ef533c9e52fd356da9ecc0d4907bd3c064`.
All six existing private control/GLM/Qwen socket/service files are byte-identical.
Two new image units enter the exact installation signature. Existing interface,
address, subnet, rule chain/tag, terminal deny, owned inverse, package validation
and TLS/private policy are unchanged. Backend30007 never enters the private ports.

The concurrent acceptance `source_identity()` map (28 files) is
byte-for-byte unchanged from this base: it does not include private_network.py.
Preserve those accepted text-capacity receipts byte-for-byte. This is a source
comparison, not a claim about any current installed VM receipt or running state.
Any wider installed root source closure still needs its explicit reviewed amendment.

## Worker1 migration after root review

1. Under the existing authorized VM mutation ownership/canonical lifecycle lease
   and current installed registered storage/root-disk guards, record exact installed
   source/receipt/unit identities, effective firewall and listener state. Compare
   with the actual root-reviewed predecessor (if it differs from this base, stop
   and request a reviewed delta; never force this proposal onto mismatching state).
2. Preserve old source and all receipts, including the exact
   `/etc/llm-server/private-network-state.json` and `before_filter`, in the current
   guarded evidence location. Stop/disable the old private sockets and stop their
   proxy services using the reviewed old source, so no listener becomes reachable
   without its rules. Text backend services/profiles/weights need no source change.
3. Use the exact OLD installed helper's stopped-unit inverse, with its matching old
   policy/units/receipt, to remove only its owned chain/jump. Verify unrelated INPUT
   rules and all other chains remain unchanged. It retains its old state receipt.
   Only after verifying and preserving that receipt may a root-reviewed transaction
   retire that exact old active state file; never edit its signature in place.
4. Stop the control service for its protected source migration as required by the
   actual installed closure. Install the reviewed helper in both locations, fixed
   policy and eight exact unit files. Preserve old units unchanged. Publish a NEW
   root source review/amendment with final source SHA and the helper/policy hashes,
   preserving prior source, deployment and text-capacity receipts as evidence.
   Reload systemd and verify no effective or pending unit overrides.
5. New helper preflight/dry-run/apply must create a NEW matching state receipt from
   verified rules without the owned chain; its source/receipt equality remains exact.
   Verify its first INPUT jump covers30000/30002/30004/30006 and no30007, ordered
   loopback/LAN allowances and finalDROP. Never run new apply against a stale old
   signature or make an old signature appear new by editing the receipt.
6. Independently finish image helper/runtime/credential/storage/cleanup/profile
   qualification. Render the nondeployable adapter/sudo templates using reviewed
   real identities; validate Linux effective sudo/confinement. Enable image exposure
   only after adapter startup proves exact backend replacement/warmup and reviewed
   profiles. Restore existing control/text proxies and independently verify their
   authenticated old endpoints, preserved native listeners and private policy.
7. Archive new source/policy/unit/receipt/firewall evidence under guarded data,
   link old and new immutable receipts and source SHAs. Independent client image
   acceptance follows root review; rollback uses the preserved old source/receipt
   with the corresponding stopped-unit inverse and a separately reviewed sequence.

This source task performed none of these VM actions. Plain private HTTP retains
its existing policy and does not acquire TLS confidentiality from an added proxy.
Actual root/Worker1 deployment, native cleanup and Linux acceptance remain open.
