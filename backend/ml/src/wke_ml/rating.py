"""POST /v1/rate: a local model rates how much a reader who wants the essentials needs a passage.

The prompt is one fixed text (rating_prompt.json): the instruction, the article title and lead
(the same for every passage of an article, so llama.cpp reuses the evaluated prefix), then the
passage. The rating is the expected value over the probabilities of the four answer digits 0 to 3,
read at the first answer token; a row where those digits hold less than half of the probability
mass falls back to the digit the model generates.
"""

# llama_cpp is an optional group of the image and has no types here.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from wke_ml.settings import Settings

logger = logging.getLogger(__name__)

_PROMPT = json.loads(Path(__file__).with_name("rating_prompt.json").read_text(encoding="utf-8"))
SYSTEM: str = _PROMPT["system"]
INTRO: str = _PROMPT["intro"]
SECTION: str = _PROMPT["section"]
PASSAGE: str = _PROMPT["passage"]
LEAD_HEADING: str = _PROMPT["lead_heading"]
# The section and lead heading are not used by this prompt but belong to the hash.
PROMPT_SHA256 = hashlib.sha256(
    f"{SYSTEM}\n{INTRO}\n{SECTION}\n{PASSAGE}\n{LEAD_HEADING}".encode()
).hexdigest()

DIGITS = (0, 1, 2, 3)
LOW_MASS = 0.5
GENERATED_MAX_TOKENS = 8
FIRST_DIGIT = re.compile(r"[0-3]")
THINK = re.compile(r"<think>(.*?)</think>|<think>.*\Z", re.DOTALL)
MAX_PASSAGES = 8
MAX_TEXT_CHARS = 100_000
GIB = 1024**3
# A cgroup v1 limit at or above this is the "no limit" value (v2 says "max").
NO_LIMIT_BYTES = 1 << 60
CGROUP_ROOT = Path("/sys/fs/cgroup")


class RatingUnavailable(Exception):
    """The rating model is not configured, its file is missing, or it did not load."""


class RatingAbandoned(Exception):
    """The client gave up on the call, so it stops at the next point the model can be left."""


class PromptTooLong(Exception):
    """The prompt of one passage does not fit the model's context."""


class RatePassage(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)


class RateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=1000)
    lead: str = Field(max_length=MAX_TEXT_CHARS)
    passages: list[RatePassage] = Field(min_length=1, max_length=MAX_PASSAGES)


class RateResponse(BaseModel):
    model: str
    prompt_sha256: str
    scores: dict[str, float | None]
    fallback_ids: list[str]
    infer_seconds: float | None = None


@dataclass(frozen=True)
class Rating:
    """One passage's score (None when no digit came) and whether the generated digit was used."""

    score: float | None
    fallback: bool


def _never() -> bool:
    return False


class Rater(Protocol):
    """Rates one passage of an article."""

    model_file: str

    def rate(
        self, title: str, lead: str, passage: str, should_stop: Callable[[], bool] = _never
    ) -> Rating:
        """Rate one passage.

        Args:
            title: the article title.
            lead: the article lead.
            passage: the passage text.
            should_stop: polled between the model's steps; True means the client has gone.

        Returns:
            Rating: the score and whether it came from the generated digit.

        Raises:
            RatingUnavailable: the model is off, missing or failed to load.
            PromptTooLong: the prompt does not fit the context.
            RatingAbandoned: should_stop said so before the next step.
        """


def prompt(title: str, lead: str, passage: str) -> tuple[str, str]:
    """Build the system and user text of one rating call.

    Args:
        title: the article title.
        lead: the article lead.
        passage: the passage text.

    Returns:
        tuple[str, str]: the system text and the user text; the title and lead come first.
    """
    return SYSTEM, INTRO.format(title=title, lead=lead.strip()) + PASSAGE.format(
        passage=passage.strip()
    )


