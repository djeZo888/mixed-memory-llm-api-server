#!/usr/bin/env python3
"""Bounded local PDF operations. MIT; see NOTICE.md for reviewed upstream context."""
from __future__ import annotations

import argparse
import contextlib
import html
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import stat
import subprocess
import sys
import time
import uuid

MIB = 1024 * 1024
MAX_INPUT = 25 * MIB
MAX_FILE = 16 * MIB
MAX_TOTAL = 80 * MIB
MAX_PAGES = 30
MAX_EDGE = 2400
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


class ToolError(Exception):
    pass


def fail(message: str, code: str = "invalid_request") -> dict:
    # JSON encoding prevents terminal controls/newlines from becoming tool markup.
    return {"ok": False, "error": {"code": code, "message": message[:1000]}}


class Workspace:
    """All input and artifact access is rooted at an opened, no-follow directory.

    Reject every symlink component, traversal, special files and hardlinked inputs.
    Output publication uses directory FDs and O_EXCL; never overwrite user files.
    """
    def __init__(self, root: str):
        if not os.path.isabs(root) or ".." in Path(root).parts:
            raise ToolError("--workspace must be an existing absolute directory without traversal")
        self.root = os.path.normpath(root)
        if self.root == "/":
            raise ToolError("The filesystem root cannot be a workspace")
        fd = os.open("/", DIR_FLAGS)
        try:
            for part in Path(self.root).parts[1:]:
                child = os.open(part, DIR_FLAGS, dir_fd=fd)
                os.close(fd)
                fd = child
            self.fd = fd
        except BaseException:
            os.close(fd)
            raise

    def close(self):
        os.close(self.fd)

    def parts(self, value: str) -> list[str]:
        if not value or len(value) > 1000 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ToolError("Paths must be nonempty, at most 1000 characters, without control characters")
        p = Path(value)
        if ".." in p.parts:
            raise ToolError("Parent traversal is forbidden")
        if p.is_absolute():
            try:
                p = p.relative_to(self.root)
            except ValueError as exc:
                raise ToolError("Path must be inside --workspace") from exc
        parts = list(p.parts)
        if not parts or len(parts) > 32 or any(x in ("", ".", "..") or len(x) > 240 for x in parts):
            raise ToolError("Invalid workspace path")
        return parts

    @contextlib.contextmanager
    def parent(self, parts: list[str], create=False):
        fd = os.dup(self.fd)
        try:
            for part in parts[:-1]:
                if create:
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                child = os.open(part, DIR_FLAGS, dir_fd=fd)
                os.close(fd)
                fd = child
            yield fd, parts[-1]
        finally:
            os.close(fd)

    def read(self, value: str, limit=MAX_INPUT) -> bytes:
        with self.parent(self.parts(value)) as (fd, name):
            handle = os.open(name, FILE_FLAGS, dir_fd=fd)
            try:
                st = os.fstat(handle)
                if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
                    raise ToolError("Input must be a regular, non-hardlinked file")
                if st.st_size > limit:
                    raise ToolError(f"Input exceeds {limit} bytes")
                with os.fdopen(handle, "rb", closefd=False) as stream:
                    data = stream.read(limit + 1)
                if len(data) > limit:
                    raise ToolError("Input grew beyond its size limit")
                return data
            finally:
                os.close(handle)

    def check_output(self, value: str):
        with self.parent(self.parts(value), create=True) as (fd, name):
            try:
                os.stat(name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                return
            raise ToolError("Output already exists; choose a new artifact path")

    def publish(self, value: str, data: bytes):
        if not data or len(data) > MAX_FILE:
            raise ToolError("Output is empty or exceeds 16 MiB")
        with self.parent(self.parts(value), create=True) as (fd, name):
            handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            try:
                with os.fdopen(handle, "wb", closefd=False) as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(handle)
            except BaseException:
                os.unlink(name, dir_fd=fd)
                raise
            finally:
                os.close(handle)


def pages(spec: str | None, count: int) -> list[int]:
    if count < 1:
        raise ToolError("PDF must have at least one page")
    if spec is None:
        if not 1 <= count <= MAX_PAGES:
            raise ToolError("Select --pages explicitly for documents over 30 pages")
        return list(range(1, count + 1))
    if len(spec) > 150:
        raise ToolError("Page selection is too long")
    chosen = set()
    for part in spec.split(","):
        if not re.fullmatch(r"[1-9][0-9]*(?:-[1-9][0-9]*)?", part):
            raise ToolError("Use --pages 1,3-5 with positive one-based page numbers")
        lo, _, hi = part.partition("-")
        first, last = int(lo), int(hi or lo)
        if first > last or last > count:
            raise ToolError("Page selection is reversed or outside the document")
        # Check range width before constructing it, even for a huge valid page
        # count. Request digit length is independently bounded above.
        if last - first + 1 > MAX_PAGES:
            raise ToolError("At most 30 pages per request")
        chosen.update(range(first, last + 1))
        if len(chosen) > MAX_PAGES:
            raise ToolError("At most 30 pages per request")
    return sorted(chosen)


def require(name: str) -> str:
    result = shutil.which(name)
    if not result:
        raise ToolError(f"Dependency unavailable: {name}; PREP must install the documented container package")
    return result


def run_native(args: list[str]):
    # Inherit supervisor's process group, deadline, file and CPU limits.
    with open("native.stdout", "wb") as out, open("native.stderr", "wb") as err:
        result = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=out, stderr=err, check=False)
    if result.returncode:
        # Do not echo untrusted PDF content, environment or native stderr.
        raise ToolError(f"{Path(args[0]).name} failed (exit {result.returncode}); check dependency/language availability or input validity")


