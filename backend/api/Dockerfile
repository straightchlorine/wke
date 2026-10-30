# Multi-arch index digest
ARG PYTHON_BASE=python:3.13.18-slim-trixie@sha256:76baad6037690d6e8c4397fbcaef17bca6f19eecef822b708fe8fa3417d30bb5

FROM ${PYTHON_BASE} AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
RUN uv sync --locked --no-dev


FROM ${PYTHON_BASE} AS runtime

LABEL org.opencontainers.image.source="https://github.com/straightchlorine/wke"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.title="wke-api"
LABEL org.opencontainers.image.description="Wikipedia Knowledge Explorer - REST, MCP, job worker, watcher and trending entrypoints"

# dropping the base image pip:
# the venv is uv-managed, nothing calls pip at runtime
RUN rm -rf /usr/local/lib/python3.*/site-packages/pip* /usr/local/bin/pip*

RUN groupadd --gid 10001 wke && \
    useradd --uid 10001 --gid wke --no-create-home --shell /usr/sbin/nologin wke

WORKDIR /app

COPY --from=builder --chown=wke:wke /app/.venv /app/.venv
COPY --from=builder --chown=wke:wke /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER wke

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request as u; u.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('WKE_PORT', '8000'), timeout=2)"]

CMD ["python", "-m", "wke.api"]
