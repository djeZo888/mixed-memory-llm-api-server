# M1 VM Preflight Report

## Milestone

- Milestone ID: M1
- Name: VM preflight
- Timestamp: 2026-07-02T00:40:26+00:00
- Hostname: llmserver
- User: user
- Working directory: /home/user/codex-bootstrap/mixed-memory-llm-api-server
- Branch name: milestone/m1-vm-preflight

## Git Remote

```text
origin	git@github.com:djeZo888/mixed-memory-llm-api-server.git (fetch)
origin	git@github.com:djeZo888/mixed-memory-llm-api-server.git (push)
```

## Executive Summary

- Codex status: found at /usr/local/bin/codex; version: codex-cli 0.142.4; login: Logged in using ChatGPT
- Sudo status: PASS: sudo -n true worked after sudo -k; sudo -n id: uid=0(root) gid=0(root) groups=0(root)
- Root disk summary: source=/dev/mapper/ubuntu--vg-ubuntu--lv; fstype=ext4; df=15G total, 7.2G used, fstype ext4
- Candidate data disk summary: likely candidate: /dev/sdb 2T disk QEMU HARDDISK aidata2tb; no top-level filesystem or mountpoint detected
- /data state: /data exists but is not a mountpoint; likely a root-disk directory until M2 verifies
- GPU state: nvidia-smi not installed or not in PATH
- Network state: basic DNS for huggingface.co and github.com resolved
- Firewall/listener summary: see Firewall and listeners section
- Failed systemd units: failed systemd units: 0
- Current boot errors: current boot error lines captured: 12

## Identity

### hostname

```console
$ hostname
llmserver

[exit=0]
```

### whoami

```console
$ whoami
user

[exit=0]
```

### id

```console
$ id
uid=1000(user) gid=1000(user) groups=1000(user),4(adm),24(cdrom),27(sudo),30(dip),46(plugdev),101(lxd)

[exit=0]
```

### date -Is

```console
$ date -Is
2026-07-02T00:40:26+00:00

[exit=0]
```

### pwd

```console
$ pwd
/home/user/codex-bootstrap/mixed-memory-llm-api-server

[exit=0]
```

## OS

### /etc/os-release

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
Linux llmserver 6.8.0-124-generic #124-Ubuntu SMP PREEMPT_DYNAMIC Tue May 26 13:00:45 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux

[exit=0]
```

## Codex

### command -v codex

```console
$ command -v codex
/usr/local/bin/codex

[exit=0]
```

### ls -l "$(command -v codex)"

```console
$ ls -l "$(command -v codex)"
lrwxrwxrwx 1 root root 27 Jul  1 08:45 /usr/local/bin/codex -> /home/user/.local/bin/codex

[exit=0]
```

### codex --version

```console
$ codex --version
codex-cli 0.142.4

[exit=0]
```

### codex login status

```console
$ codex login status
Logged in using ChatGPT

[exit=0]
```

## Sudo

### sudo -k

```console
$ sudo -k

[exit=0]
```

### sudo -n true

```console
$ sudo -n true

[exit=0]
```

### sudo -n id

```console
$ sudo -n id
uid=0(root) gid=0(root) groups=0(root)

[exit=0]
```

## Root Filesystem

### df -hT /

```console
$ df -hT /
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.3G  7.2G  47% /

[exit=0]
```

### findmnt /

```console
$ findmnt /
TARGET SOURCE                            FSTYPE OPTIONS
/      /dev/mapper/ubuntu--vg-ubuntu--lv ext4   rw,relatime

[exit=0]
```

## Block Devices

### lsblk block inventory

```console
$ lsblk -o NAME\,PATH\,SIZE\,TYPE\,FSTYPE\,LABEL\,UUID\,MOUNTPOINTS\,MODEL\,SERIAL
NAME                      PATH                               SIZE TYPE FSTYPE      LABEL UUID                                   MOUNTPOINTS MODEL         SERIAL
sda                       /dev/sda                            32G disk                                                                      QEMU HARDDISK drive-scsi0
├─sda1                    /dev/sda1                            1G part vfat              BBE0-E924                              /boot/efi
├─sda2                    /dev/sda2                            2G part ext4              1e35ddc8-6f3c-4eec-9650-6ef93d252b3b   /boot
└─sda3                    /dev/sda3                         28.9G part LVM2_member       2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp
  └─ubuntu--vg-ubuntu--lv /dev/mapper/ubuntu--vg-ubuntu--lv 14.5G lvm  ext4              bc752bce-bb3f-4802-8adf-69c45a88689d   /
