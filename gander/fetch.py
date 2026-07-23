"""Pluggable fetch layer.

Many listing sites sit behind an enterprise anti-bot (DataDome, Cloudflare, …).
Empirically, a fresh stealth/robot browser from a normal home IP gets a hard 403
even headful, even on the homepage — the anti-bot scores IP reputation + browser
fingerprint + challenge state, and a robot browser fails all three. Three
backends, selected in config via `backend:`

  * "cdp"      — Attach to YOUR already-running, logged-in Chrome over the
                 DevTools protocol. The site sees your real browser/session, so
                 the anti-bot lets you through. This is the recommended path.
                 Free. You launch Chrome once (see launch_chrome.sh) and log in.
  * "stealth"  — Scrapling StealthyFetcher (patchright). Needs a good residential
                 `proxy:` or a protected site will 403 you.
  * "unlocker" — Hand the URL to an anti-bot-capable unlocker API. Paid, reliable.

All backends return an object exposing `.css()` / `.get_all_text()` so the
adapter that parses the response is backend-agnostic.
"""
from __future__ import annotations
import json
import random
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from scrapling import Selector
from scrapling.fetchers import StealthyFetcher, DynamicSession

from .models import Config


class Blocked(Exception):
    """Raised when a fetch comes back looking like an anti-bot / captcha wall."""


def html_of(resp) -> str:
    for attr in ("html_content", "body", "content", "text"):
        v = getattr(resp, attr, None)
        if isinstance(v, str) and v:
            return v
    try:
        return str(resp)
    except Exception:
        return ""


def _looks_blocked(resp) -> bool:
    # IMPORTANT: text markers are unreliable — a normal page on an anti-bot-
    # protected site often preloads the anti-bot's own resources (the word
    # "captcha" can appear dozens of times on a page that loaded fine). The
    # reliable signals are the HTTP status and the page size: a block/challenge
    # wall is a tiny page (~1.5 KB), whereas a real search/detail page is 100 KB+.
    status = getattr(resp, "status", 200) or 200
    if status in (403, 405, 429) or status >= 500:
        return True
    return len(html_of(resp) or "") < 8000


def _resolve_ws(cfg: Config) -> str:
    """Turn config into a ws:// CDP debugger url. Accepts a ws url directly, an
    http url, or just a debug port to auto-discover from /json/version."""
    cdp = (cfg.cdp_url or "").strip()
    if cdp.startswith(("ws://", "wss://")):
        return cdp
    base = cdp if cdp.startswith("http") else f"http://localhost:{cfg.chrome_debug_port}"
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/json/version", timeout=5) as r:
            return json.loads(r.read())["webSocketDebuggerUrl"]
    except Exception as e:
        raise Blocked(
            f"Couldn't reach Chrome's debug endpoint at {base}. "
            "Start it first with ./launch_chrome.sh and log into the site. "
            f"({e})"
        )


class Fetcher:
    """Use as a context manager: `with Fetcher(cfg) as f: f.get(url)`."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._session = None
        self._dump_dir = Path(cfg.dump_html_dir) if cfg.dump_html_dir else None
        if self._dump_dir:
            self._dump_dir.mkdir(parents=True, exist_ok=True)

    def __enter__(self):
        if self.cfg.backend == "cdp":
            ws = _resolve_ws(self.cfg)
            print(f"  · attaching to your Chrome via CDP: {ws}")
            self._session = DynamicSession(cdp_url=ws)
            self._session.start()
        return self

    def __exit__(self, *exc):
        self._close_session()

    def _close_session(self):
        if self._session is not None:
            # close() disconnects the CDP session; it does NOT kill your browser.
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None

    def _restart_session(self):
        """Re-attach after the driven tab was closed/torn out (TargetClosedError)."""
        self._close_session()
        ws = _resolve_ws(self.cfg)
        self._session = DynamicSession(cdp_url=ws)
        self._session.start()

    # -- backends -----------------------------------------------------------
    def _fetch_cdp(self, url, wait_selector, page_action):
        return self._session.fetch(
            url,
            network_idle=True,
            timeout=60000,
            wait=2000,
            wait_selector=wait_selector,
            wait_selector_state="attached",
            page_action=page_action,
        )

    def _fetch_stealth(self, url, wait_selector, page_action):
        return StealthyFetcher.fetch(
            url,
            headless=self.cfg.headless,
            disable_resources=self.cfg.block_images,
            network_idle=True,
            google_search=True,
            timeout=60000,
            wait=2000,
            wait_selector=wait_selector,
            wait_selector_state="attached",
            page_action=page_action,
            proxy=self.cfg.proxy or None,
        )

    def _fetch_unlocker(self, url):
        u = self.cfg.unlocker
        params = dict(u.get("params", {}))
        params[u.get("url_param", "url")] = url
        endpoint = u["url"] + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(endpoint, headers=u.get("headers", {}))
        with urllib.request.urlopen(req, timeout=120) as r:
            sel = Selector(r.read().decode("utf-8", "replace"))
            try:
                sel.status = r.status
            except Exception:
                pass
            return sel

    def _fetch_once(self, url, wait_selector, page_action):
        if self.cfg.backend == "cdp":
            return self._fetch_cdp(url, wait_selector, page_action)
        if self.cfg.backend == "unlocker":
            return self._fetch_unlocker(url)
        return self._fetch_stealth(url, wait_selector, page_action)

    # -- public -------------------------------------------------------------
    def get(
        self,
        url: str,
        *,
        wait_selector: Optional[str] = None,
        page_action: Optional[Callable] = None,
        retries: int = 2,
        dump_name: Optional[str] = None,
    ):
        last = None
        for attempt in range(retries + 1):
            try:
                resp = self._fetch_once(url, wait_selector, page_action)
            except Exception as e:
                # e.g. TargetClosedError when the driven tab is closed/disrupted.
                last = None
                if attempt < retries:
                    print(f"    · fetch error ({type(e).__name__}); re-attaching and retrying…")
                    if self.cfg.backend == "cdp":
                        try:
                            self._restart_session()
                        except Exception:
                            pass
                    time.sleep(6 + random.uniform(0, 4))
                    continue
                raise Blocked(f"Fetch kept failing for {url}: {e}") from e

            if dump_name and self._dump_dir:
                (self._dump_dir / dump_name).write_text(html_of(resp), encoding="utf-8")
            if not _looks_blocked(resp):
                return resp
            last = resp
            if attempt < retries:
                back = 8 * (attempt + 1) + random.uniform(0, 6)
                print(f"    · looks blocked (status={getattr(resp,'status','?')}); "
                      f"backing off {back:.0f}s and retrying…")
                time.sleep(back)
        raise Blocked(self._block_hint(url, last))

    def _block_hint(self, url, last):
        base = (f"Blocked after retries: {url} (status={getattr(last,'status','?')}). ")
        if self.cfg.backend == "cdp":
            return base + ("Your Chrome session is being challenged. In the Chrome "
                           "window: open the site, solve the anti-bot captcha by "
                           "hand once, then re-run. Slow down if it persists.")
        if self.cfg.backend == "unlocker":
            return base + "Unlocker returned a block page — check its anti-bot / country settings."
        return base + ("backend=stealth needs a residential `proxy:`; without one a "
                       "protected site will keep 403-ing. Try backend=cdp instead.")
