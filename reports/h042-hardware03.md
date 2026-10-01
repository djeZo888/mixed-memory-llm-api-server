# H042 E-hardware03 — current read-only hardware evidence

Captured 1 October 2026: ai-vm18:51:48–18:55:43 UTC; ai-harness18:51:14–18:52:30 UTC. Base `369043838110bc4ed3c07423d916be8503a46c1c`; reviewed input bundle SHA256 `276a5c83c43287d2aab86f3a8e7fd36650ed6aafa978c8589478f9db48508002`. No operational GO. Only these two reports are changed.

## Answer

**CHA_FAN3 is not established as fixed.** Its controller on ai-harness is currently **failed**, MainPID **0**, Result `exit-code`, ExecMainStatus **78**, NRestarts0. The retained blocker is `competing_writer_or_overwrite`. Current configured duty, measured PWM, RPM and stable physical behavior are **NOT_TESTED**. Historical configured100 is not current readback or physical proof.

**Both Ada48GB cards are visible and have limited HEALTH_READBACK evidence.** Each reports49140MiB total/2MiB used, P8 and30% GPU fan, with stable Ada36°C/13.60W and returned Ada34°C/9.44W. No process is listed on either Ada. Both have remapped counts0, no remap pending/failure and no repair pending. ECC is disabled; corrected/uncorrected volatile/aggregate ECC and retired-page counters are **N/A**, not zero. No stress, inference or physical qualification occurred.

## Inventory and links

All fields are instantaneous NVIDIA readbacks (driver595.84). Fan is percent, memory is MiB, power is W. Serial values are pseudonymized in the JSON report; original nonsecret inventory XML/CSV is private0600.

| Guest index | Card/role label | Full GPU UUID | Guest BDF | Memory total/used | °C / fan% / state | Draw/limit W | NVIDIA link current/max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | stable Ada suffix14 | `GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf` | `0000:01:00.0` | 49140/2 | 36 / 30 / P8 | 13.6 / 300.0 | Gen1 x16 / Gen4 x16 |
| 1 | returned Ada suffix5d | `GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23` | `0000:02:00.0` | 49140/2 | 34 / 30 / P8 | 9.44 / 300.0 | Gen1 x4 / Gen3 x16 |
| 2 | Blackwell Blackwell Workstation Edition | `GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237` | `0000:03:00.0` | 97887/2 | 31 / 30 / P8 | 16.05 / 600.0 | Gen1 x16 / Gen5 x16 |
| 3 | Blackwell Blackwell Workstation Edition | `GPU-69acfa26-8b60-61b5-702d-aee252c163cc` | `0000:04:00.0` | 97887/34 | 32 / 30 / P8 | 30.03 / 600.0 | Gen1 x16 / Gen5 x16 |
| 4 | Blackwell Blackwell Server Edition | `GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528` | `0000:06:00.0` | 97887/61015 | 34 / {'unavailable': '[N/A]'} / P0 | 80.86 / 600.0 | Gen3 x4 / Gen3 x16 |

Power limit/default/enforced300W and min/max100/300W apply to both Adas. Stable Ada NVIDIA maxGen4 x16; returned Ada maxGen3 x16, currently idleGen1 x4. sysfs reports stable max16GT/s x16 and returned max16GT/s x16, with current2.5GT/s x16/x4 respectively. Preserve this difference between tools; no load or throughput test established a fault or performance qualification. The returned Ada's observed x4 width is a placement/performance constraint to investigate separately.

Guest `lspci` reports labels `0`, `0-2`, `0-3`, `0-4`, `0-6`; capabilities are access denied. sysfs `physical_slot` is absent for all five GPUs and guest slot directory matches exist. These are guest labels, not genuine chassis evidence. User physical **slot2/slot5 UUID mapping remains NOT_TESTED**; no host/Proxmox access was attempted.

## Intended roles versus actual placement

| Card | User's intended role | Current evidence |
| --- | --- | --- |
| Returned Ada `GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23` / `0000:02:00.0` | Qwen-Image-2.1 generation/edit | No GPU process,2MiB allocation; no loaded image model demonstrated. |
| Stable Ada `GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf` / `0000:01:00.0` | Qwen3.5-9B plus PaddleOCR-VL1.6 vision/OCR | No GPU process,2MiB allocation; no loaded vision/OCR model demonstrated. |

Only GPU `93dbfca8-ef3a-9628-a798-6a4afd0af528` lists a compute process: PID529415 `sglang::scheduler`,61006MiB. `/proc/stat` plus process stat records its birth02:37:21.290UTC, parent/PGID523760; parent birth02:37:03.690UTC. Executable links are permission denied and sanitized model arguments unavailable. NVIDIA process name is not executable-path proof. Image API CPU process PID11783 is `/usr/bin/python3.12`, birth02:13:47.690UTC; this is not GPU model-load proof. Docker read exits1 (socket permission denied).

