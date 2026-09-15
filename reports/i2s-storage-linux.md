# I2S actual disposable Linux storage verification

**FAIL / BLOCKED: the shipped I1S fixture failed at its wipefs probe and reported
incomplete cleanup. The harness stopped; extended GPT/ext4, writer and process
cases remain NOT_TESTED. No installer acceptance or readiness claim.**

## Executed identity and durable evidence

- Approved base: `e6c77debb4989ada0c7a563159f8df45aa89f7b5`.
- Branch: `milestone/i2s-storage-linux`; source commit
  `3e3b5a1d85e035af9f17c582a70a72ca850b87c5`.
- Actual tested launch SHA: `50d2541e9dbd194ca0fd1471fb042955e648bff8`.
- [I2S run34916701374, attempt1](https://github.com/djeZo888/mixed-memory-llm-api-server/actions/runs/34916701374):
  failure, job2026-09-15 01:17:59–01:18:08 UTC; actual harness0.442 seconds.
- Artifact `i2s-evidence-34916701374-1`, ID10376391633,4354 bytes,
  GitHub digest `sha256:36592b00a4678d58303d98b6ad53564d228b1905e0ca52852375056f0fcb4414`;
  expires2026-09-29 01:18:05 UTC.
- [Sanitized actual evidence](i2s-linux-evidence.json), SHA256
  `f531cb21fcfe673837008fb8ebfc5e4f6f13b183b95c6805649b165051bc0997`.
- [Tested source manifest](i2s-tested-source-manifest.json), SHA256
  `c1578d109dfe1ad7346f5fc65fd421e9600424e2a82146a99b4488ad1b034f54`.
  All37 entries match local source. Final report-only changes do not change it.
- Artifact plan SHA256 `dba93106d2ee4d232b1e8506b3e896d56a9ff683e429e4fcc1d9cb9d22d23133`.
  All three collected JSON files are also retained outside Git in taskroot evidence.
- [Independent source review](i2s-source-review.md) and
  [execution/verification interface](../scripts/validation/i2s/README.md).

The source commit was bundled immediately, then pushed with `[skip ci]`. A separate
marker-only push triggered exactly one I2S actual job and no extra I2P disk job.
Existing source-only CI jobs also triggered. No rerun was attempted. All commits
use CodexAIagent <133749519+djeZo888@users.noreply.github.com> as both author and
committer. Full bundle, final SHA/hash, status/session and coordinator handoff live
in taskroot. No main push or auth-file read occurred.

## Actual environment and tools

| Observation | Actual value |
| --- | --- |
| I2P capability guard | PASS: Ubuntu24.04.5 LTS, amd64/x86_64, root in hosted VM |
| Kernel / virtualization |6.17.0-1022-azure / microsoft |
| PID1 / cgroup | systemd255.4-1ubuntu8.17 / cgroupv2 |
| ImageOS / ImageVersion | ubuntu24 /20260907.300.1; rolling label, not immutable VM pin |
| Resources |4 CPUs,16373444 KiB RAM;92402147328 bytes temp free before |
| sfdisk / losetup / mount | util-linux2.39.3 |
| mke2fs / e2fsck |1.47.0, EXT2FS library1.47.0 |
| udevadm / Python |255 /3.12.3 |

Tools were already available; no package installation was attempted. The workflow
uses fixed Ubuntu24.04, pinned checkout/upload actions, contents:read only,
persist-credentials:false, an explicit scrubbed sudo environment, and bounded
output/job execution. No self-hosted runner, SSH, production host or physical
device exposure was used.

## Actual failure and cleanup evidence

The exact unchanged shipped commands executed in order:

```sh
bash tests/install/loop_disk_transaction.sh --dry-run
bash tests/install/loop_disk_transaction.sh --apply
```

Dry-run returned0 and printed the reviewed256 MiB internally allocated backing,
loop, private namespace and scoped-cleanup design. Apply returned1 with:

```text
FAIL: storage command failed: wipefs
Fixture loop detach has not completed; preserving backing file.
CLEANUP_INCOMPLETE: inspect /run/i1s-loop-yOAq3pja in disposable environment.
```

An independent parent observer found its mount namespace unchanged, the complete
loop-association inventory unchanged, and the new scratch directory still present.
It performed no cleanup mutation. This is **incomplete scratch cleanup**, even
though the observed active loop associations returned to their initial state.
The source does not expose the underlying wipefs exit code/errno/stderr. Reported
code1 is the wrapper's exit code. No stronger disk-tool diagnosis is claimed.

The harness stopped with `shipped_cleanup_unresolved_stop_matrix`. No subsequent
loop, writer or process fixture was allocated. There was no broad kill/unmount,
force wipe/repair, ignored busy check or cleanup override. The completed ephemeral
job was left to GitHub's VM lifecycle; VM teardown is not recorded as successful
fixture cleanup. The path above belongs to that discarded job, not the Mac or a
reusable device selector.

## Findings for the coordinator's bounded fix

[Independent blocker analysis](i2s-hosted-blocker-analysis.md) records the source references and evidence limits.

1. **Shipped detach test is invalid for util-linux2.39.3.** At
   `tests/install/loop_disk_transaction.sh:96`, listing NAME for an explicit loop
   can print its name even after the backing association is gone. Upstream
   `show_table()` emits a selected-device row and COL_NAME returns its path.
   The source-supported diagnosis matches the unchanged association observation;
   scratch cleanup still failed. Use exact associated-backing/identity evidence
   in a reviewed fixture fix, preserving ambiguous-state refusal.
   [Official losetup2.39.3 source](https://github.com/util-linux/util-linux/blob/v2.39.3/sys-utils/losetup.c#L225-L227),
   [selected-device row](https://github.com/util-linux/util-linux/blob/v2.39.3/sys-utils/losetup.c#L328-L333).
2. **wipefs cause remains unconfirmed.** A strong source-supported hypothesis is
   device nodes created beneath `/run` on a `nodev` mount: the fixture creates
   its block nodes there and redirects wipefs to them. systemd255 normally mounts
   `/run` with MS_NODEV; Linux rejects opening device nodes on such mounts.
   Actual `/run` options and the tool errno were not captured, so this is an
   inference, not an observed EACCES result. The new extended loop adapter shares
   this layout and needs the same review. The requested wipefs flags/columns are
   present in util-linux2.39.3 source.
   [systemd255 mount setup](https://github.com/systemd/systemd/blob/v255/src/shared/mount-setup.c#L96-L97),
   [Linux6.17 device-open check](https://github.com/torvalds/linux/blob/v6.17/fs/namei.c#L3220-L3247),
   [official wipefs source](https://github.com/util-linux/util-linux/blob/v2.39.3/misc-utils/wipefs.c).
3. **Diagnostic gap:** preserve bounded sanitized argv/result/errno and actual
   scratch mount options before retrying. Any fixture change must retain owned
   backing inode/size/offset/association checks, exclusive probes, private
   namespaces and exact cleanup. Do not change production behavior to make a
   fixture pass. Existing fixture/helper source is outside I2S ownership and
   was not patched here.

## Validation matrix and remaining gates

| Check | Result |
| --- | --- |
| Worker-local I2S safety suite | PASS:61 tests |
| Worker-local I2S plus reused I2P safety suite | PASS:97 tests |
| Pure dry-runs / Python syntax / shipped shell syntax | PASS |
| Hosted I2S ordinary-user source/safety step | PASS |
| Hosted capability / exact shipped dry-run | PASS |
| Shipped actual apply / complete scoped cleanup | FAIL / INCOMPLETE |
| Real GPT copies/CRCs/geometry, ext4 identity/zero reserve, fsck, UUID mount | NOT_TESTED |
| Actual512 logical-sector evidence / optional4096 loop | NOT_TESTED / NOT_TESTED |
| sfdisk/mkfs/mount/registration pre-receipt interruptions | NOT_TESTED |
| Payload replay, foreign partial metadata, raw before/after hashes, in-use/drift refusals | NOT_TESTED |
| Actual same-device nested writer bind, allowed sibling and mount-loss/fallthrough | NOT_TESTED; I1W reviewed fix not received |
| Actual parent SIGKILL/live child and caught timeout adapters | NOT_TESTED |
| Canonical global admission / production child deadline | NOT_TESTED; I1O pending |
| Role-aware data-only persistence / I1c writer conversion | NOT_TESTED; source pending |
| Production root exclusion / physical4Kn | NOT_TESTED |
| Actual packages/GPU/model/image installation / reboot | NOT_TESTED |

No skip or expected failure was promoted to PASS. Prepared loop discovery
adapters, raw metadata tests and disk-local flock do not establish production
root exclusion, physical hardware behavior, global admission or fresh installation.
The planned aggregate backing limit is1792 MiB including the shipped case; only
the shipped internally allocated256 MiB case was attempted in this run.

Independent source review fixed an early-return cleanup-report persistence bug
in the new harness before publication. Regression tests require explicit cleanup
PASS for both namespace probes before later allocations. The observed early stop
therefore remains a failed test outcome rather than a bypass.

## Other observed CI and local warnings

- [General CI34916701336](https://github.com/djeZo888/mixed-memory-llm-api-server/actions/runs/34916701336): success.
- [D2 regressions34916701290](https://github.com/djeZo888/mixed-memory-llm-api-server/actions/runs/34916701290): success.
- [Existing I1 source suite34916701348](https://github.com/djeZo888/mixed-memory-llm-api-server/actions/runs/34916701348):
  **failure**,276 tests,2 failures,11 errors,1 skip. Failures concern existing
  container/package policy recovery fixtures; they were not edited here. The skip
  is not acceptance. Only bounded test names/errors were inspected, no raw logs
  were committed or retained.
- Existing Mac disk suite:34 PASS,1 ERROR in final os.killpg cleanup with EPERM;
  see independent review. This is separate from actual hosted disk evidence.
- Changed-file scope, filename-only secret scan, whitespace, Markdown links,
  safe HTTPS remote and exact author/committer identities passed before pushes.

**Next action:** coordinator assigns a bounded I1S fixture compatibility/cleanup
fix with diagnostics, reviews it, and authorizes a fresh disposable job. Consume
reviewed I1W/I1O/I1c source when available. The requested actual storage/writer
matrix remains blocked; this report does not clear any of its unexecuted gates.
