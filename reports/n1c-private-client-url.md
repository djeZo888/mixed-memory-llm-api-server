# N1C — bounded direct private-IPv4 client policy

Date: 2026-09-15. Worker: mac-worker2, source-only.
Base: `6ffd620`; branch: `milestone/n1c-private-client-url`.

## Result

**PASS** for the exact client URL/auth policy, offline regressions and actual
OpenCode **1.18.31** synthetic HTTP wire checks on loopback and the worker's
confirmed private interface. **NOT_TESTED** for separate-host ai-vm reachability
and real model/tool acceptance. Exactly GLM 5.3 + Qwen3.8-27B FP8 remains the
current VM scope; installer work remains paused.

N1C made no ai-vm connection, VM mutation, model download, inference request,
server exposure, service activation, OS privacy change or TLS bypass. Temporary
client test state and synthetic listeners existed only on worker2.

## Exact production patch and ownership

The early worker handoff is `N1C/handshake.md`; the exported production-only
diff is `N1C/endpoint-functions.patch`, outside the repository.

| File/function | Change |
| --- | --- |
| `client_common.endpoint()` | Validates and returns the original URL through the classifier |
| New `client_common.endpoint_kind()` | Exact ASCII HTTP(S)/authority/port/path grammar; existing loopbacks or canonical IPv4 in explicit RFC1918 networks |
| New `client_common.validate_endpoint_auth()` | Validates endpoint and strict auth/reference shape; requires file/env auth for private endpoints |
| `client_common.config_for()` | One entry call to shared validation before generating config |
| `client_common.verify_install()` | One shared validation call immediately after reading settings, before config comparison or any launch |
| `bootstrap.parser()` | `--base-url` help only |
| `bootstrap.bootstrap()` | Shared validation call before dry-run output or any install/process step |

The now-unused URL-parser import was removed and the shared validator imported
by bootstrap. `launch.py` is unchanged: its first `verify_install()` call covers
all plan/help/check/run/chat entries. Q38C's reasoning validator, help and model
options are unchanged; V2 verifier files are untouched. No installer, lifecycle,
control, runtime or agent-protocol source was edited.

Policy accepts existing `127.0.0.1`, `localhost`, `[::1]`, plus canonical
literal IPv4 in **10/8, 172.16/12, 192.168/16**; HTTP or HTTPS; explicit decimal
port 1–65535; exact `/v1`. It rejects URL credentials, query/fragment delimiters
even when empty, whitespace/control bytes, DNS/public/link-local/multicast/other
reserved ranges, new IPv6 forms and all IPv4 address aliases. It does not use
`ipaddress.is_private`. Existing ASCII scheme/localhost case variants and padded
decimal ports remain accepted. Independent review identified Unicode long-s
case-folding as an unwanted alias; ASCII-only case matching and a regression
test close it.

Private `--auth-disabled` fails in both bootstrap apply and dry-run. Shared
installed validation rejects malformed URL/auth settings even when both
manifest and generated provider config have been tampered to agree. File/env
references, strict nonempty key loading and config privacy are preserved;
planning does not open the reference, while real launch rejects absent, empty
or unsafe keys before starting the client. Idempotency and new-prefix rules
are unchanged. Generated configuration was produced by bootstrap; deliberate
tampering occurs only in negative unit-test fixtures.

## Checks run

| Check | Status |
| --- | --- |
| Dedicated endpoint/auth suite | PASS, 21 tests with URL/auth subcases and process/socket/output/mutation guards |
| Dedicated private-wire fixture guards | PASS, 8 tests |
| Complete client suite, with real installed version/config check enabled | PASS, 71 tests, no skips |
| Existing agent protocol regressions | PASS, 94 tests |
| Actual pinned native loopback HTTP wire | PASS, 2 requests |
| Actual pinned native private IPv4 HTTP wire | PASS, 2 requests |
| Native credential persistence scan and generated-key removal | PASS |
| Production ownership/unchanged-functions, whitespace and filename-only credential-pattern scan | PASS |

