/* Players page: a per-90 leaderboard with a minutes filter.
 *
 * Every rate comes from mart_player_season, which divides by minutes once, in SQL.
 * This file filters by league and minutes, sorts by a column, and formats.
 */

import {
  $, el, num, signed, segmented, syncSegmented, fillSelect, loadJSON, showError,
  startPage, leaguesIn, seasonsIn, defaultSeason, setAnswer, highlight,
  showTip, hideTip, setGuide, svg, figureLabel, figureLeader,
} from "./common.js";

const LEAGUE_NAMES = {
  PL: "Premier League", PD: "LaLiga", BL1: "Bundesliga", SA: "Serie A", FL1: "Ligue 1",
};
const ROW_LIMIT = 200;
/** How each sortable column reads inside a sentence. */
const SORT_WORDS = {
  minutes: "minutes", np_goals: "non-penalty goals", np_goals_per_90: "non-penalty goals per 90",
  npxg_per_90: "npxG per 90", xa_per_90: "xA per 90", shots_per_90: "shots per 90",
  finishing: "goals over expected",
};
/** Decimal places per column, so the sentence matches the cells it describes. */
const SORT_PLACES = { minutes: 0, np_goals: 0 };

const state = { season: null, league: "all", minutes: 900, sort: "npxg_per_90", ascending: false };
let META = null;
let TABLE = [];
const cache = new Map();

async function playersFor(season) {
  const key = season.replace("/", "-");
  if (!cache.has(key)) cache.set(key, await loadJSON(`players/${key}.json`));
  return cache.get(key);
}

/**
 * A rate, with its league percentile drawn underneath.
 *
 * "0.78 npxG per 90" does not tell a reader whether that is good. The percentile
 * does, and it is computed in `mart_player_season` against a stated population —
 * same season, same league, players over the minutes floor — because which players
 * are in the comparison is a modelling decision, not a formatting one.
 */
function rateCell(value, percentile, label, row) {
  const cell = el("td", "strong");
  const stack = el("div", "rate");
  stack.append(el("span", "", num(value, 2)));

  if (percentile !== null && percentile !== undefined) {
    const bar = el("span", "pctbar");
    bar.style.setProperty("--p", `${percentile}%`);
    stack.append(bar);
    cell.addEventListener("pointerenter", (event) =>
      showTip(row.player, [
        [label, num(value, 2)],
        ["Percentile", `${num(percentile, 0)} of 100`],
        ["Among", `${row.league} players over the floor`],
      ], event.clientX, event.clientY));
    cell.addEventListener("pointerleave", hideTip);
  }
  cell.append(stack);
  return cell;
}

/** One rate cell, blown up and labelled: the number, and the bar under it. */
function guideFigure() {
  const node = svg("svg", {
    viewBox: "0 0 150 62", role: "img",
    "aria-label": "A labelled example of a rate and its percentile bar",
  });

  const value = svg("text", {
    x: 75, y: 30, "text-anchor": "middle", fill: "var(--ink)",
    "font-family": "var(--mono)", "font-size": "15",
  });
  value.textContent = "0.78";
  node.append(value);

  node.append(svg("rect", { x: 47, y: 36, width: 56, height: 3, fill: "var(--hair-strong)" }));
  node.append(svg("rect", { x: 47, y: 36, width: 50, height: 3, fill: "var(--ahead)" }));

  node.append(figureLeader(75, 18, 75, 10), figureLabel(75, 8, "the rate, per 90", "middle"));
  node.append(figureLeader(75, 41, 75, 50), figureLabel(75, 57, "its place in the league", "middle"));
  return node;
}

