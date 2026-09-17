# D3BR existing registered-host runner contract

Published before runner edits, from integration
`ec747134615f4f1d86cf455016aadc166d44be50` on 2026-09-15.
Source-only; installer PAUSED. No VM access, build, retry, requests or restart.

## Exact ownership and dependencies

D3BR owns only the checked source helper, focused helper/runner tests,
`containers/llama-cpp/build-d3p-runtime.sh`, and D3BR reports/provenance.
L2/L2VM own protected registration and control source staging. No changes to
that source closure, its manifest, Manager, runtime profiles, or installer files.

The registered branch invokes the existing guard at the fixed path
`/usr/local/lib/llm-server/control-api/scripts/common/registered-storage.py`
using `sudo -n /usr/bin/python3 -I -B`. The runner verifies protected nonsymlink
root-owned ancestors and ordinary single-link files plus these reviewed hashes:

| Relative source beneath control-api | SHA256 |
| --- | --- |
| `scripts/common/registered-storage.py` | `21cf082a841aeab9470bd6704b77104961b9d4afcaec696d90aa22b65f5b6f3d` |
| `scripts/install/storage.py` | `4f834e92d149ea1955e79d34c53c18bf8c5846a4121d779e135a50d31a615505` |

These match `reports/l2-source-closure-sha256.json`. The actual guard loader
uses `importlib.util.spec_from_file_location` to load the adjacent
`scripts/install/storage.py` directly. Its `read_registration`, `verify`,
`root_payload_guard`, and `_atomic_write` paths import only Python standard
library modules. They do NOT import `storage_io`, `storage_binding`,
`prerequisites`, `disk_init`, or a package initializer on this call path.
The registered guard's existing `write_report` calls `verify` again, requires
a report strictly beneath registered logs with protected nonsymlink ancestors
and an existing parent, then uses the existing atomic file writer (mode 0600).
This is the guard's existing writer; no new writer or policy framework is added.

**L2VM dependency advice:** these two exact reviewed files and their protected
ancestors suffice for this runner seam; both already appear in the reviewed L2
closure. The runner invokes `registered-storage.py --root-guard` directly, so it
does not require adding `scripts/common/root-disk-guard.sh` to that closure.
Missing or mismatched bytes/protection are a STOP, never a dirty-checkout import
or broad reinstall. Installed availability has not been checked on this worker.

## Selection and current-host constraints

Once `/etc/local-ai-server` exists (including a symlink), select registered
semantics with NO legacy fallback on absent, bad, incomplete or disappearing
registration. The guard itself owns the fixed root-owned
`/etc/local-ai-server/storage.json` schema, identity and mount verification.
Require its verified data path/mount `/data`, model path/mount
`/data/models-large`, and logs root `/data/logs`; do not supply UUID, device,
model or data overrides. Entry and final storage checks use the protected guard.
If registration appears during a legacy run, subsequent checks select and latch
registered semantics. A later disappearance fails closed.

An absent registration parent retains the existing legacy guards and report
paths. Root's canonical protected D3 guards in the supplied `../VM-GUARDS.json`
remain mandatory external preflight/postflight with exact ownership and hash
verification even when registered. They are not replaced by this runner seam.
Never invoke the historical dirty checkout guard.

## Report and build paths

The existing run remains `/data/build/d3p-*`, with clean `repo/`, pinned clean
`source/`, existing `tmp/` and `evidence/`, all on `/data`. Build logs/status,
source provenance, lock and IID remain inside that run. The runner does not
create a new top-level data directory or change ownership.

Registered root-guard reports go to
`/data/logs/<exact run basename>/root-build-before.json` and
`/data/logs/<exact run basename>/root-build-after.json`.
A later separately authorized VM owner must create that one approved task
directory root-owned, mode 0700, after canonical guards pass. The existing guard
validates containment/protection and writes reports as root. No path option or
environment override can redirect reports. Legacy reports remain
`RUN/evidence/root-build-{before,after}.md`. Dry-run writes no reports.

Preserve HOME, model-free Docker command, CUDA/base/snapshot pins, named context,
8 jobs, `120a-real`, Docker `/data/docker`, containerd `/data/containerd/root`,
source/hash/derived-tree guards, no prior IID, and before/after guard behavior.
The combined patch and derived tree remain unchanged.

## Validation boundary

Run only focused helper and source shell/fake registered-guard tests on worker:
registered success, invalid registration stops before Docker/report, report
containment and protected closure, dry-run, and unchanged legacy path. Fake
commands are isolated to temporary test copies with no production override.
Actual Linux registered runtime, Docker recipe build and later image proof:
**NOT_TESTED**. Historical D3B failure and old D3PD recipe evidence remain intact.
Root review precedes any separately authorized one-time actual retry.
