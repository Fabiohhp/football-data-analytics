
# CLAUDE.md

**This is the project's design brief** — the decisions, conventions and data
traps that everything in this repository follows. It doubles as the working
context for Claude Code, which is why it is written as instructions; if you are
a human reader, §3 (why each tool was chosen over the alternatives), §5 (the
Gold contract and the fourteen ways to get a wrong number from it) and §7
(analysis conventions) are the parts worth reading. The README is the front
door; this is the reasoning behind it.

Read it fully before generating or modifying code.

---

## 1. Project Overview

This project is **Part 2 — Analytics & BI** of a football (soccer) data
portfolio. It turns the Gold star schema built by Part 1 into **answered
questions** (written analyses) and an **interactive dashboard**.

It is its own repository, sitting next to the pipeline that feeds it. **Only the
sibling relationship matters** — every path in the code is relative (`snapshot.py`
and `marts.py` resolve from `__file__`, the export reads `../football-data-engineering`),
so the pair can live anywhere as long as they stay side by side:

```
portfolio/football-data/
├── football-data-engineering/   Part 1 — the pipeline; owns the Gold layer
└── football-data-analytics/     Part 2 — this repository
```

| Phase | Scope | Where | Status |
|-------|-------|-------|--------|
| Part 1 — Data Engineering & Architecture | Ingestion, Airflow, Bronze/Silver/Gold, data quality | `../football-data-engineering` | Complete |
| **Part 2 — Analytics & BI** | Metrics layer, analyses, dashboard | **this repository** | **Complete — 5 of 5 phases** |
| Part 3 — Machine Learning | Match outcome / xG models | separate repository, later | Not started |

**The deliverable is insight a reviewer can read and reproduce** — not a
pipeline, and not a model. The audience is someone hiring for analytics or data
science: they will read the README, open a couple of notebooks on GitHub and
click through the dashboard. Optimize for:

- one clear question per analysis, answered clearly, with honest caveats;
- metrics defined once, tested, and reused everywhere;
- reproducibility from a pinned data snapshot, **without running Part 1**.

---

## 2. Status, and the one prerequisite: history

**The data is loaded.** As of 2026-09-20 Gold holds **3,733 matches, 115,410
player events and 94,034 shots**: the complete **2024/25** and **2025/26** big-5
seasons, plus **2026/27** to date, which Part 1's daily schedule keeps current.
Part 1's quality suite passes with **0 errors**. These counts grow with every
load, so treat them as a reading, not a constant — the authority for any given
analysis is its snapshot's `manifest.json`, never this paragraph.

Checked against the real world rather than only against itself: 2024/25's final
tables are exact in all five leagues (Liverpool 84, Barcelona 88, Napoli 82,
Bayern 82, PSG 84, with correct goal differences), top scorers match (Salah 29,
Mbappé 31, Kane 26), and penalties sit on one point of the pitch at 0.756
average xG.

**Backfills must run in chronological order, and Gold was rebuilt to make that
true.** `dim_players` is an SCD Type 2 that only ever opens versions going
forward, so a date loaded before a player's earliest known version resolves to
that too-new version — a 2024 goal attached to the club they joined in 2026.
Measured: 108 violations from one out-of-order date, caught by Part 1's
`fact_player_events_team_agrees_with_player_version` ERROR check. Gold was
therefore truncated and reloaded in date order.

**What that means when reading `dim_players`:** a player's history starts at
their first appearance inside the loaded range, not at their real career start.
Earlier versions do not exist, so never read `valid_from` as a transfer date
without checking it against the snapshot's range.

**This repository never calls Football-Data or Understat.** If data is missing,
the fix belongs in Part 1.

---

## 3. Tech Stack

| Concern | Choice | Why |
|---------|--------|-----|
| Environment | **uv**, Python 3.11+ | Same toolchain as Part 1's local venv |
| Reading Gold | **DuckDB `postgres` extension**, attached `READ_ONLY` | One export script; the read-only attach makes writing to the warehouse impossible from here |
| Analytical store | **DuckDB** over a **Parquet snapshot** | In-process, zero infrastructure, fast at this volume |
| Metrics layer | **dbt-core + dbt-duckdb** | Each KPI defined once in SQL, with tests, docs and lineage — the standard tool analytics roles ask for |
| Analysis | **Jupyter**, pandas, scipy / statsmodels | What data science reviewers expect to read |
| Charts (notebooks) | **matplotlib**; **mplsoccer** for pitch plots | Static images show up in GitHub's notebook view, which is what a reviewer reads — Plotly's JavaScript charts render blank there; mplsoccer is built on matplotlib and is the football-analytics standard for shot maps |
| Dashboard | **Static site** — plain HTML, CSS and JavaScript over JSON exported from the marts | Full control over the design; any static host serves it, so it loads instantly and never sleeps; no server, no framework, no build step, nothing to install beyond uv |
| Quality | ruff, black, pytest, dbt tests, GitHub Actions | Same bar as Part 1 |

Considered and not chosen:

- **Querying Part 1's PostgreSQL live.** Every reviewer of this repository would
  have to start Part 1's whole stack, and results would shift every time the
  pipeline loaded another day. A snapshot pins each analysis to a known version
  of the data.
- **Metabase / Superset / Power BI.** Each needs a running server or a desktop
  application, and a reviewer only ever sees screenshots — none of the work is
  visible in the repository.
- **Streamlit** (the original plan). Every Streamlit app looks alike and can only
  be themed so far, and free hosting puts idle apps to sleep — a reviewer's
  first click can land on a wake-up screen instead of the dashboard.
- **A JavaScript framework or build tool** (React, Svelte, Vite, Evidence,
  Observable Framework). Each brings Node, npm and a build step into a
  repository whose owner does not write JavaScript. Four pages over
  pre-computed rows do not need one.

---

## 4. Architecture

