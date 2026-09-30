# Hardware producer entry correction — source-only

Checkpoint: 2026-09-29 08:32 UTC. Base 4faeb803d3fcad19d7b3f13bed9c34504c85f7e4.

The deterministic fixture establishes a scheduling defect, not the historical 08:22:36 cold failure cause. A fresh exact-GPU receipt is available while the retained proof is 14.95 seconds old. One transient canonical lease-entry refusal causes the original HardwareEvidenceCollector to skip its entire scheduled refresh; 0.1 seconds later the retained proof correctly projects null. The original fixture fails with `None is not False`; evidence is HARDWARE-BEFORE.txt. The next normal scheduler slot is five seconds away (passive.py POLL_SECONDS).

The correction retries only LeaseBusy from context entry, sleeping at most 25 ms between attempts within the existing callback deadline. No lease is held during waiting. Binding receives only the remaining budget, and budget checks precede existing persistence calls. Once entry succeeds, body failures propagate without replay. No deadline/TTL enlargement, negative-proof relaxation, positive-latch change, extra GPU probe, model action, or deployment is included.

Focused verification: `PYTHONPATH=scripts python3 -m unittest tests.test_node_hardware_wiring tests.test_node_projection`: 27 tests PASS in 0.024 s; `git diff --check` passes. Coverage includes transient refusal and refresh, persistent contention exhausting the two-second callback budget, no acquired-body replay, no retries on non-contention entry error, no persistence after late acquired entry, and existing proof/latch/projection tests. These are local deterministic fixtures, not live acceptance.

Files: scripts/control/node_collectors.py and tests/test_node_hardware_wiring.py. Exact exported diff: HARDWARE-CORRECTION.patch, SHA256 823dd3ccc727cd8ecb95f257340b2c4255463e1015e4bb4359dbc97075e1d888. Before output SHA256 8c9106505b5810517f01212783f27beaf8024dd99a159ccd14885ae677e0cacd. After output SHA256 bd002a2395bf6758bdeb798d15a7140d7773682fe78b7df203c270437eee06bc.

Deploy proposal: defer. Parent reports the current MiMo manifest pins node_collectors.py and source_preflight checks that closure. A changed node producer needs an explicitly reviewed source-closure transition; this patch has not changed deployed files, pinned manifests, services, or resident ownership. Ordinary maintenance and specialist admission holds remain.

Separate source observation, deliberately not changed: CanonicalIdentityReader starts timing at node_observation.py:441 before binding/latch reading (:458-459); read_latch_status computes its base proof age later at hardware_policy.py:170, and :573 then adds elapsed time from the earlier start. This conservatively overcounts the pre/latch interval. Readiness aging (:804,858) and cache residence (passive.py:70,117) cover distinct subsequent intervals. Missing historical proof-age metadata prevents attributing the cold failure to this overcount or entry contention.

Diagnostic limitation: node.py:200-211 omits validation-age/boot/GPU proof fields; app projection maps their absence to null. The captured integer generation and ready-true prerequisite narrow the compatible producer paths, but do not choose among readable missing/stale/future/wrong-boot proof or later age expiry. No historical cause or live fix is claimed.
