# Q38V fixture plan — ready for one unchanged helper launch

Published 2026-09-15T02:41:16.874490+00:00 before launch.
Root coordination Revision2 authorizes the already reviewed deployed corrected guard. The prior obsolete-checkout guard failure is preserved in `historical-old-guard-phase-result.md`; the fixture has not previously run.

## Exact source and provenance

- Reviewed commit `f17ec2c37d4c706752dd3fbe1978519983578b71`, tree `a667371eac8b46642ab87ff8e1d1be26ab501ca4`.
- Whole committed Git archive SHA256 `47f44a7aa1ef072728fe67e24bc312146e4dc1e5a29730c1b58b00660d5c95a3`; 535 tracked regular files, no symlinks/hardlinks.
- File manifest SHA256 `4bc0705e36531df5eedababbb3e5b1ff4eb66a0561346445fec6587619a6f5ac`; full local `source-manifest.json` and ai-vm `/data/q38v-20260915/source-manifest.json`.
- Snapshot `/data/build/q38v-20260915/source`; root-owned directory 0555 / file 0444 or executable 0555; task parent mode2700. Bind-root/files are readable to the exact helper container UID0 with dropped capabilities. Source root device 2065, inode 44302338.
- Provenance `1f0a49bcbfb0b499d0432b9d4b4b387f6fe5338e084e9e0f7c9578e6f77b1acd`; launcher `380da6ca383804f0cb1cad8bf037c9342e69558354ec42d911fb706db716d1be`; host fixture `9cdea022e21f1859e097be51094b9d2822dfc1387f8756448dd7b14d8a251d2c`; inner fixture `16a1e0b726295e0f0a9f046b5d496dae70f83677f5145ffdb52bfee01671b454`. All component hashes in `source-identities.json`.

## Exact launch

Worker: Mac-Worker1; transport `ssh -o BatchMode=yes ai-vm`; root process through `sudo -n python3 -B -`. Its only fixture subprocess argv is:

```text
python3 -B /data/build/q38v-20260915/source/tests/lifecycle/sglang38_fixture/run_fixture.py --repo /data/build/q38v-20260915/source --output /data/q38v-20260915/q38b-auth.json
```

Host `-B` prevents bytecode writes into the immutable source. The shipped container argv/resources/runtime flags are unchanged and are generated only by the helper. Contexts 131072/262144; image digest only; pullnever; NVIDIA runtime/none/compute,utility; CUDA_VISIBLE_DEVICES empty; HOME unchanged; networknone; readonly root/repo; capsALL dropped; pids128/memory8g/shm64m; no log driver; synthetic key/model/cache tmpfs only. No hand-rendered Docker launch or alternative fixture.

- Evidence directory `/data/q38v-20260915`: root-owned0700, protected ancestors, anchored output check passed, on exact data UUID. It is outside the uid1000/mode2775 `/data/build` ancestor; no shared permissions changed.
- Requested receipt `/data/q38v-20260915/q38b-auth.json` is new. Host stdout/stderr `/data/q38v-20260915/fixture.stdout` and `fixture.stderr`, root-owned0600; execution metadata `fixture-execution.json`.
- Exact verified data UUID `8daf56f1-5649-4163-9d87-919c2d271875`; model-volume UUID `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`. Exact root free bytes before stage 5,213,921,280 >4GiB.
- Reviewed guard release `/data/services/releases/7b541017c3e1b2bda80676bcd31bc87d0a4507bc-d3-20260915`; source/dependency hashes match that Git commit, protected executable root-owned regular single-link files. Direct data guard and root guard both PASS. The nested guard argv is adjacent `require-data-mounted.sh` with no arguments and unused output to `/dev/null`; no tmp workaround.
- Independent OCI verifier PASS: observed image `.Id` is exact `sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262`, domain `oci_platform_manifest`, Descriptor accepted by reviewed contract; config stays `sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813`; linux/amd64; source `0bcd822377da7b5718e674eaf9c870d349424dd1`. No pull.

## Result boundary

First fixture failure ends execution: retain bounded sanitized code/lifetime evidence, reconcile only exact helper-owned IDs with shipped checks, no rerun/source change/runtime diagnosis. Detailed inner origins may be unavailable because unchanged helper discards them. Postchecks: reviewed guards, exact UUIDs/root bytes, full snapshot hashes and identities. Registry absent; no registry creation/import/READY state. Model/GPU/native lifespan/live agent acceptance remain NOT_TESTED. GLM32K/Q38A/D3T and deferred Coder remain outside Q38V operations.
