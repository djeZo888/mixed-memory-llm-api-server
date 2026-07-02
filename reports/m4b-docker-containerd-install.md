
## Docker Engine Install

- Timestamp: 2026-07-02T19:37:32+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m4b-docker-containerd-install

### pre-install root-disk guard

```console
$ scripts/common/root-disk-guard.sh
PASS: root disk guard passed

[exit=0]
```

### conflicting package check

```console
$ dpkg -l | grep -E 'docker|containerd|runc' || true

[exit=0]
```

### create temporary service auto-start blocker

```console
$ sudo -n tee /usr/sbin/policy-rc.d
#!/bin/sh
exit 101

[exit=0]
```

### set temporary service auto-start blocker mode

```console
$ sudo -n chmod 0755 /usr/sbin/policy-rc.d

[exit=0]
```

### create Docker apt keyring directory

```console
$ sudo -n install -m 0755 -d /etc/apt/keyrings

[exit=0]
```

### install Docker apt signing key

```console
$ curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo -n tee '/etc/apt/keyrings/docker.asc' >/dev/null

[exit=0]
```

### set Docker apt signing key permissions

```console
$ sudo -n chmod a+r /etc/apt/keyrings/docker.asc

[exit=0]
```

### write Docker apt source

```console
$ sudo -n tee /etc/apt/sources.list.d/docker.sources
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
Architectures: amd64

[exit=0]
```

### apt update for Docker repository

```console
$ sudo -n apt-get update
Hit:1 http://si.archive.ubuntu.com/ubuntu noble InRelease
Get:2 http://si.archive.ubuntu.com/ubuntu noble-updates InRelease [126 kB]
Get:3 https://download.docker.com/linux/ubuntu noble InRelease [48.5 kB]
Get:4 http://si.archive.ubuntu.com/ubuntu noble-backports InRelease [126 kB]
Get:5 http://security.ubuntu.com/ubuntu noble-security InRelease [126 kB]
Get:6 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 Packages [1074 kB]
Get:7 https://download.docker.com/linux/ubuntu noble/stable amd64 Packages [59.3 kB]
Get:8 http://si.archive.ubuntu.com/ubuntu noble-updates/main Translation-en [266 kB]
Get:9 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 Components [180 kB]
Get:10 http://si.archive.ubuntu.com/ubuntu noble-updates/main amd64 c-n-f Metadata [17.6 kB]
Get:11 http://si.archive.ubuntu.com/ubuntu noble-updates/restricted amd64 Packages [1196 kB]
Get:12 http://security.ubuntu.com/ubuntu noble-security/main amd64 Packages [825 kB]
Get:13 http://si.archive.ubuntu.com/ubuntu noble-updates/universe amd64 Packages [1659 kB]
Get:14 http://security.ubuntu.com/ubuntu noble-security/main Translation-en [186 kB]
Get:15 http://security.ubuntu.com/ubuntu noble-security/main amd64 Components [44.9 kB]
Get:16 http://security.ubuntu.com/ubuntu noble-security/main amd64 c-n-f Metadata [11.8 kB]
Get:17 http://security.ubuntu.com/ubuntu noble-security/universe amd64 Packages [1173 kB]
Get:18 http://si.archive.ubuntu.com/ubuntu noble-updates/universe amd64 Components [388 kB]
Get:19 http://si.archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 Components [940 B]
Get:20 http://si.archive.ubuntu.com/ubuntu noble-backports/main amd64 Components [5760 B]
Get:21 http://si.archive.ubuntu.com/ubuntu noble-backports/universe amd64 Components [10.6 kB]
Get:22 http://security.ubuntu.com/ubuntu noble-security/universe amd64 Components [76.3 kB]
Get:23 http://security.ubuntu.com/ubuntu noble-security/universe amd64 c-n-f Metadata [24.2 kB]
Fetched 7625 kB in 1s (12.9 MB/s)
Reading package lists...

[exit=0]
```

### install Docker Engine packages

```console
$ sudo -n apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
Reading package lists...
Building dependency tree...
Reading state information...
The following packages were automatically installed and are no longer required:
  libfwupd2 libgusb2
Use 'sudo apt autoremove' to remove them.
The following additional packages will be installed:
  docker-ce-rootless-extras pigz
Suggested packages:
  cgroupfs-mount | cgroup-lite docker-model-plugin
The following NEW packages will be installed:
  containerd.io docker-buildx-plugin docker-ce docker-ce-cli
  docker-ce-rootless-extras docker-compose-plugin pigz
0 upgraded, 7 newly installed, 0 to remove and 13 not upgraded.
Need to get 99.3 MB of archives.
After this operation, 380 MB of additional disk space will be used.
Get:1 http://si.archive.ubuntu.com/ubuntu noble/universe amd64 pigz amd64 2.8-1 [65.6 kB]
Get:2 https://download.docker.com/linux/ubuntu noble/stable amd64 containerd.io amd64 2.2.5-1~ubuntu.24.04~noble [23.6 MB]
Get:3 https://download.docker.com/linux/ubuntu noble/stable amd64 docker-ce-cli amd64 5:29.6.1-1~ubuntu.24.04~noble [16.9 MB]
Get:4 https://download.docker.com/linux/ubuntu noble/stable amd64 docker-ce amd64 5:29.6.1-1~ubuntu.24.04~noble [23.3 MB]
Get:5 https://download.docker.com/linux/ubuntu noble/stable amd64 docker-buildx-plugin amd64 0.35.0-1~ubuntu.24.04~noble [17.2 MB]
Get:6 https://download.docker.com/linux/ubuntu noble/stable amd64 docker-ce-rootless-extras amd64 5:29.6.1-1~ubuntu.24.04~noble [10.2 MB]
Get:7 https://download.docker.com/linux/ubuntu noble/stable amd64 docker-compose-plugin amd64 5.3.0-1~ubuntu.24.04~noble [8083 kB]
debconf: unable to initialize frontend: Dialog
debconf: (Dialog frontend will not work on a dumb terminal, an emacs shell buffer, or without a controlling terminal.)
debconf: falling back to frontend: Readline
debconf: unable to initialize frontend: Readline
debconf: (This frontend requires a controlling tty.)
debconf: falling back to frontend: Teletype
dpkg-preconfigure: unable to re-open stdin:
Fetched 99.3 MB in 2s (61.0 MB/s)
Selecting previously unselected package containerd.io.
(Reading database ... (Reading database ... 5%(Reading database ... 10%(Reading database ... 15%(Reading database ... 20%(Reading database ... 25%(Reading database ... 30%(Reading database ... 35%(Reading database ... 40%(Reading database ... 45%(Reading database ... 50%(Reading database ... 55%(Reading database ... 60%(Reading database ... 65%(Reading database ... 70%(Reading database ... 75%(Reading database ... 80%(Reading database ... 85%(Reading database ... 90%(Reading database ... 95%(Reading database ... 100%(Reading database ... 126785 files and directories currently installed.)
Preparing to unpack .../0-containerd.io_2.2.5-1~ubuntu.24.04~noble_amd64.deb ...
Unpacking containerd.io (2.2.5-1~ubuntu.24.04~noble) ...
Selecting previously unselected package docker-ce-cli.
Preparing to unpack .../1-docker-ce-cli_5%3a29.6.1-1~ubuntu.24.04~noble_amd64.deb ...
Unpacking docker-ce-cli (5:29.6.1-1~ubuntu.24.04~noble) ...
Selecting previously unselected package docker-ce.
Preparing to unpack .../2-docker-ce_5%3a29.6.1-1~ubuntu.24.04~noble_amd64.deb ...
Unpacking docker-ce (5:29.6.1-1~ubuntu.24.04~noble) ...
Selecting previously unselected package pigz.
Preparing to unpack .../3-pigz_2.8-1_amd64.deb ...
Unpacking pigz (2.8-1) ...
Selecting previously unselected package docker-buildx-plugin.
Preparing to unpack .../4-docker-buildx-plugin_0.35.0-1~ubuntu.24.04~noble_amd64.deb ...
Unpacking docker-buildx-plugin (0.35.0-1~ubuntu.24.04~noble) ...
Selecting previously unselected package docker-ce-rootless-extras.
Preparing to unpack .../5-docker-ce-rootless-extras_5%3a29.6.1-1~ubuntu.24.04~noble_amd64.deb ...
Unpacking docker-ce-rootless-extras (5:29.6.1-1~ubuntu.24.04~noble) ...
Selecting previously unselected package docker-compose-plugin.
Preparing to unpack .../6-docker-compose-plugin_5.3.0-1~ubuntu.24.04~noble_amd64.deb ...
Unpacking docker-compose-plugin (5.3.0-1~ubuntu.24.04~noble) ...
Setting up docker-buildx-plugin (0.35.0-1~ubuntu.24.04~noble) ...
Setting up containerd.io (2.2.5-1~ubuntu.24.04~noble) ...
Created symlink /etc/systemd/system/multi-user.target.wants/containerd.service → /usr/lib/systemd/system/containerd.service.
/usr/sbin/policy-rc.d returned 101, not running 'start containerd.service'
Setting up docker-compose-plugin (5.3.0-1~ubuntu.24.04~noble) ...
Setting up docker-ce-cli (5:29.6.1-1~ubuntu.24.04~noble) ...
Setting up pigz (2.8-1) ...
Setting up docker-ce-rootless-extras (5:29.6.1-1~ubuntu.24.04~noble) ...
Setting up docker-ce (5:29.6.1-1~ubuntu.24.04~noble) ...
invoke-rc.d: policy-rc.d denied execution of start.
Created symlink /etc/systemd/system/multi-user.target.wants/docker.service → /usr/lib/systemd/system/docker.service.
Created symlink /etc/systemd/system/sockets.target.wants/docker.socket → /usr/lib/systemd/system/docker.socket.
/usr/sbin/policy-rc.d returned 101, not running 'start docker.service docker.socket'
Processing triggers for man-db (2.12.0-4build2) ...
debconf: unable to initialize frontend: Dialog
debconf: (Dialog frontend will not work on a dumb terminal, an emacs shell buffer, or without a controlling terminal.)
debconf: falling back to frontend: Readline
debconf: unable to initialize frontend: Readline
debconf: (This frontend requires a controlling tty.)
debconf: falling back to frontend: Teletype

Running kernel seems to be up-to-date.

No services need to be restarted.

No containers need to be restarted.

No user sessions are running outdated binaries.

No VM guests are running outdated hypervisor (qemu) binaries on this host.

[exit=0]
```

