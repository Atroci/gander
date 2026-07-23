"""Reference adapter: idealista.pt (Portugal).

This is the worked example of a gander adapter — everything site- and
country-specific lives here, behind the generic SiteAdapter interface. It also
carries idealista's Portuguese post-scrape filtering (owner-vs-agency, deposit
/caução terms, shared-room detection) that the site can't filter itself.

SELECTOR DRIFT: idealista changes its markup periodically. Every selector below
is a *list of fallbacks* tried in order. If a field starts coming back empty, run
with `dump_html_dir` set, open a saved page, and add the new selector to the
front of the relevant list. That is the only maintenance this adapter needs.
"""
from __future__ import annotations
import re
from typing import Optional
from urllib.parse import urljoin

from ..adapter import SiteAdapter
from ..models import Listing

BASE = "https://www.idealista.pt"


# ---------------------------------------------------------------------------
# generic HTML helpers (scrapling-flavored)
# ---------------------------------------------------------------------------
def _css_first(node, sel):
    try:
        hits = node.css(sel)
    except Exception:
        return None
    return hits[0] if hits else None


def _node_text(node) -> str:
    for getter in (lambda n: n.get_all_text(strip=True), lambda n: n.text):
        try:
            v = getter(node)
        except Exception:
            v = None
        if isinstance(v, str) and v.strip():
            return re.sub(r"\s+", " ", v).strip()
    return ""


def _first_text(node, selectors) -> str:
    for sel in selectors:
        hit = _css_first(node, sel)
        if hit is not None:
            txt = _node_text(hit)
            if txt:
                return txt
    return ""


def _attr(node, selectors, attr) -> str:
    for sel in selectors:
        hit = _css_first(node, sel)
        if hit is not None:
            try:
                v = hit.attrib.get(attr)
            except Exception:
                v = None
            if v:
                return v.strip()
    return ""


def listing_id_from_url(url: str) -> str:
    m = re.search(r"/imovel/(\d+)", url) or re.search(r"/(\d{6,})/?", url)
    return m.group(1) if m else url.rstrip("/").rsplit("/", 1)[-1]


def _classify_chars(chars: list[str]) -> dict:
    """idealista crams rooms / m² / floor into a flat list of spans."""
    out = {"rooms": "", "size_m2": "", "floor": ""}
    for c in chars:
        cl = c.lower()
        if not out["rooms"] and re.match(r"^t\d", cl):
            out["rooms"] = c
        elif not out["size_m2"] and ("m²" in cl or "m2" in cl):
            out["size_m2"] = c
        elif not out["floor"] and ("andar" in cl or "piso" in cl or "rés" in cl or "baixo" in cl):
            out["floor"] = c
    return out


CARD_SELECTORS = ["article.item", "article.item-multimedia-container", "div.item-info-container"]

# idealista's own support/tracking numbers — never treat these as a contact.
# (Public corporate phone lines, not personal data.)
_IDEALISTA_NUMBERS = {"211206251", "214748300", "214748364", "211201229"}


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _plausible_owner_number(s: str) -> bool:
    return _digits(s)[-9:] not in {_digits(n) for n in _IDEALISTA_NUMBERS}


def mine_contact(text: str) -> str:
    """Pull a Portuguese mobile (or whatsapp-tagged number) out of free text."""
    if not text:
        return ""
    low = text.lower()
    for m in re.finditer(r"(?:\+?351[\s.-]?)?9[1236]\d[\s.-]?\d{3}[\s.-]?\d{3}", text):
        num = m.group(0)
        if _plausible_owner_number(num):
            tag = "whatsapp " if "whats" in low else ""
            return (tag + re.sub(r"\s+", " ", num)).strip()
    return ""


# ---------------------------------------------------------------------------
# post-scrape filtering (idealista can't do these itself)
# ---------------------------------------------------------------------------
WORD_NUM = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "três": 3,
    "quatro": 4, "cinco": 5, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
}
_NUM = r"(\d+|um|uma|dois|duas|tr[êe]s|quatro|cinco)"


