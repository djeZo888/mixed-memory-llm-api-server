# W2/root activation handoff — NOT INSTALLED

Concrete JSON candidates are in candidate/. CANDIDATE-STATUS.json records their exact byte hashes, actual creation/update times, and offline validation only (frontier true/image false). Root supplied completed actual-workflow and exact compatibility review by Mac-Orchestrator at 2026-09-29T15:28:54Z; both evidence/review use that exact authorized timestamp. This is the root-provided review time, not an informal inbox label or installation time. Concrete bytes remain NOT_INSTALLED pending final packet review before W2 installation. If root later changes any review bytes, recompute review hash in evidence and evidence hash in top record. No current running-source or native-health claim is made.

Candidate destination names after root review:
- /etc/sova-qualification/h033-codex-specialists.json
- /etc/sova-qualification/h033-frontier-evidence.json
- /etc/sova-qualification/h033-frontier-review.json

Each must be a regular single-link root-owned file with no group/world write, <=65536bytes, under protected root-owned/non-writable ancestry and readable by the app. No symlinks/hardlinks or task mounts. Root/status/example files need not be installed. No host files were written by COMPAT03.

Existing source path: src/codex-preview-main.ts reads receipt=argv[2], output=argv[3], imageMode=argv[4], ownedPolicy=argv[5], specialists=argv[6]. It calls startCodexPreview(receipt, output, imageMode==='image-jobs-reviewed', false, undefined, ownedPolicy, specialists). main.ts calls loadCodexSpecialists(specialistQualificationPath), then uses its booleans and capability reasons. Legacy positional booleans do not substitute for protected specialist evidence.

Exact existing Node CLI shape (documentation only; not executed here):
```
node ABS_APP/server/dist/codex-preview-main.js ABS_EXISTING_QWEN_RECEIPT 65536 image-jobs-unqualified ABS_EXISTING_OWNED_ACCEPTANCE_POLICY /etc/sova-qualification/h033-codex-specialists.json
```
Use the actual current approved receipt/policy paths from W2's host context; do not invent empty policy files or change tickets. argv[5] must be an absolute path when supplied. Existing API callers can pass undefined for acceptance/ownedPolicy and provide the seventh specialistQualificationPath argument explicitly.

Integration gap visible in this checkout: deploy/run-server.sh does NOT accept a specialist qualification option and constructs at most the owned-policy argument. There is no existing environment toggle that opens this gate. W2 must wire the already-existing preview entrypoint argument through its reviewed launch/config path as separately authorized; COMPAT03 does not edit launcher/main/config. Standard main.ts startup remains MiniMax-only and does not consume this record implicitly.

Retain actual transcript summary/final-settlement bytes and private raw manifests outside task mounts as root evidence. The candidates use exact byte hashes of the provided summary files; those summaries preserve the underlying raw-manifest hashes, old pins/source and NULL/omitted requested effort. Source protocol byte equality is in SOURCE-PROVENANCE.json. eb8ed is reviewed implementation basis, not a later running commit. W2 owns any model-catalog mount wiring correction and deployment/settled-idle checks; this source-only task does not confirm that correction or current native health.
