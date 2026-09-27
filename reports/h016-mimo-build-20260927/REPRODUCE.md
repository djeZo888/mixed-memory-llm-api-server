# Bounded offline build commands and evidence

Executed on mac-worker2/ai-harness only. Native wrapper start11:23:37UTC, hardstop11:58:37UTC; no renewed session. Source archive generated with `git archive --format=tar 928b3b470058241f089a839367d4b30d5887a6e3 ai-harness`. No install command, network-enabled build or inference-runtime/native-tools build was used.

The installed current harness guard is the established protected-build/release path, canonical rootless graphroot and >20GiB policy. ai-harness has no ai-vm `/data` registration; ai-vm helpers were not run. `guard.py` applies this policy, verifies retained9ef885 identity and paused idle owner state without acquiring a lifecycle lock.

The compile recipe starts at immutable retained **source/dependency cache**
`sha256:d476433f8d1bb1163a3d9250cf22032845099b6f8c8c8479048d3510e498c45a`.
It verifies upstreamae65651/source/dependency/patched manifests and all patch hashes, applies the reviewed source patches, commits verified source with the existing deterministic date, then executes the exact existing commands:

```bash
pnpm typecheck
MCODE_RELEASE_TAG=v0.5.1 pnpm build
node scripts/package-cli-release.mjs v0.5.1 /build/release
node /tmp/build-native-probes.mjs /build/minimax /build/packaged/native-probes.mjs
```

The retained mcode-tools archive is bound at `/build/minimax/.cache/artifacts`; its SHA256d2e160be is verified before build and upstream packaging verifies its existing identity. Runtime graph/package lock/node_modules remain inherited from9ef885. No npm/pnpm install or native binary compilation was performed. Server/web `npm ls --all --offline; npm run build` used isolated copies of the exact H013 lock-matching installed dependencies.

The bounded independent job was launched (without `--wait`) and then observed in a new SSH command:

```bash
systemd-run --user --unit=h016-mimo-compile-928b3b4 \
  --property=RuntimeMaxSec=1200 --property=TimeoutStopSec=30 \
  --property=WorkingDirectory=/home/user/ai-harness-build/H016-MIMO-BUILD-20260927 \
  /bin/bash /home/user/ai-harness-build/H016-MIMO-BUILD-20260927/build.sh
```

`build.sh` records exit/status/time and caps compilation at900s. It settled successfully before subsequent image packaging. Source packaged revision51d06736d5dd56d0e7b7e34dbb107fa015864817 is derived from ae65651 plus the complete reviewed patchset; it is not the Mac standalone source snapshot.

Extract outputs with an owned stopped container, never a production engine:

```bash
cd /home/user/ai-harness-build/H016-MIMO-BUILD-20260927
podman create --name h016-compiled-extract --network none --entrypoint /bin/true "$(cat compiled.iid)"
podman cp h016-compiled-extract:/build/packaged ./packaged
podman cp h016-compiled-extract:/build/release ./release
podman cp h016-compiled-extract:/build/minimax/packages/local-runtime-v2/src/service/model-system/resolution/model-token-estimator.ts ./model-token-estimator.ts
podman rm h016-compiled-extract
```

The scanner reads image files under `--network none --read-only` into private base/candidate inventories. `prepare-overlay.py` derives the concrete file allowlist, refusing native/tool/dependency deltas; `verify-overlay.py` checks hashes/modes/owners, unchanged group digests and exact base-layer inheritance. Runtime recipe is `Containerfile.overlay`, **FROM exact9ef885**, with only the derived overlay copied. New names for content-addressed application chunks are added; unused old chunks remain harmlessly retained in immutable base layers.

One necessary build-only provenance correction beyond the plan's named profile/config files: also copy exact928b3b4 `deploy/engine/pins.json`, whose inherited value otherwise remained e487935 while compiled code/labels/patch identities correctly said a6dd7df. No application source changed. The final changed-file allowlist is27 files. README's only native-package delta is its derived source revision links. No tools/browser/PDF/image/native assets or dependency files changed.

`verify-built.sh` runs the requested actual-image profile/migration tests, existing compiled native estimator probe, and owner-discovered browser-inclusive roster+SDK canonical fixture offline. It captures no real user history and calls no tool. Native host startup attempts models.dev metadata refresh; deny-fetch intercepts it and the container additionally has no network. The two early capture diagnostics (missing synthetic thinking signature, then counting the denied metadata attempt) are retained privately; the final capture records both accurately.

`stage-qualified-config.mjs` is prepare-only. Verification: Node syntax/--help pass; unqualified existing template rejected before output. `DEPLOYMENT.md` describes the later paired image/host staging and rollback, including mandatory persistent native owner adoption. Existing source suites were not rerun; only requested built-image checks ran (repeated once after the final pins-only image change).
