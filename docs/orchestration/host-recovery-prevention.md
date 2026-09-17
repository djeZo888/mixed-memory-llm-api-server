# HOSTRECOVER host settings

These three small configuration templates were explicitly approved in the
HOSTRECOVER coordination handoff on 2026-09-17. They address the observed apt
cache growth, journal growth and partially upgraded NVIDIA driver stack. They
are host maintenance settings; installer work remains paused.

| Template under `configs/host-recovery/` | Protected installed path (root:root 0644) |
| --- | --- |
| `apt-no-binary-cache.conf` | `/etc/apt/apt.conf.d/99-hostrecover-no-binary-cache` |
| `journald-root-space.conf` | `/etc/systemd/journald.conf.d/90-hostrecover-root-space.conf` |
| `nvidia-manual-upgrades.conf` | `/etc/apt/apt.conf.d/99-hostrecover-nvidia-manual-upgrades` |

The apt fragment disables only the two regenerable binary package indexes.
Repository metadata, periodic updates and security origins remain enabled.
Check both effective cache keys and any binary-specific overrides using
`apt-config dump`; avoid publishing unrelated configuration that may contain
proxy credentials.

The journal fragment requests a 128 MiB persistent size target, 16 MiB files
and 4404 MiB free space. These are best-effort retention controls, not reserved
root capacity. Active journal files remain; ordinary rotation can remove old
archived journals. The separately protected June/July recovery archive under
`/data/logs/hostrecover-20260917/june-july-journals` is outside journald's managed
directory. The unchanged registered 4 GiB STOP / 6 GiB warning guard remains
mandatory. Inspect merged settings with
`systemd-analyze cat-config systemd/journald.conf`. Settings require service
activation; HOSTRECOVER was authorized one post-reboot journald restart.

The NVIDIA fragment appends four driver-family regular expressions to
unattended-upgrades' existing blacklist. It covers versioned NVIDIA userspace
libraries, driver/DKMS/firmware packages and NVIDIA-specific precompiled kernel
modules. It does not match generic kernel/header packages, systemd, libc,
OpenSSH, DKMS itself, or NVIDIA Container Toolkit. Manual apt operations remain
available. A dependency on a blacklisted driver package can also defer an
otherwise unlisted update. NVIDIA driver security fixes therefore require
timely coordinated manual maintenance.

For an explicitly authorized future driver upgrade, first obtain the existing
worker request ownership and canonical lifecycle lease, verify registered
storage and root guard, and confirm no apt/dpkg writer or active request.
Inspect the intended complete driver transaction before applying it. Upgrade
the matching userspace/kernel driver family together; confirm DKMS/module
availability for the intended boot kernel, then preserve Manager intent and
perform a normal reboot. Before restoring inference, repeat mount/root guard,
loaded-versus-installed driver, both-GPU and Docker checks. Use the installed
Manager and exact selected profile; preserve manual policy and rollback.
This note grants no future package-transaction or reboot authorization.

Validation should confirm exact installed template bytes/owner/mode, effective
cache keys, blacklist matches and exclusions, periodic/security settings,
merged journal values, active journald without parse errors, and full registered
guard. Configuration validation is separate from inference and private-client
acceptance. See the dated HOSTRECOVER report for the actual deployment result.

References: [Ubuntu apt.conf](https://manpages.ubuntu.com/manpages/noble/man5/apt.conf.5.html),
[systemd v255 journal settings](https://raw.githubusercontent.com/systemd/systemd/v255/man/journald.conf.xml),
[Ubuntu automatic updates](https://ubuntu.com/server/docs/how-to/software/automatic-updates/).
