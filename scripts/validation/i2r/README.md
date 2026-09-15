# I2R: actual systemd with synthetic package commands

This harness exercises shipped `SystemdPackageScope`, `Runner`, `Prerequisites`
and `common.lifecycle_lease` in a fresh GitHub-hosted Ubuntu 24.04 VM. It does
not install packages. The coordinator approved only two exact temporary
read-only bind mounts: private fake commands over `/usr/bin/apt-get` and
`/usr/bin/dpkg`. Never execute the hosted path on a normal machine, Mac,
self-hosted runner or production server.

## Local verification

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/validation -p 'test_i2r*.py' -v
python3 scripts/validation/i2r/run.py --help
python3 scripts/validation/i2r/run.py --dry-run
python3 scripts/validation/i2r/runnerctl.py --help
git diff --check
```

These checks are worker-safe source/refusal tests and cannot establish actual
Linux integration PASS. The exact APT sandbox-option correction was integrated
from reviewed I1R2 commit `18644f3df91f38e23bbf19889f5c03302b898047`.

## Hosted launch and collection

Only the dedicated new workflow supplies the guarded execution environment.
It pins checkout/upload action revisions, uses read-only repository permission,
scrubs environment before sudo, and executes the exact event source. It reuses
I2P capability checks; unchanged I2P loop/systemd primitives are not called.
Source files are copied byte-for-byte to a private root-owned `/run/i2r-<uuid>`
namespace and hashed before importing production modules. No production
installer or adapter source is changed by this harness.

After reviewed source commit, coordinator approval, secret/metadata/scope gates
and feature-branch push, locate the exact run:

```bash
gh run list --repo djeZo888/mixed-memory-llm-api-server --workflow i2r-linux.yml \
  --commit REVIEWED_SHA --json databaseId,headSha,status,conclusion,url
python3 scripts/validation/i2r/runnerctl.py status --run-id RUN_ID --head REVIEWED_SHA
python3 scripts/validation/i2r/runnerctl.py collect --run-id RUN_ID --head REVIEWED_SHA \
  --destination /absolute/private/taskroot/new-evidence-directory
```

The collection parent must be owned mode 0700 outside Git. Only the three named
JSON artifact files are accepted, with bounded sizes and exact embedded
run/attempt/source identity. The controller can `stop` or `rerun` an exact owned
run; use `--dry-run` first. No raw logs are collected. Artifact retention is
14 days; preserve the sanitized files in the taskroot handoff.

## Cleanup and evidence limits

An outer guardian retains original package-file descriptors, metadata and
hashes while test children are killed. It locks existing package database lock
files without writing them, refuses package activity, and verifies each exact
read-only bind identity. After all owned scopes are quiescent it unmounts only
its own bindings and verifies original files. If quiescence or binding identity
is unknown, fake bindings remain until the disposable VM is discarded. Never
expose the real package executable to a pending package gate.

The matrix uses the real canonical `/run/llmctl/lifecycle.lock`, retains its
minted export through Runner use, and closes that duplicate before outer lease
exit. A detached watcher inherits its own copy. Independent contenders and
actual unit/cgroup/process identities supply evidence; fixture-only flock
tests do not establish the integration result.

Fixture policy and storage paths, deterministic fake audit results and trace
pauses at shipped Python call boundaries are explicit test injection. I1O owns
scope-owned source/key/cache/log/temp survival and anchored gate/marker writes
under mount loss, which remain **NOT_TESTED**; I1c owns final caller/stage glue.
Older evidence fields label these gaps I1c. The shipped Manager API must separately
support canonical borrowing before that integration can be claimed. Real apt
compatibility, reboot, GPU installation, Docker daemon ownership and agent
readiness remain **NOT_TESTED**.