```
  Part 1 PostgreSQL  (gold.dim_*, gold.fact_*)
          │  scripts/export_gold.py — READ_ONLY attach + contract check
          ▼
  data/gold/*.parquet + manifest.json      snapshot: exact copy, no transforms
          │  dbt build
          ▼
  data/analytics.duckdb
     stg_*    1:1 with Gold — renames and casts only
     int_*    reusable reshapes (team-per-match, player-per-match with season)
     mart_*   the metrics
          │
          ├──► notebooks/   one question each
          │
          └──► scripts/export_site_data.py — marts only, READ_ONLY
                    │
                    ▼
               site/data/*.json         rows ready to display + snapshot range
                    │
                    ▼
               site/                    static dashboard: HTML + CSS + JS
```

### Layer rules

- **Snapshot.** Copies `gold.dim_*` and `gold.fact_*` exactly. Never the
  `staging` schema — that is Part 1's per-run scratch space, not a contract.
  `manifest.json` records the export time, row counts per table and the
  `match_date` range, and every analysis cites it.
- **Contract check.** The export compares Gold's columns and types against
  `contracts/gold_columns.json` and **fails on any difference**. Part 1 may
  change its schema; this repository must find out at export time, not as a
  wrong number in a chart. Updating the contract file is a deliberate commit.
- **Staging (`stg_`).** One model per Gold table: rename, cast `NUMERIC` to
  `DOUBLE`, derive `season` where it is missing. No filtering, no business logic.
- **Intermediate (`int_`).** Reshapes that more than one mart builds on.
  **Join the event facts to each other on `understat_match_id`, not `match_key`.**
  Both facts carry it NOT NULL, so the join cannot be broken by trap 4, and it is
  also the safe key for deduplicating shots — a `match_key` dedup would group two
  different unmatched matches together, since SQL treats NULLs as equal.
- **Marts (`mart_`).** Where metrics are defined. **Once a calculation appears in
  two places, it belongs in a mart.** Exploratory notebooks may query `stg_`
  models freely; a finished analysis's headline numbers, and every dashboard
  page, come from marts.
- **Site data.** `scripts/export_site_data.py` reads marts only and writes the
  JSON the dashboard loads, plus the snapshot's `match_date` range. It selects,
  filters, renames and rounds for display — it never aggregates. A `GROUP BY`
  there is a missing mart.

---

## 5. The Gold contract, and the traps in it

Source of truth: `../football-data-engineering/sql/ddl/` and the "Gold layer
schema" section of that repository's README. Scope is the **big-5 leagues only**
— competition codes `PL`, `PD`, `BL1`, `SA`, `FL1`.

| Table | Grain | Contents |
|-------|-------|----------|
| `fact_matches` | one match | Football-Data result (FT/HT goals, `result`, `status`) + Understat xG, npxG, PPDA, deep, xPTS per side; `season`, `matchday`, referee and stadium keys |
| `fact_player_events` | one player per match | Understat: minutes, goals, own goals, assists, shots, key passes, xG, xA, xGChain, xGBuildup, cards |
| `fact_shots` | one shot | Understat: minute, `x`/`y`, xG, `result`, `situation`, `shot_type`, assisting player |
| `dim_teams` | one club (SCD1) | `canonical_name` is the conformed cross-source name |
| `dim_players` | one player **version** (SCD2) | `valid_from` / `valid_to` / `is_current`; `understat_player_id` is the durable key |
| `dim_referees` | one official (SCD1) | name, nationality |
| `dim_stadiums` | one ground (SCD1) | name, country, raw address; `city` and `capacity` are always null |

**Traps. Each of these produces a plausible-looking wrong number, not an error** —
except the last, which produces a visibly wrong *name*.

1. **Aggregate players by `understat_player_id`, never by `player_key`.**
   `dim_players` is SCD Type 2: a player who changed clubs has several keys, and
   grouping by key splits that player's season in two.
2. **A player's club in a given match is `fact_player_events.team_key`**, not
   `dim_players.current_team_key`.
3. **Key `0` is the `Unknown` member.** `referee_key = 0` means no referee was
   reported, not a referee named Unknown. Exclude it explicitly and report how
   many rows that removed.
4. **`match_key` is nullable in `fact_player_events` and `fact_shots`.** An inner
   join to `fact_matches` silently drops those rows. Count them before joining.
5. **Only `fact_matches` carries `season`.** It is `'YYYY/YY'`, derived by Part 1
   from `match_date` with an August cutoff (`season_label` in Part 1's
   `src/common/sources.py`). Derive it the same way for the other facts, in one
   dbt macro. The cutoff mislabels 2019/20 matches played in August 2020 —
   handle that if the season is ever backfilled.
6. **Filter results-based metrics on `status IN ('FINISHED', 'AWARDED')`** — not
   on `'FINISHED'` alone. Three matches were abandoned and then awarded by the
   federation: they were really played, carry a real score and xG, and counted
   towards the real league table. `'FINISHED'` alone drops them, and six clubs
   across three league-seasons then read 33 matches played in a 34-match season.
   One `POSTPONED` match is the opposite case — never played, but carrying a
   phantom `0-0` with `result = 'DRAW'` and no xG — and both filters exclude it.
   Scores *can* be null for an unplayed fixture, but no row in the current
   snapshot has one, because Part 1 only loads up to the current date; test that
   rather than assume it. Measured in `notebooks/01_data_profile.ipynb` §9.
7. **Null xG is not zero.** It means the two sources did not pair that match.
   Never `COALESCE` it to 0 — exclude it and count what was excluded. Measured:
   among counting matches, the null-xG rows are **exactly** the Football-Data
   halves of the split fixtures in trap 13 — 12 matches, 2 + 9 + 1 across the
   three seasons — because that fixture's xG went to its twin. `home_xg` and
   `away_xg` are always null as a pair, which is what lets
   `assert_xg_nulls_are_not_zeroed` check the count exactly. PPDA is null slightly
   more often than xG (one extra match), so count its coverage separately.
