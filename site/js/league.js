/* League table: points against xPTS, one league-season at a time.
 *
 * Every number here comes from mart_team_season. This file chooses which rows to
 * show, sorts them, and positions two dots on a shared scale. It computes nothing.
 */

import {
  $, el, signed, num, direction, segmented, syncSegmented, fillSelect,
  showTip, hideTip, scale, ticks, startPage, leaguesIn, seasonsIn, defaultSeason,
  setAnswer, highlight, setGuide, svg, figureLabel, figureLeader,
} from "./common.js";

const LEAGUE_NAMES = {
  PL: "Premier League", PD: "LaLiga", BL1: "Bundesliga", SA: "Serie A", FL1: "Ligue 1",
};
const SORTS = [
  ["table", "Points"],
  ["xpts", "xPTS"],
  ["gap", "Pts − xPTS"],
];

const state = { league: "PL", season: null, sort: "table" };
let TABLE = [];

function rowsFor(league, season) {
  return TABLE.filter((row) => row.league === league && row.season === season);
}

/**
 * One row of the plot, blown up and labelled.
 *
 * The same three marks the table uses — ring, dot, connector — so the legend is the
 * thing itself rather than a description of it.
 */
function guideFigure() {
  const node = svg("svg", { viewBox: "0 0 150 62", role: "img",
    "aria-label": "A labelled example of one club's row" });

  node.append(svg("line", { class: "fig-rule", x1: 10, y1: 40, x2: 140, y2: 40 }));

  // ring = xPTS, dot = points, bar between = the gap
  node.append(svg("line", { x1: 48, y1: 40, x2: 104, y2: 40,
    stroke: "var(--ahead)", "stroke-width": 1.6 }));
  node.append(svg("circle", { cx: 48, cy: 40, r: 3.4, fill: "none",
    stroke: "var(--muted)", "stroke-width": 1.4 }));
  node.append(svg("circle", { cx: 104, cy: 40, r: 3.4, fill: "var(--ahead)" }));

  node.append(figureLeader(48, 34, 40, 20), figureLabel(38, 17, "xPTS", "end"));
  node.append(figureLeader(104, 34, 116, 20), figureLabel(118, 17, "points"));
  node.append(figureLeader(76, 44, 76, 54), figureLabel(76, 60, "the gap", "middle"));
  return node;
}

