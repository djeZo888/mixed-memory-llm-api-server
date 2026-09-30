FROM nvidia/cuda@sha256:a85c9f5af049f0ab679c1669ae6fa8393022886739af7361e85bb96878e8cdd4
LABEL org.opencontainers.image.source="https://github.com/sgl-project/sglang" \
      org.opencontainers.image.revision="0cd8be351d0825488f4b81c8931167bbab618eca" \
      io.llm-image.owner="IMAGE21-RUNTIME-20260923"
ENV DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1 \
    SGLANG_BUILD_RUST_EXTS=none TORCH_CUDA_ARCH_LIST=8.9 MAX_JOBS=8
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3.12-dev build-essential git ninja-build \
    cmake pkg-config libnuma1 libgomp1 libgl1 libglib2.0-0 ffmpeg ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN python3.12 -m venv /opt/image-venv
ENV PATH="/opt/image-venv/bin:${PATH}"
RUN python -m pip install pip==26.2.1 setuptools==84.0.0 setuptools-rust==1.13.0 \
    setuptools-scm==10.2.3 wheel==0.48.0
RUN python -m pip install torch==2.13.0 --extra-index-url https://download.pytorch.org/whl/cu130
COPY upstream /opt/sglang-src
RUN test "$(git -C /opt/sglang-src rev-parse HEAD)" = 0cd8be351d0825488f4b81c8931167bbab618eca \
    && mkdir -p /opt/image-receipts \
    && python -m pip wheel --no-deps --no-build-isolation --wheel-dir /opt/image-wheels /opt/sglang-src/python \
    && python -m pip install --verbose \
       --extra-index-url https://download.pytorch.org/whl/cu130 \
       --report /opt/image-receipts/pip-install-report.json \
       --find-links /opt/image-wheels 'sglang[diffusion]==0.0.0.dev1+g0cd8be351'
RUN python -m pip check \
    && python -m pip freeze --all > /opt/image-receipts/requirements.freeze.txt \
    && python -m pip inspect > /opt/image-receipts/pip-inspect.json \
    && dpkg-query -W > /opt/image-receipts/dpkg-versions.tsv \
    && python --version > /opt/image-receipts/python-version.txt \
    && sglang serve --model-type diffusion --help > /opt/image-receipts/native-help.txt
WORKDIR /work
ENTRYPOINT ["sglang", "serve", "--model-type", "diffusion"]
