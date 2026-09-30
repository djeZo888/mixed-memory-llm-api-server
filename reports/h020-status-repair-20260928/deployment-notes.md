# H020 DEPLOY02 actual deployment — 2026-09-28

**PASS.** Source `739462b7e246f92a3c4161c4535a1a2d8a0886f2` was activated at
04:20:28 UTC under the exact root GO. Only the reviewed
`40-h020-status.conf` was installed, followed by one daemon-reload and one normal
restart of `ai-harness-status.service`. Its actual PID is **527553**, cwd and
command-line target are the reviewed H020 release, and its executable is the
retained Node24.21.0 binary. Status is active/running with no automatic restart;
`ai-harness.service` remains inactive, MainPID **0**.

The original README and deployment manifest remain unchanged as predeployment
history. This note, `deployment-result.json`, and
`deployment-passive-acceptance.json` record the actual outcome. Current CANDIDATE
staging metadata, pinned DEPLOYMENT, and remote files agree. Earlier in-progress
candidate fields are superseded history, not an alternative release.

## Acceptance evidence

- All source, compiled module, registry, selection and drop-in pins match. Existing
  status unit/drop-ins are unchanged; the new drop-in is root:root 0644. The
  selector retains the exact deployed MiMo 950000/65536 bytes and SHA256
  `6fac2925b81e0c40154635643a327f8f3149f7211cf8b78a4f321f6d5b09dc22`.
- Passive public DTO shows selected MiMo, configured/observed alias agreement,
  matched identity and explicit fresh evidence. GLM is dormant with projected
  ready=null and health=unknown; its observed ready=false remains separate.
- Qwen GPU0/GPU1 keep different instance names, aliases and required GPU UUIDs.
  The measured frontier GPU row joins only MiMo as its ready model dependency.
  Its GLM/MiMo action-impact IDs remain intact and separately labelled.
- Cached ai-vm node generation `1543851034896813` and node-manager generation
  `4902192187430733` are unchanged across activation. Existing visible service
  generations, aliases and deployment labels also match. The old public registry
  omitted MiMo; the retained preparation observation supplies its earlier alias
  and deployment label. This comparison is observer evidence, not native PID
  attestation or evidence of benchmark state.
- Public JSON contains no credential/transport configuration keys, private
  endpoint URLs, credential paths or advertised action authority under the
  recorded checks. No credentials were read to conduct the check.
- Installed Chrome rendered live `/status` at 1440x1000 and 390x844 through an SSH
  SOCKS tunnel via ai-harness, preserving the real public Host. Eight permitted
  public GET requests all returned200; no page errors or admin requests occurred.
  Both document widths fit the viewport. The DOM assertions verify MiMo/GLM,
  Qwen instances, freshness and GPU language. Desktop full-page and mobile top
  screenshots were visually inspected. Full desktop/mobile screenshots and text
  receipts remain outside Git in the task's `private` directory.

Initial acceptance tooling failures are retained: loopback port80 was not the
nginx listener; a local-forward browser URL returned403 due to Host restrictions,
including one repeated attempt after a selector correction; Chrome rejected an
explicit Host override. Using the documented public URL through SOCKS passed.
No service/configuration change or extra status restart addressed these tooling
failures.

## Boundaries and handoff

No source changes, builds, broad tests or production fixture/configuration
mutations were performed. Preparation's17 focused tests, status typechecks and
synthetic browser tests are historical validation, not reruns in DEPLOY02.

There was no ai-vm SSH, inference request, benchmark receipt/progress/result read,
admin request, model switch, other service restart, hardware action, Codex
integration or automation change. Ordinary Sova chat stays paused; HTTP400 was
not investigated. Existing passive observer readiness and deployment labels do
not prove native process identity or benchmark qualification.

Both the actual-old7143 release and previously loaded H019 release remain intact.
Rollback was not executed. Credentials, chats/uploads, assets, quarantines and
original receipts remain untouched. Root owns synchronization/publication; this
worker commits reports only and supplies an incremental bundle over
`ef6a75178b53dfaa5bf41a50e0835676500ce966`.

Native session: `01a0e63c-591b-75e2-8c78-f457ef0dd85c`.
Wrapper start04:18:29.702351 UTC; hard deadline04:30:29.702351 UTC.
