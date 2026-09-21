# N1S transport contract — published before implementation

2026-09-15. Fixed API for L2; source-only, no live apply. Installer paused.

## Policy and read-only API

Source `configs/network/ai-vm-private-api.json` -> root-owned mode0600
`/etc/llm-server/network.json`. Exact JSON schema (all fields required, no extra
keys, duplicate keys, alternate types/encodings or arbitrary URLs/CIDRs):

```json
{
  "schema_version": 1,
  "mode": "socket_proxyd_private_ipv4",
  "interface": "enp6s18",
  "private_address": "10.156.100.60",
  "prefix_length": 24,
  "allowed_client_ipv4": ["10.156.100.0/24"],
  "ports": {"control": 30000, "glm": 30002, "qwen38": 30004}
}
```

Policy SHA256: `095bbf0ea64c792efa49ddf16a78383ec74528abe605c86b54ba8ac01563cb60`.
Only the approved LAN is accepted by this revision. A future frontend /32
requires a reviewed policy AND validator revision; no runtime overrides.

L2 imports `scripts.control.private_network.load_policy()` with **no arguments**.
It reads only the fixed installed path and returns a fresh validated `dict`
matching the schema above, or raises `PrivateNetworkError` (a `ValueError`).
It has no side effects, environment/header/request inputs, firewall commands or
readiness claims. Parents must be root-owned, non-writable by group/other,
non-symlink directories. Policy must be bounded <=4096 bytes, root0600 regular,
single-link, no symlink. `policy["private_address"]` is the advertised host;
`policy["ports"]["control"|"glm"|"qwen38"]` provides fixed role ports.
L2 maps exactly the two selected model identities/context deployments to these
roles. N1S does not edit catalog, control config/binding, Storage, client or Manager.

## Owned source and live paths

- `scripts/control/private_network.py` ->
  `/usr/local/lib/llm-server/private-network/private_network.py` (root0644).
- `configs/network/ai-vm-private-api.json` -> `/etc/llm-server/network.json` (root0600).
- `configs/network/llm-private-{control,glm,qwen38}.{socket,service}` ->
  `/etc/systemd/system/` (root0644); exactly six units, no backend dependencies.
- Firewall ownership + pre-change nonsecret filter snapshot ->
  `/etc/llm-server/private-network-state.json` (root0600); inverse retains snapshot.
- Shared helper lock -> `/run/llm-private-network.lock` (root0600).

The helper CLI is `source-check`, `preflight`, `check`, `apply [--dry-run]`,
`remove [--dry-run]`. `check` inspects **effective** rules and live interface;
no status marker proves protection. `apply` creates/restores only the exact
owned tagged chain/jump, before socket bind. `remove` requires all six transport
units stopped/disabled and removes only owned rules. It does not deploy files
or control services. Source checks run on Mac without touching host state.
Final file hashes and commit will be appended here after focused verification.

## Root closure / N1VM dependencies

N1VM must deploy the reviewed standalone helper at the fixed path above plus
policy and six units; no installer or general source-release mechanism is added.
L2 separately includes `scripts/control/private_network.py` in its control source
closure and updates its manifest under L2 ownership. Both installed copies must
be the reviewed identical bytes. Python stdlib only; no private imports.
N1VM owns absent-path checks, root metadata, reviewed file copies and exact file
rollback; preexisting files/unit overrides are refused, not overwritten.
Native systemd255 proxyd and iptables/ip/systemctl are existing host prerequisites.
Root review and fresh N1VM authorization precede host apply. Native model/control
authentication, loopback binds and GLM32K are unchanged. Empty upstream is not
ready. L2 owns advertised catalog and canonical RFC1918 literal HTTP(S), explicit
port, /v1, required-key client validation; earlier exact-origin proposal is superseded.
