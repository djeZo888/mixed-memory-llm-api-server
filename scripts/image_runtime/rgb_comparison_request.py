#!/usr/bin/env python3
"""One root-authorized fixed RGB comparison edit; no arguments or retries."""

from __future__ import annotations

import base64
import hashlib
import http.client
import importlib.util
import json
import os
import stat
import sys
import time


RUN_ID = "2088c347bc1e41a9a3e086b20b9be7be"
SUBDIRECTORY = "rgb-comparison"
NATIVE_PATH = "/runtime/native_request.py"


def load_native():
    spec = importlib.util.spec_from_file_location("image21_native_request", NATIVE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Fixed native request module unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execute(native) -> tuple[dict, int]:
    if os.geteuid() != 1000:
        raise native.EvidenceError("Comparison must run as the existing native service UID")
    parent_fd = native.open_run_directory(RUN_ID)
    try:
        directory_fd = os.open(
            SUBDIRECTORY,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
    finally:
        os.close(parent_fd)
    started = time.monotonic()
    summary = {
        "schema_version": 1, "mode": "edit", "run_id": RUN_ID,
        "comparison": "reviewed_api_opaque_rgb_reference",
        "started_utc": native.utc_now(), "status": "failed",
        "scope": "native_transport_and_decode_only", "visual_verification": "NOT_TESTED",
        "http_call_count": 0, "timeout_seconds": 840, "response_bytes": 0,
        "native_perf": {"filename": "edit-perf.json", "available": False},
    }
    can_write_summary = False
    stage = "precondition"
    try:
        info = os.fstat(directory_fd)
        if info.st_uid != 1000 or stat.S_IMODE(info.st_mode) & 0o077:
            raise native.EvidenceError("Comparison directory must be private to the native service UID")
        native.ensure_absent(directory_fd, [
            "edit-request.json", "edit-response.json", "edit-summary.json",
            "edit-perf.json", "edit.png",
        ])
        can_write_summary = True
        if native.TIMEOUT_SECONDS != 840 or native.HOST != "127.0.0.1" or native.PORT != 30007:
            raise native.EvidenceError("Fixed native endpoint or deadline changed")
        source = native.read_owned_file(directory_fd, "normalized-reference.png", native.MAX_PNG_BYTES)
        source_info = native.inspect_png(source)
        if source_info["mode"] != "RGB":
            raise native.EvidenceError("Normalized reference must be fully decoded RGB PNG")
        normalization = native.read_owned_file(directory_fd, "normalization.json", 65536)
        metadata = json.loads(normalization)
        if not isinstance(metadata, dict) or metadata.get("normalized_sha256") != source_info["sha256"]:
            raise native.EvidenceError("Normalization receipt does not match the exact reference bytes")
        summary["input"] = source_info
        summary["normalization_receipt"] = {
            "filename": "normalization.json", "sha256": hashlib.sha256(normalization).hexdigest(),
        }
        fields = native.payload("edit", RUN_ID)
        fields["perf_dump_path"] = f"/work/evidence/{RUN_ID}/{SUBDIRECTORY}/edit-perf.json"
        summary["settings"] = fields
        body, content_type = native.multipart(fields, source, RUN_ID)
        native.write_exclusive(directory_fd, "edit-request.json", native.json_bytes({
            "form_fields": fields, "image_field": "image",
            "input_filename": "normalized-reference.png",
            "multipart_filename": "generation.png", "input": source_info,
            "normalization_receipt": summary["normalization_receipt"],
            "multipart_boundary": "image21-" + RUN_ID,
        }))
        summary["request_body_sha256"] = hashlib.sha256(body).hexdigest()
        summary["request_body_bytes"] = len(body)
        stage = "http"
        connection = http.client.HTTPConnection("127.0.0.1", 30007, timeout=840)
        request_started = time.monotonic()
        try:
            with native.create_file(directory_fd, "edit-response.json") as response_file:
                with native.request_deadline():
                    summary["http_call_count"] = 1
                    connection.request("POST", "/v1/images/edits", body=body, headers={
                        "Content-Type": content_type, "Accept": "application/json",
                    })
                    response = connection.getresponse()
                    summary["http_status"] = response.status
                    chunks = []
                    while True:
                        chunk = response.read(min(65536, native.MAX_RESPONSE_BYTES + 1 - summary["response_bytes"]))
                        if not chunk:
                            break
                        response_file.write(chunk)
                        response_file.flush()
                        chunks.append(chunk)
                        summary["response_bytes"] += len(chunk)
                        if summary["response_bytes"] > native.MAX_RESPONSE_BYTES:
                            raise native.EvidenceError("Native response exceeds its fixed byte limit")
                    os.fsync(response_file.fileno())
        finally:
            connection.close()
            summary["http_elapsed_seconds"] = round(time.monotonic() - request_started, 6)
        if not 200 <= summary["http_status"] < 300:
            raise native.EvidenceError("Native backend returned a non-success HTTP status")
        stage = "response_decode"
        result = json.loads(b"".join(chunks))
        if not isinstance(result, dict) or not isinstance(result.get("data"), list) or len(result["data"]) != 1:
            raise native.EvidenceError("Native response must contain exactly one image")
        item = result["data"][0]
        if not isinstance(item, dict) or not isinstance(item.get("b64_json"), str):
            raise native.EvidenceError("Native response lacks one base64 image")
        decoded = base64.b64decode(item["b64_json"], validate=True)
        stage = "png_decode"
        summary["output"] = native.inspect_png(decoded)
        native.write_exclusive(directory_fd, "edit.png", decoded)
        summary["native_peak_reserved_mib"] = native.numeric_metric(result.get("peak_memory_mb"))
        summary["native_inference_seconds"] = native.numeric_metric(result.get("inference_time_s"))
        summary["status"] = "pass"
    except Exception as error:
        summary["error"] = {"stage": stage, "type": type(error).__name__}
        if isinstance(error, native.EvidenceError):
            summary["error"]["message"] = str(error)
        elif isinstance(error, native.RequestDeadline):
            summary["error"]["message"] = "Fixed native request deadline expired; no retry issued"
        else:
            summary["error"]["message"] = "Comparison failed; retained private artifacts contain diagnostics"
    finally:
        summary["finished_utc"] = native.utc_now()
        summary["total_elapsed_seconds"] = round(time.monotonic() - started, 6)
        try:
            if can_write_summary:
                try:
                    perf = native.read_owned_file(directory_fd, "edit-perf.json", 8 * 1024 * 1024)
                    summary["native_perf"].update({
                        "available": True, "bytes": len(perf),
                        "sha256": hashlib.sha256(perf).hexdigest(),
                    })
                except FileNotFoundError:
                    pass
                except Exception as error:
                    summary["native_perf"]["error_type"] = type(error).__name__
                native.write_exclusive(directory_fd, "edit-summary.json", native.json_bytes(summary))
                os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    return summary, 0 if summary["status"] == "pass" else 1


def main() -> int:
    if len(sys.argv) != 1:
        print(json.dumps({"status": "failed", "error": "This fixed helper accepts no arguments"}))
        return 2
    try:
        summary, result = execute(load_native())
    except Exception as error:
        summary = {"status": "failed", "error": {"stage": "setup", "type": type(error).__name__}}
        result = 1
    print(json.dumps(summary, sort_keys=True, allow_nan=False))
    return result


if __name__ == "__main__":
    sys.exit(main())