### remove temporary service auto-start blocker

```console
$ sudo -n rm -f /usr/sbin/policy-rc.d

[exit=0]
```

## Docker Engine Install

- Timestamp: 2026-07-02T19:38:19+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m4b-docker-containerd-install

### pre-install root-disk guard

```console
$ scripts/common/root-disk-guard.sh
PASS: root disk guard passed

[exit=0]
```

### conflicting package check

```console
$ dpkg -l | grep -E 'docker|containerd|runc' || true
ii  containerd.io                         2.2.5-1~ubuntu.24.04~noble                       amd64        An open and reliable container runtime
ii  docker-buildx-plugin                  0.35.0-1~ubuntu.24.04~noble                      amd64        Docker Buildx plugin extends build capabilities with BuildKit.
ii  docker-ce                             5:29.6.1-1~ubuntu.24.04~noble                    amd64        Docker: the open-source application container engine
ii  docker-ce-cli                         5:29.6.1-1~ubuntu.24.04~noble                    amd64        Docker CLI: the open-source application container engine
ii  docker-ce-rootless-extras             5:29.6.1-1~ubuntu.24.04~noble                    amd64        Rootless support for Docker.
ii  docker-compose-plugin                 5.3.0-1~ubuntu.24.04~noble                       amd64        Docker Compose (V2) plugin for the Docker CLI.

[exit=0]
```

### create temporary service auto-start blocker

```console
$ sudo -n tee /usr/sbin/policy-rc.d
#!/bin/sh
exit 101

[exit=0]
```

### set temporary service auto-start blocker mode

```console
$ sudo -n chmod 0755 /usr/sbin/policy-rc.d

[exit=0]
```

### create Docker apt keyring directory

```console
$ sudo -n install -m 0755 -d /etc/apt/keyrings

[exit=0]
```

### install Docker apt signing key

```console
$ curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo -n tee '/etc/apt/keyrings/docker.asc' >/dev/null

[exit=0]
```

### set Docker apt signing key permissions

```console
$ sudo -n chmod a+r /etc/apt/keyrings/docker.asc

[exit=0]
```

### write Docker apt source

```console
$ sudo -n tee /etc/apt/sources.list.d/docker.sources
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
Architectures: amd64

[exit=0]
```

### apt update for Docker repository

```console
$ sudo -n apt-get update
Hit:1 http://si.archive.ubuntu.com/ubuntu noble InRelease
Hit:2 http://si.archive.ubuntu.com/ubuntu noble-updates InRelease
Hit:3 http://si.archive.ubuntu.com/ubuntu noble-backports InRelease
Hit:4 https://download.docker.com/linux/ubuntu noble InRelease
Hit:5 http://security.ubuntu.com/ubuntu noble-security InRelease
Reading package lists...

[exit=0]
```

### install Docker Engine packages

```console
$ sudo -n apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
Reading package lists...
Building dependency tree...
Reading state information...
docker-ce is already the newest version (5:29.6.1-1~ubuntu.24.04~noble).
docker-ce-cli is already the newest version (5:29.6.1-1~ubuntu.24.04~noble).
containerd.io is already the newest version (2.2.5-1~ubuntu.24.04~noble).
docker-buildx-plugin is already the newest version (0.35.0-1~ubuntu.24.04~noble).
docker-compose-plugin is already the newest version (5.3.0-1~ubuntu.24.04~noble).
The following packages were automatically installed and are no longer required:
  libfwupd2 libgusb2
Use 'sudo apt autoremove' to remove them.
0 upgraded, 0 newly installed, 0 to remove and 13 not upgraded.

[exit=0]
```

### remove temporary service auto-start blocker

```console
$ sudo -n rm -f /usr/sbin/policy-rc.d

[exit=0]
```

## Docker Engine Install

- Timestamp: 2026-07-02T19:38:46+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m4b-docker-containerd-install

### pre-install root-disk guard

```console
$ scripts/common/root-disk-guard.sh
PASS: root disk guard passed

[exit=0]
```

### conflicting package check

```console
$ dpkg -l | grep -E 'docker|containerd|runc' || true
ii  containerd.io                         2.2.5-1~ubuntu.24.04~noble                       amd64        An open and reliable container runtime
ii  docker-buildx-plugin                  0.35.0-1~ubuntu.24.04~noble                      amd64        Docker Buildx plugin extends build capabilities with BuildKit.
ii  docker-ce                             5:29.6.1-1~ubuntu.24.04~noble                    amd64        Docker: the open-source application container engine
ii  docker-ce-cli                         5:29.6.1-1~ubuntu.24.04~noble                    amd64        Docker CLI: the open-source application container engine
ii  docker-ce-rootless-extras             5:29.6.1-1~ubuntu.24.04~noble                    amd64        Rootless support for Docker.
ii  docker-compose-plugin                 5.3.0-1~ubuntu.24.04~noble                       amd64        Docker Compose (V2) plugin for the Docker CLI.

[exit=0]
```

