# Build context: clean pinned llama.cpp Git checkout (including .git).
# See scripts/d1/build-runtime.sh; host toolchain/daemon configuration is unchanged.
ARG CUDA_DEVEL=nvidia/cuda:13.2.1-devel-ubuntu24.04@sha256:0e1f7b8e96fa9ec5e36d4709a38c62df7b5665977446081811c12b8234d874bf
ARG CUDA_RUNTIME=nvidia/cuda:13.2.1-runtime-ubuntu24.04@sha256:285c50be684df76df5cd0e3162687e74b7b67add47134ff55075e3a9cfa94044
FROM ${CUDA_DEVEL} AS build
ARG UBUNTU_SNAPSHOT=20260914T000000Z
# Immutable Ubuntu snapshot prevents build dependencies drifting between rebuilds.
RUN rm -f /etc/apt/sources.list /etc/apt/sources.list.d/* && \
    printf 'deb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/%s noble main universe\ndeb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/%s noble-updates main universe\ndeb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/%s noble-security main universe\n' "$UBUNTU_SNAPSHOT" "$UBUNTU_SNAPSHOT" "$UBUNTU_SNAPSHOT" > /etc/apt/sources.list && \
    apt-get update && apt-get install -y --no-install-recommends build-essential cmake ninja-build git libssl-dev ca-certificates && \
    rm -rf /var/lib/apt/lists/*
ARG LLAMA_COMMIT=7ac59a6e3ad851cd41af00f678effab0598ba9a8
ARG CUDA_ARCHITECTURES=120a-real
ARG BUILD_JOBS=8
ENV CC=gcc CXX=g++ CUDAHOSTCXX=g++
WORKDIR /src
COPY . .
RUN test "$(git rev-parse HEAD)" = "$LLAMA_COMMIT" && test -z "$(git status --porcelain)" && \
    cmake -S . -B /build -G Ninja -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCHITECTURES" -DGGML_CUDA=ON \
      -DGGML_NATIVE=OFF -DGGML_BACKEND_DL=ON -DGGML_CPU_ALL_VARIANTS=ON \
      -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_APP=OFF \
      -DLLAMA_BUILD_UI=OFF -DLLAMA_USE_PREBUILT_UI=OFF \
      -DCMAKE_EXE_LINKER_FLAGS=-Wl,--allow-shlib-undefined && \
    timeout --signal=TERM --kill-after=30s 4800 cmake --build /build --target llama-server --parallel "$BUILD_JOBS" && \
    mkdir -p /out && cp /build/bin/llama-server /out/ && \
    find /build -name '*.so*' -exec cp -P {} /out/ \; && \
    cp /build/CMakeCache.txt /out/CMakeCache.txt && \
    dpkg-query -W > /out/build-packages.tsv && \
    nvcc --version > /out/nvcc-version.txt && \
    cp LICENSE /out/llama-LICENSE && \
    git rev-parse HEAD > /out/source-commit.txt
FROM ${CUDA_RUNTIME} AS runtime
ARG UBUNTU_SNAPSHOT=20260914T000000Z
RUN rm -f /etc/apt/sources.list /etc/apt/sources.list.d/* && \
    printf 'deb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/%s noble main universe\ndeb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/%s noble-updates main universe\ndeb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/%s noble-security main universe\n' "$UBUNTU_SNAPSHOT" "$UBUNTU_SNAPSHOT" "$UBUNTU_SNAPSHOT" > /etc/apt/sources.list && \
    apt-get update && apt-get install -y --no-install-recommends libgomp1 libssl3t64 ca-certificates && \
    rm -rf /var/lib/apt/lists/*
ARG LLAMA_COMMIT=7ac59a6e3ad851cd41af00f678effab0598ba9a8
LABEL org.opencontainers.image.source="https://github.com/ggml-org/llama.cpp" \
      org.opencontainers.image.revision="$LLAMA_COMMIT" \
      org.opencontainers.image.version="h014-7ac59a6" \
      local.h014.cuda.architectures="120a-real"
COPY --from=build /out/ /opt/llama/
ENV LD_LIBRARY_PATH=/opt/llama LLAMA_ARG_HOST=127.0.0.1
WORKDIR /opt/llama
ENTRYPOINT ["/opt/llama/llama-server"]
CMD ["--help"]
