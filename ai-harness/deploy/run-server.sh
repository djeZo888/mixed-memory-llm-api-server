#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: run-server.sh --node-prefix ABS --app-dir ABS --data-dir ABS \
                     --inference-key-file ABS [--frontier-key-file ABS] [--browser-approval-key-file ABS] [--node-control-key-file ABS] [--engine-launcher ABS]

Run the built ai-harness server as the existing ordinary user. APP_DIR is the
ai-harness directory containing server/dist/main.js and web/dist. The inference
key path is server-only; the key is neither read nor printed by this launcher.
The optional frontier key path is server-only and lazy-loaded per frontier request;
missing/unreadable frontier credentials do not prevent Qwen startup.
The optional browser approval key is a separate host-only nginx proxy capability.
It is loaded by the protected server loader; omission disables approval issuance.
The optional node control key enables an independent passive node observer, never
uses the status daemon, and must never be passed to engines. Its exact authority
is documented in H005 source handoff; omission preserves baseline admission.
ENGINE_LAUNCHER defaults to this script's sibling run-engine.sh.
All required paths must exist, except DATA_DIR (created private if needed).
An explicitly reviewed --codex-preview-receipt ABS enables the optional local preview;
--codex-image-jobs-reviewed independently enables the reviewed specialist catalog/broker gate.
--codex-preview-output-limit defaults65536 and may be1024 for bounded acceptance.
--codex-specialist-qualification ABS forwards a protected specialist record and
requires both --codex-preview-receipt and --codex-owned-acceptance-policy.
Receipt failure disables only Codex. MiniMax remains the default engine.
Listeners are fixed by the server contract: 127.0.0.1:8080 and :8081.
EOF
}
fail() { printf 'run-server: %s\n' "$*" >&2; exit 1; }
node_prefix=''; app_dir=''; data_dir=''; key_file=''; approval_key_file=''; node_control_key_file=''; frontier_key_file=''; codex_receipt=''; codex_output=65536; codex_images=false
codex_ordinary_entry=""; codex_ordinary_key=""
owned_acceptance_policy=""
codex_specialist_qualification=""
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
engine_launcher="$script_dir/run-engine.sh"
while (($#)); do
  case "$1" in
    --node-prefix|--app-dir|--data-dir|--inference-key-file|--frontier-key-file|--browser-approval-key-file|--node-control-key-file|--engine-launcher|--codex-preview-receipt|--codex-owned-acceptance-policy|--codex-specialist-qualification|--codex-ordinary-entry|--codex-ordinary-entry-key)
      (($# >= 2)) || fail "$1 requires an absolute path"
      case "$1" in
        --node-prefix) node_prefix=$2 ;;
        --app-dir) app_dir=$2 ;;
        --data-dir) data_dir=$2 ;;
        --inference-key-file) key_file=$2 ;;
        --frontier-key-file) frontier_key_file=$2 ;;
        --browser-approval-key-file) approval_key_file=$2 ;;
        --node-control-key-file) node_control_key_file=$2 ;;
        --engine-launcher) engine_launcher=$2 ;;
        --codex-preview-receipt) codex_receipt=$2 ;;
        --codex-ordinary-entry) codex_ordinary_entry=$2 ;;
        --codex-ordinary-entry-key) codex_ordinary_key=$2 ;;
        --codex-owned-acceptance-policy) owned_acceptance_policy=$2 ;;
        --codex-specialist-qualification)
          [[ "$2" == /* && "$2" != *$'\n'* && "$2" != *$'\r'* ]] || fail 'specialist qualification path must be absolute and single-line'
          codex_specialist_qualification=$2 ;;
      esac
      shift 2 ;;
    --codex-image-jobs-reviewed)
      [[ "$codex_images" = false ]] || fail 'duplicate image gate'
      codex_images=true; shift ;;
    --codex-preview-output-limit)
      (($# >= 2)) || fail 'output limit required'
      [[ "$2" =~ ^[0-9]+$ && "$2" -ge 1 && "$2" -le 65536 ]] || fail 'invalid output limit'
      codex_output=$2; shift 2 ;;
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
if [[ -n "$approval_key_file" ]]; then
  [[ "$approval_key_file" == /* && "$approval_key_file" != *$'\n'* && "$approval_key_file" != *$'\r'* ]] || fail 'approval key path must be absolute and single-line'
  [[ -f "$approval_key_file" && -r "$approval_key_file" ]] || fail 'protected browser approval key file is missing or unreadable'
fi
if [[ -n "$frontier_key_file" ]]; then
  [[ "$frontier_key_file" == /* && "$frontier_key_file" != *$'\n'* && "$frontier_key_file" != *$'\r'* ]] || fail 'frontier key path must be absolute and single-line'
fi
# Frontier metadata/content validation is deliberately lazy and host-only.
# The same protected server loader validates approval-key metadata and reads it.
# Missing configuration leaves approval-token issuance closed; generation still works.
umask 077
mkdir -p -- "$data_dir"
[[ -O "$data_dir" ]] || fail 'data directory must be owned by the service user'
python3 - "$data_dir" <<'PY'
import os, sys
if os.stat(sys.argv[1]).st_mode & 0o077:
    raise SystemExit("data directory must have no group/other permissions")
PY
[[ "$codex_images" = false || -n "$codex_receipt" ]] || fail 'image gate requires reviewed Codex preview'
if [[ -n "$codex_specialist_qualification" ]]; then
  [[ -n "$codex_receipt" && -n "$owned_acceptance_policy" ]] || fail 'specialist qualification requires reviewed Codex preview and owned acceptance policy'
fi
if [[ -n "$codex_ordinary_entry" || -n "$codex_ordinary_key" ]]; then
  [[ -n "$codex_receipt" && "$codex_ordinary_entry" == /* && "$codex_ordinary_key" == /* && -f "$codex_ordinary_entry" && -f "$codex_ordinary_key" ]] || fail 'ordinary entry requires preview and protected approval/key paths'
fi
entry_args=("$app_dir/server/dist/main.js")
if [[ -n "$codex_receipt" ]]; then
  [[ "$codex_receipt" == /* && "$codex_receipt" != *$'\n'* && "$codex_receipt" != *$'\r'* ]] || fail 'receipt path must be absolute and single-line'
  [[ -f "$app_dir/server/dist/codex-preview-main.js" ]] || fail 'preview entrypoint missing'
  entry_args=("$app_dir/server/dist/codex-preview-main.js" "$codex_receipt" "$codex_output")
  if [[ "$codex_images" = true ]]; then entry_args+=(image-jobs-reviewed); elif [[ -n "$owned_acceptance_policy" ]]; then entry_args+=(image-jobs-unqualified); fi
  if [[ -n "$owned_acceptance_policy" ]]; then
    [[ "$owned_acceptance_policy" == /* && "$owned_acceptance_policy" != *$'\n'* && "$owned_acceptance_policy" != *$'\r'* ]] || fail 'owned policy path must be absolute and single-line'
    entry_args+=("$owned_acceptance_policy")
  fi
  if [[ -n "$codex_specialist_qualification" ]]; then entry_args+=("$codex_specialist_qualification"); fi
fi
cd -- "$app_dir/server"
service_user=$(id -un)
runtime_dir="/run/user/$(id -u)"
# A fixed service environment avoids login-shell dependencies and ambient API keys.
# The server alone reads its protected key; run-engine accepts only ephemeral auth.
exec env -i \
  HOME="$HOME" USER="$service_user" LOGNAME="$service_user" \
  PATH="$node_prefix/bin:/usr/local/bin:/usr/bin:/bin" LANG=C.UTF-8 NODE_ENV=production \
  XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime_dir/bus" \
  AI_HARNESS_CODEX_ORDINARY_ENTRY_FILE="$codex_ordinary_entry" \
  AI_HARNESS_CODEX_ORDINARY_ENTRY_KEY_FILE="$codex_ordinary_key" \
  AI_HARNESS_DATA_DIR="$data_dir" AI_HARNESS_ENGINE_LAUNCHER="$engine_launcher" \
  AI_HARNESS_INFERENCE_KEY_FILE="$key_file" \
  AI_HARNESS_FRONTIER_KEY_FILE="$frontier_key_file" \
  AI_HARNESS_BROWSER_APPROVAL_KEY_FILE="$approval_key_file" \
  AI_HARNESS_NODE_CONTROL_KEY_FILE="$node_control_key_file" \
  AI_HARNESS_GATEWAY_URL=http://10.0.2.2:8081/v1 \
  AI_HARNESS_ALLOWED_ORIGINS=http://10.156.100.61 \
  AI_HARNESS_WEB_DIST="$app_dir/web/dist" \
  "$node_prefix/bin/node" "${entry_args[@]}"
