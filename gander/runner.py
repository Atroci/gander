"""The scout loop: walk each configured search, parse cards, optionally open
detail pages, filter, and write new listings. Site knowledge lives entirely in
the adapter resolved per search — this loop is site-agnostic.
"""
from __future__ import annotations
import datetime as _dt
import random
import time

from .models import Config
from .fetch import Fetcher, Blocked
from .store import Store
from .adapter import get_adapter
from . import adapters  # noqa: F401  -- import for adapter registration side effect


def _sleep(lo: float, hi: float, label: str = ""):
    d = random.uniform(lo, hi)
    if label:
        print(f"    · waiting {d:.0f}s {label}")
    time.sleep(d)


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def run(cfg: Config, *, limit: int | None = None) -> int:
    with Fetcher(cfg) as fetcher:
        return _run(cfg, fetcher, limit=limit)


def _run(cfg: Config, fetcher: Fetcher, *, limit: int | None) -> int:
    store = Store(cfg.out_csv, cfg.seen_db)
    total_written = 0
    kept = 0
    dropped = 0
    page_idx = 0

    for search in cfg.searches:
        adapter = get_adapter(search.site)
        print(f"\n=== Search [{search.site}]: {search.name} ===")
        url = search.url
        for page_num in range(1, cfg.max_pages + 1):
            if limit is not None and total_written >= limit:
                break
            print(f"  [page {page_num}] {url}")
            try:
                resp = fetcher.get(
                    url,
                    wait_selector=adapter.search_wait_selector,
                    dump_name=f"search_{page_idx:03d}.html",
                )
            except Blocked as e:
                print(f"  ! {e}")
                break
            page_idx += 1

            listings = adapter.parse_search(resp, search.name)
            print(f"    found {len(listings)} cards")
            if not listings:
                print("    (0 cards — markup may have changed; set dump_html_dir and inspect)")

            for lst in listings:
                if limit is not None and total_written >= limit:
                    break
                if not store.is_new(lst.listing_id):
                    continue  # already have it from a previous run
                lst.site = search.site

                # Cheap card-level filter FIRST (from the card text) so we don't
                # waste a detail page-load on obvious rejects.
                adapter.assess(lst, cfg.filters)
                if lst.pass_filter == "no":
                    dropped += 1
                    lst.scraped_at = _now()
                    if cfg.drop_failing:
                        store.seen.add(lst.listing_id)
                    else:
                        store.add(lst)
                    print(f"    ✗ {lst.price or '?':>10} | (card) {' '*5}| "
                          f"{lst.title[:42]}   [drop: {lst.filter_reason}]")
                    continue

                # Passed the cheap checks → open the detail page for the fuller
                # data and contact, then re-assess.
                if cfg.fetch_details:
                    _sleep(cfg.detail_delay_min, cfg.detail_delay_max, "before detail page")
                    try:
                        dresp = fetcher.get(
                            lst.url,
                            wait_selector=adapter.detail_wait_selector,
                            page_action=adapter.reveal_action,
                            dump_name=f"detail_{lst.listing_id}.html",
                        )
                        adapter.parse_detail(dresp, lst)
                    except Blocked as e:
                        print(f"    ! detail blocked for {lst.listing_id}: {e}")
                    adapter.assess(lst, cfg.filters)

                lst.scraped_at = _now()
                passed = lst.pass_filter != "no"
                if passed:
                    kept += 1
                else:
                    dropped += 1
                if not passed and cfg.drop_failing:
                    store.seen.add(lst.listing_id)  # remember so we don't re-fetch
                    continue
                store.add(lst)
                total_written += 1

                mark = "✓" if passed else "✗"
                contact = lst.phone or lst.desc_contact or "no phone"
                tag = f"{lst.price or '?':>10} | {(lst.owner_type or '?'):<11} | {contact:<16}"
                line = f"    {mark} {tag} | {lst.title[:42]}"
                if not passed:
                    line += f"   [drop: {lst.filter_reason}]"
                print(line)

            nxt = adapter.next_page_url(resp)
            if not nxt or nxt == url:
                print("    (no next page)")
                break
            url = nxt
            _sleep(cfg.delay_min, cfg.delay_max, "before next page")

    print(f"\nDone. {kept} matched your filters, {dropped} dropped. "
          f"Wrote {total_written} row(s) to {cfg.out_csv}"
          + (" (failures excluded)" if cfg.drop_failing else
             " — open it and filter pass_filter=yes; dropped rows kept for audit."))
    return total_written