function render() {
  const rows = rowsFor(state.league, state.season);
  if (!rows.length) {
    $("rows").replaceChildren();
    $("board-foot").textContent = "No matches in this league-season yet.";
    return;
  }

  const sorted = [...rows];
  if (state.sort === "xpts") sorted.sort((a, b) => b.xpts - a.xpts);
  else if (state.sort === "gap") sorted.sort((a, b) => b.points_minus_xpts - a.points_minus_xpts);
  else sorted.sort((a, b) => a.position - b.position);

  syncSegmented($("league"), state.league);
  syncSegmented($("sort"), state.sort);

  const complete = rows[0].season_complete;
  $("board-title").textContent = `${LEAGUE_NAMES[state.league] ?? state.league} ${state.season}`;

  // The answer, before the table. Rows are selected by their mart-computed rank;
  // the sentence inserts values a tested model produced and computes nothing.
  const ahead = rows.find((row) => row.points_minus_xpts_rank === 1);
  const behind = [...rows].sort((a, b) => a.points_minus_xpts - b.points_minus_xpts)[0];
  const league = LEAGUE_NAMES[state.league] ?? state.league;

  // "took +13.9 points more" double-signs it, so prose uses the bare magnitude and
  // the word carries the direction. The rank-1 club's gap can in principle still be
  // negative — a league where nobody beat their xPTS — so that reads differently.
  const sentence = document.createDocumentFragment();
  if (ahead.points_minus_xpts > 0) {
    sentence.append(
      `${ahead.team} took `,
      highlight(`${num(Math.abs(ahead.points_minus_xpts), 1)} points`, "ahead"),
      ` more than their chances were worth — the widest gap of ${ahead.clubs_in_league} `,
      `clubs in the ${league}, ${state.season}.`,
    );
  } else {
    sentence.append(
      `No club in the ${league} beat its expected points in ${state.season}. `,
      `${ahead.team} came closest, at `,
      highlight(signed(ahead.points_minus_xpts), "behind"),
      ".",
    );
  }

  setAnswer({
    kicker: `${state.league} · ${state.season} · ${complete ? "complete season" : "season in progress"}`,
    sentence,
    meaning: [
      "[[xpts|xPTS]] is what Understat's model expected each club to take from the chances " +
      "in each match, added up over the season. [[gap|Points − xPTS]] is therefore the " +
      "difference between what a club collected and what the balance of play was worth.",
      `${ahead.team} finished **${ahead.gap_band}** of that mark and ${behind.team} ` +
      `**${behind.gap_band}**, at ${signed(behind.points_minus_xpts)}. ` +
      "Read down the right-hand column: a filled dot to the right of its ring is a club " +
      "taking more than it deserved, to the left is one taking less.",
    ],
    caveat:
      "A gap this size is not evidence of a knack for winning tight games. Across 192 " +
      "club-seasons, how far a club ran ahead of its xPTS before Christmas explained almost " +
      "none of how far it ran ahead afterwards — and the clubs furthest ahead gave up around " +
      "five points of it. Treat the column as a description of the season, not a forecast.",
  });

  // Three real rows, walked through: one well ahead, one level, one behind. Chosen
  // by sorting the rows already on screen — no figure here is derived.
  const level = [...rows]
    .filter((row) => row.gap_band === "level")
    .sort((a, b) => Math.abs(a.points_minus_xpts) - Math.abs(b.points_minus_xpts))[0];

  const examples = [
    { subject: ahead.team,
      text: `ring at ${num(ahead.xpts, 1)}, dot well to its right at ${ahead.points}. ` +
            `They collected ${num(Math.abs(ahead.points_minus_xpts), 1)} points more than ` +
            "the balance of play was worth — the longest bar in the column." },
  ];
  if (level) {
    examples.push({ subject: level.team,
      text: `dot almost on top of its ring — ${level.points} points against ` +
            `${num(level.xpts, 1)} expected. What they got is roughly what they deserved, ` +
            "which is where most clubs sit." });
  }
  examples.push({ subject: behind.team,
    text: `dot to the **left** of the ring, and coloured red: ${behind.points} points from ` +
          `${num(behind.xpts, 1)} expected. On the balance of play they should be ` +
          `${num(Math.abs(behind.points_minus_xpts), 1)} points better off.` });
  examples.push({ subject: "Reading down the column",
    text: "bar length is how far result and performance came apart; which side the dot " +
          "falls on is the direction. A short bar means the table is telling the truth " +
          "about that club." });

  setGuide({
    figure: guideFigure(),
    caption: "The ring is [[xpts|xPTS]]. The dot is the points actually taken. " +
             "The bar between them is the gap.",
    examples,
  });

  // One scale for every row, so the dots are comparable down the column.
  const values = rows.flatMap((row) => [row.points, row.xpts]);
  const lo = Math.max(0, Math.floor((Math.min(...values) - 3) / 10) * 10);
  const hi = Math.ceil((Math.max(...values) + 3) / 10) * 10;
  const x = scale([lo, hi], [0, 100]);
  const at = (value) => `${x(value)}%`;
  const marks = ticks(lo, hi, 5);

  $("axis").replaceChildren(...marks.map((value) => {
    const mark = el("span", "tick", String(value));
    mark.style.left = at(value);
    return mark;
  }));

  $("rows").replaceChildren(...sorted.map((row) => {
    const gap = row.points_minus_xpts;
    const dir = direction(gap);
    const tr = el("tr", dir);

    const name = el("td", "name");
    name.append(el("span", "pos", String(row.position)), row.team);

    const gapCell = el("td", "");
    gapCell.append(el("i", `tri ${dir}`), signed(gap));

    const chart = el("td", "chart");
    const track = el("div", "track");
    for (const value of marks) {
      const line = el("span", "grid");
      line.style.left = at(value);
      track.append(line);
    }
    const connector = el("span", "conn");
    const ring = el("span", "ring");
    const dot = el("span", "dot");
    ring.style.left = at(row.xpts);
    dot.style.left = at(row.points);
    const from = Math.min(row.points, row.xpts);
    const to = Math.max(row.points, row.xpts);
    connector.style.left = at(from);
    connector.style.width = `calc(${at(to)} - ${at(from)})`;
    track.append(connector, ring, dot);
    chart.append(track);

    tr.append(
      name,
      el("td", "c-optional muted", String(row.played)),
      el("td", "strong", String(row.points)),
      el("td", "muted", num(row.xpts, 1)),
      gapCell,
      el("td", "c-optional muted", signed(row.xgd)),
      chart,
    );

    const details = [
      ["Points", String(row.points)],
      ["xPTS", num(row.xpts, 1)],
      ["Pts − xPTS", signed(gap)],
      ["xG difference", signed(row.xgd)],
      ["PPDA", num(row.ppda, 2)],
      ["Matches with xPTS", `${row.matches_with_xpts} of ${row.played}`],
    ];
    tr.addEventListener("pointermove", (event) =>
      showTip(row.team, details, event.clientX, event.clientY));
    tr.addEventListener("pointerleave", hideTip);
    return tr;
  }));

  $("board-foot").replaceChildren(
    `${rows.length} clubs · ${complete ? "complete season" : "season in progress"} · from `,
    el("code", "", "mart_team_season"),
  );
}

function setSeasonOptions() {
  const inLeague = TABLE.filter((row) => row.league === state.league);
  const seasons = seasonsIn(inLeague);
  if (!seasons.includes(state.season)) state.season = defaultSeason(inLeague);
  fillSelect($("season"), seasons.map((s) => [s, s]), state.season);
}

const { leagueTable } = await startPage({
  page: "index.html", mart: "mart_team_season", container: $("table-scroll"),
});
TABLE = leagueTable;

const leagues = leaguesIn(TABLE);
if (!leagues.includes(state.league)) state.league = leagues[0];

segmented($("league"), leagues.map((code) => [code, LEAGUE_NAMES[code] ?? code]), state.league,
  (value) => { state.league = value; setSeasonOptions(); render(); });
segmented($("sort"), SORTS, state.sort, (value) => { state.sort = value; render(); });
$("season").addEventListener("change", (event) => { state.season = event.target.value; render(); });

setSeasonOptions();
render();
