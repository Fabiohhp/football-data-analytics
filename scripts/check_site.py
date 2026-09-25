"""Compare what a running preview server returns with what is on disk.

    uv run python scripts/check_site.py

Two rounds of a dashboard bug turned out not to be in the dashboard: the browser was
executing files that were not the ones in `site/`. That is invisible from the editor
and nearly invisible in the browser, so this makes it a single command.

For each page, script and stylesheet it fetches the served copy, hashes it, and
compares it with the file on disk. It also reports the `Cache-Control` header, since
a server that sends none lets a browser reuse a response without asking.

It does not start a server — point it at the one you already have running.
"""

from __future__ import annotations

import argparse
import hashlib
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE = REPO_ROOT / "site"

# One marker per file that only the current build contains, so a stale copy is named
# rather than just hashed differently.
MARKERS = {
    "index.html": 'id="kicker"',
    "team.html": 'id="kicker"',
    "players.html": 'id="kicker"',
    "shots.html": 'id="kicker"',
    "js/common.js": "checkSkeleton",
    "js/league.js": "setAnswer",
    "js/team.js": "setAnswer",
    "js/players.js": "setAnswer",
    "js/shots.js": "setAnswer",
    "css/app.css": "stale-banner",
}


def short(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:10]


def fetch(url: str) -> tuple[bytes, dict[str, str]] | None:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - localhost
            return response.read(), dict(response.headers)
    except (urllib.error.URLError, OSError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://localhost:8000", help="the running server")
    args = parser.parse_args()
    base = args.url.rstrip("/")

    probe = fetch(f"{base}/index.html")
    if probe is None:
        print(f"Nothing is answering at {base}.")
        print("Start the preview server:  uv run python scripts/serve_site.py")
        return 1

    print(f"Comparing {base}  with  {SITE}\n")
    stale: list[str] = []
    missing_marker: list[str] = []
    no_cache_header = []

    for path, marker in MARKERS.items():
        on_disk = SITE / path
        if not on_disk.exists():
            print(f"  {path:16s} NOT ON DISK")
            continue

        result = fetch(f"{base}/{path}")
        if result is None:
            print(f"  {path:16s} server returned nothing")
            stale.append(path)
            continue

        body, headers = result
        disk_bytes = on_disk.read_bytes()
        same = short(body) == short(disk_bytes)
        has_marker = marker.encode() in body

        if not headers.get("Cache-Control"):
            no_cache_header.append(path)

        if same:
            print(f"  {path:16s} ok")
        else:
            stale.append(path)
            note = "" if has_marker else f"  <- served copy has no {marker!r}"
            print(f"  {path:16s} DIFFERS   disk {short(disk_bytes)} vs served {short(body)}{note}")
            if not has_marker:
                missing_marker.append(path)

    print()
    if not stale:
        print("VERDICT: the server is serving exactly what is on disk.")
        if no_cache_header:
            print("         But it sends no Cache-Control, so your *browser* may still be")
            print("         holding older copies. Reload with Ctrl+Shift+R, or switch to")
            print("         uv run python scripts/serve_site.py, which sends no-store.")
        return 0

    print("VERDICT: the server is NOT serving the files in site/.")
    if missing_marker:
        print(f"         {len(missing_marker)} file(s) are an older build entirely.")
    print("         Most likely another server is still bound to that port, started")
    print("         from a different directory. Find and stop it, then restart:")
    print("           pkill -f http.server ; pkill -f serve_site.py")
    print("           uv run python scripts/serve_site.py")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
