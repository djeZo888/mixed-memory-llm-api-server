#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: run-server.sh --node-prefix ABS --app-dir ABS --data-dir ABS \
                     --inference-key-file ABS [--engine-launcher ABS]

Run the built ai-harness server as the existing ordinary user. APP_DIR is the
ai-harness directory containing server/dist/main.js and web/dist. The inference
key path is server-only; the key is neither read nor printed by this launcher.
ENGINE_LAUNCHER defaults to this script's sibling run-engine.sh.
All required paths must exist, except DATA_DIR (created private if needed).
Listeners are fixed by the server contract: 127.0.0.1:8080 and :8081.
EOF
}
fail() { printf 'run-server: %s\n' "$*" >&2; exit 1; }
node_prefix=''; app_dir=''; data_dir=''; key_file=''
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
engine_launcher="$script_dir/run-engine.sh"
while (($#)); do
  case "$1" in
    --node-prefix|--app-dir|--data-dir|--inference-key-file|--engine-launcher)
      (($# >= 2)) || fail "$1 requires an absolute path"
      case "$1" in
        --node-prefix) node_prefix=$2 ;;
        --app-dir) app_dir=$2 ;;
        --data-dir) data_dir=$2 ;;
        --inference-key-file) key_file=$2 ;;
        --engine-launcher) engine_launcher=$2 ;;
      esac
      shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown argument: $1" ;;
  esac
done
[[ $(id -u) != 0 ]] || fail 'run through the existing ordinary user service, not root'
for path in "$node_prefix" "$app_dir" "$data_dir" "$key_file" "$engine_launcher"; do
  [[ "$path" == /* && "$path" != *$'\n'* && "$path" != *$'\r'* ]] || fail 'all paths must be absolute and single-line'
done
[[ -x "$node_prefix/bin/node" ]] || fail 'Node binary is missing'
[[ $("$node_prefix/bin/node" --version) == v24.* ]] || fail 'Node 24 is required'
[[ -f "$app_dir/server/dist/main.js" ]] || fail 'server/dist/main.js is missing; build reviewed server sources first'
[[ -d "$app_dir/web/dist" ]] || fail 'web/dist is missing; build reviewed web sources first'
[[ -x "$engine_launcher" ]] || fail 'engine launcher is missing or not executable'
[[ -f "$key_file" && -r "$key_file" ]] || fail 'protected inference key file is missing or unreadable'
# Inspect permissions only. Never read key contents into shell/environment/argv.
python3 - "$key_file" <<'PY'
import os, stat, sys
s = os.stat(sys.argv[1])
if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077:
    raise SystemExit("inference key must be a regular file owned by the service user with no group/other permissions")
PY
umask 077
mkdir -p -- "$data_dir"
[[ -O "$data_dir" ]] || fail 'data directory must be owned by the service user'
python3 - "$data_dir" <<'PY'
import os, sys
if os.stat(sys.argv[1]).st_mode & 0o077:
    raise SystemExit("data directory must have no group/other permissions")
PY
cd -- "$app_dir/server"
service_user=$(id -un)
runtime_dir="/run/user/$(id -u)"
# A fixed service environment avoids login-shell dependencies and ambient API keys.
# The server alone reads its protected key; run-engine accepts only ephemeral auth.
exec env -i \
  HOME="$HOME" USER="$service_user" LOGNAME="$service_user" \
  PATH="$node_prefix/bin:/usr/local/bin:/usr/bin:/bin" LANG=C.UTF-8 NODE_ENV=production \
  XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime_dir/bus" \
  AI_HARNESS_DATA_DIR="$data_dir" AI_HARNESS_ENGINE_LAUNCHER="$engine_launcher" \
  AI_HARNESS_INFERENCE_KEY_FILE="$key_file" \
  AI_HARNESS_GATEWAY_URL=http://10.0.2.2:8081/v1 \
  AI_HARNESS_ALLOWED_ORIGINS=http://10.156.100.61 \
  AI_HARNESS_WEB_DIST="$app_dir/web/dist" \
  "$node_prefix/bin/node" "$app_dir/server/dist/main.js"
