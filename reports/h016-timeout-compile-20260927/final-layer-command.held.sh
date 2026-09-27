#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then echo 'HELD final single-layer recipe. Requires W1 actual context/winner, qualification and root review.'; exit 0; fi
echo 'HELD: actual W1 configuration and complete native/application checks are still pending.' >&2
exit 78
# Inert concrete command for root review only; no build or activation in COMPILE14.
H016_FINAL=/home/user/ai-harness-build/H016-TIMEOUT-COMPILE-20260927
cd "$H016_FINAL"
python3 artifact-guard.py > pre-final-layer-guard.json
sha256sum -c FINAL-INPUTS.SHA256SUMS
# Root must separately validate the reviewed W1 qualification using existing
# validateMimoIntegration/validateCapacity and pin identical host/image bytes.
# The actual active-frontier.json and final review hashes are intentionally absent.
test -s payload/opt/ai-harness/config/active-frontier.json
podman build --pull=never --network none --layers --format docker --jobs=1 \
  --file Containerfile.held --iidfile final-combined.iid .
python3 artifact-guard.py > post-final-layer-guard.json
# Do not tag, install, activate, or extend app deadlines from this recipe.
