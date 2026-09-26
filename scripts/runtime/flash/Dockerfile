FROM pytorch/pytorch@sha256:39236c0ad9c66baecf01bb2e4f5562543c5b336c0c785887798775d6d6fdbf9a
ENV DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 TORCH_CUDA_ARCH_LIST="12.0" CUDA_MODULE_LOADING=LAZY
RUN python --version && python -c "import sys; assert sys.version_info[:2] == (3,11)"
RUN apt-get update && apt-get install -y --no-install-recommends libnuma1 numactl && rm -rf /var/lib/apt/lists/*
COPY flash-primary-requirements.txt /opt/flash-primary-requirements.txt
COPY flash-build-pins.json /opt/flash-build-pins.json
RUN python -m pip install --report /opt/flash-dependency-report.json -r /opt/flash-primary-requirements.txt && python -m pip freeze --all > /opt/flash-dependencies.freeze
RUN python -c "import torch,sglang,kt_kernel; print(torch.__version__,torch.version.cuda); assert torch.version.cuda == '12.8'; assert 'sm_120' in torch._C._cuda_getArchFlags(); print(torch._C._cuda_getArchFlags())" && python -m pip check
WORKDIR /service
