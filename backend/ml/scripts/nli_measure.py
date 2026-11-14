"""Scratch measurement: NLI entailment of summary sentences against section sources.

Run from backend/ml: uv run python scripts/nli_measure.py MODEL OUT.json [--threads N]
Reads the dossier JSON cache used by the fidelity check; writes per-sentence
max-entailment scores. Not part of the service.
"""

# Scratch script over untyped transformers and ad-hoc JSON rows: basic checking only.
# pyright: basic

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / ".run" / "dossier-quality" / "after_cache"
sys.path.insert(0, str(ROOT / "backend" / "api" / "src"))
sys.path.insert(0, str(ROOT / "backend" / "api" / "scripts" / "eval"))


def split(text: str) -> list[str]:
    """Split text into sentences with the API splitter when importable.

    Args:
        text: raw text.

    Returns:
        The sentences.
    """
    # wke is wke-api's package, put on sys.path above rather than installed here.
    from wke.core.text.sentences import split_sentences  # pyright: ignore[reportMissingImports]

    return split_sentences(text)


def chunk_source(tok, sentences: list[str], budget: int) -> list[str]:
    """Pack source sentences into premises of at most budget tokens.

    Args:
        tok: tokenizer.
        sentences: source sentences.
        budget: token budget per premise.

    Returns:
        Premise strings.
    """
    out, cur, n = [], [], 0
    for s in sentences:
        k = len(tok(s, add_special_tokens=False)["input_ids"])
        if k > budget:
            ids = tok(s, add_special_tokens=False)["input_ids"]
            if cur:
                out.append(" ".join(cur))
                cur, n = [], 0
            for i in range(0, len(ids), budget):
                out.append(tok.decode(ids[i : i + budget]))
            continue
        if n + k > budget and cur:
            out.append(" ".join(cur))
            cur, n = [], 0
        cur.append(s)
        n += k
    if cur:
        out.append(" ".join(cur))
    return out


def main() -> None:
    """Score every summary sentence and write the result.

    Returns:
        None.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("out")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument(
        "--window", type=int, default=0, help="premise = sliding window of N source sentences"
    )
    a = ap.parse_args()
    if a.threads:
        torch.set_num_threads(a.threads)
    t0 = time.perf_counter()
    tok = AutoTokenizer.from_pretrained(a.model)
    model = AutoModelForSequenceClassification.from_pretrained(a.model).eval()
    load_s = time.perf_counter() - t0
    id2 = {int(k): v.lower() for k, v in model.config.id2label.items()}
    ent = [k for k, v in id2.items() if v.startswith("entail")][0]
    maxlen = min(tok.model_max_length, 512)
    rows, pairs, cpu_total = [], 0, 0.0
    files = sorted(CACHE.glob("*.json"))
    for f in files:
        d = json.loads(f.read_text())
        chunks = {c["id"]: c for c in d["chunks"]}
        for s in d["sections"]:
            if s["summary_state"] != "done" or not s.get("summary"):
                continue
            if a.limit and len(rows) >= a.limit:
                break
            ids = s["summary"]["input_chunk_ids"]
            src = " ".join(chunks[i]["text"] for i in ids if i in chunks).strip()
            sents = split(s["summary"]["text"].replace(" .", "."))
            prem_sents = split(src)
            c0 = time.process_time()
            w0 = time.perf_counter()
            scores = []
            for h in sents:
                hl = len(tok(h, add_special_tokens=False)["input_ids"])
                if a.window:
                    n = a.window
                    prem = [
                        " ".join(prem_sents[i : i + n])
                        for i in range(max(1, len(prem_sents) - n + 1))
                    ]
                else:
                    prem = chunk_source(tok, prem_sents, max(32, maxlen - hl - 4))
                best = 0.0
                for i in range(0, len(prem), 8):
                    enc = tok(
                        prem[i : i + 8],
                        [h] * len(prem[i : i + 8]),
                        truncation="only_first",
                        max_length=maxlen,
                        padding=True,
                        return_tensors="pt",
                    )
                    with torch.inference_mode():
                        p = model(**enc).logits.softmax(-1)[:, ent]
                    best = max(best, float(p.max()))
                    pairs += len(p)
                scores.append(round(best, 4))
            cpu = time.process_time() - c0
            cpu_total += cpu
            rows.append(
                {
                    "title": d["topic"]["title"],
                    "label": s["label"],
                    "sid": s["id"],
                    "sentences": sents,
                    "scores": scores,
                    "cpu_s": cpu,
                    "wall_s": time.perf_counter() - w0,
                    "n_prem_tokens": len(tok(src)["input_ids"]),
                }
            )
    nsent = sum(len(r["scores"]) for r in rows)
    Path(a.out).write_text(
        json.dumps(
            {
                "model": a.model,
                "threads": torch.get_num_threads(),
                "load_s": load_s,
                "pairs": pairs,
                "sentences": nsent,
                "summaries": len(rows),
                "cpu_total": cpu_total,
                "rows": rows,
            }
        )
    )
    print(
        a.model,
        "threads",
        torch.get_num_threads(),
        "load",
        round(load_s, 2),
        "summaries",
        len(rows),
        "sentences",
        nsent,
        "pairs",
        pairs,
        "cpu_s",
        round(cpu_total, 1),
    )


if __name__ == "__main__":
    main()
