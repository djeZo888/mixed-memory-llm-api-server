# Retained diagnostic source, not production installation

These files preserve exact executed probes for attribution. D02 and D03 runner
snapshots are `.txt` because they include subsequently-corrected orchestration
bugs: D02 lacked in-container timeout settlement; D03 used VRAM bytes as part of
GPU process identity and correctly failed closed but required explicit thaw.
D04 uses bounded in-container timeout and UUID/PID-only comparison before thaw.
All future probes must re-read current state, use distinct ledger entries/paths,
and preserve the six-GPU-call budget. Never blindly execute a retained runner.
No helper touches text services or restarts the backend. The final production
candidate is solely protocol.py's missing-edit-seed default/response metadata;
these probes are not deployed service code.

D05/D06 files retain the exact executed probes and guarded runners. No backend/source deployment occurred. Each ran one request with in-container TERM840s/KILL5s plus outer855s bounds. Thaw required successful HTTP200/decoded PNG, absent probe process and unchanged native UUID/PID; native inference would not be assumed settled merely from HTTP-client termination. prepare_d05_fixture.py records the explicitly authorized CPU-only test sample preparation. verify_final_evidence.py compares actual receipts and raw/delivered pixels; it makes no model request.
