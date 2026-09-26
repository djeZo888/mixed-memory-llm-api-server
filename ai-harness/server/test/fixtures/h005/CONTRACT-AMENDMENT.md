# Additive frozen fixture amendment for liaison / Worker2

Source/offline synthetic fixture only, no live capacity claim.
Exact fixture: repo/tests/fixtures/service_resilience/disk-volumes-v1.json
SHA256: 723de2ecfde1d62d1c2a7b95277302ba2b9c81a0736caa19b0c76d9a222c1e4a

`resources.disk.volumes` is an array with three stable IDs `root`, `data`, `models`.
Each entry has `volume_id`, `mount_point`, `filesystem_uuid`, `filesystem_type`,
`state`, `reason`, `observed_at`, `age_ms`, `freshness`, `total_bytes`,
`available_bytes`, `read_bytes_per_second`, `write_bytes_per_second`.
Identity/capacity/rates and observation fields may be null. State is
ok|unknown|unavailable. Reasons: registration_unknown|mount_identity_unavailable|
capacity_unavailable or null. Parent disk numeric fields retain root-only semantics.
Display separately; do not sum volumes (registered roles can share a filesystem).
Missing/misbound model mount is unavailable with null capacity, never root capacity.
Each entry retains its own observation age; fresh parent must not refresh stale child.

STEERING amendment: each service adds `hardware_latched_boot_id:string|null`.
It preserves authoritative originating latched boot, including inherited boot A
while current boot is B. Never stamp B on inherited A. Unknown startup uses null.
Inventory preserves validated allowlisted UUID→typed hardware_faults; malformed
fault metadata makes complete false/state unknown, never a clean successful map.

```json
{
  "state": "ok",
  "reason": null,
  "observed_at": "2026-09-25T00:00:00+00:00",
  "age_ms": 0,
  "freshness": "fresh",
  "total_bytes": 34359738368,
  "available_bytes": 17179869184,
  "read_bytes_per_second": 1024.0,
  "write_bytes_per_second": 2048.0,
  "volumes": [
    {
      "volume_id": "root",
      "mount_point": "/",
      "filesystem_uuid": "fixture-root-uuid",
      "filesystem_type": "ext4",
      "state": "ok",
      "reason": null,
      "observed_at": "2026-09-25T00:00:00+00:00",
      "age_ms": 0,
      "freshness": "fresh",
      "total_bytes": 34359738368,
      "available_bytes": 17179869184,
      "read_bytes_per_second": 1024.0,
      "write_bytes_per_second": 2048.0
    },
    {
      "volume_id": "data",
      "mount_point": "/data",
      "filesystem_uuid": "fixture-data-uuid",
      "filesystem_type": "ext4",
      "state": "ok",
      "reason": null,
      "observed_at": "2026-09-25T00:00:00+00:00",
      "age_ms": 0,
      "freshness": "fresh",
      "total_bytes": 1099511627776,
      "available_bytes": 549755813888,
      "read_bytes_per_second": 1024.0,
      "write_bytes_per_second": 2048.0
    },
    {
      "volume_id": "models",
      "mount_point": "/data/models",
      "filesystem_uuid": "fixture-models-uuid",
      "filesystem_type": "ext4",
      "state": "ok",
      "reason": null,
      "observed_at": "2026-09-25T00:00:00+00:00",
      "age_ms": 0,
      "freshness": "fresh",
      "total_bytes": 2199023255552,
      "available_bytes": 1099511627776,
      "read_bytes_per_second": 1024.0,
      "write_bytes_per_second": 2048.0
    }
  ]
}
```