sdb                       /dev/sdb                             2T disk                                                                      QEMU HARDDISK aidata2tb

[exit=0]
```

### sudo -n blkid

```console
$ sudo -n blkid
/dev/mapper/ubuntu--vg-ubuntu--lv: UUID="bc752bce-bb3f-4802-8adf-69c45a88689d" BLOCK_SIZE="4096" TYPE="ext4"
/dev/sda2: UUID="1e35ddc8-6f3c-4eec-9650-6ef93d252b3b" BLOCK_SIZE="4096" TYPE="ext4" PARTUUID="d7b915e9-2dcd-45c9-9726-aefaa84b03eb"
/dev/sda3: UUID="2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp" TYPE="LVM2_member" PARTUUID="a8bd8ebb-e8b5-4fca-9bfc-dade9a0d89fb"
/dev/sda1: UUID="BBE0-E924" BLOCK_SIZE="512" TYPE="vfat" PARTUUID="3cf45807-c1be-47ef-966b-fc2f51bdf10a"

[exit=0]
```

## /data State

### findmnt /data

```console
$ findmnt /data || true

[exit=0]
```

### ls -ld /data

```console
$ if [ -e /data ]; then ls -ld /data; else echo "/data does not exist"; fi
drwxr-xr-x 4 root root 4096 Jul  1 00:52 /data

[exit=0]
```

### sudo -n find /data -maxdepth 4 -ls

```console
$ if [ -e /data ]; then sudo -n find /data -maxdepth 4 -ls; else echo "/data does not exist"; fi
   393230      4 drwxr-xr-x   4 root     root         4096 Jul  1 00:52 /data
   393231      4 drwxr-xr-x   2 root     root         4096 Jun 30 22:38 /data/docker
   393262      4 drwxr-xr-x   3 root     root         4096 Jul  1 00:52 /data/services
   393263      4 drwxr-xr-x   2 root     root         4096 Jul  1 00:52 /data/services/codex-smoke-test

[exit=0]
```

## GPU Inventory

### lspci display inventory

```console
$ if command -v lspci >/dev/null 2>&1; then lspci -nn | egrep -i 'nvidia|vga|3d|display' || true; else echo 'lspci not installed'; fi
00:01.0 VGA compatible controller [0300]: Device [1234:1111] (rev 02)
01:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
01:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)
02:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
02:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)

[exit=0]
```

### nvidia-smi

```console
$ if command -v nvidia-smi >/dev/null 2>&1; then nvidia-smi; else echo "nvidia-smi not installed or not in PATH"; fi
nvidia-smi not installed or not in PATH

[exit=0]
```

### current boot journal nvidia/nouveau

```console
$ journalctl -b --no-pager 2>/dev/null | egrep -i 'nvidia|nouveau' | tail -n 200 || true
Jul 01 22:07:17 llmserver kernel: input: HDA NVidia HDMI/DP,pcm=3 as /devices/pci0000:00/0000:00:1c.1/0000:02:00.1/sound/card2/input10
Jul 01 22:07:17 llmserver kernel: input: HDA NVidia HDMI/DP,pcm=7 as /devices/pci0000:00/0000:00:1c.1/0000:02:00.1/sound/card2/input11
Jul 01 22:07:17 llmserver kernel: input: HDA NVidia HDMI/DP,pcm=8 as /devices/pci0000:00/0000:00:1c.1/0000:02:00.1/sound/card2/input12
Jul 01 22:07:17 llmserver kernel: input: HDA NVidia HDMI/DP,pcm=9 as /devices/pci0000:00/0000:00:1c.1/0000:02:00.1/sound/card2/input13
Jul 01 22:07:17 llmserver kernel: input: HDA NVidia HDMI/DP,pcm=3 as /devices/pci0000:00/0000:00:1c.0/0000:01:00.1/sound/card1/input6
Jul 01 22:07:17 llmserver kernel: input: HDA NVidia HDMI/DP,pcm=7 as /devices/pci0000:00/0000:00:1c.0/0000:01:00.1/sound/card1/input7
Jul 01 22:07:17 llmserver kernel: input: HDA NVidia HDMI/DP,pcm=8 as /devices/pci0000:00/0000:00:1c.0/0000:01:00.1/sound/card1/input8
Jul 01 22:07:17 llmserver kernel: input: HDA NVidia HDMI/DP,pcm=9 as /devices/pci0000:00/0000:00:1c.0/0000:01:00.1/sound/card1/input9
Jul 01 22:07:17 llmserver kernel: nouveau 0000:01:00.0: unknown chipset (1b2000a1)
Jul 01 22:07:17 llmserver kernel: nouveau 0000:02:00.0: unknown chipset (1b2000a1)

