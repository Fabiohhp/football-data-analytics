/* Team page: one club's rolling xG, match by match.
 *
 * The rolling averages are computed in mart_team_form, including the window length
 * and how many matches in each window actually had xG. This file draws them.
 */

import {
  $, el, svg, num, signed, segmented, syncSegmented, fillSelect, loadJSON,
  showError, showTip, hideTip, scale, ticks, prettyDate, startPage, leaguesIn,
  seasonsIn, defaultSeason, clubsIn,
} from "./common.js";

const LEAGUE_NAMES = {
  PL: "Premier League", PD: "LaLiga", BL1: "Bundesliga", SA: "Serie A", FL1: "Ligue 1",
};

const state = { league: "PL", season: null, teamKey: null };
let TABLE = [];
let META = null;
const cache = new Map();

async function formFor(teamKey) {
  if (!cache.has(teamKey)) cache.set(teamKey, await loadJSON(`team/${teamKey}.json`));
  return cache.get(teamKey);
}

/** The rolling-xG chart, drawn as inline SVG. */
function drawChart(matches) {
  const width = 900;
  const height = 300;
  const pad = { top: 16, right: 16, bottom: 46, left: 38 };

  const node = svg("svg", {
    class: "chart-svg", viewBox: `0 0 ${width} ${height}`,
    preserveAspectRatio: "none", role: "img",
    "aria-label": "Rolling expected goals created and conceded",
  });

  const xs = matches.map((m) => m.match_number);
  const values = matches
    .flatMap((m) => [m.rolling_xg_for, m.rolling_xg_against])
    .filter((v) => v !== null);
  const top = Math.max(1, Math.ceil(Math.max(...values, 1) * 2) / 2 + 0.25);

  const x = scale([Math.min(...xs), Math.max(...xs)], [pad.left, width - pad.right]);
  const y = scale([0, top], [height - pad.bottom, pad.top]);

  for (const value of ticks(0, top, 4)) {
    node.append(svg("line", {
      class: "axis-line", x1: pad.left, x2: width - pad.right, y1: y(value), y2: y(value),
    }));
    node.append(Object.assign(
      svg("text", { class: "axis-text", x: pad.left - 8, y: y(value) + 3, "text-anchor": "end" }),
      { textContent: value.toFixed(1) },
    ));
  }

  // One point per match; a gap in the line is a window with no xG in it at all.
  for (const [key, cls] of [["rolling_xg_for", "series-for"], ["rolling_xg_against", "series-against"]]) {
    let path = "";
    let pen = "M";
    for (const match of matches) {
      const value = match[key];
      if (value === null) { pen = "M"; continue; }
      path += `${pen}${x(match.match_number).toFixed(1)},${y(value).toFixed(1)} `;
      pen = "L";
    }
    if (path) node.append(svg("path", { class: `series ${cls}`, d: path.trim() }));
  }

  // Results underneath: one dot per match, coloured by what the club got.
  const resultY = height - pad.bottom + 20;
  for (const match of matches) {
    const cls = match.points === 3 ? "win" : match.points === 1 ? "draw" : "loss";
    const dot = svg("circle", {
      class: `result-dot ${cls}`, cx: x(match.match_number), cy: resultY, r: 5,
    });
    dot.addEventListener("pointerenter", (event) => showTip(
      `${match.home ? "vs" : "at"} ${match.opponent}`,
      [
        ["Date", prettyDate(match.date)],
        ["Score", `${match.gf}–${match.ga}`],
        ["xG", num(match.xg_for, 2)],
        ["xG against", num(match.xg_against, 2)],
        ["Rolling xG", num(match.rolling_xg_for, 2)],
        ["Window", `${match.window_xg_matches} of ${match.window_matches} with xG`],
      ],
      event.clientX, event.clientY,
    ));
    dot.addEventListener("pointerleave", hideTip);
    node.append(dot);
  }

  $("chart").replaceChildren(node);
}

