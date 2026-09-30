# Guarded paired deployment and rollback — review only, NOT executed

Root must give the separate GO for the exact source/image below, after reviewing
Worker1's fresh authenticated post-promotion/reboot receipt: native context and
pool 1048576, max_req_input_len1048570 with actual admitted input <=1048569,
input+output <=1048574, output65536, tokenizer/template
`eb9eb208eb0d988989d07a6a12d0fdeb5f52574a`. Readiness must reflect the new
production backend, not retained H012. This PREP does not supply that receipt.
No inference replay is needed to reproduce the scientific PASS.

A fresh Worker2 activation task owns these commands on ai-harness as user.
Recheck no active/queued/unknown native/user/image jobs, retained dispatch/stop
intent and exact container ownership. If ownership is uncertain, stop; do not
clear quarantine or cancel another task. Keep Sova stopped throughout staging.
Search currently runs and must remain unchanged. No ai-vm commands are included.

```bash
set -euo pipefail
umask 077
H013_TASK=/home/user/ai-harness-build/H013-SOVA-1M-20260927
H013_OLD=/opt/ai-harness/releases/296ae49e44eb250773223885b843994e2c5b9bcc/ai-harness
H013_RELEASE=/opt/ai-harness/releases/7143c17d73173db9364b77956679c86d7026a4ae/ai-harness
H013_UNIT=/home/user/.config/systemd/user/ai-harness.service
H013_STATUS=/etc/systemd/system/ai-harness-status.service.d/30-h008-registry.conf
H013_TAG=localhost/ai-harness-engine:0.0.2-ae65651df5f9
H013_OLD_IMAGE=c328dac0e6ede1dfb890a0657ebafd6f6fd4a1f2281f4e1c664ab95db7dcaa20
H013_IMAGE=$(cat "$H013_TASK/candidate-overlay.iid")
export PATH=/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/bin:/bin
cd "$H013_TASK"
python3 preservation.py pre-activation.json --compare before.json
sha256sum -c source.SHA256SUMS
(cd source/ai-harness; sha256sum -c ../../artifacts.SHA256SUMS)
# Bind H013_IMAGE to the exact image ID in the reviewed RESULT.json, not a tag.
test "$(podman image inspect localhost/ai-harness-engine:h013-7143c17-profile --format '{{.Id}}')" = "${H013_IMAGE#sha256:}"
test ! -e "$H013_RELEASE"
mkdir -m 700 activation-backup
cp -a "$H013_UNIT" activation-backup/ai-harness.service
cp -a "$H013_STATUS" activation-backup/30-h008-registry.conf
# Consistent private database backup for evidence; NEVER restore it on rollback.
python3 - <<'PY'
import pathlib,sqlite3
root=pathlib.Path('/home/user/.local/share/ai-harness')
for name in ('harness.sqlite','owner.sqlite'):
 with sqlite3.connect(f'file:{root/name}?mode=ro',uri=True) as src:
  with sqlite3.connect(pathlib.Path('activation-backup')/name) as dst:src.backup(dst)
PY
sudo install -d -m 755 "$(dirname "$H013_RELEASE")"
sudo cp -a source/ai-harness "$H013_RELEASE"
sudo chown -R root:root "$H013_RELEASE"
# Only immutable release source/artifacts/dependencies. No HOME/.local or data chmod.
sudo chmod -R a+rX "$H013_RELEASE"
(cd "$H013_RELEASE/server"; node --input-type=module -e "await import('./dist/app.js'); await import('./dist/gateway.js')")
# Stage units, preserving every credential/environment directive.
python3 - "$H013_UNIT" "$H013_OLD" "$H013_RELEASE" "$H013_STATUS" <<'PY'
import pathlib,sys
unit,old,new,status=sys.argv[1:]
s=pathlib.Path(unit).read_text();assert old in s
pathlib.Path('ai-harness.service').write_text(s.replace(old,new))
s=pathlib.Path(status).read_text()
old_status='/opt/ai-harness/components/H008-REGISTRY-296ae49/ai-harness'
assert old_status in s
pathlib.Path('30-h008-registry.conf').write_text(s.replace(old_status,new))
PY
systemd-analyze --user verify "$H013_TASK/ai-harness.service"
# Recheck root GO + fresh backend receipt and exact stopped/idle ownership here.
test "$(systemctl --user show ai-harness.service -p ActiveState --value)" = inactive
test "$(podman image inspect "$H013_TAG" --format '{{.Id}}')" = "$H013_OLD_IMAGE"
podman tag "$H013_IMAGE" "$H013_TAG"
install -m 600 ai-harness.service "$H013_UNIT.h013-new"
mv "$H013_UNIT.h013-new" "$H013_UNIT"
sudo install -o root -g root -m 644 30-h008-registry.conf "$H013_STATUS.h013-new"
sudo mv "$H013_STATUS.h013-new" "$H013_STATUS"
systemctl --user daemon-reload
sudo systemctl daemon-reload
sudo systemctl restart ai-harness-status.service
systemctl --user start ai-harness.service
```

