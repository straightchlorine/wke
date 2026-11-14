"""Check a rendered dossier against the acceptance rules for self-contained output.

A dossier is acceptable when no passage or summary stops mid-sentence, none
sends the reader to another page, every citation marker in the Markdown names
an entry of the citation list, every citation anchor is a real heading id of
the pinned revision, and every summary cites the section it summarises.
"""

from wke.core.validate.headings import heading_map
from wke.core.validate.report import ValidationReport
from wke.core.validate.view import validate_view

__all__ = ["ValidationReport", "heading_map", "validate_view"]