Commands from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest discover \
  -s scripts/client/tests -p 'test_endpoints.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest discover \
  -s scripts/client/tests -p 'test_private_wire_fixture.py' -v
V0_CLIENT_PREFIX=/Users/agent/LLMServer-orchestration/20260915/N1C/n1c-wire-1/private-prefix \
  PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest discover \
  -s scripts/client/tests -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest discover \
  -s tests -p 'test_agent*.py' -v
git diff --check
```

Full bounded command output remains in the worker task's
`client-final-tests.txt` and `agent-regression-tests.txt`. Source/publication
gates and exact published commit/bundle identities are recorded in its final
handoff files. Author and committer must both be
`CodexAIagent <133749519+djeZo888@users.noreply.github.com>`; publication is only
to the N1C feature branch via the `gh` credential helper, never directly to main.

## Actual native wire evidence

Read-only `/sbin/ifconfig` confirmed worker2 `en0 = 10.156.100.182/24` before
any private listener. The fixture independently repeats assigned-address
confirmation; it never binds a wildcard or accepts another LAN peer.

| Listener | Exact observed request URL | Requests | Header/path checks |
| --- | --- | --- | --- |
| Loopback | `http://127.0.0.1:64480/v1/chat/completions` | 2 | PASS |
| Own private interface | `http://10.156.100.182:64523/v1/chat/completions` | 2 | PASS |

Every request passed exact `Host`, `/v1/chat/completions` and synthetic Bearer
header validation. The actual native process completed its synthetic response;
native version and resolved-config checks passed. Request bodies, headers,
transcripts and key bytes are not retained in the report. Allowlisted evidence:
[`n1c-private-client-wire.json`](n1c-private-client-wire.json).

Reproduction (choose a new work root and this worker's currently assigned
private address; the recorded work root is intentionally non-reusable):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning \
  scripts/client/tests/private_wire_fixture.py --help
PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning \
  scripts/client/tests/private_wire_fixture.py \
  --work-root /Users/agent/LLMServer-orchestration/20260915/N1C/n1c-wire-1 \
  --source-prefix '/Users/agent/LLMServer-orchestration/20260915/V0/verification client' \
  --private-address 10.156.100.182
```

The fixture used a read-only copy of V0's existing dependency tree after exact
committed package/lock and pinned package-version checks. Only the npm install
step was substituted with that copy; bootstrap generated both new private
prefixes. Native executable hashes matched the source dependency tree. Both
installed support files matched the final N1C `client_common.py` SHA-256
`8d9f89af8371884ff508ec8ee9e62c0e88199681999688f113a2884e63e34783`.
This proves the actual pinned client transport; it is not clean-install proof.

The fixture bounds each native child, cleans process groups/listeners, removes
its synthetic key and scans retained files for credential persistence. An
unavailable private bind or zero-request native timeout is `NOT_TESTED`;
auth/URL/client validation failures remain `FAIL`. This run passed both cases.

## Warnings, limits and next action

- HTTPS URL acceptance and the unchanged native verification controls are
  covered; no new live HTTPS server/certificate test was performed. No child
  process received a certificate-bypass variable. The TLS filter unit test
  uses a plain mocked mapping, without setting OS environment controls.
- HTTP is accepted under the approved trusted-LAN policy and carries bearer
  credentials/API traffic without TLS encryption. Client RFC1918 acceptance
  does not expand ai-vm's separately approved `10.156.100.0/24` exposure.
- The native checks were same-worker synthetic fixtures. They are neither
  separate-host reachability nor GLM/Qwen inference, tool-loop, context or
  performance acceptance. Existing native loopback proof is retained.
- macOS local-network access restrictions, if observed later, must be
  distinguished from service/firewall failure without changing OS controls.
- Next: review/merge the bounded function patch with Q38C/V2 ownership intact,
  then coordinate N1 exposure and V1 request ownership for a new direct-client
  prefix and actual ai-vm acceptance. Follow
  [direct client network documentation](../docs/direct-client-network.md).
