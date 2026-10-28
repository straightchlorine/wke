# wke-ml

FastAPI inference service called by wke-api over HTTP (ADR 0004:
wke-api ships no torch).

- `POST /v1/analyze` -- MiniLM embed, cosine relevance to the lead,
  KMeans clustering, related-article edges. Vectors never leave the pod.
- `POST /v1/summarize` -- abstractive summary via distilbart-cnn-6-6.
- `GET /healthz` (weights resident), `/readyz` (warm-up done),
  `/metrics` (prometheus text exposition).

## Models
| Model | Revision |
|---|---|
| `sentence-transformers/all-MiniLM-L6-v2` | `1110a243` |
| `sshleifer/distilbart-cnn-6-6` | `d2fde4ca` |

Weights are baked into the image (`fetch_models.py`), converted to
safetensors and kept at the checkpoint's native fp16 on disk; the torch
backend casts to fp32 at load (faster than fp16 on CPU). Inference is
serialized to one slot at a time (`asyncio.Semaphore(1)`) behind a
bounded wait queue (`QUEUE_MAX_WAIT`, default 4); once full, or a
queued job's deadline/connection lapses, the caller gets 503 +
`Retry-After`.

## Environment variables (no `.env.example`; all have defaults)
| Var | Default | Meaning |
|---|---|---|
| `WKE_ML_BACKEND` | torch | `torch` (real) or `stub` (deterministic, no torch import) |
| `WKE_ML_EMBED_MODEL` / `_REVISION` | MiniLM-L6-v2 / 1110a243 | Embedding model + pinned revision |
| `WKE_ML_SUMMARIZE_MODEL` / `_REVISION` | distilbart-cnn-6-6 / d2fde4ca | Summarizer + pinned revision |
| `WKE_ML_MAX_INPUT_TOKENS` | 512 | Input truncation cap for summarization |
| `WKE_ML_OMP_NUM_THREADS` | 2 | Torch thread count |
| `WKE_ML_QUEUE_MAX_WAIT` | 4 | Max jobs waiting for the single inference slot |
| `WKE_ML_KMEANS_SEED` | 42 | KMeans random seed |
| `WKE_ML_KMEANS_MAX_K` | 6 | Upper bound on cluster count |
| `WKE_ML_KMEANS_CHUNKS_PER_CLUSTER` | 6 | Used to bound k against chunk count |
| `WKE_ML_EDGE_SIMILARITY_THRESHOLD` | 0.35 | Min cosine similarity for a related-lead edge |
| `WKE_ML_EDGE_TOP_N` | 2 | Max related edges kept |
| `WKE_ML_LOG_LEVEL` | INFO | Python logging level |

## Run locally
```
docker compose -f docker-compose.dev.yml --profile ml up --build
```

or against the host's Hugging Face cache, so weights download once:

```
cd backend/ml && uv sync
uv run uvicorn wke_ml.main:app --host 0.0.0.0 --port 8000
```

`WKE_ML_BACKEND=stub` skips the torch import and download entirely.

## Test
```
cd backend/ml && uv run pytest
```

Every test uses the stub backend by default (`tests/conftest.py` sets
`WKE_ML_BACKEND=stub`), so the suite never imports torch. Real-model
smoke tests are marked `model`, deselected by default; run them with
`uv run pytest -m model`.

Container image: multi-stage `python:3.13-slim` build; `fetch_models.py`
pre-bakes both models (`--build-arg MINILM_REV`/`DISTILBART_REV`); the
builder strips torch's test/build artifacts and pip/setuptools; runtime
is offline (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`) as non-root
`wkeml`. Built for linux/arm64 (OCI A1.Flex). Measured arm64 size:
1413 MB (2026-09-28).

## Bench
`bench/bench.py` times distilbart-cnn-6-6 `generate()` at a 512-token
input, `num_beams` 1 and 2, ten runs each (median), plus peak RSS,
fixed to 2 threads and fp32. Run inside the image: `python
/app/bench/bench.py`; prints one JSON line.
