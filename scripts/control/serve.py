#!/usr/bin/env python3
"""Installed root control listener. No fixture/host/path/environment overrides."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import stat
import sys


_ROOT = Path('/usr/local/lib/llm-server/control-api')


def _trusted_bootstrap():
    # Check fixed root and import parent before executing any adjacent module.
    if os.geteuid() != 0 or Path(__file__).resolve() != _ROOT / 'scripts/control/serve.py':
        raise ValueError
    for path in (_ROOT / 'scripts/control', *(_ROOT / 'scripts/control').parents):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError
    for name in ('__init__.py', 'installation.py'):
        info = (_ROOT / 'scripts/control' / name).lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022
                or info.st_nlink != 1 or info.st_dev != Path('/').stat().st_dev):
            raise ValueError
    sys.path.insert(0, str(_ROOT / 'scripts'))


def main(argv=None):
    parser = argparse.ArgumentParser(description='Protected authenticated control API on 127.0.0.1:30000')
    parser.add_argument('--check-binding', action='store_true',
                        help='Validate fixed source/config/credential closure; no listener or mutation')
    args = parser.parse_args(argv)
    application = server = None
    try:
        _trusted_bootstrap()
        from control.installation import validate_installation, read_advertised_policy
        key = validate_installation()
        advertised_policy = read_advertised_policy()
        from control.adapter import production_application
        from control.http import make_server
        if args.check_binding:
            print(json.dumps({'status': 'binding_validated', 'listener_started': False,
                              'normal_lifecycle_acceptance': 'not_performed'}))
            return 0
        application = production_application(_ROOT / 'configs', key, advertised_policy=advertised_policy)
        server = make_server(application, key, host='127.0.0.1', port=30000)
        def interrupted(_signum, _frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGINT, interrupted)
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        return 0
    except Exception:
        print(json.dumps({'status': 'unavailable', 'code': 'unsafe_or_missing_control_installation',
                          'listener_started': False}))
        return 3
    finally:
        if server is not None:
            server.server_close()
        if application is not None:
            application.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
