# Football Analytics — Part 2: Analytics & BI

Turning a football data warehouse into **answered questions**.

This is the analytics half of a two-part (soon three-part) portfolio. Part 1
built the pipeline and owns the Gold star schema; this repository reads a pinned
snapshot of that schema and produces written analyses, a tested metrics layer,
and an interactive dashboard.

| Part | Scope | Repository | Status |
|------|-------|------------|--------|
| 1 — Data Engineering | Ingestion, Airflow, Bronze/Silver/Gold, data quality | [`football-data-engineering`](../football-data-engineering) | Complete |
| **2 — Analytics & BI** | Metrics layer, analyses, dashboard | **this repository** | **In progress** |
| 3 — Machine Learning | Match outcome / xG models | separate, later | Not started |

**You do not need Part 1 to read this repository.** Every analysis runs against a
Parquet snapshot pinned by a manifest, and CI runs against a tiny synthetic
fixture, so a fresh clone needs no database and no credentials.

---

## The data

Big-5 European leagues — Premier League, La Liga, Bundesliga, Serie A, Ligue 1 —
combining Football-Data.org results with Understat expected-goals measures.

The snapshot this was built against holds **3,733 matches, 115,410 player events
and 94,034 shots**: the complete 2024/25 and 2025/26 seasons plus 2026/27 to
date. Every analysis cites its snapshot's exact export time and `match_date`
range from `manifest.json`, so a number can always be traced to a known version
of the data.

---

## What is built so far

**Phase 1 — snapshot, contract and data profile.** Done.

- `scripts/export_gold.py` copies Gold to Parquet through a **`READ_ONLY`
  attach**, so writing to Part 1's warehouse from here is not a convention —
  it is impossible. (Verified: an `UPDATE` through the attach is rejected by
  DuckDB, not merely discouraged.)
- A **schema contract** (`contracts/gold_columns.json`) records every Gold
  column, type, precision and nullability. The export **fails on any
  difference**, so a change in Part 1 surfaces at export time rather than as a
  wrong number in a chart. Updating it is a deliberate commit.
- [`notebooks/01_data_profile.ipynb`](notebooks/01_data_profile.ipynb) — what is
  actually in the data, and which documented traps are real.

**Phase 2 — the metrics layer.** Done.

- A **dbt project** over the snapshot: seven `stg_` models 1:1 with Gold,
  `int_team_matches`, and the first two marts — `mart_team_season` (the league
  table with xPTS, points − xPTS, xG difference and PPDA) and `mart_team_form`
  (rolling xG for and against). **72 dbt tests** across 10 models pass against the
  real snapshot and against the synthetic fixture in CI.
- **It reconciles against the real world.** 2024/25's champions come out exactly:
  Liverpool 84, Barcelona 88, Napoli 82, Bayern 82, PSG 84, with correct goal
  differences. Liverpool's opening fixture is away at Ipswich, won 2-0, at
  3.93 xG — the real one.
- **The tests were checked by breaking the model.** Filtering on `FINISHED` alone,
  dropping the duplicate-fixture filter, and `COALESCE`-ing xG to zero were each
  introduced on purpose to confirm a test fails. A test suite nobody has seen fail
  is a decoration.

**Phase 3 — the first two analyses.** Done.

- [`notebooks/02_points_vs_xpts.ipynb`](notebooks/02_points_vs_xpts.ipynb) — do points
  that run ahead of expected points stay ahead?
- [`notebooks/03_is_finishing_repeatable.ipynb`](notebooks/03_is_finishing_repeatable.ipynb)
  — is finishing a skill, or mostly noise?
- Six more models to support them, taking the project to **16 models and 131 dbt
  tests**: `mart_player_season`, `mart_shots`, `mart_team_season_half` and the
  intermediates behind them. npxG is rebuilt from the shot fact, because Gold has no
  non-penalty xG per player.