def _messages(system: str, user: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def strip_think(text: str) -> str:
    """Remove every think block (closed or unclosed) from a reply.

    Args:
        text: the generated reply.

    Returns:
        str: the reply without think blocks, stripped.
    """
    return THINK.sub("", text).strip()


def digit_ids(llm: Any) -> dict[int, list[int]]:
    """Find the token ids an answer digit can start with.

    Args:
        llm: the loaded model, for its tokenizer.

    Returns:
        dict[int, list[int]]: per digit the id of the bare digit and, where " 3" is a token of its
        own, of the spaced one.

    Raises:
        ValueError: a digit is not a single token, or two digits share a token.
    """
    out: dict[int, list[int]] = {}
    for digit in DIGITS:
        found: set[int] = set()
        for spelling in (str(digit), f" {digit}"):
            tokens = llm.tokenize(spelling.encode(), add_bos=False, special=False)
            if len(tokens) == 1:
                found.add(tokens[0])
        if not found:
            raise ValueError(f"the digit {digit} is not a single token for this model")
        out[digit] = sorted(found)
    if len({i for ids in out.values() for i in ids}) != sum(len(ids) for ids in out.values()):
        raise ValueError(f"two digits share a token id: {out}")
    return out


def digit_probabilities(
    scores: list[float], ids: dict[int, list[int]]
) -> tuple[float | None, float]:
    """Read one next-token logit row as the expected digit and the digits' share of the mass.

    Args:
        scores: the logits over the whole vocabulary.
        ids: the token ids of each digit.

    Returns:
        tuple[float | None, float]: the expected value over the four digits (None when they hold
        no mass) and the share of the softmax they hold.
    """
    top = max(scores)
    total = math.log(sum(math.exp(s - top) for s in scores)) + top
    p = {d: sum(math.exp(scores[i] - total) for i in tokens) for d, tokens in ids.items()}
    mass = sum(p.values())
    expected = sum(d * x for d, x in p.items()) / mass if mass > 0 else None
    return expected, mass


def generated_digit(llm: Any, system: str, user: str) -> int | None:
    """Generate a short reply and take its first digit 0 to 3.

    Args:
        llm: the loaded model.
        system: the system text.
        user: the user text.

    Returns:
        int | None: the digit, or None when the first 80 characters hold none.
    """
    reply = llm.create_chat_completion(
        messages=_messages(system, user),
        temperature=0.0,
        top_p=1.0,
        seed=0,
        max_tokens=GENERATED_MAX_TOKENS,
    )
    found = FIRST_DIGIT.search(strip_think(reply["choices"][0]["message"]["content"] or "")[:80])
    return int(found.group(0)) if found else None


def memory_limit_bytes(root: Path = CGROUP_ROOT) -> int | None:
    """Read the memory limit of this container's cgroup.

    Args:
        root: the cgroup mount; v2's memory.max is read first, then v1's limit_in_bytes.

    Returns:
        int | None: the limit in bytes, None when there is none or it cannot be read.
    """
    for name in ("memory.max", "memory/memory.limit_in_bytes"):
        try:
            text = (root / name).read_text().strip()
        except OSError:
            continue
        if text.isdigit() and int(text) < NO_LIMIT_BYTES:
            return int(text)
        return None
    return None


def load_llama(model_path: str, threads: int, n_ctx: int) -> tuple[Any, type[list[Any]]]:
    """Load the GGUF model; the only place llama_cpp is imported.

    Args:
        model_path: the GGUF file.
        threads: threads for prompt processing and generation.
        n_ctx: the context size in tokens.

    Returns:
        tuple: the loaded model and llama_cpp's LogitsProcessorList class.

    Raises:
        RatingUnavailable: llama_cpp is not installed or the file did not load.
    """
    try:
        import llama_cpp

        llm = llama_cpp.Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_threads=threads,
            n_threads_batch=threads,
            seed=0,
            verbose=False,
        )
    except Exception as exc:
        raise RatingUnavailable(f"rating model did not load: {exc!r}") from exc
    return llm, llama_cpp.LogitsProcessorList