[exit=0]
```

## Network

### ip -br addr

```console
$ ip -br addr
lo               UNKNOWN        127.0.0.1/8 ::1/128
enp6s18          UP             10.156.100.60/24 metric 100 2a00:ee2:2700:2c01:be24:11ff:feb5:6dda/64 fe80::be24:11ff:feb5:6dda/64

[exit=0]
```

### ip route

```console
$ ip route
default via 10.156.100.1 dev enp6s18 proto dhcp src 10.156.100.60 metric 100
10.156.100.0/24 dev enp6s18 proto kernel scope link src 10.156.100.60 metric 100
10.156.100.1 dev enp6s18 proto dhcp scope link src 10.156.100.60 metric 100

[exit=0]
```

### getent hosts huggingface.co

```console
$ getent hosts huggingface.co
2600:9000:2208:b600:17:b174:6d00:93a1 huggingface.co
2600:9000:2208:ba00:17:b174:6d00:93a1 huggingface.co
2600:9000:2208:9c00:17:b174:6d00:93a1 huggingface.co
2600:9000:2208:400:17:b174:6d00:93a1 huggingface.co
2600:9000:2208:a400:17:b174:6d00:93a1 huggingface.co
2600:9000:2208:6e00:17:b174:6d00:93a1 huggingface.co
2600:9000:2208:a200:17:b174:6d00:93a1 huggingface.co
2600:9000:2208:3200:17:b174:6d00:93a1 huggingface.co

[exit=0]
```

### getent hosts github.com

```console
$ getent hosts github.com
140.82.121.4    github.com

[exit=0]
```

### getent hosts docker.com

```console
$ getent hosts docker.com
2620:12a:8001::4 docker.com
2620:12a:8000::4 docker.com

[exit=0]
```

### getent hosts nvidia.com

```console
$ getent hosts nvidia.com
34.194.97.138   nvidia.com

[exit=0]
```

### curl -I --max-time 10 https://huggingface.co

```console
$ curl -I --max-time 10 https://huggingface.co
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed

  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  0  171k    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
HTTP/2 200 
content-type: text/html; charset=utf-8
content-length: 175992
date: Thu, 02 Jul 2026 00:39:57 GMT
etag: W/"2af78-UopbDCAp9p/G7AZsJ199iJ1WEI4"
x-powered-by: huggingface-moon
x-request-id: Root=1-6a45b35d-36a96984746db15079438508
ratelimit: "pages";r=98;t=224
ratelimit-policy: "fixed window";"pages";q=100;w=300
cross-origin-opener-policy: same-origin
referrer-policy: strict-origin-when-cross-origin
x-frame-options: DENY
x-cache: Hit from cloudfront
via: 1.1 354d7bf1502cddab4e6578e49dee68d4.cloudfront.net (CloudFront)
x-amz-cf-pop: MXP63-P7
x-amz-cf-id: aFmDLRZh0EwK3hN_EHeJuqW9JsNLSkh0ry2dQ-E1e6vLyPljFnvBBQ==
age: 29


[exit=0]
```

### curl -I --max-time 10 https://github.com

```console
$ curl -I --max-time 10 https://github.com
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed

  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0HTTP/2 200 
