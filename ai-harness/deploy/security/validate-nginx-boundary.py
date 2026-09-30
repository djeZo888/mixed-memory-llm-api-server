#!/usr/bin/env python3
"""Check actual nginx configuration without exposing protected include contents."""
import argparse
import re
import subprocess
import sys


def validate(text):
    # Access rules must use the transport peer, not any request header. Reject
    # inherited realip rewriting as well as server-local rewrites.
    uncommented = '\n'.join(line.split('#', 1)[0] for line in text.splitlines())
    if re.search(r'\b(?:real_ip_header|set_real_ip_from|real_ip_recursive)\s', uncommented):
        raise ValueError('realip rewriting invalidates actual-peer boundary')
    for required in ('unix:/run/ai-harness-status/http.sock', 'location = /admin',
                     'location ^~ /api/admin/', 'deny 127.0.0.0/8;', 'deny ::1;',
                     'deny 10.156.100.61;', 'server_name status.ai-harness;'):
        if required not in uncommented:
            raise ValueError('required boundary configuration absent')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', required=True)
    parser.parse_args()
    result = subprocess.run(['/usr/sbin/nginx', '-T'], capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise ValueError('nginx configuration invalid')
    validate(result.stdout)
    print('nginx actual-peer/UDS configuration preflight PASS; live access acceptance still required')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        # nginx -T includes the separate image approval capability; never print it.
        print(f'nginx-boundary: refused ({type(error).__name__})', file=sys.stderr)
        sys.exit(1)
