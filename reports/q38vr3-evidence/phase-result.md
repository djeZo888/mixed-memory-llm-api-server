# Q38VR3 first actual fixture result

```json
{
  "argv": [
    "/usr/bin/python3",
    "-B",
    "/data/build/q38vr3-20260915/source/tests/lifecycle/sglang38_fixture/run_fixture.py",
    "--repo",
    "/data/build/q38vr3-20260915/source",
    "--output",
    "/data/logs/q38vr3-20260915/q38b-auth.json"
  ],
  "elapsed_seconds": 0.757678,
  "exit": 1,
  "finished_utc": "2026-09-15T04:18:22.787051+00:00",
  "model_execution": "NOT_TESTED",
  "receipt_exists": false,
  "result": {
    "code": "q38s_image_fixture_failed",
    "lifetime": {
      "attach_diagnostic": {
        "cli_returncode": 2,
        "cli_signal": null,
        "container_before_cleanup_stop": {
          "exit_code": 2,
          "signal": null,
          "status": "EXITED"
        },
        "failure_kind": "CLI_NONZERO_EXIT",
        "failure_metadata": {
          "cache_failure": {
            "code": "gpu_device_node_present",
            "failure_origin": {
              "exception_class": "ProbeError",
              "filename": "cache_probe.py",
              "line": 190
            },
            "status": "FAIL"
          },
          "code": "actual_image_fixture_failed",
          "origin": {
            "exception_class": "FixtureFailure",
            "filename": "run_pinned_image.py",
            "line": 599
          },
          "status": "SAFE_ORIGIN"
        },
        "operation": "START_ATTACH",
        "phase": "ATTACH",
        "schema_version": 1,
        "stderr": {
          "capture": "COMPLETE",
          "captured_bytes": 0,
          "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        },
        "stdout": {
          "capture": "COMPLETE",
          "captured_bytes": 331,
          "sha256": "0b02141789ead6a4bba31c5639136feca9a1c9f45c27d3b0d1c08f2148ac5379"
        }
      },
      "cleanup": "QUIESCENT_REMOVAL_VERIFIED",
      "container_id": "216f7d148354dd85bc5c1c2225c5b3021d10d9645eedb86d16a002b29e29e44d",
      "container_name": "q38b-fixture-2b459dcbf992ee743e37a5d1602b6ac5",
      "outcome": "ATTACH_FAILED",
      "runtime_inspect": {
        "context": 131072,
        "device_requests": [],
        "driver_capabilities": "compute,utility",
        "entrypoint": [
          "python3"
        ],
        "host_devices": [],
        "model_and_secret_mounts": "EMPTY_PRIVATE_TMPFS",
        "network": "none",
        "root_readonly": true,
        "runtime": "nvidia",
        "status": "PASS_HOST_INSPECT",
        "visible_devices": "none"
      }
    },
    "status": "FAIL"
  },
  "started_utc": "2026-09-15T04:18:22.027258+00:00",
  "streams": {
    "stderr": {
      "bytes": 0,
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    },
    "stdout": {
      "bytes": 1490,
      "sha256": "1d45c067c5cfd00870c91958c0cf651b42f8fc3786cdfb009b70136b3630c406"
    }
  }
}
```

Independent postchecks pending. First failure stops dependent context/model activation. No live receipt publication.
