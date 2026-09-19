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


def source_files():
    paths = set()
    for group in ("scripts/benchmark", "scripts/agent", "scripts/d3t", "scripts/runtime"):
        paths.update(profiles.ROOT.joinpath(group).glob("*.py"))
    paths.add(profiles.ROOT / "scripts/bench/benchmark-host.py")
    paths.add(profiles.CONFIG)
    paths.update(profiles.ROOT / name for name in profiles.read_config()["source_pins"])
    return {str(p.relative_to(profiles.ROOT)): p.read_bytes() for p in sorted(paths)}


def arm(state, campaign):
    state = Path(state)
    if not re.fullmatch(r"benchrun-[a-z0-9-]{1,32}", campaign):
        raise ValueError("invalid_campaign")
    if (state / "arm.json").exists():
        raise ValueError("arm_exists_preserve_existing_campaign")
    files = source_files()
    manifests = [profiles.command_manifest(p, n, campaign=campaign) for p in ("Q2", "Q1", "G2", "G1") for n in (4096, 16384, 65536)]
    value = {"schema": 1, "campaign": campaign, "source_files": {p: hashlib.sha256(b).hexdigest() for p, b in files.items()},
             "manifests": manifests, "trial_plan": profiles.trial_order(),
             "phase": "ARMED_OFFLINE_NOT_STARTED", "host": "ai-vm", "private_lan": "10.156.100.60"}
    save(state / "arm.json", value)
    save(state / "progress.json", {"phase": "ARMED", "completed": {}, "inflight": {}, "errors": []})
    return fixtures.digest(fixtures.canonical(value))


