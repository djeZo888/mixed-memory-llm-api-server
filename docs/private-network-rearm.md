# H028 private transport recovery and Ada extension

The enabled timer observes 45 seconds after boot, then 60 seconds after the
previous recovery run becomes inactive. Each run permits four attempts with
delays0,5,15,30 seconds, a90-second helper budget and120-second systemd timeout.
One oneshot service prevents overlapping timer runs. Healthy sockets require
only state reads; no model recovery or upstream start is performed.

All seven fixed roles are covered: control30000, GLM30002, Qwen30004, image30006,
node30008, frontier30010 and dedicated Ada200K30014. Only enabled or runtime-enabled
inactive/failed sockets can be rearmed. A second state read respects operator
disable. Active sockets are not restarted; disabled or masked sockets are not
enabled. Guard refusal and pending activation remain failures.

Before starting any candidate, the fixed installed `private_network.py` must pass
`apply` and `check`. These verify the exact IP/NIC, protected source/policy receipt,
all fourteen socket/service unit files, effective fragments, pending drop-ins and
owned ingress. The proxy forwards opaque TCP to the matching loopback port;
file-backed native authentication remains mandatory. Transport readiness never
proves model readiness. The dedicated Ada endpoint is excluded from480K routing.

FINALIZE01 extended the existing six-role owner through the explicit one-time
`scripts/h028/finalize_network.py` transition. The twelve predecessor unit files
remained byte-identical. The transition verified and archived the exact old
helper, policy, ownership receipt, firewall and units under the existing lock,
then atomically replaced only the owned INPUT jump's port list. It retained the
same interface/client allow rules and terminal DROP; no firewall flush or
unprotected gap occurred. The successor receipt retains the original pre-owner
firewall backup and binds the new helper/policy/fourteen-unit signature.

The predecessor archive is `/etc/llm-server/h028-network-predecessor-20260929`.
It is evidence, not an automatically replayable rollback. Never overwrite or
waive a mismatched receipt. A future inverse requires all fourteen owned units
stopped and sockets disabled, as enforced by the ordinary owner. No whole
firewall snapshot should be restored.

The standalone, control-api and node-api helper copies all have the same final
source. Both API processes were refreshed to load the successor policy. The
rearm helper and two units are root-owned0644 in the existing protected locations.
Source files, installed hashes and compact deployment receipts are recorded in
`reports/h028-finalize01-20260929/`.

Focused fixtures cover source/policy/ownership drift, exact ingress ordering,
interruption boundaries, disabled sockets, late network return, bounded retries
and no model authority. Live `systemd-analyze verify`, ingress checks, all seven
active sockets and natural healthy timer runs passed. Deliberate NIC disruption
and whole reboot are NOT_TESTED; neither was requested for finalization.
