#!/bin/sh
# Release gate: runs the bench inside the built wke-ml image and fails when
# the greedy (num_beams=1) p50 wall time is missing or above 10 s.
#
# Env: ML_IMAGE is the image to test; without it the script falls back to a ghcr.io
# tag built from GITHUB_SHA.
set -eu

ref="${ML_IMAGE:-ghcr.io/straightchlorine/wke-ml:${GITHUB_SHA}}"
if [ -n "${GHCR_USER:-}" ] && [ -n "${GHCR_TOKEN:-}" ]; then
    docker login ghcr.io -u "$GHCR_USER" -p "$GHCR_TOKEN"
fi

cid=$(docker create "$ref" python bench/bench.py)
trap 'docker rm -f "$cid" >/dev/null 2>&1 || true' EXIT
docker cp backend/ml/bench "$cid:/app/bench"
out=$(docker start -a "$cid")
echo "$out"
p50=$(echo "$out" | docker run --rm -i --entrypoint python "$ref" -c \
    'import json, sys; print(json.loads(sys.stdin.read())["p50_wall_s"].get("before", ""))')
if [ -z "$p50" ]; then
    echo "no greedy p50 in bench output" >&2
    exit 1
fi
awk -v p50="$p50" 'BEGIN { if (p50 + 0 > 10) { print "p50 " p50 "s exceeds 10s gate"; exit 1 } }'