8. **There is no non-penalty xG per player.** `fact_player_events.xg` includes
   penalties. Build npxG from `fact_shots` where `situation <> 'Penalty'` —
   `int_player_matches` does this once and `mart_player_season` carries the result.
   The reconstruction is trustworthy because it is checked: summing a player's shot
   xG reproduces `fact_player_events.xg` to within 0.0002 on every one of the
   115,410 player-match rows, tested on every build.
9. **Not in Gold at all:** possession, passes, tackles (FBref is blocked in
   Part 1), and stadium city and capacity. Do not design metrics around them and
   do not impute them.
10. **Shot coordinates are Understat's, normalized to [0, 1].** Confirmed
    correct: all 1,118 penalties sit at exactly `x = 0.885, y = 0.5` with zero
    variance on both axes, averaging 0.756 xG. Higher `x` is closer to the goal
    being attacked. `src/football_analytics/viz.py` maps them onto mplsoccer's
    Opta pitch by multiplying by 100, which puts the penalty spot on Opta's own.
11. **Categorical columns hold source strings.** Run `SELECT DISTINCT` on
    `result`, `situation` and `shot_type` against the snapshot before hardcoding
    any list of values. Two that bite: `MissedShots` is plural where every other
    value is singular, and **`OwnGoal` is a value of `fact_shots.result`** — so
    `result = 'Goal'` correctly excludes own goals, but any "on target" proxy
    built by excluding misses does not. An `OwnGoal` row sits on **the team of the
    player who scored it**, and counts as a goal for the opponent: rebuilding each
    side's goals as its own `Goal` shots plus the opponent's `OwnGoal` shots comes
    to 5,683 against 5,684 reported. The measured vocabularies are `result` ∈
    {Goal, OwnGoal, MissedShots, BlockedShot, SavedShot, ShotOnPost}, `situation` ∈
    {OpenPlay, FromCorner, SetPiece, DirectFreekick, Penalty}, `shot_type` ∈
    {RightFoot, LeftFoot, Head, OtherBodyPart} — asserted by `accepted_values`
    tests in `dbt/models/staging/schema.yml`, which fail if Part 1 ever loads a
    value this repository has not decided about. Two more measured facts about own
    goals: every one of the 299 carries **exactly 0.0000 xG**, and
    `fact_player_events.shots` does **not** count them — the shot rows equal the
    reported shot count plus the own goals, exactly, on all 115,410 rows. So a shot
    *volume* metric excludes them and an xG sum need not care.
12. **Read metrics in the right direction:** a *lower* PPDA means *more*
    pressing; `xpts` is Understat's expected points for the match.
13. **Twelve fixtures exist as two rows** (2 in 2024/25, 9 in 2025/26, 1 in
    2026/27, out of 3,733 — and only 10 of the 12 have a twin within one day, so
    do not assume the pair is always adjacent). The sources disagree on the date
    of a late kickoff, so the cross-source join missed them.

    **Corrected, having measured it — `status` does not separate the halves.**
    Both are `FINISHED`, and both carry the same scoreline: all eleven comparable
    pairs agree on the score, because Understat reports the result too. What the
    Understat half lacks is Football-Data's columns — `football_data_match_id`,
    `competition_code`, `matchday`, the half-time score — and it reports no
    official (`referee_key = 0`); `competition_name` survives. The
    Football-Data half is the one with no xG (trap 7).

    So counting matches, points or league position needs
    `football_data_match_id IS NOT NULL` **on top of** the status filter; neither
    implies the other. A player-goals total taken through that filter alone loses
    a goal or two a season (Retegui reads 24 rather than 25), because the goals
    live on the Understat half. Decide per analysis; it is 0.3% either way.
14. **46 duplicate shot rows across 2 La Liga matches.** Understat returned every
    shot of those matches twice under different shot ids, so shot counts and
    summed xG double there. Deduplicate on
    `(match_key, player_key, minute, result, x, y, xg)` if shot volume matters.
15. **Names arrive HTML-escaped.** Understat serves them that way and Part 1 stores
    them as received, so Gold really holds `Nico O&#039;Reilly`. Measured: 22
    `dim_players` versions, 16 distinct players, 399 event rows; the only entity in
    the current snapshot is `&#039;`. It is invisible in a terminal that renders the
    entity and glaring in a browser that does not, which is how it was found — on the
    dashboard's player dropdown, not in any test.

    `dbt/macros/html_unescape.sql` decodes it in staging, and
    `assert_no_html_entities_in_names` fails if an entity this repository has not seen
    starts arriving. `&amp;` is decoded **last**, so a double-escaped `&amp;#039;`
    cannot be unwound into a character that was never in the name. Legitimate
    ampersands are untouched: `Brighton & Hove Albion` is stored unescaped.

    **This belongs in Part 1, at ingestion** — it repairs a value rather than renaming
    or casting one, and every consumer of Gold otherwise has to repair it
    independently. Raise it there; the macro is a stopgap, not the fix.

---

## 6. Metrics layer (dbt) conventions

- Every model states its **grain** in its `schema.yml` description and tests it.
  The grains here are composite, and dbt's built-in `unique` test only covers one
  column, so `unique_combination` is vendored as a four-line generic test in
  `dbt/macros/` rather than pulling in dbt_utils — `dbt build` never downloads a
  package.
- **`int_team_matches` is the foundation of every team metric:** one row per team
  per **counting** match, two rows per fixture, with `team_key`, `opponent_key`,
  `is_home`, `goals_for`, `goals_against`, `xg_for`, `xg_against`, `points`,
  `xpts`, `season`, `competition_code`. League tables, form and home advantage are
  all a `GROUP BY` over it, and nothing downstream re-applies its filters.

  "Counting" is **two independent filters**, and neither implies the other:
  `status IN ('FINISHED', 'AWARDED')` per §5 trap 6, *and*
  `football_data_match_id IS NOT NULL` per §5 trap 13 — both halves of a split
  fixture are `FINISHED` with a scoreline, so status alone lets one through.

  Test it three ways, because each catches something the others do not:
  1. exactly twice as many rows as counting matches — catches a lost or duplicated
     row, but *not* a wrong filter, since the count stays self-consistent either
     way;
  2. no club playing more than a full double round robin — catches a duplicated
     fixture, and has to be **ungated**, because an over-count also pushes a season
     past any "is this season finished" test and would otherwise silence check 3;
  3. in a completed season, every club's played count equal to twice its number of
     opponents — this is what catches a wrong status filter.

  Derive "completed season" from the data (`2 × (clubs − 1)`), never from a list of
  seasons or a hardcoded 38: Ligue 1 and the Bundesliga run 18 clubs, and the
  in-progress season has to join the test by itself when it finishes.
