/* Team page: one club's rolling xG, match by match.
 *
 * The rolling averages are computed in mart_team_form, including the window length
 * and how many matches in each window actually had xG. This file draws them.
 */

import {
  $, el, svg, num, signed, segmented, syncSegmented, fillSelect, loadJSON,
  showError, showTip, hideTip, scale, ticks, prettyDate, startPage, leaguesIn,
  seasonsIn, defaultSeason, clubsIn, setAnswer, highlight, setGuide,
  figureLabel, figureLeader,
} from "./common.js";

const LEAGUE_NAMES = {
  PL: "Premier League", PD: "LaLiga", BL1: "Bundesliga", SA: "Serie A", FL1: "Ligue 1",
};

function ordinal(n) {
  const suffix = ["th", "st", "nd", "rd"];
  const value = n % 100;
  return n + (suffix[(value - 20) % 10] || suffix[value] || suffix[0]);
}

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

/** Two short lines and five result dots, labelled — the chart in miniature. */
function guideFigure() {
  // `chart-svg` on purpose: the miniature then picks up exactly the styles the real
  // chart uses, so the legend is the thing itself. Without it the series rules —
  // which are scoped to `.chart-svg` — do not apply, and the lines render as filled
  // black shapes instead of strokes.
  const node = svg("svg", {
    class: "chart-svg", viewBox: "0 0 150 76", role: "img",
    "aria-label": "A labelled example of the rolling xG chart",
  });

  node.append(svg("path", {
    class: "series series-for", d: "M14,46 L42,32 L70,27 L98,40 L126,24",
  }));
  node.append(svg("path", {
    class: "series series-against", d: "M14,31 L42,39 L70,45 L98,29 L126,43",
  }));

  for (const [x, cls] of [[14, "loss"], [42, "win"], [70, "win"], [98, "draw"], [126, "win"]]) {
    node.append(svg("circle", { class: `result-dot ${cls}`, cx: x, cy: 62, r: 2.6 }));
  }

  node.append(figureLeader(70, 25, 70, 15), figureLabel(70, 12, "xG created", "middle"));
  node.append(figureLeader(70, 47, 100, 53), figureLabel(102, 55, "xG conceded"));
  node.append(figureLeader(14, 64, 10, 71), figureLabel(8, 74, "result"));
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

  $("board-title").textContent = `${club.team} — rolling xG over ${META.form_window} matches`;

  // Every figure below is a column of the league-table row for this club-season.
  const gapDir = club.points_minus_xpts >= 0 ? "ahead" : "behind";
  const sentence = document.createDocumentFragment();
  sentence.append(
    `${club.team} finished ${ordinal(club.position)} on ${club.points} points, `,
    highlight(`${signed(club.points_minus_xpts)}`, gapDir),
    ` against their expected points, with an xG difference of ${signed(club.xgd)} — `,
    `${ordinal(club.xg_difference_rank)} best of ${club.clubs_in_league}.`,
  );

  setAnswer({
    kicker: `${club.team} · ${state.season} · ${LEAGUE_NAMES[club.league] ?? club.league}`,
    sentence,
    meaning: [
      `The chart below is the same season seen week by week: [[xg|expected goals]] created ` +
      `and conceded, averaged over a rolling window of ${META.form_window} matches so one ` +
      "wild afternoon does not swing the line. The dots underneath are what the club " +
      "actually got — win, draw or loss — for the way it was playing.",
      "Where the blue line sits above the red, the club was creating more than it was " +
      "giving up. Where the dots disagree with the lines for a stretch, that is the gap " +
      "between performance and result that the league table's [[gap|Points − xPTS]] column " +
      "adds up.",
    ],
    caveat:
      `A window of ${META.form_window} matches is short: the first few points of a season ` +
      "rest on fewer, and a fixture the two sources never paired has no xG at all and is " +
      "left out rather than counted as zero. The footer says when that has happened.",
  });

  if (!matches.length) {
    $("chart").replaceChildren(el("div", "state", "No matches for this club in this season."));
    $("rows").replaceChildren();
    return;
  }

  drawChart(matches);

  // Three stretches of this club's own season, found by sorting the matches already
  // drawn: its best spell for creating, its worst for conceding, and a match where
  // the result and the performance disagreed.
  const windowed = matches.filter((m) => m.rolling_xg_for !== null);
  const bestSpell = [...windowed].sort((a, b) => b.rolling_xg_for - a.rolling_xg_for)[0];
  const leakiest = [...windowed].sort((a, b) => b.rolling_xg_against - a.rolling_xg_against)[0];
  const robbed = matches
    .filter((m) => m.points === 0 && m.xg_for !== null && m.xg_for > m.xg_against)
    .sort((a, b) => b.xg_for - a.xg_for)[0];

  const examples = [];
  if (bestSpell) {
    examples.push({
      subject: `Match ${bestSpell.match_number}`,
      text: `the blue line peaks at ${num(bestSpell.rolling_xg_for, 2)}. Over the ` +
        `${META.form_window} matches ending there, ${club.team} created more than in any ` +
        "other stretch of the season.",
    });
  }
  if (leakiest) {
    examples.push({
      subject: `Match ${leakiest.match_number}`,
      text: `the red line peaks at ${num(leakiest.rolling_xg_against, 2)} — red above blue, ` +
        "so the opposition were getting the better chances. A run to worry about however " +
        "the results looked at the time.",
    });
  }
  if (robbed) {
    examples.push({
      subject: `${robbed.home ? "vs" : "at"} ${robbed.opponent}`,
      text: `lost ${robbed.gf}\u2013${robbed.ga} after creating ${num(robbed.xg_for, 2)} xG ` +
        `against ${num(robbed.xg_against, 2)}. A red dot sitting under a high blue line is ` +
        "what deserving more than you got looks like.",
    });
  }
  examples.push({
    subject: "The shape to look for",
    text: "where the lines cross, something about the team changed. Where the dots stop " +
      "agreeing with the lines, their luck did.",
  });

  setGuide({
    figure: guideFigure(),
    caption: `Blue is [[xg|xG]] created, red is xG conceded, each averaged over the last ` +
      `${META.form_window} matches. The dots underneath are the results.`,
    examples,
  });

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
