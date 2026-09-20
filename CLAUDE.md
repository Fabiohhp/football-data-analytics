
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

It is its own repository, sitting next to the pipeline that feeds it:

```
~/football-data-engineering/   Part 1 — the pipeline; owns the Gold layer
~/football-data-analytics/     Part 2 — this repository
```

| Phase | Scope | Where | Status |
|-------|-------|-------|--------|
| Part 1 — Data Engineering & Architecture | Ingestion, Airflow, Bronze/Silver/Gold, data quality | `../football-data-engineering` | Complete |
| **Part 2 — Analytics & BI** | Metrics layer, analyses, dashboard | **this repository** | **In progress — phase 1 of 5 done** |
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

**Traps. Each of these produces a plausible-looking wrong number, not an error.**

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
   Never `COALESCE` it to 0 — exclude it and count what was excluded.
8. **There is no non-penalty xG per player.** `fact_player_events.xg` includes
   penalties. Build npxG from `fact_shots` where `situation <> 'Penalty'`.
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
    built by excluding misses does not.
12. **Read metrics in the right direction:** a *lower* PPDA means *more*
    pressing; `xpts` is Understat's expected points for the match.
13. **Twelve fixtures exist as two rows** (2 in 2024/25, 9 in 2025/26, 1 in
    2026/27, out of 3,733 — and only 10 of the 12 have a twin within one day, so
    do not assume the pair is always adjacent). The sources disagree on the date of a late
    kickoff, so the cross-source join missed them: one row carries the result
    with no xG, the other carries xG and the player events with no result and no
    `competition_code`. Counting matches per team therefore needs
    `football_data_match_id IS NOT NULL`, and a player-goals total taken through
    that filter alone loses a goal or two a season (Retegui reads 24 rather than
    25). Decide per analysis; it is 0.3% either way.
14. **46 duplicate shot rows across 2 La Liga matches.** Understat returned every
    shot of those matches twice under different shot ids, so shot counts and
    summed xG double there. Deduplicate on
    `(match_key, player_key, minute, result, x, y, xg)` if shot volume matters.

---

## 6. Metrics layer (dbt) conventions

- Every model states its **grain** in its `schema.yml` description and has
  `unique` + `not_null` tests on the grain's key.
- **`int_team_matches` is the foundation of every team metric:** one row per team
  per **counting** match — `status IN ('FINISHED', 'AWARDED')` per §5 trap 6, two
  rows per fixture — with `team_key`, `opponent_key`, `is_home`, `goals_for`,
  `goals_against`, `xg_for`, `xg_against`, `points`, `xpts`, `season`,
  `competition_code`. League tables, form and home advantage are all a
  `GROUP BY` over it. Test it two ways: exactly twice as many rows as counting
  matches, and — in a completed season — every club's played count equal to twice
  its number of opponents. The second test is what catches a wrong status filter;
  the first does not.
- **Per-90 metrics need a minutes floor.** It is one dbt var (`min_minutes`,
  default 900), and every chart that uses it says so.
- Seasons, leagues and thresholds are vars or columns — never literals buried in
  a model.
- Sources point at the Parquet snapshot through dbt-duckdb's `external_location`,
  parameterized so CI can aim the same project at the test fixture.

First marts, in this order:

| Mart | Grain | Holds |
|------|-------|-------|
| `mart_team_season` | team × season × competition | the league table, plus xPTS, points − xPTS, xG difference, PPDA |
| `mart_team_form` | team × match | rolling xG for / against over the last N matches |
| `mart_player_season` | player (`understat_player_id`) × season × team | totals, per-90s, goals − xG, npxG |
| `mart_shots` | shot | shots with player, team, match and season attached |

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
| 1 | Which teams' points run ahead of or behind their xPTS — and does the gap persist into the second half of the season, or does xG difference predict what comes next better than points do? | `int_team_matches`, `mart_team_season` | 1 season |
| 2 | Is finishing (goals − xG) a repeatable player skill, or mostly noise? | `mart_player_season` | 2 seasons |
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
- **Preview through a local server** — the pages fetch JSON, so opening the
  HTML file directly does not work (see §11).
