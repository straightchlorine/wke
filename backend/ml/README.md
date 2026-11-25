# wke-ml

FastAPI inference service called by wke-api over HTTP.

- `POST /v1/analyze` - MiniLM embed, cosine relevance to the lead, KMeans clustering,
  related-article edges. Vectors never leave the pod.
- `POST /v1/summarize` - abstractive summary via distilbart-cnn-6-6.
- `POST /v1/rate` - a local GGUF model (Gemma 4 E4B Q4_K_M) rates 1 to 8 passages of one
  article from 0 to 3 for how much a reader who wants the essentials needs them; the prompt is
  `src/wke_ml/rating_prompt.json`. It has its own gate, so `/v1/analyze` and `/v1/summarize` never
  queue behind it, but they share the CPU. A client that goes away stops the running call at the
  next point the model can be left (not inside prompt evaluation) and starts no further passage.
  503 `rating_unavailable` (no Retry-After) when `WKE_ML_RATING_MODEL_PATH` is empty, the file is
  missing, `llama-cpp-python` is not installed, the pod's memory limit is below
  `WKE_ML_RATING_REQUIRED_MEMORY_GIB`, or the tokenizer cannot carry the digits; 422 when a prompt
  exceeds the context. The model loads on the first call and stays resident.
- `GET /healthz` (weights resident), `/readyz` (warm-up done), and Prometheus metrics at
  `/metrics`.

## Models

| Model | Revision |
|---|---|
| `sentence-transformers/all-MiniLM-L6-v2` | `1110a243` |
| `sshleifer/distilbart-cnn-6-6` | `d2fde4ca` |

Weights are bundled into the image (`fetch_models.py`), converted to safetensors and kept
at the checkpoint's native fp16 on disk; the torch backend casts to fp32 at load.

## Environment variables

There is no `.env.example`; all variables have defaults.

| Var | Default | Meaning |
|---|---|---|
| `WKE_ML_BACKEND` | torch | `torch` (real) or `stub` (deterministic, no torch import) |
| `WKE_ML_EMBED_MODEL` / `_REVISION` | MiniLM-L6-v2 / 1110a243 | Embedding model + pinned revision |
| `WKE_ML_SUMMARIZE_MODEL` / `_REVISION` | distilbart-cnn-6-6 / d2fde4ca | Summarizer + pinned revision |
| `WKE_ML_MAX_INPUT_TOKENS` | 512 | Input truncation cap for summarization |
| `WKE_ML_OMP_NUM_THREADS` | 2 | Torch thread count |
| `WKE_ML_QUEUE_MAX_WAIT` | 4 | Max jobs waiting for the single inference slot |
| `WKE_ML_STUCK_AFTER_SECONDS` | 300 | `/healthz` fails once one job has held the inference slot this long |
| `WKE_ML_RATING_MODEL_PATH` | empty | GGUF file of the rating model; empty turns `/v1/rate` off |
| `WKE_ML_RATING_THREADS` | 2 | Threads of the rating model |
| `WKE_ML_RATING_N_CTX` | 8192 | Context size of the rating model |
| `WKE_ML_RATING_REQUIRED_MEMORY_GIB` | 10 | Memory limit (cgroup `memory.max` or `limit_in_bytes`) the pod must have before the model loads; no limit passes, 0 turns the check off |
| `WKE_ML_KMEANS_SEED` | 42 | KMeans random seed |
| `WKE_ML_KMEANS_MAX_K` | 6 | Upper bound on cluster count |
| `WKE_ML_KMEANS_CHUNKS_PER_CLUSTER` | 6 | Used to bound k against chunk count |
| `WKE_ML_EDGE_SIMILARITY_THRESHOLD` | 0.35 | Min cosine similarity for a related-lead edge |
| `WKE_ML_EDGE_TOP_N` | 2 | Max related edges kept |
| `WKE_ML_LOG_LEVEL` | INFO | Python logging level |
| `WKE_ML_LOG_FORMAT` | json | `json` or `console` |

The rating model file must be named `gemma-4-E4B-it-Q4_K_M.gguf`: wke-api compares the file name
wke-ml reports and ignores answers under another one. The name is the only check; a different
quantisation under that name is not detected. Set `WKE_ML_RATING_REQUIRED_MEMORY_GIB` from the peak
of the whole pod (embedding and summary models as well as Gemma), and raise the pod limit above it
before `SELECTION_RATING` is switched on. A pod with no cgroup limit skips the check and logs that.
Deploy wke-ml before wke-api, or the api's rating calls get a 404.

The rating runtime is the dependency group `rating` (`llama-cpp-python`), which a plain `uv sync`
does not install; add it with `uv sync --group rating`.

## Run locally

```
docker compose -f docker-compose.dev.yml --profile ml up --build
```

or against the host's Hugging Face cache, so weights download once:

```
cd backend/ml && uv sync
uv run uvicorn wke_ml.main:app --host 0.0.0.0 --port 8000
```

`WKE_ML_BACKEND=stub` skips the torch import and download entirely. The compose file
limits the container to 3 GB of memory.

## Test

```
cd backend/ml && uv run pytest
```

## Bench

`bench/bench.py` times distilbart-cnn-6-6 `generate()` on a fixed input, greedy
against beam-search decoding. It reports median wall and CPU seconds, generated
tokens, cold start and peak RSS.

Run it from `backend/ml` with `uv run python bench/bench.py`; it prints one JSON
line.
