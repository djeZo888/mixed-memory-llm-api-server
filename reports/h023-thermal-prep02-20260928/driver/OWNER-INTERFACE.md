# Fixed current-value contract

`contract.py` validates required policy; `deployment.example.json` is a non-runnable placeholder. `native.py` implements fixed bindings, not configurable RPC/shell callbacks. Source-reference owner_contract fields are documentary only. Auth_ref must name the existing protected inference-key path; never include key contents.

Manifest: schema/task/current review marker; current boot/deployment/capture time; deployed manifest hash; fixed native.py adapter hash; full source closure path→sha256; per-lane exact endpoint/model/runtime/GPU UUID/type/family/current power+ECC/reserve/critical baselines; phase bounds; chosen external curve75/75/75/75/100 OR separately reviewed100/100/100/100/100. external_fan_readback must include source, evidence_ref, actual observed UTC, raw tach, unknown units, and explicit snapshot label. Driver makes no fan/TDP writes.

Lane identities are structured actual values emitted by native.identity():
- MiMo: native_identity(c), actual supervisor tuple, proxy{pid,pid_start_ticks,parent_pid}, launch_id, container identity, canonical current production manifest digest as policy.
- Qwen: container identity, current slot generation, actual slot.container object as runtime_profile. Existing slots qwen0=glm and qwen1=qwen are fixed source-backed bookkeeping keys.
- Image: container identity and actual owner run_id.

Container identity: Id,Image,StartedAt,Pid,cgroup,pid_start_ticks. No supervisor/proxy/launch/lease fiction for Qwen/image. W1 must supply fresh native/container identities and compare live before execution. MiMo proxy absent while LOADING blocks the four-way phase.

Text corpus per lane: protected absolute path+sha256, bounded2MiB; each request adds a fresh leading prefix BEFORE count. Corpus fitting is not attempted. MiMo uses canonical inference body on /v1/chat/completions/input_tokens. Qwen uses /v1/tokenize with only stream/stream_options removed; validates count==len(tokens), retains both body hashes, token IDs hash and reviewed template_sha256. Supply exact capacity_readback mapping from get_server_info confirming480000 and unchanged runtime output ceiling. MiMo output ceiling65536 is distinct from per-request<=128.

Qwen completion_contract=`PINNED_ADAPTIVE_DRAIN_FULL_RESPONSE_EXCLUSIVE_OWNER`; full response + exact identity + exclusive root admission labels REQUEST_SETTLED, never scheduler-global idle. Image completion_contract=`PINNED_IMAGE_OWNER_NATIVE_EOF_PUBLIC_OUTPUT_CLEANUP`; full decodedPNG/native EOF and actual API busyfalse/admittingtrue, unchanged owned run tmp_snapshot. No synthetic native jobID. Changed spool content stops admission and stays owned; cleanup_tmp is only allowed inside existing failed-lane reset_owned after backend removal.

GO: action `ROOT GO H023 PHASE A` or B; phase, task_id, unique go_id, boot_id, deployment_sha256=canonical manifest hash, package_sha256=driver source hash map digest, quiet_confirmed=true, exact global_admission_receipt, independent systemd unit, not_before_utc, admission_deadline_utc (<=300s window), settlement_deadline_utc (bounded manifest extension). One grant per phase; batch grants reject. Existing phase journal rejects replay. No per-request permission gate.

Source review targets: native.py fixed imported modules/guard closure; actual configured count/template/capacity fields; image exact spool snapshot contract; stop owner outputs; workload completion budget and telemetry delay. No current credentials or private token contents belong in reports. W1 supplies values and reviews bindings; no new observer or permit service is needed.
