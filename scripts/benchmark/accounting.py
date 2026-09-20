"""Native benchmark template/count adapters; injected protected client only."""
from __future__ import annotations
import re
from agent import protocol
from benchmark.fixtures import (HarnessError, MODELS, CAPACITIES, canonical, digest,
                                CONCURRENT_SCOPE, CONCURRENT_CAPACITIES, CPU_SCOPE, CPU_CAPACITIES)
from benchmark.profiles import GLM_DECODE_DIAG_CAPACITIES


def native_counter(model, capacity, call, *, qwen_template_sha256=None, scope=None):
    """Adapt existing native counting routes through an injected protected client.

    call(path, payload) must enforce current runtime identity/storage/owner gates
    and verify the declared trial capacity from effective allocation/readiness.
    Qwen's template digest comes from BENCHRUN's verified loaded template evidence;
    its tokenize route alone does not expose that identity. No route is called
    until the returned counter is invoked; these are not generation endpoints.
    """
    allowed_capacities = CAPACITIES
    if scope is not None:
        if scope == "candidate-pair-validation" and model in {"glm-5.3", "qwen3.8-27b"}:
            allowed_capacities = (480000,) if model == "glm-5.3" else (700160,)
        elif scope == CPU_SCOPE and model in CPU_CAPACITIES:
            allowed_capacities = CPU_CAPACITIES[model]
        elif scope == CONCURRENT_SCOPE and model in CONCURRENT_CAPACITIES:
            allowed_capacities = CONCURRENT_CAPACITIES[model]
        elif scope == "glm-decode-diag" and model == "bench-glm-5.3":
            allowed_capacities = GLM_DECODE_DIAG_CAPACITIES
        else:
            raise HarnessError("invalid native counting diagnostic scope")
    if (model not in MODELS or type(capacity) is not int or capacity not in allowed_capacities
            or (capacity == 262144 and model != "bench-qwen3.8-27b")):
        raise HarnessError("invalid native counting configuration")
    if model.removeprefix("bench-") == "qwen3.8-27b" and (not isinstance(qwen_template_sha256, str)
                                     or not re.fullmatch(r"[0-9a-f]{64}", qwen_template_sha256)):
        raise HarnessError("verified Qwen template identity is required")

    def count(raw):
        body = protocol.strict_json_loads(raw)
        # Count-only routes do not stream. Preserve every template/sampling field
        # and bind both the final inference body and normalized counting body.
        count_body = {k: v for k, v in body.items() if k not in ("stream", "stream_options")}
        count_transport = {"count_body_sha256": digest(canonical(count_body)),
                           "count_transport_normalization": {
                               "removed_fields": [k for k in ("stream", "stream_options") if k in body]}}
        if body.get("model") != model:
            raise HarnessError("accounting model differs from request")
        if model.removeprefix("bench-") == "glm-5.3":
            props = call("/props", None)
            if (props.get("model_alias") != model or props.get("is_sleeping") is not False
                    or props.get("total_slots") != 1
                    or props.get("default_generation_settings", {}).get("n_ctx") != capacity):
                raise HarnessError("GLM native properties differ from configured trial")
            template = (props.get("chat_template_tool_use", props.get("chat_template"))
                        if body.get("tools") else props.get("chat_template"))
            if not isinstance(template, str) or not template:
                raise HarnessError("loaded native template missing")
            rendered = call("/apply-template", count_body)
            if not isinstance(rendered, dict) or not isinstance(rendered.get("prompt"), str):
                raise HarnessError("native rendering missing")
            reply = call("/tokenize", {"content": rendered["prompt"], "add_special": True,
                                       "parse_special": True, "with_pieces": False})
            source, template_hash = "native_apply_template_tokenize", digest(template.encode())
        else:
            # Native tokenization has no streaming implementation. Preserve all
            # template inputs; only generation transport fields are omitted.
            reply = call("/v1/tokenize", count_body)
            # Pinned route exposes tokenizer metadata, not the allocation/window
            # accepted by this server. Keep it visible without treating it as a
            # trial-capacity proof; RUN verifies actual args/allocation separately.
            if not isinstance(reply, dict) or type(reply.get("max_model_len")) is not int or reply["max_model_len"] <= 0:
                raise HarnessError("native Qwen tokenizer metadata is invalid")
            source, template_hash = "native_chat_tokenize", qwen_template_sha256
        tokens = reply.get("tokens") if isinstance(reply, dict) else None
        if (not isinstance(tokens, list) or not tokens or len(tokens) > 8 * max(131072, capacity)
                or any(type(token) is not int or not 0 <= token < 2**31 for token in tokens)):
            raise HarnessError("native token IDs missing or invalid")
        if model.removeprefix("bench-") == "qwen3.8-27b" and (type(reply.get("count")) is not int or reply["count"] != len(tokens)):
            raise HarnessError("native Qwen count/token IDs disagree")
        return {"source": source, "input_tokens": len(tokens), "body_sha256": digest(raw),
                **count_transport,
                "template_sha256": template_hash, "token_ids_sha256": digest(canonical(tokens)),
                "configured_context": capacity,
                "configured_context_source": "native_props" if model.removeprefix("bench-") == "glm-5.3" else "caller_verified_runtime_allocation",
                "tokenizer_max_model_len": reply.get("max_model_len") if model.removeprefix("bench-") == "qwen3.8-27b" else None}

    return count
