"""Site adapter interface + registry.

An adapter teaches gander how to read ONE listing site: which element means the
results are ready, how to pull cards out of a search page, how to page forward,
and (optionally) how to open a detail page, reveal a hidden phone, and post-filter.

To add a site: subclass SiteAdapter in gander/adapters/<site>.py, implement the
two required methods (`parse_search`, `next_page_url`), override whichever
optional hooks the site needs, and `register()` an instance in
gander/adapters/__init__.py. The core never imports your adapter directly — it
resolves it by `name` from this registry at runtime.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional

from .models import Listing


class SiteAdapter(ABC):
    #: registry key; must match the `site:` value used in config searches.
    name: str = ""
    #: CSS selector that signals a search-results page has rendered.
    search_wait_selector: str = "body"
    #: CSS selector that signals a detail page has rendered.
    detail_wait_selector: str = "body"

    @abstractmethod
    def parse_search(self, resp, search_name: str) -> list[Listing]:
        """Extract listing cards from a rendered search-results page."""

    @abstractmethod
    def next_page_url(self, resp) -> Optional[str]:
        """Absolute URL of the next results page, or None if this is the last."""

    # -- optional hooks; defaults are no-ops --------------------------------
    def reveal_action(self, page) -> None:
        """Best-effort in-page action before reading a detail page (e.g. click a
        'show phone' button). Receives the live browser page. Optional."""
        return None

    def parse_detail(self, resp, listing: Listing) -> None:
        """Enrich `listing` in place from its rendered detail page. Optional."""
        return None

    def assess(self, listing: Listing, filters: dict) -> None:
        """Post-scrape filter the site can't do itself. Annotate `listing` in
        place (pass_filter / filter_reason / flags / …). Optional; if an adapter
        leaves this as a no-op, every listing passes."""
        if not listing.pass_filter:
            listing.pass_filter = "yes"


_REGISTRY: dict[str, SiteAdapter] = {}


def register(adapter: SiteAdapter) -> None:
    if not adapter.name:
        raise ValueError(f"{type(adapter).__name__} has no `name`")
    _REGISTRY[adapter.name] = adapter


def get_adapter(name: str) -> SiteAdapter:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise SystemExit(
            f"No adapter registered for site={name!r}. "
            f"Available: {sorted(_REGISTRY) or '(none)'}"
        )
