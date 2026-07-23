"""CSV output + cross-run dedup of listing ids.

Columns are derived from the Listing dataclass, so the CSV shape follows the
model automatically — no field list to keep in sync.

# ponytail: dedup is exact-id only (one adapter's ids don't collide with
# another's in practice yet). Add cross-source fuzzy dedup when a second adapter
# makes near-duplicate listings across sites a real problem.
"""
from __future__ import annotations
import csv
import json
from dataclasses import fields
from pathlib import Path

from .models import Listing

FIELDS = [f.name for f in fields(Listing)]


class Store:
    def __init__(self, csv_path: str, seen_path: str):
        self.csv_path = Path(csv_path)
        self.seen_path = Path(seen_path)
        self.seen: set[str] = set()
        if self.seen_path.exists():
            try:
                self.seen = set(json.loads(self.seen_path.read_text()))
            except Exception:
                self.seen = set()
        self._ensure_header()

    def _ensure_header(self):
        if not self.csv_path.exists():
            with self.csv_path.open("w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=FIELDS).writeheader()

    def is_new(self, listing_id: str) -> bool:
        return listing_id not in self.seen

    def add(self, listing: Listing):
        row = {k: listing.as_row().get(k, "") for k in FIELDS}
        with self.csv_path.open("a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writerow(row)
        self.seen.add(listing.listing_id)
        self.seen_path.write_text(json.dumps(sorted(self.seen)), encoding="utf-8")