These sequential changes occur with the app stopped; they are not an atomic
cross-host transaction. Stop on any failure, retain state, and use the rollback
below. The independent status service is included because its current drop-in
points to a separate H008 registry; updating only the app would retain the old
visible label. Verify the installed registry is exactly `Frontier GLM-5.3-Flash`
and that actual ready/down semantics still come from observations.

After activation: ordinary-user installed imports, actual PID/cwd/image ID,
health/status and pinned backend readiness, no restart loop, current context
1048576 for Flash and480000 for Qwens, no unknown native ownership, and preserved
session/file/history identities. Observe the normal guarded startup; do not
claim full1M agent occupancy. Managed agents migrate at engine startup only if
the old bytes exactly match the reviewed hash. Any custom conflict stays intact
and blocks that profile for review. Existing conservative estimator remains.

## Rollback commands (retain current data, no snapshot restore)

Stop the app and confirm native tasks/containers settled; if settlement cannot
be verified, leave paused and escalate. Do not kill arbitrary containers.
Use the reviewed `rollback-managed-profiles.py` from this report, copied into the
same protected task directory by the activation worker. Default is dry-run;
apply changes ONLY exact managed1M agent bytes back to the exact old480K bytes.
Custom content, unsafe modes/owners/links or drift fail closed before changes.
All histories, identities, AGENTS.md, images, files and user work are preserved.

```bash
systemctl --user stop ai-harness.service
# Verify exact owned native task/container settlement before profile mutation.
python3 rollback-managed-profiles.py /home/user/.local/share/ai-harness/profiles --dry-run
python3 rollback-managed-profiles.py /home/user/.local/share/ai-harness/profiles --apply
podman tag "$H013_OLD_IMAGE" "$H013_TAG"
install -m 600 activation-backup/ai-harness.service "$H013_UNIT.h013-old"
mv "$H013_UNIT.h013-old" "$H013_UNIT"
sudo install -o root -g root -m 644 activation-backup/30-h008-registry.conf "$H013_STATUS.h013-old"
sudo mv "$H013_STATUS.h013-old" "$H013_STATUS"
systemctl --user daemon-reload
sudo systemctl daemon-reload
sudo systemctl restart ai-harness-status.service
# Sova stays STOPPED. Old harness480K cannot be paired with a1M backend.
# Root/Worker1 must establish a matching reviewed backend before any later start.
```

Do not restore old SQLite, profiles, files, keys, dispatch state or histories.
The old engine refreshes only generated config/token fields on subsequent
startup after matching backend readiness. Preserve both releases/images and all
failed build logs; no prune. Reversal is a recovery action requiring the fresh
activation task's authority, not permission to use a wrong-capacity backend.
