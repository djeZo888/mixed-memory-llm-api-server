# D3B2 verification commands

All execution below was on ai-vm through SSH. No installer or generic test suite.

- Exact protected source paths and SHA256/uid/mode/link/ancestor checks from VM-GUARDS.json; actual original require-data-mounted.sh and root-disk-guard.sh before/after.
- sudo -n /usr/bin/python3 -I -B /usr/local/lib/llm-server/control-api/scripts/common/registered-storage.py --root-guard --json
- Exact root-byte threshold and data/model UUID/mount checks; before/after parent uid/gid/mode/inode comparisons.
- Reviewed build-d3p-runtime.sh --dry-run RUN; helper --check-only before/after; six-file hashes compared with c7155099 provenance.
- bash -n RUN/task-build-wrapper.sh; RUN/task-build-wrapper.sh --help; independent wrapper review.
- ONE systemd-run with User=user Group=ai Restart=no RuntimeMaxSec=12h, exact wrapper; systemctl MainPID independently recorded.
- Inspect exact image IID; docker image save streamed to hash selected OCI index/manifest/config bytes; compare image/host recipe manifests and source proof.
- Exact no-network/no-mount runc containers for --version and --help; exit0 and required flags/load modes verified from retained output.
- ONE authorized NVIDIA devices0,1 enumeration: timeout --signal=TERM --kill-after=5s 30s docker start -a EXACT_ID; entrypoint args only --list-devices.
- nvidia-smi GPU memory and compute-process samples before/after; unchanged original GLM ID/image/status/StartedAt.
- Every verification container inspected quiescent/exited0, docker rm EXACT_ID without force, independent docker inspect absence; final owned-name list empty.
- Failed D3B log sha256sum -c; final owner repo clean including ignored files; HOME unchanged.

Local packaging only: git diff --cached --check; quiet grep-based staged-evidence credential scan; author/committer inspection; git bundle verify. Not a local implementation/build/test run.
