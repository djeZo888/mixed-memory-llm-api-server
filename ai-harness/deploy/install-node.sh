#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: install-node.sh [--prefix ABS] [--dry-run]

Install the reviewed official Node 24 archive in the invoking user's home.
Default: $HOME/.local/opt/ai-harness/node-<pinned-version>
Requires Linux, curl, tar/xz, Python 3 and sha256sum; never invokes sudo.
Checks the downloaded official SHASUMS256.txt AND the committed SHA256 pin.
Existing managed installs are verified; an unrelated destination is refused.
--dry-run reports the exact download/destination without writing anything.
EOF
}
fail() { printf 'install-node: %s\n' "$*" >&2; exit 1; }
prefix=''
dry_run=false
while (($#)); do
  case "$1" in
    --prefix) (($# >= 2)) || fail '--prefix needs an absolute path'; prefix=$2; shift 2 ;;
    --dry-run) dry_run=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown argument: $1" ;;
  esac
done
[[ $(id -u) != 0 ]] || fail 'run as the existing ordinary user, not root'
[[ $(uname -s) == Linux ]] || fail 'only Linux host archives are pinned'
for tool in curl tar xz python3 sha256sum; do command -v "$tool" >/dev/null || fail "missing dependency: $tool"; done
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
pin_fields=$(python3 - "$script_dir/node-pin.json" "$(uname -m)" <<'PY'
import json, re, sys
p = json.load(open(sys.argv[1], encoding="utf-8"))
a = p["artifacts"].get(sys.argv[2])
if not a:
    raise SystemExit("unreviewed Linux CPU architecture")
v = p["version"]
assert re.fullmatch(r"v24\.\d+\.\d+", v)
assert re.fullmatch(r"[0-9a-f]{64}", a["sha256"])
assert a["name"] in (f"node-{v}-linux-x64.tar.xz", f"node-{v}-linux-arm64.tar.xz")
assert a["url"] == f'https://nodejs.org/dist/{v}/{a["name"]}'
assert p["checksumsUrl"] == f"https://nodejs.org/dist/{v}/SHASUMS256.txt"
print(v, a["name"], a["url"], a["sha256"], p["checksumsUrl"], sep="\n")
PY
)
fields=()
while IFS= read -r field; do fields+=("$field"); done <<<"$pin_fields"
version=${fields[0]}; archive=${fields[1]}; url=${fields[2]}; expected=${fields[3]}; sums_url=${fields[4]}
prefix=${prefix:-"$HOME/.local/opt/ai-harness/node-$version"}
prefix=$(python3 - "$HOME" "$prefix" <<'PY'
from pathlib import Path
import sys
home = Path(sys.argv[1]).resolve()
raw = Path(sys.argv[2])
if not raw.is_absolute() or any(c in str(raw) for c in "\n\r\t"):
    raise SystemExit("prefix must be an absolute path without control characters")
prefix = raw.resolve()
if prefix == home or home not in prefix.parents:
    raise SystemExit("prefix must be strictly within the invoking user's home")
print(prefix)
PY
)
printf 'Node %s\nSource: %s\nSHA256: %s\nPrefix: %s\n' "$version" "$url" "$expected" "$prefix"
$dry_run && exit 0
umask 077
if [[ -e "$prefix" ]]; then
  [[ -d "$prefix" && -f "$prefix/.ai-harness-node-install.json" ]] || fail 'destination exists without a managed install receipt'
  python3 - "$prefix" "$version" "$expected" <<'PY'
from pathlib import Path
import hashlib, json, sys
p = Path(sys.argv[1])
r = json.loads((p / ".ai-harness-node-install.json").read_text())
if r.get("version") != sys.argv[2] or r.get("archiveSha256") != sys.argv[3]:
    raise SystemExit("existing receipt does not match the reviewed pin")
if hashlib.sha256((p / "bin/node").read_bytes()).hexdigest() != r.get("nodeSha256"):
    raise SystemExit("installed node binary differs from its receipt")
PY
  [[ $("$prefix/bin/node" --version) == "$version" ]] || fail 'installed binary version mismatch'
  printf 'Existing managed Node installation verified.\n'
  exit 0
fi
parent=$(dirname -- "$prefix")
mkdir -p -- "$parent"
staging=$(mktemp -d "$parent/.ai-harness-node.XXXXXXXX")
cleanup() { [[ -n "$staging" && "$staging" == "$parent"/.ai-harness-node.* ]] && rm -rf -- "$staging"; }
trap cleanup EXIT
curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --tlsv1.2 "$sums_url" -o "$staging/SHASUMS256.txt"
python3 - "$staging/SHASUMS256.txt" "$archive" "$expected" <<'PY'
import sys
matches = [line.split()[0] for line in open(sys.argv[1], encoding="ascii")
           if len(line.split()) == 2 and line.split()[1] == sys.argv[2]]
if matches != [sys.argv[3]]:
    raise SystemExit("official SHA256SUMS differs from committed archive pin")
PY
curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --tlsv1.2 "$url" -o "$staging/$archive"
printf '%s  %s\n' "$expected" "$staging/$archive" | sha256sum --check --status || fail 'archive SHA256 mismatch'
mkdir -- "$staging/unpack"
tar -xJf "$staging/$archive" --strip-components=1 -C "$staging/unpack" --no-same-owner
[[ $("$staging/unpack/bin/node" --version) == "$version" ]] || fail 'downloaded binary version mismatch'
python3 - "$script_dir/node-pin.json" "$(uname -m)" "$staging/unpack" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import hashlib, json, sys
pin = json.load(open(sys.argv[1], encoding="utf-8"))
a = pin["artifacts"][sys.argv[2]]
p = Path(sys.argv[3])
r = {"version": pin["version"], "archiveUrl": a["url"], "archiveSha256": a["sha256"],
     "checksumsUrl": pin["checksumsUrl"], "installedAt": datetime.now(timezone.utc).isoformat(),
     "nodeSha256": hashlib.sha256((p / "bin/node").read_bytes()).hexdigest()}
(p / ".ai-harness-node-install.json").write_text(json.dumps(r, indent=2) + "\n")
PY
mv -- "$staging/SHASUMS256.txt" "$staging/unpack/.ai-harness-SHASUMS256.txt"
# Do not overwrite a destination introduced while downloading.
[[ ! -e "$prefix" ]] || fail 'destination appeared during installation; refusing replacement'
mv -T --no-clobber -- "$staging/unpack" "$prefix"
[[ ! -d "$staging/unpack" ]] || fail 'destination appeared during installation; refusing replacement'
printf 'Installed %s. Explicit PATH: %s/bin:/usr/local/bin:/usr/bin:/bin\n' "$version" "$prefix"
