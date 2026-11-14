# Build for wke-ml
# ---
# Service provides:
# - embeddings,
# - clustering,
# - summarization.
#
# Model weights are baked into the image, so pods can start without fetching
# them from Hugging Face.
# ---

# distilbart-cnn-6-6 ships only a pickle pytorch_model.bin upstream;
# builder converts it to safetensors once (see fetch_models.py) so the runtime
# image never touches a pickle and ensures no weight file lands next to it.

# DISABLE_SAFETENSORS_CONVERSION=1 stops transformers from doing its own on-the-fly
# conversion during the fetch step - that would write the stray file.
# fetch_models.py also skips the flax/rust weight files distilbart ships upstream
# and keeps the safetensors conversion in the checkpoint's native fp16, without
# upcasting to fp32 on disk.
#
# The builder strips huggingface_hub's download bookkeeping once the models are
# fetched, and strips build/test-only weight from the venv.
#
# Built for linux/arm64; build under any arch: `docker buildx --platform`.

# Multi-arch index digest
ARG PYTHON_BASE=python:3.13.18-slim-trixie@sha256:76baad6037690d6e8c4397fbcaef17bca6f19eecef822b708fe8fa3417d30bb5

FROM ${PYTHON_BASE} AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 /uv /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

ARG DISTILBART_REV=d2fde4ca
ARG MINILM_REV=1110a243

ENV HF_HOME=/models \
    DISABLE_SAFETENSORS_CONVERSION=1

COPY fetch_models.py ./
RUN MINILM_REV=${MINILM_REV} DISTILBART_REV=${DISTILBART_REV} \
    /app/.venv/bin/python fetch_models.py

# cleanup step, before the runtime
RUN VENV=$(echo /app/.venv/lib/python3.*/site-packages); \
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

LABEL org.opencontainers.image.source="https://github.com/straightchlorine/wke"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.title="wke-ml"
LABEL org.opencontainers.image.description="Wikipedia Knowledge Explorer - ML inference service (embeddings, clustering, summarization)"

# drop the base image pip; the venv is uv-managed
RUN rm -rf /usr/local/lib/python3.*/site-packages/pip* /usr/local/bin/pip*

RUN groupadd -r --gid 10001 wkeml \
    && useradd -r --uid 10001 --gid 10001 -d /home/wkeml -m wkeml

WORKDIR /app

# copy files from the builder stage - venv and models
COPY --from=builder --chown=wkeml:wkeml /app/.venv /app/.venv
COPY --from=builder --chown=wkeml:wkeml /models /models
# The model weights are Apache-2.0; their licence ships with them.
COPY --chown=wkeml:wkeml licenses/ /models/licenses/
COPY --chown=wkeml:wkeml src/ ./src/

# set up the environment
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

# start-period for the model load
HEALTHCHECK --interval=30s --timeout=3s --start-period=180s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]

CMD ["python", "-m", "uvicorn", "wke_ml.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
