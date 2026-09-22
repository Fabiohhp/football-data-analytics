/* Shared helpers for all four pages.
 *
 * The one rule this file exists to make easy: **no metric logic in JavaScript**
 * (CLAUDE.md §9). Everything here loads, picks, sorts, formats or draws. Nothing
 * sums or averages — every number on screen was computed by a tested dbt model and
 * written out by scripts/export_site_data.py. If a page needs a figure that is not
 * in the JSON, the answer is a new mart, not a loop with a running total.
 *
 * Plain ES modules, no build step, no framework, no bundler.
 */

/* --- tiny DOM helpers ---------------------------------------------------- */

export const $ = (id) => document.getElementById(id);

export function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

/* --- loading ------------------------------------------------------------- */

/** Fetch one JSON file from site/data, with an error a reader can act on. */
export async function loadJSON(path) {
  const response = await fetch(`data/${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Could not load data/${path} (${response.status})`);
  }
  return response.json();
}

/**
 * Show a failure in the page instead of only in the console.
 *
 * The usual cause is the export not having been run, or the file being opened
 * directly rather than through a local server — so the message says both.
 */
export function showError(container, error) {
  const box = el("div", "state error");
  box.append(el("p", "", error.message));
  const hint = el("code", "");
  hint.textContent =
    "uv run dbt build --project-dir dbt --profiles-dir dbt && " +
    "uv run python scripts/export_site_data.py && uv run python -m http.server -d site";
  box.append(hint);
  container.replaceChildren(box);
  console.error(error);
}

/* --- formatting ---------------------------------------------------------- */

/** "+2.1" / "−3.4" / "±0.0" — a true minus sign, and always a sign. */
export function signed(value, places = 1) {
  if (value === null || value === undefined) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "±";
  return sign + Math.abs(value).toFixed(places);
}

/** A number, or an em dash when it is null — which is never the same as zero. */
export function num(value, places = 0) {
  if (value === null || value === undefined) return "—";
  return value.toFixed(places);
}

/** Which way a gap points. The dead band keeps near-zero gaps visually neutral. */
export function direction(gap, band = 0.5) {
  if (gap === null || gap === undefined) return "even";
  return gap >= band ? "ahead" : gap <= -band ? "behind" : "even";
}

/** "2024-08-15" -> "15 Aug 2024". Parsed as UTC so the day never shifts. */
export function prettyDate(iso) {
  if (!iso) return "—";
  const date = new Date(`${iso}T00:00:00Z`);
  return date.toLocaleDateString("en-GB", {
    day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
  });
}

/* --- page chrome --------------------------------------------------------- */

const PAGES = [
  ["index.html", "League table"],
  ["team.html", "Team"],
  ["players.html", "Players"],
  ["shots.html", "Shots"],
];

const BADGE = `
  <svg width="30" height="20" viewBox="0 0 30 20" aria-hidden="true">
    <rect x="1" y="1" width="28" height="18" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/>
    <line x1="15" y1="1" x2="15" y2="19" stroke="currentColor" stroke-width="1.6"/>
    <circle cx="15" cy="10" r="3.4" fill="none" stroke="currentColor" stroke-width="1.6"/>
  </svg>`;

/**
 * Build the top bar, including the snapshot's match_date range.
 *
 * Every page shows that range (CLAUDE.md §9): a number on this dashboard is only
 * meaningful against the export it came from, so the range is chrome, not a detail
 * tucked into a footer.
 */
export function buildTopbar(current, meta) {
  const bar = $("topbar");
  if (!bar) return;

  const brand = el("a", "brand");
  brand.href = "index.html";
  brand.setAttribute("aria-label", "Big 5 Analytics, home");
  brand.insertAdjacentHTML("afterbegin", BADGE);
  brand.append("Big 5 Analytics");

  const nav = el("nav", "tabs");
  nav.setAttribute("aria-label", "Pages");
  for (const [href, label] of PAGES) {
    const link = el("a", "", label);
    link.href = href;
    if (href === current) link.setAttribute("aria-current", "page");
    nav.append(link);
  }

  const snapshot = el("div", "snapshot");
  const range = meta.match_date_range;
  snapshot.append(
    el("span", "", "Snapshot"),
    el("span", "", `${prettyDate(range.min)} – ${prettyDate(range.max)}`),
  );

  const wrap = el("div", "wrap");
  wrap.append(brand, nav, snapshot);
  bar.replaceChildren(wrap);
}

/** The same footer on every page, naming the mart the page read. */
export function buildFooter(martName) {
  const foot = $("foot");
  if (!foot) return;
  foot.append(
    el("span", "", "Big 5 Analytics · Results from Football-Data.org, xG from Understat, via a pinned snapshot"),
    el("span", "mono", martName),
  );
}

/* --- controls ------------------------------------------------------------ */

