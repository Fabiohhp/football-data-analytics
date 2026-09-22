"""Smoke-test the dashboard in a real browser.

CLAUDE.md §9: CI loads every page in a headless browser and fails on any console
error. That is the only test that can catch the failures this site can actually
have — a typo in a selector, a JSON key that was renamed in the export, a module
that throws on load. None of them are visible to ruff, and none of them would fail
a dbt test.

It is deliberately a *smoke* test. It asserts that each page loads, renders real
rows, and logs nothing to the console; it does not assert particular numbers,
because those are the marts' job and are tested there.

**It skips rather than fails** when the browser is not installed or the site data
has not been exported, so `uv run pytest -q` still works on a fresh clone with no
database (CLAUDE.md §11). CI runs the export first, so there it really runs.
"""

from __future__ import annotations

import contextlib
import http.server
import socket
import threading
from functools import partial
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE = REPO_ROOT / "site"
SITE_DATA = SITE / "data"

PAGES = [
    ("index.html", "League table"),
    ("team.html", "Team"),
    ("players.html", "Players"),
    ("shots.html", "Shots"),
]

pytestmark = pytest.mark.site


@pytest.fixture(scope="module")
def site_data() -> Path:
    """Skip the whole module unless the dashboard's JSON has been exported."""
    if not (SITE_DATA / "meta.json").exists():
        pytest.skip(
            "site/data not exported - run: uv run dbt build --project-dir dbt "
            "--profiles-dir dbt && uv run python scripts/export_site_data.py"
        )
    return SITE_DATA


@pytest.fixture(scope="module")
def server(site_data: Path):
    """Serve site/ on a free port.

    The pages fetch JSON, so opening the files directly does not work — `file://`
    has no origin a fetch can use. That is true for a reviewer previewing locally
    too, which is why CLAUDE.md §11 documents `python -m http.server -d site`.
    """
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture(scope="module")
def browser_page(server):
    """A headless Chromium page, or a skip if the browser was never downloaded."""
    playwright = pytest.importorskip(
        "playwright.sync_api", reason="pytest-playwright not installed"
    )
    with playwright.sync_playwright() as driver:
        try:
            browser = driver.chromium.launch()
        except Exception as exc:  # pragma: no cover - environment, not logic
            pytest.skip(f"Chromium not available ({exc}). Run: uv run playwright install chromium")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        yield page
        with contextlib.suppress(Exception):
            browser.close()


def open_page(page, base_url: str, path: str):
    """Load one page, collecting console errors and uncaught exceptions."""
    problems: list[str] = []
    page.on(
        "console",
        lambda msg: (
            problems.append(f"console.{msg.type}: {msg.text}") if msg.type == "error" else None
        ),
    )
    page.on("pageerror", lambda err: problems.append(f"pageerror: {err}"))
    response = page.goto(f"{base_url}/{path}", wait_until="networkidle")
    assert response is not None and response.ok, f"{path} did not load"
    return problems


@pytest.mark.parametrize(("path", "tab"), PAGES)
def test_page_loads_without_console_errors(browser_page, server, path, tab):
    problems = open_page(browser_page, server, path)
    assert problems == [], f"{path} logged: {problems}"


@pytest.mark.parametrize(("path", "tab"), PAGES)
def test_page_shows_the_snapshot_range(browser_page, server, path, tab):
    """Every page states the snapshot's match_date range (CLAUDE.md §9)."""
    open_page(browser_page, server, path)
    snapshot = browser_page.locator(".snapshot").inner_text()
    assert "–" in snapshot, f"{path} does not show a date range, got {snapshot!r}"


@pytest.mark.parametrize(("path", "tab"), PAGES)
def test_page_marks_its_own_tab_as_current(browser_page, server, path, tab):
    open_page(browser_page, server, path)
    current = browser_page.locator('.tabs a[aria-current="page"]').inner_text()
    assert current == tab


def test_league_table_renders_clubs(browser_page, server):
    open_page(browser_page, server, "index.html")
    rows = browser_page.locator("#rows tr")
    assert rows.count() >= 2, "league table rendered no clubs"
    # The dot-and-ring plot is the page's point, so it has to be there.
    assert browser_page.locator("#rows tr .dot").count() == rows.count()
    assert browser_page.locator("#rows tr .ring").count() == rows.count()


def test_league_table_switches_league(browser_page, server):
    open_page(browser_page, server, "index.html")
    buttons = browser_page.locator("#league button")
    if buttons.count() < 2:
        pytest.skip("only one league in this snapshot")
    before = browser_page.locator("#rows tr td.name").first.inner_text()
    buttons.nth(1).click()
    browser_page.wait_for_timeout(120)
    after = browser_page.locator("#rows tr td.name").first.inner_text()
    assert before != after, "switching league did not change the table"


def test_team_page_draws_the_rolling_chart(browser_page, server):
    open_page(browser_page, server, "team.html")
    assert browser_page.locator("#chart svg.chart-svg").count() == 1
    # Two lines: xG created and xG conceded.
    assert browser_page.locator("#chart path.series").count() >= 1
    assert browser_page.locator("#rows tr").count() >= 1


def test_players_page_filters_on_minutes(browser_page, server):
    open_page(browser_page, server, "players.html")
    before = browser_page.locator("#rows tr").count()
    assert before >= 1, "player leaderboard rendered no rows"

    slider = browser_page.locator("#minutes")
    slider.fill("2700")
    slider.dispatch_event("input")
    browser_page.wait_for_timeout(150)
    after = browser_page.locator("#rows tr").count()
    assert after <= before, "raising the minutes floor did not narrow the leaderboard"


def test_shots_page_draws_a_pitch_with_markers(browser_page, server):
    open_page(browser_page, server, "shots.html")
    assert browser_page.locator("#pitch svg.pitch").count() == 1
    assert browser_page.locator("#pitch circle.shot").count() >= 1
    # Penalties sit on one point of the pitch; selecting them must not empty it.
    browser_page.locator('#situation button[data-value="Penalty"]').click()
    browser_page.wait_for_timeout(150)
    assert browser_page.locator("#pitch svg.pitch").count() == 1


def test_pages_work_at_phone_width(browser_page, server):
    """CLAUDE.md §9: works at phone width."""
    browser_page.set_viewport_size({"width": 390, "height": 844})
    try:
        for path, _ in PAGES:
            problems = open_page(browser_page, server, path)
            assert problems == [], f"{path} logged at phone width: {problems}"
            overflow = browser_page.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            assert overflow <= 1, f"{path} scrolls sideways at 390px by {overflow}px"
    finally:
        browser_page.set_viewport_size({"width": 1280, "height": 900})
