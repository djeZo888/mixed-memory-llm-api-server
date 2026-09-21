#!/usr/bin/env python3
"""Explicit arm/run/restore/status entry point; --help and arm are offline."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmark.runner import main
if __name__ == "__main__":
    raise SystemExit(main())
