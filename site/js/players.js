/* Players page: a per-90 leaderboard with a minutes filter.
 *
 * Every rate comes from mart_player_season, which divides by minutes once, in SQL.
 * This file filters by league and minutes, sorts by a column, and formats.
 */

import {
  $, el, num, signed, segmented, syncSegmented, fillSelect, loadJSON, showError,
  startPage, leaguesIn, seasonsIn, defaultSeason,
} from "./common.js";

const LEAGUE_NAMES = {
  PL: "Premier League", PD: "LaLiga", BL1: "Bundesliga", SA: "Serie A", FL1: "Ligue 1",
};
const ROW_LIMIT = 200;

const state = { season: null, league: "all", minutes: 900, sort: "npxg_per_90", ascending: false };
let META = null;
let TABLE = [];
const cache = new Map();

async function playersFor(season) {
  const key = season.replace("/", "-");
  if (!cache.has(key)) cache.set(key, await loadJSON(`players/${key}.json`));
  return cache.get(key);
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

  if (!filtered.length) {
    const cell = el("td", "state");
    cell.colSpan = 9;
    cell.textContent =
      `No players with ${state.minutes}+ minutes in ${state.season}` +
      (state.league === "all" ? "" : ` in ${LEAGUE_NAMES[state.league]}`) +
      ". Lower the minutes filter, or pick a completed season.";
    const tr = el("tr", "");
    tr.append(cell);
    $("rows").replaceChildren(tr);
    $("board-foot").replaceChildren("0 players match this filter · from ", el("code", "", "mart_player_season"));
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
      el("td", "strong", num(row.np_goals_per_90, 2)),
      el("td", "strong", num(row.npxg_per_90, 2)),
      el("td", "c-optional muted", num(row.xa_per_90, 2)),
      el("td", "c-optional muted", num(row.shots_per_90, 2)),
      el("td", "muted", signed(row.finishing)),
    );
    return tr;
  }));

  const scope = state.league === "all" ? "all five leagues" : LEAGUE_NAMES[state.league];
  const capped = filtered.length > ROW_LIMIT ? ` · showing the top ${ROW_LIMIT}` : "";
  $("board-foot").replaceChildren(
    `${filtered.length} players in ${scope} with ${state.minutes}+ minutes${capped} · from `,
    el("code", "", "mart_player_season"),
  );
  $("eyebrow").textContent = `${state.season} · ${scope} · Per-90 leaderboard`;
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
