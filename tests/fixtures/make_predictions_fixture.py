"""Build tests/fixtures/predictions/: a synthetic copy of Part 3's predictions export.

The predictions page reads JSON that Part 3 (../football-data-science) writes with
its scripts/export_predictions.py. CI here does not check Part 3 out, and real
predictions are derived from Football-Data and Understat data whose publishing is
still undecided (CLAUDE.md §13) — so the dashboard smoke test runs the page on this
fixture instead, via ``PREDICTIONS_DIR=tests/fixtures/predictions``.

**It mirrors Part 3's export format, key for key.** If Part 3 changes that format,
change this generator in the same commit, or the page will pass here and break on
real data. Deterministic: re-running it reproduces the committed files exactly.

    uv run python tests/fixtures/make_predictions_fixture.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent / "predictions"
LEAGUES = {
    "PL": "Premier League",
    "PD": "La Liga",
    "BL1": "Bundesliga",
    "SA": "Serie A",
    "FL1": "Ligue 1",
}
OUTCOMES = ["H", "D", "A"]


def _probs(rng) -> list[float]:
    p = rng.dirichlet([4.5, 2.6, 3.2])
    return [round(float(v), 3) for v in p]


def holdout_rows(league: str, rng) -> list[dict]:
    rows = []
    for i in range(12):
        model, baseline = _probs(rng), _probs(rng)
        result = OUTCOMES[int(rng.choice(3, p=np.array(model) / sum(model)))]
        home_goals, away_goals = {"H": (2, 1), "D": (1, 1), "A": (0, 2)}[result]
        rows.append(
            {
                "date": f"2025-{8 + i // 4:02d}-{10 + i:02d}",
                "league": league,
                "home": f"{league} Club {2 * i % 10 + 1}",
                "away": f"{league} Club {(2 * i + 1) % 10 + 1}",
                "score": f"{home_goals}–{away_goals}",
                "result": result,
                "model": model,
                "baseline": baseline,
                "model_on_result": model[OUTCOMES.index(result)],
            }
        )
    return rows


def calibration(rng, spread: float) -> list[dict]:
    rows = []
    for outcome, bins in (("H", range(1, 8)), ("D", range(1, 4)), ("A", range(0, 7))):
        for b in bins:
            predicted = b / 10 + 0.05
            rows.append(
                {
                    "outcome": outcome,
                    "bin": f"{b / 10:.1f}–{(b + 1) / 10:.1f}",
                    "matches": int(rng.integers(30, 300)),
                    "predicted": round(predicted, 3),
                    "observed": round(predicted - spread * (predicted - 0.3), 3),
                }
            )
    return rows


def meta(rng) -> dict:
    scores = {
        "base_rates": {"rps": 0.2293, "log_loss": 1.0731, "brier": 0.6489, "n": 60},
        "elo": {"rps": 0.2076, "log_loss": 1.0103, "brier": 0.6046, "n": 60},
        "model": {"rps": 0.2091, "log_loss": 1.0225, "brier": 0.6105, "n": 60},
        "dc_goals": {"rps": 0.2054, "log_loss": 1.004, "brier": 0.5995, "n": 60},
        "dc_xg": {"rps": 0.2045, "log_loss": 1.0026, "brier": 0.5979, "n": 60},
    }
    labels = {
        "dc_xg": "Dixon-Coles on xG",
        "dc_goals": "Dixon-Coles on goals",
        "elo": "Elo rating",
        "model": "form model",
        "base_rates": "league base rates",
    }
    return {
        "snapshot": {
            "exported_at": "2026-09-20T12:00:00+00:00",
            "match_date_min": "2024-08-17",
            "match_date_max": "2025-08-30",
        },
        "model": {"key": "dc_xg", "label": "Dixon-Coles on xG", "settings": {"name": "fixture"}},
        "baseline": {"key": "elo", "label": "Elo rating"},
        "why_this_model": "synthetic fixture",
        "outcomes": OUTCOMES,
        "leagues": LEAGUES,
        "holdout": {
            "season": "2025/26",
            "matches": 60,
            "scores": scores,
            "labels": labels,
            "comparison": {
                "candidate": "Dixon-Coles on xG",
                "reference": "Elo rating",
                "metric": "rps",
                "difference": -0.0031,
                "low": -0.007,
                "high": 0.0008,
                "verdict": "cannot be distinguished",
                "matches": 60,
            },
            "calibration": {"dc_xg": calibration(rng, 0.05), "elo": calibration(rng, 0.25)},
            "draws": {
                "dc_xg": {
                    "actual_draw_rate": 0.255,
                    "mean_predicted_draw": 0.228,
                    "draw_most_likely_share": 0.0,
                },
                "elo": {
                    "actual_draw_rate": 0.255,
                    "mean_predicted_draw": 0.232,
                    "draw_most_likely_share": 0.0,
                },
            },
        },
        "prospective": {
            "freeze_id": "20261003T0900Z-0000000",
            "frozen_at": "2026-10-03T09:00:00+00:00",
            "scores_matches_after": "2026-10-03",
            "trained_on": {"first_match": "2024-08-17", "last_match": "2025-08-30", "matches": 60},
            "frozen_on": "synthetic fixture",
            "commit": "0" * 40,
            "status": "waiting",
            "reason": "frozen, and waiting for matches played after 2026-10-03",
        },
        "citation": "synthetic predictions fixture (tests/fixtures/make_predictions_fixture.py)",
        "no_market": "Compared with base rates and Elo only — Gold holds no betting odds.",
    }


def main() -> None:
    rng = np.random.default_rng(20261002)
    OUT.mkdir(parents=True, exist_ok=True)
    files = {"meta.json": meta(rng), "prospective.json": []}
    for league in LEAGUES:
        files[f"holdout_{league}.json"] = holdout_rows(league, rng)
    for name, payload in files.items():
        (OUT / name).write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        )
    print(f"wrote {len(files)} files to {OUT}")


if __name__ == "__main__":
    main()
