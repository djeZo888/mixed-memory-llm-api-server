#!/usr/bin/env python3
"""Bounded, inference-free Linux acceptance of the reviewed rootless image.

Run as the ordinary deployment user. Evidence must be outside Git. Only this
run's scratch directory, exact containers and exclusive HTTP fixture are cleaned.
No upstream credential, model prompt, paid service or browser internet is used.
"""
import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid


IMAGE = "localhost/ai-harness-engine:0.0.1-ae65651df5f9"
REVISION = "ae65651df5f97ae1085ab4e19964f4b78c769a4e"


def pid_identity(pid):
    try:
        # Field 22 is starttime. Parenthesized comm may contain spaces.
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return None


class Smoke:
    def __init__(self, args):
        self.args = args
        self.output = Path(args.output_dir).resolve()
        if self.output.exists():
            raise ValueError("output directory must be new")
        if any((parent / ".git").exists() for parent in [self.output, *self.output.parents]):
            raise ValueError("output directory must be outside Git")
        self.output.mkdir(parents=True, mode=0o700)
        self.scratch = Path(tempfile.mkdtemp(prefix="h001-runtime-smoke-", dir=args.scratch_parent)).resolve()
        self.profile, self.workspace = self.scratch / "profile", self.scratch / "workspace"
        self.profile.mkdir(mode=0o700)
        self.workspace.mkdir(mode=0o700)
        # Match the launcher mount envelope: state has writable sibling paths
        # for MiniMax migration locks and rollback, without mounting its parent.
        self.state = self.profile / "state"
        self.state.mkdir(mode=0o700)
        (self.state / "home").mkdir(mode=0o700)
        self.token = secrets.token_urlsafe(32)
        self.prefix = "h001-smoke-" + uuid.uuid4().hex
        self.containers = set()
        self.requests = []
        self.server = None
        self.process = None
        self.image_id = None
        self.security_options = []
        launcher_text = Path(args.launcher).read_text()
        if "security/chromium-seccomp.json" in launcher_text:
            if ('security_profile=$launcher_dir/security/chromium-seccomp.json' not in launcher_text or
                    '--security-opt "seccomp=$security_profile"' not in launcher_text):
                raise ValueError("unrecognized launcher seccomp integration; fixture security must match")
            profile = Path(args.launcher).resolve().parent / "security" / "chromium-seccomp.json"
            if not profile.is_file():
                raise ValueError("real launcher's scoped Chromium seccomp profile is missing")
            expected_hash = re.search(r"hexdigest\(\) == '([0-9a-f]{64})'", launcher_text)
            if not expected_hash or hashlib.sha256(profile.read_bytes()).hexdigest() != expected_hash.group(1):
                raise ValueError("scoped Chromium seccomp profile fails real launcher hash pin")
            self.security_options.append("seccomp=" + str(profile))
        self.report = {"started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "source_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       "launcher_sha256": hashlib.sha256(Path(args.launcher).read_bytes()).hexdigest(),
                       "scope": "runtime-base only; no generation or inference", "checks": {}}
        if self.security_options:
            self.report["scoped_seccomp_sha256"] = hashlib.sha256(profile.read_bytes()).hexdigest()
        self.env = {key: os.environ[key] for key in ("HOME", "USER", "LOGNAME", "PATH", "XDG_RUNTIME_DIR") if key in os.environ}
        self.env["PATH"] = "/usr/bin:/bin"
        self.env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"

    def save(self):
        self.report["http_requests"] = list(self.requests)
        (self.output / "receipt.json").write_text(json.dumps(self.report, indent=2) + "\n")

    def record(self, name, fn):
        started = time.monotonic()
        try:
            value = fn()
            self.report["checks"][name] = {"ok": True, **(value or {})}
        except Exception as error:
            # Commands and exceptions never contain the dummy token; still
            # redact it defensively before writing diagnostic artifacts.
            message = str(error).replace(self.token, "[REDACTED]")
            self.report["checks"][name] = {"ok": False, "error": message[:3000]}
        self.report["checks"][name]["elapsed_seconds"] = round(time.monotonic() - started, 3)
        self.save()
        print(json.dumps({"check": name, **self.report["checks"][name]}), flush=True)

    def command(self, args, timeout=60, check=True):
        result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                timeout=timeout, check=False, env=self.env)
        if check and result.returncode:
            raise RuntimeError(f"command failed ({result.returncode}): " + result.stderr[-2500:])
        return result

    def podman(self, *args, **kwargs):
        return self.command(["/usr/bin/podman", "--remote=false", *args], **kwargs)

    def run_image(self, name, command, timeout=60):
        if not self.image_id:
            raise RuntimeError("reviewed image identity not established")
        container = self.prefix + "-" + name
        self.containers.add(container)
        args = ["run", "--name", container, "--rm", "--pull=never",
                "--userns", "keep-id", "--user", f"{os.getuid()}:{os.getgid()}",
                "--network", "slirp4netns:allow_host_loopback=true",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--read-only", "--pids-limit", "1024", "--shm-size", "512m",
                "--tmpfs", "/tmp:rw,nosuid,nodev,size=1g,mode=1777",
                "--tmpfs", "/run:rw,nosuid,nodev,size=64m,mode=755",
                "--tmpfs", "/var/tmp:rw,nosuid,nodev,size=256m,mode=1777",
                "--stop-signal", "SIGTERM", "--stop-timeout", "20",
                "--volume", f"{self.profile}:{self.profile}:rw,rprivate",
                "--volume", f"{self.workspace}:{self.workspace}:rw,rprivate",
                "--workdir", str(self.workspace),
                "--env", f"HOME={self.state}/home", "--env", f"MINIMAX_DATA_DIR={self.state}",
                "--env", "PATH=/opt/ai-harness-python/bin:/opt/ai-harness/bin:/usr/local/bin:/usr/bin:/bin",
                "--env", "TERM=dumb", "--env", "NO_COLOR=1", "--env", "MCODE_DISABLE_TELEMETRY=1",
                "--env", "DO_NOT_TRACK=1", "--env", "MCODE_CHROME_PATH=/usr/bin/chromium",
                "--env", "PYTHONDONTWRITEBYTECODE=1"]
        for option in self.security_options:
            args.extend(["--security-opt", option])
        args.extend(["--entrypoint", command[0], self.image_id, *command[1:]])
        (self.output / f"{name}-command.json").write_text(json.dumps(["podman", "--remote=false", *args], indent=2) + "\n")
        try:
            result = self.podman(*args, timeout=timeout, check=False)
            (self.output / f"{name}.stdout").write_text(result.stdout)
            (self.output / f"{name}.stderr").write_text(result.stderr)
            if result.returncode:
                raise RuntimeError(f"image command exit={result.returncode}; see {name}.stderr: {result.stderr[-1800:]}")
            return result.stdout
        finally:
            self.podman("rm", "--force", "--time", "20", "--ignore", container, timeout=30, check=False)

    def image(self):
        # Inspect selected public metadata only. Never serialize image/container env.
        metadata = self.podman("image", "inspect", "--format", '{{.Id}}|{{index .Labels "org.opencontainers.image.revision"}}|{{index .Labels "org.opencontainers.image.ai-harness.patchset"}}', self.args.image).stdout.strip().split("|")
        if len(metadata) != 3 or not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", metadata[0]) or metadata[1] != REVISION:
            raise RuntimeError("image revision or ID does not match reviewed runtime")
        launcher = Path(self.args.launcher).read_text()
        expected = re.search(r"^patchset=([0-9a-f]{64})$", launcher, re.M)
        if not expected or metadata[2] != expected.group(1):
            raise RuntimeError("image patchset does not match real launcher")
        self.image_id = metadata[0]
        history = self.podman("history", "--no-trunc", "--format", "{{.ID}}|{{.Size}}", self.image_id).stdout
        (self.output / "image-layer-history.txt").write_text(history)
        return {"image_id": metadata[0], "revision": metadata[1], "patchset": metadata[2], "layer_history": "image-layer-history.txt"}

    def versions(self):
        script = r'''
import hashlib,json,pathlib,subprocess,os
assert os.getuid()!=0
commands={'node':['node','--version'],'minimax':['node','/opt/minimax/cli.js','--version'],'chromium':['chromium','--version'],'python':['python','--version']}
result={'uid':os.getuid(),'versions':{},'notices':[]}
for name,argv in commands.items():
 p=subprocess.run(argv,capture_output=True,text=True,timeout=30,check=True)
 result['versions'][name]=(p.stdout+p.stderr).strip()
for path in sorted(pathlib.Path('/opt/minimax').iterdir()):
 if path.is_file() and ('license' in path.name.lower() or 'notice' in path.name.lower()):
  data=path.read_bytes();result['notices'].append({'path':str(path),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'first_line':data.decode(errors='replace').splitlines()[0] if data else ''})
for path in ['/usr/local/share/ai-harness-dpkg.tsv','/usr/local/share/ai-harness-python.txt','/usr/local/share/ai-harness-npm.json','/opt/minimax/embedded/mcode-tools/manifest.json']:
 data=pathlib.Path(path).read_bytes();result.setdefault('manifests',[]).append({'path':path,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
print(json.dumps(result))
assert any('license' in p['path'].lower() and p['bytes'] for p in result['notices']), 'MiniMax license absent'
assert any('MCODE_TOOLS_NOTICES' in p['path'] and p['bytes'] for p in result['notices']), 'mcode tools notices absent'
'''
        return json.loads(self.run_image("versions", ["python3", "-c", script], timeout=120))

    def browser(self):
        fixture = self.workspace / "browser-fixture.html"
        fixture.write_text('<!doctype html><meta charset="utf-8"><title>Local smoke</title><p id="result">pending</p><script>document.getElementById("result").textContent="dom-js-ok:"+(6*7)</script>')
        script = r'''
const {chromium}=require('/usr/local/lib/node_modules/@playwright/test');
(async()=>{
if(process.getuid()===0)throw Error('root browser refused');
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,chromiumSandbox:true,args:['--disable-background-networking','--disable-component-update','--no-first-run']});
try {
 const page=await browser.newPage();
 await page.route('http://**/*',route=>route.abort());
 await page.route('https://**/*',route=>route.abort());
 await page.goto('file://'+process.argv[1]);
 const dom=await page.locator('#result').innerText();
 if(dom!=='dom-js-ok:42')throw Error('local JS DOM mismatch');
 await page.goto('chrome://sandbox');
 const sandbox=await page.locator('body').innerText();
 console.log(JSON.stringify({uid:process.getuid(),dom,sandbox}));
 const namespaceActive=/Layer 1 Sandbox\s+Namespace/i.test(sandbox)&&/PID namespaces\s+Yes/i.test(sandbox)&&/Network namespaces\s+Yes/i.test(sandbox);
 const legacyLayerActive=/(?:Namespace|SUID) sandbox\s+Yes/i.test(sandbox);
 if(!(namespaceActive||legacyLayerActive)||!/Seccomp-BPF sandbox\s+Yes/i.test(sandbox))throw Error('Chrome sandbox status did not confirm namespace/SUID and seccomp');
}finally{await browser.close()}
})().catch(error=>{console.error(error.stack);process.exitCode=1});
'''
        return json.loads(self.run_image("browser", ["node", "-e", script, str(fixture)], timeout=90))

    def fixture(self):
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                # Discard headers. The path is never copied to evidence because
                # credentials must not leak through an unexpected query string.
                allowed = self.path == "/__h001_runtime_smoke__"
                owner.requests.append({"method": "GET", "kind": "route-fixture" if allowed else "unexpected", "accepted": allowed})
                body = b'{"fixture":"h001-no-inference"}' if allowed else b'{"error":"smoke fixture only"}'
                self.send_response(200 if allowed else 403)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def reject(self):
                owner.requests.append({"method": self.command, "kind": "rejected-no-inference", "accepted": False})
                self.send_response(403)
                self.send_header("Content-Length", "0")
                self.end_headers()
                self.close_connection = True

            do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = reject

        class ExclusiveServer(http.server.ThreadingHTTPServer):
            allow_reuse_address = False
            daemon_threads = True

        # Bind fails if another owner has the port. Never stop another service.
        self.server = ExclusiveServer(("127.0.0.1", 8081), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return {"bind": "127.0.0.1:8081", "exclusive": True}

    def gateway(self):
        if self.server is None:
            raise RuntimeError("exclusive host fixture unavailable; no gateway request attempted")
        script = "const r=await fetch('http://10.0.2.2:8081/__h001_runtime_smoke__',{signal:AbortSignal.timeout(5000)});const body=await r.json();if(r.status!==200||body.fixture!=='h001-no-inference')throw Error('wrong fixture response');console.log(JSON.stringify({status:r.status,body}));"
        return json.loads(self.run_image("gateway", ["node", "--input-type=module", "-e", script], timeout=30))

    def owned_launcher_container(self):
        for container in self.podman("ps", "--quiet", "--no-trunc").stdout.splitlines():
            inspected = self.podman("inspect", "--format", '{{json .Mounts}}|{{.State.Pid}}|{{.Image}}|{{.Name}}', container, check=False)
            if inspected.returncode:
                continue
            parts = inspected.stdout.strip().split("|")
            if len(parts) != 4:
                continue
            mounts = json.loads(parts[0])
            paths = {(item.get("Source"), item.get("Destination")) for item in mounts}
            if ((str(self.profile), str(self.profile)) in paths and
                    (str(self.workspace), str(self.workspace)) in paths and
                    parts[2] == self.image_id and re.fullmatch(r"/?ai-harness-[0-9a-f]{32}", parts[3])):
                self.containers.add(container)
                return container, int(parts[1])
        raise RuntimeError("real launcher container not found by exact owned mounts and image")

    def acp(self):
        if self.server is None or not self.image_id:
            raise RuntimeError("exclusive no-inference fixture and reviewed image are mandatory before ACP")
        env = dict(self.env, AI_HARNESS_GATEWAY_TOKEN=self.token, AI_HARNESS_SESSION_ID=self.prefix,
                   AI_HARNESS_GATEWAY_URL="http://10.0.2.2:8081/v1")
        args = ["/bin/bash", str(Path(self.args.launcher).resolve()), "--profile-dir", str(self.profile), "--workspace", str(self.workspace)]
        (self.output / "acp-command.json").write_text(json.dumps(args, indent=2) + "\n")
        self.process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True, bufsize=1, env=env)
        messages = queue.Queue()

        def reader(stream, filename, is_stdout):
            with (self.output / filename).open("w") as log:
                for line in stream:
                    log.write(line.replace(self.token, "[REDACTED]"))
                    log.flush()
                    if is_stdout:
                        try:
                            messages.put(json.loads(line))
                        except json.JSONDecodeError:
                            messages.put({"parse_error": True})

        self.readers = [threading.Thread(target=reader, args=(self.process.stdout, "acp.stdout", True), daemon=True),
                        threading.Thread(target=reader, args=(self.process.stderr, "acp.stderr", False), daemon=True)]
        for worker in self.readers:
            worker.start()

        def request(number, method, params):
            self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": number, "method": method, "params": params}) + "\n")
            self.process.stdin.flush()
            deadline = time.monotonic() + self.args.acp_timeout
            while time.monotonic() < deadline:
                if self.process.poll() is not None and messages.empty():
                    raise RuntimeError(f"launcher exited {self.process.returncode} during {method}; see acp.stderr")
                try:
                    message = messages.get(timeout=0.2)
                except queue.Empty:
                    continue
                if message.get("parse_error"):
                    raise RuntimeError("non-JSON data on ACP stdout")
                if message.get("id") == number and "method" not in message:
                    if "error" in message:
                        raise RuntimeError(f"{method} returned ACP error: {json.dumps(message['error'])}")
                    return message.get("result")
                if "method" in message and "id" in message:
                    self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": message["id"],
                        "error": {"code": -32601, "message": "Inference-free smoke client exposes no tools"}}) + "\n")
                    self.process.stdin.flush()
            raise RuntimeError(f"{method} response timeout after {self.args.acp_timeout}s")

        initialized = request(1, "initialize", {"protocolVersion": 1, "clientCapabilities": {},
                               "clientInfo": {"name": "h001-inference-free-smoke", "version": "1.0.0"}})
        if not isinstance(initialized, dict) or initialized.get("protocolVersion") != 1:
            raise RuntimeError("initialize did not negotiate native ACP protocolVersion 1")
        session = request(2, "session/new", {"cwd": str(self.workspace), "mcpServers": []})
        if not isinstance(session, dict) or not isinstance(session.get("sessionId"), str) or not session["sessionId"]:
            raise RuntimeError("session/new did not return a native sessionId")
        container, pid = self.owned_launcher_container()
        self.launcher_container = container
        self.container_pid = pid
        # A real extra descendant tests process-tree settlement without a model
        # call or host process mount. Its argv contains no authorization material.
        self.podman("exec", "--detach", container, "node", "-e", "setInterval(()=>{},1000)", timeout=15)
        deadline = time.monotonic() + 5
        while True:
            top = self.podman("top", container, "hpid", timeout=15).stdout
            pids = [int(line.strip()) for line in top.splitlines()[1:] if line.strip().isdigit()]
            if len(pids) >= 2 or time.monotonic() >= deadline:
                break
            time.sleep(0.1)
        self.descendants = {pid: pid_identity(pid) for pid in pids}
        if pid not in self.descendants or len(self.descendants) < 2 or any(value is None for value in self.descendants.values()):
            raise RuntimeError("could not record actual container and child host PID identities")
        return {"protocol_version": initialized["protocolVersion"], "session_created": True,
                "container_id": container, "host_pid": pid, "host_process_count": len(pids),
                "requests_sent": ["initialize", "session/new"], "generation_requests_sent": 0}

    def termination(self):
        if self.process is None:
            raise RuntimeError("no launcher process was started")
        if self.process.poll() is not None:
            raise RuntimeError(f"launcher was already exited with {self.process.returncode}; TERM acceptance not established")
        started = time.monotonic()
        self.process.send_signal(signal.SIGTERM)
        code = self.process.wait(timeout=40)
        elapsed = time.monotonic() - started
        for worker in getattr(self, "readers", []):
            worker.join(timeout=2)
        container = getattr(self, "launcher_container", None)
        exists = self.podman("container", "exists", container, check=False, timeout=5).returncode if container else None
        pending = dict(getattr(self, "descendants", {}))
        # Removal should reap all container PIDs by launcher settlement. Permit
        # only the remaining launcher budget for scheduler/reaper completion.
        while pending and time.monotonic() - started < 40:
            pending = {pid: identity for pid, identity in pending.items() if pid_identity(pid) == identity}
            if pending:
                time.sleep(0.1)
        receipt = {"launcher_exit": code, "term_to_exit_seconds": round(elapsed, 3),
                   "term_to_verification_seconds": round(time.monotonic() - started, 3),
                   "container_id": container, "container_exists_exit": exists,
                   "remaining_original_host_pids": list(pending), "launcher_budget_seconds": 40}
        (self.output / "termination.json").write_text(json.dumps(receipt, indent=2) + "\n")
        if code != 0 or elapsed > 40 or exists != 1 or pending or not getattr(self, "descendants", None):
            raise RuntimeError("real TERM receipt failed or incomplete; see termination.json")
        return receipt

    def cleanup(self):
        failures = []
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=40)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
                failures.append("launcher exceeded cleanup budget")
        # Capture a container even if ACP failed before normal discovery.
        if self.process:
            try:
                self.owned_launcher_container()
            except RuntimeError:
                pass
        for container in sorted(self.containers):
            result = self.podman("rm", "--force", "--time", "20", "--ignore", container, timeout=30, check=False)
            absent = self.podman("container", "exists", container, timeout=5, check=False).returncode == 1
            if result.returncode or not absent:
                failures.append(f"owned container settlement unconfirmed: {container}")
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if failures:
            raise RuntimeError("; ".join(failures) + "; scratch preserved at " + str(self.scratch))
        shutil.rmtree(self.scratch)
        return {"owned_containers_absent": True, "owned_fixture_closed": self.server is not None,
                "owned_scratch_removed": True, "image_and_cache_retained": True}

    def run(self):
        for name, check in (("image", self.image), ("versions_notices", self.versions),
                            ("chromium_sandbox", self.browser), ("exclusive_host_fixture", self.fixture),
                            ("private_gateway_route", self.gateway), ("native_acp", self.acp),
                            ("real_termination", self.termination), ("owned_cleanup", self.cleanup)):
            self.record(name, check)
        rejected = [request for request in self.requests if request["kind"] != "route-fixture"]
        self.report["checks"]["no_inference"] = {"ok": not rejected, "unexpected_requests": len(rejected),
                                                   "model_requests_sent_by_test": 0}
        self.report["complete_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.report["ok"] = all(check["ok"] for check in self.report["checks"].values())
        self.save()
        return 0 if self.report["ok"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launcher", default=str(Path(__file__).resolve().parents[1] / "run-engine.sh"))
    parser.add_argument("--image", default=IMAGE, help="reviewed local tag; must match the real launcher")
    parser.add_argument("--output-dir", required=True, help="new evidence directory outside Git")
    parser.add_argument("--scratch-parent", default="/tmp", help="existing canonical user-writable parent for isolated mounts")
    parser.add_argument("--acp-timeout", type=int, default=60, choices=range(5, 121), metavar="5..120")
    args = parser.parse_args()
    if sys.platform != "linux" or os.getuid() == 0:
        parser.error("requires Linux and an ordinary user; never invoke through sudo")
    os.umask(0o077)
    return Smoke(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
