"""Actual arrival dispatcher with injected request/switch functions; no networking.

Timing begins with Qwen ready (A) or both ready (B). Loaded-configuration warmup
and initial load cost are separate. Restoration is owned by CampaignOwner.
"""
from concurrent.futures import ThreadPoolExecutor
import threading
import time

from .campaign import mixed_schedule


def execute_mixed(jobs, mode, run_job, switch_to_glm, *, clock=time.monotonic, sleep=time.sleep):
    """One GLM task and four serial Qwen tasks, never blind retry or cancel.

    run_job checks owner/budget/fixture/count gates and persists each raw sample.
    It returns its sanitized verdict after draining inference. If a Qwen job
    fails, its lane stops admitting new work; an already healthy GLM request is
    still allowed to drain. Switching must use the active campaign owner.
    """
    mixed_schedule(jobs, {j["id"]: 0 for j in jobs}, mode)
    qwen = sorted((j for j in jobs if j["model"] == "qwen"), key=lambda j: j["arrival_s"])
    glm = next(j for j in jobs if j["model"] == "glm")
    started = clock()
    rows, errors = [], []
    mutex = threading.Lock()

    def one(job):
        sleep(max(0, started + job["arrival_s"] - clock()))
        begin = clock()
        try:
            result = run_job(job)
            if not isinstance(result, dict) or result.get("status") not in ("PASS", "HARNESS_FAILURE", "MODEL_INCORRECT", "OUTPUT_LIMIT", "TRANSPORT_FAILURE", "STOP_BUDGET"):
                raise ValueError("job_not_accepted")
            state = result["status"]
            if state != "PASS":
                with mutex:
                    errors.append({"id": job["id"], "state": state})
        except Exception:
            with mutex:
                errors.append({"id": job["id"], "state": "STOP_LANE_REVIEW_PRIVATE_SAMPLE"})
            state = "STOP_LANE_REVIEW_PRIVATE_SAMPLE"
        end = clock()
        row = {**job, "start_s": begin - started, "end_s": end - started,
               "queue_delay_s": begin - started - job["arrival_s"],
               "latency_s": end - started - job["arrival_s"], "service_s": end - begin,
               "status": state}
        with mutex:
            rows.append(row)
        return state == "PASS"

    def qlane():
        for job in qwen:
            if not one(job):
                break

    switch_seconds = 0
    if mode == "B":
        # Exactly one Qwen lane and one GLM lane. Joining both does not cancel
        # a healthy request in response to a parser/other-lane failure.
        with ThreadPoolExecutor(max_workers=2) as pool:
            q = pool.submit(qlane)
            g = pool.submit(one, glm)
            q.result()
            g.result()
    else:
        qlane()
        if not errors:
            begin = clock()
            switch_to_glm()
            switch_seconds = clock() - begin
            one(glm)
    completed = {r["id"] for r in rows}
    return {"mode": mode, "timing_basis": "actual_client_dispatch_timestamps", "timeline": rows,
            "makespan_s": max((r["end_s"] for r in rows), default=0) - min(j["arrival_s"] for j in jobs),
            "switch_seconds": switch_seconds, "return_to_original_model_seconds": None,
            "errors": errors, "skipped_ids": [j["id"] for j in jobs if j["id"] not in completed],
            "status": "COMPLETE" if not errors else "INCOMPLETE_REVIEW_REQUIRED",
            "score": "makespan_and_each_model_latency; no sum of unlike token rates"}
