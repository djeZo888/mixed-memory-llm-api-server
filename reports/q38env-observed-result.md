# Q38ENV — three-variable observation complete

Exactly one disposable container ran. All three host Config.Env inputs were exact single occurrences. Parent and directly spawned same-interpreter child agreed:

| Variable | Docker Config.Env | Parent | Child |
|---|---|---|---|
| NVIDIA_VISIBLE_DEVICES | `"none"` | `"void"` | `"void"` |
| NVIDIA_DRIVER_CAPABILITIES | `"compute,utility"` | `"compute,utility"` | `"compute,utility"` |
| CUDA_VISIBLE_DEVICES | `""` | `""` | `""` |

The only failed predicate equality in this observation is **NVIDIA_VISIBLE_DEVICES == "none"**. No reason for the host/process difference is established. Q38VR2 itself recorded only the combined failure, so this diagnostic does not retroactively measure its individual values.

Origin: host values were projected from the exact owned container's Docker Config.Env before start; process values came only from three `os.environ.get` calls in `python3 -B -c` and a direct `[sys.executable, "-B", "-c", ...]` child with inherited environment. No `-I`/site flags in either container process, native/SGLang imports, model/hardware stubs or environment correction. Full fixed command and exact pre-start policy are adjacent evidence.

## Identity, cleanup and guards

- Exact pinned image verified by unchanged reviewed `qwen38_oci` checks. Observed Docker ID domain: **oci_platform_manifest**; no invented config/manifest mismatch.
- Owned immutable container ID: `a88d34f603cdebdcf3e34a578dcb5412239c862e2895ac0c7b84657c6782bf87`.
- Name: `q38env-20260915-5ea22171e82ac28bf3247ec8c794f4bb`; exact owner label retained in pre-start policy.
- Exit 0; cleanup **QUIESCENT_REMOVAL_VERIFIED**; final exact owned-ID absence verified.
- Registered guards and protected guard/Storage hashes passed before and after; both UUIDs matched registration. Final root available: **5208907776 bytes**, above 4 GiB STOP, with the under-6-GiB warning.
- `../env-facts.json` and `../phase-result.md` were published immediately after the values were observed, acknowledged before cleanup, then updated with verified cleanup. Initial publication is preserved under the VM observation directory.

## Preflight correction and boundaries

Original pre-create failure evidence and commit `52b5d5e` remain intact. The actual bounded Docker error identified absent `Config.Cmd`; the task-local formatter now returns null for missing optional fields. Missing JSON closing braces were also corrected. Immutable identity and runtime checks were preserved. No repository source fix or test suite was run.

VM originals: `/data/logs/q38env-20260915/observation-1`, root:root0700; report files root-owned0600. Only the authorized single noGPU/no-inference container was created. No image pull, model/key/source mounts, ports, GPU devices, network access, API call, environment predicate fix or auth receipt. Installer remains STOPPED. D3BASE's lease release did not expand this task's no-generation scope.

Next action: Root/Worker2 review the observed difference and separately own any subsequent source correction. Diagnostic completion provides no PASS_NATIVE or authentication acceptance.

Report packaging checks: exact retrieved facts match the immediately published local files; staged paths are report-only; quiet grep-based secret scan, commit identity and bundle verification. No push.
