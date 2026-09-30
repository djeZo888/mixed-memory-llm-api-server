#!/usr/bin/env python3
"""Standalone llm-node listener; fixed protected source, credentials and port."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import stat
import sys

ROOT = Path('/usr/local/lib/llm-server/node-api')


def bootstrap():
    if os.geteuid() != 0 or Path(__file__).resolve() != ROOT / 'scripts/control/node_serve.py':
        raise ValueError('unsafe_node_installation')
    for parent in (ROOT / 'scripts/control', *(ROOT / 'scripts/control').parents):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('unsafe_node_installation')
    for relative in ('scripts/control/__init__.py', 'scripts/control/installation.py',
                     'scripts/control/node_installation.py'):
        info = (ROOT / relative).lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or
                info.st_nlink != 1 or info.st_dev != Path('/').stat().st_dev):
            raise ValueError('unsafe_node_installation')
    sys.path.insert(0, str(ROOT / 'scripts'))


def main(argv=None):
    parser = argparse.ArgumentParser(description='Independent protected node API on127.0.0.1:30008')
    parser.add_argument('--check-binding', action='store_true', help='Validate fixed source and credentials only')
    args = parser.parse_args(argv)
    observers = server = owner = None
    try:
        bootstrap()
        from control.node_installation import validate_installation
        key = validate_installation()
        if args.check_binding:
            return 0
        from control.node_collectors import production_callbacks
        from control.passive import BoundedObservers
        from control.node import NodeStatus, NodeApplication
        from control.node_actions import NodeActions
        from control.http import make_server
        from control.node_observation import CanonicalIdentityReader
        from control.node_action_owner import production_owner
        reader = CanonicalIdentityReader()
        owner = production_owner(reader, control_key=key)
        observers = BoundedObservers(production_callbacks(reader, control_key=key))
        application = NodeApplication(NodeStatus(observers), NodeActions(owner))
        server = make_server(application, key, host='127.0.0.1', port=30008)
        owner.start()
        observers.start()
        def interrupted(_signum, _frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGINT, interrupted)
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        return 0
    except Exception:
        return 3
    finally:
        if owner is not None:
            owner.close()
        if observers is not None:
            observers.close()
        if server is not None:
            server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
