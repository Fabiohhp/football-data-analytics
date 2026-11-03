# Football Analytics — expected goals, and what they are worth

[![CI](https://github.com/Fabiohhp/football-data-analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/Fabiohhp/football-data-analytics/actions/workflows/ci.yml)

**Two questions about expected goals, answered from two complete seasons of the big-5
European leagues, with a tested metrics layer and a dashboard behind them.**

This is Part 2 of a three-part portfolio. Part 1 built the pipeline, this repository
turns its warehouse into answers, and Part 3 asks the predictive version of those
questions.

| Part | Scope | Repository |
|------|-------|------------|
| 1 — Data Engineering | Ingestion, Airflow, Bronze/Silver/Gold, data quality | [`football-data-engineering`](https://github.com/Fabiohhp/football-data-engineering) |
| **2 — Analytics & BI** | **Metrics layer, analyses, dashboard** | **this repository** |
| 3 — Machine Learning | Match outcome and xG models, evaluation | [`football-data-science`](https://github.com/Fabiohhp/football-data-science) |

**You do not need Part 1 to read this or to reproduce it.** Every number comes from a
Parquet snapshot committed in [`data/gold/`](data/gold), and CI also runs on a synthetic
fixture. A fresh clone needs no database and no credentials.

---

## The findings

### 1. Points that run ahead of expected points do not stay ahead

Some clubs collect more points than their chances deserved. Is that a trait that
carries into the next stretch of matches, or a run that ends?

> **It ends.** Across **192 club-seasons**, a club's first-half points-over-xPTS gap
> correlates with its second-half gap at **r = +0.13, with a 95% interval that
> reaches zero**. The clubs furthest ahead at the halfway mark gave up around five
> points of gap — and around five *actual* points — in the second half. The clubs
> furthest behind recovered by about as much.

![First-half against second-half points minus xPTS: a shapeless cloud with a nearly flat fitted line](docs/images/02-gap-persistence.png)

Grouping clubs by their first-half gap and following the same groups forward shows
the same thing from the other side. Every group lands on roughly zero:

![Clubs grouped by first-half gap, with each group's second-half gap alongside: all five collapse towards zero](docs/images/02-regression-to-mean.png)

The obvious follow-up — "so read xG instead of the table" — **does not hold up
either**, and that is the more interesting half of the answer:

> As a **single number**, first-half xG difference and xPTS are *not* distinguishably
> better than first-half points at tracking second-half points. Both paired-bootstrap
> intervals on the difference include zero.
>
> What xG difference *does* do is add information **on top of** points: with
> first-half points already in the model, first-half xG difference still carries a
> clearly non-zero coefficient, and explained variance in second-half points rises
> from **0.482 to 0.541**. The answer is "read both", not "xG wins".

→ [`notebooks/02_points_vs_xpts.ipynb`](notebooks/02_points_vs_xpts.ipynb)

### 2. Finishing is mostly noise — and two seasons cannot find the signal underneath

A player who scores more than their chances were worth is called a good finisher.
Does that repeat next season?

> **Barely.** Across **1,022 players** with 900+ minutes in both complete seasons,
> non-penalty finishing per 90 repeats at **r ≈ 0.10**. The *same players'* shot
> volume repeats at **r ≈ 0.90** and their npxG per 90 at **r ≈ 0.85** — so this is a
> noisy quantity, not a noisy dataset.

The control is the argument. Two panels, same players, same seasons, same source —
one measure sits on the diagonal and the other is a shapeless blob:

![Two scatter plots: npxG per 90 hugs the line of perfect repeatability, finishing per 90 does not](docs/images/03-finishing-vs-volume.png)

Restricting to players who actually shoot a lot was meant to settle whether a skill
hides underneath. It did not:

> The estimate clears zero at npxG ≥ 5 (133 players) but **not** at npxG ≥ 1
> (585 players — *more* statistical power), and is inconclusive at npxG ≥ 10
> (24 players). One threshold in three is not how a solid effect behaves, so it is
> reported as **"cannot distinguish a very small effect from none"** rather than as a
> discovery.
>
> For anything forward-looking, chance volume is the number to read: last season's
> npxG per 90 tracks next season's non-penalty goals per 90 at **r ≈ 0.78**, while
> last season's finishing is very slightly *negative*.

→ [`notebooks/03_is_finishing_repeatable.ipynb`](notebooks/03_is_finishing_repeatable.ipynb)

Before either analysis, [`notebooks/01_data_profile.ipynb`](notebooks/01_data_profile.ipynb)
establishes what is actually in the data — and corrected two documented assumptions
that would each have produced a plausible wrong number.

---

## The dashboard

Four static pages over the same tested marts, in the shape of an analyst's console:
a left rail of filters beside the numbers, dark by default, mono-forward. No
framework, no build step, no charting library, and no request to any other host at
runtime — the fonts are vendored, so it works offline.

**Every page answers before it tabulates.** A sentence at the top states what the
current view shows, a *What this means* block explains the metric in plain words, and
a **How to read it** block teaches the picture: a labelled miniature of that page's
own visual, then two or three worked examples naming rows that are on screen —
*"Aston Villa: ring at 51.1, dot well to its right at 65 — the longest bar in the
column."* They are selected by sorting the loaded rows, so they follow the filters.

Rates carry their **league percentile** as a bar, because "0.78 npxG per 90" does not
tell a reader whether that is good — and the percentile is computed in dbt against a
stated population, not in the browser.

The site is not hosted. These are screenshots of the real thing, generated from the real
pages, and [a few commands](#run-it-yourself) serve it locally from the committed snapshot.

| | |
|---|---|
| **League table** — points against xPTS, per league and season. A filled dot right of its ring means more points than the chances suggested. | **Team** — rolling xG created and conceded, with each match's result underneath. |
| [![League table](docs/images/dashboard-league-table.png)](docs/images/dashboard-league-table.png) | [![Team](docs/images/dashboard-team.png)](docs/images/dashboard-team.png) |
| **Players** — per-90 leaderboard with a minutes filter. Penalties stripped out. | **Shots** — every shot where it was taken, sized by xG, drawn as hand-written SVG in Understat's own coordinates. |
| [![Players](docs/images/dashboard-players.png)](docs/images/dashboard-players.png) | [![Shots](docs/images/dashboard-shots.png)](docs/images/dashboard-shots.png) |

**No metric is computed in the browser** — including the explanations. The frontend
filters, sorts and formats; every figure it shows, and every ranking or band it reads
out, was defined in dbt and tested there. A percentile depends on which players are
in the comparison, so it is a modelling decision, not a label. The rule is enforced
by the export script rather than left to discipline: it refuses to read any table
whose name does not begin with `mart_`.

---

## Why the numbers can be trusted

In this dataset a mistake produces a *plausible wrong number*, not an error. A league
table that is one match short still adds up. A player's season split across two clubs
still looks like a season. So the work went into making those failures loud.

**A schema contract.** `contracts/gold_columns.json` records every Gold column, type,
precision and nullability. The export **fails on any difference**, so a change
upstream surfaces at export time rather than as a wrong number in a chart.

**Fourteen documented traps, each measured against the real data** — and **two of
them turned out to be documented incorrectly**:

> **The status filter.** Filtering matches on `status = 'FINISHED'` silently drops
> three abandoned-then-**`AWARDED`** matches that were really played and really
> counted. Six clubs across three league-seasons then read **33 matches played in a
> 34-match season**.
>
> **The duplicated fixtures.** Twelve fixtures exist as two rows. They were documented
> as one row holding the result and one holding the xG — but **both are `FINISHED`
> and both carry the same scoreline**, so `status` does not separate them and a
> second, independent filter is needed. Without it a club plays 39 matches in a
> 38-match season.

Measuring the rest sharpened them. Own goals, for instance, are a *shot result* that
carries exactly 0.0000 xG and is not counted in Understat's own shot tally — so shot
rows equal reported shots plus own goals, exactly, on all 115,410 rows. That is now an
invariant the build checks, not a footnote.

**A synthetic fixture carrying every trap on purpose**, so a model that mishandles one
fails in CI rather than in production. Building it exposed that it had been giving
false confidence: it had no `AWARDED` match at all, and its penalties were placed by
an 8% random draw that produced *none* on some seeds — quietly removing the trap it
existed to guarantee.

**Tests that have been seen to fail.** Filtering on `FINISHED` alone, dropping the
duplicate-fixture filter, and `COALESCE`-ing xG to zero were each introduced on
purpose to confirm a test catches them. A test suite nobody has watched fail is a
decoration.

**Reconciliation against the real world**, not just against itself. 2024/25's final
tables are exact in all five leagues — Liverpool 84, Barcelona 88, Napoli 82, Bayern
82, PSG 84, with correct goal differences — and top scorers match: Mbappé 31, Salah
29 with 18 assists, Kane 26.

**16 dbt models · 137 dbt tests · 160 Python tests**, all green on the real snapshot
and on the fixture.

---

## How it is built

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
          └──► scripts/export_site_data.py — marts only, READ_ONLY
                    │
                    ▼
               site/  static dashboard: HTML + CSS + JS over JSON
```

Two rules hold the design together. **A metric is defined once**, in dbt, and
everything else reads it — a calculation anywhere else means a mart is missing. And
**the snapshot is pinned**, so an analysis does not change its answer because the
pipeline loaded another day.

**Why a Parquet snapshot rather than querying Part 1 live?** Every reader would have to
start Part 1's whole stack, and results would shift each time the pipeline loaded another
day. **Why a static site rather than Streamlit or Metabase?** Metabase needs a running
server and leaves none of the work visible in the repository; Streamlit can only be themed
so far, and free hosting puts idle apps to sleep. Static files load at once from any host.
**Why dbt for sixteen models?** Each metric is defined once in SQL, with tests, docs and
lineage.

### The data

Big-5 European leagues — Premier League, LaLiga, Bundesliga, Serie A, Ligue 1 —
combining Football-Data.org results with Understat expected-goals measures.

The snapshot behind every number above holds **3,733 matches, 115,410 player events
and 94,034 shots**: the complete 2024/25 and 2025/26 seasons plus 2026/27 to date.
Every analysis cites its snapshot's exact export time and `match_date` range from
`manifest.json`.

Football data provided by the Football-Data.org API. Expected-goals, player and shot data
come from [Understat](https://understat.com/). The data belongs to its providers, under
their terms, and is not covered by this repository's MIT License.

---

## Run it yourself

```bash
uv sync --extra dev
```

Everything below works from a fresh clone, with no database and no credentials, and gives
the numbers in this README.

```bash
# --- build the metrics layer on the committed snapshot -------------------------
uv run dbt build --project-dir dbt --profiles-dir dbt

# --- tests, lint, format -------------------------------------------------------
uv run pytest -q
uv run ruff check .
uv run black --check .

# --- read the analyses --------------------------------------------------------
uv run jupyter lab

# --- the dashboard ------------------------------------------------------------
uv run python scripts/export_site_data.py    # marts -> site/data/*.json
uv run python scripts/serve_site.py          # then open http://127.0.0.1:8000
uv run python scripts/check_site.py          # confirm it is serving site/, not a stale copy
```

The pages fetch JSON, so opening the HTML files directly does not work. Use
`serve_site.py` rather than `python -m http.server`: the stock server sends no
`Cache-Control`, so browsers reuse cached JavaScript and a reload can quietly run
the previous build's scripts against the current markup.

The browser smoke tests run in Chromium and Firefox, need them installed once per
machine (`uv run playwright install --with-deps chromium firefox`), and skip
themselves without.

To run everything on the synthetic fixture instead, `export GOLD_SNAPSHOT_DIR=tests/fixtures/gold`
first and build again.

To refresh the snapshot from Part 1, once its warehouse holds data:

```bash
cp .env.example .env     # defaults match Part 1's docker-compose
(cd ../football-data-engineering && docker compose up -d postgres)
uv run python scripts/export_gold.py
```

If that warehouse is empty, the export refuses to run and leaves the snapshot as it is. If
Part 1's schema has changed, it refuses too and names every difference. Review what it
affects, then `uv run python scripts/export_gold.py --write-contract` and commit that on
its own.

---

## Layout

```
├── contracts/gold_columns.json   expected Gold schema; the export fails on drift
├── scripts/
│   ├── export_gold.py            Part 1 PostgreSQL -> Parquet snapshot + manifest
│   ├── export_site_data.py       marts -> site/data/*.json (marts only, enforced)
│   ├── serve_site.py             local preview that never serves a stale script
│   ├── check_site.py             compares a running server against site/ on disk
│   └── export_readme_images.py   charts from the notebooks, screenshots from the site
├── dbt/
│   ├── macros/                   season_label (Part 1's August cutoff), grain test
│   ├── models/{staging,intermediate,marts}/
│   └── tests/                    singular tests: a wrong filter fails here
├── notebooks/                    one question each, outputs committed
├── site/                         static dashboard: 4 pages, no framework
│   ├── css/app.css               the whole design system
│   ├── js/                       common.js + one file per page
│   └── vendor/fonts/             Archivo + IBM Plex Mono, vendored (OFL)
├── src/football_analytics/
│   ├── gold.py                   the contract, and drift detection
│   ├── snapshot.py               the Parquet snapshot loader
│   ├── marts.py                  the mart loader; refuses a stale database
│   ├── stats.py                  seeded bootstrap intervals
│   └── viz.py                    chart style and pitch plots
├── tests/
│   ├── fixtures/make_gold_fixture.py   the synthetic snapshot CI runs on
│   └── test_*.py
├── data/gold/                    the committed snapshot, with its manifest
└── data/analytics.duckdb, site/data/   gitignored: DuckDB store, dashboard JSON
```

---

## Scope and limits

- **Observational data.** Every finding is an association, never a cause.
- **Two complete seasons.** Enough to show a near-zero correlation clearly; not enough
  to rule out a small persistent effect, and not enough to say much league by league.
- **Understat's xG model** is the yardstick throughout. "More goals than expected"
  means more than *that model* expected; a systematic bias in it would appear here as
  a player trait, and nothing in the data can separate the two.
- **Not in the data at all:** possession, passes, tackles, and stadium city and
  capacity. No metric is designed around them, and nothing is imputed.
- **Predictive modelling is out of scope** — that is Part 3. This repository explains
  what happened; it does not forecast. Both analyses stop exactly where a train/test
  split would begin.
- **The snapshot is committed so the numbers can be reproduced.** It holds data from
  Football-Data.org and Understat, which belongs to them under their own terms of use.

## Where this leads

[Part 3](https://github.com/Fabiohhp/football-data-science) picks up exactly where
question 1 stops: xG difference adds information about the next half-season, so can it
*predict* unseen matches? With walk-forward splits, baselines to beat and one season held
out, Dixon-Coles fitted to xG scores best and still cannot be told apart from an Elo
rating.

## Author

Fábio Henrique Peixe ([LinkedIn](https://www.linkedin.com/in/f%C3%A1bio-henrique-peixe/)). Also by
the author: [`football-scouting`](https://github.com/Fabiohhp/football-scouting), a recruitment
back-test on StatsBomb event data.

## License

The code is released under the [MIT License](LICENSE). The data belongs to its providers and is
used under their terms.
