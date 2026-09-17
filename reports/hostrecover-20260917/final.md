# HOSTRECOVER closeout — 2026-09-17

Host recovery and the approved prevention/transport maintenance completed.
**GLM is stopped; its API is not currently serving.** Root explicitly closed
HOSTRECOVER without another start or model request and handed the healthy host
to the separately approved Q38LIVE task after ownership release.

- Exact two apt indexes removed after identity/non-use/writer checks. Unchanged
  full root guard passed immediately afterward. Exactly 56 June/July archived
  journals were copied to the protected `/data/logs/hostrecover-20260917/`
  archive, independently SHA256-verified, checked for owner/group/mode/mtime/
  xattrs, and only unchanged closed originals unlinked. Other cleanup was not
  performed. Active/September journal retention subsequently follows the
  separately approved normal journald limits.
- One normal reboot completed. Final kernel `6.8.0-139-generic`; loaded and
  installed NVIDIA `595.84`; both RTX PRO 6000 GPUs healthy; registered mounts,
  Docker `/data/docker` and full root guard passed. Final root free:
  **5,562,286,080 bytes / 5.180 GiB**, above 4 GiB STOP and below 6 GiB warning.
- The exact existing native1M GLM container reached fresh Manager readiness
  after one start: context 1,048,576, N76/both GPUs, 442 cheap load samples,
  zero sampled error counters or monitoring failures. This proves allocation
  and readiness in that lifetime, not occupied-context quality or throughput.
- My task wrapper then passed the sample list to `AnchoredRoot.atomic_json`,
  which requires an object. Its broad error handler boot-stopped the already
  ready container. The durable readiness result precedes the durable failure/
  stopped result. Final state is selected native1M, stopped, desired running,
  manual policy, Docker restart `no`, PID0/exit0. **Zero inference requests.**
  Corrected task-only wrappers are retained unexecuted; no additional start
  was authorized. The dense first-load array was not persisted; its final
  sample and sparse worker event summaries remain.
- Three approved prevention fragments were installed root:root0644 and
  verified: apt binary caches disabled; journald128M/4404M/16M; four NVIDIA
  driver-family blacklist patterns matching16 installed packages. Security
  origins/periodic updates remain configured, and unrelated package exclusions
  pass. One approved journald restart completed without parse warnings. An
  initial comparison falsely included apt's newly created empty blacklist
  parent; current verification passes, but the old in-memory apt snapshot is
  unavailable for historical byte equality.
- NETPATCH `a12c8618f3b58000a914dd0369528ec2b88283cc` was deployed to
  `/usr/local/lib/llm-server/private-network/private_network.py` with SHA256
  `9ca8ca4b86dbf04988bfe2f8f0a7b3748bbe5d1922c0543f081616f37ec1a6af`.
  The protected receipt was backed up and only `signature.helper` migrated;
  policy, six units, owner and `before_filter` were preserved. New receipt SHA:
  `f17b33637bbc88c3fcb65d2016a73aa1c071fd383571e1452c01cef677c01eeb`.
  Reviewed ingress and GLM socket/proxy checks pass on systemd Ubuntu8.17.
  The active proxy has a stopped upstream; no private inference claim follows.

Final audit at03:51:39 UTC preserved exact registered source77 files, registry,
credentials, profiles and stopped old32K/D1 rollback containers. All backends,
control and Qwen sockets are inactive. Canonical lifecycle ownership was
released and observed free at03:51:39.202105 UTC; worker request ownership was
then independently checked free and released. **No further HOSTRECOVER VM
operations.** See `lease-release.md` for the actionable handoff.

Evidence remains protected on the VM under `/data/logs/hostrecover-20260917`
and in the worker task's `private/remote` directory. `evidence-manifest.json`
records transferred raw-report hashes; `result.json` contains exact identities
and limits. Configuration templates and the maintenance note are in
`configs/host-recovery/` and `docs/orchestration/host-recovery-prevention.md`.
No weights, secrets, memory, raw private logs or installer changes are committed.

Later work must establish current GLM serving/smoke and private-client
acceptance. Full control/network source composition remains with root.
Qwen, switching, occupied1M, frontend and installer acceptance were not tested.
