"""DossierService: the one set of methods REST routes and MCP tools share."""

from __future__ import annotations

from wke.services.admit import AdmitMixin
from wke.services.listing import ListingMixin
from wke.services.live import LiveMixin
from wke.services.search import SearchMixin
from wke.services.trending import TrendingMixin
from wke.services.views import ViewsMixin


class DossierService(AdmitMixin, SearchMixin, ViewsMixin, TrendingMixin, ListingMixin, LiveMixin):
    """Shared read/write surface for the REST routes and MCP tools."""
