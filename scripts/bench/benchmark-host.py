#!/usr/bin/env python3
"""Explicit BENCHRUN host JSON-line endpoint. Never invoked during BENCHPREP."""
import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--campaign', required=True)
    parser.add_argument('--manifests', required=True, type=Path)
    parser.add_argument('--serve', action='store_true', required=True)
    args = parser.parse_args()
    # Installed Manager and canonical lease win. Only benchmark modules come
    # from the separately staged/root-reviewed source; no production replacement.
    source = Path(__file__).resolve().parents[2]
    installed = Path('/usr/local/lib/llm-server/control-api/scripts')
    # Verify the current installed entry modules before importing their code.
    if os.geteuid() != 0:
        parser.error('explicit root BENCHRUN host session required')
    config = json.loads((source / 'configs/benchmarks/gpu-split-20260919.json').read_bytes())
    for entry in config['installed_source_identities'].values():
        path = Path(entry['path'])
        if not path.is_relative_to(installed):
            parser.error('installed source path mismatch')
        for component in (path, *path.parents):
            info = component.lstat()
            if component.is_symlink() or info.st_uid != 0 or info.st_mode & 0o022:
                parser.error('unprotected installed source')
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            parser.error('installed source pin mismatch')
    sys.path[:0] = [str(installed), str(source / 'scripts')]
    from benchmark.host import LinuxHost, serve
    try:
        host = LinuxHost(args.campaign, args.manifests)
        serve(host, sys.stdin, sys.stdout)
    except Exception:
        print('{"ok":false,"error":"host_initialization_failed"}', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