- **Report coverage next to every xG figure.** `sum()` skips nulls silently, so a
  mart that sums xG over a season is really summing over however many matches had
  it. Each xG, xPTS and PPDA block carries its own `matches_with_*` count, and
  `points − xPTS` compares points over *the matches that have an xPTS*
  (`points_in_xpts_matches`) rather than a full season of points against a partial
  season of xPTS.
- **Per-90 metrics need a minutes floor.** It is one dbt var (`min_minutes`,
  default 900), and every chart that uses it says so. Same for the rolling-form
  window (`form_window`, default 5), which `mart_team_form` carries on every row so
  a chart cannot draw a window without being able to state its length.
- Seasons, leagues and thresholds are vars or columns — never literals buried in
  a model.
- Sources point at the Parquet snapshot through dbt-duckdb's `external_location`,
  parameterized by `GOLD_SNAPSHOT_DIR` so CI can aim the same project at the test
  fixture. **Read the env var in `sources.yml`, not through a dbt var:** dbt renders
  Jinja in the yml files but *not* inside a var's default in `dbt_project.yml`, so
  a `{{ env_var(...) }}` written there reaches DuckDB as a literal string.
- **Everything is materialized as a table.** A view over the snapshot would store
  `read_parquet('data/gold/...')` inside `analytics.duckdb` and resolve that
  relative path against whoever opened the database next — working from the
  repository root and failing from `notebooks/`. Tables make the snapshot path a
  build-time concern and `analytics.duckdb` a self-contained artifact.

First marts, in this order:

| Mart | Grain | Holds | Status |
|------|-------|-------|--------|
| `mart_team_season` | team × season × competition | the league table, plus xPTS, points − xPTS, xG difference, PPDA | ✅ phase 2 |
| `mart_team_form` | team × match | rolling xG for / against over the last N matches | ✅ phase 2 |
| `mart_player_season` | player (`understat_player_id`) × **season** | totals, per-90s, goals − xG, npxG | ✅ phase 3 |
| `mart_shots` | shot | shots with player, team, match and season attached | ✅ phase 3 |
| `mart_team_season_half` | team × season × competition × half | the league table cut in two, for the persistence question | ✅ phase 3 |

Two deviations from the plan above, both made while building phase 3:

- **`mart_player_season` is player × season, not player × season × team.** The
  reasoning behind trap 1 applies to a club split as much as to a key split: 94
  player-seasons in 2024/25 and 92 in 2025/26 span two clubs while clearing the
  minutes floor, and at club grain each half is a shorter season that often clears
  no floor at all. "Does this player finish well?" needs the whole season. The club
  survives as `primary_team_name` plus a `clubs` count, and `int_player_matches`
  keeps the per-club detail.
- **`mart_team_season_half` was added**, because question 1 needs the
  points-over-xPTS gap measured over one stretch of matches and compared with the
  next, and doing that in a notebook would have re-implemented the coverage-aware
  `points − xPTS` that `mart_team_season` already defines.

---

## 7. Analysis conventions

- **One notebook, one question**, named `NN_short_name.ipynb`. The first cell
  states the question and why it matters; the last cell answers it in plain
  language, with its caveats.
- **Run top to bottom on a fresh kernel before committing, and commit the
  outputs.** GitHub's rendering is what a reviewer actually reads. CI re-executes
  every notebook to prove they still run.
- **Every result states** its sample size, any thresholds, and the snapshot's
  `match_date` range from `manifest.json`.
- **Show uncertainty.** Confidence or bootstrap intervals on any estimate a
  conclusion rests on.
- **No causal language.** This is observational data: "associated with", not
  "causes".
- **Expect regression to the mean.** Extreme over- or under-performers in one
  period will tend to drift back towards average in the next; account for it
  before calling anything a skill.
- **Heavy SQL or reshaping inside a notebook means a mart is missing.**
- Reusable Python — the snapshot loader, pitch plots, a bootstrap helper — lives
  in `src/football_analytics/` with pytest tests, not copy-pasted between
  notebooks.

### Boundary with Part 3

- **Here:** descriptive statistics, correlations, hypothesis tests, and simple
  regressions used to *explain* what happened.
- **Part 3:** anything trained to *predict* unseen matches — train/test splits,
  feature pipelines, model selection, and xG models built from `fact_shots`.

---

## 8. Question backlog

Ranked. #1 is the flagship: it is the classic xG question, and it leads straight
into Part 3.

| # | Question | Built on | Needs |
|---|----------|----------|-------|
| 1 ✅ | Which teams' points run ahead of or behind their xPTS — and does the gap persist into the second half of the season, or does xG difference predict what comes next better than points do? | `mart_team_season_half` | answered in `02_points_vs_xpts.ipynb` |
| 2 ✅ | Is finishing (goals − xG) a repeatable player skill, or mostly noise? | `mart_player_season` | answered in `03_is_finishing_repeatable.ipynb` |
| 3 | How big is home advantage, and does it differ between the big-5 leagues? | `int_team_matches` | 1–2 seasons |
| 4 | Where do goals come from? Conversion by pitch zone, situation and body part | `mart_shots` | 1 season |
| 5 | Does pressing intensity (PPDA) go with better results, and does that hold in every league? | `int_team_matches` | 1 season |
| 6 | Do referees differ in how many cards they show, once the league is accounted for? | `fact_player_events` + `fact_matches.referee_key` | 2 seasons |

---

