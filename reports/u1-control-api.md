# U1 bounded catalog and asynchronous control API — source handoff

Session: `01a0a287-fa5f-7931-addf-034369af7105`
Reviewed base: `412aaed08cfb0a1f8b79b595d8a101d9828ff22e`
Branch: `milestone/u1-control-api`
Date: 2026-09-15

## Conclusion

**PASS: bounded independent source and local fixture acceptance.**
**INCOMPLETE: production Manager/installer binding.** No Ready or live-inference
claim follows from these tests. `serve.py --check-binding` exits 3 with
`production_adapter_unavailable` and `listener_started:false`; default startup
also refuses. No production fixture fallback exists.

The latest root coordination explicitly permits actual `Manager.prepare_start(d)`
under canonical lease before old-stop, including its anchored report write.
This supersedes the earlier missing read-only preflight decision. The base
Manager still has no frozen borrowed-lease `dispatch(..., lease=...)`,
`load_manager`, or `recovery_manager` implementation. U1 did not import an
unreviewed sibling checkout or modify lifecycle/storage/installer source.

## Implemented independent contract

- Dedicated bearer authentication on every route, default IPv4 loopback port
  30000, strict bounded HTTP/JSON, no auth/body/error logging, browser control,
  WebSockets, CORS, inference proxy or arbitrary command/path/profile inputs.
- Versioned installed catalog/status/switch/stop/operation routes and safe
  response allowlists. Generic protected-adapter DTOs support additional models
  and deployment variants; no model-weight reads/scans/hashes in serialization.
- Capability provenance and unknown values; readiness requires four explicit
  trusted proofs. Discovery includes server-relative endpoint, mutable port and
  alias, separate inference authentication and interruption metadata.
- One executor and nonqueued admission. The executor itself acquires the actual
  canonical lease nonblockingly, holds its minted context through receipt,
  preflight, old-stop proof, select/start and outcome, and passes the same lease
  to every fixture lifecycle action. External ownership conflicts before 202.
- Durable bounded operation journal, content-sensitive idempotency, semantic
  identity/generation checks, restart reconciliation without replay, and no
  automatic resurrection after failed start. Slow receipt cancellation cannot
  execute work after admission timeout.
- Exact protected immutable `/run` recovery fixture supports trusted stop with
  unavailable storage, full journal, and failed receipt/running writes. Separate
  bounded volatile results never evict durable receipts; `state_persisted:false`
  is explicit. A restarted fixture control process can discover its trusted
  recovery identity and stop without model/config reads.
- Source-only systemd template, fail-closed production entry point and detailed
  API/installer/client contract in `docs/control-api.md`.

## Checks and evidence

Machine-readable counts: `reports/u1-test-results.json`.

| Check | Count | Result |
| --- | ---: | --- |
| Actual loopback HTTP/socket transport | 31 | PASS |
| Actual loopback HTTP Application + synthetic lifecycle | 24 | PASS |
| Actual accepted HTTP operation + subprocess SIGKILL/restart | 1 | PASS |
| Catalog serialization/evidence | 20 | PASS |
| Core schema/observation/error/production-refusal guards | 28 | PASS |
| Durable/atomic fixture journal | 19 | PASS |
| Receipt races, restart storage and failed persistence | 10 | PASS |
| **U1 total** | **133** | **PASS, 0 skipped** |
| Existing actual canonical lease regression suite | 37 | PASS |

The 56 HTTP tests use real local TCP sockets. The Application integrations use
disposable keys and a synthetic lifecycle backend, and real canonical lease
ownership includes external subprocess contention. They prove exactly one
synthetic backend starts during simultaneous requests and reads respond during
Event-controlled loading. They do not launch an inference engine.

The crash test kills a disposable child only after an actual HTTP 202 and
blocked synthetic startup. It verifies kernel lease release, original durable
running receipt, restarted HTTP interrupted reconciliation, current immutable
identity/generation, retained idempotency and zero restarted backend calls.
This is actual local process recovery, not installed-systemd or boot recovery.

Additional checks: production CLI help PASS; binding/default startup refusal
expected exit 3; Python source syntax and scoped whitespace checks; exact file
scope, filename-only credential-pattern scan, safe HTTPS remote, and author plus
committer identity are release checks. Release commit, push and verified full
bundle are recorded in taskroot `progress.md`, `status.json`, and `final.md`.

Reproduction:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_control*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/lifecycle -p 'test_lease.py' -q
python3 -I -B scripts/control/serve.py --help
python3 -I -B scripts/control/serve.py --check-binding
```

The last command must exit 3 at this source milestone. No packages were installed,
no VM was contacted, no model/image was downloaded, no disk/service was mutated,
and no main branch was pushed.

## Exact remaining production seams

1. Deliver reviewed L1 source with canonical loader, immutable protected instance
   binding, borrowed `dispatch` and exact recovery construction. The extracted
   interface alone cannot enable production.
2. Use actual reviewed I1R `assert_package_admission(data_dir, storage_guard, *,
   policy_path=None)` under the held lease. Do not infer admission from a free
   flock or a marker alone; gate/orphan inhibitor checks belong to I1R.
3. Construct catalog/evidence and endpoint DTOs generically from protected
   registered manifests and acquisition records; review exact Ready translation
   from fresh Manager status. Current catalog module is serialization only.
4. Bind the journal to the actual reviewed registered mount-anchored writer,
   with a bounded read and durable write; no production path-based file fixture.
5. Show actual bounded Manager call behavior, including prepare/start/stop/probe
   timeouts. The independent port enforces cooperative deadlines; arbitrary
   Python code cannot be forcibly canceled safely. A live call never releases
   its lease simply because a timer elapsed.
6. Show an exact `/run`-only immutable recovery observation for fresh-process
   status/CAS and stop. No guessed `recovery_manager.status()` is used. The port's
   trusted recovery observation is an explicit fixture contract awaiting source.
7. I1c provisions distinct root-owned 0600 control key, protected source/config,
   registered journal location, and final substituted unit. Key reuse on resume,
   credential survival across storage loss, actual Docker/registry/guard access,
   hardening, termination/boot and installation/enabling require I1c/I2 evidence.

## Installer receipt and client handoff

Default control endpoint: `http://127.0.0.1:30000/control/v1`. Dedicated control
key is distinct from the inference key, never passed in argv/environment/unit
text or journal. Unit template uses a protected systemd credential source;
actual key-path/reader binding remains with final production integration.

202 is an admitted operation receipt after canonical ownership and durable
pending persistence; it is not model readiness. Busy returns 409 before admitting
a new operation. Poll the receipt URL, then refresh catalog discovery and map the
server-loopback inference port through the client's tunnel with its inference
key. Port/model alias may change. Switching/stop can interrupt any in-flight
inference stream. There is no drain, client-session reservation, force route or
permanent routed inference endpoint.

Normal receipts retain idempotency for 24h after completion, capacity 128. Full
capacity refuses normal mutation. Trusted recovery stop uses up to 16 volatile
receipts, explicitly unpersisted and lost on process restart/eviction. Restore
registered storage and repeat stop to persist stopped intent before reboot.

## Next action and limits

Root reviews this bounded source/bundle, delivers reviewed L1/I1R seams, and
coordinates final U1 binding with I1c ownership. Worker1/V1 then performs actual
two-installed-model HTTP switch, discovered-endpoint inference and OpenCode
acceptance. Live inference, real client-stream interruption, installed service,
boot and fresh installer remain **NOT_TESTED** here. Source template settings
are not a hardening or fresh-host readiness result.
