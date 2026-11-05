"""Parser rules on small synthetic HTML snippets (the recorded fixtures stay untouched)."""

from __future__ import annotations

import pytest

from tests.factories.parsed import CITATION_ID, LEAD, REV_ID, parse_sections, texts
from wke.core.parse import parse_html
from wke.core.parse.chunks import MERGE_THRESHOLD_TOKENS, SPLIT_THRESHOLD_TOKENS
from wke.core.parse.state import MAX_CHUNKS


def test_style_link_noprint_and_empty_elements_are_dropped() -> None:
    article = parse_sections(
        "<p>a <style>.x{y:1}</style>b <link rel='x'>c"
        "<sup class='noprint Inline-Template'>[<i>citation needed</i>]</sup> d"
        "<span class='mw-empty-elt'>gone</span> end.</p>"
    )
    assert texts(article) == ["a b c d end."]


def test_cs1_maintenance_comments_are_dropped() -> None:
    """The CS1 module's maintenance notes are apparatus, not article prose.

    The page renders them as visible text with template braces in it
    ("{{cite journal}}: CS1 maint: ..."), which would read as markup residue.
    """
    article = parse_sections(
        "<p>a <span class='cs1-maint citation-comment'>"
        "<code class='cs1-code'>{{cite journal}}</code>: CS1 maint: DOI inactive (link)"
        "</span> b end.</p>"
    )
    assert texts(article) == ["a b end."]


def test_caption_paragraphs_are_dropped_but_short_sentences_stay() -> None:
    article = parse_sections(
        LEAD,
        "<p>Women</p><p>Head coach: A Head coach: B</p><p>Raiola is a Christian.</p>",
    )
    assert texts(article) == [LEAD[3:-4], "Raiola is a Christian."]


@pytest.mark.parametrize(
    ("lead", "expected"),
    [
        ("<p>Short lead</p>", ["Short lead"]),
        ("<p>Short lead</p><p>Another caption</p>", []),
    ],
    ids=["only-paragraph-kept", "two-captions-dropped"],
)
def test_a_caption_like_lead_paragraph_is_kept_only_when_it_is_the_only_one(
    lead: str, expected: list[str]
) -> None:
    assert texts(parse_sections(lead)) == expected


def test_list_captions_are_dropped_and_the_lists_kept_as_list_chunks() -> None:
    article = parse_sections(
        LEAD,
        "<p>Historical usage</p><ul><li>a</li></ul><p>Present usage:</p><ul><li>b</li></ul>",
    )
    titles = article.sections[1]
    assert titles.chunk_ids == [f"{REV_ID}:1:list0", f"{REV_ID}:1:list1"]
    assert texts(article)[1:] == ["- a", "- b"]
    assert titles.dropped_non_prose is False
    assert article.sections[0].dropped_non_prose is False


def test_lists_of_a_section_with_prose_are_counted_not_emitted() -> None:
    prose = "<p>" + "A full sentence of ordinary prose. " * 8 + "</p>"
    article = parse_sections(LEAD, f"{prose}<ul><li>a</li></ul><ol><li>b</li></ol>")
    section = article.sections[1]
    assert [c.kind for c in article.chunks if c.id in section.chunk_ids] == ["prose"]
    assert section.dropped_lists == 2
    assert section.dropped_non_prose is True


def test_nested_section_list_does_not_flag_parent() -> None:
    prose = "A full sentence of ordinary prose. " * 8
    inner = (
        "<section data-mw-section-id='2'><h3 id='Sub'>Sub</h3>"
        f"<p>{prose}</p><ul><li>x</li></ul></section>"
    )
    article = parse_sections(LEAD, f"<p>Parent prose is here.</p>{inner}")
    by_anchor = {s.anchor: s for s in article.sections}
    assert by_anchor["S1"].dropped_non_prose is False
    assert by_anchor["Sub"].dropped_non_prose is True
    assert by_anchor["Sub"].heading_path == ["Part 1"]


def test_heading_path_keeps_every_ancestor_heading() -> None:
    prose = "<p>" + "A full sentence of ordinary prose. " * 8 + "</p>"
    deep = f"<section data-mw-section-id='3'><h4 id='Deep'>Deep</h4>{prose}</section>"
    mid = f"<section data-mw-section-id='2'><h3 id='Mid'>Mid</h3>{prose}{deep}</section>"
    article = parse_sections(LEAD, f"{prose}{mid}")
    by_anchor = {s.anchor: s for s in article.sections}
    assert (by_anchor[""].heading, by_anchor[""].heading_path) == ("", [])
    assert by_anchor["S1"].heading_path == []
    assert by_anchor["Mid"].heading_path == ["Part 1"]
    assert by_anchor["Deep"].heading_path == ["Part 1", "Mid"]


def test_list_introduction_is_dropped_only_before_a_list_or_table() -> None:
    long_intro = "The word has many senses in the period. " * 3 + "These include:"
    article = parse_sections(
        LEAD,
        f"<p>Examples include:</p><ul><li>a</li></ul><p>{long_intro}</p><table></table>"
        "<p>Other uses are listed as follows:</p><p>Then prose follows here.</p>",
    )
    assert texts(article)[1:3] == [
        ("The word has many senses in the period. " * 3).strip(),
        "Then prose follows here.",
    ]


