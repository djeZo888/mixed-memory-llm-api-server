#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then echo 'Compile retained CLI/probe bundles offline in owned artifact dir; no image build.'; exit 0; fi
umask 077
H016_COMPILE=/home/user/ai-harness-build/H016-TIMEOUT-COMPILE-20260927
cd "$H016_COMPILE"
trap 'rc=$?; trap - EXIT; printf "%s\n" "$rc" > compile.exit; date -u +%FT%TZ > compile.finished; exit "$rc"' EXIT
python3 artifact-guard.py > pre-compile-guard.json
date -u +%FT%TZ > compile.started
cmp build-native-probes.mjs accepted-build-native-probes.mjs
timeout --signal=TERM --kill-after=10s 240s podman run --rm --network none --read-only --name h016-timeout-compile14 --entrypoint /bin/bash -v "$H016_COMPILE:/work:rw" -w /work/native-source sha256:cde82ffa870c45f8b4396b19a74fe0ad31fdc50b60a2ecbad9d1a29a7cd1f813 -c 'set -euo pipefail; node --version; node -e '\''console.log(require("esbuild/package.json").version)'\''; MCODE_RELEASE_TAG=v0.5.1 node scripts/h016-compile-only.mjs; node /work/build-native-probes.mjs /work/native-source /work/native-probes.mjs' > compile.log 2>&1
python3 artifact-guard.py > post-compile-guard.json
