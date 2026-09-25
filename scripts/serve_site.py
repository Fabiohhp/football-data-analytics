"""Serve the dashboard for local preview.

    uv run python scripts/serve_site.py

**Why this exists instead of `python -m http.server -d site`.** That server sends a
`Last-Modified` header and no `Cache-Control`, so a browser is free to cache the
JavaScript heuristically and reuse it *without revalidating*. Edit a page and
reload, and you get the current HTML running the previous build's JS — which fails
in whatever way the two happen to disagree. It cost a real debugging session: the
symptom was an empty dashboard and `can't access property "textContent" ... is null`,
because the cached script still looked for an element the new markup had dropped.

So every response here carries `Cache-Control: no-store`. A preview server has no
reason to cache anything, and silently serving a stale build is far more expensive
than re-reading a few hundred kilobytes from disk.

None of this applies to a real deployment: a static host *should* cache, and the
answer there is a fingerprint in the filename, not `no-store` (CLAUDE.md §13, which
is still deciding whether the site is hosted at all).
"""

from __future__ import annotations

import argparse
import http.server
import socketserver
from functools import partial
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE = REPO_ROOT / "site"


class PreviewServer(socketserver.ThreadingTCPServer):
    """Rebind the port straight away after a restart.

    Set as a class attribute on purpose: `socketserver` reads it during `__init__`,
    so assigning it on the instance afterwards is too late to have any effect.
    """

    allow_reuse_address = True
    daemon_threads = True


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    """Serve `site/`, and tell the browser never to reuse any of it."""

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:
        # One line per request is noise while clicking around; failures are not.
        status = str(args[1]) if len(args) > 1 else ""
        if not status.startswith("2"):
            super().log_message(fmt, *args)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1", help="default is loopback only")
    args = parser.parse_args()

    if not (SITE / "data" / "meta.json").exists():
        print("site/data is empty — the pages will show a load error. Build it first:")
        print("  uv run dbt build --project-dir dbt --profiles-dir dbt")
        print("  uv run python scripts/export_site_data.py")
        print()

    handler = partial(NoCacheHandler, directory=str(SITE))
    with PreviewServer((args.host, args.port), handler) as httpd:
        print(f"Dashboard at http://{args.host}:{args.port}/  (Ctrl-C to stop)")
        print("Responses are sent no-store, so a reload always picks up your edits.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
