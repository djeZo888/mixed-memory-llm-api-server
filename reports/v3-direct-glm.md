# V3: direct separate-host GLM and ordinary agent acceptance

2026-09-15 — **Direct authentication PASS; streamed A1 agent PASS; ordinary
OpenCode PASS. A1 protocol aggregate remains FAIL solely for unknown-model
acceptance (HTTP 200, served `glm-5.3`).** Installer remains STOPPED.

## Authority, source and transport

Worker2 ran as ordinary UID 502 on `mac-worker2`, private IP
`10.156.100.182`, directly against `http://10.156.100.60:30002/v1`.
No SSH tunnel or proxy carried inference. Native `/usr/bin/nc` connected;
native `/usr/bin/curl -q --noproxy '*'` independently measured the HTTP path.
A1 Python HTTP and V2 Python model preflight also succeeded; no errno 65 occurred.
Native OpenCode then used the configured direct endpoint.

The exact reviewed source was
`5e713441d9ea164b81860ee795c5ef35972ee8e3`, branch
`milestone/v3-direct-glm`. All 33 tracked A1/client/V1G2 validation files
match that commit. [Source manifest](v3-evidence/source-manifest.json) binds
file bytes, Git tree and source archive. No client, validator, fixture,
generated config or installer source was edited.

Read AGENTS.md and taskroot plan.md, exposure-ready.md and incoming.md;
incoming was reread at phase boundaries. The explicit current sole GLM lease
superseded plan.md's older queued wording. Worker1 owns all VM/lifecycle work.
There were no VM mutations, installs, model downloads, builds, tuning,
profile/instance/key/service changes, control calls or Qwen calls by V3.

Worker1's exposure handoff identifies unchanged GLM context 32768,
`clear_thinking=true`, container
`bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55`, image
`sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`,
and command SHA256
`89510f6d1b0ede1ae1bba8a1f9097c42fa063f2196ee14c000e6c9810e7fae00`.
These runtime identities come from the handoff; V3 directly verified the API
model identity, not the container state.

## Direct authentication and unchanged A1

[Native evidence](v3-evidence/direct-auth.json), recorded at
02:57:37.914834–02:57:38.179850 UTC: missing key **401**, wrong key **401**,
correct key **200**, exactly `glm-5.3`. curl recorded both direct source and
destination addresses. A fresh owned 0700 task directory and 0600 key file
outside Git received the existing key through authorized SSH sudo. Curl used
protected header config files; no actual secret appeared in argv or output.

[A1 evidence](v3-evidence/a1-stream-tools.json): one unchanged CLI run,
02:57:53.537098–02:59:11.305118 UTC, exit 1, measured 77.672917 seconds.
Settings: `--stream-tools --reasoning-effort low --max-tokens 2048
--request-timeout 300 --overall-timeout 1800`; other bounds stayed at defaults.
The reviewed client sends top-level `reasoning_effort: low` on every model POST,
including missing/wrong-key and unknown-model probes and tool continuations.

| Check | Actual result |
| --- | --- |
| Model list and ordinary chat | PASS; HTTP 200, `glm-5.3` |
| Missing/wrong authentication, models and chat | PASS; all four HTTP 401 |
| Correct authentication, models and chat | PASS; HTTP 200 |
| Ordinary SSE completion | PASS; stop and `[DONE]` |
| Unknown requested model | **FAIL; HTTP 200, returned `glm-5.3`** |
| Streamed genuine read/edit/test agent | PASS; four rounds, 56.762031 seconds |
| A1 aggregate | **FAIL**, preserved unchanged |

The actual sequence read `calc.py` and `test_calc.py`, wrote `calc.py`, ran
real tests, then returned final assistant content. The baseline exited 1;
the model-requested test and independent final test exited 0. Implementation
changed, immutable test hashes matched, and the disposable A1 fixture was
removed. Agent finish reasons were `tool_calls`, `tool_calls`, `tool_calls`,
`stop`; all four streams recorded `[DONE]`. No returned reasoning fields
were present. Raw messages, tool arguments, outputs and diffs remain private.

