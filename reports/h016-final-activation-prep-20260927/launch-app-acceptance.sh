#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then
 echo 'HELD source-only fresh Linux systemd acceptance. Fixed hard settlement 2026-09-27T17:45:00Z; no dispatch until root reviews final source/qualification/timing.'
 exit 0
fi
echo 'HELD: final W1 qualification/production identity and exact source/timing review required.' >&2
exit 78
# Root-reviewed future body; deliberately unreachable in this packet.
umask 077
export PATH=/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/bin:/bin
H016_TASK=/home/user/ai-harness-build/H016-FINAL-ACTIVATION-PREP-20260927
H016_DRIVER="$H016_TASK/driver"
: "${H016_REVIEW:?existing root review/current W1 handoff}"
: "${H016_GO_SHA:?actual reviewed gate digest}"
[[ $H016_GO_SHA =~ ^[a-f0-9]{64}$ ]]
H016_RUNTIME=$(python3 - <<'PY'
import datetime,math
now=datetime.datetime.now(datetime.timezone.utc)
stop=datetime.datetime(2026,9,27,17,44,30,tzinfo=datetime.timezone.utc)
assert (stop-now).total_seconds()>=900, 'insufficient launch budget before measured preflight'
# Actual preflight elapsed is charged again by supervisor/live admission.
print(min(1470,math.floor((stop-now).total_seconds())))
PY
)
test ! -e "$H016_DRIVER/supervisor-result.json"
test ! -e "$H016_TASK/live-acceptance-01"
test ! -e "$H016_DRIVER/dispatch-intent.json"
python3 - "$H016_DRIVER/dispatch-intent.json" "$H016_GO_SHA" <<'PY'
import datetime,json,os,sys
fd=os.open(sys.argv[1],os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:
 json.dump({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'unit':'h016-final15-app-acceptance.service','gate_sha256':sys.argv[2],'status':'DISPATCH_INTENT_NOT_PROOF'},f);f.write('\n');f.flush();os.fsync(f.fileno())
PY
# Independent fixed calendar stop also covers delayed service start. It cannot
# extend the deadline. Runtime1470 + stop grace30 <=1500. No automatic restart.
# Arm BEFORE the client; failed/ambiguous dispatch keeps intent and forbids replay.
systemd-run --user --unit=h016-final15-app-hardstop \
 --on-calendar='2026-09-27 17:44:30 UTC' \
 --timer-property=AccuracySec=1us --timer-property=RandomizedDelaySec=0 \
 /usr/bin/systemctl --user stop h016-final15-app-acceptance.service
systemctl --user show h016-final15-app-hardstop.timer -p ActiveState -p NextElapseUSecRealtime > "$H016_DRIVER/hardstop-readback.txt"
systemctl --user is-active --quiet h016-final15-app-hardstop.timer
# No --wait/--pipe/--pty. Every live client and both preflights are systemd-owned.
systemd-run --user --unit=h016-final15-app-acceptance \
 --property="RuntimeMaxSec=$H016_RUNTIME" --property=TimeoutStopSec=30 \
 --property=Restart=no --property=KillMode=control-group \
 --property=WorkingDirectory="$H016_DRIVER" \
 --property=StandardOutput="append:$H016_DRIVER/systemd-output.log" \
 --property=StandardError="append:$H016_DRIVER/systemd-output.log" \
 /usr/bin/python3 "$H016_DRIVER/supervise.py" \
 --gate "$H016_REVIEW" --gate-sha256 "$H016_GO_SHA" \
 --activation-manifest "$H016_TASK/private/ACTIVATION-MANIFEST.json" \
 --receipt "$H016_DRIVER/supervisor-result.json"
systemctl --user show h016-final15-app-acceptance.service \
 -p ActiveState -p SubState -p MainPID -p InvocationID -p ExecMainStatus \
 > "$H016_DRIVER/systemd-dispatch-readback.txt"
# Separately reconnect/read the SAME invocation and saved streams; no relaunch,
# native CLI SIGINT, quarantine clear or socket-close => native-idle inference.
