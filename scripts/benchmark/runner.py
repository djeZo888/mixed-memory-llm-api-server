"""Deterministic worker campaign. Live I/O is explicit, source imports are inert.

The worker runs as an ordinary user; tools and private raw samples remain here.
A persistent SSH host process owns the canonical capability and all VM lifecycle
operations. JSON RPC is serialized; inference uses existing protected keys and
authenticated SSH-forwarded loopback HTTP, allowing two independent requests.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import threading
import time

from . import accounting, client, fixtures, profiles, telemetry, workload

# One root-reviewed saved-response disposition, never a general failure bypass.
Q1_GENERATION_FRAMING = {
    "case": "Q1-16384-generation",
    "failed_row_sha256": "539e3d713bb8d35a580c7b43d5e48dd6b6813e271124364f30dde0adfe907e3e",
    "semantic_disposition_sha256": "33ad94d2e70546bc3929be66f5d7e68ae35251caf5dfd13a70ff54065c8b89e4",
    "normalization": "remove_one_enclosing_json_fence",
    "semantic_status": "PASS",
}


def save(path, value):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".pending")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(fixtures.canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def source_files(scope=None):
    paths = set()
    for group in ("scripts/benchmark", "scripts/agent", "scripts/d3t", "scripts/runtime"):
        paths.update(profiles.ROOT.joinpath(group).glob("*.py"))
    paths.add(profiles.ROOT / "scripts/bench/benchmark-host.py")
    paths.add(profiles.CONFIG)
    paths.add(profiles.ROOT / "configs/benchmarks/glmrepair-g2-20260919.json")
    paths.add(profiles.ROOT / "configs/benchmarks/glmrepair-g1-20260919.json")
    paths.update(profiles.ROOT / name for name in profiles.read_config()["source_pins"])
    if scope == "candidate-pair-validation":
        cp, qwen = profiles.candidate_modules()
        paths.update(profiles.ROOT / name for name in cp.source_identity())
        paths.update(profiles.ROOT / name for name in qwen.PROFILE_HASHES)
        paths.add(profiles.ROOT / "reports/q38r-source-weight-manifest.json")
        paths.update((profiles.ROOT / "scripts/lifecycle").glob("*.py"))
        paths.update(p for p in (profiles.ROOT / "tests/lifecycle/sglang38_fixture").iterdir()
                     if p.is_file() and p.suffix in {".py", ".json", ".jinja"})
    return {str(p.relative_to(profiles.ROOT)): p.read_bytes() for p in sorted(paths)}


def arm(state, campaign, scope="full"):
    state = Path(state)
    if not re.fullmatch(r"benchrun-[a-z0-9-]{1,32}", campaign):
        raise ValueError("invalid_campaign")
    if (state / "arm.json").exists():
        raise ValueError("arm_exists_preserve_existing_campaign")
    files = source_files()
    manifests = [profiles.command_manifest(p, n, campaign=campaign, ram_cap=profiles.G1_RAM_CAP_BYTES if scope == "g1-only" else None, log_verbosity=4 if scope == "g1-only" else None) for p in profiles.scope_placements(scope) for n in profiles.scope_capacities(scope)]
    value = {"schema": 1, "campaign": campaign, "source_files": {p: hashlib.sha256(b).hexdigest() for p, b in files.items()},
             "manifests": manifests, "trial_plan": profiles.trial_order(scope),
             "phase": "ARMED_OFFLINE_NOT_STARTED", "host": "ai-vm", "private_lan": "10.156.100.60"}
    if scope != "full":
        value.update(scope=scope, continuation_execution=json.loads((state / "execution.json").read_bytes()))
    save(state / "arm.json", value)
    save(state / "progress.json", {"phase": "ARMED", "completed": {}, "inflight": {}, "errors": []})
    return fixtures.digest(fixtures.canonical(value))


def load_arm(state, reviewed):
    value = json.loads((Path(state) / "arm.json").read_bytes())
    if fixtures.digest(fixtures.canonical(value)) != reviewed:
        raise ValueError("root_reviewed_arm_hash_mismatch")
    if {p: hashlib.sha256(b).hexdigest() for p, b in source_files(value.get("scope")).items()} != value["source_files"]:
        raise ValueError("armed_source_changed")
    if profiles.validate_arm_scope(value) not in {"full", "candidate-pair-validation"}:
        if json.loads((Path(state) / "execution.json").read_bytes()) != value.get("continuation_execution"):
            raise ValueError("q1_continuation_epoch_changed")
    return value


def run_preflight(scope="full"):
    """Offline source-evidence gate, before key reads, staging or ownership."""
    if scope in ("q1-only", "q1-256k"):
        return
    expected = profiles.read_config().get("glm_offload_expectation", {})
    if (expected.get("evidence_status") != "REVIEWED_LOG_COUNT_SEMANTICS"
            or not expected.get("provenance")
            or any(type(expected.get(k)) is not int or expected[k] <= 0 for k in ("offloaded_layers", "total_layers"))):
        raise RuntimeError("BLOCKED_GLM_OFFLOAD_LOG_COUNT_EVIDENCE")


# Source staging is a reviewed operation in RUN only. Files are a closed hash
# inventory, not arbitrary tar extraction. All writes use the installed anchored
# writer and are guarded before/after. No installation or production file edits.
STAGE = r'''
import base64,hashlib,json,os,pathlib,subprocess,sys
v=json.load(sys.stdin);root=pathlib.Path('/usr/local/lib/llm-server/control-api')
for rel,row in v['config']['installed_source_identities'].items():
 p=root/rel
 for q in (p,*p.parents):
  st=q.lstat();assert not q.is_symlink() and st.st_uid==0 and not st.st_mode&0o022
 assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
guard=root/'scripts/common/registered-storage.py'
def guards():
 subprocess.run(['/usr/bin/python3','-I','-B',str(guard),'--root-guard'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
guards();sys.path.insert(0,str(root/'scripts'))
from lifecycle.storage_binding import RegisteredStorageBinding
from lifecycle.manager import StorageRunner
from common.lifecycle_lease import acquire_lease
from install import storage_io
binding=RegisteredStorageBinding.load(StorageRunner())
campaign=v['arm']['campaign'];assert __import__('re').fullmatch(r'benchrun-[a-z0-9-]{1,32}',campaign)
with acquire_lease(blocking=False):
 with binding.mounted_guard(storage_io) as mounted:
  with storage_io.AnchoredRoot('/data/services',mounted) as anchor:
   anchor.mkdir(campaign+'/source')
   for rel,digest in v['arm']['source_files'].items():
    assert not rel.startswith('/') and '..' not in pathlib.PurePosixPath(rel).parts
    raw=base64.b64decode(v['files'][rel],validate=True);assert hashlib.sha256(raw).hexdigest()==digest
    target=campaign+'/source/'+rel;anchor.mkdir(str(pathlib.PurePosixPath(target).parent))
    exists=anchor.stat(target,missing_ok=True)
    if exists is not None:
     with anchor.open(target) as file:
      assert hashlib.sha256(file.read()).hexdigest()==digest
    else:
     with anchor.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644) as file:
      file.write(raw);file.fsync()
   anchor.atomic_json(campaign+'/manifests.json',v['arm'])
 guards()
print('{"staged":true}')
'''


class SSHHost:
    def __init__(self, armed, *, stage=False, popen=subprocess.Popen, run=subprocess.run):
        self.armed, self.lock = armed, threading.RLock()
        campaign = armed["campaign"]
        self.command = ["/usr/bin/sudo", "-n", "/usr/bin/python3", "-I", "-B",
                        f"/data/services/{campaign}/source/scripts/bench/benchmark-host.py",
                        "--campaign", campaign, "--manifests", f"/data/services/{campaign}/manifests.json", "--serve"]
        if stage:
            payload = {"arm": armed, "config": profiles.read_config(),
                       "files": {p: base64.b64encode(b).decode() for p, b in source_files(armed.get("scope")).items()}}
            result = run(["ssh", "-T", "-o", "BatchMode=yes", "ai-vm", shlex.join(["sudo", "-n", "python3", "-I", "-B", "-c", STAGE])],
                         input=fixtures.canonical(payload), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
            if result.returncode or json.loads(result.stdout).get("staged") is not True:
                raise ValueError("guarded_source_stage_failed")
        target_ports = (30002, 30004) if armed.get("scope") == "candidate-pair-validation" else (31002, 31004)
        argv = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
                "-L", f"127.0.0.1:31002:127.0.0.1:{target_ports[0]}", "-L", f"127.0.0.1:31004:127.0.0.1:{target_ports[1]}",
                "ai-vm", shlex.join(self.command)]
        if armed.get("scope") == "postrestart72-480k":
            argv[1:1] = ["-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3"]
        self.rpc_unavailable = False
        self.process = popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)

    def call(self, op, **args):
        with self.lock:
            if self.armed.get("scope") == "postrestart72-480k":
                if self.rpc_unavailable:
                    raise RuntimeError("postrestart_RPC_unavailable_explicit_recovery_required")
                # Read the entire line in a daemon: select/readline alone can
                # hang on a partial reply. Never send a second RPC after timeout.
                complete, captured = threading.Event(), {}
                def exchange():
                    try:
                        self.process.stdin.write(json.dumps({"op": op, **args}, separators=(",", ":")) + "\n")
                        self.process.stdin.flush()
                        captured["line"] = self.process.stdout.readline()
                    except BaseException as error:
                        captured["error"] = type(error).__name__
                    finally:
                        complete.set()
                thread = threading.Thread(target=exchange, daemon=True)
                thread.start()
                timeout = (min(7200, args.get("timeout_s", 7200)) + 30 if op == "readiness" else
                           7300 if op in {"restore", "recover"} else 180 if op in {"begin", "load"} else 90)
                if not complete.wait(timeout) or "error" in captured:
                    self.rpc_unavailable = True
                    raise RuntimeError("postrestart_RPC_unavailable_explicit_recovery_required")
                line = captured.get("line")
            else:
                self.process.stdin.write(json.dumps({"op": op, **args}, separators=(",", ":")) + "\n")
                self.process.stdin.flush()
                line = self.process.stdout.readline()
            if not line:
                if self.armed.get("scope") == "postrestart72-480k":
                    self.rpc_unavailable = True
                raise RuntimeError("host_session_lost_explicit_recovery_required")
            if self.armed.get("scope") == "postrestart72-480k":
                try:
                    result = json.loads(line)
                    if not line.endswith("\n") or not isinstance(result, dict):
                        raise ValueError("incomplete_host_RPC_reply")
                except (ValueError, TypeError):
                    self.rpc_unavailable = True
                    raise RuntimeError("postrestart_RPC_unavailable_explicit_recovery_required") from None
            else:
                result = json.loads(line)
            if result.get("error"):
                raise RuntimeError("host_operation_refused:" + str(result["error"]))
            return result.get("result", result)

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=30)


class Campaign:
    """One deterministic journaled campaign; same code used by mocked integration tests."""
    def __init__(self, state, armed, host, key, *, transport_factory=client.http_transport,
                 json_factory=client.protected_json_client, clock=time.monotonic, sleep=time.sleep):
        self.state, self.armed, self.host, self.key = Path(state), armed, host, key
        self.transport_factory, self.json_factory, self.clock, self.sleep = transport_factory, json_factory, clock, sleep
        self.lock = threading.RLock()
        self.progress = json.loads((self.state / "progress.json").read_bytes())
        self.active, self.samples, self.safety = {}, {}, {}
        self.proof_pending = None  # REAL72 current observation only; safety is latched
        self.demand = dict(self.progress.get("measured_demand_bytes", {}))
        self.demand_evidence = dict(self.progress.get("measured_demand_evidence", {}))
        self.stop = threading.Event()
        self.private = self.state / "private"
        self.private.mkdir(mode=0o700, exist_ok=True)
        self.fixture_cache = {}
        if (self.private / "fixtures.json").exists():
            self.fixture_cache = json.loads((self.private / "fixtures.json").read_bytes())

    def record(self, phase=None):
        with self.lock:
            if phase:
                self.progress["phase"] = phase
            self.progress["measured_demand_bytes"] = dict(self.demand)
            self.progress["measured_demand_evidence"] = dict(self.demand_evidence)
            save(self.state / "progress.json", self.progress)

    def emit(self, record):
        with self.lock:
            fd = os.open(self.state / "results.jsonl", os.O_APPEND | os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "ab") as stream:
                stream.write(fixtures.canonical(record) + b"\n");stream.flush();os.fsync(stream.fileno())

    def collect(self):
        started = self.clock()
        for cid in list(self.active):
            try:
                row = self.host.call("telemetry", id=cid)
                # Host monotonic is a different clock; preserve it separately.
                row["host_timestamp_monotonic_s"] = row.get("timestamp_monotonic_s")
                row["timestamp_monotonic_s"] = self.clock()
                if "cpu_budget" in row:
                    row["cpu_budget"]["client_observed_monotonic_s"] = row["timestamp_monotonic_s"]
                with self.lock:
                    self.samples.setdefault(cid, []).append(row)
                    base = self.active[cid]["baseline"]
                    groups = row.get("cgroups", {})
                    group = groups.get(cid, next(iter(groups.values()), {}))
                    swaps = [s.get("cgroups", {}).get(cid, {}).get("swap_bytes") for s in self.samples[cid]]
                    verdict = telemetry.model_swap_state(base.get("swap_bytes"), swaps)
                    events, old = group.get("events", {}), base.get("events", {})
                    if any(type(events.get(k)) is int and type(old.get(k)) is int and events[k] > old[k] for k in ("oom", "oom_kill", "oom_group_kill")):
                        verdict = "STOP_OOM"
                    resource_stop = verdict if verdict.startswith("STOP_") else None
                    # A known timed-out GPU query during loading is an observation
                    # gap, not measured low reserve. Keep the raw sample; require
                    # fresh complete resource proof before warmup below.
                    loading_gpu_timeout = (self.armed.get("scope") in {"g1-only", "glmrepair", "g1-ladder", "glm-decode-diag", "concurrent-g1q1", "candidate-pair-validation", "concurrent-480k-cpu", "postrestart72-480k"}
                        and self.active[cid].get("phase") == "loading"
                        and row.get("errors") == ["gpu_TimeoutExpired"] and row.get("gpus") == [])
                    if self.armed.get("scope") in {"concurrent-g1q1", "candidate-pair-validation", "concurrent-480k-cpu", "postrestart72-480k"}:
                        gate = row.get("concurrent_resource_gate", {})
                        gpu_gap_reasons = (["candidate_qwen_ten_percent_unavailable", "concurrent_gpu_free_unavailable"]
                            if self.armed.get("scope") == "candidate-pair-validation" else
                            ["concurrent_gpu_free_unavailable", "cpu_qwen_ten_percent_unavailable"]
                            if self.armed.get("scope") in {"concurrent-480k-cpu", "postrestart72-480k"} and any(
                                m.get("placement") == "Q1" for m in [entry["manifest"] for entry in self.active.values()])
                            else ["concurrent_gpu_free_unavailable"])
                        loading_gpu_gap = (loading_gpu_timeout and gate.get("status") == "UNAVAILABLE"
                            and gate.get("unavailable_reasons") == gpu_gap_reasons
                            and gate.get("reasons") == [] and gate.get("latched_violations") == {})
                        # Allocation readiness and every request_begin still
                        # require fresh full PASS on the host; no zero/reset.
                        if gate.get("status") == "STOP_RESOURCE_GATE":
                            verdict = resource_stop = "STOP_RESOURCE_GATE"
                        elif gate.get("status") != "PASS" and not loading_gpu_gap:
                            verdict = "SKIP_UNSAFE_PLACEMENT"
                    if self.armed.get("scope") != "postrestart72-480k" and not loading_gpu_timeout and not set(self.active[cid]["manifest"]["gpu_uuids"]).issubset({g.get("uuid") for g in row.get("gpus", [])}):
                        verdict = "SKIP_UNSAFE_PLACEMENT"
                    if self.armed.get("scope") != "postrestart72-480k" and any(g.get("uuid") in self.active[cid]["manifest"]["gpu_uuids"] and (g.get("free_bytes") is None or g["free_bytes"] < 16 * 1024**3) for g in row.get("gpus", [])):
                        verdict = "SKIP_UNSAFE_PLACEMENT"
                    if self.armed.get("scope") != "postrestart72-480k" and (row.get("host", {}).get("available_bytes") is None or row["host"]["available_bytes"] < 16 * 1024**3):
                        verdict = "SKIP_UNSAFE_PLACEMENT"
                    if self.armed.get("scope") == "postrestart72-480k":
                        # One host row covers the whole currently loaded pair.
                        # New full proof replaces only the current gap, never a
                        # fault, abort/cancel state or the append-only samples.
                        gate = row.get("concurrent_resource_gate", {})
                        if resource_stop or gate.get("reasons") or gate.get("latched_violations"):
                            verdict = resource_stop = resource_stop or "STOP_RESOURCE_GATE"
                        else:
                            complete = (gate.get("status") == "PASS" and not row.get("errors")
                                and set(self.active) <= set(gate.get("charges", {})))
                            self.proof_pending = None if complete else {
                                "status": "UNAVAILABLE", "container": cid,
                                "host_timestamp_monotonic_s": row.get("host_timestamp_monotonic_s"),
                                "unavailable_reasons": gate.get("unavailable_reasons", [])}
                            verdict = "CURRENT_PROOF_PASS" if complete else "UNAVAILABLE"
                    if verdict.startswith(("STOP_", "SKIP_")):
                        if self.armed.get("scope") == "postrestart72-480k":
                            self.safety.setdefault(cid, verdict)
                        else:
                            self.safety[cid] = verdict
                    if self.armed.get("scope") in {"g1-only", "glmrepair", "g1-ladder", "glm-decode-diag", "concurrent-g1q1", "candidate-pair-validation", "concurrent-480k-cpu", "postrestart72-480k"}:
                        # Cancel only proven resource violations, never missing
                        # telemetry or a reporting/parser failure. Existing stop
                        # paths run after the transport closes and saves raw data.
                        gpu_low = any(g.get("uuid") in self.active[cid]["manifest"]["gpu_uuids"]
                                      and type(g.get("free_bytes")) is int and g["free_bytes"] < 16 * 1024**3
                                      for g in row.get("gpus", []))
                        available = row.get("host", {}).get("available_bytes")
                        if resource_stop or gpu_low or (type(available) is int and available < 16 * 1024**3):
                            self.active[cid].setdefault("abort_reason", resource_stop or "SKIP_UNSAFE_PLACEMENT")
                            self.active[cid]["cancel_event"].set()
                    evidence = row.get("required_host_demand") or {}
                    demand = evidence.get("required_bytes")
                    if type(demand) is int:
                        p = self.active[cid]["manifest"]["placement"]
                        if demand >= self.demand.get(p, 0):
                            self.demand[p] = demand
                            self.demand_evidence[p] = evidence
                self.emit({"type": "telemetry", "container": cid, "sample": row})
            except Exception:
                with self.lock:
                    if self.armed.get("scope") == "postrestart72-480k":
                        self.safety.setdefault(cid, "HARNESS_FAILURE")
                    else:
                        self.safety[cid] = "HARNESS_FAILURE"
        return {"collection_duration_s": self.clock() - started}

    def monitor(self):
        while not self.stop.is_set():
            self.collect()
            self.stop.wait(1)

    def loaded(self, manifest):
        begin = self.clock()
        remaining = self.host.call("budget").get("remaining_s", 0)
        if remaining <= 0:
            raise RuntimeError("STOP_BUDGET")
        deadline = begin + min(7200, remaining)
        resource = self.host.call("load", manifest_sha256=fixtures.digest(fixtures.canonical(manifest)))
        cid = resource["id"]
        # Observe loader demand before readiness. Host also samples immediately
        # after start, so a fast-ready model cannot produce warm-only caps.
        row = self.host.call("telemetry", id=cid)
        groups = row.get("cgroups", {})
        baseline = groups.get(cid, next(iter(groups.values()), {}))
        with self.lock:
            self.active[cid] = {"manifest": manifest, "baseline": baseline,
                                "template_sha256": None, "phase": "loading", "cancel_event": threading.Event()}
            self.samples[cid] = []
        self.collect()
        self.record()
        while True:
            with self.lock:
                if self.armed.get("scope") in {"g1-only", "glmrepair", "g1-ladder", "glm-decode-diag", "concurrent-g1q1", "candidate-pair-validation", "concurrent-480k-cpu", "postrestart72-480k"} and self.active[cid].get("abort_reason"):
                    raise RuntimeError(self.active[cid]["abort_reason"])
            remaining = min(deadline - self.clock(), self.host.call("budget").get("remaining_s", 0))
            if remaining <= 0:
                raise RuntimeError("STOP_BUDGET")
            proof = self.host.call("readiness", id=cid, timeout_s=remaining)
            with self.lock:
                if self.armed.get("scope") in {"g1-only", "glmrepair", "g1-ladder", "glm-decode-diag", "concurrent-g1q1", "candidate-pair-validation", "concurrent-480k-cpu", "postrestart72-480k"} and self.active[cid].get("abort_reason"):
                    raise RuntimeError(self.active[cid]["abort_reason"])
            if self.clock() >= deadline:
                raise RuntimeError("STOP_BUDGET")
            if proof.get("ready"):
                break
            if proof.get("failed"):
                raise RuntimeError("STOP_OOM" if proof.get("status", proof.get("state")) == "STOP_OOM" else "STOP_ALLOCATION_FAILURE")
            self.collect()
            self.record()
            self.sleep(min(1, max(0, deadline - self.clock())))
        if proof.get("allocation", {}).get("status") != "ALLOCATION_PROOF_ACCEPTED":
            raise RuntimeError("STOP_ALLOCATION_PROOF")
        ready = self.host.call("quiescent", id=cid, point="readiness")
        if self.armed.get("scope") in {"g1-only", "glmrepair", "g1-ladder", "glm-decode-diag", "concurrent-g1q1", "candidate-pair-validation", "concurrent-480k-cpu", "postrestart72-480k"}:
            current = ready.get("telemetry") or {}
            available = current.get("host", {}).get("available_bytes")
            free = {g.get("uuid"): g.get("free_bytes") for g in current.get("gpus", [])}
            with self.lock:
                if self.active[cid].get("abort_reason"):
                    raise RuntimeError(self.active[cid]["abort_reason"])
                if not (type(available) is int and available >= 16 * 1024**3 and
                        all(type(free.get(u)) is int and free[u] >= 16 * 1024**3 for u in manifest["gpu_uuids"])):
                    raise RuntimeError("SKIP_UNSAFE_PLACEMENT")
        with self.lock:
            self.active[cid].update(template_sha256=proof.get("template_sha256"), phase="ready")
        self.emit({"type": "load", "placement": manifest["placement"], "capacity": manifest["configured_capacity"],
                   "client_load_seconds": self.clock() - begin, "readiness": ready, "allocation": proof["allocation"]})
        self.warm(cid, manifest, proof)
        return cid

    def warm(self, cid, manifest, proof):
        # Warmup has a different seed AND prefix from every measured fixture.
        warm, counted = fixtures.warmup_sample("bench-glm-5.3" if manifest["placement"].startswith("G") else "bench-qwen3.8-27b",
                                              manifest["configured_capacity"], "warmup-prefix-" + str(time.time_ns()), self.counter(cid))
        warmed = self.request(cid, fixtures.serialize_validate(warm), "warmup-" + str(time.time_ns()), timed=False)
        if not warmed.get("parsed") or warmed["parsed"]["status"] not in ("COMPLETE", "OUTPUT_LIMIT") or warmed["summary"]["status"] not in ("COMPLETE", "OUTPUT_LIMIT"):
            raise RuntimeError("HARNESS_FAILURE_WARMUP")
        from .warmup import prefill_proof
        counters = warmed["parsed"]["counters"]
        prefill = prefill_proof(counters, manifest, proof)
        self.emit({"type": "warm_idle", "container": cid, "count": counted,
                   "evaluated_prompt_tokens": counters.get("evaluated_prompt_tokens"), "prefill_proof": prefill,
                   "checkpoint": self.host.call("quiescent", id=cid, point="warm_idle"), "warmup_timing": "discarded"})
        self.collect()
        self.record()

    def retire_all(self):
        for cid in list(self.active):
            self.host.call("retire", id=cid)
            del self.active[cid]

    def admission(self, cid, maximum=7200):
        with self.lock:
            if cid in self.safety:
                raise RuntimeError(self.safety[cid])
        return self.host.call("request_begin", id=cid, timeout_s=maximum).get("timeout_s", 0)

    def request(self, cid, raw, identifier, *, timed=True):
        timeout = self.admission(cid)
        if not 0 < timeout <= 7200:
            raise RuntimeError("STOP_BUDGET")
        manifest = self.active[cid]["manifest"]
        url = "http://127.0.0.1:" + str(manifest["transport"]["port"])
        try:
            options = {"cancel_event": self.active[cid]["cancel_event"]} if self.armed.get("scope") in {"g1-only", "glmrepair", "g1-ladder", "glm-decode-diag", "concurrent-g1q1", "candidate-pair-validation", "concurrent-480k-cpu", "postrestart72-480k"} else {}
            result = client.run_request(raw, self.transport_factory(url, self.key, **options), sample_id=identifier,
                                      private_dir=self.private, summary_path=self.state / ("samples.jsonl" if timed else "warmups.jsonl"), timeout=timeout,
                                      clock=self.clock)
            if self.active[cid].get("abort_reason"):
                reason = self.active[cid]["abort_reason"]
                self.emit({"type": "request_resource_stop", "container": cid, "status": reason,
                           "sample_id": identifier, "raw_summary": result["summary"],
                           "semantics": "resource event cancels HTTP; partial response saved; owned stop/restoration follows request_end"})
                raise RuntimeError(reason)
            return result
        finally:
            self.host.call("request_end", id=cid)

    def counter(self, cid):
        manifest = self.active[cid]["manifest"]
        model = "bench-glm-5.3" if manifest["placement"].startswith("G") else "bench-qwen3.8-27b"
        def call(route, body):
            timeout = self.admission(cid, 120)
            if not 0 < timeout <= 120:
                raise RuntimeError("STOP_BUDGET")
            try:
                return self.json_factory("http://127.0.0.1:" + str(manifest["transport"]["port"]), self.key, timeout=timeout)(route, body)
            finally:
                self.host.call("request_end", id=cid)
        return accounting.native_counter(model, manifest["configured_capacity"], call,
                                         qwen_template_sha256=self.active[cid]["template_sha256"], scope=self.armed.get("scope") if self.armed.get("scope") in {"glm-decode-diag", "concurrent-g1q1", "candidate-pair-validation", "concurrent-480k-cpu", "postrestart72-480k"} else None)

    def prepare_trial(self, cid, identifier, kind="retrieval", output_cap=256, fixture_key=None):
        """Count/freeze exact bytes separately, before mixed arrival clocks start."""
        started = self.clock()
        manifest = self.active[cid]["manifest"]
        model = "bench-glm-5.3" if manifest["placement"].startswith("G") else "bench-qwen3.8-27b"
        capacity = manifest["configured_capacity"]
        key = fixture_key or f"{model}-{capacity}-{kind}"
        seed = hashlib.sha256(key.encode()).hexdigest()[:24]
        nonce = "trial-" + hashlib.sha256((identifier + str(time.time_ns())).encode()).hexdigest()[:28]
        counter = self.counter(cid)
        with self.lock:
            frozen = self.fixture_cache.get(key)
        if self.armed.get("scope") == "q1-only" and capacity in (4096, 16384) and not frozen:
            raise RuntimeError("q1_requires_saved_matched_fixture")
        if frozen:
            sample, counted = fixtures.matched_sample(frozen, nonce, counter, capacity)
        else:
            sample, counted = fixtures.fit_sample(model, capacity, seed, nonce, counter, kind=kind, output_cap=output_cap)
            with self.lock:
                self.fixture_cache[key] = sample
                save(self.private / "fixtures.json", self.fixture_cache)
        raw = fixtures.serialize_validate(sample)
        ended = self.clock()
        prepared = {"sample": sample, "count": counted, "raw": raw, "placement": manifest["placement"],
                    "capacity": capacity, "template_sha256": self.active[cid]["template_sha256"],
                    "preparation_seconds": ended - started,
                    "preparation_telemetry": self.telemetry_window(cid, started, ended, "fixture_fitting_counting")}
        self.emit({"type": "fixture_preparation", "id": identifier, "count": counted,
                   "fixture_sha256": sample["fixture_sha256"], "preparation_seconds": prepared["preparation_seconds"],
                   "telemetry": prepared["preparation_telemetry"],
                   "included_in_mixed_schedule": False})
        return prepared

    def telemetry_window(self, cid, started, ended, scope):
        """Same worker clock as the client; never replace a missing interval."""
        window = {"scope": scope, "started_monotonic_s": started, "ended_monotonic_s": ended,
                  "clock": "worker_monotonic"}
        if type(started) not in (int, float) or type(ended) not in (int, float) or ended <= started:
            return {**window, "status": "UNAVAILABLE", "reason": "missing_or_nonpositive_interval"}
        with self.lock:
            rows = list(self.samples.get(cid, []))
        return {**telemetry.summarize_samples(rows, started, ended), **window,
                "status": "SAMPLED" if any(started <= row["timestamp_monotonic_s"] <= ended for row in rows) else "UNAVAILABLE"}

    def trial(self, cid, identifier, kind="retrieval", output_cap=256, fixture_key=None, prepared=None):
        with self.lock:
            if identifier in self.progress["completed"]:
                return self.progress["completed"][identifier]
            if identifier in self.progress["inflight"]:
                raise RuntimeError("interrupted_trial_requires_explicit_recovery_not_retry")
            self.progress["inflight"][identifier] = {"container": cid, "kind": kind}
            self.record()
        started = self.clock()
        manifest = self.active[cid]["manifest"]
        capacity = manifest["configured_capacity"]
        result = {"type": "trial", "id": identifier, "placement": manifest["placement"], "capacity": capacity, "kind": kind}
        try:
            prepared = prepared or self.prepare_trial(cid, identifier, kind, output_cap, fixture_key)
            if prepared["placement"] != manifest["placement"] or prepared["capacity"] != capacity or prepared["template_sha256"] != self.active[cid]["template_sha256"]:
                raise RuntimeError("prepared_runtime_identity_changed")
            sample, counted = prepared["sample"], prepared["count"]
            # Exact serialization was validated before schedule; bind the frozen
            # bytes without a fresh tokenize request in the timed dispatcher.
            if fixtures.digest(prepared["raw"]) != counted["body_sha256"]:
                raise RuntimeError("prepared_body_changed")
            result.update(fixture_sha256=sample["fixture_sha256"], count=counted,
                          fixture_preparation_seconds=prepared["preparation_seconds"],
                          fixture_preparation_telemetry=prepared.get("preparation_telemetry"))
            response = self.request(cid, prepared["raw"], identifier)
            result["sample"] = response["summary"]
            parsed = response["parsed"]
            if not parsed or response["summary"]["status"] not in ("COMPLETE", "OUTPUT_LIMIT"):
                result["status"] = response["summary"].get("status", "HARNESS_FAILURE")
            elif kind == "tool" and parsed.get("message", {}).get("tool_calls"):
                workspace = self.private / (identifier + "-tool")
                workspace.mkdir(mode=0o700)
                body, tool = fixtures.execute_tool(sample, parsed["message"], workspace)
                raw, continued_count = fixtures.validate_continuation(body, self.counter(cid), capacity)
                second = self.request(cid, raw, identifier + "-continuation")
                result.update(tool=tool, continuation_count=continued_count, continuation=second["summary"])
                if second["summary"]["status"] not in ("COMPLETE", "OUTPUT_LIMIT"):
                    second["parsed"] = None
                result["status"] = (fixtures.score_retrieval(sample, second["parsed"]["message"])["status"]
                                    if second["parsed"] and second["parsed"]["status"] == "COMPLETE" else "OUTPUT_LIMIT" if second["parsed"] else "HARNESS_FAILURE")
            elif parsed["status"] == "OUTPUT_LIMIT":
                result["status"] = "OUTPUT_LIMIT"
            else:
                result["status"] = fixtures.score_retrieval(sample, parsed["message"])["status"]
            output = (parsed or {}).get("counters", {}).get("completion_tokens")
            result["sample_limitations"] = ["output_shorter_than_requested_cap"] if type(output) is int and output < output_cap else []
        except Exception as error:
            code = str(error)
            safe = code if code in {"STOP_BUDGET", "STOP_OOM", "STOP_SUSTAINED_MODEL_SWAP_GROWTH", "SKIP_UNSAFE_PLACEMENT"} else "HARNESS_FAILURE"
            result["status"] = self.safety.get(cid, safe)
        result["client_total_seconds"] = self.clock() - started
        result["client_total_scope"] = "trial_orchestration_including_any_fixture_preparation_and_reporting"
        for field, output in (("sample", "telemetry"), ("continuation", "continuation_telemetry")):
            summary = result.get(field, {})
            if summary:
                result[output] = self.telemetry_window(cid, summary.get("request_started_monotonic_s"),
                                                      summary.get("request_ended_monotonic_s"),
                                                      "inference_transport_dispatch_to_drain")
        if cid in self.safety:
            result["safety_status"] = self.safety[cid]
            result["status"] = self.safety[cid]
        self.emit(result)
        with self.lock:
            self.progress["completed"][identifier] = result
            del self.progress["inflight"][identifier]
            self.record()
        return result

    def cases(self, manifest):
        p, n = manifest["placement"], manifest["configured_capacity"]
        cases = [(f"{p}-{n}-retrieval", "retrieval", 256)]
        if n == 16384:
            cases += [(f"{p}-{n}-anchor", "retrieval", 256), (f"{p}-{n}-generation", "generation", 512)]
            if self.armed.get("scope", "full") == "full":
                cases += [(f"{p}-{n}-tool", "tool", 256)]
        return cases

    def reviewed_generation_framing(self, identity, row):
        return (self.armed.get("scope") == "q1-only"
                and self.armed.get("q1_generation_framing") == Q1_GENERATION_FRAMING
                and identity == Q1_GENERATION_FRAMING["case"]
                and row.get("status") == "HARNESS_FAILURE"
                and fixtures.digest(fixtures.canonical(row)) == Q1_GENERATION_FRAMING["failed_row_sha256"])

    def run(self, *, resume=False):
        scope = profiles.validate_arm_scope(self.armed)
        if scope != "full" and not resume:
            raise RuntimeError("q1_requires_explicit_resume")
        if self.progress["inflight"]:
            raise RuntimeError("inflight_samples_require_restore_and_explicit_review")
        completed = self.progress["completed"]
        if any(row.get("status") not in {"PASS", "OUTPUT_LIMIT", "COMPLETE"}
               and not self.reviewed_generation_framing(identity, row) for identity, row in completed.items()):
            raise RuntimeError("failed_measurement_requires_review_no_automatic_resume")
        if any(mode not in completed and any(key.startswith(mode + "-") for key in completed) for mode in ("mixed-A", "mixed-B")):
            raise RuntimeError("partial_mixed_timing_requires_new_reviewed_campaign")
        if any(group.get("state") != "COMPLETE" for group in self.progress.get("groups", {}).values()):
            raise RuntimeError("interrupted_or_failed_group_is_missing_measurement")
        self.host.call("begin", resume=resume)
        self.record("RUNNING")
        watcher = threading.Thread(target=self.monitor, daemon=True)
        watcher.start()
        try:
            for manifest in self.armed["manifests"]:
                trials = self.cases(manifest)
                if all(t[0] in self.progress["completed"] for t in trials):
                    continue
                cid = self.loaded(manifest)
                for identity, kind, cap in trials:
                    result = self.trial(cid, identity, kind, cap)
                    if result["status"] not in ("PASS", "OUTPUT_LIMIT"):
                        raise RuntimeError("campaign_stopped_for_review")
                self.retire_all()
            if scope == "full":
                self.mixed()
            self.record("MEASUREMENTS_COMPLETE")
        except Exception as error:
            code = str(error)
            allowed = {"STOP_BUDGET", "STOP_OOM", "STOP_ALLOCATION_FAILURE", "STOP_ALLOCATION_PROOF", "STOP_SUSTAINED_MODEL_SWAP_GROWTH", "SKIP_UNSAFE_PLACEMENT", "HARNESS_FAILURE_WARMUP", "HARNESS_FAILURE_WARMUP_PREFILL_UNPROVED"}
            reason = code if code in allowed else "STOPPED_REVIEW_REQUIRED"
            pending = []
            for manifest in self.armed["manifests"]:
                for identity, _, _ in self.cases(manifest):
                    if identity not in self.progress["completed"]:
                        pending.append(identity)
            self.progress["stop_reason"] = reason
            self.progress["skipped_after_stop"] = pending
            self.emit({"type": "stop", "status": reason, "skipped_trial_ids": pending, "mixed_pending": [x for x in ("mixed-A", "mixed-B") if x not in self.progress["completed"]] if scope == "full" else []})
            self.record("STOPPED_REVIEW_REQUIRED")
            raise
        finally:
            self.stop.set();watcher.join(timeout=10)
            try:
                self.restore()
            except Exception as error:
                self.emit({"type": "restoration_failure", "error_class": type(error).__name__,
                           "measurement_status": self.progress.get("stop_reason", self.progress["phase"])})
                self.record("RECOVERY_REQUIRED")
                raise

    def mixed(self):
        if self.armed.get("scope", "full") != "full":
            raise RuntimeError("mixed_excluded_by_arm_scope")
        plan = self.armed["trial_plan"]["mixed_jobs"]
        for mode in ("A", "B"):
            identity = "mixed-" + mode
            if identity in self.progress["completed"]:
                continue
            self.progress.setdefault("groups", {})[identity] = {"state": "PREPARING", "measurement": "MISSING"}
            self.record()
            self.retire_all()
            prepared = {}
            if mode == "A":
                qmanifest = next(m for m in self.armed["manifests"] if m["placement"] == "Q2" and m["configured_capacity"] == 16384)
                gmanifest = next(m for m in self.armed["manifests"] if m["placement"] == "G2" and m["configured_capacity"] == 65536)
                # Fit/freeze the later GLM job before the arrival clock starts.
                # Retire it, then prepare Qwen and begin A with Qwen ready.
                ids = {"glm": self.loaded(gmanifest)}
                for job in plan:
                    if job["model"] == "glm":
                        prepared[job["id"]] = self.prepare_trial(ids["glm"], identity + "-" + job["id"], fixture_key=job["seed"])
                self.retire_all()
                ids = {"qwen": self.loaded(qmanifest)}
            else:
                admitted = self.host.call("admit_mixed", measured_glm=self.demand.get("G1"), measured_qwen=self.demand.get("Q1"))
                self.emit({"type": "mixed_admission", "group": identity, **admitted})
                gmanifest, qmanifest = admitted["manifests"]
                ids = {"glm": self.loaded(gmanifest), "qwen": self.loaded(qmanifest)}
            for job in plan:
                if job["id"] not in prepared:
                    prepared[job["id"]] = self.prepare_trial(ids[job["model"]], identity + "-" + job["id"], fixture_key=job["seed"])
            def switch():
                # Reload/warmup contributes to the separately reported switch;
                # frozen workload fixture fitting/counting is already complete.
                self.retire_all();ids["glm"] = self.loaded(gmanifest)
            jobs = [{**j, "fixture_sha256": prepared[j["id"]]["sample"]["fixture_sha256"]} for j in plan]
            self.progress["groups"][identity] = {"state": "DISPATCHING", "measurement": "MISSING", "fixture_hashes": {j["id"]: j["fixture_sha256"] for j in jobs}}
            self.record()
            result = workload.execute_mixed(jobs, mode, lambda j: self.trial(ids[j["model"]], identity + "-" + j["id"], prepared=prepared[j["id"]]), switch)
            result["fixture_preparation_seconds"] = sum(p["preparation_seconds"] for p in prepared.values())
            result["timing_basis"] = "client_dispatch_and_drain; workload_fixture_fitting_counting_excluded; A_switch_includes_reload_and_discarded_warmup"
            self.emit({"type": "mixed", **result})
            self.progress["completed"][identity] = result
            self.progress["groups"][identity].update(state="COMPLETE" if result["status"] == "COMPLETE" else "FAILED", measurement="COMPLETE" if result["status"] == "COMPLETE" else "MISSING")
            self.record()
            if result["status"] != "COMPLETE":
                raise RuntimeError("mixed_incomplete")

    def restore(self):
        started = self.clock()
        result = self.host.call("restore")
        self.emit({"type": "restoration", "client_seconds": self.clock() - started, "result": result})
        self.record("RESTORED_PENDING_WORKER_VERIFICATION")
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("arm", "run", "restore", "status"))
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--campaign", default="benchrun-20260919")
    parser.add_argument("--scope", choices=profiles.ARM_SCOPES, help="arm only; default full; continuation scopes retain an existing execution epoch")
    parser.add_argument("--reviewed-arm-sha256")
    parser.add_argument("--inference-key-file", type=Path)
    parser.add_argument("--control-key-file", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if args.action == "arm":
        print(json.dumps({"arm_sha256": arm(args.state, args.campaign, args.scope or "full"), "run_started": False}));return 0
    if args.scope is not None:
        parser.error("--scope is arm-only; run uses the reviewed arm scope")
    if args.action == "status":
        print((args.state / "progress.json").read_text());return 0
    armed = load_arm(args.state, args.reviewed_arm_sha256)
    if args.action == "run":
        if armed.get("scope", "full") != "full" and not args.resume:
            parser.error("continuation scopes require --resume within the original campaign budget")
        run_preflight(armed.get("scope", "full"))
    if os.geteuid() == 0:
        parser.error("worker runner must execute as ordinary user")
    if args.inference_key_file is None or args.control_key_file is None:
        parser.error("existing protected worker key files are required; values never enter argv or logs")
    from runtime.sglang38_file_auth import read_key
    key, control_key = read_key(args.inference_key_file), read_key(args.control_key_file)
    if args.action == "run":
        execution_path = args.state / "execution.json"
        if execution_path.exists():
            execution = json.loads(execution_path.read_bytes())
        else:
            execution = {"start_epoch": time.time(), "clock": "UTC_wall_seconds_first_staging_maintenance"}
            save(execution_path, execution)
        armed = {**armed, "runtime": execution}
    host = SSHHost(armed, stage=args.action == "run")
    campaign = Campaign(args.state, armed, host, key)
    try:
        measurement_error = None
        if args.action == "run":
            try:
                campaign.run(resume=args.resume)
            except Exception as error:
                measurement_error = type(error).__name__
                if host.call("status").get("phase") != "POST_RELEASE_LAN_VERIFICATION_PENDING":
                    raise RuntimeError("campaign_stopped_explicit_restore_required") from None
        else:
            host.call("recover")
            campaign.record("RESTORED_PENDING_WORKER_VERIFICATION")
        # Concrete independent worker-LAN proof is required before finalization.
        from .worker_verify import verify
        try:
            receipt = verify(host.call("status"), key, control_key)
            result = host.call("verify_restoration", receipt=receipt)
        except Exception as error:
            campaign.emit({"type": "worker_restoration_verification_failure", "error_class": type(error).__name__,
                           "measurement_error_class": measurement_error, "local_restoration": "PENDING_INDEPENDENT_VERIFICATION"})
            campaign.record("RESTORATION_VERIFICATION_FAILED")
            raise
        campaign.emit({"type": "worker_restoration_verification", "result": result})
        campaign.record("RESTORED")
        if measurement_error:
            campaign.emit({"type": "measurement_stop", "error_class": measurement_error, "restoration_verified": True})
            return 1
    finally:
        host.close()
    return 0