function tile(label, value, sub) {
  const node = el("div", "tile");
  const main = el("div", "tile-main");
  main.append(el("div", "tile-value", value));
  node.append(el("div", "tile-label", label), main, el("div", "tile-sub", sub));
  return node;
}

async function render() {
  syncSegmented($("league"), state.league);
  const club = TABLE.find(
    (row) => row.team_key === state.teamKey && row.season === state.season,
  );
  if (!club) return;

  const all = await formFor(state.teamKey);
  const matches = all.filter((row) => row.season === state.season);

  $("eyebrow").textContent = `${club.team} · ${state.season} · ${LEAGUE_NAMES[club.league] ?? club.league}`;
  $("board-title").textContent = `${club.team} — rolling xG over ${META.form_window} matches`;

  // Season figures straight from the league table row. Nothing is recomputed here.
  $("tiles").replaceChildren(
    tile("League position", String(club.position), `${club.points} points from ${club.played} matches`),
    tile("xPTS", num(club.xpts, 1), `${signed(club.points_minus_xpts)} against points`),
    tile("xG difference", signed(club.xgd), `${num(club.xg_for, 1)} created, ${num(club.xg_against, 1)} conceded`),
  );

  if (!matches.length) {
    $("chart").replaceChildren(el("div", "state", "No matches for this club in this season."));
    $("rows").replaceChildren();
    return;
  }

  drawChart(matches);

  const missing = matches.filter((m) => m.xg_for === null).length;
  $("board-foot").replaceChildren(
    `${matches.length} matches · window of ${META.form_window}` +
    (missing ? ` · ${missing} match${missing === 1 ? "" : "es"} without xG, excluded from the lines` : "") +
    " · from ",
    el("code", "", "mart_team_form"),
  );

  $("rows").replaceChildren(...[...matches].reverse().map((match) => {
    const tr = el("tr", "");
    tr.append(
      el("td", "name", match.opponent),
      el("td", "c-optional muted", prettyDate(match.date)),
      el("td", "muted", match.home ? "H" : "A"),
      el("td", "strong", `${match.gf}–${match.ga}`),
      el("td", "muted", num(match.xg_for, 2)),
      el("td", "muted", num(match.xg_against, 2)),
      el("td", "c-optional muted", String(match.points)),
    );
    return tr;
  }));
}

function setSeasonOptions() {
  const inLeague = TABLE.filter((row) => row.league === state.league);
  const seasons = seasonsIn(inLeague);
  if (!seasons.includes(state.season)) state.season = defaultSeason(inLeague);
  fillSelect($("season"), seasons.map((s) => [s, s]), state.season);
}

function setClubOptions() {
  const clubs = clubsIn(TABLE, state.league, state.season);
  if (!clubs.some((row) => row.team_key === state.teamKey)) {
    state.teamKey = clubs.length ? clubs[0].team_key : null;
  }
  fillSelect($("team"), clubs.map((row) => [row.team_key, row.team]), state.teamKey);
}

const { meta, leagueTable } = await startPage({
  page: "team.html", mart: "mart_team_form", container: $("chart"),
});
META = meta;
TABLE = leagueTable;
$("window-size").textContent = String(META.form_window);

const leagues = leaguesIn(TABLE);
if (!leagues.includes(state.league)) state.league = leagues[0];

async function refresh() {
  try {
    await render();
  } catch (error) {
    showError($("chart"), error);
  }
}

segmented($("league"), leagues.map((code) => [code, LEAGUE_NAMES[code] ?? code]), state.league,
  (value) => { state.league = value; setSeasonOptions(); setClubOptions(); refresh(); });
$("season").addEventListener("change", (event) => {
  state.season = event.target.value; setClubOptions(); refresh();
});
$("team").addEventListener("change", (event) => {
  state.teamKey = Number(event.target.value); refresh();
});

setSeasonOptions();
setClubOptions();
await refresh();
