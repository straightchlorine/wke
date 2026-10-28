# Multi-stage build for wke-ml (embeddings, clustering, summarization).
#
# Model weights are pre-baked into the image so pods boot without
# reaching Hugging Face at start-up. distilbart-cnn-6-6 ships only a
# pickle pytorch_model.bin upstream; the builder converts it to
# safetensors once (save_pretrained(safe_serialization=True)) so the
# runtime image never touches a pickle and no second 460 MB weight
# file lands next to it. DISABLE_SAFETENSORS_CONVERSION=1 stops
# transformers from doing its own on-the-fly conversion during the
# fetch step, which would otherwise write that stray file first.
# fetch_models.py also skips the flax/rust weight files distilbart
# ships upstream and keeps the safetensors conversion in the
# checkpoint's native fp16, rather than upcasting to fp32 on disk.
#
# The builder strips huggingface_hub's download bookkeeping (lock
# files, negative-lookup markers, xet transfer staging) once the
# models are fetched, and strips build/test-only weight from the
# venv: torch's own C++ test binaries and extension-build headers,
# every package's __pycache__ and test suite, and pip/setuptools
# (uv manages the venv directly, so neither is needed at runtime).
# None of this ships in the final image; none of it runs at runtime.
#
# Built for linux/arm64 (OCI A1.Flex); the file itself is
# platform-agnostic and builds under any `docker buildx --platform`.

ARG PYTHON_BASE=python:3.13-slim

FROM ${PYTHON_BASE} AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

ARG DISTILBART_REV=d2fde4ca
ARG MINILM_REV=1110a243

ENV HF_HOME=/models \
    DISABLE_SAFETENSORS_CONVERSION=1

COPY fetch_models.py ./
RUN --mount=type=cache,target=/root/.cache/uv \
    MINILM_REV=${MINILM_REV} DISTILBART_REV=${DISTILBART_REV} \
    /app/.venv/bin/python fetch_models.py

RUN VENV=/app/.venv/lib/python3.13/site-packages; \
    rm -rf /models/hub/.locks /models/xet; \
    find /models/hub -depth -type d -name .no_exist -exec rm -rf {} +; \
    rm -rf "$VENV/torch/test" "$VENV/torch/include"; \
    find "$VENV/torch/bin" -mindepth 1 -not -name torch_shm_manager \
        -exec rm -rf {} +; \
    rm -rf "$VENV"/pip "$VENV"/pip-*.dist-info \
           "$VENV"/setuptools "$VENV"/setuptools-*.dist-info \
           "$VENV"/pkg_resources; \
    find /app/.venv \( -name '__pycache__' -o -name tests \) -type d \
        -exec rm -rf {} +

FROM ${PYTHON_BASE} AS runtime

LABEL org.opencontainers.image.source="https://github.com/straightchlorine/wikipedia-knowledge-explorer"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.title="wke-ml"
LABEL org.opencontainers.image.description="Wikipedia Knowledge Explorer - ML inference service (embeddings, clustering, summarization)"

# Drop the base image pip (vendors msgpack 1.1.2, GHSA-6v7p-g79w-8964); the venv is
# uv-managed and nothing calls pip at runtime.
RUN rm -rf /usr/local/lib/python3.13/site-packages/pip* /usr/local/bin/pip*

RUN groupadd -r --gid 10001 wkeml \
    && useradd -r --uid 10001 --gid 10001 -d /home/wkeml -m wkeml

WORKDIR /app

COPY --from=builder --chown=wkeml:wkeml /app/.venv /app/.venv
COPY --from=builder --chown=wkeml:wkeml /models /models
COPY --chown=wkeml:wkeml src/ ./src/
COPY --chown=wkeml:wkeml bench/ ./bench/

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    HF_HOME=/models \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TRANSFORMERS_VERBOSITY=error \
    HF_HUB_DISABLE_PROGRESS_BARS=1 \
    OMP_NUM_THREADS=2 \
    TOKENIZERS_PARALLELISM=false

USER wkeml

EXPOSE 8000

# start-period matches the k8s startupProbe window (36 x 5s) for the model load.
HEALTHCHECK --interval=30s --timeout=3s --start-period=180s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]

CMD ["python", "-m", "uvicorn", "wke_ml.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
