"""Core data model + config. Site-agnostic — no adapter imports live here.

`Listing` is the one shape every adapter fills. Fields are all optional strings,
so an adapter only populates what its site exposes; the CSV writer derives its
columns from this dataclass (see store.py), so adding a field here adds a column
everywhere with no other change.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
import yaml


@dataclass
class Listing:
    listing_id: str
    url: str
    title: str = ""
    price: str = ""
    rooms: str = ""
    size_m2: str = ""
    floor: str = ""
    location: str = ""
    description: str = ""
    advertiser: str = ""        # the real advertiser NAME shown on the ad
    owner_type: str = ""        # e.g. owner vs agency, if the site distinguishes
    phone: str = ""             # number from the contact box
    desc_contact: str = ""      # phone/whatsapp typed into the free-text description
    reference: str = ""         # the site's own ad code, if shown
    deposit_info: str = ""      # raw deposit phrase found in the description
    deposit_months: str = ""    # estimated deposit months (as string) or ""
    flags: str = ""             # ";"-joined notes an adapter chooses to attach
    pass_filter: str = ""       # "yes" / "no" after an adapter's post-filter
    filter_reason: str = ""     # why it failed (if it did)
    source_search: str = ""     # which search (config name) produced it
    site: str = ""              # which adapter produced it
    scraped_at: str = ""

    def as_row(self) -> dict:
        return asdict(self)


@dataclass
class Search:
    name: str
    url: str
    site: str = "idealista"     # which registered adapter parses this search


@dataclass
class Config:
    searches: list[Search]
    max_pages: int = 5
    fetch_details: bool = True
    delay_min: float = 6
    delay_max: float = 14
    detail_delay_min: float = 8
    detail_delay_max: float = 20
    headless: bool = True
    block_images: bool = True
    out_csv: str = "listings.csv"
    seen_db: str = ".seen.json"
    dump_html_dir: str = ""
    proxy: str = ""
    backend: str = "cdp"              # "cdp" | "stealth" | "unlocker"
    cdp_url: str = ""                 # ws://, http://, or blank to use chrome_debug_port
    chrome_debug_port: int = 9222
    unlocker: dict = field(default_factory=dict)
    filters: dict = field(default_factory=dict)   # opaque to the core; passed to the adapter
    drop_failing: bool = False        # if true, don't write rows that fail an adapter's filter

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        searches = [
            Search(name=s.get("name", s["url"]), url=s["url"], site=s.get("site", "idealista"))
            for s in raw.pop("searches", [])
        ]
        if not searches:
            raise SystemExit(
                "No searches in config. Add at least one listing-search URL under `searches:`."
            )
        valid = {
            "max_pages", "fetch_details", "delay_min", "delay_max",
            "detail_delay_min", "detail_delay_max", "headless", "block_images",
            "out_csv", "seen_db", "dump_html_dir", "proxy",
            "backend", "cdp_url", "chrome_debug_port", "unlocker",
            "filters", "drop_failing",
        }
        kwargs = {k: v for k, v in raw.items() if k in valid}
        return cls(searches=searches, **kwargs)
