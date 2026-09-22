/* Shots page: a hand-drawn pitch, in Understat's coordinates.
 *
 * The pitch is SVG drawn in **metres**, goal at the top, so the markings have real
 * proportions. Understat's coordinates are normalised to a 0-1 pitch, so mapping a
 * shot onto it is two multiplications and no rescaling of the data (CLAUDE.md §5,
 * trap 10). Higher `x` is nearer the goal being attacked, `y = 0.5` is the middle —
 * the same orientation as the notebooks' mplsoccer plots, so a shot map here and a
 * shot map there are the same picture.
 *
 * The only counting this file does is of the markers it has drawn, which is a
 * statement about the view. It never sums or averages a metric (CLAUDE.md §9).
 */

import {
  $, el, svg, num, segmented, syncSegmented, fillSelect, loadJSON, showError,
  showTip, hideTip, prettyDate, startPage, leaguesIn, seasonsIn, defaultSeason,
  clubsIn,
} from "./common.js";

const LEAGUE_NAMES = {
  PL: "Premier League", PD: "LaLiga", BL1: "Bundesliga", SA: "Serie A", FL1: "Ligue 1",
};

/* Pitch dimensions in metres — a full pitch is 105 long by 68 wide. */
const LENGTH = 105;
const WIDTH = 68;
const HALF = LENGTH / 2;

/* Understat [0, 1] -> the SVG's metre grid, goal at the top. */
const px = (y) => y * WIDTH;
const py = (x) => (1 - x) * LENGTH;

const SITUATIONS = [
  ["all", "All"],
  ["OpenPlay", "Open play"],
  ["FromCorner", "Corners"],
  ["SetPiece", "Set pieces"],
  ["DirectFreekick", "Free kicks"],
  ["Penalty", "Penalties"],
];

const state = { league: "PL", season: null, teamKey: null, player: "all", situation: "all" };
let TABLE = [];
const cache = new Map();

async function shotsFor(teamKey) {
  if (!cache.has(teamKey)) cache.set(teamKey, await loadJSON(`shots/${teamKey}.json`));
  return cache.get(teamKey);
}

/** The attacking half, with its markings. */
function drawPitch() {
  const node = svg("svg", {
    // The extra room at the top is not decoration: a shot taken on the goal line
    // has a marker whose radius reaches past it, and a clipped half-disc reads as
    // a rendering bug rather than as a tap-in.
    class: "pitch", viewBox: `-2 -4 ${WIDTH + 4} ${HALF + 6}`,
    role: "img", "aria-label": "Shot map on the attacking half of a pitch",
  });

  // Boundary of the half, and the goal line at the top.
  node.append(svg("rect", { class: "line", x: 0, y: 0, width: WIDTH, height: HALF }));
  // Penalty area: 40.32 m wide, 16.5 m deep. Six-yard box: 18.32 m by 5.5 m.
  node.append(svg("rect", { class: "line", x: (WIDTH - 40.32) / 2, y: 0, width: 40.32, height: 16.5 }));
  node.append(svg("rect", { class: "line", x: (WIDTH - 18.32) / 2, y: 0, width: 18.32, height: 5.5 }));
  // Goal, drawn just outside the line.
  node.append(svg("rect", { class: "line", x: (WIDTH - 7.32) / 2, y: -1, width: 7.32, height: 1 }));
  // Penalty spot, and the arc of the penalty area outside the box.
  node.append(svg("circle", { class: "spot", cx: WIDTH / 2, cy: 11, r: 0.35 }));
  node.append(svg("path", {
    class: "line",
    d: `M ${WIDTH / 2 - 7.31},16.5 A 9.15,9.15 0 0,0 ${WIDTH / 2 + 7.31},16.5`,
  }));
  // Centre circle, at the halfway line along the bottom edge.
  node.append(svg("path", {
    class: "line",
    d: `M ${WIDTH / 2 - 9.15},${HALF} A 9.15,9.15 0 0,1 ${WIDTH / 2 + 9.15},${HALF}`,
  }));
  return node;
}

