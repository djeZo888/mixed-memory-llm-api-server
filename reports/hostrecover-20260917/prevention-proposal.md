# HOSTRECOVER prevention review draft

Proposal only; no VM contact or mutation by this reviewer. Root worker supplies the final `prevention-proposal.md` and applies nothing before explicit approval in `coordination-input.md`. Based on the copied RESUME1 recovery evidence and the live installed package names supplied by Worker1 on 2026-09-17.

Create each file root:root 0644, with protected root-owned ancestry. Preserve any existing file before a specifically approved replacement. No apt transaction, driver hold/pin, service disable, journal vacuum, or installer work is proposed.

## 1. Disable the two generated apt binary caches

Path: `/etc/apt/apt.conf.d/99-hostrecover-no-binary-cache`

```conf
Dir::Cache::pkgcache "";
Dir::Cache::srcpkgcache "";
```

This prevents regeneration of `pkgcache.bin` and `srcpkgcache.bin`; apt reads repository package metadata as needed. It does not disable `/var/lib/apt/lists`, package downloads, periodic update timers, unattended-upgrades, or security origins. Apt startup can be slower. The two exact cache unlinks remain the separately authorized cleanup operation. Confirm the effective values with `apt-config dump` filtered to these keys and any `Binary::*::Dir::Cache` overrides; a later fragment, main apt.conf, binary-specific option or command argument can override a generic value. [Ubuntu Noble apt.conf manual](https://manpages.ubuntu.com/manpages/noble/man5/apt.conf.5.html)

## 2. Bound persistent journal growth

Path: `/etc/systemd/journald.conf.d/90-hostrecover-root-space.conf`

```ini
[Journal]
SystemMaxUse=128M
SystemKeepFree=4404M
SystemMaxFileSize=16M
```

`4404M` is 4.30078125 GiB, a target above the unchanged 4 GiB STOP guard. The 128 MiB cap allows more than the approximately 67 MiB of journals left by the reviewed cleanup estimate; 16 MiB files give smaller rotation increments. Omit an age-based retention limit so useful low-volume history can remain within the size budget.

These are journald limits, not a root-disk reservation. Active files remain; only archived journals are eligible for automatic removal. Concurrent non-journal growth and starting below the free-space target prevent a hard guarantee. The registered guard remains mandatory. Activation can cause ordinary automatic retention, so approval must acknowledge that oldest archived journals may eventually age out; no explicit vacuum or extra immediate deletion is requested. The protected June/July archive remains outside journald's managed directory. [systemd v255 journald configuration source](https://raw.githubusercontent.com/systemd/systemd/v255/man/journald.conf.xml)

After approval, inspect effective settings with `systemd-analyze cat-config systemd/journald.conf`; allow the already authorized normal reboot to activate them where timing permits. If installed after reboot, a separate explicit journald restart within the approved setting-activation scope is needed; do not assume daemon-reload or a SIGHUP alone applies journald configuration. Verify journald active, no configuration parsing warning, and unchanged full registered guard. Do not assert an exact retained number of days.

## 3. Coordinate only NVIDIA driver-family updates manually

Path: `/etc/apt/apt.conf.d/99-hostrecover-nvidia-manual-upgrades`

```conf
Unattended-Upgrade::Package-Blacklist {
    "^libnvidia-(cfg1|common|compute|decode|encode|extra|fbc1|gl)(-|$)";
    "^nvidia-(compute-utils|dkms|driver|firmware|headless|kernel-common|kernel-source|utils|open)(-|$)";
    "^xserver-xorg-video-nvidia(-|$)";
    "^linux-(modules|objects|signatures)-nvidia(-|$)";
};
```

This adds Python regex entries to the existing blacklist without `#clear`; preserve existing rules. The first three patterns cover every live ABI-coupled 595 driver package supplied by Worker1: the eight `libnvidia-*-595` libraries; `nvidia-compute-utils-595`, `nvidia-dkms-595-open`, `nvidia-driver-595-open`, `nvidia-firmware-595-595.84`, `nvidia-kernel-common-595`, `nvidia-kernel-source-595-open`, `nvidia-utils-595`; and `xserver-xorg-video-nvidia-595`. The fourth covers NVIDIA-specific precompiled kernel-module/object/signature packages if later used; it does not match generic kernel or headers packages.

The delimiter permits the current branch-suffixed packages and unversioned driver-family names. This matters because NVIDIA's own current repository packaging differs from the branch-suffixed packages observed on this host; live inventory remains authoritative. [NVIDIA Ubuntu driver installation guide](https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/ubuntu.html)

Explicitly excluded from these added matches: `nvidia-prime`, `nvidia-settings`, `libnvidia-egl-wayland1`, `libnvidia-container-tools`, `libnvidia-container1`, `nvidia-container-toolkit`, and `nvidia-container-toolkit-base`. Also not matched: apt/dpkg, systemd, libc, openssh, generic Linux kernel/headers, DKMS itself, CUDA toolkit, or unrelated security packages. No Allowed-Origins, APT::Periodic, timer, automatic-reboot or remove-unused policy changes are proposed.

Unattended-upgrades can also defer a nonblacklisted update whose dependency requires a blacklisted driver package. The change does not stop manual apt upgrades; an operator must deliberately upgrade the matching driver packages together, confirm DKMS for intended kernels, and schedule a normal reboot before resumed inference. Thus matching driver security fixes require timely manual maintenance; unrelated security updates remain enabled. [Ubuntu automatic updates documentation](https://ubuntu.com/server/docs/how-to/software/automatic-updates/)

Verify effective blacklist values with narrowly filtered `apt-config dump`, and evaluate the proposed regexes against installed package names plus the explicit nonmatches above. Use this configuration/inventory check, not an unattended-upgrades dry run that could perform logs/cache writes or imply package-update acceptance. No tests were run by this source-only reviewer.

## Boundaries

The draft does not change the private-network systemd compatibility pin, modify source/receipt/state, or solve unrelated future root growth. All VM writes and setting activation require the unchanged installed registered guard, existing ownership, approved exact content, and root coordination. Recovery data/model/driver health and final private API acceptance must come from Worker1/Worker2 durable evidence.
