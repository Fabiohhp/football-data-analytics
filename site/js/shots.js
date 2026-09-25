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
  clubsIn, setAnswer, highlight, setGuide, figureLabel, figureLeader, asPercent,
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

/** How each situation reads inside a sentence. */
const SITUATION_WORDS = {
  OpenPlay: "open play", FromCorner: "corners", SetPiece: "set pieces",
  DirectFreekick: "direct free kicks", Penalty: "penalties",
};

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

/** A simplified goalmouth with three shots, labelled by what their size means. */
function guideFigure() {
  const node = svg("svg", {
    viewBox: "0 0 150 68", role: "img",
    "aria-label": "A labelled example of three shots on the shot map",
  });

  // The pitch sits left, so the labels have clear room on the right.
  node.append(svg("rect", { class: "fig-rule", x: 12, y: 6, width: 60, height: 38, fill: "none" }));
  node.append(svg("rect", { class: "fig-rule", x: 30, y: 6, width: 24, height: 10, fill: "none" }));
  node.append(svg("circle", { cx: 42, cy: 24, r: 0.9, fill: "var(--pitch-line)" }));

  // Close and large (a goal, so coloured), mid-range, and far and small.
  node.append(svg("circle", { cx: 42, cy: 15, r: 6, fill: "var(--ahead)", "fill-opacity": .8 }));
  node.append(svg("circle", { cx: 26, cy: 28, r: 3, fill: "var(--even)", "fill-opacity": .5 }));
  node.append(svg("circle", { cx: 62, cy: 38, r: 1.8, fill: "var(--even)", "fill-opacity": .5 }));

  node.append(figureLeader(48.5, 15, 76, 15), figureLabel(78, 17, "big + close"));
  node.append(figureLeader(64, 38, 76, 40), figureLabel(78, 42, "small + far"));
  node.append(figureLeader(42, 25, 42, 52), figureLabel(42, 58, "penalty spot", "middle"));
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
  const who = state.player === "all" ? (club?.team ?? "this club") : state.player;
  const scope = state.situation === "all"
    ? "" : ` from ${SITUATION_WORDS[state.situation] ?? state.situation}`;

  $("board-title").textContent = `${who} — ${state.season}`;

  const sentence = document.createDocumentFragment();
  sentence.append(
    `${who} took `,
    highlight(`${filtered.length} shots`, "ahead"),
    `${scope} in ${state.season}, and scored ${goals} of them.`,
  );

  // Three shots from the ones actually drawn: the best chance, a goal from a poor
  // one, and the furthest effort. Picked by sorting; nothing here is derived.
  const byXg = [...filtered].sort((a, b) => (b.xg ?? 0) - (a.xg ?? 0));
  const best = byXg[0];
  const luckiest = filtered
    .filter((shot) => shot.goal && !shot.penalty && shot.result !== "OwnGoal")
    .sort((a, b) => (a.xg ?? 0) - (b.xg ?? 0))[0];
  // Own goals are drawn with the shots, but they are not attempts at this goal: they
  // sit on the scorer's own team at exactly 0.00 xG (§5 trap 11), which puts them at
  // the wrong end of the pitch and top of a sort by distance. Picking one as "the
  // effort furthest from goal" would teach the reader something untrue.
  const furthest = filtered
    .filter((shot) => shot.result !== "OwnGoal")
    .sort((a, b) => a.x - b.x)[0];

  const guideExamples = [];
  if (best) {
    guideExamples.push({
      subject: `${best.player}, ${best.minute}'`,
      text: `the largest disc here, worth ${num(best.xg, 2)} [[xg|xG]] — a chance that ` +
        `goes in about ${asPercent(best.xg)} times in a hundred. ` +
        `${best.goal ? "It went in." : "It did not go in."}`,
    });
  }
  if (luckiest) {
    guideExamples.push({
      subject: `${luckiest.player}, ${luckiest.minute}'`,
      text: `a goal from only ${num(luckiest.xg, 2)} xG, about ${asPercent(luckiest.xg)} in ` +
        "a hundred — a small coloured disc. These are " +
        "the ones that inflate a finishing number, and the ones least likely to happen " +
        "again next season.",
    });
  }
  if (furthest) {
    guideExamples.push({
      subject: `${furthest.player}, ${furthest.minute}'`,
      text: `the effort furthest from goal, worth ${num(furthest.xg, 2)} xG. A cloud with ` +
        "many of these and few large discs is a side settling for whatever it can get.",
    });
  }
  guideExamples.push({
    subject: "Reading the cloud",
    text: "size is chance quality, position is where it came from, colour is whether it " +
      "went in. Lots of large discs near the six-yard box means a team working the ball " +
      "into good positions; a scatter of small ones round the edge of the area does not.",
  });

  setGuide({
    figure: guideFigure(),
    caption: "Marker area is the shot's [[xg|xG]]; goals are coloured. Every penalty " +
      "lands on the same spot, which is how the axes are checked.",
    examples: guideExamples,
  });

  setAnswer({
    kicker: `${club?.team ?? ""} · ${state.season} · ${LEAGUE_NAMES[state.league] ?? state.league}`,
    sentence,
    meaning: [
      "Each circle is one shot, placed where it was taken, and sized by its " +
      "[[xg|expected goals]] — so a tap-in is a large disc and a hopeful effort from " +
      "distance is a small one. Goals are picked out in colour. The goal being attacked " +
      "is at the top.",
      "The shape of the cloud is the point. A club whose discs are large and central is " +
      "working the ball into good positions; one whose shots are small and spread around " +
      "the edge of the box is taking whatever it can get, and will score less for the " +
      "same number of attempts.",
    ],
    caveat:
      "Counts here describe what is drawn, not a season total: change the situation filter " +
      "and the number changes with it. Own goals appear because Understat records them as a " +
      "shot result on the scorer's own team — they are never counted as goals for this club.",
  });

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
