"""Keep formulas as their TeX source instead of dropping them."""

from __future__ import annotations

import json
import re

from selectolax.lexbor import LexborHTMLParser, LexborNode

from wke.core.models import FormulaSpan
from wke.core.parse.cells import classes
from wke.core.parse.passage import Passage
from wke.core.text.clean import clean_text

MATH_CLASS = "mwe-math-element"
MATH_ELEMENT = f".{MATH_CLASS}"
BLOCK_CLASS = "mwe-math-element-block"
TEX_ATTRIBUTE = "data-tex"

# An inline formula that keeps its TeX is left as an element of this class
# holding the TeX as text; the prose reader marks it as a formula span.
FORMULA_CLASS = "wke-formula"
FORMULA_SELECTOR = f".{FORMULA_CLASS}"
# A display equation after keep_formulas: emptied, its TeX in TEX_ATTRIBUTE.
DISPLAY_SELECTOR = f"[{TEX_ATTRIBUTE}]"
# Shown where a formula is an image with no TeX source to quote.
FORMULA_PLACEHOLDER = "[formula]"
# Plane-15 private-use code points: clear of the link marks, kept by clean_text.
FORMULA_START = chr(0xF0000)
FORMULA_END = chr(0xF0001)

_STYLE_WRAPPER = re.compile(r"^\{\\(?:display|text|script)style\s*(?P<tex>.*)\}$", re.S)


def _authored_tex(element: LexborNode) -> str:
    """Read the TeX the editor wrote, which Parsoid keeps in data-mw.

    Args:
        element: an element with the mwe-math-element class.

    Returns:
        str: the source TeX; "" when data-mw is missing or holds none.
    """
    try:
        return str(json.loads(element.attributes.get("data-mw") or "")["body"]["extsrc"])
    except (ValueError, KeyError, TypeError):
        return ""


def formula_tex(element: LexborNode) -> str:
    """Read the TeX source of a rendered formula.

    Args:
        element: an element with the mwe-math-element class: a span holding
            hidden MathML and a fallback image, or a `<math>` element itself.

    Returns:
        str: the TeX without its `{\\displaystyle ...}` wrapper, taken from
        the MathML alttext, the fallback image's alt or, for a `<math>`
        element that carries neither, the source in data-mw; "" when none is
        set.
    """
    # css_first matches the element itself too, so a `<math>` element finds itself.
    math = element.css_first("math")
    image = element.css_first("img")
    raw = (
        (math.attributes.get("alttext") if math is not None else None)
        or (image.attributes.get("alt") if image is not None else None)
        or _authored_tex(element)
    )
    raw = (raw or "").strip()
    wrapped = _STYLE_WRAPPER.match(raw)
    # The source TeX of a multi-line environment holds newlines; prose is one line.
    return clean_text(wrapped.group("tex") if wrapped else raw)


def is_block_formula(element: LexborNode) -> bool:
    """Tell a display equation from a formula set inside a line of text.

    Args:
        element: an element with the mwe-math-element class.

    Returns:
        bool: True for a `<div>` or an element with the block class.
    """
    return element.tag == "div" or BLOCK_CLASS in classes(element)


def has_picture(element: LexborNode) -> bool:
    """Tell whether a formula element holds a rendered picture or MathML.

    Args:
        element: an element with the mwe-math-element class.

    Returns:
        bool: True when it is, or holds, an image or a math element.
    """
    return element.css_first("img, math") is not None


def is_formula_only(cell: LexborNode) -> bool:
    """Tell a table cell that holds nothing but formulas.

    Args:
        cell: a `<td>` or `<th>` element after `keep_formulas` ran.

    Returns:
        bool: True when the cell has text and the formula elements, or the
        placeholder for a formula picture, make up all of it.
    """
    text = clean_text(cell.text(separator="", strip=False))
    formulas = clean_text(
        "".join(f.text(separator="", strip=False) for f in cell.css(FORMULA_SELECTOR))
    )
    return bool(text) and text in (formulas, FORMULA_PLACEHOLDER)


def display_tex(node: LexborNode) -> str:
    """Read the TeX of a display equation standing as a block of its own.

    Parsoid renders display math as a block-class span inside a `<p>`, as a
    block `<math>` element inside an indent `<div>`, or (older output) as a
    `<div>`. keep_formulas empties each and keeps its TeX in TEX_ATTRIBUTE.

    Args:
        node: any element of a section.

    Returns:
        str: the TeX when node is a display equation, or holds exactly one
        and no text; else "".
    """
    if clean_text(node.text(separator="", strip=False)):
        return ""
    # css matches the node itself too, so an emptied display element finds itself.
    equations = node.css(DISPLAY_SELECTOR)
    return (equations[0].attributes.get(TEX_ATTRIBUTE) or "") if len(equations) == 1 else ""


def ends_with_display(paragraph: LexborNode) -> bool:
    """Tell whether a paragraph's text ends with a display equation.

    Args:
        paragraph: a `<p>` element after keep_formulas ran.

    Returns:
        bool: True when no text follows the paragraph's last display equation.
    """
    equations = paragraph.css(DISPLAY_SELECTOR)
    if not equations:
        return False
    after = equations[-1].next
    while after is not None:
        if clean_text(after.text(separator="", strip=False)):
            return False
        after = after.next
    return True


def display_equation(tex: str) -> Passage:
    """Wrap the TeX of a display equation as a passage that is one formula.

    Args:
        tex: the equation's TeX source.

    Returns:
        Passage: the TeX, covered by one formula span.
    """
    return Passage(tex, formulas=(FormulaSpan(start=0, end=len(tex)),))


def mark_formulas(paragraph: LexborNode) -> None:
    """Wrap every kept formula of a paragraph in start and end marks.

    A display equation set inside the paragraph's text gets its TeX back and
    reads in line, like an inline formula, set off by a space on each side
    (it stands on its own line on the page). Its marks go inside the element,
    so ends_with_display still holds after marking.

    Args:
        paragraph: a `<p>` element; modified in place.
    """
    for element in paragraph.css(FORMULA_SELECTOR):
        element.insert_before(FORMULA_START)
        element.insert_after(FORMULA_END)
    for element in paragraph.css(DISPLAY_SELECTOR):
        tex = element.attributes.get(TEX_ATTRIBUTE) or ""
        element.insert_child(f" {FORMULA_START}{tex}{FORMULA_END} ")


def keep_formulas(tree: LexborHTMLParser) -> None:
    """Keep each inline formula as its TeX and empty each display equation.

    An inline formula becomes a `wke-formula` element holding the TeX; one
    that is a picture without TeX becomes the placeholder text. A display
    equation stays as an empty shell that carries its TeX in an attribute,
    so the paragraph walk can append it to the paragraph before.

    Args:
        tree: the parsed document, modified in place.
    """
    for element in reversed(tree.css(MATH_ELEMENT)):
        tex = formula_tex(element)
        picture = has_picture(element)
        for child in list(element.iter(include_text=True)):
            child.decompose()
        if is_block_formula(element):
            if tex:
                element.attrs[TEX_ATTRIBUTE] = tex
        elif tex:
            element.attrs["class"] = FORMULA_CLASS
            element.insert_child(tex)
        elif picture:
            element.insert_child(FORMULA_PLACEHOLDER)