Phases 4–5 (dashboard, portfolio README) are next; see [Roadmap](#roadmap).

### What the profile found

The profile exists because in this dataset a mistake produces a *plausible
wrong number*, not an error. Of the fourteen documented traps, it confirmed ten,
cleared two, and **found one that was documented incorrectly**:

> Filtering matches on `status = 'FINISHED'` — the documented rule — silently
> drops three abandoned-then-**`AWARDED`** matches that were really played, have
> real scores and xG, and counted towards the real league table. Six clubs across
> three league-seasons then read **33 matches played in a 34-match season**.
> Meanwhile a `POSTPONED` fixture carries a phantom `0-0` with `result = 'DRAW'`.
>
> The correct filter is **`status IN ('FINISHED', 'AWARDED')`**: it keeps the three
> real results and still excludes the phantom.

Other findings worth naming:

- **Shot coordinates are oriented correctly** — all 1,118 penalties sit at
  exactly `x = 0.885, y = 0.5` with zero variance, averaging 0.756 xG.
- **934 of 4,047 players have more than one dimension version** (one has six).
  Grouping a career by the surrogate key instead of the durable one reads
  Burkardt's 34 goals as 18.
- **12 matches (0.32%) have null xG** — the two sources never paired them. Null
  is not zero, and coalescing it would drag every xG average down.
- **46 surplus shot rows across 2 La Liga matches**, duplicated under different
  shot ids — 5.9 xG of double counting for anything that does not deduplicate on
  a shot's *shape* rather than its id.
- **64 matches (1.7%) report no referee**, pointing at the `Unknown` member at
  key 0 — an official who would otherwise appear to have worked dozens of matches.

### What building the metrics layer found

Two corrections, both the same shape: a documented trap turned out to be a
*different* trap, and the difference was the part that mattered.

> **The twelve duplicated fixtures are not separated by `status`.** They were
> documented as one row holding the result and one holding the xG. In fact **both
> are `FINISHED` and both carry the same scoreline** — Understat reports the result
> too, and all eleven comparable pairs agree on it. What the Understat half lacks
> is Football-Data's columns. So a league table needs
> `football_data_match_id IS NOT NULL` as a **second, independent filter** on top
> of the status one; neither implies the other, and status alone lets a club play
> 39 matches in a 38-match season.
>
> The same twelve fixtures are also all of the null xG: every counting match
> without xG is the Football-Data half of one of them.

> **The fixture was raising false confidence.** It had no `AWARDED` match at all,
> so nothing in CI could have caught the status bug the profile had just found. Its
> split-fixture half carried a status the real data never uses, and its penalties
> were placed with an 8% random chance that produced *none* on some seeds — quietly
> removing the trap the fixture existed to guarantee. All three are now present by
> construction, inside a completed season so the played-count assertion can see
> them.

### What the analyses found

**Points that run ahead of expected points do not stay ahead.** Across 192
club-seasons, the correlation between a club's first-half and second-half
points-over-xPTS gap is **+0.13, with an interval that reaches zero**. The clubs
furthest ahead of their expected points at the halfway mark gave up around five
points of gap — and around five *actual* points — in the second half, and the clubs
furthest behind recovered by about as much.

But the obvious follow-up does not hold up either:

> As a **single number**, first-half xG difference and xPTS are *not* distinguishably
> better than first-half points at tracking second-half points — the paired bootstrap
> intervals on the differences both include zero. What xG difference *does* do is add
> information on top of points: with points already in the model, it still carries a
> clearly non-zero coefficient and lifts explained variance from 0.482 to 0.541. The
> answer is "read both", not "xG wins".

**Finishing is mostly noise — and two seasons cannot find the signal underneath.**
Non-penalty finishing per 90 repeats season to season at **r ≈ 0.10** across 1,022
players who cleared 900 minutes in both complete seasons. The very same players'
shot volume repeats at **r ≈ 0.90** and their npxG per 90 at **r ≈ 0.85**, so this is
a noisy *quantity*, not a noisy dataset.

> Restricting to players with real shooting volume was meant to settle whether a
> skill hides underneath. It did not: the estimate clears zero at npxG ≥ 5
> (133 players) but *not* at npxG ≥ 1 (585 players — more statistical power), and is
> inconclusive at npxG ≥ 10 (24 players). One threshold out of three is not how a
> solid effect behaves, so it is reported as "cannot distinguish a very small effect
> from none".
>
> For anything forward-looking, chance volume is the number to read: last season's
> npxG per 90 tracks next season's non-penalty goals per 90 at r ≈ 0.78, while last
> season's finishing is very slightly *negative*.

---

## Architecture

```
  Part 1 PostgreSQL  (gold.dim_*, gold.fact_*)
          │  scripts/export_gold.py — READ_ONLY attach + contract check
          ▼
  data/gold/*.parquet + manifest.json      exact copy, no transforms
          │  dbt build
          ▼
  data/analytics.duckdb
     stg_*    1:1 with Gold — renames and casts only
     int_*    team-per-match, player-per-match, deduplicated shots, club seasons
     mart_*   team season + half, team form, player season, shots
          │
          ├──► notebooks/   one question each
          │
          └──► scripts/export_site_data.py                   (phase 4)
                    │
                    ▼
               site/  static dashboard: HTML + CSS + JS over JSON
```

Two rules hold the design together. **A metric is defined once**, in dbt, and
everything else — notebooks, export script, dashboard — reads it; a calculation
anywhere else means a mart is missing. And **the snapshot is pinned**, so an
analysis does not change its answer because the pipeline loaded another day.

Why a Parquet snapshot rather than querying Part 1 live, and why a static site
rather than Streamlit or Metabase: see `CLAUDE.md` §3.

---

## Running it

```bash
uv sync --extra dev
```

Everything below works with no database except the export itself.

```bash
# --- tests, lint, format: no data required ------------------------------------
uv run pytest -q
uv run ruff check .
uv run black --check .

# --- work against the synthetic fixture instead of real data -----------------
export GOLD_SNAPSHOT_DIR=tests/fixtures/gold

# --- export a real snapshot (needs Part 1's database, nothing else) ----------
cp .env.example .env     # defaults match Part 1's docker-compose
(cd ../football-data-engineering && docker compose up -d postgres)
uv run python scripts/export_gold.py

# --- build the metrics layer (works on the fixture or a real snapshot) -------
# Run from the repository root; writes data/analytics.duckdb.
uv run dbt build --project-dir dbt --profiles-dir dbt

# --- read the analyses (they read the marts, so build those first) -----------
uv run jupyter lab
```

If Part 1's schema has changed, the export refuses to run and names every
difference. Review what it affects, then:

```bash
uv run python scripts/export_gold.py --write-contract   # commit this on its own
```

---

## Layout

```
├── contracts/gold_columns.json   expected Gold schema; the export fails on drift
├── scripts/export_gold.py        Part 1 PostgreSQL -> Parquet snapshot + manifest
├── notebooks/                    one question each, outputs committed
├── src/football_analytics/
│   ├── gold.py                   the contract, and drift detection
│   ├── snapshot.py               the Parquet snapshot loader
│   ├── marts.py                  the mart loader; refuses a stale database
│   ├── stats.py                  seeded bootstrap intervals
│   └── viz.py                    chart style and pitch plots
├── tests/
│   ├── fixtures/make_gold_fixture.py   builds the synthetic snapshot CI runs on
│   └── test_*.py
├── dbt/
│   ├── macros/                   season_label (Part 1's August cutoff), grain test
│   ├── models/{staging,intermediate,marts}/
│   └── tests/                    singular tests: a wrong filter fails here
├── site/                         static dashboard                   (phase 4)
└── data/                         gitignored: snapshot + DuckDB store
```

### The fixture

`tests/fixtures/gold` is a hand-built Gold snapshot of a few dozen rows, in the
contract's exact column types, carrying **every documented trap on purpose** — an
`Unknown` member, a player who transfers mid-season, an abandoned-then-awarded
match, a postponed one with a phantom `0-0`, a fixture split across two rows,
duplicated shots, penalties on the penalty spot, every categorical value the real
data uses. A model that mishandles one fails in CI rather than in production. CI
also rebuilds it and diffs, so it cannot silently go stale.

The traps that only a *wrong filter* exposes live inside a **completed** fixture
season, because the assertion that catches them — every club played twice its
number of opponents — can only run where a full fixture list is expected. And
where the real snapshot and the fixture disagree about a trap's shape, the real
snapshot wins: a fixture carrying a trap in a form the data does not take would
let a broken model pass.

---

## Roadmap

| Phase | Deliverable | Status |
|-------|-------------|--------|
| 1 | Snapshot export, contract check, data profile | **Done** |
| 2 | dbt staging, `int_team_matches`, first two marts, CI on the fixture | **Done** |
| 3 | Analyses: points vs xPTS; is finishing a repeatable skill? | **Done** |
| 4 | Static dashboard — league table, team, players, shots | Next |
| 5 | README as the portfolio front page | |

### Question backlog

1. ✅ Which teams' points run ahead of or behind their xPTS — and does the gap
   persist into the second half of the season, or does xG difference predict what
   comes next better than points do?
2. ✅ Is finishing (goals − xG) a repeatable player skill, or mostly noise?
3. How big is home advantage, and does it differ between the big-5 leagues?
4. Where do goals come from? Conversion by pitch zone, situation and body part.
5. Does pressing intensity (PPDA) go with better results, in every league?
6. Do referees differ in how many cards they show, once the league is accounted for?

---

## Notes and limits

- **Observational data.** Findings are associations, never causes.
- **Not in the data at all:** possession, passes, tackles (FBref is blocked
  upstream), and stadium city and capacity. No metric is designed around them,
  and nothing is imputed.
- **Predictive modelling is out of scope** here — that is Part 3. This repository
  explains what happened; it does not forecast.
- **`data/` is gitignored.** Football-Data.org and Understat each have terms of
  use, and whether any snapshot or dashboard JSON may be published is an open
  decision (`CLAUDE.md` §13). Until then CI runs on the synthetic fixture.