## 9. Dashboard

A static site in `site/`: plain HTML, CSS and JavaScript reading the JSON files
that `scripts/export_site_data.py` writes from the marts. No server, no
framework, no build step.

Pages, in build order:

1. **League table** — actual points against xPTS, per league and season.
2. **Team** — rolling xG for and against, with results.
3. **Players** — per-90 leaderboard with a minutes filter.
4. **Shots** — shot map for a team or a player.

Rules:

- **No metric logic in JavaScript.** The frontend filters, sorts and formats
  rows; it never sums, averages or derives a number. A calculation in `site/` is
  a missing mart.
- **Keep `site/` plain enough to maintain from a SQL and Python background.**
  Small files, comments where the intent is not obvious, no clever abstractions.
  Describe every change by what a page shows, not by how the code works. This is
  also why no number is computed here: everything a reviewer could ask about a
  figure lives in dbt and the export script.
- **No npm, no framework, no bundler.** At most one charting library, vendored
  into `site/vendor/` with its version in the filename.
- **No requests to other hosts at runtime.** Libraries and fonts are vendored,
  so the site works offline and cannot break when a CDN changes.
- **The shot map is hand-drawn SVG** in Understat's [0, 1] coordinates, oriented
  the same way as the notebooks' mplsoccer plots (§5, trap 10).
- **Every page shows the snapshot's `match_date` range.**
- **Works at phone width.**
- **`site/data/` is generated and gitignored**, like `data/`, until §13 decides
  what may be published.
- **Preview with `scripts/serve_site.py`, not `python -m http.server`.** The pages
  fetch JSON, so opening the HTML directly does not work — but the stock server also
  sends no `Cache-Control`, and browsers then reuse cached JavaScript without
  revalidating. That serves the previous build's scripts against the current markup,
  which fails wherever the two disagree; it cost a debugging session whose symptom
  was an empty dashboard and a null `textContent`. The preview server sends
  `no-store`. A real host should cache, and the answer there is a fingerprinted
  filename — not a concern until §13 decides on hosting.
- **When the dashboard misbehaves, check what is being served before reading the
  code.** `scripts/check_site.py` fetches every page, script and stylesheet from a
  running server, hashes it against the file on disk, and names any that differ. Two
  rounds of a bug were spent in the source when the browser was simply executing a
  different build — an old server still bound to the port, or a cached response. It
  is one command and it rules that out first.
- **CI smoke-tests the site:** it runs the export on the fixture and loads every
  page in **Chromium and Firefox** (pytest-playwright, so no Node), failing on any
  console error. Two engines because a static site has no other test worth the name,
  and because the one reader-reported breakage arrived from the engine the suite was
  not running.
- **Part 3 shows predictions the same way** — as pre-computed JSON the site
  reads, never a model running live.

Settled while building it:

- **A left rail, not a top bar.** The filters live beside the numbers rather than in
  a band above them, so they stay on screen while the figures change — the pattern
  Linear, Stripe and Grafana use. This was the second attempt: the first redesign
  kept the old skeleton (hero → controls → tiles → table) and only changed the
  colours, which is why it read as the same page in a different palette.
- **Every page answers before it tabulates.** The canvas is an inverted pyramid: a
  kicker, then **a sentence stating what the current view shows**, then a *What this
  means* block, then the evidence. A reader who stops after the first screen should
  leave with a finding rather than a table to interpret. `assert` this: the smoke
  test fails a page with no filled-in answer line, no highlighted figure, or no
  defined terms.
- **The explanation is a metric, so it lives in dbt.** "Is 0.78 npxG per 90 good?"
  is answered by a percentile, and a percentile depends entirely on which players
  are in the comparison — a modelling decision, not formatting. `mart_player_season`
  computes it against *the same season and league, players over the minutes floor*;
  `mart_team_season` carries `points_minus_xpts_rank` and a `gap_band`. The pages
  insert those values and compute nothing.
- **A band is not a significance test.** `gap_band` says "well ahead" so a reader who
  does not know what 13.9 means is told it is unusual — and the caveat beside it says
  the analysis found a gap of any size barely persists. The reading aid and the
  finding that undercuts it appear together, on purpose.
- **A page must degrade, not blank.** Every `getElementById` write is guarded, and
  `startPage()` checks the skeleton the scripts assume and renders a red banner
  naming any missing element. The failure this replaces was a reader's screenshot of
  an empty dashboard and `can't access property "textContent" ... is null`: one
  unguarded write threw halfway through `render()` and took the table, the footer and
  everything after it with it. A page that is missing one element should lose that
  element and say so.
- **Show, then explain.** Each page carries a *How to read it* block: a labelled
  miniature of that page's own visual, plus two or three worked examples naming rows
  that are on screen right now. Definitions alone do not teach someone to read a
  dot-and-ring plot — being walked through one club's row does. The miniatures reuse
  the real visuals' CSS classes on purpose, so the legend is the thing itself; the
  team figure rendered as filled black shapes until it was given `chart-svg`, which
  is the failure mode that choice invites and the reason it is worth stating.
