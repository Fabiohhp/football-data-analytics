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

Phases 2–5 (metrics layer, analyses, dashboard, portfolio README) are next; see
[Roadmap](#roadmap).

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

---

## Architecture

```
  Part 1 PostgreSQL  (gold.dim_*, gold.fact_*)
          │  scripts/export_gold.py — READ_ONLY attach + contract check
          ▼
  data/gold/*.parquet + manifest.json      exact copy, no transforms
          │  dbt build                                      (phase 2)
          ▼
  data/analytics.duckdb
     stg_*    1:1 with Gold — renames and casts only
     int_*    reusable reshapes
     mart_*   the metrics, defined once
          │
          ├──► notebooks/   one question each                (phase 3)
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

# --- read the analyses -------------------------------------------------------
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
│   ├── snapshot.py               the loader every notebook starts from
│   └── viz.py                    chart style and pitch plots
├── tests/
│   ├── fixtures/make_gold_fixture.py   builds the synthetic snapshot CI runs on
│   └── test_*.py
├── dbt/                          metrics layer                      (phase 2)
├── site/                         static dashboard                   (phase 4)
└── data/                         gitignored: snapshot + DuckDB store
```

### The fixture

`tests/fixtures/gold` is a hand-built Gold snapshot of a few dozen rows, in the
contract's exact column types, carrying **every documented trap on purpose** — an
`Unknown` member, a player who transfers mid-season, a null-xG match, a fixture
split across two rows, duplicated shots, penalties on the penalty spot. A model
that mishandles one fails in CI rather than in production. CI also rebuilds it
and diffs, so it cannot silently go stale.

---

## Roadmap

| Phase | Deliverable | Status |
|-------|-------------|--------|
| 1 | Snapshot export, contract check, data profile | **Done** |
| 2 | dbt staging, `int_team_matches`, first two marts, CI on the fixture | Next |
| 3 | Analyses: points vs xPTS; is finishing a repeatable skill? | |
| 4 | Static dashboard — league table, team, players, shots | |
| 5 | README as the portfolio front page | |

### Question backlog

1. Which teams' points run ahead of or behind their xPTS — and does the gap
   persist into the second half of the season, or does xG difference predict what
   comes next better than points do?
2. Is finishing (goals − xG) a repeatable player skill, or mostly noise?
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