def test_table_shell_still_marks_the_intro_paragraph() -> None:
    article = parse_sections(
        LEAD, "<p>The medals were awarded as follows:</p><table><tr><td>1</td></tr></table>"
    )
    assert article.sections[1].chunk_ids == []


def test_navigation_sentences_are_removed_even_mid_paragraph() -> None:
    article = parse_sections(
        "<p>He was a lord. See also the article <a href='./Jesus_is_Lord'>Jesus is Lord</a>."
        " He later sat in the Lords.</p>"
        "<p>See also Turing machine.</p>"
        "<p>Other works cite this; you can see also the records. For a complete list of"
        " releases, see the discography.</p>"
    )
    assert texts(article) == [
        "He was a lord. He later sat in the Lords. "
        "Other works cite this; you can see also the records."
    ]


def test_blockquote_without_paragraph_is_collected_minus_citation() -> None:
    article = parse_sections(
        LEAD,
        "<p>According to Dunn,</p>"
        "<blockquote>The gospels are <i>biographies</i>.<br>Really."
        "<div class='templatequotecite'>Dunn 2003</div></blockquote>",
    )
    assert texts(article)[1].endswith("According to Dunn, The gospels are biographies. Really.")


def test_introduction_of_kept_quote_survives_the_caption_rule() -> None:
    article = parse_sections(
        LEAD, "<p>He was far from enthusiastic:</p><blockquote>No way.</blockquote>"
    )
    assert texts(article)[1] == "He was far from enthusiastic: No way."


def test_blockquote_with_paragraph_is_not_collected_twice() -> None:
    article = parse_sections(LEAD, "<blockquote><p>A quoted sentence.</p></blockquote>")
    assert texts(article) == [LEAD[3:-4], "A quoted sentence."]


def test_short_tail_joins_previous_chunk_when_total_fits() -> None:
    big = "word " * 39 + "end."
    tail = "tail " * 5 + "done."
    article = parse_sections(f"<p>{big}</p><p>{tail}</p>")
    assert len(article.chunks) == 1
    assert article.chunks[0].text == f"{big} {tail}"
    assert article.chunks[0].est_tokens <= SPLIT_THRESHOLD_TOKENS


def test_short_tail_stays_alone_when_total_would_exceed_cap() -> None:
    big = "word " * 198 + "end."
    tail = "tail " * 29 + "done."
    article = parse_sections(f"<p>{big}</p><p>{tail}</p>")
    assert [c.est_tokens for c in article.chunks][1] < MERGE_THRESHOLD_TOKENS
    assert len(article.chunks) == 2


def test_invisible_characters_and_joiners_are_stripped() -> None:
    article = parse_sections(
        "<p>Zero&#8203;width &#173;soft&#8206; a&#8205;b c&#8204;d &#65279;end.</p>"
    )
    assert texts(article) == ["Zerowidth soft ab cd end."]


def test_duplicate_passages_are_emitted_once() -> None:
    same = (
        "<p>This exact sentence occurs twice in the article text. " + "More words. " * 15 + "</p>"
    )
    article = parse_sections(LEAD, same, same)
    assert sum("occurs twice" in t for t in texts(article)) == 1


def test_intro_keeps_the_rest_of_a_short_paragraph() -> None:
    article = parse_sections(LEAD, "<p>The tower is tall. He listed them:</p><ul><li>a</li></ul>")
    assert "The tower is tall." in texts(article)
    assert "listed" not in " ".join(texts(article))


def test_intro_before_a_wrapped_list_is_dropped() -> None:
    article = parse_sections(
        LEAD,
        "<p>The works cited are the following:</p><div class='div-col'><ul><li>a</li></ul></div>"
        "<p>Other prose follows here.</p>",
    )
    assert texts(article)[1] == "Other prose follows here."


def test_intro_before_an_emptied_cladogram_is_dropped() -> None:
    article = parse_sections(
        LEAD,
        "<p>The species sits among its relatives:</p><div class='clade'><div></div></div>"
        "<p>Other prose follows here.</p>",
    )
    assert texts(article)[1] == "Other prose follows here."


def test_intro_before_a_list_behind_a_figure_is_dropped() -> None:
    after_list = parse_sections(
        LEAD,
        "<p>It looked like this:</p><figure><img src='x'></figure><ul><li>a</li></ul>"
        "<p>Then more prose follows.</p>",
    )
    assert texts(after_list)[1] == "Then more prose follows."


def test_short_intro_before_a_quote_behind_a_figure_is_not_a_caption() -> None:
    article = parse_sections(
        LEAD,
        "<p>He replied in short:</p><figure><img src='x'></figure><blockquote>No way.</blockquote>",
    )
    assert texts(article)[1] == "He replied in short: No way."


def test_intro_before_a_quote_behind_a_figure_survives() -> None:
    after_quote = parse_sections(
        LEAD,
        "<p>He wrote the following words to his friend in a long letter that year:</p>"
        "<figure><img src='x'></figure>"
        "<blockquote>No way.</blockquote>",
    )
    assert (
        "He wrote the following words to his friend in a long letter that year: No way."
        in " ".join(texts(after_quote))
    )