- **Worked examples are selected, never composed.** They come from sorting the rows
  already loaded — the widest gap, the best five-match spell, the biggest chance — so
  they follow the filters instead of going stale. Two things that bit: a sort by
  distance put an **own goal** top of "the effort furthest from goal" (they sit at the
  scorer's own end at 0.00 xG, §5 trap 11), and writing `+13.9 points more` double-signs
  the number. Prose takes the magnitude; the word carries the direction.
- **Terms explain themselves where they appear.** One `GLOSSARY` in `common.js`,
  marked up as `[[xpts]]` inside the explanation text, rendered as a focusable
  button with the definition on hover. A page of definitions nobody opens is not an
  explanation.
- **Dark is the default, not a variant.** The design is an analyst's console —
  mono-forward, dense, hairline panels rather than rounded cards, and two semantic
  hues and no more: blue is ahead / created, red is behind / conceded, the same on
  every page and in the notebook charts. Neither is spent on interface state, so a
  selected control inverts the ink instead.
- **The theme toggle writes only an explicit choice.** `data-theme="light"` is the
  override; an inline script in each page's `<head>` applies a stored choice before
  first paint so the page never flashes the wrong theme, and every `localStorage`
  read and write is wrapped because it throws in a private window.
- **No charting library at all.** §9 allowed one; none was needed. The league
  table's dot plot is positioned `<span>`s, the rolling-xG chart and the shot map
  are hand-written inline SVG, and `common.js` carries the only two pieces of chart
  maths — a linear scale and axis ticks. `site/vendor/` holds fonts and nothing else.
- **Fonts are vendored, not linked.** Archivo and IBM Plex Mono (both OFL), latin
  and latin-ext only, 248 kB with the version in each filename.
- **The JSON is split per club and per season**, because each page shows one of
  those at a time. One 94,000-row shots file would make a phone download the whole
  dataset to draw one club's map; per club it is 171 kB on average.
- **Every page opens on the newest *complete* season.** Five matches into the
  in-progress one, a league table has a two-point spread and no player has cleared
  the minutes floor — a working page that looks broken. `defaultSeason()` in
  `common.js` is the one definition; the in-progress season stays in every dropdown.
- **Counting rows is allowed; summing is not.** The shot map says how many markers
  it drew and how many are goals, which describes the view. It shows no summed xG:
  that is a metric, and metrics come from marts.
- **A card that holds a wide table needs `contain: layout`.** Without it the
  table's min-content width leaks past `overflow: hidden` and drags the whole page
  sideways — measured at 212 px on a 390 px viewport. The smoke test asserts no page
  scrolls sideways at phone width, which is how that was found.

---

## 10. Repository Structure

```
football-data-analytics/
├── .github/workflows/ci.yml   # lint, pytest, fixture freshness, execute notebooks
│                              #   (+ dbt build phase 2, site smoke test phase 4)
├── contracts/
│   └── gold_columns.json      # expected Gold columns + types; the export fails on drift
├── scripts/
│   ├── export_gold.py         # Part 1 PostgreSQL -> data/gold/*.parquet + manifest.json
│   ├── export_site_data.py    # marts -> site/data/*.json (select and format only)
│   ├── serve_site.py          # local preview; sends no-store so reloads are honest
│   ├── check_site.py          # is the running server serving site/? hashes vs disk
│   └── export_readme_images.py  # notebook figures + dashboard screenshots -> docs/images/
├── docs/images/               # committed: what the README shows (the site is not hosted)
├── dbt/
│   ├── dbt_project.yml        # min_minutes and form_window vars; everything materialized
│   ├── profiles.yml           # DuckDB path only, no secrets
│   ├── macros/
│   │   ├── season.sql         # Part 1's August cutoff, in SQL, defined once
│   │   └── test_unique_combination.sql  # composite-grain test, vendored not dbt_utils
│   ├── models/
│   │   ├── staging/           # stg_* — 1:1 with Gold, + sources.yml, schema.yml
│   │   ├── intermediate/      # int_team_matches, int_player_matches, int_shots,
│   │   │                      #   int_club_seasons
│   │   └── marts/             # mart_team_season, _form, _season_half,
│   │                          #   mart_player_season, mart_shots
│   └── tests/                 # the singular tests: a wrong filter fails here
├── notebooks/                 # NN_question.ipynb, outputs committed
├── site/                      # static dashboard: one HTML file per page
│   ├── index.html             #   League table — points against xPTS
│   ├── team.html              #   Team — rolling xG, match by match
│   ├── players.html           #   Players — per-90 leaderboard, minutes filter
│   ├── shots.html             #   Shots — hand-drawn SVG pitch
│   ├── css/app.css            # the whole design system, one file
│   ├── js/                    # common.js + one file per page
│   ├── vendor/fonts/          # Archivo + IBM Plex Mono, vendored, never a CDN
│   └── data/                  # gitignored: JSON written by export_site_data.py
├── src/football_analytics/    # shared Python, with pytest tests — never copy-pasted
│   ├── gold.py                # the contract itself, and drift detection
│   ├── snapshot.py            # the Parquet loader; .citation()
│   ├── marts.py               # the mart loader; refuses a DB stale vs the snapshot
│   ├── stats.py               # seeded bootstrap intervals, so outputs reproduce
│   └── viz.py                 # chart style + pitch plots in Understat coordinates
├── tests/
│   ├── fixtures/
│   │   ├── make_gold_fixture.py   # builds the fixture; deterministic, CI diffs it
│   │   └── gold/              # tiny synthetic snapshot carrying every §5 trap
│   └── test_*.py
├── data/                      # gitignored except .gitkeep: gold/ snapshot, analytics.duckdb
├── pyproject.toml             # dependencies (uv) + ruff/black config; dev tools in [dev]
├── uv.lock                    # committed: the exact versions a reviewer will get
├── .python-version            # 3.12
├── .env.example               # GOLD_PG_* connection settings for the export script
└── README.md                  # portfolio front page: questions -> findings -> how to run
```

`site/` does not exist yet; it arrives in phase 4. Empty directories are not
tracked by git, so they are created with their contents — except `data/`, which
carries a `.gitkeep` because DuckDB will not create a missing parent directory and
`dbt build` would otherwise fail on a fresh clone.

---

## 11. Common Commands

> Commands marked **(phase N)** are not built yet. If one fails because
> something is not built or not running, say so instead of inventing output.

```bash
uv sync --extra dev          # dev tools (ruff, black, pytest, nbclient) are an extra

# --- no data or database required --------------------------------------------
uv run pytest -q
uv run ruff check .
uv run black --check .

# Work against the synthetic fixture instead of the real snapshot. This is what
# CI sets, and it makes every command below runnable on a fresh clone.
export GOLD_SNAPSHOT_DIR=tests/fixtures/gold
uv run python tests/fixtures/make_gold_fixture.py    # rebuild it (deterministic)

# --- export a real snapshot: needs only Part 1's PostgreSQL ------------------
cp .env.example .env
(cd ../football-data-engineering && docker compose up -d postgres)
uv run python scripts/export_gold.py
uv run python scripts/export_gold.py --write-contract   # only when Gold changed

# The analyses read the marts, so build them before opening a notebook.
uv run jupyter lab

# --- the metrics layer: needs only the snapshot (or the fixture) -------------
# Writes data/analytics.duckdb. Run from the repository root: both the snapshot
# path and the database path are relative to the working directory.
uv run dbt build --project-dir dbt --profiles-dir dbt
uv run dbt test --project-dir dbt --profiles-dir dbt     # tests only
uv run dbt docs generate --project-dir dbt --profiles-dir dbt   # lineage + grains

# --- the dashboard: needs the marts built first ------------------------------
uv run python scripts/export_site_data.py    # marts -> site/data/*.json
uv run python scripts/serve_site.py          # then open http://127.0.0.1:8000
uv run python scripts/check_site.py          # is the server serving site/? (see below)
# The pages fetch JSON, so opening the HTML files directly does not work.
# **Do not preview with `python -m http.server`.** It sends no Cache-Control, so a
# browser caches the JS heuristically and reloads serve the previous build's
# scripts against the current HTML. serve_site.py sends no-store for that reason.

# The browser smoke tests run in Chromium *and* Firefox. Once, per machine:
uv run playwright install --with-deps chromium firefox   # --with-deps needs root
uv run pytest tests/test_site.py -q
uv run pytest -q -m "not site"                   # skip them outright
```

---

## 12. Roadmap

Each phase is small and ends in something showable. Finish one before starting
the next.

| Phase | Deliverable | Done when |
|-------|-------------|-----------|
| 0 ✅ | Backfill 2024/25 and 2025/26 — **in Part 1** | Part 1's quality checks pass on two complete seasons |
| 1 ✅ | Repo skeleton, export script, contract check, `01_data_profile.ipynb` | We know what is really in the data: matches per league and season, null-xG rate, `Unknown`-member and null-`match_key` counts |
| 2 ✅ | dbt staging, `int_team_matches`, the first two marts, CI | `dbt build` passes locally, and on the fixture in CI |
| 3 ✅ | Analyses #1 and #2 from §8 | Each ends in a written answer with its caveats |
| 4 ◐ | Static dashboard site | Runs locally from marts, passes the CI smoke test; **hosting still undecided (§13)** |
| 5 ✅ | README as the portfolio front page | A reviewer understands the findings without running anything |

**What phase 1 established.** The export, the contract check and the fixture are
in place, and `notebooks/01_data_profile.ipynb` measured every trap in §5 against
the real snapshot. Ten were confirmed, two were found absent (null `match_key` is
currently zero in both event facts, and no match has a null score), and **one was
documented wrongly** — §5 trap 6 now carries the corrected status filter, which is
the first thing `int_team_matches` has to get right. Where a trap's count is
currently zero, the dbt models test that it stays zero rather than assuming it.

**What phase 2 established.** Seven `stg_` models, `int_team_matches`,
`mart_team_season` and `mart_team_form` — 10 models and 72 dbt tests, passing on
the real snapshot and on the fixture. `mart_team_season` reconciles against the real world:
2024/25's champions come out exactly — Liverpool 84, Barcelona 88, Napoli 82,
Bayern 82, PSG 84 — with correct goal differences.

Two things the build changed:

- **§5 trap 13 was documented wrongly, and the correction matters.** Both halves
  of a split fixture are `FINISHED` and both carry the same scoreline, so the
  status filter does not separate them and `football_data_match_id IS NOT NULL` is
  a second, independent filter. Trap 7 turned out to be the same twelve fixtures
  seen from the other side.
- **The fixture was raising false confidence.** It had no `AWARDED` match at all,
  its split-fixture half carried a status the real data never uses, and its
  penalties were drawn with an 8% probability that happened to produce none on
  some seeds. All three are now present by construction, inside a *completed*
  fixture season so the played-count assertion can see them. Each of the three
  filters was then broken on purpose to confirm a test fails: dropping `AWARDED`,
  dropping the Football-Data id filter, and `COALESCE`-ing xG to zero.

One test was deliberately **not** written yet: the profile promised that the zero
orphan `match_key` count (trap 4) would be tested. Phase 2 has no model that reads
the event facts, so there is nothing yet for an orphan to be dropped *from* — the
meaningful form of that test is "no goals lost between staging and the mart", and
it arrives with `mart_player_season` in phase 3. What stands in for it now is the
`not_null` test on `stg_player_events.season`, which fails if that derivation ever
becomes a join to `fact_matches`.

**What phase 3 established.** Two written analyses, and six more models to support
them: `int_club_seasons`, `int_shots`, `int_player_matches`, `mart_player_season`,
`mart_shots` and `mart_team_season_half`. The project is now 16 models and 131 dbt
tests, passing on the real snapshot and on the fixture.

The findings, both of which came out more nuanced than the question implied:

- **Question 1 — the points-over-xPTS gap does not persist.** Across 192
  club-seasons, first-half gap against second-half gap correlates at +0.13 with an
  interval reaching zero; the biggest overperformers give up ~5 points of gap *and*
  ~5 actual points. But xPTS and xG difference are **not** distinguishably better
  than points as a single number (paired Δr intervals include zero) — while xG
  difference *does* add significantly on top of points in a regression (R² 0.482 →
  0.541). The answer is "use both", not "xG wins".
- **Question 2 — finishing is mostly noise, and the sample cannot find the signal.**
  Finishing per 90 repeats at r ≈ 0.10 across 1,022 players, where the same players'
  shot volume repeats at r ≈ 0.90 and npxG per 90 at r ≈ 0.85 — so it is a noisy
  quantity, not a noisy dataset. Restricting to real shot-takers was meant to settle
  it and did not: the estimate clears zero at npxG ≥ 5 (n = 133) but not at npxG ≥ 1
  (n = 585, more power) and is inconclusive at npxG ≥ 10 (n = 24). Reported as
  "cannot distinguish a very small effect from none" rather than as a finding.

Three things the build added to §5, all measured:

- own goals carry **exactly 0.0000 xG**, and `fact_player_events.shots` does not
  count them — shot rows equal reported shots plus own goals, exactly (trap 11);
- `fact_player_events.xg` equals the sum of that player's shot xG to within 0.0002
  on all 115,410 rows, which is what makes the rebuilt npxG trustworthy (trap 8);
- the event facts should be joined to each other on `understat_match_id`, which is
  NOT NULL in both, rather than on the nullable `match_key` (trap 4).

The trap-4 test promised in phase 2 now exists as
`assert_no_player_goals_lost`: totals must survive from `stg_player_events` to
`mart_player_season`, whether the orphan count is zero or not.

Two notebook-reproducibility lessons worth keeping: bootstrap helpers take a
**default seed** (`stats.DEFAULT_SEED`), and a cell prints **once** — consecutive
`print()` calls get split into stdout chunks unpredictably, which makes an identical
re-run produce a different notebook file.

**What phase 4 established.** `scripts/export_site_data.py` and a four-page static
dashboard in `site/`, with browser smoke tests in two engines. No npm, no framework, no build
step, no charting library, and no request to any other host at runtime.

The export enforces its own rule rather than relying on discipline: `rows()` refuses
any table whose name does not start with `mart_`, and every query is built from a
table name plus a column list, so there is nowhere to put a `GROUP BY` even by
accident.

Three things the browser found that nothing else would have:

- the league table dragged the whole page sideways by 212 px at phone width, because
  a table's min-content width escapes `overflow: hidden` (fixed with
  `contain: layout`);
