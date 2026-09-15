#!/usr/bin/env python3
"""Read-only installed-storage guard. UUID/path environment overrides are ignored."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


class Runner:
    def run(self, argv, *, timeout=30, env=None):
        # Do not inherit LIBMOUNT_FSTAB, PATH, LD_PRELOAD, or other overrides in
        # privileged service guards. No raw command errors or environment logged.
        result = subprocess.run(argv, timeout=timeout, check=True, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                stdin=subprocess.DEVNULL,
                                env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
        return result.stdout


def write_report(instance, result, report_path):
    """Write only to a verified registered logs subtree after repeating guards."""
    report = Path(instance._path(report_path))
    logs = Path(result["roots"]["logs"])
    if report == logs or logs not in report.parents:
        raise ValueError("guard report must be below registered logs")
    local = instance._no_symlink(str(report), protected=True)
    if not local.parent.is_dir():
        raise ValueError("report parent directory is unavailable")
    instance.verify()
    instance._atomic_write(str(report), json.dumps(result, sort_keys=True, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print verified storage metadata")
    parser.add_argument("--root-guard", action="store_true", help="scan root for container and large AI payload leakage")
    parser.add_argument("--report", help="write JSON report beneath the registered logs directory after guards pass")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("installer_storage", Path(__file__).resolve().parents[1] / "install" / "storage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        # Bootstrap read uses fixed root-owned path; no argv or environment can
        # redirect the trust anchor. A registered file is mandatory here.
        reader = module.Storage({}, Runner())
        registered = reader.read_registration()
        if registered is None:
            raise module.StorageError("no root-owned installer storage registration")
        config = {"data_dir": registered["data"]["path"], "data_uuid": registered["data"]["uuid"],
                  "model_dir": registered["models"]["path"], "model_uuid": registered["models"]["uuid"],
                  "storage_mode": registered.get("storage_mode", "existing")}
        instance = module.Storage(config, Runner())
        result = instance.root_payload_guard() if args.root_guard else instance.verify()
        if args.report:
            write_report(instance, result, args.report)
    except (module.StorageError, OSError, ValueError, KeyError):
        print("STOP: registered storage identity, ownership, layout or capacity guard failed", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print("PASS: registered dedicated data/model storage and root capacity verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