def load_pdf():
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ToolError("Dependency unavailable: pypdf; install requirements.lock into the task Python venv") from exc
    reader = PdfReader("input.pdf", strict=True)
    if reader.is_encrypted:
        raise ToolError("Encrypted PDFs are unsupported; provide an explicitly decrypted local copy")
    return reader


class StaticHTML(HTMLParser):
    """Text-only HTML subset; no user styles, URL attributes, scripts or resources."""
    allowed = {"p", "div", "span", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "pre", "code", "blockquote", "strong", "em", "b", "i", "u", "s", "sub", "sup", "table", "thead", "tbody", "tr", "th", "td", "br", "hr", "a"}
    skip = {"script", "style", "iframe", "object", "embed", "svg", "math", "template", "head"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag in self.skip:
            self.hidden.append(tag)
        elif not self.hidden and tag in self.allowed:
            self.output.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
        elif tag in self.allowed and tag not in {"br", "hr"}:
            self.output.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.hidden:
            self.output.append(html.escape(data))


def static_html(text: str, markdown=False) -> str:
    if markdown:
        try:
            import markdown as md
        except ImportError as exc:
            raise ToolError("Dependency unavailable: Markdown; install requirements.lock") from exc
        text = md.markdown(text, extensions=["tables", "fenced_code"])
    parser = StaticHTML()
    parser.feed(text)
    parser.close()
    return ('<!doctype html><html><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; script-src \'none\'; img-src \'none\'; font-src \'none\'; connect-src \'none\'; frame-src \'none\'; base-uri \'none\'; form-action \'none\'">'
            '<style>@page{size:A4;margin:18mm}body{font:11pt sans-serif;line-height:1.45;color:#111}h1,h2,h3{break-after:avoid}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f4f4;padding:8pt}table{border-collapse:collapse;width:100%}td,th{border:1px solid #aaa;padding:5pt;overflow-wrap:anywhere}img{display:none}</style></head><body>'
            + "".join(parser.output) + '</body></html>')


def worker(config: dict) -> dict:
    command = config["command"]
    if command == "create":
        chrome = os.environ.get("MCODE_CHROME_PATH", "/usr/bin/chromium")
        if not os.path.isabs(chrome) or not os.path.isfile(chrome) or not os.access(chrome, os.X_OK):
            raise ToolError("Dependency unavailable: sandboxed Chromium; PREP must set MCODE_CHROME_PATH to its installed absolute executable")
        text = Path("input.document").read_text(encoding="utf-8")
        clean = static_html(text, config["markdown"])
        Path("static.html").write_text(clean, encoding="utf-8")
        # No downloads, remote resources, JavaScript, user CSS or unsafe sandbox flags.
        run_native([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    "--disable-background-networking", "--disable-component-update", "--disable-extensions",
                    "--disable-sync", "--no-first-run", "--no-default-browser-check",
                    "--disable-default-apps", "--metrics-recording-only",
                    "--host-resolver-rules=MAP * ~NOTFOUND", "--proxy-server=http://127.0.0.1:9",
                    "--user-data-dir=" + str(Path("chrome-profile").absolute()),
                    "--print-to-pdf=" + str(Path("created.pdf").absolute()), Path("static.html").absolute().as_uri()])
        if not Path("created.pdf").is_file() or Path("created.pdf").stat().st_size > MAX_FILE:
            raise ToolError("Chromium did not create a bounded PDF; its sandbox must work without disabling flags")
        # Reuse the bounded parser to check generated page count.
        shutil.copyfile("created.pdf", "input.pdf")
        count = len(load_pdf().pages)
        if not 1 <= count <= MAX_PAGES:
            raise ToolError("Created PDF exceeds 30 pages; reduce the source")
        return {"files": ["created.pdf"], "pages": list(range(1, count + 1)), "notes": ["Static text/table subset; scripts, styles, images and URL attributes removed"]}

    reader = load_pdf()
    selected = pages(config.get("pages"), len(reader.pages))
    if command == "extract":
        sections = []
        engine = config["engine"]
        if engine == "pdfplumber":
            try:
                import pdfplumber
            except ImportError as exc:
                raise ToolError("Dependency unavailable: pdfplumber; install requirements.lock") from exc
            with pdfplumber.open("input.pdf") as pdf:
                for page in selected:
                    sections.append(f"--- Page {page} ---\n" + (pdf.pages[page - 1].extract_text() or ""))
                    if sum(len(x) for x in sections) > MAX_FILE // 4:
                        raise ToolError("Extracted text exceeds the bounded output budget")
        elif engine == "poppler":
            executable = require("pdftotext")
            for page in selected:
                run_native([executable, "-f", str(page), "-l", str(page), "-enc", "UTF-8", "-layout", "input.pdf", "page.txt"])
                text = Path("page.txt").read_bytes()
                if len(text) > MAX_FILE:
                    raise ToolError("Extracted page exceeds output budget")
                sections.append(f"--- Page {page} ---\n" + text.decode("utf-8", "replace"))
        else:
            for page in selected:
                sections.append(f"--- Page {page} ---\n" + (reader.pages[page - 1].extract_text() or ""))
                if sum(len(x) for x in sections) > MAX_FILE // 4:
                    raise ToolError("Extracted text exceeds the bounded output budget")
        content = "\n\n".join(sections).encode("utf-8")
        if len(content) > MAX_FILE:
            raise ToolError("Extracted text exceeds 16 MiB")
        Path("extracted.txt").write_bytes(content)
        return {"files": ["extracted.txt"], "pages": selected, "engine": engine}

    executable = require("pdftoppm")
    if command == "ocr":
        tesseract = require("tesseract")
    files, sections = [], []
    for page in selected:
        box = reader.pages[page - 1].mediabox
        width, height = float(box.width), float(box.height)
        if not all(math.isfinite(x) and 0 < x <= 14400 for x in (width, height)):
            raise ToolError("Page dimensions exceed safe raster limits")
        prefix = f"page-{page:04d}"
        raster_edge = min(MAX_EDGE, max(1, math.ceil(max(width, height) * config["dpi"] / 72)))
        run_native([executable, "-f", str(page), "-l", str(page), "-singlefile", "-r", str(config["dpi"]),
                    "-scale-to", str(raster_edge), "-png", "input.pdf", prefix])
        file = prefix + ".png"
        if Path(file).stat().st_size > MAX_FILE:
            raise ToolError("Rendered page exceeds 16 MiB")
        if command == "ocr":
            run_native([tesseract, file, "ocr-page", "-l", config["language"], "--psm", "3"])
            text = Path("ocr-page.txt").read_bytes()
            if len(text) > MAX_FILE:
                raise ToolError("OCR page exceeds 16 MiB")
            sections.append(f"--- Page {page} (OCR; verify visually) ---\n" + text.decode("utf-8", "replace"))
            Path(file).unlink()
        else:
            files.append(file)
    if command == "ocr":
        content = "\n\n".join(sections).encode("utf-8")
        if len(content) > MAX_FILE:
            raise ToolError("OCR text exceeds 16 MiB")
        Path("ocr.txt").write_bytes(content)
        files = ["ocr.txt"]
    return {"files": files, "pages": selected, "max_edge_pixels": MAX_EDGE}


def resource_setup(stage_fd, seconds, memory):
    os.fchdir(stage_fd)
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FILE, MAX_FILE))
    resource.setrlimit(resource.RLIMIT_CPU, (seconds + 1, seconds + 2))
    if sys.platform.startswith("linux") and memory:
        resource.setrlimit(resource.RLIMIT_AS, (768 * MIB, 768 * MIB))


