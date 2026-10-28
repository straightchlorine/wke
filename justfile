# Local stack; services run detached.
#
# In order to override default ports - change them in backend/api/.env.

set shell := ["bash", "-cu"]
set dotenv-load
set dotenv-path := "backend/api/.env"

export WKE_PORT := env("WKE_PORT", "8000")
ML_PORT := env("ML_PORT", "8001")
WEB_PORT := env("WEB_PORT", "8080")
SHARE_PORT := env("SHARE_PORT", "8081")
REDIS_PORT := env("REDIS_PORT", "6379")
export WATCHER_METRICS_PORT := env("WATCHER_METRICS_PORT", "8002")
API_ORIGIN := "http://localhost:" + WKE_PORT

export ML_URL := "http://localhost:" + ML_PORT
export REDIS_URL := "redis://localhost:" + REDIS_PORT + "/0"
export PUBLIC_HOST := "localhost:" + WKE_PORT
export PUBLIC_SCHEME := env("PUBLIC_SCHEME", "http")
export CORS_ORIGINS := "http://localhost:" + WEB_PORT
export POD_CIDR := env("POD_CIDR", "127.0.0.1/32")

# redis, wke-ml, wke-api, the watcher and the web preview (logs in .run/)
up:
    @test -f backend/api/.env -o -n "${JUST_DOTENV_COMMAND:-}" || { echo 'no backend/api/.env: cp backend/api/.env.example backend/api/.env'; exit 1; }
    mkdir -p .run
    ss -ltn | grep -q ':{{REDIS_PORT}} ' || docker start wke-crit-redis 2>/dev/null || docker start wke-redis 2>/dev/null || docker run -d --name wke-redis -p {{REDIS_PORT}}:6379 redis:7-alpine
    -for c in wke-crit-redis wke-redis; do docker exec $c redis-cli config set save '300 1' >/dev/null 2>&1; done
    # keep dev data across reboots
    cd backend/ml && setsid -f uv run uvicorn wke_ml.main:app --port {{ML_PORT}} > ../../.run/ml.log 2>&1
    cd backend/api && setsid -f uv run python -m wke.api > ../../.run/api.log 2>&1
    cd backend/api && setsid -f uv run python -m wke.watcher > ../../.run/watcher.log 2>&1
    cd frontend/app && pnpm run build > /dev/null && WKE_API_ORIGIN={{API_ORIGIN}} setsid -f pnpm exec vite preview --port {{WEB_PORT}} > ../../.run/web.log 2>&1
    @echo "starting; open http://localhost:{{WEB_PORT}} (just status)"

# stop everything but Redis
down:
    -pkill -f 'vite previe[w]'
    -pkill -f 'python[0-9]* -m wke[.]'
    -pkill -f 'wke_ml[.]main'

status:
    @for p in {{REDIS_PORT}} {{ML_PORT}} {{WKE_PORT}} {{WEB_PORT}} {{SHARE_PORT}}; do ss -ltn | grep -q ":$p " && echo "$p up" || echo "$p down"; done

# api, ml, watcher or web
logs svc="api":
    tail -f .run/{{svc}}.log

# restart one service in place with the same ports and env as `up`: just restart api|ml|watcher|web
restart svc="api":
    #!/usr/bin/env bash
    set -eu
    mkdir -p .run
    case "{{svc}}" in
      api)
        pkill -f 'python[0-9]* -m wke[.]api' || true; sleep 1
        cd backend/api && setsid -f uv run python -m wke.api > ../../.run/api.log 2>&1 ;;
      ml)
        pkill -f 'wke_ml[.]main' || true; sleep 1
        cd backend/ml && setsid -f uv run uvicorn wke_ml.main:app --port {{ML_PORT}} > ../../.run/ml.log 2>&1 ;;
      watcher)
        pkill -f 'python[0-9]* -m wke[.]watcher' || true; sleep 1
        cd backend/api && setsid -f uv run python -m wke.watcher > ../../.run/watcher.log 2>&1 ;;
      web)
        p={{WEB_PORT}}; pkill -f "vite preview --port ${p%?}[${p: -1}]" || true; sleep 1
        cd frontend/app && pnpm run build > /dev/null && WKE_API_ORIGIN={{API_ORIGIN}} setsid -f pnpm exec vite preview --port {{WEB_PORT}} > ../../.run/web.log 2>&1 ;;
      *)
        echo "unknown service '{{svc}}' (api|ml|watcher|web)"; exit 1 ;;
    esac
    echo "restarted {{svc}}; check with: just status"

# share a frozen build on SHARE_PORT through ngrok; rebuilds on WEB_PORT never reach visitors.
# restarts only the API, with links pointing at the tunnel: just share <name>.ngrok-free.dev
share host:
    mkdir -p .run
    cd frontend/app && pnpm typecheck > /dev/null && pnpm run build > /dev/null
    rm -rf .run/share-dist && cp -r frontend/app/dist .run/share-dist
    p={{SHARE_PORT}}; pkill -f "vite preview --port ${p%?}[${p: -1}]" || true
    cd frontend/app && WKE_API_ORIGIN={{API_ORIGIN}} setsid -f pnpm exec vite preview --port {{SHARE_PORT}} --outDir ../../.run/share-dist > ../../.run/share.log 2>&1
    -pkill -f 'python[0-9]* -m wke[.]api'
    sleep 2
    cd backend/api && PUBLIC_HOST={{host}} PUBLIC_SCHEME=https setsid -f uv run python -m wke.api > ../../.run/api.log 2>&1
    ngrok http {{SHARE_PORT}} --url https://{{host}}

# pull a dossier through every channel and check it (just dossier "<topic>")
dossier topic *args:
    @test -f .claude/skills/dossier-control/pull.py || { echo "dossier-control skill not installed"; exit 1; }
    cd backend/api && dir=$(uv run python ../../.claude/skills/dossier-control/pull.py "{{topic}}" {{args}} | tail -1); test -d "$dir" && uv run python ../../.claude/skills/dossier-control/check "$dir"