def _to_int(tok: str) -> int:
    return WORD_NUM.get(tok.lower(), 0)


def _price_value(price: str) -> int | None:
    digits = re.sub(r"[^\d]", "", (price or "").split("/")[0])
    return int(digits) if digits else None


def assess_deposit(desc: str) -> tuple[int | None, str]:
    """Return (estimated caução months, raw phrase). None = not stated."""
    if not desc:
        return None, ""
    low = desc.lower()
    if re.search(r"sem\s+cau[çc][aã]o", low):
        return 0, "sem caução"

    candidates: list[tuple[int, str]] = []
    for m in re.finditer(_NUM + r"\s*(?:mes(?:es)?|m[êe]s)\s*(?:de\s*)?cau[çc][aã]o", low):
        candidates.append((_to_int(m.group(1)), m.group(0)))
    for m in re.finditer(r"cau[çc][aã]o[\s:]*(?:de\s*|equivalente a\s*)?" + _NUM + r"\s*(?:mes(?:es)?|m[êe]s|rendas?)", low):
        candidates.append((_to_int(m.group(1)), m.group(0)))
    for m in re.finditer(_NUM + r"\s*rendas?\s*(?:de\s*)?cau[çc][aã]o", low):
        candidates.append((_to_int(m.group(1)), m.group(0)))

    if candidates:
        best = max(candidates, key=lambda c: c[0])
        return best[0], best[1]

    m = re.search(_NUM + r"\s*(?:rendas?|mes(?:es)?)\s*(?:adiantad|antecipad)", low)
    if m:
        return max(0, _to_int(m.group(1)) - 1), m.group(0)
    return None, ""


def detect_flags(listing: Listing) -> list[str]:
    text = f"{listing.title} {listing.description}".lower()
    flags = []
    if re.search(
        r"quarto\s+(?:partilhad|duplo|para\s+partilhar)|partilh\w*\s+(?:o\s+)?quarto"
        r"|dividir\s+(?:o\s+)?quarto|colega\s+de\s+quarto|shared\s+room",
        text,
    ):
        flags.append("shared")
    if "fiador" in text and not re.search(r"sem\s+fiador", text):
        flags.append("fiador")
    if re.search(r"primeiro\s+e\s+[uú]ltimo|1[ºo]\s+e\s+[uú]ltimo", text):
        flags.append("first+last")
    return flags


