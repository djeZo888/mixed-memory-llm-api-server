#!/usr/bin/env python3
"""Run Q38 happy-path and drift checks from an immutable Git archive.

The exported tree contains committed bytes only. This verifier never regenerates
pins, installs packages, invokes Docker, or writes evidence into the source tree.
Run after the final commit, and repeat for the bundle-imported final head.
"""
import argparse
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--commit', default='HEAD')
    args = parser.parse_args()
    if not re.fullmatch(r'HEAD|[a-f0-9]{40}', args.commit):
        parser.error('commit must be HEAD or a full commit hash')
    def git(*command):
        return subprocess.check_output(['git', '-C', str(args.repo), *command])
    commit = git('rev-parse', args.commit + '^{commit}').decode().strip()
    tree = git('rev-parse', commit + '^{tree}').decode().strip()
    archive = git('archive', '--format=tar', commit)
    with tempfile.TemporaryDirectory(prefix='q38b-git-source-') as directory:
        with tarfile.open(fileobj=io.BytesIO(archive)) as package:
            package.extractall(directory, filter='data')
        result = subprocess.run([sys.executable, '-B', '-m', 'unittest',
            'tests.lifecycle.test_qwen38.AuthEvidence.test_receipt_schema_and_source_fixture_checks_agree',
            'tests.lifecycle.test_qwen38_final_source', 'tests.test_control_installation', '-v'], cwd=directory,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=60, check=False)
    print(json.dumps({'commit': commit, 'tree': tree,
        'status': 'PASS' if result.returncode == 0 else 'FAIL',
        'checks': 'committed-source receipt happy path, byte drift and exact control closure/protection',
        'actual_image': 'NOT_TESTED', 'live': 'NOT_TESTED'}, sort_keys=True))
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
