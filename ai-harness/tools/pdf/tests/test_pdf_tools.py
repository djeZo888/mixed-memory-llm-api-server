"""Worker-local tests; native tools skip explicitly when unavailable."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "pdf_tools.py"
spec = importlib.util.spec_from_file_location("pdf_tools", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def write_pdf(path, text="PDF fixture alpha 123", pages=1):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    for page_index in range(pages):
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        page_text = text(page_index + 1) if callable(text) else text
        stream.set_data(f"BT /F1 20 Tf 72 700 Td ({page_text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as target:
        writer.write(target)


def process_snapshot(pid):
    """Read liveness and identity; kill(pid, 0) also succeeds for zombies."""
    if sys.platform.startswith("linux"):
        try:
            fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        except FileNotFoundError:
            return None
        return {"pid": pid, "state": fields[0], "ppid": int(fields[1]),
                "pgid": int(fields[2]), "start": fields[19]}
    result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "ppid=,pgid=,stat=,lstart="],
                            text=True, capture_output=True, check=False)
    fields = result.stdout.split()
    if not fields:
        return None
    return {"pid": pid, "ppid": int(fields[0]), "pgid": int(fields[1]),
            "state": fields[2][0], "start": " ".join(fields[3:])}


def same_live_process(before, after):
    return after is not None and before["start"] == after["start"] and after["state"] not in {"Z", "X"}


class PDFTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        # macOS /var is a symlink; the helper deliberately requires canonical roots.
        self.root = Path(self.temp.name).resolve()
        self.pdf = self.root / "fixture.pdf"
        write_pdf(self.pdf)

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args, ok=True, env=None, timeout=15):
        result = subprocess.run([sys.executable, str(SCRIPT), "--workspace", str(self.root), *args], text=True, capture_output=True, env=env, timeout=timeout)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["ok"], ok)
        self.assertFalse(list(self.root.glob(".pdf-tools-*")), "staging directory leaked")
        return payload

    def test_pypdf_extract_real(self):
        result = self.cli("extract", "fixture.pdf", "--output", "results/read.txt")
        self.assertEqual(result["pages"], [1])
        self.assertIn("PDF fixture alpha 123", (self.root / "results/read.txt").read_text())

    def test_pdfplumber_extract_real(self):
        self.cli("extract", "fixture.pdf", "--engine", "pdfplumber", "--output", "text.txt")
        self.assertIn("PDF fixture alpha 123", (self.root / "text.txt").read_text())

    @unittest.skipUnless(shutil.which("pdftotext"), "NOT_TESTED: real Poppler pdftotext unavailable")
    def test_poppler_extract_real(self):
        self.cli("extract", "fixture.pdf", "--engine", "poppler", "--output", "text.txt")
        self.assertIn("PDF fixture alpha 123", (self.root / "text.txt").read_text())

    @unittest.skipUnless(shutil.which("pdftoppm"), "NOT_TESTED: real Poppler pdftoppm unavailable")
    def test_render_real(self):
        result = self.cli("render", "fixture.pdf", "--output-dir", "images")
        self.assertEqual(len(result["artifacts"]), 1)
        from PIL import Image
        with Image.open(self.root / result["artifacts"][0]["path"]) as image:
            self.assertLessEqual(max(image.size), 2400)
            self.assertGreater(min(image.size), 100)

    @unittest.skipUnless(shutil.which("pdftoppm") and shutil.which("tesseract"), "NOT_TESTED: real Poppler/Tesseract unavailable")
    def test_ocr_real(self):
        self.cli("ocr", "fixture.pdf", "--output", "ocr.txt", timeout=30)
        self.assertIn("fixture", (self.root / "ocr.txt").read_text().lower())

    @unittest.skipUnless(os.environ.get("MCODE_CHROME_PATH") and Path(os.environ.get("MCODE_CHROME_PATH", "")).is_file()
                         and shutil.which("pdftoppm") and shutil.which("tesseract"),
                         "NOT_TESTED: real sandboxed Chromium/Poppler/Tesseract unavailable")
    def test_chromium_create_real(self):
        # This path reproduces Chromium's former AF_UNIX socket path overflow.
        self.root = self.root / ("long-workspace-" + "x" * 120)
        self.root.mkdir()
        self.assertGreater(len(str(self.root)), 120)
        (self.root / "report.md").write_text("# Fixture report\n\nChromium fixture alpha 123.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n")
        self.cli("--timeout", "30", "create", "report.md", "--output", "report.pdf", timeout=35)
        self.cli("extract", "report.pdf", "--output", "report.txt")
        self.assertIn("Chromium fixture alpha 123", (self.root / "report.txt").read_text())
        self.cli("render", "report.pdf", "--output-dir", "images", timeout=30)
        self.assertTrue((self.root / "images/page-0001.png").is_file())
        self.cli("ocr", "report.pdf", "--output", "ocr.txt", timeout=30)
        self.assertIn("fixture", (self.root / "ocr.txt").read_text().lower())

    def test_selected_pages(self):
        write_pdf(self.pdf, pages=3)
        result = self.cli("extract", "fixture.pdf", "--pages", "1,3", "--output", "text.txt")
        self.assertEqual(result["pages"], [1, 3])
        self.assertNotIn("Page 2", (self.root / "text.txt").read_text())

    def test_invalid_pages(self):
        for pages in ("0", "-1", "2", "1-0", "1;echo BAD", "1-20000000000"):
            with self.subTest(pages=pages):
                self.cli("extract", "fixture.pdf", "--pages", pages, "--output", "text.txt", ok=False)

    def test_document_page_limits(self):
        write_pdf(self.pdf, pages=31)
        self.cli("extract", "fixture.pdf", "--output", "text.txt", ok=False)
        self.cli("extract", "fixture.pdf", "--pages", "1", "--output", "text.txt")
        write_pdf(self.pdf, pages=205, text=lambda page: f"Datasheet unique page {page}")
        result = self.cli("extract", "fixture.pdf", "--pages", "203-205", "--output", "late.txt")
        self.assertEqual(result["pages"], [203, 204, 205])
        text = (self.root / "late.txt").read_text()
        self.assertIn("Datasheet unique page 203", text)
        self.assertIn("Datasheet unique page 205", text)
        self.assertNotIn("Datasheet unique page 202", text)

    def test_four_digit_late_range_real_extraction(self):
        write_pdf(self.pdf, pages=1005, text=lambda page: f"Long datasheet unique page {page}")
        result = self.cli("extract", "fixture.pdf", "--pages", "1001-1003", "--output", "late-four-digit.txt")
        self.assertEqual(result["pages"], [1001, 1002, 1003])
        text = (self.root / "late-four-digit.txt").read_text()
        for page in (1001, 1002, 1003):
            self.assertIn(f"Long datasheet unique page {page}", text)
        self.assertNotIn("Long datasheet unique page 1000", text)
        self.assertNotIn("Long datasheet unique page 1004", text)

    def test_page_range_width_checked_before_expansion(self):
        from unittest.mock import patch
        with patch.object(module, "range", side_effect=AssertionError("range was expanded"), create=True):
            for spec in ("1-100000000000000000000", "90000000000000000000-100000000000000000000"):
                with self.subTest(spec=spec), self.assertRaises(module.ToolError):
                    module.pages(spec, 100000000000000000000)
        self.assertEqual(module.pages("10000-10002", 20000), [10000, 10001, 10002])
        self.assertEqual(module.pages("20000", 20000), [20000])
        with self.assertRaises(module.ToolError):
            module.pages("1-30,31", 20000)
        with self.assertRaises(module.ToolError):
            module.pages("1" * 151, 20000)

    def test_five_digit_artifact_publication_fixture(self):
        # Exercise complete publication/validation with a fake worker result;
        # no giant PDF or native rendering acceptance claim is needed.
        from unittest.mock import patch
        def fake_worker(config, stage_fd, stage_path, timeout):
            handle = os.open("page-10000.png", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=stage_fd)
            with os.fdopen(handle, "wb") as stream:
                stream.write(b"fixture PNG")
            return {"files": ["page-10000.png"], "pages": [10000]}
        args = module.build_parser().parse_args(["--workspace", str(self.root), "render", "fixture.pdf", "--pages", "10000", "--output-dir", "images"])
        with patch.object(module, "supervise", side_effect=fake_worker):
            result = module.execute(args)
        self.assertEqual(result["artifacts"][0]["path"], "images/page-10000.png")
        self.assertEqual((self.root / "images/page-10000.png").read_bytes(), b"fixture PNG")

    def test_output_collision(self):
        target = self.root / "text.txt"
        target.write_text("keep me")
        self.cli("extract", "fixture.pdf", "--output", "text.txt", ok=False)
        self.assertEqual(target.read_text(), "keep me")

    def test_input_traversal_and_absolute_escape(self):
        for path in ("../fixture.pdf", "/etc/passwd"):
            with self.subTest(path=path):
                self.cli("extract", path, "--output", "out.txt", ok=False)

    def test_symlink_input_and_output(self):
        (self.root / "link.pdf").symlink_to(self.pdf)
        self.cli("extract", "link.pdf", "--output", "out.txt", ok=False)
        (self.root / "out.txt").symlink_to(self.pdf)
        self.cli("extract", "fixture.pdf", "--output", "out.txt", ok=False)

    def test_directory_symlink_escape(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root / "escape").symlink_to(Path(outside).resolve(), target_is_directory=True)
            self.cli("extract", "fixture.pdf", "--output", "escape/output.txt", ok=False)
            self.assertFalse((Path(outside) / "output.txt").exists())

    def test_hardlink_input(self):
        os.link(self.pdf, self.root / "hard.pdf")
        self.cli("extract", "hard.pdf", "--output", "out.txt", ok=False)

    def test_fifo_input_does_not_block(self):
        os.mkfifo(self.root / "fifo.pdf")
        self.cli("extract", "fifo.pdf", "--output", "out.txt", ok=False)

    def test_input_file_limit(self):
        with (self.root / "large.pdf").open("wb") as stream:
            stream.truncate(module.MAX_INPUT + 1)
        self.cli("extract", "large.pdf", "--output", "out.txt", ok=False)

    def test_invalid_pdf(self):
        (self.root / "invalid.pdf").write_bytes(b"%PDF-invalid")
        self.cli("extract", "invalid.pdf", "--output", "out.txt", ok=False)

    def test_encrypted_pdf(self):
        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter(clone_from=PdfReader(self.pdf))
        writer.encrypt("fixture-only-password")
        writer.write(self.pdf)
        result = self.cli("extract", "fixture.pdf", "--output", "out.txt", ok=False)
        self.assertIn("Encrypted", result["error"]["message"])

    def test_bounds(self):
        for timeout in (0, 121):
            self.cli("--timeout", str(timeout), "extract", "fixture.pdf", "--output", "text.txt", ok=False)
        for dpi in (0, 201):
            self.cli("render", "fixture.pdf", "--output-dir", "pages", "--dpi", str(dpi), ok=False)

    def test_missing_native_dependency(self):
        env = dict(os.environ, PATH="/nonexistent")
        result = self.cli("render", "fixture.pdf", "--output-dir", "pages", ok=False, env=env)
        self.assertIn("Dependency unavailable: pdftoppm", result["error"]["message"])

    def test_missing_chromium(self):
        (self.root / "report.md").write_text("# Test")
        env = dict(os.environ, MCODE_CHROME_PATH="/nonexistent/chromium")
        result = self.cli("create", "report.md", "--output", "report.pdf", ok=False, env=env)
        self.assertIn("Dependency unavailable: sandboxed Chromium", result["error"]["message"])

    def test_sanitizer_blocks_active_content(self):
        text = '<h1 onclick="evil()">Good</h1><script>evil()</script><img src="file:///etc/passwd"><style>body{background:url(https://evil)}</style><iframe src="https://evil">hidden</iframe><a href="javascript:evil()">label</a>'
        clean = module.static_html(text)
        self.assertIn("<h1>Good</h1>", clean)
        self.assertIn("<a>label</a>", clean)
        for forbidden in ("evil()", "file:///", "https://evil", "onclick", "<iframe", "<img"):
            self.assertNotIn(forbidden, clean)
        self.assertIn("default-src 'none'", clean)

    def test_render_shell_args_are_literal_fixture(self):
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "pdftoppm"
        fake.write_text(f"#!{sys.executable}\nimport pathlib,sys\nassert sys.argv[-2]=='input.pdf'\npathlib.Path(sys.argv[-1]+'.png').write_bytes(b'fixture PNG')\n")
        fake.chmod(0o700)
        name = "strange ; $(touch PWNED).pdf"
        self.pdf.rename(self.root / name)
        result = self.cli("render", name, "--output-dir", "rendered", env=dict(os.environ, PATH=str(bin_dir)))
        self.assertFalse((self.root / "PWNED").exists())
        self.assertEqual(result["artifacts"][0]["path"], "rendered/page-0001.png")

    def test_internal_worker_rejects_direct_invocation(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--internal-worker"], input="{}", text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["ok"])

    def test_render_selection_ignores_unselected_collision(self):
        write_pdf(self.pdf, pages=2)
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "pdftoppm"
        fake.write_text(f"#!{sys.executable}\nimport pathlib,sys\npathlib.Path(sys.argv[-1]+'.png').write_bytes(b'fixture PNG')\n")
        fake.chmod(0o700)
        (self.root / "images").mkdir()
        (self.root / "images/page-0001.png").write_bytes(b"keep me")
        self.cli("render", "fixture.pdf", "--pages", "2", "--output-dir", "images", env=dict(os.environ, PATH=str(bin_dir)))
        self.assertEqual((self.root / "images/page-0001.png").read_bytes(), b"keep me")

    def cancellation_fixture(self, command, cancel):
        # Fake native executable: verifies supervision, not native tool behavior.
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fake = bin_dir / ("chromium" if command == "create" else "pdftoppm")
        fake.write_text(f"#!{sys.executable}\n" + r'''import json,os,pathlib,subprocess,sys,time
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
marker = pathlib.Path.cwd().parent / 'native-processes.json'
marker.with_suffix('.tmp').write_text(json.dumps({'pids': [os.getpid(), child.pid], 'tmpdir': os.environ['TMPDIR']}))
marker.with_suffix('.tmp').replace(marker)
time.sleep(30)
''')
        fake.chmod(0o700)
        if command == "create":
            (self.root / "report.md").write_text("# Cancellation fixture")
            arguments = ["create", "report.md", "--output", "report.pdf"]
        else:
            arguments = ["render", "fixture.pdf", "--output-dir", "images"]
        env = dict(os.environ, PATH=str(bin_dir), MCODE_CHROME_PATH=str(fake))
        proc = subprocess.Popen([sys.executable, str(SCRIPT), "--workspace", str(self.root),
                                 "--timeout", "2" if cancel == "timeout" else "15", *arguments],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        identities = []
        try:
            marker = self.root / "native-processes.json"
            deadline = time.monotonic() + 5
            while not marker.exists() and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(marker.exists(), "native parent/descendant did not start")
            recorded = json.loads(marker.read_text())
            identities = [process_snapshot(pid) for pid in recorded["pids"]]
            for identity in identities:
                self.assertIsNotNone(identity)
                self.assertTrue(same_live_process(identity, identity), identity)
            self.assertEqual(identities[1]["ppid"], identities[0]["pid"])
            self.assertEqual(identities[1]["pgid"], identities[0]["pgid"])
            if cancel == "sigterm":
                proc.terminate()
            out, err = proc.communicate(timeout=5)
            self.assertEqual(proc.returncode, 130 if cancel == "sigterm" else 1, out + err)
            payload = json.loads(out)
            self.assertFalse(payload["ok"])
            if cancel == "sigterm":
                self.assertEqual(payload["error"]["code"], "cancelled")
            else:
                self.assertIn("timed out", payload["error"]["message"])
            deadline = time.monotonic() + 2
            while True:
                observed = [process_snapshot(item["pid"]) for item in identities]
                live = [after for before, after in zip(identities, observed) if same_live_process(before, after)]
                if all(after is None or before["start"] != after["start"]
                       for before, after in zip(identities, observed)) or time.monotonic() >= deadline:
                    break
                time.sleep(0.02)
            # Preserve the distinction in Linux test logs: terminated zombies are
            # not running descendants, but their reaping requires container init.
            print("native cancellation evidence: " + json.dumps({"command": command, "cancel": cancel,
                  "before": identities, "after": observed, "reaping_verified": all(x is None for x in observed)}),
                  file=sys.stderr, flush=True)
            self.assertFalse(live, f"native descendants still running: {live}")
            self.assertFalse(list(self.root.glob(".pdf-tools-*")), "staging directory leaked")
            if command == "create":
                scratch = Path(recorded["tmpdir"])
                self.assertNotEqual(scratch.parent, self.root)
                self.assertFalse(scratch.exists(), "Chromium short temporary directory leaked")
            self.assertFalse((self.root / "report.pdf").exists())
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate(timeout=5)
            # Exact identities only, including when an assertion fails; never pkill
            # or a process-group kill that could select unrelated test processes.
            for identity in identities:
                if identity and same_live_process(identity, process_snapshot(identity["pid"])):
                    try:
                        os.kill(identity["pid"], signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_sigterm_cancels_entire_native_group(self):
        self.cancellation_fixture("render", "sigterm")

    def test_timeout_kills_native_process(self):
        self.cancellation_fixture("render", "timeout")

    def test_creation_sigterm_cleans_short_tmp_fixture(self):
        self.cancellation_fixture("create", "sigterm")

    def test_creation_timeout_cleans_short_tmp_fixture(self):
        self.cancellation_fixture("create", "timeout")

    def test_creation_chromium_policy_fixture(self):
        # Fake browser verifies policy and writes a real fixture PDF. This is NOT
        # real Chromium render acceptance; test_chromium_create_real is separate.
        (self.root / "report.md").write_text("# Report\n\nfixture body\n<script>BAD_SCRIPT()</script><img src='https://invalid.invalid/a'>")
        fake = self.root / "fake-chromium"
        fake.write_text(f"#!{sys.executable}\n" + r'''import os,pathlib,socket,stat,sys
tmp = pathlib.Path(os.environ['TMPDIR'])
assert tmp.parent == pathlib.Path('/tmp').resolve()
assert stat.S_IMODE(tmp.stat().st_mode) == 0o700
assert len(os.fsencode(str(tmp))) < 60
assert tmp != pathlib.Path.cwd()
assert os.environ['HOME'] == str(pathlib.Path.cwd())
assert '--user-data-dir=' + str(pathlib.Path.cwd() / 'chrome-profile') in sys.argv
(pathlib.Path.cwd().parent / 'observed-tmpdir').write_text(str(tmp))
socket_dir = tmp / 'org.chromium.Chromium.fixture'
socket_dir.mkdir()
with socket.socket(socket.AF_UNIX) as singleton:
    singleton.bind(str(socket_dir / 'SingletonSocket'))
assert '--no-sandbox' not in sys.argv
assert '--disable-setuid-sandbox' not in sys.argv
assert '--blink-settings=scriptEnabled=false' not in sys.argv
assert '--host-resolver-rules=MAP * ~NOTFOUND' in sys.argv
assert '--proxy-server=http://127.0.0.1:9' in sys.argv
text=pathlib.Path('static.html').read_text()
assert 'BAD_SCRIPT' not in text and 'invalid.invalid' not in text
assert "script-src 'none'" in text and '<h1>Report</h1>' in text
from pypdf import PdfWriter
writer=PdfWriter()
writer.add_blank_page(width=612,height=792)
output=next(x.split('=',1)[1] for x in sys.argv if x.startswith('--print-to-pdf='))
writer.write(output)
''')
        fake.chmod(0o700)
        result = self.cli("create", "report.md", "--output", "report.pdf", env=dict(os.environ, MCODE_CHROME_PATH=str(fake)))
        self.assertEqual(result["pages"], [1])
        self.assertTrue((self.root / "report.pdf").read_bytes().startswith(b"%PDF-"))
        self.assertFalse(Path((self.root / "observed-tmpdir").read_text()).exists())

    def test_creation_still_caps_generated_pages_fixture(self):
        (self.root / "report.md").write_text("# Creation remains bounded")
        fake = self.root / "fake-chromium"
        fake.write_text(f"#!{sys.executable}\n" + r'''import os,pathlib,sys
(pathlib.Path.cwd().parent / 'observed-tmpdir').write_text(os.environ['TMPDIR'])
from pypdf import PdfWriter
writer=PdfWriter()
for _ in range(31):
    writer.add_blank_page(width=612,height=792)
output=next(x.split('=',1)[1] for x in sys.argv if x.startswith('--print-to-pdf='))
writer.write(output)
''')
        fake.chmod(0o700)
        result = self.cli("create", "report.md", "--output", "report.pdf", ok=False, env=dict(os.environ, MCODE_CHROME_PATH=str(fake)))
        self.assertIn("exceeds 30 pages", result["error"]["message"])
        self.assertFalse(Path((self.root / "observed-tmpdir").read_text()).exists())
        self.assertFalse((self.root / "report.pdf").exists())

    def test_creation_monitors_short_tmp_size_fixture(self):
        (self.root / "report.md").write_text("# Temporary size fixture")
        fake = self.root / "fake-chromium"
        fake.write_text(f"#!{sys.executable}\n" + r'''import os,pathlib,time
scratch = pathlib.Path(os.environ['TMPDIR'])
(pathlib.Path.cwd().parent / 'observed-tmpdir').write_text(str(scratch))
for index in range(6):
    with (scratch / f'piece-{index}').open('wb') as stream:
        stream.truncate(16 * 1024 * 1024)
time.sleep(20)
''')
        fake.chmod(0o700)
        result = self.cli("--timeout", "3", "create", "report.md", "--output", "report.pdf",
                          ok=False, env=dict(os.environ, MCODE_CHROME_PATH=str(fake)), timeout=5)
        self.assertIn("aggregate limit", result["error"]["message"])
        self.assertFalse(Path((self.root / "observed-tmpdir").read_text()).exists())
        self.assertFalse((self.root / "report.pdf").exists())

    def test_short_tmp_shares_working_size_budget(self):
        # Sparse local files exercise aggregate accounting without heavy I/O.
        stage = self.root / "stage"
        scratch = self.root / "scratch"
        stage.mkdir()
        scratch.mkdir()
        with (stage / "input.pdf").open("wb") as stream:
            stream.truncate(module.MIB)
        for index in range(5):
            with (scratch / f"piece-{index}").open("wb") as stream:
                stream.truncate(module.MAX_FILE)
        stage_fd = os.open(stage, module.DIR_FLAGS)
        scratch_fd = os.open(scratch, module.DIR_FLAGS)
        try:
            self.assertEqual(module.stage_size(scratch_fd), module.MAX_TOTAL)
            with self.assertRaisesRegex(module.ToolError, "aggregate limit"):
                module.stage_size(stage_fd, scratch_fd)
            for path in scratch.iterdir():
                path.unlink()
            with (scratch / "input.pdf").open("wb") as stream:
                stream.truncate(module.MAX_FILE + 1)
            with self.assertRaisesRegex(module.ToolError, "per-file limit"):
                module.stage_size(stage_fd, scratch_fd)
            (scratch / "input.pdf").unlink()
            outside = self.root / "outside"
            outside.mkdir()
            with (outside / "large").open("wb") as stream:
                stream.truncate(module.MAX_TOTAL + 1)
            (scratch / "link").symlink_to(outside, target_is_directory=True)
            self.assertEqual(module.stage_size(stage_fd, scratch_fd), module.MIB)
        finally:
            os.close(scratch_fd)
            os.close(stage_fd)

    def test_native_output_file_limit_fixture(self):
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "pdftoppm"
        fake.write_text(f"#!{sys.executable}\nimport pathlib,sys\npathlib.Path(sys.argv[-1]+'.png').write_bytes(b'x'*(17*1024*1024))\n")
        fake.chmod(0o700)
        self.cli("render", "fixture.pdf", "--output-dir", "images", ok=False, env=dict(os.environ, PATH=str(bin_dir)))
        self.assertFalse((self.root / "images/page-0001.png").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
