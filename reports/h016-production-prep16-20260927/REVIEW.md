# Prep16 source review

The only runtime delta from 85e438895ddeef593ac721e2872eb2cd7f1559d9 is three added client lines binding the raw status line to the exact reviewed HTTP/1.0 429 response. Root inspected the complete diff and actual socketpair plus actual run/reader/settlement regression. Existing positive BUSY, callbacks, unknown settlement and terminal full-drain ordering remain unchanged; no per-delta work was added. HTTP-FIX-CHECKS.json records 38 focused tests plus seven W2 negatives.

Independent ordinary-owner review found the retained control-api guard/lease/latch import closure requires exact installed source binding in addition to the new node-api source map. No retained source is replaced here. The inactive procedure must make that missing closure explicit.

The real owner CLI has no stage/install/select-MiMo command. Its supervise --dry-run already requires a qualified manifest and selected MiMo; check-selected is only a predicate. Rollback uses rollback-glm --dry-run then rollback-glm only after exact settlement/no request hold. The existing rollback changes selection and starts the preserved GLM owner itself.

The saved R9 checkpoint has no cgroup memory.peak value; its sampled memory.current maximum cannot satisfy a peak claim. Charged cache must not be added a second time. All production templates remain non-authorizing until missing fields and final winner are root-reviewed.
