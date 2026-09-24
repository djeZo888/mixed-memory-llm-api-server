# Bounded reference reproduction source

Historical, actually executed one-shot comparison only. No server/API/production changes.

- Dockerfile is the exact successfully built immutable derivative of the accepted SGLang image. It removes SGLang only from the derivative and installs exact Diffusers commit plus Transformers5.17.0. Actual resolved dependencies and new wheel hashes are frozen in requirements.freeze.txt and DEPENDENCIES.json.
- remote_common.py imports the unchanged installed registered-storage/lifecycle helpers and validates runtime/config identity.
- build.py runs the GPU-free independent build without holding the canonical lease during long work.
- trial.py stops the exact owned image service outside its lease, then creates one constrained Ada container under the canonical lease and existing anchored storage/telemetry contracts. No Qwen lifecycle action. One container lifetime bound900s; all exit paths settle the recorded owned container.
- reference_edit.py performs exactly one prescribed call and preserves native defaults, allocator measurements and failure evidence.
- verify_close.py verifies restored SGLang warmth, unchanged Qwens, stopped reference and released lease; it does not perform inference.

Input fixture is supplied separately, exact SHA2569756c58b989a7656162e8777bb98fcd20671c58a9c79ae4c2d1744a63fb0d575. Exact model checkpoint already exists on registered storage; no download. Paths/session/deadline are fixed to the executed task and refuse replay. A fresh task requires explicit root authorization and its own owned paths/deadline.

Known blocker preserved, not silently repaired: trial launch lacks TRITON_CACHE_DIR and default Transformers rotary Triton cache creation fails on read-only /home/ubuntu/.triton. There was no completed edit or visual qualification. No repaired launcher or second run is included. Existing fixed SGLang recovery completed separately. Exception path failed to preserve exact failed-call duration; do not infer it from combined container wall time.
