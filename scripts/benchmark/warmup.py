"""Warmup prefill evidence; derived policy proof never becomes a native counter."""
from . import fixtures


def prefill_proof(counters, manifest, readiness, minimum_tokens=2048):
    evaluated = counters.get("evaluated_prompt_tokens")
    prompt, cached = counters.get("prompt_tokens"), counters.get("cached_tokens")
    source = "native_evaluated_prompt_tokens"
    policy = None
    if evaluated is None:
        if type(prompt) is int and type(cached) is int and 0 <= cached <= prompt:
            evaluated, source = prompt - cached, "derived_native_prompt_minus_cached"
        elif (cached is None and type(prompt) is int
              and manifest["placement"].startswith("Q")
              and readiness.get("allocation", {}).get("status") == "ALLOCATION_PROOF_ACCEPTED"
              and readiness.get("observed", {}).get("native_argv") == manifest["native_argv"]
              and manifest["native_argv"].count("--disable-radix-cache") == 1
              and readiness.get("server_facts", {}).get("disable_radix_cache") is True):
            evaluated, source = prompt, "derived_cache_disabled_prompt_tokens"
            policy = {"disable_radix_cache": True,
                      "source": "current_server_args_and_validated_native_argv",
                      "native_argv_sha256": fixtures.digest(fixtures.canonical(manifest["native_argv"]))}
    if (type(evaluated) is not int or evaluated < minimum_tokens
            or type(counters.get("completion_tokens")) is not int
            or counters["completion_tokens"] <= 0):
        raise RuntimeError("HARNESS_FAILURE_WARMUP_PREFILL_UNPROVED")
    return {"prefill_tokens": evaluated, "source": source, "cache_policy": policy,
            "minimum_required_tokens": minimum_tokens,
            "native_evaluated_prompt_tokens": counters.get("evaluated_prompt_tokens"),
            "native_cached_tokens": cached,
            "evidence_scope": "warmup prefill proof; derived values are not native counters"}
