"""Score how many fixed questions a stored dossier answers at each token budget.

Purpose: measure dossier content before and after a pipeline change. The
question set lives in scripts/eval/questions.json (each question is tagged
prose, infobox or table, and key or detail; --questions scores another set).
For every topic the script fetches the Markdown at each budget, 2000, 8000 and
32000 unless --budgets narrows them, and marks a question answered when any
accepted answer occurs in the scored text.

Scored text is the Markdown without the header block (everything before the
first "## " heading), without the Sources footer, without heading lines and
without machine summaries, so a section title or model output never answers a
question (a question may opt in to headings with "headings_count"; --summaries
keeps summaries). Both sides are normalised: lower case, no diacritics,
whitespace collapsed, every dash variant as "-", curly quotes straightened,
Markdown links reduced to their text, backslash escapes removed. An
accepted answer starting with "re:" is a regular
expression over the normalised text; any other answer is a plain substring.

Tokens use the chars/4 estimator the API itself uses, applied to the whole
Markdown document, because that is what a caller puts into a context window.

Cost: one read-only GET per topic and budget (3 per topic) against the WKE API;
no Wikimedia calls unless the API cache behind a dossier is cold. The fetching
itself is stdlib only (urllib); the wke imports serve --offline and the token
estimator.

With --offline the dossiers are read from Redis (wke.offline, at --redis-url)
and packed and rendered in this process by the current code, with no API call
and no rebuild. --reparse implies --offline and also re-runs the current
parser over the cached Parsoid HTML, so key facts and tables are scored on
dossiers stored before they existed; the HTML is the Redis cache at
--redis-url, then the source-<rev>.html of the --pulled-dir folder, and a
topic with neither is scored as stored. --no-summary-standins packs without
summaries, to measure what summary stand-ins add. --pulled-dir falls back to a
pull.py folder for a topic Redis does not hold.

Usage, from backend/api:

    uv run python scripts/eval_recall.py --base-url http://localhost:8010/api/v1
    uv run python scripts/eval_recall.py --pinned --out /tmp/recall.json
    uv run python scripts/eval_recall.py --offline --reparse --topics lizzie,madonna
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

from wke.core.citations import seed_pin
from wke.core.models.budgets import BUDGETS, BudgetTokens
from wke.core.text.tokens import est_tokens
from wke.offline.reparse import reparse, view_and_markdown
from wke.offline.store import (
    connect,
    load_dossier,
    load_html,
    load_pulled,
    load_pulled_html,
)

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DEFAULT_QUESTIONS = HERE / "eval" / "questions.json"
DEFAULT_OUT = REPO / ".run" / "eval" / "recall.json"
DEFAULT_API = "http://localhost:8010/api/v1"

TAGS = ("prose", "infobox", "table")
IMPORTANCE = ("key", "detail")

DASHES = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"), "-")
QUOTES = {
    0x2018: "'",
    0x2019: "'",
    0x201C: '"',
    0x201D: '"',
    0x00A0: " ",
}
# A Markdown link on quoted text: only its text is what a reader sees.
MD_LINK = re.compile(r"\[((?:\\.|[^\]\\])*)\]\(https?://[^)\s]*\)")
PIN_LINE = re.compile(r"Pinned at revision (\d+)")


def _parse_args() -> argparse.Namespace:
    """Parse the command line.

    Returns:
        argparse.Namespace: the parsed command line.
    """
    parser = argparse.ArgumentParser(description="Score dossier recall on a fixed question set.")
    parser.add_argument("--base-url", default=DEFAULT_API, help="API base URL including /api/v1")
    parser.add_argument("--questions", default=str(DEFAULT_QUESTIONS), help="question set JSON")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="result JSON path")
    parser.add_argument(
        "--budgets",
        default=",".join(map(str, BUDGETS)),
        help="comma-separated token budgets",
    )
    parser.add_argument("--topics", default="", help="comma-separated topic keys (default: all)")
    parser.add_argument(
        "--summaries", action="store_true", help="score model summaries as well as passages"
    )
    parser.add_argument(
        "--offline", action="store_true", help="pack stored dossiers from Redis in-process"
    )
    parser.add_argument(
        "--reparse",
        action="store_true",
        help="re-parse the cached Parsoid HTML (implies --offline)",
    )
    parser.add_argument(
        "--no-summary-standins",
        action="store_true",
        help="with --offline: pack without summaries",
    )
    parser.add_argument("--redis-url", default="redis://localhost:6379/0", help="for --offline")
    parser.add_argument(
        "--pulled-dir",
        default="",
        help="with --offline: read a topic missing from Redis from this pull.py folder",
    )
    parser.add_argument(
        "--pinned",
        action="store_true",
        help="fetch each topic at its ground-truth revision instead of the latest",
    )
    return parser.parse_args()


def normalise(text: str) -> str:
    """Normalise text for matching.

    Args:
        text: Raw text or an accepted answer.

    Returns:
        str: lower-case text without diacritics, backslash escapes or spaces
        around dashes, with whitespace collapsed.
    """
    text = MD_LINK.sub(r"\1", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.translate(DASHES).translate(QUOTES).replace("\\", "")
    text = re.sub(r"\s*-\s*", "-", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def scored_text(markdown: str, headings: bool, summaries: bool = False) -> str:
    """Cut a dossier Markdown down to the text a question is scored against.

    Args:
        markdown: The full Markdown document.
        headings: Keep heading lines when true.
        summaries: Keep machine summary blocks when true.

    Returns:
        The normalised body: no header block, no Sources footer and, unless
        the flags say otherwise, no heading lines and no machine summaries.
    """
    # Heading lines are dropped by default so a section title never answers a
    # question; a question whose answer is a title sets headings_count and is
    # scored against the headings=True variant.
    lines = markdown.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith("## ")), len(lines))
    kept: list[str] = []
    in_summary = False
    for ln in lines[start:]:
        if ln.strip() == "## Sources":
            break
        if ln.startswith("**Machine summary") and not summaries:
            in_summary = True
        if in_summary:
            in_summary = not ln.startswith(("Model:", "#", ">"))
            if in_summary or ln.startswith("Model:"):
                continue
        if ln.startswith("#") and not headings:
            continue
        kept.append(ln)
    return normalise("\n".join(kept))


def answered(text: str, accepted: list[str]) -> bool:
    """Tell whether any accepted answer occurs in the text.

    Args:
        text: Normalised scored text.
        accepted: Accepted answers; "re:" marks a regular expression.

    Returns:
        bool: True when at least one accepted answer matches.
    """
    for answer in accepted:
        if answer.startswith("re:"):
            if re.search(answer[3:], text):
                return True
        elif normalise(answer) in text:
            return True
    return False


def parse_budget(value: str) -> BudgetTokens:
    """Read one --budgets value as a served budget.

    Args:
        value: a number from the comma-separated list.

    Returns:
        BudgetTokens: the budget.

    Raises:
        SystemExit: when the value is not a served budget.
    """
    for budget in BUDGETS:
        if str(budget) == value.strip():
            return budget
    raise SystemExit(f"--budgets: {value!r} is not one of {', '.join(map(str, BUDGETS))}")


def fetch_markdown(base: str, topic: dict[str, Any], budget: int, pinned: bool) -> str:
    """Fetch one dossier as Markdown.

    Args:
        base: API base URL including /api/v1.
        topic: Topic entry with page_id and rev_id.
        budget: Token budget.
        pinned: Fetch the ground-truth revision instead of the latest.

    Returns:
        str: the Markdown body.
    """
    pid = topic["page_id"]
    if pinned:
        url = f"{base}/dossiers/{pid}/rev/{topic['rev_id']}?budget={budget}&format=md"
    else:
        url = f"{base}/dossiers/{pid}.md?budget={budget}"
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"Accept": "text/markdown"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            raise RuntimeError(f"{url}: HTTP {exc.code}") from exc
    raise RuntimeError(f"{url}: rate limited")


def score_topic(
    markdown: str, questions: list[dict[str, Any]], summaries: bool = False
) -> dict[str, Any]:
    """Score one Markdown document against the questions of its topic.

    Args:
        markdown: The dossier Markdown.
        questions: Question entries for this topic.
        summaries: Score machine summaries as well as passages.

    Returns:
        dict[str, Any]: answered count, total, recall, per-tag counts and
        per-question hits.
    """
    body = scored_text(markdown, headings=False, summaries=summaries)
    body_h = scored_text(markdown, headings=True, summaries=summaries)
    hits: dict[str, bool] = {}
    by_tag: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_importance: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for q in questions:
        text = body_h if q.get("headings_count") else body
        hit = answered(text, q["answers"])
        hits[q["id"]] = hit
        by_tag[q["tag"]][0] += hit
        by_tag[q["tag"]][1] += 1
        by_importance[q.get("importance", "detail")][0] += hit
        by_importance[q.get("importance", "detail")][1] += 1
    done = sum(hits.values())
    return {
        "answered": done,
        "total": len(questions),
        "recall": round(done / len(questions), 4),
        "by_tag": {t: {"answered": a, "total": n} for t, (a, n) in sorted(by_tag.items())},
        "by_importance": {
            k: {"answered": a, "total": n} for k, (a, n) in sorted(by_importance.items())
        },
        "missed": [k for k, v in hits.items() if not v],
        "hits": hits,
    }


def summarise(results: dict[str, Any], budgets: list[BudgetTokens]) -> dict[str, Any]:
    """Roll topic results up to per-budget and per-tag recall.

    Args:
        results: Mapping topic key -> budget -> topic result.
        budgets: Budgets that were fetched.

    Returns:
        dict[str, Any]: mapping budget to overall recall, per-tag recall and total
        tokens.
    """
    out: dict[str, dict[str, Any]] = {}
    for b in budgets:
        done = total = tokens = 0
        tags: dict[str, list[int]] = {t: [0, 0] for t in TAGS}
        levels: dict[str, list[int]] = {k: [0, 0] for k in IMPORTANCE}
        for per_budget in results.values():
            r = per_budget[str(b)]
            done += r["answered"]
            total += r["total"]
            tokens += r["tokens_est"]
            for t, c in r["by_tag"].items():
                tags[t][0] += c["answered"]
                tags[t][1] += c["total"]
            for k, c in r["by_importance"].items():
                levels[k][0] += c["answered"]
                levels[k][1] += c["total"]
        out[str(b)] = {
            "answered": done,
            "total": total,
            "recall": round(done / total, 4) if total else 0.0,
            "tokens_est": tokens,
            "by_tag": {
                t: {"answered": a, "total": n, "recall": round(a / n, 4) if n else None}
                for t, (a, n) in tags.items()
            },
            "by_importance": {
                k: {"answered": a, "total": n, "recall": round(a / n, 4) if n else None}
                for k, (a, n) in levels.items()
            },
        }
    return out


def print_table(
    results: dict[str, Any], overall: dict[str, Any], budgets: list[BudgetTokens]
) -> None:
    """Print the recall table to stdout.

    Args:
        results: Mapping topic key -> budget -> topic result.
        overall: Output of summarise.
        budgets: Budgets that were fetched.
    """
    head = f"{'topic':<14}" + "".join(f"{b // 1000}k answered  tokens   " for b in budgets)
    print(head)
    for key, per_budget in results.items():
        row = f"{key:<14}"
        for b in budgets:
            r = per_budget[str(b)]
            cell = f"{r['answered']}/{r['total']}"
            row += f"{cell:<10}{r['tokens_est']:<10}"
        print(row)
    row = f"{'ALL':<14}"
    for b in budgets:
        o = overall[str(b)]
        cell = f"{o['answered']}/{o['total']}"
        row += f"{cell:<10}{o['tokens_est']:<10}"
    print(row)
    for t in TAGS:
        cells: list[str] = []
        for b in budgets:
            c = overall[str(b)]["by_tag"][t]
            cells.append(f"{b // 1000}k {c['answered']}/{c['total']}")
        print(f"  {t:<8}" + "  ".join(cells))
    for k in IMPORTANCE:
        cells: list[str] = []
        for b in budgets:
            c = overall[str(b)]["by_importance"][k]
            cells.append(f"{b // 1000}k {c['answered']}/{c['total']}")
        print(f"  {k:<8}" + "  ".join(cells))


def main() -> None:
    """Fetch, score and write the recall report."""
    args = _parse_args()
    spec = json.loads(Path(args.questions).read_text())
    budgets: list[BudgetTokens] = [parse_budget(b) for b in args.budgets.split(",")]
    keys = [k for k in args.topics.split(",") if k] or list(spec["topics"])
    results: dict[str, dict[str, Any]] = {}
    use_offline = args.offline or args.reparse
    client = connect(args.redis_url) if use_offline else None
    for key in keys:
        topic = spec["topics"][key]
        qs = [q for q in spec["questions"] if q["topic"] == key]
        folder = (
            next(Path(args.pulled_dir).glob(f"{topic['page_id']}-*"), None)
            if args.pulled_dir
            else None
        )
        results[key] = {}
        for budget in budgets:
            if client is not None:
                dossier = load_dossier(
                    client, topic["page_id"], topic["rev_id"] if args.pinned else None
                )
                if dossier is None and args.pulled_dir:
                    dossier = load_pulled(args.pulled_dir, topic["page_id"])
                if dossier is None:
                    raise SystemExit(f"{key}: no stored dossier in Redis")
                if args.reparse:
                    rev_id = seed_pin(dossier).rev_id
                    html = load_html(client, rev_id) or load_pulled_html(folder, rev_id)
                    if html is None:
                        print(f"{key}: Parsoid HTML cache is cold, scoring the stored dossier")
                    else:
                        dossier = reparse(dossier, html)
                _view, md = view_and_markdown(
                    dossier, budget, summaries=not args.no_summary_standins
                )
            else:
                md = fetch_markdown(args.base_url, topic, budget, args.pinned)
            scored = score_topic(md, qs, args.summaries)
            pin = PIN_LINE.search(md)
            scored["tokens_est"] = est_tokens(md)
            scored["rev_id"] = int(pin.group(1)) if pin else None
            scored["rev_matches_ground_truth"] = scored["rev_id"] == topic["rev_id"]
            results[key][str(budget)] = scored
            if client is None:
                time.sleep(0.3)
    overall = summarise(results, budgets)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "base_url": "offline" if use_offline else args.base_url,
                "reparsed": bool(args.reparse),
                "pinned": args.pinned,
                "summaries_scored": args.summaries,
                "questions_file": str(Path(args.questions).name),
                "overall": overall,
                "topics": results,
            },
            indent=1,
        )
    )
    print_table(results, overall, budgets)
    print(f"written {out}")


if __name__ == "__main__":
    main()