date: Thu, 02 Jul 2026 00:40:23 GMT
content-type: text/html; charset=utf-8
vary: X-PJAX, X-PJAX-Container, Turbo-Visit, Turbo-Frame, X-Requested-With, Accept-Language, Sec-Fetch-Site,Accept-Encoding, Accept, X-Requested-With
content-language: en-US
etag: W/"0f50e28d5bca8b2bf5d062131e9768e6"
cache-control: max-age=0, private, must-revalidate
strict-transport-security: max-age=31536000; includeSubdomains; preload
x-frame-options: deny
x-content-type-options: nosniff
x-xss-protection: 0
referrer-policy: origin-when-cross-origin, strict-origin-when-cross-origin
content-security-policy: default-src 'none'; base-uri 'self'; child-src github.githubassets.com github.com/assets-cdn/worker/ github.com/assets/ gist.github.com/assets-cdn/worker/; connect-src 'self' uploads.github.com www.githubstatus.com collector.github.com raw.githubusercontent.com api.github.com github-cloud.s3.amazonaws.com github-production-repository-file-5c1aeb.s3.amazonaws.com github-production-upload-manifest-file-7fdce7.s3.amazonaws.com github-production-user-asset-6210df.s3.amazonaws.com *.rel.tunnels.api.visualstudio.com wss://*.rel.tunnels.api.visualstudio.com github.githubassets.com objects-origin.githubusercontent.com copilot-proxy.githubusercontent.com proxy.individual.githubcopilot.com proxy.business.githubcopilot.com proxy.enterprise.githubcopilot.com *.actions.githubusercontent.com wss://*.actions.githubusercontent.com productionresultssa0.blob.core.windows.net productionresultssa1.blob.core.windows.net productionresultssa2.blob.core.windows.net productionresultssa3.blob.core.windows.net productionresultssa4.blob.core.windows.net productionresultssa5.blob.core.windows.net productionresultssa6.blob.core.windows.net productionresultssa7.blob.core.windows.net productionresultssa8.blob.core.windows.net productionresultssa9.blob.core.windows.net productionresultssa10.blob.core.windows.net productionresultssa11.blob.core.windows.net productionresultssa12.blob.core.windows.net productionresultssa13.blob.core.windows.net productionresultssa14.blob.core.windows.net productionresultssa15.blob.core.windows.net productionresultssa16.blob.core.windows.net productionresultssa17.blob.core.windows.net productionresultssa18.blob.core.windows.net productionresultssa19.blob.core.windows.net github-production-repository-image-32fea6.s3.amazonaws.com github-production-release-asset-2e65be.s3.amazonaws.com insights.github.com wss://alive.github.com wss://alive-staging.github.com api.githubcopilot.com api.individual.githubcopilot.com api.business.githubcopilot.com api.enterprise.githubcopilot.com wss://production-copilot-host.webpubsub.azure.com edge.fullstory.com rs.fullstory.com; font-src github.githubassets.com; form-action 'self' github.com gist.github.com copilot-workspace.githubnext.com objects-origin.githubusercontent.com; frame-ancestors 'none'; frame-src viewscreen.githubusercontent.com notebooks.githubusercontent.com www.youtube-nocookie.com; img-src 'self' data: blob: github.githubassets.com media.githubusercontent.com camo.githubusercontent.com identicons.github.com avatars.githubusercontent.com private-avatars.githubusercontent.com github-cloud.s3.amazonaws.com objects.githubusercontent.com release-assets.githubusercontent.com secured-user-images.githubusercontent.com user-images.githubusercontent.com private-user-images.githubusercontent.com opengraph.githubassets.com marketplace-screenshots.githubusercontent.com copilotprodattachments.blob.core.windows.net/github-production-copilot-attachments/ github-production-user-asset-6210df.s3.amazonaws.com customer-stories-feed.github.com spotlights-feed.github.com explore-feed.github.com objects-origin.githubusercontent.com *.githubusercontent.com images.ctfassets.net/8aevphvgewt8/; manifest-src 'self'; media-src github.com user-images.githubusercontent.com secured-user-images.githubusercontent.com private-user-images.githubusercontent.com github-production-user-asset-6210df.s3.amazonaws.com gist.github.com github.githubassets.com assets.ctfassets.net/8aevphvgewt8/ videos.ctfassets.net/8aev
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
phvgewt8/; script-src github.githubassets.com; style-src 'unsafe-inline' github.githubassets.com; upgrade-insecure-requests; worker-src github.githubassets.com github.com/assets-cdn/worker/ github.com/assets/ gist.github.com/assets-cdn/worker/
server: github.com
accept-ranges: bytes
set-cookie: _gh_sess=7d6gdADzZXfartnDXfJ0df8ZNON4qaqKsJZ2cxy9SK1Ie1eQMcbmIfd07Xz2z%2BjLz3ltP8%2FLUURxaaMzb3PjrWjerrrhwqYD0bqfP1ayLAO5gXEspUIkwO6ZgOsE0X1h8r0F1mWcIX8WH7nNU9IHlP6O%2F%2FuZL3kHGC20Kvm2yARWfC%2BO0YOIv6SZpE0NADXAVYEpXFCirx5soYAiyjvtuT7d7PbV1JiJ8%2FEA6EzCx%2Fr7SBeojZetdec4sMffHax0kVBb6CiuejX%2BuTNe5D5a2g%3D%3D--PDuOPVsGcMwcAjVG--KWmSXCyjH1ZY6Z7uNBMT4A%3D%3D; path=/; HttpOnly; secure; SameSite=Lax
set-cookie: _octo=GH1.1.1450022901.1782952826; expires=Fri, 02 Jul 2027 00:40:26 GMT; domain=.github.com; path=/; secure; SameSite=Lax
set-cookie: logged_in=no; expires=Fri, 02 Jul 2027 00:40:26 GMT; domain=.github.com; path=/; HttpOnly; secure; SameSite=Lax
x-github-request-id: A682:31FFBC:16B0B7:1319D3:6A45B37A