function render(players) {
  const filtered = players.filter(
    (row) => row.minutes >= state.minutes && (state.league === "all" || row.league === state.league),
  );

  const key = state.sort;
  filtered.sort((a, b) => {
    const left = a[key] ?? -Infinity;
    const right = b[key] ?? -Infinity;
    if (left === right) return a.player.localeCompare(b.player);
    return state.ascending ? left - right : right - left;
  });

  const scopeName = state.league === "all" ? "all five leagues" : LEAGUE_NAMES[state.league];

  if (!filtered.length) {
    // An empty view still has to answer. Returning early here left the sentence
    // above the table blank, which reads as a page that failed to load rather than
    // as a filter with nothing behind it.
    const sentence = document.createDocumentFragment();
    sentence.append(
      "No player in ",
      highlight(scopeName, "behind"),
      ` reached ${state.minutes} minutes in ${state.season}.`,
    );
    // The guide belongs here too. It explains the columns, which is exactly what a
    // reader staring at an empty table needs in order to know what to go and look
    // for — and leaving it out was how the last empty-state bug got through.
    setGuide({
      figure: guideFigure(),
      caption: "The figure is the [[per90|per-90]] rate. The bar beneath is its " +
        "[[percentile|league percentile]] — full means best in the league.",
      examples: [
        { subject: "Nothing to show yet",
          text: "with no player over the floor there is nothing to rank, so the bars " +
            "have no population to measure against." },
        { subject: "The rate", text: "every figure is per 90 minutes, so a substitute " +
            "and an ever-present can be compared directly." },
        { subject: "The bar", text: "how that rate ranks among players in the same " +
            "league and season who cleared the [[floor|minutes floor]]." },
      ],
    });

    setAnswer({
      kicker: `${state.season} · ${scopeName} · per-90 leaderboard`,
      sentence,
      meaning: [
        "A [[per90|per-90]] leaderboard needs a [[floor|minutes floor]], and nobody here " +
        "has cleared it. That is what an in-progress season looks like a few matches in: " +
        "the rates exist, but they rest on too little football to compare.",
        "Lower the minutes filter in the rail, or pick a completed season.",
      ],
    });

    const cell = el("td", "state");
    cell.colSpan = 9;
    cell.textContent =
      `No players with ${state.minutes}+ minutes in ${state.season}` +
      (state.league === "all" ? "" : ` in ${LEAGUE_NAMES[state.league]}`) +
      ". Lower the minutes filter, or pick a completed season.";
    const tr = el("tr", "");
    tr.append(cell);
    $("rows").replaceChildren(tr);
    $("board-foot").replaceChildren(
      "0 players match this filter · from ", el("code", "", "mart_player_season"));
    return;
  }

  const shown = filtered.slice(0, ROW_LIMIT);
  $("rows").replaceChildren(...shown.map((row) => {
    const tr = el("tr", "");
    const name = el("td", "name");
    name.append(row.player);
    // A player who turned out for more than one club that season: the column shows
    // where they played most, so say so rather than letting it read as their only club.
    if (row.clubs > 1) {
      const badge = el("span", "mono", `  +${row.clubs - 1}`);
      badge.title = `Played for ${row.clubs} clubs this season; showing the one with the most minutes`;
      name.append(badge);
    }
    tr.append(
      name,
      el("td", "c-optional sub", row.team),
      el("td", "muted", String(row.minutes)),
      el("td", "", String(row.np_goals)),
      rateCell(row.np_goals_per_90, row.np_goals_per_90_pct, "npG per 90", row),
      rateCell(row.npxg_per_90, row.npxg_per_90_pct, "npxG per 90", row),
      el("td", "c-optional muted", num(row.xa_per_90, 2)),
      el("td", "c-optional muted", num(row.shots_per_90, 2)),
      el("td", "muted", signed(row.finishing)),
    );
    return tr;
  }));

  const scope = scopeName;
  const capped = filtered.length > ROW_LIMIT ? ` · showing the top ${ROW_LIMIT}` : "";
  $("board-foot").replaceChildren(
    `${filtered.length} players in ${scope} with ${state.minutes}+ minutes${capped} · from `,
    el("code", "", "mart_player_season"),
  );

  // The leader on whatever column is being sorted by, described rather than listed.
  // Each column is formatted the way its own cells are — minutes and goals are whole
  // numbers, rates take two places, and finishing keeps its sign.
  const top = shown[0];
  const value = state.sort === "finishing"
    ? signed(top.finishing)
    : num(top[state.sort], SORT_PLACES[state.sort] ?? 2);
  const direction = state.ascending ? "trails" : "leads";

  const sentence = document.createDocumentFragment();
  sentence.append(
    `${top.player} ${direction} on ${SORT_WORDS[state.sort] ?? state.sort} with `,
    highlight(value, state.sort === "finishing" && top.finishing < 0 ? "behind" : "ahead"),
    `, from ${filtered.length} players in ${scope} over ${state.minutes} minutes.`,
  );

  // Three real players from the rows on screen: the volume leader, the biggest
  // overperformer and the biggest under. All picked by sorting, nothing derived.
  const byFinishing = [...filtered].sort((a, b) => b.finishing - a.finishing);
  const overperformer = byFinishing[0];
  const underperformer = byFinishing[byFinishing.length - 1];

  const guideExamples = [];
  if (top.npxg_per_90_pct !== null && top.npxg_per_90_pct !== undefined) {
    guideExamples.push({
      subject: top.player,
      text: `npxG/90 of ${num(top.npxg_per_90, 2)} with an almost full bar — the ` +
        `${num(top.npxg_per_90_pct, 0)}th percentile. He gets into good positions more ` +
        "often than nearly anyone in his league.",
    });
  }
  if (overperformer && overperformer !== top) {
    guideExamples.push({
      subject: overperformer.player,
      text: `scored ${num(Math.abs(overperformer.finishing), 1)} more than his chances were ` +
        "worth — " +
        `the biggest overperformance here — from an npxG/90 of ` +
        `${num(overperformer.npxg_per_90, 2)}. A short bar next to a big finishing number ` +
        "is a player who took his chances, not one who made them.",
    });
  }
  if (underperformer && underperformer !== overperformer) {
    guideExamples.push({
      subject: underperformer.player,
      text: `the other end: ${signed(underperformer.finishing)} on ` +
        `${num(underperformer.npxg_per_90, 2)} npxG/90. The chances were there and did not ` +
        "go in — which, on the evidence, says more about this season than the next one.",
    });
  }
  guideExamples.push({
    subject: "Bar against number",
    text: "the number is how much; the bar is how that compares. Two players on the same " +
      "rate in different leagues can sit at very different percentiles, because each bar " +
      "is measured against that player's own league.",
  });

  setGuide({
    figure: guideFigure(),
    caption: "The figure is the [[per90|per-90]] rate. The bar beneath is its " +
      "[[percentile|league percentile]] — full means best in the league.",
    examples: guideExamples,
  });

  setAnswer({
    kicker: `${state.season} · ${scope} · per-90 leaderboard`,
    sentence,
    meaning: [
      "Everything here is [[per90|per 90 minutes]], so a substitute and an ever-present can " +
      "be compared. Penalties are stripped out of both the goals and the expected goals: " +
      "Understat's per-player xG includes them, and a penalty taker's numbers would " +
      "otherwise say more about the spot kick than the player.",
      "The bar under each rate is its [[percentile|league percentile]] — how the player " +
      "ranks among everyone in the same league and season who cleared the " +
      "[[floor|minutes floor]]. A full bar is the best in the league; a short one is near " +
      "the bottom. That is what turns \u201c0.78\u201d into something you can read.",
    ],
    caveat:
      "[[finishing|npG − npxG]] is the most tempting column here and the least useful: it " +
      "barely repeats from one season to the next (r \u2248 0.10), while shot volume repeats " +
      "at r \u2248 0.90. Read it as a description of the season that happened, not a guide to " +
      "the next one \u2014 npxG per 90 is the column that carries forward.",
  });
}

