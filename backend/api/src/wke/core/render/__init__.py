"""Render a packed DossierView to Markdown with structure-safe escaping."""

from wke.core.render.escape import escape_inline_markup
from wke.core.render.labels import SUMMARY_LABEL
from wke.core.render.markdown import render_markdown
from wke.core.render.view import build_view

__all__ = ["SUMMARY_LABEL", "build_view", "escape_inline_markup", "render_markdown"]