function render(shots) {
  const filtered = shots.filter((shot) =>
    shot.season === state.season &&
    (state.player === "all" || shot.player === state.player) &&
    (state.situation === "all" || shot.situation === state.situation));

  const node = drawPitch();

  // Biggest first, so a tap-in never hides behind a long shot.
  for (const shot of [...filtered].sort((a, b) => (b.xg ?? 0) - (a.xg ?? 0))) {
    // Marker area is proportional to xG, so a 0.02 chance does not read like a 0.7 one.
    const radius = 0.7 + Math.sqrt(shot.xg ?? 0) * 2.4;
    const marker = svg("circle", {
      class: `shot${shot.goal ? " goal" : ""}`,
      cx: px(shot.y), cy: py(shot.x), r: radius,
    });
    marker.addEventListener("pointerenter", (event) => showTip(
      shot.player,
      [
        ["Result", shot.result],
        ["xG", num(shot.xg, 2)],
        ["Situation", shot.situation],
        ["Body part", shot.body_part],
        ["Minute", `${shot.minute}'`],
        ["Date", prettyDate(shot.date)],
      ],
      event.clientX, event.clientY,
    ));
    marker.addEventListener("pointerleave", hideTip);
    node.append(marker);
  }

  $("pitch").replaceChildren(node);

  // Counting the markers on screen. Not a metric: no sums, no averages — the xG
  // totals for a club live on the League table page, where a mart defines them.
  const goals = filtered.filter((shot) => shot.goal).length;
  const club = TABLE.find((row) => row.team_key === state.teamKey && row.season === state.season);
  const who = state.player === "all" ? club?.team ?? "this club" : state.player;
  $("board-title").textContent = `${who} — ${state.season}`;
  $("eyebrow").textContent =
    `${club?.team ?? ""} · ${state.season} · ${LEAGUE_NAMES[state.league] ?? state.league}`;
  $("board-foot").replaceChildren(
    `${filtered.length} shots shown, ${goals} of them goals · from `,
    el("code", "", "mart_shots"),
  );
}

function setPlayerOptions(shots) {
  // Distinct names among the shots already loaded: a projection, not a grouping.
  const names = [...new Set(
    shots.filter((shot) => shot.season === state.season).map((shot) => shot.player),
  )].sort((a, b) => a.localeCompare(b));
  if (!names.includes(state.player)) state.player = "all";
  fillSelect($("player"), [["all", "Everyone"], ...names.map((n) => [n, n])], state.player);
}

async function refresh({ reloadPlayers = true } = {}) {
  try {
    if (state.teamKey === null) return;
    const shots = await shotsFor(state.teamKey);
    if (reloadPlayers) setPlayerOptions(shots);
    render(shots);
  } catch (error) {
    showError($("pitch"), error);
  }
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

const { leagueTable } = await startPage({
  page: "shots.html", mart: "mart_shots", container: $("pitch"),
});
TABLE = leagueTable;

const leagues = leaguesIn(TABLE);
if (!leagues.includes(state.league)) state.league = leagues[0];

segmented($("league"), leagues.map((code) => [code, LEAGUE_NAMES[code] ?? code]), state.league,
  (value) => {
    state.league = value;
    syncSegmented($("league"), value);
    setSeasonOptions(); setClubOptions(); refresh();
  });
segmented($("situation"), SITUATIONS, state.situation, (value) => {
  state.situation = value;
  syncSegmented($("situation"), value);
  refresh({ reloadPlayers: false });
});
$("season").addEventListener("change", (event) => {
  state.season = event.target.value; setClubOptions(); refresh();
});
$("team").addEventListener("change", (event) => {
  state.teamKey = Number(event.target.value); state.player = "all"; refresh();
});
$("player").addEventListener("change", (event) => {
  state.player = event.target.value; refresh({ reloadPlayers: false });
});

setSeasonOptions();
setClubOptions();
await refresh();
