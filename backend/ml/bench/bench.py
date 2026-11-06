"""Timing script: distilbart-cnn-6-6 generate() latency and peak RSS.

Run from backend/ml: uv run python bench/bench.py
Fixed to 2 threads and fp32 to match OCI A1.Flex pod budget (2000m/3Gi).
Compares the old greedy decoding with the beam-search decoding wke-ml
uses now, reporting p50 wall and CPU seconds per summary for each.
Prints exactly one JSON line to stdout.
"""

# transformers leaves from_pretrained and generate untyped.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false

import json
import os
import resource
import statistics
import time
from typing import Any

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

from wke_ml.backends import LENGTH_PENALTY, NO_REPEAT_NGRAM_SIZE
from wke_ml.settings import Settings
from wke_ml.summarize import DEFAULT_MAX_LENGTH, DEFAULT_MIN_LENGTH, DEFAULT_NUM_BEAMS

_SETTINGS = Settings()
MODEL_NAME = _SETTINGS.summarize_model
MODEL_REVISION = os.environ.get("DISTILBART_REV", _SETTINGS.summarize_model_revision)
NUM_THREADS = 2
INPUT_TOKENS = 512
RUNS_PER_CONFIG = 5

# "before" is the greedy decoding the service shipped with; "after" is
# the decoding in wke_ml.backends.
DECODING: dict[str, dict[str, Any]] = {
    "before": {"num_beams": 1, "min_length": 30, "max_length": 96},
    "after": {
        "num_beams": DEFAULT_NUM_BEAMS,
        "min_length": DEFAULT_MIN_LENGTH,
        "max_length": DEFAULT_MAX_LENGTH,
        "length_penalty": LENGTH_PENALTY,
        "no_repeat_ngram_size": NO_REPEAT_NGRAM_SIZE,
        "early_stopping": True,
    },
}

# Long enough source text that tokenizing with truncation=True at
# max_length=512 fills the full window; repetition is fine, generate()
# latency depends on sequence length, not content.
SOURCE_TEXT = (
    "Wikipedia is a free online encyclopedia that anyone can edit. "
    "It is written collaboratively by volunteers and hosted by the "
    "Wikimedia Foundation. Articles cover a broad range of topics, "
    "from history and science to culture and current events. "
) * 40


def _peak_rss_mb() -> float:
    """Read this process's peak resident set size.

    Returns:
        Peak RSS in megabytes. ru_maxrss is KB on Linux.
    """
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def main() -> None:
    """Load the model, time both decoding configs and print one JSON line."""
    torch.set_num_threads(NUM_THREADS)

    load_start = time.monotonic()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, revision=MODEL_REVISION)
    try:
        model = AutoModelForSeq2SeqLM.from_pretrained(
            MODEL_NAME, revision=MODEL_REVISION, use_safetensors=True, dtype=torch.float32
        )
    except OSError:
        # The pinned revision predates the safetensors conversion; same
        # fallback as wke_ml.backends.TorchSummarizer.
        model = AutoModelForSeq2SeqLM.from_pretrained(
            MODEL_NAME, revision=MODEL_REVISION, use_safetensors=False, dtype=torch.float32
        )
    model.eval()
    cold_start_s = time.monotonic() - load_start

    inputs = tokenizer(SOURCE_TEXT, return_tensors="pt", max_length=INPUT_TOKENS, truncation=True)
    input_tokens = int(inputs["input_ids"].shape[1])

    wall_p50: dict[str, float] = {}
    cpu_p50: dict[str, float] = {}
    generated_tokens: dict[str, int] = {}
    with torch.inference_mode():
        for name, kwargs in DECODING.items():
            wall: list[float] = []
            cpu: list[float] = []
            for _ in range(RUNS_PER_CONFIG):
                wall_start, cpu_start = time.monotonic(), time.process_time()
                out = model.generate(**inputs, **kwargs)
                cpu.append(time.process_time() - cpu_start)
                wall.append(time.monotonic() - wall_start)
                generated_tokens[name] = int(out.shape[1])
            wall_p50[name] = statistics.median(wall)
            cpu_p50[name] = statistics.median(cpu)

    result = {
        "model": MODEL_NAME,
        "model_revision": MODEL_REVISION,
        "threads": NUM_THREADS,
        "dtype": "fp32",
        "input_tokens": input_tokens,
        "runs_per_config": RUNS_PER_CONFIG,
        "cold_start_s": round(cold_start_s, 3),
        "p50_wall_s": {k: round(v, 3) for k, v in wall_p50.items()},
        "p50_cpu_s": {k: round(v, 3) for k, v in cpu_p50.items()},
        "generated_tokens": generated_tokens,
        "peak_rss_mb": round(_peak_rss_mb(), 1),
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
