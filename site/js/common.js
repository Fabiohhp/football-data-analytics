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
    "uv run python scripts/export_site_data.py && " +
    "uv run python scripts/serve_site.py";
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

/**
 * A 0-1 probability written as a percentage.
 *
 * A unit change on a single value, in the same family as rounding — not a derived
 * number. It exists because "0.81 xG" means nothing to a reader who has not met xG,
 * while "goes in about 81 times in a hundred" does.
 */
export function asPercent(value) {
  if (value === null || value === undefined) return "—";
  return String(Math.round(value * 100));
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

/* --- the glossary ---------------------------------------------------------
 *
 * The dashboard is full of terms a reader may not have met. Rather than a page of
 * definitions nobody opens, each term is marked up where it appears and explains
 * itself on hover or focus. Defined once here so the same words mean the same thing
 * on all four pages.
 */

export const GLOSSARY = {
  xg: ["xG — expected goals",
    "How likely a shot was to be scored, from 0 to 1, based on where and how it was taken. " +
    "A team's xG for a match is its shots added up: 2.1 xG means the chances it created " +
    "would, on average, be worth about two goals."],
  npxg: ["npxG — non-penalty expected goals",
    "The same, with penalties removed. A penalty is worth about 0.76 xG on its own, so " +
    "including them mostly measures who takes the spot kicks rather than who creates chances."],
  xpts: ["xPTS — expected points",
    "The points a club would have been expected to take from each match given both sides' " +
    "chances, added up over the season. A club on 60 points and 50 xPTS has collected ten " +
    "more than its chances were worth."],
  xa: ["xA — expected assists",
    "The expected goals of the shots a player set up. It credits the pass, not the finish."],
  ppda: ["PPDA — passes allowed per defensive action",
    "How many passes the opposition completes before this club does something to stop them. " +
    "Lower means more pressing, which is the opposite way round from most metrics."],
  per90: ["Per 90",
    "A rate, not a total: the figure a player would post over a full match. It lets a " +
    "substitute and an ever-present be compared without rewarding whoever played more."],
  percentile: ["Percentile",
    "Where this figure sits among players in the same league and season who cleared the " +
    "minutes floor. 90 means only one player in ten did better."],
  floor: ["Minutes floor",
    "The minimum minutes a player needs before appearing. Without one, somebody with " +
    "thirty minutes and a lucky goal reads as the best finisher in Europe."],
  gap: ["Points − xPTS",
    "Points actually taken, minus the points the chances were worth. Positive means a club " +
    "got more than it deserved on the balance of play — for one season, usually luck."],
  finishing: ["npG − npxG (finishing)",
    "Non-penalty goals scored, minus what those chances were worth. Positive means the " +
    "player out-scored their chances."],
  snapshot: ["Snapshot",
    "Every figure here comes from one pinned export of the warehouse, so the numbers do " +
    "not shift under you. This is the range of match dates it covers."],
};

/** Mark up a term so it explains itself. Returns a <button>, so it is keyboard-reachable. */
export function term(key, text) {
  const entry = GLOSSARY[key];
  const node = el("button", "term", text ?? (entry ? entry[0].split(" — ")[0] : key));
  node.type = "button";
  if (!entry) return node;
  const show = (x, y) => showDefinition(entry[0], entry[1], x, y);
  node.addEventListener("pointerenter", (event) => show(event.clientX, event.clientY));
  node.addEventListener("focus", () => {
    const box = node.getBoundingClientRect();
    show(box.left + box.width / 2, box.top);
  });
  node.addEventListener("pointerleave", hideTip);
  node.addEventListener("blur", hideTip);
  return node;
}

/**
 * Turn the two bits of markup the explanations use into nodes:
 * `[[xpts]]` / `[[xpts|expected points]]` become live glossary terms, and `**text**`
 * becomes bold. Built as DOM nodes rather than innerHTML so a club name containing
 * an ampersand or an apostrophe cannot turn into markup.
 */
export function withTerms(text) {
  const fragment = document.createDocumentFragment();
  let index = 0;
  const pattern = /\[\[([a-z0-9]+)(?:\|([^\]]+))?\]\]|\*\*([^*]+)\*\*/g;
  for (const match of text.matchAll(pattern)) {
    if (match.index > index) fragment.append(text.slice(index, match.index));
    fragment.append(match[3] !== undefined ? el("strong", "", match[3]) : term(match[1], match[2]));
    index = match.index + match[0].length;
  }
  if (index < text.length) fragment.append(text.slice(index));
  return fragment;
}

/* --- page chrome ----------------------------------------------------------- */

const PAGES = [
  ["index.html", "League table"],
  ["team.html", "Team"],
  ["players.html", "Players"],
  ["shots.html", "Shots"],
];

