# wke-api

FastAPI service: REST API, MCP server, `/llms.txt`, the job worker, and watcher/trending entrypoints.

## Endpoints

- `GET/POST /api/v1/dossiers`, `GET .../{page_id}[.md]`,
  `GET .../{page_id}/rev/{rev_id}`, `GET /api/v1/search`
- `GET /api/v1/jobs/{job_id}`, `/trending`, `/live`, `/status`
- `GET /healthz`, `/readyz`, `/metrics`, `/llms.txt`
- `/mcp`: tools `search_topics`, `get_dossier`, `get_trending`;
  read-only, no auth, 30/min per IP.

## Entrypoints

- `python -m wke.api` - uvicorn + job worker in-process (app lifespan).
- `python -m wke.worker` - the same job worker, standalone process.
- `python -m wke.watcher` - EventStreams `recentchange` consumer.
- `python -m wke.trending` - nightly snapshot + prebuild drain (CronJob).

## Environment variables (see `.env.example`; no default = required)
| Var | Default | Meaning |
|---|---|---|
| `WIKIPEDIA_API_URL` | required | Action API endpoint |
| `WIKIPEDIA_REST_URL` | required | Wikipedia REST/Parsoid endpoint |
| `WIKIMEDIA_EVENTSTREAMS_URL` | required | EventStreams endpoint (watcher) |
| `WIKIFEEDS_URL` | required | Wikifeeds base URL (trending) |
| `ML_URL` | required | wke-ml base URL |
| `REDIS_URL` | required | Redis URL: cache, queue, counters |
| `PUBLIC_HOST` | required | Public hostname; also MCP allowed host |
| `WKE_CONTACT_EMAIL` | required | Contact in the Wikimedia User-Agent |
| `POD_CIDR` | required | Trusted proxy CIDR for uvicorn |
| `PIPELINE_VERSION` | required | Version tag in dossier/job keys |
| `WKE_PORT` | 8000 | uvicorn listen port |
| `CORS_ORIGINS` | empty | Comma-separated allowed origins |
| `SUMMARY_SECTIONS` | 8 | Most sections summarized per build (3 to 8 by article size) |
| `NUM_BEAMS` | 1 | Beam count for wke-ml `/v1/summarize` |
| `LOG_LEVEL` | INFO | Python logging level |
| `QUEUE_CAP` | 20 | `q:interactive` depth before 503 |
| `BACKGROUND_QUEUE_CAP` | 50 | `q:background` depth before 503 |
| `WM_BUDGET_PER_MINUTE` | 150 | Shared Wikimedia call budget/min |

## Run locally

```
docker compose -f docker-compose.dev.yml up --build
```
or
```
cd backend/api && cp .env.example .env && uv sync && uv run python -m wke.api
```
wke-ml is optional (`profiles: ["ml"]`); without it the API still serves, degraded (`structural` mode).

## Test

```
cd backend/api && uv run pytest
uv run pytest --cov   # gate: >=85% on wke/
```

## Wikimedia policy

`wke/clients/wikimedia.py` sends a compliant User-Agent (`wke/<version>
(https://wke.piotrkrzysztof.dev; <WKE_CONTACT_EMAIL>) httpx/<version>`),
serializes calls cluster-wide to concurrency 1 via a Redis lock, and
sends `maxlag=5` on every Action API call.

Cold dossier build = 3 Wikimedia calls; warm GET = 0. `Retry-After`
(429, or `maxlag`/ `ratelimited` on HTTP 200) is honoured before any retry.

Container image: two-stage `python:3.13-slim` build. Measured size as of 28-09-2026: 209MB.
