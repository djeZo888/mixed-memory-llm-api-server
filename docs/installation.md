# Installation

Installation is milestone-driven. Do not skip storage safety milestones.

## Order

1. M0 repository bootstrap.
2. M1 VM preflight.
3. M2 data disk dry-run and `/data` preparation.
4. M3 root-disk guard.
5. M4 Docker/containerd storage.
6. M5 NVIDIA host driver.
7. M6 NVIDIA Container Toolkit.
8. M7 backend runtime abstraction.
9. M8 small model API smoke service.
10. M9 and later model deployments.

## M0 Warning

M0 creates repository files only. It does not configure the server, initialize disks, install packages, download models, or expose an API.