class LlamaRater:
    """Rates with a GGUF model loaded on the first call and kept resident."""

    def __init__(
        self,
        model_path: str,
        threads: int,
        n_ctx: int,
        loader: Callable[[str, int, int], tuple[Any, type[list[Any]]]] = load_llama,
        required_memory_bytes: int = 0,
        cgroup_root: Path = CGROUP_ROOT,
    ) -> None:
        self._model_path = model_path
        self._threads = threads
        self._n_ctx = n_ctx
        self._loader = loader
        self._required_memory = required_memory_bytes
        self._cgroup_root = cgroup_root
        self._loaded: tuple[Any, type[list[Any]], dict[int, list[int]]] | None = None
        # Set when the loaded model's tokenizer cannot carry the digits; the model is then dropped.
        self._unusable: str | None = None
        self.model_file = Path(model_path).name

    def _check_memory(self) -> None:
        limit = memory_limit_bytes(self._cgroup_root)
        if self._required_memory and limit is None:
            logger.warning("rating model memory check skipped: no cgroup memory limit was found")
        if self._required_memory and limit is not None and limit < self._required_memory:
            message = (
                f"rating model not loaded: the memory limit is {limit / GIB:.1f} GiB and "
                f"it needs {self._required_memory / GIB:.1f} GiB; raise the pod limit first"
            )
            logger.error(message)
            raise RatingUnavailable(message)

    def _load(self) -> tuple[Any, type[list[Any]], dict[int, list[int]]]:
        if self._unusable is not None:
            raise RatingUnavailable(self._unusable)
        if self._loaded is None:
            if not self._model_path or not Path(self._model_path).is_file():
                raise RatingUnavailable("no rating model file is configured or it is missing")
            self._check_memory()
            llm, processors = self._loader(self._model_path, self._threads, self._n_ctx)
            try:
                ids = digit_ids(llm)
            except ValueError as exc:
                self._unusable = str(exc)
                logger.error("rating model unusable, not loading it again: %s", exc)
                raise RatingUnavailable(self._unusable) from exc
            self._loaded = (llm, processors, ids)
            logger.info("rating model loaded: %s", self.model_file)
        return self._loaded

    def rate(
        self, title: str, lead: str, passage: str, should_stop: Callable[[], bool] = _never
    ) -> Rating:
        """Rate one passage; see Rater.rate.

        Args:
            title: the article title.
            lead: the article lead.
            passage: the passage text.
            should_stop: polled before the load, after the prompt is evaluated and before the
                generated digit; the prompt evaluation itself cannot be interrupted.

        Returns:
            Rating: the expected digit, or the generated digit when the digits hold too little mass.

        Raises:
            RatingUnavailable: the model is off, missing, too big for the pod or failed to load.
            PromptTooLong: the prompt does not fit the context.
            RatingAbandoned: should_stop said so at one of those points.
        """
        if should_stop():
            raise RatingAbandoned()
        llm, processors, ids = self._load()
        system, user = prompt(title, lead, passage)
        grabbed: list[list[float]] = []

        def grab(_input_ids: Any, scores: Any) -> Any:
            if should_stop():
                raise RatingAbandoned()
            grabbed.append([float(x) for x in scores])
            return scores

        try:
            llm.create_chat_completion(
                messages=_messages(system, user),
                temperature=0.0,
                top_p=1.0,
                seed=0,
                max_tokens=1,
                logits_processor=processors([grab]),
            )
        except ValueError as exc:
            # llama_cpp's wording (Llama._create_completion); another ValueError is not a 422.
            if "exceed context window" not in str(exc):
                raise
            raise PromptTooLong(str(exc)) from exc
        expected, mass = digit_probabilities(grabbed[0], ids)
        if expected is not None and mass >= LOW_MASS:
            return Rating(expected, False)
        if should_stop():
            raise RatingAbandoned()
        digit = generated_digit(llm, system, user)
        return Rating(None if digit is None else float(digit), True)


def build_rater(settings: Settings) -> Rater:
    """Construct the rater; nothing is loaded until its first call.

    Args:
        settings: service settings.

    Returns:
        Rater: a LlamaRater over WKE_ML_RATING_MODEL_PATH.
    """
    return LlamaRater(
        settings.rating_model_path,
        settings.rating_threads,
        settings.rating_n_ctx,
        required_memory_bytes=int(settings.rating_required_memory_gib * GIB),
    )
