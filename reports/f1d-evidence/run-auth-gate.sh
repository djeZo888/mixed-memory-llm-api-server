#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == --help ]]; then
  printf '%s\n' 'Run only the reviewed F1S synthetic-sentinel gate in the pinned installed image.'
  exit 0
fi
[[ $# == 0 ]] || exit 2
RUN=/data/build/f1d-qwen-20260915
export TMPDIR=$RUN/tmp
export PYTHONDONTWRITEBYTECODE=1
test "$(findmnt -rn -M /data -o UUID)" = 8daf56f1-5649-4163-9d87-919c2d271875
test "$(findmnt -rn -M /data/models-large -o UUID)" = a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a
cd "$RUN/reviewed-source"
test "$(git rev-parse HEAD)" = e46c788534d5b71e988c2cdf188f37f6214f7514
test -z "$(git status --porcelain)"
scripts/common/require-data-mounted.sh > "$RUN/evidence/auth-pre-mount.txt"
scripts/common/root-disk-guard.sh --report "$RUN/evidence/auth-pre-root-guard.md"
sudo -n docker image inspect sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3 --format '{{.Id}} {{.Architecture}}' > "$RUN/evidence/auth-image.txt"
set +e
sudo -n docker run --rm --pull never --runtime runc \
  --network none --read-only --log-driver none \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --env NVIDIA_VISIBLE_DEVICES=void --env CUDA_VISIBLE_DEVICES= \
  --env DISABLE_OPENAPI_DOC=1 --env HF_HUB_OFFLINE=1 --env TRANSFORMERS_OFFLINE=1 \
  --env HF_HOME=/cache/huggingface --env XDG_CACHE_HOME=/cache \
  --env TRITON_CACHE_DIR=/cache/triton --env TORCHINDUCTOR_CACHE_DIR=/cache/torchinductor \
  --tmpfs /tmp:rw,nosuid,nodev,size=512m \
  --tmpfs /cache:rw,nosuid,nodev,size=512m \
  --tmpfs /models:rw,nosuid,nodev,mode=0755,size=16m \
  --tmpfs /run/secrets:rw,nosuid,nodev,mode=0700,size=64k \
  --mount "type=bind,source=$PWD,target=/fixture,readonly" \
  --workdir /fixture --entrypoint python3 \
  sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3 \
  /fixture/tests/lifecycle/sglang_fixture/run_pinned_image.py --actual-image --repo /fixture \
  > "$RUN/evidence/auth-gate.stdout" 2> "$RUN/evidence/auth-gate.stderr"
AUTH_EXIT=$?
set -e
printf '%s\n' "$AUTH_EXIT" > "$RUN/evidence/auth-gate.exit"
scripts/common/require-data-mounted.sh > "$RUN/evidence/auth-post-mount.txt"
scripts/common/root-disk-guard.sh --report "$RUN/evidence/auth-post-root-guard.md"
cat "$RUN/evidence/auth-gate.stdout"
printf 'auth_gate_exit=%s\n' "$AUTH_EXIT"
exit "$AUTH_EXIT"
