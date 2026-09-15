# L2VM registration-ready — COMPLETE / control OFF

Registration, historical import and protected stopped control staging are complete on ai-vm. Canonical D3 pre/post guards and actual installed registered rootguard PASS. Both exact whole-volume identities and derived roots verified. Canonical lifecycle lease has been released.

- `/etc/local-ai-server/storage.json`: schema1 root:root0600; parent root:root0700. Existing UUIDs preserved: data `8daf56f1-5649-4163-9d87-919c2d271875`; models `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`.
- Four exact nonrecursive metadata changes applied; all original inodes/gids/setgid retained. D3B existing run preserved. `/data/logs` is now root:root2755. A later authorized root writer must create its own protected task-private report parent below `/data/logs`; guard does not create missing report parents.
- Historical instance has exact stable storage_identity and historical_import=true only. Read-only registered binding/trusted identity/old GLM reuse validation PASS. No compatibility profile installed.
- Actual installed guard: `/usr/local/lib/llm-server/control-api/scripts/common/registered-storage.py`, SHA256 `21cf082a841aeab9470bd6704b77104961b9d4afcaec696d90aa22b65f5b6f3d`.
- Its actual storage dependency: `/usr/local/lib/llm-server/control-api/scripts/install/storage.py`, SHA256 `4f834e92d149ea1955e79d34c53c18bf8c5846a4121d779e135a50d31a615505`.
- Verified command: `sudo -n /usr/bin/python3 -I -B /usr/local/lib/llm-server/control-api/scripts/common/registered-storage.py --root-guard --json`. Optional `--report /data/logs/<protected-existing-task-parent>/<file>.json` is constrained to registered logs and requires that parent to exist/protected. No environment override or D3BR source change needed for this dependency.
- Control service installed, Linux unit verification exit0, stopped/disabled. Port30000/30004 off. GLM native127.0.0.1:30002 and private10.156.100.60:30002 preserved. No start/stop/reload/API generation/probe/network/key rotation/state timestamp change.
- Full exact46-file source manifest is `/usr/local/lib/llm-server/control-api.manifest.json`, current reviewed base `5e713441d9ea164b81860ee795c5ef35972ee8e3`. Q38VD refresh still required before runtime; no auth receipt or finalReady.
- Protected originals/inverse/checks: `/data/services/llm-manager/adoption/l2vm-existing-host-20260915`. `stage-result.json` reports PASS_STAGED_ONLY. Initial unordered Docker Mounts list equality stopped post-check; exact sorted mount tuples and all required container/state fields verified unchanged by follow-up. No container action occurred.

Q38 protected acquisition seal validation passed81/81. Receipt publication is the next bounded L2VM bookkeeping step; actual Q38 fixture/auth/runtime and final measured patched GLM inputs remain separate owners. Do not interpret this handoff as model/control activation authorization. Installer remains STOPPED; no boot/reinstall work.
