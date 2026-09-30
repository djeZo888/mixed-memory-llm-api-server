# Chromium seccomp profile

`chromium-seccomp.json` is the captured ai-harness Podman 4.9.3 profile with
one syscall change: its two capability-conditional `chroot` rules are replaced
by one unconditional seccomp allow. All 33 remaining syscall rules, default
deny action, error values and architecture mappings are unchanged.

Chromium creates a nested user namespace for its sandbox and needs
`CAP_SYS_CHROOT` inside that namespace to change its root there. The stock OCI
profile chooses its `chroot` rule from the outer container capabilities when
the container starts; it cannot account for the later nested namespace. With
`--cap-drop=ALL`, the stock filter therefore returns `EPERM` even when the
kernel's namespace capability check would allow Chromium's sandbox operation.
The scoped profile admits the syscall to that kernel check. It does not grant
outer container capabilities, replace Chromium's sandbox or grant host access.

Keep the runner nonroot with all outer capabilities dropped and
`no-new-privileges`. Keep AppArmor and its existing policy unchanged. Do not
use `--privileged`, add outer capabilities, disable seccomp globally or pass
`--no-sandbox`. This is a runner-specific profile selected by the launcher;
the host's `/usr/share/containers/seccomp.json` stays unchanged.

The H001-RUNTIME-BUILD-20260922 Linux smoke observed successful `unshare -Ur`
but stock-profile Chromium termination at
`sys_chroot("/proc/self/fdinfo/") == 0`. With this profile, the same nonroot,
capabilities-dropped, no-new-privileges execution completed a local HTML/JS DOM
fixture. These runs are recorded under
`/home/user/ai-harness-build/H001-RUNTIME-BUILD-20260922/logs/` in
`browser-preflight.log` (exit 134) and `browser-seccomp.log` (exit 0, JS body
`42`). The task's external `RESULT.md` and retained smoke logs are the Linux
evidence authority. This standalone Chromium fixture and the source integrity
test below do not establish native engine browser integration or full deployment
acceptance.

The exact pins are also stored in `identity.json`:

| Artifact | SHA256 |
| --- | --- |
| Captured host profile | `cc374cf23846ce1f62f4dc807a8e2b8673c783c6f56cb475467621035d281e6c` |
| Runner profile | `0474c063b32acee85a1eb5ccfc35f7b1f66278af8da722c45b1d25eb2ae1cfbb` |
| Either profile after removing only singleton `chroot` rules | `615f55e6d11dc878108ab7368c0da74e7288b9a65e168ded110a39b0569337c8` |

The last hash uses UTF-8 JSON with recursively sorted keys and separators
`(',', ':')`, with no trailing newline. It retains every other rule and field.
The original byte-for-byte snapshot is retained outside Git at
`H001-RUNTIME-BUILD-20260922/evidence/host-seccomp-original.json`.

Run from the repository root:

```sh
python3 ai-harness/deploy/tests/test-chromium-seccomp.py
python3 ai-harness/deploy/tests/test-chromium-seccomp.py --source-profile ../evidence/host-seccomp-original.json
```

The second command also verifies the original byte hash, its exact two
conditional `chroot` rules, and full equality of the remaining JSON objects.
A future base-policy or profile change requires review and refreshed identities;
these pins are not a promise that every future Podman profile is equivalent.
