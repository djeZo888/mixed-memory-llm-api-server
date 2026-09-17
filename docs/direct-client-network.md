# Direct private-network client URLs

The native OpenCode client can use the existing loopback transport or a direct
literal RFC1918 IPv4 API endpoint. This is a client URL policy; it does not
configure a server listener, firewall, TLS, tunnel or model. Current delivery
scope remains GLM 5.3 and Qwen3.8-27B FP8; the installer is paused.

## Exact accepted policy

Use `http://<host>:<port>/v1` or `https://<host>:<port>/v1`:

| Part | Accepted values |
| --- | --- |
| Existing loopbacks | `127.0.0.1`, `localhost`, `[::1]` |
| Direct IPv4 | Canonical dotted decimal in `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` |
| Port | Explicit decimal value 1–65535 |
| Path | Exactly `/v1` |

Leading-zero IPv4 octets, hexadecimal/integer/short/mixed address aliases,
percent encodings, other DNS names, public IPv4, link-local, multicast,
unspecified, other reserved ranges and additional IPv6 forms are refused.
Credentials in the URL, query strings and fragments **including empty `?` or
`#`**, whitespace and control characters are refused. The client preserves the
accepted URL text; it does not resolve or normalize a private address to decide
whether it is allowed. Existing case-insensitive HTTP(S)/localhost and
zero-padded decimal ports remain supported.

These are the three explicit RFC1918 networks, not the broader set some IP
libraries call “private.” Client acceptance does not imply that every address
in those ranges has a reachable service or has been authorized for exposure.
The reviewed ai-vm address is `10.156.100.60`; its separately owned exposure
policy is limited to the approved `10.156.100.0/24` LAN.

## Authentication and transport

A direct private IPv4 endpoint **requires** `--api-key-file` or `--api-key-env`.
`--auth-disabled` is refused before bootstrap writes or subprocesses, including
`--dry-run`. Installed manifest/config validation repeats the check before any
launcher output, child process or network operation. Matching edits to both
generated files cannot bypass endpoint/auth validation.

Key handling is unchanged from [client installation](client-install.md):

- File mode stores only an absolute reference. Real launch requires an owned
  private regular file, private parent, no symlink/hard link, and 1–8192 printable
  ASCII bytes with no whitespace or newline. Missing, unsafe or empty keys fail
  before launching OpenCode.
- Environment mode stores only the approved variable name. Real launch requires
  a nonempty value satisfying the same byte policy. Never pass key values on
  the CLI or place them in reports.
- Bootstrap/dry-run/launcher plans do not open or require the key to exist.
  The `check` command uses a synthetic key to check interpolation. These checks
  do not authenticate to the model service.

Generated provider config contains the existing child environment reference,
never the key bytes or protected key filename. The launcher preserves its
isolated environment and strict key loader. Runtime/model authentication is
unchanged.

HTTPS retains native certificate verification; there is no insecure flag or
certificate-verification bypass. HTTP is for the currently approved trusted
private LAN: it sends the bearer credential and API traffic without TLS
encryption. Use only the endpoint/protocol the operator hands off under the
documented LAN/firewall policy. This change grants no public listener or new
server-side exposure.

## Generate a new private prefix

Choose an ordinary client user, an existing trusted workspace and a **new**
dedicated prefix under an existing private parent. Use the exact endpoint port,
model ID and limits from the current operator handoff. For example, after setting
the existing `CLIENT_PREFIX`, `CLIENT_MODEL`, `CLIENT_CONTEXT`, `CLIENT_OUTPUT`
and `CLIENT_KEY_FILE` variables as described in the installation guide:

```sh
export CLIENT_API_PORT='REPLACE_WITH_OPERATOR_PUBLISHED_PORT'
export CLIENT_API_BASE="http://10.156.100.60:${CLIENT_API_PORT}/v1"
python3 scripts/client/bootstrap.py \
  --prefix "$CLIENT_PREFIX" --base-url "$CLIENT_API_BASE" \
  --model "$CLIENT_MODEL" --context-tokens "$CLIENT_CONTEXT" \
  --output-tokens "$CLIENT_OUTPUT" --api-key-file "$CLIENT_KEY_FILE" --dry-run
```

Use the selected model's separately reviewed reasoning options when generating
its prefix; N1C does not change those options. Remove `--dry-run` only during
the authorized client setup. Changing endpoint/auth/model/limits requires a new
prefix; identical bootstrap calls retain existing idempotency checks. Do not
hand-edit generated config or copy changed helpers over an old installation.
Existing installed loopback clients retain their copied helper behavior; rerun
changed source into a new prefix for direct support. Native loopback/tunnel
transport remains available.

## Verification boundaries

Offline endpoint/auth tests:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest discover \
  -s scripts/client/tests -p 'test_endpoints.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest discover \
  -s scripts/client/tests -p 'test_*.py' -v
git diff --check
```

See the [N1C report](../reports/n1c-private-client-url.md) for the exact native
OpenCode 1.18.31 synthetic wire commands and results. That fixture uses a
confirmed worker-owned private address, an explicit short-lived bind and only
a synthetic sentinel. It checks the requested URL and key header. It does not
contact ai-vm, run inference or establish model acceptance. A failed local
Python/Bun connection can reflect macOS local-network permissions; diagnose
that separately from service/firewall failure without changing OS controls.

Separate-host ai-vm reachability and actual model/tool acceptance remain V1
work after N1 exposure and request-lease coordination. A loopback wire pass or
synthetic private fixture pass does not substitute for that evidence.
