#!/usr/bin/env bash
set -euo pipefail
# Ubuntu's base python3 is the only bootstrap interpreter. No download pipe.
INSTALLER_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec /usr/bin/python3 -I -B "$INSTALLER_ROOT/scripts/install/main.py" "$@"