def stage_size(stage_fd: int, *extra_fds: int) -> int:
    total, entries = 0, 0
    def walk(fd, staged_inputs=False):
        nonlocal total, entries
        for name in os.listdir(fd):
            entries += 1
            if entries > 4096:
                raise ToolError("Working directory exceeded its file-count limit")
            try:
                st = os.stat(name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                continue  # Native tools may remove temporary files between scans.
            if stat.S_ISDIR(st.st_mode):
                try:
                    child = os.open(name, DIR_FLAGS, dir_fd=fd)
                except FileNotFoundError:
                    continue
                try:
                    walk(child)
                finally:
                    os.close(child)
            elif stat.S_ISREG(st.st_mode):
                if st.st_size > MAX_FILE and not (staged_inputs and name in {"input.pdf", "input.document"}):
                    raise ToolError("Native output exceeded the per-file limit")
                total += st.st_size
                if total > MAX_TOTAL:
                    raise ToolError("Working files exceeded the 80 MiB aggregate limit")
    walk(stage_fd, staged_inputs=True)
    for fd in extra_fds:
        walk(fd)
    return total


@contextlib.contextmanager
def chromium_tmp():
    # Ignore inherited TMPDIR: Chromium appends socket names subject to AF_UNIX
    # path limits. /tmp is a reviewed container tmpfs; macOS uses /private/tmp.
    # Anchor creation and cleanup, and never follow a replaced directory entry.
    parent = Workspace("/private/tmp" if sys.platform == "darwin" else "/tmp")
    name = "pdf-" + uuid.uuid4().hex
    fd = None
    created = False
    try:
        os.mkdir(name, 0o700, dir_fd=parent.fd)
        created = True
        fd = os.open(name, DIR_FLAGS, dir_fd=parent.fd)
        yield Path(parent.root) / name, fd
    finally:
        try:
            if fd is not None:
                os.close(fd)
            if created:
                shutil.rmtree(name, dir_fd=parent.fd)
        finally:
            parent.close()


def supervise(config, stage_fd, stage_path: Path, timeout):
    script = str(Path(__file__).resolve())
    env = {key: os.environ[key] for key in ("PATH", "MCODE_CHROME_PATH", "LANG", "LC_ALL", "SYSTEMROOT") if key in os.environ}
    env.update({"HOME": str(stage_path), "TMPDIR": str(stage_path), "PYTHONDONTWRITEBYTECODE": "1", "AI_HARNESS_PDF_WORKER_FD": str(stage_fd)})
    def log_file(name):
        return os.fdopen(os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=stage_fd), "wb")
    # Only Chromium needs a short socket path. Its private temporary files share
    # the stage's aggregate/file-count budget and are removed after group cleanup.
    tmp_context = chromium_tmp() if config["command"] == "create" else contextlib.nullcontext((stage_path, None))
    with tmp_context as (tmp_path, tmp_fd), log_file("worker.stdout") as out, log_file("worker.stderr") as err:
        env["TMPDIR"] = str(tmp_path)
        extra_fds = (tmp_fd,) if tmp_fd is not None else ()
        proc = subprocess.Popen([sys.executable, script, "--internal-worker"], stdin=subprocess.PIPE, stdout=out, stderr=err,
                                env=env, start_new_session=True, pass_fds=(stage_fd,),
                                preexec_fn=lambda: resource_setup(stage_fd, timeout, config["command"] != "create"))
        try:
            proc.stdin.write(json.dumps(config).encode())
            proc.stdin.close()
            deadline = time.monotonic() + timeout
            while proc.poll() is None:
                if time.monotonic() >= deadline:
                    raise ToolError("Operation timed out; select fewer pages or a smaller input")
                stage_size(stage_fd, *extra_fds)
                time.sleep(0.05)
            stage_size(stage_fd, *extra_fds)
            with os.fdopen(os.open("worker.stdout", FILE_FLAGS, dir_fd=stage_fd), "rb") as stream:
                raw = stream.read(32 * 1024 + 1)
            if len(raw) > 32 * 1024:
                raise ToolError("Worker response exceeded its limit")
            if proc.returncode != 0:
                try:
                    result = json.loads(raw)
                except (ValueError, UnicodeError):
                    result = fail("PDF worker failed or exceeded resource limits")
                raise ToolError(result["error"]["message"])
            return json.loads(raw)
        finally:
            # Also terminate any descendants remaining after their parent exits.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="Existing absolute trusted task workspace; symlinks rejected")
    parser.add_argument("--timeout", type=int, default=60, help="Whole-operation wall deadline, 1..120 seconds (default 60)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("extract", "render", "ocr", "create"):
        child = sub.add_parser(name)
        child.add_argument("input", help="Local input within workspace")
        if name == "render":
            child.add_argument("--output-dir", required=True, help="Directory for page-NNNN.png artifacts")
        else:
            child.add_argument("--output", required=True, help="New output file within workspace; never overwritten")
        if name != "create":
            child.add_argument("--pages", help="At most 30 one-based pages, e.g. 1,3-5; omitted only for PDFs <=30 pages")
        if name in ("render", "ocr"):
            child.add_argument("--dpi", type=int, default=150, help="72..200, capped at 2400 pixels per edge")
        if name == "extract":
            child.add_argument("--engine", choices=("pypdf", "pdfplumber", "poppler"), default="pypdf")
        if name == "ocr":
            child.add_argument("--language", choices=("eng",), default="eng", help="Only contracted installed OCR language: eng")
    return parser


def execute(args):
    if not 1 <= args.timeout <= 120:
        raise ToolError("--timeout must be 1..120 seconds")
    if hasattr(args, "dpi") and not 72 <= args.dpi <= 200:
        raise ToolError("--dpi must be 72..200")
    config = vars(args).copy()
    workspace = Workspace(args.workspace)
    stage_name = ".pdf-tools-" + uuid.uuid4().hex
    stage_fd = None
    try:
        if args.command == "create":
            suffix = Path(args.input).suffix.lower()
            if suffix not in {".html", ".htm", ".md", ".markdown"}:
                raise ToolError("create input must be .html, .htm, .md or .markdown")
            data = workspace.read(args.input, MIB)
            config["markdown"] = suffix in {".md", ".markdown"}
            data.decode("utf-8")
            input_name = "input.document"
        else:
            data = workspace.read(args.input)
            if not data.startswith(b"%PDF-"):
                raise ToolError("Input must start with a PDF header")
            input_name = "input.pdf"
        if args.command == "render":
            # Validate/create the target directory without inventing a page selection.
            with workspace.parent(workspace.parts(args.output_dir) + ["_probe"], create=True):
                pass
        else:
            workspace.check_output(args.output)
        os.mkdir(stage_name, 0o700, dir_fd=workspace.fd)
        stage_fd = os.open(stage_name, DIR_FLAGS, dir_fd=workspace.fd)
        stage_path = Path(workspace.root) / stage_name
        handle = os.open(input_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=stage_fd)
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        result = supervise(config, stage_fd, stage_path, args.timeout)
        artifacts = []
        produced = result.pop("files")
        for name in produced:
            output = str(Path(args.output_dir) / name) if args.command == "render" else args.output
            workspace.check_output(output)
        for name in produced:
            if not re.fullmatch(r"(?:page-[0-9]{4,}\.png|extracted\.txt|ocr\.txt|created\.pdf)", name):
                raise ToolError("Invalid internal artifact")
            output = str(Path(args.output_dir) / name) if args.command == "render" else args.output
            with os.fdopen(os.open(name, FILE_FLAGS, dir_fd=stage_fd), "rb") as stream:
                content = stream.read(MAX_FILE + 1)
            workspace.publish(output, content)
            artifacts.append({"path": "/".join(workspace.parts(output)), "bytes": len(content)})
        return {"ok": True, "operation": args.command, "artifacts": artifacts, **result}
    finally:
        if stage_fd is not None:
            os.close(stage_fd)
            # fd-anchored cleanup avoids following a replaced workspace pathname.
            shutil.rmtree(stage_name, dir_fd=workspace.fd)
        workspace.close()


def main():
    # Native task cancellation commonly sends SIGTERM rather than Ctrl-C.
    def cancelled(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, cancelled)
    if sys.argv[1:] == ["--internal-worker"]:
        try:
            inherited = int(os.environ.get("AI_HARNESS_PDF_WORKER_FD", "-1"))
            stage = os.fstat(inherited)
            cwd = os.stat(".")
            if not stat.S_ISDIR(stage.st_mode) or (stage.st_dev, stage.st_ino) != (cwd.st_dev, cwd.st_ino) or stat.S_IMODE(stage.st_mode) != 0o700:
                raise ToolError("Internal worker requires its supervised private staging directory")
            data = sys.stdin.buffer.read(4097)
            if len(data) > 4096:
                raise ToolError("Internal request too large")
            result = worker(json.loads(data))
            print(json.dumps(result, ensure_ascii=True))
            return 0
        except Exception as exc:
            print(json.dumps(fail(str(exc) if isinstance(exc, ToolError) else "Invalid PDF/document or unavailable parser dependency"), ensure_ascii=True))
            return 1
    try:
        args = build_parser().parse_args()
        result = execute(args)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except KeyboardInterrupt:
        print(json.dumps(fail("Operation cancelled", "cancelled")))
        return 130
    except (ToolError, OSError, UnicodeError, ValueError) as exc:
        message = str(exc) if isinstance(exc, ToolError) else "Path/file unavailable or unsafe, or input encoding invalid"
        print(json.dumps(fail(message), ensure_ascii=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
