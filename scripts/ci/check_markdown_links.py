#!/usr/bin/env python3
"""Check local Markdown links, preserving exact archived source provenance."""
import hashlib
from pathlib import Path
import re
import sys

# Hash-bound original contexts: never edit retained evidence to repair its links.
ARCHIVE_CONTEXTS = {
    'docs/orchestration/AGENTS-H016-archive.md': ('226cdcb58289a60bcaf26b5f78ef6911a45c55d65d451d3b5a97b1987d3f76c6', '.'),
    'ai-harness/deploy/engine/fixtures/pdf-skill-h034-31088c03.md':
        ('31088c03ce196bfc575d48c3f9214c5a5c2ac94f3fb6f9fd00f71fbe31472918', 'ai-harness/skills/pdf'),
}
# These two README captures retain external repository image references only.
# Their exact original bytes and upstream URLs are in H014 SOURCE-MANIFEST.json.
EXTERNAL_ARCHIVES = {
    'reports/h014-mimo-selection-20260927/sources/aes-pro-README.md':
        ('04b74e5dd77713f57131f089ef6eaa463e2a26ec2d73201506a105c84827f931',
         {'kld_data/01_kld_vs_filesize.png', 'kld_data/02_ppl_vs_filesize.png'}),
    'reports/h014-mimo-selection-20260927/sources/aes-flash-README.md':
        ('0ebac3aa51c97b14a04b906544f31a34ad12edad9da58145ce5ff0ce7efd66d2',
         {'kld_data/01_kld_vs_filesize.png', 'kld_data/02_ppl_vs_filesize.png'}),
    **{f'reports/{revision}-evidence/q38vc-source-handoff.md':
       ('222f362d2bba98bedd2c8203584a8322acbba2ae98fd22c76391957386faf787',
        {'/Users/agent/LLMServer-orchestration/20260915/Q38VC/' + name
         for name in ('Q38VC.bundle', 'final.md', 'verification.json')})
       for revision in ('q38vr2', 'q38vr3')},
}
LINK = re.compile(r'\[[^\]]+\]\(([^)]+)\)')


def prose(text):
    """Literal inline and fenced examples are not navigable Markdown links."""
    lines = []
    fence = None
    for line in text.splitlines(keepends=True):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            lines.append('\n')
        elif marker:
            fence = marker[1]
            lines.append('\n')
        else:
            lines.append(line)
    return re.sub(r'(`+)([^`]|(?!\1)`)*?\1(?!`)', '', ''.join(lines))


def check(root):
    root = root.resolve()
    failures = []
    for md in sorted(root.rglob('*.md')):
        if '.git' in md.relative_to(root).parts:
            continue
        relative = md.relative_to(root).as_posix()
        data = md.read_bytes()
        expected = ARCHIVE_CONTEXTS.get(relative) or EXTERNAL_ARCHIVES.get(relative)
        verified = expected is not None and hashlib.sha256(data).hexdigest() == expected[0]
        if expected and not verified:
            failures.append(f'{relative}: archived evidence hash mismatch')
        base = root / ARCHIVE_CONTEXTS[relative][1] if verified and relative in ARCHIVE_CONTEXTS else md.parent
        for match in LINK.finditer(prose(data.decode('utf-8'))):
            target = match[1].strip()
            # A quoted optional title is not part of a path. Angle destinations
            # can contain spaces; keep ordinary unquoted paths compatible.
            titled = re.fullmatch(r'(.*?)\s+[\"\'].*[\"\']', target)
            if titled:
                target = titled[1]
            if target.startswith('<') and target.endswith('>'):
                target = target[1:-1]
            if verified and relative in EXTERNAL_ARCHIVES and target in EXTERNAL_ARCHIVES[relative][1]:
                continue
            if not target or '://' in target or target.startswith(('#', 'mailto:')):
                continue
            path_part = target.split('#', 1)[0]
            if not path_part:
                continue
            resolved = (base / path_part).resolve()
            if not resolved.is_relative_to(root):
                failures.append(f'{relative}: link escapes repository: {target}')
            elif not resolved.exists():
                failures.append(f'{relative}: missing local link target: {target}')
    return failures


if __name__ == '__main__':
    failures = check(Path('.'))
    print('\n'.join(failures) if failures else 'markdown-local-links-ok')
    sys.exit(bool(failures))
