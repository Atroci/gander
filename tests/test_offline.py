"""Offline logic tests — no network, no browser, no scrapling import.

Covers the parts that can silently break: listing-id extraction, the idealista
deposit/caução filter math, cross-run dedup, and a smoke test that the package
imports, the reference adapter resolves from the registry, and the example
config parses. Run: `python -m pytest tests/` or `python tests/test_offline.py`.
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import gander.adapters  # noqa: E402  -- registers adapters
from gander.adapter import get_adapter  # noqa: E402
from gander.models import Config, Listing  # noqa: E402
from gander.store import Store  # noqa: E402
from gander.adapters.idealista import listing_id_from_url  # noqa: E402


def test_listing_id_from_url():
    assert listing_id_from_url("https://www.idealista.pt/imovel/12345678/") == "12345678"
    assert listing_id_from_url("https://www.idealista.pt/en/imovel/987654/") == "987654"
    # falls back to the last path segment when no numeric id is present
    assert listing_id_from_url("https://example.com/listings/abc") == "abc"


def _listing(desc="", price="500 €/mês", title=""):
    return Listing(listing_id="1", url="u", title=title, price=price, description=desc)


def test_deposit_filter_math():
    ad = get_adapter("idealista")

    # 2 months deposit + first month = 3x entry, over a max of 2 -> dropped
    lst = _listing("Exige 2 meses de caução.")
    ad.assess(lst, {"max_entry_multiple": 2})
    assert lst.deposit_months == "2"
    assert lst.pass_filter == "no" and "entry 3x" in lst.filter_reason

    # explicitly no deposit -> entry is 1x -> passes
    lst = _listing("Sem caução, entra já.")
    ad.assess(lst, {"max_entry_multiple": 2})
    assert lst.deposit_months == "0" and lst.pass_filter == "yes"

    # price safety net
    lst = _listing("", price="650 €/mês")
    ad.assess(lst, {"max_price": 500})
    assert lst.pass_filter == "no" and "price 650>500" in lst.filter_reason

    # shared-room detection drops when exclude_shared is on
    lst = _listing("Quarto partilhado, dois colegas.")
    ad.assess(lst, {"exclude_shared": True})
    assert "shared" in lst.flags and lst.pass_filter == "no"


def test_store_dedup():
    with tempfile.TemporaryDirectory() as d:
        store = Store(str(Path(d) / "out.csv"), str(Path(d) / ".seen.json"))
        assert store.is_new("42")
        store.add(_listing())  # listing_id "1"
        store.add(Listing(listing_id="42", url="u2"))
        assert not store.is_new("42")
        # a fresh Store reloads the seen db from disk
        again = Store(str(Path(d) / "out.csv"), str(Path(d) / ".seen.json"))
        assert not again.is_new("42")


def test_smoke_registry_and_example_config():
    ad = get_adapter("idealista")
    assert ad.name == "idealista"
    cfg = Config.load(ROOT / "config.example.yaml")
    assert cfg.searches and cfg.searches[0].site == "idealista"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