### create temporary service auto-start blocker

```console
$ sudo -n tee /usr/sbin/policy-rc.d
#!/bin/sh
exit 101

[exit=0]
```

### set temporary service auto-start blocker mode

```console
$ sudo -n chmod 0755 /usr/sbin/policy-rc.d

[exit=0]
```

### create Docker apt keyring directory

```console
$ sudo -n install -m 0755 -d /etc/apt/keyrings

[exit=0]
```

### install Docker apt signing key

```console
$ curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo -n tee '/etc/apt/keyrings/docker.asc' >/dev/null

[exit=0]
```

### set Docker apt signing key permissions

```console
$ sudo -n chmod a+r /etc/apt/keyrings/docker.asc

[exit=0]
```

### write Docker apt source

```console
$ sudo -n tee /etc/apt/sources.list.d/docker.sources
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
Architectures: amd64

[exit=0]
```

### apt update for Docker repository

```console
$ sudo -n apt-get update
Hit:1 http://si.archive.ubuntu.com/ubuntu noble InRelease
Hit:2 http://si.archive.ubuntu.com/ubuntu noble-updates InRelease
Hit:3 http://si.archive.ubuntu.com/ubuntu noble-backports InRelease
Hit:4 https://download.docker.com/linux/ubuntu noble InRelease
Hit:5 http://security.ubuntu.com/ubuntu noble-security InRelease
Reading package lists...

[exit=0]
```

### install Docker Engine packages

```console
$ sudo -n apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
Reading package lists...
Building dependency tree...
Reading state information...
docker-ce is already the newest version (5:29.6.1-1~ubuntu.24.04~noble).
docker-ce-cli is already the newest version (5:29.6.1-1~ubuntu.24.04~noble).
containerd.io is already the newest version (2.2.5-1~ubuntu.24.04~noble).
docker-buildx-plugin is already the newest version (0.35.0-1~ubuntu.24.04~noble).
docker-compose-plugin is already the newest version (5.3.0-1~ubuntu.24.04~noble).
The following packages were automatically installed and are no longer required:
  libfwupd2 libgusb2
Use 'sudo apt autoremove' to remove them.
0 upgraded, 0 newly installed, 0 to remove and 13 not upgraded.

[exit=0]
```

### remove temporary service auto-start blocker

```console
$ sudo -n rm -f /usr/sbin/policy-rc.d

[exit=0]
```

### installed Docker package versions

```console
$ dpkg-query -W docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
containerd.io	2.2.5-1~ubuntu.24.04~noble
docker-buildx-plugin	0.35.0-1~ubuntu.24.04~noble
docker-ce	5:29.6.1-1~ubuntu.24.04~noble
docker-ce-cli	5:29.6.1-1~ubuntu.24.04~noble
docker-compose-plugin	5.3.0-1~ubuntu.24.04~noble

[exit=0]
```

### post-install root-disk guard

```console
$ scripts/common/root-disk-guard.sh
PASS: root disk guard passed

[exit=0]
```

## Docker/containerd Storage Configuration

- Timestamp: 2026-07-02T19:39:06+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m4b-docker-containerd-install

### pre-configuration /var/lib sizes

```console
$ sudo -n du -sx -m /var/lib/docker /var/lib/containerd 2>/dev/null || true

[exit=0]
```

### create /data Docker/containerd storage directories

```console
$ sudo -n install -m 0711 -o root -g root -d /data/docker /data/containerd /data/containerd/root

[exit=0]
```

### create Docker config directory

```console
$ sudo -n install -m 0755 -d /etc/docker

[exit=0]
```

### write Docker daemon.json data-root

```console
$ sudo -n env DOCKER_DAEMON_JSON=/etc/docker/daemon.json DOCKER_DATA_ROOT=/data/docker python3 -

[exit=0]
```

### validate Docker daemon.json JSON

```console
$ python3 -m json.tool /etc/docker/daemon.json
{
    "data-root": "/data/docker",
    "log-driver": "json-file",
    "log-opts": {
        "max-file": "5",
        "max-size": "100m"
    }
}

[exit=0]
```

### create containerd config directory

```console
$ sudo -n install -m 0755 -d /etc/containerd

[exit=0]
```

### write generated containerd default config

```console
$ sudo -n bash -c containerd\ config\ default\ \>\ \'/etc/containerd/config.toml\'

[exit=0]
```

### configure containerd root and state

```console
$ sudo -n env CONTAINERD_CONFIG=/etc/containerd/config.toml CONTAINERD_ROOT=/data/containerd/root CONTAINERD_STATE=/run/containerd python3 -

[exit=0]
```

### containerd config root/state check

```console
$ grep -E '^(root|state) = ' '/etc/containerd/config.toml'
root = "/data/containerd/root"
state = "/run/containerd"

[exit=0]
```

### containerd config validator availability

```console
$ containerd --help | grep -E 'config' || true
   by using this command. If none of the *config*, *publish*, *oci-hook*, or *help* commands
   A default configuration is used if no TOML configuration is specified or located
   at the default file location. The *containerd config* command can be used to
   generate the default configuration for containerd. The output of that command
   can be used and modified as necessary as a custom configuration.
   config    Information on the containerd config
   --config value, -c value     Path to the configuration file (default: "/etc/containerd/config.toml")

[exit=0]
```

### post-configuration /var/lib and /data sizes

```console
$ sudo -n du -sx -m /var/lib/docker /var/lib/containerd '/data/docker' '/data/containerd' '/data/containerd/root' 2>/dev/null || true
1	/data/docker
1	/data/containerd

[exit=0]
```

### post-configuration root-disk guard

```console
$ scripts/common/root-disk-guard.sh
PASS: root disk guard passed

[exit=0]
```

## Docker/containerd Storage Verification

- Timestamp: 2026-07-02T19:39:57+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m4b-docker-containerd-install

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
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.9G  6.6G  52% /
/dev/sdb1                         ext4  2.0T  2.2M  1.9T   1% /data

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
     Active: active (running) since Thu 2026-07-02 19:39:24 UTC; 33s ago
       Docs: https://containerd.io
    Process: 11130 ExecStartPre=/sbin/modprobe overlay (code=exited, status=0/SUCCESS)
   Main PID: 11131 (containerd)
      Tasks: 25
     Memory: 28.2M (peak: 41.6M)
        CPU: 308ms
     CGroup: /system.slice/containerd.service
             └─11131 /usr/bin/containerd

