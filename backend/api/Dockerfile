# syntax=docker/dockerfile:1

FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY README.md ./
RUN uv sync --frozen --no-dev


FROM python:3.13-slim AS runtime

# Drop the base image pip; the venv is uv-managed and nothing calls pip at runtime.
RUN rm -rf /usr/local/lib/python3.13/site-packages/pip* /usr/local/bin/pip*

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