# ---------------------------------------------------------------------------
# adapter
# ---------------------------------------------------------------------------
class IdealistaAdapter(SiteAdapter):
    name = "idealista"
    search_wait_selector = "article.item"
    detail_wait_selector = "h1"

    def parse_search(self, resp, search_name: str) -> list[Listing]:
        cards = []
        for sel in CARD_SELECTORS:
            try:
                cards = resp.css(sel)
            except Exception:
                cards = []
            if cards:
                break

        listings: list[Listing] = []
        for card in cards:
            href = _attr(card, ["a.item-link", "a[href*='/imovel/']"], "href")
            if not href:
                continue
            url = urljoin(BASE, href)
            try:
                chars = [_node_text(n) for n in card.css(".item-detail-char .item-detail")]
            except Exception:
                chars = []
            chars = [c for c in chars if c]
            cls = _classify_chars(chars)

            listings.append(Listing(
                listing_id=listing_id_from_url(url),
                url=url,
                title=_first_text(card, ["a.item-link"]) or _attr(card, ["a.item-link"], "title"),
                price=_first_text(card, [".item-price", "span.item-price", ".price-row"]),
                rooms=cls["rooms"],
                size_m2=cls["size_m2"],
                floor=cls["floor"],
                description=_first_text(card, [".item-description", ".item-description p", ".ellipsis"]),
                phone=_first_text(card, [".item-not-clickable-phone", ".icon-phone + span"]),
                advertiser=_attr(card, [".logo-branding img", ".item-logo img"], "alt"),
                source_search=search_name,
            ))
        return listings

    def next_page_url(self, resp) -> Optional[str]:
        href = _attr(resp, ["a.icon-arrow-right-after", ".pagination a.next", "li.next a",
                            ".pagination .selected + li a"], "href")
        if href:
            return urljoin(BASE, href)
        return None

    def reveal_action(self, page) -> None:
        """Click idealista's 'Ver telefone' button. Best-effort: idealista shows
        the number for many *professional* listings with no login. Private owners
        usually require login (we deliberately don't), so those have no phone —
        expected, not a bug."""
        selectors = [
            "p.hidden-contact-phones_text",
            "a._mobilePhone",
            ".hidden-phone-text",
            "//*[contains(text(),'Ver telefone')]",
            "//*[contains(text(),'telefone')]",
        ]
        for sel in selectors:
            try:
                loc = page.locator(f"xpath={sel}") if sel.startswith("//") else page.locator(sel)
                if loc.count() > 0:
                    loc.first.click(timeout=3000)
                    page.wait_for_timeout(1200)
                    break
            except Exception:
                continue
        try:
            page.wait_for_timeout(800)
        except Exception:
            pass

    def parse_detail(self, resp, listing: Listing) -> None:
        listing.title = listing.title or _first_text(resp, [".main-info__title-main", "h1 .main-info__title-main", "h1"])
        listing.location = _first_text(resp, [".main-info__title-minor", ".main-info__title-block"])
        price = _first_text(resp, [".info-data-price", ".price-features__container .txt-bold", ".h3-simulated"])
        if price:
            listing.price = price
        desc = _first_text(resp, [".comment .adCommentsLanguage", ".comment p", "div.comment"])
        if desc:
            listing.description = desc
        listing.advertiser = listing.advertiser or _first_text(
            resp, [".about-advertiser-name", ".advertiser-name", ".advertiser-name-container .name"])
        listing.owner_type = _first_text(resp, [".professional-name .name"]) or listing.owner_type
        listing.reference = _first_text(resp, [".txt-ref", ".ad-reference", ".reference-container"])

        phone = _first_text(resp, ["p.hidden-contact-phones_text", "a._mobilePhone span",
                                   "._mobilePhone", ".icon-phone + span"])
        # guard against button labels ("Ligar", "Ver telefone") leaking through:
        # a real number has >=9 digits.
        if phone and len(_digits(phone)) >= 9 and _plausible_owner_number(phone):
            listing.phone = re.sub(r"\s+", " ", phone).strip()

        listing.desc_contact = mine_contact(listing.description)

    def assess(self, listing: Listing, filters: dict) -> None:
        """Annotate listing in place with deposit/flags/pass_filter/filter_reason.

        Config `filters:` keys: owner_only, exclude_shared, max_entry_multiple,
        max_price, exclude_advertisers. Nothing is silently dropped — every
        listing is annotated and (unless drop_failing) still written for audit.
        """
        F = filters or {}
        reasons: list[str] = []

        months, phrase = assess_deposit(listing.description)
        listing.deposit_info = phrase
        listing.deposit_months = "" if months is None else str(months)

        flags = detect_flags(listing)
        if "first+last" in flags:
            months = max(months or 0, 2)
        listing.flags = ";".join(flags)

        blocked = [b.lower() for b in F.get("exclude_advertisers", [])]
        if blocked:
            hay = f"{listing.advertiser} {listing.title} {listing.description}".lower()
            hit = next((b for b in blocked if b in hay), None)
            if hit:
                reasons.append(f"blocked platform ({hit})")

        if F.get("owner_only") and listing.owner_type and "particular" not in listing.owner_type.lower():
            reasons.append(f"not owner ({listing.owner_type})")

        if F.get("exclude_shared") and "shared" in flags:
            reasons.append("shared room")

        max_mult = F.get("max_entry_multiple")
        if max_mult is not None and months is not None:
            entry = 1 + months
            if entry > max_mult:
                reasons.append(f"entry {entry}x rent (>{max_mult})")

        mp = F.get("max_price")
        pv = _price_value(listing.price)
        if mp and pv and pv > mp:
            reasons.append(f"price {pv}>{mp}")

        listing.pass_filter = "no" if reasons else "yes"
        listing.filter_reason = "; ".join(reasons)
