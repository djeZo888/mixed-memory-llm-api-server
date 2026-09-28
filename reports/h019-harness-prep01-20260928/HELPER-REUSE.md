# H019 prepared acceptance helpers

Twenty focused helper/driver files reuse the H018 source at the current
`89cc931b69e39a4a2acd95270d3156396d0053d0` checkout. Eleven are byte-identical;
nine have the H019 task/release/unit namespace, current clocks, or the exact
950,000-token admission pin. All source modes are retained. The exact old/new
hashes and staging dependencies are in `HELPER-SOURCE-DELTA.json` and
`HELPER-SHA256SUMS`. No source under `ai-harness/` changed.

The existing live driver, wire guards, prompts, fixtures and preflight CLI are
unchanged. The driver requires exactly one foreground Qwen parent -> MiMo
child, actual child tool calls paired with nonempty results including bash,
the native child task identity, and a successful Qwen bash verification after
the child result. The original `H016_VERIFIED` marker is an unchanged fixture
token. Full 17 offered schemas, output ceiling 65,536, real request binding,
serial settlement, HTTP/SSE handling, no replay and existing quarantine
handling are retained. Full 17 offered tools does not mean every tool executes.

The H019 preflight requires actual usable context 950,000 and matching
configured/allocated context. It rejects the historical million-token
qualifier, fallback capacities, and 950,016 physical padding as usable context.
It retains the protected evidence reader and existing qualification validator;
current native qualification and a root review remain necessary. No new
qualification or root GO was generated.

Acceptance stops at **2026-09-28 03:49:30 UTC** with hard settlement by
**03:50:00 UTC**. The theoretical post-preflight admission bound is 03:34:30;
actual service entry must be earlier by both measured preflights. Minimum
actual work remains 720 seconds, maximum work 1,200, cleanup 180, supervisor
1,380, and final systemd stop grace 30. Monotonic and fixed calendar limits,
exclusive dispatch intent and no automatic restart are unchanged. The targets
remain an app result by 03:40 and native background dispatch by 03:55. The
latest root steering permits the native long test after native qualification
even if an app-only issue remains; this helper does not dispatch that test.

The future task path is
`/home/user/ai-harness-build/H019-HARNESS-PREP01-20260928`, with release
`/opt/ai-harness/releases/${SOURCE_COMMIT}-h019-prep01/ai-harness`. The parent
stages the retained H018 source with an explicit current overlay. The build
helper requires `SOURCE-COMMIT` to equal the reviewed current source identity;
the source manifest must describe those actual staged bytes and distinguish
the retained H018 source/clock overlay from the new H019 overlay.

The prepared build procedure reuses compiled image `46feffff`, retained host
release `6c4b5869`, and the exact 44-file compiled payload. Only the reviewed
two-file image COPY layer and three-file host configuration overlay are planned.
Profile `1767aec7` already preserves Qwen 480K, MiMo 950K and output 65,536.
The retained compiled MiMo 511-minute transport/provider support covers the
existing eight-hour operation policy; historical short abort tests are not an
eight-hour elapsed-duration result. Separate Qwen/frontier queues and native
child-wait ownership behavior remain in the retained runtime. No native or
dependency build, package fixture or historical broad test was repeated.

Offline checks: five existing clock fixtures passed; three focused capacity,
independent-owner refusal and admission/profile-pin fixtures passed. Syntax
checks passed for four shell files, four Python files, nine JavaScript modules
and the prompts JSON. Tests made no VM contact or model request. No build,
pair apply, service start or acceptance dispatch occurred in this helper task.
Historical rollback helpers were not copied; no automatic GLM rollback is
prepared for H019.
