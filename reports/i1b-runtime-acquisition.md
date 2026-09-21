# I1b — bounded installer runtime/acquisition source

Date: 2026-09-15. Worker: Mac-Worker1, Darwin arm64, Python3.14.7.
Base: root-reviewed I1 `722050fdcb6de4a9f56a5488b705998a1d82ce85`.
Branch: `milestone/i1b-runtime-acquisition`.

## Result

**BOUNDED SOURCE DELIVERED; production execution PENDING reviewed integration.**
Container/toolkit, GPU gate interface, runtime artifacts, generic acquisition,
protected anchored state and actual stage dispatcher source are implemented.
The complete fresh-machine installer remains incomplete. All public output keeps
`ready: false`; full apply/resume refuses before mutation.

The coordinator updated ownership while this task ran: I1R owns process/package
transactions; L1 owns the canonical lease and authorized watcher FD export.
Their reviewed source bundle was not supplied at handoff. Consequently public
package mutation through base or later intentionally returns78 with
`reviewed_i1r_l1_package_integration_required`. This is an explicit dependency,
not an implied permission request or a claim of working full apply. Existing
core.Runner, prerequisites, storage.py, lifecycle, profiles and V0 client source
were not edited. The exact existing global-lock context is retained pending
reviewed L1 integration; no raw-FD export bypass was created.

No live ai-vm installation, adoption, disk mutation, reboot, service restart,
model activation or weight download occurred. All source and tests ran on this
worker. Primary package archives were streamed into memory for hash verification;
registry checks fetched metadata only. No package or image was installed here.

## Delivered source and interfaces

- `scripts/install/main.py` exposes source boundaries `container`, `runtime`,
  `acquisition` (`models` alias), and separates the GPU-container gate. It retains
  I1 plan/apply/resume/status/verify, configuration identity and no-READY rules.
  Real stage tuples feed the inherited `State.run`; fixtures do not substitute
  a parallel installer. The explicit I1R/L1 execution checkpoint must remain
  until actual reviewed admission/ownership source is integrated.
- `stage_plan.py` reports exact container dependencies, keys/hashes/bytes, pinned
  runtime descriptors and model manifests/destinations, service effects and
  aggregate reservations. The selected runtime blob union deduplicates by SHA.
  Registered-host planning can report actual remaining model bytes without
  claiming a computed-hash check. Root/readiness requirements stay separate.
- `storage_io.py` exports `AnchoredRoot` and `MountedStorageGuard`: private
  directory-FD anchored mkdir/read/write/fsync/rename, protected ancestry,
  inode/device and exact mount/registration checks around every bounded chunk.
  The fast guard reads mountinfo and retained registry bytes without spawning
  a verifier process per chunk. `stage_state.py` reuses State validation/run and
  replaces its persistence with this anchored API.
- `container.py` extends the reviewed prerequisite solver with exact Docker/
  NVIDIA sources and FD-anchored APT cache/temp/logs. Compatible config/data and
  original backups are preserved; unsafe roots/overrides/active workloads are
  refused. Roots and mount-bound service settings precede first start. Exact
  maintainer-script inspection found direct NVIDIA CDI starts, so inhibition
  covers those units as well as Docker/containerd and prior policy restoration.
  Unknown package ownership keeps protective masks in place.
- `runtime.py` reproduces D1 source/Dockerfile/base/build/CLI identities and the
  exact reviewed SGLang digest, accounting for Docker manifest/config ID forms.
  Reuse inspects actual images and protected evidence hashes. Durable source,
  build, temporary files, Docker client config and logs use registered storage.
  Actual probes and synthetic fixtures have different evidence classes.
- `acquisition.py` generalizes D1b/F1A transfer logic to immutable selected lock
  manifests and registered roots. One pool has at most4 workers across all
  selected artifacts, with at most6 network attempts per file. Capacity uses
  aggregate remaining bytes and one reserve per filesystem, including persisted
  short writes; partial files are not duplicated in an HF cache. Range, length,
  encoding, revision/response identity and computed SHA gate completion; Git
  assets also check their pinned Git blob identity. Cancellation preserves bytes.
  Corrupt full partials receive unique retained quarantine names; retry does not
  discard verified peers. Oversize/ambiguous/corrupt final files fail preserved.
  Completion rechecks every fingerprint before publishing, and known invalid
  prior contracts move out of the lifecycle-consumed name into retained history.

Protected per-selection contracts are
`<roots.state>/acquisition/{glm,qwen}.complete.json`, schema1. They contain exact
manifest SHA, revision, destination/storage identity, every computed file SHA and
verified total. The expected manifests never change. Consumers must validate the
contract and current protected artifacts; existence/status alone is not a load
gate. Acquisition proves no auth, inference or tool support. Existing key bytes
are preserved and tested. Resume/verify hashes every expected file; repeated full
verification has real I/O cost and is not represented as a constant-time marker.

Early durable coordinator interfaces: `../i1b-stage-interface.md`,
`../storage-io-api.md`, `../container-stage-api.md`, and
`../i1r-interface-request.md`. The committed summaries are
[stage API](../docs/orchestration/i1b-stage-api.md) and
[remaining checklist](i1c-installer-checklist.md).

## Exact pins and measured source evidence

