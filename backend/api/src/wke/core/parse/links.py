"""Mark the wikilinks of a paragraph so they can be read back as spans."""

from __future__ import annotations

from urllib.parse import unquote

from selectolax.lexbor import LexborNode

# Private-use code points: they survive clean_text and occur in no article.
# A link opens with LINK_START_BASE plus its index in the paragraph, so a
# mark removed by a later text edit cannot shift the titles of the others.
LINK_START_BASE = 0xE000
LINK_END_CODE = 0xF8FF
LINK_END = chr(LINK_END_CODE)
MAX_LINKS_PER_PARAGRAPH = LINK_END_CODE - LINK_START_BASE

WIKILINK_SELECTOR = "a[rel='mw:WikiLink']"
_HREF_PREFIX = "./"
# Pages that are not articles: files, categories, help (the IPA key) and the
# project, template and portal pages that navigation and notices link to.
_SKIPPED_NAMESPACES = (
    "File:",
    "Category:",
    "Special:",
    "Media:",
    "Help:",
    "Wikipedia:",
    "Template:",
    "Template talk:",
    "Portal:",
    "Talk:",
)


def link_title(anchor: LexborNode) -> str:
    """Read the target article title of a wikilink.

    Args:
        anchor: an `<a rel="mw:WikiLink">` element.

    Returns:
        str: the title decoded from the href without its fragment, with
        spaces for underscores; "" for a red link, a bare fragment link or a
        file or category link.
    """
    href = anchor.attributes.get("href") or ""
    if not href.startswith(_HREF_PREFIX) or "redlink=1" in href:
        return ""
    title = unquote(href[len(_HREF_PREFIX) :].split("#", 1)[0]).replace("_", " ").strip()
    return "" if title.startswith(_SKIPPED_NAMESPACES) else title


def mark_links(paragraph: LexborNode) -> list[str]:
    """Wrap every usable wikilink of a paragraph in start and end marks.

    Args:
        paragraph: a `<p>` element; modified in place.

    Returns:
        list[str]: the titles of the marked links in document order.
    """
    titles: list[str] = []
    for anchor in paragraph.css(WIKILINK_SELECTOR):
        title = link_title(anchor)
        if not title:
            continue
        if len(titles) == MAX_LINKS_PER_PARAGRAPH:
            break
        anchor.insert_before(chr(LINK_START_BASE + len(titles)))
        anchor.insert_after(LINK_END)
        titles.append(title)
    return titles
