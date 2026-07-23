# gander

**Take a gander at listings — through your own eyes, automated.**

A polite, low-volume real-estate listing scout. You set your filters in the
browser; it walks the results, optionally opens each listing to grab whatever
contact info is *publicly* visible, and writes a CSV for **you to follow up on
by hand**.

It does **not** log in, send messages, or contact anyone. That's deliberate:
auto-messaging landlords is spammy, gets accounts banned, and usually requires
login. gander stays on the safe side of that line.

## The idea: your own browser, not a robot

Many listing sites sit behind an enterprise anti-bot (DataDome, Cloudflare, …).
A free, proxy-less *robot* browser — headless or headful, stealth or not — gets
a hard **403** from a normal home IP. The anti-bot scores IP reputation, browser
fingerprint, and challenge state, and a fresh robot browser fails all three.

gander's trick is to stop using a robot browser and drive **your own real,
logged-in Chrome** instead — the site already trusts that session. It attaches
over the DevTools protocol and runs the automation *inside* your browser. You're
not really "scraping from a bot"; it's your own eyes, automated. That's the
recommended `cdp` backend, and it's free.

### Backends (pick one in `config.yaml` → `backend:`)

- **`cdp` — attach to your real Chrome (recommended, free) ⭐**
  The anti-bot catches *bot-shaped* browsers. Your real Chrome, logged in, with
  your cookies/history/IP, passes. Launch it once, log in, leave it open:
  ```bash
  ./launch_chrome.sh          # Chrome on debug port 9222 + a scout profile
  #  → in that window: log into the site, solve any captcha once (you're human)
  python -m gander            # leave that Chrome open; gander drives your session
  ```
  Chrome 136+ blocks remote debugging on your *default* profile, so the launcher
  uses an isolated profile (`~/.gander-chrome`). Keep volume low and delays
  humane (defaults 14–36s). Don't hammer it.

- **`stealth` + a residential/mobile proxy (free-ish, fiddly)**
  A good residential/mobile proxy in the right country often gets you through
  with the bundled stealth browser. Datacenter proxies won't. Paste it into
  `proxy:`. Expect occasional challenges.

- **`unlocker` + an anti-bot-capable API (pricier, reliable)**
  Services like ZenRows, ScraperAPI, Scrape.do, Bright Data, or Oxylabs handle
  the anti-bot and return rendered HTML (~$1–3 / 1000 requests). Fill in the
  `unlocker:` block. Caveat: these APIs can't click a "show phone" button —
  phones only come through if they're already in the rendered HTML.

## Sites: one core, pluggable adapters

The core (fetch, pacing, dedup, CSV, the scout loop) is **site-agnostic**. Each
site is taught to gander by a small **adapter**. It ships with **one reference
adapter — `idealista` (idealista.pt, Portugal)** — which is also the worked
example for writing your own.

**Adding a site** = create `gander/adapters/<site>.py` with a `SiteAdapter`
subclass, implement the two required methods and whichever optional hooks the
site needs, and register it:

| Method | Required | Does |
|---|---|---|
| `parse_search(resp, name)` | ✅ | pull listing cards out of a search page |
| `next_page_url(resp)` | ✅ | the next results page, or `None` |
| `reveal_action(page)` | — | in-page click before reading a detail page (e.g. "show phone") |
| `parse_detail(resp, listing)` | — | enrich a listing from its detail page |
| `assess(listing, filters)` | — | post-scrape filtering the site can't do itself |

Then reference it per search with `site: <name>` in `config.yaml`. See
`gander/adapters/idealista.py` end to end.

## Setup

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m patchright install chromium      # browser for the stealth backend
cp config.example.yaml config.yaml         # then edit config.yaml
```

## Use

1. **Set your criteria in the browser.** Open the site, apply every filter you
   want, copy the URL.
2. Paste it under `searches:` in `config.yaml` with the matching `site:`.
3. Start your real Chrome: `./launch_chrome.sh`, log in.
4. Run:
   ```bash
   python -m gander                 # full run per config.yaml
   python -m gander --limit 5       # small test run
   python -m gander --no-details    # cards only, fast (no detail pages)
   python -m gander --max-pages 1   # override page depth
   ```

Results append to `listings.csv`, deduped by listing id via `.seen.json`, so
re-running only adds listings you haven't seen — good for a daily "what's new"
sweep. Open the CSV and filter `pass_filter=yes`; dropped rows are kept (unless
`drop_failing: true`) so you can audit the calls.

## If fields come back empty (selector drift)

Sites change their HTML. Set `dump_html_dir: "dumps"`, run once, open a saved
page, and add the new selector to the front of the relevant list in that site's
adapter. That's the only maintenance an adapter needs.

## Tests

```bash
python -m pytest tests/       # or: python tests/test_offline.py
```

Covers listing-id extraction, the idealista deposit/filter math, cross-run
dedup, and a smoke test (package imports, adapter resolves, example config
parses). The live fetch path needs a real logged-in browser and isn't unit-tested.

## Layout

```
gander/
  __main__.py       CLI (python -m gander)
  models.py         Listing + Search + Config (site-agnostic core)
  adapter.py        SiteAdapter interface + registry
  fetch.py          pluggable fetch layer (cdp | stealth | unlocker)
  store.py          CSV + cross-run dedup
  runner.py         the scout loop (adapter-driven)
  adapters/
    idealista.py    reference adapter (Portugal)
config.example.yaml searches + backend + pacing
launch_chrome.sh    starts your real Chrome on the CDP debug port
```

## Etiquette / legality

Automated access may be against a site's Terms of Service. Keep this to
**personal, low-volume** apartment hunting, logged out where possible, with
humane delays (the defaults are generous on purpose). Don't redistribute the
data. Any contact info you collect is a real person's — reach out like a human,
once. This tool exists to save you tab-flipping, not to enable spam or bulk
harvesting.

## License

MIT — see [LICENSE](LICENSE).