Jul 02 19:39:24 llmserver containerd[11131]: time="2026-07-02T19:39:24.166756543Z" level=info msg="Registered namespace \"k8s.io\" with NRI"
Jul 02 19:39:24 llmserver containerd[11131]: time="2026-07-02T19:39:24.166760459Z" level=info msg="runtime interface starting up..."
Jul 02 19:39:24 llmserver containerd[11131]: time="2026-07-02T19:39:24.166763734Z" level=info msg="starting plugins..."
Jul 02 19:39:24 llmserver containerd[11131]: time="2026-07-02T19:39:24.166773349Z" level=info msg="Synchronizing NRI (plugin) with current runtime state"
Jul 02 19:39:24 llmserver containerd[11131]: time="2026-07-02T19:39:24.166853052Z" level=info msg="containerd successfully booted in 0.021419s"
Jul 02 19:39:24 llmserver systemd[1]: Started containerd.service - containerd container runtime.
Jul 02 19:39:50 llmserver containerd[11131]: time="2026-07-02T19:39:50.423076374Z" level=info msg="connecting to shim 1fdc753ddca33bf3a7bc5a6879e351e3787fa8716e4cf4ebf792f1ea71dd2bd2" address="unix:///run/containerd/s/330010339f2df944820cd70981de89728a6775137f41d88d49ed7aa6f923a97d" namespace=moby protocol=ttrpc version=3
Jul 02 19:39:50 llmserver containerd[11131]: time="2026-07-02T19:39:50.519713346Z" level=info msg="shim disconnected" id=1fdc753ddca33bf3a7bc5a6879e351e3787fa8716e4cf4ebf792f1ea71dd2bd2 namespace=moby
Jul 02 19:39:50 llmserver containerd[11131]: time="2026-07-02T19:39:50.519744424Z" level=info msg="cleaning up after shim disconnected" id=1fdc753ddca33bf3a7bc5a6879e351e3787fa8716e4cf4ebf792f1ea71dd2bd2 namespace=moby
Jul 02 19:39:50 llmserver containerd[11131]: time="2026-07-02T19:39:50.519751525Z" level=info msg="cleaning up dead shim" id=1fdc753ddca33bf3a7bc5a6879e351e3787fa8716e4cf4ebf792f1ea71dd2bd2 namespace=moby

[exit=0]
```

### systemctl status docker

```console
$ sudo -n systemctl status docker --no-pager
● docker.service - Docker Application Container Engine
     Loaded: loaded (/usr/lib/systemd/system/docker.service; enabled; preset: enabled)
     Active: active (running) since Thu 2026-07-02 19:39:24 UTC; 33s ago
TriggeredBy: ● docker.socket
       Docs: https://docs.docker.com
   Main PID: 11168 (dockerd)
      Tasks: 39
     Memory: 49.0M (peak: 56.1M)
        CPU: 556ms
     CGroup: /system.slice/docker.service
             └─11168 /usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock

Jul 02 19:39:24 llmserver dockerd[11168]: time="2026-07-02T19:39:24.457906108Z" level=info msg="Loading containers: done."
Jul 02 19:39:24 llmserver dockerd[11168]: time="2026-07-02T19:39:24.461991828Z" level=info msg="Docker daemon" commit=8ec5ab3 containerd-snapshotter=true storage-driver=overlayfs version=29.6.1
Jul 02 19:39:24 llmserver dockerd[11168]: time="2026-07-02T19:39:24.462063589Z" level=info msg="Initializing buildkit"
Jul 02 19:39:24 llmserver dockerd[11168]: time="2026-07-02T19:39:24.603073093Z" level=info msg="Completed buildkit initialization"
Jul 02 19:39:24 llmserver dockerd[11168]: time="2026-07-02T19:39:24.606874032Z" level=info msg="Daemon has completed initialization"
Jul 02 19:39:24 llmserver dockerd[11168]: time="2026-07-02T19:39:24.606911250Z" level=info msg="API listen on /run/docker.sock"
Jul 02 19:39:24 llmserver systemd[1]: Started docker.service - Docker Application Container Engine.
Jul 02 19:39:50 llmserver dockerd[11168]: time="2026-07-02T19:39:50.351136850Z" level=info msg="image pulled" digest="sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d" remote="docker.io/library/hello-world:latest"
Jul 02 19:39:50 llmserver dockerd[11168]: time="2026-07-02T19:39:50.490116363Z" level=info msg="sbJoin: gwep4 ''->'759b501e6b19', gwep6 ''->''" eid=759b501e6b19 ep=dreamy_galileo net=bridge nid=ec90f26e2bd5
Jul 02 19:39:50 llmserver dockerd[11168]: time="2026-07-02T19:39:50.519680094Z" level=info msg="received task-delete event from containerd" container=1fdc753ddca33bf3a7bc5a6879e351e3787fa8716e4cf4ebf792f1ea71dd2bd2 module=libcontainerd namespace=moby topic=/tasks/delete type="*events.TaskDelete"

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

## M4B pre-reboot checks and secret scan

- `bash -n scripts/docker/install-docker.sh`: PASS
- `bash -n scripts/docker/configure-docker-data-root.sh`: PASS
- `bash -n scripts/docker/verify-docker-storage.sh`: PASS
- `bash -n tests/shell/test-docker-scripts-static.sh`: PASS
- `tests/shell/test-docker-scripts-static.sh`: PASS
- `scripts/common/require-data-mounted.sh`: PASS
- `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`: PASS
- `scripts/docker/verify-docker-storage.sh`: PASS
- `git diff --check`: PASS
- Grep-based secret scan: matched only intentional documentation, static-test, sanitizer, `.gitignore`, CI, and prior report command strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.

## M4B pre-reboot summary

- Timestamp: 2026-07-02T19:40:09+00:00
- Branch: `milestone/m4b-docker-containerd-install`
- Pre-install state: Docker, dockerd, and containerd were not installed; `/var/lib/docker` and `/var/lib/containerd` were absent.
- Installed package versions:
  - `docker-ce` 5:29.6.1-1~ubuntu.24.04~noble
  - `docker-ce-cli` 5:29.6.1-1~ubuntu.24.04~noble
  - `containerd.io` 2.2.5-1~ubuntu.24.04~noble
  - `docker-buildx-plugin` 0.35.0-1~ubuntu.24.04~noble
  - `docker-compose-plugin` 5.3.0-1~ubuntu.24.04~noble
- Docker apt key path: `/etc/apt/keyrings/docker.asc`
- Docker apt source path: `/etc/apt/sources.list.d/docker.sources`
- Docker daemon config path: `/etc/docker/daemon.json`
- Docker daemon config summary: `data-root` is `/data/docker`; existing JSON log settings are preserved.
- containerd config path: `/etc/containerd/config.toml`
- containerd root: `/data/containerd/root`
- containerd state: `/run/containerd`
- Service status before reboot: `containerd` active, `docker` active
- Docker Root Dir: `/data/docker`
- `/var/lib/docker` state: absent
- `/var/lib/containerd` state: absent
- `/data/docker` size before reboot: 236K
- `/data/containerd` size before reboot: 336K
- Docker `hello-world` result: PASS
- Docker Compose version: v5.3.0
- Docker Buildx version: v0.35.0
- Root-disk guard result: PASS
- Temporary post-reboot service path: `/etc/systemd/system/m4b-post-reboot-verify.service`
- Temporary post-reboot runner path: `/data/services/m4b-post-reboot/m4b-post-reboot-verify.sh`
- Temporary post-reboot log path: `/data/logs/m4b-post-reboot-verify.log`
- User `user` was not added to the `docker` group.
- No NVIDIA Container Toolkit, NVIDIA runtime, CUDA, PyTorch CUDA, KTransformers GPU, ik_llama GPU, model, or API changes were made.
- Reboot verification is pending.

## Docker/containerd Storage Verification

- Timestamp: 2026-07-02T19:42:51+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m4b-docker-containerd-install

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
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.9G  6.6G  52% /
/dev/sdb1                         ext4  2.0T  2.2M  1.9T   1% /data

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
     Active: active (running) since Thu 2026-07-02 19:39:24 UTC; 3min 28s ago
       Docs: https://containerd.io
   Main PID: 11131 (containerd)
      Tasks: 28
     Memory: 25.7M (peak: 41.6M)
        CPU: 626ms
     CGroup: /system.slice/containerd.service
             └─11131 /usr/bin/containerd