const BADGE = `
  <svg width="22" height="15" viewBox="0 0 30 20" aria-hidden="true">
    <rect x="1" y="1" width="28" height="18" rx="1" fill="none" stroke="currentColor" stroke-width="1.8"/>
    <line x1="15" y1="1" x2="15" y2="19" stroke="currentColor" stroke-width="1.8"/>
    <circle cx="15" cy="10" r="3.4" fill="none" stroke="currentColor" stroke-width="1.8"/>
  </svg>`;

const THEME_ICON = `
  <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true">
    <circle cx="8" cy="8" r="6.4" fill="none" stroke="currentColor" stroke-width="1.5"/>
    <path d="M8 1.6 A6.4 6.4 0 0 1 8 14.4 Z" fill="currentColor"/>
  </svg>`;

/**
 * The light/dark toggle.
 *
 * Dark is the default and light is the stored override, so the button only ever
 * writes an explicit choice. Every read and write is wrapped: `localStorage` throws
 * in a private window, and a theme button is not worth breaking a page over.
 */
function themeToggle() {
  const button = el("button", "theme-toggle");
  button.type = "button";
  button.insertAdjacentHTML("afterbegin", THEME_ICON);
  const caption = el("span", "", "");
  button.append(caption);

  const current = () => (document.documentElement.dataset.theme === "light" ? "light" : "dark");
  const sync = () => {
    const next = current() === "light" ? "dark" : "light";
    caption.textContent = `${next} theme`;
    button.setAttribute("aria-label", `Switch to ${next} theme`);
  };

  button.addEventListener("click", () => {
    const next = current() === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch (error) {
      /* nothing to remember it with; the choice still applies to this page */
    }
    sync();
  });

  sync();
  return button;
}

/**
 * Fill the rail's fixed parts around whatever filters the page put in it.
 *
 * The snapshot range sits here, at the foot of every page (CLAUDE.md §9): a number
 * on this dashboard only means something against the export it came from.
 */
export function buildRail(current, meta) {
  const top = $("rail-top");
  if (top) {
    const brand = el("a", "brand");
    brand.href = "index.html";
    brand.setAttribute("aria-label", "Big 5 Analytics, home");
    brand.insertAdjacentHTML("afterbegin", BADGE);
    brand.append("Big 5 Analytics");

    const nav = el("nav", "rail-nav");
    nav.setAttribute("aria-label", "Pages");
    PAGES.forEach(([href, label], index) => {
      const link = el("a", "");
      link.href = href;
      link.append(el("span", "idx", String(index + 1).padStart(2, "0")), label);
      if (href === current) link.setAttribute("aria-current", "page");
      nav.append(link);
    });
    top.replaceChildren(brand, nav);
  }

  const foot = $("rail-foot");
  if (foot) {
    const range = meta.match_date_range;
    const snapshot = el("div", "snapshot");
    snapshot.append(el("b", "", "Snapshot"));
    snapshot.append(term("snapshot", `${prettyDate(range.min)} – ${prettyDate(range.max)}`));
    foot.replaceChildren(snapshot, themeToggle());
  }
}

/** The same footer on every page, naming the mart the page read. */
export function buildFooter(martName) {
  const foot = $("foot");
  if (!foot) return;
  foot.append(
    el("span", "", "Results from Football-Data.org \u00b7 xG from Understat \u00b7 pinned snapshot"),
    el("span", "mono", martName),
  );
}

/**
 * The top of the inverted pyramid: what happened, then what it means.
 *
 * `sentence` is built from mart columns by the page and may contain `[[term]]`
 * markers; `paragraphs` explain the metric in plain words. Nothing here computes a
 * number — the page passes values that a tested model produced (CLAUDE.md §9).
 */
export function setAnswer({ kicker, sentence, meaning = [], caveat = null }) {
  // Every lookup is guarded. A page that is missing one of these should lose that
  // one element, not throw halfway through `render()` and leave the table, the
  // footer and everything after it unwritten — which is exactly what an unguarded
  // `$("kicker").textContent` did, and it took a screenshot from a reader to find.
  const heading = $("kicker");
  if (heading && kicker !== undefined) heading.textContent = kicker;

  const line = $("answer");
  if (line && sentence !== undefined) line.replaceChildren(sentence);

  const box = $("meaning");
  if (!box) return;
  const parts = [el("h2", "", "What this means")];
  for (const text of meaning) {
    const p = el("p", "");
    p.append(withTerms(text));
    parts.push(p);
  }
  if (caveat) {
    const p = el("p", "caveat");
    p.append(withTerms(caveat));
    parts.push(p);
  }
  box.replaceChildren(...parts);
}

