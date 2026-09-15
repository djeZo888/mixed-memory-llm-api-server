# Q38A acquisition tools

These tools implement the explicitly authorized ai-vm acquisition only. They do
not install or invoke the installer, change runtime configuration, publish a
lifecycle receipt, or launch a container/model. The complete pinned Q38S manifest
is the source of artifact identity, including `.gitattributes` and the empty
`safetensors-md5sum.txt`.

## Fixed task paths

| Purpose | Path |
| --- | --- |
| Protected source | `/data/services/q38a-20260915/repo` |
| Task output and temporary files | `/data/build/q38a-20260915` |
| Model | `/data/models-large/qwen38-27b-fp8` |
| Download status | `/data/build/q38a-20260915/evidence/acquisition-status.json` |
| Download completion | `/data/build/q38a-20260915/evidence/acquisition-complete.json` |
| Image status | `/data/build/q38a-20260915/image/status.json` |
| Protected seal evidence | `/data/models-large/.q38a-evidence-20260915/sealed-evidence.json` |

Stage only reviewed task scripts, `scripts/d1/storage_guard.py`, the common
guards, and Q38S manifest/provenance beneath the protected source. Source must be
root-owned and nonwritable by the download user. Run/output directories remain
task-private. Verify actual mounts/UUIDs, containment, root >=4GiB, capacity and
the immutable manifest before staging/writes. Run both common guards before and
after acquisition. No installer source is required on this legacy VM.

## Verification and execution

Local offline fixtures, with no SSH/Docker/model imports:

```sh
python3 -B -m unittest discover -s scripts/q38a -p 'test_*.py' -q
python3 -B scripts/q38a/acquire.py --help
python3 -B scripts/q38a/pull_image.py --help
python3 -B scripts/q38a/seal.py --help
git diff --check
```

On ai-vm, set `TMPDIR=/data/build/q38a-20260915/tmp` for all Python invocations,
including fixtures. The weights helper runs as ordinary `user`, with `-I -B`;
its `--dry-run` checks readiness without creating payloads. Default concurrency
is three, bounded to one through three. The same helper resumes matching
partials while retaining all bytes; it refuses foreign trees and ambiguous
final/partial pairs. Its lock is `RUN/acquisition.lock`. Status is atomic, and
transport errors contain safe class names only. Completion always rereads
payload bytes; it does not trust an old computed-hash flag.

Actual task unit names/PIDs and completion evidence are in the Q38A report and
taskroot handoff. Acquisition jobs use bounded transient units with standard
output/error disabled; durable task status/guard reports carry the evidence.
No installed service or daemon configuration is changed.

The image tool runs as root, uses an empty task-private Docker configuration,
and targets the local socket and exact linux/amd64 digest. See `--help` for the
read-only verification path. No container create/run/import is present.

## Seal and receipt handoff

Only invoke `seal.py` after the weights unit is inactive/dead, all81 computed
checks have passed, and a root read-only check finds no writable descriptors or
shared writable mappings of any payload inode. `--dry-run` checks exact
manifest/status/stat alignment; apply independently rereads all81 artifacts as
root, then sets payloads root-owned0444 and model directory root-owned0555.
Its task lock excludes the downloader through sealing/publication. Recheck
write denial, open writers, and every saved sealed stat after apply.

The rich evidence is protected under the root-owned model mount. It includes
the expected manifest, actual SHA256 values, acquisition receipt hash, exact
storage identity and before/after file metadata. The empty artifact remains a
real zero-byte file; LFS pointer Git IDs remain distinct from payload hashes.

Canonical `/etc/local-ai-server/storage.json` is absent on this VM. Publish no
substitute lifecycle receipt or protected instance entry. The reviewed live
deployment must later validate the seal/manifest and use the canonical lease,
registered binding and anchored writer for the exact Q38S receipt transform.
Image authentication, inference, continuation and occupied context remain
separate NOT_TESTED gates.

## Executed read-only completion checks

`check_open_writers.py` and `check_image_contract.py` preserve the exact bounded
read-only commands used in this acquisition. Execute through worker SSH with
standard-library Python and the task TMPDIR:

```sh
ssh ai-vm 'sudo -n env TMPDIR=/data/build/q38a-20260915/tmp python3 -I -B -' < scripts/q38a/check_open_writers.py
ssh ai-vm 'sudo -n env TMPDIR=/data/build/q38a-20260915/tmp python3 -I -B -' < scripts/q38a/check_image_contract.py
```

The second check imports only the exact pure OCI validator from Q38B checkpoint
`3a470d2b8c90398be0bffe78bccd13fe1c3a0f2e`, staged in the protected isolated
`/data/services/q38a-20260915/q38b-reviewed` directory. Its SHA256 is
`f2059445f3a06b15e710bc7d65866bc8d821ca3a78ef900f3d94ce4866accc2f`.
It verifies actual Docker Descriptor/RepoDigest/source/default-process fields,
the stored manifest-to-config relationship, and full public image environment
equality without printing environment values. The governing identity evidence
is `reports/q38a-image-evidence.json`; no Q38B runtime/auth receipt is produced.