[exit=0]
```

## Firewall And Listeners

### sudo -n ufw status verbose

```console
$ sudo -n ufw status verbose || true
Status: inactive

[exit=0]
```

### sudo -n ss -tulpn || ss -tulpn

```console
$ sudo -n ss -tulpn || ss -tulpn || true
Netid State  Recv-Q Send-Q         Local Address:Port Peer Address:PortProcess
udp   UNCONN 0      0                 127.0.0.54:53        0.0.0.0:*    users:(("systemd-resolve",pid=1978,fd=16))
udp   UNCONN 0      0              127.0.0.53%lo:53        0.0.0.0:*    users:(("systemd-resolve",pid=1978,fd=14))
udp   UNCONN 0      0      10.156.100.60%enp6s18:68        0.0.0.0:*    users:(("systemd-network",pid=1866,fd=21))
tcp   LISTEN 0      4096                 0.0.0.0:22        0.0.0.0:*    users:(("sshd",pid=2187,fd=3),("systemd",pid=1,fd=90))
tcp   LISTEN 0      4096              127.0.0.54:53        0.0.0.0:*    users:(("systemd-resolve",pid=1978,fd=17))
tcp   LISTEN 0      4096           127.0.0.53%lo:53        0.0.0.0:*    users:(("systemd-resolve",pid=1978,fd=15))
tcp   LISTEN 0      4096                    [::]:22           [::]:*    users:(("sshd",pid=2187,fd=4),("systemd",pid=1,fd=91))

[exit=0]
```

## System Health

### systemctl --failed --no-pager

```console
$ systemctl --failed --no-pager
  UNIT LOAD ACTIVE SUB DESCRIPTION

0 loaded units listed.

[exit=0]
```

### journalctl -b -p err -n 100 --no-pager

```console
$ journalctl -b -p err -n 100 --no-pager
Jul 01 22:07:16 llmserver kernel: RDSEED32 is broken. Disabling the corresponding CPUID bit.
Jul 01 22:07:16 llmserver kernel: shpchp 0000:05:01.0: pci_hp_register failed with error -16
Jul 01 22:07:16 llmserver kernel: shpchp 0000:05:01.0: Slot initialization failed
Jul 01 22:07:16 llmserver kernel: shpchp 0000:05:02.0: pci_hp_register failed with error -16
Jul 01 22:07:16 llmserver kernel: shpchp 0000:05:02.0: Slot initialization failed
Jul 01 22:07:16 llmserver kernel: shpchp 0000:05:03.0: pci_hp_register failed with error -16
Jul 01 22:07:16 llmserver kernel: shpchp 0000:05:03.0: Slot initialization failed
Jul 01 22:07:16 llmserver kernel: shpchp 0000:05:04.0: pci_hp_register failed with error -16
Jul 01 22:07:16 llmserver kernel: shpchp 0000:05:04.0: Slot initialization failed
Jul 01 22:07:17 llmserver kernel: snd_hda_intel 0000:00:1b.0: no codecs found!
Jul 01 22:07:17 llmserver kernel: nouveau 0000:01:00.0: unknown chipset (1b2000a1)
Jul 01 22:07:17 llmserver kernel: nouveau 0000:02:00.0: unknown chipset (1b2000a1)

[exit=0]
```


## Post-Run Repository Checks

- `bash -n scripts/preflight/vm-preflight.sh`: PASS.
- `bash -n tests/shell/test-vm-preflight-static.sh`: PASS.
- `tests/shell/test-vm-preflight-static.sh`: PASS.
- `scripts/preflight/vm-preflight.sh`: PASS; generated this report.
- `git diff --check`: PASS after report output whitespace normalization.
- Grep-based secret scan: PASS; matches were intentional safety documentation, ignore/workflow references, and redaction patterns only. No real secret was detected.

## Scope Confirmation

- No disk, partition, filesystem, mount, or fstab changes were made.
- /dev/sdb was not initialized, partitioned, formatted, mounted, or otherwise modified.
- /data was not created, mounted, initialized, or modified.
- Docker was not installed or configured.
- NVIDIA drivers or toolkit were not installed or configured.
- systemd was not configured.
- No API was exposed.
- No models were downloaded.
- No secrets, tokens, passwords, private keys, auth files, real .env files, MEMORY.md, or local Codex memory files were read or written.

## Conclusion

PASS

The VM preflight completed. Critical checks for Codex availability and non-interactive sudo passed. Review warnings and raw command output before M2.

## Next Recommended Milestone

M2 data disk dry-run.
