"""Final authenticated worker-LAN checks; no control mutation or credential output."""
import hashlib
import http.client
import json
import socket
import threading
import time

from .fixtures import canonical


def fetch(port, path, key, payload=None):
    conn = http.client.HTTPConnection("10.156.100.60", port, timeout=60)
    timer = None
    try:
        conn.connect()
        sock = conn.sock
        def expire():
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        timer = threading.Timer(60, expire);timer.daemon = True;timer.start()
        conn.request("GET" if payload is None else "POST", path, body=None if payload is None else canonical(payload),
                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "Accept-Encoding": "identity"})
        response = conn.getresponse();raw = response.read(1024 * 1024 + 1)
        if response.status != 200 or len(raw) > 1024 * 1024 or key.encode() in raw:
            raise ValueError("worker_lan_verification_failed")
        return json.loads(raw)
    except Exception:
        raise ValueError("worker_lan_verification_failed") from None
    finally:
        if timer:
            timer.cancel()
        conn.close()


def verify(status, inference_key, control_key, *, call=fetch):
    original = status["original"]
    state = original["manager"]
    nonce = status["nonce"]
    if not isinstance(nonce, str) or len(nonce) < 16:
        raise ValueError("fresh_host_verification_nonce_required")
    control_expected = original["services"]["llm-control.service"]["active"] == "active"
    control = "NOT_APPLICABLE_CONTROL_INACTIVE"
    if control_expected:
        result = call(30000, "/control/v1/status", control_key)
        # The published control contract exposes these at its top level.
        if result.get("selected") != state["selected"] or result.get("desired") != state["desired"] or result.get("current_operation") is not None:
            raise ValueError("worker_control_original_intent_mismatch")
        if state["desired"] == "running" and result.get("observed") != "ready":
            raise ValueError("worker_control_not_ready")
        control = True
    inference = "NOT_APPLICABLE_STOPPED_INTENT"
    if state["desired"] == "running":
        glm = state["selected"].startswith("glm-")
        alias = "glm-5.3" if glm else "qwen3.8-27b"
        reply = call(30002 if glm else 30004, "/v1/chat/completions", inference_key,
                     {"model": alias, "messages": [{"role": "user", "content": "Reply with OK."}],
                      "stream": False, "max_tokens": 32, "temperature": 0,
                      "reasoning_effort": "low" if glm else "none"})
        if reply.get("model") != alias or not reply.get("choices"):
            raise ValueError("worker_inference_model_or_reply_invalid")
        inference = True
    return {"nonce": nonce, "original_sha256": hashlib.sha256(canonical(original)).hexdigest(),
            "verified_at": time.time(), "checks": {"worker_source": "mac-worker1", "transport": "private_lan",
            "worker_lan_control_authenticated": control, "worker_lan_inference_authenticated": inference}}
