# H031 ACTIVATE02 — MiMo refused; image not ready with unresolved native

The six reviewed runtime paths were installed at **09:51:58 UTC** and SOURCE02 reconciled at **09:55:04 UTC**. One MiMo start and one supervised image API start were submitted at **09:55:17 UTC**. **MiMo refused its start and never reached LOADING. Image subsequently failed its startup/recovery; the final API state is closed, ready=false, admitting=false.** At **09:57:40 UTC**, the image native container was still running despite failed backend ownership and unresolved active operation/recovery records. No further lifecycle actions or retries were performed.

| UTC | Completed phase |
| --- | --- |
| 09:49:38 | Exact boot, stopped state, six old pins, original intent/delta, generation 12, image/node/Qwen identities and idle image verified. |
| 09:51:11 | Protected SOURCE02 staging and 27 packet checksums verified; only corrected immutable inputs installed while old runtime pins remained. |
| 09:51:15 | Timeout supplement prepared on its first invocation with physical absence and strict negative hardware proof enforced. |
| 09:51:36 | Existing image API/backend stopped normally once; exact old image container removed and native PID absent; node stopped for installation. |
| 09:51:58 | Protected predecessor backup and per-file atomic CAS installed exactly six approved paths; frozen MiMo state unchanged. |
| 09:52:02 | Node started once: PID `1590070`, invocation `941f3b29804f4983981c2fa9dc8023be`. |
| 09:52:18 | Fresh negative hardware proof matched boot/GPU identity, age 630 ms. |
| 09:52:22 | Initial reconcile refused at `acquire_lease.__enter__` with `LeaseBusy`, before its body. Execution paused. |
| 09:53:06 | Readback confirmed six new pins, frozen state/selection, original intent/delta/supplement, and no new archive/receipt/consumed files. |
| 09:54 | Root explicitly clarified the bounded entry-only retry grant also covers reconciliation. |
| 09:55:03 | Fresh proof again confirmed unchanged tuple/state and absent transition files before the further invocation. |
| 09:55:04 | First authorized further invocation reconciled successfully, retaining generation 12 and selecting corrected canonical manifest `9315a02f...a9e9`. |
| 09:55:17 | One MiMo and one supervised image API start submitted; backend not directly started. |
| 09:55:18 | MiMo supervisor refused with `lifecycle_busy`; ExecStopPost refused with `recovery_invocation_changed`. |
| 09:56:00 | Initial ownership: MiMo failed/MainPID 0, unchanged SETTLED state and unconsumed receipt; image parent/child/native loading. |
| 09:56:48 | Image start failed `image_operation_changed` during `telemetry_verify`. |
| 09:56:50 | Image recovery failed `owned_systemd_restart_warm_failed`; settlement `image_operation_unresolved`. |
| 09:57:40 | Final API closed/not ready; native image still running, backend failed, owner process scan empty and active records unresolved. |

The supplement SHA256 is `8a9597d54cdb1adcebf2e7fb9b6987653a6a994f099ad46ec5057f9ca625844a`. The accepted transition is `SAME_BOOT_IDLE_STOP_TIMEOUT_SETTLED`, with prior disposition `IDLE_STOP_TIMEOUT_PHYSICALLY_SETTLED`. Supported owner code created archive SHA256 `a2d1b5c58611cd9d98be68d4be3279548f6a7d53bbe899b168da2660ab328a47` and amended selection. Original state `b1ba8b36...fa7420`, intent and delta are preserved in the transition chain. Both historical failures remain: `owner_interrupted` at 09:24:39 and settlement `command_timeout` at 09:24:47. No MiMo stop was repeated; no fault, latch, history or uncertain ownership was cleared. The initial entry refusal remains retained separately from the successful further invocation.

MiMo journal records supervisor `REFUSED`, phase `CLI`, code `lifecycle_busy` at 09:55:18.415682 UTC and ExecStopPost `recovery_invocation_changed` at 09:55:18.478603 UTC. Unit invocation `a2ae1474e0d24ecaa111a6382290fc23` is failed, exit 255/MainPID 0. The competing lock holder was not sampled and is not inferred. Archive and receipt exist; consumed receipt is absent. Old stopped state and both original failure records remain unchanged, while selection retains the reconciled canonical manifest. No new MiMo native owner exists.

The initial image parent/child ownership at 09:56:00 did not settle successfully. Backend invocation/run `6e8aa276397a451cb5a480b2c0aa90ea` failed with exit 1/MainPID 0. The final owner-process scan found no recovery/start processes. Native container `d66478c5449611e521af17e918b8929c0d7d2d0a6526788d9ed55386b57cd539` remained running as PID `1661054`, started 09:55:35.757660444 UTC. State records `phase=warm`, `warm=true`, but these fields do not establish readiness: the image API reports closed, not ready and not admitting. The operation remains active with recorded PID `1656742`, token `868d9b48784b44f4b702b52c05655a65`; recovery remains active in settle with recorded PID `1655508`, token `83be8882e6374f3fbc3918de6bc5107c`. These are unresolved records, not claims of living parent/child owners. No cleanup, restart, fault clearing or recovery replay followed.

Source closure path lists, model/runtime/GPU/flags and all three Qwen container identities, PIDs and start times remained unchanged at the final observation. Current node observations show both 480K Qwens ready with hardware_latched=false. These observations do not qualify a workflow; no cold/PDF or specialist acceptance was run. No inference, readiness acceptance, capability opening, app/config ticket write or baseline restoration occurred. Root owns disposition of the failed MiMo start and unresolved image native ownership. No more mutations after the single starts; no loading wait or further lifecycle action remains authorized to W1.

Provenance is separate: W1 image source `752ecebc12ff439f7813197620522fab80f696dd`; W2 SOURCE02 `b2ecf727d1a5192e5e791db4b088ef9b9a3ee865`, bundle SHA256 `53f35c6aa32af3e8968f87b9ed926c124c3092d817723e3dc120c3e2cda9f585`; isolated retained base `b502a1288443f7871225f76d3e8cab5b611b8fb9`. SOURCE01 and SOURCE02 were imported locally as `4661de9cc897cc93f2b6c20cc10b1c6fd988124a` and `04651d0d3488163492cb75bd82243f513c9570aa`; their original provenance is retained. Prior 83 W1 and 54 W2 focused source checks were retained, not rerun and not live qualification. RESULT.json contains exact pins, phase receipts and identities; raw state and stderr remain private outside Git. ACTIVATE01 scratch, predecessor files, original inputs and failures remain preserved.

Root's 09:59 conditional authorization for one MiMo start required image fully READY. That condition was not met; no additional start was submitted. W1 closes with no more live actions.
