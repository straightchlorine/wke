"""Tunables of the build pipeline: summary limits, stage counts and URL budget."""

from __future__ import annotations

from wke.core.text.tokens import CHARS_PER_TOKEN

LICENSE_NOTICE = (
    "Quoted passages are CC BY-SA 4.0 Wikipedia content, cited to a pinned "
    "revision. Summaries are machine output, not a Wikipedia quotation."
)

SUMMARY_MODEL = "sshleifer/distilbart-cnn-6-6"

# Hugging Face commit the cache key is computed from.
# A persisted summary keeps whatever revision wke-ml reports back instead.
SUMMARY_MODEL_REVISION = "d2fde4ca"
SUMMARY_MIN_LENGTH = 30
SUMMARY_MAX_LENGTH = 96
SUMMARY_INPUT_CHAR_CAP = 512 * CHARS_PER_TOKEN
SUMMARY_TOKENS_PER_SECTION = 2000
SUMMARY_SECTIONS_MIN = 3

# Article builds cap graph edges at 20; wke.trending.run has its own, higher cap.
ANALYZE_MAX_EDGES = 20

# Budget Job.result_url points at: the default GET /api/v1/dossiers budget, so
# the link needs no query string.
RESULT_URL_BUDGET = 8000

# Stages to a successful persist: resolve, fetch, parse, related, embed,
# cluster, persist. Without wke-ml the path skips "cluster".
ML_PATH_STAGE_COUNT = 7
STRUCTURAL_PATH_STAGE_COUNT = 6

# Rating of the prose passages by a local model (selection by rating).
RATING_MODEL = "gemma4-e4b"
RATING_MODEL_FILE = "gemma-4-E4B-it-Q4_K_M.gguf"
# sha256 of the five prompt strings wke-ml sends the model; a reply with another hash is refused.
RATING_PROMPT_SHA256 = "f68afeb2bc1aaf3734cdeb0127500589966f47fbb7b74c20a004941e69bc6ec7"
RATING_CALL_ATTEMPTS = 3
RATING_RETRY_PAUSE_SECONDS = 5
# Lock of a rating stage outlives its deadline by this much.
RATING_LOCK_MARGIN_SECONDS = 600