def load_arm(state, reviewed):
    value = json.loads((Path(state) / "arm.json").read_bytes())
    if fixtures.digest(fixtures.canonical(value)) != reviewed:
        raise ValueError("root_reviewed_arm_hash_mismatch")
    if {p: hashlib.sha256(b).hexdigest() for p, b in source_files().items()} != value["source_files"]:
        raise ValueError("armed_source_changed")
    return value


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
                       "files": {p: base64.b64encode(b).decode() for p, b in source_files().items()}}
            result = run(["ssh", "-T", "-o", "BatchMode=yes", "ai-vm", shlex.join(["sudo", "-n", "python3", "-I", "-B", "-c", STAGE])],
                         input=fixtures.canonical(payload), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
            if result.returncode or json.loads(result.stdout).get("staged") is not True:
                raise ValueError("guarded_source_stage_failed")
        argv = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
                "-L", "127.0.0.1:31002:127.0.0.1:31002", "-L", "127.0.0.1:31004:127.0.0.1:31004",
                "ai-vm", shlex.join(self.command)]
        self.process = popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)

    def call(self, op, **args):
        with self.lock:
            self.process.stdin.write(json.dumps({"op": op, **args}, separators=(",", ":")) + "\n")
            self.process.stdin.flush()
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError("host_session_lost_explicit_recovery_required")
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
        self.demand = dict(self.progress.get("measured_demand_bytes", {}))
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
                    if not set(self.active[cid]["manifest"]["gpu_uuids"]).issubset({g.get("uuid") for g in row.get("gpus", [])}):
                        verdict = "SKIP_UNSAFE_PLACEMENT"
                    if any(g.get("uuid") in self.active[cid]["manifest"]["gpu_uuids"] and (g.get("free_bytes") is None or g["free_bytes"] < 16 * 1024**3) for g in row.get("gpus", [])):
                        verdict = "SKIP_UNSAFE_PLACEMENT"
                    if row.get("host", {}).get("available_bytes") is None or row["host"]["available_bytes"] < 16 * 1024**3:
                        verdict = "SKIP_UNSAFE_PLACEMENT"
                    if verdict.startswith(("STOP_", "SKIP_")):
                        self.safety[cid] = verdict
                    demand = group.get("current_bytes")
                    if type(demand) is int:
                        p = self.active[cid]["manifest"]["placement"]
                        self.demand[p] = max(self.demand.get(p, 0), demand)
                self.emit({"type": "telemetry", "container": cid, "sample": row})
            except Exception:
                with self.lock:
                    self.safety[cid] = "HARNESS_FAILURE"
        return {"collection_duration_s": self.clock() - started}

    def monitor(self):
        while not self.stop.is_set():
            self.collect()
            self.stop.wait(1)

    def loaded(self, manifest):
        begin = self.clock()
        resource = self.host.call("load", manifest_sha256=fixtures.digest(fixtures.canonical(manifest)))
        cid = resource["id"]
        while True:
            proof = self.host.call("readiness", id=cid)
            if proof.get("ready"):
                break
            if proof.get("failed") or self.clock() - begin >= 7200:
                raise RuntimeError("STOP_ALLOCATION_FAILURE")
            budget = self.host.call("budget")
            if budget.get("remaining_s", 0) <= 0:
                raise RuntimeError("STOP_BUDGET")
            self.sleep(2)
        if proof.get("allocation", {}).get("status") != "ALLOCATION_PROOF_ACCEPTED":
            raise RuntimeError("STOP_ALLOCATION_PROOF")
        ready = self.host.call("quiescent", id=cid, point="readiness")
        row = self.host.call("telemetry", id=cid)
        groups = row.get("cgroups", {})
        baseline = groups.get(cid, next(iter(groups.values()), {}))
        self.active[cid] = {"manifest": manifest, "baseline": baseline, "template_sha256": proof.get("template_sha256")}
        self.samples[cid] = []
        self.emit({"type": "load", "placement": manifest["placement"], "capacity": manifest["configured_capacity"],
                   "client_load_seconds": self.clock() - begin, "readiness": ready, "allocation": proof["allocation"]})
        # Warmup has a different seed AND prefix from every measured fixture.
        warm = fixtures.build_sample("bench-glm-5.3" if manifest["placement"].startswith("G") else "bench-qwen3.8-27b",
                                     12, "warmup-only-seed", "warmup-prefix-" + str(time.time_ns()))
        warmed = self.request(cid, fixtures.serialize_validate(warm), "warmup-" + str(time.time_ns()), timed=False)
        if not warmed.get("parsed") or warmed["parsed"]["status"] not in ("COMPLETE", "OUTPUT_LIMIT") or warmed["summary"]["status"] not in ("COMPLETE", "OUTPUT_LIMIT"):
            raise RuntimeError("HARNESS_FAILURE_WARMUP")
        self.emit({"type": "warm_idle", "container": cid, "checkpoint": self.host.call("quiescent", id=cid, point="warm_idle"), "warmup_timing": "discarded"})
        return cid

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
            return client.run_request(raw, self.transport_factory(url, self.key), sample_id=identifier,
                                      private_dir=self.private, summary_path=self.state / ("samples.jsonl" if timed else "warmups.jsonl"), timeout=timeout)
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
                                         qwen_template_sha256=self.active[cid]["template_sha256"])

    def trial(self, cid, identifier, kind="retrieval", output_cap=256, fixture_key=None):
        with self.lock:
            if identifier in self.progress["completed"]:
                return self.progress["completed"][identifier]
            if identifier in self.progress["inflight"]:
                raise RuntimeError("interrupted_trial_requires_explicit_recovery_not_retry")
            self.progress["inflight"][identifier] = {"container": cid, "kind": kind}
            self.record()
        started = self.clock()
        manifest = self.active[cid]["manifest"]
        model = "bench-glm-5.3" if manifest["placement"].startswith("G") else "bench-qwen3.8-27b"
        capacity = manifest["configured_capacity"]
        key = fixture_key or f"{model}-{capacity}-{kind}"
        seed = hashlib.sha256(key.encode()).hexdigest()[:24]
        nonce = "trial-" + hashlib.sha256((identifier + str(time.time_ns())).encode()).hexdigest()[:28]
        counter = self.counter(cid)
        result = {"type": "trial", "id": identifier, "placement": manifest["placement"], "capacity": capacity, "kind": kind}
        try:
            with self.lock:
                frozen = self.fixture_cache.get(key)
            if frozen:
                sample, counted = fixtures.matched_sample(frozen, nonce, counter, capacity)
            else:
                sample, counted = fixtures.fit_sample(model, capacity, seed, nonce, counter, kind=kind, output_cap=output_cap)
                with self.lock:
                    self.fixture_cache[key] = sample
                    save(self.private / "fixtures.json", self.fixture_cache)
            result.update(fixture_sha256=sample["fixture_sha256"], count=counted)
            response = self.request(cid, fixtures.serialize_validate(sample), identifier)
            result["sample"] = response["summary"]
            parsed = response["parsed"]
            if not parsed or response["summary"]["status"] not in ("COMPLETE", "OUTPUT_LIMIT"):
                result["status"] = response["summary"].get("status", "HARNESS_FAILURE")
            elif kind == "tool" and parsed.get("message", {}).get("tool_calls"):
                workspace = self.private / (identifier + "-tool")
                workspace.mkdir(mode=0o700)
                body, tool = fixtures.execute_tool(sample, parsed["message"], workspace)
                raw, continued_count = fixtures.validate_continuation(body, counter, capacity)
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
        with self.lock:
            rows = list(self.samples.get(cid, []))
        if rows and result["client_total_seconds"] > 0:
            result["telemetry"] = telemetry.summarize_samples(rows, started, self.clock())
        if cid in self.safety:
            result["safety_status"] = self.safety[cid]
            result["status"] = self.safety[cid]
        self.emit(result)
        with self.lock:
            self.progress["completed"][identifier] = result
            del self.progress["inflight"][identifier]
            self.record()
        return result

    def run(self, *, resume=False):
        if self.progress["inflight"]:
            raise RuntimeError("inflight_samples_require_restore_and_explicit_review")
        completed = self.progress["completed"]
        if any(row.get("status") not in {"PASS", "OUTPUT_LIMIT", "COMPLETE"} for row in completed.values()):
            raise RuntimeError("failed_measurement_requires_review_no_automatic_resume")
        if any(mode not in completed and any(key.startswith(mode + "-") for key in completed) for mode in ("mixed-A", "mixed-B")):
            raise RuntimeError("partial_mixed_timing_requires_new_reviewed_campaign")
        self.host.call("begin", resume=resume)
        self.record("RUNNING")
        watcher = threading.Thread(target=self.monitor, daemon=True)
        watcher.start()
        try:
            for manifest in self.armed["manifests"]:
                p, n = manifest["placement"], manifest["configured_capacity"]
                trials = [(f"{p}-{n}-retrieval", "retrieval", 256)]
                if n == 16384:
                    trials += [(f"{p}-{n}-anchor", "retrieval", 256), (f"{p}-{n}-generation", "generation", 512), (f"{p}-{n}-tool", "tool", 256)]
                if all(t[0] in self.progress["completed"] for t in trials):
                    continue
                cid = self.loaded(manifest)
                for identity, kind, cap in trials:
                    result = self.trial(cid, identity, kind, cap)
                    if result["status"] not in ("PASS", "OUTPUT_LIMIT"):
                        raise RuntimeError("campaign_stopped_for_review")
                self.retire_all()
            self.mixed()
            self.record("MEASUREMENTS_COMPLETE")
        except Exception as error:
            code = str(error)
            allowed = {"STOP_BUDGET", "STOP_OOM", "STOP_ALLOCATION_FAILURE", "STOP_ALLOCATION_PROOF", "STOP_SUSTAINED_MODEL_SWAP_GROWTH", "SKIP_UNSAFE_PLACEMENT", "HARNESS_FAILURE_WARMUP"}
            reason = code if code in allowed else "STOPPED_REVIEW_REQUIRED"
            pending = []
            for manifest in self.armed["manifests"]:
                p, n = manifest["placement"], manifest["configured_capacity"]
                for case in (["retrieval", "anchor", "generation", "tool"] if n == 16384 else ["retrieval"]):
                    identity = f"{p}-{n}-{case}"
                    if identity not in self.progress["completed"]:
                        pending.append(identity)
            self.progress["stop_reason"] = reason
            self.progress["skipped_after_stop"] = pending
            self.emit({"type": "stop", "status": reason, "skipped_trial_ids": pending, "mixed_pending": [x for x in ("mixed-A", "mixed-B") if x not in self.progress["completed"]]})
            self.record("STOPPED_REVIEW_REQUIRED")
            raise
        finally:
            self.stop.set();watcher.join(timeout=10)
            self.restore()

    def mixed(self):
        plan = self.armed["trial_plan"]["mixed_jobs"]
        for mode in ("A", "B"):
            identity = "mixed-" + mode
            if identity in self.progress["completed"]:
                continue
            self.retire_all()
            if mode == "A":
                qmanifest = next(m for m in self.armed["manifests"] if m["placement"] == "Q2" and m["configured_capacity"] == 16384)
                gmanifest = next(m for m in self.armed["manifests"] if m["placement"] == "G2" and m["configured_capacity"] == 65536)
                ids = {"qwen": self.loaded(qmanifest)}
            else:
                admitted = self.host.call("admit_mixed", measured_glm=self.demand.get("G1"), measured_qwen=self.demand.get("Q1"))
                gmanifest, qmanifest = admitted["manifests"]
                ids = {"glm": self.loaded(gmanifest), "qwen": self.loaded(qmanifest)}
            def switch():
                self.retire_all();ids["glm"] = self.loaded(gmanifest)
            jobs = [{**j, "fixture_sha256": hashlib.sha256(j["seed"].encode()).hexdigest()} for j in plan]
            # The dispatcher identities above bind the deterministic source seeds;
            # actual fitted archive hashes are in each incremental trial record.
            result = workload.execute_mixed(jobs, mode, lambda j: self.trial(ids[j["model"]], identity + "-" + j["id"], fixture_key=j["seed"]), switch)
            self.emit({"type": "mixed", **result})
            self.progress["completed"][identity] = result;self.record()
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
    parser.add_argument("--reviewed-arm-sha256")
    parser.add_argument("--inference-key-file", type=Path)
    parser.add_argument("--control-key-file", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if args.action == "arm":
        print(json.dumps({"arm_sha256": arm(args.state, args.campaign), "run_started": False}));return 0
    if args.action == "status":
        print((args.state / "progress.json").read_text());return 0
    armed = load_arm(args.state, args.reviewed_arm_sha256)
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
        receipt = verify(host.call("status"), key, control_key)
        result = host.call("verify_restoration", receipt=receipt)
        campaign.emit({"type": "worker_restoration_verification", "result": result})
        campaign.record("RESTORED")
        if measurement_error:
            campaign.emit({"type": "measurement_stop", "error_class": measurement_error, "restoration_verified": True})
            return 1
    finally:
        host.close()
    return 0