- the players page opened completely empty, because it defaulted to the
  in-progress season where nobody has 900 minutes;
- both were invisible to ruff, to pytest and to every dbt test.

That is the argument for the smoke test being a real browser rather than an HTML
parser. It skips itself when a browser cannot start, so `uv run pytest -q` still
works on a fresh clone.

**A later episode added the fourth lesson, and it was a process one.** A reader
opened the dashboard and got an empty page and
`can't access property "textContent" ... is null`. Reproduced exactly by serving the
current HTML with a *mismatched* build's JavaScript: the two disagreed about which
elements exist. `python -m http.server` — the preview command this file used to
document — sends `Last-Modified` and no `Cache-Control`, so browsers cache
heuristically and do not revalidate, which is one way to get that mismatch.

Three changes, in increasing order of importance:

1. `scripts/serve_site.py` sends `no-store`, so the documented preview workflow
   cannot serve a stale file.
2. The smoke tests run in Chromium **and** Firefox — the report arrived from the
   engine the suite was not running.
3. **The page no longer depends on being right.** Writes are guarded and a missing
   element produces a named banner instead of a blank screen. The first two reduce
   the chance of a mismatch; only the third makes one survivable, and it is the fix
   that would have turned a debugging session into a glance.

**What phase 5 established.** The README is now the portfolio front page: findings
first, then the dashboard, then how it is built and why it can be trusted, then how to
run it. The phase-by-phase build log it had grown into is gone — that history lives
here in §12, which is where it belongs.

