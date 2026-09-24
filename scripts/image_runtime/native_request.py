#!/usr/bin/env python3
"""One fixed worker-only Qwen-Image request with private, exclusive evidence.

The root-owned service caller creates /work/evidence/RUN_ID for its service UID.
This helper has no public ingress, path override, retry, or recovery operation.
Successful decoding is transport evidence; visual acceptance is a separate step.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import http.client
import io
import json
import math
import os
import re
import signal
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image


EVIDENCE_ROOT = Path("/work/evidence")
HOST = "127.0.0.1"
PORT = 30007
TIMEOUT_SECONDS = 840
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_PNG_BYTES = 32 * 1024 * 1024
RUN_ID_RE = re.compile(r"[0-9a-f]{32}\Z")
PROMPTS = {
    "generation": (
        "A red ceramic teapot on a wooden table beside a window, "
        "softly lit by daylight."
    ),
    "edit": (
        "Change the red teapot to blue, keeping its shape, table, window, "
        "and lighting unchanged."
    ),
}


class EvidenceError(Exception):
    """A fixed diagnostic safe to include in the small summary."""


class RequestDeadline(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def open_run_directory(run_id: str) -> int:
    """Anchor every directory component and refuse symlinks, including ancestors."""
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in (*EVIDENCE_ROOT.parts[1:], run_id):
            next_fd = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=fd,
            )
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or info.st_mode & stat.S_IWOTH:
            raise EvidenceError("Run directory ownership or permissions are invalid")
        return fd
    except BaseException:
        os.close(fd)
        raise


def ensure_absent(directory_fd: int, names: list[str]) -> None:
    for name in names:
        try:
            os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            continue
        raise EvidenceError("An attempt artifact already exists; refusing another request")


def create_file(directory_fd: int, name: str):
    fd = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600, dir_fd=directory_fd,
    )
    return os.fdopen(fd, "wb")


def write_exclusive(directory_fd: int, name: str, content: bytes) -> None:
    with create_file(directory_fd, name) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def read_owned_file(directory_fd: int, name: str, limit: int) -> bytes:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory_fd)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise EvidenceError("Input evidence must be a regular file with one link")
        if info.st_uid != os.geteuid() or info.st_size > limit:
            raise EvidenceError("Input evidence ownership or size is invalid")
        data = handle.read(limit + 1)
        if len(data) > limit:
            raise EvidenceError("Input evidence exceeds its fixed byte limit")
        return data


def inspect_png(content: bytes) -> dict:
    if not content or len(content) > MAX_PNG_BYTES:
        raise EvidenceError("PNG is empty or exceeds its fixed byte limit")
    with Image.open(io.BytesIO(content)) as image:
        if image.format != "PNG" or image.size != (1024, 1024):
            raise EvidenceError("Output must be a PNG with exact dimensions 1024x1024")
        if getattr(image, "n_frames", 1) != 1:
            raise EvidenceError("Output must contain exactly one PNG frame")
        image.load()
        return {
            "format": image.format,
            "mode": image.mode,
            "width": image.width,
            "height": image.height,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "fully_decoded": True,
        }


def payload(mode: str, run_id: str) -> dict:
    result = {
        "model": "qwen-image-2.1",
        "prompt": PROMPTS[mode],
        "n": 1,
        "size": "1024x1024",
        "num_inference_steps": 40,
        "guidance_scale": 1.0,
        "true_cfg_scale": 1.0,
        "seed": 42,
        "generator_device": "cpu",
        "output_format": "png",
        "response_format": "b64_json",
        "enable_teacache": False,
        "perf_dump_path": f"/work/evidence/{run_id}/{mode}-perf.json",
    }
    if mode == "generation":
        result["enable_cache_dit"] = False
    return result


def multipart(fields: dict, content: bytes, run_id: str) -> tuple[bytes, str]:
    boundary = "image21-" + run_id
    marker = boundary.encode()
    if marker in content:
        raise EvidenceError("Fixed multipart boundary collides with input bytes")
    pieces = []
    for name, value in fields.items():
        text = str(value).lower() if isinstance(value, bool) else str(value)
        pieces.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{text}\r\n".encode()
        )
    pieces.extend([
        f'--{boundary}\r\nContent-Disposition: form-data; name="image"; '
        'filename="generation.png"\r\nContent-Type: image/png\r\n\r\n'.encode(),
        content,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    return b"".join(pieces), f"multipart/form-data; boundary={boundary}"


@contextlib.contextmanager
def request_deadline():
    def expired(_signum, _frame):
        raise RequestDeadline()

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, TIMEOUT_SECONDS)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def numeric_metric(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isfinite(value) and value >= 0:
            return value
    return None


def execute(mode: str, run_id: str) -> tuple[dict, int]:
    if mode not in PROMPTS or not RUN_ID_RE.fullmatch(run_id):
        raise EvidenceError("Invalid internal mode or run identifier")
    directory_fd = open_run_directory(run_id)
    started = time.monotonic()
    summary = {
        "schema_version": 1, "mode": mode, "run_id": run_id,
        "started_utc": utc_now(), "status": "failed",
        "scope": "native_transport_and_decode_only", "visual_verification": "NOT_TESTED",
        "http_call_count": 0, "timeout_seconds": TIMEOUT_SECONDS,
        "response_bytes": 0,
        "native_perf": {"filename": f"{mode}-perf.json", "available": False},
    }
    artifacts = [f"{mode}-{suffix}" for suffix in (
        "request.json", "response.json", "summary.json", "perf.json",
    )] + [f"{mode}.png"]
    can_write_summary = False
    stage = "precondition"
    try:
        ensure_absent(directory_fd, artifacts)
        can_write_summary = True
        fields = payload(mode, run_id)
        summary["settings"] = fields
        if mode == "edit":
            source = read_owned_file(directory_fd, "generation.png", MAX_PNG_BYTES)
            source_info = inspect_png(source)
            accepted = json.loads(read_owned_file(directory_fd, "generation-summary.json", 65536))
            if (
                accepted.get("status") != "pass"
                or accepted.get("run_id") != run_id
                or accepted.get("mode") != "generation"
                or accepted.get("output", {}).get("sha256") != source_info["sha256"]
            ):
                raise EvidenceError("Reference is not the accepted decoded generation for this run")
            body, content_type = multipart(fields, source, run_id)
            receipt = {
                "form_fields": fields, "image_field": "image",
                "input_filename": "generation.png", "input": source_info,
                "multipart_boundary": "image21-" + run_id,
            }
            summary["input"] = source_info
            request_bytes = json_bytes(receipt)
        else:
            body = request_bytes = json_bytes(fields)
            content_type = "application/json"
        write_exclusive(directory_fd, f"{mode}-request.json", request_bytes)
        summary["request_body_sha256"] = hashlib.sha256(body).hexdigest()
        summary["request_body_bytes"] = len(body)
        endpoint = "/v1/images/generations" if mode == "generation" else "/v1/images/edits"
        stage = "http"
        connection = http.client.HTTPConnection(HOST, PORT, timeout=TIMEOUT_SECONDS)
        request_started = time.monotonic()
        try:
            with create_file(directory_fd, f"{mode}-response.json") as response_file:
                with request_deadline():
                    summary["http_call_count"] = 1
                    connection.request("POST", endpoint, body=body, headers={
                        "Content-Type": content_type, "Accept": "application/json",
                    })
                    response = connection.getresponse()
                    summary["http_status"] = response.status
                    chunks = []
                    while True:
                        chunk = response.read(min(65536, MAX_RESPONSE_BYTES + 1 - summary["response_bytes"]))
                        if not chunk:
                            break
                        response_file.write(chunk)
                        response_file.flush()
                        chunks.append(chunk)
                        summary["response_bytes"] += len(chunk)
                        if summary["response_bytes"] > MAX_RESPONSE_BYTES:
                            raise EvidenceError("Native response exceeds its fixed byte limit")
                    os.fsync(response_file.fileno())
        finally:
            connection.close()
            summary["http_elapsed_seconds"] = round(time.monotonic() - request_started, 6)
        if not 200 <= summary["http_status"] < 300:
            raise EvidenceError("Native backend returned a non-success HTTP status")
        stage = "response_decode"
        result = json.loads(b"".join(chunks))
        if not isinstance(result, dict) or not isinstance(result.get("data"), list) or len(result["data"]) != 1:
            raise EvidenceError("Native response must contain exactly one image")
        item = result["data"][0]
        if not isinstance(item, dict) or not isinstance(item.get("b64_json"), str):
            raise EvidenceError("Native response lacks one base64 image")
        decoded = base64.b64decode(item["b64_json"], validate=True)
        stage = "png_decode"
        summary["output"] = inspect_png(decoded)
        write_exclusive(directory_fd, f"{mode}.png", decoded)
        summary["native_peak_reserved_mib"] = numeric_metric(result.get("peak_memory_mb"))
        summary["native_inference_seconds"] = numeric_metric(result.get("inference_time_s"))
        summary["status"] = "pass"
    except Exception as error:
        summary["error"] = {"stage": stage, "type": type(error).__name__}
        if isinstance(error, EvidenceError):
            summary["error"]["message"] = str(error)
        elif isinstance(error, RequestDeadline):
            summary["error"]["message"] = "Fixed native request deadline expired; no retry issued"
        else:
            summary["error"]["message"] = "Request failed; retained private artifacts contain diagnostics"
    finally:
        summary["finished_utc"] = utc_now()
        summary["total_elapsed_seconds"] = round(time.monotonic() - started, 6)
        if can_write_summary:
            try:
                try:
                    perf = read_owned_file(directory_fd, f"{mode}-perf.json", 8 * 1024 * 1024)
                    summary["native_perf"].update({
                        "available": True, "bytes": len(perf),
                        "sha256": hashlib.sha256(perf).hexdigest(),
                    })
                except FileNotFoundError:
                    pass
                except Exception as error:
                    summary["native_perf"]["error_type"] = type(error).__name__
                write_exclusive(directory_fd, f"{mode}-summary.json", json_bytes(summary))
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        else:
            os.close(directory_fd)
    return summary, 0 if summary["status"] == "pass" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=tuple(PROMPTS))
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not RUN_ID_RE.fullmatch(args.run_id):
        parser.error("--run-id must contain exactly 32 lowercase hexadecimal characters")
    try:
        summary, result = execute(args.mode, args.run_id)
    except Exception as error:
        summary = {"status": "failed", "error": {"stage": "setup", "type": type(error).__name__}}
        result = 1
    print(json.dumps(summary, sort_keys=True, allow_nan=False))
    return result


if __name__ == "__main__":
    sys.exit(main())