async function refresh() {
  try {
    render(await playersFor(state.season));
  } catch (error) {
    showError($("table-scroll"), error);
  }
}

function syncMinutes() {
  const isDefault = state.minutes === META.min_minutes;
  $("minutes-out").textContent = `${state.minutes} min${isDefault ? " (default)" : ""}`;
}

const { meta, leagueTable } = await startPage({
  page: "players.html", mart: "mart_player_season", container: $("table-scroll"),
});
META = meta;
TABLE = leagueTable;

// The default threshold is the dbt var the mart was built with, not a number
// retyped here (CLAUDE.md §6).
state.minutes = META.min_minutes;
$("minutes").value = String(META.min_minutes);

const seasons = seasonsIn(TABLE);
state.season = defaultSeason(TABLE);
fillSelect($("season"), seasons.map((s) => [s, s]), state.season);

const leagues = [["all", "All"], ...leaguesIn(TABLE).map((code) => [code, LEAGUE_NAMES[code] ?? code])];
segmented($("league"), leagues, state.league, (value) => {
  state.league = value;
  syncSegmented($("league"), value);
  refresh();
});

$("season").addEventListener("change", (event) => { state.season = event.target.value; refresh(); });
$("minutes").addEventListener("input", (event) => {
  state.minutes = Number(event.target.value);
  syncMinutes();
  refresh();
});

for (const header of document.querySelectorAll("th[data-sort]")) {
  header.addEventListener("click", () => {
    const column = header.dataset.sort;
    if (state.sort === column) state.ascending = !state.ascending;
    else { state.sort = column; state.ascending = false; }
    for (const other of document.querySelectorAll("th[data-sort]")) other.removeAttribute("aria-sort");
    header.setAttribute("aria-sort", state.ascending ? "ascending" : "descending");
    refresh();
  });
}

syncMinutes();
await refresh();
