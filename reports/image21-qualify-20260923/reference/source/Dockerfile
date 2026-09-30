FROM sha256:dafbccb763cff6a6aa3777c7c0a8cc185d838bd4b9f61bec8007f57f2c7233f8
LABEL io.llm-reference.owner="IMAGE21-REFERENCE-20260923" \
      org.opencontainers.image.revision="8b3c707ebd3ec4881f4190cf42931da07eaf3b65"
ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
RUN mkdir -p /opt/reference-receipts /opt/diffusers-src \
    && git -C /opt/diffusers-src init \
    && git -C /opt/diffusers-src remote add origin https://github.com/huggingface/diffusers.git \
    && git -C /opt/diffusers-src fetch --depth=1 origin 8b3c707ebd3ec4881f4190cf42931da07eaf3b65 \
    && git -C /opt/diffusers-src checkout --detach FETCH_HEAD \
    && test "$(git -C /opt/diffusers-src rev-parse HEAD)" = 8b3c707ebd3ec4881f4190cf42931da07eaf3b65 \
    && git -C /opt/diffusers-src ls-tree -r HEAD > /opt/reference-receipts/diffusers-tree.txt
RUN python -m pip uninstall -y sglang \
    && python -m pip install --no-build-isolation --report /opt/reference-receipts/pip-install-report.json \
       'transformers==5.17.0' /opt/diffusers-src \
    && python -m pip check \
    && python -c "import torch,transformers; from diffusers import QwenImage21Pipeline; assert torch.__version__=='2.13.0+cu130'; assert transformers.__version__=='5.17.0'" \
    && python -m pip freeze --all > /opt/reference-receipts/requirements.freeze.txt \
    && python -m pip inspect > /opt/reference-receipts/pip-inspect.json \
    && python --version > /opt/reference-receipts/python-version.txt \
    && dpkg-query -W > /opt/reference-receipts/dpkg-versions.tsv \
    && find /opt/image-venv/lib/python3.12/site-packages -path '*.dist-info/RECORD' -print0 | sort -z | xargs -0 sha256sum > /opt/reference-receipts/distribution-records.sha256
ENTRYPOINT ["/opt/image-venv/bin/python"]