Jul 02 19:39:24 llmserver containerd[11131]: time="2026-07-02T19:39:24.166756543Z" level=info msg="Registered namespace \"k8s.io\" with NRI"
Jul 02 19:39:24 llmserver containerd[11131]: time="2026-07-02T19:39:24.166760459Z" level=info msg="runtime interface starting up..."
Jul 02 19:39:24 llmserver containerd[11131]: time="2026-07-02T19:39:24.166763734Z" level=info msg="starting plugins..."
Jul 02 19:39:24 llmserver containerd[11131]: time="2026-07-02T19:39:24.166773349Z" level=info msg="Synchronizing NRI (plugin) with current runtime state"
Jul 02 19:39:24 llmserver containerd[11131]: time="2026-07-02T19:39:24.166853052Z" level=info msg="containerd successfully booted in 0.021419s"
Jul 02 19:39:24 llmserver systemd[1]: Started containerd.service - containerd container runtime.
Jul 02 19:39:50 llmserver containerd[11131]: time="2026-07-02T19:39:50.423076374Z" level=info msg="connecting to shim 1fdc753ddca33bf3a7bc5a6879e351e3787fa8716e4cf4ebf792f1ea71dd2bd2" address="unix:///run/containerd/s/330010339f2df944820cd70981de89728a6775137f41d88d49ed7aa6f923a97d" namespace=moby protocol=ttrpc version=3
Jul 02 19:39:50 llmserver containerd[11131]: time="2026-07-02T19:39:50.519713346Z" level=info msg="shim disconnected" id=1fdc753ddca33bf3a7bc5a6879e351e3787fa8716e4cf4ebf792f1ea71dd2bd2 namespace=moby
Jul 02 19:39:50 llmserver containerd[11131]: time="2026-07-02T19:39:50.519744424Z" level=info msg="cleaning up after shim disconnected" id=1fdc753ddca33bf3a7bc5a6879e351e3787fa8716e4cf4ebf792f1ea71dd2bd2 namespace=moby
Jul 02 19:39:50 llmserver containerd[11131]: time="2026-07-02T19:39:50.519751525Z" level=info msg="cleaning up dead shim" id=1fdc753ddca33bf3a7bc5a6879e351e3787fa8716e4cf4ebf792f1ea71dd2bd2 namespace=moby

[exit=0]
```

### systemctl status docker

```console
$ sudo -n systemctl status docker --no-pager
● docker.service - Docker Application Container Engine
     Loaded: loaded (/usr/lib/systemd/system/docker.service; enabled; preset: enabled)
     Active: active (running) since Thu 2026-07-02 19:39:24 UTC; 3min 27s ago
TriggeredBy: ● docker.socket
       Docs: https://docs.docker.com
   Main PID: 11168 (dockerd)
      Tasks: 39
     Memory: 43.0M (peak: 56.1M)
        CPU: 649ms
     CGroup: /system.slice/docker.service
             └─11168 /usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock

Jul 02 19:39:24 llmserver dockerd[11168]: time="2026-07-02T19:39:24.457906108Z" level=info msg="Loading containers: done."
Jul 02 19:39:24 llmserver dockerd[11168]: time="2026-07-02T19:39:24.461991828Z" level=info msg="Docker daemon" commit=8ec5ab3 containerd-snapshotter=true storage-driver=overlayfs version=29.6.1
Jul 02 19:39:24 llmserver dockerd[11168]: time="2026-07-02T19:39:24.462063589Z" level=info msg="Initializing buildkit"
Jul 02 19:39:24 llmserver dockerd[11168]: time="2026-07-02T19:39:24.603073093Z" level=info msg="Completed buildkit initialization"
Jul 02 19:39:24 llmserver dockerd[11168]: time="2026-07-02T19:39:24.606874032Z" level=info msg="Daemon has completed initialization"
Jul 02 19:39:24 llmserver dockerd[11168]: time="2026-07-02T19:39:24.606911250Z" level=info msg="API listen on /run/docker.sock"
Jul 02 19:39:24 llmserver systemd[1]: Started docker.service - Docker Application Container Engine.
Jul 02 19:39:50 llmserver dockerd[11168]: time="2026-07-02T19:39:50.351136850Z" level=info msg="image pulled" digest="sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d" remote="docker.io/library/hello-world:latest"
Jul 02 19:39:50 llmserver dockerd[11168]: time="2026-07-02T19:39:50.490116363Z" level=info msg="sbJoin: gwep4 ''->'759b501e6b19', gwep6 ''->''" eid=759b501e6b19 ep=dreamy_galileo net=bridge nid=ec90f26e2bd5
Jul 02 19:39:50 llmserver dockerd[11168]: time="2026-07-02T19:39:50.519680094Z" level=info msg="received task-delete event from containerd" container=1fdc753ddca33bf3a7bc5a6879e351e3787fa8716e4cf4ebf792f1ea71dd2bd2 module=libcontainerd namespace=moby topic=/tasks/delete type="*events.TaskDelete"

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

## Docker/containerd Storage Verification

- Timestamp: 2026-07-02T19:43:19+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m4b-docker-containerd-install

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
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.9G  6.6G  52% /
/dev/sdb1                         ext4  2.0T  2.2M  1.9T   1% /data

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
     Active: active (running) since Thu 2026-07-02 19:39:24 UTC; 3min 55s ago
       Docs: https://containerd.io
   Main PID: 11131 (containerd)
      Tasks: 28
     Memory: 28.7M (peak: 41.6M)
        CPU: 697ms
     CGroup: /system.slice/containerd.service
             └─11131 /usr/bin/containerd

Jul 02 19:39:24 llmserver containerd[11131]: time="2026-07-02T19:39:24.166756543Z" level=info msg="Registered namespace \"k8s.io\" with NRI"
Jul 02 19:39:24 llmserver containerd[11131]: time="2026-07-02T19:39:24.166760459Z" level=info msg="runtime interface starting up..."
Jul 02 19:39:24 llmserver containerd[11131]: time="2026-07-02T19:39:24.166763734Z" level=info msg="starting plugins..."
Jul 02 19:39:24 llmserver containerd[11131]: time="2026-07-02T19:39:24.166773349Z" level=info msg="Synchronizing NRI (plugin) with current runtime state"
Jul 02 19:39:24 llmserver containerd[11131]: time="2026-07-02T19:39:24.166853052Z" level=info msg="containerd successfully booted in 0.021419s"
Jul 02 19:39:24 llmserver systemd[1]: Started containerd.service - containerd container runtime.
Jul 02 19:39:50 llmserver containerd[11131]: time="2026-07-02T19:39:50.423076374Z" level=info msg="connecting to shim 1fdc753ddca33bf3a7bc5a6879e351e3787fa8716e4cf4ebf792f1ea71dd2bd2" address="unix:///run/containerd/s/330010339f2df944820cd70981de89728a6775137f41d88d49ed7aa6f923a97d" namespace=moby protocol=ttrpc version=3
Jul 02 19:39:50 llmserver containerd[11131]: time="2026-07-02T19:39:50.519713346Z" level=info msg="shim disconnected" id=1fdc753ddca33bf3a7bc5a6879e351e3787fa8716e4cf4ebf792f1ea71dd2bd2 namespace=moby
Jul 02 19:39:50 llmserver containerd[11131]: time="2026-07-02T19:39:50.519744424Z" level=info msg="cleaning up after shim disconnected" id=1fdc753ddca33bf3a7bc5a6879e351e3787fa8716e4cf4ebf792f1ea71dd2bd2 namespace=moby
Jul 02 19:39:50 llmserver containerd[11131]: time="2026-07-02T19:39:50.519751525Z" level=info msg="cleaning up dead shim" id=1fdc753ddca33bf3a7bc5a6879e351e3787fa8716e4cf4ebf792f1ea71dd2bd2 namespace=moby

