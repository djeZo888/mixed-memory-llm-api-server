#!/usr/bin/env python3
"""Fixed production entrypoint. No configurable URL, worker count or admin command."""
import os
from pathlib import Path
import sys


def main():
    if sys.argv[1:] == ['--help']:
        print('Run the reviewed llm-image-api.service; no configuration arguments. Offline checks: docs/image-api.md')
        return 0
    if sys.argv[1:]:
        return 2
    # -I excludes caller search paths; all added source is protected installation.
    sys.path.insert(0, str(Path(__file__).absolute().parents[1]))
    lock = None
    try:
        from image_api.protection import installation, singleton
        raw, key = installation()
        lock = singleton()
        from image_api.protocol import qualification, strict_json
        from image_api.app import create_app
        import uvicorn
        config = qualification(strict_json(raw))
        uvicorn.run(create_app(config, key), host='127.0.0.1', port=30006, workers=1,
                    proxy_headers=False, forwarded_allow_ips='', access_log=False,
                    log_config=None, log_level='critical', server_header=False,
                    timeout_keep_alive=5, timeout_graceful_shutdown=1810,
                    h11_max_incomplete_event_size=16384)
        return 0
    except Exception:
        # No raw protected paths, payloads, credentials or native exception text.
        print('image adapter startup refused', file=sys.stderr)
        return 1
    finally:
        if lock is not None:
            os.close(lock)


if __name__ == '__main__':
    raise SystemExit(main())