`scripts/export_readme_images.py` generates what the README shows. Charts are **lifted
out of the notebooks' committed outputs** rather than redrawn by a copy of the plotting
code, so a README figure cannot drift from the analysis it illustrates; screenshots
come from the real pages in headless Chromium. Both halves skip themselves when their
inputs are missing.

`docs/images/` is **committed**, unlike `data/` and `site/data/`. It is 1.5 MB of
rendered output, not the dataset, and with hosting undecided (§13) it is the only way a
reviewer sees the dashboard.

One accuracy fix worth remembering: the first draft claimed three documented traps had
been wrong. Two were (§5 traps 6 and 13); the own-goal findings were *additions* to a
trap that was already correct. A README that boasts about rigour is the last place to
round three up from two.

---

## 13. Open decisions

- **Publishing data.** Football-Data.org and Understat each have terms of use.
  Check them before committing any snapshot or mart to a public repository, or
  deploying a public dashboard. Until that is decided, `data/` is gitignored and
  CI runs on the synthetic fixture.
- **Dashboard hosting.** GitHub Pages, or any static host, serves the site for
  free — but publishing the site publishes its JSON files, which are the data
  itself and can be downloaded, so this waits on the decision above.
  Screenshots and a short GIF in the README are the fallback.

  **This is the one thing phase 4 did not finish, and deliberately so** — it is a
  licensing judgement, not a technical one. The site is built so that either answer
  works with no rework: `site/data/` is gitignored, the fonts are vendored so
  nothing is fetched at runtime, and the whole thing is static files that any host
  serves as-is. Deploying is `export_site_data.py` plus a copy; not deploying costs
  screenshots in the README.
- **Backfill depth** beyond two seasons.

---

## 14. Definition of Done

A piece of work is complete when:

- Every metric it uses comes from a tested dbt model.
- `ruff`, `black`, `pytest` and `dbt build` pass, and notebooks execute top to
  bottom.
- An analysis states its question, sample size, thresholds, snapshot range,
  uncertainty and answer.
- The README reflects it.

---

## 15. What NOT to do in this repo

- ❌ Do not call Football-Data or Understat — data comes from Part 1's Gold only.
- ❌ Do not write to Part 1's database, and do not read its `staging` schema.
- ❌ Do not change Part 1's Gold schema from here — raise it as a Part 1 task.
- ❌ Do not train or ship predictive models (that's Part 3).
- ❌ Do not redefine a metric in a notebook, the export script or the site when a
  mart already has it.
- ❌ Do not add npm, a JavaScript framework or a build step to `site/`.
- ❌ Do not turn null xG into 0, or impute stats that Gold does not carry.
- ❌ Do not make causal claims from correlations.
- ❌ Do not commit `.env` or `data/` (until §13 decides otherwise).
