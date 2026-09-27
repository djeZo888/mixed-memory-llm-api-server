#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then
 echo 'Review-only H016 systemd wrapper. Requires final capacity/source review, exact root GO and W1 lane handoff. No foreground live client. Default/--launch remain HELD (78).'
 exit 0
fi
echo 'HELD: final capacity/profile settings and full17 qualification pending; root must review this exact wrapper/driver before separate live GO.' >&2
exit 78
# Concrete future body, intentionally unreachable until that separate review.
umask 077
export PATH=/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/bin:/bin
H016_TASK=/home/user/ai-harness-build/H016-FINAL-INTEGRATION-20260927
H016_DRIVER="$H016_TASK/driver"
: "${H016_GO_SHA:?actual reviewed root gate SHA256}"
[[ $H016_GO_SHA =~ ^[a-f0-9]{64}$ ]]
test ! -e "$H016_DRIVER/supervisor-result.json"
test ! -e "$H016_TASK/live-acceptance-01"
test ! -e "$H016_DRIVER/dispatch-intent.json"
python3 - "$H016_DRIVER/dispatch-intent.json" "$H016_GO_SHA" <<'PY'
import datetime,json,os,sys
fd=os.open(sys.argv[1],os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:
 json.dump({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'unit':'h016-final-app-acceptance.service','gate_sha256':sys.argv[2],'status':'DISPATCH_INTENT_NOT_PROOF'},f);f.write('\n');f.flush();os.fsync(f.fileno())
PY
# No --wait, --pipe, --pty, foreground client or detached SSH child.
# Preflight AND all live requests run under the independent Linux manager.
systemd-run --user --unit=h016-final-app-acceptance \
 --property=RuntimeMaxSec=660 --property=TimeoutStopSec=30 \
 --property=KillMode=control-group --property=WorkingDirectory="$H016_DRIVER" \
 --property=StandardOutput="append:$H016_DRIVER/systemd-output.log" \
 --property=StandardError="append:$H016_DRIVER/systemd-output.log" \
 /usr/bin/python3 "$H016_DRIVER/supervise.py" \
 --gate "$H016_TASK/private/ROOT-GO.json" --gate-sha256 "$H016_GO_SHA" \
 --activation-manifest "$H016_TASK/private/ACTIVATION-MANIFEST.json" \
 --receipt "$H016_DRIVER/supervisor-result.json"
systemctl --user show h016-final-app-acceptance.service \
 -p ActiveState -p SubState -p MainPID -p InvocationID -p ExecMainStatus \
 > "$H016_DRIVER/systemd-dispatch-readback.txt"
# Reconnect independently and verify this invocation remains owned before exit.
# Never SIGINT the supervisor/client while it owns a live native request.
# Observe saved streams and terminal settlement; do not relaunch on ambiguity.
