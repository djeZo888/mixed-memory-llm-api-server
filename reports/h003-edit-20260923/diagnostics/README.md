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