- **CI smoke-tests the site:** it runs the export on the fixture and loads every
  page in a headless browser (pytest-playwright, so no Node), failing on any
  console error.
- **Part 3 shows predictions the same way** — as pre-computed JSON the site
  reads, never a model running live.

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
│   └── export_site_data.py    # marts -> site/data/*.json (select and format only)
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml           # DuckDB path only, no secrets
│   ├── macros/                # season_label, ...
│   └── models/
│       ├── staging/
│       ├── intermediate/
│       └── marts/
├── notebooks/                 # NN_question.ipynb, outputs committed
├── site/                      # static dashboard: index.html + one HTML file per page
│   ├── css/
│   ├── js/                    # one file per page, plus shared helpers
│   ├── vendor/                # third-party JS and fonts, pinned, never a CDN
│   └── data/                  # gitignored: JSON written by export_site_data.py
├── src/football_analytics/    # shared Python, with pytest tests — never copy-pasted
│   ├── gold.py                # the contract itself, and drift detection
│   ├── snapshot.py            # the loader every notebook starts from; .citation()
│   └── viz.py                 # chart style + pitch plots in Understat coordinates
├── tests/
│   ├── fixtures/
│   │   ├── make_gold_fixture.py   # builds the fixture; deterministic, CI diffs it
│   │   └── gold/              # tiny synthetic snapshot carrying every §5 trap
│   └── test_*.py
├── data/                      # gitignored: gold/ snapshot, analytics.duckdb
├── pyproject.toml             # dependencies (uv) + ruff/black config; dev tools in [dev]
├── uv.lock                    # committed: the exact versions a reviewer will get
├── .python-version            # 3.12
├── .env.example               # GOLD_PG_* connection settings for the export script
└── README.md                  # portfolio front page: questions -> findings -> how to run
```

`dbt/` and `site/` do not exist yet; they arrive in phases 2 and 4. Empty
directories are not tracked by git, so they are created with their contents.

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

uv run jupyter lab

# --- not built yet -----------------------------------------------------------
uv run dbt build --project-dir dbt --profiles-dir dbt   # (phase 2)
uv run python scripts/export_site_data.py               # (phase 4)
uv run python -m http.server -d site                    # (phase 4)
```

---

## 12. Roadmap

Each phase is small and ends in something showable. Finish one before starting
the next.

| Phase | Deliverable | Done when |
|-------|-------------|-----------|
| 0 ✅ | Backfill 2024/25 and 2025/26 — **in Part 1** | Part 1's quality checks pass on two complete seasons |
| 1 ✅ | Repo skeleton, export script, contract check, `01_data_profile.ipynb` | We know what is really in the data: matches per league and season, null-xG rate, `Unknown`-member and null-`match_key` counts |
| 2 | dbt staging, `int_team_matches`, the first two marts, CI | `dbt build` passes locally, and on the fixture in CI |
| 3 | Analyses #1 and #2 from §8 | Each ends in a written answer with its caveats |
| 4 | Static dashboard site | Runs locally from marts, passes the CI smoke test; hosting decided (§13) |
| 5 | README as the portfolio front page | A reviewer understands the findings without running anything |

**What phase 1 established.** The export, the contract check and the fixture are
in place, and `notebooks/01_data_profile.ipynb` measured every trap in §5 against
the real snapshot. Ten were confirmed, two were found absent (null `match_key` is
currently zero in both event facts, and no match has a null score), and **one was
documented wrongly** — §5 trap 6 now carries the corrected status filter, which is
the first thing `int_team_matches` has to get right. Where a trap's count is
currently zero, the dbt models test that it stays zero rather than assuming it.

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
