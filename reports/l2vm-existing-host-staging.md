# L2VM — existing ai-vm registration and stopped control staging

**PASS — bounded stage complete. Control STOPPED and disabled; GLM unchanged.**

Executed on2026-09-15 from mac-worker1 through SSH `ai-vm` only. Base `5e713441d9ea164b81860ee795c5ef35972ee8e3`, including reviewed L2 `4da259ebfc7f933f59fa4065577aa318ac60d130`. Branch `milestone/l2vm-existing-host-staging`. Installer remains STOPPED; this commit contains reports/evidence and fixed one-use verification/procedure transcripts only. No product source/framework or installer test was added.

## Result

- Protected schema1 registration is installed at `/etc/local-ai-server/storage.json` root:root0600; new parent0700. Both exact UUID/mount/ext4/FSROOT=/ whole-volume identities, no whole-volume alias, distinct root/data/model devices and derived roots verified. No device/filesystem/fstab operation.
- Exact reviewed historical import added storage_identity and historical_import=true under canonical LifecycleLease, through the actual MountedStorageGuard/AnchoredRoot. Every other original field was preserved. Actual read-only binding, state read, trusted container identity and old GLM reuse contract checks passed; historical D1/32K profile objects were used only in memory and never installed in the final catalog.
- Exact46-file/752,246-byte root closure plus full source manifest installed.36 NORMAL/RECOVERY files, five fixed profiles, three closure/selection/evidence files and the two explicitly planned reviewed helper/guard supplements. All files/source hashes and17 exact directory identities/modes verified. No recursive repository copy, symlink or bytecode. Standalone N1S helper bytes and N1VM files preserved.
- Protected control config uses schema1/private_network. Dedicated control key created once root:root0600; metadata-only evidence, no value or key digest in worker/Git/logs/arguments. Existing native GLM key exact bytes privately compared unchanged. `/etc/llm-server` and `/usr/local/lib/llm-server` shared parents reused with owner/group/mode/inode preserved; normal child-creation directory timestamps are not claimed unchanged.
- Exact reviewed systemd template has its one `/data` substitution; `systemd-analyze verify` exit0. No daemon-reload/start/enable. Final unit is loaded/inactive/dead/disabled/MainPID0, with no drop-ins. No systemd runtime credential fabricated. Credential-dependent validate_installation/start acceptance is deferred.
- Q38 receipt published separately under canonical lease plus retained acquisition lock/seal/stat proof. Protected root0600 exact81 artifact receipt and correct model_integrity revision/manifest SHA link published. Actual reviewed `qwen38.check_completion` PASS. No model payload bytes reread; no runtime/auth entry or readiness flag added.

## Four exact metadata changes

| Path | Before uid:gid/mode | After uid:gid/mode | Preserved inode |
| --- | --- | --- | ---: |
| `/data/build` | 1000:1001/2775 | 0:1001/2755 | 21757953 |
| `/data/hf-cache` | 1000:1001/2775 | 0:1001/2755 | 16777217 |
| `/data/backups` | 1000:1001/2775 | 0:1001/2755 | 14417921 |
| `/data/logs` | 1000:1000/2755 | **0:1000/2755** | 47972353 |

All four retain device2065, gid, setgid and inode. Every original direct child retains its inode/device/owner/group/mode; no additional direct children were present at final inspection. No recursive chown/chmod or child-content write occurred. D3B run inode44302940 remains uid1000:gid1001/2770. The initial ready handoff's root:root wording for logs was a prose typo; direct fresh stat confirmed uid0/gid1000/mode2755/sameinode. Corrected handoff published immediately; no restoration or metadata rewrite was required.

## Exact unchanged proof and hashes

- GLM container `bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55`; image `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`; PID/restart count/StartedAt/argv/entrypoint/labels/bind tuples/network mode/logging/GPU request settings unchanged. Docker array ordering is normalized only for the unordered mount list.
- Both durable active.json and `/run/llmctl/recovery.json`: SHA256 `c63de9b1a77aa4d62496880c7dad8cb6a22a10de9736c5305545e3579d576f1f`; exact inode/uid/gid/mode/size/mtime/ctime unchanged, including JSON timestamps. Selected historical GLM32K, desiredrunning and bootmanual unchanged. Native key path/metadata/bytes and canonical lifecycle-lock inode/metadata unchanged.
- Original instance SHA256 `8a5f7787c00319f093656d4fe0b6953c79ae31669b4da7690e6f7386ecad839a`; final with approved binding plus Q38 acquisition link `55a1516385441e58c47e410a387afd71cfc20e58cb251ca9f495d9606e79a3ab`. Original raw backup and immediate pre-Q38 raw instance are protected on data. No state synthesis or timestamp reset.
- Q38 exact receipt SHA256 `2020e3d4b19a3d4a7221dfbf37a4f558ed98dcbd73e302b716ab95fb04e17dce`; pinned manifest SHA256 `726012378a40f648a104230d3f5ed5d6bc505cbd09b32918fc29aa81c0f075f2`; revision `017b9c7af6b5689d5dd426a76e0bc077eb5ca20a`.
- Root source manifest SHA256 `bb0176749bd35deace1643d1a70c42be92a9f0b7bc629d41663c594678365f55`; source remains exact reviewed5e71344. Manifest includes per-file SHA/size/mode/git blob/last source commit.
- GLM completion receipt, fstab, N1VM network policy/standalone helper and m6b-post unit exact bytes/stat unchanged. m6b-post remains disabled; boot unit/tmpfiles absent. Only127.0.0.1:30002 and10.156.100.60:30002 listen; control30000/Qwen30004 off.

