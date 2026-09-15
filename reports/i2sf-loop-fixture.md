# I2SF bounded loop fixture correction

## Authorization and scope

Source and one affected actual GitHub-hosted Ubuntu 24.04 follow-up are authorized
by taskroot prompt/incoming revision1. Starting integration HEAD is
`9d700ae` (I2S `c1c31f47b237b98d6a4e94b75b59dfcbcb88ed4b` and reviewed root
`4ab862f` are ancestors). Branch: `milestone/i2sf-loop-fixture`.
No production `scripts/install/*` changes, ai-vm access, Mac system mutation,
package/GPU/model install, host `/run` remount, whole-host `/dev` exposure, or
physical/external device argument is introduced.

## Prior actual failure remains FAIL

[Run 34916701374](https://github.com/djeZo888/mixed-memory-llm-api-server/actions/runs/34916701374)
tested `50d2541e9dbd194ca0fd1471fb042955e648bff8`: dry-run PASS, apply rc1 with
generic wipefs error, incomplete cleanup report and retained scratch. Parent
namespace and loop associations were unchanged. Its nodev explanation was an
inference. Original `reports/i2s-*` evidence is preserved byte-for-byte.

## Fixture correction and validation boundary

- Capture exact private node path/major/minor, containing mount ID and flags,
  read-only open errno, wipefs exit status and sanitized bounded stderr before
  calling the production transaction. A failed signature query remains a failure.
- Only observed nodev + EACCES + failed wipefs permits a new 1 MiB, 64-inode tmpfs
  at this task's owned `root/dev` in its private namespace. Require exact mount
  ID, private propagation, nosuid/noexec, device access, limits and protection;
  reprobe successfully before the transaction. Only owned loop/partition nodes
  and its exact by-id link are allowed in cleanup.
- Verify active backing inode/filesystem, path, loop/sysfs identity, zero
  offset/size limit, mode, holders/slaves and exact 256 MiB/512-byte geometry.
  Preserve existing synthetic loop serial, WWN and root adapters, real tool busy
  checks and real signature reads.
- Replace the invalid explicit-device NAME predicate with active backing/sysfs
  checks. Hold an exact O_NOFOLLOW loop descriptor during final status checks
  and one `LOOP_CLR_FD`; never retry detach against a recycled name. See Linux
  [loop implementation](https://github.com/torvalds/linux/blob/v6.17/drivers/block/loop.c#L1115-L1145)
  and [UAPI structure/commands](https://github.com/torvalds/linux/blob/v6.17/include/uapi/linux/loop.h#L45-L58).
  That cleanup descriptor is never held across production busy probes.
- Account for synchronous producers before cleanup. Timeouts, surviving command
  groups, abnormal fixture death or production command exceptions preserve the
  pending marker and scratch. I1O lifetime work remains unresolved; this fixture
  does not bypass it. No broad kill or unmount is added.
- Capture sysfs/device mount identities and remove only exact owned mounts.
  Unexpected resources preserve scratch. Independent original parent namespace,
  mountinfo and loop inventories are compared, with before/after hashes.

## Worker-local review and checks

PASS: independent read-only bounded source review; two findings (detach name
race and uncertain production-exception cleanup) were corrected before release.
The reviewer checked 21 fixture tests; three further diagnostic/producer tests
were subsequently added and all 24 pass.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/install -p 'test_loop_disk_fixture.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/validation -p 'test_i2s*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/validation -p 'test_i2p*.py' -v
bash -n tests/install/loop_disk_transaction.sh
python3 -I -B tests/install/loop_disk_transaction.py --dry-run
python3 -B scripts/validation/i2s/run.py --dry-run --affected-only
git diff --check
```

Results: 24 fixture + 68 I2S + 27 I2P = **119 PASS**, zero skips/xfails.
Shell syntax, pure dry-runs and whitespace PASS. Initial runner test attempt
had a missing-new-test manifest failure while source was being written; the
integrated rerun passed. No actual Linux operations ran on the Mac.

## Affected hosted execution — FAIL, cleanup PASS

- Reviewed source: `ffb4e5ed36e7469012bed84408031e352d4bd4e5`.
- Tested launch SHA: `01cf9b8af2a8d65c1c1d677fd26132d3597ec441`.
- [Actual run 34918388941](https://github.com/djeZo888/mixed-memory-llm-api-server/actions/runs/34918388941),
  attempt1, affected-loop-fixture job104220862016, GitHub Actions runner group,
  `ubuntu-24.04`; completed failure. No second job/rerun was launched.
- Artifact `i2s-evidence-34918388941-1`, ID `10377331164`, 5605 bytes,
  digest `sha256:c3ba1fcb825ee22acdefb1bf227ec6be1ea0c5105c425530d835578029731f67`,
  expires 2026-09-29T01:43:24Z. Collected privately outside Git at
  `I2SF/evidence/34918388941/` using the existing gh helper and exact run guard.
- Sanitized evidence: [i2sf-linux-evidence.json](i2sf-linux-evidence.json).
  [All 42 tested source hashes](i2sf-tested-source-manifest.json) match local
  source and the reviewed implementation byte-for-byte.
- Ubuntu24.04.5, kernel6.17.0-1022-azure, systemd255, Python3.12.3,
  util-linux2.39.3 (including wipefs), e2fsprogs1.47.0.

| Affected check | Actual result |
| --- | --- |
| Hosted source/safety checks (18 runner + 24 fixture) | PASS |
| Existing I2P capability/context guard | PASS |
| Shipped dry-run | PASS, rc0 |
| Original private node read-only diagnostics | Confirmed nodev/EACCES; wipefs rc1 |
| Conditional exact `root/dev` tmpfs and reprobe | PASS |
| Shipped apply | FAIL, rc1 at fixture node identity guard |
| Exact descriptor detach and private tmpfs removal | PASS |
| Owned scratch removal | PASS |
| Independent original parent namespace/mountinfo/loops | All unchanged; no new scratch |
| Extended loop/writer/process matrix | NOT_TESTED |

### Confirmed initial cause

The original node was `/run/i1s-loop-Qb5hyDmV/root/dev/loop0`, major7/minor0.
Its containing `/run` mount ID294 had `rw,nosuid,nodev`. A read-only `os.open`
failed with errno13 (`EACCES`); wipefs returned1 with the sanitized error
`probing initialization failed: Permission denied`. These are actual observations
from the new run, confirming the previous nodev hypothesis for this fixture setup.
The historical run's missing diagnostics remain missing.

The approved tmpfs was mounted only at that scratch's `root/dev`, ID392,
`rw,nosuid,noexec,relatime`, size1024k, nr_inodes64, mode700. The same exact
major7/minor0 node then opened successfully and wipefs returned0 with no stderr.
The production transaction began only after that successful reprobe.

### New refusal: preserve FAIL, do not override identity

Production `sfdisk` completed successfully. After the following `lsblk` and
`udevadm` completions, the fixture raised `fixture block node identity changed`
from `sync_nodes()` at the next observation. The guard compares block type,
rdev, root ownership and mode0600 with the exact owned sysfs-derived node.
The artifact does **not** identify which node or which field differed. No
`production_command_failed` event is recorded; mkfs was never reached. This is
a fixture refusal, not a proven production defect or GPT/ext4 acceptance.

A partition device-number change following production `DiskIO.refresh()`'s
`BLKRRPART` is a plausible source-based explanation. It remains **inference**:
the failure lacks before/after partition node and sysfs values. Do not weaken
the guard, replace a node from current sysfs alone, or suppress the real refresh.
Exact new failure diagnostics and a separately reviewed bounded fixture approach
are needed before another actual attempt. No production patch or rerun was made.

### Cleanup evidence

The one held-descriptor `LOOP_CLR_FD` completed; the active backing and original
sysfs backing were absent. The exact device tmpfs mount392 was removed and the
owned scratch tree was removed. The original parent namespace remained
`mnt:[4026531832]`; mountinfo SHA256 before/after was
`8d1cbecc0ca32852999b183b05e06278cbb825def92d356ff2d3eb345e3a3c0f`.
The independently observed loop associations were empty both times, hash
`4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.
No newly created scratch remained. This run demonstrates actual successful
cleanup for this refusal; it does not retroactively change the prior cleanup FAIL.

## Warnings, pass/fail status and next action

**Overall actual status: FAIL / further fixture review required.** The nodev and
detach corrections worked, but the shipped transaction has not passed. Independent
read-only evidence review agrees that partition refresh is only an inference.

The workflow executed only shipped dry-run/apply and cleanup observation,
with one256 MiB backing below the2 GiB budget. Wider probes remained NOT_TESTED;
no skip/xfail was promoted to PASS. Actual GPT/ext4 completion/replay, I1O
lifetime/admission, I1c Storage roles, I1W writer, extended loops, physical/logical
4Kn, production root exclusion, packages/GPU/models and reboot remain NOT_TESTED.

Existing automatic source-only workflows on the tested SHA: general CI PASS
(run34918388915), I1 installer fixtures FAIL (34918388957), D2 lifecycle source
regressions FAIL (34918388996). Their failures are separate, not investigated or
patched in this bounded task. The prior I1 suite was already failing; no claim is
made that the new D2 failure is pre-existing.

Next recommended action: review exact partition/private-node mismatch diagnostics
and ownership-preserving synchronization with the fixture owner. Keep production
I1O/I1c/I1W ownership intact and require a reviewed bounded follow-up before
another actual job. Preserve the initial failure and this actual result separately.
