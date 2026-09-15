# D3P focused native worker tests

These tests compile the shipped guard and route registration helper, the pinned
`llama-server-impl` target, and its actual `server-http.cpp` / vendored httplib.
The HTTP fixture listens on an ephemeral `127.0.0.1` port with a public test
credential. It creates no inference context and loads no model.

First prepare and verify the exact patched source using the D3P source helper.
Run from this repository root, with source and build directories outside it:

```sh
cmake -S ../llama-upstream -B ../native-build \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PROJECT_INCLUDE="$PWD/containers/llama-cpp/tests/register-tests.cmake" \
  -DLLAMA_BUILD_COMMON=ON -DLLAMA_BUILD_TOOLS=ON -DLLAMA_BUILD_SERVER=ON \
  -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_APP=OFF \
  -DLLAMA_BUILD_UI=OFF -DLLAMA_USE_PREBUILT_UI=OFF -DLLAMA_OPENSSL=OFF \
  -DGGML_CPU=ON -DGGML_METAL=OFF -DGGML_CUDA=OFF -DGGML_VULKAN=OFF \
  -DGGML_SYCL=OFF -DGGML_HIP=OFF -DGGML_RPC=OFF \
  -DGGML_NATIVE=OFF -DGGML_BLAS=OFF -DGGML_ACCELERATE=OFF
cmake --build ../native-build --target d3p-test-strict-model-chat -j 4
ctest --test-dir ../native-build -R '^d3p-' --output-on-failure --no-tests=error
```

The CMake hook requires CMake 3.19 or newer and preserves upstream's source-root
assumptions. Assertions stay enabled with `NDEBUG`. The integration check uses
Python 3 and Git; it verifies the exact `server.cpp` change, including the cached
metadata getter, exception wrapper, route position and router/child parameters,
and confirms HTTP/model/router/session implementation files are unchanged.

The native matrix covers omitted, canonical and declared secondary IDs; unknown
IDs, whitespace/case/path variants; empty/null/bool/number/array/object values;
invalid JSON and non-object bodies. Both paths run with stream omitted, false
and true, where a top-level stream field is representable. Non-objects cannot
carry a top-level stream field; array cases contain nested stream fields instead.
The same matrix exercises router and child bypass, including a router-valid
alias absent from child metadata. A second metadata fixture checks that the
canonical ID is read dynamically rather than hard-coded.

The fake downstream records generator, wake, template, session and queue entry,
stream delivery and completion callbacks. Rejection must leave every counter
and the existing fake conversation session unchanged. Accepted direct calls
must receive the same request object and return the same response object.
HTTP tests check numeric 400 independently of string/null JSON error code,
nonstream JSON content and headers, unchanged successful JSON/SSE delegation,
readiness before authentication before model validation, OPTIONS bypass and
the exact stock missing-route 404 body.

## Evidence limits

This is a bounded CPU/source test, verified on the Mac worker. It does not
exercise CUDA, Linux containers, TLS, real inference, native model sleep/wake,
real stream-session storage, templates/tokenizers, real router processes, or
production model aliases. Fake counters prove that rejected requests never
enter the downstream handler; unchanged pinned source supplies the link from
that handler to model/session side effects. The separate source integration
check verifies main wiring; the harness does not initialize the server's real
model-owning main function. No unrelated upstream test suites are run.
