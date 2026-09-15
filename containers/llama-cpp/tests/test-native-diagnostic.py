#!/usr/bin/env python3
"""Check the fixed D3T native source contract without loading a model.

Run: python3 containers/llama-cpp/tests/test-native-diagnostic.py SOURCE
This checks source confinement and record bindings; it is not kernel profiling.
"""
import argparse
from pathlib import Path
import re
import subprocess


BASE = "b29c606e28a01b1bc8c1351026a0fa6e616bf6c4"
FILE = "src/llama-context.cpp"
GUARD = "if (model.arch == LLM_ARCH_GLM_DSA) {"
TOKEN = r'"(?:\\.|[^"\\])*"|[A-Za-z_]\w*|\S'
CALLS = [
    r'''LLAMA_LOG_WARN("D3T_NATIVE_V1 kind=graph n_ctx=%" PRIu32 " n_ctx_seq=%" PRIu32
        " n_seq_max=%" PRIu32 " n_batch=%" PRIu32 " n_ubatch=%" PRIu32
        " flash_attn=%d fused_lid=%d lid_nodes=%zu fa_nodes=%zu no_alloc=%d\n",
        cparams.n_ctx, cparams.n_ctx_seq, cparams.n_seq_max, cparams.n_batch, cparams.n_ubatch,
        int(cparams.flash_attn), int(cparams.fused_lid), lid_nodes, fa_nodes, int(model.hparams.no_alloc));''',
    r'''LLAMA_LOG_WARN("D3T_NATIVE_V1 kind=compute backend=%s bytes=%zu\n",
        ggml_backend_buft_name(buft), backend_buf_exp_size[i]);''',
    r'''LLAMA_LOG_WARN("D3T_NATIVE_V1 kind=cache backend=%s bytes=%zu\n",
        ggml_backend_buft_name(buft_size.first), buft_size.second);''',
    r'''LLAMA_LOG_WARN("D3T_NATIVE_V1 kind=end\n");''',
]


def require(condition, message):
    if not condition:
        raise SystemExit("FAIL: " + message)


def tokens(text):
    # Preserve whitespace inside record literals, ignore source formatting.
    return re.findall(TOKEN, text)


def check(source):
    original = subprocess.check_output(
        ["git", "-C", str(source), "show", f"{BASE}:{FILE}"], text=True)
    current = (source / FILE).read_text()
    start = current.index("void llama_context::sched_reserve() {")
    end = current.index("\nvoid llama_context::synchronize()", start)
    function = current[start:end]
    spans = []
    blocks = []
    for match in re.finditer(re.escape(GUARD), function):
        depth = 0
        stop = None
        for token in re.finditer(TOKEN, function[match.start():]):
            if token.group() == "{":
                depth += 1
            elif token.group() == "}":
                depth -= 1
                if depth == 0:
                    stop = match.start() + token.end()
                    break
        require(stop is not None, "unclosed GLM diagnostic guard")
        blocks.append(function[match.start():stop])
        left = function.rfind("\n", 0, match.start()) + 1
        right = stop + 1  # closing brace newline
        if function[right:right + 1] == "\n":
            right += 1
        spans.append((left, right))
    require(len(blocks) == 3, "expected only three GLM diagnostic blocks")
    restored = function
    for left, right in reversed(spans):
        restored = restored[:left] + restored[right:]
    require(current[:start] + restored + current[end:] == original,
            "source changes exceed additive GLM guards in sched_reserve")

    calls = re.findall(r"LLAMA_LOG_WARN\(.*?\);", "\n".join(blocks), re.S)
    require([tokens(call) for call in calls] == [tokens(call) for call in CALLS],
            "record grammar, warning level, order or actual value bindings changed")
    require(current.count("D3T_NATIVE_V1") == 4, "unexpected diagnostic records")
    graph, compute, cache = blocks
    for statement in (
        "size_t lid_nodes = 0;", "size_t fa_nodes = 0;",
        "for (const auto & node : get_gf_res_reserve()->get_fused_nodes()) {",
        "lid_nodes += node.op == LLM_FUSED_OP_LIGHTNING_INDEXER;",
        "fa_nodes += node.op == LLM_FUSED_OP_FLASH_ATTN;",
    ):
        require(" ".join(tokens(statement)) in " ".join(tokens(graph)),
                "selected final graph node counting changed")
    require(function[:spans[0][0]].rstrip().endswith(
        'throw std::runtime_error("failed to allocate compute pp buffers");\n        }\n    }'),
        "graph diagnostic must follow final successful prompt reserve")
    require(function[:spans[1][0]].rstrip().endswith(
        "backend_buf_exp_size[i] = ggml_backend_sched_get_buffer_size(sched.get(), backend);\n        }"),
        "compute diagnostic must follow the existing exact-size assignment")
    require(function[spans[2][1]:].startswith("    if (n_nodes_pp == n_nodes_tg) {"),
            "cache diagnostics must follow the existing backend loop")
    require("if (memory) {" in cache and
            "for (const auto & buft_size : memory->memory_breakdown()) {" in cache,
            "cache diagnostics must use the existing optional memory breakdown")
    require(cache.rstrip().endswith(CALLS[3] + "\n    }"),
            "end delimiter must be outside the optional memory block")
    print("PASS: additive sched_reserve-only GLM guards; fixed warning grammar and actual selected values; complete group delimiter")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Verified combined upstream checkout")
    check(parser.parse_args().source)


if __name__ == "__main__":
    main()