Nonstream provider prompt/completion/cache counts were 18/11/17 for the first
chat, 15/38/14 for the invalid-model request, and 18/6/17 for the authenticated
chat. SSE provider usage was **NOT_REPORTED** for both chat and all agent
rounds. Request `success` means transport/parse success and does not override
the invalid-model acceptance failure.

## Actual ordinary OpenCode 1.18.31

[Bootstrap evidence](v3-evidence/bootstrap.json): fresh ordinary-user prefix
created through unchanged `scripts/client/bootstrap.py`, direct URL,
`glm-5.3`, context 32768, output 2048 and low effort. No supported production
locked-tree-copy option exists, so the authorized client-only pinned npm ci
was used; it completed within its existing 600-second bound. Nothing was
installed on ai-vm. No generated settings were hand-edited.

[The unchanged V2 report](v3-evidence/ordinary-client.json) is **PASS**:
02:59:42.202277–03:01:48.478639 UTC; native process 121.747799 seconds,
exit 0, no timeout or output limit, one invocation with timeout 1800.
Pre/post integrity verified 29 packages and 3650 files against reviewed
source, package lock and SHA512-verified cached tarballs. Actual versions:
Node v24.21.0, npm 11.19.0, OpenCode and plugin 1.18.31.

All eight checks passed: both file reads, implementation edit, exact test
command, actual passing tool result, final response, immutable tests,
independent final rerun, and process cleanup. The baseline had five intended
assertion failures and no import errors. Native tools performed read/read/edit/
bash in the private workspace, with the exact requested command
`python3 -I -B test_text_utils.py`; bash exited 0 and tests passed.
The independent test also exited 0. Only `text_utils.py` changed, with final
hash `3fd34f6eaad8377d745966c43047f1ac2c2914a6c731e69e0b281f98e77e45d1`.
The before/after immutable test hash was
`b51a86da2ac6fbcf76b7b4b8cebadbdc5d28ab4c6bf833dbca11265dcb3e6c43`.
Both model-list observations returned exactly `glm-5.3`.

| Native step | Input | Cache read | Output | Total | Finish |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 5062 | 10 | 87 | 5159 | tool-calls |
| 2 | 471 | 5158 | 69 | 5698 | tool-calls |
| 3 | 9 | 5697 | 57 | 5763 | tool-calls |
| 4 | 21 | 5762 | 34 | 5817 | stop |

These are observed native client counters, not independently captured
provider-wire usage. Native reasoning/cache-write/cost counters were zero;
provider usage is separately **NOT_REPORTED**. No per-token rate, TTFT or
uncontended speed claim is made. D3B builds/staging were permitted to overlap,
so all timings are **potentially build-contended**.

Largest native input plus cache-read count was **5783**, within configured
32768. This short task does not prove occupied 32K or maximum hardware context.
The model-list `n_ctx_train=1048576` is training metadata, not the configured
slot capacity or a measured hardware limit. Historical V1G2 tunnel results
remain historical and are not reused as direct-network proof.

## Verification and next action

Reproduction commands and evidence checks are in
[the evidence README](v3-evidence/README.md). Publication/cleanup checks are in
[validation.json](v3-evidence/validation.json) and
[lease-release.md](v3-evidence/lease-release.md). Raw task data, fixture and
native logs remain private outside Git. No human fixture fix, counterfeit
tool/test, silent retry, budget increase or validator weakening occurred.

**Next:** coordinator/Worker1 can resume its separately authorized work after
lease release. Preserve the unknown-model compatibility failure when deciding
API readiness. Ordinary direct agent capability is proven for this short
baseline only; installer, frontend, control/Qwen acceptance and larger-context
qualification remain separate work.