## Checks, warnings and resolved execution issues

| Check | Result |
| --- | --- |
| Exact supplied canonical D3 guard SHA/root-protected ancestry | PASS every guard phase |
| Corrected canonical require-data/rootguard pre/post stages | PASS, no STOP entries |
| Actual installed registered rootguard, both roles and anchored writers | PASS |
| Final root available bytes | 5,209,284,608; PASS>=4GiB, WARN<6GiB |
| Full source union/profile hashes/protection/exact directory membership | PASS46 files/17 directories |
| Worker procedure syntax/help | PASS5 fixed scripts |
| Revised read-only VM preapply dry-run | PASS |
| Actual Linux systemd unit syntax | PASS exit0 |
| Actual historical binding/read-only GLM reuse validation | PASS |
| Q38 seal/proof/81 exact stat identities including .gitattributes and zero-byte file | PASS |
| Q38 writer/shared writable map/unreadable checks | zero/zero/zero; payload bytes read0 |
| Actual Q38 receipt contract and unchanged runtime evidence | PASS |
| Active/recovery/container/native key/lock preservation | PASS |

Two procedural verification errors were resolved without model/service actions. First, `--report /dev/stdout` contaminated the canonical guard's captured conclusion string, causing exit1 and an incomplete report; using retained original-output FD3 preserved its unmodified logic and returned actual PASS/no STOP. Second, initial final equality compared Docker's unordered Mounts array positionally. It stopped after staging; fresh evidence showed identical tuples in a different order. A fixed follow-up verified sorted full tuples and every required state/container field, actual source/registration/unit checks and canonical guards. The original failed outputs and exact executed procedures are retained; no reapply/overwrite or fabricated success was used.

Historical rootguard warnings for two existing small root directories were retained; nothing was cleaned or moved. No package/build/model/download/API generation/auth probe/stop/start/reload/context/network/reboot activity occurred in this task. Separate Q38VR no-model fixture activity was acknowledged through coordination and not awaited.

## Protected resources and inverse

Exclusive root0700 `/data/services/llm-manager/adoption/l2vm-existing-host-20260915` contains raw nonsecret originals with index, original metadata/absence, frozen manifest/inverse, immediate preimport and pre-Q38 instance bytes, copied sealed acquisition proof, key-action metadata, guard/unit/binding/publication reports. Files fsynced and verified; transaction/originals directory FDs explicitly fsynced under actual mounted guard and canonical lease. No actual keys or key hashes are backed up. Empty `/data/services/installer` and `/data/services/llm-control` remain root0700 compatibility roots, with no installer markers or control journal.

See [owned resources](l2vm-evidence/owned-resources.json) and [conditional inverse](l2vm-evidence/inverse.json). Inverse is not executed: compare exact current post identity/hash and require canonical lease/guards/owner release, restore original instance raw bytes rather than reconstructing fields, remove Q38 receipt only if still this publication, remove only task-created key by recorded creation action/metadata, preserve shared owners and state/intents. Restore exact four metadata tuples only on original inodes. Never blindly restore stale state or rollback after another model owner transitions. Protected backups remain available.

## Handoff and next action

[Registration-ready](registration-ready.md) was published before final bookkeeping; coordinator acknowledged it and released separate Q38VR work. The installed guard and storage.py hashes/path are provided there. A report path requires an existing protected task-private parent under `/data/logs`; no caller identity override is accepted.

**Control remains STOPPED.** Pending: refresh exact reviewed Q38VD changed helper/provenance closure before runtime; resolve actual Q38 ATTACH_FAILED/auth/runtime gates; later reviewed GLM owner performs canonical old-instance stop and final Q38/control binding; final patched GLM runtime/deployment/image/proof needs measured owner inputs. No compatibility exception, auth receipt, finalReady or occupied-context claim. Installer/boot/reinstall remains out of scope. Commit/bundle only; no push.

Evidence: [final verification](l2vm-evidence/final-verification.json), [final inventory](l2vm-evidence/final.json), [protected VM reports](l2vm-evidence/protected-stage-evidence.json), [preapply plan](preapply-plan.md), [input identities](l2vm-evidence/input-identities.json), [session](l2vm-session.md). Fixed procedure files under reports are exact execution evidence, not reusable host installation commands.
