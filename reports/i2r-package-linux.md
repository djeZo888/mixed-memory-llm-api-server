# I2R actual disposable Ubuntu package ownership

**PASS for all 15 executed package-ownership scenarios and exact cleanup.**
This is actual systemd/cgroup-v2 execution with synthetic package commands.
**Full installer/source acceptance remains NOT_TESTED.** No real APT/dpkg
mutation, GPU installation, model/image download, production access or Mac
installation occurred.

## Immutable execution identity

- Tested source: `e9fe5d00f9bcc6c1dffc93a3fb75c660aa037a48`.
- Reviewed base: `6920fa445bd9ea8d41f59e7f052a83e7322497bf`.
- Reviewed I1R2 dependency: `18644f3df91f38e23bbf19889f5c03302b898047`,
  merged without editing its source at `a833afeff52768b453e214f6aebade4137f96b0e`.
- Branch: `milestone/i2r-package-linux`.
- [GitHub run 34918085832, attempt 1](https://github.com/djeZo888/mixed-memory-llm-api-server/actions/runs/34918085832): success.
- Artifact `10376034175`, `i2r-evidence-34918085832-1`;
  GitHub digest `sha256:cc93e9a76db61fc81b532d2b9bbe609b2fbea0ea25743c45820295175c830618`.
- Actual integration elapsed time: **60.177 seconds**.
- Observed VM: Ubuntu 24.04.5 LTS, amd64, root, systemd PID1,
  systemd `255.4-1ubuntu8.17`, kernel `6.17.0-1022-azure`, cgroup v2,
  Microsoft virtualization. Image version `20260907.300.1`; the hosted image
  label is rolling and no immutable full-VM checksum is exposed here.
- cgroup2 mount ID 36 at `/sys/fs/cgroup`, device `0:30`,
  `rw,nodev,noexec,nosuid,relatime`; actual owned cgroups support `cgroup.kill`.

Preserved sanitized evidence is committed with this report:
[run/artifact metadata](i2r-hosted-run.json),
[actual observations and cleanup](i2r-hosted-evidence.json),
[source manifest](i2r-source-manifest.json), and [execution plan](i2r-hosted-plan.json).
All **127 artifact source hashes** were independently compared with the exact
Git commit. The original GitHub artifact expires 2026-09-29; these preserved
files retain their recorded hashes independently of that retention window.
No arbitrary logs, unit environments, credentials or request bodies are included.

## Actual matrix

Every row below executed on the hosted VM with the shipped `SystemdPackageScope`,
`Runner`, `Prerequisites` and canonically imported `common.lifecycle_lease`.
The canonical lock was `/run/llmctl/lifecycle.lock`. Each Runner retained its
minted exported duplicate through the entire package-use scope and closed it
before the outer lease exited. Independent processes attempted acquisition;
no substitute fixture flock establishes these results.

| Actual scenario | Result | Observed evidence |
| --- | --- | --- |
| Ordinary completion and two transactions | PASS | Distinct exact invocations/cgroup inodes; same export valid twice; preparing/owned/READY precede gate; final contender acquired. |
| Initially absent policy | PASS | Policy remains absent after quiescence and clean fake audit; marker/gate retired. |
| Failed command and terminal retention | PASS | Fake exit 23 retained as failed/failed, Result=exit-code; no live cgroup; policy restored after audit. |
| Main exits with live descendant | PASS | MainPID=0 while SubState=running and recursive population=true; owned descendant remains; contender busy. |
| Ctrl-C | PASS | Installer receives SIGINT, owned cgroup descendant is terminated, caller reports interruption; sentinel survives and lock releases. |
| Manager timeout | PASS | Actual RuntimeMaxSec produces Result=timeout, signal 9 and empty cgroup; sentinel survives. |
| Installer SIGKILL in preparing phase | PASS for refusal | Lock free but shared admission blocked; recovery returns package_ownership_incomplete; no unit started and no gate opened. |
| Installer SIGKILL after ownership, before watcher | PASS | Lock free but admission blocked; unopened worker reaches manager deadline, then explicit recovery succeeds. |
| READY but no gate, installer SIGKILL | PASS | Contender busy until autonomous deadline; no fake execution event, terminal unsuccessful; explicit recovery required. |
| Installer SIGKILL after gate | PASS | Contender busy after installer death; manager timeout empties exact scope, watcher releases, explicit recovery restores policy. |
| Watcher then installer SIGKILL | PASS | Contender acquires while scope remains populated, but pending marker blocks shared admission until quiescence/recovery. |
| Unknown identity | PASS for tested variants | Changed expected InvocationID/inode and missing unit refused; abort refuses changed identity; corrupt marker preserves inhibitor and recovers after fixture correction. |
| Dirty fake audit | PASS | package_database_repair_required preserves inhibitor/marker and blocks admission; clean fixture audit permits explicit recovery. |
| External policy change | PASS | existing_policy_changed preserves external bytes; only explicit fixture reconciliation permits recovery. |
| Crash during retirement | PASS | Policy restored but marker still pending; after SIGKILL admission stays blocked and explicit recovery completes retirement. |

All 15 cases observed the same unrelated sentinel alive before intentional final
cleanup. No policy-restored-while-populated observation occurred. Original opaque
policy bytes and full mode **04750** round-tripped where initially present.
Successful units retained active/exited with exact InvocationID after kernel
cgroup removal; failed units retained failed/failed with their exact invocation.

Example of actual descendant ownership: unit
`local-ai-package-8b52758c344241dc8627bf066648fe2a.service`, InvocationID
`04bd5e0025ce4f71b7b1fbbe58e74187`, cgroup inode **6947**. MainPID was **0** while
PID **2694**, kernel start ticks **3451**, remained in the recorded cgroup,
reparented to PID1. The contender remained busy. Later the exact invocation was
retained with an empty/missing cgroup. The artifact retains each other identity
and descendant observation; PID/name alone never authorized a signal.

## Actual I1b preparation boundary

**PASS:** real `ContainerPackages` option generation and actual `Runner` execution
for update, simulation and download-only returned the deterministic fake response.
The exact `APT::Sandbox::User=root` option passed. All **12** bound-command unsupported sandbox,
option/mode override and plain package-mutation shapes were refused. The unbound
`apt` negative is checked through the actual parser only; its Runner execution
path is explicitly **NOT_TESTED**. A hard fixture allowlist prevents any unbound
negative from reaching Runner or subprocess even if the admission parser regresses.

The actual canonical module rejected wrong root/UID, fabricated capability,
plain object and raw exported FD. This proves the helper boundary; it does
**not** prove Manager/public installer borrowing or admission wiring.
Preparation used an explicitly injected protected `AnchoredRoot` fixture and
performed no repository/key download or package installation.

## Exact cleanup and restoration

**PASS:** 16 allocated identities comprise **15 retained terminal invocations**
with no cgroup, recursive population false and no descendants, plus **one never
started allocation**. All **30 recorded processes** were dead: 15 installers,
14 watchers and the sentinel after its intentional final cleanup. A fresh
independent canonical acquisition succeeded; no recorded keeper/lock holder
survived. Terminal units and private fixture evidence were intentionally retained
until GitHub discarded the disposable VM; no broad stop/reset/prune was used.

The outer guardian held four existing package database locks without writing
contents. It bound exactly two private fake scripts read-only, mount IDs **59**
and **96**, and unmounted only their verified identities after scope cleanup.
Original descriptors and canonical paths were compared against original full
metadata and SHA256; cleanup recorded `state=restored`, `originals_restored=true`.

| Restored original | Original inode / full mode / bytes | SHA256 |
| --- | --- | --- |
| `/usr/bin/apt-get` | 1861 / 0100755 / 51680 | `eb53b3b66cbb7a90a370e26439e941b7cf146ddd91a5422063c761ce9e59c53b` |
| `/usr/bin/dpkg` | 1840 / 0100755 / 318176 | `567180a568ad6af680314fdcb4d963246985e682b28a9e8fafed8b09abbd50af` |

Both originals were device 2049, UID/GID 0. Exact atime/mtime/ctime and lock-file
snapshots are in the artifact. The artifact retains original snapshots and
restoration PASS rather than separate post-cleanup snapshots: before/after
metadata/hash equality and unmount absence were asserted by the matching tested
guardian source. Policy byte/mode checks likewise rely on source assertions and
stage observations, not a continuous monitor or independent final file snapshot.

## Remaining gates and next bounded work

- **I1O storage lifetime and mount loss: NOT_TESTED.** Scope-owned source/key/cache/
  log/temp anchors and anchored gate/marker writes are unfinished. Fixture paths
  in private `/run` do not establish this proof. Older artifact field names use
  I1c for these gaps; current coordination assigns them to I1O.
- **Unbound apt Runner execution: NOT_TESTED** in the corrected harness; its
  parser/source check passed. Only apt-get/dpkg have authorized fake bindings.
- **I1c final caller/stage glue and full Manager borrowing: NOT_TESTED.** Public
  installer main still uses its raw-FD exclusive context, and the tested Manager
  dispatch lacks a lease keyword. Shared admission was tested directly under the
  canonical lease, not through every public start/select/install transition.
- **Preparing-marker operator reconciliation: NOT_TESTED.** Safe refusal passed;
  the incomplete marker was not silently repaired or promoted to success.
- **Actual cgroup inode replacement and manager outage: NOT_TESTED.** Tested
  expected-identity mismatch/missing-unit behavior is narrower.
- **Real APT/dpkg compatibility, fresh GPU installation, reboot, Docker daemon
  ownership and end-to-end agent readiness: NOT_TESTED.** Packages and audit
  outputs were deliberately synthetic.

Next: root reviews this evidence and the separate I1O/I1c/L1 source deliveries.
A new bounded integration task should consume their final scope-lifetime and
public caller contracts and test the remaining mount-loss/admission paths.
Do not enable full installer apply from I2R's bounded PASS alone.

## Local checks and publication history

After the dependency merge and Revision4 correction, **53 I2R tests** pass.
The **4 affected preparation tests** and **4 canonical export retention tests**
also passed against the unchanged reviewed dependency. Syntax, dry-run,
help, owned-file scope, exact author/committer, credential-free remote/helper,
filename-only secret scan and whitespace gates passed. Independent reviews
checked the dependency's executable diff and the actual matrix/cleanup evidence.

Initial source commit `6cc86b1be53c864e5436f1d3961362a8559140e8` had 49 of 51
methods passing; three subtest failures and one error exposed the missing exact
sandbox option. Those failures were recorded, then resolved only by the reviewed
I1R2 dependency. No production defect was patched inside verification. The
source was published before hosted execution; the complete-history I2R.bundle
was refreshed immediately after each commit. Final evidence changes are report
files only and leave the tested executable source unchanged.

The existing I2P workflow automatically triggered on the initial feature push and
finished before cancellation observation; its primitive result was never
substituted for I2R. For the corrected source push, exact unchanged I2P run
34918085856 was cancelled while queued. The harness reused only I2P context/
capability gates and did not call its unchanged primitive tests.

## Revision4 containment correction and prior execution

The first actual run [34917460102](https://github.com/djeZo888/mixed-memory-llm-api-server/actions/runs/34917460102)
at `23524b50257a1e6ae5aee0d7096a1a2f91c8e231` completed before coordinator
Revision4 arrived. Its 15 ownership cases and cleanup passed. Its `apt_mutation`
negative called Runner for an unbound executable and recorded
`owned_package_transaction_required`. The exact tested Runner raises that code
before subprocess creation. No independent syscall audit was collected, so the
recorded refusal and matching source control flow are the evidence, not a claim
that this first run used the corrected source-only fixture.

The architecture concern was valid: a future admission regression could have
executed real unbound apt. Revision4 explicitly authorized the narrow correction.
Commit `e9fe5d00f9bcc6c1dffc93a3fb75c660aa037a48` changed only the owned preparation
harness/tests: unbound apt is now source-only, and all unbound negative executables
are refused by the harness before Runner. Two regression tests cover permissive
parser and injected unbound-command cases. Exactly two read-only fake bindings
remain; no third binding or production source change was introduced.

The corrected source was published before the second actual run documented
above. Both runs remain preserved: [initial observations](i2r-initial-hosted-evidence.json),
[initial source manifest](i2r-initial-source-manifest.json),
[initial plan](i2r-initial-hosted-plan.json) and
[initial run metadata](i2r-initial-hosted-run.json). The first artifact's digest is
`sha256:aa3c97904529b54583071e4b0658c218adb7050aaa2bd3efc881e08f0609bc14`.
No initial result was retroactively relabelled.

The separate I1 installer workflow failed on both the
[first source](https://github.com/djeZo888/mixed-memory-llm-api-server/actions/runs/34917460062)
and [corrected source](https://github.com/djeZo888/mixed-memory-llm-api-server/actions/runs/34918085845).
I1R2's reviewed report already records failing aggregate installer tests;
this task does not requalify that suite or claim all repository CI passes.
