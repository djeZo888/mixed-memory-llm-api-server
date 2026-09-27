#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then
 echo 'Fresh Linux systemd acceptance; root direct coordinated acceptance GO required. Fixed hard settlement 2026-09-28T01:15:00Z; no dispatch until root reviews final source/qualification/timing.'
 exit 0
fi
# Root-reviewed final body; do not dispatch without direct acceptance GO.
umask 077
export PATH=/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/bin:/bin
H018_TASK=/home/user/ai-harness-build/H018-HARNESS-PREP01-20260928
H018_DRIVER="$H018_TASK/driver"
: "${H018_REVIEW:?existing root review/current W1 handoff}"
: "${H018_GO_SHA:?actual reviewed gate digest}"
[[ $H018_GO_SHA =~ ^[a-f0-9]{64}$ ]]
H018_RUNTIME=$(python3 - <<'PY'
import datetime,math
now=datetime.datetime.now(datetime.timezone.utc)
stop=datetime.datetime(2026,9,28,1,14,30,tzinfo=datetime.timezone.utc)
assert (stop-now).total_seconds()>=900, 'insufficient launch budget before measured preflight'
# Actual preflight elapsed is charged again by supervisor/live admission.
print(min(1470,math.floor((stop-now).total_seconds())))
PY
)
test ! -e "$H018_DRIVER/supervisor-result.json"
test ! -e "$H018_TASK/live-acceptance-01"
test ! -e "$H018_DRIVER/dispatch-intent.json"
python3 - "$H018_DRIVER/dispatch-intent.json" "$H018_GO_SHA" <<'PY'
import datetime,json,os,sys
fd=os.open(sys.argv[1],os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:
 json.dump({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'unit':'h018-prep01-app-acceptance.service','gate_sha256':sys.argv[2],'status':'DISPATCH_INTENT_NOT_PROOF'},f);f.write('\n');f.flush();os.fsync(f.fileno())
PY
# Independent fixed calendar stop also covers delayed service start. It cannot
# extend the deadline. Runtime1470 + stop grace30 <=1500. No automatic restart.
# Arm BEFORE the client; failed/ambiguous dispatch keeps intent and forbids replay.
systemd-run --user --unit=h018-prep01-app-hardstop \
 --on-calendar='2026-09-28 01:14:30 UTC' \
 --timer-property=AccuracySec=1us --timer-property=RandomizedDelaySec=0 \
 /usr/bin/systemctl --user stop h018-prep01-app-acceptance.service
systemctl --user show h018-prep01-app-hardstop.timer -p ActiveState -p NextElapseUSecRealtime > "$H018_DRIVER/hardstop-readback.txt"
systemctl --user is-active --quiet h018-prep01-app-hardstop.timer
# No --wait/--pipe/--pty. Every live client and both preflights are systemd-owned.
systemd-run --user --unit=h018-prep01-app-acceptance \
 --property="RuntimeMaxSec=$H018_RUNTIME" --property=TimeoutStopSec=30 \
 --property=Restart=no --property=KillMode=control-group \
 --property=WorkingDirectory="$H018_DRIVER" \
 --property=StandardOutput="append:$H018_DRIVER/systemd-output.log" \
 --property=StandardError="append:$H018_DRIVER/systemd-output.log" \
 /usr/bin/python3 "$H018_DRIVER/supervise.py" \
 --gate "$H018_REVIEW" --gate-sha256 "$H018_GO_SHA" \
 --activation-manifest "$H018_TASK/private/ACTIVATION-MANIFEST.json" \
 --receipt "$H018_DRIVER/supervisor-result.json"
systemctl --user show h018-prep01-app-acceptance.service \
 -p ActiveState -p SubState -p MainPID -p InvocationID -p ExecMainStatus \
 > "$H018_DRIVER/systemd-dispatch-readback.txt"
# Separately reconnect/read the SAME invocation and saved streams; no relaunch,
# native CLI SIGINT, quarantine clear or socket-close => native-idle inference.
