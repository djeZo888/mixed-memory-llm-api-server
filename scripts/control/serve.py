#!/usr/bin/env python3
"""Production entry point. No fixture/host/config/command/environment overrides."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Exactly one canonical scripts import root. -I ignores PYTHONPATH/user packages.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from control.adapter import production_application  # noqa: E402
from control.protocol import ControlError  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description="Protected loopback control API; production binding currently incomplete")
    parser.add_argument("--check-binding", action="store_true", help="Check reviewed production integration; never start a listener")
    args = parser.parse_args(argv)
    try:
        production_application()
    except ControlError:
        print(json.dumps({"status": "incomplete", "code": "production_adapter_unavailable", "listener_started": False}))
        return 3
    # An adapter implementation must add its reviewed key and listener binding
    # in the same review. A returned object alone never enables this entry point.
    print(json.dumps({"status": "incomplete", "code": "production_adapter_unavailable", "listener_started": False}))
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