def test_intro_before_a_wrapper_with_prose_survives() -> None:
    article = parse_sections(
        LEAD,
        "<p>He said the following about the whole matter in a long speech to the crowd:</p>"
        "<div><p>Quote here.</p></div>",
    )
    assert texts(article)[-1].endswith("to the crowd: Quote here.")


@pytest.mark.parametrize(
    "block",
    [
        "<ul><li>a</li></ul>",
        "<table><tr><td>1</td></tr></table>",
        "<!-- a comment --><ul><li>a</li></ul>",
        "<div class='div-col'><ul><li>a</li></ul></div>",
        "<div class='clade'><div></div></div>",
    ],
    ids=["list", "table", "list-after-a-comment", "wrapped-list", "emptied-wrapper"],
)
def test_a_lead_list_introduction_is_dropped_though_the_lead_keeps_fragments(block: str) -> None:
    # Twelve words or more, so the caption rule does not drop it first.
    intro = "The parts of the subject that the lead goes on to list in full are:"
    article = parse_sections(
        f"<p>The lead is a sentence.</p><p>{intro}</p>{block}", "<p>Body is prose.</p>"
    )
    assert texts(article)[0] == "The lead is a sentence."


def test_a_long_lead_paragraph_without_a_full_stop_is_kept_not_taken_for_a_caption() -> None:
    unended = "A second lead paragraph that runs on for well over twelve words without a stop"
    article = parse_sections(
        f"<p>The lead is a sentence.</p><p>{unended}</p>", "<p>Body is prose.</p>"
    )
    assert texts(article)[0] == f"The lead is a sentence. {unended}"


def test_a_wrapper_holding_prose_is_a_quote_not_a_dropped_list() -> None:
    article = parse_sections(
        "<p>The lead is a sentence.</p><p>It reads:</p>"
        "<div><p>A quoted paragraph.</p><ul><li>a</li></ul></div>",
        "<p>Body is prose.</p>",
    )
    assert texts(article)[0] == "The lead is a sentence. It reads: A quoted paragraph."


def test_leads_only_paragraph_is_kept_even_as_an_intro() -> None:
    article = parse_sections(
        "<p>The topics covered are:</p><ul><li>a</li></ul>", "<p>Body is prose.</p>"
    )
    assert texts(article)[0] == "The topics covered are:"


def test_chunk_cap_truncates() -> None:
    paragraph = "word " * 50  # ~63 est-tokens: never merges, never splits
    paragraphs_html = "".join(f"<p>{paragraph}{i}.</p>" for i in range(MAX_CHUNKS + 100))
    html = f"<html><body><section data-mw-section-id='1'>{paragraphs_html}</section></body></html>"

    result = parse_html(html, rev_id=REV_ID, citation_id=CITATION_ID)

    assert len(result.chunks) == MAX_CHUNKS
    assert result.truncated is True


def test_an_unended_quote_at_the_end_of_a_section_is_not_joined_to_the_chunk_before() -> None:
    prose = "A full sentence of ordinary prose. " * 8
    article = parse_sections(LEAD, f"<p>{prose}</p><p>He wrote:</p><blockquote>No way</blockquote>")
    assert texts(article)[1:] == [prose.strip()]


def test_a_long_chunk_is_cut_back_to_its_last_sentence_end() -> None:
    intro = "A sentence ends here. Then " + "word " * 45 + "wrote:"
    after = "Then more prose follows here. " * 12
    article = parse_sections(
        LEAD, f"<p>{intro}</p><blockquote>No way at all</blockquote><p>{after}</p>"
    )
    assert texts(article)[1:] == ["A sentence ends here.", after.strip()]


def test_list_items_and_table_cells_carry_no_invisible_characters() -> None:
    zw = "\u200c\u200d"
    article = parse_sections(
        LEAD,
        f"<ul><li>In a novel S{zw}laughter</li><li>Another item</li></ul>",
        "<table class='wikitable'><caption>Rows</caption>"
        f"<tr><th>A{zw}</th><th>B</th></tr><tr><td>x{zw}y</td><td>z</td></tr></table>",
    )
    found = texts(article, "list") + texts(article, "table")
    assert len(found) == 2
    assert all("\u200c" not in t and "\u200d" not in t for t in found)
    assert "In a novel Slaughter" in found[0]


def test_pullquote_box_is_dropped_but_a_block_quote_stays() -> None:
    pull = (
        "<div class='quotebox pullquote floatright'><blockquote class='quotebox-quote'>"
        "<p>A scholar's striking line about the subject.</p></blockquote>"
        "<div><cite>- Academic Jane Roe (2017)</cite></div></div>"
    )
    plain = (
        "<blockquote class='templatequote'><p>An ordinary quotation set in the text.</p>"
        "</blockquote>"
    )
    text = " ".join(texts(parse_sections(LEAD, pull + plain)))
    assert "striking line" not in text and "Jane Roe" not in text
    assert "ordinary quotation" in text