| Input | Evidence |
| --- | --- |
| GLM selected files | 11 shards, 467289116837 bytes; revision346b3591c7f28d1a23716f97a065ecf12ec14771 |
| Qwen selected files | 48 artifacts, 80407722953 bytes; revisionda6e2ed27304dd39abadd9c82ef50e8de67bdd4c |
| Selected total | 59 artifacts, 547696839790 bytes |
| Docker/toolkit closure | 37 unique archives, 95,799,538 bytes; every computed SHA and size matched the reviewed lock |
| Selected runtime blob union | 16,851,434,151 compressed bytes from verified immutable registry descriptors; excludes Git/build packages/metadata |
| Capacity | 100GiB GLM +40GiB Qwen runtime/build reservation;20GiB reserve per distinct filesystem; actual remaining model bytes on resume |

Docker29.6.1, containerd2.2.5, buildx0.35.0 and NVIDIA toolkit1.19.1 package
versions, primary URLs/key fingerprints and complete dependency groups are in
`versions.lock.json`. I1 Ubuntu dependency snapshot remains20260707T140000Z;
D1's unchanged runtime Dockerfile intentionally uses its distinct reviewed
20260914T000000Z build snapshot. No selected model/profile/recipe was rewritten.

Detailed primary checks and URLs:
[container evidence](i1b-container-evidence.md),
[runtime evidence](i1b-runtime-evidence.md),
[machine-readable registry descriptors](i1b-runtime-registry.json).
HTTP Range/identity behavior was checked against
[RFC9110 range requests](https://www.rfc-editor.org/rfc/rfc9110.html#name-range-requests)
and the [Hugging Face download reference](https://huggingface.co/docs/huggingface_hub/package_reference/file_download).
Neither these sources nor fixture bytes prove a live full-model download.

## Validation and review

Final machine-readable results, source identity and lock SHA are in
[i1b-validation.json](i1b-validation.json). Exact command:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/install -p 'test_*.py' -v
bash -n install.sh scripts/common/require-data-mounted.sh scripts/common/root-disk-guard.sh
./install.sh plan --profile flagship-hybrid --model-set glm,qwen \
  --fixture-host tests/install/fixtures/ubuntu-host.json
```

**197 tests:193 PASS,4 SKIPPED,0 failures/errors.** Evidence classes:

| Class | Status and limit |
| --- | --- |
| macOS source/FS/process fixtures | PASS; real anchored state/dispatcher/engine methods, duplicate process locks, local file writes and loopback HTTP Range transport |
| Synthetic host/package/runtime/GPU outputs | PASS as explicitly labeled fixtures; no actual apt, Docker or GPU proof |
| Primary HTTPS archive/registry checks | PASS; exact keys/archives/metadata hashes and descriptor bytes; no installed package/runtime |
| Actual Linux namespace mount-loss | One test present; SKIPPED on macOS; no CAP_SYS_ADMIN/Linux test environment supplied |
| Linux inherited-FD/process termination | Three tests present; SKIPPED on macOS |
| Ubuntu packages/systemd/private binds | NOT_TESTED |
| GPU container/runtime/model/auth/client | NOT_TESTED |
| Full fresh-host GPU install/reboot | NOT_TESTED |

Coverage includes interrupted acquisition plus dispatcher resume, source/lock/
state drift, compatible config/backup/policy preservation, autostart prevention,
service-root/override mismatch, simulated mount loss and a real-Linux detach test
source, duplicate owner, corrupt/truncated/range mismatch, single-file retries,
repeated identical corruption, shared/distinct reserves, short-write accounting,
hash publication rejection, source/image drift, and incomplete full-apply refusal.

Independent intra-worker review found and fixed repeated-quarantine retry traps,
stale completion proof, changed early-file fingerprints during publication,
short-write reservation drift, GPU fixture misclassification, Docker image-ID
domain differences, compact service-root overrides and backup replacement on
resume. No reviewed source was copied from adjacent unfinished task trees.
Diff whitespace and grep-based secret scans pass. Git author and committer are
both `CodexAIagent <133749519+djeZo888@users.noreply.github.com>`; remote contains
no embedded credentials. No push is performed; coordinator owns merge/publication.

## Required next action and limitations

1. Root reviews source/commits/bundle and integrates reviewed L1/I1R. Package
   transaction cgroup quiescence, unknown-owner admission and authorized close-only
   lease export must precede any package mutation. Add all declared read-only
   observer shapes. Long runtime jobs must retain ownership across parent SIGKILL;
   caught exception/timeout group cleanup alone is insufficient. I1b leaves the
   public execution checkpoint in place.
2. Fresh I1S finishes optional blank-disk provisioning using
   [the concrete seam/transaction/test handoff](../docs/orchestration/i1s-storage-handoff.md).
   I1b makes no storage.py changes, so ownership is unambiguous.
3. Run disposable Ubuntu24.04 amd64 package/systemd/private-mount checks, including
   actual effective Docker/containerd roots. Containerd config parsing alone does
   not prove an existing daemon loaded that config; live adoption needs actual
   observation or fail-closed policy. This task performed no live adoption.
4. I1c integrates protected release/key/instance/boot lifecycle, native SGLang
   sentinel auth, U1 authenticated catalog/switch, V0 ordinary-user staged client,
   and actual role-specific health/generation/streaming/tool/client acceptance.
   [The checklist](i1c-installer-checklist.md) records every remaining contract.

Only GLM/Qwen are acquisition scope. No new smoke, Qwen3.8 or DeepSeek download,
legacy cleanup, browser UI, or agent tools on the API VM is introduced.
