#!/usr/bin/env python3
"""Inference-free final-image checks. Run as the existing nonroot engine user."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import site
import subprocess
import sys
import tempfile


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    assert os.getuid() != 0
    assert sys.version_info[:2] == (3, 12)
    assert sys.prefix == '/opt/ai-harness-python' and sys.prefix != sys.base_prefix
    assert not site.ENABLE_USER_SITE
    assert 'include-system-site-packages = false' in Path(sys.prefix, 'pyvenv.cfg').read_text()
    import ssl, sqlite3, ctypes, lzma
    import numpy, scipy, sympy, matplotlib, pytest, pypdf, pdfplumber, markdown
    report = {'uid': os.getuid(), 'python': sys.version, 'venv': sys.prefix,
              'ssl': ssl.OPENSSL_VERSION, 'sqlite3': sqlite3.sqlite_version,
              'stdlib_imports': ['ssl', 'sqlite3', 'ctypes', 'lzma'],
              'packages': {}, 'checks': {}, 'licenses': []}
    for dist in importlib.metadata.distributions():
        report['packages'][dist.metadata['Name']] = dist.version
        for entry in dist.files or []:
            if any(term in str(entry).lower() for term in ('license', 'copying', 'notice')):
                p = Path(dist.locate_file(entry))
                if p.is_file():
                    report['licenses'].append({'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
    assert Path('/usr/local/share/licenses/python-3.12/LICENSE.txt').is_file()
    for root in ['/opt/ai-harness/tools', '/opt/ai-harness/skills', '/usr/local/share/licenses/python-3.12']:
        for p in Path(root).rglob('*'):
            if p.is_file() and any(term in p.name.lower() for term in ('license', 'copying', 'notice')):
                report['licenses'].append({'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
    assert report['licenses']
    shared = [Path('/usr/local/bin/python3.12'), Path('/usr/local/lib/libpython3.12.so.1.0')]
    shared += list(Path('/usr/local/lib/python3.12/lib-dynload').glob('*.so'))
    shared += list(Path(sys.prefix).rglob('*.so')) + list(Path(sys.prefix).rglob('*.so.*'))
    for p in sorted(set(shared)):
        result = subprocess.run(['ldd', str(p)], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0 and 'not found' not in result.stdout + result.stderr, str(p) + ': ' + result.stdout + result.stderr
    report['shared_library_closure'] = {'files_checked': len(set(shared)), 'missing': 0}
    env = dict(os.environ, MPLCONFIGDIR='/tmp/h001-matplotlib', PYTHONDONTWRITEBYTECODE='1')
    def run(name, args, cwd=None, timeout=120):
        p = subprocess.run(args, capture_output=True, text=True, cwd=cwd, env=env, timeout=timeout)
        report['checks'][name] = {'exit': p.returncode, 'stdout': p.stdout[-10000:], 'stderr': p.stderr[-6000:]}
        return p.returncode == 0
    run('pip_check', [sys.executable, '-m', 'pip', 'check'])
    run('python_numerical', [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '/opt/ai-harness/tools/runtime/test/test_calculations.py'])
    run('pdf_extract_render_ocr_create', [sys.executable, '-m', 'unittest', 'discover', '-v', '-s', '/opt/ai-harness/tools/pdf/tests'], timeout=240)
    run('node_typescript', ['node', '--test', '/opt/ai-harness/tools/runtime/test/calculation.test.mjs'])
    run('typescript_version', ['/opt/ai-harness/tools/runtime/node_modules/.bin/tsc', '--version'])
    run('playwright_version', ['/opt/ai-harness/tools/runtime/node_modules/.bin/playwright', '--version'])
    with tempfile.TemporaryDirectory(prefix='h001-compiler-') as tmp:
        if run('cmake_configure', ['cmake', '-S', '/opt/ai-harness/tools/runtime/test', '-B', tmp, '-G', 'Ninja']):
            if run('cpp_build', ['cmake', '--build', tmp]):
                run('c_cpp_fixtures', ['ctest', '--test-dir', tmp, '--output-on-failure'])
    report['ok'] = all(check['exit'] == 0 for check in report['checks'].values())
    print(json.dumps(report, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