Current protected active catalog and image config reads were denied. Existing metadata GETs `/v1/models` on30004 and `/v1/image-capabilities` on30006 returned401/exit22; credentials were not issued/refreshed and no inference endpoint was called. Visible artifact directory names include Qwen-Image, qwen38, H039 vision, MiMo and GLM; names alone do not prove loading.

Qwen-Image path `/data/models-large/qwen-image-2.1-790c92633540aa0cb11d9abf19eb46d861714758` exposes27files including7weight files: **AVAILABLE_NOT_EXERCISED**, presence/sizes only. Qwen3.5-9B/PaddleOCR candidate directories and original/H040-recovery status, manifests and artifact locks were permission denied: current completion **NOT_TESTED**. The retained handoff's36files/fiveweights completion is historical and was not requalified. No full weight hashing, replay, download or load occurred.

## Error scope and unavailable fields

Current guest-boot kernel journal read exited0, returned fewer than3000lines and included the02:13:26UTC boot. No `NVRM: Xid`, fallen-off-bus or PCIe AER error pattern matched in that accessible scope; AER enabled messages are not hardware errors. Accessible per-device sysfs AER counters are preserved in JSON and report0. Limits: retained/rotated journal scope is not complete device history or host error coverage; `dmesg` exits1 (Operation not permitted). GPU sensors tool is missing(exit127), with no installation.

Other kernel diagnostics are retained: four virtual hotplug `pci_hp_register failed` errors(-16), unsigned-module verification/taint warning, and headless DRM no-CRTC/no-compatible-format messages. They do not establish an Ada workload failure; no generic all-errors-zero claim is made.

## CHA_FAN3 current fault and limits

Installed source `/usr/local/lib/sova-cha-fan3/cha_fan3.py` SHA256 `77a451e94ea50534bcd3cb9c012bca54752f1e38f1fc5961c2b48c7003870aa3`; unit SHA256 `04f861f9c59caee51b6fc4f1e48b58cd5516c5705afd1dd230a1d5b788114a3b`. Reviewed replacement `85b39446d385975cc9b368dc082986bf8cf783c208a47be4a00cb789ea49297f` is **not installed**. Unit is loaded/enabled but failed; no controller process is running at readback.

Files were read now, but `status.json` telemetry is from14:41:54UTC: stateblocked, desired/readback duty100 and tach3600 with unitsnull. Its own kind is `first_four_curve_duties_not_measured_pwm`; none of these establish current measured duty or RPM. blocked latch remains `competing_writer_or_overwrite`; pending-write retained stateverified for the historical write. No clearing, CAS or helper invocation occurred.

No known usable protected existing BMC session was available in the narrowly inspected known paths; controller sessions are in-memory and controller PID0. **BMC NOT_TESTED: zero GETs, zero login/refresh/session creation/logout**. Password values were not read and Basic auth was not used. Fan sensors is missing(exit127), hwmon exposes no entries. Thus current duty/RPM and physical stable operation remain unavailable.

Bounded service journal query since12:00UTC with80-line cap returned four14:41:54UTC exit78/CONFIG/failure events and no later lines. Journal access was as user in adm without sudo; boot listings expose retained scope only. An initial local-time since query is preserved and corrected with an explicit UTC query. No configured duty or source review substitutes for physical stability; original cycling cause remains unresolved.

Policy is preserved: four integrated GPU cards at≥70°C command100%; CHA_FAN3 at70°C commands80% and strictly>80°C commands100%. Installed constants match HOT70/HOT_DUTY80/VERY_HOT80/HIGH_DUTY100. No action exercised this policy.

## Evidence, validation and closure

The companion JSON indexes private command receipts/logs under `../output`: exact sanitized argv, host/cwd, start/end UTC, integer exit and SHA256. Query scripts and original nonsecret outputs are0600 inside0700 directories and excluded from Git. Unsupported and permission-denied queries remain evidence. A successful enclosing SSH exit does not erase failed internal queries.

Report JSON validation, `git diff --check`, owned-file checks, bundle verification and export hash consistency are required and recorded in `../output/RESULTS.json` after sealing. No application build/test is needed for this report-only graph. Sova0.158.0/upstream064c and480000/400000/65536 are unchanged. No operational, actuator, model, dependency, pin or push actions occurred.

Fresh observed native SID `01a0f8cc-4a26-7743-95ab-20a125407d5e`; actual session metadata/settings confirm codex_exec CLI0.159.2, GPT6.1Sol/ultra, approvalnever, danger-full-access and this isolated cwd. Voluntary exit follows export; actual CLI/wrapper/outer terminal exits and exact birth/PGID process absence must be verified by root after this session closes. They are not prospectively claimed here. Outstanding qualification: physical slot mapping, fan stable/cycling cause, Ada workload/stress/throughput, current protected vision download completion and actual intended model placement.