/**
 * "How to read it": an annotated miniature of the visual, and worked examples.
 *
 * `setAnswer` says what the number is. This says how to *look* at the picture — a
 * labelled copy of the visual grammar, then two or three real rows walked through in
 * words. Definitions alone do not teach someone to read a dot-and-ring plot; being
 * shown one club's row does.
 *
 * `examples` are `{ subject, text }`, built by the page from rows it selected. As
 * everywhere else, the page inserts values a tested model produced (CLAUDE.md §9).
 */
export function setGuide({ figure = null, caption = null, examples = [] }) {
  const box = $("guide");
  if (!box) return;

  const parts = [el("h2", "", "How to read it")];
  const body = el("div", "guide-body");

  if (figure) {
    const holder = el("figure", "guide-figure");
    holder.append(figure);
    if (caption) {
      const words = el("figcaption", "");
      words.append(withTerms(caption));
      holder.append(words);
    }
    body.append(holder);
  }

  if (examples.length) {
    const list = el("ul", "guide-examples");
    for (const { subject, text } of examples) {
      const item = el("li", "");
      if (subject) item.append(el("b", "", subject), " — ");
      item.append(withTerms(text));
      list.append(item);
    }
    body.append(list);
  }

  parts.push(body);
  box.replaceChildren(...parts);
}

/* --- the annotated miniatures --------------------------------------------
 * Each page draws a small, labelled copy of its own visual using the same marks
 * the real one uses, so the legend is the thing itself rather than a description
 * of it. Two helpers keep the label plumbing out of the page files.
 */

/** A text label inside a guide figure. */
export function figureLabel(x, y, text, anchor = "start") {
  const node = svg("text", { class: "fig-label", x, y, "text-anchor": anchor });
  node.textContent = text;
  return node;
}

/** A thin leader line from a label to the mark it names. */
export function figureLeader(x1, y1, x2, y2) {
  return svg("path", { class: "fig-leader", d: `M${x1},${y1} L${x2},${y2}` });
}

/** A highlighted number inside an answer sentence. */
export function highlight(text, direction = "ahead") {
  return el("span", `hl ${direction}`, text);
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
  place(node, clientX, clientY);
}

/** Keep a tooltip on screen: flip left, then below, rather than overflow. */
function place(node, clientX, clientY) {
  const width = node.offsetWidth;
  const height = node.offsetHeight;
  let left = clientX + 16;
  let top = clientY - height - 12;
  if (left + width > window.innerWidth - 8) left = clientX - width - 16;
  if (top < 8) top = clientY + 16;
  node.style.left = `${Math.max(8, left)}px`;
  node.style.top = `${top}px`;
}

/** A term's definition, as prose rather than a label/value grid. */
export function showDefinition(title, body, clientX, clientY) {
  const node = tip();
  if (!node) return;
  node.replaceChildren(el("div", "tip-title", title), el("div", "tip-def", body));
  node.hidden = false;
  place(node, clientX, clientY);
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

/* Every page is built around these. If one is missing, the document in the browser
 * is not the one this script belongs with — almost always a cached copy. */
const REQUIRED_IDS = ["rail-top", "rail-foot", "kicker", "answer", "meaning", "foot", "tip"];

/**
 * Check the page is the one this script expects, and say so plainly if not.
 *
 * A browser can hold an old copy of the HTML while fetching new JavaScript, and the
 * two then disagree about what elements exist. Without this the symptom is a blank
 * dashboard and a null property access, which says nothing useful to whoever is
 * looking at it. With it, the page names the problem and the fix.
 */
function checkSkeleton() {
  const missing = REQUIRED_IDS.filter((id) => !$(id));
  if (!missing.length) return true;

  const banner = el("div", "stale-banner");
  banner.append(
    el("strong", "", "This page is out of date with its scripts. "),
    "Reload bypassing the cache — Ctrl+Shift+R, or Cmd+Shift+R on a Mac. ",
    el("span", "mono", `missing: ${missing.join(", ")}`),
  );
  document.body.prepend(banner);
  console.error(`Stale document: missing #${missing.join(", #")}`);
  return false;
}

/**
 * Load meta + the league table (which every page uses for its pickers), build the
 * chrome, and hand back the data. One place for the boilerplate four pages share.
 */
export async function startPage({ page, mart, container }) {
  checkSkeleton();
  try {
    const [meta, leagueTable] = await Promise.all([
      loadJSON("meta.json"),
      loadJSON("league_table.json"),
    ]);
    buildRail(page, meta);
    buildFooter(mart);
    return { meta, leagueTable };
  } catch (error) {
    buildRail(page, { match_date_range: { min: null, max: null } });
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
