#!/usr/bin/env bash
# Launch a real Chrome you can attach to over CDP (backend: cdp).
#
# WHY a dedicated profile: Chrome 136+ refuses --remote-debugging-port on your
# DEFAULT profile (security mitigation). So we use an isolated profile dir. It's
# a real Chrome — you just log into the target site once; the cookies + anti-bot
# clearance persist in this profile across runs.
#
# Usage:
#   ./launch_chrome.sh                 # opens Chrome on port 9222, scout profile
#   ./launch_chrome.sh 9333            # different port
#   START_URL=https://www.idealista.pt ./launch_chrome.sh   # open a site directly
# Then, in that window:
#   1. Go to the listing site and log in (your normal account).
#   2. If an anti-bot captcha shows, solve it once by hand (you're a human).
#   3. Leave this Chrome open and run:  python -m gander
#
# Keep this window open while gander runs. Closing it ends the session.

PORT="${1:-9222}"
PROFILE="${GANDER_CHROME_PROFILE:-$HOME/.gander-chrome}"
START_URL="${START_URL:-about:blank}"
CHROME="$(command -v google-chrome || command -v google-chrome-stable || command -v chromium)"

if [ -z "$CHROME" ]; then
  echo "No Chrome/Chromium found on PATH." >&2
  exit 1
fi

mkdir -p "$PROFILE"
echo "Launching $CHROME on debug port $PORT with profile $PROFILE"
echo "Log into your listing site in the window that opens, then run: python -m gander"

exec "$CHROME" \
  --remote-debugging-port="$PORT" \
  --user-data-dir="$PROFILE" \
  --no-first-run --no-default-browser-check \
  "$START_URL"
