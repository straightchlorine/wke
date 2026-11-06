"""Claim-level fidelity check of stored model summaries, run outside the app.

Purpose: find summaries whose sentences are not supported by the passages the
model read. The hard rules are the ones of wke.core.summaries.fidelity, the same
functions the summary gate runs, so a summary reported WITHHOLD here is the
one the gate withholds. The soft rules (sentence-level novel phrases and the
smaller glitches) are reported only.

Input: dossiers from a directory of API or stored-dossier JSON files
(`--dir`), or from Redis through wke.offline (`--redis`). The
summary source is rebuilt as the pipeline does: the section's prose chunks
named in summary.input_chunk_ids, joined by one space.

Output: a table of flagged summaries on stdout (--all adds the unflagged ones)
and a JSON file (--out) with every done summary, its failures and, when the
labels file (--labels) matches, the Opus verdict.

Usage, from backend/api:

    uv run python scripts/eval/fidelity_check.py --dir ../../.run/dossier-quality/after_cache
    uv run python scripts/eval/fidelity_check.py --redis redis://localhost:6379/0
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from wke.core.summaries.fidelity import content, hard_failures, missing_runs, tokens, words
from wke.core.text.sentences import split_sentences
from wke.offline.store import connect, load_dossier, stored_page_ids

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DIR = ROOT / ".run" / "dossier-quality" / "after_cache"
DEFAULT_OUT = ROOT / ".run" / "eval" / "fidelity_local.json"
DEFAULT_LABELS = Path(__file__).with_name("fidelity_local_labels.json")

Severity = Literal["hard", "soft"]

MIN_SENTENCE_WORDS = 3
RUN_ON_MIN_WORDS = 2
DUPLICATE_NGRAM = 6

_SPACE_BEFORE = re.compile(r"\s[.,;:](?=\s|$)")
_RUN_ON = re.compile(r"(?P<span>[\"\u201c][^\"\u201c\u201d]+[\"\u201d]|\([^()]+\))\s+[A-Z][a-z]+\b")


@dataclass
class Failure:
    """One rule failing on one summary."""

    rule: str
    severity: Severity
    sentence: str
    evidence: str
    sub: str = ""


@dataclass
class Row:
    """One done summary and what the rules found."""

    page_id: int
    title: str
    section_id: str
    label: str
    state: str
    failures: list[Failure] = field(default_factory=lambda: list[Failure]())
    verdict: str = ""
    defect: str = ""
    role: str = ""


def soft_glitches(sentences: list[str]) -> list[Failure]:
    """Find the smaller glitches, which are reported and never withhold.

    Args:
        sentences: the summary split into sentences.

    Returns:
        One soft failure per glitch: space before punctuation inside a
        sentence, a sentence of fewer than MIN_SENTENCE_WORDS words, a
        closing quote or bracket followed by a capital with no full stop, a
        repeated sentence, or a repeated 6-gram. The model writes a space
        before the closing full stop of every sentence, so that one does not
        count.
    """
    found: list[Failure] = []

    def add(sub: str, sentence: str, evidence: str) -> None:
        """Record a soft glitch failure for one sub-rule.

        Args:
            sub: the rule sub-key, such as "space_before".
            sentence: the sentence the glitch was seen in.
            evidence: what was found, quoted in the report.
        """
        found.append(Failure("glitch", "soft", sentence, evidence, sub))

    normalised = [" ".join(content(s)) for s in sentences]
    for i, sentence in enumerate(sentences):
        if _SPACE_BEFORE.search(re.sub(r"\s+([.!?])$", r"\1", sentence)):
            add("space_before", sentence, "space before . , ; or : inside the sentence")
        if re.search(r"[^\W\d_]", sentence) and len(words(sentence)) < MIN_SENTENCE_WORDS:
            add("short", sentence, f"sentence of {len(words(sentence))} words")
        if any(
            len(words(m.group("span"))) >= RUN_ON_MIN_WORDS
            and not re.search(r"[.!?,;:]\W*$", m.group("span")[:-1])
            for m in _RUN_ON.finditer(sentence)
        ):
            add("run_on", sentence, "closing quote or bracket then a capital with no full stop")
        if normalised[i] and normalised[i] in normalised[i + 1 :]:
            add("duplicate_sentence", sentence, "sentence repeated")
    all_tokens = [t for s in sentences for t in tokens(s)]
    seen: dict[tuple[str, ...], int] = {}
    for i in range(len(all_tokens) - DUPLICATE_NGRAM + 1):
        gram = tuple(all_tokens[i : i + DUPLICATE_NGRAM])
        if gram in seen and i - seen[gram] >= DUPLICATE_NGRAM:
            add("duplicate_ngram", " ".join(gram), f"{DUPLICATE_NGRAM}-gram occurs twice")
            break
        seen.setdefault(gram, i)
    return found


def soft_phrases(sentences: list[str], source_sentences: list[str]) -> list[Failure]:
    """Report each sentence with a run of content words the source never has.

    Args:
        sentences: the summary split into sentences.
        source_sentences: the source split into sentences.

    Returns:
        list[Failure]: one soft failure per such sentence.
    """
    _, _, absent = missing_runs(sentences, source_sentences)
    return [
        Failure("novel_phrase", "soft", sentence, "no source run for: " + " ".join(gram))
        for sentence, gram in absent
    ]


def check(summary: str, source: str, heading: str = "") -> list[Failure]:
    """Run every rule on one summary.

    Args:
        summary: the summary text.
        source: the passages the model read, joined by one space.
        heading: the section heading.

    Returns:
        list[Failure]: the hard failures, then the soft ones.
    """
    sentences = split_sentences(summary)
    out: list[Failure] = []
    for key, evidence in hard_failures(summary, source, heading):
        rule, _, sub = key.partition(".")
        out.append(Failure(rule, "hard", "(whole summary)", evidence, sub))
    out += soft_glitches(sentences)
    out += soft_phrases(sentences, split_sentences(source))
    return out


def source_text(section: dict[str, Any], chunks: dict[str, dict[str, Any]]) -> str:
    """Rebuild the text the model read for a section.

    Args:
        section: the section as a dict.
        chunks: chunk dicts by id.

    Returns:
        str: the input chunks named in summary.input_chunk_ids, joined by one space.
    """
    ids = section["summary"]["input_chunk_ids"]
    return " ".join(chunks[i]["text"] for i in ids if i in chunks).strip()


def load_dir(path: Path) -> list[dict[str, Any]]:
    """Read dossier JSON files from a directory.

    Args:
        path: directory with one dossier JSON per file.

    Returns:
        list[dict[str, Any]]: the dossiers as dicts, in file-name order.
    """
    return [json.loads(f.read_text()) for f in sorted(path.glob("*.json"))]


def load_redis(url: str) -> list[dict[str, Any]]:
    """Read every stored dossier from Redis.

    Args:
        url: Redis URL.

    Returns:
        list[dict[str, Any]]: the dossiers as dicts.
    """
    client = connect(url)
    out: list[dict[str, Any]] = []
    for page_id in stored_page_ids(client):
        dossier = load_dossier(client, page_id)
        if dossier is not None:
            out.append(dossier.model_dump(mode="json"))
    return out


def _norm_label(text: str) -> str:
    """Fold a label or title to lowercase words for matching.

    Args:
        text: a title, label or Opus verdict.

    Returns:
        str: lower-case words separated by single spaces, punctuation dropped.
    """
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def find_label(labels: list[dict[str, Any]], title: str, label: str) -> dict[str, Any] | None:
    """Match a section against the labels by title and label prefix.

    Args:
        labels: label records with title, label, verdict, defect, role.
        title: the dossier title.
        label: the section label.

    Returns:
        dict[str, Any] | None: the label record, or None.
    """
    for record in labels:
        if record["title"] == title and _norm_label(label).startswith(_norm_label(record["label"])):
            return record
    return None


def evaluate(dossiers: list[dict[str, Any]], labels: list[dict[str, Any]]) -> list[Row]:
    """Run the rules over every done summary whose source can be rebuilt.

    A summary stored without input_chunk_ids has no known source and is skipped.

    Args:
        dossiers: dossiers as dicts.
        labels: label records; may be empty.

    Returns:
        list[Row]: one Row per done summary.
    """
    rows: list[Row] = []
    for dossier in dossiers:
        title = dossier["topic"]["title"]
        page_id = dossier["topic"]["page_id"]
        chunks = {c["id"]: c for c in dossier["chunks"]}
        for section in dossier["sections"]:
            summary = section.get("summary")
            if section["summary_state"] != "done" or not summary:
                continue
            if not summary.get("input_chunk_ids"):
                continue
            heading = (section.get("heading_path") or [section["label"]])[-1]
            row = Row(page_id, title, section["id"], section["label"], "done")
            row.failures = check(section["summary"]["text"], source_text(section, chunks), heading)
            record = find_label(labels, title, section["label"])
            if record:
                row.verdict, row.defect, row.role = (
                    record["verdict"],
                    record.get("defect", ""),
                    record.get("role", ""),
                )
            rows.append(row)
    return rows


def hard(row: Row) -> bool:
    """Tell whether any failure of a row is hard.

    Args:
        row: an evaluated summary.

    Returns:
        bool: True when the summary would be withheld.
    """
    return any(f.severity == "hard" for f in row.failures)


def print_table(rows: list[Row], show_all: bool) -> None:
    """Print one line per summary: page, section, state, verdict, failed rules.

    Args:
        rows: evaluated summaries.
        show_all: print summaries without failures too.
    """
    for row in rows:
        if not row.failures and not show_all:
            continue
        rules = ",".join(sorted({f.rule + ("." + f.sub if f.sub else "") for f in row.failures}))
        flag = "WITHHOLD" if hard(row) else ("soft" if row.failures else "ok")
        print(
            f"{row.page_id:>9} | {row.title[:26]:<26} | {row.label[:34]:<34} | {row.state} "
            f"| {row.verdict or '-':<6} | {flag:<8} | {rules}"
        )


def rule_table(rows: list[Row]) -> list[dict[str, Any]]:
    """Count, per rule and sub-rule, catches, false positives and corpus hits.

    Args:
        rows: evaluated summaries.

    Returns:
        list[dict[str, Any]]: one dict per rule key with the counts over the target,
        partly, yes and all summaries; a key is a rule id or "rule.sub".
    """
    keys = sorted(
        {f.rule for r in rows for f in r.failures}
        | {f"{f.rule}.{f.sub}" for r in rows for f in r.failures if f.sub}
    )
    groups = {
        "targets": [r for r in rows if r.role == "target"],
        "no": [r for r in rows if r.verdict == "no"],
        "partly": [r for r in rows if r.verdict == "partly"],
        "yes": [r for r in rows if r.verdict == "yes"],
        "corpus": rows,
    }
    table: list[dict[str, Any]] = []
    for key in keys:
        entry: dict[str, Any] = {"rule": key}
        for name, group in groups.items():
            entry[name] = sum(
                any(key in (f.rule, f"{f.rule}.{f.sub}") for f in r.failures) for r in group
            )
            entry[name + "_of"] = len(group)
        table.append(entry)
    return table


def main() -> int:
    """Run the check and write the JSON report.

    Returns:
        int: the process exit code, 0.
    """
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--dir", type=Path, default=None, help="directory of dossier JSON files")
    parser.add_argument("--redis", default=None, help="Redis URL; reads stored dossiers")
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--all", action="store_true", help="print unflagged summaries too")
    args = parser.parse_args()
    if args.redis:
        dossiers = load_redis(args.redis)
    else:
        dossiers = load_dir(args.dir or DEFAULT_DIR)
    labels: list[dict[str, Any]] = (
        json.loads(args.labels.read_text()) if args.labels.exists() else []
    )
    rows = evaluate(dossiers, labels)
    print_table(rows, args.all)
    withheld = sum(1 for r in rows if hard(r))
    print(
        f"\n{len(rows)} done summaries, {withheld} would be withheld, "
        f"{sum(1 for r in rows if r.failures)} flagged (hard or soft)"
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    table = rule_table(rows)
    print("\nrule | targets | no | partly | yes (false positives) | corpus")
    for e in table:
        print(
            f"{e['rule']} | {e['targets']}/{e['targets_of']} | {e['no']}/{e['no_of']} | "
            f"{e['partly']}/{e['partly_of']} | {e['yes']}/{e['yes_of']} | "
            f"{e['corpus']}/{e['corpus_of']}"
        )
    hard_rows = [r for r in rows if hard(r)]
    print(
        f"hard-withheld among targets {sum(hard(r) for r in rows if r.role == 'target')}, "
        f"yes {sum(hard(r) for r in rows if r.verdict == 'yes')}, "
        f"partly {sum(hard(r) for r in rows if r.verdict == 'partly')}, "
        f"unlabelled {sum(1 for r in hard_rows if not r.verdict)}"
    )
    report = {"rules": table, "withheld": len(hard_rows), "done": len(rows)}
    args.out.write_text(
        json.dumps({"summary": report, "rows": [asdict(r) for r in rows]}, indent=1) + "\n"
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
