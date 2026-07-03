# M5B - NVIDIA Host Driver Installation

- Milestone ID: M5B
- Milestone name: NVIDIA host driver installation
- Timestamp: 2026-07-03T07:27:48+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m5b-nvidia-host-driver
- Main commit: 22d495342d21006f629986b70d9a9a7be39e8d48
- VM snapshot/checkpoint note: human stated a VM snapshot/checkpoint should exist before this task; Codex cannot verify Proxmox snapshot state from inside the guest and did not access the Proxmox host.
- Approved driver target: Ubuntu package `nvidia-driver-595-open` plus `nvidia-utils-595`

## Scope Guard

M5B is host NVIDIA driver installation only. CUDA Toolkit, PyTorch, KTransformers, ik_llama, NVIDIA Container Toolkit, model downloads, inference backend configuration, Docker NVIDIA runtime configuration, Docker/containerd configuration changes, disk/fstab/mountpoint changes, and API exposure are out of scope and were not authorized for this milestone.

## Pre-install Gate Results

- Hostname gate: llmserver
- User: user
- Working directory: /data/services/mixed-memory-llm-api-server
- /data mounted: PASS
- Git identity: CodexAIagent <133749519+djeZo888@users.noreply.github.com>
- Docker Root Dir required: /data/docker
- Approved package source: Ubuntu apt packages only; no NVIDIA .run installer and no NVIDIA CUDA network repo installer.

## Pre-install Inventory

### /etc/os-release

```console
PRETTY_NAME="Ubuntu 24.04.4 LTS"
NAME="Ubuntu"
VERSION_ID="24.04"
VERSION="24.04.4 LTS (Noble Numbat)"
VERSION_CODENAME=noble
ID=ubuntu
ID_LIKE=debian
HOME_URL="https://www.ubuntu.com/"
SUPPORT_URL="https://help.ubuntu.com/"
BUG_REPORT_URL="https://bugs.launchpad.net/ubuntu/"
PRIVACY_POLICY_URL="https://www.ubuntu.com/legal/terms-and-policies/privacy-policy"
UBUNTU_CODENAME=noble
LOGO=ubuntu-logo
```

### uname -a

```console
Linux llmserver 6.8.0-134-generic #134-Ubuntu SMP PREEMPT_DYNAMIC Fri Jun 26 18:43:11 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
```

### Installed NVIDIA/CUDA/container-toolkit packages before install

```console
```

### Manual NVIDIA/CUDA/container-toolkit packages before install

```console
```

### PCI GPU inventory

```console
00:01.0 VGA compatible controller [0300]: Device [1234:1111] (rev 02)
01:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
01:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)
02:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
02:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)
```

### PCI driver binding inventory

```console
00:01.0 VGA compatible controller [0300]: Device [1234:1111] (rev 02)
	Subsystem: Red Hat, Inc. Device [1af4:1100]
	Kernel driver in use: bochs-drm
	Kernel modules: bochs
00:1a.0 USB controller [0c03]: Intel Corporation 82801I (ICH9 Family) USB UHCI Controller #4 [8086:2937] (rev 03)
	Subsystem: Red Hat, Inc. QEMU Virtual Machine [1af4:1100]
--
01:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
	Subsystem: NVIDIA Corporation Device [10de:204b]
	Kernel modules: nvidiafb, nouveau
01:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)
	Subsystem: NVIDIA Corporation Device [10de:0000]
	Kernel driver in use: snd_hda_intel
	Kernel modules: snd_hda_intel
02:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
	Subsystem: NVIDIA Corporation Device [10de:204b]
	Kernel modules: nvidiafb, nouveau
02:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)
	Subsystem: NVIDIA Corporation Device [10de:0000]
	Kernel driver in use: snd_hda_intel
	Kernel modules: snd_hda_intel
05:01.0 PCI bridge [0604]: Red Hat, Inc. QEMU PCI-PCI bridge [1b36:0001]
05:02.0 PCI bridge [0604]: Red Hat, Inc. QEMU PCI-PCI bridge [1b36:0001]
05:03.0 PCI bridge [0604]: Red Hat, Inc. QEMU PCI-PCI bridge [1b36:0001]
```

### Loaded GPU modules before install

```console
nouveau              3096576  0
mxm_wmi                12288  1 nouveau
drm_gpuvm              45056  1 nouveau
drm_exec               12288  2 drm_gpuvm,nouveau
gpu_sched              61440  1 nouveau
drm_display_helper    237568  1 nouveau
i2c_algo_bit           16384  1 nouveau
video                  77824  1 nouveau
wmi                    28672  3 video,mxm_wmi,nouveau
drm_ttm_helper         12288  3 bochs,drm_vram_helper,nouveau
ttm                   110592  3 drm_vram_helper,drm_ttm_helper,nouveau
```

### nvidia-smi before install

```console
bash: line 1: nvidia-smi: command not found
```

### nvcc before install

```console
bash: line 1: nvcc: command not found
```

## Package Availability And Install Simulation

## Package Availability And Install Simulation (retry after reporter formatting failure)

- Timestamp: 2026-07-03T07:29:40+00:00

### apt update

```console
$ sudo -n apt update

WARNING: apt does not have a stable CLI interface. Use with caution in scripts.

Hit:1 http://si.archive.ubuntu.com/ubuntu noble InRelease
Get:2 http://si.archive.ubuntu.com/ubuntu noble-updates InRelease [126 kB]
Hit:3 http://si.archive.ubuntu.com/ubuntu noble-backports InRelease
Get:4 https://download.docker.com/linux/ubuntu noble InRelease [48.5 kB]
Get:5 http://security.ubuntu.com/ubuntu noble-security InRelease [126 kB]
Get:6 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 Packages [1074 kB]
Get:7 http://si.archive.ubuntu.com/ubuntu noble-updates/main Translation-en [266 kB]
Get:8 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 c-n-f Metadata [17.6 kB]
Get:9 http://si.archive.ubuntu.com/ubuntu noble-updates/restricted amd64 Packages [1196 kB]
Get:10 http://si.archive.ubuntu.com/ubuntu noble-updates/universe amd64 Packages [1658 kB]
Get:11 http://security.ubuntu.com/ubuntu noble-security/main amd64 Components [44.8 kB]
Get:12 http://security.ubuntu.com/ubuntu noble-security/universe amd64 Components [76.3 kB]
Get:13 http://si.archive.ubuntu.com/ubuntu noble-updates/universe amd64 c-n-f Metadata [34.9 kB]
Fetched 4670 kB in 0s (11.6 MB/s)
Reading package lists...
Building dependency tree...
Reading state information...
1 package can be upgraded. Run 'apt list --upgradable' to see it.

[exit=0]
```

### ubuntu-drivers list --gpgpu

```console
$ ubuntu-drivers list --gpgpu
udevadm hwdb is deprecated. Use systemd-hwdb instead.
udevadm hwdb is deprecated. Use systemd-hwdb instead.
udevadm hwdb is deprecated. Use systemd-hwdb instead.
udevadm hwdb is deprecated. Use systemd-hwdb instead.
udevadm hwdb is deprecated. Use systemd-hwdb instead.
udevadm hwdb is deprecated. Use systemd-hwdb instead.
udevadm hwdb is deprecated. Use systemd-hwdb instead.
udevadm hwdb is deprecated. Use systemd-hwdb instead.
nvidia-driver-595-server-open, (kernel modules provided by linux-modules-nvidia-595-server-open-generic)
nvidia-driver-580-server-open, (kernel modules provided by linux-modules-nvidia-580-server-open-generic)
nvidia-driver-595-server, (kernel modules provided by linux-modules-nvidia-595-server-generic)
nvidia-driver-580-server, (kernel modules provided by linux-modules-nvidia-580-server-generic)
nvidia-driver-595-open, (kernel modules provided by linux-modules-nvidia-595-open-generic)
nvidia-driver-580-open, (kernel modules provided by linux-modules-nvidia-580-open-generic)
nvidia-driver-595, (kernel modules provided by linux-modules-nvidia-595-generic)
nvidia-driver-580, (kernel modules provided by linux-modules-nvidia-580-generic)

[exit=0]
```

### ubuntu-drivers devices

```console
$ ubuntu-drivers devices
udevadm hwdb is deprecated. Use systemd-hwdb instead.
udevadm hwdb is deprecated. Use systemd-hwdb instead.
udevadm hwdb is deprecated. Use systemd-hwdb instead.
udevadm hwdb is deprecated. Use systemd-hwdb instead.
udevadm hwdb is deprecated. Use systemd-hwdb instead.
udevadm hwdb is deprecated. Use systemd-hwdb instead.
udevadm hwdb is deprecated. Use systemd-hwdb instead.
udevadm hwdb is deprecated. Use systemd-hwdb instead.
ERROR:root:aplay command not found
== /sys/devices/pci0000:00/0000:00:1c.1/0000:02:00.0 ==
modalias : pci:v000010DEd00002BB1sv000010DEsd0000204Bbc03sc00i00
vendor   : NVIDIA Corporation
driver   : nvidia-driver-595 - distro non-free
driver   : nvidia-driver-595-server-open - distro non-free
driver   : nvidia-driver-595-server - distro non-free
driver   : nvidia-driver-595-open - distro non-free recommended
driver   : nvidia-driver-580 - distro non-free
driver   : nvidia-driver-580-server - distro non-free
driver   : nvidia-driver-580-open - distro non-free
driver   : nvidia-driver-580-server-open - distro non-free
driver   : xserver-xorg-video-nouveau - distro free builtin


[exit=0]
```

### apt-cache policy for M5B driver packages

```console
$ apt-cache policy nvidia-driver-595-open nvidia-utils-595 linux-modules-nvidia-595-open-generic linux-modules-nvidia-595-open-6.8.0-134-generic nvidia-dkms-595-open nvidia-firmware-595-* 2>/dev/null || true
nvidia-driver-595-open:
  Installed: (none)
  Candidate: 595.71.05-0ubuntu0.24.04.1
  Version table:
     595.71.05-0ubuntu0.24.04.1 500
        500 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 Packages
        500 http://security.ubuntu.com/ubuntu noble-security/multiverse amd64 Packages
nvidia-utils-595:
  Installed: (none)
  Candidate: 595.71.05-0ubuntu0.24.04.1
  Version table:
     595.71.05-0ubuntu0.24.04.1 500
        500 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 Packages
        500 http://security.ubuntu.com/ubuntu noble-security/multiverse amd64 Packages
linux-modules-nvidia-595-open-generic:
  Installed: (none)
  Candidate: 6.8.0-134.134
  Version table:
     6.8.0-134.134 500
        500 http://si.archive.ubuntu.com/ubuntu noble-updates/restricted amd64 Packages
        500 http://security.ubuntu.com/ubuntu noble-security/restricted amd64 Packages
linux-modules-nvidia-595-open-6.8.0-134-generic:
  Installed: (none)
  Candidate: 6.8.0-134.134
  Version table:
     6.8.0-134.134 500
        500 http://si.archive.ubuntu.com/ubuntu noble-updates/restricted amd64 Packages
        500 http://security.ubuntu.com/ubuntu noble-security/restricted amd64 Packages
nvidia-dkms-595-open:
  Installed: (none)
  Candidate: 595.71.05-0ubuntu0.24.04.1
  Version table:
     595.71.05-0ubuntu0.24.04.1 500
        500 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 Packages
        500 http://security.ubuntu.com/ubuntu noble-security/multiverse amd64 Packages
nvidia-firmware-595-595.58.03:
  Installed: (none)
  Candidate: 595.58.03-0ubuntu0.24.04.1
  Version table:
     595.58.03-0ubuntu0.24.04.1 500
        500 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 Packages
nvidia-firmware-595-server-595.71.05:
  Installed: (none)
  Candidate: 595.71.05-0ubuntu0.24.04.1
  Version table:
     595.71.05-0ubuntu0.24.04.1 500
        500 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 Packages
        500 http://security.ubuntu.com/ubuntu noble-security/multiverse amd64 Packages
nvidia-firmware-595-595.71.05:
  Installed: (none)
  Candidate: 595.71.05-0ubuntu0.24.04.1
  Version table:
     595.71.05-0ubuntu0.24.04.1 500
        500 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 Packages
        500 http://security.ubuntu.com/ubuntu noble-security/multiverse amd64 Packages
nvidia-firmware-595-server-595.58.03:
  Installed: (none)
  Candidate: 595.58.03-0ubuntu0.24.04.1
  Version table:
     595.58.03-0ubuntu0.24.04.1 500
        500 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 Packages

[exit=0]
```

## Package Candidate And Install Simulation (strict parser retry)

- Timestamp: 2026-07-03T07:30:19+00:00

### nvidia-driver-595-open availability gate

- Candidate: `595.71.05-0ubuntu0.24.04.1`

### apt install simulation

```console
$ sudo -n apt-get -s install nvidia-driver-595-open nvidia-utils-595
Reading package lists...
Building dependency tree...
Reading state information...
The following packages were automatically installed and are no longer required:
  libfwupd2 libgusb2
Use 'sudo apt autoremove' to remove them.
The following additional packages will be installed:
  adwaita-icon-theme at-spi2-common at-spi2-core binutils binutils-common
  binutils-x86-64-linux-gnu build-essential bzip2 cpp cpp-13
  cpp-13-x86-64-linux-gnu cpp-x86-64-linux-gnu dconf-gsettings-backend
  dconf-service dkms dpkg-dev fakeroot fontconfig g++ g++-13
  g++-13-x86-64-linux-gnu g++-x86-64-linux-gnu gcc gcc-13 gcc-13-base
  gcc-13-x86-64-linux-gnu gcc-x86-64-linux-gnu gsettings-desktop-schemas
  gtk-update-icon-cache hicolor-icon-theme humanity-icon-theme
  libalgorithm-diff-perl libalgorithm-diff-xs-perl libalgorithm-merge-perl
  libasan8 libatk-bridge2.0-0t64 libatk1.0-0t64 libatomic1 libatspi2.0-0t64
  libavahi-client3 libavahi-common-data libavahi-common3 libbinutils
  libcairo-gobject2 libcairo2 libcc1-0 libcolord2 libctf-nobfd0 libctf0
  libcups2t64 libdatrie1 libdconf1 libdpkg-perl libdrm-intel1 libegl-mesa0
  libegl1 libepoxy0 libfakeroot libfile-fcntllock-perl libfontenc1 libgbm1
  libgcc-13-dev libgdk-pixbuf-2.0-0 libgdk-pixbuf2.0-bin
  libgdk-pixbuf2.0-common libgl1 libgl1-mesa-dri libglvnd0 libglx-mesa0
  libglx0 libgomp1 libgprofng0 libgraphite2-3 libgtk-3-0t64 libgtk-3-bin
  libgtk-3-common libharfbuzz0b libhwasan0 libice6 libisl23 libitm1 liblcms2-2
  libllvm20 liblsan0 libmpc3 libnvidia-cfg1-595 libnvidia-common-595
  libnvidia-compute-595 libnvidia-decode-595 libnvidia-egl-wayland1
  libnvidia-encode-595 libnvidia-extra-595 libnvidia-fbc1-595 libnvidia-gl-595
  libpango-1.0-0 libpangocairo-1.0-0 libpangoft2-1.0-0 libpciaccess0
  libpixman-1-0 libpkgconf3 libquadmath0 librsvg2-2 librsvg2-common libsframe1
  libsm6 libstdc++-13-dev libthai-data libthai0 libtsan2 libubsan1 libvdpau1
  libvulkan1 libwayland-client0 libwayland-cursor0 libwayland-egl1
  libwayland-server0 libx11-xcb1 libxaw7 libxcb-dri3-0 libxcb-glx0
  libxcb-present0 libxcb-randr0 libxcb-render0 libxcb-shm0 libxcb-sync1
  libxcb-xfixes0 libxcomposite1 libxcursor1 libxcvt0 libxdamage1 libxfixes3
  libxfont2 libxi6 libxinerama1 libxkbfile1 libxmu6 libxnvctrl0 libxrandr2
  libxrender1 libxshmfence1 libxt6t64 libxtst6 libxxf86vm1 lto-disabled-list
  make mesa-libgallium mesa-vdpau-drivers mesa-vulkan-drivers
  nvidia-compute-utils-595 nvidia-dkms-595-open nvidia-firmware-595-595.71.05
  nvidia-kernel-common-595 nvidia-kernel-source-595-open nvidia-prime
  nvidia-settings ocl-icd-libopencl1 pkexec pkg-config pkgconf pkgconf-bin
  screen-resolution-extra session-migration ubuntu-mono vdpau-driver-all
  x11-common x11-xkb-utils xcvt xfonts-base xfonts-encodings xfonts-utils
  xserver-common xserver-xorg-core xserver-xorg-video-nvidia-595
Suggested packages:
  binutils-doc gprofng-gui bzip2-doc cpp-doc gcc-13-locales cpp-13-doc menu
  debian-keyring g++-multilib g++-13-multilib gcc-13-doc gcc-multilib autoconf
  automake libtool flex bison gdb gcc-doc gcc-13-multilib gdb-x86-64-linux-gnu
  colord cups-common bzr gvfs liblcms2-utils librsvg2-bin libstdc++-13-doc
  make-doc nvidia-driver-595 libvdpau-va-gl1 xfs | xserver xfonts-100dpi
  | xfonts-75dpi xfonts-scalable
Recommended packages:
  libnvidia-compute-595:i386 libnvidia-decode-595:i386
  libnvidia-encode-595:i386 libnvidia-fbc1-595:i386 libnvidia-gl-595:i386
The following NEW packages will be installed:
  adwaita-icon-theme at-spi2-common at-spi2-core binutils binutils-common
  binutils-x86-64-linux-gnu build-essential bzip2 cpp cpp-13
  cpp-13-x86-64-linux-gnu cpp-x86-64-linux-gnu dconf-gsettings-backend
  dconf-service dkms dpkg-dev fakeroot fontconfig g++ g++-13
  g++-13-x86-64-linux-gnu g++-x86-64-linux-gnu gcc gcc-13 gcc-13-base
  gcc-13-x86-64-linux-gnu gcc-x86-64-linux-gnu gsettings-desktop-schemas
  gtk-update-icon-cache hicolor-icon-theme humanity-icon-theme
  libalgorithm-diff-perl libalgorithm-diff-xs-perl libalgorithm-merge-perl
  libasan8 libatk-bridge2.0-0t64 libatk1.0-0t64 libatomic1 libatspi2.0-0t64
  libavahi-client3 libavahi-common-data libavahi-common3 libbinutils
  libcairo-gobject2 libcairo2 libcc1-0 libcolord2 libctf-nobfd0 libctf0
  libcups2t64 libdatrie1 libdconf1 libdpkg-perl libdrm-intel1 libegl-mesa0
  libegl1 libepoxy0 libfakeroot libfile-fcntllock-perl libfontenc1 libgbm1
  libgcc-13-dev libgdk-pixbuf-2.0-0 libgdk-pixbuf2.0-bin
  libgdk-pixbuf2.0-common libgl1 libgl1-mesa-dri libglvnd0 libglx-mesa0
  libglx0 libgomp1 libgprofng0 libgraphite2-3 libgtk-3-0t64 libgtk-3-bin
  libgtk-3-common libharfbuzz0b libhwasan0 libice6 libisl23 libitm1 liblcms2-2
  libllvm20 liblsan0 libmpc3 libnvidia-cfg1-595 libnvidia-common-595
  libnvidia-compute-595 libnvidia-decode-595 libnvidia-egl-wayland1
  libnvidia-encode-595 libnvidia-extra-595 libnvidia-fbc1-595 libnvidia-gl-595
  libpango-1.0-0 libpangocairo-1.0-0 libpangoft2-1.0-0 libpciaccess0
  libpixman-1-0 libpkgconf3 libquadmath0 librsvg2-2 librsvg2-common libsframe1
  libsm6 libstdc++-13-dev libthai-data libthai0 libtsan2 libubsan1 libvdpau1
  libvulkan1 libwayland-client0 libwayland-cursor0 libwayland-egl1
  libwayland-server0 libx11-xcb1 libxaw7 libxcb-dri3-0 libxcb-glx0
  libxcb-present0 libxcb-randr0 libxcb-render0 libxcb-shm0 libxcb-sync1
  libxcb-xfixes0 libxcomposite1 libxcursor1 libxcvt0 libxdamage1 libxfixes3
  libxfont2 libxi6 libxinerama1 libxkbfile1 libxmu6 libxnvctrl0 libxrandr2
  libxrender1 libxshmfence1 libxt6t64 libxtst6 libxxf86vm1 lto-disabled-list
  make mesa-libgallium mesa-vdpau-drivers mesa-vulkan-drivers
  nvidia-compute-utils-595 nvidia-dkms-595-open nvidia-driver-595-open
  nvidia-firmware-595-595.71.05 nvidia-kernel-common-595
  nvidia-kernel-source-595-open nvidia-prime nvidia-settings nvidia-utils-595
  ocl-icd-libopencl1 pkexec pkg-config pkgconf pkgconf-bin
  screen-resolution-extra session-migration ubuntu-mono vdpau-driver-all
  x11-common x11-xkb-utils xcvt xfonts-base xfonts-encodings xfonts-utils
  xserver-common xserver-xorg-core xserver-xorg-video-nvidia-595
0 upgraded, 175 newly installed, 0 to remove and 1 not upgraded.
Inst gcc-13-base (13.3.0-6ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libisl23 (0.26-3build1.1 Ubuntu:24.04/noble-updates [amd64])
Inst libmpc3 (1.3.1-1build1.1 Ubuntu:24.04/noble-updates [amd64])
Inst cpp-13-x86-64-linux-gnu (13.3.0-6ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst cpp-13 (13.3.0-6ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst cpp-x86-64-linux-gnu (4:13.2.0-7ubuntu1 Ubuntu:24.04/noble [amd64])
Inst cpp (4:13.2.0-7ubuntu1 Ubuntu:24.04/noble [amd64])
Inst libcc1-0 (14.2.0-4ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst binutils-common (2.42-4ubuntu2.10 Ubuntu:24.04/noble-updates [amd64])
Inst libsframe1 (2.42-4ubuntu2.10 Ubuntu:24.04/noble-updates [amd64])
Inst libbinutils (2.42-4ubuntu2.10 Ubuntu:24.04/noble-updates [amd64])
Inst libctf-nobfd0 (2.42-4ubuntu2.10 Ubuntu:24.04/noble-updates [amd64])
Inst libctf0 (2.42-4ubuntu2.10 Ubuntu:24.04/noble-updates [amd64])
Inst libgprofng0 (2.42-4ubuntu2.10 Ubuntu:24.04/noble-updates [amd64])
Inst binutils-x86-64-linux-gnu (2.42-4ubuntu2.10 Ubuntu:24.04/noble-updates [amd64])
Inst libgomp1 (14.2.0-4ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libitm1 (14.2.0-4ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libatomic1 (14.2.0-4ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libasan8 (14.2.0-4ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst liblsan0 (14.2.0-4ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libtsan2 (14.2.0-4ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libubsan1 (14.2.0-4ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libhwasan0 (14.2.0-4ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libquadmath0 (14.2.0-4ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libgcc-13-dev (13.3.0-6ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst gcc-13-x86-64-linux-gnu (13.3.0-6ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst binutils (2.42-4ubuntu2.10 Ubuntu:24.04/noble-updates [amd64])
Inst gcc-13 (13.3.0-6ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst gcc-x86-64-linux-gnu (4:13.2.0-7ubuntu1 Ubuntu:24.04/noble [amd64])
Inst gcc (4:13.2.0-7ubuntu1 Ubuntu:24.04/noble [amd64])
Inst libdpkg-perl (1.22.6ubuntu6.6 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [all])
Inst bzip2 (1.0.8-5.1build0.1 Ubuntu:24.04/noble-updates [amd64])
Inst make (4.3-4.1build2 Ubuntu:24.04/noble [amd64])
Inst lto-disabled-list (47 Ubuntu:24.04/noble [all])
Inst dpkg-dev (1.22.6ubuntu6.6 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [all])
Inst libstdc++-13-dev (13.3.0-6ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst g++-13-x86-64-linux-gnu (13.3.0-6ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst g++-13 (13.3.0-6ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst g++-x86-64-linux-gnu (4:13.2.0-7ubuntu1 Ubuntu:24.04/noble [amd64])
Inst g++ (4:13.2.0-7ubuntu1 Ubuntu:24.04/noble [amd64])
Inst build-essential (12.10ubuntu1 Ubuntu:24.04/noble [amd64])
Inst dkms (3.0.11-1ubuntu13 Ubuntu:24.04/noble [all])
Inst libgdk-pixbuf2.0-common (2.42.10+dfsg-3ubuntu3.3 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [all])
Inst libgdk-pixbuf-2.0-0 (2.42.10+dfsg-3ubuntu3.3 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst gtk-update-icon-cache (3.24.41-4ubuntu1.3 Ubuntu:24.04/noble-updates [amd64])
Inst hicolor-icon-theme (0.17-2 Ubuntu:24.04/noble [all])
Inst humanity-icon-theme (0.6.16 Ubuntu:24.04/noble [all]) []
Inst ubuntu-mono (24.04-0ubuntu1 Ubuntu:24.04/noble [all]) []
Inst adwaita-icon-theme (46.0-1 Ubuntu:24.04/noble [all])
Inst at-spi2-common (2.52.0-1build1 Ubuntu:24.04/noble [all])
Inst libxi6 (2:1.8.1-1build1 Ubuntu:24.04/noble [amd64])
Inst libatspi2.0-0t64 (2.52.0-1build1 Ubuntu:24.04/noble [amd64])
Inst x11-common (1:7.7+23ubuntu3 Ubuntu:24.04/noble [all])
Inst libxtst6 (2:1.2.3-1.1build1 Ubuntu:24.04/noble [amd64])
Inst libdconf1 (0.40.0-4ubuntu0.1 Ubuntu:24.04/noble-updates [amd64])
Inst dconf-service (0.40.0-4ubuntu0.1 Ubuntu:24.04/noble-updates [amd64])
Inst dconf-gsettings-backend (0.40.0-4ubuntu0.1 Ubuntu:24.04/noble-updates [amd64])
Inst session-migration (0.3.9build1 Ubuntu:24.04/noble [amd64])
Inst gsettings-desktop-schemas (46.1-0ubuntu1 Ubuntu:24.04/noble-updates [all])
Inst at-spi2-core (2.52.0-1build1 Ubuntu:24.04/noble [amd64])
Inst libfakeroot (1.33-1 Ubuntu:24.04/noble [amd64])
Inst fakeroot (1.33-1 Ubuntu:24.04/noble [amd64])
Inst fontconfig (2.15.0-1.1ubuntu2 Ubuntu:24.04/noble [amd64])
Inst libalgorithm-diff-perl (1.201-1 Ubuntu:24.04/noble [all])
Inst libalgorithm-diff-xs-perl (0.04-8build3 Ubuntu:24.04/noble [amd64])
Inst libalgorithm-merge-perl (0.08-5 Ubuntu:24.04/noble [all])
Inst libatk1.0-0t64 (2.52.0-1build1 Ubuntu:24.04/noble [amd64])
Inst libatk-bridge2.0-0t64 (2.52.0-1build1 Ubuntu:24.04/noble [amd64])
Inst libavahi-common-data (0.8-13ubuntu6.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libavahi-common3 (0.8-13ubuntu6.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libavahi-client3 (0.8-13ubuntu6.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libpixman-1-0 (0.42.2-1build1 Ubuntu:24.04/noble [amd64])
Inst libxcb-render0 (1.15-1ubuntu2 Ubuntu:24.04/noble [amd64])
Inst libxcb-shm0 (1.15-1ubuntu2 Ubuntu:24.04/noble [amd64])
Inst libxrender1 (1:0.9.10-1.1build1 Ubuntu:24.04/noble [amd64])
Inst libcairo2 (1.18.0-3build1 Ubuntu:24.04/noble [amd64])
Inst libcairo-gobject2 (1.18.0-3build1 Ubuntu:24.04/noble [amd64])
Inst liblcms2-2 (2.14-2ubuntu0.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libcolord2 (1.4.7-1build2 Ubuntu:24.04/noble [amd64])
Inst libcups2t64 (2.4.7-1.2ubuntu7.14 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libdatrie1 (0.2.13-3build1 Ubuntu:24.04/noble [amd64])
Inst libpciaccess0 (0.17-3ubuntu0.24.04.2 Ubuntu:24.04/noble-updates [amd64])
Inst libdrm-intel1 (2.4.125-1ubuntu0.1~24.04.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libllvm20 (1:20.1.2-0ubuntu1~24.04.3 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libx11-xcb1 (2:1.8.7-1build1 Ubuntu:24.04/noble [amd64])
Inst libxcb-dri3-0 (1.15-1ubuntu2 Ubuntu:24.04/noble [amd64])
Inst libxcb-present0 (1.15-1ubuntu2 Ubuntu:24.04/noble [amd64])
Inst libxcb-randr0 (1.15-1ubuntu2 Ubuntu:24.04/noble [amd64])
Inst libxcb-sync1 (1.15-1ubuntu2 Ubuntu:24.04/noble [amd64])
Inst libxcb-xfixes0 (1.15-1ubuntu2 Ubuntu:24.04/noble [amd64])
Inst libxshmfence1 (1.3-1build5 Ubuntu:24.04/noble [amd64])
Inst mesa-libgallium (25.2.8-0ubuntu0.24.04.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libgbm1 (25.2.8-0ubuntu0.24.04.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libwayland-client0 (1.22.0-2.1build1 Ubuntu:24.04/noble [amd64])
Inst libegl-mesa0 (25.2.8-0ubuntu0.24.04.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libepoxy0 (1.5.10-1build1 Ubuntu:24.04/noble [amd64])
Inst libfile-fcntllock-perl (0.22-4ubuntu5 Ubuntu:24.04/noble [amd64])
Inst libfontenc1 (1:1.1.8-1build1 Ubuntu:24.04/noble [amd64])
Inst libgdk-pixbuf2.0-bin (2.42.10+dfsg-3ubuntu3.3 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libvulkan1 (1.3.275.0-1build1 Ubuntu:24.04/noble [amd64])
Inst libgl1-mesa-dri (25.2.8-0ubuntu0.24.04.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libxcb-glx0 (1.15-1ubuntu2 Ubuntu:24.04/noble [amd64])
Inst libxxf86vm1 (1:1.1.4-1build4 Ubuntu:24.04/noble [amd64])
Inst libglx-mesa0 (25.2.8-0ubuntu0.24.04.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libgraphite2-3 (1.3.14-2ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libharfbuzz0b (8.3.0-2build2 Ubuntu:24.04/noble [amd64])
Inst libthai-data (0.1.29-2build1 Ubuntu:24.04/noble [all])
Inst libthai0 (0.1.29-2build1 Ubuntu:24.04/noble [amd64])
Inst libpango-1.0-0 (1.52.1+ds-1build1 Ubuntu:24.04/noble [amd64])
Inst libpangoft2-1.0-0 (1.52.1+ds-1build1 Ubuntu:24.04/noble [amd64])
Inst libpangocairo-1.0-0 (1.52.1+ds-1build1 Ubuntu:24.04/noble [amd64])
Inst libwayland-cursor0 (1.22.0-2.1build1 Ubuntu:24.04/noble [amd64])
Inst libwayland-egl1 (1.22.0-2.1build1 Ubuntu:24.04/noble [amd64])
Inst libxcomposite1 (1:0.4.5-1build3 Ubuntu:24.04/noble [amd64])
Inst libxfixes3 (1:6.0.0-2build1 Ubuntu:24.04/noble [amd64])
Inst libxcursor1 (1:1.2.1-1build1 Ubuntu:24.04/noble [amd64])
Inst libxdamage1 (1:1.1.6-1build1 Ubuntu:24.04/noble [amd64])
Inst libxinerama1 (2:1.1.4-3build1 Ubuntu:24.04/noble [amd64])
Inst libxrandr2 (2:1.5.2-2build1 Ubuntu:24.04/noble [amd64])
Inst libgtk-3-common (3.24.41-4ubuntu1.3 Ubuntu:24.04/noble-updates [all])
Inst libgtk-3-0t64 (3.24.41-4ubuntu1.3 Ubuntu:24.04/noble-updates [amd64])
Inst libgtk-3-bin (3.24.41-4ubuntu1.3 Ubuntu:24.04/noble-updates [amd64])
Inst libice6 (2:1.0.10-1build3 Ubuntu:24.04/noble [amd64])
Inst nvidia-firmware-595-595.71.05 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst nvidia-kernel-common-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libnvidia-cfg1-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libnvidia-common-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst ocl-icd-libopencl1 (2.3.2-1build1 Ubuntu:24.04/noble, Ubuntu:24.04/noble-updates [amd64])
Inst libnvidia-compute-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libnvidia-decode-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libwayland-server0 (1.22.0-2.1build1 Ubuntu:24.04/noble [amd64])
Inst libnvidia-egl-wayland1 (1:1.1.13-1ubuntu0.1 Ubuntu:24.04/noble-updates [amd64])
Inst libnvidia-encode-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libnvidia-extra-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libnvidia-fbc1-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libnvidia-gl-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst libpkgconf3 (1.8.1-2build1 Ubuntu:24.04/noble [amd64])
Inst librsvg2-2 (2.58.0+dfsg-1build1 Ubuntu:24.04/noble [amd64])
Inst librsvg2-common (2.58.0+dfsg-1build1 Ubuntu:24.04/noble [amd64])
Inst libsm6 (2:1.2.3-1build3 Ubuntu:24.04/noble [amd64])
Inst libvdpau1 (1.5-2build1 Ubuntu:24.04/noble [amd64])
Inst libxt6t64 (1:1.2.1-1.2build1 Ubuntu:24.04/noble [amd64])
Inst libxmu6 (2:1.1.3-3build2 Ubuntu:24.04/noble [amd64])
Inst libxaw7 (2:1.0.14-1build2 Ubuntu:24.04/noble [amd64])
Inst libxcvt0 (0.1.2-1build1 Ubuntu:24.04/noble [amd64])
Inst libxfont2 (1:2.0.6-1build1 Ubuntu:24.04/noble [amd64])
Inst libxkbfile1 (1:1.1.0-1build4 Ubuntu:24.04/noble [amd64])
Inst libxnvctrl0 (510.47.03-0ubuntu4.24.04.1 Ubuntu:24.04/noble-updates [amd64])
Inst mesa-vdpau-drivers (25.2.8-0ubuntu0.24.04.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst mesa-vulkan-drivers (25.2.8-0ubuntu0.24.04.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst nvidia-compute-utils-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst nvidia-kernel-source-595-open (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst nvidia-dkms-595-open (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst nvidia-utils-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst x11-xkb-utils (7.7+8build2 Ubuntu:24.04/noble [amd64])
Inst xserver-common (2:21.1.12-1ubuntu1.6 Ubuntu:24.04/noble-updates [all])
Inst libglvnd0 (1.7.0-1build1 Ubuntu:24.04/noble [amd64])
Inst libegl1 (1.7.0-1build1 Ubuntu:24.04/noble [amd64])
Inst libglx0 (1.7.0-1build1 Ubuntu:24.04/noble [amd64])
Inst libgl1 (1.7.0-1build1 Ubuntu:24.04/noble [amd64])
Inst xserver-xorg-core (2:21.1.12-1ubuntu1.6 Ubuntu:24.04/noble-updates [amd64])
Inst xserver-xorg-video-nvidia-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst nvidia-driver-595-open (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst nvidia-prime (0.8.17.2 Ubuntu:24.04/noble [all])
Inst pkgconf-bin (1.8.1-2build1 Ubuntu:24.04/noble [amd64])
Inst pkgconf (1.8.1-2build1 Ubuntu:24.04/noble [amd64])
Inst pkg-config (1.8.1-2build1 Ubuntu:24.04/noble [amd64])
Inst pkexec (124-2ubuntu1.24.04.3 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst screen-resolution-extra (0.18.3ubuntu0.24.04.1 Ubuntu:24.04/noble-updates [all])
Inst nvidia-settings (510.47.03-0ubuntu4.24.04.1 Ubuntu:24.04/noble-updates [amd64])
Inst vdpau-driver-all (1.5-2build1 Ubuntu:24.04/noble [amd64])
Inst xcvt (0.1.2-1build1 Ubuntu:24.04/noble [amd64])
Inst xfonts-encodings (1:1.0.5-0ubuntu2 Ubuntu:24.04/noble [all])
Inst xfonts-utils (1:7.7+6build3 Ubuntu:24.04/noble [amd64])
Inst xfonts-base (1:1.0.5+nmu1 Ubuntu:24.04/noble [all])
Conf gcc-13-base (13.3.0-6ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libisl23 (0.26-3build1.1 Ubuntu:24.04/noble-updates [amd64])
Conf libmpc3 (1.3.1-1build1.1 Ubuntu:24.04/noble-updates [amd64])
Conf cpp-13-x86-64-linux-gnu (13.3.0-6ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf cpp-13 (13.3.0-6ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf cpp-x86-64-linux-gnu (4:13.2.0-7ubuntu1 Ubuntu:24.04/noble [amd64])
Conf cpp (4:13.2.0-7ubuntu1 Ubuntu:24.04/noble [amd64])
Conf libcc1-0 (14.2.0-4ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf binutils-common (2.42-4ubuntu2.10 Ubuntu:24.04/noble-updates [amd64])
Conf libsframe1 (2.42-4ubuntu2.10 Ubuntu:24.04/noble-updates [amd64])
Conf libbinutils (2.42-4ubuntu2.10 Ubuntu:24.04/noble-updates [amd64])
Conf libctf-nobfd0 (2.42-4ubuntu2.10 Ubuntu:24.04/noble-updates [amd64])
Conf libctf0 (2.42-4ubuntu2.10 Ubuntu:24.04/noble-updates [amd64])
Conf libgprofng0 (2.42-4ubuntu2.10 Ubuntu:24.04/noble-updates [amd64])
Conf binutils-x86-64-linux-gnu (2.42-4ubuntu2.10 Ubuntu:24.04/noble-updates [amd64])
Conf libgomp1 (14.2.0-4ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libitm1 (14.2.0-4ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libatomic1 (14.2.0-4ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libasan8 (14.2.0-4ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf liblsan0 (14.2.0-4ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libtsan2 (14.2.0-4ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libubsan1 (14.2.0-4ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libhwasan0 (14.2.0-4ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libquadmath0 (14.2.0-4ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libgcc-13-dev (13.3.0-6ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf gcc-13-x86-64-linux-gnu (13.3.0-6ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf binutils (2.42-4ubuntu2.10 Ubuntu:24.04/noble-updates [amd64])
Conf gcc-13 (13.3.0-6ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf gcc-x86-64-linux-gnu (4:13.2.0-7ubuntu1 Ubuntu:24.04/noble [amd64])
Conf gcc (4:13.2.0-7ubuntu1 Ubuntu:24.04/noble [amd64])
Conf libdpkg-perl (1.22.6ubuntu6.6 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [all])
Conf bzip2 (1.0.8-5.1build0.1 Ubuntu:24.04/noble-updates [amd64])
Conf make (4.3-4.1build2 Ubuntu:24.04/noble [amd64])
Conf lto-disabled-list (47 Ubuntu:24.04/noble [all])
Conf dpkg-dev (1.22.6ubuntu6.6 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [all])
Conf libstdc++-13-dev (13.3.0-6ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf g++-13-x86-64-linux-gnu (13.3.0-6ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf g++-13 (13.3.0-6ubuntu2~24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf g++-x86-64-linux-gnu (4:13.2.0-7ubuntu1 Ubuntu:24.04/noble [amd64])
Conf g++ (4:13.2.0-7ubuntu1 Ubuntu:24.04/noble [amd64])
Conf build-essential (12.10ubuntu1 Ubuntu:24.04/noble [amd64])
Conf dkms (3.0.11-1ubuntu13 Ubuntu:24.04/noble [all])
Conf libgdk-pixbuf2.0-common (2.42.10+dfsg-3ubuntu3.3 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [all])
Conf libgdk-pixbuf-2.0-0 (2.42.10+dfsg-3ubuntu3.3 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf gtk-update-icon-cache (3.24.41-4ubuntu1.3 Ubuntu:24.04/noble-updates [amd64])
Conf hicolor-icon-theme (0.17-2 Ubuntu:24.04/noble [all])
Conf humanity-icon-theme (0.6.16 Ubuntu:24.04/noble [all])
Conf ubuntu-mono (24.04-0ubuntu1 Ubuntu:24.04/noble [all])
Conf adwaita-icon-theme (46.0-1 Ubuntu:24.04/noble [all])
Conf at-spi2-common (2.52.0-1build1 Ubuntu:24.04/noble [all])
Conf libxi6 (2:1.8.1-1build1 Ubuntu:24.04/noble [amd64])
Conf libatspi2.0-0t64 (2.52.0-1build1 Ubuntu:24.04/noble [amd64])
Conf x11-common (1:7.7+23ubuntu3 Ubuntu:24.04/noble [all])
Conf libxtst6 (2:1.2.3-1.1build1 Ubuntu:24.04/noble [amd64])
Conf libdconf1 (0.40.0-4ubuntu0.1 Ubuntu:24.04/noble-updates [amd64])
Conf dconf-service (0.40.0-4ubuntu0.1 Ubuntu:24.04/noble-updates [amd64])
Conf dconf-gsettings-backend (0.40.0-4ubuntu0.1 Ubuntu:24.04/noble-updates [amd64])
Conf session-migration (0.3.9build1 Ubuntu:24.04/noble [amd64])
Conf gsettings-desktop-schemas (46.1-0ubuntu1 Ubuntu:24.04/noble-updates [all])
Conf at-spi2-core (2.52.0-1build1 Ubuntu:24.04/noble [amd64])
Conf libfakeroot (1.33-1 Ubuntu:24.04/noble [amd64])
Conf fakeroot (1.33-1 Ubuntu:24.04/noble [amd64])
Conf fontconfig (2.15.0-1.1ubuntu2 Ubuntu:24.04/noble [amd64])
Conf libalgorithm-diff-perl (1.201-1 Ubuntu:24.04/noble [all])
Conf libalgorithm-diff-xs-perl (0.04-8build3 Ubuntu:24.04/noble [amd64])
Conf libalgorithm-merge-perl (0.08-5 Ubuntu:24.04/noble [all])
Conf libatk1.0-0t64 (2.52.0-1build1 Ubuntu:24.04/noble [amd64])
Conf libatk-bridge2.0-0t64 (2.52.0-1build1 Ubuntu:24.04/noble [amd64])
Conf libavahi-common-data (0.8-13ubuntu6.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libavahi-common3 (0.8-13ubuntu6.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libavahi-client3 (0.8-13ubuntu6.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libpixman-1-0 (0.42.2-1build1 Ubuntu:24.04/noble [amd64])
Conf libxcb-render0 (1.15-1ubuntu2 Ubuntu:24.04/noble [amd64])
Conf libxcb-shm0 (1.15-1ubuntu2 Ubuntu:24.04/noble [amd64])
Conf libxrender1 (1:0.9.10-1.1build1 Ubuntu:24.04/noble [amd64])
Conf libcairo2 (1.18.0-3build1 Ubuntu:24.04/noble [amd64])
Conf libcairo-gobject2 (1.18.0-3build1 Ubuntu:24.04/noble [amd64])
Conf liblcms2-2 (2.14-2ubuntu0.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libcolord2 (1.4.7-1build2 Ubuntu:24.04/noble [amd64])
Conf libcups2t64 (2.4.7-1.2ubuntu7.14 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libdatrie1 (0.2.13-3build1 Ubuntu:24.04/noble [amd64])
Conf libpciaccess0 (0.17-3ubuntu0.24.04.2 Ubuntu:24.04/noble-updates [amd64])
Conf libdrm-intel1 (2.4.125-1ubuntu0.1~24.04.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libllvm20 (1:20.1.2-0ubuntu1~24.04.3 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libx11-xcb1 (2:1.8.7-1build1 Ubuntu:24.04/noble [amd64])
Conf libxcb-dri3-0 (1.15-1ubuntu2 Ubuntu:24.04/noble [amd64])
Conf libxcb-present0 (1.15-1ubuntu2 Ubuntu:24.04/noble [amd64])
Conf libxcb-randr0 (1.15-1ubuntu2 Ubuntu:24.04/noble [amd64])
Conf libxcb-sync1 (1.15-1ubuntu2 Ubuntu:24.04/noble [amd64])
Conf libxcb-xfixes0 (1.15-1ubuntu2 Ubuntu:24.04/noble [amd64])
Conf libxshmfence1 (1.3-1build5 Ubuntu:24.04/noble [amd64])
Conf mesa-libgallium (25.2.8-0ubuntu0.24.04.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libgbm1 (25.2.8-0ubuntu0.24.04.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libwayland-client0 (1.22.0-2.1build1 Ubuntu:24.04/noble [amd64])
Conf libegl-mesa0 (25.2.8-0ubuntu0.24.04.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libepoxy0 (1.5.10-1build1 Ubuntu:24.04/noble [amd64])
Conf libfile-fcntllock-perl (0.22-4ubuntu5 Ubuntu:24.04/noble [amd64])
Conf libfontenc1 (1:1.1.8-1build1 Ubuntu:24.04/noble [amd64])
Conf libgdk-pixbuf2.0-bin (2.42.10+dfsg-3ubuntu3.3 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libvulkan1 (1.3.275.0-1build1 Ubuntu:24.04/noble [amd64])
Conf libgl1-mesa-dri (25.2.8-0ubuntu0.24.04.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libxcb-glx0 (1.15-1ubuntu2 Ubuntu:24.04/noble [amd64])
Conf libxxf86vm1 (1:1.1.4-1build4 Ubuntu:24.04/noble [amd64])
Conf libglx-mesa0 (25.2.8-0ubuntu0.24.04.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libgraphite2-3 (1.3.14-2ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libharfbuzz0b (8.3.0-2build2 Ubuntu:24.04/noble [amd64])
Conf libthai-data (0.1.29-2build1 Ubuntu:24.04/noble [all])
Conf libthai0 (0.1.29-2build1 Ubuntu:24.04/noble [amd64])
Conf libpango-1.0-0 (1.52.1+ds-1build1 Ubuntu:24.04/noble [amd64])
Conf libpangoft2-1.0-0 (1.52.1+ds-1build1 Ubuntu:24.04/noble [amd64])
Conf libpangocairo-1.0-0 (1.52.1+ds-1build1 Ubuntu:24.04/noble [amd64])
Conf libwayland-cursor0 (1.22.0-2.1build1 Ubuntu:24.04/noble [amd64])
Conf libwayland-egl1 (1.22.0-2.1build1 Ubuntu:24.04/noble [amd64])
Conf libxcomposite1 (1:0.4.5-1build3 Ubuntu:24.04/noble [amd64])
Conf libxfixes3 (1:6.0.0-2build1 Ubuntu:24.04/noble [amd64])
Conf libxcursor1 (1:1.2.1-1build1 Ubuntu:24.04/noble [amd64])
Conf libxdamage1 (1:1.1.6-1build1 Ubuntu:24.04/noble [amd64])
Conf libxinerama1 (2:1.1.4-3build1 Ubuntu:24.04/noble [amd64])
Conf libxrandr2 (2:1.5.2-2build1 Ubuntu:24.04/noble [amd64])
Conf libgtk-3-common (3.24.41-4ubuntu1.3 Ubuntu:24.04/noble-updates [all])
Conf libgtk-3-0t64 (3.24.41-4ubuntu1.3 Ubuntu:24.04/noble-updates [amd64])
Conf libgtk-3-bin (3.24.41-4ubuntu1.3 Ubuntu:24.04/noble-updates [amd64])
Conf libice6 (2:1.0.10-1build3 Ubuntu:24.04/noble [amd64])
Conf nvidia-firmware-595-595.71.05 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf nvidia-kernel-common-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libnvidia-cfg1-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libnvidia-common-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf ocl-icd-libopencl1 (2.3.2-1build1 Ubuntu:24.04/noble, Ubuntu:24.04/noble-updates [amd64])
Conf libnvidia-compute-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libnvidia-decode-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libwayland-server0 (1.22.0-2.1build1 Ubuntu:24.04/noble [amd64])
Conf libnvidia-egl-wayland1 (1:1.1.13-1ubuntu0.1 Ubuntu:24.04/noble-updates [amd64])
Conf libnvidia-encode-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libnvidia-extra-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libnvidia-fbc1-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libnvidia-gl-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf libpkgconf3 (1.8.1-2build1 Ubuntu:24.04/noble [amd64])
Conf librsvg2-2 (2.58.0+dfsg-1build1 Ubuntu:24.04/noble [amd64])
Conf librsvg2-common (2.58.0+dfsg-1build1 Ubuntu:24.04/noble [amd64])
Conf libsm6 (2:1.2.3-1build3 Ubuntu:24.04/noble [amd64])
Conf libvdpau1 (1.5-2build1 Ubuntu:24.04/noble [amd64])
Conf libxt6t64 (1:1.2.1-1.2build1 Ubuntu:24.04/noble [amd64])
Conf libxmu6 (2:1.1.3-3build2 Ubuntu:24.04/noble [amd64])
Conf libxaw7 (2:1.0.14-1build2 Ubuntu:24.04/noble [amd64])
Conf libxcvt0 (0.1.2-1build1 Ubuntu:24.04/noble [amd64])
Conf libxfont2 (1:2.0.6-1build1 Ubuntu:24.04/noble [amd64])
Conf libxkbfile1 (1:1.1.0-1build4 Ubuntu:24.04/noble [amd64])
Conf libxnvctrl0 (510.47.03-0ubuntu4.24.04.1 Ubuntu:24.04/noble-updates [amd64])
Conf mesa-vdpau-drivers (25.2.8-0ubuntu0.24.04.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf mesa-vulkan-drivers (25.2.8-0ubuntu0.24.04.2 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf nvidia-compute-utils-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf nvidia-kernel-source-595-open (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf nvidia-dkms-595-open (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf nvidia-utils-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf x11-xkb-utils (7.7+8build2 Ubuntu:24.04/noble [amd64])
Conf xserver-common (2:21.1.12-1ubuntu1.6 Ubuntu:24.04/noble-updates [all])
Conf libglvnd0 (1.7.0-1build1 Ubuntu:24.04/noble [amd64])
Conf libegl1 (1.7.0-1build1 Ubuntu:24.04/noble [amd64])
Conf libglx0 (1.7.0-1build1 Ubuntu:24.04/noble [amd64])
Conf libgl1 (1.7.0-1build1 Ubuntu:24.04/noble [amd64])
Conf xserver-xorg-core (2:21.1.12-1ubuntu1.6 Ubuntu:24.04/noble-updates [amd64])
Conf xserver-xorg-video-nvidia-595 (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf nvidia-driver-595-open (595.71.05-0ubuntu0.24.04.1 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf nvidia-prime (0.8.17.2 Ubuntu:24.04/noble [all])
Conf pkgconf-bin (1.8.1-2build1 Ubuntu:24.04/noble [amd64])
Conf pkgconf (1.8.1-2build1 Ubuntu:24.04/noble [amd64])
Conf pkg-config (1.8.1-2build1 Ubuntu:24.04/noble [amd64])
Conf pkexec (124-2ubuntu1.24.04.3 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Conf screen-resolution-extra (0.18.3ubuntu0.24.04.1 Ubuntu:24.04/noble-updates [all])
Conf nvidia-settings (510.47.03-0ubuntu4.24.04.1 Ubuntu:24.04/noble-updates [amd64])
Conf vdpau-driver-all (1.5-2build1 Ubuntu:24.04/noble [amd64])
Conf xcvt (0.1.2-1build1 Ubuntu:24.04/noble [amd64])
Conf xfonts-encodings (1:1.0.5-0ubuntu2 Ubuntu:24.04/noble [all])
Conf xfonts-utils (1:7.7+6build3 Ubuntu:24.04/noble [amd64])
Conf xfonts-base (1:1.0.5+nmu1 Ubuntu:24.04/noble [all])

[exit=0]
```

### apt simulation package-name guard

```console
$ awk '/^Inst / {print $2}' /tmp/m5b-apt-sim.txt | sort -u
adwaita-icon-theme
at-spi2-common
at-spi2-core
binutils
binutils-common
binutils-x86-64-linux-gnu
build-essential
bzip2
cpp
cpp-13
cpp-13-x86-64-linux-gnu
cpp-x86-64-linux-gnu
dconf-gsettings-backend
dconf-service
dkms
dpkg-dev
fakeroot
fontconfig
g++
g++-13
g++-13-x86-64-linux-gnu
g++-x86-64-linux-gnu
gcc
gcc-13
gcc-13-base
gcc-13-x86-64-linux-gnu
gcc-x86-64-linux-gnu
gsettings-desktop-schemas
gtk-update-icon-cache
hicolor-icon-theme
humanity-icon-theme
libalgorithm-diff-perl
libalgorithm-diff-xs-perl
libalgorithm-merge-perl
libasan8
libatk-bridge2.0-0t64
libatk1.0-0t64
libatomic1
libatspi2.0-0t64
libavahi-client3
libavahi-common-data
libavahi-common3
libbinutils
libcairo-gobject2
libcairo2
libcc1-0
libcolord2
libctf-nobfd0
libctf0
libcups2t64
libdatrie1
libdconf1
libdpkg-perl
libdrm-intel1
libegl-mesa0
libegl1
libepoxy0
libfakeroot
libfile-fcntllock-perl
libfontenc1
libgbm1
libgcc-13-dev
libgdk-pixbuf-2.0-0
libgdk-pixbuf2.0-bin
libgdk-pixbuf2.0-common
libgl1
libgl1-mesa-dri
libglvnd0
libglx-mesa0
libglx0
libgomp1
libgprofng0
libgraphite2-3
libgtk-3-0t64
libgtk-3-bin
libgtk-3-common
libharfbuzz0b
libhwasan0
libice6
libisl23
libitm1
liblcms2-2
libllvm20
liblsan0
libmpc3
libnvidia-cfg1-595
libnvidia-common-595
libnvidia-compute-595
libnvidia-decode-595
libnvidia-egl-wayland1
libnvidia-encode-595
libnvidia-extra-595
libnvidia-fbc1-595
libnvidia-gl-595
libpango-1.0-0
libpangocairo-1.0-0
libpangoft2-1.0-0
libpciaccess0
libpixman-1-0
libpkgconf3
libquadmath0
librsvg2-2
librsvg2-common
libsframe1
libsm6
libstdc++-13-dev
libthai-data
libthai0
libtsan2
libubsan1
libvdpau1
libvulkan1
libwayland-client0
libwayland-cursor0
libwayland-egl1
libwayland-server0
libx11-xcb1
libxaw7
libxcb-dri3-0
libxcb-glx0
libxcb-present0
libxcb-randr0
libxcb-render0
libxcb-shm0
libxcb-sync1
libxcb-xfixes0
libxcomposite1
libxcursor1
libxcvt0
libxdamage1
libxfixes3
libxfont2
libxi6
libxinerama1
libxkbfile1
libxmu6
libxnvctrl0
libxrandr2
libxrender1
libxshmfence1
libxt6t64
libxtst6
libxxf86vm1
lto-disabled-list
make
mesa-libgallium
mesa-vdpau-drivers
mesa-vulkan-drivers
nvidia-compute-utils-595
nvidia-dkms-595-open
nvidia-driver-595-open
nvidia-firmware-595-595.71.05
nvidia-kernel-common-595
nvidia-kernel-source-595-open
nvidia-prime
nvidia-settings
nvidia-utils-595
ocl-icd-libopencl1
pkexec
pkg-config
pkgconf
pkgconf-bin
screen-resolution-extra
session-migration
ubuntu-mono
vdpau-driver-all
x11-common
x11-xkb-utils
xcvt
xfonts-base
xfonts-encodings
xfonts-utils
xserver-common
xserver-xorg-core
xserver-xorg-video-nvidia-595
```

### apt simulation scope conclusion

PASS: simulation did not include forbidden CUDA Toolkit, NVIDIA Container Toolkit, backend, model, or API package names.

## Driver Installation

- Timestamp: 2026-07-03T07:30:45+00:00

- Manual install command: `sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y nvidia-driver-595-open nvidia-utils-595`

### apt install output

```console
$ sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y nvidia-driver-595-open nvidia-utils-595
Reading package lists...
Building dependency tree...
Reading state information...
The following packages were automatically installed and are no longer required:
  libfwupd2 libgusb2
Use 'sudo apt autoremove' to remove them.
The following additional packages will be installed:
  adwaita-icon-theme at-spi2-common at-spi2-core binutils binutils-common
  binutils-x86-64-linux-gnu build-essential bzip2 cpp cpp-13
  cpp-13-x86-64-linux-gnu cpp-x86-64-linux-gnu dconf-gsettings-backend
  dconf-service dkms dpkg-dev fakeroot fontconfig g++ g++-13
  g++-13-x86-64-linux-gnu g++-x86-64-linux-gnu gcc gcc-13 gcc-13-base
  gcc-13-x86-64-linux-gnu gcc-x86-64-linux-gnu gsettings-desktop-schemas
  gtk-update-icon-cache hicolor-icon-theme humanity-icon-theme
  libalgorithm-diff-perl libalgorithm-diff-xs-perl libalgorithm-merge-perl
  libasan8 libatk-bridge2.0-0t64 libatk1.0-0t64 libatomic1 libatspi2.0-0t64
  libavahi-client3 libavahi-common-data libavahi-common3 libbinutils
  libcairo-gobject2 libcairo2 libcc1-0 libcolord2 libctf-nobfd0 libctf0
  libcups2t64 libdatrie1 libdconf1 libdpkg-perl libdrm-intel1 libegl-mesa0
  libegl1 libepoxy0 libfakeroot libfile-fcntllock-perl libfontenc1 libgbm1
  libgcc-13-dev libgdk-pixbuf-2.0-0 libgdk-pixbuf2.0-bin
  libgdk-pixbuf2.0-common libgl1 libgl1-mesa-dri libglvnd0 libglx-mesa0
  libglx0 libgomp1 libgprofng0 libgraphite2-3 libgtk-3-0t64 libgtk-3-bin
  libgtk-3-common libharfbuzz0b libhwasan0 libice6 libisl23 libitm1 liblcms2-2
  libllvm20 liblsan0 libmpc3 libnvidia-cfg1-595 libnvidia-common-595
  libnvidia-compute-595 libnvidia-decode-595 libnvidia-egl-wayland1
  libnvidia-encode-595 libnvidia-extra-595 libnvidia-fbc1-595 libnvidia-gl-595
  libpango-1.0-0 libpangocairo-1.0-0 libpangoft2-1.0-0 libpciaccess0
  libpixman-1-0 libpkgconf3 libquadmath0 librsvg2-2 librsvg2-common libsframe1
  libsm6 libstdc++-13-dev libthai-data libthai0 libtsan2 libubsan1 libvdpau1
  libvulkan1 libwayland-client0 libwayland-cursor0 libwayland-egl1
  libwayland-server0 libx11-xcb1 libxaw7 libxcb-dri3-0 libxcb-glx0
  libxcb-present0 libxcb-randr0 libxcb-render0 libxcb-shm0 libxcb-sync1
  libxcb-xfixes0 libxcomposite1 libxcursor1 libxcvt0 libxdamage1 libxfixes3
  libxfont2 libxi6 libxinerama1 libxkbfile1 libxmu6 libxnvctrl0 libxrandr2
  libxrender1 libxshmfence1 libxt6t64 libxtst6 libxxf86vm1 lto-disabled-list
  make mesa-libgallium mesa-vdpau-drivers mesa-vulkan-drivers
  nvidia-compute-utils-595 nvidia-dkms-595-open nvidia-firmware-595-595.71.05
  nvidia-kernel-common-595 nvidia-kernel-source-595-open nvidia-prime
  nvidia-settings ocl-icd-libopencl1 pkexec pkg-config pkgconf pkgconf-bin
  screen-resolution-extra session-migration ubuntu-mono vdpau-driver-all
  x11-common x11-xkb-utils xcvt xfonts-base xfonts-encodings xfonts-utils
  xserver-common xserver-xorg-core xserver-xorg-video-nvidia-595
Suggested packages:
  binutils-doc gprofng-gui bzip2-doc cpp-doc gcc-13-locales cpp-13-doc menu
  debian-keyring g++-multilib g++-13-multilib gcc-13-doc gcc-multilib autoconf
  automake libtool flex bison gdb gcc-doc gcc-13-multilib gdb-x86-64-linux-gnu
  colord cups-common bzr gvfs liblcms2-utils librsvg2-bin libstdc++-13-doc
  make-doc nvidia-driver-595 libvdpau-va-gl1 xfs | xserver xfonts-100dpi
  | xfonts-75dpi xfonts-scalable
Recommended packages:
  libnvidia-compute-595:i386 libnvidia-decode-595:i386
  libnvidia-encode-595:i386 libnvidia-fbc1-595:i386 libnvidia-gl-595:i386
The following NEW packages will be installed:
  adwaita-icon-theme at-spi2-common at-spi2-core binutils binutils-common
  binutils-x86-64-linux-gnu build-essential bzip2 cpp cpp-13
  cpp-13-x86-64-linux-gnu cpp-x86-64-linux-gnu dconf-gsettings-backend
  dconf-service dkms dpkg-dev fakeroot fontconfig g++ g++-13
  g++-13-x86-64-linux-gnu g++-x86-64-linux-gnu gcc gcc-13 gcc-13-base
  gcc-13-x86-64-linux-gnu gcc-x86-64-linux-gnu gsettings-desktop-schemas
  gtk-update-icon-cache hicolor-icon-theme humanity-icon-theme
  libalgorithm-diff-perl libalgorithm-diff-xs-perl libalgorithm-merge-perl
  libasan8 libatk-bridge2.0-0t64 libatk1.0-0t64 libatomic1 libatspi2.0-0t64
  libavahi-client3 libavahi-common-data libavahi-common3 libbinutils
  libcairo-gobject2 libcairo2 libcc1-0 libcolord2 libctf-nobfd0 libctf0
  libcups2t64 libdatrie1 libdconf1 libdpkg-perl libdrm-intel1 libegl-mesa0
  libegl1 libepoxy0 libfakeroot libfile-fcntllock-perl libfontenc1 libgbm1
  libgcc-13-dev libgdk-pixbuf-2.0-0 libgdk-pixbuf2.0-bin
  libgdk-pixbuf2.0-common libgl1 libgl1-mesa-dri libglvnd0 libglx-mesa0
  libglx0 libgomp1 libgprofng0 libgraphite2-3 libgtk-3-0t64 libgtk-3-bin
  libgtk-3-common libharfbuzz0b libhwasan0 libice6 libisl23 libitm1 liblcms2-2
  libllvm20 liblsan0 libmpc3 libnvidia-cfg1-595 libnvidia-common-595
  libnvidia-compute-595 libnvidia-decode-595 libnvidia-egl-wayland1
  libnvidia-encode-595 libnvidia-extra-595 libnvidia-fbc1-595 libnvidia-gl-595
  libpango-1.0-0 libpangocairo-1.0-0 libpangoft2-1.0-0 libpciaccess0
  libpixman-1-0 libpkgconf3 libquadmath0 librsvg2-2 librsvg2-common libsframe1
  libsm6 libstdc++-13-dev libthai-data libthai0 libtsan2 libubsan1 libvdpau1
  libvulkan1 libwayland-client0 libwayland-cursor0 libwayland-egl1
  libwayland-server0 libx11-xcb1 libxaw7 libxcb-dri3-0 libxcb-glx0
  libxcb-present0 libxcb-randr0 libxcb-render0 libxcb-shm0 libxcb-sync1
  libxcb-xfixes0 libxcomposite1 libxcursor1 libxcvt0 libxdamage1 libxfixes3
  libxfont2 libxi6 libxinerama1 libxkbfile1 libxmu6 libxnvctrl0 libxrandr2
  libxrender1 libxshmfence1 libxt6t64 libxtst6 libxxf86vm1 lto-disabled-list
  make mesa-libgallium mesa-vdpau-drivers mesa-vulkan-drivers
  nvidia-compute-utils-595 nvidia-dkms-595-open nvidia-driver-595-open
  nvidia-firmware-595-595.71.05 nvidia-kernel-common-595
  nvidia-kernel-source-595-open nvidia-prime nvidia-settings nvidia-utils-595
  ocl-icd-libopencl1 pkexec pkg-config pkgconf pkgconf-bin
  screen-resolution-extra session-migration ubuntu-mono vdpau-driver-all
  x11-common x11-xkb-utils xcvt xfonts-base xfonts-encodings xfonts-utils
  xserver-common xserver-xorg-core xserver-xorg-video-nvidia-595
0 upgraded, 175 newly installed, 0 to remove and 1 not upgraded.
Need to get 464 MB of archives.
After this operation, 1578 MB of additional disk space will be used.
Get:1 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 gcc-13-base amd64 13.3.0-6ubuntu2~24.04.1 [51.6 kB]
Get:2 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libisl23 amd64 0.26-3build1.1 [680 kB]
Get:3 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libmpc3 amd64 1.3.1-1build1.1 [54.6 kB]
Get:4 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 cpp-13-x86-64-linux-gnu amd64 13.3.0-6ubuntu2~24.04.1 [10.7 MB]
Get:5 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 cpp-13 amd64 13.3.0-6ubuntu2~24.04.1 [1042 B]
Get:6 http://si.archive.ubuntu.com/ubuntu noble/main amd64 cpp-x86-64-linux-gnu amd64 4:13.2.0-7ubuntu1 [5326 B]
Get:7 http://si.archive.ubuntu.com/ubuntu noble/main amd64 cpp amd64 4:13.2.0-7ubuntu1 [22.4 kB]
Get:8 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libcc1-0 amd64 14.2.0-4ubuntu2~24.04.1 [48.0 kB]
Get:9 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 binutils-common amd64 2.42-4ubuntu2.10 [240 kB]
Get:10 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libsframe1 amd64 2.42-4ubuntu2.10 [15.7 kB]
Get:11 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libbinutils amd64 2.42-4ubuntu2.10 [577 kB]
Get:12 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libctf-nobfd0 amd64 2.42-4ubuntu2.10 [98.0 kB]
Get:13 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libctf0 amd64 2.42-4ubuntu2.10 [94.5 kB]
Get:14 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libgprofng0 amd64 2.42-4ubuntu2.10 [849 kB]
Get:15 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 binutils-x86-64-linux-gnu amd64 2.42-4ubuntu2.10 [2463 kB]
Get:16 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libgomp1 amd64 14.2.0-4ubuntu2~24.04.1 [148 kB]
Get:17 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libitm1 amd64 14.2.0-4ubuntu2~24.04.1 [29.7 kB]
Get:18 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libatomic1 amd64 14.2.0-4ubuntu2~24.04.1 [10.5 kB]
Get:19 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libasan8 amd64 14.2.0-4ubuntu2~24.04.1 [3027 kB]
Get:20 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 liblsan0 amd64 14.2.0-4ubuntu2~24.04.1 [1322 kB]
Get:21 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libtsan2 amd64 14.2.0-4ubuntu2~24.04.1 [2772 kB]
Get:22 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libubsan1 amd64 14.2.0-4ubuntu2~24.04.1 [1184 kB]
Get:23 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libhwasan0 amd64 14.2.0-4ubuntu2~24.04.1 [1641 kB]
Get:24 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libquadmath0 amd64 14.2.0-4ubuntu2~24.04.1 [153 kB]
Get:25 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libgcc-13-dev amd64 13.3.0-6ubuntu2~24.04.1 [2681 kB]
Get:26 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 gcc-13-x86-64-linux-gnu amd64 13.3.0-6ubuntu2~24.04.1 [21.1 MB]
Get:27 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 binutils amd64 2.42-4ubuntu2.10 [18.2 kB]
Get:28 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 gcc-13 amd64 13.3.0-6ubuntu2~24.04.1 [494 kB]
Get:29 http://si.archive.ubuntu.com/ubuntu noble/main amd64 gcc-x86-64-linux-gnu amd64 4:13.2.0-7ubuntu1 [1212 B]
Get:30 http://si.archive.ubuntu.com/ubuntu noble/main amd64 gcc amd64 4:13.2.0-7ubuntu1 [5018 B]
Get:31 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libdpkg-perl all 1.22.6ubuntu6.6 [268 kB]
Get:32 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 bzip2 amd64 1.0.8-5.1build0.1 [34.5 kB]
Get:33 http://si.archive.ubuntu.com/ubuntu noble/main amd64 make amd64 4.3-4.1build2 [180 kB]
Get:34 http://si.archive.ubuntu.com/ubuntu noble/main amd64 lto-disabled-list all 47 [12.4 kB]
Get:35 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 dpkg-dev all 1.22.6ubuntu6.6 [1074 kB]
Get:36 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libstdc++-13-dev amd64 13.3.0-6ubuntu2~24.04.1 [2420 kB]
Get:37 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 g++-13-x86-64-linux-gnu amd64 13.3.0-6ubuntu2~24.04.1 [12.2 MB]
Get:38 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 g++-13 amd64 13.3.0-6ubuntu2~24.04.1 [16.0 kB]
Get:39 http://si.archive.ubuntu.com/ubuntu noble/main amd64 g++-x86-64-linux-gnu amd64 4:13.2.0-7ubuntu1 [964 B]
Get:40 http://si.archive.ubuntu.com/ubuntu noble/main amd64 g++ amd64 4:13.2.0-7ubuntu1 [1100 B]
Get:41 http://si.archive.ubuntu.com/ubuntu noble/main amd64 build-essential amd64 12.10ubuntu1 [4928 B]
Get:42 http://si.archive.ubuntu.com/ubuntu noble/main amd64 dkms all 3.0.11-1ubuntu13 [51.5 kB]
Get:43 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libgdk-pixbuf2.0-common all 2.42.10+dfsg-3ubuntu3.3 [8302 B]
Get:44 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libgdk-pixbuf-2.0-0 amd64 2.42.10+dfsg-3ubuntu3.3 [147 kB]
Get:45 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 gtk-update-icon-cache amd64 3.24.41-4ubuntu1.3 [51.9 kB]
Get:46 http://si.archive.ubuntu.com/ubuntu noble/main amd64 hicolor-icon-theme all 0.17-2 [9976 B]
Get:47 http://si.archive.ubuntu.com/ubuntu noble/main amd64 humanity-icon-theme all 0.6.16 [1282 kB]
Get:48 http://si.archive.ubuntu.com/ubuntu noble/main amd64 ubuntu-mono all 24.04-0ubuntu1 [151 kB]
Get:49 http://si.archive.ubuntu.com/ubuntu noble/main amd64 adwaita-icon-theme all 46.0-1 [723 kB]
Get:50 http://si.archive.ubuntu.com/ubuntu noble/main amd64 at-spi2-common all 2.52.0-1build1 [8674 B]
Get:51 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxi6 amd64 2:1.8.1-1build1 [32.4 kB]
Get:52 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libatspi2.0-0t64 amd64 2.52.0-1build1 [80.5 kB]
Get:53 http://si.archive.ubuntu.com/ubuntu noble/main amd64 x11-common all 1:7.7+23ubuntu3 [21.7 kB]
Get:54 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxtst6 amd64 2:1.2.3-1.1build1 [12.6 kB]
Get:55 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libdconf1 amd64 0.40.0-4ubuntu0.1 [39.6 kB]
Get:56 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 dconf-service amd64 0.40.0-4ubuntu0.1 [27.6 kB]
Get:57 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 dconf-gsettings-backend amd64 0.40.0-4ubuntu0.1 [22.1 kB]
Get:58 http://si.archive.ubuntu.com/ubuntu noble/main amd64 session-migration amd64 0.3.9build1 [9034 B]
Get:59 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 gsettings-desktop-schemas all 46.1-0ubuntu1 [35.6 kB]
Get:60 http://si.archive.ubuntu.com/ubuntu noble/main amd64 at-spi2-core amd64 2.52.0-1build1 [56.6 kB]
Get:61 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libfakeroot amd64 1.33-1 [32.4 kB]
Get:62 http://si.archive.ubuntu.com/ubuntu noble/main amd64 fakeroot amd64 1.33-1 [67.2 kB]
Get:63 http://si.archive.ubuntu.com/ubuntu noble/main amd64 fontconfig amd64 2.15.0-1.1ubuntu2 [180 kB]
Get:64 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libalgorithm-diff-perl all 1.201-1 [41.8 kB]
Get:65 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libalgorithm-diff-xs-perl amd64 0.04-8build3 [11.2 kB]
Get:66 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libalgorithm-merge-perl all 0.08-5 [11.4 kB]
Get:67 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libatk1.0-0t64 amd64 2.52.0-1build1 [55.3 kB]
Get:68 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libatk-bridge2.0-0t64 amd64 2.52.0-1build1 [66.0 kB]
Get:69 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libavahi-common-data amd64 0.8-13ubuntu6.2 [30.1 kB]
Get:70 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libavahi-common3 amd64 0.8-13ubuntu6.2 [23.4 kB]
Get:71 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libavahi-client3 amd64 0.8-13ubuntu6.2 [26.8 kB]
Get:72 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libpixman-1-0 amd64 0.42.2-1build1 [279 kB]
Get:73 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxcb-render0 amd64 1.15-1ubuntu2 [16.2 kB]
Get:74 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxcb-shm0 amd64 1.15-1ubuntu2 [5756 B]
Get:75 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxrender1 amd64 1:0.9.10-1.1build1 [19.0 kB]
Get:76 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libcairo2 amd64 1.18.0-3build1 [566 kB]
Get:77 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libcairo-gobject2 amd64 1.18.0-3build1 [127 kB]
Get:78 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 liblcms2-2 amd64 2.14-2ubuntu0.1 [161 kB]
Get:79 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libcolord2 amd64 1.4.7-1build2 [149 kB]
Get:80 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libcups2t64 amd64 2.4.7-1.2ubuntu7.14 [274 kB]
Get:81 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libdatrie1 amd64 0.2.13-3build1 [19.0 kB]
Get:82 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libpciaccess0 amd64 0.17-3ubuntu0.24.04.2 [18.9 kB]
Get:83 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libdrm-intel1 amd64 2.4.125-1ubuntu0.1~24.04.2 [63.9 kB]
Get:84 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libllvm20 amd64 1:20.1.2-0ubuntu1~24.04.3 [30.6 MB]
Get:85 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libx11-xcb1 amd64 2:1.8.7-1build1 [7800 B]
Get:86 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxcb-dri3-0 amd64 1.15-1ubuntu2 [7142 B]
Get:87 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxcb-present0 amd64 1.15-1ubuntu2 [5676 B]
Get:88 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxcb-randr0 amd64 1.15-1ubuntu2 [17.9 kB]
Get:89 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxcb-sync1 amd64 1.15-1ubuntu2 [9312 B]
Get:90 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxcb-xfixes0 amd64 1.15-1ubuntu2 [10.2 kB]
Get:91 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxshmfence1 amd64 1.3-1build5 [4764 B]
Get:92 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 mesa-libgallium amd64 25.2.8-0ubuntu0.24.04.2 [10.8 MB]
Get:93 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libgbm1 amd64 25.2.8-0ubuntu0.24.04.2 [34.2 kB]
Get:94 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libwayland-client0 amd64 1.22.0-2.1build1 [26.4 kB]
Get:95 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libegl-mesa0 amd64 25.2.8-0ubuntu0.24.04.2 [117 kB]
Get:96 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libepoxy0 amd64 1.5.10-1build1 [220 kB]
Get:97 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libfile-fcntllock-perl amd64 0.22-4ubuntu5 [30.7 kB]
Get:98 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libfontenc1 amd64 1:1.1.8-1build1 [14.0 kB]
Get:99 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libgdk-pixbuf2.0-bin amd64 2.42.10+dfsg-3ubuntu3.3 [13.9 kB]
Get:100 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libvulkan1 amd64 1.3.275.0-1build1 [142 kB]
Get:101 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libgl1-mesa-dri amd64 25.2.8-0ubuntu0.24.04.2 [37.9 kB]
Get:102 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxcb-glx0 amd64 1.15-1ubuntu2 [24.8 kB]
Get:103 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxxf86vm1 amd64 1:1.1.4-1build4 [9282 B]
Get:104 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libglx-mesa0 amd64 25.2.8-0ubuntu0.24.04.2 [110 kB]
Get:105 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libgraphite2-3 amd64 1.3.14-2ubuntu0.24.04.1 [73.4 kB]
Get:106 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libharfbuzz0b amd64 8.3.0-2build2 [469 kB]
Get:107 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libthai-data all 0.1.29-2build1 [158 kB]
Get:108 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libthai0 amd64 0.1.29-2build1 [18.9 kB]
Get:109 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libpango-1.0-0 amd64 1.52.1+ds-1build1 [231 kB]
Get:110 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libpangoft2-1.0-0 amd64 1.52.1+ds-1build1 [42.5 kB]
Get:111 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libpangocairo-1.0-0 amd64 1.52.1+ds-1build1 [28.8 kB]
Get:112 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libwayland-cursor0 amd64 1.22.0-2.1build1 [10.4 kB]
Get:113 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libwayland-egl1 amd64 1.22.0-2.1build1 [5628 B]
Get:114 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxcomposite1 amd64 1:0.4.5-1build3 [6320 B]
Get:115 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxfixes3 amd64 1:6.0.0-2build1 [10.8 kB]
Get:116 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxcursor1 amd64 1:1.2.1-1build1 [20.7 kB]
Get:117 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxdamage1 amd64 1:1.1.6-1build1 [6150 B]
Get:118 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxinerama1 amd64 2:1.1.4-3build1 [6396 B]
Get:119 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxrandr2 amd64 2:1.5.2-2build1 [19.7 kB]
Get:120 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libgtk-3-common all 3.24.41-4ubuntu1.3 [1426 kB]
Get:121 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libgtk-3-0t64 amd64 3.24.41-4ubuntu1.3 [2913 kB]
Get:122 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libgtk-3-bin amd64 3.24.41-4ubuntu1.3 [73.9 kB]
Get:123 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libice6 amd64 2:1.0.10-1build3 [41.4 kB]
Get:124 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 nvidia-firmware-595-595.71.05 amd64 595.71.05-0ubuntu0.24.04.1 [74.9 MB]
Get:125 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 nvidia-kernel-common-595 amd64 595.71.05-0ubuntu0.24.04.1 [824 kB]
Get:126 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 libnvidia-cfg1-595 amd64 595.71.05-0ubuntu0.24.04.1 [158 kB]
Get:127 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 libnvidia-common-595 amd64 595.71.05-0ubuntu0.24.04.1 [18.2 kB]
Get:128 http://si.archive.ubuntu.com/ubuntu noble/universe amd64 ocl-icd-libopencl1 amd64 2.3.2-1build1 [38.5 kB]
Get:129 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 libnvidia-compute-595 amd64 595.71.05-0ubuntu0.24.04.1 [86.0 MB]
Get:130 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 libnvidia-decode-595 amd64 595.71.05-0ubuntu0.24.04.1 [3070 kB]
Get:131 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libwayland-server0 amd64 1.22.0-2.1build1 [33.9 kB]
Get:132 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libnvidia-egl-wayland1 amd64 1:1.1.13-1ubuntu0.1 [30.8 kB]
Get:133 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 libnvidia-encode-595 amd64 595.71.05-0ubuntu0.24.04.1 [119 kB]
Get:134 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 libnvidia-extra-595 amd64 595.71.05-0ubuntu0.24.04.1 [77.4 kB]
Get:135 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 libnvidia-fbc1-595 amd64 595.71.05-0ubuntu0.24.04.1 [94.1 kB]
Get:136 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 libnvidia-gl-595 amd64 595.71.05-0ubuntu0.24.04.1 [139 MB]
Get:137 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libpkgconf3 amd64 1.8.1-2build1 [30.7 kB]
Get:138 http://si.archive.ubuntu.com/ubuntu noble/main amd64 librsvg2-2 amd64 2.58.0+dfsg-1build1 [2135 kB]
Get:139 http://si.archive.ubuntu.com/ubuntu noble/main amd64 librsvg2-common amd64 2.58.0+dfsg-1build1 [11.8 kB]
Get:140 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libsm6 amd64 2:1.2.3-1build3 [15.7 kB]
Get:141 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libvdpau1 amd64 1.5-2build1 [27.8 kB]
Get:142 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxt6t64 amd64 1:1.2.1-1.2build1 [171 kB]
Get:143 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxmu6 amd64 2:1.1.3-3build2 [47.6 kB]
Get:144 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxaw7 amd64 2:1.0.14-1build2 [187 kB]
Get:145 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxcvt0 amd64 0.1.2-1build1 [5684 B]
Get:146 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxfont2 amd64 1:2.0.6-1build1 [93.0 kB]
Get:147 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libxkbfile1 amd64 1:1.1.0-1build4 [70.0 kB]
Get:148 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 libxnvctrl0 amd64 510.47.03-0ubuntu4.24.04.1 [12.7 kB]
Get:149 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 mesa-vdpau-drivers amd64 25.2.8-0ubuntu0.24.04.2 [23.2 kB]
Get:150 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 mesa-vulkan-drivers amd64 25.2.8-0ubuntu0.24.04.2 [17.5 MB]
Get:151 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 nvidia-compute-utils-595 amd64 595.71.05-0ubuntu0.24.04.1 [135 kB]
Get:152 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 nvidia-kernel-source-595-open amd64 595.71.05-0ubuntu0.24.04.1 [8353 kB]
Get:153 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 nvidia-dkms-595-open amd64 595.71.05-0ubuntu0.24.04.1 [16.2 kB]
Get:154 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 nvidia-utils-595 amd64 595.71.05-0ubuntu0.24.04.1 [609 kB]
Get:155 http://si.archive.ubuntu.com/ubuntu noble/main amd64 x11-xkb-utils amd64 7.7+8build2 [170 kB]
Get:156 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 xserver-common all 2:21.1.12-1ubuntu1.6 [34.7 kB]
Get:157 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libglvnd0 amd64 1.7.0-1build1 [69.6 kB]
Get:158 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libegl1 amd64 1.7.0-1build1 [28.7 kB]
Get:159 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libglx0 amd64 1.7.0-1build1 [38.6 kB]
Get:160 http://si.archive.ubuntu.com/ubuntu noble/main amd64 libgl1 amd64 1.7.0-1build1 [102 kB]
Get:161 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 xserver-xorg-core amd64 2:21.1.12-1ubuntu1.6 [1476 kB]
Get:162 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 xserver-xorg-video-nvidia-595 amd64 595.71.05-0ubuntu0.24.04.1 [1207 kB]
Get:163 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 nvidia-driver-595-open amd64 595.71.05-0ubuntu0.24.04.1 [13.9 kB]
Get:164 http://si.archive.ubuntu.com/ubuntu noble/main amd64 nvidia-prime all 0.8.17.2 [10.4 kB]
Get:165 http://si.archive.ubuntu.com/ubuntu noble/main amd64 pkgconf-bin amd64 1.8.1-2build1 [20.7 kB]
Get:166 http://si.archive.ubuntu.com/ubuntu noble/main amd64 pkgconf amd64 1.8.1-2build1 [16.8 kB]
Get:167 http://si.archive.ubuntu.com/ubuntu noble/main amd64 pkg-config amd64 1.8.1-2build1 [7264 B]
Get:168 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 pkexec amd64 124-2ubuntu1.24.04.3 [15.9 kB]
Get:169 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 screen-resolution-extra all 0.18.3ubuntu0.24.04.1 [4192 B]
Get:170 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 nvidia-settings amd64 510.47.03-0ubuntu4.24.04.1 [898 kB]
Get:171 http://si.archive.ubuntu.com/ubuntu noble/main amd64 vdpau-driver-all amd64 1.5-2build1 [4414 B]
Get:172 http://si.archive.ubuntu.com/ubuntu noble/main amd64 xcvt amd64 0.1.2-1build1 [6982 B]
Get:173 http://si.archive.ubuntu.com/ubuntu noble/main amd64 xfonts-encodings all 1:1.0.5-0ubuntu2 [578 kB]
Get:174 http://si.archive.ubuntu.com/ubuntu noble/main amd64 xfonts-utils amd64 1:7.7+6build3 [94.4 kB]
Get:175 http://si.archive.ubuntu.com/ubuntu noble/main amd64 xfonts-base all 1:1.0.5+nmu1 [5941 kB]
Fetched 464 MB in 6s (75.7 MB/s)
Selecting previously unselected package gcc-13-base:amd64.
(Reading database ... (Reading database ... 5%(Reading database ... 10%(Reading database ... 15%(Reading database ... 20%(Reading database ... 25%(Reading database ... 30%(Reading database ... 35%(Reading database ... 40%(Reading database ... 45%(Reading database ... 50%(Reading database ... 55%(Reading database ... 60%(Reading database ... 65%(Reading database ... 70%(Reading database ... 75%(Reading database ... 80%(Reading database ... 85%(Reading database ... 90%(Reading database ... 95%(Reading database ... 100%(Reading database ... 127022 files and directories currently installed.)
Preparing to unpack .../000-gcc-13-base_13.3.0-6ubuntu2~24.04.1_amd64.deb ...
Unpacking gcc-13-base:amd64 (13.3.0-6ubuntu2~24.04.1) ...
Selecting previously unselected package libisl23:amd64.
Preparing to unpack .../001-libisl23_0.26-3build1.1_amd64.deb ...
Unpacking libisl23:amd64 (0.26-3build1.1) ...
Selecting previously unselected package libmpc3:amd64.
Preparing to unpack .../002-libmpc3_1.3.1-1build1.1_amd64.deb ...
Unpacking libmpc3:amd64 (1.3.1-1build1.1) ...
Selecting previously unselected package cpp-13-x86-64-linux-gnu.
Preparing to unpack .../003-cpp-13-x86-64-linux-gnu_13.3.0-6ubuntu2~24.04.1_amd64.deb ...
Unpacking cpp-13-x86-64-linux-gnu (13.3.0-6ubuntu2~24.04.1) ...
Selecting previously unselected package cpp-13.
Preparing to unpack .../004-cpp-13_13.3.0-6ubuntu2~24.04.1_amd64.deb ...
Unpacking cpp-13 (13.3.0-6ubuntu2~24.04.1) ...
Selecting previously unselected package cpp-x86-64-linux-gnu.
Preparing to unpack .../005-cpp-x86-64-linux-gnu_4%3a13.2.0-7ubuntu1_amd64.deb ...
Unpacking cpp-x86-64-linux-gnu (4:13.2.0-7ubuntu1) ...
Selecting previously unselected package cpp.
Preparing to unpack .../006-cpp_4%3a13.2.0-7ubuntu1_amd64.deb ...
Unpacking cpp (4:13.2.0-7ubuntu1) ...
Selecting previously unselected package libcc1-0:amd64.
Preparing to unpack .../007-libcc1-0_14.2.0-4ubuntu2~24.04.1_amd64.deb ...
Unpacking libcc1-0:amd64 (14.2.0-4ubuntu2~24.04.1) ...
Selecting previously unselected package binutils-common:amd64.
Preparing to unpack .../008-binutils-common_2.42-4ubuntu2.10_amd64.deb ...
Unpacking binutils-common:amd64 (2.42-4ubuntu2.10) ...
Selecting previously unselected package libsframe1:amd64.
Preparing to unpack .../009-libsframe1_2.42-4ubuntu2.10_amd64.deb ...
Unpacking libsframe1:amd64 (2.42-4ubuntu2.10) ...
Selecting previously unselected package libbinutils:amd64.
Preparing to unpack .../010-libbinutils_2.42-4ubuntu2.10_amd64.deb ...
Unpacking libbinutils:amd64 (2.42-4ubuntu2.10) ...
Selecting previously unselected package libctf-nobfd0:amd64.
Preparing to unpack .../011-libctf-nobfd0_2.42-4ubuntu2.10_amd64.deb ...
Unpacking libctf-nobfd0:amd64 (2.42-4ubuntu2.10) ...
Selecting previously unselected package libctf0:amd64.
Preparing to unpack .../012-libctf0_2.42-4ubuntu2.10_amd64.deb ...
Unpacking libctf0:amd64 (2.42-4ubuntu2.10) ...
Selecting previously unselected package libgprofng0:amd64.
Preparing to unpack .../013-libgprofng0_2.42-4ubuntu2.10_amd64.deb ...
Unpacking libgprofng0:amd64 (2.42-4ubuntu2.10) ...
Selecting previously unselected package binutils-x86-64-linux-gnu.
Preparing to unpack .../014-binutils-x86-64-linux-gnu_2.42-4ubuntu2.10_amd64.deb ...
Unpacking binutils-x86-64-linux-gnu (2.42-4ubuntu2.10) ...
Selecting previously unselected package libgomp1:amd64.
Preparing to unpack .../015-libgomp1_14.2.0-4ubuntu2~24.04.1_amd64.deb ...
Unpacking libgomp1:amd64 (14.2.0-4ubuntu2~24.04.1) ...
Selecting previously unselected package libitm1:amd64.
Preparing to unpack .../016-libitm1_14.2.0-4ubuntu2~24.04.1_amd64.deb ...
Unpacking libitm1:amd64 (14.2.0-4ubuntu2~24.04.1) ...
Selecting previously unselected package libatomic1:amd64.
Preparing to unpack .../017-libatomic1_14.2.0-4ubuntu2~24.04.1_amd64.deb ...
Unpacking libatomic1:amd64 (14.2.0-4ubuntu2~24.04.1) ...
Selecting previously unselected package libasan8:amd64.
Preparing to unpack .../018-libasan8_14.2.0-4ubuntu2~24.04.1_amd64.deb ...
Unpacking libasan8:amd64 (14.2.0-4ubuntu2~24.04.1) ...
Selecting previously unselected package liblsan0:amd64.
Preparing to unpack .../019-liblsan0_14.2.0-4ubuntu2~24.04.1_amd64.deb ...
Unpacking liblsan0:amd64 (14.2.0-4ubuntu2~24.04.1) ...
Selecting previously unselected package libtsan2:amd64.
Preparing to unpack .../020-libtsan2_14.2.0-4ubuntu2~24.04.1_amd64.deb ...
Unpacking libtsan2:amd64 (14.2.0-4ubuntu2~24.04.1) ...
Selecting previously unselected package libubsan1:amd64.
Preparing to unpack .../021-libubsan1_14.2.0-4ubuntu2~24.04.1_amd64.deb ...
Unpacking libubsan1:amd64 (14.2.0-4ubuntu2~24.04.1) ...
Selecting previously unselected package libhwasan0:amd64.
Preparing to unpack .../022-libhwasan0_14.2.0-4ubuntu2~24.04.1_amd64.deb ...
Unpacking libhwasan0:amd64 (14.2.0-4ubuntu2~24.04.1) ...
Selecting previously unselected package libquadmath0:amd64.
Preparing to unpack .../023-libquadmath0_14.2.0-4ubuntu2~24.04.1_amd64.deb ...
Unpacking libquadmath0:amd64 (14.2.0-4ubuntu2~24.04.1) ...
Selecting previously unselected package libgcc-13-dev:amd64.
Preparing to unpack .../024-libgcc-13-dev_13.3.0-6ubuntu2~24.04.1_amd64.deb ...
Unpacking libgcc-13-dev:amd64 (13.3.0-6ubuntu2~24.04.1) ...
Selecting previously unselected package gcc-13-x86-64-linux-gnu.
Preparing to unpack .../025-gcc-13-x86-64-linux-gnu_13.3.0-6ubuntu2~24.04.1_amd64.deb ...
Unpacking gcc-13-x86-64-linux-gnu (13.3.0-6ubuntu2~24.04.1) ...
Selecting previously unselected package binutils.
Preparing to unpack .../026-binutils_2.42-4ubuntu2.10_amd64.deb ...
Unpacking binutils (2.42-4ubuntu2.10) ...
Selecting previously unselected package gcc-13.
Preparing to unpack .../027-gcc-13_13.3.0-6ubuntu2~24.04.1_amd64.deb ...
Unpacking gcc-13 (13.3.0-6ubuntu2~24.04.1) ...
Selecting previously unselected package gcc-x86-64-linux-gnu.
Preparing to unpack .../028-gcc-x86-64-linux-gnu_4%3a13.2.0-7ubuntu1_amd64.deb ...
Unpacking gcc-x86-64-linux-gnu (4:13.2.0-7ubuntu1) ...
Selecting previously unselected package gcc.
Preparing to unpack .../029-gcc_4%3a13.2.0-7ubuntu1_amd64.deb ...
Unpacking gcc (4:13.2.0-7ubuntu1) ...
Selecting previously unselected package libdpkg-perl.
Preparing to unpack .../030-libdpkg-perl_1.22.6ubuntu6.6_all.deb ...
Unpacking libdpkg-perl (1.22.6ubuntu6.6) ...
Selecting previously unselected package bzip2.
Preparing to unpack .../031-bzip2_1.0.8-5.1build0.1_amd64.deb ...
Unpacking bzip2 (1.0.8-5.1build0.1) ...
Selecting previously unselected package make.
Preparing to unpack .../032-make_4.3-4.1build2_amd64.deb ...
Unpacking make (4.3-4.1build2) ...
Selecting previously unselected package lto-disabled-list.
Preparing to unpack .../033-lto-disabled-list_47_all.deb ...
Unpacking lto-disabled-list (47) ...
Selecting previously unselected package dpkg-dev.
Preparing to unpack .../034-dpkg-dev_1.22.6ubuntu6.6_all.deb ...
Unpacking dpkg-dev (1.22.6ubuntu6.6) ...
Selecting previously unselected package libstdc++-13-dev:amd64.
Preparing to unpack .../035-libstdc++-13-dev_13.3.0-6ubuntu2~24.04.1_amd64.deb ...
Unpacking libstdc++-13-dev:amd64 (13.3.0-6ubuntu2~24.04.1) ...
Selecting previously unselected package g++-13-x86-64-linux-gnu.
Preparing to unpack .../036-g++-13-x86-64-linux-gnu_13.3.0-6ubuntu2~24.04.1_amd64.deb ...
Unpacking g++-13-x86-64-linux-gnu (13.3.0-6ubuntu2~24.04.1) ...
Selecting previously unselected package g++-13.
Preparing to unpack .../037-g++-13_13.3.0-6ubuntu2~24.04.1_amd64.deb ...
Unpacking g++-13 (13.3.0-6ubuntu2~24.04.1) ...
Selecting previously unselected package g++-x86-64-linux-gnu.
Preparing to unpack .../038-g++-x86-64-linux-gnu_4%3a13.2.0-7ubuntu1_amd64.deb ...
Unpacking g++-x86-64-linux-gnu (4:13.2.0-7ubuntu1) ...
Selecting previously unselected package g++.
Preparing to unpack .../039-g++_4%3a13.2.0-7ubuntu1_amd64.deb ...
Unpacking g++ (4:13.2.0-7ubuntu1) ...
Selecting previously unselected package build-essential.
Preparing to unpack .../040-build-essential_12.10ubuntu1_amd64.deb ...
Unpacking build-essential (12.10ubuntu1) ...
Selecting previously unselected package dkms.
Preparing to unpack .../041-dkms_3.0.11-1ubuntu13_all.deb ...
Unpacking dkms (3.0.11-1ubuntu13) ...
Selecting previously unselected package libgdk-pixbuf2.0-common.
Preparing to unpack .../042-libgdk-pixbuf2.0-common_2.42.10+dfsg-3ubuntu3.3_all.deb ...
Unpacking libgdk-pixbuf2.0-common (2.42.10+dfsg-3ubuntu3.3) ...
Selecting previously unselected package libgdk-pixbuf-2.0-0:amd64.
Preparing to unpack .../043-libgdk-pixbuf-2.0-0_2.42.10+dfsg-3ubuntu3.3_amd64.deb ...
Unpacking libgdk-pixbuf-2.0-0:amd64 (2.42.10+dfsg-3ubuntu3.3) ...
Selecting previously unselected package gtk-update-icon-cache.
Preparing to unpack .../044-gtk-update-icon-cache_3.24.41-4ubuntu1.3_amd64.deb ...
Unpacking gtk-update-icon-cache (3.24.41-4ubuntu1.3) ...
Selecting previously unselected package hicolor-icon-theme.
Preparing to unpack .../045-hicolor-icon-theme_0.17-2_all.deb ...
Unpacking hicolor-icon-theme (0.17-2) ...
Selecting previously unselected package humanity-icon-theme.
Preparing to unpack .../046-humanity-icon-theme_0.6.16_all.deb ...
Unpacking humanity-icon-theme (0.6.16) ...
Selecting previously unselected package ubuntu-mono.
Preparing to unpack .../047-ubuntu-mono_24.04-0ubuntu1_all.deb ...
Unpacking ubuntu-mono (24.04-0ubuntu1) ...
Selecting previously unselected package adwaita-icon-theme.
Preparing to unpack .../048-adwaita-icon-theme_46.0-1_all.deb ...
Unpacking adwaita-icon-theme (46.0-1) ...
Selecting previously unselected package at-spi2-common.
Preparing to unpack .../049-at-spi2-common_2.52.0-1build1_all.deb ...
Unpacking at-spi2-common (2.52.0-1build1) ...
Selecting previously unselected package libxi6:amd64.
Preparing to unpack .../050-libxi6_2%3a1.8.1-1build1_amd64.deb ...
Unpacking libxi6:amd64 (2:1.8.1-1build1) ...
Selecting previously unselected package libatspi2.0-0t64:amd64.
Preparing to unpack .../051-libatspi2.0-0t64_2.52.0-1build1_amd64.deb ...
Unpacking libatspi2.0-0t64:amd64 (2.52.0-1build1) ...
Selecting previously unselected package x11-common.
Preparing to unpack .../052-x11-common_1%3a7.7+23ubuntu3_all.deb ...
Unpacking x11-common (1:7.7+23ubuntu3) ...
Selecting previously unselected package libxtst6:amd64.
Preparing to unpack .../053-libxtst6_2%3a1.2.3-1.1build1_amd64.deb ...
Unpacking libxtst6:amd64 (2:1.2.3-1.1build1) ...
Selecting previously unselected package libdconf1:amd64.
Preparing to unpack .../054-libdconf1_0.40.0-4ubuntu0.1_amd64.deb ...
Unpacking libdconf1:amd64 (0.40.0-4ubuntu0.1) ...
Selecting previously unselected package dconf-service.
Preparing to unpack .../055-dconf-service_0.40.0-4ubuntu0.1_amd64.deb ...
Unpacking dconf-service (0.40.0-4ubuntu0.1) ...
Selecting previously unselected package dconf-gsettings-backend:amd64.
Preparing to unpack .../056-dconf-gsettings-backend_0.40.0-4ubuntu0.1_amd64.deb ...
Unpacking dconf-gsettings-backend:amd64 (0.40.0-4ubuntu0.1) ...
Selecting previously unselected package session-migration.
Preparing to unpack .../057-session-migration_0.3.9build1_amd64.deb ...
Unpacking session-migration (0.3.9build1) ...
Selecting previously unselected package gsettings-desktop-schemas.
Preparing to unpack .../058-gsettings-desktop-schemas_46.1-0ubuntu1_all.deb ...
Unpacking gsettings-desktop-schemas (46.1-0ubuntu1) ...
Selecting previously unselected package at-spi2-core.
Preparing to unpack .../059-at-spi2-core_2.52.0-1build1_amd64.deb ...
Unpacking at-spi2-core (2.52.0-1build1) ...
Selecting previously unselected package libfakeroot:amd64.
Preparing to unpack .../060-libfakeroot_1.33-1_amd64.deb ...
Unpacking libfakeroot:amd64 (1.33-1) ...
Selecting previously unselected package fakeroot.
Preparing to unpack .../061-fakeroot_1.33-1_amd64.deb ...
Unpacking fakeroot (1.33-1) ...
Selecting previously unselected package fontconfig.
Preparing to unpack .../062-fontconfig_2.15.0-1.1ubuntu2_amd64.deb ...
Unpacking fontconfig (2.15.0-1.1ubuntu2) ...
Selecting previously unselected package libalgorithm-diff-perl.
Preparing to unpack .../063-libalgorithm-diff-perl_1.201-1_all.deb ...
Unpacking libalgorithm-diff-perl (1.201-1) ...
Selecting previously unselected package libalgorithm-diff-xs-perl:amd64.
Preparing to unpack .../064-libalgorithm-diff-xs-perl_0.04-8build3_amd64.deb ...
Unpacking libalgorithm-diff-xs-perl:amd64 (0.04-8build3) ...
Selecting previously unselected package libalgorithm-merge-perl.
Preparing to unpack .../065-libalgorithm-merge-perl_0.08-5_all.deb ...
Unpacking libalgorithm-merge-perl (0.08-5) ...
Selecting previously unselected package libatk1.0-0t64:amd64.
Preparing to unpack .../066-libatk1.0-0t64_2.52.0-1build1_amd64.deb ...
Unpacking libatk1.0-0t64:amd64 (2.52.0-1build1) ...
Selecting previously unselected package libatk-bridge2.0-0t64:amd64.
Preparing to unpack .../067-libatk-bridge2.0-0t64_2.52.0-1build1_amd64.deb ...
Unpacking libatk-bridge2.0-0t64:amd64 (2.52.0-1build1) ...
Selecting previously unselected package libavahi-common-data:amd64.
Preparing to unpack .../068-libavahi-common-data_0.8-13ubuntu6.2_amd64.deb ...
Unpacking libavahi-common-data:amd64 (0.8-13ubuntu6.2) ...
Selecting previously unselected package libavahi-common3:amd64.
Preparing to unpack .../069-libavahi-common3_0.8-13ubuntu6.2_amd64.deb ...
Unpacking libavahi-common3:amd64 (0.8-13ubuntu6.2) ...
Selecting previously unselected package libavahi-client3:amd64.
Preparing to unpack .../070-libavahi-client3_0.8-13ubuntu6.2_amd64.deb ...
Unpacking libavahi-client3:amd64 (0.8-13ubuntu6.2) ...
Selecting previously unselected package libpixman-1-0:amd64.
Preparing to unpack .../071-libpixman-1-0_0.42.2-1build1_amd64.deb ...
Unpacking libpixman-1-0:amd64 (0.42.2-1build1) ...
Selecting previously unselected package libxcb-render0:amd64.
Preparing to unpack .../072-libxcb-render0_1.15-1ubuntu2_amd64.deb ...
Unpacking libxcb-render0:amd64 (1.15-1ubuntu2) ...
Selecting previously unselected package libxcb-shm0:amd64.
Preparing to unpack .../073-libxcb-shm0_1.15-1ubuntu2_amd64.deb ...
Unpacking libxcb-shm0:amd64 (1.15-1ubuntu2) ...
Selecting previously unselected package libxrender1:amd64.
Preparing to unpack .../074-libxrender1_1%3a0.9.10-1.1build1_amd64.deb ...
Unpacking libxrender1:amd64 (1:0.9.10-1.1build1) ...
Selecting previously unselected package libcairo2:amd64.
Preparing to unpack .../075-libcairo2_1.18.0-3build1_amd64.deb ...
Unpacking libcairo2:amd64 (1.18.0-3build1) ...
Selecting previously unselected package libcairo-gobject2:amd64.
Preparing to unpack .../076-libcairo-gobject2_1.18.0-3build1_amd64.deb ...
Unpacking libcairo-gobject2:amd64 (1.18.0-3build1) ...
Selecting previously unselected package liblcms2-2:amd64.
Preparing to unpack .../077-liblcms2-2_2.14-2ubuntu0.1_amd64.deb ...
Unpacking liblcms2-2:amd64 (2.14-2ubuntu0.1) ...
Selecting previously unselected package libcolord2:amd64.
Preparing to unpack .../078-libcolord2_1.4.7-1build2_amd64.deb ...
Unpacking libcolord2:amd64 (1.4.7-1build2) ...
Selecting previously unselected package libcups2t64:amd64.
Preparing to unpack .../079-libcups2t64_2.4.7-1.2ubuntu7.14_amd64.deb ...
Unpacking libcups2t64:amd64 (2.4.7-1.2ubuntu7.14) ...
Selecting previously unselected package libdatrie1:amd64.
Preparing to unpack .../080-libdatrie1_0.2.13-3build1_amd64.deb ...
Unpacking libdatrie1:amd64 (0.2.13-3build1) ...
Selecting previously unselected package libpciaccess0:amd64.
Preparing to unpack .../081-libpciaccess0_0.17-3ubuntu0.24.04.2_amd64.deb ...
Unpacking libpciaccess0:amd64 (0.17-3ubuntu0.24.04.2) ...
Selecting previously unselected package libdrm-intel1:amd64.
Preparing to unpack .../082-libdrm-intel1_2.4.125-1ubuntu0.1~24.04.2_amd64.deb ...
Unpacking libdrm-intel1:amd64 (2.4.125-1ubuntu0.1~24.04.2) ...
Selecting previously unselected package libllvm20:amd64.
Preparing to unpack .../083-libllvm20_1%3a20.1.2-0ubuntu1~24.04.3_amd64.deb ...
Unpacking libllvm20:amd64 (1:20.1.2-0ubuntu1~24.04.3) ...
Selecting previously unselected package libx11-xcb1:amd64.
Preparing to unpack .../084-libx11-xcb1_2%3a1.8.7-1build1_amd64.deb ...
Unpacking libx11-xcb1:amd64 (2:1.8.7-1build1) ...
Selecting previously unselected package libxcb-dri3-0:amd64.
Preparing to unpack .../085-libxcb-dri3-0_1.15-1ubuntu2_amd64.deb ...
Unpacking libxcb-dri3-0:amd64 (1.15-1ubuntu2) ...
Selecting previously unselected package libxcb-present0:amd64.
Preparing to unpack .../086-libxcb-present0_1.15-1ubuntu2_amd64.deb ...
Unpacking libxcb-present0:amd64 (1.15-1ubuntu2) ...
Selecting previously unselected package libxcb-randr0:amd64.
Preparing to unpack .../087-libxcb-randr0_1.15-1ubuntu2_amd64.deb ...
Unpacking libxcb-randr0:amd64 (1.15-1ubuntu2) ...
Selecting previously unselected package libxcb-sync1:amd64.
Preparing to unpack .../088-libxcb-sync1_1.15-1ubuntu2_amd64.deb ...
Unpacking libxcb-sync1:amd64 (1.15-1ubuntu2) ...
Selecting previously unselected package libxcb-xfixes0:amd64.
Preparing to unpack .../089-libxcb-xfixes0_1.15-1ubuntu2_amd64.deb ...
Unpacking libxcb-xfixes0:amd64 (1.15-1ubuntu2) ...
Selecting previously unselected package libxshmfence1:amd64.
Preparing to unpack .../090-libxshmfence1_1.3-1build5_amd64.deb ...
Unpacking libxshmfence1:amd64 (1.3-1build5) ...
Selecting previously unselected package mesa-libgallium:amd64.
Preparing to unpack .../091-mesa-libgallium_25.2.8-0ubuntu0.24.04.2_amd64.deb ...
Unpacking mesa-libgallium:amd64 (25.2.8-0ubuntu0.24.04.2) ...
Selecting previously unselected package libgbm1:amd64.
Preparing to unpack .../092-libgbm1_25.2.8-0ubuntu0.24.04.2_amd64.deb ...
Unpacking libgbm1:amd64 (25.2.8-0ubuntu0.24.04.2) ...
Selecting previously unselected package libwayland-client0:amd64.
Preparing to unpack .../093-libwayland-client0_1.22.0-2.1build1_amd64.deb ...
Unpacking libwayland-client0:amd64 (1.22.0-2.1build1) ...
Selecting previously unselected package libegl-mesa0:amd64.
Preparing to unpack .../094-libegl-mesa0_25.2.8-0ubuntu0.24.04.2_amd64.deb ...
Unpacking libegl-mesa0:amd64 (25.2.8-0ubuntu0.24.04.2) ...
Selecting previously unselected package libepoxy0:amd64.
Preparing to unpack .../095-libepoxy0_1.5.10-1build1_amd64.deb ...
Unpacking libepoxy0:amd64 (1.5.10-1build1) ...
Selecting previously unselected package libfile-fcntllock-perl.
Preparing to unpack .../096-libfile-fcntllock-perl_0.22-4ubuntu5_amd64.deb ...
Unpacking libfile-fcntllock-perl (0.22-4ubuntu5) ...
Selecting previously unselected package libfontenc1:amd64.
Preparing to unpack .../097-libfontenc1_1%3a1.1.8-1build1_amd64.deb ...
Unpacking libfontenc1:amd64 (1:1.1.8-1build1) ...
Selecting previously unselected package libgdk-pixbuf2.0-bin.
Preparing to unpack .../098-libgdk-pixbuf2.0-bin_2.42.10+dfsg-3ubuntu3.3_amd64.deb ...
Unpacking libgdk-pixbuf2.0-bin (2.42.10+dfsg-3ubuntu3.3) ...
Selecting previously unselected package libvulkan1:amd64.
Preparing to unpack .../099-libvulkan1_1.3.275.0-1build1_amd64.deb ...
Unpacking libvulkan1:amd64 (1.3.275.0-1build1) ...
Selecting previously unselected package libgl1-mesa-dri:amd64.
Preparing to unpack .../100-libgl1-mesa-dri_25.2.8-0ubuntu0.24.04.2_amd64.deb ...
Unpacking libgl1-mesa-dri:amd64 (25.2.8-0ubuntu0.24.04.2) ...
Selecting previously unselected package libxcb-glx0:amd64.
Preparing to unpack .../101-libxcb-glx0_1.15-1ubuntu2_amd64.deb ...
Unpacking libxcb-glx0:amd64 (1.15-1ubuntu2) ...
Selecting previously unselected package libxxf86vm1:amd64.
Preparing to unpack .../102-libxxf86vm1_1%3a1.1.4-1build4_amd64.deb ...
Unpacking libxxf86vm1:amd64 (1:1.1.4-1build4) ...
Selecting previously unselected package libglx-mesa0:amd64.
Preparing to unpack .../103-libglx-mesa0_25.2.8-0ubuntu0.24.04.2_amd64.deb ...
Unpacking libglx-mesa0:amd64 (25.2.8-0ubuntu0.24.04.2) ...
Selecting previously unselected package libgraphite2-3:amd64.
Preparing to unpack .../104-libgraphite2-3_1.3.14-2ubuntu0.24.04.1_amd64.deb ...
Unpacking libgraphite2-3:amd64 (1.3.14-2ubuntu0.24.04.1) ...
Selecting previously unselected package libharfbuzz0b:amd64.
Preparing to unpack .../105-libharfbuzz0b_8.3.0-2build2_amd64.deb ...
Unpacking libharfbuzz0b:amd64 (8.3.0-2build2) ...
Selecting previously unselected package libthai-data.
Preparing to unpack .../106-libthai-data_0.1.29-2build1_all.deb ...
Unpacking libthai-data (0.1.29-2build1) ...
Selecting previously unselected package libthai0:amd64.
Preparing to unpack .../107-libthai0_0.1.29-2build1_amd64.deb ...
Unpacking libthai0:amd64 (0.1.29-2build1) ...
Selecting previously unselected package libpango-1.0-0:amd64.
Preparing to unpack .../108-libpango-1.0-0_1.52.1+ds-1build1_amd64.deb ...
Unpacking libpango-1.0-0:amd64 (1.52.1+ds-1build1) ...
Selecting previously unselected package libpangoft2-1.0-0:amd64.
Preparing to unpack .../109-libpangoft2-1.0-0_1.52.1+ds-1build1_amd64.deb ...
Unpacking libpangoft2-1.0-0:amd64 (1.52.1+ds-1build1) ...
Selecting previously unselected package libpangocairo-1.0-0:amd64.
Preparing to unpack .../110-libpangocairo-1.0-0_1.52.1+ds-1build1_amd64.deb ...
Unpacking libpangocairo-1.0-0:amd64 (1.52.1+ds-1build1) ...
Selecting previously unselected package libwayland-cursor0:amd64.
Preparing to unpack .../111-libwayland-cursor0_1.22.0-2.1build1_amd64.deb ...
Unpacking libwayland-cursor0:amd64 (1.22.0-2.1build1) ...
Selecting previously unselected package libwayland-egl1:amd64.
Preparing to unpack .../112-libwayland-egl1_1.22.0-2.1build1_amd64.deb ...
Unpacking libwayland-egl1:amd64 (1.22.0-2.1build1) ...
Selecting previously unselected package libxcomposite1:amd64.
Preparing to unpack .../113-libxcomposite1_1%3a0.4.5-1build3_amd64.deb ...
Unpacking libxcomposite1:amd64 (1:0.4.5-1build3) ...
Selecting previously unselected package libxfixes3:amd64.
Preparing to unpack .../114-libxfixes3_1%3a6.0.0-2build1_amd64.deb ...
Unpacking libxfixes3:amd64 (1:6.0.0-2build1) ...
Selecting previously unselected package libxcursor1:amd64.
Preparing to unpack .../115-libxcursor1_1%3a1.2.1-1build1_amd64.deb ...
Unpacking libxcursor1:amd64 (1:1.2.1-1build1) ...
Selecting previously unselected package libxdamage1:amd64.
Preparing to unpack .../116-libxdamage1_1%3a1.1.6-1build1_amd64.deb ...
Unpacking libxdamage1:amd64 (1:1.1.6-1build1) ...
Selecting previously unselected package libxinerama1:amd64.
Preparing to unpack .../117-libxinerama1_2%3a1.1.4-3build1_amd64.deb ...
Unpacking libxinerama1:amd64 (2:1.1.4-3build1) ...
Selecting previously unselected package libxrandr2:amd64.
Preparing to unpack .../118-libxrandr2_2%3a1.5.2-2build1_amd64.deb ...
Unpacking libxrandr2:amd64 (2:1.5.2-2build1) ...
Selecting previously unselected package libgtk-3-common.
Preparing to unpack .../119-libgtk-3-common_3.24.41-4ubuntu1.3_all.deb ...
Unpacking libgtk-3-common (3.24.41-4ubuntu1.3) ...
Selecting previously unselected package libgtk-3-0t64:amd64.
Preparing to unpack .../120-libgtk-3-0t64_3.24.41-4ubuntu1.3_amd64.deb ...
Unpacking libgtk-3-0t64:amd64 (3.24.41-4ubuntu1.3) ...
Selecting previously unselected package libgtk-3-bin.
Preparing to unpack .../121-libgtk-3-bin_3.24.41-4ubuntu1.3_amd64.deb ...
Unpacking libgtk-3-bin (3.24.41-4ubuntu1.3) ...
Selecting previously unselected package libice6:amd64.
Preparing to unpack .../122-libice6_2%3a1.0.10-1build3_amd64.deb ...
Unpacking libice6:amd64 (2:1.0.10-1build3) ...
Selecting previously unselected package nvidia-firmware-595-595.71.05.
Preparing to unpack .../123-nvidia-firmware-595-595.71.05_595.71.05-0ubuntu0.24.04.1_amd64.deb ...
Unpacking nvidia-firmware-595-595.71.05 (595.71.05-0ubuntu0.24.04.1) ...
Selecting previously unselected package nvidia-kernel-common-595.
Preparing to unpack .../124-nvidia-kernel-common-595_595.71.05-0ubuntu0.24.04.1_amd64.deb ...
Unpacking nvidia-kernel-common-595 (595.71.05-0ubuntu0.24.04.1) ...
Selecting previously unselected package libnvidia-cfg1-595:amd64.
Preparing to unpack .../125-libnvidia-cfg1-595_595.71.05-0ubuntu0.24.04.1_amd64.deb ...
Unpacking libnvidia-cfg1-595:amd64 (595.71.05-0ubuntu0.24.04.1) ...
Selecting previously unselected package libnvidia-common-595.
Preparing to unpack .../126-libnvidia-common-595_595.71.05-0ubuntu0.24.04.1_amd64.deb ...
Unpacking libnvidia-common-595 (595.71.05-0ubuntu0.24.04.1) ...
Selecting previously unselected package ocl-icd-libopencl1:amd64.
Preparing to unpack .../127-ocl-icd-libopencl1_2.3.2-1build1_amd64.deb ...
Unpacking ocl-icd-libopencl1:amd64 (2.3.2-1build1) ...
Selecting previously unselected package libnvidia-compute-595:amd64.
Preparing to unpack .../128-libnvidia-compute-595_595.71.05-0ubuntu0.24.04.1_amd64.deb ...
Unpacking libnvidia-compute-595:amd64 (595.71.05-0ubuntu0.24.04.1) ...
Selecting previously unselected package libnvidia-decode-595:amd64.
Preparing to unpack .../129-libnvidia-decode-595_595.71.05-0ubuntu0.24.04.1_amd64.deb ...
Unpacking libnvidia-decode-595:amd64 (595.71.05-0ubuntu0.24.04.1) ...
Selecting previously unselected package libwayland-server0:amd64.
Preparing to unpack .../130-libwayland-server0_1.22.0-2.1build1_amd64.deb ...
Unpacking libwayland-server0:amd64 (1.22.0-2.1build1) ...
Selecting previously unselected package libnvidia-egl-wayland1:amd64.
Preparing to unpack .../131-libnvidia-egl-wayland1_1%3a1.1.13-1ubuntu0.1_amd64.deb ...
Unpacking libnvidia-egl-wayland1:amd64 (1:1.1.13-1ubuntu0.1) ...
Selecting previously unselected package libnvidia-encode-595:amd64.
Preparing to unpack .../132-libnvidia-encode-595_595.71.05-0ubuntu0.24.04.1_amd64.deb ...
Unpacking libnvidia-encode-595:amd64 (595.71.05-0ubuntu0.24.04.1) ...
Selecting previously unselected package libnvidia-extra-595:amd64.
Preparing to unpack .../133-libnvidia-extra-595_595.71.05-0ubuntu0.24.04.1_amd64.deb ...
Unpacking libnvidia-extra-595:amd64 (595.71.05-0ubuntu0.24.04.1) ...
Selecting previously unselected package libnvidia-fbc1-595:amd64.
Preparing to unpack .../134-libnvidia-fbc1-595_595.71.05-0ubuntu0.24.04.1_amd64.deb ...
Unpacking libnvidia-fbc1-595:amd64 (595.71.05-0ubuntu0.24.04.1) ...
Selecting previously unselected package libnvidia-gl-595:amd64.
Preparing to unpack .../135-libnvidia-gl-595_595.71.05-0ubuntu0.24.04.1_amd64.deb ...
dpkg-query: no packages found matching libnvidia-gl-550
Unpacking libnvidia-gl-595:amd64 (595.71.05-0ubuntu0.24.04.1) ...
Selecting previously unselected package libpkgconf3:amd64.
Preparing to unpack .../136-libpkgconf3_1.8.1-2build1_amd64.deb ...
Unpacking libpkgconf3:amd64 (1.8.1-2build1) ...
Selecting previously unselected package librsvg2-2:amd64.
Preparing to unpack .../137-librsvg2-2_2.58.0+dfsg-1build1_amd64.deb ...
Unpacking librsvg2-2:amd64 (2.58.0+dfsg-1build1) ...
Selecting previously unselected package librsvg2-common:amd64.
Preparing to unpack .../138-librsvg2-common_2.58.0+dfsg-1build1_amd64.deb ...
Unpacking librsvg2-common:amd64 (2.58.0+dfsg-1build1) ...
Selecting previously unselected package libsm6:amd64.
Preparing to unpack .../139-libsm6_2%3a1.2.3-1build3_amd64.deb ...
Unpacking libsm6:amd64 (2:1.2.3-1build3) ...
Selecting previously unselected package libvdpau1:amd64.
Preparing to unpack .../140-libvdpau1_1.5-2build1_amd64.deb ...
Unpacking libvdpau1:amd64 (1.5-2build1) ...
Selecting previously unselected package libxt6t64:amd64.
Preparing to unpack .../141-libxt6t64_1%3a1.2.1-1.2build1_amd64.deb ...
Unpacking libxt6t64:amd64 (1:1.2.1-1.2build1) ...
Selecting previously unselected package libxmu6:amd64.
Preparing to unpack .../142-libxmu6_2%3a1.1.3-3build2_amd64.deb ...
Unpacking libxmu6:amd64 (2:1.1.3-3build2) ...
Selecting previously unselected package libxaw7:amd64.
Preparing to unpack .../143-libxaw7_2%3a1.0.14-1build2_amd64.deb ...
Unpacking libxaw7:amd64 (2:1.0.14-1build2) ...
Selecting previously unselected package libxcvt0:amd64.
Preparing to unpack .../144-libxcvt0_0.1.2-1build1_amd64.deb ...
Unpacking libxcvt0:amd64 (0.1.2-1build1) ...
Selecting previously unselected package libxfont2:amd64.
Preparing to unpack .../145-libxfont2_1%3a2.0.6-1build1_amd64.deb ...
Unpacking libxfont2:amd64 (1:2.0.6-1build1) ...
Selecting previously unselected package libxkbfile1:amd64.
Preparing to unpack .../146-libxkbfile1_1%3a1.1.0-1build4_amd64.deb ...
Unpacking libxkbfile1:amd64 (1:1.1.0-1build4) ...
Selecting previously unselected package libxnvctrl0:amd64.
Preparing to unpack .../147-libxnvctrl0_510.47.03-0ubuntu4.24.04.1_amd64.deb ...
Unpacking libxnvctrl0:amd64 (510.47.03-0ubuntu4.24.04.1) ...
Selecting previously unselected package mesa-vdpau-drivers:amd64.
Preparing to unpack .../148-mesa-vdpau-drivers_25.2.8-0ubuntu0.24.04.2_amd64.deb ...
Unpacking mesa-vdpau-drivers:amd64 (25.2.8-0ubuntu0.24.04.2) ...
Selecting previously unselected package mesa-vulkan-drivers:amd64.
Preparing to unpack .../149-mesa-vulkan-drivers_25.2.8-0ubuntu0.24.04.2_amd64.deb ...
Unpacking mesa-vulkan-drivers:amd64 (25.2.8-0ubuntu0.24.04.2) ...
Selecting previously unselected package nvidia-compute-utils-595.
Preparing to unpack .../150-nvidia-compute-utils-595_595.71.05-0ubuntu0.24.04.1_amd64.deb ...
Unpacking nvidia-compute-utils-595 (595.71.05-0ubuntu0.24.04.1) ...
Selecting previously unselected package nvidia-kernel-source-595-open.
Preparing to unpack .../151-nvidia-kernel-source-595-open_595.71.05-0ubuntu0.24.04.1_amd64.deb ...
Unpacking nvidia-kernel-source-595-open (595.71.05-0ubuntu0.24.04.1) ...
Selecting previously unselected package nvidia-dkms-595-open.
Preparing to unpack .../152-nvidia-dkms-595-open_595.71.05-0ubuntu0.24.04.1_amd64.deb ...
Unpacking nvidia-dkms-595-open (595.71.05-0ubuntu0.24.04.1) ...
Selecting previously unselected package nvidia-utils-595.
Preparing to unpack .../153-nvidia-utils-595_595.71.05-0ubuntu0.24.04.1_amd64.deb ...
Unpacking nvidia-utils-595 (595.71.05-0ubuntu0.24.04.1) ...
Selecting previously unselected package x11-xkb-utils.
Preparing to unpack .../154-x11-xkb-utils_7.7+8build2_amd64.deb ...
Unpacking x11-xkb-utils (7.7+8build2) ...
Selecting previously unselected package xserver-common.
Preparing to unpack .../155-xserver-common_2%3a21.1.12-1ubuntu1.6_all.deb ...
Unpacking xserver-common (2:21.1.12-1ubuntu1.6) ...
Selecting previously unselected package libglvnd0:amd64.
Preparing to unpack .../156-libglvnd0_1.7.0-1build1_amd64.deb ...
Unpacking libglvnd0:amd64 (1.7.0-1build1) ...
Selecting previously unselected package libegl1:amd64.
Preparing to unpack .../157-libegl1_1.7.0-1build1_amd64.deb ...
Unpacking libegl1:amd64 (1.7.0-1build1) ...
Selecting previously unselected package libglx0:amd64.
Preparing to unpack .../158-libglx0_1.7.0-1build1_amd64.deb ...
Unpacking libglx0:amd64 (1.7.0-1build1) ...
Selecting previously unselected package libgl1:amd64.
Preparing to unpack .../159-libgl1_1.7.0-1build1_amd64.deb ...
Unpacking libgl1:amd64 (1.7.0-1build1) ...
Selecting previously unselected package xserver-xorg-core.
Preparing to unpack .../160-xserver-xorg-core_2%3a21.1.12-1ubuntu1.6_amd64.deb ...
Unpacking xserver-xorg-core (2:21.1.12-1ubuntu1.6) ...
Selecting previously unselected package xserver-xorg-video-nvidia-595.
Preparing to unpack .../161-xserver-xorg-video-nvidia-595_595.71.05-0ubuntu0.24.04.1_amd64.deb ...
Unpacking xserver-xorg-video-nvidia-595 (595.71.05-0ubuntu0.24.04.1) ...
Selecting previously unselected package nvidia-driver-595-open.
Preparing to unpack .../162-nvidia-driver-595-open_595.71.05-0ubuntu0.24.04.1_amd64.deb ...
Unpacking nvidia-driver-595-open (595.71.05-0ubuntu0.24.04.1) ...
Selecting previously unselected package nvidia-prime.
Preparing to unpack .../163-nvidia-prime_0.8.17.2_all.deb ...
Unpacking nvidia-prime (0.8.17.2) ...
Selecting previously unselected package pkgconf-bin.
Preparing to unpack .../164-pkgconf-bin_1.8.1-2build1_amd64.deb ...
Unpacking pkgconf-bin (1.8.1-2build1) ...
Selecting previously unselected package pkgconf:amd64.
Preparing to unpack .../165-pkgconf_1.8.1-2build1_amd64.deb ...
Unpacking pkgconf:amd64 (1.8.1-2build1) ...
Selecting previously unselected package pkg-config:amd64.
Preparing to unpack .../166-pkg-config_1.8.1-2build1_amd64.deb ...
Unpacking pkg-config:amd64 (1.8.1-2build1) ...
Selecting previously unselected package pkexec.
Preparing to unpack .../167-pkexec_124-2ubuntu1.24.04.3_amd64.deb ...
Unpacking pkexec (124-2ubuntu1.24.04.3) ...
Selecting previously unselected package screen-resolution-extra.
Preparing to unpack .../168-screen-resolution-extra_0.18.3ubuntu0.24.04.1_all.deb ...
Unpacking screen-resolution-extra (0.18.3ubuntu0.24.04.1) ...
Selecting previously unselected package nvidia-settings.
Preparing to unpack .../169-nvidia-settings_510.47.03-0ubuntu4.24.04.1_amd64.deb ...
Unpacking nvidia-settings (510.47.03-0ubuntu4.24.04.1) ...
Selecting previously unselected package vdpau-driver-all:amd64.
Preparing to unpack .../170-vdpau-driver-all_1.5-2build1_amd64.deb ...
Unpacking vdpau-driver-all:amd64 (1.5-2build1) ...
Selecting previously unselected package xcvt.
Preparing to unpack .../171-xcvt_0.1.2-1build1_amd64.deb ...
Unpacking xcvt (0.1.2-1build1) ...
Selecting previously unselected package xfonts-encodings.
Preparing to unpack .../172-xfonts-encodings_1%3a1.0.5-0ubuntu2_all.deb ...
Unpacking xfonts-encodings (1:1.0.5-0ubuntu2) ...
Selecting previously unselected package xfonts-utils.
Preparing to unpack .../173-xfonts-utils_1%3a7.7+6build3_amd64.deb ...
Unpacking xfonts-utils (1:7.7+6build3) ...
Selecting previously unselected package xfonts-base.
Preparing to unpack .../174-xfonts-base_1%3a1.0.5+nmu1_all.deb ...
Unpacking xfonts-base (1:1.0.5+nmu1) ...
Setting up libgraphite2-3:amd64 (1.3.14-2ubuntu0.24.04.1) ...
Setting up libxcb-dri3-0:amd64 (1.15-1ubuntu2) ...
Setting up liblcms2-2:amd64 (2.14-2ubuntu0.1) ...
Setting up libpixman-1-0:amd64 (0.42.2-1build1) ...
Setting up libwayland-server0:amd64 (1.22.0-2.1build1) ...
Setting up libx11-xcb1:amd64 (2:1.8.7-1build1) ...
Setting up libpciaccess0:amd64 (0.17-3ubuntu0.24.04.2) ...
Setting up session-migration (0.3.9build1) ...
Created symlink /etc/systemd/user/graphical-session-pre.target.wants/session-migration.service → /usr/lib/systemd/user/session-migration.service.
Setting up fontconfig (2.15.0-1.1ubuntu2) ...
Regenerating fonts cache... done.
Setting up lto-disabled-list (47) ...
Setting up libxdamage1:amd64 (1:1.1.6-1build1) ...
Setting up libxcb-xfixes0:amd64 (1.15-1ubuntu2) ...
Setting up hicolor-icon-theme (0.17-2) ...
Setting up libxi6:amd64 (2:1.8.1-1build1) ...
Setting up libxrender1:amd64 (1:0.9.10-1.1build1) ...
Setting up libdatrie1:amd64 (0.2.13-3build1) ...
Setting up libfile-fcntllock-perl (0.22-4ubuntu5) ...
Setting up libxcb-render0:amd64 (1.15-1ubuntu2) ...
Setting up libalgorithm-diff-perl (1.201-1) ...
Setting up nvidia-prime (0.8.17.2) ...
Setting up libglvnd0:amd64 (1.7.0-1build1) ...
Setting up libxcb-glx0:amd64 (1.15-1ubuntu2) ...
Setting up libdrm-intel1:amd64 (2.4.125-1ubuntu0.1~24.04.2) ...
Setting up libgdk-pixbuf2.0-common (2.42.10+dfsg-3ubuntu3.3) ...
Setting up binutils-common:amd64 (2.42-4ubuntu2.10) ...
Setting up x11-common (1:7.7+23ubuntu3) ...
Setting up nvidia-kernel-source-595-open (595.71.05-0ubuntu0.24.04.1) ...
Setting up libctf-nobfd0:amd64 (2.42-4ubuntu2.10) ...
Setting up pkexec (124-2ubuntu1.24.04.3) ...
Setting up libxcb-shm0:amd64 (1.15-1ubuntu2) ...
Setting up libgomp1:amd64 (14.2.0-4ubuntu2~24.04.1) ...
Setting up bzip2 (1.0.8-5.1build0.1) ...
Setting up libcairo2:amd64 (1.18.0-3build1) ...
Setting up libcolord2:amd64 (1.4.7-1build2) ...
Setting up libsframe1:amd64 (2.42-4ubuntu2.10) ...
Setting up libfakeroot:amd64 (1.33-1) ...
Setting up libxxf86vm1:amd64 (1:1.1.4-1build4) ...
Setting up libxnvctrl0:amd64 (510.47.03-0ubuntu4.24.04.1) ...
Setting up fakeroot (1.33-1) ...
update-alternatives: using /usr/bin/fakeroot-sysv to provide /usr/bin/fakeroot (fakeroot) in auto mode
Setting up libxcb-present0:amd64 (1.15-1ubuntu2) ...
Setting up libdconf1:amd64 (0.40.0-4ubuntu0.1) ...
Setting up libfontenc1:amd64 (1:1.1.8-1build1) ...
Setting up libpkgconf3:amd64 (1.8.1-2build1) ...
Setting up gcc-13-base:amd64 (13.3.0-6ubuntu2~24.04.1) ...
Setting up make (4.3-4.1build2) ...
Setting up libepoxy0:amd64 (1.5.10-1build1) ...
Setting up libxfixes3:amd64 (1:6.0.0-2build1) ...
Setting up libxcb-sync1:amd64 (1.15-1ubuntu2) ...
Setting up nvidia-firmware-595-595.71.05 (595.71.05-0ubuntu0.24.04.1) ...
Setting up libavahi-common-data:amd64 (0.8-13ubuntu6.2) ...
Setting up libatspi2.0-0t64:amd64 (2.52.0-1build1) ...
Setting up xfonts-encodings (1:1.0.5-0ubuntu2) ...
Setting up libquadmath0:amd64 (14.2.0-4ubuntu2~24.04.1) ...
Setting up libxinerama1:amd64 (2:1.1.4-3build1) ...
Setting up libmpc3:amd64 (1.3.1-1build1.1) ...
Setting up libatomic1:amd64 (14.2.0-4ubuntu2~24.04.1) ...
Setting up libxrandr2:amd64 (2:1.5.2-2build1) ...
Setting up libllvm20:amd64 (1:20.1.2-0ubuntu1~24.04.3) ...
Setting up pkgconf-bin (1.8.1-2build1) ...
Setting up libdpkg-perl (1.22.6ubuntu6.6) ...
Setting up libvulkan1:amd64 (1.3.275.0-1build1) ...
Setting up libubsan1:amd64 (14.2.0-4ubuntu2~24.04.1) ...
Setting up screen-resolution-extra (0.18.3ubuntu0.24.04.1) ...
Setting up ocl-icd-libopencl1:amd64 (2.3.2-1build1) ...
Setting up libxshmfence1:amd64 (1.3-1build5) ...
Setting up libhwasan0:amd64 (14.2.0-4ubuntu2~24.04.1) ...
Setting up at-spi2-common (2.52.0-1build1) ...
Setting up libvdpau1:amd64 (1.5-2build1) ...
Setting up libxcb-randr0:amd64 (1.15-1ubuntu2) ...
Setting up libasan8:amd64 (14.2.0-4ubuntu2~24.04.1) ...
Setting up libxcvt0:amd64 (0.1.2-1build1) ...
Setting up libharfbuzz0b:amd64 (8.3.0-2build2) ...
Setting up libthai-data (0.1.29-2build1) ...
Setting up libgdk-pixbuf-2.0-0:amd64 (2.42.10+dfsg-3ubuntu3.3) ...
Setting up libcairo-gobject2:amd64 (1.18.0-3build1) ...
Setting up libwayland-egl1:amd64 (1.22.0-2.1build1) ...
Setting up libxkbfile1:amd64 (1:1.1.0-1build4) ...
Setting up libtsan2:amd64 (14.2.0-4ubuntu2~24.04.1) ...
Setting up libbinutils:amd64 (2.42-4ubuntu2.10) ...
Setting up libisl23:amd64 (0.26-3build1.1) ...
Setting up libxcomposite1:amd64 (1:0.4.5-1build3) ...
Setting up libxfont2:amd64 (1:2.0.6-1build1) ...
Setting up libalgorithm-diff-xs-perl:amd64 (0.04-8build3) ...
Setting up libcc1-0:amd64 (14.2.0-4ubuntu2~24.04.1) ...
Setting up liblsan0:amd64 (14.2.0-4ubuntu2~24.04.1) ...
Setting up libitm1:amd64 (14.2.0-4ubuntu2~24.04.1) ...
Setting up libalgorithm-merge-perl (0.08-5) ...
Setting up libwayland-client0:amd64 (1.22.0-2.1build1) ...
Setting up libctf0:amd64 (2.42-4ubuntu2.10) ...
Setting up mesa-vulkan-drivers:amd64 (25.2.8-0ubuntu0.24.04.2) ...
Setting up mesa-vdpau-drivers:amd64 (25.2.8-0ubuntu0.24.04.2) ...
Setting up gtk-update-icon-cache (3.24.41-4ubuntu1.3) ...
Setting up libice6:amd64 (2:1.0.10-1build3) ...
Setting up mesa-libgallium:amd64 (25.2.8-0ubuntu0.24.04.2) ...
Setting up libatk1.0-0t64:amd64 (2.52.0-1build1) ...
Setting up libgbm1:amd64 (25.2.8-0ubuntu0.24.04.2) ...
Setting up cpp-13-x86-64-linux-gnu (13.3.0-6ubuntu2~24.04.1) ...
Setting up libxtst6:amd64 (2:1.2.3-1.1build1) ...
Setting up libxcursor1:amd64 (1:1.2.1-1build1) ...
Setting up libgl1-mesa-dri:amd64 (25.2.8-0ubuntu0.24.04.2) ...
Setting up libavahi-common3:amd64 (0.8-13ubuntu6.2) ...
Setting up nvidia-kernel-common-595 (595.71.05-0ubuntu0.24.04.1) ...
update-initramfs: deferring update (trigger activated)
Created symlink /etc/systemd/system/systemd-hibernate.service.wants/nvidia-hibernate.service → /usr/lib/systemd/system/nvidia-hibernate.service.
Created symlink /etc/systemd/system/systemd-suspend.service.wants/nvidia-resume.service → /usr/lib/systemd/system/nvidia-resume.service.
Created symlink /etc/systemd/system/systemd-hibernate.service.wants/nvidia-resume.service → /usr/lib/systemd/system/nvidia-resume.service.
Created symlink /etc/systemd/system/systemd-suspend-then-hibernate.service.wants/nvidia-resume.service → /usr/lib/systemd/system/nvidia-resume.service.
Created symlink /etc/systemd/system/systemd-suspend.service.wants/nvidia-suspend.service → /usr/lib/systemd/system/nvidia-suspend.service.
Setting up dconf-service (0.40.0-4ubuntu0.1) ...
Setting up libnvidia-extra-595:amd64 (595.71.05-0ubuntu0.24.04.1) ...
Setting up xfonts-utils (1:7.7+6build3) ...
Setting up pkgconf:amd64 (1.8.1-2build1) ...
Setting up xcvt (0.1.2-1build1) ...
Setting up libnvidia-egl-wayland1:amd64 (1:1.1.13-1ubuntu0.1) ...
Setting up libnvidia-cfg1-595:amd64 (595.71.05-0ubuntu0.24.04.1) ...
Setting up libthai0:amd64 (0.1.29-2build1) ...
Setting up xfonts-base (1:1.0.5+nmu1) ...
Setting up libgprofng0:amd64 (2.42-4ubuntu2.10) ...
Setting up libegl-mesa0:amd64 (25.2.8-0ubuntu0.24.04.2) ...
Setting up pkg-config:amd64 (1.8.1-2build1) ...
Setting up vdpau-driver-all:amd64 (1.5-2build1) ...
Setting up libgcc-13-dev:amd64 (13.3.0-6ubuntu2~24.04.1) ...
Setting up libgdk-pixbuf2.0-bin (2.42.10+dfsg-3ubuntu3.3) ...
Setting up libwayland-cursor0:amd64 (1.22.0-2.1build1) ...
Setting up libegl1:amd64 (1.7.0-1build1) ...
Setting up libsm6:amd64 (2:1.2.3-1build3) ...
Setting up libavahi-client3:amd64 (0.8-13ubuntu6.2) ...
Setting up libnvidia-common-595 (595.71.05-0ubuntu0.24.04.1) ...
Setting up libstdc++-13-dev:amd64 (13.3.0-6ubuntu2~24.04.1) ...
Setting up binutils-x86-64-linux-gnu (2.42-4ubuntu2.10) ...
Setting up cpp-x86-64-linux-gnu (4:13.2.0-7ubuntu1) ...
Setting up libatk-bridge2.0-0t64:amd64 (2.52.0-1build1) ...
Setting up libglx-mesa0:amd64 (25.2.8-0ubuntu0.24.04.2) ...
Setting up libglx0:amd64 (1.7.0-1build1) ...
Setting up cpp-13 (13.3.0-6ubuntu2~24.04.1) ...
Setting up dconf-gsettings-backend:amd64 (0.40.0-4ubuntu0.1) ...
Setting up gcc-13-x86-64-linux-gnu (13.3.0-6ubuntu2~24.04.1) ...
Setting up libpango-1.0-0:amd64 (1.52.1+ds-1build1) ...
Setting up libnvidia-fbc1-595:amd64 (595.71.05-0ubuntu0.24.04.1) ...
Setting up libnvidia-compute-595:amd64 (595.71.05-0ubuntu0.24.04.1) ...
Setting up binutils (2.42-4ubuntu2.10) ...
Setting up libnvidia-gl-595:amd64 (595.71.05-0ubuntu0.24.04.1) ...
Setting up dpkg-dev (1.22.6ubuntu6.6) ...
Setting up libgl1:amd64 (1.7.0-1build1) ...
Setting up libxt6t64:amd64 (1:1.2.1-1.2build1) ...
Setting up gcc-13 (13.3.0-6ubuntu2~24.04.1) ...
Setting up cpp (4:13.2.0-7ubuntu1) ...
Setting up libpangoft2-1.0-0:amd64 (1.52.1+ds-1build1) ...
Setting up nvidia-utils-595 (595.71.05-0ubuntu0.24.04.1) ...
Setting up libcups2t64:amd64 (2.4.7-1.2ubuntu7.14) ...
Setting up libgtk-3-common (3.24.41-4ubuntu1.3) ...
Setting up libpangocairo-1.0-0:amd64 (1.52.1+ds-1build1) ...
Setting up nvidia-compute-utils-595 (595.71.05-0ubuntu0.24.04.1) ...
info: The home dir /nonexistent you specified can't be accessed: No such file or directory

info: Selecting UID from range 100 to 999 ...

info: Selecting GID from range 100 to 999 ...
info: Adding system user `nvidia-persistenced' (UID 110) ...
info: Adding new group `nvidia-persistenced' (GID 110) ...
info: Adding new user `nvidia-persistenced' (UID 110) with group `nvidia-persistenced' ...
info: Not creating `/nonexistent'.
Setting up gsettings-desktop-schemas (46.1-0ubuntu1) ...
Setting up libnvidia-decode-595:amd64 (595.71.05-0ubuntu0.24.04.1) ...
Setting up libxmu6:amd64 (2:1.1.3-3build2) ...
Setting up g++-13-x86-64-linux-gnu (13.3.0-6ubuntu2~24.04.1) ...
Setting up gcc-x86-64-linux-gnu (4:13.2.0-7ubuntu1) ...
Setting up libnvidia-encode-595:amd64 (595.71.05-0ubuntu0.24.04.1) ...
Setting up libxaw7:amd64 (2:1.0.14-1build2) ...
Setting up gcc (4:13.2.0-7ubuntu1) ...
Setting up dkms (3.0.11-1ubuntu13) ...
Setting up librsvg2-2:amd64 (2.58.0+dfsg-1build1) ...
Setting up librsvg2-common:amd64 (2.58.0+dfsg-1build1) ...
Setting up g++-x86-64-linux-gnu (4:13.2.0-7ubuntu1) ...
Setting up g++-13 (13.3.0-6ubuntu2~24.04.1) ...
Setting up x11-xkb-utils (7.7+8build2) ...
Setting up nvidia-dkms-595-open (595.71.05-0ubuntu0.24.04.1) ...
update-initramfs: deferring update (trigger activated)
INFO:Enable nvidia
DEBUG:Parsing /usr/share/ubuntu-drivers-common/quirks/dell_latitude
DEBUG:Parsing /usr/share/ubuntu-drivers-common/quirks/put_your_quirks_here
DEBUG:Parsing /usr/share/ubuntu-drivers-common/quirks/lenovo_thinkpad
Loading new nvidia-595.71.05 DKMS files...
Building for 6.8.0-134-generic
Building for architecture x86_64
Building initial module for 6.8.0-134-generic
Secure Boot not enabled on this system.
Done.

nvidia.ko.zst:
Running module version sanity check.
 - Original module
   - No original module exists within this kernel
 - Installation
   - Installing to /lib/modules/6.8.0-134-generic/updates/dkms/

nvidia-modeset.ko.zst:
Running module version sanity check.
 - Original module
   - No original module exists within this kernel
 - Installation
   - Installing to /lib/modules/6.8.0-134-generic/updates/dkms/

nvidia-drm.ko.zst:
Running module version sanity check.
 - Original module
   - No original module exists within this kernel
 - Installation
   - Installing to /lib/modules/6.8.0-134-generic/updates/dkms/

nvidia-uvm.ko.zst:
Running module version sanity check.
 - Original module
   - No original module exists within this kernel
 - Installation
   - Installing to /lib/modules/6.8.0-134-generic/updates/dkms/

nvidia-peermem.ko.zst:
Running module version sanity check.
 - Original module
   - No original module exists within this kernel
 - Installation
   - Installing to /lib/modules/6.8.0-134-generic/updates/dkms/
depmod...
Setting up g++ (4:13.2.0-7ubuntu1) ...
update-alternatives: using /usr/bin/g++ to provide /usr/bin/c++ (c++) in auto mode
Setting up build-essential (12.10ubuntu1) ...
Setting up xserver-common (2:21.1.12-1ubuntu1.6) ...
Setting up xserver-xorg-core (2:21.1.12-1ubuntu1.6) ...
Setting up xserver-xorg-video-nvidia-595 (595.71.05-0ubuntu0.24.04.1) ...
Setting up nvidia-driver-595-open (595.71.05-0ubuntu0.24.04.1) ...
Setting up adwaita-icon-theme (46.0-1) ...
update-alternatives: using /usr/share/icons/Adwaita/cursor.theme to provide /usr/share/icons/default/index.theme (x-cursor-theme) in auto mode
Setting up humanity-icon-theme (0.6.16) ...
Setting up ubuntu-mono (24.04-0ubuntu1) ...
Processing triggers for man-db (2.12.0-4build2) ...
Processing triggers for libglib2.0-0t64:amd64 (2.80.0-6ubuntu3.8) ...
Setting up libgtk-3-0t64:amd64 (3.24.41-4ubuntu1.3) ...
Setting up at-spi2-core (2.52.0-1build1) ...
Setting up nvidia-settings (510.47.03-0ubuntu4.24.04.1) ...
Processing triggers for initramfs-tools (0.142ubuntu25.8) ...
update-initramfs: Generating /boot/initrd.img-6.8.0-134-generic
Processing triggers for libc-bin (2.39-0ubuntu8.7) ...
Setting up libgtk-3-bin (3.24.41-4ubuntu1.3) ...
Processing triggers for libgdk-pixbuf-2.0-0:amd64 (2.42.10+dfsg-3ubuntu3.3) ...

Running kernel seems to be up-to-date.

No services need to be restarted.

No containers need to be restarted.

No user sessions are running outdated binaries.

No VM guests are running outdated hypervisor (qemu) binaries on this host.

[exit=0]
```

### Driver install command conclusion

PASS: apt install completed for approved host NVIDIA driver package targets only.

## Installed Package And Pre-reboot State

- Timestamp: 2026-07-03T07:31:53+00:00

### Installed NVIDIA/CUDA/container-toolkit packages after driver install

```console
$ dpkg -l | egrep 'nvidia|cuda|container-toolkit' || true
ii  libnvidia-cfg1-595:amd64              595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA binary OpenGL/GLX configuration library
ii  libnvidia-common-595                  595.71.05-0ubuntu0.24.04.1                       amd64        Shared files used by the NVIDIA libraries
ii  libnvidia-compute-595:amd64           595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA libcompute package
ii  libnvidia-decode-595:amd64            595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA Video Decoding runtime libraries
ii  libnvidia-egl-wayland1:amd64          1:1.1.13-1ubuntu0.1                              amd64        Wayland EGL External Platform library -- shared library
ii  libnvidia-encode-595:amd64            595.71.05-0ubuntu0.24.04.1                       amd64        NVENC Video Encoding runtime library
ii  libnvidia-extra-595:amd64             595.71.05-0ubuntu0.24.04.1                       amd64        Extra libraries for the NVIDIA driver
ii  libnvidia-fbc1-595:amd64              595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA OpenGL-based Framebuffer Capture runtime library
ii  libnvidia-gl-595:amd64                595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA OpenGL/GLX/EGL/GLES GLVND libraries and Vulkan ICD
ii  nvidia-compute-utils-595              595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA compute utilities
ii  nvidia-dkms-595-open                  595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA DKMS package (open kernel module)
ii  nvidia-driver-595-open                595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA driver (open kernel) metapackage
ii  nvidia-firmware-595-595.71.05         595.71.05-0ubuntu0.24.04.1                       amd64        Firmware files used by the kernel module
ii  nvidia-kernel-common-595              595.71.05-0ubuntu0.24.04.1                       amd64        Shared files used with the kernel module
ii  nvidia-kernel-source-595-open         595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA kernel source package
ii  nvidia-prime                          0.8.17.2                                         all          Tools to enable NVIDIA's Prime
ii  nvidia-settings                       510.47.03-0ubuntu4.24.04.1                       amd64        Tool for configuring the NVIDIA graphics driver
ii  nvidia-utils-595                      595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA driver support binaries
ii  screen-resolution-extra               0.18.3ubuntu0.24.04.1                            all          Extension for the nvidia-settings control panel
ii  xserver-xorg-video-nvidia-595         595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA binary Xorg driver

[exit=0]
```

### Manual NVIDIA/CUDA/container-toolkit packages after driver install

```console
$ apt-mark showmanual | egrep 'nvidia|cuda|container-toolkit' || true
nvidia-driver-595-open
nvidia-utils-595

[exit=0]
```

### nouveau blacklist and module configuration references

```console
$ grep -RIn 'nouveau' /etc/modprobe.d /lib/modprobe.d 2>/dev/null || true
/lib/modprobe.d/nvidia-graphics-drivers.conf:1:blacklist nouveau
/lib/modprobe.d/nvidia-graphics-drivers.conf:2:blacklist lbm-nouveau
/lib/modprobe.d/nvidia-graphics-drivers.conf:5:alias nouveau off
/lib/modprobe.d/nvidia-graphics-drivers.conf:6:alias lbm-nouveau off

[exit=0]
```

### nouveau entries in current initramfs

```console
$ lsinitramfs /boot/initrd.img-6.8.0-134-generic 2>/dev/null | grep -i nouveau | head || true

[exit=0]
```

### nvidia-smi before reboot

```console
$ command -v nvidia-smi || true; nvidia-smi || true
/usr/bin/nvidia-smi
NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver. Make sure that the latest NVIDIA driver is installed and running.


[exit=0]
```

### nvcc after driver install before reboot

```console
$ command -v nvcc || true; nvcc --version || true
bash: line 1: nvcc: command not found

[exit=0]
```

### Loaded GPU modules after install before reboot

```console
$ lsmod | egrep 'nvidia|nouveau|vfio' || true
nouveau              3096576  0
mxm_wmi                12288  1 nouveau
drm_gpuvm              45056  1 nouveau
drm_exec               12288  2 drm_gpuvm,nouveau
gpu_sched              61440  1 nouveau
drm_display_helper    237568  1 nouveau
i2c_algo_bit           16384  1 nouveau
video                  77824  1 nouveau
wmi                    28672  3 video,mxm_wmi,nouveau
drm_ttm_helper         12288  3 bochs,drm_vram_helper,nouveau
ttm                   110592  3 drm_vram_helper,drm_ttm_helper,nouveau

[exit=0]
```

## Pre-reboot Verification And Reboot Plan

- Timestamp: 2026-07-03T07:33:56+00:00

- Post-reboot runner: `/data/services/m5b-post-reboot/m5b-post-reboot-verify.sh`
- Post-reboot systemd service: `/etc/systemd/system/m5b-post-reboot-verify.service`
- Post-reboot log: `/data/logs/m5b-post-reboot-verify.log`
- Post-reboot status files: `/data/services/m5b-post-reboot/PASS` or `/data/services/m5b-post-reboot/STOP`
- Reboot command planned: `sudo -n systemctl reboot` for the guest VM only.
- Scope confirmation before reboot: no CUDA Toolkit, PyTorch, KTransformers, ik_llama, NVIDIA Container Toolkit, models, Docker NVIDIA runtime, Docker/containerd configuration, disk/fstab/mountpoint, or API exposure changes were intentionally made.

### post-reboot runner syntax check

```console
$ bash -n /data/services/m5b-post-reboot/m5b-post-reboot-verify.sh

[exit=0]
```

### require-data-mounted before reboot

```console
$ scripts/common/require-data-mounted.sh
PASS: /data is mounted and ready
- root source: /dev/mapper/ubuntu--vg-ubuntu--lv
- data source: /dev/sdb1
- data fstype: ext4
- data label: AI_DATA
- data UUID: 8daf56f1-5649-4163-9d87-919c2d271875

[exit=0]
```

### root-disk-guard before reboot

```console
$ scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md
PASS: root disk guard passed

[exit=0]
```

### Docker storage verifier before reboot

```console
$ scripts/docker/verify-docker-storage.sh

## Docker/containerd Storage Verification

- Timestamp: 2026-07-03T07:33:57+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m5b-nvidia-host-driver

### require /data mounted

```console
$ scripts/common/require-data-mounted.sh
PASS: /data is mounted and ready
- root source: /dev/mapper/ubuntu--vg-ubuntu--lv
- data source: /dev/sdb1
- data fstype: ext4
- data label: AI_DATA
- data UUID: 8daf56f1-5649-4163-9d87-919c2d271875

[exit=0]
```

### pre-verification root-disk guard

```console
$ scripts/common/root-disk-guard.sh
PASS: root disk guard passed

[exit=0]
```

### df -hT / /data

```console
$ df -hT / /data
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  8.9G  4.6G  66% /
/dev/sdb1                         ext4  2.0T  3.0M  1.9T   1% /data

[exit=0]
```

### /var/lib Docker/containerd size summary

| Path | MiB | Policy |
| --- | ---: | --- |
| `/var/lib/docker` | 0 | absent/empty/small or documented |
| `/var/lib/containerd` | 0 | absent/empty/small or documented |

### systemctl is-active containerd

```console
$ sudo -n systemctl is-active containerd
active

[exit=0]
```

### systemctl is-active docker

```console
$ sudo -n systemctl is-active docker
active

[exit=0]
```

### systemctl status containerd

```console
$ sudo -n systemctl status containerd --no-pager
● containerd.service - containerd container runtime
     Loaded: loaded (/usr/lib/systemd/system/containerd.service; enabled; preset: enabled)
     Active: active (running) since Fri 2026-07-03 07:24:43 UTC; 9min ago
       Docs: https://containerd.io
   Main PID: 2129 (containerd)
      Tasks: 24
     Memory: 76.3M (peak: 83.8M)
        CPU: 893ms
     CGroup: /system.slice/containerd.service
             └─2129 /usr/bin/containerd

Jul 03 07:24:43 llmserver containerd[2129]: time="2026-07-03T07:24:43.900864865Z" level=info msg="Start cni network conf syncer for default"
Jul 03 07:24:43 llmserver containerd[2129]: time="2026-07-03T07:24:43.900870473Z" level=info msg="Start streaming server"
Jul 03 07:24:43 llmserver containerd[2129]: time="2026-07-03T07:24:43.900879096Z" level=info msg="Registered namespace \"k8s.io\" with NRI"
Jul 03 07:24:43 llmserver containerd[2129]: time="2026-07-03T07:24:43.900884064Z" level=info msg="runtime interface starting up..."
Jul 03 07:24:43 llmserver containerd[2129]: time="2026-07-03T07:24:43.900888190Z" level=info msg="starting plugins..."
Jul 03 07:24:43 llmserver containerd[2129]: time="2026-07-03T07:24:43.900897193Z" level=info msg="Synchronizing NRI (plugin) with current runtime state"
Jul 03 07:24:43 llmserver containerd[2129]: time="2026-07-03T07:24:43.900925175Z" level=info msg=serving... address=/run/containerd/containerd.sock.ttrpc
Jul 03 07:24:43 llmserver containerd[2129]: time="2026-07-03T07:24:43.900959907Z" level=info msg=serving... address=/run/containerd/containerd.sock
Jul 03 07:24:43 llmserver containerd[2129]: time="2026-07-03T07:24:43.901745396Z" level=info msg="containerd successfully booted in 0.031051s"
Jul 03 07:24:43 llmserver systemd[1]: Started containerd.service - containerd container runtime.

[exit=0]
```

### systemctl status docker

```console
$ sudo -n systemctl status docker --no-pager
● docker.service - Docker Application Container Engine
     Loaded: loaded (/usr/lib/systemd/system/docker.service; enabled; preset: enabled)
     Active: active (running) since Fri 2026-07-03 07:24:45 UTC; 9min ago
TriggeredBy: ● docker.socket
       Docs: https://docs.docker.com
   Main PID: 2227 (dockerd)
      Tasks: 38
     Memory: 112.0M (peak: 122.3M)
        CPU: 441ms
     CGroup: /system.slice/docker.service
             └─2227 /usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock

Jul 03 07:24:45 llmserver dockerd[2227]: time="2026-07-03T07:24:45.613698621Z" level=info msg="Restoring containers: start."
Jul 03 07:24:45 llmserver dockerd[2227]: time="2026-07-03T07:24:45.638269340Z" level=info msg="Deleting nftables IPv4 rules" error="running nft: /dev/stdin:1:17-30: Error: Could not process rule: No such file or directory\ndelete table ip docker-bridges\n                ^^^^^^^^^^^^^^\n exit status 1"
Jul 03 07:24:45 llmserver dockerd[2227]: time="2026-07-03T07:24:45.646296468Z" level=info msg="Deleting nftables IPv6 rules" error="running nft: /dev/stdin:1:18-31: Error: Could not process rule: No such file or directory\ndelete table ip6 docker-bridges\n                 ^^^^^^^^^^^^^^\n exit status 1"
Jul 03 07:24:45 llmserver dockerd[2227]: time="2026-07-03T07:24:45.904016429Z" level=info msg="Loading containers: done."
Jul 03 07:24:45 llmserver dockerd[2227]: time="2026-07-03T07:24:45.909000610Z" level=info msg="Docker daemon" commit=8ec5ab3 containerd-snapshotter=true storage-driver=overlayfs version=29.6.1
Jul 03 07:24:45 llmserver dockerd[2227]: time="2026-07-03T07:24:45.909224757Z" level=info msg="Initializing buildkit"
Jul 03 07:24:45 llmserver dockerd[2227]: time="2026-07-03T07:24:45.992680058Z" level=info msg="Completed buildkit initialization"
Jul 03 07:24:45 llmserver dockerd[2227]: time="2026-07-03T07:24:45.994842554Z" level=info msg="Daemon has completed initialization"
Jul 03 07:24:45 llmserver dockerd[2227]: time="2026-07-03T07:24:45.994878498Z" level=info msg="API listen on /run/docker.sock"
Jul 03 07:24:45 llmserver systemd[1]: Started docker.service - Docker Application Container Engine.

[exit=0]
```

### sudo docker version

```console
$ sudo -n docker version
Client: Docker Engine - Community
 Version:           29.6.1
 API version:       1.55
 Go version:        go1.26.4
 Git commit:        8900f1d
 Built:             Fri Jun 26 11:40:19 2026
 OS/Arch:           linux/amd64
 Context:           default

Server: Docker Engine - Community
 Engine:
  Version:          29.6.1
  API version:      1.55 (minimum version 1.40)
  Go version:       go1.26.4
  Git commit:       8ec5ab3
  Built:            Fri Jun 26 11:40:19 2026
  OS/Arch:          linux/amd64
  Experimental:     false
 containerd:
  Version:          v2.2.5
  GitCommit:        e53c7c1516c3b2bff98eb76f1f4117477e6f4e66
 runc:
  Version:          1.3.6
  GitCommit:        v1.3.6-0-g491b69ba
 docker-init:
  Version:          0.19.0
  GitCommit:        de40ad0

[exit=0]
```

### sudo docker info

```console
$ sudo -n docker info
Client: Docker Engine - Community
 Version:    29.6.1
 Context:    default
 Debug Mode: false
 Plugins:
  buildx: Docker Buildx (Docker Inc.)
    Version:  v0.35.0
    Path:     /usr/libexec/docker/cli-plugins/docker-buildx
  compose: Docker Compose (Docker Inc.)
    Version:  v5.3.0
    Path:     /usr/libexec/docker/cli-plugins/docker-compose

Server:
 Containers: 0
  Running: 0
  Paused: 0
  Stopped: 0
 Images: 1
 Server Version: 29.6.1
 Storage Driver: overlayfs
  driver-type: io.containerd.snapshotter.v1
 Logging Driver: json-file
 Cgroup Driver: systemd
 Cgroup Version: 2
 Plugins:
  Volume: local
  Network: bridge host ipvlan macvlan null overlay
  Log: awslogs fluentd gcplogs gelf journald json-file local splunk syslog
 CDI spec directories:
  /etc/cdi
  /var/run/cdi
 Swarm: inactive
 Runtimes: runc io.containerd.runc.v2
 Default Runtime: runc
 Init Binary: docker-init
 containerd version: e53c7c1516c3b2bff98eb76f1f4117477e6f4e66
 runc version: v1.3.6-0-g491b69ba
 init version: de40ad0
 Security Options:
  apparmor
  seccomp
   Profile: builtin
  cgroupns
 Kernel Version: 6.8.0-134-generic
 Operating System: Ubuntu 24.04.4 LTS
 OSType: linux
 Architecture: x86_64
 CPUs: 112
 Total Memory: 881.8GiB
 Name: llmserver
 ID: fba62709-52b6-4594-98a7-b3a7e2626f3b
 Docker Root Dir: /data/docker
 Debug Mode: false
 Experimental: false
 Insecure Registries:
  ::1/128
  127.0.0.0/8
 Live Restore Enabled: false
 Firewall Backend: iptables
  EnableUserlandProxy: true
  UserlandProxyPath: /usr/bin/docker-proxy


[exit=0]
```

### sudo docker compose version

```console
$ sudo -n docker compose version
Docker Compose version v5.3.0

[exit=0]
```

### sudo docker buildx version

```console
$ sudo -n docker buildx version
github.com/docker/buildx v0.35.0 a319e5b15052cf6557ceb666eb8ff6e32380b782

[exit=0]
```

### hello-world image inspect

```console
$ sudo -n docker image inspect hello-world:latest
[
    {
        "Id": "sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d",
        "RepoTags": [
            "hello-world:latest"
        ],
        "RepoDigests": [
            "hello-world@sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d"
        ],
        "Comment": "buildkit.dockerfile.v0",
        "Created": "2026-03-23T21:33:59.562202219Z",
        "Config": {
            "Env": [
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            ],
            "Cmd": [
                "/hello"
            ],
            "WorkingDir": "/"
        },
        "Architecture": "amd64",
        "Os": "linux",
        "Size": 16227,
        "RootFS": {
            "Type": "layers",
            "Layers": [
                "sha256:897b3f2a7c1bc2f3d02432f7892fe31c6272c521ad4d70257df624504a3238b4"
            ]
        },
        "Metadata": {
            "LastTagTime": "2026-07-02T19:39:50.349224487Z"
        },
        "Descriptor": {
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "digest": "sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d",
            "size": 12212
        },
        "Identity": {
            "Pull": [
                {
                    "Repository": "docker.io/library/hello-world"
                }
            ]
        }
    }
]

[exit=0]
```

### sudo docker system df

```console
$ sudo -n docker system df
TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          1         0         38.09kB   25.87kB (67%)
Containers      0         0         0B        0B
Local Volumes   0         0         0B        0B
Build Cache     0         0         0B        0B

[exit=0]
```

### Docker/containerd root and data sizes

```console
$ sudo -n du -sh /var/lib/docker /var/lib/containerd '/data/docker' '/data/containerd' '/data/containerd/root' 2>/dev/null || true
236K	/data/docker
336K	/data/containerd

[exit=0]
```

### post-verification root-disk guard

```console
$ scripts/common/root-disk-guard.sh
PASS: root disk guard passed

[exit=0]
```

## Docker/containerd Verification Summary

- Docker installed: yes
- containerd installed: yes
- Docker Root Dir: /data/docker
- containerd root: /data/containerd/root
- containerd state: /run/containerd
- hello-world image present: yes
- root-disk guard: PASS

## Docker/containerd Verification Conclusion

PASS
PASS: Docker/containerd storage verified

[exit=0]
```

### No forbidden CUDA Toolkit or NVIDIA Container Toolkit packages before reboot

```console
$ dpkg-query -W -f='${binary:Package}\n' | grep -E '^(cuda|cuda-toolkit(-.*)?|cuda-drivers(-.*)?|nvidia-cuda-toolkit|nvidia-container-toolkit|nvidia-container-runtime)$' || true

[exit=0]
```

### nvidia-smi and nvcc before reboot

```console
$ command -v nvidia-smi || true; nvidia-smi || true; command -v nvcc || true; nvcc --version || true
/usr/bin/nvidia-smi
NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver. Make sure that the latest NVIDIA driver is installed and running.

bash: line 1: nvcc: command not found

[exit=0]
```

## Pre-reboot Git Checks

- Timestamp: 2026-07-03T07:34:26+00:00

### git remote -v

```console
origin	git@github.com:djeZo888/mixed-memory-llm-api-server.git (fetch)
origin	git@github.com:djeZo888/mixed-memory-llm-api-server.git (push)
```

### git diff --check

```console
[exit=0]
```

### grep-based secret scan

```console
./tests/shell/test-prepare-data-disk-static.sh:36:if grep -RInE '(BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY|HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,})' "$PREPARE" "$VERIFY"; then
./tests/shell/test-root-disk-guard-static.sh:52:if grep -RInE '(BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY|HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,})' "$ROOT_GUARD" "$REQUIRE_DATA"; then
./tests/shell/test-docker-scripts-static.sh:50:if grep -RInE 'usermod[[:space:]].*docker|gpasswd[[:space:]].*docker|groupadd[[:space:]].*docker' "${scripts[@]}"; then
./tests/shell/test-docker-scripts-static.sh:58:if grep -RInE '(BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY|HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,})' "${scripts[@]}"; then
./scripts/preflight/disk-dry-run.sh:38:    -e 's/(HF_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/preflight/disk-dry-run.sh:39:    -e 's/(OPENAI_API_KEY=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/preflight/disk-dry-run.sh:40:    -e 's/(GITHUB_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/preflight/disk-dry-run.sh:42:    -e 's/((password|passwd)[=:][[:space:]]*)[^[:space:]]+/\1[REDACTED]/Ig' \
./scripts/preflight/disk-dry-run.sh:123:if git remote -v 2>/dev/null | grep -Eq '(://[^[:space:]]*:[^[:space:]@]*@|token|password|passwd|GITHUB_TOKEN)'; then
./scripts/preflight/disk-dry-run.sh:149:Reason for STOP: sudo -n true failed after sudo -k. No password was requested or read.
./scripts/preflight/vm-preflight.sh:33:- never prompts for a sudo password
./scripts/preflight/vm-preflight.sh:51:    -e 's/(HF_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/preflight/vm-preflight.sh:52:    -e 's/(OPENAI_API_KEY=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/preflight/vm-preflight.sh:53:    -e 's/(GITHUB_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/preflight/vm-preflight.sh:55:    -e 's/((password|passwd)[=:][[:space:]]*)[^[:space:]]+/\1[REDACTED]/Ig' \
./scripts/preflight/vm-preflight.sh:113:  git remote -v 2>/dev/null | grep -Eq '(://[^[:space:]]*:[^[:space:]@]*@|token|password|passwd|GITHUB_TOKEN)'
./scripts/preflight/vm-preflight.sh:352:- No secrets, tokens, passwords, private keys, auth files, real .env files, MEMORY.md, or local Codex memory files were read or written.
./scripts/storage/prepare-data-disk.sh:58:    -e 's/(HF_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/storage/prepare-data-disk.sh:59:    -e 's/(OPENAI_API_KEY=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/storage/prepare-data-disk.sh:60:    -e 's/(GITHUB_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/storage/prepare-data-disk.sh:62:    -e 's/((password|passwd)[=:][[:space:]]*)[^[:space:]]+/\1[REDACTED]/Ig' \
./scripts/storage/prepare-data-disk.sh:206:  if git remote -v 2>/dev/null | grep -Eq '(://[^[:space:]]*:[^[:space:]@]*@|token|password|passwd|GITHUB_TOKEN)'; then
./scripts/storage/verify-data-mount.sh:41:    -e 's/(HF_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/storage/verify-data-mount.sh:42:    -e 's/(OPENAI_API_KEY=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/storage/verify-data-mount.sh:43:    -e 's/(GITHUB_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/storage/verify-data-mount.sh:45:    -e 's/((password|passwd)[=:][[:space:]]*)[^[:space:]]+/\1[REDACTED]/Ig' \
./scripts/common/root-disk-guard.sh:524:      -name auth.json -o \
./AGENTS.md:32:- Do not commit real `.env` files, tokens, passwords, private keys, API keys, Hugging Face tokens, GitHub tokens, SSH keys, sudo files, auth files, model weights, or service secrets.
./.github/workflows/ci.yml:49:          forbidden=$(find . -path ./.git -prune -o \( -name .env -o -name '*.key' -o -name '*.pem' -o -name auth.json -o -name MEMORY.md \) -print)
./.github/ISSUE_TEMPLATE/bug_report.yml:9:      value: Do not include secrets, tokens, private keys, passwords, or model weights.
./.github/ISSUE_TEMPLATE/hardware_report.yml:9:      value: Do not include secrets, tokens, private keys, passwords, public IPs, or model weights.
./.gitignore:15:auth.json
./SECURITY.md:9:Do not commit secrets, tokens, passwords, SSH keys, API keys, sudo files, real `.env` files, Hugging Face tokens, GitHub tokens, auth files, model weights, or `/data/services/secrets` contents.
./reports/m3-main-merge.md:35:The grep-based secret scan matched only intentional documentation, test, sanitizer, `.gitignore`, CI, and prior report command strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m4b-main-merge.md:47:The grep-based secret scan matched only intentional documentation, sanitizer, static-test, `.gitignore`, CI, and prior report strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m4a-docker-containerd-plan.md:114:The grep-based secret scan found only intentional documentation, static-test, sanitizer, `.gitignore`, CI, and prior report command strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m5a-cuda-nvidia-compatibility.md:339:The grep-based secret scan matched only intentional documentation, safety rules, examples, and scan pattern text. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were found.
./reports/m5a-main-merge.md:116:The grep-based secret scan matched only intentional documentation, test, sanitizer, `.gitignore`, CI, and prior report strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m4b-docker-permission-policy.md:72:The grep-based secret scan matched only intentional documentation, sanitizer, static-test, `.gitignore`, CI, and prior report strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m4a-main-merge.md:36:The grep-based secret scan matched only intentional documentation, test, sanitizer, `.gitignore`, CI, and prior report command strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m4b-docker-containerd-install.md:975:- Grep-based secret scan: matched only intentional documentation, static-test, sanitizer, `.gitignore`, CI, and prior report command strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m1-vm-preflight.md:512:- No secrets, tokens, passwords, private keys, auth files, real .env files, MEMORY.md, or local Codex memory files were read or written.
./reports/m2-main-merge.md:31:grep -RInE "(HF_TOKEN|OPENAI_API_KEY|GITHUB_TOKEN|password|passwd|PRIVATE KEY|BEGIN OPENSSH|BEGIN RSA|auth.json|ai-vm.sudo)" . --exclude-dir=.git || true
```

The grep-based secret scan matched only intentional documentation, safety rules, examples, sanitizer/static-test code, prior report text, and the scan pattern itself. No real secrets, tokens, passwords, private keys, auth files, real .env files, MEMORY.md, or local Codex memory files were identified.


# M5B post-reboot NVIDIA driver verification

- Timestamp: 2026-07-03T07:35:52+00:00
- Hostname: llmserver
- Uptime: up 0 minutes
- Runner: /data/services/m5b-post-reboot/m5b-post-reboot-verify.sh
- Log: /data/logs/m5b-post-reboot-verify.log

### hostname

```console
$ hostname
llmserver

[exit=0]
```

### uptime

```console
$ uptime
 07:35:52 up 0 min,  3 users,  load average: 0.43, 0.12, 0.04

[exit=0]
```

### date -Is

```console
$ date -Is
2026-07-03T07:35:52+00:00

[exit=0]
```

### require-data-mounted

```console
$ scripts/common/require-data-mounted.sh
PASS: /data is mounted and ready
- root source: /dev/mapper/ubuntu--vg-ubuntu--lv
- data source: /dev/sdb1
- data fstype: ext4
- data label: AI_DATA
- data UUID: 8daf56f1-5649-4163-9d87-919c2d271875

[exit=0]
```

### root-disk-guard

```console
$ scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md
PASS: root disk guard passed

[exit=0]
```


## Docker/containerd Storage Verification

- Timestamp: 2026-07-03T07:35:53+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m5b-nvidia-host-driver

### require /data mounted

```console
$ scripts/common/require-data-mounted.sh
PASS: /data is mounted and ready
- root source: /dev/mapper/ubuntu--vg-ubuntu--lv
- data source: /dev/sdb1
- data fstype: ext4
- data label: AI_DATA
- data UUID: 8daf56f1-5649-4163-9d87-919c2d271875

[exit=0]
```

### pre-verification root-disk guard

```console
$ scripts/common/root-disk-guard.sh
PASS: root disk guard passed

[exit=0]
```

### df -hT / /data

```console
$ df -hT / /data
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  8.9G  4.6G  66% /
/dev/sdb1                         ext4  2.0T  3.2M  1.9T   1% /data

[exit=0]
```

### /var/lib Docker/containerd size summary

| Path | MiB | Policy |
| --- | ---: | --- |
| `/var/lib/docker` | 0 | absent/empty/small or documented |
| `/var/lib/containerd` | 0 | absent/empty/small or documented |

### systemctl is-active containerd

```console
$ sudo -n systemctl is-active containerd
active

[exit=0]
```

### systemctl is-active docker

```console
$ sudo -n systemctl is-active docker
active

[exit=0]
```

### systemctl status containerd

```console
$ sudo -n systemctl status containerd --no-pager
● containerd.service - containerd container runtime
     Loaded: loaded (/usr/lib/systemd/system/containerd.service; enabled; preset: enabled)
     Active: active (running) since Fri 2026-07-03 07:35:25 UTC; 28s ago
       Docs: https://containerd.io
   Main PID: 2091 (containerd)
      Tasks: 21
     Memory: 75.6M (peak: 82.4M)
        CPU: 128ms
     CGroup: /system.slice/containerd.service
             └─2091 /usr/bin/containerd

Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875859853Z" level=info msg="Start cni network conf syncer for default"
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875865272Z" level=info msg="Start streaming server"
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875873444Z" level=info msg="Registered namespace \"k8s.io\" with NRI"
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875878251Z" level=info msg="runtime interface starting up..."
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875881666Z" level=info msg="starting plugins..."
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875890109Z" level=info msg="Synchronizing NRI (plugin) with current runtime state"
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875902768Z" level=info msg=serving... address=/run/containerd/containerd.sock.ttrpc
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875941546Z" level=info msg=serving... address=/run/containerd/containerd.sock
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.876173504Z" level=info msg="containerd successfully booted in 0.033839s"
Jul 03 07:35:25 llmserver systemd[1]: Started containerd.service - containerd container runtime.

[exit=0]
```

### systemctl status docker

```console
$ sudo -n systemctl status docker --no-pager
● docker.service - Docker Application Container Engine
     Loaded: loaded (/usr/lib/systemd/system/docker.service; enabled; preset: enabled)
     Active: active (running) since Fri 2026-07-03 07:35:28 UTC; 25s ago
TriggeredBy: ● docker.socket
       Docs: https://docs.docker.com
   Main PID: 2261 (dockerd)
      Tasks: 39
     Memory: 112.6M (peak: 119.6M)
        CPU: 382ms
     CGroup: /system.slice/docker.service
             └─2261 /usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock

Jul 03 07:35:27 llmserver dockerd[2261]: time="2026-07-03T07:35:27.673114630Z" level=info msg="Restoring containers: start."
Jul 03 07:35:27 llmserver dockerd[2261]: time="2026-07-03T07:35:27.775998332Z" level=info msg="Deleting nftables IPv4 rules" error="running nft: /dev/stdin:1:17-30: Error: Could not process rule: No such file or directory\ndelete table ip docker-bridges\n                ^^^^^^^^^^^^^^\n exit status 1"
Jul 03 07:35:27 llmserver dockerd[2261]: time="2026-07-03T07:35:27.788141528Z" level=info msg="Deleting nftables IPv6 rules" error="running nft: /dev/stdin:1:18-31: Error: Could not process rule: No such file or directory\ndelete table ip6 docker-bridges\n                 ^^^^^^^^^^^^^^\n exit status 1"
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.052444560Z" level=info msg="Loading containers: done."
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.058049123Z" level=info msg="Docker daemon" commit=8ec5ab3 containerd-snapshotter=true storage-driver=overlayfs version=29.6.1
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.058280870Z" level=info msg="Initializing buildkit"
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.220160582Z" level=info msg="Completed buildkit initialization"
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.224043800Z" level=info msg="Daemon has completed initialization"
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.224122648Z" level=info msg="API listen on /run/docker.sock"
Jul 03 07:35:28 llmserver systemd[1]: Started docker.service - Docker Application Container Engine.

[exit=0]
```

### sudo docker version

```console
$ sudo -n docker version
Client: Docker Engine - Community
 Version:           29.6.1
 API version:       1.55
 Go version:        go1.26.4
 Git commit:        8900f1d
 Built:             Fri Jun 26 11:40:19 2026
 OS/Arch:           linux/amd64
 Context:           default

Server: Docker Engine - Community
 Engine:
  Version:          29.6.1
  API version:      1.55 (minimum version 1.40)
  Go version:       go1.26.4
  Git commit:       8ec5ab3
  Built:            Fri Jun 26 11:40:19 2026
  OS/Arch:          linux/amd64
  Experimental:     false
 containerd:
  Version:          v2.2.5
  GitCommit:        e53c7c1516c3b2bff98eb76f1f4117477e6f4e66
 runc:
  Version:          1.3.6
  GitCommit:        v1.3.6-0-g491b69ba
 docker-init:
  Version:          0.19.0
  GitCommit:        de40ad0

[exit=0]
```

### sudo docker info

```console
$ sudo -n docker info
Client: Docker Engine - Community
 Version:    29.6.1
 Context:    default
 Debug Mode: false
 Plugins:
  buildx: Docker Buildx (Docker Inc.)
    Version:  v0.35.0
    Path:     /usr/libexec/docker/cli-plugins/docker-buildx
  compose: Docker Compose (Docker Inc.)
    Version:  v5.3.0
    Path:     /usr/libexec/docker/cli-plugins/docker-compose

Server:
 Containers: 0
  Running: 0
  Paused: 0
  Stopped: 0
 Images: 1
 Server Version: 29.6.1
 Storage Driver: overlayfs
  driver-type: io.containerd.snapshotter.v1
 Logging Driver: json-file
 Cgroup Driver: systemd
 Cgroup Version: 2
 Plugins:
  Volume: local
  Network: bridge host ipvlan macvlan null overlay
  Log: awslogs fluentd gcplogs gelf journald json-file local splunk syslog
 CDI spec directories:
  /etc/cdi
  /var/run/cdi
 Swarm: inactive
 Runtimes: io.containerd.runc.v2 runc
 Default Runtime: runc
 Init Binary: docker-init
 containerd version: e53c7c1516c3b2bff98eb76f1f4117477e6f4e66
 runc version: v1.3.6-0-g491b69ba
 init version: de40ad0
 Security Options:
  apparmor
  seccomp
   Profile: builtin
  cgroupns
 Kernel Version: 6.8.0-134-generic
 Operating System: Ubuntu 24.04.4 LTS
 OSType: linux
 Architecture: x86_64
 CPUs: 112
 Total Memory: 881.8GiB
 Name: llmserver
 ID: fba62709-52b6-4594-98a7-b3a7e2626f3b
 Docker Root Dir: /data/docker
 Debug Mode: false
 Experimental: false
 Insecure Registries:
  ::1/128
  127.0.0.0/8
 Live Restore Enabled: false
 Firewall Backend: iptables
  EnableUserlandProxy: true
  UserlandProxyPath: /usr/bin/docker-proxy


[exit=0]
```

### sudo docker compose version

```console
$ sudo -n docker compose version
Docker Compose version v5.3.0

[exit=0]
```

### sudo docker buildx version

```console
$ sudo -n docker buildx version
github.com/docker/buildx v0.35.0 a319e5b15052cf6557ceb666eb8ff6e32380b782

[exit=0]
```

### hello-world image inspect

```console
$ sudo -n docker image inspect hello-world:latest
[
    {
        "Id": "sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d",
        "RepoTags": [
            "hello-world:latest"
        ],
        "RepoDigests": [
            "hello-world@sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d"
        ],
        "Comment": "buildkit.dockerfile.v0",
        "Created": "2026-03-23T21:33:59.562202219Z",
        "Config": {
            "Env": [
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            ],
            "Cmd": [
                "/hello"
            ],
            "WorkingDir": "/"
        },
        "Architecture": "amd64",
        "Os": "linux",
        "Size": 16227,
        "RootFS": {
            "Type": "layers",
            "Layers": [
                "sha256:897b3f2a7c1bc2f3d02432f7892fe31c6272c521ad4d70257df624504a3238b4"
            ]
        },
        "Metadata": {
            "LastTagTime": "2026-07-02T19:39:50.349224487Z"
        },
        "Descriptor": {
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "digest": "sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d",
            "size": 12212
        },
        "Identity": {
            "Pull": [
                {
                    "Repository": "docker.io/library/hello-world"
                }
            ]
        }
    }
]

[exit=0]
```

### sudo docker system df

```console
$ sudo -n docker system df
TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          1         0         38.09kB   25.87kB (67%)
Containers      0         0         0B        0B
Local Volumes   0         0         0B        0B
Build Cache     0         0         0B        0B

[exit=0]
```

### Docker/containerd root and data sizes

```console
$ sudo -n du -sh /var/lib/docker /var/lib/containerd '/data/docker' '/data/containerd' '/data/containerd/root' 2>/dev/null || true
236K	/data/docker
336K	/data/containerd

[exit=0]
```

### post-verification root-disk guard

```console
$ scripts/common/root-disk-guard.sh
PASS: root disk guard passed

[exit=0]
```

## Docker/containerd Verification Summary

- Docker installed: yes
- containerd installed: yes
- Docker Root Dir: /data/docker
- containerd root: /data/containerd/root
- containerd state: /run/containerd
- hello-world image present: yes
- root-disk guard: PASS

## Docker/containerd Verification Conclusion

PASS
### Docker storage verifier

```console
$ scripts/docker/verify-docker-storage.sh
PASS: Docker/containerd storage verified

[exit=0]
```

### os-release

```console
$ cat /etc/os-release
PRETTY_NAME="Ubuntu 24.04.4 LTS"
NAME="Ubuntu"
VERSION_ID="24.04"
VERSION="24.04.4 LTS (Noble Numbat)"
VERSION_CODENAME=noble
ID=ubuntu
ID_LIKE=debian
HOME_URL="https://www.ubuntu.com/"
SUPPORT_URL="https://help.ubuntu.com/"
BUG_REPORT_URL="https://bugs.launchpad.net/ubuntu/"
PRIVACY_POLICY_URL="https://www.ubuntu.com/legal/terms-and-policies/privacy-policy"
UBUNTU_CODENAME=noble
LOGO=ubuntu-logo

[exit=0]
```

### uname -a

```console
$ uname -a
Linux llmserver 6.8.0-134-generic #134-Ubuntu SMP PREEMPT_DYNAMIC Fri Jun 26 18:43:11 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux

[exit=0]
```

### lspci NVIDIA/display inventory

```console
$ lspci -nn | egrep -i 'nvidia|vga|3d|display' || true
00:01.0 VGA compatible controller [0300]: Device [1234:1111] (rev 02)
01:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
01:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)
02:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
02:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)

[exit=0]
```

### lspci driver binding summary

```console
$ lspci -nnk | egrep -A5 -i 'nvidia|vga|3d|display' || true
00:01.0 VGA compatible controller [0300]: Device [1234:1111] (rev 02)
	Subsystem: Red Hat, Inc. Device [1af4:1100]
	Kernel driver in use: bochs-drm
	Kernel modules: bochs
00:1a.0 USB controller [0c03]: Intel Corporation 82801I (ICH9 Family) USB UHCI Controller #4 [8086:2937] (rev 03)
	Subsystem: Red Hat, Inc. QEMU Virtual Machine [1af4:1100]
--
01:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
	Subsystem: NVIDIA Corporation Device [10de:204b]
	Kernel driver in use: nvidia
	Kernel modules: nvidiafb, nouveau, nvidia_drm, nvidia
01:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)
	Subsystem: NVIDIA Corporation Device [10de:0000]
	Kernel driver in use: snd_hda_intel
	Kernel modules: snd_hda_intel
02:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
	Subsystem: NVIDIA Corporation Device [10de:204b]
	Kernel driver in use: nvidia
	Kernel modules: nvidiafb, nouveau, nvidia_drm, nvidia
02:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)
	Subsystem: NVIDIA Corporation Device [10de:0000]
	Kernel driver in use: snd_hda_intel
	Kernel modules: snd_hda_intel
05:01.0 PCI bridge [0604]: Red Hat, Inc. QEMU PCI-PCI bridge [1b36:0001]
05:02.0 PCI bridge [0604]: Red Hat, Inc. QEMU PCI-PCI bridge [1b36:0001]
05:03.0 PCI bridge [0604]: Red Hat, Inc. QEMU PCI-PCI bridge [1b36:0001]

[exit=0]
```

### lsmod nvidia/nouveau/vfio summary

```console
$ lsmod | egrep 'nvidia|nouveau|vfio' || true
nvidia_uvm           2060288  0
nvidia_drm            139264  0
nvidia_modeset       1744896  1 nvidia_drm
nvidia              14794752  2 nvidia_uvm,nvidia_modeset
video                  77824  1 nvidia_modeset
ecc                    45056  1 nvidia

[exit=0]
```

### command -v nvidia-smi

```console
$ command -v nvidia-smi
/usr/bin/nvidia-smi

[exit=0]
```

### nvidia-smi

```console
$ nvidia-smi
Fri Jul  3 07:35:55 2026
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 595.71.05              Driver Version: 595.71.05      CUDA Version: 13.2     |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA RTX PRO 6000 Blac...    Off |   00000000:01:00.0 Off |                  Off |
| 30%   35C    P8             15W /  600W |       2MiB /  97887MiB |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+
|   1  NVIDIA RTX PRO 6000 Blac...    Off |   00000000:02:00.0 Off |                  Off |
| 30%   41C    P8             33W /  600W |      34MiB /  97887MiB |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+

+-----------------------------------------------------------------------------------------+
| Processes:                                                                              |
|  GPU   GI   CI              PID   Type   Process name                        GPU Memory |
|        ID   ID                                                               Usage      |
|=========================================================================================|
|  No running processes found                                                             |
+-----------------------------------------------------------------------------------------+

[exit=0]
```

### nvidia-smi -L

```console
$ nvidia-smi -L
GPU 0: NVIDIA RTX PRO 6000 Blackwell Workstation Edition (UUID: GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237)
GPU 1: NVIDIA RTX PRO 6000 Blackwell Workstation Edition (UUID: GPU-69acfa26-8b60-61b5-702d-aee252c163cc)

[exit=0]
```

### nvidia-smi query-gpu CSV

```console
$ nvidia-smi --query-gpu=index\,name\,pci.bus_id\,driver_version\,memory.total\,power.limit --format=csv
index, name, pci.bus_id, driver_version, memory.total [MiB], power.limit [W]
0, NVIDIA RTX PRO 6000 Blackwell Workstation Edition, 00000000:01:00.0, 595.71.05, 97887 MiB, 600.00 W
1, NVIDIA RTX PRO 6000 Blackwell Workstation Edition, 00000000:02:00.0, 595.71.05, 97887 MiB, 600.00 W

[exit=0]
```

### nvidia-smi topology

```console
$ nvidia-smi topo -m
	[4mGPU0	GPU1	CPU Affinity	NUMA Affinity	GPU NUMA ID[0m
GPU0	 X 	PHB	0-111	0-6		N/A
GPU1	PHB	 X 	0-111	0-6		N/A

Legend:

  X    = Self
  SYS  = Connection traversing PCIe as well as the SMP interconnect between NUMA nodes (e.g., QPI/UPI)
  NODE = Connection traversing PCIe as well as the interconnect between PCIe Host Bridges within a NUMA node
  PHB  = Connection traversing PCIe as well as a PCIe Host Bridge (typically the CPU)
  PXB  = Connection traversing multiple PCIe bridges (without traversing the PCIe Host Bridge)
  PIX  = Connection traversing at most a single PCIe bridge
  NV#  = Connection traversing a bonded set of # NVLinks

[exit=0]
```

### nvidia-smi memory PCI power detail

```console
$ nvidia-smi -q -d MEMORY\,PCI\,POWER
Failed to parse --display/-d flags

[exit=2]
```

## M5B Post-reboot Conclusion

STOP

Reason: nvidia-smi detail query failed

Manual Proxmox VFIO/AER/reset checks are still required outside Codex.

## Post-reboot verifier retry note

The first post-reboot verifier run stopped because NVIDIA-SMI 595 rejects `PCI` as a `-d/--display` flag. Manual inspection confirmed `nvidia-smi`, `nvidia-smi -L`, query-gpu CSV, memory detail, and power detail work. The verifier was rerun with the original `MEMORY,PCI,POWER` command recorded as non-fatal and with `nvidia-smi -q`, `nvidia-smi -q -d MEMORY`, and `nvidia-smi -q -d POWER` used for PCI, memory, and power evidence.

# M5B post-reboot NVIDIA driver verification

- Timestamp: 2026-07-03T07:37:25+00:00
- Hostname: llmserver
- Uptime: up 2 minutes
- Runner: /data/services/m5b-post-reboot/m5b-post-reboot-verify.sh
- Log: /data/logs/m5b-post-reboot-verify.log

### hostname

```console
$ hostname
llmserver

[exit=0]
```

### uptime

```console
$ uptime
 07:37:25 up 2 min,  3 users,  load average: 0.11, 0.10, 0.04

[exit=0]
```

### date -Is

```console
$ date -Is
2026-07-03T07:37:25+00:00

[exit=0]
```

### require-data-mounted

```console
$ scripts/common/require-data-mounted.sh
PASS: /data is mounted and ready
- root source: /dev/mapper/ubuntu--vg-ubuntu--lv
- data source: /dev/sdb1
- data fstype: ext4
- data label: AI_DATA
- data UUID: 8daf56f1-5649-4163-9d87-919c2d271875

[exit=0]
```

### root-disk-guard

```console
$ scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md
PASS: root disk guard passed

[exit=0]
```


## Docker/containerd Storage Verification

- Timestamp: 2026-07-03T07:37:26+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m5b-nvidia-host-driver

### require /data mounted

```console
$ scripts/common/require-data-mounted.sh
PASS: /data is mounted and ready
- root source: /dev/mapper/ubuntu--vg-ubuntu--lv
- data source: /dev/sdb1
- data fstype: ext4
- data label: AI_DATA
- data UUID: 8daf56f1-5649-4163-9d87-919c2d271875

[exit=0]
```

### pre-verification root-disk guard

```console
$ scripts/common/root-disk-guard.sh
PASS: root disk guard passed

[exit=0]
```

### df -hT / /data

```console
$ df -hT / /data
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  8.9G  4.6G  66% /
/dev/sdb1                         ext4  2.0T  3.2M  1.9T   1% /data

[exit=0]
```

### /var/lib Docker/containerd size summary

| Path | MiB | Policy |
| --- | ---: | --- |
| `/var/lib/docker` | 0 | absent/empty/small or documented |
| `/var/lib/containerd` | 0 | absent/empty/small or documented |

### systemctl is-active containerd

```console
$ sudo -n systemctl is-active containerd
active

[exit=0]
```

### systemctl is-active docker

```console
$ sudo -n systemctl is-active docker
active

[exit=0]
```

### systemctl status containerd

```console
$ sudo -n systemctl status containerd --no-pager
● containerd.service - containerd container runtime
     Loaded: loaded (/usr/lib/systemd/system/containerd.service; enabled; preset: enabled)
     Active: active (running) since Fri 2026-07-03 07:35:25 UTC; 2min 1s ago
       Docs: https://containerd.io
   Main PID: 2091 (containerd)
      Tasks: 30
     Memory: 79.6M (peak: 86.7M)
        CPU: 348ms
     CGroup: /system.slice/containerd.service
             └─2091 /usr/bin/containerd

Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875859853Z" level=info msg="Start cni network conf syncer for default"
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875865272Z" level=info msg="Start streaming server"
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875873444Z" level=info msg="Registered namespace \"k8s.io\" with NRI"
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875878251Z" level=info msg="runtime interface starting up..."
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875881666Z" level=info msg="starting plugins..."
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875890109Z" level=info msg="Synchronizing NRI (plugin) with current runtime state"
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875902768Z" level=info msg=serving... address=/run/containerd/containerd.sock.ttrpc
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875941546Z" level=info msg=serving... address=/run/containerd/containerd.sock
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.876173504Z" level=info msg="containerd successfully booted in 0.033839s"
Jul 03 07:35:25 llmserver systemd[1]: Started containerd.service - containerd container runtime.

[exit=0]
```

### systemctl status docker

```console
$ sudo -n systemctl status docker --no-pager
● docker.service - Docker Application Container Engine
     Loaded: loaded (/usr/lib/systemd/system/docker.service; enabled; preset: enabled)
     Active: active (running) since Fri 2026-07-03 07:35:28 UTC; 1min 59s ago
TriggeredBy: ● docker.socket
       Docs: https://docs.docker.com
   Main PID: 2261 (dockerd)
      Tasks: 39
     Memory: 115.2M (peak: 119.7M)
        CPU: 449ms
     CGroup: /system.slice/docker.service
             └─2261 /usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock

Jul 03 07:35:27 llmserver dockerd[2261]: time="2026-07-03T07:35:27.673114630Z" level=info msg="Restoring containers: start."
Jul 03 07:35:27 llmserver dockerd[2261]: time="2026-07-03T07:35:27.775998332Z" level=info msg="Deleting nftables IPv4 rules" error="running nft: /dev/stdin:1:17-30: Error: Could not process rule: No such file or directory\ndelete table ip docker-bridges\n                ^^^^^^^^^^^^^^\n exit status 1"
Jul 03 07:35:27 llmserver dockerd[2261]: time="2026-07-03T07:35:27.788141528Z" level=info msg="Deleting nftables IPv6 rules" error="running nft: /dev/stdin:1:18-31: Error: Could not process rule: No such file or directory\ndelete table ip6 docker-bridges\n                 ^^^^^^^^^^^^^^\n exit status 1"
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.052444560Z" level=info msg="Loading containers: done."
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.058049123Z" level=info msg="Docker daemon" commit=8ec5ab3 containerd-snapshotter=true storage-driver=overlayfs version=29.6.1
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.058280870Z" level=info msg="Initializing buildkit"
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.220160582Z" level=info msg="Completed buildkit initialization"
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.224043800Z" level=info msg="Daemon has completed initialization"
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.224122648Z" level=info msg="API listen on /run/docker.sock"
Jul 03 07:35:28 llmserver systemd[1]: Started docker.service - Docker Application Container Engine.

[exit=0]
```

### sudo docker version

```console
$ sudo -n docker version
Client: Docker Engine - Community
 Version:           29.6.1
 API version:       1.55
 Go version:        go1.26.4
 Git commit:        8900f1d
 Built:             Fri Jun 26 11:40:19 2026
 OS/Arch:           linux/amd64
 Context:           default

Server: Docker Engine - Community
 Engine:
  Version:          29.6.1
  API version:      1.55 (minimum version 1.40)
  Go version:       go1.26.4
  Git commit:       8ec5ab3
  Built:            Fri Jun 26 11:40:19 2026
  OS/Arch:          linux/amd64
  Experimental:     false
 containerd:
  Version:          v2.2.5
  GitCommit:        e53c7c1516c3b2bff98eb76f1f4117477e6f4e66
 runc:
  Version:          1.3.6
  GitCommit:        v1.3.6-0-g491b69ba
 docker-init:
  Version:          0.19.0
  GitCommit:        de40ad0

[exit=0]
```

### sudo docker info

```console
$ sudo -n docker info
Client: Docker Engine - Community
 Version:    29.6.1
 Context:    default
 Debug Mode: false
 Plugins:
  buildx: Docker Buildx (Docker Inc.)
    Version:  v0.35.0
    Path:     /usr/libexec/docker/cli-plugins/docker-buildx
  compose: Docker Compose (Docker Inc.)
    Version:  v5.3.0
    Path:     /usr/libexec/docker/cli-plugins/docker-compose

Server:
 Containers: 0
  Running: 0
  Paused: 0
  Stopped: 0
 Images: 1
 Server Version: 29.6.1
 Storage Driver: overlayfs
  driver-type: io.containerd.snapshotter.v1
 Logging Driver: json-file
 Cgroup Driver: systemd
 Cgroup Version: 2
 Plugins:
  Volume: local
  Network: bridge host ipvlan macvlan null overlay
  Log: awslogs fluentd gcplogs gelf journald json-file local splunk syslog
 CDI spec directories:
  /etc/cdi
  /var/run/cdi
 Swarm: inactive
 Runtimes: io.containerd.runc.v2 runc
 Default Runtime: runc
 Init Binary: docker-init
 containerd version: e53c7c1516c3b2bff98eb76f1f4117477e6f4e66
 runc version: v1.3.6-0-g491b69ba
 init version: de40ad0
 Security Options:
  apparmor
  seccomp
   Profile: builtin
  cgroupns
 Kernel Version: 6.8.0-134-generic
 Operating System: Ubuntu 24.04.4 LTS
 OSType: linux
 Architecture: x86_64
 CPUs: 112
 Total Memory: 881.8GiB
 Name: llmserver
 ID: fba62709-52b6-4594-98a7-b3a7e2626f3b
 Docker Root Dir: /data/docker
 Debug Mode: false
 Experimental: false
 Insecure Registries:
  ::1/128
  127.0.0.0/8
 Live Restore Enabled: false
 Firewall Backend: iptables
  EnableUserlandProxy: true
  UserlandProxyPath: /usr/bin/docker-proxy


[exit=0]
```

### sudo docker compose version

```console
$ sudo -n docker compose version
Docker Compose version v5.3.0

[exit=0]
```

### sudo docker buildx version

```console
$ sudo -n docker buildx version
github.com/docker/buildx v0.35.0 a319e5b15052cf6557ceb666eb8ff6e32380b782

[exit=0]
```

### hello-world image inspect

```console
$ sudo -n docker image inspect hello-world:latest
[
    {
        "Id": "sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d",
        "RepoTags": [
            "hello-world:latest"
        ],
        "RepoDigests": [
            "hello-world@sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d"
        ],
        "Comment": "buildkit.dockerfile.v0",
        "Created": "2026-03-23T21:33:59.562202219Z",
        "Config": {
            "Env": [
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            ],
            "Cmd": [
                "/hello"
            ],
            "WorkingDir": "/"
        },
        "Architecture": "amd64",
        "Os": "linux",
        "Size": 16227,
        "RootFS": {
            "Type": "layers",
            "Layers": [
                "sha256:897b3f2a7c1bc2f3d02432f7892fe31c6272c521ad4d70257df624504a3238b4"
            ]
        },
        "Metadata": {
            "LastTagTime": "2026-07-02T19:39:50.349224487Z"
        },
        "Descriptor": {
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "digest": "sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d",
            "size": 12212
        },
        "Identity": {
            "Pull": [
                {
                    "Repository": "docker.io/library/hello-world"
                }
            ]
        }
    }
]

[exit=0]
```

### sudo docker system df

```console
$ sudo -n docker system df
TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          1         0         38.09kB   25.87kB (67%)
Containers      0         0         0B        0B
Local Volumes   0         0         0B        0B
Build Cache     0         0         0B        0B

[exit=0]
```

### Docker/containerd root and data sizes

```console
$ sudo -n du -sh /var/lib/docker /var/lib/containerd '/data/docker' '/data/containerd' '/data/containerd/root' 2>/dev/null || true
236K	/data/docker
336K	/data/containerd

[exit=0]
```

### post-verification root-disk guard

```console
$ scripts/common/root-disk-guard.sh
PASS: root disk guard passed

[exit=0]
```

## Docker/containerd Verification Summary

- Docker installed: yes
- containerd installed: yes
- Docker Root Dir: /data/docker
- containerd root: /data/containerd/root
- containerd state: /run/containerd
- hello-world image present: yes
- root-disk guard: PASS

## Docker/containerd Verification Conclusion

PASS
### Docker storage verifier

```console
$ scripts/docker/verify-docker-storage.sh
PASS: Docker/containerd storage verified

[exit=0]
```

### os-release

```console
$ cat /etc/os-release
PRETTY_NAME="Ubuntu 24.04.4 LTS"
NAME="Ubuntu"
VERSION_ID="24.04"
VERSION="24.04.4 LTS (Noble Numbat)"
VERSION_CODENAME=noble
ID=ubuntu
ID_LIKE=debian
HOME_URL="https://www.ubuntu.com/"
SUPPORT_URL="https://help.ubuntu.com/"
BUG_REPORT_URL="https://bugs.launchpad.net/ubuntu/"
PRIVACY_POLICY_URL="https://www.ubuntu.com/legal/terms-and-policies/privacy-policy"
UBUNTU_CODENAME=noble
LOGO=ubuntu-logo

[exit=0]
```

### uname -a

```console
$ uname -a
Linux llmserver 6.8.0-134-generic #134-Ubuntu SMP PREEMPT_DYNAMIC Fri Jun 26 18:43:11 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux

[exit=0]
```

### lspci NVIDIA/display inventory

```console
$ lspci -nn | egrep -i 'nvidia|vga|3d|display' || true
00:01.0 VGA compatible controller [0300]: Device [1234:1111] (rev 02)
01:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
01:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)
02:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
02:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)

[exit=0]
```

### lspci driver binding summary

```console
$ lspci -nnk | egrep -A5 -i 'nvidia|vga|3d|display' || true
00:01.0 VGA compatible controller [0300]: Device [1234:1111] (rev 02)
	Subsystem: Red Hat, Inc. Device [1af4:1100]
	Kernel driver in use: bochs-drm
	Kernel modules: bochs
00:1a.0 USB controller [0c03]: Intel Corporation 82801I (ICH9 Family) USB UHCI Controller #4 [8086:2937] (rev 03)
	Subsystem: Red Hat, Inc. QEMU Virtual Machine [1af4:1100]
--
01:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
	Subsystem: NVIDIA Corporation Device [10de:204b]
	Kernel driver in use: nvidia
	Kernel modules: nvidiafb, nouveau, nvidia_drm, nvidia
01:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)
	Subsystem: NVIDIA Corporation Device [10de:0000]
	Kernel driver in use: snd_hda_intel
	Kernel modules: snd_hda_intel
02:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
	Subsystem: NVIDIA Corporation Device [10de:204b]
	Kernel driver in use: nvidia
	Kernel modules: nvidiafb, nouveau, nvidia_drm, nvidia
02:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)
	Subsystem: NVIDIA Corporation Device [10de:0000]
	Kernel driver in use: snd_hda_intel
	Kernel modules: snd_hda_intel
05:01.0 PCI bridge [0604]: Red Hat, Inc. QEMU PCI-PCI bridge [1b36:0001]
05:02.0 PCI bridge [0604]: Red Hat, Inc. QEMU PCI-PCI bridge [1b36:0001]
05:03.0 PCI bridge [0604]: Red Hat, Inc. QEMU PCI-PCI bridge [1b36:0001]

[exit=0]
```

### lsmod nvidia/nouveau/vfio summary

```console
$ lsmod | egrep 'nvidia|nouveau|vfio' || true
nvidia_uvm           2060288  0
nvidia_drm            139264  0
nvidia_modeset       1744896  1 nvidia_drm
nvidia              14794752  2 nvidia_uvm,nvidia_modeset
video                  77824  1 nvidia_modeset
ecc                    45056  1 nvidia

[exit=0]
```

### command -v nvidia-smi

```console
$ command -v nvidia-smi
/usr/bin/nvidia-smi

[exit=0]
```

### nvidia-smi

```console
$ nvidia-smi
Fri Jul  3 07:37:28 2026
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 595.71.05              Driver Version: 595.71.05      CUDA Version: 13.2     |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA RTX PRO 6000 Blac...    Off |   00000000:01:00.0 Off |                  Off |
| 30%   32C    P8             15W /  600W |       2MiB /  97887MiB |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+
|   1  NVIDIA RTX PRO 6000 Blac...    Off |   00000000:02:00.0 Off |                  Off |
| 30%   38C    P8             32W /  600W |      34MiB /  97887MiB |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+

+-----------------------------------------------------------------------------------------+
| Processes:                                                                              |
|  GPU   GI   CI              PID   Type   Process name                        GPU Memory |
|        ID   ID                                                               Usage      |
|=========================================================================================|
|  No running processes found                                                             |
+-----------------------------------------------------------------------------------------+

[exit=0]
```

### nvidia-smi -L

```console
$ nvidia-smi -L
GPU 0: NVIDIA RTX PRO 6000 Blackwell Workstation Edition (UUID: GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237)
GPU 1: NVIDIA RTX PRO 6000 Blackwell Workstation Edition (UUID: GPU-69acfa26-8b60-61b5-702d-aee252c163cc)

[exit=0]
```

### nvidia-smi query-gpu CSV

```console
$ nvidia-smi --query-gpu=index\,name\,pci.bus_id\,driver_version\,memory.total\,power.limit --format=csv
index, name, pci.bus_id, driver_version, memory.total [MiB], power.limit [W]
0, NVIDIA RTX PRO 6000 Blackwell Workstation Edition, 00000000:01:00.0, 595.71.05, 97887 MiB, 600.00 W
1, NVIDIA RTX PRO 6000 Blackwell Workstation Edition, 00000000:02:00.0, 595.71.05, 97887 MiB, 600.00 W

[exit=0]
```

### nvidia-smi topology

```console
$ nvidia-smi topo -m
	[4mGPU0	GPU1	CPU Affinity	NUMA Affinity	GPU NUMA ID[0m
GPU0	 X 	PHB	0-111	0-6		N/A
GPU1	PHB	 X 	0-111	0-6		N/A

Legend:

  X    = Self
  SYS  = Connection traversing PCIe as well as the SMP interconnect between NUMA nodes (e.g., QPI/UPI)
  NODE = Connection traversing PCIe as well as the interconnect between PCIe Host Bridges within a NUMA node
  PHB  = Connection traversing PCIe as well as a PCIe Host Bridge (typically the CPU)
  PXB  = Connection traversing multiple PCIe bridges (without traversing the PCIe Host Bridge)
  PIX  = Connection traversing at most a single PCIe bridge
  NV#  = Connection traversing a bonded set of # NVLinks

[exit=0]
```

### nvidia-smi requested MEMORY,PCI,POWER detail (unsupported PCI display flag in 595)

```console
$ nvidia-smi -q -d MEMORY\,PCI\,POWER
Failed to parse --display/-d flags

[exit=2]
```

### nvidia-smi full query for PCI detail

```console
$ nvidia-smi -q

==============NVSMI LOG==============

Timestamp                                              : Fri Jul  3 07:37:28 2026
Driver Version                                         : 595.71.05
CUDA Version                                           : 13.2

Attached GPUs                                          : 2
GPU 00000000:01:00.0
    Product Name                                       : NVIDIA RTX PRO 6000 Blackwell Workstation Edition
    Product Brand                                      : NVIDIA RTX
    Product Architecture                               : Blackwell
    Display Mode                                       : Requested functionality has been deprecated
    Display Attached                                   : No
    Display Active                                     : Disabled
    Persistence Mode                                   : Disabled
    Addressing Mode                                    : HMM
    MIG Mode
        Current                                        : N/A
        Pending                                        : N/A
    Accounting Mode                                    : Disabled
    Accounting Mode Buffer Size                        : 4000
    Driver Model
        Current                                        : N/A
        Pending                                        : N/A
    Serial Number                                      : 1792525050955
    GPU UUID                                           : GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237
    GPU PDI                                            : 0x2fc57a11785567f6
    Minor Number                                       : 0
    VBIOS Version                                      : 98.02.52.00.02
    MultiGPU Board                                     : No
    Board ID                                           : 0x100
    Board Part Number                                  : 900-5G144-2200-000
    GPU Part Number                                    : 2BB1-870-A1
    FRU Part Number                                    : N/A
    Platform Info
        Chassis Serial Number                          :
        Slot Number                                    : 0
        Tray Index                                     : 0
        Host ID                                        : 1
        Peer Type                                      : Direct Connected
        Module Id                                      : 1
        GPU Fabric GUID                                : 0x0000000000000000
    Inforom Version
        Image Version                                  : G144.0520.00.02
        OEM Object                                     : 2.1
        ECC Object                                     : 7.16
        Power Management Object                        : N/A
    Inforom BBX Object Flush
        Latest Timestamp                               : N/A
        Latest Duration                                : N/A
    GPU Operation Mode
        Current                                        : N/A
        Pending                                        : N/A
    GPU C2C Mode                                       : Disabled
    GPU Virtualization Mode
        Virtualization Mode                            : Pass-Through
        Host VGPU Mode                                 : N/A
        vGPU Heterogeneous Mode                        : N/A
    GPU Recovery Action                                : None
    GSP Firmware Version                               : 595.71.05
    IBMNPU
        Relaxed Ordering Mode                          : N/A
    PCI
        Bus                                            : 0x01
        Device                                         : 0x00
        Domain                                         : 0x0000
        Base Classcode                                 : 0x3
        Sub Classcode                                  : 0x0
        Device Id                                      : 0x2BB110DE
        Bus Id                                         : 00000000:01:00.0
        Sub System Id                                  : 0x204B10DE
        GPU Link Info
            PCIe Generation
                Max                                    : 5
                Current                                : 1
                Device Current                         : 1
                Device Max                             : 5
                Host Max                               : N/A
            Link Width
                Max                                    : 16x
                Current                                : 16x
        Bridge Chip
            Type                                       : N/A
            Firmware                                   : N/A
        Replays Since Reset                            : 0
        Replay Number Rollovers                        : 0
        Tx Throughput                                  : 888 KB/s
        Rx Throughput                                  : 595 KB/s
        Atomic Caps Outbound                           : N/A
        Atomic Caps Inbound                            : FETCHADD_32 FETCHADD_64 SWAP_32 SWAP_64 CAS_32 CAS_64
    Fan Speed                                          : 30 %
    Performance State                                  : P8
    Clocks Event Reasons
        Idle                                           : Not Active
        Applications Clocks Setting                    : Not Active
        SW Power Cap                                   : Not Active
        HW Slowdown                                    : Not Active
            HW Thermal Slowdown                        : Not Active
            HW Power Brake Slowdown                    : Not Active
        Sync Boost                                     : Not Active
        SW Thermal Slowdown                            : Not Active
        Display Clock Setting                          : Not Active
    Clocks Event Reasons Counters
        SW Power Capping                               : 200402 us
        Sync Boost                                     : 0 us
        SW Thermal Slowdown                            : 0 us
        HW Thermal Slowdown                            : 0 us
        HW Power Braking                               : 0 us
    Sparse Operation Mode                              : N/A
    FB Memory Usage
        Total                                          : 97887 MiB
        Reserved                                       : 638 MiB
        Used                                           : 2 MiB
        Free                                           : 97249 MiB
    BAR1 Memory Usage
        Total                                          : 131072 MiB
        Used                                           : 1 MiB
        Free                                           : 131071 MiB
    Conf Compute Protected Memory Usage
        Total                                          : 0 MiB
        Used                                           : 0 MiB
        Free                                           : 0 MiB
    Compute Mode                                       : Default
    Utilization
        GPU                                            : 0 %
        Memory                                         : 0 %
        Encoder                                        : 0 %
        Decoder                                        : 0 %
        JPEG                                           : 0 %
        OFA                                            : 0 %
    Encoder Stats
        Active Sessions                                : 0
        Average FPS                                    : 0
        Average Latency                                : 0
    FBC Stats
        Active Sessions                                : 0
        Average FPS                                    : 0
        Average Latency                                : 0
    DRAM Encryption Mode
        Current                                        : Disabled
        Pending                                        : Disabled
    ECC Mode
        Current                                        : Disabled
        Pending                                        : Disabled
    ECC Errors
        Volatile
            SRAM Correctable                           : N/A
            SRAM Uncorrectable Parity                  : N/A
            SRAM Uncorrectable SEC-DED                 : N/A
            DRAM Correctable                           : N/A
            DRAM Uncorrectable                         : N/A
        Aggregate
            SRAM Correctable                           : N/A
            SRAM Uncorrectable Parity                  : N/A
            SRAM Uncorrectable SEC-DED                 : N/A
            DRAM Correctable                           : N/A
            DRAM Uncorrectable                         : N/A
            SRAM Threshold Exceeded                    : N/A
        Aggregate Uncorrectable SRAM Sources
            SRAM L2                                    : N/A
            SRAM SM                                    : N/A
            SRAM Microcontroller                       : N/A
            SRAM PCIE                                  : N/A
            SRAM Other                                 : N/A
        Channel Repair Pending                         : No
        TPC Repair Pending                             : No
        Unrepairable Memory                            : N/A
    Retired Pages
        Single Bit ECC                                 : N/A
        Double Bit ECC                                 : N/A
        Pending Page Blacklist                         : N/A
    Remapped Rows
        Correctable Error                              : 0
        Inactive Correctable Error                     : 0
        Uncorrectable Error                            : 0
        Inactive Uncorrectable Error                   : 0
        Pending                                        : No
        Remapping Failure Occurred                     : No
        Bank Remap Availability Histogram
            Max                                        : 512 bank(s)
            High                                       : 0 bank(s)
            Partial                                    : 0 bank(s)
            Low                                        : 0 bank(s)
            None                                       : 0 bank(s)
    Temperature
        GPU Current Temp                               : 32 C
        GPU T.Limit Temp                               : 61 C
        GPU Shutdown T.Limit Temp                      : -5 C
        GPU Slowdown T.Limit Temp                      : -2 C
        GPU Max Operating T.Limit Temp                 : 0 C
        GPU Target Temperature                         : N/A
        Memory Current Temp                            : N/A
        Memory Max Operating T.Limit Temp              : N/A
    GPU Power Readings
        Average Power Draw                             : 15.08 W
        Instantaneous Power Draw                       : 15.08 W
        Current Power Limit                            : 600.00 W
        Requested Power Limit                          : 600.00 W
        Default Power Limit                            : 600.00 W
        Min Power Limit                                : 150.00 W
        Max Power Limit                                : 600.00 W
    GPU Memory Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
    Module Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
        Current Power Limit                            : N/A
        Requested Power Limit                          : N/A
        Default Power Limit                            : N/A
        Min Power Limit                                : N/A
        Max Power Limit                                : N/A
    Power Smoothing                                    : N/A
    Workload Power Profiles
        Requested Profiles                             : N/A
        Enforced Profiles                              : N/A
    EDPp Multiplier                                    : N/A
    Clocks
        Graphics                                       : 180 MHz
        SM                                             : 180 MHz
        Memory                                         : 405 MHz
        Video                                          : 600 MHz
    Applications Clocks
        Graphics                                       : Requested functionality has been deprecated
        Memory                                         : Requested functionality has been deprecated
    Default Applications Clocks
        Graphics                                       : Requested functionality has been deprecated
        Memory                                         : Requested functionality has been deprecated
    Deferred Clocks
        Memory                                         : N/A
    Max Clocks
        Graphics                                       : 3090 MHz
        SM                                             : 3090 MHz
        Memory                                         : 14001 MHz
        Video                                          : 3090 MHz
    Max Customer Boost Clocks
        Graphics                                       : N/A
    Clock Policy
        Auto Boost                                     : N/A
        Auto Boost Default                             : N/A
    Fabric
        State                                          : N/A
        Status                                         : N/A
        CliqueId                                       : N/A
        ClusterUUID                                    : N/A
        Health
            Summary                                    : N/A
            Bandwidth                                  : N/A
            Route Recovery in progress                 : N/A
            Route Unhealthy                            : N/A
            Access Timeout Recovery                    : N/A
            Incorrect Configuration                    : N/A
            Partition Assigned                         : N/A
    Processes                                          : None
    Capabilities
        EGM                                            : disabled

GPU 00000000:02:00.0
    Product Name                                       : NVIDIA RTX PRO 6000 Blackwell Workstation Edition
    Product Brand                                      : NVIDIA RTX
    Product Architecture                               : Blackwell
    Display Mode                                       : Requested functionality has been deprecated
    Display Attached                                   : Yes
    Display Active                                     : Disabled
    Persistence Mode                                   : Disabled
    Addressing Mode                                    : HMM
    MIG Mode
        Current                                        : N/A
        Pending                                        : N/A
    Accounting Mode                                    : Disabled
    Accounting Mode Buffer Size                        : 4000
    Driver Model
        Current                                        : N/A
        Pending                                        : N/A
    Serial Number                                      : 1792825000515
    GPU UUID                                           : GPU-69acfa26-8b60-61b5-702d-aee252c163cc
    GPU PDI                                            : 0x3802a64ab95f128c
    Minor Number                                       : 1
    VBIOS Version                                      : 98.02.52.00.02
    MultiGPU Board                                     : No
    Board ID                                           : 0x200
    Board Part Number                                  : 900-5G144-2200-000
    GPU Part Number                                    : 2BB1-870-A1
    FRU Part Number                                    : N/A
    Platform Info
        Chassis Serial Number                          :
        Slot Number                                    : 0
        Tray Index                                     : 0
        Host ID                                        : 1
        Peer Type                                      : Direct Connected
        Module Id                                      : 1
        GPU Fabric GUID                                : 0x0000000000000000
    Inforom Version
        Image Version                                  : G144.0520.00.02
        OEM Object                                     : 2.1
        ECC Object                                     : 7.16
        Power Management Object                        : N/A
    Inforom BBX Object Flush
        Latest Timestamp                               : N/A
        Latest Duration                                : N/A
    GPU Operation Mode
        Current                                        : N/A
        Pending                                        : N/A
    GPU C2C Mode                                       : Disabled
    GPU Virtualization Mode
        Virtualization Mode                            : Pass-Through
        Host VGPU Mode                                 : N/A
        vGPU Heterogeneous Mode                        : N/A
    GPU Recovery Action                                : None
    GSP Firmware Version                               : 595.71.05
    IBMNPU
        Relaxed Ordering Mode                          : N/A
    PCI
        Bus                                            : 0x02
        Device                                         : 0x00
        Domain                                         : 0x0000
        Base Classcode                                 : 0x3
        Sub Classcode                                  : 0x0
        Device Id                                      : 0x2BB110DE
        Bus Id                                         : 00000000:02:00.0
        Sub System Id                                  : 0x204B10DE
        GPU Link Info
            PCIe Generation
                Max                                    : 5
                Current                                : 1
                Device Current                         : 1
                Device Max                             : 5
                Host Max                               : N/A
            Link Width
                Max                                    : 16x
                Current                                : 16x
        Bridge Chip
            Type                                       : N/A
            Firmware                                   : N/A
        Replays Since Reset                            : 0
        Replay Number Rollovers                        : 0
        Tx Throughput                                  : 771 KB/s
        Rx Throughput                                  : 484 KB/s
        Atomic Caps Outbound                           : N/A
        Atomic Caps Inbound                            : FETCHADD_32 FETCHADD_64 SWAP_32 SWAP_64 CAS_32 CAS_64
    Fan Speed                                          : 30 %
    Performance State                                  : P8
    Clocks Event Reasons
        Idle                                           : Not Active
        Applications Clocks Setting                    : Not Active
        SW Power Cap                                   : Not Active
        HW Slowdown                                    : Not Active
            HW Thermal Slowdown                        : Not Active
            HW Power Brake Slowdown                    : Not Active
        Sync Boost                                     : Not Active
        SW Thermal Slowdown                            : Not Active
        Display Clock Setting                          : Not Active
    Clocks Event Reasons Counters
        SW Power Capping                               : 200214 us
        Sync Boost                                     : 0 us
        SW Thermal Slowdown                            : 0 us
        HW Thermal Slowdown                            : 0 us
        HW Power Braking                               : 0 us
    Sparse Operation Mode                              : N/A
    FB Memory Usage
        Total                                          : 97887 MiB
        Reserved                                       : 638 MiB
        Used                                           : 34 MiB
        Free                                           : 97217 MiB
    BAR1 Memory Usage
        Total                                          : 131072 MiB
        Used                                           : 33 MiB
        Free                                           : 131039 MiB
    Conf Compute Protected Memory Usage
        Total                                          : 0 MiB
        Used                                           : 0 MiB
        Free                                           : 0 MiB
    Compute Mode                                       : Default
    Utilization
        GPU                                            : 0 %
        Memory                                         : 0 %
        Encoder                                        : 0 %
        Decoder                                        : 0 %
        JPEG                                           : 0 %
        OFA                                            : 0 %
    Encoder Stats
        Active Sessions                                : 0
        Average FPS                                    : 0
        Average Latency                                : 0
    FBC Stats
        Active Sessions                                : 0
        Average FPS                                    : 0
        Average Latency                                : 0
    DRAM Encryption Mode
        Current                                        : Disabled
        Pending                                        : Disabled
    ECC Mode
        Current                                        : Disabled
        Pending                                        : Disabled
    ECC Errors
        Volatile
            SRAM Correctable                           : N/A
            SRAM Uncorrectable Parity                  : N/A
            SRAM Uncorrectable SEC-DED                 : N/A
            DRAM Correctable                           : N/A
            DRAM Uncorrectable                         : N/A
        Aggregate
            SRAM Correctable                           : N/A
            SRAM Uncorrectable Parity                  : N/A
            SRAM Uncorrectable SEC-DED                 : N/A
            DRAM Correctable                           : N/A
            DRAM Uncorrectable                         : N/A
            SRAM Threshold Exceeded                    : N/A
        Aggregate Uncorrectable SRAM Sources
            SRAM L2                                    : N/A
            SRAM SM                                    : N/A
            SRAM Microcontroller                       : N/A
            SRAM PCIE                                  : N/A
            SRAM Other                                 : N/A
        Channel Repair Pending                         : No
        TPC Repair Pending                             : No
        Unrepairable Memory                            : N/A
    Retired Pages
        Single Bit ECC                                 : N/A
        Double Bit ECC                                 : N/A
        Pending Page Blacklist                         : N/A
    Remapped Rows
        Correctable Error                              : 0
        Inactive Correctable Error                     : 0
        Uncorrectable Error                            : 0
        Inactive Uncorrectable Error                   : 0
        Pending                                        : No
        Remapping Failure Occurred                     : No
        Bank Remap Availability Histogram
            Max                                        : 512 bank(s)
            High                                       : 0 bank(s)
            Partial                                    : 0 bank(s)
            Low                                        : 0 bank(s)
            None                                       : 0 bank(s)
    Temperature
        GPU Current Temp                               : 38 C
        GPU T.Limit Temp                               : 55 C
        GPU Shutdown T.Limit Temp                      : -5 C
        GPU Slowdown T.Limit Temp                      : -2 C
        GPU Max Operating T.Limit Temp                 : 0 C
        GPU Target Temperature                         : N/A
        Memory Current Temp                            : N/A
        Memory Max Operating T.Limit Temp              : N/A
    GPU Power Readings
        Average Power Draw                             : 32.31 W
        Instantaneous Power Draw                       : 32.41 W
        Current Power Limit                            : 600.00 W
        Requested Power Limit                          : 600.00 W
        Default Power Limit                            : 600.00 W
        Min Power Limit                                : 150.00 W
        Max Power Limit                                : 600.00 W
    GPU Memory Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
    Module Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
        Current Power Limit                            : N/A
        Requested Power Limit                          : N/A
        Default Power Limit                            : N/A
        Min Power Limit                                : N/A
        Max Power Limit                                : N/A
    Power Smoothing                                    : N/A
    Workload Power Profiles
        Requested Profiles                             : N/A
        Enforced Profiles                              : N/A
    EDPp Multiplier                                    : N/A
    Clocks
        Graphics                                       : 180 MHz
        SM                                             : 180 MHz
        Memory                                         : 405 MHz
        Video                                          : 600 MHz
    Applications Clocks
        Graphics                                       : Requested functionality has been deprecated
        Memory                                         : Requested functionality has been deprecated
    Default Applications Clocks
        Graphics                                       : Requested functionality has been deprecated
        Memory                                         : Requested functionality has been deprecated
    Deferred Clocks
        Memory                                         : N/A
    Max Clocks
        Graphics                                       : 3090 MHz
        SM                                             : 3090 MHz
        Memory                                         : 14001 MHz
        Video                                          : 3090 MHz
    Max Customer Boost Clocks
        Graphics                                       : N/A
    Clock Policy
        Auto Boost                                     : N/A
        Auto Boost Default                             : N/A
    Fabric
        State                                          : N/A
        Status                                         : N/A
        CliqueId                                       : N/A
        ClusterUUID                                    : N/A
        Health
            Summary                                    : N/A
            Bandwidth                                  : N/A
            Route Recovery in progress                 : N/A
            Route Unhealthy                            : N/A
            Access Timeout Recovery                    : N/A
            Incorrect Configuration                    : N/A
            Partition Assigned                         : N/A
    Processes                                          : None
    Capabilities
        EGM                                            : disabled


[exit=0]
```

### nvidia-smi memory detail

```console
$ nvidia-smi -q -d MEMORY

==============NVSMI LOG==============

Timestamp                                              : Fri Jul  3 07:37:28 2026
Driver Version                                         : 595.71.05
CUDA Version                                           : 13.2

Attached GPUs                                          : 2
GPU 00000000:01:00.0
    FB Memory Usage
        Total                                          : 97887 MiB
        Reserved                                       : 638 MiB
        Used                                           : 2 MiB
        Free                                           : 97249 MiB
    BAR1 Memory Usage
        Total                                          : 131072 MiB
        Used                                           : 1 MiB
        Free                                           : 131071 MiB
    Conf Compute Protected Memory Usage
        Total                                          : 0 MiB
        Used                                           : 0 MiB
        Free                                           : 0 MiB

GPU 00000000:02:00.0
    FB Memory Usage
        Total                                          : 97887 MiB
        Reserved                                       : 638 MiB
        Used                                           : 34 MiB
        Free                                           : 97217 MiB
    BAR1 Memory Usage
        Total                                          : 131072 MiB
        Used                                           : 33 MiB
        Free                                           : 131039 MiB
    Conf Compute Protected Memory Usage
        Total                                          : 0 MiB
        Used                                           : 0 MiB
        Free                                           : 0 MiB


[exit=0]
```

### nvidia-smi power detail

```console
$ nvidia-smi -q -d POWER

==============NVSMI LOG==============

Timestamp                                              : Fri Jul  3 07:37:29 2026
Driver Version                                         : 595.71.05
CUDA Version                                           : 13.2

Attached GPUs                                          : 2
GPU 00000000:01:00.0
    GPU Power Readings
        Average Power Draw                             : 15.08 W
        Instantaneous Power Draw                       : 15.08 W
        Current Power Limit                            : 600.00 W
        Requested Power Limit                          : 600.00 W
        Default Power Limit                            : 600.00 W
        Min Power Limit                                : 150.00 W
        Max Power Limit                                : 600.00 W
    Power Samples
        Duration                                       : 103.31 sec
        Number of Samples                              : 119
        Max                                            : 57.81 W
        Min                                            : 14.77 W
        Avg                                            : 15.25 W
    GPU Memory Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
    Module Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
        Current Power Limit                            : N/A
        Requested Power Limit                          : N/A
        Default Power Limit                            : N/A
        Min Power Limit                                : N/A
        Max Power Limit                                : N/A
    EDPp Multiplier                                    : N/A

GPU 00000000:02:00.0
    GPU Power Readings
        Average Power Draw                             : 32.31 W
        Instantaneous Power Draw                       : 32.41 W
        Current Power Limit                            : 600.00 W
        Requested Power Limit                          : 600.00 W
        Default Power Limit                            : 600.00 W
        Min Power Limit                                : 150.00 W
        Max Power Limit                                : 600.00 W
    Power Samples
        Duration                                       : 102.33 sec
        Number of Samples                              : 119
        Max                                            : 98.16 W
        Min                                            : 31.97 W
        Avg                                            : 32.62 W
    GPU Memory Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
    Module Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
        Current Power Limit                            : N/A
        Requested Power Limit                          : N/A
        Default Power Limit                            : N/A
        Min Power Limit                                : N/A
        Max Power Limit                                : N/A
    EDPp Multiplier                                    : N/A


[exit=0]
```

### nvcc after reboot

```console
$ command -v nvcc || true; nvcc --version || true
bash: line 1: nvcc: command not found

[exit=0]
```

### Installed NVIDIA/CUDA/container-toolkit packages after reboot

```console
$ dpkg -l | egrep 'nvidia|cuda|container-toolkit' || true
ii  libnvidia-cfg1-595:amd64              595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA binary OpenGL/GLX configuration library
ii  libnvidia-common-595                  595.71.05-0ubuntu0.24.04.1                       amd64        Shared files used by the NVIDIA libraries
ii  libnvidia-compute-595:amd64           595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA libcompute package
ii  libnvidia-decode-595:amd64            595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA Video Decoding runtime libraries
ii  libnvidia-egl-wayland1:amd64          1:1.1.13-1ubuntu0.1                              amd64        Wayland EGL External Platform library -- shared library
ii  libnvidia-encode-595:amd64            595.71.05-0ubuntu0.24.04.1                       amd64        NVENC Video Encoding runtime library
ii  libnvidia-extra-595:amd64             595.71.05-0ubuntu0.24.04.1                       amd64        Extra libraries for the NVIDIA driver
ii  libnvidia-fbc1-595:amd64              595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA OpenGL-based Framebuffer Capture runtime library
ii  libnvidia-gl-595:amd64                595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA OpenGL/GLX/EGL/GLES GLVND libraries and Vulkan ICD
ii  nvidia-compute-utils-595              595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA compute utilities
ii  nvidia-dkms-595-open                  595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA DKMS package (open kernel module)
ii  nvidia-driver-595-open                595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA driver (open kernel) metapackage
ii  nvidia-firmware-595-595.71.05         595.71.05-0ubuntu0.24.04.1                       amd64        Firmware files used by the kernel module
ii  nvidia-kernel-common-595              595.71.05-0ubuntu0.24.04.1                       amd64        Shared files used with the kernel module
ii  nvidia-kernel-source-595-open         595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA kernel source package
ii  nvidia-prime                          0.8.17.2                                         all          Tools to enable NVIDIA's Prime
ii  nvidia-settings                       510.47.03-0ubuntu4.24.04.1                       amd64        Tool for configuring the NVIDIA graphics driver
ii  nvidia-utils-595                      595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA driver support binaries
ii  screen-resolution-extra               0.18.3ubuntu0.24.04.1                            all          Extension for the nvidia-settings control panel
ii  xserver-xorg-video-nvidia-595         595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA binary Xorg driver

[exit=0]
```

### Docker Root Dir and containerd info

```console
$ sudo -n docker info | egrep 'Docker Root Dir|Storage Driver|containerd' || true
 Storage Driver: overlayfs
  driver-type: io.containerd.snapshotter.v1
 Runtimes: io.containerd.runc.v2 runc
 containerd version: e53c7c1516c3b2bff98eb76f1f4117477e6f4e66
 Docker Root Dir: /data/docker

[exit=0]
```

### Docker/containerd path sizes

```console
$ sudo -n du -sh /var/lib/docker /var/lib/containerd /data/docker /data/containerd /data/containerd/root 2>/dev/null || true
236K	/data/docker
336K	/data/containerd

[exit=0]
```

## M5B Post-reboot Conclusion

STOP

Reason: one or more GPUs did not report approximately 96 GB VRAM

Manual Proxmox VFIO/AER/reset checks are still required outside Codex.

## Post-reboot verifier retry note 2

The second verifier run stopped because the script parsed `driver_version` instead of `memory.total` from the no-header query CSV. The query output shows both GPUs report `97887 MiB`; the runner was corrected to validate the fifth CSV column.

# M5B post-reboot NVIDIA driver verification

- Timestamp: 2026-07-03T07:38:00+00:00
- Hostname: llmserver
- Uptime: up 2 minutes
- Runner: /data/services/m5b-post-reboot/m5b-post-reboot-verify.sh
- Log: /data/logs/m5b-post-reboot-verify.log

### hostname

```console
$ hostname
llmserver

[exit=0]
```

### uptime

```console
$ uptime
 07:38:00 up 2 min,  3 users,  load average: 0.11, 0.10, 0.04

[exit=0]
```

### date -Is

```console
$ date -Is
2026-07-03T07:38:00+00:00

[exit=0]
```

### require-data-mounted

```console
$ scripts/common/require-data-mounted.sh
PASS: /data is mounted and ready
- root source: /dev/mapper/ubuntu--vg-ubuntu--lv
- data source: /dev/sdb1
- data fstype: ext4
- data label: AI_DATA
- data UUID: 8daf56f1-5649-4163-9d87-919c2d271875

[exit=0]
```

### root-disk-guard

```console
$ scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md
PASS: root disk guard passed

[exit=0]
```


## Docker/containerd Storage Verification

- Timestamp: 2026-07-03T07:38:01+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m5b-nvidia-host-driver

### require /data mounted

```console
$ scripts/common/require-data-mounted.sh
PASS: /data is mounted and ready
- root source: /dev/mapper/ubuntu--vg-ubuntu--lv
- data source: /dev/sdb1
- data fstype: ext4
- data label: AI_DATA
- data UUID: 8daf56f1-5649-4163-9d87-919c2d271875

[exit=0]
```

### pre-verification root-disk guard

```console
$ scripts/common/root-disk-guard.sh
PASS: root disk guard passed

[exit=0]
```

### df -hT / /data

```console
$ df -hT / /data
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  8.9G  4.6G  66% /
/dev/sdb1                         ext4  2.0T  3.4M  1.9T   1% /data

[exit=0]
```

### /var/lib Docker/containerd size summary

| Path | MiB | Policy |
| --- | ---: | --- |
| `/var/lib/docker` | 0 | absent/empty/small or documented |
| `/var/lib/containerd` | 0 | absent/empty/small or documented |

### systemctl is-active containerd

```console
$ sudo -n systemctl is-active containerd
active

[exit=0]
```

### systemctl is-active docker

```console
$ sudo -n systemctl is-active docker
active

[exit=0]
```

### systemctl status containerd

```console
$ sudo -n systemctl status containerd --no-pager
● containerd.service - containerd container runtime
     Loaded: loaded (/usr/lib/systemd/system/containerd.service; enabled; preset: enabled)
     Active: active (running) since Fri 2026-07-03 07:35:25 UTC; 2min 35s ago
       Docs: https://containerd.io
   Main PID: 2091 (containerd)
      Tasks: 30
     Memory: 82.3M (peak: 86.7M)
        CPU: 445ms
     CGroup: /system.slice/containerd.service
             └─2091 /usr/bin/containerd

Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875859853Z" level=info msg="Start cni network conf syncer for default"
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875865272Z" level=info msg="Start streaming server"
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875873444Z" level=info msg="Registered namespace \"k8s.io\" with NRI"
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875878251Z" level=info msg="runtime interface starting up..."
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875881666Z" level=info msg="starting plugins..."
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875890109Z" level=info msg="Synchronizing NRI (plugin) with current runtime state"
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875902768Z" level=info msg=serving... address=/run/containerd/containerd.sock.ttrpc
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875941546Z" level=info msg=serving... address=/run/containerd/containerd.sock
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.876173504Z" level=info msg="containerd successfully booted in 0.033839s"
Jul 03 07:35:25 llmserver systemd[1]: Started containerd.service - containerd container runtime.

[exit=0]
```

### systemctl status docker

```console
$ sudo -n systemctl status docker --no-pager
● docker.service - Docker Application Container Engine
     Loaded: loaded (/usr/lib/systemd/system/docker.service; enabled; preset: enabled)
     Active: active (running) since Fri 2026-07-03 07:35:28 UTC; 2min 33s ago
TriggeredBy: ● docker.socket
       Docs: https://docs.docker.com
   Main PID: 2261 (dockerd)
      Tasks: 41
     Memory: 116.0M (peak: 122.0M)
        CPU: 525ms
     CGroup: /system.slice/docker.service
             └─2261 /usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock

Jul 03 07:35:27 llmserver dockerd[2261]: time="2026-07-03T07:35:27.673114630Z" level=info msg="Restoring containers: start."
Jul 03 07:35:27 llmserver dockerd[2261]: time="2026-07-03T07:35:27.775998332Z" level=info msg="Deleting nftables IPv4 rules" error="running nft: /dev/stdin:1:17-30: Error: Could not process rule: No such file or directory\ndelete table ip docker-bridges\n                ^^^^^^^^^^^^^^\n exit status 1"
Jul 03 07:35:27 llmserver dockerd[2261]: time="2026-07-03T07:35:27.788141528Z" level=info msg="Deleting nftables IPv6 rules" error="running nft: /dev/stdin:1:18-31: Error: Could not process rule: No such file or directory\ndelete table ip6 docker-bridges\n                 ^^^^^^^^^^^^^^\n exit status 1"
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.052444560Z" level=info msg="Loading containers: done."
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.058049123Z" level=info msg="Docker daemon" commit=8ec5ab3 containerd-snapshotter=true storage-driver=overlayfs version=29.6.1
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.058280870Z" level=info msg="Initializing buildkit"
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.220160582Z" level=info msg="Completed buildkit initialization"
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.224043800Z" level=info msg="Daemon has completed initialization"
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.224122648Z" level=info msg="API listen on /run/docker.sock"
Jul 03 07:35:28 llmserver systemd[1]: Started docker.service - Docker Application Container Engine.

[exit=0]
```

### sudo docker version

```console
$ sudo -n docker version
Client: Docker Engine - Community
 Version:           29.6.1
 API version:       1.55
 Go version:        go1.26.4
 Git commit:        8900f1d
 Built:             Fri Jun 26 11:40:19 2026
 OS/Arch:           linux/amd64
 Context:           default

Server: Docker Engine - Community
 Engine:
  Version:          29.6.1
  API version:      1.55 (minimum version 1.40)
  Go version:       go1.26.4
  Git commit:       8ec5ab3
  Built:            Fri Jun 26 11:40:19 2026
  OS/Arch:          linux/amd64
  Experimental:     false
 containerd:
  Version:          v2.2.5
  GitCommit:        e53c7c1516c3b2bff98eb76f1f4117477e6f4e66
 runc:
  Version:          1.3.6
  GitCommit:        v1.3.6-0-g491b69ba
 docker-init:
  Version:          0.19.0
  GitCommit:        de40ad0

[exit=0]
```

### sudo docker info

```console
$ sudo -n docker info
Client: Docker Engine - Community
 Version:    29.6.1
 Context:    default
 Debug Mode: false
 Plugins:
  buildx: Docker Buildx (Docker Inc.)
    Version:  v0.35.0
    Path:     /usr/libexec/docker/cli-plugins/docker-buildx
  compose: Docker Compose (Docker Inc.)
    Version:  v5.3.0
    Path:     /usr/libexec/docker/cli-plugins/docker-compose

Server:
 Containers: 0
  Running: 0
  Paused: 0
  Stopped: 0
 Images: 1
 Server Version: 29.6.1
 Storage Driver: overlayfs
  driver-type: io.containerd.snapshotter.v1
 Logging Driver: json-file
 Cgroup Driver: systemd
 Cgroup Version: 2
 Plugins:
  Volume: local
  Network: bridge host ipvlan macvlan null overlay
  Log: awslogs fluentd gcplogs gelf journald json-file local splunk syslog
 CDI spec directories:
  /etc/cdi
  /var/run/cdi
 Swarm: inactive
 Runtimes: io.containerd.runc.v2 runc
 Default Runtime: runc
 Init Binary: docker-init
 containerd version: e53c7c1516c3b2bff98eb76f1f4117477e6f4e66
 runc version: v1.3.6-0-g491b69ba
 init version: de40ad0
 Security Options:
  apparmor
  seccomp
   Profile: builtin
  cgroupns
 Kernel Version: 6.8.0-134-generic
 Operating System: Ubuntu 24.04.4 LTS
 OSType: linux
 Architecture: x86_64
 CPUs: 112
 Total Memory: 881.8GiB
 Name: llmserver
 ID: fba62709-52b6-4594-98a7-b3a7e2626f3b
 Docker Root Dir: /data/docker
 Debug Mode: false
 Experimental: false
 Insecure Registries:
  ::1/128
  127.0.0.0/8
 Live Restore Enabled: false
 Firewall Backend: iptables
  EnableUserlandProxy: true
  UserlandProxyPath: /usr/bin/docker-proxy


[exit=0]
```

### sudo docker compose version

```console
$ sudo -n docker compose version
Docker Compose version v5.3.0

[exit=0]
```

### sudo docker buildx version

```console
$ sudo -n docker buildx version
github.com/docker/buildx v0.35.0 a319e5b15052cf6557ceb666eb8ff6e32380b782

[exit=0]
```

### hello-world image inspect

```console
$ sudo -n docker image inspect hello-world:latest
[
    {
        "Id": "sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d",
        "RepoTags": [
            "hello-world:latest"
        ],
        "RepoDigests": [
            "hello-world@sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d"
        ],
        "Comment": "buildkit.dockerfile.v0",
        "Created": "2026-03-23T21:33:59.562202219Z",
        "Config": {
            "Env": [
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            ],
            "Cmd": [
                "/hello"
            ],
            "WorkingDir": "/"
        },
        "Architecture": "amd64",
        "Os": "linux",
        "Size": 16227,
        "RootFS": {
            "Type": "layers",
            "Layers": [
                "sha256:897b3f2a7c1bc2f3d02432f7892fe31c6272c521ad4d70257df624504a3238b4"
            ]
        },
        "Metadata": {
            "LastTagTime": "2026-07-02T19:39:50.349224487Z"
        },
        "Descriptor": {
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "digest": "sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d",
            "size": 12212
        },
        "Identity": {
            "Pull": [
                {
                    "Repository": "docker.io/library/hello-world"
                }
            ]
        }
    }
]

[exit=0]
```

### sudo docker system df

```console
$ sudo -n docker system df
TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          1         0         38.09kB   25.87kB (67%)
Containers      0         0         0B        0B
Local Volumes   0         0         0B        0B
Build Cache     0         0         0B        0B

[exit=0]
```

### Docker/containerd root and data sizes

```console
$ sudo -n du -sh /var/lib/docker /var/lib/containerd '/data/docker' '/data/containerd' '/data/containerd/root' 2>/dev/null || true
236K	/data/docker
336K	/data/containerd

[exit=0]
```

### post-verification root-disk guard

```console
$ scripts/common/root-disk-guard.sh
PASS: root disk guard passed

[exit=0]
```

## Docker/containerd Verification Summary

- Docker installed: yes
- containerd installed: yes
- Docker Root Dir: /data/docker
- containerd root: /data/containerd/root
- containerd state: /run/containerd
- hello-world image present: yes
- root-disk guard: PASS

## Docker/containerd Verification Conclusion

PASS
### Docker storage verifier

```console
$ scripts/docker/verify-docker-storage.sh
PASS: Docker/containerd storage verified

[exit=0]
```

### os-release

```console
$ cat /etc/os-release
PRETTY_NAME="Ubuntu 24.04.4 LTS"
NAME="Ubuntu"
VERSION_ID="24.04"
VERSION="24.04.4 LTS (Noble Numbat)"
VERSION_CODENAME=noble
ID=ubuntu
ID_LIKE=debian
HOME_URL="https://www.ubuntu.com/"
SUPPORT_URL="https://help.ubuntu.com/"
BUG_REPORT_URL="https://bugs.launchpad.net/ubuntu/"
PRIVACY_POLICY_URL="https://www.ubuntu.com/legal/terms-and-policies/privacy-policy"
UBUNTU_CODENAME=noble
LOGO=ubuntu-logo

[exit=0]
```

### uname -a

```console
$ uname -a
Linux llmserver 6.8.0-134-generic #134-Ubuntu SMP PREEMPT_DYNAMIC Fri Jun 26 18:43:11 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux

[exit=0]
```

### lspci NVIDIA/display inventory

```console
$ lspci -nn | egrep -i 'nvidia|vga|3d|display' || true
00:01.0 VGA compatible controller [0300]: Device [1234:1111] (rev 02)
01:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
01:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)
02:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
02:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)

[exit=0]
```

### lspci driver binding summary

```console
$ lspci -nnk | egrep -A5 -i 'nvidia|vga|3d|display' || true
00:01.0 VGA compatible controller [0300]: Device [1234:1111] (rev 02)
	Subsystem: Red Hat, Inc. Device [1af4:1100]
	Kernel driver in use: bochs-drm
	Kernel modules: bochs
00:1a.0 USB controller [0c03]: Intel Corporation 82801I (ICH9 Family) USB UHCI Controller #4 [8086:2937] (rev 03)
	Subsystem: Red Hat, Inc. QEMU Virtual Machine [1af4:1100]
--
01:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
	Subsystem: NVIDIA Corporation Device [10de:204b]
	Kernel driver in use: nvidia
	Kernel modules: nvidiafb, nouveau, nvidia_drm, nvidia
01:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)
	Subsystem: NVIDIA Corporation Device [10de:0000]
	Kernel driver in use: snd_hda_intel
	Kernel modules: snd_hda_intel
02:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
	Subsystem: NVIDIA Corporation Device [10de:204b]
	Kernel driver in use: nvidia
	Kernel modules: nvidiafb, nouveau, nvidia_drm, nvidia
02:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)
	Subsystem: NVIDIA Corporation Device [10de:0000]
	Kernel driver in use: snd_hda_intel
	Kernel modules: snd_hda_intel
05:01.0 PCI bridge [0604]: Red Hat, Inc. QEMU PCI-PCI bridge [1b36:0001]
05:02.0 PCI bridge [0604]: Red Hat, Inc. QEMU PCI-PCI bridge [1b36:0001]
05:03.0 PCI bridge [0604]: Red Hat, Inc. QEMU PCI-PCI bridge [1b36:0001]

[exit=0]
```

### lsmod nvidia/nouveau/vfio summary

```console
$ lsmod | egrep 'nvidia|nouveau|vfio' || true
nvidia_uvm           2060288  0
nvidia_drm            139264  0
nvidia_modeset       1744896  1 nvidia_drm
nvidia              14794752  2 nvidia_uvm,nvidia_modeset
video                  77824  1 nvidia_modeset
ecc                    45056  1 nvidia

[exit=0]
```

### command -v nvidia-smi

```console
$ command -v nvidia-smi
/usr/bin/nvidia-smi

[exit=0]
```

### nvidia-smi

```console
$ nvidia-smi
Fri Jul  3 07:38:02 2026
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 595.71.05              Driver Version: 595.71.05      CUDA Version: 13.2     |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA RTX PRO 6000 Blac...    Off |   00000000:01:00.0 Off |                  Off |
| 30%   31C    P8             15W /  600W |       2MiB /  97887MiB |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+
|   1  NVIDIA RTX PRO 6000 Blac...    Off |   00000000:02:00.0 Off |                  Off |
| 30%   37C    P8             31W /  600W |      34MiB /  97887MiB |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+

+-----------------------------------------------------------------------------------------+
| Processes:                                                                              |
|  GPU   GI   CI              PID   Type   Process name                        GPU Memory |
|        ID   ID                                                               Usage      |
|=========================================================================================|
|  No running processes found                                                             |
+-----------------------------------------------------------------------------------------+

[exit=0]
```

### nvidia-smi -L

```console
$ nvidia-smi -L
GPU 0: NVIDIA RTX PRO 6000 Blackwell Workstation Edition (UUID: GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237)
GPU 1: NVIDIA RTX PRO 6000 Blackwell Workstation Edition (UUID: GPU-69acfa26-8b60-61b5-702d-aee252c163cc)

[exit=0]
```

### nvidia-smi query-gpu CSV

```console
$ nvidia-smi --query-gpu=index\,name\,pci.bus_id\,driver_version\,memory.total\,power.limit --format=csv
index, name, pci.bus_id, driver_version, memory.total [MiB], power.limit [W]
0, NVIDIA RTX PRO 6000 Blackwell Workstation Edition, 00000000:01:00.0, 595.71.05, 97887 MiB, 600.00 W
1, NVIDIA RTX PRO 6000 Blackwell Workstation Edition, 00000000:02:00.0, 595.71.05, 97887 MiB, 600.00 W

[exit=0]
```

### nvidia-smi topology

```console
$ nvidia-smi topo -m
	[4mGPU0	GPU1	CPU Affinity	NUMA Affinity	GPU NUMA ID[0m
GPU0	 X 	PHB	0-111	0-6		N/A
GPU1	PHB	 X 	0-111	0-6		N/A

Legend:

  X    = Self
  SYS  = Connection traversing PCIe as well as the SMP interconnect between NUMA nodes (e.g., QPI/UPI)
  NODE = Connection traversing PCIe as well as the interconnect between PCIe Host Bridges within a NUMA node
  PHB  = Connection traversing PCIe as well as a PCIe Host Bridge (typically the CPU)
  PXB  = Connection traversing multiple PCIe bridges (without traversing the PCIe Host Bridge)
  PIX  = Connection traversing at most a single PCIe bridge
  NV#  = Connection traversing a bonded set of # NVLinks

[exit=0]
```

### nvidia-smi requested MEMORY,PCI,POWER detail (unsupported PCI display flag in 595)

```console
$ nvidia-smi -q -d MEMORY\,PCI\,POWER
Failed to parse --display/-d flags

[exit=2]
```

### nvidia-smi full query for PCI detail

```console
$ nvidia-smi -q

==============NVSMI LOG==============

Timestamp                                              : Fri Jul  3 07:38:03 2026
Driver Version                                         : 595.71.05
CUDA Version                                           : 13.2

Attached GPUs                                          : 2
GPU 00000000:01:00.0
    Product Name                                       : NVIDIA RTX PRO 6000 Blackwell Workstation Edition
    Product Brand                                      : NVIDIA RTX
    Product Architecture                               : Blackwell
    Display Mode                                       : Requested functionality has been deprecated
    Display Attached                                   : No
    Display Active                                     : Disabled
    Persistence Mode                                   : Disabled
    Addressing Mode                                    : HMM
    MIG Mode
        Current                                        : N/A
        Pending                                        : N/A
    Accounting Mode                                    : Disabled
    Accounting Mode Buffer Size                        : 4000
    Driver Model
        Current                                        : N/A
        Pending                                        : N/A
    Serial Number                                      : 1792525050955
    GPU UUID                                           : GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237
    GPU PDI                                            : 0x2fc57a11785567f6
    Minor Number                                       : 0
    VBIOS Version                                      : 98.02.52.00.02
    MultiGPU Board                                     : No
    Board ID                                           : 0x100
    Board Part Number                                  : 900-5G144-2200-000
    GPU Part Number                                    : 2BB1-870-A1
    FRU Part Number                                    : N/A
    Platform Info
        Chassis Serial Number                          :
        Slot Number                                    : 0
        Tray Index                                     : 0
        Host ID                                        : 1
        Peer Type                                      : Direct Connected
        Module Id                                      : 1
        GPU Fabric GUID                                : 0x0000000000000000
    Inforom Version
        Image Version                                  : G144.0520.00.02
        OEM Object                                     : 2.1
        ECC Object                                     : 7.16
        Power Management Object                        : N/A
    Inforom BBX Object Flush
        Latest Timestamp                               : N/A
        Latest Duration                                : N/A
    GPU Operation Mode
        Current                                        : N/A
        Pending                                        : N/A
    GPU C2C Mode                                       : Disabled
    GPU Virtualization Mode
        Virtualization Mode                            : Pass-Through
        Host VGPU Mode                                 : N/A
        vGPU Heterogeneous Mode                        : N/A
    GPU Recovery Action                                : None
    GSP Firmware Version                               : 595.71.05
    IBMNPU
        Relaxed Ordering Mode                          : N/A
    PCI
        Bus                                            : 0x01
        Device                                         : 0x00
        Domain                                         : 0x0000
        Base Classcode                                 : 0x3
        Sub Classcode                                  : 0x0
        Device Id                                      : 0x2BB110DE
        Bus Id                                         : 00000000:01:00.0
        Sub System Id                                  : 0x204B10DE
        GPU Link Info
            PCIe Generation
                Max                                    : 5
                Current                                : 1
                Device Current                         : 1
                Device Max                             : 5
                Host Max                               : N/A
            Link Width
                Max                                    : 16x
                Current                                : 16x
        Bridge Chip
            Type                                       : N/A
            Firmware                                   : N/A
        Replays Since Reset                            : 0
        Replay Number Rollovers                        : 0
        Tx Throughput                                  : 886 KB/s
        Rx Throughput                                  : 487 KB/s
        Atomic Caps Outbound                           : N/A
        Atomic Caps Inbound                            : FETCHADD_32 FETCHADD_64 SWAP_32 SWAP_64 CAS_32 CAS_64
    Fan Speed                                          : 30 %
    Performance State                                  : P8
    Clocks Event Reasons
        Idle                                           : Not Active
        Applications Clocks Setting                    : Not Active
        SW Power Cap                                   : Not Active
        HW Slowdown                                    : Not Active
            HW Thermal Slowdown                        : Not Active
            HW Power Brake Slowdown                    : Not Active
        Sync Boost                                     : Not Active
        SW Thermal Slowdown                            : Not Active
        Display Clock Setting                          : Not Active
    Clocks Event Reasons Counters
        SW Power Capping                               : 200402 us
        Sync Boost                                     : 0 us
        SW Thermal Slowdown                            : 0 us
        HW Thermal Slowdown                            : 0 us
        HW Power Braking                               : 0 us
    Sparse Operation Mode                              : N/A
    FB Memory Usage
        Total                                          : 97887 MiB
        Reserved                                       : 638 MiB
        Used                                           : 2 MiB
        Free                                           : 97249 MiB
    BAR1 Memory Usage
        Total                                          : 131072 MiB
        Used                                           : 1 MiB
        Free                                           : 131071 MiB
    Conf Compute Protected Memory Usage
        Total                                          : 0 MiB
        Used                                           : 0 MiB
        Free                                           : 0 MiB
    Compute Mode                                       : Default
    Utilization
        GPU                                            : 0 %
        Memory                                         : 0 %
        Encoder                                        : 0 %
        Decoder                                        : 0 %
        JPEG                                           : 0 %
        OFA                                            : 0 %
    Encoder Stats
        Active Sessions                                : 0
        Average FPS                                    : 0
        Average Latency                                : 0
    FBC Stats
        Active Sessions                                : 0
        Average FPS                                    : 0
        Average Latency                                : 0
    DRAM Encryption Mode
        Current                                        : Disabled
        Pending                                        : Disabled
    ECC Mode
        Current                                        : Disabled
        Pending                                        : Disabled
    ECC Errors
        Volatile
            SRAM Correctable                           : N/A
            SRAM Uncorrectable Parity                  : N/A
            SRAM Uncorrectable SEC-DED                 : N/A
            DRAM Correctable                           : N/A
            DRAM Uncorrectable                         : N/A
        Aggregate
            SRAM Correctable                           : N/A
            SRAM Uncorrectable Parity                  : N/A
            SRAM Uncorrectable SEC-DED                 : N/A
            DRAM Correctable                           : N/A
            DRAM Uncorrectable                         : N/A
            SRAM Threshold Exceeded                    : N/A
        Aggregate Uncorrectable SRAM Sources
            SRAM L2                                    : N/A
            SRAM SM                                    : N/A
            SRAM Microcontroller                       : N/A
            SRAM PCIE                                  : N/A
            SRAM Other                                 : N/A
        Channel Repair Pending                         : No
        TPC Repair Pending                             : No
        Unrepairable Memory                            : N/A
    Retired Pages
        Single Bit ECC                                 : N/A
        Double Bit ECC                                 : N/A
        Pending Page Blacklist                         : N/A
    Remapped Rows
        Correctable Error                              : 0
        Inactive Correctable Error                     : 0
        Uncorrectable Error                            : 0
        Inactive Uncorrectable Error                   : 0
        Pending                                        : No
        Remapping Failure Occurred                     : No
        Bank Remap Availability Histogram
            Max                                        : 512 bank(s)
            High                                       : 0 bank(s)
            Partial                                    : 0 bank(s)
            Low                                        : 0 bank(s)
            None                                       : 0 bank(s)
    Temperature
        GPU Current Temp                               : 32 C
        GPU T.Limit Temp                               : 61 C
        GPU Shutdown T.Limit Temp                      : -5 C
        GPU Slowdown T.Limit Temp                      : -2 C
        GPU Max Operating T.Limit Temp                 : 0 C
        GPU Target Temperature                         : N/A
        Memory Current Temp                            : N/A
        Memory Max Operating T.Limit Temp              : N/A
    GPU Power Readings
        Average Power Draw                             : 16.61 W
        Instantaneous Power Draw                       : 16.61 W
        Current Power Limit                            : 600.00 W
        Requested Power Limit                          : 600.00 W
        Default Power Limit                            : 600.00 W
        Min Power Limit                                : 150.00 W
        Max Power Limit                                : 600.00 W
    GPU Memory Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
    Module Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
        Current Power Limit                            : N/A
        Requested Power Limit                          : N/A
        Default Power Limit                            : N/A
        Min Power Limit                                : N/A
        Max Power Limit                                : N/A
    Power Smoothing                                    : N/A
    Workload Power Profiles
        Requested Profiles                             : N/A
        Enforced Profiles                              : N/A
    EDPp Multiplier                                    : N/A
    Clocks
        Graphics                                       : 180 MHz
        SM                                             : 180 MHz
        Memory                                         : 405 MHz
        Video                                          : 600 MHz
    Applications Clocks
        Graphics                                       : Requested functionality has been deprecated
        Memory                                         : Requested functionality has been deprecated
    Default Applications Clocks
        Graphics                                       : Requested functionality has been deprecated
        Memory                                         : Requested functionality has been deprecated
    Deferred Clocks
        Memory                                         : N/A
    Max Clocks
        Graphics                                       : 3090 MHz
        SM                                             : 3090 MHz
        Memory                                         : 14001 MHz
        Video                                          : 3090 MHz
    Max Customer Boost Clocks
        Graphics                                       : N/A
    Clock Policy
        Auto Boost                                     : N/A
        Auto Boost Default                             : N/A
    Fabric
        State                                          : N/A
        Status                                         : N/A
        CliqueId                                       : N/A
        ClusterUUID                                    : N/A
        Health
            Summary                                    : N/A
            Bandwidth                                  : N/A
            Route Recovery in progress                 : N/A
            Route Unhealthy                            : N/A
            Access Timeout Recovery                    : N/A
            Incorrect Configuration                    : N/A
            Partition Assigned                         : N/A
    Processes                                          : None
    Capabilities
        EGM                                            : disabled

GPU 00000000:02:00.0
    Product Name                                       : NVIDIA RTX PRO 6000 Blackwell Workstation Edition
    Product Brand                                      : NVIDIA RTX
    Product Architecture                               : Blackwell
    Display Mode                                       : Requested functionality has been deprecated
    Display Attached                                   : Yes
    Display Active                                     : Disabled
    Persistence Mode                                   : Disabled
    Addressing Mode                                    : HMM
    MIG Mode
        Current                                        : N/A
        Pending                                        : N/A
    Accounting Mode                                    : Disabled
    Accounting Mode Buffer Size                        : 4000
    Driver Model
        Current                                        : N/A
        Pending                                        : N/A
    Serial Number                                      : 1792825000515
    GPU UUID                                           : GPU-69acfa26-8b60-61b5-702d-aee252c163cc
    GPU PDI                                            : 0x3802a64ab95f128c
    Minor Number                                       : 1
    VBIOS Version                                      : 98.02.52.00.02
    MultiGPU Board                                     : No
    Board ID                                           : 0x200
    Board Part Number                                  : 900-5G144-2200-000
    GPU Part Number                                    : 2BB1-870-A1
    FRU Part Number                                    : N/A
    Platform Info
        Chassis Serial Number                          :
        Slot Number                                    : 0
        Tray Index                                     : 0
        Host ID                                        : 1
        Peer Type                                      : Direct Connected
        Module Id                                      : 1
        GPU Fabric GUID                                : 0x0000000000000000
    Inforom Version
        Image Version                                  : G144.0520.00.02
        OEM Object                                     : 2.1
        ECC Object                                     : 7.16
        Power Management Object                        : N/A
    Inforom BBX Object Flush
        Latest Timestamp                               : N/A
        Latest Duration                                : N/A
    GPU Operation Mode
        Current                                        : N/A
        Pending                                        : N/A
    GPU C2C Mode                                       : Disabled
    GPU Virtualization Mode
        Virtualization Mode                            : Pass-Through
        Host VGPU Mode                                 : N/A
        vGPU Heterogeneous Mode                        : N/A
    GPU Recovery Action                                : None
    GSP Firmware Version                               : 595.71.05
    IBMNPU
        Relaxed Ordering Mode                          : N/A
    PCI
        Bus                                            : 0x02
        Device                                         : 0x00
        Domain                                         : 0x0000
        Base Classcode                                 : 0x3
        Sub Classcode                                  : 0x0
        Device Id                                      : 0x2BB110DE
        Bus Id                                         : 00000000:02:00.0
        Sub System Id                                  : 0x204B10DE
        GPU Link Info
            PCIe Generation
                Max                                    : 5
                Current                                : 1
                Device Current                         : 1
                Device Max                             : 5
                Host Max                               : N/A
            Link Width
                Max                                    : 16x
                Current                                : 16x
        Bridge Chip
            Type                                       : N/A
            Firmware                                   : N/A
        Replays Since Reset                            : 0
        Replay Number Rollovers                        : 0
        Tx Throughput                                  : 2456 KB/s
        Rx Throughput                                  : 488 KB/s
        Atomic Caps Outbound                           : N/A
        Atomic Caps Inbound                            : FETCHADD_32 FETCHADD_64 SWAP_32 SWAP_64 CAS_32 CAS_64
    Fan Speed                                          : 30 %
    Performance State                                  : P8
    Clocks Event Reasons
        Idle                                           : Not Active
        Applications Clocks Setting                    : Not Active
        SW Power Cap                                   : Not Active
        HW Slowdown                                    : Not Active
            HW Thermal Slowdown                        : Not Active
            HW Power Brake Slowdown                    : Not Active
        Sync Boost                                     : Not Active
        SW Thermal Slowdown                            : Not Active
        Display Clock Setting                          : Not Active
    Clocks Event Reasons Counters
        SW Power Capping                               : 200214 us
        Sync Boost                                     : 0 us
        SW Thermal Slowdown                            : 0 us
        HW Thermal Slowdown                            : 0 us
        HW Power Braking                               : 0 us
    Sparse Operation Mode                              : N/A
    FB Memory Usage
        Total                                          : 97887 MiB
        Reserved                                       : 638 MiB
        Used                                           : 34 MiB
        Free                                           : 97217 MiB
    BAR1 Memory Usage
        Total                                          : 131072 MiB
        Used                                           : 33 MiB
        Free                                           : 131039 MiB
    Conf Compute Protected Memory Usage
        Total                                          : 0 MiB
        Used                                           : 0 MiB
        Free                                           : 0 MiB
    Compute Mode                                       : Default
    Utilization
        GPU                                            : 0 %
        Memory                                         : 0 %
        Encoder                                        : 0 %
        Decoder                                        : 0 %
        JPEG                                           : 0 %
        OFA                                            : 0 %
    Encoder Stats
        Active Sessions                                : 0
        Average FPS                                    : 0
        Average Latency                                : 0
    FBC Stats
        Active Sessions                                : 0
        Average FPS                                    : 0
        Average Latency                                : 0
    DRAM Encryption Mode
        Current                                        : Disabled
        Pending                                        : Disabled
    ECC Mode
        Current                                        : Disabled
        Pending                                        : Disabled
    ECC Errors
        Volatile
            SRAM Correctable                           : N/A
            SRAM Uncorrectable Parity                  : N/A
            SRAM Uncorrectable SEC-DED                 : N/A
            DRAM Correctable                           : N/A
            DRAM Uncorrectable                         : N/A
        Aggregate
            SRAM Correctable                           : N/A
            SRAM Uncorrectable Parity                  : N/A
            SRAM Uncorrectable SEC-DED                 : N/A
            DRAM Correctable                           : N/A
            DRAM Uncorrectable                         : N/A
            SRAM Threshold Exceeded                    : N/A
        Aggregate Uncorrectable SRAM Sources
            SRAM L2                                    : N/A
            SRAM SM                                    : N/A
            SRAM Microcontroller                       : N/A
            SRAM PCIE                                  : N/A
            SRAM Other                                 : N/A
        Channel Repair Pending                         : No
        TPC Repair Pending                             : No
        Unrepairable Memory                            : N/A
    Retired Pages
        Single Bit ECC                                 : N/A
        Double Bit ECC                                 : N/A
        Pending Page Blacklist                         : N/A
    Remapped Rows
        Correctable Error                              : 0
        Inactive Correctable Error                     : 0
        Uncorrectable Error                            : 0
        Inactive Uncorrectable Error                   : 0
        Pending                                        : No
        Remapping Failure Occurred                     : No
        Bank Remap Availability Histogram
            Max                                        : 512 bank(s)
            High                                       : 0 bank(s)
            Partial                                    : 0 bank(s)
            Low                                        : 0 bank(s)
            None                                       : 0 bank(s)
    Temperature
        GPU Current Temp                               : 37 C
        GPU T.Limit Temp                               : 56 C
        GPU Shutdown T.Limit Temp                      : -5 C
        GPU Slowdown T.Limit Temp                      : -2 C
        GPU Max Operating T.Limit Temp                 : 0 C
        GPU Target Temperature                         : N/A
        Memory Current Temp                            : N/A
        Memory Max Operating T.Limit Temp              : N/A
    GPU Power Readings
        Average Power Draw                             : 31.82 W
        Instantaneous Power Draw                       : 31.82 W
        Current Power Limit                            : 600.00 W
        Requested Power Limit                          : 600.00 W
        Default Power Limit                            : 600.00 W
        Min Power Limit                                : 150.00 W
        Max Power Limit                                : 600.00 W
    GPU Memory Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
    Module Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
        Current Power Limit                            : N/A
        Requested Power Limit                          : N/A
        Default Power Limit                            : N/A
        Min Power Limit                                : N/A
        Max Power Limit                                : N/A
    Power Smoothing                                    : N/A
    Workload Power Profiles
        Requested Profiles                             : N/A
        Enforced Profiles                              : N/A
    EDPp Multiplier                                    : N/A
    Clocks
        Graphics                                       : 180 MHz
        SM                                             : 180 MHz
        Memory                                         : 405 MHz
        Video                                          : 600 MHz
    Applications Clocks
        Graphics                                       : Requested functionality has been deprecated
        Memory                                         : Requested functionality has been deprecated
    Default Applications Clocks
        Graphics                                       : Requested functionality has been deprecated
        Memory                                         : Requested functionality has been deprecated
    Deferred Clocks
        Memory                                         : N/A
    Max Clocks
        Graphics                                       : 3090 MHz
        SM                                             : 3090 MHz
        Memory                                         : 14001 MHz
        Video                                          : 3090 MHz
    Max Customer Boost Clocks
        Graphics                                       : N/A
    Clock Policy
        Auto Boost                                     : N/A
        Auto Boost Default                             : N/A
    Fabric
        State                                          : N/A
        Status                                         : N/A
        CliqueId                                       : N/A
        ClusterUUID                                    : N/A
        Health
            Summary                                    : N/A
            Bandwidth                                  : N/A
            Route Recovery in progress                 : N/A
            Route Unhealthy                            : N/A
            Access Timeout Recovery                    : N/A
            Incorrect Configuration                    : N/A
            Partition Assigned                         : N/A
    Processes                                          : None
    Capabilities
        EGM                                            : disabled


[exit=0]
```

### nvidia-smi memory detail

```console
$ nvidia-smi -q -d MEMORY

==============NVSMI LOG==============

Timestamp                                              : Fri Jul  3 07:38:03 2026
Driver Version                                         : 595.71.05
CUDA Version                                           : 13.2

Attached GPUs                                          : 2
GPU 00000000:01:00.0
    FB Memory Usage
        Total                                          : 97887 MiB
        Reserved                                       : 638 MiB
        Used                                           : 2 MiB
        Free                                           : 97249 MiB
    BAR1 Memory Usage
        Total                                          : 131072 MiB
        Used                                           : 1 MiB
        Free                                           : 131071 MiB
    Conf Compute Protected Memory Usage
        Total                                          : 0 MiB
        Used                                           : 0 MiB
        Free                                           : 0 MiB

GPU 00000000:02:00.0
    FB Memory Usage
        Total                                          : 97887 MiB
        Reserved                                       : 638 MiB
        Used                                           : 34 MiB
        Free                                           : 97217 MiB
    BAR1 Memory Usage
        Total                                          : 131072 MiB
        Used                                           : 33 MiB
        Free                                           : 131039 MiB
    Conf Compute Protected Memory Usage
        Total                                          : 0 MiB
        Used                                           : 0 MiB
        Free                                           : 0 MiB


[exit=0]
```

### nvidia-smi power detail

```console
$ nvidia-smi -q -d POWER

==============NVSMI LOG==============

Timestamp                                              : Fri Jul  3 07:38:03 2026
Driver Version                                         : 595.71.05
CUDA Version                                           : 13.2

Attached GPUs                                          : 2
GPU 00000000:01:00.0
    GPU Power Readings
        Average Power Draw                             : 16.61 W
        Instantaneous Power Draw                       : 16.61 W
        Current Power Limit                            : 600.00 W
        Requested Power Limit                          : 600.00 W
        Default Power Limit                            : 600.00 W
        Min Power Limit                                : 150.00 W
        Max Power Limit                                : 600.00 W
    Power Samples
        Duration                                       : 118.00 sec
        Number of Samples                              : 119
        Max                                            : 17.80 W
        Min                                            : 14.77 W
        Avg                                            : 15.04 W
    GPU Memory Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
    Module Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
        Current Power Limit                            : N/A
        Requested Power Limit                          : N/A
        Default Power Limit                            : N/A
        Min Power Limit                                : N/A
        Max Power Limit                                : N/A
    EDPp Multiplier                                    : N/A

GPU 00000000:02:00.0
    GPU Power Readings
        Average Power Draw                             : 31.82 W
        Instantaneous Power Draw                       : 31.82 W
        Current Power Limit                            : 600.00 W
        Requested Power Limit                          : 600.00 W
        Default Power Limit                            : 600.00 W
        Min Power Limit                                : 150.00 W
        Max Power Limit                                : 600.00 W
    Power Samples
        Duration                                       : 118.01 sec
        Number of Samples                              : 119
        Max                                            : 33.02 W
        Min                                            : 31.65 W
        Avg                                            : 32.32 W
    GPU Memory Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
    Module Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
        Current Power Limit                            : N/A
        Requested Power Limit                          : N/A
        Default Power Limit                            : N/A
        Min Power Limit                                : N/A
        Max Power Limit                                : N/A
    EDPp Multiplier                                    : N/A


[exit=0]
```

### nvcc after reboot

```console
$ command -v nvcc || true; nvcc --version || true
bash: line 1: nvcc: command not found

[exit=0]
```

### Installed NVIDIA/CUDA/container-toolkit packages after reboot

```console
$ dpkg -l | egrep 'nvidia|cuda|container-toolkit' || true
ii  libnvidia-cfg1-595:amd64              595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA binary OpenGL/GLX configuration library
ii  libnvidia-common-595                  595.71.05-0ubuntu0.24.04.1                       amd64        Shared files used by the NVIDIA libraries
ii  libnvidia-compute-595:amd64           595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA libcompute package
ii  libnvidia-decode-595:amd64            595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA Video Decoding runtime libraries
ii  libnvidia-egl-wayland1:amd64          1:1.1.13-1ubuntu0.1                              amd64        Wayland EGL External Platform library -- shared library
ii  libnvidia-encode-595:amd64            595.71.05-0ubuntu0.24.04.1                       amd64        NVENC Video Encoding runtime library
ii  libnvidia-extra-595:amd64             595.71.05-0ubuntu0.24.04.1                       amd64        Extra libraries for the NVIDIA driver
ii  libnvidia-fbc1-595:amd64              595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA OpenGL-based Framebuffer Capture runtime library
ii  libnvidia-gl-595:amd64                595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA OpenGL/GLX/EGL/GLES GLVND libraries and Vulkan ICD
ii  nvidia-compute-utils-595              595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA compute utilities
ii  nvidia-dkms-595-open                  595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA DKMS package (open kernel module)
ii  nvidia-driver-595-open                595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA driver (open kernel) metapackage
ii  nvidia-firmware-595-595.71.05         595.71.05-0ubuntu0.24.04.1                       amd64        Firmware files used by the kernel module
ii  nvidia-kernel-common-595              595.71.05-0ubuntu0.24.04.1                       amd64        Shared files used with the kernel module
ii  nvidia-kernel-source-595-open         595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA kernel source package
ii  nvidia-prime                          0.8.17.2                                         all          Tools to enable NVIDIA's Prime
ii  nvidia-settings                       510.47.03-0ubuntu4.24.04.1                       amd64        Tool for configuring the NVIDIA graphics driver
ii  nvidia-utils-595                      595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA driver support binaries
ii  screen-resolution-extra               0.18.3ubuntu0.24.04.1                            all          Extension for the nvidia-settings control panel
ii  xserver-xorg-video-nvidia-595         595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA binary Xorg driver

[exit=0]
```

### Docker Root Dir and containerd info

```console
$ sudo -n docker info | egrep 'Docker Root Dir|Storage Driver|containerd' || true
 Storage Driver: overlayfs
  driver-type: io.containerd.snapshotter.v1
 Runtimes: io.containerd.runc.v2 runc
 containerd version: e53c7c1516c3b2bff98eb76f1f4117477e6f4e66
 Docker Root Dir: /data/docker

[exit=0]
```

### Docker/containerd path sizes

```console
$ sudo -n du -sh /var/lib/docker /var/lib/containerd /data/docker /data/containerd /data/containerd/root 2>/dev/null || true
236K	/data/docker
336K	/data/containerd

[exit=0]
```

## M5B Post-reboot Validation Summary

- nvidia-smi: PASS
- GPU count: 2
- GPU names: NVIDIA RTX PRO 6000 Blackwell Workstation Edition (UUID;NVIDIA RTX PRO 6000 Blackwell Workstation Edition (UUID

- Query CSV:

```csv
0, NVIDIA RTX PRO 6000 Blackwell Workstation Edition, 00000000:01:00.0, 595.71.05, 97887 MiB, 600.00 W
1, NVIDIA RTX PRO 6000 Blackwell Workstation Edition, 00000000:02:00.0, 595.71.05, 97887 MiB, 600.00 W
```

- nouveau loaded/bound: not bound to NVIDIA GPUs; see lsmod/lspci sections above.
- nvidia modules loaded: PASS
- nvcc: absent
- CUDA Toolkit packages: absent
- NVIDIA Container Toolkit packages: absent
- Docker Root Dir: /data/docker
- containerd root: /data/containerd/root
- containerd state: /run/containerd
- /data guard: PASS
- root-disk guard: PASS
- Docker storage verifier: PASS
- Scope confirmation: CUDA Toolkit, PyTorch, KTransformers, ik_llama, NVIDIA Container Toolkit, models, Docker NVIDIA runtime, Docker/containerd configuration, and API exposure were not installed or configured by M5B.
- Manual Proxmox host checks still required: VFIO/PCIe/AER/reset logs plus VM config/status checks outside Codex.

## M5B Post-reboot Conclusion

PASS
### git diff --check

```console
$ git diff --check
reports/m5b-nvidia-host-driver.md:3111: trailing whitespace.
+Fri Jul  3 07:35:55 2026
reports/m5b-nvidia-host-driver.md:3721: trailing whitespace.
+Fri Jul  3 07:37:28 2026
reports/m5b-nvidia-host-driver.md:3840: trailing whitespace.
+        Chassis Serial Number                          :
reports/m5b-nvidia-host-driver.md:3894: trailing whitespace.
+        Atomic Caps Inbound                            : FETCHADD_32 FETCHADD_64 SWAP_32 SWAP_64 CAS_32 CAS_64
reports/m5b-nvidia-host-driver.md:4006: trailing whitespace.
+    GPU Memory Power Readings
reports/m5b-nvidia-host-driver.md:4090: trailing whitespace.
+        Chassis Serial Number                          :
reports/m5b-nvidia-host-driver.md:4144: trailing whitespace.
+        Atomic Caps Inbound                            : FETCHADD_32 FETCHADD_64 SWAP_32 SWAP_64 CAS_32 CAS_64
reports/m5b-nvidia-host-driver.md:4256: trailing whitespace.
+    GPU Memory Power Readings
reports/m5b-nvidia-host-driver.md:4389: trailing whitespace.
+    GPU Memory Power Readings
reports/m5b-nvidia-host-driver.md:4417: trailing whitespace.
+    GPU Memory Power Readings
reports/m5b-nvidia-host-driver.md:5025: trailing whitespace.
+Fri Jul  3 07:38:02 2026
reports/m5b-nvidia-host-driver.md:5144: trailing whitespace.
+        Chassis Serial Number                          :
reports/m5b-nvidia-host-driver.md:5198: trailing whitespace.
+        Atomic Caps Inbound                            : FETCHADD_32 FETCHADD_64 SWAP_32 SWAP_64 CAS_32 CAS_64
reports/m5b-nvidia-host-driver.md:5310: trailing whitespace.
+    GPU Memory Power Readings
reports/m5b-nvidia-host-driver.md:5394: trailing whitespace.
+        Chassis Serial Number                          :
reports/m5b-nvidia-host-driver.md:5448: trailing whitespace.
+        Atomic Caps Inbound                            : FETCHADD_32 FETCHADD_64 SWAP_32 SWAP_64 CAS_32 CAS_64
reports/m5b-nvidia-host-driver.md:5560: trailing whitespace.
+    GPU Memory Power Readings
reports/m5b-nvidia-host-driver.md:5693: trailing whitespace.
+    GPU Memory Power Readings
reports/m5b-nvidia-host-driver.md:5721: trailing whitespace.
+    GPU Memory Power Readings

[exit=2]
```

## M5B Post-reboot Conclusion

STOP

Reason: git diff --check failed

Manual Proxmox VFIO/AER/reset checks are still required outside Codex.

# M5B post-reboot NVIDIA driver verification

- Timestamp: 2026-07-03T07:38:41+00:00
- Hostname: llmserver
- Uptime: up 3 minutes
- Runner: /data/services/m5b-post-reboot/m5b-post-reboot-verify.sh
- Log: /data/logs/m5b-post-reboot-verify.log

### hostname

```console
$ hostname
llmserver

[exit=0]
```

### uptime

```console
$ uptime
 07:38:41 up 3 min,  3 users,  load average: 0.26, 0.15, 0.06

[exit=0]
```

### date -Is

```console
$ date -Is
2026-07-03T07:38:41+00:00

[exit=0]
```

### require-data-mounted

```console
$ scripts/common/require-data-mounted.sh
PASS: /data is mounted and ready
- root source: /dev/mapper/ubuntu--vg-ubuntu--lv
- data source: /dev/sdb1
- data fstype: ext4
- data label: AI_DATA
- data UUID: 8daf56f1-5649-4163-9d87-919c2d271875

[exit=0]
```

### root-disk-guard

```console
$ scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md
PASS: root disk guard passed

[exit=0]
```


## Docker/containerd Storage Verification

- Timestamp: 2026-07-03T07:38:42+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m5b-nvidia-host-driver

### require /data mounted

```console
$ scripts/common/require-data-mounted.sh
PASS: /data is mounted and ready
- root source: /dev/mapper/ubuntu--vg-ubuntu--lv
- data source: /dev/sdb1
- data fstype: ext4
- data label: AI_DATA
- data UUID: 8daf56f1-5649-4163-9d87-919c2d271875

[exit=0]
```

### pre-verification root-disk guard

```console
$ scripts/common/root-disk-guard.sh
PASS: root disk guard passed

[exit=0]
```

### df -hT / /data

```console
$ df -hT / /data
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  8.9G  4.6G  66% /
/dev/sdb1                         ext4  2.0T  3.5M  1.9T   1% /data

[exit=0]
```

### /var/lib Docker/containerd size summary

| Path | MiB | Policy |
| --- | ---: | --- |
| `/var/lib/docker` | 0 | absent/empty/small or documented |
| `/var/lib/containerd` | 0 | absent/empty/small or documented |

### systemctl is-active containerd

```console
$ sudo -n systemctl is-active containerd
active

[exit=0]
```

### systemctl is-active docker

```console
$ sudo -n systemctl is-active docker
active

[exit=0]
```

### systemctl status containerd

```console
$ sudo -n systemctl status containerd --no-pager
● containerd.service - containerd container runtime
     Loaded: loaded (/usr/lib/systemd/system/containerd.service; enabled; preset: enabled)
     Active: active (running) since Fri 2026-07-03 07:35:25 UTC; 3min 17s ago
       Docs: https://containerd.io
   Main PID: 2091 (containerd)
      Tasks: 30
     Memory: 84.1M (peak: 86.7M)
        CPU: 542ms
     CGroup: /system.slice/containerd.service
             └─2091 /usr/bin/containerd

Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875859853Z" level=info msg="Start cni network conf syncer for default"
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875865272Z" level=info msg="Start streaming server"
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875873444Z" level=info msg="Registered namespace \"k8s.io\" with NRI"
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875878251Z" level=info msg="runtime interface starting up..."
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875881666Z" level=info msg="starting plugins..."
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875890109Z" level=info msg="Synchronizing NRI (plugin) with current runtime state"
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875902768Z" level=info msg=serving... address=/run/containerd/containerd.sock.ttrpc
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875941546Z" level=info msg=serving... address=/run/containerd/containerd.sock
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.876173504Z" level=info msg="containerd successfully booted in 0.033839s"
Jul 03 07:35:25 llmserver systemd[1]: Started containerd.service - containerd container runtime.

[exit=0]
```

### systemctl status docker

```console
$ sudo -n systemctl status docker --no-pager
● docker.service - Docker Application Container Engine
     Loaded: loaded (/usr/lib/systemd/system/docker.service; enabled; preset: enabled)
     Active: active (running) since Fri 2026-07-03 07:35:28 UTC; 3min 14s ago
TriggeredBy: ● docker.socket
       Docs: https://docs.docker.com
   Main PID: 2261 (dockerd)
      Tasks: 41
     Memory: 119.6M (peak: 126.1M)
        CPU: 607ms
     CGroup: /system.slice/docker.service
             └─2261 /usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock

Jul 03 07:35:27 llmserver dockerd[2261]: time="2026-07-03T07:35:27.673114630Z" level=info msg="Restoring containers: start."
Jul 03 07:35:27 llmserver dockerd[2261]: time="2026-07-03T07:35:27.775998332Z" level=info msg="Deleting nftables IPv4 rules" error="running nft: /dev/stdin:1:17-30: Error: Could not process rule: No such file or directory\ndelete table ip docker-bridges\n                ^^^^^^^^^^^^^^\n exit status 1"
Jul 03 07:35:27 llmserver dockerd[2261]: time="2026-07-03T07:35:27.788141528Z" level=info msg="Deleting nftables IPv6 rules" error="running nft: /dev/stdin:1:18-31: Error: Could not process rule: No such file or directory\ndelete table ip6 docker-bridges\n                 ^^^^^^^^^^^^^^\n exit status 1"
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.052444560Z" level=info msg="Loading containers: done."
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.058049123Z" level=info msg="Docker daemon" commit=8ec5ab3 containerd-snapshotter=true storage-driver=overlayfs version=29.6.1
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.058280870Z" level=info msg="Initializing buildkit"
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.220160582Z" level=info msg="Completed buildkit initialization"
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.224043800Z" level=info msg="Daemon has completed initialization"
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.224122648Z" level=info msg="API listen on /run/docker.sock"
Jul 03 07:35:28 llmserver systemd[1]: Started docker.service - Docker Application Container Engine.

[exit=0]
```

### sudo docker version

```console
$ sudo -n docker version
Client: Docker Engine - Community
 Version:           29.6.1
 API version:       1.55
 Go version:        go1.26.4
 Git commit:        8900f1d
 Built:             Fri Jun 26 11:40:19 2026
 OS/Arch:           linux/amd64
 Context:           default

Server: Docker Engine - Community
 Engine:
  Version:          29.6.1
  API version:      1.55 (minimum version 1.40)
  Go version:       go1.26.4
  Git commit:       8ec5ab3
  Built:            Fri Jun 26 11:40:19 2026
  OS/Arch:          linux/amd64
  Experimental:     false
 containerd:
  Version:          v2.2.5
  GitCommit:        e53c7c1516c3b2bff98eb76f1f4117477e6f4e66
 runc:
  Version:          1.3.6
  GitCommit:        v1.3.6-0-g491b69ba
 docker-init:
  Version:          0.19.0
  GitCommit:        de40ad0

[exit=0]
```

### sudo docker info

```console
$ sudo -n docker info
Client: Docker Engine - Community
 Version:    29.6.1
 Context:    default
 Debug Mode: false
 Plugins:
  buildx: Docker Buildx (Docker Inc.)
    Version:  v0.35.0
    Path:     /usr/libexec/docker/cli-plugins/docker-buildx
  compose: Docker Compose (Docker Inc.)
    Version:  v5.3.0
    Path:     /usr/libexec/docker/cli-plugins/docker-compose

Server:
 Containers: 0
  Running: 0
  Paused: 0
  Stopped: 0
 Images: 1
 Server Version: 29.6.1
 Storage Driver: overlayfs
  driver-type: io.containerd.snapshotter.v1
 Logging Driver: json-file
 Cgroup Driver: systemd
 Cgroup Version: 2
 Plugins:
  Volume: local
  Network: bridge host ipvlan macvlan null overlay
  Log: awslogs fluentd gcplogs gelf journald json-file local splunk syslog
 CDI spec directories:
  /etc/cdi
  /var/run/cdi
 Swarm: inactive
 Runtimes: io.containerd.runc.v2 runc
 Default Runtime: runc
 Init Binary: docker-init
 containerd version: e53c7c1516c3b2bff98eb76f1f4117477e6f4e66
 runc version: v1.3.6-0-g491b69ba
 init version: de40ad0
 Security Options:
  apparmor
  seccomp
   Profile: builtin
  cgroupns
 Kernel Version: 6.8.0-134-generic
 Operating System: Ubuntu 24.04.4 LTS
 OSType: linux
 Architecture: x86_64
 CPUs: 112
 Total Memory: 881.8GiB
 Name: llmserver
 ID: fba62709-52b6-4594-98a7-b3a7e2626f3b
 Docker Root Dir: /data/docker
 Debug Mode: false
 Experimental: false
 Insecure Registries:
  ::1/128
  127.0.0.0/8
 Live Restore Enabled: false
 Firewall Backend: iptables
  EnableUserlandProxy: true
  UserlandProxyPath: /usr/bin/docker-proxy


[exit=0]
```

### sudo docker compose version

```console
$ sudo -n docker compose version
Docker Compose version v5.3.0

[exit=0]
```

### sudo docker buildx version

```console
$ sudo -n docker buildx version
github.com/docker/buildx v0.35.0 a319e5b15052cf6557ceb666eb8ff6e32380b782

[exit=0]
```

### hello-world image inspect

```console
$ sudo -n docker image inspect hello-world:latest
[
    {
        "Id": "sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d",
        "RepoTags": [
            "hello-world:latest"
        ],
        "RepoDigests": [
            "hello-world@sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d"
        ],
        "Comment": "buildkit.dockerfile.v0",
        "Created": "2026-03-23T21:33:59.562202219Z",
        "Config": {
            "Env": [
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            ],
            "Cmd": [
                "/hello"
            ],
            "WorkingDir": "/"
        },
        "Architecture": "amd64",
        "Os": "linux",
        "Size": 16227,
        "RootFS": {
            "Type": "layers",
            "Layers": [
                "sha256:897b3f2a7c1bc2f3d02432f7892fe31c6272c521ad4d70257df624504a3238b4"
            ]
        },
        "Metadata": {
            "LastTagTime": "2026-07-02T19:39:50.349224487Z"
        },
        "Descriptor": {
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "digest": "sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d",
            "size": 12212
        },
        "Identity": {
            "Pull": [
                {
                    "Repository": "docker.io/library/hello-world"
                }
            ]
        }
    }
]

[exit=0]
```

### sudo docker system df

```console
$ sudo -n docker system df
TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          1         0         38.09kB   25.87kB (67%)
Containers      0         0         0B        0B
Local Volumes   0         0         0B        0B
Build Cache     0         0         0B        0B

[exit=0]
```

### Docker/containerd root and data sizes

```console
$ sudo -n du -sh /var/lib/docker /var/lib/containerd '/data/docker' '/data/containerd' '/data/containerd/root' 2>/dev/null || true
236K	/data/docker
336K	/data/containerd

[exit=0]
```

### post-verification root-disk guard

```console
$ scripts/common/root-disk-guard.sh
PASS: root disk guard passed

[exit=0]
```

## Docker/containerd Verification Summary

- Docker installed: yes
- containerd installed: yes
- Docker Root Dir: /data/docker
- containerd root: /data/containerd/root
- containerd state: /run/containerd
- hello-world image present: yes
- root-disk guard: PASS

## Docker/containerd Verification Conclusion

PASS
### Docker storage verifier

```console
$ scripts/docker/verify-docker-storage.sh
PASS: Docker/containerd storage verified

[exit=0]
```

### os-release

```console
$ cat /etc/os-release
PRETTY_NAME="Ubuntu 24.04.4 LTS"
NAME="Ubuntu"
VERSION_ID="24.04"
VERSION="24.04.4 LTS (Noble Numbat)"
VERSION_CODENAME=noble
ID=ubuntu
ID_LIKE=debian
HOME_URL="https://www.ubuntu.com/"
SUPPORT_URL="https://help.ubuntu.com/"
BUG_REPORT_URL="https://bugs.launchpad.net/ubuntu/"
PRIVACY_POLICY_URL="https://www.ubuntu.com/legal/terms-and-policies/privacy-policy"
UBUNTU_CODENAME=noble
LOGO=ubuntu-logo

[exit=0]
```

### uname -a

```console
$ uname -a
Linux llmserver 6.8.0-134-generic #134-Ubuntu SMP PREEMPT_DYNAMIC Fri Jun 26 18:43:11 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux

[exit=0]
```

### lspci NVIDIA/display inventory

```console
$ lspci -nn | egrep -i 'nvidia|vga|3d|display' || true
00:01.0 VGA compatible controller [0300]: Device [1234:1111] (rev 02)
01:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
01:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)
02:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
02:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)

[exit=0]
```

### lspci driver binding summary

```console
$ lspci -nnk | egrep -A5 -i 'nvidia|vga|3d|display' || true
00:01.0 VGA compatible controller [0300]: Device [1234:1111] (rev 02)
	Subsystem: Red Hat, Inc. Device [1af4:1100]
	Kernel driver in use: bochs-drm
	Kernel modules: bochs
00:1a.0 USB controller [0c03]: Intel Corporation 82801I (ICH9 Family) USB UHCI Controller #4 [8086:2937] (rev 03)
	Subsystem: Red Hat, Inc. QEMU Virtual Machine [1af4:1100]
--
01:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
	Subsystem: NVIDIA Corporation Device [10de:204b]
	Kernel driver in use: nvidia
	Kernel modules: nvidiafb, nouveau, nvidia_drm, nvidia
01:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)
	Subsystem: NVIDIA Corporation Device [10de:0000]
	Kernel driver in use: snd_hda_intel
	Kernel modules: snd_hda_intel
02:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
	Subsystem: NVIDIA Corporation Device [10de:204b]
	Kernel driver in use: nvidia
	Kernel modules: nvidiafb, nouveau, nvidia_drm, nvidia
02:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)
	Subsystem: NVIDIA Corporation Device [10de:0000]
	Kernel driver in use: snd_hda_intel
	Kernel modules: snd_hda_intel
05:01.0 PCI bridge [0604]: Red Hat, Inc. QEMU PCI-PCI bridge [1b36:0001]
05:02.0 PCI bridge [0604]: Red Hat, Inc. QEMU PCI-PCI bridge [1b36:0001]
05:03.0 PCI bridge [0604]: Red Hat, Inc. QEMU PCI-PCI bridge [1b36:0001]

[exit=0]
```

### lsmod nvidia/nouveau/vfio summary

```console
$ lsmod | egrep 'nvidia|nouveau|vfio' || true
nvidia_uvm           2060288  0
nvidia_drm            139264  0
nvidia_modeset       1744896  1 nvidia_drm
nvidia              14794752  2 nvidia_uvm,nvidia_modeset
video                  77824  1 nvidia_modeset
ecc                    45056  1 nvidia

[exit=0]
```

### command -v nvidia-smi

```console
$ command -v nvidia-smi
/usr/bin/nvidia-smi

[exit=0]
```

### nvidia-smi

```console
$ nvidia-smi
Fri Jul  3 07:38:44 2026
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 595.71.05              Driver Version: 595.71.05      CUDA Version: 13.2     |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA RTX PRO 6000 Blac...    Off |   00000000:01:00.0 Off |                  Off |
| 30%   31C    P8             15W /  600W |       2MiB /  97887MiB |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+
|   1  NVIDIA RTX PRO 6000 Blac...    Off |   00000000:02:00.0 Off |                  Off |
| 30%   37C    P8             31W /  600W |      34MiB /  97887MiB |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+

+-----------------------------------------------------------------------------------------+
| Processes:                                                                              |
|  GPU   GI   CI              PID   Type   Process name                        GPU Memory |
|        ID   ID                                                               Usage      |
|=========================================================================================|
|  No running processes found                                                             |
+-----------------------------------------------------------------------------------------+

[exit=0]
```

### nvidia-smi -L

```console
$ nvidia-smi -L
GPU 0: NVIDIA RTX PRO 6000 Blackwell Workstation Edition (UUID: GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237)
GPU 1: NVIDIA RTX PRO 6000 Blackwell Workstation Edition (UUID: GPU-69acfa26-8b60-61b5-702d-aee252c163cc)

[exit=0]
```

### nvidia-smi query-gpu CSV

```console
$ nvidia-smi --query-gpu=index\,name\,pci.bus_id\,driver_version\,memory.total\,power.limit --format=csv
index, name, pci.bus_id, driver_version, memory.total [MiB], power.limit [W]
0, NVIDIA RTX PRO 6000 Blackwell Workstation Edition, 00000000:01:00.0, 595.71.05, 97887 MiB, 600.00 W
1, NVIDIA RTX PRO 6000 Blackwell Workstation Edition, 00000000:02:00.0, 595.71.05, 97887 MiB, 600.00 W

[exit=0]
```

### nvidia-smi topology

```console
$ nvidia-smi topo -m
	[4mGPU0	GPU1	CPU Affinity	NUMA Affinity	GPU NUMA ID[0m
GPU0	 X 	PHB	0-111	0-6		N/A
GPU1	PHB	 X 	0-111	0-6		N/A

Legend:

  X    = Self
  SYS  = Connection traversing PCIe as well as the SMP interconnect between NUMA nodes (e.g., QPI/UPI)
  NODE = Connection traversing PCIe as well as the interconnect between PCIe Host Bridges within a NUMA node
  PHB  = Connection traversing PCIe as well as a PCIe Host Bridge (typically the CPU)
  PXB  = Connection traversing multiple PCIe bridges (without traversing the PCIe Host Bridge)
  PIX  = Connection traversing at most a single PCIe bridge
  NV#  = Connection traversing a bonded set of # NVLinks

[exit=0]
```

### nvidia-smi requested MEMORY,PCI,POWER detail (unsupported PCI display flag in 595)

```console
$ nvidia-smi -q -d MEMORY\,PCI\,POWER
Failed to parse --display/-d flags

[exit=2]
```

### nvidia-smi full query for PCI detail

```console
$ nvidia-smi -q

==============NVSMI LOG==============

Timestamp                                              : Fri Jul  3 07:38:44 2026
Driver Version                                         : 595.71.05
CUDA Version                                           : 13.2

Attached GPUs                                          : 2
GPU 00000000:01:00.0
    Product Name                                       : NVIDIA RTX PRO 6000 Blackwell Workstation Edition
    Product Brand                                      : NVIDIA RTX
    Product Architecture                               : Blackwell
    Display Mode                                       : Requested functionality has been deprecated
    Display Attached                                   : No
    Display Active                                     : Disabled
    Persistence Mode                                   : Disabled
    Addressing Mode                                    : HMM
    MIG Mode
        Current                                        : N/A
        Pending                                        : N/A
    Accounting Mode                                    : Disabled
    Accounting Mode Buffer Size                        : 4000
    Driver Model
        Current                                        : N/A
        Pending                                        : N/A
    Serial Number                                      : 1792525050955
    GPU UUID                                           : GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237
    GPU PDI                                            : 0x2fc57a11785567f6
    Minor Number                                       : 0
    VBIOS Version                                      : 98.02.52.00.02
    MultiGPU Board                                     : No
    Board ID                                           : 0x100
    Board Part Number                                  : 900-5G144-2200-000
    GPU Part Number                                    : 2BB1-870-A1
    FRU Part Number                                    : N/A
    Platform Info
        Chassis Serial Number                          :
        Slot Number                                    : 0
        Tray Index                                     : 0
        Host ID                                        : 1
        Peer Type                                      : Direct Connected
        Module Id                                      : 1
        GPU Fabric GUID                                : 0x0000000000000000
    Inforom Version
        Image Version                                  : G144.0520.00.02
        OEM Object                                     : 2.1
        ECC Object                                     : 7.16
        Power Management Object                        : N/A
    Inforom BBX Object Flush
        Latest Timestamp                               : N/A
        Latest Duration                                : N/A
    GPU Operation Mode
        Current                                        : N/A
        Pending                                        : N/A
    GPU C2C Mode                                       : Disabled
    GPU Virtualization Mode
        Virtualization Mode                            : Pass-Through
        Host VGPU Mode                                 : N/A
        vGPU Heterogeneous Mode                        : N/A
    GPU Recovery Action                                : None
    GSP Firmware Version                               : 595.71.05
    IBMNPU
        Relaxed Ordering Mode                          : N/A
    PCI
        Bus                                            : 0x01
        Device                                         : 0x00
        Domain                                         : 0x0000
        Base Classcode                                 : 0x3
        Sub Classcode                                  : 0x0
        Device Id                                      : 0x2BB110DE
        Bus Id                                         : 00000000:01:00.0
        Sub System Id                                  : 0x204B10DE
        GPU Link Info
            PCIe Generation
                Max                                    : 5
                Current                                : 1
                Device Current                         : 1
                Device Max                             : 5
                Host Max                               : N/A
            Link Width
                Max                                    : 16x
                Current                                : 16x
        Bridge Chip
            Type                                       : N/A
            Firmware                                   : N/A
        Replays Since Reset                            : 0
        Replay Number Rollovers                        : 0
        Tx Throughput                                  : 780 KB/s
        Rx Throughput                                  : 465 KB/s
        Atomic Caps Outbound                           : N/A
        Atomic Caps Inbound                            : FETCHADD_32 FETCHADD_64 SWAP_32 SWAP_64 CAS_32 CAS_64
    Fan Speed                                          : 30 %
    Performance State                                  : P8
    Clocks Event Reasons
        Idle                                           : Not Active
        Applications Clocks Setting                    : Not Active
        SW Power Cap                                   : Not Active
        HW Slowdown                                    : Not Active
            HW Thermal Slowdown                        : Not Active
            HW Power Brake Slowdown                    : Not Active
        Sync Boost                                     : Not Active
        SW Thermal Slowdown                            : Not Active
        Display Clock Setting                          : Not Active
    Clocks Event Reasons Counters
        SW Power Capping                               : 200402 us
        Sync Boost                                     : 0 us
        SW Thermal Slowdown                            : 0 us
        HW Thermal Slowdown                            : 0 us
        HW Power Braking                               : 0 us
    Sparse Operation Mode                              : N/A
    FB Memory Usage
        Total                                          : 97887 MiB
        Reserved                                       : 638 MiB
        Used                                           : 2 MiB
        Free                                           : 97249 MiB
    BAR1 Memory Usage
        Total                                          : 131072 MiB
        Used                                           : 1 MiB
        Free                                           : 131071 MiB
    Conf Compute Protected Memory Usage
        Total                                          : 0 MiB
        Used                                           : 0 MiB
        Free                                           : 0 MiB
    Compute Mode                                       : Default
    Utilization
        GPU                                            : 0 %
        Memory                                         : 0 %
        Encoder                                        : 0 %
        Decoder                                        : 0 %
        JPEG                                           : 0 %
        OFA                                            : 0 %
    Encoder Stats
        Active Sessions                                : 0
        Average FPS                                    : 0
        Average Latency                                : 0
    FBC Stats
        Active Sessions                                : 0
        Average FPS                                    : 0
        Average Latency                                : 0
    DRAM Encryption Mode
        Current                                        : Disabled
        Pending                                        : Disabled
    ECC Mode
        Current                                        : Disabled
        Pending                                        : Disabled
    ECC Errors
        Volatile
            SRAM Correctable                           : N/A
            SRAM Uncorrectable Parity                  : N/A
            SRAM Uncorrectable SEC-DED                 : N/A
            DRAM Correctable                           : N/A
            DRAM Uncorrectable                         : N/A
        Aggregate
            SRAM Correctable                           : N/A
            SRAM Uncorrectable Parity                  : N/A
            SRAM Uncorrectable SEC-DED                 : N/A
            DRAM Correctable                           : N/A
            DRAM Uncorrectable                         : N/A
            SRAM Threshold Exceeded                    : N/A
        Aggregate Uncorrectable SRAM Sources
            SRAM L2                                    : N/A
            SRAM SM                                    : N/A
            SRAM Microcontroller                       : N/A
            SRAM PCIE                                  : N/A
            SRAM Other                                 : N/A
        Channel Repair Pending                         : No
        TPC Repair Pending                             : No
        Unrepairable Memory                            : N/A
    Retired Pages
        Single Bit ECC                                 : N/A
        Double Bit ECC                                 : N/A
        Pending Page Blacklist                         : N/A
    Remapped Rows
        Correctable Error                              : 0
        Inactive Correctable Error                     : 0
        Uncorrectable Error                            : 0
        Inactive Uncorrectable Error                   : 0
        Pending                                        : No
        Remapping Failure Occurred                     : No
        Bank Remap Availability Histogram
            Max                                        : 512 bank(s)
            High                                       : 0 bank(s)
            Partial                                    : 0 bank(s)
            Low                                        : 0 bank(s)
            None                                       : 0 bank(s)
    Temperature
        GPU Current Temp                               : 31 C
        GPU T.Limit Temp                               : 62 C
        GPU Shutdown T.Limit Temp                      : -5 C
        GPU Slowdown T.Limit Temp                      : -2 C
        GPU Max Operating T.Limit Temp                 : 0 C
        GPU Target Temperature                         : N/A
        Memory Current Temp                            : N/A
        Memory Max Operating T.Limit Temp              : N/A
    GPU Power Readings
        Average Power Draw                             : 16.52 W
        Instantaneous Power Draw                       : 16.52 W
        Current Power Limit                            : 600.00 W
        Requested Power Limit                          : 600.00 W
        Default Power Limit                            : 600.00 W
        Min Power Limit                                : 150.00 W
        Max Power Limit                                : 600.00 W
    GPU Memory Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
    Module Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
        Current Power Limit                            : N/A
        Requested Power Limit                          : N/A
        Default Power Limit                            : N/A
        Min Power Limit                                : N/A
        Max Power Limit                                : N/A
    Power Smoothing                                    : N/A
    Workload Power Profiles
        Requested Profiles                             : N/A
        Enforced Profiles                              : N/A
    EDPp Multiplier                                    : N/A
    Clocks
        Graphics                                       : 180 MHz
        SM                                             : 180 MHz
        Memory                                         : 405 MHz
        Video                                          : 600 MHz
    Applications Clocks
        Graphics                                       : Requested functionality has been deprecated
        Memory                                         : Requested functionality has been deprecated
    Default Applications Clocks
        Graphics                                       : Requested functionality has been deprecated
        Memory                                         : Requested functionality has been deprecated
    Deferred Clocks
        Memory                                         : N/A
    Max Clocks
        Graphics                                       : 3090 MHz
        SM                                             : 3090 MHz
        Memory                                         : 14001 MHz
        Video                                          : 3090 MHz
    Max Customer Boost Clocks
        Graphics                                       : N/A
    Clock Policy
        Auto Boost                                     : N/A
        Auto Boost Default                             : N/A
    Fabric
        State                                          : N/A
        Status                                         : N/A
        CliqueId                                       : N/A
        ClusterUUID                                    : N/A
        Health
            Summary                                    : N/A
            Bandwidth                                  : N/A
            Route Recovery in progress                 : N/A
            Route Unhealthy                            : N/A
            Access Timeout Recovery                    : N/A
            Incorrect Configuration                    : N/A
            Partition Assigned                         : N/A
    Processes                                          : None
    Capabilities
        EGM                                            : disabled

GPU 00000000:02:00.0
    Product Name                                       : NVIDIA RTX PRO 6000 Blackwell Workstation Edition
    Product Brand                                      : NVIDIA RTX
    Product Architecture                               : Blackwell
    Display Mode                                       : Requested functionality has been deprecated
    Display Attached                                   : Yes
    Display Active                                     : Disabled
    Persistence Mode                                   : Disabled
    Addressing Mode                                    : HMM
    MIG Mode
        Current                                        : N/A
        Pending                                        : N/A
    Accounting Mode                                    : Disabled
    Accounting Mode Buffer Size                        : 4000
    Driver Model
        Current                                        : N/A
        Pending                                        : N/A
    Serial Number                                      : 1792825000515
    GPU UUID                                           : GPU-69acfa26-8b60-61b5-702d-aee252c163cc
    GPU PDI                                            : 0x3802a64ab95f128c
    Minor Number                                       : 1
    VBIOS Version                                      : 98.02.52.00.02
    MultiGPU Board                                     : No
    Board ID                                           : 0x200
    Board Part Number                                  : 900-5G144-2200-000
    GPU Part Number                                    : 2BB1-870-A1
    FRU Part Number                                    : N/A
    Platform Info
        Chassis Serial Number                          :
        Slot Number                                    : 0
        Tray Index                                     : 0
        Host ID                                        : 1
        Peer Type                                      : Direct Connected
        Module Id                                      : 1
        GPU Fabric GUID                                : 0x0000000000000000
    Inforom Version
        Image Version                                  : G144.0520.00.02
        OEM Object                                     : 2.1
        ECC Object                                     : 7.16
        Power Management Object                        : N/A
    Inforom BBX Object Flush
        Latest Timestamp                               : N/A
        Latest Duration                                : N/A
    GPU Operation Mode
        Current                                        : N/A
        Pending                                        : N/A
    GPU C2C Mode                                       : Disabled
    GPU Virtualization Mode
        Virtualization Mode                            : Pass-Through
        Host VGPU Mode                                 : N/A
        vGPU Heterogeneous Mode                        : N/A
    GPU Recovery Action                                : None
    GSP Firmware Version                               : 595.71.05
    IBMNPU
        Relaxed Ordering Mode                          : N/A
    PCI
        Bus                                            : 0x02
        Device                                         : 0x00
        Domain                                         : 0x0000
        Base Classcode                                 : 0x3
        Sub Classcode                                  : 0x0
        Device Id                                      : 0x2BB110DE
        Bus Id                                         : 00000000:02:00.0
        Sub System Id                                  : 0x204B10DE
        GPU Link Info
            PCIe Generation
                Max                                    : 5
                Current                                : 1
                Device Current                         : 1
                Device Max                             : 5
                Host Max                               : N/A
            Link Width
                Max                                    : 16x
                Current                                : 16x
        Bridge Chip
            Type                                       : N/A
            Firmware                                   : N/A
        Replays Since Reset                            : 0
        Replay Number Rollovers                        : 0
        Tx Throughput                                  : 1991 KB/s
        Rx Throughput                                  : 490 KB/s
        Atomic Caps Outbound                           : N/A
        Atomic Caps Inbound                            : FETCHADD_32 FETCHADD_64 SWAP_32 SWAP_64 CAS_32 CAS_64
    Fan Speed                                          : 30 %
    Performance State                                  : P8
    Clocks Event Reasons
        Idle                                           : Not Active
        Applications Clocks Setting                    : Not Active
        SW Power Cap                                   : Not Active
        HW Slowdown                                    : Not Active
            HW Thermal Slowdown                        : Not Active
            HW Power Brake Slowdown                    : Not Active
        Sync Boost                                     : Not Active
        SW Thermal Slowdown                            : Not Active
        Display Clock Setting                          : Not Active
    Clocks Event Reasons Counters
        SW Power Capping                               : 200214 us
        Sync Boost                                     : 0 us
        SW Thermal Slowdown                            : 0 us
        HW Thermal Slowdown                            : 0 us
        HW Power Braking                               : 0 us
    Sparse Operation Mode                              : N/A
    FB Memory Usage
        Total                                          : 97887 MiB
        Reserved                                       : 638 MiB
        Used                                           : 34 MiB
        Free                                           : 97217 MiB
    BAR1 Memory Usage
        Total                                          : 131072 MiB
        Used                                           : 33 MiB
        Free                                           : 131039 MiB
    Conf Compute Protected Memory Usage
        Total                                          : 0 MiB
        Used                                           : 0 MiB
        Free                                           : 0 MiB
    Compute Mode                                       : Default
    Utilization
        GPU                                            : 0 %
        Memory                                         : 0 %
        Encoder                                        : 0 %
        Decoder                                        : 0 %
        JPEG                                           : 0 %
        OFA                                            : 0 %
    Encoder Stats
        Active Sessions                                : 0
        Average FPS                                    : 0
        Average Latency                                : 0
    FBC Stats
        Active Sessions                                : 0
        Average FPS                                    : 0
        Average Latency                                : 0
    DRAM Encryption Mode
        Current                                        : Disabled
        Pending                                        : Disabled
    ECC Mode
        Current                                        : Disabled
        Pending                                        : Disabled
    ECC Errors
        Volatile
            SRAM Correctable                           : N/A
            SRAM Uncorrectable Parity                  : N/A
            SRAM Uncorrectable SEC-DED                 : N/A
            DRAM Correctable                           : N/A
            DRAM Uncorrectable                         : N/A
        Aggregate
            SRAM Correctable                           : N/A
            SRAM Uncorrectable Parity                  : N/A
            SRAM Uncorrectable SEC-DED                 : N/A
            DRAM Correctable                           : N/A
            DRAM Uncorrectable                         : N/A
            SRAM Threshold Exceeded                    : N/A
        Aggregate Uncorrectable SRAM Sources
            SRAM L2                                    : N/A
            SRAM SM                                    : N/A
            SRAM Microcontroller                       : N/A
            SRAM PCIE                                  : N/A
            SRAM Other                                 : N/A
        Channel Repair Pending                         : No
        TPC Repair Pending                             : No
        Unrepairable Memory                            : N/A
    Retired Pages
        Single Bit ECC                                 : N/A
        Double Bit ECC                                 : N/A
        Pending Page Blacklist                         : N/A
    Remapped Rows
        Correctable Error                              : 0
        Inactive Correctable Error                     : 0
        Uncorrectable Error                            : 0
        Inactive Uncorrectable Error                   : 0
        Pending                                        : No
        Remapping Failure Occurred                     : No
        Bank Remap Availability Histogram
            Max                                        : 512 bank(s)
            High                                       : 0 bank(s)
            Partial                                    : 0 bank(s)
            Low                                        : 0 bank(s)
            None                                       : 0 bank(s)
    Temperature
        GPU Current Temp                               : 37 C
        GPU T.Limit Temp                               : 56 C
        GPU Shutdown T.Limit Temp                      : -5 C
        GPU Slowdown T.Limit Temp                      : -2 C
        GPU Max Operating T.Limit Temp                 : 0 C
        GPU Target Temperature                         : N/A
        Memory Current Temp                            : N/A
        Memory Max Operating T.Limit Temp              : N/A
    GPU Power Readings
        Average Power Draw                             : 31.78 W
        Instantaneous Power Draw                       : 31.78 W
        Current Power Limit                            : 600.00 W
        Requested Power Limit                          : 600.00 W
        Default Power Limit                            : 600.00 W
        Min Power Limit                                : 150.00 W
        Max Power Limit                                : 600.00 W
    GPU Memory Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
    Module Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
        Current Power Limit                            : N/A
        Requested Power Limit                          : N/A
        Default Power Limit                            : N/A
        Min Power Limit                                : N/A
        Max Power Limit                                : N/A
    Power Smoothing                                    : N/A
    Workload Power Profiles
        Requested Profiles                             : N/A
        Enforced Profiles                              : N/A
    EDPp Multiplier                                    : N/A
    Clocks
        Graphics                                       : 180 MHz
        SM                                             : 180 MHz
        Memory                                         : 405 MHz
        Video                                          : 600 MHz
    Applications Clocks
        Graphics                                       : Requested functionality has been deprecated
        Memory                                         : Requested functionality has been deprecated
    Default Applications Clocks
        Graphics                                       : Requested functionality has been deprecated
        Memory                                         : Requested functionality has been deprecated
    Deferred Clocks
        Memory                                         : N/A
    Max Clocks
        Graphics                                       : 3090 MHz
        SM                                             : 3090 MHz
        Memory                                         : 14001 MHz
        Video                                          : 3090 MHz
    Max Customer Boost Clocks
        Graphics                                       : N/A
    Clock Policy
        Auto Boost                                     : N/A
        Auto Boost Default                             : N/A
    Fabric
        State                                          : N/A
        Status                                         : N/A
        CliqueId                                       : N/A
        ClusterUUID                                    : N/A
        Health
            Summary                                    : N/A
            Bandwidth                                  : N/A
            Route Recovery in progress                 : N/A
            Route Unhealthy                            : N/A
            Access Timeout Recovery                    : N/A
            Incorrect Configuration                    : N/A
            Partition Assigned                         : N/A
    Processes                                          : None
    Capabilities
        EGM                                            : disabled


[exit=0]
```

### nvidia-smi memory detail

```console
$ nvidia-smi -q -d MEMORY

==============NVSMI LOG==============

Timestamp                                              : Fri Jul  3 07:38:44 2026
Driver Version                                         : 595.71.05
CUDA Version                                           : 13.2

Attached GPUs                                          : 2
GPU 00000000:01:00.0
    FB Memory Usage
        Total                                          : 97887 MiB
        Reserved                                       : 638 MiB
        Used                                           : 2 MiB
        Free                                           : 97249 MiB
    BAR1 Memory Usage
        Total                                          : 131072 MiB
        Used                                           : 1 MiB
        Free                                           : 131071 MiB
    Conf Compute Protected Memory Usage
        Total                                          : 0 MiB
        Used                                           : 0 MiB
        Free                                           : 0 MiB

GPU 00000000:02:00.0
    FB Memory Usage
        Total                                          : 97887 MiB
        Reserved                                       : 638 MiB
        Used                                           : 34 MiB
        Free                                           : 97217 MiB
    BAR1 Memory Usage
        Total                                          : 131072 MiB
        Used                                           : 33 MiB
        Free                                           : 131039 MiB
    Conf Compute Protected Memory Usage
        Total                                          : 0 MiB
        Used                                           : 0 MiB
        Free                                           : 0 MiB


[exit=0]
```

### nvidia-smi power detail

```console
$ nvidia-smi -q -d POWER

==============NVSMI LOG==============

Timestamp                                              : Fri Jul  3 07:38:44 2026
Driver Version                                         : 595.71.05
CUDA Version                                           : 13.2

Attached GPUs                                          : 2
GPU 00000000:01:00.0
    GPU Power Readings
        Average Power Draw                             : 16.52 W
        Instantaneous Power Draw                       : 16.52 W
        Current Power Limit                            : 600.00 W
        Requested Power Limit                          : 600.00 W
        Default Power Limit                            : 600.00 W
        Min Power Limit                                : 150.00 W
        Max Power Limit                                : 600.00 W
    Power Samples
        Duration                                       : 118.00 sec
        Number of Samples                              : 119
        Max                                            : 17.80 W
        Min                                            : 14.79 W
        Avg                                            : 15.05 W
    GPU Memory Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
    Module Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
        Current Power Limit                            : N/A
        Requested Power Limit                          : N/A
        Default Power Limit                            : N/A
        Min Power Limit                                : N/A
        Max Power Limit                                : N/A
    EDPp Multiplier                                    : N/A

GPU 00000000:02:00.0
    GPU Power Readings
        Average Power Draw                             : 31.78 W
        Instantaneous Power Draw                       : 31.78 W
        Current Power Limit                            : 600.00 W
        Requested Power Limit                          : 600.00 W
        Default Power Limit                            : 600.00 W
        Min Power Limit                                : 150.00 W
        Max Power Limit                                : 600.00 W
    Power Samples
        Duration                                       : 117.99 sec
        Number of Samples                              : 119
        Max                                            : 32.72 W
        Min                                            : 31.25 W
        Avg                                            : 32.12 W
    GPU Memory Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
    Module Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
        Current Power Limit                            : N/A
        Requested Power Limit                          : N/A
        Default Power Limit                            : N/A
        Min Power Limit                                : N/A
        Max Power Limit                                : N/A
    EDPp Multiplier                                    : N/A


[exit=0]
```

### nvcc after reboot

```console
$ command -v nvcc || true; nvcc --version || true
bash: line 1: nvcc: command not found

[exit=0]
```

### Installed NVIDIA/CUDA/container-toolkit packages after reboot

```console
$ dpkg -l | egrep 'nvidia|cuda|container-toolkit' || true
ii  libnvidia-cfg1-595:amd64              595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA binary OpenGL/GLX configuration library
ii  libnvidia-common-595                  595.71.05-0ubuntu0.24.04.1                       amd64        Shared files used by the NVIDIA libraries
ii  libnvidia-compute-595:amd64           595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA libcompute package
ii  libnvidia-decode-595:amd64            595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA Video Decoding runtime libraries
ii  libnvidia-egl-wayland1:amd64          1:1.1.13-1ubuntu0.1                              amd64        Wayland EGL External Platform library -- shared library
ii  libnvidia-encode-595:amd64            595.71.05-0ubuntu0.24.04.1                       amd64        NVENC Video Encoding runtime library
ii  libnvidia-extra-595:amd64             595.71.05-0ubuntu0.24.04.1                       amd64        Extra libraries for the NVIDIA driver
ii  libnvidia-fbc1-595:amd64              595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA OpenGL-based Framebuffer Capture runtime library
ii  libnvidia-gl-595:amd64                595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA OpenGL/GLX/EGL/GLES GLVND libraries and Vulkan ICD
ii  nvidia-compute-utils-595              595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA compute utilities
ii  nvidia-dkms-595-open                  595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA DKMS package (open kernel module)
ii  nvidia-driver-595-open                595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA driver (open kernel) metapackage
ii  nvidia-firmware-595-595.71.05         595.71.05-0ubuntu0.24.04.1                       amd64        Firmware files used by the kernel module
ii  nvidia-kernel-common-595              595.71.05-0ubuntu0.24.04.1                       amd64        Shared files used with the kernel module
ii  nvidia-kernel-source-595-open         595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA kernel source package
ii  nvidia-prime                          0.8.17.2                                         all          Tools to enable NVIDIA's Prime
ii  nvidia-settings                       510.47.03-0ubuntu4.24.04.1                       amd64        Tool for configuring the NVIDIA graphics driver
ii  nvidia-utils-595                      595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA driver support binaries
ii  screen-resolution-extra               0.18.3ubuntu0.24.04.1                            all          Extension for the nvidia-settings control panel
ii  xserver-xorg-video-nvidia-595         595.71.05-0ubuntu0.24.04.1                       amd64        NVIDIA binary Xorg driver

[exit=0]
```

### Docker Root Dir and containerd info

```console
$ sudo -n docker info | egrep 'Docker Root Dir|Storage Driver|containerd' || true
 Storage Driver: overlayfs
  driver-type: io.containerd.snapshotter.v1
 Runtimes: io.containerd.runc.v2 runc
 containerd version: e53c7c1516c3b2bff98eb76f1f4117477e6f4e66
 Docker Root Dir: /data/docker

[exit=0]
```

### Docker/containerd path sizes

```console
$ sudo -n du -sh /var/lib/docker /var/lib/containerd /data/docker /data/containerd /data/containerd/root 2>/dev/null || true
236K	/data/docker
336K	/data/containerd

[exit=0]
```

## M5B Post-reboot Validation Summary

- nvidia-smi: PASS
- GPU count: 2
- GPU names: NVIDIA RTX PRO 6000 Blackwell Workstation Edition (UUID;NVIDIA RTX PRO 6000 Blackwell Workstation Edition (UUID

- Query CSV:

```csv
0, NVIDIA RTX PRO 6000 Blackwell Workstation Edition, 00000000:01:00.0, 595.71.05, 97887 MiB, 600.00 W
1, NVIDIA RTX PRO 6000 Blackwell Workstation Edition, 00000000:02:00.0, 595.71.05, 97887 MiB, 600.00 W
```

- nouveau loaded/bound: not bound to NVIDIA GPUs; see lsmod/lspci sections above.
- nvidia modules loaded: PASS
- nvcc: absent
- CUDA Toolkit packages: absent
- NVIDIA Container Toolkit packages: absent
- Docker Root Dir: /data/docker
- containerd root: /data/containerd/root
- containerd state: /run/containerd
- /data guard: PASS
- root-disk guard: PASS
- Docker storage verifier: PASS
- Scope confirmation: CUDA Toolkit, PyTorch, KTransformers, ik_llama, NVIDIA Container Toolkit, models, Docker NVIDIA runtime, Docker/containerd configuration, and API exposure were not installed or configured by M5B.
- Manual Proxmox host checks still required: VFIO/PCIe/AER/reset logs plus VM config/status checks outside Codex.

## M5B Post-reboot Conclusion

PASS
### git diff --check

```console
$ git diff --check

[exit=0]
```

### grep-based secret scan

```console
$ grep -RInE '(HF_TOKEN|OPENAI_API_KEY|GITHUB_TOKEN|password|passwd|PRIVATE KEY|BEGIN OPENSSH|BEGIN RSA|auth.json|ai-vm.sudo)' . --exclude-dir=.git || true
./tests/shell/test-prepare-data-disk-static.sh:36:if grep -RInE '(BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY|HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,})' "$PREPARE" "$VERIFY"; then
./tests/shell/test-root-disk-guard-static.sh:52:if grep -RInE '(BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY|HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,})' "$ROOT_GUARD" "$REQUIRE_DATA"; then
./tests/shell/test-docker-scripts-static.sh:50:if grep -RInE 'usermod[[:space:]].*docker|gpasswd[[:space:]].*docker|groupadd[[:space:]].*docker' "${scripts[@]}"; then
./tests/shell/test-docker-scripts-static.sh:58:if grep -RInE '(BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY|HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,})' "${scripts[@]}"; then
./scripts/preflight/disk-dry-run.sh:38:    -e 's/(HF_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/preflight/disk-dry-run.sh:39:    -e 's/(OPENAI_API_KEY=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/preflight/disk-dry-run.sh:40:    -e 's/(GITHUB_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/preflight/disk-dry-run.sh:42:    -e 's/((password|passwd)[=:][[:space:]]*)[^[:space:]]+/\1[REDACTED]/Ig' \
./scripts/preflight/disk-dry-run.sh:123:if git remote -v 2>/dev/null | grep -Eq '(://[^[:space:]]*:[^[:space:]@]*@|token|password|passwd|GITHUB_TOKEN)'; then
./scripts/preflight/disk-dry-run.sh:149:Reason for STOP: sudo -n true failed after sudo -k. No password was requested or read.
./scripts/preflight/vm-preflight.sh:33:- never prompts for a sudo password
./scripts/preflight/vm-preflight.sh:51:    -e 's/(HF_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/preflight/vm-preflight.sh:52:    -e 's/(OPENAI_API_KEY=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/preflight/vm-preflight.sh:53:    -e 's/(GITHUB_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/preflight/vm-preflight.sh:55:    -e 's/((password|passwd)[=:][[:space:]]*)[^[:space:]]+/\1[REDACTED]/Ig' \
./scripts/preflight/vm-preflight.sh:113:  git remote -v 2>/dev/null | grep -Eq '(://[^[:space:]]*:[^[:space:]@]*@|token|password|passwd|GITHUB_TOKEN)'
./scripts/preflight/vm-preflight.sh:352:- No secrets, tokens, passwords, private keys, auth files, real .env files, MEMORY.md, or local Codex memory files were read or written.
./scripts/storage/prepare-data-disk.sh:58:    -e 's/(HF_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/storage/prepare-data-disk.sh:59:    -e 's/(OPENAI_API_KEY=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/storage/prepare-data-disk.sh:60:    -e 's/(GITHUB_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/storage/prepare-data-disk.sh:62:    -e 's/((password|passwd)[=:][[:space:]]*)[^[:space:]]+/\1[REDACTED]/Ig' \
./scripts/storage/prepare-data-disk.sh:206:  if git remote -v 2>/dev/null | grep -Eq '(://[^[:space:]]*:[^[:space:]@]*@|token|password|passwd|GITHUB_TOKEN)'; then
./scripts/storage/verify-data-mount.sh:41:    -e 's/(HF_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/storage/verify-data-mount.sh:42:    -e 's/(OPENAI_API_KEY=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/storage/verify-data-mount.sh:43:    -e 's/(GITHUB_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./scripts/storage/verify-data-mount.sh:45:    -e 's/((password|passwd)[=:][[:space:]]*)[^[:space:]]+/\1[REDACTED]/Ig' \
./scripts/common/root-disk-guard.sh:524:      -name auth.json -o \
./AGENTS.md:32:- Do not commit real `.env` files, tokens, passwords, private keys, API keys, Hugging Face tokens, GitHub tokens, SSH keys, sudo files, auth files, model weights, or service secrets.
./.github/workflows/ci.yml:49:          forbidden=$(find . -path ./.git -prune -o \( -name .env -o -name '*.key' -o -name '*.pem' -o -name auth.json -o -name MEMORY.md \) -print)
./.github/ISSUE_TEMPLATE/bug_report.yml:9:      value: Do not include secrets, tokens, private keys, passwords, or model weights.
./.github/ISSUE_TEMPLATE/hardware_report.yml:9:      value: Do not include secrets, tokens, private keys, passwords, public IPs, or model weights.
./.gitignore:15:auth.json
./SECURITY.md:9:Do not commit secrets, tokens, passwords, SSH keys, API keys, sudo files, real `.env` files, Hugging Face tokens, GitHub tokens, auth files, model weights, or `/data/services/secrets` contents.
./reports/m3-main-merge.md:35:The grep-based secret scan matched only intentional documentation, test, sanitizer, `.gitignore`, CI, and prior report command strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m4b-main-merge.md:47:The grep-based secret scan matched only intentional documentation, sanitizer, static-test, `.gitignore`, CI, and prior report strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m4a-docker-containerd-plan.md:114:The grep-based secret scan found only intentional documentation, static-test, sanitizer, `.gitignore`, CI, and prior report command strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m5a-cuda-nvidia-compatibility.md:339:The grep-based secret scan matched only intentional documentation, safety rules, examples, and scan pattern text. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were found.
./reports/m5a-main-merge.md:116:The grep-based secret scan matched only intentional documentation, test, sanitizer, `.gitignore`, CI, and prior report strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m4b-docker-permission-policy.md:72:The grep-based secret scan matched only intentional documentation, sanitizer, static-test, `.gitignore`, CI, and prior report strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m4a-main-merge.md:36:The grep-based secret scan matched only intentional documentation, test, sanitizer, `.gitignore`, CI, and prior report command strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m4b-docker-containerd-install.md:975:- Grep-based secret scan: matched only intentional documentation, static-test, sanitizer, `.gitignore`, CI, and prior report command strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m1-vm-preflight.md:512:- No secrets, tokens, passwords, private keys, auth files, real .env files, MEMORY.md, or local Codex memory files were read or written.
./reports/m2-main-merge.md:31:grep -RInE "(HF_TOKEN|OPENAI_API_KEY|GITHUB_TOKEN|password|passwd|PRIVATE KEY|BEGIN OPENSSH|BEGIN RSA|auth.json|ai-vm.sudo)" . --exclude-dir=.git || true
./reports/m5b-nvidia-host-driver.md:2544:./tests/shell/test-prepare-data-disk-static.sh:36:if grep -RInE '(BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY|HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,})' "$PREPARE" "$VERIFY"; then
./reports/m5b-nvidia-host-driver.md:2545:./tests/shell/test-root-disk-guard-static.sh:52:if grep -RInE '(BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY|HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,})' "$ROOT_GUARD" "$REQUIRE_DATA"; then
./reports/m5b-nvidia-host-driver.md:2546:./tests/shell/test-docker-scripts-static.sh:50:if grep -RInE 'usermod[[:space:]].*docker|gpasswd[[:space:]].*docker|groupadd[[:space:]].*docker' "${scripts[@]}"; then
./reports/m5b-nvidia-host-driver.md:2547:./tests/shell/test-docker-scripts-static.sh:58:if grep -RInE '(BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY|HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,})' "${scripts[@]}"; then
./reports/m5b-nvidia-host-driver.md:2548:./scripts/preflight/disk-dry-run.sh:38:    -e 's/(HF_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./reports/m5b-nvidia-host-driver.md:2549:./scripts/preflight/disk-dry-run.sh:39:    -e 's/(OPENAI_API_KEY=)[^[:space:]]+/\1[REDACTED]/g' \
./reports/m5b-nvidia-host-driver.md:2550:./scripts/preflight/disk-dry-run.sh:40:    -e 's/(GITHUB_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./reports/m5b-nvidia-host-driver.md:2551:./scripts/preflight/disk-dry-run.sh:42:    -e 's/((password|passwd)[=:][[:space:]]*)[^[:space:]]+/\1[REDACTED]/Ig' \
./reports/m5b-nvidia-host-driver.md:2552:./scripts/preflight/disk-dry-run.sh:123:if git remote -v 2>/dev/null | grep -Eq '(://[^[:space:]]*:[^[:space:]@]*@|token|password|passwd|GITHUB_TOKEN)'; then
./reports/m5b-nvidia-host-driver.md:2553:./scripts/preflight/disk-dry-run.sh:149:Reason for STOP: sudo -n true failed after sudo -k. No password was requested or read.
./reports/m5b-nvidia-host-driver.md:2554:./scripts/preflight/vm-preflight.sh:33:- never prompts for a sudo password
./reports/m5b-nvidia-host-driver.md:2555:./scripts/preflight/vm-preflight.sh:51:    -e 's/(HF_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./reports/m5b-nvidia-host-driver.md:2556:./scripts/preflight/vm-preflight.sh:52:    -e 's/(OPENAI_API_KEY=)[^[:space:]]+/\1[REDACTED]/g' \
./reports/m5b-nvidia-host-driver.md:2557:./scripts/preflight/vm-preflight.sh:53:    -e 's/(GITHUB_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./reports/m5b-nvidia-host-driver.md:2558:./scripts/preflight/vm-preflight.sh:55:    -e 's/((password|passwd)[=:][[:space:]]*)[^[:space:]]+/\1[REDACTED]/Ig' \
./reports/m5b-nvidia-host-driver.md:2559:./scripts/preflight/vm-preflight.sh:113:  git remote -v 2>/dev/null | grep -Eq '(://[^[:space:]]*:[^[:space:]@]*@|token|password|passwd|GITHUB_TOKEN)'
./reports/m5b-nvidia-host-driver.md:2560:./scripts/preflight/vm-preflight.sh:352:- No secrets, tokens, passwords, private keys, auth files, real .env files, MEMORY.md, or local Codex memory files were read or written.
./reports/m5b-nvidia-host-driver.md:2561:./scripts/storage/prepare-data-disk.sh:58:    -e 's/(HF_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./reports/m5b-nvidia-host-driver.md:2562:./scripts/storage/prepare-data-disk.sh:59:    -e 's/(OPENAI_API_KEY=)[^[:space:]]+/\1[REDACTED]/g' \
./reports/m5b-nvidia-host-driver.md:2563:./scripts/storage/prepare-data-disk.sh:60:    -e 's/(GITHUB_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./reports/m5b-nvidia-host-driver.md:2564:./scripts/storage/prepare-data-disk.sh:62:    -e 's/((password|passwd)[=:][[:space:]]*)[^[:space:]]+/\1[REDACTED]/Ig' \
./reports/m5b-nvidia-host-driver.md:2565:./scripts/storage/prepare-data-disk.sh:206:  if git remote -v 2>/dev/null | grep -Eq '(://[^[:space:]]*:[^[:space:]@]*@|token|password|passwd|GITHUB_TOKEN)'; then
./reports/m5b-nvidia-host-driver.md:2566:./scripts/storage/verify-data-mount.sh:41:    -e 's/(HF_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./reports/m5b-nvidia-host-driver.md:2567:./scripts/storage/verify-data-mount.sh:42:    -e 's/(OPENAI_API_KEY=)[^[:space:]]+/\1[REDACTED]/g' \
./reports/m5b-nvidia-host-driver.md:2568:./scripts/storage/verify-data-mount.sh:43:    -e 's/(GITHUB_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
./reports/m5b-nvidia-host-driver.md:2569:./scripts/storage/verify-data-mount.sh:45:    -e 's/((password|passwd)[=:][[:space:]]*)[^[:space:]]+/\1[REDACTED]/Ig' \
./reports/m5b-nvidia-host-driver.md:2570:./scripts/common/root-disk-guard.sh:524:      -name auth.json -o \
./reports/m5b-nvidia-host-driver.md:2571:./AGENTS.md:32:- Do not commit real `.env` files, tokens, passwords, private keys, API keys, Hugging Face tokens, GitHub tokens, SSH keys, sudo files, auth files, model weights, or service secrets.
./reports/m5b-nvidia-host-driver.md:2572:./.github/workflows/ci.yml:49:          forbidden=$(find . -path ./.git -prune -o \( -name .env -o -name '*.key' -o -name '*.pem' -o -name auth.json -o -name MEMORY.md \) -print)
./reports/m5b-nvidia-host-driver.md:2573:./.github/ISSUE_TEMPLATE/bug_report.yml:9:      value: Do not include secrets, tokens, private keys, passwords, or model weights.
./reports/m5b-nvidia-host-driver.md:2574:./.github/ISSUE_TEMPLATE/hardware_report.yml:9:      value: Do not include secrets, tokens, private keys, passwords, public IPs, or model weights.
./reports/m5b-nvidia-host-driver.md:2575:./.gitignore:15:auth.json
./reports/m5b-nvidia-host-driver.md:2576:./SECURITY.md:9:Do not commit secrets, tokens, passwords, SSH keys, API keys, sudo files, real `.env` files, Hugging Face tokens, GitHub tokens, auth files, model weights, or `/data/services/secrets` contents.
./reports/m5b-nvidia-host-driver.md:2577:./reports/m3-main-merge.md:35:The grep-based secret scan matched only intentional documentation, test, sanitizer, `.gitignore`, CI, and prior report command strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m5b-nvidia-host-driver.md:2578:./reports/m4b-main-merge.md:47:The grep-based secret scan matched only intentional documentation, sanitizer, static-test, `.gitignore`, CI, and prior report strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m5b-nvidia-host-driver.md:2579:./reports/m4a-docker-containerd-plan.md:114:The grep-based secret scan found only intentional documentation, static-test, sanitizer, `.gitignore`, CI, and prior report command strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m5b-nvidia-host-driver.md:2580:./reports/m5a-cuda-nvidia-compatibility.md:339:The grep-based secret scan matched only intentional documentation, safety rules, examples, and scan pattern text. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were found.
./reports/m5b-nvidia-host-driver.md:2581:./reports/m5a-main-merge.md:116:The grep-based secret scan matched only intentional documentation, test, sanitizer, `.gitignore`, CI, and prior report strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m5b-nvidia-host-driver.md:2582:./reports/m4b-docker-permission-policy.md:72:The grep-based secret scan matched only intentional documentation, sanitizer, static-test, `.gitignore`, CI, and prior report strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m5b-nvidia-host-driver.md:2583:./reports/m4a-main-merge.md:36:The grep-based secret scan matched only intentional documentation, test, sanitizer, `.gitignore`, CI, and prior report command strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m5b-nvidia-host-driver.md:2584:./reports/m4b-docker-containerd-install.md:975:- Grep-based secret scan: matched only intentional documentation, static-test, sanitizer, `.gitignore`, CI, and prior report command strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.
./reports/m5b-nvidia-host-driver.md:2585:./reports/m1-vm-preflight.md:512:- No secrets, tokens, passwords, private keys, auth files, real .env files, MEMORY.md, or local Codex memory files were read or written.
./reports/m5b-nvidia-host-driver.md:2586:./reports/m2-main-merge.md:31:grep -RInE "(HF_TOKEN|OPENAI_API_KEY|GITHUB_TOKEN|password|passwd|PRIVATE KEY|BEGIN OPENSSH|BEGIN RSA|auth.json|ai-vm.sudo)" . --exclude-dir=.git || true
./reports/m5b-nvidia-host-driver.md:2589:The grep-based secret scan matched only intentional documentation, safety rules, examples, sanitizer/static-test code, prior report text, and the scan pattern itself. No real secrets, tokens, passwords, private keys, auth files, real .env files, MEMORY.md, or local Codex memory files were identified.

[exit=0]
```

### Secret scan interpretation

The grep-based secret scan matched only intentional documentation, safety rules, examples, or scan pattern text. No real secrets, tokens, passwords, private keys, auth files, real .env files, MEMORY.md, or local Codex memory files were identified.


## Docker/containerd Storage Verification

- Timestamp: 2026-07-03T07:39:16+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m5b-nvidia-host-driver

### require /data mounted

```console
$ scripts/common/require-data-mounted.sh
PASS: /data is mounted and ready
- root source: /dev/mapper/ubuntu--vg-ubuntu--lv
- data source: /dev/sdb1
- data fstype: ext4
- data label: AI_DATA
- data UUID: 8daf56f1-5649-4163-9d87-919c2d271875

[exit=0]
```

### pre-verification root-disk guard

```console
$ scripts/common/root-disk-guard.sh
PASS: root disk guard passed

[exit=0]
```

### df -hT / /data

```console
$ df -hT / /data
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  8.9G  4.6G  66% /
/dev/sdb1                         ext4  2.0T  3.7M  1.9T   1% /data

[exit=0]
```

### /var/lib Docker/containerd size summary

| Path | MiB | Policy |
| --- | ---: | --- |
| `/var/lib/docker` | 0 | absent/empty/small or documented |
| `/var/lib/containerd` | 0 | absent/empty/small or documented |

### systemctl is-active containerd

```console
$ sudo -n systemctl is-active containerd
active

[exit=0]
```

### systemctl is-active docker

```console
$ sudo -n systemctl is-active docker
active

[exit=0]
```

### systemctl status containerd

```console
$ sudo -n systemctl status containerd --no-pager
● containerd.service - containerd container runtime
     Loaded: loaded (/usr/lib/systemd/system/containerd.service; enabled; preset: enabled)
     Active: active (running) since Fri 2026-07-03 07:35:25 UTC; 3min 51s ago
       Docs: https://containerd.io
   Main PID: 2091 (containerd)
      Tasks: 36
     Memory: 88.2M (peak: 94.0M)
        CPU: 662ms
     CGroup: /system.slice/containerd.service
             └─2091 /usr/bin/containerd

Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875859853Z" level=info msg="Start cni network conf syncer for default"
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875865272Z" level=info msg="Start streaming server"
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875873444Z" level=info msg="Registered namespace \"k8s.io\" with NRI"
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875878251Z" level=info msg="runtime interface starting up..."
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875881666Z" level=info msg="starting plugins..."
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875890109Z" level=info msg="Synchronizing NRI (plugin) with current runtime state"
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875902768Z" level=info msg=serving... address=/run/containerd/containerd.sock.ttrpc
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.875941546Z" level=info msg=serving... address=/run/containerd/containerd.sock
Jul 03 07:35:25 llmserver containerd[2091]: time="2026-07-03T07:35:25.876173504Z" level=info msg="containerd successfully booted in 0.033839s"
Jul 03 07:35:25 llmserver systemd[1]: Started containerd.service - containerd container runtime.

[exit=0]
```

### systemctl status docker

```console
$ sudo -n systemctl status docker --no-pager
● docker.service - Docker Application Container Engine
     Loaded: loaded (/usr/lib/systemd/system/docker.service; enabled; preset: enabled)
     Active: active (running) since Fri 2026-07-03 07:35:28 UTC; 3min 49s ago
TriggeredBy: ● docker.socket
       Docs: https://docs.docker.com
   Main PID: 2261 (dockerd)
      Tasks: 41
     Memory: 119.9M (peak: 126.1M)
        CPU: 674ms
     CGroup: /system.slice/docker.service
             └─2261 /usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock

Jul 03 07:35:27 llmserver dockerd[2261]: time="2026-07-03T07:35:27.673114630Z" level=info msg="Restoring containers: start."
Jul 03 07:35:27 llmserver dockerd[2261]: time="2026-07-03T07:35:27.775998332Z" level=info msg="Deleting nftables IPv4 rules" error="running nft: /dev/stdin:1:17-30: Error: Could not process rule: No such file or directory\ndelete table ip docker-bridges\n                ^^^^^^^^^^^^^^\n exit status 1"
Jul 03 07:35:27 llmserver dockerd[2261]: time="2026-07-03T07:35:27.788141528Z" level=info msg="Deleting nftables IPv6 rules" error="running nft: /dev/stdin:1:18-31: Error: Could not process rule: No such file or directory\ndelete table ip6 docker-bridges\n                 ^^^^^^^^^^^^^^\n exit status 1"
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.052444560Z" level=info msg="Loading containers: done."
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.058049123Z" level=info msg="Docker daemon" commit=8ec5ab3 containerd-snapshotter=true storage-driver=overlayfs version=29.6.1
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.058280870Z" level=info msg="Initializing buildkit"
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.220160582Z" level=info msg="Completed buildkit initialization"
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.224043800Z" level=info msg="Daemon has completed initialization"
Jul 03 07:35:28 llmserver dockerd[2261]: time="2026-07-03T07:35:28.224122648Z" level=info msg="API listen on /run/docker.sock"
Jul 03 07:35:28 llmserver systemd[1]: Started docker.service - Docker Application Container Engine.

[exit=0]
```

### sudo docker version

```console
$ sudo -n docker version
Client: Docker Engine - Community
 Version:           29.6.1
 API version:       1.55
 Go version:        go1.26.4
 Git commit:        8900f1d
 Built:             Fri Jun 26 11:40:19 2026
 OS/Arch:           linux/amd64
 Context:           default

Server: Docker Engine - Community
 Engine:
  Version:          29.6.1
  API version:      1.55 (minimum version 1.40)
  Go version:       go1.26.4
  Git commit:       8ec5ab3
  Built:            Fri Jun 26 11:40:19 2026
  OS/Arch:          linux/amd64
  Experimental:     false
 containerd:
  Version:          v2.2.5
  GitCommit:        e53c7c1516c3b2bff98eb76f1f4117477e6f4e66
 runc:
  Version:          1.3.6
  GitCommit:        v1.3.6-0-g491b69ba
 docker-init:
  Version:          0.19.0
  GitCommit:        de40ad0

[exit=0]
```

### sudo docker info

```console
$ sudo -n docker info
Client: Docker Engine - Community
 Version:    29.6.1
 Context:    default
 Debug Mode: false
 Plugins:
  buildx: Docker Buildx (Docker Inc.)
    Version:  v0.35.0
    Path:     /usr/libexec/docker/cli-plugins/docker-buildx
  compose: Docker Compose (Docker Inc.)
    Version:  v5.3.0
    Path:     /usr/libexec/docker/cli-plugins/docker-compose

Server:
 Containers: 0
  Running: 0
  Paused: 0
  Stopped: 0
 Images: 1
 Server Version: 29.6.1
 Storage Driver: overlayfs
  driver-type: io.containerd.snapshotter.v1
 Logging Driver: json-file
 Cgroup Driver: systemd
 Cgroup Version: 2
 Plugins:
  Volume: local
  Network: bridge host ipvlan macvlan null overlay
  Log: awslogs fluentd gcplogs gelf journald json-file local splunk syslog
 CDI spec directories:
  /etc/cdi
  /var/run/cdi
 Swarm: inactive
 Runtimes: io.containerd.runc.v2 runc
 Default Runtime: runc
 Init Binary: docker-init
 containerd version: e53c7c1516c3b2bff98eb76f1f4117477e6f4e66
 runc version: v1.3.6-0-g491b69ba
 init version: de40ad0
 Security Options:
  apparmor
  seccomp
   Profile: builtin
  cgroupns
 Kernel Version: 6.8.0-134-generic
 Operating System: Ubuntu 24.04.4 LTS
 OSType: linux
 Architecture: x86_64
 CPUs: 112
 Total Memory: 881.8GiB
 Name: llmserver
 ID: fba62709-52b6-4594-98a7-b3a7e2626f3b
 Docker Root Dir: /data/docker
 Debug Mode: false
 Experimental: false
 Insecure Registries:
  ::1/128
  127.0.0.0/8
 Live Restore Enabled: false
 Firewall Backend: iptables
  EnableUserlandProxy: true
  UserlandProxyPath: /usr/bin/docker-proxy


[exit=0]
```

### sudo docker compose version

```console
$ sudo -n docker compose version
Docker Compose version v5.3.0

[exit=0]
```

### sudo docker buildx version

```console
$ sudo -n docker buildx version
github.com/docker/buildx v0.35.0 a319e5b15052cf6557ceb666eb8ff6e32380b782

[exit=0]
```

### hello-world image inspect

```console
$ sudo -n docker image inspect hello-world:latest
[
    {
        "Id": "sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d",
        "RepoTags": [
            "hello-world:latest"
        ],
        "RepoDigests": [
            "hello-world@sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d"
        ],
        "Comment": "buildkit.dockerfile.v0",
        "Created": "2026-03-23T21:33:59.562202219Z",
        "Config": {
            "Env": [
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            ],
            "Cmd": [
                "/hello"
            ],
            "WorkingDir": "/"
        },
        "Architecture": "amd64",
        "Os": "linux",
        "Size": 16227,
        "RootFS": {
            "Type": "layers",
            "Layers": [
                "sha256:897b3f2a7c1bc2f3d02432f7892fe31c6272c521ad4d70257df624504a3238b4"
            ]
        },
        "Metadata": {
            "LastTagTime": "2026-07-02T19:39:50.349224487Z"
        },
        "Descriptor": {
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "digest": "sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d",
            "size": 12212
        },
        "Identity": {
            "Pull": [
                {
                    "Repository": "docker.io/library/hello-world"
                }
            ]
        }
    }
]

[exit=0]
```

### sudo docker system df

```console
$ sudo -n docker system df
TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          1         0         38.09kB   25.87kB (67%)
Containers      0         0         0B        0B
Local Volumes   0         0         0B        0B
Build Cache     0         0         0B        0B

[exit=0]
```

### Docker/containerd root and data sizes

```console
$ sudo -n du -sh /var/lib/docker /var/lib/containerd '/data/docker' '/data/containerd' '/data/containerd/root' 2>/dev/null || true
236K	/data/docker
336K	/data/containerd

[exit=0]
```

### post-verification root-disk guard

```console
$ scripts/common/root-disk-guard.sh
PASS: root disk guard passed

[exit=0]
```

## Docker/containerd Verification Summary

- Docker installed: yes
- containerd installed: yes
- Docker Root Dir: /data/docker
- containerd root: /data/containerd/root
- containerd state: /run/containerd
- hello-world image present: yes
- root-disk guard: PASS

## Docker/containerd Verification Conclusion

PASS
