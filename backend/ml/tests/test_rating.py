"""The rating prompt, its digit reading and the LlamaRater over a fake model."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from tests.support.fakes import FakeLlama, fake_loader
from wke_ml import rating
from wke_ml.rating import LlamaRater, PromptTooLong, RatingAbandoned, RatingUnavailable
from wke_ml.settings import Settings

# The hash of the five prompt strings the rating was measured with.
MEASURED_PROMPT_SHA256 = "f68afeb2bc1aaf3734cdeb0127500589966f47fbb7b74c20a004941e69bc6ec7"
PROMPT_FILE = Path(rating.__file__).with_name("rating_prompt.json")


@pytest.fixture
def model_file(tmp_path: Path) -> str:
    path = tmp_path / "rating-model.gguf"
    path.write_bytes(b"gguf")
    return str(path)


def _two_digit_row(first: int, second: int) -> list[float]:
    row = FakeLlama.row(favoured=None, boost=0.0)
    for digit in (first, second):
        row[10 + digit] = row[20 + digit] = 10.0
    return row


def test_prompt_strings_hash_to_the_measured_value() -> None:
    assert rating.PROMPT_SHA256 == MEASURED_PROMPT_SHA256


def test_prompt_file_holds_exactly_the_five_strings_and_is_ascii() -> None:
    raw = PROMPT_FILE.read_bytes()
    raw.decode("ascii")
    strings = json.loads(raw)

    assert list(strings) == ["system", "intro", "section", "passage", "lead_heading"]
    joined = "\n".join(strings[k] for k in strings)
    assert hashlib.sha256(joined.encode()).hexdigest() == MEASURED_PROMPT_SHA256


def test_prompt_puts_title_and_lead_before_the_stripped_passage() -> None:
    system, user = rating.prompt("Ada Lovelace", "  Ada was a mathematician.\n", "\n A passage. ")

    assert system.startswith("You rate how much a passage")
    assert 'the Wikipedia article "Ada Lovelace".' in user
    assert user.index("Lead of the article:\nAda was a mathematician.\n\n") < user.index(
        "Passage:\nA passage.\n\nHow much does a reader"
    )
    assert user.endswith("Answer with one digit: 0, 1, 2 or 3.")


# The lab's own messages (wkelab.readability.rate.prompt, variant "lead") for two items, written
# out from its output: the lead and the passage are stripped, braces and quotes stay literal.
LAB_SYSTEM = (
    "You rate how much a passage of an article matters to a reader who wants its essentials. "
    "Answer with one digit: 0, 1, 2 or 3."
)


def _lab_user(title: str, lead: str, passage: str) -> str:
    return (
        f'A reader wants the essentials of the Wikipedia article "{title}". Below are the lead of '
        "the article and then one passage of it. "
        f'Rate how much a reader who wants the essentials of "{title}" needs this passage, '
        "on this scale:\n"
        "3 = essential: the reader would miss something central to the topic without it\n"
        "2 = important: a main fact, event or idea of the topic\n"
        "1 = detail: side information that only a reader who wants more than the essentials "
        "would need\n"
        "0 = trivia: not needed by a reader who wants the essentials\n"
        "\n"
        f"Lead of the article:\n{lead}\n"
        "\n"
        f"Passage:\n{passage}\n"
        "\n"
        "How much does a reader who wants the essentials of the topic need this passage? "
        "Answer with one digit: 0, 1, 2 or 3."
    )


def test_user_prompt_is_the_labs_byte_for_byte() -> None:
    first = rating.prompt(
        "Ada Lovelace",
        "  Ada Lovelace was an English mathematician.\nShe wrote the first program.  ",
        "\n She worked with Charles Babbage on the Analytical Engine. ",
    )
    second = rating.prompt("{Braces} 'x'", "Lead one.", "Passage {with} braces: 100%.")

    assert first == (
        LAB_SYSTEM,
        _lab_user(
            "Ada Lovelace",
            "Ada Lovelace was an English mathematician.\nShe wrote the first program.",
            "She worked with Charles Babbage on the Analytical Engine.",
        ),
    )
    assert second == (
        LAB_SYSTEM,
        _lab_user("{Braces} 'x'", "Lead one.", "Passage {with} braces: 100%."),
    )


def test_prompt_keeps_braces_in_the_title_and_passage_literal() -> None:
    _, user = rating.prompt("{lead}", "L", "{passage} {0}")

    assert 'article "{lead}"' in user
    assert "Passage:\n{passage} {0}\n\n" in user


def test_digit_ids_take_the_bare_and_the_spaced_token() -> None:
    assert rating.digit_ids(FakeLlama()) == {0: [10, 20], 1: [11, 21], 2: [12, 22], 3: [13, 23]}


def test_digit_ids_accept_a_digit_with_only_a_bare_token() -> None:
    assert rating.digit_ids(FakeLlama(spaced=False))[2] == [12]


def test_digit_ids_refuse_a_digit_that_is_not_one_token() -> None:
    class NoDigits(FakeLlama):
        def tokenize(self, text: bytes, add_bos: bool = True, special: bool = False) -> list[int]:
            return [30, 31]

    with pytest.raises(ValueError, match="not a single token"):
        rating.digit_ids(NoDigits())


def test_digit_ids_refuse_two_digits_sharing_a_token() -> None:
    class Shared(FakeLlama):
        def tokenize(self, text: bytes, add_bos: bool = True, special: bool = False) -> list[int]:
            return [10]

    with pytest.raises(ValueError, match="share a token"):
        rating.digit_ids(Shared())


def test_digit_probabilities_is_the_expected_value_renormalised_among_the_digits() -> None:
    ids = rating.digit_ids(FakeLlama())

    expected, mass = rating.digit_probabilities(_two_digit_row(1, 2), ids)

    assert expected == pytest.approx(1.5)
    assert mass == pytest.approx(1.0, abs=1e-3)


def test_digit_probabilities_mass_is_the_digits_share_of_the_whole_vocabulary() -> None:
    ids = rating.digit_ids(FakeLlama())

    _, mass = rating.digit_probabilities(FakeLlama.row(favoured=None, boost=0.0), ids)

    assert mass == pytest.approx(8 / 40)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2", "2"),
        ("<think>1</think> 3", "3"),
        ("<think>never closed 1", ""),
        ("a <think></think>b", "a b"),
    ],
)
def test_strip_think_removes_closed_and_unclosed_blocks(text: str, expected: str) -> None:
    assert rating.strip_think(text) == expected


def test_generated_digit_reads_the_first_digit_after_the_think_block() -> None:
    llama = FakeLlama(generated="<think>maybe 1</think>Answer: 2")

    assert rating.generated_digit(llama, "s", "u") == 2
    assert llama.calls[0]["max_tokens"] == 8


def test_generated_digit_is_none_without_a_digit_in_the_first_80_characters() -> None:
    assert rating.generated_digit(FakeLlama(generated="x" * 80 + "2"), "s", "u") is None
    assert rating.generated_digit(FakeLlama(generated="none"), "s", "u") is None


def test_the_logits_route_scores_the_expected_digit_with_the_measured_decoding(
    model_file: str,
) -> None:
    llama = FakeLlama(_two_digit_row(1, 2))
    rater = LlamaRater(model_file, 2, 8192, fake_loader(llama))

    result = rater.rate("Title", "Lead.", " Passage. ")

    assert result.score == pytest.approx(1.5)
    assert result.fallback is False
    [call] = llama.calls
    assert call["temperature"] == 0.0
    assert call["top_p"] == 1.0
    assert call["seed"] == 0
    assert call["max_tokens"] == 1
    assert [m["role"] for m in call["messages"]] == ["system", "user"]
    assert call["messages"][1]["content"] == rating.prompt("Title", "Lead.", "Passage.")[1]


def test_a_row_with_little_digit_mass_takes_the_generated_digit(model_file: str) -> None:
    llama = FakeLlama(FakeLlama.row(favoured=None, boost=0.0), generated="2")
    rater = LlamaRater(model_file, 2, 8192, fake_loader(llama))

    result = rater.rate("T", "L", "P")

    assert (result.score, result.fallback) == (2.0, True)
    assert len(llama.calls) == 2
    assert llama.calls[1]["max_tokens"] == 8


def test_a_low_mass_row_without_a_generated_digit_scores_none(model_file: str) -> None:
    llama = FakeLlama(FakeLlama.row(favoured=None, boost=0.0), generated="no digit")
    rater = LlamaRater(model_file, 2, 8192, fake_loader(llama))

    result = rater.rate("T", "L", "P")

    assert (result.score, result.fallback) == (None, True)


def test_the_model_loads_once_on_the_first_call_and_stays(model_file: str) -> None:
    loader = fake_loader(FakeLlama())
    rater = LlamaRater(model_file, 2, 8192, loader)
    assert loader.loads == 0  # type: ignore[attr-defined]

    rater.rate("T", "L", "one")
    rater.rate("T", "L", "two")

    assert loader.loads == 1  # type: ignore[attr-defined]


def test_the_loader_gets_the_configured_path_threads_and_context(model_file: str) -> None:
    seen: list[tuple[str, int, int]] = []
    inner = fake_loader(FakeLlama())

    def loader(path: str, threads: int, n_ctx: int):  # noqa: ANN202
        seen.append((path, threads, n_ctx))
        return inner(path, threads, n_ctx)

    LlamaRater(model_file, 3, 4096, loader).rate("T", "L", "P")

    assert seen == [(model_file, 3, 4096)]


def test_the_model_file_name_is_the_rater_model(model_file: str) -> None:
    assert LlamaRater(model_file, 2, 8192).model_file == "rating-model.gguf"


@pytest.mark.parametrize("path", ["", "/nonexistent/model.gguf"])
def test_an_empty_or_missing_model_path_is_unavailable_and_loads_nothing(path: str) -> None:
    loader = fake_loader(FakeLlama())

    with pytest.raises(RatingUnavailable):
        LlamaRater(path, 2, 8192, loader).rate("T", "L", "P")

    assert loader.loads == 0  # type: ignore[attr-defined]


def test_without_llama_cpp_the_default_loader_is_unavailable(
    model_file: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "llama_cpp", None)

    with pytest.raises(RatingUnavailable, match="did not load"):
        LlamaRater(model_file, 2, 8192).rate("T", "L", "P")


def test_a_digit_the_tokenizer_cannot_hold_is_unavailable(model_file: str) -> None:
    class NoDigits(FakeLlama):
        def tokenize(self, text: bytes, add_bos: bool = True, special: bool = False) -> list[int]:
            return [30, 31]

    with pytest.raises(RatingUnavailable, match="not a single token"):
        LlamaRater(model_file, 2, 8192, fake_loader(NoDigits())).rate("T", "L", "P")


def test_a_prompt_over_the_context_is_too_long(model_file: str) -> None:
    class Overflowing(FakeLlama):
        def create_chat_completion(self, **kwargs):  # noqa: ANN003, ANN201
            raise ValueError("Requested tokens (9000) exceed context window of 8192")

    with pytest.raises(PromptTooLong, match="exceed context window"):
        LlamaRater(model_file, 2, 8192, fake_loader(Overflowing())).rate("T", "L", "P")


def test_another_value_error_from_the_model_is_not_a_too_long_prompt(model_file: str) -> None:
    class Broken(FakeLlama):
        def create_chat_completion(self, **kwargs):  # noqa: ANN003, ANN201
            raise ValueError("Unsupported role: tool")

    with pytest.raises(ValueError, match="Unsupported role"):
        LlamaRater(model_file, 2, 8192, fake_loader(Broken())).rate("T", "L", "P")


def test_importing_the_module_does_not_import_llama_cpp() -> None:
    assert "llama_cpp" not in sys.modules or sys.modules["llama_cpp"] is None


def test_build_rater_reads_the_settings(model_file: str) -> None:
    built = rating.build_rater(
        Settings(backend="stub", rating_model_path=model_file, rating_threads=3, rating_n_ctx=4096)
    )

    assert built.model_file == "rating-model.gguf"
    assert isinstance(built, LlamaRater)


def test_the_rating_settings_default_to_off() -> None:
    settings = Settings(backend="stub")

    assert (settings.rating_model_path, settings.rating_threads, settings.rating_n_ctx) == (
        "",
        2,
        8192,
    )


# --- the pod's memory limit ---

GIB = 1024**3


def _cgroup(tmp_path: Path, **files: str) -> Path:
    for name, text in files.items():
        path = tmp_path / name.replace("__", "/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


def test_the_cgroup_v2_limit_is_read(tmp_path: Path) -> None:
    assert rating.memory_limit_bytes(_cgroup(tmp_path, **{"memory.max": f"{3 * GIB}\n"})) == 3 * GIB


def test_the_cgroup_v1_limit_is_read_when_there_is_no_v2_file(tmp_path: Path) -> None:
    root = _cgroup(tmp_path, **{"memory__memory.limit_in_bytes": str(4 * GIB)})

    assert rating.memory_limit_bytes(root) == 4 * GIB


@pytest.mark.parametrize(
    "files",
    [{"memory.max": "max\n"}, {"memory__memory.limit_in_bytes": "9223372036854771712\n"}, {}],
    ids=["v2_max", "v1_unlimited", "no_cgroup"],
)
def test_no_limit_is_none(tmp_path: Path, files: dict[str, str]) -> None:
    assert rating.memory_limit_bytes(_cgroup(tmp_path, **files)) is None


def test_a_pod_limit_below_the_requirement_refuses_the_load_with_a_log_line(
    model_file: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    loader = fake_loader(FakeLlama())
    root = _cgroup(tmp_path, **{"memory.max": str(3 * GIB)})
    rater = LlamaRater(model_file, 2, 8192, loader, 9 * GIB, root)

    with pytest.raises(RatingUnavailable, match="3.0 GiB.*9.0 GiB"):
        rater.rate("T", "L", "P")

    assert loader.loads == 0  # type: ignore[attr-defined]
    assert "memory limit is 3.0 GiB" in caplog.text


@pytest.mark.parametrize(
    ("limit_gib", "loads"), [(9.5, 0), (10, 1)], ids=["9.5_refused", "10_accepted"]
)
def test_the_default_requirement_refuses_9_5_gib_and_accepts_10_gib(
    model_file: str, tmp_path: Path, limit_gib: float, loads: int
) -> None:
    loader = fake_loader(FakeLlama())
    root = _cgroup(tmp_path, **{"memory.max": str(int(limit_gib * GIB))})
    required = int(Settings(backend="stub").rating_required_memory_gib * GIB)
    rater = LlamaRater(model_file, 2, 8192, loader, required, root)

    if loads:
        rater.rate("T", "L", "P")
    else:
        with pytest.raises(RatingUnavailable, match="9.5 GiB.*10.0 GiB"):
            rater.rate("T", "L", "P")

    assert loader.loads == loads  # type: ignore[attr-defined]


def test_a_limit_that_is_big_enough_loads(model_file: str, tmp_path: Path) -> None:
    loader = fake_loader(FakeLlama())
    root = _cgroup(tmp_path, **{"memory.max": str(10 * GIB)})

    LlamaRater(model_file, 2, 8192, loader, 9 * GIB, root).rate("T", "L", "P")

    assert loader.loads == 1  # type: ignore[attr-defined]


@pytest.mark.parametrize("files", [{"memory.max": "max"}, {}], ids=["max", "no_cgroup"])
def test_a_pod_without_a_limit_goes_ahead(
    model_file: str, tmp_path: Path, files: dict[str, str]
) -> None:
    loader = fake_loader(FakeLlama())

    LlamaRater(model_file, 2, 8192, loader, 9 * GIB, _cgroup(tmp_path, **files)).rate("T", "L", "P")

    assert loader.loads == 1  # type: ignore[attr-defined]


@pytest.mark.parametrize("files", [{"memory.max": "max"}, {}], ids=["max", "no_cgroup"])
def test_a_pod_without_a_limit_logs_that_the_check_was_skipped(
    model_file: str, tmp_path: Path, files: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("WARNING", logger="wke_ml.rating"):
        LlamaRater(
            model_file, 2, 8192, fake_loader(FakeLlama()), 9 * GIB, _cgroup(tmp_path, **files)
        ).rate("T", "L", "P")

    assert "no cgroup memory limit was found" in caplog.text


def test_a_requirement_of_zero_turns_the_check_off(model_file: str, tmp_path: Path) -> None:
    loader = fake_loader(FakeLlama())
    root = _cgroup(tmp_path, **{"memory.max": "1000"})

    LlamaRater(model_file, 2, 8192, loader, 0, root).rate("T", "L", "P")

    assert loader.loads == 1  # type: ignore[attr-defined]


def test_the_refusal_is_checked_again_on_the_next_call_without_loading(
    model_file: str, tmp_path: Path
) -> None:
    loader = fake_loader(FakeLlama())
    root = _cgroup(tmp_path, **{"memory.max": str(3 * GIB)})
    rater = LlamaRater(model_file, 2, 8192, loader, 9 * GIB, root)

    for _ in range(2):
        with pytest.raises(RatingUnavailable):
            rater.rate("T", "L", "P")

    assert loader.loads == 0  # type: ignore[attr-defined]


def test_build_rater_passes_the_required_memory_of_the_settings(model_file: str) -> None:
    rater = rating.build_rater(Settings(backend="stub", rating_model_path=model_file))

    assert isinstance(rater, LlamaRater)
    assert rater._required_memory == 10 * GIB  # pyright: ignore[reportPrivateUsage]
    assert Settings(backend="stub").rating_required_memory_gib == 10.0


# --- a tokenizer that cannot carry the digits ---


def test_a_failed_tokenizer_check_does_not_load_the_model_again_on_every_call(
    model_file: str,
) -> None:
    class NoDigits(FakeLlama):
        def tokenize(self, text: bytes, add_bos: bool = True, special: bool = False) -> list[int]:
            return [30, 31]

    loader = fake_loader(NoDigits())
    rater = LlamaRater(model_file, 2, 8192, loader)

    for _ in range(3):
        with pytest.raises(RatingUnavailable, match="not a single token"):
            rater.rate("T", "L", "P")

    assert loader.loads == 1  # type: ignore[attr-defined]


# --- a call the client abandoned ---


def test_a_call_abandoned_before_it_starts_loads_nothing_and_asks_the_model_nothing(
    model_file: str,
) -> None:
    llama = FakeLlama()
    loader = fake_loader(llama)

    with pytest.raises(RatingAbandoned):
        LlamaRater(model_file, 2, 8192, loader).rate("T", "L", "P", lambda: True)

    assert loader.loads == 0  # type: ignore[attr-defined]
    assert llama.calls == []


def test_a_call_abandoned_after_the_prompt_is_read_scores_nothing(model_file: str) -> None:
    polls = iter([False, True])

    with pytest.raises(RatingAbandoned):
        LlamaRater(model_file, 2, 8192, fake_loader(FakeLlama())).rate(
            "T", "L", "P", lambda: next(polls)
        )


def test_a_call_abandoned_before_the_generated_digit_does_not_generate(model_file: str) -> None:
    llama = FakeLlama(FakeLlama.row(favoured=None, boost=0.0))
    polls = iter([False, False, True])

    with pytest.raises(RatingAbandoned):
        LlamaRater(model_file, 2, 8192, fake_loader(llama)).rate("T", "L", "P", lambda: next(polls))

    assert len(llama.calls) == 1  # the one-token read; no 8-token generation


def test_a_call_nobody_abandons_is_unchanged(model_file: str) -> None:
    result = LlamaRater(model_file, 2, 8192, fake_loader(FakeLlama())).rate(
        "T", "L", "P", lambda: False
    )

    assert result.fallback is False
