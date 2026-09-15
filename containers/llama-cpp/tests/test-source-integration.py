#!/usr/bin/env python3
"""Verify the exact pinned main call site and unchanged HTTP/model internals."""

import argparse
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Patched exact upstream checkout")
    args = parser.parse_args()
    base = "b29c606e28a01b1bc8c1351026a0fa6e616bf6c4"

    def original(path):
        return subprocess.check_output(
            ["git", "-C", str(args.source), "show", f"{base}:{path}"], text=True
        )

    old_routes = '''    ctx_http.post("/chat/completions",         ex_wrapper(routes.post_chat_completions));
    ctx_http.post("/v1/chat/completions",      ex_wrapper(routes.post_chat_completions));'''
    new_routes = '''    server_chat_register_routes(ctx_http, ex_wrapper(server_chat_model_guard(
        routes.post_chat_completions, is_router_server, child.is_child(),
        [&routes]() { return routes.get_model_info(); })));'''
    upstream = original("tools/server/server.cpp")
    if upstream.count(old_routes) != 1:
        raise SystemExit("FAIL: unexpected pinned chat registration")
    expected = upstream.replace(old_routes, new_routes).replace(
        '#include "server-http.h"',
        '#include "server-http.h"\n#include "server-chat-model.h"',
        1,
    )
    if (args.source / "tools/server/server.cpp").read_text() != expected:
        raise SystemExit("FAIL: main integration or unrelated route/startup code changed")
    for path in ("tools/server/server-http.cpp", "tools/server/server-context.cpp",
                 "tools/server/server-stream.cpp", "tools/server/server-models.cpp",
                 "vendor/cpp-httplib/httplib.cpp"):
        if (args.source / path).read_text() != original(path):
            raise SystemExit(f"FAIL: pinned middleware, downstream or HTTP implementation changed: {path}")
    print("PASS: exact main guard call, cached metadata getter, exception wrapper, route position; HTTP, router, session and model internals unchanged")


if __name__ == "__main__":
    main()
