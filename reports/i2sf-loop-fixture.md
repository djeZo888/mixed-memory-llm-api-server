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

## Affected hosted execution

Pending publication at this source-review checkpoint. The exact tested SHA,
run URL, artifact ID/digest, source hashes and actual result will be recorded
here after collection. This statement is not an actual PASS.

The workflow runs only shipped `--dry-run`, shipped `--apply`, and exact cleanup
observation, after focused source safety tests and the existing I2P hosted/VM
capability guard. One 256 MiB backing is below the existing 2 GiB total budget.
Any shipped failure stops the job. The broad matrix is not rerun.

## Warnings and next action

Actual transaction/cleanup acceptance is pending. A still-active AUTOCLEAR
association after detach conservatively fails and preserves scratch. A production
failure must be reported with sanitized source/stage evidence, without patching
production code or trying another matrix. Remaining I1O lifetime/admission,
I1c Storage roles, I1W writer, extended-loop cases, physical/logical 4Kn, production
root exclusion, packages/GPU/models and reboot remain **NOT_TESTED**.
Next: publish gated source/launch marker and collect one affected hosted result.
