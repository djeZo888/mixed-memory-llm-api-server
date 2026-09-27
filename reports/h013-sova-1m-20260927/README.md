# H013 Sova 1M preparation — PASS, not activated

Built source **7143c17d73173db9364b77956679c86d7026a4ae**, based on root
**f031ce71b1a3a9064ac3d665e86296f0741cee4e**. Candidate engine:
**sha256:9ef88598cf54a03aa259c5aa2d2878b34b7473cfcec7c8c07cee6ba462c39f1c**,
tag `localhost/ai-harness-engine:h013-7143c17-profile`.
Candidate server/web/config: ai-harness host,
`/home/user/ai-harness-build/H013-SOVA-1M-20260927/source/ai-harness`.
Source archive SHA256:
`185c76b91c3bbfe68ac78f684eaebbbaf65cd5683f0253797754a66235d49eaa`.

The label is exactly `Frontier GLM-5.3-Flash`. The intended production candidate
is qualified=true, Flash1048576/output65536; both Qwens remain480K, image unchanged.
Exact FRONTIER_INSTRUCTIONS and truthful observed readiness are preserved.
Native P-7/P-2 admission remains authoritative; no new claim of full1M Sova agent
occupancy or tokenizer-aware native scheduling. Scientific H012 evidence remains
intact; no request was replayed.

| Verification | Result |
|---|---|
| Prepared full Flash HTTP/capacity/readiness Python suite |38 PASS|
| Full server suite, including HTTP480K/1M boundary fixtures |396 PASS|
| Full web suite |176 PASS|
| Server/web typecheck and build; locked dependency graphs |PASS|
| Actual dist/app.js + gateway.js imports as ordinary user |PASS|
| Actual candidate image profile suite, UID1000/network none |16 PASS, no skips|
| Exact-content rollback helper, preservation/refusal cases |2 PASS|
| Original release/image/data/unit/credential metadata |unchanged|

`RESULT.json` records exact commands, checksums and limits. Logs and compiler
output are in `evidence/`; `SHA256SUMS` binds this packet. Python used a separate
local venv constrained to project package versions, not production installs.
Server dependencies were copied from the current production release and web
from its retained build, after exact manifest/lock comparison; `npm ls --all
--offline`, typechecks/builds and actual imports passed. The H009 readable-runtime
packaging requirement is explicit in the final installed-release procedure.

The full engine attempt first hit an offline npm cache miss. One bounded network
retry built fd4c3e91… but its ordinary-user test found root-owned0600 profile files
from private source staging. That image is retained and **unqualified**. Root's
updated authorization permitted the final two-file overlay. Comparison of90
engine/tool/skill/patch/probe inputs against exact deployed c328dac0… found only
configure-profile.mjs and configure-profile.test.mjs changed; the Containerfile
and native-probe build recipe also match the prior build source. The final image
inherits all proven dependencies/native binaries from c328dac0… and copies only
those two files with0444 modes. Its real managed-profile480K→1M migration and
packaged CLI tests passed as the runtime user. Use `build-profile-overlay.sh`
and its pinned Containerfile as the accepted recipe; full-build scripts/logs are
failed-attempt provenance, not a recommendation to rebuild unchanged tooling.

Original production engine c328dac0e6ede1dfb890a0657ebafd6f6fd4a1f2281f4e1c664ab95db7dcaa20
and release `/opt/ai-harness/releases/296ae49e44eb250773223885b843994e2c5b9bcc/ai-harness`
remain intact. Aggregate content/type/owner/mode hashes match before/after for
17,757 data files,3links,5,041directories and the complete old release. Secret
contents were not read; credential metadata matched. Sova remains inactive/PID0;
Search remains active/PID190181. No HOME/.local permissions changed, no BMC or
ai-vm access, no inference, activation, production tag/unit/profile/config write,
subagent, push, or unpause.

`DEPLOYMENT.md` is a concrete later paired app/status/image activation and rollback
command set, not executed. It includes the independent status-registry drop-in,
ordinary-user imports from the final immutable release and exact-content reverse
managed-profile migration. Rollback never restores old data and stays paused
until its backend capacity matches. Remaining gates are **root GO plus Worker1's
new authenticated production1048576 pool/tokenizer/readiness receipt**, fresh
quiet/ownership checks, activation, and post-activation preservation/readback.
No waiting for Worker1 is part of this task. Wrapper native/start/deadline are in
`SESSION.json`; final report commit and bundle digest are in task-parent
`FINAL-IDENTITY.json` (avoids a self-referential committed bundle checksum).
