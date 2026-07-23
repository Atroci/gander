#!/usr/bin/env python3
"""gander CLI.

    python -m gander                    # run with config.yaml
    python -m gander --config my.yaml
    python -m gander --no-details       # skip detail pages (fast, cards only)
    python -m gander --limit 10         # cap total listings (test runs)
    python -m gander --max-pages 1      # override config max_pages

Reads ONLY public, logged-out pages and writes a CSV for you to follow up on by
hand. It does not log in, send messages, or contact anyone. Re-runs only add
listings not seen before (deduped via the seen db).
"""
from __future__ import annotations
import argparse
import sys

from .models import Config
from .runner import run


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--no-details", action="store_true", help="skip detail pages (cards only)")
    ap.add_argument("--limit", type=int, default=None, help="cap total listings (for test runs)")
    ap.add_argument("--max-pages", type=int, default=None, help="override config max_pages")
    args = ap.parse_args(argv)

    cfg = Config.load(args.config)
    if args.no_details:
        cfg.fetch_details = False
    if args.max_pages is not None:
        cfg.max_pages = args.max_pages

    try:
        run(cfg, limit=args.limit)
    except KeyboardInterrupt:
        print("\nInterrupted — progress is saved (CSV + seen db).")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