[exit=0]
```

### systemctl status docker

```console
$ sudo -n systemctl status docker --no-pager
● docker.service - Docker Application Container Engine
     Loaded: loaded (/usr/lib/systemd/system/docker.service; enabled; preset: enabled)
     Active: active (running) since Thu 2026-07-02 19:39:24 UTC; 3min 55s ago
TriggeredBy: ● docker.socket
       Docs: https://docs.docker.com
   Main PID: 11168 (dockerd)
      Tasks: 39
     Memory: 43.0M (peak: 56.1M)
        CPU: 705ms
     CGroup: /system.slice/docker.service
             └─11168 /usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock

Jul 02 19:39:24 llmserver dockerd[11168]: time="2026-07-02T19:39:24.457906108Z" level=info msg="Loading containers: done."
Jul 02 19:39:24 llmserver dockerd[11168]: time="2026-07-02T19:39:24.461991828Z" level=info msg="Docker daemon" commit=8ec5ab3 containerd-snapshotter=true storage-driver=overlayfs version=29.6.1
Jul 02 19:39:24 llmserver dockerd[11168]: time="2026-07-02T19:39:24.462063589Z" level=info msg="Initializing buildkit"
Jul 02 19:39:24 llmserver dockerd[11168]: time="2026-07-02T19:39:24.603073093Z" level=info msg="Completed buildkit initialization"
Jul 02 19:39:24 llmserver dockerd[11168]: time="2026-07-02T19:39:24.606874032Z" level=info msg="Daemon has completed initialization"
Jul 02 19:39:24 llmserver dockerd[11168]: time="2026-07-02T19:39:24.606911250Z" level=info msg="API listen on /run/docker.sock"
Jul 02 19:39:24 llmserver systemd[1]: Started docker.service - Docker Application Container Engine.
Jul 02 19:39:50 llmserver dockerd[11168]: time="2026-07-02T19:39:50.351136850Z" level=info msg="image pulled" digest="sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d" remote="docker.io/library/hello-world:latest"
Jul 02 19:39:50 llmserver dockerd[11168]: time="2026-07-02T19:39:50.490116363Z" level=info msg="sbJoin: gwep4 ''->'759b501e6b19', gwep6 ''->''" eid=759b501e6b19 ep=dreamy_galileo net=bridge nid=ec90f26e2bd5
Jul 02 19:39:50 llmserver dockerd[11168]: time="2026-07-02T19:39:50.519680094Z" level=info msg="received task-delete event from containerd" container=1fdc753ddca33bf3a7bc5a6879e351e3787fa8716e4cf4ebf792f1ea71dd2bd2 module=libcontainerd namespace=moby topic=/tasks/delete type="*events.TaskDelete"

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

## M4B post-reboot verification

- Timestamp: 2026-07-02T19:45:14+00:00
- Hostname: llmserver
- User: user
- Uptime:  19:45:14 up 0 min,  3 users,  load average: 0.08, 0.03, 0.01
- Branch: milestone/m4b-docker-containerd-install
- Commit before verification: 5afa1afee852f8b9fb09661daf22c3a15493aa61
- Temporary service disabled at start: yes

### hostname

Command:
    $ hostname

Output:
    llmserver

Exit: 0

### uptime

Command:
    $ uptime

Output:
     19:45:14 up 0 min,  3 users,  load average: 0.08, 0.03, 0.01

Exit: 0

### findmnt /data

Command:
    $ findmnt /data

Output:
    TARGET SOURCE    FSTYPE OPTIONS
    /data  /dev/sdb1 ext4   rw,relatime

Exit: 0

### df -hT / /data

Command:
    $ df -hT / /data

Output:
    Filesystem                        Type  Size  Used Avail Use% Mounted on
    /dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.9G  6.6G  52% /
    /dev/sdb1                         ext4  2.0T  2.4M  1.9T   1% /data

Exit: 0

### containerd active

Command:
    $ sudo -n systemctl is-active containerd

Output:
    active

Exit: 0

### docker active

Command:
    $ sudo -n systemctl is-active docker

Output:
    active

Exit: 0

### sudo docker info

Command:
    $ sudo -n docker info

Output:
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


Exit: 0

### sudo docker version

Command:
    $ sudo -n docker version

Output:
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

Exit: 0

### sudo docker compose version

Command:
    $ sudo -n docker compose version

Output:
    Docker Compose version v5.3.0

Exit: 0

### sudo docker run --rm hello-world

Command:
    $ sudo -n docker run --rm hello-world

Output:

    Hello from Docker!
    This message shows that your installation appears to be working correctly.

    To generate this message, Docker took the following steps:
     1. The Docker client contacted the Docker daemon.
     2. The Docker daemon pulled the "hello-world" image from the Docker Hub.
        (amd64)
     3. The Docker daemon created a new container from that image which runs the
        executable that produces the output you are currently reading.
     4. The Docker daemon streamed that output to the Docker client, which sent it
        to your terminal.

    To try something more ambitious, you can run an Ubuntu container with:
     $ docker run -it ubuntu bash

    Share images, automate workflows, and more with a free Docker ID:
     https://hub.docker.com/

    For more examples and ideas, visit:
     https://docs.docker.com/get-started/


Exit: 0

### sudo docker system df

Command:
    $ sudo -n docker system df

Output:
    TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
    Images          1         0         38.09kB   25.87kB (67%)
    Containers      0         0         0B        0B
    Local Volumes   0         0         0B        0B
    Build Cache     0         0         0B        0B

Exit: 0

### Docker/containerd storage sizes

Command:
    $ sudo -n du -sh /var/lib/docker /var/lib/containerd /data/docker /data/containerd /data/containerd/root 2>/dev/null || true

Output:
    236K	/data/docker
    336K	/data/containerd

Exit: 0

### scripts/docker/verify-docker-storage.sh

Command:
    $ scripts/docker/verify-docker-storage.sh

Output:

## Docker/containerd Storage Verification

- Timestamp: 2026-07-02T19:45:15+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m4b-docker-containerd-install

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
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.9G  6.6G  52% /
/dev/sdb1                         ext4  2.0T  2.4M  1.9T   1% /data

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
     Active: active (running) since Thu 2026-07-02 19:44:34 UTC; 41s ago
       Docs: https://containerd.io
   Main PID: 2064 (containerd)
      Tasks: 27
     Memory: 84.2M (peak: 95.7M)
        CPU: 274ms
     CGroup: /system.slice/containerd.service
             └─2064 /usr/bin/containerd

