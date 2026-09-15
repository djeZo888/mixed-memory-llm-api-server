# Q38DEV device observation

Status: OBSERVED; diagnostic only, no PASS_NATIVE or auth receipt.

Start UTC: `2026-09-15T04:25:06.838309+00:00`; end UTC: `2026-09-15T04:25:07.177105+00:00`. Inner inventory UTC: `2026-09-15T04:25:07.139106121Z` to `2026-09-15T04:25:07.139166211Z`. D3N32 overlap may be correlated against these times; its operations were not queried.

| Path | Type | Character major:minor |
|---|---|---|
| `/dev/nvidia-modeset` | char | 195:254 |
| `/dev/nvidia-uvm` | char | 511:0 |
| `/dev/nvidia-uvm-tools` | char | 511:1 |
| `/dev/nvidiactl` | char | 195:255 |

Missing fixed paths: `["/dev/dri", "/dev/dxg", "/dev/kfd", "/dev/nvidia-caps"]`. Truncated: `False`.

Names in this observation selected by the original immediate-child glob and rejected by unchanged check_device_names: `["/dev/nvidia-modeset"]`. The historical Q38VR3 triggering name remains unrecorded; this separate run does not retrospectively prove it.

One container; no device nodes opened/read/written, native imports, inference, model/API requests, downloads, real model/key/source mounts or source changes. Installer STOPPED.

Cleanup: QUIESCENT_REMOVAL_VERIFIED. Final guards: PASS. Independent absence: VERIFIED.
