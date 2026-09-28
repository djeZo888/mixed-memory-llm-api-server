# H028 finite private transport recovery

The timer continuously observes slowly, including when the interface/address
returns long after boot or a manual NIC repair. It first runs after 45 seconds,
then 120 seconds after the previous recovery service run becomes inactive.
Each run makes at most four attempts with delays of 0, 5, 15 and 30 seconds,
a 90-second total helper budget, and a 120-second systemd hard timeout. Exhaustion
is reported honestly; the next slow timer observation remains scheduled.
A single oneshot service and OnUnitInactiveSec prevent overlapping timer runs.
Healthy sockets require only state reads and produce no mutations. There is no
automatic model recovery or unbounded per-run retry loop.

Only existing enabled (including runtime-enabled) inactive/failed transport
sockets are candidates. Active sockets are not restarted; disabled/masked sockets
are not enabled. A fresh state read before each action respects a concurrent
operator disable. Only socket `reset-failed` and nonblocking `start` are issued.
The exact original `private_network.py apply` and `check` guards must pass before
any such action. They preserve the reviewed interface/address, all twelve unit
bytes, pending drop-in checks, source/policy receipt and firewall ownership. No
network configuration or upstream service is changed. Socket activation proves
transport only, never model readiness. An activation still pending is retried and
cannot be reported as success.

## W1 installation and source pins

W1 is the sole ai-vm writer. This is a separate root-owned helper and two new unit
files, not a change to any existing transport unit or the guarded network helper.
Do not update/archive its ownership receipt, alter its source pin, add socket
drop-ins, or change node/control source closures for this addition. Existing
`private_network.py` bytes remain unchanged. Verify the delivery's SHA-256 pins
for these exact new files before installing:

- `scripts/control/private_network_rearm.py` to
  `/usr/local/lib/llm-server/private-network/private_network_rearm.py`, root:root 0644.
- `configs/network/llm-private-network-rearm.service` and
  `configs/network/llm-private-network-rearm.timer` to `/etc/systemd/system/`,
  root:root 0644.

Use the existing protected parent directory. Check the new paths are absent
(including dangling symlinks) and there are no existing same-name fragments,
overrides or dependency directories; refuse an unowned collision. Record before
socket enabled/active states and helper/unit hashes privately. Keep all twelve
existing transport unit hashes and the original ownership receipt unchanged.

Run both source checks, then install only the three new pinned files:

```sh
python3 -B scripts/control/private_network.py source-check
python3 -B scripts/control/private_network_rearm.py source-check
sudo install -o root -g root -m 0644 scripts/control/private_network_rearm.py /usr/local/lib/llm-server/private-network/private_network_rearm.py
sudo install -o root -g root -m 0644 configs/network/llm-private-network-rearm.service configs/network/llm-private-network-rearm.timer /etc/systemd/system/
sudo systemd-analyze verify --man=no /etc/systemd/system/llm-private-network-rearm.service /etc/systemd/system/llm-private-network-rearm.timer
sudo systemctl daemon-reload
sudo systemctl enable --now llm-private-network-rearm.timer
```

Enabling the new timer does not enable any transport socket. If boot time is
already beyond 45 seconds, the timer starts the bounded helper immediately.
Record status and a bounded journal for the new service, then current socket
states and private status API reachability. An HTTP response or listening socket
does not qualify model readiness. Preserve failure logs on exhaustion. The next
timer observation occurs 120 seconds after completion, whether the prior run
succeeded or failed. An operator may also start the same service explicitly;
systemd does not create a second concurrent instance of this fixed service.

Rollback stops/disables only the new timer, stops the new recovery service, and
removes only new files whose installed hashes match the recorded delivery. Then
daemon-reload. Do not stop the existing sockets, reverse enabled states, remove
ingress, rewrite the original receipt, or touch native upstream/model services.

Local focused tests simulate unavailable/recovered networking, finite backoff,
guard refusal, pending activation, operator-disabled sockets and a late-network
return after an earlier run exhausted its budget. Live systemd
activation and late-network recovery require W1's actual deployment receipt.
