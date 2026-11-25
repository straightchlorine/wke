# wke-api

FastAPI service: REST API, MCP server, `/llms.txt`, the job worker, and the watcher and
trending entrypoints.

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

## Environment variables

See `.env.example`; a variable with no default is required.

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
| `WATCHER_METRICS_PORT` | 8000 | Port the watcher serves `/metrics` on |
| `LOG_FORMAT` | json | `json` (one object per line) or `console` |
| `CORS_ORIGINS` | empty | Comma-separated allowed origins |
| `SUMMARY_SECTIONS` | 8 | Most sections summarized per build (3 to 8 by article size) |
| `NUM_BEAMS` | 1 | Beam count for wke-ml `/v1/summarize` |
| `LEAN_RESPONSE` | true | Leave the Key facts block and the per-section "left out" lines out of responses and the budget; `parts=dossier,metadata` brings them back |
| `SUBSECTION_HEADINGS` | true | Structural-dossier Markdown names the subsection where passages jump; `false` leaves the headings out |
| `ANALYZE_DEADLINE_MS` | 8000 | Deadline sent to wke-ml `/v1/analyze` and that call's timeout; keep one attempt under the 20 s the MCP `get_dossier` tool waits |
| `ANALYZE_RETRIES` | 0 | Extra analyze attempts after a failure (4xx is never retried); a 503 shed by wke-ml late in the deadline is retried even without `ANALYZE_RETRY_ON_TIMEOUT` |
| `ANALYZE_RETRY_PAUSE_MS` | 1000 | Pause between analyze attempts |
| `ANALYZE_RETRY_ON_TIMEOUT` | false | Also retry an analyze timeout |
| `DOSSIER_STRUCTURAL_TTL_SECONDS` | 600 | Lifetime of a structural dossier built while wke-ml is unavailable |
| `SELECTION_RATING` | false | Pack by wke-ml's model rating once a revision's rating is stored (see below) |
| `RATING_DEADLINE_SECONDS` | 1800 | Longest one rating attempt of an article; the next attempt resumes it |
| `RATING_CALL_TIMEOUT_SECONDS` | 120 | Timeout of one wke-ml rating call (one passage) |
| `RATING_MIN_COVERAGE` | 0.9 | Share of prose passages that need a real score for the rating to apply; below it the stored relevance packs |
| `RATING_MAX_ATTEMPTS` | 3 | Failed attempts without a new score before a stage is dropped until the next build |
| `RATING_RETRY_BACKOFF_SECONDS` | 60 | Wait before such a stage is tried again; doubles per attempt |
| `LOG_LEVEL` | INFO | Python logging level |
| `QUEUE_CAP` | 20 | `q:interactive` depth before 503 |
| `BACKGROUND_QUEUE_CAP` | 50 | `q:background` depth before 503 |
| `WM_BUDGET_PER_MINUTE` | 150 | Shared Wikimedia call budget/min |

## Selection by rating (`SELECTION_RATING`)

Off by default. On, every built dossier (ml and structural) is queued on `q:rate` once it is stored. A
rater loop in the worker rates its prose passages one wke-ml `POST /v1/rate` call at a time and stores
the scores in `rating:{page}:{rev}:{pv}:{prompt}:{model}` (7 days; a rebuild of the same revision
extends a finished rating to the dossier's life). A read packs with the rating only when that document
is complete, names exactly the dossier's prose passages and holds a real score for at least
`RATING_MIN_COVERAGE` of them; otherwise it packs with the stored relevance. JSON
`metadata.build.selection` says which ("relevance" or "rating"), and the ETag gets `-r0` or `-r1`. No
read waits for a rating.

A stage that ends unavailable (wke-ml down or answering 503) or over `RATING_DEADLINE_SECONDS` releases
its lock and is queued again after `RATING_RETRY_BACKOFF_SECONDS` (doubling), resuming from the stored
scores; `RATING_MAX_ATTEMPTS` attempts in a row without a new score end it until the next build. A
dossier that expired, a rating under another prompt or model and a revision the page pointer has moved
past are dropped. Each rater claims the revision it rates with a heartbeat key (`rate:hb:{page}:{rev}`)
and a second rater skips an item that is claimed; an item in `q:rate:processing` without a heartbeat
is put back on the queue, at start and every 30 seconds. Metric `wke_rating_stage_total{outcome}`.

wke-ml must run the model file `gemma-4-E4B-it-Q4_K_M.gguf` (Gemma 4 E4B, Q4_K_M): the rater compares
the file name wke-ml reports and ends a stage with outcome `mismatch` on any other. The name is the
only check; a different quantisation under that name is not detected. The pod needs memory for it
(see the wke-ml README); a rating call during a stage can take 6 to 27 seconds, and wke-ml runs it
beside `/v1/analyze`, so the analyze calls of a build are slower while it runs.

The rater has its own wke-ml client and its own timeouts (`RATING_CALL_TIMEOUT_SECONDS` and the stage
deadline). The analyze deadline and retry (`ANALYZE_DEADLINE_MS`, `ANALYZE_RETRIES`,
`ANALYZE_RETRY_PAUSE_MS`, `ANALYZE_RETRY_ON_TIMEOUT`) apply to a build's analyze call only and do not
touch a rating call.

## Run locally

```
docker compose -f docker-compose.dev.yml up --build
```

or

```
cd backend/api && cp .env.example .env && uv sync && uv run python -m wke.api
```

By hand this needs Redis at `REDIS_URL` (for example
`docker run -d -p 6379:6379 redis:7-alpine`); start wke-ml separately or run without it.
wke-ml is optional (`profiles: ["ml"]`); without it the API still serves, degraded
(`structural` mode).

## Test

```
cd backend/api && uv run pytest
uv run pytest --cov   # gate: >=85% on wke/
```

## Wikimedia policy

`src/wke/clients/` sends a compliant User-Agent (`wke/<version>
(https://wke.piotrkrzysztof.dev; <WKE_CONTACT_EMAIL>) httpx/<version>`),
serializes calls cluster-wide to concurrency 1 via a Redis lock, and
sends `maxlag=5` on every Action API call.

Cold dossier build = 3 Wikimedia calls; warm GET = 0. `Retry-After`
(429, or `maxlag` or `ratelimited` on HTTP 200) is honoured before any retry.

Article text is served as Wikipedia wrote it; clustering and summaries are WKE's own and
are labelled as such.

Container image: two-stage `python:3.13-slim` build. Measured size as of 28-09-2026: 209MB.
