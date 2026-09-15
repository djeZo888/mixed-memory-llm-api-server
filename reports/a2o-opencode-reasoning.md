# A2O pinned OpenCode low-effort option

2026-09-15 — **PASS: source change and actual client-to-synthetic-server proof.**
Real GLM agent acceptance remains **NOT_TESTED by A2O**; root reviews this change
before V1 creates a new client configuration.

## Change and ownership

Base `e6c77debb4989ada0c7a563159f8df45aa89f7b5`, branch
`milestone/a2o-opencode-reasoning`. Add optional bootstrap
`--reasoning-effort low`. Only the literal string `low` is accepted. Default
omission preserves the V0 manifest/config shape; malformed present manifest
values, including null/bool/collections, fail verification. The setting is
bound to generated model options and identical-install verification. A changed
selection requires a new private prefix; installed files are never hand-edited.

The launcher, permission/environment controls, exact OpenCode **1.18.31** pin,
package manifests/lock, model/endpoint/limit inputs, and trusted arbitrary
workspace semantics are unchanged. No runtime flag, server option, reasoning
budget or A1 replay-policy change was made. The option itself changes only
`bootstrap.py` and `client_common.py`; additional files are dedicated client
tests, client documentation, and `reports/a2o-*`.

Read AGENTS, current V0 client guide/report/handoff, D3 client request and V1
handoff before implementation. `incoming.md` was checked at phase boundaries;
I1c's client-file freeze and A2A's separate ownership were respected. The early
frozen installer CLI contract is in taskroot `installer-handshake.md`. Existing
historical installation STOP gates were not treated as authorization for VM
work; this execution is source/private-fixture only.

## Pinned implementation and measured wire proof

The [primary-source report](a2o-provider-source.md) traces the exact OpenCode tag,
bundled compatible provider **2.0.41**, and its official source serializer:
`provider.local.models[model].options.reasoningEffort` becomes top-level
`reasoning_effort`. The actual native binary returned **1.18.31**. No adapter,
SDK substitution, monkeypatch, proxy rewrite, or manually edited config was used.

The final [allowlisted wire artifact](a2o-wire-evidence.json) was produced by
[the reproducible fixture](../scripts/client/tests/wire_fixture.py) on macOS
arm64 / Python 3.14.7. Three fresh private prefixes were generated through the
real bootstrap and committed npm lock. Each was verified again idempotently,
then the installed launcher executed ordinary and tool-loop sessions against
a local synthetic HTTP server using a generated protected disposable key.

| Selection | Ordinary + auxiliary requests | Tool + auxiliary + continuation requests | Observed effort |
| --- | ---: | ---: | --- |
| Default, `glm-5.3` | 2 | 3 | Omitted on all 5 |
| Low, `glm-5.3` | 2 | 3 | Top-level `low` on all 5 |
| Low, `vendor/model:Q4_K_M` | 2 | 3 | Top-level `low` on all 5 |

**6 cases, 15 HTTP requests, 3 actual completed read events, 3 two-round loops.**
All 10 selected-low requests carried the required top-level field, including
OpenCode auxiliary/title requests, ordinary generation, tool invocation and
continuation. All 5 default GLM requests omitted it. Output limit was 2048 for
every observed request; generated context was 32768. These are fixture inputs,
not universal model defaults.

The synthetic server returned a valid `read` call; OpenCode actually read a
private disposable file. An unpredictable marker from that file appeared in
both OpenCode's completed read event and its second HTTP request, with the
matching assistant call ID and tool-result ID. Exactly one tool invocation and
one continuation were required in each loop, together with a final text event.
The files remained unchanged. No bash/edit permission was granted and no
network/subagent tools were offered or invoked.

Only fixed model/effort/transport fields, bounded scalar limits/counts,
authentication booleans and tool-continuation metadata are retained. No auth
headers, raw request/response bodies, CLI transcripts, key values or host
workspace content are published. The runner checked that its disposable key
was absent from all other private files and captured child output, then removed
it. Request count, payload size, child wall time and process-group cleanup are
bounded. The private listener is closed on exit. The runner refuses existing
roots and roots inside any Git checkout/worktree.

## Checks and status

| Check | Result |
| --- | --- |
| Exact official source, SDK version/patch and actual binary version | PASS |
| Original 21 client tests, including actual installed version/config check | PASS |
| New effort-option tests | PASS: 15 |
| New fixture guard/real subprocess cleanup tests | PASS: 6 |
| Combined client suite with installed-prefix check | PASS: 42 tests, no skips |
| Existing A1 suite, unchanged | PASS: 75 tests |
| Final actual OpenCode wire fixture | PASS: 6 cases / 15 requests / 3 read loops |
| Actual bootstrap/config verification and repeated install | PASS for default and both low prefixes |
| Invalid types/default/tamper/idempotency/no-write behavior | PASS |
| Fixture key absent from other files/output; removed after run | PASS |
| Python 3.10 syntax, helper/fixture `--help`, whitespace and local links | PASS |
| Independent option/fixture/test/docs review | PASS; cleanup, Git-root and scalar-metadata findings fixed before final wire run |
| Ubuntu execution / clean Linux installer / GitHub Actions | NOT_TESTED on this worker |
| Actual OpenCode nonstream generation | NOT_SUPPORTED by this pinned ordinary CLI agent path |
| Live GLM / real credentials / read-edit-test agent acceptance | NOT_TESTED — V1 after root review |

Verification commands are in [client-install.md](../docs/client-install.md#regressions-and-upgrade-policy).
Final worker wire command used taskroot `wire-run-2`; report source hashes bind
the evidence to the generator, launcher, lock and fixture. Final suite command
set `V0_CLIENT_PREFIX` to `wire-run-2/low-glm`; this installed check uses a
synthetic interpolation key and does not contact the fixture or a model.

## Warnings, next action and publication

The pinned CLI agent path uses `streamText`; all 15 observed requests used
`stream: true`. Its output `--format` is not a transport option. SDK nonstream
serialization shares the source argument builder but was not falsely reported
as an actual OpenCode nonstream request. The synthetic server supplies all
model responses, so this proves the client wire/config/tool loop, **not real
LLM reasoning, repair/test capability, or live GLM continuation**.

No VM access, tunnel, inference model, real key, global installation/config
change, service activation, host installer, disk mutation, GPU package, or
reboot occurred. Private local npm client installs were confined to the task
prefixes. Configuration isolation remains distinct from an OS sandbox.

Root should review this source and wire evidence, then V1 should bootstrap a
new private prefix with the current endpoint/protected key handoff, exact model
`glm-5.3`, context 32768, initial output 2048 and `--reasoning-effort low`.
V1 owns actual GLM continuation/read/edit/test acceptance; preserve A1 replay
policy and the reviewed server invocation.

Publication uses only the feature branch with both author and committer
`CodexAIagent <133749519+djeZo888@users.noreply.github.com>`. Exact ownership,
filename-only secret scans, whitespace, safe HTTPS remote, attribution and clean
worktree are publication gates. The full verified `A2O.bundle` is created
immediately after the source commit. Taskroot `final.md` records the session ID,
source commit, final gates, remote result and bundle hash without another source
formatting commit. Main is not pushed.
