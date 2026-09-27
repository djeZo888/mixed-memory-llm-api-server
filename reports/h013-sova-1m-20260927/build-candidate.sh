#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then echo 'H013 isolated exact source build; no production mutation or inference'; exit 0; fi
umask 077
H013_TASK=/home/user/ai-harness-build/H013-SOVA-1M-20260927
export PATH=/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/bin:/bin
cd "$H013_TASK"
H013_SOURCE=$(cat source.commit)
[[ "$H013_SOURCE" =~ ^[a-f0-9]{40}$ ]]
[[ $(node --version) == v24.21.0 ]]
python3 preservation.py "$H013_TASK/before.json"
trap 'rc=$?; trap - EXIT; printf "%s\n" "$rc" > "$H013_TASK/build.exit"; date -u +%FT%TZ > "$H013_TASK/build.finished"; exit "$rc"' EXIT
sha256sum -c source.SHA256SUMS
if [[ ! -d source ]]; then mkdir -m 700 source; tar -xf H013-source.tar -C source; fi
python3 - <<'PYSOURCE'
import hashlib, pathlib, tarfile
with tarfile.open('H013-source.tar') as t:
 for member in t.getmembers():
  if member.isfile():
   p=pathlib.Path('source')/member.name
   assert p.is_file() and not p.is_symlink()
   assert hashlib.sha256(p.read_bytes()).digest()==hashlib.sha256(t.extractfile(member).read()).digest(),member.name
print('PASS exact archived source content')
PYSOURCE
cd source/ai-harness
for part in server web; do
 donor=/opt/ai-harness/releases/296ae49e44eb250773223885b843994e2c5b9bcc/ai-harness/$part
 if [[ "$part" == web ]]; then donor=/home/user/ai-harness-build/H008-296ae49-03/web; fi
 cmp "$part/package.json" "$donor/package.json"
 cmp "$part/package-lock.json" "$donor/package-lock.json"
 [[ -d $donor/node_modules && ! -L $donor/node_modules ]]
 if [[ ! -d $part/node_modules ]]; then cp -a "$donor/node_modules" "$part/node_modules"; fi
 (cd "$part"; npm ls --all --offline; npm run typecheck; npm run build) > "$H013_TASK/$part-build.log" 2>&1
 done
(cd server; npm test) > "$H013_TASK/server-tests.log" 2>&1
(cd web; npm test) > "$H013_TASK/web-tests.log" 2>&1
(cd server; node --input-type=module -e "await import('./dist/app.js'); await import('./dist/gateway.js'); console.log('PASS ordinary user actual dist imports')") > "$H013_TASK/imports.log" 2>&1
node --test deploy/engine/configure-profile.test.mjs > "$H013_TASK/profile-linux.log" 2>&1
python3 "$H013_TASK/preservation.py" "$H013_TASK/pre-engine.json" --compare "$H013_TASK/before.json"
cache_root=/home/user/ai-harness-h003-engine-mcp-build-20260923
mkdir -m 755 "$H013_TASK/artifact-cache"
cp -a "$cache_root/artifact-cache/code-0.3.11.tgz" "$H013_TASK/artifact-cache/"
echo 'd2e160be6081dd69b48da661bc6f9a6e049d258cbd0b3121ef1185d7ece52662  '"$H013_TASK/artifact-cache/code-0.3.11.tgz" | sha256sum -c -
echo '10b0cf0dad31303eff83a73108640e83371f826b64cff9ed3df5d3ead3462c3d  '"$cache_root/native-deps-cache/package-lock.json" | sha256sum -c -
timeout --signal=TERM --kill-after=30s 720s podman --remote=false build --layers --format docker --pull=never --network none --target runtime --volume "$H013_TASK/artifact-cache:/build/minimax/.cache/artifacts:rw,rprivate" --volume "$cache_root/native-deps-cache:/tmp/ai-harness-native-deps-cache:ro,rprivate" --build-arg AI_HARNESS_NATIVE_DEPS_CACHE=1 --file deploy/Containerfile --jobs=1 --tag "localhost/ai-harness-engine:h013-$H013_SOURCE" --iidfile "$H013_TASK/candidate.iid" . > "$H013_TASK/engine-build.log" 2>&1
image_id=$(cat "$H013_TASK/candidate.iid")
timeout --signal=TERM --kill-after=15s 120s podman run --rm --name h013-offline-profile-probe --pull=never --http-proxy=false --network none --userns keep-id --user 1000:1000 --cap-drop ALL --security-opt no-new-privileges --read-only --pids-limit 128 --tmpfs /tmp:rw,nosuid,nodev,size=128m,mode=1777 --env HOME=/tmp --entrypoint sh "$image_id" -c 'node /opt/minimax/cli.js --version && cat /opt/minimax/patched-source-revision.txt && node --test /opt/ai-harness/engine/configure-profile.test.mjs && sha256sum /opt/ai-harness/engine/configure-profile.mjs /opt/minimax/cli.js /opt/minimax/native-probes.mjs /opt/minimax/source-pnpm-lock.yaml' > "$H013_TASK/candidate-probe.log" 2>&1
find server/dist web/dist -type f -print0 | sort -z | xargs -0 sha256sum > "$H013_TASK/artifacts.SHA256SUMS"
python3 "$H013_TASK/preservation.py" "$H013_TASK/after.json" --compare "$H013_TASK/before.json"