Jul 02 19:44:34 llmserver containerd[2064]: time="2026-07-02T19:44:34.784902513Z" level=info msg="starting plugins..."
Jul 02 19:44:34 llmserver containerd[2064]: time="2026-07-02T19:44:34.784909083Z" level=info msg="Synchronizing NRI (plugin) with current runtime state"
Jul 02 19:44:34 llmserver containerd[2064]: time="2026-07-02T19:44:34.784992428Z" level=info msg=serving... address=/run/containerd/containerd.sock.ttrpc
Jul 02 19:44:34 llmserver containerd[2064]: time="2026-07-02T19:44:34.785034931Z" level=info msg=serving... address=/run/containerd/containerd.sock
Jul 02 19:44:34 llmserver containerd[2064]: time="2026-07-02T19:44:34.785309223Z" level=info msg="containerd successfully booted in 0.029927s"
Jul 02 19:44:34 llmserver systemd[1]: Started containerd.service - containerd container runtime.
Jul 02 19:45:15 llmserver containerd[2064]: time="2026-07-02T19:45:15.039415115Z" level=info msg="connecting to shim b752929c1cf45bc45cd52cdd64d4d094af15d7857b0c669c8815967c674e0874" address="unix:///run/containerd/s/bbc38b04043a4280d557f526a7092790d0b1da7e8982e5e4b552c8227733991f" namespace=moby protocol=ttrpc version=3
Jul 02 19:45:15 llmserver containerd[2064]: time="2026-07-02T19:45:15.141604034Z" level=info msg="shim disconnected" id=b752929c1cf45bc45cd52cdd64d4d094af15d7857b0c669c8815967c674e0874 namespace=moby
Jul 02 19:45:15 llmserver containerd[2064]: time="2026-07-02T19:45:15.141633177Z" level=info msg="cleaning up after shim disconnected" id=b752929c1cf45bc45cd52cdd64d4d094af15d7857b0c669c8815967c674e0874 namespace=moby
Jul 02 19:45:15 llmserver containerd[2064]: time="2026-07-02T19:45:15.141639577Z" level=info msg="cleaning up dead shim" id=b752929c1cf45bc45cd52cdd64d4d094af15d7857b0c669c8815967c674e0874 namespace=moby

[exit=0]
```

### systemctl status docker

```console
$ sudo -n systemctl status docker --no-pager
● docker.service - Docker Application Container Engine
     Loaded: loaded (/usr/lib/systemd/system/docker.service; enabled; preset: enabled)
     Active: active (running) since Thu 2026-07-02 19:44:36 UTC; 40s ago
TriggeredBy: ● docker.socket
       Docs: https://docs.docker.com
   Main PID: 2230 (dockerd)
      Tasks: 38
     Memory: 117.1M (peak: 120.7M)
        CPU: 380ms
     CGroup: /system.slice/docker.service
             └─2230 /usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock

Jul 02 19:44:36 llmserver dockerd[2230]: time="2026-07-02T19:44:36.035385389Z" level=info msg="Deleting nftables IPv6 rules" error="running nft: /dev/stdin:1:18-31: Error: Could not process rule: No such file or directory\ndelete table ip6 docker-bridges\n                 ^^^^^^^^^^^^^^\n exit status 1"
Jul 02 19:44:36 llmserver dockerd[2230]: time="2026-07-02T19:44:36.284385803Z" level=info msg="Loading containers: done."
Jul 02 19:44:36 llmserver dockerd[2230]: time="2026-07-02T19:44:36.289807260Z" level=info msg="Docker daemon" commit=8ec5ab3 containerd-snapshotter=true storage-driver=overlayfs version=29.6.1
Jul 02 19:44:36 llmserver dockerd[2230]: time="2026-07-02T19:44:36.290046018Z" level=info msg="Initializing buildkit"
Jul 02 19:44:36 llmserver dockerd[2230]: time="2026-07-02T19:44:36.372977544Z" level=info msg="Completed buildkit initialization"
Jul 02 19:44:36 llmserver dockerd[2230]: time="2026-07-02T19:44:36.375326079Z" level=info msg="Daemon has completed initialization"
Jul 02 19:44:36 llmserver dockerd[2230]: time="2026-07-02T19:44:36.375364837Z" level=info msg="API listen on /run/docker.sock"
Jul 02 19:44:36 llmserver systemd[1]: Started docker.service - Docker Application Container Engine.
Jul 02 19:45:15 llmserver dockerd[2230]: time="2026-07-02T19:45:15.113361203Z" level=info msg="sbJoin: gwep4 ''->'d00628f428c5', gwep6 ''->''" eid=d00628f428c5 ep=gracious_keldysh net=bridge nid=65b49f18accf
Jul 02 19:45:15 llmserver dockerd[2230]: time="2026-07-02T19:45:15.141551475Z" level=info msg="received task-delete event from containerd" container=b752929c1cf45bc45cd52cdd64d4d094af15d7857b0c669c8815967c674e0874 module=libcontainerd namespace=moby topic=/tasks/delete type="*events.TaskDelete"

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
    PASS: Docker/containerd storage verified

Exit: 0

### scripts/common/root-disk-guard.sh

Command:
    $ scripts/common/root-disk-guard.sh --report /data/services/mixed-memory-llm-api-server/reports/m3-root-disk-guard.md

Output:
    PASS: root disk guard passed

Exit: 0

## M4B post-reboot conclusion

PASS

- Docker survived reboot: yes
- containerd survived reboot: yes
- Docker Root Dir: /data/docker
- containerd root: root = "/data/containerd/root"
- containerd state: state = "/run/containerd"
- No NVIDIA/CUDA/model/API changes were made by the post-reboot verifier.

## M4B post-reboot verification

- Timestamp: 2026-07-02T19:45:18+00:00
- Hostname: llmserver
- Uptime:  19:45:18 up 0 min,  3 users,  load average: 0.15, 0.04, 0.01
- Conclusion: STOP
- Reason: git diff --check failed after reboot

## M4B post-reboot verification

- Timestamp: 2026-07-02T19:45:50+00:00
- Hostname: llmserver
- User: user
- Uptime:  19:45:50 up 1 min,  3 users,  load average: 0.08, 0.04, 0.01
- Branch: milestone/m4b-docker-containerd-install
- Commit before verification: 5afa1afee852f8b9fb09661daf22c3a15493aa61
- Temporary service disabled at start: yes

### hostname

Command:
    $ hostname

Output:
    llmserver

Exit: 0

### uptime

Command:
    $ uptime

Output:
     19:45:50 up 1 min,  3 users,  load average: 0.08, 0.04, 0.01

Exit: 0

### findmnt /data

Command:
    $ findmnt /data

Output:
    TARGET SOURCE    FSTYPE OPTIONS
    /data  /dev/sdb1 ext4   rw,relatime

Exit: 0

### df -hT / /data

Command:
    $ df -hT / /data

Output:
    Filesystem                        Type  Size  Used Avail Use% Mounted on
    /dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.9G  6.6G  52% /
    /dev/sdb1                         ext4  2.0T  2.4M  1.9T   1% /data

Exit: 0

### containerd active

Command:
    $ sudo -n systemctl is-active containerd

Output:
    active

Exit: 0

### docker active

Command:
    $ sudo -n systemctl is-active docker

Output:
    active

Exit: 0

### sudo docker info

Command:
    $ sudo -n docker info

Output:
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


Exit: 0

### sudo docker version

Command:
    $ sudo -n docker version

Output:
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

Exit: 0

### sudo docker compose version

Command:
    $ sudo -n docker compose version

Output:
    Docker Compose version v5.3.0

Exit: 0

### sudo docker run --rm hello-world

Command:
    $ sudo -n docker run --rm hello-world

Output:

    Hello from Docker!
    This message shows that your installation appears to be working correctly.

    To generate this message, Docker took the following steps:
     1. The Docker client contacted the Docker daemon.
     2. The Docker daemon pulled the "hello-world" image from the Docker Hub.
        (amd64)
     3. The Docker daemon created a new container from that image which runs the
        executable that produces the output you are currently reading.
     4. The Docker daemon streamed that output to the Docker client, which sent it
        to your terminal.

    To try something more ambitious, you can run an Ubuntu container with:
     $ docker run -it ubuntu bash

    Share images, automate workflows, and more with a free Docker ID:
     https://hub.docker.com/

    For more examples and ideas, visit:
     https://docs.docker.com/get-started/


Exit: 0

### sudo docker system df

Command:
    $ sudo -n docker system df

