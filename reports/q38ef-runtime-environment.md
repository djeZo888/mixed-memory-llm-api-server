# Q38EF — measured inner environment correction

Status: source correction; actual final-image/native/auth/model acceptance NOT_TESTED.
Reviewed base: `e8d8bbad3f2f6345295d440b25f084fed83dc734`.
Scope: Mac-Worker2 source only; exactly GLM5.3 + Qwen3.8. Installer STOPPED;
Q38LS implementation HELD. No VM access, diagnostic retry, inference requests,
model/image/build/download, runtime mutation, or service work occurred.

## Measurement and source rationale

Supplied Q38ENV `env-facts.json` and `phase-result.md` record the separate
2026-09-15 04:02:10Z observation:

| Variable | Host Docker Config.Env | Python parent | Direct inherited child |
| --- | --- | --- | --- |
| `NVIDIA_VISIBLE_DEVICES` | literal `none`, one occurrence | `void` | `void` |
| `NVIDIA_DRIVER_CAPABILITIES` | `compute,utility` | `compute,utility` | `compute,utility` |
| `CUDA_VISIBLE_DEVICES` | empty | empty | empty |

That one diagnostic exited 0 with zero stderr bytes and verified exact-container
quiescent removal. It created no auth receipt and provides no native/model
acceptance. Q38VR2 did not record individual environment values; this observation
does not establish those earlier values or their cause.

Official NVIDIA Container Toolkit [v1.19.1](https://github.com/NVIDIA/nvidia-container-toolkit/releases/tag/v1.19.1),
commit `09ceee5dde66ba9ce25c7cc69b1ebd5e6e3266fa`, appends
`NVIDIA_VISIBLE_DEVICES=void` when generating CDI common environment edits in
[`pkg/nvcdi/wrapper.go`, lines 86–94](https://github.com/NVIDIA/nvidia-container-toolkit/blob/09ceee5dde66ba9ce25c7cc69b1ebd5e6e3266fa/pkg/nvcdi/wrapper.go#L86-L94).
This general source mechanism is consistent with the measured boundary. It does
not establish which runtime mode produced Q38ENV; that metadata was unavailable.
The bounded primary-source lookup ended there.

## Exact change and preserved gates

Only the inner cache-probe predicate admits exact `none` or `void`. It reads the
existing process environment without modifying it. Capabilities must remain
exactly `compute,utility`; CUDA visibility must be present and exactly empty.
Absent/empty/all/numeric/UUID/whitespace/other NVIDIA values remain refused.
Host create and inspect remain literal `none`, with no DeviceRequests or host
GPU devices. Independent private tmpfs, readonly root, directory ownership/mode,
empty model/secret mounts, no GPU nodes, native torch zero GPU, driver libraries,
cache paths/writes, source pins, auth/native prompt, lifetime, PASS and receipt
gates remain intact, including safe nonzero/unknown failure diagnostics.

Freeze order: fixture executable bytes, cache hash in fixture provenance,
provenance digest in the adapter, then only the three affected existing L2 hash
entries. No closure membership change; all other L2 values and D3RD GLM snapshot
and evidence bytes are preserved. No Manager/runtime/deployment/launcher/model/
control behavior edits; AGENTS.md and D3TC-owned files are untouched.

## Verification and handoff

PASS: 140 focused worker tests, including both inner values, invalid literals,
independent isolation gates, literal-none host create and host-inspect void refusal:

```sh
python3 -B -m unittest \
  tests.lifecycle.test_qwen38_{cache_probe,cache_diagnostics,fixture_diagnostics,fixture_lifetime,image_fixture,native_wire,final_source} \
  tests.lifecycle.test_sglang38_file_auth tests.lifecycle.test_qwen38.AuthEvidence -v
```

PASS: whitespace and exact scope/hash review. The initial test run exposed a
shared host constant dependency; preserving the original literal-none constant
fixed it before the final ordered hash freeze and successful 140-test rerun.
Warnings: runtime mode remains unobserved; installed-image/native/auth/model
acceptance is NOT_TESTED here.

Post-commit and imported-bundle verification command (results in external handoff):

```sh
python3 -B tests/lifecycle/verify_qwen38_git_source.py --repo . --commit HEAD
```

Final checks read frozen hashes without regeneration.
Synthetic collaborators in worker tests establish source controls only, never an
installed-image or native PASS.

Next action: root reviews the committed source/full bundle; Worker1 then executes
the unchanged actual fixture pair on that final source under root coordination.
No new diagnostic is authorized by this report. Stop after bounded handoff.
