# Local PDF tools

Entrypoint: `/opt/ai-harness-python/bin/python /opt/ai-harness/tools/pdf/pdf_tools.py`.
First-party MIT. Python >=3.11; PREP's Python >=3.12 technical runtime is compatible.
Run `--help` or `<command> --help` for the actual interface. Every command requires
an explicit existing absolute workspace; resolve macOS `/var` or `/tmp` aliases
before passing them because all symlink ancestry is rejected.

```sh
PDF=/opt/ai-harness/tools/pdf/pdf_tools.py
PYTHON=/opt/ai-harness-python/bin/python
"$PYTHON" "$PDF" --workspace "$PWD" extract datasheet.pdf --pages 1,3-5 --output artifacts/text.txt
"$PYTHON" "$PDF" --workspace "$PWD" extract datasheet.pdf --pages 1 --engine pdfplumber --output artifacts/layout.txt
"$PYTHON" "$PDF" --workspace "$PWD" extract datasheet.pdf --pages 1 --engine poppler --output artifacts/poppler.txt
"$PYTHON" "$PDF" --workspace "$PWD" render datasheet.pdf --pages 1 --dpi 150 --output-dir artifacts/pages
"$PYTHON" "$PDF" --workspace "$PWD" --timeout 120 ocr scanned.pdf --pages 1-3 --output artifacts/ocr.txt
"$PYTHON" "$PDF" --workspace "$PWD" create report.md --output artifacts/report.pdf
```

Success prints one bounded JSON object with `ok`, workspace-relative `artifacts`
(paths and byte sizes), operation and selected pages. Errors print bounded JSON
with `ok:false` and a message; exit status 1. Argument syntax errors use argparse
stderr and exit 2; cancellation exits 130. Paths and error text are JSON escaped.
The helper returns artifact paths, not an unbounded transcript of extracted text.
Consumers must keep any file content escaped and treat PDF/HTML text as data.
Existing output files are never overwritten. A later output collision can leave
previously published pages if another writer races publication; workspace writers
must be serialized by the owning runtime.

## Container integration proposal (PREP-owned)

Copy this directory to `/opt/ai-harness/tools/pdf`, alongside the other tools.
Install into the existing `/opt/ai-harness-python` venv. No extra host mounts.

```dockerfile
# Incorporate into PREP's reviewed image package step; do not run on the host.
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils tesseract-ocr tesseract-ocr-eng chromium \
 && rm -rf /var/lib/apt/lists/*
COPY ai-harness/tools /opt/ai-harness/tools
COPY ai-harness/skills /opt/ai-harness/skills
RUN /opt/ai-harness-python/bin/python -m pip install --no-cache-dir \
    --require-hashes -r /opt/ai-harness/tools/pdf/requirements.lock
ENV MCODE_CHROME_PATH=/usr/bin/chromium
```

PREP owns exact OS package versions/base-image pin and image rebuild; record
resolved `dpkg-query` versions in build evidence. This proposal does not start a
service or authorize a host package install. Poppler supplies `pdftotext` and
`pdftoppm`; Tesseract's contracted language is English (`eng`) only. Chromium must
run with its native sandbox under the ordinary non-root container user. Missing
Python/native tools fail with an explicit dependency message. Never disable
Chromium's sandbox to work around a failed container integration.

Python direct pins are `pypdf==6.19.0`, `pdfplumber==0.11.10`,
`Markdown==3.10.3`. `requirements.lock` includes every runtime transitive version
and SHA-256 hashes from official PyPI release metadata for allowed artifacts.
`dependency-notices.json` records sources/licenses; keep installed distribution
license files in the final image. No package is installed automatically at runtime.

## Limits and safety boundaries

- Local regular files only: absolute input/output paths must be inside workspace;
  relative paths cannot contain `..`. Symlink components and hardlinked inputs
  are rejected. Input reads/output writes use anchored directory descriptors,
  `O_NOFOLLOW`, regular-file checks and exclusive output creation.
- PDF input <=25 MiB; HTML/Markdown <=1 MiB of UTF-8. PDF must have 1..200 pages;
  at most 30 selected pages per command. Documents over 30 pages require an
  explicit selection. Encrypted PDFs are refused.
- Every output <=16 MiB; temporary working set on disk <=80 MiB (polled at 50ms).
  Native per-file resource limit is 16 MiB. Deadline defaults 60 seconds, supports
  1..120; supervisor kills the process group on timeout/cancellation/error.
  All native invocations use argument arrays and no shell.
- Rasterization: 72..200 requested DPI, <=2400 pixels on either edge. Very large
  or invalid page dimensions are rejected. OCR emits page boundaries and a
  verification reminder; verify units, tables, minus signs and component values
  against page images.
- Parser/native worker CPU time is limited. Linux parsing/render/OCR additionally
  has a 768 MiB address-space limit. Chromium needs a large virtual address space,
  so creation does not receive that limit; PREP must provide its normal container
  memory/process limits. macOS address-space enforcement is not claimed.
- Creation supports a deliberately small static text/table HTML subset. User CSS,
  scripts, images, iframes, URL attributes and active content are removed. A fixed
  CSP forbids resource fetches; JavaScript is disabled, name resolution is blocked,
  and a dead loopback proxy is set. Browser background networking is disabled.
  This is basic document creation, not arbitrary webpage printing; use the native
  browser for public-page research separately. It never calls models or cloud OCR.
- Private staging is created inside workspace and removed afterwards. The runtime
  must serialize workspace writers and protect the workspace ancestry from rename
  races by other same-user processes; this helper is not a hostile same-UID
  filesystem isolation boundary. Its checks complement the native container
  sandbox and do not replace it.

## Worker-local verification

```sh
python3 -m venv /task/evidence/pdf/venv
/task/evidence/pdf/venv/bin/python -m pip install --require-hashes -r ai-harness/tools/pdf/requirements.lock
/task/evidence/pdf/venv/bin/python -m unittest discover -s ai-harness/tools/pdf/tests -v
```

The suite distinguishes real parser/native operations from fake-executable timeout
and argument-boundary fixtures. Native tests skip with explicit `NOT_TESTED` when
a tool is absent. For real creation, set `MCODE_CHROME_PATH` to the installed
sandboxed browser executable. A configured browser that fails is a test failure,
not a skip; report it as blocked/failed. Test evidence belongs outside Git.
Linux-container behavior, native-agent integration and actual container sandbox
acceptance require the separate integration run; macOS tests cannot establish them.
