/* League table: points against xPTS, one league-season at a time.
 *
 * Every number here comes from mart_team_season. This file chooses which rows to
 * show, sorts them, and positions two dots on a shared scale. It computes nothing.
 */

import {
  $, el, signed, num, direction, segmented, syncSegmented, fillSelect,
  showTip, hideTip, scale, ticks, startPage, leaguesIn, seasonsIn, defaultSeason,
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

function ordinal(n) {
  const suffix = ["th", "st", "nd", "rd"];
  const value = n % 100;
  return n + (suffix[(value - 20) % 10] || suffix[value] || suffix[0]);
}

/** A summary tile. Each one picks a single row — no aggregation. */
function tile(label, team, value, dir, sub) {
  const node = el("div", "tile");
  const main = el("div", "tile-main");
  const shown = el("div", "tile-value");
  if (dir) shown.append(el("i", `tri ${dir}`));
  shown.append(value);
  main.append(el("div", "tile-team", team), shown);
  node.append(el("div", "tile-label", label), main, el("div", "tile-sub", sub));
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
  $("eyebrow").textContent = `${state.league} · ${state.season} · League table`;
  $("board-title").textContent = `${LEAGUE_NAMES[state.league] ?? state.league} ${state.season}`;

  // Tiles: three single rows, selected by sorting.
  const byGap = [...rows].sort((a, b) => b.points_minus_xpts - a.points_minus_xpts);
  const ahead = byGap[0];
  const behind = byGap[byGap.length - 1];
  const topXpts = [...rows].sort((a, b) => b.xpts - a.xpts)[0];
  $("tiles").replaceChildren(
    tile("Furthest ahead of xPTS", ahead.team, signed(ahead.points_minus_xpts), "ahead",
      `${ahead.points} pts from ${num(ahead.xpts, 1)} xPTS`),
    tile("Furthest behind xPTS", behind.team, signed(behind.points_minus_xpts), "behind",
      `${behind.points} pts from ${num(behind.xpts, 1)} xPTS`),
    tile("Top of the xPTS table", topXpts.team, num(topXpts.xpts, 1), null,
      topXpts.position === 1 ? "Also first on points" : `${ordinal(topXpts.position)} on points`),
  );

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

  const note = complete ? "complete season" : "season in progress";
  $("board-foot").replaceChildren(
    `${rows.length} clubs · ${note} · xPTS is Understat's expected points per match, summed in `,
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