/** A segmented pill control. `options` is [[value, label], ...]. */
export function segmented(container, options, selected, onChange) {
  container.replaceChildren(
    ...options.map(([value, label]) => {
      const button = el("button", "", label);
      button.type = "button";
      button.dataset.value = String(value);
      button.setAttribute("aria-pressed", String(value === selected));
      button.addEventListener("click", () => onChange(value));
      return button;
    }),
  );
}

export function syncSegmented(container, selected) {
  for (const button of container.children) {
    button.setAttribute("aria-pressed", String(button.dataset.value === String(selected)));
  }
}

/** Fill a <select>. `options` is [[value, label], ...]. */
export function fillSelect(select, options, selected) {
  select.replaceChildren(
    ...options.map(([value, label]) => {
      const option = el("option", "", label);
      option.value = String(value);
      option.selected = String(value) === String(selected);
      return option;
    }),
  );
}

/* --- tooltip ------------------------------------------------------------- */

const tip = () => $("tip");

/** Show a tooltip near a point. `pairs` is [[label, value], ...]. */
export function showTip(title, pairs, clientX, clientY) {
  const node = tip();
  if (!node) return;
  const grid = el("div", "tip-row");
  for (const [label, value] of pairs) {
    grid.append(el("span", "", label), el("strong", "", value));
  }
  node.replaceChildren(el("div", "tip-title", title), grid);
  node.hidden = false;

  const width = node.offsetWidth;
  const height = node.offsetHeight;
  let left = clientX + 16;
  let top = clientY - height - 12;
  if (left + width > window.innerWidth - 8) left = clientX - width - 16;
  if (top < 8) top = clientY + 16;
  node.style.left = `${Math.max(8, left)}px`;
  node.style.top = `${top}px`;
}

export function hideTip() {
  const node = tip();
  if (node) node.hidden = true;
}

window.addEventListener("scroll", hideTip, { passive: true });

/* --- SVG ----------------------------------------------------------------- */

const SVG_NS = "http://www.w3.org/2000/svg";

export function svg(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value !== null && value !== undefined) node.setAttribute(name, String(value));
  }
  return node;
}

/**
 * A linear scale, the one piece of chart maths worth naming.
 *
 * Mapping a data value onto a pixel is drawing, not a metric: it changes with the
 * width of the browser window and means nothing outside this page.
 */
export function scale(domain, range) {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const span = d1 - d0 || 1;
  return (value) => r0 + ((value - d0) / span) * (r1 - r0);
}

/** Round tick values covering [lo, hi], for an axis. */
export function ticks(lo, hi, count = 5) {
  const raw = (hi - lo) / count || 1;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? magnitude * 10;
  const out = [];
  for (let value = Math.ceil(lo / step) * step; value <= hi + 1e-9; value += step) {
    out.push(Number(value.toFixed(6)));
  }
  return out;
}

/* --- shared page startup ------------------------------------------------- */

/**
 * Load meta + the league table (which every page uses for its pickers), build the
 * chrome, and hand back the data. One place for the boilerplate four pages share.
 */
export async function startPage({ page, mart, container }) {
  try {
    const [meta, leagueTable] = await Promise.all([
      loadJSON("meta.json"),
      loadJSON("league_table.json"),
    ]);
    buildTopbar(page, meta);
    buildFooter(mart);
    return { meta, leagueTable };
  } catch (error) {
    buildTopbar(page, { match_date_range: { min: null, max: null } });
    showError(container, error);
    throw error;
  }
}

/* --- picker options, derived by filtering, never by aggregating ---------- */

/** Distinct leagues present, in the conventional big-5 order. */
export function leaguesIn(rows) {
  const order = ["PL", "PD", "BL1", "SA", "FL1"];
  const present = new Set(rows.map((row) => row.league));
  return order.filter((code) => present.has(code));
}

/** Distinct seasons present, newest first. */
export function seasonsIn(rows) {
  return [...new Set(rows.map((row) => row.season))].sort().reverse();
}

/**
 * The season a page should open on: the newest **complete** one.
 *
 * The snapshot always includes a season in progress, and five matches into it every
 * figure on this dashboard is noise — a league table with a two-point spread, a
 * rolling window that has nothing in it, a per-90 leaderboard where nobody has
 * cleared the minutes floor. Opening there makes a working page look broken. The
 * in-progress season stays in every dropdown, one click away.
 */
export function defaultSeason(rows) {
  const seasons = seasonsIn(rows);
  const complete = seasons.find((season) =>
    rows.some((row) => row.season === season && row.season_complete));
  return complete ?? seasons[0];
}

/** The clubs in one league-season, already one row per club in the league table. */
export function clubsIn(rows, league, season) {
  return rows
    .filter((row) => row.league === league && row.season === season)
    .sort((a, b) => a.team.localeCompare(b.team));
}
