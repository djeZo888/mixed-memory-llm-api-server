Narrow source repair READY FOR ROOT REVIEW; no repair deployment/relaunch/GLM restore.

-19 focused owner tests PASS, including actual supervisor-loop pending socket timeout, dedicated mandatory deadline fatal inside readiness, both guard timeouts fatal outside readiness, and actual SIGALRM deadline type.
-Original owner regression reproduces fatal ordinary socket TimeoutError offline. Original production start cause remains UNPROVEN because logging discarded its exception.
-Only owner exception distinction plus this ordinary unit stdout/stderr journal; no guard/reserve/lease/config changes.

Owner SHA256: `7768181c10bb35c7fcaa02d243913aaedf9ff7396416252b826dc2bbdb814a2c`
Unit SHA256: `c0c260e2fd554fc74ab045d072bdfa902780d05fa23b88f69f6324079e40573a`
Patch SHA256: `b6debcdfa5989507c52365d56a1ba0c67120ca70442ab30cce008dfeaea8157f`
Proposed canonical manifest: `c2d4cb314ce86a6c082faf784a5c3c55a6bb95acc1056f43f8baaeaa43f9016b`

Taskroot ROOT-REPAIR.patch contains exact owner/unit/test diff; its digest is preserved here. REPAIR-TESTS.txt and REPAIR-REGRESSION.json retain results. Proposed transition preserves failed raw records before exact removal of container144757b104c97ffad8d05158e93f1abcb929d34083a1a944c5690e0e801e7fdc, then3source-pin replacements and genuine next generation3. Root must separatelyGO actual guarded transition and one corrected launch by17:55. Readiness cutoff18:10 unchanged; no inference.
