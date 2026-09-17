# Q38RETRY device-name finding — one authorized observation

**Only violating path: `/dev/nvidia-caps`, directory, mode0755, st_mode16877, rdev0 (major0:minor0), uid0/gid0. It is not a symlink.** No unexpected path was deleted or changed.

Observed2026-09-17T04:38:06.837507Z. Initial container and auth-failure child cache ENTRY and EXIT inventories contained only the four allowed character devices. `/dev/nvidia-caps` was still absent after torch/model-config/serving imports and parser/template checks. It first appears at the next recorded boundary: parent after `warmup-auth-failure` exits. The precise creating function is not observed; first appearance is bounded between that child's parser/template snapshot and termination.

The next `warmup-timeout` child sees the same directory before its cache probe. Its FIRST `verify_isolation()` invocation (`cache_verify_entry`) rejects the unchanged name-subset predicate. It never reaches exit isolation, its own native cache imports, launcher setup or watchdog. Auth-failure child exit1/stdout exact40B marker/stderr0 satisfies all clauses; timeout child exit2/stdout331B closed FAIL with `gpu_device_node_present`/zero markers/stderr0 fails exit+marker clauses. Child order, original predicates and all timeouts remain unchanged.

| Relevant path | Type | Mode | Major:minor | uid:gid | Policy |
|---|---|---|---|---|---|
| /dev/nvidia-modeset | character | 0666 | 195:254 | 0:0 | allowed |
| /dev/nvidiactl | character | 0666 | 195:255 | 0:0 | allowed |
| /dev/nvidia-uvm | character | 0666 | 511:0 | 0:0 | allowed |
| /dev/nvidia-uvm-tools | character | 0666 | 511:1 | 0:0 | allowed |
| /dev/nvidia-caps | directory | 0755 | 0:0 (rdev0) | 0:0 | refused |

Actual Docker metadata: runtime nvidia; DeviceRequests null, Devices[], DeviceCgroupRules null; Privileged false; CapDrop[ALL]; no-new-privileges; read-only root; network none; memory8GiB; pids128; exact core soft1/hard1. Existing driver validation also confirms noGPU requests/maps, visibility literal none at create/inspect and empty private model/secret tmpfs. Inner environment is observed NVIDIA_VISIBLE_DEVICES=void, exact compute,utility capabilities, empty CUDA_VISIBLE_DEVICES and OpenBLAS threads1. The directory is not itself a GPU character device. Its presence does not establish actual GPU exposure, access or execution. No access probe was performed, and directory children were not enumerated because the original failed predicate inspects immediate /dev names.

Source base357358ab, current task-only observer adds snapshots to fixture runner/cache probe plus matching diagnostic provenance; production launcher and host containment remain exact unchanged bytes. Original exact-source FAIL and preceding diagnostic/history remain unchanged. This is diagnostic evidence, never auth/model acceptance. No native pair rerun, model load, production publication, guard relaxation or auth receipt.

Owned container2c3bc0dee123999b84eaf03bdc554bec40e7a12c773fca8470be2146b7fb9da1 / q38b-fixture-1949194761d85717ecb995adf34736e7 removed normally, independent ID/name absencePASS. PostguardsPASS, all backend containers stopped, no new/changed Apport. Canonical lease released2026-09-17T04:38:07.406178Z; SSH exit0 and worker request context exited. VM/request ownership released; same session remains available for concrete root follow-up.

Complete13 snapshots, all safe lstat operands, child predicate facts, actual noGPU metadata and cleanup are in `device-name-operands.json`. Raw child/native streams remain private under `worker-private-device-observation`. VM files retained at /data/build/q38retry-20260917/device-observation/source and /data/logs/q38retry-20260917/device-observation. Worker2 can now analyze the concrete `/dev/nvidia-caps` directory without guessing a per-GPU device or weakening policy.
