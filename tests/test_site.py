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
import sys
import threading
from functools import partial
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE = REPO_ROOT / "site"
SITE_DATA = SITE / "data"

# The preview server's handler, so the tests serve with the same no-store headers.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from serve_site import NoCacheHandler  # noqa: E402

PAGES = [
    ("index.html", "League table"),
    ("team.html", "Team"),
    ("players.html", "Players"),
    ("shots.html", "Shots"),
    ("predictions.html", "Predictions"),
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
    too, which is why CLAUDE.md §11 documents `scripts/serve_site.py`.

    It serves with that script's `NoCacheHandler`. One browser page is shared by the
    whole module, so without `no-store` Firefox revalidates a page it has already
    loaded, gets `304 Not Modified`, and `response.ok` reads that as a failed load.
    """
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    handler = partial(NoCacheHandler, directory=str(SITE))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


# Both engines. A static site's only real test is a browser, and the two disagree
# about enough to matter. The bug that prompted this was found by a reader on Firefox
# while the suite ran Chromium alone — it turned out not to be engine-specific, but
# the blind spot was real.
BROWSERS = ["chromium", "firefox"]


@pytest.fixture(scope="module", params=BROWSERS)
def browser_page(request, server):
    """A headless page, or a skip if that engine was never downloaded."""
    playwright = pytest.importorskip(
        "playwright.sync_api", reason="pytest-playwright not installed"
    )
    engine = request.param
    with playwright.sync_playwright() as driver:
        try:
            browser = getattr(driver, engine).launch()
        except Exception as exc:  # pragma: no cover - environment, not logic
            pytest.skip(
                f"{engine} not available ({type(exc).__name__}). "
                f"Run: uv run playwright install --with-deps {engine}"
            )
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        # Registered once rather than per navigation: the page is shared by the whole
        # module, so re-adding listeners on every load would stack them up.
        problems: list[str] = []
        page.on(
            "console",
            lambda msg: (
                problems.append(f"console.{msg.type}: {msg.text}") if msg.type == "error" else None
            ),
        )
        page.on("pageerror", lambda err: problems.append(f"pageerror: {err}"))
        page.problems = problems

        yield page
        with contextlib.suppress(Exception):
            browser.close()


def open_page(page, base_url: str, path: str):
    """Load one page, and return whatever it logged while doing so."""
    page.problems.clear()
    response = page.goto(f"{base_url}/{path}", wait_until="networkidle")
    assert response is not None and response.ok, f"{path} did not load"
    return page.problems


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
def test_page_answers_before_it_tabulates(browser_page, server, path, tab):
    """The top of the page says what the data shows, in a sentence.

    The point of the layout: a reader who stops after the first screen should leave
    with a finding, not with a table they have to interpret. So every page renders a
    filled-in answer line and a "what this means" block, both built from mart values.
    """
    open_page(browser_page, server, path)
    answer = browser_page.locator("#answer").inner_text().strip()
    assert len(answer) > 30, f"{path} has no answer sentence, got {answer!r}"
    assert browser_page.locator("#answer .hl").count() >= 1, f"{path} highlights no figure"

    # Compared case-insensitively: the heading is uppercased in CSS, and `inner_text`
    # returns what is rendered rather than what the markup says.
    meaning = browser_page.locator("#meaning").inner_text().strip()
    assert "what this means" in meaning.lower(), f"{path} has no explanation block"
    # Terms explain themselves rather than assuming the reader knows them.
    assert browser_page.locator("#meaning .term").count() >= 1, f"{path} defines no terms"


@pytest.mark.parametrize(("path", "tab"), PAGES)
def test_page_marks_its_own_tab_as_current(browser_page, server, path, tab):
    open_page(browser_page, server, path)
    current = browser_page.locator('.rail-nav a[aria-current="page"]').inner_text()
    assert tab in current


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


@pytest.mark.parametrize(("path", "tab"), PAGES)
def test_page_shows_how_to_read_its_visual(browser_page, server, path, tab):
    """Definitions are not enough; the page has to teach the picture.

    Each one carries a "How to read it" block: a labelled miniature drawn with the
    same marks as the real visual, and worked examples naming real rows that are on
    screen. A reader who has never seen a dot-and-ring plot should be able to read
    one after this, which a glossary alone does not achieve.
    """
    open_page(browser_page, server, path)

    guide = browser_page.locator("#guide")
    assert guide.count() == 1, f"{path} has no guide block"
    assert "how to read" in guide.inner_text().lower()

    # The miniature is drawn, and it is labelled.
    assert guide.locator("figure svg").count() == 1, f"{path} draws no example figure"
    assert guide.locator("figure svg .fig-label").count() >= 2, f"{path} labels nothing"

    # And the examples are substantial, not placeholders.
    items = guide.locator(".guide-examples li")
    assert items.count() >= 3, f"{path} gives too few worked examples"
    assert all(len(items.nth(i).inner_text()) > 40 for i in range(items.count()))


def test_league_guide_names_a_club_that_is_in_the_table(browser_page, server):
    """The worked examples must describe the rows actually on screen.

    Static prose would pass the test above while quietly describing a different
    league or season, so this checks the first example names a club in the table.
    """
    open_page(browser_page, server, "index.html")
    subject = browser_page.locator("#guide .guide-examples li b").first.inner_text()
    teams = browser_page.locator("#rows td.name").all_inner_texts()
    assert any(subject in team for team in teams), f"{subject!r} is not in this table"


def test_predictions_page_draws_forecasts_and_calibration(browser_page, server):
    """Part 3's predictions: a forecast bar per match and a calibration chart.

    Runs on whatever is in site/data/predictions — Part 3's real export locally, the
    synthetic fixture in CI (PREDICTIONS_DIR=tests/fixtures/predictions).
    """
    open_page(browser_page, server, "predictions.html")
    assert browser_page.locator("#rows tr .probbar").count() >= 3, "no forecast bars"
    assert browser_page.locator("#rows .probbar i.hit").count() >= 3, "the result is not marked"
    assert browser_page.locator("#calibration svg .cal-dot").count() >= 3, "no calibration dots"
    assert browser_page.locator("#calibration svg .cal-diagonal").count() == 1


def test_predictions_page_switches_league(browser_page, server):
    open_page(browser_page, server, "predictions.html")
    first = browser_page.locator("#rows td.name").first.inner_text()
    browser_page.locator('#league button[data-value="SA"]').click()
    browser_page.wait_for_timeout(200)
    assert browser_page.locator("#rows td.name").first.inner_text() != first


def test_predictions_page_says_where_the_prospective_test_stands(browser_page, server):
    """Before any match has been played since the freeze, the view says so —
    an answer, not an empty table."""
    open_page(browser_page, server, "predictions.html")
    browser_page.locator('#period button[data-value="prospective"]').click()
    browser_page.wait_for_timeout(200)
    answer = browser_page.locator("#answer").inner_text().strip()
    assert len(answer) > 30
    assert browser_page.locator("#answer .hl").count() >= 1
    assert browser_page.problems == []


def test_a_stale_document_says_so_instead_of_going_blank(browser_page, server):
    """The failure a reader actually hit, turned into a test.

    A browser can hold an old copy of the HTML and fetch new JavaScript. The two then
    disagree about which elements exist, and before this the symptom was a blank page
    and `can't access property "textContent" ... is null` — which tells whoever is
    looking at it nothing at all.

    Simulated by deleting the elements the scripts expect *as the document is parsed*.
    It has to be that early: module scripts are deferred, which runs them before
    `DOMContentLoaded`, so removing the elements on that event would be too late to
    stand in for a stale page.

    Runs in its own browser context, because an init script cannot be unregistered
    and would otherwise strip those elements from every test that came after.
    """
    context = browser_page.context.browser.new_context(viewport={"width": 1280, "height": 900})
    try:
        page = context.new_page()
        page.add_init_script("""
            const strip = () => {
              for (const id of ['kicker', 'answer', 'meaning']) {
                document.getElementById(id)?.remove();
              }
            };
            new MutationObserver(strip).observe(document.documentElement || document, {
              childList: true, subtree: true,
            });
            """)
        page.goto(f"{server}/index.html", wait_until="networkidle")
        page.wait_for_timeout(300)

        banner = page.locator(".stale-banner")
        assert banner.count() == 1, "a stale document rendered no warning"
        assert "out of date" in banner.inner_text().lower()

        # And the rest of the page still works: the table is the point of it.
        assert page.locator("#rows tr").count() >= 2, "the table did not survive"
    finally:
        context.close()


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