Output:
    TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
    Images          1         0         38.09kB   25.87kB (67%)
    Containers      0         0         0B        0B
    Local Volumes   0         0         0B        0B
    Build Cache     0         0         0B        0B

Exit: 0

### Docker/containerd storage sizes

Command:
    $ sudo -n du -sh /var/lib/docker /var/lib/containerd /data/docker /data/containerd /data/containerd/root 2>/dev/null || true

Output:
    236K	/data/docker
    336K	/data/containerd

Exit: 0

### scripts/docker/verify-docker-storage.sh

Command:
    $ scripts/docker/verify-docker-storage.sh

Output:

## Docker/containerd Storage Verification

- Timestamp: 2026-07-02T19:45:50+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m4b-docker-containerd-install

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
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.9G  6.6G  52% /
/dev/sdb1                         ext4  2.0T  2.4M  1.9T   1% /data

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
     Active: active (running) since Thu 2026-07-02 19:44:34 UTC; 1min 16s ago
       Docs: https://containerd.io
   Main PID: 2064 (containerd)
      Tasks: 29
     Memory: 91.1M (peak: 106.2M)
        CPU: 460ms
     CGroup: /system.slice/containerd.service
             └─2064 /usr/bin/containerd

Jul 02 19:44:34 llmserver containerd[2064]: time="2026-07-02T19:44:34.785309223Z" level=info msg="containerd successfully booted in 0.029927s"
Jul 02 19:44:34 llmserver systemd[1]: Started containerd.service - containerd container runtime.
Jul 02 19:45:15 llmserver containerd[2064]: time="2026-07-02T19:45:15.039415115Z" level=info msg="connecting to shim b752929c1cf45bc45cd52cdd64d4d094af15d7857b0c669c8815967c674e0874" address="unix:///run/containerd/s/bbc38b04043a4280d557f526a7092790d0b1da7e8982e5e4b552c8227733991f" namespace=moby protocol=ttrpc version=3
Jul 02 19:45:15 llmserver containerd[2064]: time="2026-07-02T19:45:15.141604034Z" level=info msg="shim disconnected" id=b752929c1cf45bc45cd52cdd64d4d094af15d7857b0c669c8815967c674e0874 namespace=moby
Jul 02 19:45:15 llmserver containerd[2064]: time="2026-07-02T19:45:15.141633177Z" level=info msg="cleaning up after shim disconnected" id=b752929c1cf45bc45cd52cdd64d4d094af15d7857b0c669c8815967c674e0874 namespace=moby
Jul 02 19:45:15 llmserver containerd[2064]: time="2026-07-02T19:45:15.141639577Z" level=info msg="cleaning up dead shim" id=b752929c1cf45bc45cd52cdd64d4d094af15d7857b0c669c8815967c674e0874 namespace=moby
Jul 02 19:45:50 llmserver containerd[2064]: time="2026-07-02T19:45:50.616812968Z" level=info msg="connecting to shim 5b75cc68df767d0e280e884b9e6f39521029ca10a60fb34b36e04d27d0b12581" address="unix:///run/containerd/s/2e5fc173f3a23a56d648288494401df5a972d408a5eb1d4a02b7fe6c3c2526e2" namespace=moby protocol=ttrpc version=3
Jul 02 19:45:50 llmserver containerd[2064]: time="2026-07-02T19:45:50.703182419Z" level=info msg="shim disconnected" id=5b75cc68df767d0e280e884b9e6f39521029ca10a60fb34b36e04d27d0b12581 namespace=moby
Jul 02 19:45:50 llmserver containerd[2064]: time="2026-07-02T19:45:50.703210954Z" level=info msg="cleaning up after shim disconnected" id=5b75cc68df767d0e280e884b9e6f39521029ca10a60fb34b36e04d27d0b12581 namespace=moby
Jul 02 19:45:50 llmserver containerd[2064]: time="2026-07-02T19:45:50.703215651Z" level=info msg="cleaning up dead shim" id=5b75cc68df767d0e280e884b9e6f39521029ca10a60fb34b36e04d27d0b12581 namespace=moby

[exit=0]
```

### systemctl status docker

```console
$ sudo -n systemctl status docker --no-pager
● docker.service - Docker Application Container Engine
     Loaded: loaded (/usr/lib/systemd/system/docker.service; enabled; preset: enabled)
     Active: active (running) since Thu 2026-07-02 19:44:36 UTC; 1min 15s ago
TriggeredBy: ● docker.socket
       Docs: https://docs.docker.com
   Main PID: 2230 (dockerd)
      Tasks: 41
     Memory: 121.5M (peak: 129.1M)
        CPU: 553ms
     CGroup: /system.slice/docker.service
             └─2230 /usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock

Jul 02 19:44:36 llmserver dockerd[2230]: time="2026-07-02T19:44:36.289807260Z" level=info msg="Docker daemon" commit=8ec5ab3 containerd-snapshotter=true storage-driver=overlayfs version=29.6.1
Jul 02 19:44:36 llmserver dockerd[2230]: time="2026-07-02T19:44:36.290046018Z" level=info msg="Initializing buildkit"
Jul 02 19:44:36 llmserver dockerd[2230]: time="2026-07-02T19:44:36.372977544Z" level=info msg="Completed buildkit initialization"
Jul 02 19:44:36 llmserver dockerd[2230]: time="2026-07-02T19:44:36.375326079Z" level=info msg="Daemon has completed initialization"
Jul 02 19:44:36 llmserver dockerd[2230]: time="2026-07-02T19:44:36.375364837Z" level=info msg="API listen on /run/docker.sock"
Jul 02 19:44:36 llmserver systemd[1]: Started docker.service - Docker Application Container Engine.
Jul 02 19:45:15 llmserver dockerd[2230]: time="2026-07-02T19:45:15.113361203Z" level=info msg="sbJoin: gwep4 ''->'d00628f428c5', gwep6 ''->''" eid=d00628f428c5 ep=gracious_keldysh net=bridge nid=65b49f18accf
Jul 02 19:45:15 llmserver dockerd[2230]: time="2026-07-02T19:45:15.141551475Z" level=info msg="received task-delete event from containerd" container=b752929c1cf45bc45cd52cdd64d4d094af15d7857b0c669c8815967c674e0874 module=libcontainerd namespace=moby topic=/tasks/delete type="*events.TaskDelete"
Jul 02 19:45:50 llmserver dockerd[2230]: time="2026-07-02T19:45:50.678594129Z" level=info msg="sbJoin: gwep4 ''->'e73b412bc7ef', gwep6 ''->''" eid=e73b412bc7ef ep=bold_cori net=bridge nid=65b49f18accf
Jul 02 19:45:50 llmserver dockerd[2230]: time="2026-07-02T19:45:50.703249804Z" level=info msg="received task-delete event from containerd" container=5b75cc68df767d0e280e884b9e6f39521029ca10a60fb34b36e04d27d0b12581 module=libcontainerd namespace=moby topic=/tasks/delete type="*events.TaskDelete"

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
    PASS: Docker/containerd storage verified

Exit: 0

### scripts/common/root-disk-guard.sh

Command:
    $ scripts/common/root-disk-guard.sh --report /data/services/mixed-memory-llm-api-server/reports/m3-root-disk-guard.md

Output:
    PASS: root disk guard passed

Exit: 0

## M4B post-reboot conclusion

PASS

- Docker survived reboot: yes
- containerd survived reboot: yes
- Docker Root Dir: /data/docker
- containerd root: root = "/data/containerd/root"
- containerd state: state = "/run/containerd"
- No NVIDIA/CUDA/model/API changes were made by the post-reboot verifier.
